# -*- coding: utf-8 -*-
"""候选 KOL 验证脚本 —— 通过生产采集链路（X GraphQL + 小号 cookie）验证新增 handle

验证内容：
  1. 账号存在且可访问（get_user_id 成功 = UserByScreenName 返回 rest_id）
  2. 活跃度（fetch_timeline 拉最近 3 条，看最后一条的发布时间与内容摘要）

输出：data/verify_candidates.json + 控制台逐条摘要
用法（在 GitHub Actions 中）：python hybrid/verify_candidates.py
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from x_client import build_session, XGraphQLClient, RateLimited, AuthRejected

# 待验证候选：中国/港股方向（2026-08-27 Jaron「增加a股，港股的kol跟踪」）
CANDIDATES = [
    "butao",            # 唐朝（唐书房），A股价值选股
    "francis_lun",      # Francis Lun，GEO Securities，港股评论
    "TechBuzzChina",    # 中国科技股播客
    "MarvinChen_",      # Bloomberg Intelligence 中国科技（猜测）
    "andyxie",          # 谢国忠（猜测）
    "XiangSongzuo",     # 向松祚（猜测）
]

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "data", "verify_candidates.json")


def find_legacy(obj, depth=0):
    """在 UserByScreenName result 的各种包装结构里递归找 legacy 块"""
    if depth > 4 or not isinstance(obj, dict):
        return None
    if isinstance(obj.get("legacy"), dict) and obj["legacy"]:
        return obj["legacy"]
    for k in ("unsafe_user_result", "result", "user"):
        if k in obj and isinstance(obj[k], dict):
            r = find_legacy(obj[k], depth + 1)
            if r:
                return r
    return None


def main():
    auth = os.environ.get("X_AUTH_TOKEN") or os.environ.get("AUTH_TOKEN") or ""
    ct0 = os.environ.get("X_CT0") or os.environ.get("CT0") or ""
    if not auth or not ct0:
        print("FATAL: 缺少 cookie 环境变量")
        sys.exit(1)

    client = XGraphQLClient(build_session(auth, ct0))
    try:
        qids = client.fetch_query_ids()
        print(f"queryIds 提取成功，共 {len(qids)} 个（UserByScreenName={'UserByScreenName' in qids}）")
    except Exception as e:
        print(f"queryId 提取失败（将用 fallback qid）：{e}")

    results = []
    for h in CANDIDATES:
        rec = {"handle": h, "exists": False, "active": None,
               "name": None, "followers": None, "description": None,
               "protected": None, "result_keys": None,
               "last_tweet_at": None, "last_tweet_preview": None, "error": None}
        try:
            # ① 存在性：UserByScreenName 解析 rest_id
            uid = client.get_user_id(h)
            rec["exists"] = True
            rec["user_id"] = uid

            # ② 尽力取资料（多种包装结构兼容）
            qid = client.query_ids.get("UserByScreenName",
                                       "G3KGOASz96M-Qu0nwmGXNg")
            try:
                data = client._gql_get(
                    qid, "UserByScreenName",
                    {"screen_name": h, "withSafetyModeUserFields": True},
                    f"profile {h}")
                result = data["data"]["user"]["result"]
                rec["result_keys"] = sorted(result.keys())[:10]
                legacy = find_legacy(result)
                if legacy:
                    rec.update({
                        "name": legacy.get("name"),
                        "followers": legacy.get("followers_count"),
                        "description": (legacy.get("description") or "")[:200],
                        "protected": legacy.get("protected", False),
                    })
            except Exception as pe:
                rec["error"] = f"profile: {str(pe)[:120]}"

            # ③ 活跃度：时间线最近 3 条（生产代码同款解析路径）
            try:
                tweets, display_name = client.fetch_timeline(h, 8)
                if rec.get("name") is None:
                    rec["name"] = display_name
                if tweets:
                    rec["last_tweet_at"] = tweets[0].get("created_at")
                    rec["last_tweet_preview"] = (tweets[0].get("text") or "")[:150].replace("\n", " ")
                    rec["active"] = True
                else:
                    rec["active"] = False
            except Exception as te:
                rec["active"] = False
                err = str(te)
                rec["error"] = (rec.get("error") or "") + f" | timeline: {err[:120]}"
        except RateLimited as e:
            rec["error"] = f"429: {e}"
        except AuthRejected as e:
            rec["error"] = f"auth: {e}"
            results.append(rec)
            break
        except Exception as e:
            rec["error"] = str(e)[:200]
        results.append(rec)
        print(f"[{h}] exists={rec['exists']} name={rec['name']} "
              f"followers={rec['followers']} last_tweet={rec['last_tweet_at']} "
              f"err={rec['error']}")

    out = {"verified_at": datetime.now(timezone.utc).isoformat(),
           "candidates": results}
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"结果已写入 {OUT_PATH}")
    ok = [r["handle"] for r in results if r["exists"] and r["active"]]
    print(f"验证通过（存在且活跃）：{ok}")


if __name__ == "__main__":
    main()
