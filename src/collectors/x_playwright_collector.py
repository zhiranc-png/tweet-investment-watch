"""
X (Twitter) Playwright 爬虫 — 基于浏览器渲染的稳定采集
适合 GitHub Actions 等无界面环境，用 auth_token + ct0 注入 Cookie 登录

使用方式:
    collector = XPlaywrightCollector(auth_token="xxx", ct0="yyy")
    tweets = collector.collect_daily()
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Optional

from .asset_extractor import extract_assets, extract_themes
from .models import Tweet


# 垃圾内容过滤规则
SPAM_PATTERNS = [
    r"^(up|gm|gn|lfg|nice|wow|hi|hello|wagmi|ngmi)\b",
    r"^\s*UID\s*[:：]?\s*\d+",
    r"^@\w+\s*@\w+\s*@\w+",
    r"(join|enter).*(giveaway|raffle|lottery)",
    r"(DM|dm)\s*(me|for|to)\s*(collab|promo|marketing|join|access)",
    r"(guaranteed|easy)\s*(profit|money|income|return)",
    r"(telegram|t\.me)/\S+",
    r"(🚀\s*){3,}",
    r"(private|alpha|vip)\s*(TG|telegram|group|channel)",
    r"\d{3,}(\.\d+)?x\s*(return|gain|profit)",
    r"(?:#\w+\s*){7,}",
    r"^(like|retweet|rt|follow|tag)\s.*(to\s*win|for\s*a\s*chance)",
]
_SPAM_RE = [re.compile(p, re.I) for p in SPAM_PATTERNS]


def _is_spam(text: str) -> bool:
    if len(text.strip()) < 20:
        return True
    for pat in _SPAM_RE:
        if pat.search(text):
            return True
    return False


def _parse_count(text: str) -> int:
    """解析 '1.2K' / '3万' 等格式的数字"""
    if not text:
        return 0
    text = text.strip().replace(',', '').replace('，', '')
    try:
        # 纯数字
        return int(float(text))
    except ValueError:
        pass
    # K / M 格式
    m = re.match(r'([\d.]+)\s*([KMBkmb])', text)
    if m:
        num = float(m.group(1))
        unit = m.group(2).upper()
        if unit == 'K':
            return int(num * 1000)
        elif unit == 'M':
            return int(num * 1_000_000)
        elif unit == 'B':
            return int(num * 1_000_000_000)
    # 中文格式
    if '万' in text:
        m = re.match(r'([\d.]+)\s*万', text)
        if m:
            return int(float(m.group(1)) * 10000)
    return 0


class XPlaywrightCollector:
    """基于 Playwright 的 X 爬虫"""

    def __init__(self, auth_token: str, ct0: str, headless: bool = True):
        self.auth_token = auth_token
        self.ct0 = ct0
        self.headless = headless
        self.kol_handles: list[str] = []
        self._browser = None
        self._context = None
        self._page = None

    def set_kol_handles(self, handles: list[str]) -> None:
        self.kol_handles = handles

    def _start(self) -> None:
        """启动浏览器"""
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.firefox.launch(headless=self.headless)
        self._context = self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        # 注入 Cookie
        self._context.add_cookies([
            {
                "name": "auth_token",
                "value": self.auth_token,
                "domain": ".x.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
            },
            {
                "name": "ct0",
                "value": self.ct0,
                "domain": ".x.com",
                "path": "/",
                "secure": True,
            },
        ])
        self._page = self._context.new_page()

    def _close(self) -> None:
        """关闭浏览器"""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if hasattr(self, '_playwright') and self._playwright:
                self._playwright.stop()
        except Exception:
            pass

    def __enter__(self):
        self._start()
        return self

    def __exit__(self, *args):
        self._close()

    def health_check(self) -> dict:
        """检查登录状态"""
        try:
            self._start()
            self._page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            # 检查是否有登录后的元素（搜索框、发推按钮等）
            url = self._page.url
            if 'login' in url:
                self._close()
                return {"cookies_valid": False, "error": "auth_token 无效，跳转到了登录页"}
            self._close()
            return {"cookies_valid": True, "error": None}
        except Exception as e:
            self._close()
            return {"cookies_valid": False, "error": str(e)}

    def _extract_tweets_from_page(self, is_kol: bool = False, limit: int = 20) -> list[Tweet]:
        """从当前页面提取推文"""
        tweets = []
        seen_ids = set()

        # 滚动加载更多
        for scroll_round in range(4):
            # 提取当前可见推文
            try:
                tweet_articles = self._page.query_selector_all('article[data-testid="tweet"]')
            except Exception:
                tweet_articles = []

            for article in tweet_articles:
                try:
                    tweet = self._parse_article(article, is_kol)
                    if tweet and tweet.tweet_id not in seen_ids:
                        seen_ids.add(tweet.tweet_id)
                        tweets.append(tweet)
                except Exception:
                    continue

            if len(tweets) >= limit:
                break

            # 滚动
            self._page.evaluate("window.scrollBy(0, 1500)")
            time.sleep(1.5)

        return tweets[:limit]

    def _parse_article(self, article, is_kol: bool = False) -> Optional[Tweet]:
        """解析单个 article 元素为 Tweet 对象"""
        try:
            # 获取推文链接（包含 tweet_id 和 author）
            link_el = article.query_selector('a[href*="/status/"]')
            if not link_el:
                return None
            href = link_el.get_attribute('href') or ''
            # 解析 @handle 和 tweet_id
            m = re.match(r'/([^/]+)/status/(\d+)', href)
            if not m:
                return None
            author = m.group(1)
            tweet_id = m.group(2)

            # 获取显示名
            name_el = article.query_selector('[data-testid="User-Name"] span')
            author_name = name_el.inner_text().strip() if name_el else ''

            # 获取推文文本
            text_el = article.query_selector('[data-testid="tweetText"]')
            content = text_el.inner_text().strip() if text_el else ''

            if _is_spam(content):
                return None

            # 获取互动数据
            likes = 0
            reposts = 0
            replies = 0
            views = 0

            # 点赞
            like_el = article.query_selector('[data-testid="like"]')
            if like_el:
                label = like_el.get_attribute('aria-label') or ''
                m_like = re.search(r'([\d,.KMB万]+)\s*like', label, re.I)
                if m_like:
                    likes = _parse_count(m_like.group(1))

            # 转推
            repost_el = article.query_selector('[data-testid="retweet"]')
            if repost_el:
                label = repost_el.get_attribute('aria-label') or ''
                m_repost = re.search(r'([\d,.KMB万]+)\s*repost', label, re.I)
                if m_repost:
                    reposts = _parse_count(m_repost.group(1))

            # 回复
            reply_el = article.query_selector('[data-testid="reply"]')
            if reply_el:
                label = reply_el.get_attribute('aria-label') or ''
                m_reply = re.search(r'([\d,.KMB万]+)\s*repl', label, re.I)
                if m_reply:
                    replies = _parse_count(m_reply.group(1))

            # 浏览量（从链接里可能拿不到，尝试其他方式）
            # 简化处理：用点赞数估算
            views = int(likes * 20)  # 粗略估算

            url = f"https://x.com{href}"

            # 提取标的和主题
            assets = extract_assets(content)
            themes = extract_themes(content)

            # 质量分
            quality = self._calc_quality(likes, reposts, replies, views, len(content), is_kol)

            return Tweet(
                tweet_id=tweet_id,
                author=author,
                author_name=author_name,
                content=content,
                likes=likes,
                reposts=reposts,
                replies=replies,
                views=views,
                created_at="",  # 简化处理
                url=url,
                assets=assets,
                themes=themes,
                quality_score=quality,
                is_kol=is_kol,
            )
        except Exception:
            return None

    def _calc_quality(self, likes: int, reposts: int, replies: int, views: int,
                       content_len: int, is_kol: bool) -> float:
        score = 0.0
        score += min(likes / 100.0, 10)
        score += min(reposts / 50.0, 5)
        score += min(replies / 20.0, 5)
        if views > 0:
            score += min(views / 10000.0, 5)
        score += min(content_len / 100.0, 3)
        if is_kol:
            score *= 1.2
        return round(score, 2)

    def fetch_user_tweets(self, screen_name: str, limit: int = 15) -> list[Tweet]:
        """获取指定用户的最新推文"""
        try:
            url = f"https://x.com/{screen_name}"
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            is_kol = screen_name.lower() in [h.lower() for h in self.kol_handles]
            tweets = self._extract_tweets_from_page(is_kol=is_kol, limit=limit)
            return tweets
        except Exception as e:
            print(f"   ⚠️ 获取 @{screen_name} 失败: {e}")
            return []

    def search_tweets(self, query: str, limit: int = 15) -> list[Tweet]:
        """搜索推文（热门）"""
        try:
            from urllib.parse import quote
            encoded = quote(query)
            url = f"https://x.com/search?q={encoded}&src=typed_query&f=top"
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            tweets = self._extract_tweets_from_page(is_kol=False, limit=limit)
            return tweets
        except Exception as e:
            print(f"   ⚠️ 搜索失败 '{query}': {e}")
            return []

    def fetch_tweet_comments(self, tweet_id: str, limit: int = 10) -> list[Tweet]:
        """获取推文评论"""
        try:
            # 构造推文URL
            url = f"https://x.com/i/web/status/{tweet_id}"
            self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            comments = []
            seen_ids = set()

            for scroll_round in range(3):
                articles = self._page.query_selector_all('article[data-testid="tweet"]')
                for article in articles:
                    try:
                        comment = self._parse_article(article, is_kol=False)
                        if comment and comment.tweet_id != tweet_id and comment.tweet_id not in seen_ids:
                            seen_ids.add(comment.tweet_id)
                            comments.append(comment)
                    except Exception:
                        continue

                if len(comments) >= limit:
                    break

                self._page.evaluate("window.scrollBy(0, 1000)")
                time.sleep(1)

            comments.sort(key=lambda t: t.likes, reverse=True)
            return comments[:limit]
        except Exception:
            return []

    def collect_daily(
        self,
        kol_handles: list[str] | None = None,
        search_queries: list[str] | None = None,
        limit: int = 150,
        fetch_comments: bool = False,
        comments_per_tweet: int = 10,
        min_likes_for_comments: int = 100,
    ) -> list[Tweet]:
        """采集每日数据：KOL 时间线 + 关键词搜索"""
        if kol_handles:
            self.kol_handles = kol_handles

        all_tweets: dict[str, Tweet] = {}
        kol_set = {h.lower() for h in self.kol_handles}

        # 启动浏览器
        self._start()

        try:
            # 1. 抓取 KOL 时间线
            print(f"📱 抓取 {len(self.kol_handles)} 位 KOL 的时间线...")
            for i, handle in enumerate(self.kol_handles):
                print(f"   [{i+1}/{len(self.kol_handles)}] @{handle}")
                user_tweets = self.fetch_user_tweets(handle, limit=12)
                for t in user_tweets:
                    t.is_kol = True
                    if t.tweet_id not in all_tweets:
                        all_tweets[t.tweet_id] = t
                time.sleep(0.5)

            print(f"   ✅ KOL 推文: {len(all_tweets)} 条")

            # 2. 关键词搜索
            if search_queries:
                print(f"🔍 搜索 {len(search_queries)} 个关键词...")
                for i, query in enumerate(search_queries):
                    print(f"   [{i+1}/{len(search_queries)}] {query}")
                    results = self.search_tweets(query, limit=12)
                    for t in results:
                        t.is_kol = t.author.lower() in kol_set
                        if t.tweet_id not in all_tweets:
                            all_tweets[t.tweet_id] = t
                    time.sleep(0.5)

                print(f"   ✅ 搜索结果: {len(all_tweets)} 条（去重后）")

            # 3. 抓取高互动推文的评论
            if fetch_comments:
                high_engagement = [
                    t for t in all_tweets.values()
                    if t.likes >= min_likes_for_comments
                ]
                high_engagement.sort(key=lambda t: t.likes, reverse=True)
                high_engagement = high_engagement[:8]  # 最多抓8条的评论

                if high_engagement:
                    print(f"💬 抓取 {len(high_engagement)} 条高互动推文的评论...")
                    for i, tweet in enumerate(high_engagement):
                        print(f"   [{i+1}/{len(high_engagement)}] @{tweet.author}: {tweet.content[:40]}...")
                        comments = self.fetch_tweet_comments(tweet.tweet_id, limit=comments_per_tweet)
                        tweet.comments = comments
                        time.sleep(0.5)
                    print(f"   ✅ 评论抓取完成")

        finally:
            self._close()

        # 按质量分排序
        sorted_tweets = sorted(all_tweets.values(), key=lambda t: t.quality_score, reverse=True)
        return sorted_tweets[:limit]
