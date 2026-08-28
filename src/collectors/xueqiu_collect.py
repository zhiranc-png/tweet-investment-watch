# -*- coding: utf-8 -*-
"""
雪球 KOL 采集器（稳定版）
基于复现文档实现：匿名 xq_a_token 两步引导 + user_timeline.json 时间线
仅使用已验证的 2 个端点：search/user.json + statuses/user_timeline.json

稳定性改进：
- WAF 拦截自动重试（指数退避 + 重建 session）
- 自适应限速（遇 429/WAF 后自动放慢）
- 单 KOL 失败不影响整体，全部 try-except 包裹
- UID 缓存持久化，减少搜索请求
"""
import datetime as dt
import html
import json
import os
import random
import re
import sys
import time
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(HERE, "..", "config", "xueqiu_uid_cache.json")
WINDOW_HOURS = 48
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
TZ8 = dt.timezone(dt.timedelta(hours=8))

# ── 稳定性参数 ──────────────────────────────────────────
MAX_RETRIES = 3           # 单条请求最多重试次数
BASE_BACKOFF = 30         # 首次退避秒数
BACKOFF_MULTIPLIER = 2    # 每次重试退避倍数
BASE_SLEEP = 3.0          # KOL 间基础间隔（秒）
SLEEP_JITTER = 2.0        # 间隔随机抖动（±秒）
WAF_SLOW_FACTOR = 1.5     # 遇 WAF 后间隔倍率
MAX_SLOW_MULTIPLIER = 3.0 # 最大减速倍率


class WAFBlocked(Exception):
    """阿里云 WAF 拦截"""
    pass


def _sleep_with_jitter(base: float, jitter: float = SLEEP_JITTER):
    """带随机抖动的 sleep，避免固定频率被识别"""
    delay = base + random.uniform(-jitter, jitter)
    delay = max(0.5, delay)
    time.sleep(delay)


def build_session():
    """两步引导：首页 → /hq，拿到匿名 xq_a_token"""
    for attempt in range(MAX_RETRIES):
        try:
            s = requests.Session()
            s.headers.update({"User-Agent": UA, "Referer": "https://xueqiu.com/"})
            s.get("https://xueqiu.com/", timeout=15)
            _sleep_with_jitter(1.0, 0.5)
            s.get("https://xueqiu.com/hq", timeout=15)
            tok = s.cookies.get("xq_a_token")
            if tok:
                return s
            print(f"[xueqiu] 第 {attempt+1} 次引导失败，未拿到 token，重试...", flush=True)
        except Exception as e:
            print(f"[xueqiu] 第 {attempt+1} 次引导异常: {e}", flush=True)
        _sleep_with_jitter(BASE_BACKOFF * (BACKOFF_MULTIPLIER ** attempt), 5)
    raise RuntimeError("匿名 xq_a_token 引导失败（已重试 3 次）")


def _get_json(s, url, referer=None, retries=MAX_RETRIES):
    """发 GET 请求，检查 WAF，返回 JSON。带重试和退避。"""
    h = {"Referer": referer or "https://xueqiu.com/"}
    backoff = BASE_BACKOFF

    for attempt in range(retries):
        try:
            r = s.get(url, headers=h, timeout=20)
            ct = r.headers.get("content-type", "")
            body = r.text

            # WAF 检测
            if "aliyun_waf" in body[:2000] or "renderData" in body[:500]:
                raise WAFBlocked(f"WAF JS 质询 (attempt {attempt+1})")

            # 非 JSON 响应
            if "json" not in ct and not body.lstrip().startswith(("{", "[")):
                if r.status_code == 429:
                    raise WAFBlocked(f"429 Too Many Requests (attempt {attempt+1})")
                raise RuntimeError(f"非 JSON 响应 ({r.status_code} {ct[:40]}): {url[:80]}")

            return json.loads(body)

        except WAFBlocked as e:
            if attempt < retries - 1:
                print(f"[xueqiu] WAF 拦截，{backoff}s 后重试...", flush=True)
                time.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER
                # 重建 session（换 token）
                try:
                    new_s = build_session()
                    s.cookies = new_s.cookies
                except Exception:
                    pass
            else:
                raise

        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                print(f"[xueqiu] 请求超时，{backoff}s 后重试...", flush=True)
                time.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER
            else:
                raise

        except Exception:
            raise

    raise RuntimeError("重试耗尽")


def resolve_uid(s, name, cache):
    """名字→uid，带本地缓存；取粉丝最多的精确匹配"""
    if name in cache:
        return cache[name]
    url = ("https://xueqiu.com/query/v1/search/user.json"
           f"?q={requests.utils.quote(name)}&count=10&page=1")
    d = _get_json(s, url)
    best = None
    for u in d.get("list", []):
        if u.get("screen_name") == name or name in u.get("screen_name", ""):
            if best is None or u.get("followers_count", 0) > best.get("followers_count", 0):
                best = u
    if not best:
        raise RuntimeError(f"搜索未命中: {name}")
    cache[name] = best["id"]
    return best["id"]


def strip_html(t):
    """去除 HTML 标签，<br> 转换行"""
    t = html.unescape(t or "")
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    return t.strip()


def classify(st):
    """分类：原创 / 转发 / 回复"""
    text = st.get("text") or st.get("description") or ""
    if st.get("retweeted_status"):
        return "retweet"
    if text.lstrip().startswith("回复@") or text.lstrip().startswith("回复 <a"):
        return "reply"
    return "original"


def fetch_kol_timeline(s, uid, pages=3, current_sleep=BASE_SLEEP):
    """拉取单个 KOL 的时间线，pages=页数（20条/页）"""
    out = []
    for p in range(1, pages + 1):
        url = (f"https://xueqiu.com/statuses/user_timeline.json"
               f"?user_id={uid}&page={p}")
        d = _get_json(s, url, referer=f"https://xueqiu.com/u/{uid}")
        sts = d.get("statuses", [])
        out.extend(sts)
        if len(sts) < 20:
            break
        _sleep_with_jitter(current_sleep, SLEEP_JITTER)
    return out


def collect_xueqiu(roster, window_hours=WINDOW_HOURS, pages_per_kol=3):
    """
    主入口：采集雪球 KOL 时间线
    返回结构与 X 采集 JSON 同构，方便下游合并

    稳定性保证：
    - 单 KOL 失败不影响整体
    - WAF 拦截自动重试 + 重建 session
    - 自适应减速
    - 全部异常捕获
    """
    # 加载 UID 缓存
    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            cache = json.load(open(CACHE_PATH, encoding="utf-8"))
        except Exception:
            cache = {}

    # 构建 session
    try:
        s = build_session()
    except Exception as e:
        print(f"[xueqiu] ❌ Session 构建失败: {e}", flush=True)
        return {
            "collected_at": dt.datetime.now(TZ8).isoformat(),
            "window_hours": window_hours,
            "platform": "xueqiu",
            "kols_total": len(roster),
            "kols_ok": 0,
            "failures": [{"kol": "ALL", "error": f"session 构建失败: {e}"}],
            "tweets": [],
            "error": str(e),
        }

    today = dt.datetime.now(TZ8).strftime("%Y%m%d")
    cutoff = dt.datetime.now(TZ8) - dt.timedelta(hours=window_hours)

    tweets_all = []
    failures = []
    current_sleep = BASE_SLEEP
    waf_count = 0

    for i, kol in enumerate(roster, 1):
        name = kol["screen_name"]
        try:
            uid = kol.get("uid") or resolve_uid(s, name, cache)
            sts = fetch_kol_timeline(s, uid, pages=pages_per_kol, current_sleep=current_sleep)
            recent = 0
            for st in sts:
                iso = dt.datetime.fromtimestamp(st["created_at"] / 1000, TZ8)
                if iso < cutoff:
                    continue
                recent += 1
                tweets_all.append({
                    "source": "xueqiu",
                    "platform": "xueqiu",
                    "handle": name,
                    "uid": str(uid),
                    "display_name": st.get("user", {}).get("screen_name", name),
                    "id": str(st["id"]),
                    "created_at": iso.isoformat(),
                    "text": strip_html(st.get("text") or st.get("description") or ""),
                    "title": strip_html(st.get("title", "")),
                    "type": classify(st),
                    "retweet_count": st.get("retweet_count", 0),
                    "like_count": st.get("fav_count", 0),
                    "reply_count": st.get("reply_count", 0),
                    "follower_count": st.get("user", {}).get("followers_count", 0),
                    "url": f"https://xueqiu.com/{uid}/{st['id']}",
                    "kol_weight": kol.get("weight", 3.0),
                    "category": kol.get("category", "other"),
                })
            print(f"[{i}/{len(roster)}] {name}: {len(sts)} 条 / 窗口内 {recent} 条", flush=True)

        except WAFBlocked as e:
            waf_count += 1
            # 遇 WAF 后减速
            current_sleep = min(current_sleep * WAF_SLOW_FACTOR, BASE_SLEEP * MAX_SLOW_MULTIPLIER)
            failures.append({"kol": name, "error": f"WAF 拦截: {str(e)[:100]}"})
            print(f"[{i}/{len(roster)}] {name}: WAF 拦截，已减速到 {current_sleep:.1f}s", flush=True)
            # 重建 session
            try:
                s = build_session()
            except Exception:
                pass

        except Exception as e:
            failures.append({"kol": name, "error": str(e)[:200]})
            print(f"[{i}/{len(roster)}] {name}: FAILED -> {str(e)[:120]}", flush=True)

        # KOL 间间隔
        _sleep_with_jitter(current_sleep, SLEEP_JITTER)

    # 保存缓存
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        json.dump(cache, open(CACHE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass

    result = {
        "collected_at": dt.datetime.now(TZ8).isoformat(),
        "window_hours": window_hours,
        "platform": "xueqiu",
        "kols_total": len(roster),
        "kols_ok": len(roster) - len(failures),
        "failures": failures,
        "tweets": sorted(tweets_all, key=lambda x: x["created_at"], reverse=True),
        "waf_count": waf_count,
        "final_sleep": round(current_sleep, 1),
    }

    print(f"\n📊 雪球采集完成: {result['kols_ok']}/{result['kols_total']} 成功，"
          f"窗口内 {len(tweets_all)} 条，WAF 拦截 {waf_count} 次", flush=True)
    return result


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(HERE, ".."))
    from config.xueqiu_kol_list import XUEQIU_ROSTER
    result = collect_xueqiu(XUEQIU_ROSTER)
    out_path = os.path.join(HERE, "..", "..", "data", f"xueqiu_tweets_{dt.datetime.now(TZ8).strftime('%Y%m%d')}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    json.dump(result, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"输出: {out_path}")
