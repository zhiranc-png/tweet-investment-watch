"""
36氪采集器
抓取36氪热门资讯（科技创投）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

import requests


@dataclass
class Kr36Article:
    """36氪文章"""
    article_id: str
    title: str
    content: str
    author: str
    likes: int
    views: int
    created_at: str
    url: str
    source: str = "36kr"
    tags: List[str] = field(default_factory=list)
    category: str = ""


class Kr36Collector:
    """36氪采集器"""

    API_URL = "https://gateway.36kr.com/api/mis/nav/home/nav/rank/hot"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://36kr.com/",
            "Content-Type": "application/json",
        })

    def collect_hot(self, limit: int = 20) -> List[Kr36Article]:
        """抓取36氪热榜"""
        print("🚀 采集 36氪...")
        articles = []
        try:
            payload = {
                "partner_id": "wap",
                "param": {
                    "siteId": 1,
                    "platformId": 2,
                },
                "timestamp": 0,
            }
            resp = self.session.post(self.API_URL, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            items = data.get("data", {}).get("hotRankList", [])
            for item in items[:limit]:
                template = item.get("templateMaterial", {})
                article_id = str(template.get("itemId", ""))
                if not article_id:
                    continue

                content = template.get("summary", "") or template.get("widgetTitle", "")
                content = re.sub(r'<[^>]+>', '', content)
                content = re.sub(r'\s+', ' ', content).strip()

                article = Kr36Article(
                    article_id=article_id,
                    title=template.get("widgetTitle", "")[:80],
                    content=content[:500],
                    author=template.get("authorName", "36氪"),
                    likes=template.get("likeCount", 0),
                    views=template.get("viewCount", 0),
                    created_at=str(template.get("publishTime", "")),
                    url=f"https://36kr.com/p/{article_id}",
                    source="36kr",
                    tags=[t.get("name", "") for t in template.get("tagList", []) if t.get("name")],
                    category=template.get("columnName", ""),
                )
                articles.append(article)

            print(f"   ✅ 36氪: {len(articles)} 条")
        except Exception as e:
            print(f"   ⚠️ 36氪采集失败: {e}")

        return articles
