"""
Hacker News 采集器
抓取 Hacker News 热门帖子（科技圈热点）
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List

import requests


@dataclass
class HNStory:
    """Hacker News 帖子"""
    story_id: str
    title: str
    content: str
    author: str
    score: int
    comments_count: int
    created_at: str
    url: str
    source: str = "hackernews"
    tags: List[str] = field(default_factory=list)
    external_url: str = ""


class HackerNewsCollector:
    """Hacker News 采集器"""

    TOP_STORIES = "https://hacker-news.firebaseio.com/v0/topstories.json"
    ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        })

    def collect_top(self, limit: int = 20) -> List[HNStory]:
        """抓取 Top 故事"""
        print("💻 采集 Hacker News...")
        stories = []
        try:
            resp = self.session.get(self.TOP_STORIES, timeout=10)
            resp.raise_for_status()
            story_ids = resp.json()[:limit]

            for sid in story_ids:
                try:
                    resp = self.session.get(self.ITEM_URL.format(id=sid), timeout=5)
                    resp.raise_for_status()
                    item = resp.json()
                    if not item or item.get("type") != "story":
                        continue

                    story = HNStory(
                        story_id=str(item.get("id", "")),
                        title=item.get("title", ""),
                        content=item.get("text", "") or item.get("url", "")[:200],
                        author=item.get("by", "unknown"),
                        score=item.get("score", 0),
                        comments_count=item.get("descendants", 0),
                        created_at=str(item.get("time", "")),
                        url=f"https://news.ycombinator.com/item?id={sid}",
                        source="hackernews",
                        external_url=item.get("url", ""),
                    )
                    stories.append(story)
                    time.sleep(0.05)  # 限速
                except:
                    continue

            print(f"   ✅ Hacker News: {len(stories)} 条")
        except Exception as e:
            print(f"   ⚠️ Hacker News 采集失败: {e}")

        return stories
