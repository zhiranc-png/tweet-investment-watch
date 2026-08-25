"""
知乎热榜采集器
抓取知乎热榜
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

import requests


@dataclass
class ZhihuHotItem:
    """知乎热榜条目"""
    item_id: str
    title: str
    content: str
    author: str
    hot_value: int
    answers_count: int
    created_at: str
    url: str
    source: str = "zhihu"
    tags: List[str] = field(default_factory=list)


class ZhihuHotCollector:
    """知乎热榜采集器"""

    HOT_URL = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.zhihu.com/hot",
        })

    def collect_hot(self, limit: int = 20) -> List[ZhihuHotItem]:
        """抓取知乎热榜"""
        print("🧠 采集知乎热榜...")
        items = []
        try:
            params = {
                "limit": min(limit, 50),
                "desktop": "true",
            }
            resp = self.session.get(self.HOT_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            hot_list = data.get("data", [])
            for i, item in enumerate(hot_list[:limit]):
                target = item.get("target", {})
                title = target.get("title", "")
                if not title:
                    continue

                excerpt = target.get("excerpt", "")
                excerpt = re.sub(r'<[^>]+>', '', excerpt)
                excerpt = re.sub(r'\s+', ' ', excerpt).strip()

                metrics = item.get("detail_text", "")
                # 提取热度值
                hot_val = 0
                hot_match = re.search(r'(\d+(?:\.\d+)?)\s*万', metrics)
                if hot_match:
                    hot_val = int(float(hot_match.group(1)) * 10000)

                zh_item = ZhihuHotItem(
                    item_id=str(target.get("id", "")) or f"hot_{i}",
                    title=title,
                    content=excerpt[:300],
                    author=target.get("author", {}).get("name", "知乎"),
                    hot_value=hot_val,
                    answers_count=target.get("answer_count", 0),
                    created_at="",
                    url=f"https://www.zhihu.com/question/{target.get('id', '')}",
                    source="zhihu",
                )
                items.append(zh_item)

            print(f"   ✅ 知乎热榜: {len(items)} 条")
        except Exception as e:
            print(f"   ⚠️ 知乎热榜采集失败: {e}")

        return items
