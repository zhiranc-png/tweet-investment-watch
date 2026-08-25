"""
微博热搜采集器
抓取微博热搜榜
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

import requests


@dataclass
class WeiboHotItem:
    """微博热搜条目"""
    item_id: str
    title: str
    content: str
    author: str
    hot_value: int
    rank: int
    created_at: str
    url: str
    source: str = "weibo"
    tags: List[str] = field(default_factory=list)
    category: str = ""


class WeiboHotCollector:
    """微博热搜采集器"""

    HOT_URL = "https://weibo.com/ajax/side/hotSearch"
    MOBILE_URL = "https://m.weibo.cn/api/container/getIndex"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://weibo.com/",
        })

    def collect_hot(self, limit: int = 30) -> List[WeiboHotItem]:
        """抓取微博热搜"""
        print("🔥 采集微博热搜...")
        items = []
        try:
            resp = self.session.get(self.HOT_URL, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            hot_list = data.get("data", {}).get("realtime", [])
            for i, item in enumerate(hot_list[:limit]):
                word = item.get("word", "")
                if not word:
                    continue

                hot_item = WeiboHotItem(
                    item_id=str(item.get("mid", "")) or f"hot_{i}",
                    title=word,
                    content=item.get("note", word)[:300],
                    author="微博热搜",
                    hot_value=item.get("num", 0),
                    rank=i + 1,
                    created_at="",
                    url=f"https://s.weibo.com/weibo?q={requests.utils.quote(word)}",
                    source="weibo",
                    tags=[item.get("category", "")] if item.get("category") else [],
                    category=item.get("category", ""),
                )
                items.append(hot_item)

            print(f"   ✅ 微博热搜: {len(items)} 条")
        except Exception as e:
            print(f"   ⚠️ 微博热搜采集失败: {e}")
            # 备用方式
            items = self._collect_mobile(limit)

        return items

    def _collect_mobile(self, limit: int = 30) -> List[WeiboHotItem]:
        """移动端备用"""
        items = []
        try:
            params = {
                "containerid": "106003type=25&t=3&disable_hot=1&filter_type_set=1",
            }
            resp = self.session.get(self.MOBILE_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            cards = data.get("data", {}).get("cards", [])
            for card in cards:
                card_group = card.get("card_group", [])
                for i, item in enumerate(card_group[:limit]):
                    desc = item.get("desc", "")
                    if not desc:
                        continue
                    hot_item = WeiboHotItem(
                        item_id=str(item.get("id", "")) or f"hot_{i}",
                        title=desc,
                        content=item.get("desc_extr", desc)[:300],
                        author="微博热搜",
                        hot_value=item.get("desc_extr_rank", 0),
                        rank=i + 1,
                        created_at="",
                        url=item.get("scheme", ""),
                        source="weibo",
                    )
                    items.append(hot_item)
                    if len(items) >= limit:
                        break
                if items:
                    break

            print(f"   ✅ 微博热搜(移动): {len(items)} 条")
        except Exception as e:
            print(f"   ❌ 微博热搜移动版也失败: {e}")

        return items
