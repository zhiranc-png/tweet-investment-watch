"""
财联社采集器
抓取财联社电报（A股实时快讯）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

import requests


@dataclass
class CLSTelegraph:
    """财联社电报"""
    telegraph_id: str
    title: str
    content: str
    author: str
    likes: int
    views: int
    created_at: str
    url: str
    source: str = "cls"
    tags: List[str] = field(default_factory=list)
    is_important: bool = False


class CLSCollector:
    """财联社采集器"""

    API_URL = "https://www.cls.cn/nodeapi/telegraphList"
    V2_API = "https://www.cls.cn/v3/depth/home/assembled/1000"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.cls.cn/telegraph",
        })

    def collect_telegraphs(self, limit: int = 30) -> List[CLSTelegraph]:
        """抓取财联社电报"""
        print("📈 采集财联社电报...")
        telegraphs = []
        try:
            params = {
                "app": "CailianpressWeb",
                "os": "web",
                "sv": "8.4.6",
                "sign": "",
            }
            resp = self.session.get(self.API_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            items = data.get("data", {}).get("roll_data", [])
            if not items:
                items = data.get("data", [])

            for item in items[:limit]:
                tg_id = str(item.get("id", ""))
                if not tg_id:
                    continue

                content = item.get("content", "") or item.get("title", "")
                content = re.sub(r'<[^>]+>', '', content)
                content = re.sub(r'\s+', ' ', content).strip()

                title = item.get("title", "") or content[:50]

                tg = CLSTelegraph(
                    telegraph_id=tg_id,
                    title=title[:80],
                    content=content[:500],
                    author="财联社",
                    likes=item.get("like_count", 0),
                    views=item.get("read_num", 0),
                    created_at=str(item.get("ctime", "")),
                    url=f"https://www.cls.cn/detail/{tg_id}",
                    source="cls",
                    tags=item.get("stocklist", []) or item.get("tags", []),
                    is_important=item.get("is_important", 0) == 1,
                )
                telegraphs.append(tg)

            print(f"   ✅ 财联社电报: {len(telegraphs)} 条")
        except Exception as e:
            print(f"   ⚠️ 财联社采集失败: {e}")

        return telegraphs
