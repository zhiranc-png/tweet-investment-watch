"""
雪球热榜采集器
抓取雪球热门讨论（https://xueqiu.com/hots）
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
    HOT_URL = "https://xueqiu.com/hots"
    API_URL = "https://xueqiu.com/statuses/hot/listV2.json"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://xueqiu.com/hots",
        })

    def _get_token(self) -> str:
        """获取雪球 token（访问首页获取 cookie）"""
        try:
            resp = self.session.get(self.BASE_URL, timeout=10)
            resp.raise_for_status()
            return "ok"
        except Exception as e:
            print(f"   ⚠️ 获取雪球 token 失败: {e}")
            return ""

    def collect_hot(self, limit: int = 30) -> List[XueqiuPost]:
        """抓取雪球热榜"""
        print("📊 采集雪球热榜...")

        # 先访问首页获取 cookie
        self._get_token()
        time.sleep(1)

        posts = []
        try:
            # 尝试 API 方式
            params = {
                "since_id": -1,
                "max_id": -1,
                "size": min(limit, 50),
            }
            resp = self.session.get(self.API_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            items = data.get("items", [])
            for item in items[:limit]:
                status = item.get("original_status", item)
                if not status:
                    continue

                post_id = str(status.get("id", ""))
                if not post_id:
                    continue

                user = status.get("user", {})
                title = status.get("title", "") or status.get("description", "")[:50]
                content = status.get("text", "")
                # 去除 HTML 标签
                if content:
                    content = re.sub(r'<[^>]+>', '', content)
                    content = re.sub(r'\s+', ' ', content).strip()

                post = XueqiuPost(
                    post_id=post_id,
                    title=title,
                    author=user.get("screen_name", "未知"),
                    content=content[:500],
                    likes=status.get("like_count", 0),
                    replies=status.get("reply_count", 0),
                    reposts=status.get("retweet_count", 0),
                    views=status.get("view_count", 0),
                    created_at=status.get("created_at", ""),
                    url=f"{self.BASE_URL}/{status.get('user_id', '')}/{post_id}",
                    source="xueqiu",
                    tags=[t.get("name", "") for t in status.get("tags", []) if t.get("name")],
                    stock_codes=[s.get("code", "") for s in status.get("stocks", []) if s.get("code")],
                )
                posts.append(post)

            print(f"   ✅ 雪球热榜: {len(posts)} 条")

        except Exception as e:
            print(f"   ⚠️ 雪球 API 采集失败: {e}，尝试网页方式...")
            posts = self._collect_hot_html(limit)

        return posts

    def _collect_hot_html(self, limit: int = 30) -> List[XueqiuPost]:
        """网页方式抓取（备用）"""
        posts = []
        try:
            resp = self.session.get(self.HOT_URL, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')

            # 尝试从页面中提取 JSON 数据
            script_tags = soup.find_all('script')
            for script in script_tags:
                text = script.string or ""
                if 'SNB.data' in text or 'window.__INITIAL_STATE__' in text:
                    # 尝试提取 JSON
                    match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', text, re.DOTALL)
                    if match:
                        try:
                            data = json.loads(match.group(1))
                            items = data.get("hots", {}).get("list", [])
                            for item in items[:limit]:
                                post_id = str(item.get("id", ""))
                                if not post_id:
                                    continue
                                user = item.get("user", {})
                                content = item.get("text", "")
                                if content:
                                    content = re.sub(r'<[^>]+>', '', content)
                                    content = re.sub(r'\s+', ' ', content).strip()
                                post = XueqiuPost(
                                    post_id=post_id,
                                    title=item.get("title", "")[:80],
                                    author=user.get("screen_name", "未知"),
                                    content=content[:500],
                                    likes=item.get("like_count", 0),
                                    replies=item.get("reply_count", 0),
                                    reposts=item.get("retweet_count", 0),
                                    views=item.get("view_count", 0),
                                    created_at=str(item.get("created_at", "")),
                                    url=f"{self.BASE_URL}/{item.get('user_id', '')}/{post_id}",
                                    source="xueqiu",
                                    stock_codes=[s.get("code", "") for s in item.get("stocks", []) if s.get("code")],
                                )
                                posts.append(post)
                        except:
                            pass
                    break

            print(f"   ✅ 雪球网页: {len(posts)} 条")
        except Exception as e:
            print(f"   ❌ 雪球网页采集也失败: {e}")

        return posts
