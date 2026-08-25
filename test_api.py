"""测试 UserTweets 和 v1.1 方案"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(__file__))

auth_token = os.environ.get("AUTH_TOKEN", "")
ct0 = os.environ.get("CT0", "")

import requests

BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

s = requests.Session()
s.headers.update({
    "Authorization": f"Bearer {BEARER}",
    "x-csrf-token": ct0,
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "x-twitter-active-user": "yes",
    "x-twitter-auth-type": "OAuth2Session",
    "x-twitter-client-language": "en",
})
s.cookies.set("auth_token", auth_token, domain=".x.com")
s.cookies.set("ct0", ct0, domain=".x.com")

features = {
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}

# 方案 1: v1.1 search 返回了什么
print("=" * 60)
print("方案 1: v1.1 search/tweets.json 原始响应")
print("=" * 60)
try:
    resp = s.get("https://api.x.com/1.1/search/tweets.json", 
                 params={"q": "NVDA", "count": 3},
                 timeout=15)
    print(f"状态码: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('content-type','')}")
    print(f"响应前 500 字:")
    print(resp.text[:500])
except Exception as e:
    print(f"异常: {e}")

print()

# 方案 2: UserTweets - 先获取用户 ID，再拿推文
print("=" * 60)
print("方案 2: UserTweets (获取大V推文)")
print("=" * 60)

# 先用 UserByScreenName 拿用户 rest_id
try:
    url = "https://x.com/i/api/graphql/G3KGOASz96M-Qu0nwmGXNg/UserByScreenName"
    vars_ = {"screen_name": "elonmusk", "withSafetyModeUserFields": True}
    resp = s.get(url, params={"variables": json.dumps(vars_), "features": json.dumps(features)}, timeout=10)
    data = resp.json()
    user_id = data["data"]["user"]["result"]["rest_id"]
    print(f"elonmusk rest_id: {user_id}")
except Exception as e:
    print(f"获取用户 ID 失败: {e}")
    user_id = None

if user_id:
    # 测试不同的 UserTweets queryId
    user_tweets_query_ids = [
        ("Uuw5X2n3tuGE_SZTkFHDZA", "UserTweets 旧版"),
        ("7dM3mhfFhGO1Bys93tPw2g", "UserTweets 变体"),
        ("V7vXp3q2z1w4y8a6b9c0d", "UserTweets 猜测A"),
    ]
    
    for qid, desc in user_tweets_query_ids:
        try:
            url = f"https://x.com/i/api/graphql/{qid}/UserTweets"
            vars_ = {
                "userId": user_id,
                "count": 5,
                "includePromotedContent": False,
                "withQuickPromoteEligibilityTweetFields": False,
                "withVoice": False,
                "withV2Timeline": True,
            }
            resp = s.get(url, params={"variables": json.dumps(vars_), "features": json.dumps(features)}, timeout=10)
            print(f"  [{desc}] {qid[:12]}... -> {resp.status_code}")
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if "data" in data:
                        print(f"    ✅ 有 data!")
                        # 尝试解析推文
                        user = data["data"].get("user", {})
                        result = user.get("result", {})
                        timeline = result.get("timeline_v2", {}).get("timeline", {})
                        instructions = timeline.get("instructions", [])
                        print(f"    instructions: {len(instructions)} 条")
                        for inst in instructions:
                            entries = inst.get("entries", [])
                            print(f"      {inst.get('type')}: {len(entries)} entries")
                            for entry in entries[:2]:
                                eid = entry.get("entryId", "")
                                if "tweet" in eid.lower():
                                    content = entry.get("content", {})
                                    item_content = content.get("itemContent", {})
                                    tweet_results = item_content.get("tweet_results", {})
                                    tweet_result = tweet_results.get("result", {})
                                    legacy = tweet_result.get("legacy", {})
                                    text = legacy.get("full_text", "")[:80]
                                    print(f"        - {text}")
                    else:
                        print(f"    无 data: {resp.text[:200]}")
                except Exception as e:
                    print(f"    解析失败: {e}")
        except Exception as e:
            print(f"  [{desc}] 异常: {e}")

print()

# 方案 3: 试试 trending 相关 API
print("=" * 60)
print("方案 3: 试试 trends/place (v1.1)")
print("=" * 60)
try:
    resp = s.get("https://api.x.com/1.1/trends/place.json", params={"id": 1}, timeout=10)
    print(f"状态码: {resp.status_code}")
    if resp.status_code == 200:
        try:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                trends = data[0].get("trends", [])
                print(f"✅ 获取到 {len(trends)} 个趋势")
                for t in trends[:5]:
                    print(f"  - {t.get('name','')} ({t.get('tweet_volume','N/A')})")
        except:
            print(f"响应: {resp.text[:300]}")
    else:
        print(f"响应: {resp.text[:300]}")
except Exception as e:
    print(f"异常: {e}")
