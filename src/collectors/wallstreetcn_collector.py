"""
华尔街见闻采集器
抓取华尔街见闻热门资讯
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import List

import requests


@dataclass
class WscnArticle:
    """华尔街见闻文章"""
    article_id: str
    title: str
    content: str
    author: str
    likes: int
    views: int
    created_at: str
    url: str
    source: str = "wallstreetcn"
    tags: List[str] = field(default_factory=list)
    category: str = ""


class WallStreetCNCollector:
    """华尔街见闻采集器"""

    API_URL = "https://api-one-wscn.awtmt.com/apiv1/content/lives"
    NEWS_API = "https://api-one-wscn.awtmt.com/apiv1/content/articles"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://wallstreetcn.com/",
        })

    def collect_lives(self, limit: int = 30) -> List[WscnArticle]:
        """抓取实时快讯（7x24小时）"""
        print("📰 采集华尔街见闻快讯...")
        articles = []
        try:
            params = {
                "channel": "global-channel",
                "limit": min(limit, 50),
                "first_page": "true",
            }
            resp = self.session.get(self.API_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            items = data.get("data", {}).get("items", [])
            for item in items[:limit]:
                article_id = str(item.get("id", ""))
                if not article_id:
                    continue

                content_text = item.get("content_text", "") or item.get("title", "")
                content_text = re.sub(r'<[^>]+>', '', content_text)
                content_text = re.sub(r'\s+', ' ', content_text).strip()

                article = WscnArticle(
                    article_id=article_id,
                    title=item.get("title", "")[:80] or content_text[:60],
                    content=content_text[:500],
                    author=item.get("author_name", "华尔街见闻"),
                    likes=item.get("like_count", 0),
                    views=item.get("view_count", 0),
                    created_at=item.get("display_time", ""),
                    url=f"https://wallstreetcn.com/live/{article_id}",
                    source="wallstreetcn",
                    tags=item.get("tags", []),
                    category="live",
                )
                articles.append(article)

            print(f"   ✅ 华尔街见闻快讯: {len(articles)} 条")
        except Exception as e:
            print(f"   ⚠️ 华尔街见闻采集失败: {e}")

        return articles

    def collect_articles(self, limit: int = 20) -> List[WscnArticle]:
        """抓取深度文章"""
        print("📑 采集华尔街见闻深度文章...")
        articles = []
        try:
            params = {
                "limit": min(limit, 30),
                "first_page": "true",
            }
            resp = self.session.get(self.NEWS_API, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            items = data.get("data", {}).get("items", [])
            for item in items[:limit]:
                article_id = str(item.get("id", ""))
                if not article_id:
                    continue

                content_short = item.get("content_short", "") or item.get("summary", "")
                content_short = re.sub(r'<[^>]+>', '', content_short)
                content_short = re.sub(r'\s+', ' ', content_short).strip()

                article = WscnArticle(
                    article_id=article_id,
                    title=item.get("title", "")[:80],
                    content=content_short[:500],
                    author=item.get("author_name", "华尔街见闻"),
                    likes=item.get("like_count", 0),
                    views=item.get("view_count", 0),
                    created_at=item.get("display_time", ""),
                    url=f"https://wallstreetcn.com/articles/{article_id}",
                    source="wallstreetcn",
                    tags=[t.get("name", "") for t in item.get("tags", []) if t.get("name")],
                    category="article",
                )
                articles.append(article)

            print(f"   ✅ 华尔街见闻深度: {len(articles)} 条")
        except Exception as e:
            print(f"   ⚠️ 华尔街见闻深度文章采集失败: {e}")

        return articles
