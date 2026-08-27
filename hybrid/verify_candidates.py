# -*- coding: utf-8 -*-
"""候选 KOL 验证脚本 —— 通过生产采集链路（X GraphQL + 小号 cookie）验证新增 handle

验证内容：
  1. 账号存在且可访问（UserByScreenName 返回完整资料）
  2. 活跃度（拉最近 2 条推，看最后一条的发布时间与内容摘要）

输出：data/verify_candidates.json + 控制台逐条摘要
用法（在 GitHub Actions 中）：python hybrid/verify_candidates.py
"""
import json
import os
import sys
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from x_client import build_session, XGraphQLClient, RateLimited, AuthRejected

# 待验证候选：中国/港股方向（2026-08-27 Jaron「增加a股，港股的kol跟踪」）
CANDIDATES = [
    "michaelxpettis",   # Michael Pettis 北大，中国宏观/贸易
    "AliciaGarciaH",    # Alicia García-Herrero Natixis 亚太首席经济学家
    "AndrewBatson",     # Gavekal Dragonomics 中国研究
    "BradSetser",       # CFR 中国资本流动/外汇
    "DuncanWrigley",    # Gavekal 中国经济学家
    "SCMPNews",         # 南华早报 香港/中国新闻与市场
]

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "data", "verify_candidates.json")


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
               "created_at": None, "protected": None,
               "last_tweet_at": None, "last_tweet_preview": None, "error": None}
        try:
            qid = client.query_ids.get("UserByScreenName", "G3KGOASz96M-Qu0nwmGXNg")
            data = client._gql_get(qid, "UserByScreenName",
                                     {"screen_name": h, "withSafetyModeUserFields": True},
                                     f"verify {h}")
            legacy = data["data"]["user"]["result"]["legacy"]
            rec.update({
                "exists": True,
                "name": legacy.get("name"),
                "followers": legacy.get("followers_count"),
                "description": (legacy.get("description") or "")[:200],
                "created_at": legacy.get("created_at"),
                "protected": legacy.get("protected", False),
            })
            try:
                tweets, _ = client.fetch_timeline(h, 2)
                if tweets:
                    rec["last_tweet_at"] = tweets[0].get("created_at")
                    rec["last_tweet_preview"] = (tweets[0].get("text") or "")[:150].replace("\n", " ")
                    rec["active"] = True
                else:
                    rec["active"] = False
            except Exception as te:
                rec["active"] = False
                rec["error"] = f"timeline: {str(te)[:150]}"
        except RateLimited as e:
            rec["error"] = f"429: {e}"
        except AuthRejected as e:
            rec["error"] = f"auth: {e}"
            results.append(rec)
            break  # 认证失败后续全没戏，提前退出
        except Exception as e:
            msg = str(e)
            rec["error"] = ("unavailable/不存在" if "unavailable" in msg.lower()
                            or "suspend" in msg.lower() or "Could not find" in msg else msg[:200])
        results.append(rec)
        print(f"[{h}] exists={rec['exists']} followers={rec['followers']} "
              f"last_tweet={rec['last_tweet_at']} err={rec['error']}")

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
