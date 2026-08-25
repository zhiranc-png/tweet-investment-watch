"""从 X 主页 JS 中提取最新的 GraphQL queryId"""
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

print("=" * 60)
print("步骤 1: 访问 X 主页，获取 main.js URL")
print("=" * 60)

try:
    resp = s.get("https://x.com/home", timeout=15)
    print(f"主页状态码: {resp.status_code}")
    print(f"响应大小: {len(resp.text)} bytes")
    
    # 找 main.xxxx.js
    js_files = re.findall(r'https://abs\.twimg\.com/responsive-web/client-web-legacy/main\.[a-f0-9]+\.js', resp.text)
    if not js_files:
        js_files = re.findall(r'https://abs\.twimg\.com/responsive-web/client-web/main\.[a-f0-9]+\.js', resp.text)
    if not js_files:
        js_files = re.findall(r'src="([^"]*main\.[a-f0-9]+\.js)"', resp.text)
    
    print(f"找到 {len(js_files)} 个 main.js")
    for js in js_files[:3]:
        print(f"  - {js[:100]}")
        
except Exception as e:
    print(f"异常: {e}")
    import traceback
    traceback.print_exc()
    js_files = []

print()

if js_files:
    print("=" * 60)
    print("步骤 2: 下载 main.js 并提取 queryId")
    print("=" * 60)
    
    main_js_url = js_files[0]
    if not main_js_url.startswith("http"):
        main_js_url = "https://abs.twimg.com" + main_js_url
    
    try:
        resp = s.get(main_js_url, timeout=30)
        print(f"main.js 大小: {len(resp.text)} bytes")
        
        # 搜索 SearchTimeline 的 queryId
        # 模式: e.exports={queryId:"xxx",operationName:"SearchTimeline"
        search_matches = re.findall(r'queryId["\s:]+([a-zA-Z0-9_-]+)["\s,}]+[^}]*SearchTimeline', resp.text)
        if not search_matches:
            search_matches = re.findall(r'([a-zA-Z0-9_-]{15,})[^}]*SearchTimeline', resp.text)
        
        print(f"\nSearchTimeline queryId 候选: {len(search_matches)}")
        for m in search_matches[:5]:
            print(f"  - {m}")
        
        # 搜索 UserTweets 的 queryId
        user_tweets_matches = re.findall(r'queryId["\s:]+([a-zA-Z0-9_-]+)["\s,}]+[^}]*UserTweets', resp.text)
        if not user_tweets_matches:
            user_tweets_matches = re.findall(r'([a-zA-Z0-9_-]{15,})[^}]*UserTweets', resp.text)
        
        print(f"\nUserTweets queryId 候选: {len(user_tweets_matches)}")
        for m in user_tweets_matches[:5]:
            print(f"  - {m}")
            
        # 保存所有找到的 queryId
        all_query_ids = {}
        # 找所有 operationName 和对应的 queryId
        # 模式: operationName:"XXX",queryId:"YYY" 或 queryId:"YYY",operationName:"XXX"
        pattern1 = re.findall(r'operationName["\s:]+([A-Za-z_]+)["\s,}]+[^}]*?queryId["\s:]+([a-zA-Z0-9_-]+)', resp.text)
        pattern2 = re.findall(r'queryId["\s:]+([a-zA-Z0-9_-]+)["\s,}]+[^}]*?operationName["\s:]+([A-Za-z_]+)', resp.text)
        
        for name, qid in pattern1:
            all_query_ids[name] = qid
        for qid, name in pattern2:
            all_query_ids[name] = qid
        
        print(f"\n找到 {len(all_query_ids)} 个 operation 的 queryId")
        print("前 20 个:")
        for i, (name, qid) in enumerate(sorted(all_query_ids.items())[:20]):
            print(f"  {i+1}. {name}: {qid}")
        
        # 保存到文件
        with open("/tmp/query_ids.json", "w") as f:
            json.dump(all_query_ids, f, indent=2)
        print(f"\n已保存到 /tmp/query_ids.json")
        
    except Exception as e:
        print(f"异常: {e}")
        import traceback
        traceback.print_exc()
