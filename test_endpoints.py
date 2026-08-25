"""深度调试：找正确的 UserTweets 调用方式"""
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
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://x.com/",
    "Origin": "https://x.com",
})
s.cookies.set("auth_token", auth_token, domain=".x.com")
s.cookies.set("ct0", ct0, domain=".x.com")

# 先确认 UserByScreenName 能用（已知能用的）
print("验证 UserByScreenName 认证有效...")
resp = s.get(
    "https://x.com/i/api/graphql/G3KGOASz96M-Qu0nwmGXNg/UserByScreenName",
    params={
        "variables": json.dumps({"screen_name": "elonmusk", "withSafetyModeUserFields": True}),
        "features": json.dumps({
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_timeline_navigation_enabled": True,
        })
    },
    timeout=15
)
if resp.status_code == 200:
    data = resp.json()
    user_id = data["data"]["user"]["result"]["rest_id"]
    print(f"✅ 认证有效，elonmusk ID: {user_id}")
else:
    print(f"❌ UserByScreenName 失败: {resp.status_code}")
    sys.exit(1)

print()

# 从 main.js 提取所有 queryId 并测试
print("从 main.js 提取所有 queryId...")
s2 = requests.Session()
s2.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"})
resp_home = s2.get("https://x.com/home", timeout=20)
js_urls = re.findall(r'https://abs\.twimg\.com/responsive-web/client-web(?:-legacy)?/main\.[a-f0-9]+\.js', resp_home.text)
if not js_urls:
    js_urls = re.findall(r'src="([^"]*main\.[a-f0-9]+\.js)"', resp_home.text)

main_url = js_urls[0] if js_urls else ""
if not main_url.startswith("http"):
    main_url = "https://abs.twimg.com" + main_url

resp_js = s2.get(main_url, timeout=30)
js_text = resp_js.text

# 提取所有 (queryId, operationName) 对
# 更精确的正则：找类似 {queryId:"xxx", operationName:"YYY"} 的结构
pairs = []
# 模式 1: queryId:"...",operationName:"..."
for m in re.finditer(r'queryId\s*:\s*"([^"]+)"[^}]*?operationName\s*:\s*"([^"]+)"', js_text):
    pairs.append((m.group(2), m.group(1)))
# 模式 2: operationName:"...",queryId:"..."
for m in re.finditer(r'operationName\s*:\s*"([^"]+)"[^}]*?queryId\s*:\s*"([^"]+)"', js_text):
    pairs.append((m.group(1), m.group(2)))

# 去重
qid_map = {}
for name, qid in pairs:
    qid_map[name] = qid

print(f"找到 {len(qid_map)} 个 operation")

# 列出所有和 tweet/timeline/search/user 相关的
keywords = ["Tweet", "Timeline", "Search", "User", "Profile"]
relevant = {k: v for k, v in qid_map.items() if any(kw in k for kw in keywords)}
print(f"相关的 {len(relevant)} 个:")
for name in sorted(relevant.keys()):
    print(f"  {name}: {relevant[name]}")

print()

# 测试所有可能获取推文的端点
test_endpoints = [
    "UserTweets",
    "UserTweetsAndReplies",
    "UserMedia",
    "SearchTimeline",
    "SearchTypeahead",
    "HomeLatestTimeline",
    "HomeTimeline",
    "TweetDetail",
    "TweetResults",
    "ListLatestTweetsTimeline",
    "ProfileSpotlightsQuery",
]

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

print("=" * 60)
print("测试各个端点")
print("=" * 60)

for endpoint in test_endpoints:
    qid = qid_map.get(endpoint)
    if not qid:
        print(f"  {endpoint}: 无 queryId，跳过")
        continue
    
    try:
        url = f"https://x.com/i/api/graphql/{qid}/{endpoint}"
        
        if endpoint == "UserTweets":
            variables = {
                "userId": user_id,
                "count": 5,
                "includePromotedContent": False,
                "withQuickPromoteEligibilityTweetFields": False,
                "withVoice": False,
                "withV2Timeline": True,
            }
        elif endpoint == "UserTweetsAndReplies":
            variables = {
                "userId": user_id,
                "count": 5,
                "includePromotedContent": False,
                "withCommunity": True,
                "withVoice": False,
                "withV2Timeline": True,
            }
        elif endpoint == "UserMedia":
            variables = {
                "userId": user_id,
                "count": 5,
                "includePromotedContent": False,
                "withV2Timeline": True,
            }
        elif endpoint == "SearchTimeline":
            variables = {"rawQuery": "NVDA", "count": 5, "querySource": "typed_query", "product": "Top"}
        elif endpoint == "SearchTypeahead":
            variables = {"q": "NVDA", "result_type": "users"}
        elif endpoint == "TweetDetail":
            variables = {"focalTweetId": "1695001252306980864", "with_rux_injections": False, "includePromotedContent": True, "withCommunity": True, "withQuickPromoteEligibilityTweetFields": True, "withBirdwatchNotes": False, "withVoice": True, "withV2Timeline": True}
        elif endpoint == "ProfileSpotlightsQuery":
            variables = {"screen_name": "elonmusk"}
        else:
            variables = {}
        
        resp = s.get(url, params={"variables": json.dumps(variables), "features": json.dumps(features)}, timeout=10)
        
        if resp.status_code == 200:
            try:
                data = resp.json()
                if "errors" in data:
                    errors = data["errors"]
                    msg = errors[0].get("message", "") if errors else "unknown error"
                    print(f"  {endpoint}: 200 但有错误: {msg[:60]}")
                elif "data" in data:
                    # 检查是否有实际数据
                    data_keys = list(data["data"].keys())
                    print(f"  {endpoint}: ✅ 200 有数据! keys={data_keys}")
                else:
                    print(f"  {endpoint}: 200 无 data 字段")
            except:
                print(f"  {endpoint}: 200 非 JSON ({len(resp.content)} bytes)")
        else:
            print(f"  {endpoint}: {resp.status_code}")
    except Exception as e:
        print(f"  {endpoint}: 异常 - {str(e)[:50]}")
