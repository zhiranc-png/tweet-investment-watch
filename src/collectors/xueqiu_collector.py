"""
雪球热榜采集器
抓取雪球热门讨论
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import List

import requests
from bs4 import BeautifulSoup


@dataclass
class XueqiuPost:
    """雪球帖子"""
    post_id: str
    title: str
    author: str
    content: str
    likes: int
    replies: int
    reposts: int
    views: int
    created_at: str
    url: str
    source: str = "xueqiu"
    tags: List[str] = field(default_factory=list)
    stock_codes: List[str] = field(default_factory=list)


class XueqiuCollector:
    """雪球热榜采集器"""

    BASE_URL = "https://xueqiu.com"
    HOT_STOCK_URL = "https://stock.xueqiu.com/v5/stock/hot_stock/list.json"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://xueqiu.com/",
        })

    def _get_token(self) -> bool:
        """获取雪球 token"""
        try:
            resp = self.session.get(self.BASE_URL, timeout=10)
            resp.raise_for_status()
            return True
        except Exception as e:
            print(f"   ⚠️ 获取雪球 token 失败: {e}")
            return False

    def collect_hot(self, limit: int = 30) -> List[XueqiuPost]:
        """抓取雪球热门讨论"""
        print("📊 采集雪球热榜...")

        if not self._get_token():
            print("   ⚠️ 无法获取雪球 token，跳过")
            return []
        time.sleep(1)

        posts = []
        try:
            # 方式1: 热门股票讨论
            params = {
                "size": min(limit, 50),
                "type": "10",  # 热门
            }
            resp = self.session.get(self.HOT_STOCK_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            items = data.get("data", {}).get("items", [])
            if not items:
                items = data.get("data", {}).get("stocks", [])

            for item in items[:limit]:
                # 热门股票条目
                stock_name = item.get("name", "")
                stock_code = item.get("symbol", "")
                if not stock_code:
                    continue

                # 构造一条"帖子"（股票热度信息）
                post = XueqiuPost(
                    post_id=f"stock_{stock_code}",
                    title=f"{stock_name}({stock_code}) - 雪球热门",
                    author="雪球热门",
                    content=f"热度排名: {item.get('rank', 'N/A')}, 涨跌幅: {item.get('percent', 'N/A')}%, 当前价: {item.get('current', 'N/A')}",
                    likes=item.get("followers", 0) // 100,
                    replies=item.get("trend", 0),
                    reposts=0,
                    views=item.get("followers", 0),
                    created_at="",
                    url=f"{self.BASE_URL}/S/{stock_code}",
                    source="xueqiu",
                    tags=[stock_name, stock_code],
                    stock_codes=[stock_code],
                )
                posts.append(post)

            print(f"   ✅ 雪球热门股票: {len(posts)} 条")

        except Exception as e:
            print(f"   ⚠️ 雪球采集失败: {e}")

        return posts
