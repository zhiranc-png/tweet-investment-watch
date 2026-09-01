# -*- coding: utf-8 -*-
"""入口：拉取监测池时间线 -> 窗口过滤 -> data/hybrid_tweets_YYYYMMDD.json

secret 读取优先级：X_AUTH_TOKEN/X_CT0（试点专用）→ AUTH_TOKEN/CT0（旧流程遗留）
2026-09-01 v5（增量采集模式）：
  - INCREMENTAL=1（默认开）：cutoff = 上次成功运行时间 - 1h 重叠（state 文件），只抓增量
    - state 文件 data/hybrid_state.json 随数据一起 commit，跨 run 持久
    - 当日文件 data/hybrid_tweets_YYYYMMDD.json 按 tweet_id 去重合并（新值覆盖旧值）
    - state 缺失 / 上次运行超 WINDOW_HOURS / MAX_KOLS 限量模式 → 自动回退 36h 全量窗口；限量模式不更新 state
  - 效果：GitHub schedule 每 3h 一轮，每轮 10-25 分钟；12:15 日报直接收割当日文件
2026-08-26 v4：
  - user_id 缓存持久化（hybrid/user_ids.json）：稳态每跑只需 ~54 个 UserTweets 请求，
    限流风险减半（108 -> ~55）
  - SEED_ONLY=1 模式：只解析 user_id 预热缓存，不拉时间线、不覆盖数据文件
  - 按日轮换 KOL 顺序，缓存未热时尾部限流损失不固定砸在同一组
  - 缓存 uid 失效（改名/封禁）自动重解析重试一次
"""
import datetime as dt
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import PILOT_KOLS, TWEETS_PER_KOL, WINDOW_HOURS
import x_client

RETRY_BUDGET = int(os.environ.get("RETRY_BUDGET", "8"))      # 全局 429 重试预算，可用环境变量覆盖
RETRY_WAIT_BASE = int(os.environ.get("RETRY_WAIT_BASE", "180"))  # 429 基础退避时间（秒），每次重试递增 60s
BASE_SLEEP_MIN = 8        # KOL 间基础间隔下限（秒）
BASE_SLEEP_MAX = 14       # KOL 间基础间隔上限（秒）
_slowdown_factor = 1.0    # 自适应减速因子，遇到 429 后递增
_budget = RETRY_BUDGET

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_ids.json")
STATE_PATH = os.path.join("data", "hybrid_state.json")
OVERLAP_HOURS = 1.0        # 增量窗口向前重叠，防时间边界漏推文
MAX_STATE_AGE_HOURS = 36.0  # state 过旧则视为失效，回退全量窗口


def to_iso(x_created_at: str) -> str:
    try:
        return dt.datetime.strptime(x_created_at, "%a %b %d %H:%M:%S %z %Y").isoformat()
    except Exception:
        return x_created_at


def in_window(iso_ts: str, cutoff: dt.datetime) -> bool:
    try:
        return dt.datetime.fromisoformat(iso_ts) >= cutoff
    except Exception:
        return True


def _fetch_once(client, handle: str, count: int):
    """429 消耗全局预算退避重试（指数退避 + 自适应减速）。"""
    global _budget, _slowdown_factor
    attempt = 0
    while True:
        try:
            return client.fetch_timeline(handle, count)
        except x_client.RateLimited:
            if _budget <= 0:
                raise
            _budget -= 1
            attempt += 1
            wait = RETRY_WAIT_BASE + (attempt - 1) * 60
            _slowdown_factor = min(_slowdown_factor * 1.5, 4.0)  # 最多4倍减速
            print(f"  429 限流，退避 {wait}s（第{attempt}次，剩余预算 {_budget}，减速因子 {_slowdown_factor:.1f}x）", flush=True)
            time.sleep(wait)


def fetch_with_budget(client, handle: str, count: int):
    """缓存 uid 失效时重解析重试一次。"""
    try:
        return _fetch_once(client, handle, count)
    except x_client.RateLimited:
        raise
    except Exception:
        if handle in client._user_cache:
            client._user_cache.pop(handle)
            print(f"  {handle}: 缓存 uid 可能失效，重新解析重试", flush=True)
            return _fetch_once(client, handle, count)
        raise


def save_cache(client):
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(client._user_cache, f, ensure_ascii=False, indent=1)
        print(f"cache: 已保存 {len(client._user_cache)} 个 user_id -> {CACHE_PATH}", flush=True)
    except Exception as e:
        print(f"cache: 保存失败 {e}", flush=True)


def load_state() -> dict:
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(now_utc: dt.datetime, tweets_in_file: int, incremental: bool):
    os.makedirs("data", exist_ok=True)
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "last_run_utc": now_utc.isoformat(),
                "mode": "incremental" if incremental else "full_window",
                "tweets_in_day_file": tweets_in_file,
            }, f, ensure_ascii=False, indent=1)
        print(f"state: 已保存 last_run_utc={now_utc.isoformat()}", flush=True)
    except Exception as e:
        print(f"state: 保存失败 {e}（下轮将回退全量窗口，不会漏数据）", flush=True)


def resolve_cutoff(now_utc: dt.datetime, incremental_on: bool, limited_mode: bool) -> tuple:
    """返回 (cutoff, 模式说明)。增量：上次成功运行 - 1h 重叠；越界/失效/限量回退 36h 全量。"""
    full_cutoff = now_utc - dt.timedelta(hours=WINDOW_HOURS)
    if not incremental_on or limited_mode:
        return full_cutoff, ("limited_full_window" if limited_mode else "full_window")
    state = load_state()
    last_raw = state.get("last_run_utc", "")
    try:
        last = dt.datetime.fromisoformat(last_raw)
        if last.tzinfo is None:
            last = last.replace(tzinfo=dt.timezone.utc)
        age_h = (now_utc - last).total_seconds() / 3600.0
        if age_h > MAX_STATE_AGE_HOURS:
            print(f"state: 上次运行距今 {age_h:.1f}h > {MAX_STATE_AGE_HOURS}h，回退全量窗口", flush=True)
            return full_cutoff, "full_window(state_stale)"
        cutoff = max(last - dt.timedelta(hours=OVERLAP_HOURS), full_cutoff)
        print(f"state: 上次运行 {last.isoformat()}（{age_h:.1f}h 前）→ 增量 cutoff={cutoff.isoformat()}", flush=True)
        return cutoff, "incremental"
    except (ValueError, TypeError):
        print("state: 缺失或格式无效 → 首轮全量窗口", flush=True)
        return full_cutoff, "full_window(no_state)"


def merge_day_file(path: str, new_tweets: list) -> tuple:
    """与当日已有文件按 tweet_id 去重合并（新值优先，全局唯一），返回 (合并后列表, 旧文件条数)。"""
    if not os.path.exists(path):
        # 批次内部也可能有重复（KOL 列表重复 / 转发），全局去重
        seen, out = set(), []
        for t in new_tweets:
            tid = t.get("tweet_id")
            if tid in seen:
                continue
            seen.add(tid)
            out.append(t)
        return out, 0
    try:
        with open(path, encoding="utf-8") as f:
            prev = json.load(f)
        prev_tweets = prev.get("tweets", [])
        merged_map = {}
        for t in new_tweets:          # 新值优先
            merged_map[t.get("tweet_id")] = t
        for t in prev_tweets:         # 旧文件中未被新值覆盖的保留
            merged_map.setdefault(t.get("tweet_id"), t)
        merged = list(merged_map.values())
        dup_new = len(new_tweets) + len(prev_tweets) - len(merged)
        print(f"merge: 旧文件 {len(prev_tweets)} 条 + 本次 {len(new_tweets)} 条 → 合并 {len(merged)} 条（去重 {dup_new} 条）", flush=True)
        return merged, len(prev_tweets)
    except Exception as e:
        print(f"merge: 旧文件读取失败（{e}），仅写本次 {len(new_tweets)} 条", flush=True)
        seen, out = set(), []
        for t in new_tweets:
            tid = t.get("tweet_id")
            if tid in seen:
                continue
            seen.add(tid)
            out.append(t)
        return out, 0


def main():
    auth_token = os.environ.get("X_AUTH_TOKEN") or os.environ.get("AUTH_TOKEN", "")
    ct0 = os.environ.get("X_CT0") or os.environ.get("CT0", "")
    secret_src = "X_AUTH_TOKEN/X_CT0" if os.environ.get("X_AUTH_TOKEN") else "AUTH_TOKEN/CT0(legacy)"
    if not auth_token or not ct0:
        print("ERROR: secrets 未注入", flush=True)
        sys.exit(2)
    seed_only = os.environ.get("SEED_ONLY", "").strip().lower() in ("1", "true", "yes")
    print(f"secret 来源: {secret_src} | seed_only={seed_only}", flush=True)

    session = x_client.build_session(auth_token, ct0)
    client = x_client.XGraphQLClient(session)
    if os.path.exists(CACHE_PATH):
        try:
            client._user_cache = json.load(open(CACHE_PATH, encoding="utf-8"))
            print(f"cache: 载入 {len(client._user_cache)} 个 user_id", flush=True)
        except Exception:
            pass

    now_utc = dt.datetime.now(dt.timezone.utc)
    today = now_utc.strftime("%Y%m%d")
    incremental_on = os.environ.get("INCREMENTAL", "1").strip().lower() not in ("0", "false", "no")
    order = list(PILOT_KOLS)
    random.Random(today).shuffle(order)  # 按日轮换，尾部损失不固定砸同一组
    max_kols = os.environ.get("MAX_KOLS", "").strip()
    limited_mode = max_kols.isdigit() and int(max_kols) > 0
    if limited_mode:
        order = order[:int(max_kols)]
        print(f"MAX_KOLS 限量模式：只采集前 {len(order)} 个账号", flush=True)
    cutoff, collect_mode = resolve_cutoff(now_utc, incremental_on, limited_mode)
    print(f"采集模式: {collect_mode} | cutoff={cutoff.isoformat()}（窗口过滤）", flush=True)

    tweets_all, failures = [], []
    total = len(order)
    for i, handle in enumerate(order, 1):
        if seed_only:
            try:
                uid = client.get_user_id(handle)
                print(f"[{i}/{total}] {handle}: uid={uid}", flush=True)
            except Exception as e:
                failures.append({"handle": handle, "error": str(e)[:200]})
                print(f"[{i}/{total}] {handle}: FAILED -> {str(e)[:200]}", flush=True)
            time.sleep(random.uniform(BASE_SLEEP_MIN, BASE_SLEEP_MAX) * _slowdown_factor)
            continue
        try:
            tweets, name = fetch_with_budget(client, handle, TWEETS_PER_KOL)
            recent = []
            for t in tweets:
                t["handle"] = handle
                t["display_name"] = name
                t["created_at"] = to_iso(t["created_at"])
                if in_window(t["created_at"], cutoff):
                    recent.append(t)
            tweets_all.extend(recent)
            print(f"[{i}/{total}] {handle}: 拉到 {len(tweets)} 条 / 窗口内 {len(recent)} 条", flush=True)
        except Exception as e:
            failures.append({"handle": handle, "error": str(e)[:200]})
            print(f"[{i}/{total}] {handle}: FAILED -> {str(e)[:200]}", flush=True)
        time.sleep(random.uniform(BASE_SLEEP_MIN, BASE_SLEEP_MAX) * _slowdown_factor)

    save_cache(client)

    if seed_only:
        ok = total - len(failures)
        print(f"SEED SUMMARY: {ok}/{total} 解析成功", flush=True)
        if ok / total < 0.8:
            sys.exit(1)
        return

    out_path = f"data/hybrid_tweets_{today}.json"
    merged, prev_n = merge_day_file(out_path, tweets_all)
    merged.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    out = {
        "collected_at": now_utc.isoformat(),
        "window_hours": WINDOW_HOURS,
        "collect_mode": collect_mode,
        "cutoff_iso": cutoff.isoformat(),
        "kols_total": total,
        "kols_ok": total - len(failures),
        "failures": failures,
        "prev_tweets": prev_n,
        "tweets": merged,
    }
    os.makedirs("data", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    ok = total - len(failures)
    print(f"SUMMARY: {ok}/{total} 成功，窗口内 {len(tweets_all)} 条 / 合并 {len(merged)} 条 -> {out_path}", flush=True)
    if ok / total < 0.8:
        print("FAIL: 成功率低于 80%，检查 secrets / 账号状态（state 不更新，下轮自动回补窗口）", flush=True)
        sys.exit(1)
    save_state(now_utc, len(merged), collect_mode == "incremental")


if __name__ == "__main__":
    main()
