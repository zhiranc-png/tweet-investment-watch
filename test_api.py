"""测试 adaptive.json 搜索 API 和其他端点"""
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
    "Accept": "*/*",
    "Referer": "https://x.com/",
    "Origin": "https://x.com",
})
s.cookies.set("auth_token", auth_token, domain=".x.com")
s.cookies.set("ct0", ct0, domain=".x.com")

# 方案 1: adaptive.json 搜索 (X 网页实际使用的 v2 搜索)
print("=" * 60)
print("方案 1: adaptive.json 搜索 API")
print("=" * 60)

params_list = [
    {"q": "NVDA", "count": 5, "query_source": "typed_query", "product": "Top"},
    {"q": "from:elonmusk", "count": 5, "query_source": "typed_query", "product": "Latest"},
]

for i, params in enumerate(params_list):
    try:
        resp = s.get("https://x.com/i/api/2/search/adaptive.json", params=params, timeout=15)
        print(f"\n测试 {i+1}: q={params['q']}, product={params['product']}")
        print(f"  状态码: {resp.status_code}")
        print(f"  Content-Type: {resp.headers.get('content-type','')}")
        print(f"  响应大小: {len(resp.content)} bytes")
        if resp.status_code == 200 and len(resp.content) > 0:
            try:
                data = resp.json()
                tweets = data.get("globalObjects", {}).get("tweets", {})
                users = data.get("globalObjects", {}).get("users", {})
                print(f"  ✅ 解析成功! tweets: {len(tweets)}, users: {len(users)}")
                for tid, tweet in list(tweets.items())[:3]:
                    uid = tweet.get("user_id_str", "")
                    user = users.get(uid, {})
                    screen = user.get("screen_name", "?")
                    text = tweet.get("full_text", tweet.get("text", ""))[:80]
                    likes = tweet.get("favorite_count", 0)
                    print(f"    - @{screen} (❤️{likes}): {text}")
            except Exception as e:
                print(f"  解析失败: {e}")
                print(f"  前 300 字: {resp.text[:300]}")
        elif resp.status_code == 200:
            print(f"  空响应!")
        else:
            print(f"  响应: {resp.text[:300]}")
    except Exception as e:
        print(f"  异常: {e}")

print()

# 方案 2: timeline/tweet 详情 API
print("=" * 60)
print("方案 2: 测试单条推文详情 API")
print("=" * 60)

# 找一条已知推文 ID 测试
test_tweet_ids = ["1827834567890123456", "1700000000000000000"]
# 用搜索结果里的 ID 更好，但先试试已知的

# 方案 3: 试试 statuses/lookup (v1.1 批量查推文)
print("=" * 60)
print("方案 3: v1.1 statuses/lookup")
print("=" * 60)
try:
    # 用 trends 里的热门话题，看看能不能找到推文 ID
    # 先试试随便一个 ID 格式对不对
    resp = s.get("https://api.x.com/1.1/statuses/lookup.json", 
                 params={"id": "1695001252306980864", "tweet_mode": "extended"},
                 timeout=10)
    print(f"状态码: {resp.status_code}")
    print(f"响应大小: {len(resp.content)} bytes")
    if resp.status_code == 200 and len(resp.content) > 10:
        try:
            data = resp.json()
            print(f"✅ 返回 {len(data) if isinstance(data, list) else 'object'}")
            if isinstance(data, list) and len(data) > 0:
                t = data[0]
                print(f"  - @{t.get('user',{}).get('screen_name','')}: {t.get('full_text','')[:80]}")
        except:
            print(f"响应: {resp.text[:300]}")
    else:
        print(f"响应: {resp.text[:300]}")
except Exception as e:
    print(f"异常: {e}")

print()

# 方案 4: 试试 v2 API 端点 (需要不同认证)
print("=" * 60)
print("方案 4: 试试 v2 搜索 (api.x.com/2/tweets/search/recent)")
print("=" * 60)
try:
    resp = s.get("https://api.x.com/2/tweets/search/recent", 
                 params={"query": "NVDA", "max_results": 5},
                 timeout=10)
    print(f"状态码: {resp.status_code}")
    print(f"响应前 300 字: {resp.text[:300]}")
except Exception as e:
    print(f"异常: {e}")
