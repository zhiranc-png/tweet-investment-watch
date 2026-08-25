"""测试不同的 X API 方案"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(__file__))

auth_token = os.environ.get("AUTH_TOKEN", "")
ct0 = os.environ.get("CT0", "")

print(f"auth_token 长度: {len(auth_token)}")
print(f"ct0 长度: {len(ct0)}")
print()

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

# 方案 1: v1.1 search/tweets (旧版 API，可能还能用)
print("=" * 60)
print("方案 1: v1.1 search/tweets.json")
print("=" * 60)
try:
    resp = s.get("https://api.x.com/1.1/search/tweets.json", 
                 params={"q": "NVDA", "count": 5, "result_type": "popular"},
                 timeout=15)
    print(f"状态码: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        statuses = data.get("statuses", [])
        print(f"返回 {len(statuses)} 条")
        if statuses:
            for t in statuses[:2]:
                print(f"  - @{t.get('user',{}).get('screen_name','')}: {t.get('text','')[:80]}")
    else:
        print(f"响应: {resp.text[:300]}")
except Exception as e:
    print(f"异常: {e}")

print()

# 方案 2: 尝试不同的 SearchTimeline queryId
print("=" * 60)
print("方案 2: 测试多个 GraphQL queryId")
print("=" * 60)

# 一些已知的 queryId（不同时期的）
query_ids = [
    ("7c31s4h0q57s8fr76n2a0g", "旧版"),
    ("lWkt2jfYlM8Pj074jVbL8Q", "另一个版本"),
    ("5v2Zz3-fN9T5f7hH2kG9dQ", "变体A"),
]

features = {
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}

variables = {"rawQuery": "NVDA", "count": 5, "querySource": "typed_query", "product": "Top"}

for qid, desc in query_ids:
    try:
        url = f"https://x.com/i/api/graphql/{qid}/SearchTimeline"
        resp = s.get(url, params={"variables": json.dumps(variables), "features": json.dumps(features)}, timeout=10)
        print(f"  [{desc}] {qid[:12]}... -> {resp.status_code}")
        if resp.status_code == 200:
            try:
                data = resp.json()
                if "data" in data:
                    print(f"    ✅ 有 data 字段!")
                    print(f"    keys: {list(data['data'].keys())}")
                else:
                    print(f"    无 data，响应前 200 字: {resp.text[:200]}")
            except:
                print(f"    非 JSON 响应")
    except Exception as e:
        print(f"  [{desc}] 异常: {e}")

print()

# 方案 3: 用 UserByScreenName 测试认证是否有效
print("=" * 60)
print("方案 3: 测试认证是否有效 (UserByScreenName)")
print("=" * 60)

user_query_ids = [
    "G3KGOASz96M-Qu0nwmGXNg",
    "sLV32h4s3d7f8j2k5l1m0n",
]

for qid in user_query_ids[:1]:
    try:
        url = f"https://x.com/i/api/graphql/{qid}/UserByScreenName"
        vars_ = {"screen_name": "elonmusk", "withSafetyModeUserFields": True}
        resp = s.get(url, params={"variables": json.dumps(vars_), "features": json.dumps(features)}, timeout=10)
        print(f"  UserByScreenName -> {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            if "data" in data:
                print(f"    ✅ 认证有效！有 data 字段")
                user = data["data"].get("user", {})
                result = user.get("result", {})
                print(f"    用户名: {result.get('legacy',{}).get('screen_name','N/A')}")
            else:
                print(f"    无 data: {resp.text[:200]}")
        else:
            print(f"    响应: {resp.text[:200]}")
    except Exception as e:
        print(f"  异常: {e}")
