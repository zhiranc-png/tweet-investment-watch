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

    API_URL = "https://www.cls.cn/api/sw"
    TELEGRAPH_URL = "https://www.cls.cn/telegraph"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.cls.cn/",
        })

    def collect_telegraphs(self, limit: int = 30) -> List[CLSTelegraph]:
        """抓取财联社电报"""
        print("📈 采集财联社电报...")
        telegraphs = []
        try:
            # 尝试网页方式提取数据
            resp = self.session.get(self.TELEGRAPH_URL, timeout=15)
            resp.raise_for_status()
            
            # 从 HTML 中提取 JSON 数据
            match = re.search(r'window\.__NUXT__\s*=\s*({.*?});', resp.text, re.DOTALL)
            if not match:
                match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', resp.text, re.DOTALL)
            
            if match:
                try:
                    import json
                    data = json.loads(match.group(1))
                    # 递归查找电报数据
                    items = self._find_telegraph_data(data)
                    for item in items[:limit]:
                        tg = self._parse_telegraph(item)
                        if tg:
                            telegraphs.append(tg)
                except Exception as e:
                    print(f"   ⚠️ 解析网页数据失败: {e}")

            # 如果网页方式没拿到，尝试深度页面
            if not telegraphs:
                params = {
                    "app": "CailianpressWeb",
                    "os": "web",
                    "sv": "7.7.5",
                }
                resp = self.session.get(
                    "https://www.cls.cn/v1/roll/get_roll_list",
                    params=params,
                    timeout=15
                )
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("data", {}).get("roll_data", [])
                    for item in items[:limit]:
                        tg = self._parse_telegraph(item)
                        if tg:
                            telegraphs.append(tg)

            print(f"   ✅ 财联社电报: {len(telegraphs)} 条")
        except Exception as e:
            print(f"   ⚠️ 财联社采集失败: {e}")

        return telegraphs

    def _find_telegraph_data(self, data, depth=0):
        """递归查找电报数据"""
        if depth > 10:
            return []
        if isinstance(data, list):
            # 检查是否是电报列表
            if data and isinstance(data[0], dict):
                if 'content' in data[0] and ('ctime' in data[0] or 'id' in data[0]):
                    return data
            for item in data:
                result = self._find_telegraph_data(item, depth + 1)
                if result:
                    return result
        elif isinstance(data, dict):
            for key in ['roll_data', 'telegraphList', 'list', 'items', 'data']:
                if key in data:
                    result = self._find_telegraph_data(data[key], depth + 1)
                    if result:
                        return result
            for v in data.values():
                if isinstance(v, (dict, list)):
                    result = self._find_telegraph_data(v, depth + 1)
                    if result:
                        return result
        return []

    def _parse_telegraph(self, item):
        """解析单条电报"""
        try:
            tg_id = str(item.get("id", ""))
            if not tg_id:
                return None

            content = item.get("content", "") or item.get("title", "")
            content = re.sub(r'<[^>]+>', '', content)
            content = re.sub(r'\s+', ' ', content).strip()

            title = item.get("title", "") or content[:60]

            return CLSTelegraph(
                telegraph_id=tg_id,
                title=title[:80],
                content=content[:500],
                author="财联社",
                likes=item.get("like_count", 0),
                views=item.get("read_num", 0) or item.get("view_count", 0),
                created_at=str(item.get("ctime", item.get("created_at", ""))),
                url=f"https://www.cls.cn/detail/{tg_id}",
                source="cls",
                tags=item.get("stocklist", []) or item.get("tags", []),
                is_important=item.get("is_important", 0) == 1 or item.get("level", "") == "important",
            )
        except:
            return None
