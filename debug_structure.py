"""打印 UserTweets 完整响应结构"""
import os
import sys
import json
import re

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

# 提取 queryId
s2 = requests.Session()
s2.headers.update({"User-Agent": "Mozilla/5.0"})
resp_home = s2.get("https://x.com/home", timeout=20)
js_urls = re.findall(r'https://abs\.twimg\.com/responsive-web/client-web(?:-legacy)?/main\.[a-f0-9]+\.js', resp_home.text)
main_url = js_urls[0]
resp_js = s2.get(main_url, timeout=30)
js_text = resp_js.text

qid_map = {}
for m in re.finditer(r'queryId\s*:\s*"([^"]+)"[^}]*?operationName\s*:\s*"([^"]+)"', js_text):
    qid_map[m.group(2)] = m.group(1)
for m in re.finditer(r'operationName\s*:\s*"([^"]+)"[^}]*?queryId\s*:\s*"([^"]+)"', js_text):
    qid_map[m.group(1)] = m.group(2)

# 用旧的 UserByScreenName queryId (已知能用的)
ub_qid = "G3KGOASz96M-Qu0nwmGXNg"
ut_qid = qid_map.get("UserTweets", "")

print(f"UserByScreenName: {ub_qid}")
print(f"UserTweets: {ut_qid}")
print()

features = {
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "tweetypie_unmention_optimization_enabled": True,
    "vibe_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "view_counts_everywhere_api_enabled": True,
}

# 获取 elonmusk 的 ID
resp = s.get(
    f"https://x.com/i/api/graphql/{ub_qid}/UserByScreenName",
    params={
        "variables": json.dumps({"screen_name": "elonmusk", "withSafetyModeUserFields": True}),
        "features": json.dumps(features)
    },
    timeout=15
)
user_id = resp.json()["data"]["user"]["result"]["rest_id"]
print(f"elonmusk ID: {user_id}")
print()

# 获取 UserTweets 并打印结构
resp = s.get(
    f"https://x.com/i/api/graphql/{ut_qid}/UserTweets",
    params={
        "variables": json.dumps({
            "userId": user_id,
            "count": 10,
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": False,
            "withVoice": False,
            "withV2Timeline": True,
        }),
        "features": json.dumps(features)
    },
    timeout=15
)

print(f"状态码: {resp.status_code}")
data = resp.json()

# 递归打印结构
def print_structure(obj, indent=0, max_depth=6):
    prefix = "  " * indent
    if indent > max_depth:
        print(f"{prefix}...(max depth)")
        return
    if isinstance(obj, dict):
        keys = list(obj.keys())
        print(f"{prefix}dict ({len(keys)} keys): {keys[:15]}")
        for k in keys[:5]:
            v = obj[k]
            if isinstance(v, (dict, list)):
                print(f"{prefix}  '{k}':")
                print_structure(v, indent + 2, max_depth)
            else:
                v_str = str(v)[:80]
                print(f"{prefix}  '{k}': {v_str}")
    elif isinstance(obj, list):
        print(f"{prefix}list ({len(obj)} items)")
        if obj and len(obj) > 0:
            print(f"{prefix}  [0]:")
            print_structure(obj[0], indent + 2, max_depth)
    else:
        print(f"{prefix}{type(obj).__name__}: {str(obj)[:80]}")

if "errors" in data:
    print("有错误:")
    for e in data["errors"]:
        print(f"  - {e.get('message','')}")
    print()

if "data" in data:
    print("data 结构:")
    print_structure(data["data"], indent=2, max_depth=8)
else:
    print("没有 data 字段")
    print(f"响应前 500 字: {resp.text[:500]}")
