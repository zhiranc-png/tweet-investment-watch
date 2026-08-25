"""解析 UserTweets 响应，验证能拿到推文"""
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
resp_js = s2.get(js_urls[0], timeout=30)
js_text = resp_js.text

qid_map = {}
for m in re.finditer(r'queryId\s*:\s*"([^"]+)"[^}]*?operationName\s*:\s*"([^"]+)"', js_text):
    qid_map[m.group(2)] = m.group(1)
for m in re.finditer(r'operationName\s*:\s*"([^"]+)"[^}]*?queryId\s*:\s*"([^"]+)"', js_text):
    qid_map[m.group(1)] = m.group(2)

ut_qid = qid_map.get("UserTweets", "")
ub_qid = "G3KGOASz96M-Qu0nwmGXNg"  # 已知能用的

features = {
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "tweetypie_unmention_optimization_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "view_counts_everywhere_api_enabled": True,
}

# 获取用户 ID
resp = s.get(
    f"https://x.com/i/api/graphql/{ub_qid}/UserByScreenName",
    params={"variables": json.dumps({"screen_name": "elonmusk", "withSafetyModeUserFields": True}), "features": json.dumps(features)},
    timeout=15
)
user_id = resp.json()["data"]["user"]["result"]["rest_id"]

# 获取推文
resp = s.get(
    f"https://x.com/i/api/graphql/{ut_qid}/UserTweets",
    params={
        "variables": json.dumps({
            "userId": user_id,
            "count": 20,
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": False,
            "withVoice": False,
            "withV2Timeline": True,
        }),
        "features": json.dumps(features)
    },
    timeout=15
)

data = resp.json()

# 新路径: data.user.result.timeline.timeline.instructions
timeline = data["data"]["user"]["result"]["timeline"]["timeline"]
instructions = timeline.get("instructions", [])

print(f"instructions 数量: {len(instructions)}")
print()

tweet_count = 0
for inst in instructions:
    itype = inst.get("type", "")
    entries = inst.get("entries", [])
    print(f"  [{itype}]: {len(entries)} entries")
    
    for entry in entries[:5]:
        eid = entry.get("entryId", "")
        content = entry.get("content", {})
        ctype = content.get("entryType", content.get("__typename", "?"))
        
        # 尝试多种路径找推文
        tweet_text = ""
        likes = 0
        
        # 路径 1: itemContent.tweet_results.result.legacy
        item = content.get("itemContent", {})
        tr = item.get("tweet_results", item.get("tweetResult", {}))
        result = tr.get("result", {}) if isinstance(tr, dict) else {}
        legacy = result.get("legacy", {})
        if legacy:
            tweet_text = legacy.get("full_text", "")
            likes = legacy.get("favorite_count", 0)
        
        # 路径 2: content.items[].item.itemContent.tweet_results.result.legacy
        if not tweet_text and "items" in content:
            for item2 in content.get("items", []):
                item_content = item2.get("item", {}).get("itemContent", {})
                tr2 = item_content.get("tweet_results", item_content.get("tweetResult", {}))
                result2 = tr2.get("result", {}) if isinstance(tr2, dict) else {}
                legacy2 = result2.get("legacy", {})
                if legacy2:
                    tweet_text = legacy2.get("full_text", "")
                    likes = legacy2.get("favorite_count", 0)
                    break
        
        if "tweet" in eid.lower():
            tweet_count += 1
        
        if tweet_text:
            print(f"    - {eid[:40]} (❤️{likes}): {tweet_text[:70]}")
        else:
            print(f"    - {eid[:40]} ({ctype})")

print()
print(f"总计找到 {tweet_count} 条推文 entry")
