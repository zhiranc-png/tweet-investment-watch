# -*- coding: utf-8 -*-
"""入口：拉取监测池时间线 -> 窗口过滤 -> data/hybrid_tweets_YYYYMMDD.json

secret 读取优先级：X_AUTH_TOKEN/X_CT0（试点专用）→ AUTH_TOKEN/CT0（旧流程遗留）
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

    today = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d")
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=WINDOW_HOURS)
    order = list(PILOT_KOLS)
    random.Random(today).shuffle(order)  # 按日轮换，尾部损失不固定砸同一组
    max_kols = os.environ.get("MAX_KOLS", "").strip()
    if max_kols.isdigit() and int(max_kols) > 0:
        order = order[:int(max_kols)]
        print(f"MAX_KOLS 限量模式：只采集前 {len(order)} 个账号", flush=True)

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

    out = {
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "window_hours": WINDOW_HOURS,
        "kols_total": total,
        "kols_ok": total - len(failures),
        "failures": failures,
        "tweets": tweets_all,
    }
    os.makedirs("data", exist_ok=True)
    path = f"data/hybrid_tweets_{today}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    ok = total - len(failures)
    print(f"SUMMARY: {ok}/{total} 成功，窗口内推文 {len(tweets_all)} 条 -> {path}", flush=True)
    if ok / total < 0.8:
        print("FAIL: 成功率低于 80%，检查 secrets / 账号状态", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
