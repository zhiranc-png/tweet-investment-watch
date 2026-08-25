"""验证 UserTweets 能拿到多少推文，并测试解析"""
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

# 从 main.js 提取 queryId
print("提取 queryId...")
s2 = requests.Session()
s2.headers.update({"User-Agent": "Mozilla/5.0"})
resp_home = s2.get("https://x.com/home", timeout=20)
js_urls = re.findall(r'https://abs\.twimg\.com/responsive-web/client-web(?:-legacy)?/main\.[a-f0-9]+\.js', resp_home.text)
main_url = js_urls[0] if js_urls else ""
resp_js = s2.get(main_url, timeout=30)
js_text = resp_js.text

qid_map = {}
for m in re.finditer(r'queryId\s*:\s*"([^"]+)"[^}]*?operationName\s*:\s*"([^"]+)"', js_text):
    qid_map[m.group(2)] = m.group(1)
for m in re.finditer(r'operationName\s*:\s*"([^"]+)"[^}]*?queryId\s*:\s*"([^"]+)"', js_text):
    qid_map[m.group(1)] = m.group(2)

user_tweets_qid = qid_map.get("UserTweets", "")
user_by_screen_qid = qid_map.get("UserByScreenName", "")
print(f"UserTweets queryId: {user_tweets_qid}")
print(f"UserByScreenName queryId: {user_by_screen_qid}")
print()

features = {
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "tweetypie_unmention_optimization_enabled": True,
    "vibe_api_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": False,
    "interactive_text_enabled": True,
    "responsive_web_text_conversations_enabled": False,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}

# 测试用户列表
test_users = ["elonmusk", "federalreserve", "WarrenBuffett", "jimcramer", "Reuters"]

for screen_name in test_users:
    print("=" * 60)
    print(f"测试 @{screen_name}")
    print("=" * 60)
    
    try:
        # 1. 获取用户 ID
        url = f"https://x.com/i/api/graphql/{user_by_screen_qid}/UserByScreenName"
        vars_ = {"screen_name": screen_name, "withSafetyModeUserFields": True}
        resp = s.get(url, params={"variables": json.dumps(vars_), "features": json.dumps(features)}, timeout=10)
        
        if resp.status_code != 200:
            # 用旧的 queryId 试试
            url = f"https://x.com/i/api/graphql/G3KGOASz96M-Qu0nwmGXNg/UserByScreenName"
            resp = s.get(url, params={"variables": json.dumps(vars_), "features": json.dumps(features)}, timeout=10)
        
        data = resp.json()
        if "errors" in data:
            print(f"  ❌ 错误: {data['errors'][0].get('message','')}")
            continue
        
        user_result = data["data"]["user"]["result"]
        user_id = user_result["rest_id"]
        user_name = user_result.get("legacy", {}).get("name", screen_name)
        followers = user_result.get("legacy", {}).get("followers_count", 0)
        print(f"  用户名: {user_name}")
        print(f"  用户 ID: {user_id}")
        print(f"  粉丝数: {followers:,}")
        
        # 2. 获取用户推文
        url = f"https://x.com/i/api/graphql/{user_tweets_qid}/UserTweets"
        vars_ = {
            "userId": user_id,
            "count": 20,
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": False,
            "withVoice": False,
            "withV2Timeline": True,
        }
        resp = s.get(url, params={"variables": json.dumps(vars_), "features": json.dumps(features)}, timeout=15)
        
        if resp.status_code != 200:
            print(f"  ❌ UserTweets 失败: {resp.status_code}")
            continue
        
        data = resp.json()
        if "errors" in data:
            print(f"  ❌ 错误: {data['errors'][0].get('message','')}")
            continue
        
        user = data["data"].get("user", {})
        result = user.get("result", {})
        timeline = result.get("timeline_v2", {}).get("timeline", {})
        instructions = timeline.get("instructions", [])
        
        tweets = []
        for inst in instructions:
            for entry in inst.get("entries", []):
                eid = entry.get("entryId", "")
                if "tweet" in eid.lower() and "-tweet-" in eid:
                    content = entry.get("content", {})
                    item = content.get("itemContent", {})
                    tweet_results = item.get("tweet_results", {})
                    tweet_result = tweet_results.get("result", {})
                    
                    # 跳过转推的卡片等
                    if not tweet_result:
                        continue
                    
                    legacy = tweet_result.get("legacy", {})
                    if not legacy:
                        continue
                    
                    tweet_id = legacy.get("id_str", "")
                    text = legacy.get("full_text", "")
                    created_at = legacy.get("created_at", "")
                    likes = legacy.get("favorite_count", 0)
                    retweets = legacy.get("retweet_count", 0)
                    replies = legacy.get("reply_count", 0)
                    is_retweet = legacy.get("retweeted_status_result", None) is not None
                    
                    # 获取用户信息
                    tweet_user = tweet_result.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {})
                    
                    tweets.append({
                        "id": tweet_id,
                        "text": text[:100],
                        "created_at": created_at,
                        "likes": likes,
                        "retweets": retweets,
                        "replies": replies,
                        "is_retweet": is_retweet,
                        "user": tweet_user.get("screen_name", screen_name),
                    })
        
        print(f"  推文数量: {len(tweets)}")
        for i, t in enumerate(tweets[:5]):
            rt = "🔁 " if t["is_retweet"] else ""
            print(f"  [{i+1}] {rt}@{t['user']} (❤️{t['likes']} 🔁{t['retweets']}): {t['text'][:70]}")
        
    except Exception as e:
        print(f"  异常: {e}")
        import traceback
        traceback.print_exc()
    
    print()
