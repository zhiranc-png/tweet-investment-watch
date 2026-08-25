"""
多源数据管理器
统一管理所有数据源的采集和数据格式转换
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Dict, Any

from .xueqiu_collector import XueqiuCollector, XueqiuPost
from .wallstreetcn_collector import WallStreetCNCollector, WscnArticle
from .cls_collector import CLSCollector, CLSTelegraph
from .weibo_hot_collector import WeiboHotCollector, WeiboHotItem
from .hackernews_collector import HackerNewsCollector, HNStory
from .kr36_collector import Kr36Collector, Kr36Article
from .zhihu_hot_collector import ZhihuHotCollector, ZhihuHotItem


@dataclass
class UnifiedPost:
    """统一格式的帖子（适配所有数据源）"""
    post_id: str
    source: str  # xueqiu / wallstreetcn / cls / weibo / hackernews / 36kr / zhihu / twitter
    author: str
    author_name: str = ""
    title: str = ""
    content: str = ""
    likes: int = 0
    reposts: int = 0
    replies: int = 0
    views: int = 0
    hot_value: int = 0
    created_at: str = ""
    url: str = ""
    tags: List[str] = field(default_factory=list)
    category: str = ""
    is_important: bool = False

    @property
    def engagement_score(self) -> int:
        """互动分数，用于排序"""
        return self.likes * 2 + self.reposts * 3 + self.replies * 1 + self.hot_value // 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "post_id": self.post_id,
            "source": self.source,
            "author": self.author,
            "author_name": self.author_name or self.author,
            "title": self.title,
            "content": self.content,
            "likes": self.likes,
            "reposts": self.reposts,
            "replies": self.replies,
            "views": self.views,
            "hot_value": self.hot_value,
            "engagement_score": self.engagement_score,
            "created_at": self.created_at,
            "url": self.url,
            "tags": self.tags,
            "category": self.category,
            "is_important": self.is_important,
        }


class MultiSourceCollector:
    """多源数据采集管理器"""

    def __init__(self):
        self.collectors = {
            "xueqiu": XueqiuCollector(),
            "wallstreetcn": WallStreetCNCollector(),
            "cls": CLSCollector(),
            "weibo": WeiboHotCollector(),
            "hackernews": HackerNewsCollector(),
            "36kr": Kr36Collector(),
            "zhihu": ZhihuHotCollector(),
        }

    def collect_all(self, limits: Dict[str, int] = None) -> Dict[str, List[UnifiedPost]]:
        """采集所有数据源"""
        if limits is None:
            limits = {
                "xueqiu": 30,
                "wallstreetcn": 30,
                "cls": 30,
                "weibo": 30,
                "hackernews": 20,
                "36kr": 20,
                "zhihu": 20,
            }

        results = {}
        source_count = 0

        print("=" * 60)
        print("🌐 多源数据采集")
        print("=" * 60)

        # 雪球
        try:
            xueqiu_posts = self.collectors["xueqiu"].collect_hot(limits.get("xueqiu", 30))
            results["xueqiu"] = [self._from_xueqiu(p) for p in xueqiu_posts]
            source_count += 1
        except Exception as e:
            print(f"   ❌ 雪球采集异常: {e}")
            results["xueqiu"] = []

        # 华尔街见闻
        try:
            wscn_lives = self.collectors["wallstreetcn"].collect_lives(limits.get("wallstreetcn", 30))
            results["wallstreetcn"] = [self._from_wscn(a) for a in wscn_lives]
            source_count += 1
        except Exception as e:
            print(f"   ❌ 华尔街见闻采集异常: {e}")
            results["wallstreetcn"] = []

        # 财联社
        try:
            cls_tgs = self.collectors["cls"].collect_telegraphs(limits.get("cls", 30))
            results["cls"] = [self._from_cls(t) for t in cls_tgs]
            source_count += 1
        except Exception as e:
            print(f"   ❌ 财联社采集异常: {e}")
            results["cls"] = []

        # 微博热搜
        try:
            weibo_items = self.collectors["weibo"].collect_hot(limits.get("weibo", 30))
            results["weibo"] = [self._from_weibo(w) for w in weibo_items]
            source_count += 1
        except Exception as e:
            print(f"   ❌ 微博热搜采集异常: {e}")
            results["weibo"] = []

        # Hacker News
        try:
            hn_stories = self.collectors["hackernews"].collect_top(limits.get("hackernews", 20))
            results["hackernews"] = [self._from_hn(s) for s in hn_stories]
            source_count += 1
        except Exception as e:
            print(f"   ❌ Hacker News 采集异常: {e}")
            results["hackernews"] = []

        # 36氪
        try:
            kr_articles = self.collectors["36kr"].collect_hot(limits.get("36kr", 20))
            results["36kr"] = [self._from_36kr(a) for a in kr_articles]
            source_count += 1
        except Exception as e:
            print(f"   ❌ 36氪采集异常: {e}")
            results["36kr"] = []

        # 知乎热榜
        try:
            zhihu_items = self.collectors["zhihu"].collect_hot(limits.get("zhihu", 20))
            results["zhihu"] = [self._from_zhihu(z) for z in zhihu_items]
            source_count += 1
        except Exception as e:
            print(f"   ❌ 知乎热榜采集异常: {e}")
            results["zhihu"] = []

        total = sum(len(v) for v in results.values())
        print(f"\n📊 采集完成: {source_count}/{len(self.collectors)} 个源，共 {total} 条")
        for src, posts in results.items():
            status = "✅" if posts else "❌"
            print(f"   {status} {src}: {len(posts)} 条")

        return results

    def get_all_posts(self, results: Dict[str, List[UnifiedPost]] = None) -> List[UnifiedPost]:
        """获取所有帖子，按互动分数排序"""
        if results is None:
            results = self.collect_all()

        all_posts = []
        for posts in results.values():
            all_posts.extend(posts)

        all_posts.sort(key=lambda p: p.engagement_score, reverse=True)
        return all_posts

    def _from_xueqiu(self, post: XueqiuPost) -> UnifiedPost:
        return UnifiedPost(
            post_id=f"xueqiu_{post.post_id}",
            source="xueqiu",
            author=post.author,
            author_name=post.author,
            title=post.title,
            content=post.content,
            likes=post.likes,
            reposts=post.reposts,
            replies=post.replies,
            views=post.views,
            created_at=post.created_at,
            url=post.url,
            tags=post.tags + post.stock_codes,
        )

    def _from_wscn(self, article: WscnArticle) -> UnifiedPost:
        return UnifiedPost(
            post_id=f"wscn_{article.article_id}",
            source="wallstreetcn",
            author=article.author,
            author_name=article.author,
            title=article.title,
            content=article.content,
            likes=article.likes,
            views=article.views,
            created_at=article.created_at,
            url=article.url,
            tags=article.tags,
            category=article.category,
        )

    def _from_cls(self, tg: CLSTelegraph) -> UnifiedPost:
        return UnifiedPost(
            post_id=f"cls_{tg.telegraph_id}",
            source="cls",
            author=tg.author,
            author_name=tg.author,
            title=tg.title,
            content=tg.content,
            likes=tg.likes,
            views=tg.views,
            created_at=tg.created_at,
            url=tg.url,
            tags=tg.tags,
            is_important=tg.is_important,
        )

    def _from_weibo(self, item: WeiboHotItem) -> UnifiedPost:
        return UnifiedPost(
            post_id=f"weibo_{item.item_id}",
            source="weibo",
            author="微博热搜",
            author_name="微博热搜",
            title=item.title,
            content=item.content,
            hot_value=item.hot_value,
            replies=item.rank * 0,  # 热搜没有回复数
            created_at=item.created_at,
            url=item.url,
            tags=item.tags,
            category=item.category,
        )

    def _from_hn(self, story: HNStory) -> UnifiedPost:
        return UnifiedPost(
            post_id=f"hn_{story.story_id}",
            source="hackernews",
            author=story.author,
            author_name=story.author,
            title=story.title,
            content=story.content,
            likes=story.score,
            replies=story.comments_count,
            created_at=story.created_at,
            url=story.url,
            tags=["tech", "startup"],
        )

    def _from_36kr(self, article: Kr36Article) -> UnifiedPost:
        return UnifiedPost(
            post_id=f"36kr_{article.article_id}",
            source="36kr",
            author=article.author,
            author_name=article.author,
            title=article.title,
            content=article.content,
            likes=article.likes,
            views=article.views,
            created_at=article.created_at,
            url=article.url,
            tags=article.tags,
            category=article.category,
        )

    def _from_zhihu(self, item: ZhihuHotItem) -> UnifiedPost:
        return UnifiedPost(
            post_id=f"zhihu_{item.item_id}",
            source="zhihu",
            author=item.author,
            author_name=item.author,
            title=item.title,
            content=item.content,
            hot_value=item.hot_value,
            replies=item.answers_count,
            created_at=item.created_at,
            url=item.url,
            tags=["zhihu_hot"],
        )

    def filter_investment(self, posts: List[UnifiedPost]) -> List[UnifiedPost]:
        """筛选投资相关内容"""
        try:
            from .filter import filter_investment_posts
            filtered = filter_investment_posts(posts)
            print(f"🔍 投资内容过滤: {len(posts)} → {len(filtered)} 条")
            return filtered
        except ImportError:
            print("⚠️ filter 模块不可用，跳过过滤")
            return posts
