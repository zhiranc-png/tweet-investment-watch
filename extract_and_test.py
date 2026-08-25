"""从 X 主页 JS 中提取最新的 GraphQL queryId 并测试关键端点"""
import os
import sys
import json
import re

sys.path.insert(0, os.path.dirname(__file__))

auth_token = os.environ.get("AUTH_TOKEN", "")
ct0 = os.environ.get("CT0", "")

import requests

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})
s.cookies.set("auth_token", auth_token, domain=".x.com")
s.cookies.set("ct0", ct0, domain=".x.com")

BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"

print("步骤 1: 访问 X 主页，获取 main.js")
resp = s.get("https://x.com/home", timeout=20)
js_files = re.findall(r'https://abs\.twimg\.com/responsive-web/client-web(?:-legacy)?/main\.[a-f0-9]+\.js', resp.text)
if not js_files:
    js_files = re.findall(r'src="([^"]*main\.[a-f0-9]+\.js)"', resp.text)
main_js_url = js_files[0] if js_files else ""
if not main_js_url.startswith("http"):
    main_js_url = "https://abs.twimg.com" + main_js_url
print(f"  main.js: {main_js_url[:80]}...")

resp2 = s.get(main_js_url, timeout=30)
js_text = resp2.text
print(f"  大小: {len(js_text)} bytes")

# 提取所有 operationName -> queryId 映射
all_qids = {}
# 模式: queryId:"xxx",operationName:"YYY"
for m in re.finditer(r'queryId["\s:]+([a-zA-Z0-9_-]+).*?operationName["\s:]+([A-Za-z_]+)', js_text):
    qid, name = m.group(1), m.group(2)
    all_qids[name] = qid
for m in re.finditer(r'operationName["\s:]+([A-Za-z_]+).*?queryId["\s:]+([a-zA-Z0-9_-]+)', js_text):
    name, qid = m.group(1), m.group(2)
    all_qids[name] = qid

print(f"  共找到 {len(all_qids)} 个 queryId")
print()

# 打印关键的几个
key_ops = ["SearchTimeline", "UserTweets", "UserByScreenName", "HomeTimeline", "BookmarkTimeline", "ListLatestTweetsTimeline"]
print("关键端点 queryId:")
for op in key_ops:
    qid = all_qids.get(op, "未找到")
    print(f"  {op}: {qid}")
print()

# 步骤 2: 测试 SearchTimeline
search_qid = all_qids.get("SearchTimeline", "")
if search_qid:
    print("=" * 60)
    print(f"测试 SearchTimeline (queryId: {search_qid})")
    print("=" * 60)
    
    s2 = requests.Session()
    s2.headers.update({
        "Authorization": f"Bearer {BEARER}",
        "x-csrf-token": ct0,
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
    })
    s2.cookies.set("auth_token", auth_token, domain=".x.com")
    s2.cookies.set("ct0", ct0, domain=".x.com")
    
    features = {
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "responsive_web_graphql_timeline_navigation_enabled": True,
    }
    
    variables = {"rawQuery": "NVDA min_faves:10", "count": 10, "querySource": "typed_query", "product": "Top"}
    
    try:
        url = f"https://x.com/i/api/graphql/{search_qid}/SearchTimeline"
        resp = s2.get(url, params={"variables": json.dumps(variables), "features": json.dumps(features)}, timeout=15)
        print(f"状态码: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            if "data" in data:
                search_data = data["data"].get("search_by_raw_query", {})
                timeline = search_data.get("search_timeline", {}).get("timeline", {})
                instructions = timeline.get("instructions", [])
                count = 0
                for inst in instructions:
                    for entry in inst.get("entries", []):
                        if "tweet" in entry.get("entryId", "").lower():
                            count += 1
                print(f"✅ 成功！找到 {count} 条推文")
                # 打印前 3 条
                printed = 0
                for inst in instructions:
                    for entry in inst.get("entries", []):
                        eid = entry.get("entryId", "")
                        if "tweet" in eid.lower() and printed < 3:
                            content = entry.get("content", {})
                            item = content.get("itemContent", {})
                            tweet = item.get("tweet_results", {}).get("result", {})
                            legacy = tweet.get("legacy", {})
                            user = tweet.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {})
                            text = legacy.get("full_text", "")[:80]
                            screen = user.get("screen_name", "?")
                            likes = legacy.get("favorite_count", 0)
                            print(f"  - @{screen} (❤️{likes}): {text}")
                            printed += 1
            else:
                print(f"无 data: {resp.text[:300]}")
        else:
            print(f"失败: {resp.text[:300]}")
    except Exception as e:
        print(f"异常: {e}")
        import traceback
        traceback.print_exc()

print()

# 步骤 3: 测试 UserTweets
user_tweets_qid = all_qids.get("UserTweets", "")
if user_tweets_qid:
    print("=" * 60)
    print(f"测试 UserTweets (queryId: {user_tweets_qid})")
    print("=" * 60)
    
    # 先拿 elonmusk 的 ID
    try:
        s2 = requests.Session()
        s2.headers.update({
            "Authorization": f"Bearer {BEARER}",
            "x-csrf-token": ct0,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "x-twitter-active-user": "yes",
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-client-language": "en",
        })
        s2.cookies.set("auth_token", auth_token, domain=".x.com")
        s2.cookies.set("ct0", ct0, domain=".x.com")
        
        features = {
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
        }
        
        # 获取用户 ID
        ub_qid = all_qids.get("UserByScreenName", "G3KGOASz96M-Qu0nwmGXNg")
        url = f"https://x.com/i/api/graphql/{ub_qid}/UserByScreenName"
        vars_ = {"screen_name": "elonmusk", "withSafetyModeUserFields": True}
        resp = s2.get(url, params={"variables": json.dumps(vars_), "features": json.dumps(features)}, timeout=10)
        user_id = resp.json()["data"]["user"]["result"]["rest_id"]
        print(f"elonmusk ID: {user_id}")
        
        # 测试 UserTweets
        url = f"https://x.com/i/api/graphql/{user_tweets_qid}/UserTweets"
        vars_ = {
            "userId": user_id,
            "count": 10,
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": False,
            "withVoice": False,
            "withV2Timeline": True,
        }
        resp = s2.get(url, params={"variables": json.dumps(vars_), "features": json.dumps(features)}, timeout=15)
        print(f"状态码: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            if "data" in data:
                user = data["data"].get("user", {})
                result = user.get("result", {})
                timeline = result.get("timeline_v2", {}).get("timeline", {})
                instructions = timeline.get("instructions", [])
                count = 0
                for inst in instructions:
                    for entry in inst.get("entries", []):
                        if "tweet" in entry.get("entryId", "").lower():
                            count += 1
                print(f"✅ 成功！找到 {count} 条推文")
                printed = 0
                for inst in instructions:
                    for entry in inst.get("entries", []):
                        eid = entry.get("entryId", "")
                        if "tweet" in eid.lower() and printed < 3:
                            content = entry.get("content", {})
                            item = content.get("itemContent", {})
                            tweet = item.get("tweet_results", {}).get("result", {})
                            legacy = tweet.get("legacy", {})
                            text = legacy.get("full_text", "")[:80]
                            likes = legacy.get("favorite_count", 0)
                            print(f"  - (❤️{likes}): {text}")
                            printed += 1
            else:
                print(f"无 data: {resp.text[:300]}")
        else:
            print(f"失败: {resp.text[:300]}")
    except Exception as e:
        print(f"异常: {e}")
        import traceback
        traceback.print_exc()
