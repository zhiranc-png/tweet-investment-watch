"""打印 entry 的详细结构"""
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
ub_qid = "G3KGOASz96M-Qu0nwmGXNg"

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

resp = s.get(
    f"https://x.com/i/api/graphql/{ub_qid}/UserByScreenName",
    params={"variables": json.dumps({"screen_name": "elonmusk", "withSafetyModeUserFields": True}), "features": json.dumps(features)},
    timeout=15
)
user_id = resp.json()["data"]["user"]["result"]["rest_id"]

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
timeline = data["data"]["user"]["result"]["timeline"]["timeline"]
instructions = timeline.get("instructions", [])

print(f"instructions 数量: {len(instructions)}")
print()

for i, inst in enumerate(instructions):
    itype = inst.get("type", "")
    entries = inst.get("entries", [])
    print(f"--- instruction[{i}] type={itype}, {len(entries)} entries ---")
    
    for j, entry in enumerate(entries[:3]):
        eid = entry.get("entryId", "")
        content = entry.get("content", {})
        print(f"\n  entry[{j}] id={eid[:50]}")
        print(f"    content keys: {list(content.keys())[:10]}")
        
        # 深度打印 content 的结构
        def deep_print(obj, indent=6, depth=0, max_depth=5):
            if depth > max_depth:
                print(" " * indent + "...")
                return
            if isinstance(obj, dict):
                keys = list(obj.keys())
                for k in keys[:8]:
                    v = obj[k]
                    if isinstance(v, dict):
                        print(" " * indent + f"{k}: dict ({len(v)} keys)")
                        deep_print(v, indent + 2, depth + 1, max_depth)
                    elif isinstance(v, list):
                        print(" " * indent + f"{k}: list ({len(v)} items)")
                        if v and depth < max_depth - 1:
                            deep_print(v[0], indent + 2, depth + 1, max_depth)
                    else:
                        v_str = str(v)[:60]
                        print(" " * indent + f"{k}: {v_str}")
                if len(keys) > 8:
                    print(" " * indent + f"... and {len(keys)-8} more keys")
            elif isinstance(obj, list):
                if obj:
                    deep_print(obj[0], indent, depth + 1, max_depth)
        
        deep_print(content, indent=6, max_depth=4)
    
    print()
