"""验证 UserTweets 能拿到完整推文，测试多个用户"""
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

def get_user_id(screen_name):
    resp = s.get(
        f"https://x.com/i/api/graphql/{ub_qid}/UserByScreenName",
        params={"variables": json.dumps({"screen_name": screen_name, "withSafetyModeUserFields": True}), "features": json.dumps(features)},
        timeout=15
    )
    data = resp.json()
    if "errors" in data:
        return None, data["errors"][0].get("message", "")
    return data["data"]["user"]["result"]["rest_id"], None

def get_user_tweets(user_id, count=20):
    resp = s.get(
        f"https://x.com/i/api/graphql/{ut_qid}/UserTweets",
        params={
            "variables": json.dumps({
                "userId": user_id,
                "count": count,
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
    if "errors" in data:
        return [], data["errors"][0].get("message", "")
    
    timeline = data["data"]["user"]["result"]["timeline"]["timeline"]
    tweets = []
    
    for inst in timeline.get("instructions", []):
        if inst.get("type") != "TimelineAddEntries":
            continue
        for entry in inst.get("entries", []):
            eid = entry.get("entryId", "")
            if not eid.startswith("tweet-"):
                continue
            
            content = entry.get("content", {})
            item = content.get("itemContent", {})
            tr = item.get("tweet_results", item.get("tweetResult", {}))
            result = tr.get("result", {}) if isinstance(tr, dict) else {}
            legacy = result.get("legacy", {})
            
            if not legacy:
                continue
            
            # 获取用户信息
            user_legacy = result.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {})
            
            tweets.append({
                "id": legacy.get("id_str", ""),
                "text": legacy.get("full_text", ""),
                "created_at": legacy.get("created_at", ""),
                "likes": legacy.get("favorite_count", 0),
                "retweets": legacy.get("retweet_count", 0),
                "replies": legacy.get("reply_count", 0),
                "views": result.get("views", {}).get("count", 0) if isinstance(result.get("views"), dict) else 0,
                "is_retweet": "retweeted_status_result" in legacy,
                "user_screen": user_legacy.get("screen_name", ""),
                "user_name": user_legacy.get("name", ""),
                "followers": user_legacy.get("followers_count", 0),
            })
    
    return tweets, None

# 测试多个投资相关用户
test_users = [
    "elonmusk",
    "Reuters",
    "Bloomberg",
    "WSJ",
    "jimcramer",
]

total_tweets = 0
for screen_name in test_users:
    print(f"@{screen_name}: ", end="")
    user_id, err = get_user_id(screen_name)
    if err:
        print(f"❌ 获取用户失败: {err[:50]}")
        continue
    
    tweets, err = get_user_tweets(user_id, count=20)
    if err:
        print(f"❌ 获取推文失败: {err[:50]}")
        continue
    
    total_tweets += len(tweets)
    print(f"✅ {len(tweets)} 条推文")
    
    # 打印前 2 条
    for t in tweets[:2]:
        rt = "🔁 " if t["is_retweet"] else ""
        print(f"  {rt}❤️{t['likes']} 🔁{t['retweets']} 👁{t['views']}: {t['text'][:80]}")
    
    print()

print(f"总计: {total_tweets} 条推文 (来自 {len(test_users)} 个用户)")
