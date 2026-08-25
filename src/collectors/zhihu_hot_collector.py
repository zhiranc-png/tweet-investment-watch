"""
知乎热榜采集器
抓取知乎热榜
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

import requests
from bs4 import BeautifulSoup


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

    HOT_URL = "https://www.zhihu.com/hot"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.zhihu.com/",
        })

    def collect_hot(self, limit: int = 20) -> List[ZhihuHotItem]:
        """抓取知乎热榜"""
        print("🧠 采集知乎热榜...")
        items = []
        try:
            resp = self.session.get(self.HOT_URL, timeout=15)
            resp.raise_for_status()

            # 从 HTML 中提取初始数据
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 尝试从 script 标签中提取数据
            for script in soup.find_all('script'):
                text = script.string or ""
                if 'initialState' in text or 'hotList' in text:
                    match = re.search(r'"hotList":\s*(\[.*?\])', text, re.DOTALL)
                    if match:
                        import json
                        try:
                            hot_list = json.loads(match.group(1))
                            for i, item in enumerate(hot_list[:limit]):
                                target = item.get("target", {})
                                title = target.get("titleArea", {}).get("text", "")
                                if not title:
                                    title = target.get("title", "")
                                if not title:
                                    continue
                                
                                excerpt = target.get("excerptArea", {}).get("text", "")
                                metrics = target.get("metricsArea", {}).get("text", "")
                                
                                hot_val = 0
                                hot_match = re.search(r'(\d+(?:\.\d+)?)\s*万', metrics)
                                if hot_match:
                                    hot_val = int(float(hot_match.group(1)) * 10000)
                                
                                link = target.get("link", {}).get("url", "")
                                if not link:
                                    link = f"https://www.zhihu.com/question/{target.get('id', '')}"
                                
                                zh_item = ZhihuHotItem(
                                    item_id=str(target.get("id", "")) or f"hot_{i}",
                                    title=title,
                                    content=excerpt[:300],
                                    author="知乎热榜",
                                    hot_value=hot_val,
                                    answers_count=0,
                                    created_at="",
                                    url=link,
                                    source="zhihu",
                                )
                                items.append(zh_item)
                        except Exception as e:
                            print(f"   ⚠️ 解析知乎数据失败: {e}")
                    break

            # 如果上面没拿到，尝试从 HTML 元素中提取
            if not items:
                hot_items = soup.select('.HotItem')
                for i, item in enumerate(hot_items[:limit]):
                    title_el = item.select_one('.HotItem-title')
                    if not title_el:
                        continue
                    title = title_el.get_text(strip=True)
                    
                    metrics_el = item.select_one('.HotItem-metrics')
                    metrics = metrics_el.get_text(strip=True) if metrics_el else ""
                    
                    hot_val = 0
                    hot_match = re.search(r'(\d+(?:\.\d+)?)\s*万', metrics)
                    if hot_match:
                        hot_val = int(float(hot_match.group(1)) * 10000)
                    
                    link_el = title_el.select_one('a')
                    link = link_el['href'] if link_el and link_el.has_attr('href') else ""
                    if link and link.startswith('/'):
                        link = f"https://www.zhihu.com{link}"
                    
                    zh_item = ZhihuHotItem(
                        item_id=f"hot_{i}",
                        title=title,
                        content="",
                        author="知乎热榜",
                        hot_value=hot_val,
                        answers_count=0,
                        created_at="",
                        url=link,
                        source="zhihu",
                    )
                    items.append(zh_item)

            print(f"   ✅ 知乎热榜: {len(items)} 条")
        except Exception as e:
            print(f"   ⚠️ 知乎热榜采集失败: {e}")

        return items
