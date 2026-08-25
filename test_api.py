"""深度调试：打印 API 原始响应"""
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
QUERY_ID = "7c31s4h0q57s8fr76n2a0g"

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
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
}

print("=" * 60)
print("测试 1: 搜索 'NVDA min_faves:100'")
print("=" * 60)

url = f"https://x.com/i/api/graphql/{QUERY_ID}/SearchTimeline"
variables = {"rawQuery": "NVDA min_faves:100", "count": 10, "querySource": "typed_query", "product": "Top"}

try:
    resp = s.get(url, params={"variables": json.dumps(variables), "features": json.dumps(features)}, timeout=15)
    print(f"状态码: {resp.status_code}")
    print(f"响应头 Content-Type: {resp.headers.get('content-type', '')}")
    print()
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"JSON keys: {list(data.keys())}")
        
        if "data" in data:
            search = data["data"].get("search_by_raw_query", {})
            print(f"search_by_raw_query keys: {list(search.keys())}")
            
            timeline = search.get("search_timeline", {}).get("timeline", {})
            print(f"timeline keys: {list(timeline.keys())}")
            
            instructions = timeline.get("instructions", [])
            print(f"instructions 数量: {len(instructions)}")
            
            for i, inst in enumerate(instructions):
                print(f"  [{i}] type={inst.get('type')}, entries={len(inst.get('entries', []))}")
                if inst.get("entries"):
                    for j, entry in enumerate(inst["entries"][:3]):
                        print(f"      entry[{j}]: id={entry.get('entryId')[:50]}")
        else:
            print("没有 data 字段")
            print(f"完整响应前 500 字: {resp.text[:500]}")
    else:
        print(f"响应内容前 500 字: {resp.text[:500]}")
        
except Exception as e:
    print(f"❌ 异常: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 60)
print("测试 2: 检查 cookies 是否被正确发送")
print("=" * 60)
# 访问一个简单的端点看看认证状态
try:
    resp2 = s.get("https://x.com/i/api/1.1/account/settings.json", timeout=10)
    print(f"settings.json 状态码: {resp2.status_code}")
    print(f"响应前 300 字: {resp2.text[:300]}")
except Exception as e:
    print(f"异常: {e}")
