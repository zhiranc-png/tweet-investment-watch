"""Playwright 方案：用浏览器采集 X 搜索结果"""
import os
import sys
import json
import asyncio

sys.path.insert(0, os.path.dirname(__file__))

auth_token = os.environ.get("AUTH_TOKEN", "")
ct0 = os.environ.get("CT0", "")

print(f"auth_token 长度: {len(auth_token)}")
print(f"ct0 长度: {len(ct0)}")

async def main():
    from playwright.async_api import async_playwright
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
        )
        
        # 注入 cookies
        await context.add_cookies([
            {"name": "auth_token", "value": auth_token, "domain": ".x.com", "path": "/"},
            {"name": "ct0", "value": ct0, "domain": ".x.com", "path": "/"},
        ])
        
        page = await context.new_page()
        
        # 测试 1: 访问搜索页
        print("\n" + "=" * 60)
        print("测试 1: 访问搜索页 (NVDA)")
        print("=" * 60)
        
        try:
            await page.goto("https://x.com/search?q=NVDA&src=typed_query", wait_until="networkidle", timeout=30000)
            print(f"页面标题: {await page.title()}")
            
            # 截图看看
            await page.screenshot(path="/tmp/x_search.png", full_page=False)
            print("✅ 页面加载成功，已截图")
            
            # 尝试获取推文内容
            tweets = await page.query_selector_all('article[data-testid="tweet"]')
            print(f"找到 {len(tweets)} 条推文 article")
            
            for i, tweet in enumerate(tweets[:3]):
                try:
                    text_el = await tweet.query_selector('div[data-testid="tweetText"]')
                    user_el = await tweet.query_selector('div[data-testid="User-Name"]')
                    text = await text_el.inner_text() if text_el else "N/A"
                    user = await user_el.inner_text() if user_el else "N/A"
                    print(f"  [{i+1}] @{user[:30]}: {text[:60]}")
                except:
                    pass
                    
        except Exception as e:
            print(f"❌ 失败: {e}")
            await page.screenshot(path="/tmp/x_error.png")
        
        # 测试 2: 用 API 方式通过页面上下文调用
        print("\n" + "=" * 60)
        print("测试 2: 通过页面上下文调用 SearchTimeline API")
        print("=" * 60)
        
        try:
            # 从页面获取 CSRF token 和 bearer token
            # 先等页面加载完，再用 evaluate 发请求
            result = await page.evaluate("""
                async () => {
                    const headers = {
                        'content-type': 'application/json',
                        'x-twitter-active-user': 'yes',
                        'x-twitter-auth-type': 'OAuth2Session',
                        'x-twitter-client-language': 'en',
                    };
                    
                    // 获取 csrf token
                    const ct0 = document.cookie.split(';').find(c => c.trim().startsWith('ct0='));
                    if (ct0) {
                        headers['x-csrf-token'] = ct0.split('=')[1];
                    }
                    
                    // 发搜索请求
                    const queryId = '5h0kNbk3ii97rmfY6CdgAA';
                    const features = {
                        responsive_web_graphql_exclude_directive_enabled: true,
                        verified_phone_label_enabled: false,
                        creator_subscriptions_tweet_preview_api_enabled: true,
                        responsive_web_graphql_timeline_navigation_enabled: true,
                    };
                    const variables = {
                        rawQuery: 'NVDA min_faves:10',
                        count: 10,
                        querySource: 'typed_query',
                        product: 'Top'
                    };
                    
                    const url = `/i/api/graphql/${queryId}/SearchTimeline?variables=${encodeURIComponent(JSON.stringify(variables))}&features=${encodeURIComponent(JSON.stringify(features))}`;
                    
                    const resp = await fetch(url, {
                        method: 'GET',
                        headers: headers,
                        credentials: 'include',
                    });
                    
                    return {
                        status: resp.status,
                        body: await resp.text()
                    };
                }
            """)
            
            print(f"状态码: {result['status']}")
            body = result['body']
            print(f"响应大小: {len(body)} bytes")
            
            if len(body) > 0:
                try:
                    data = json.loads(body)
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
                    else:
                        print(f"无 data 字段")
                        print(f"前 300 字: {body[:300]}")
                except:
                    print(f"非 JSON: {body[:300]}")
        except Exception as e:
            print(f"❌ 失败: {e}")
            import traceback
            traceback.print_exc()
        
        await browser.close()

asyncio.run(main())
