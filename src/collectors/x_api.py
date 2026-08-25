"""
X (Twitter) API 采集器 — 基于 GraphQL API + Cookie 认证
纯 HTTP 请求，无需浏览器，速度快、稳定性高、不易被检测

使用方式:
    collector = XApiCollector(auth_token="xxx", ct0="xxx")
    tweets = collector.collect_daily(kol_handles, keywords, limit=120)
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import requests

from .asset_extractor import extract_assets, extract_themes
from .models import Tweet

logger = logging.getLogger(__name__)

# ── X 网页端公开 Bearer Token（固定值） ────────────────────────────────────
BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# ── GraphQL API 端点 ──────────────────────────────────────────────────────
API_BASE = "https://x.com/i/api/graphql"

# SearchTimeline endpoint（搜索）
SEARCH_ENDPOINT = "G3A8KQeaYl7E5g0S0W5X5A"  # 可能需要更新，用通用方式

# ── 垃圾内容过滤（复用 x_twitter.py 的规则）────────────────────────────────
MIN_CONTENT_LEN = 40

SPAM_PATTERNS: list[str] = [
    r"^(up|gm|gn|lfg|nice|wow|hi|hello)\b",
    r"^\s*UID\s*[:：]?\s*\d+",
    r"^@\w+\s*@\w+\s*@\w+",
    r"^(RT|retweet)\s",
    r"(join|enter).*(giveaway|raffle|lottery)",
    r"(DM|dm)\s*(me|for|to)\s*(collab|promo|marketing|join|access)",
    r"(guaranteed|easy)\s*(profit|money|income|return)",
    r"(telegram|t\.me)/\S+",
    r"not\s*financial\s*advice.*dyor",
    r"(🚀\s*){3,}",
    r"(private|alpha|vip)\s*(TG|telegram|group|channel)",
    r"DM\s*(TO|ME|FOR)\s*(JOIN|ACCESS|GET)",
    r"\d{3,}(\.\d+)?x\s*(return|gain|profit)",
    r"(?:#\w+\s*){7,}",
    r"^(like|retweet|rt|follow|tag)\s.*(to\s*win|for\s*a\s*chance)",
    r"^(?:patience|hodl|diamond\s*hands?|stay\s*strong|trust\s*the\s*process)\b.*[.!]?\s*$",
]
_SPAM_RE = [re.compile(p, re.I) for p in SPAM_PATTERNS]


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u200b", " ")).strip()


def _extract_tags(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for tag in re.findall(r"#([\w\u4e00-\u9fff-]+)", text or ""):
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def _content_fingerprint(text: str) -> str:
    t = re.sub(r"https?://\S+|[#@]\w+|\$\w+", "", text.lower())
    t = re.sub(r"[^\w\u4e00-\u9fff]", "", t)
    return t[:80]


def _is_spam(text: str, seen_fps: dict[str, int]) -> bool:
    if len(text) < MIN_CONTENT_LEN:
        return True
    for pat in _SPAM_RE:
        if pat.search(text):
            return True
    url_count = len(re.findall(r"https?://\S+", text))
    text_no_url = re.sub(r"https?://\S+", "", text).strip()
    if url_count >= 2 and len(text_no_url) < 30:
        return True
    stripped = re.sub(r"[#@]\w+|https?://\S+|\$\w+", "", text).strip()
    if len(stripped) < 20:
        return True
    fp = _content_fingerprint(text)
    if fp:
        seen_fps[fp] = seen_fps.get(fp, 0) + 1
        if seen_fps[fp] > 2:
            return True
    alpha_chars = len(re.findall(r"[\w\u4e00-\u9fff]", text))
    if alpha_chars < len(text) * 0.4 and len(text) > 30:
        return True
    return False


class XApiCollector:
    """
    X/Twitter API 采集器 — GraphQL API + Cookie 认证
    纯 HTTP 请求，无需浏览器
    """

    def __init__(self, auth_token: str, ct0: str) -> None:
        self.auth_token = auth_token
        self.ct0 = ct0
        self.session = requests.Session()
        self._seen_fingerprints: dict[str, int] = {}
        self._kol_handles: set[str] = set()
        self._setup_session()

    def _setup_session(self) -> None:
        """配置请求会话"""
        self.session.headers.update({
            "Authorization": f"Bearer {BEARER_TOKEN}",
            "x-csrf-token": self.ct0,
            "content-type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": "https://x.com",
            "Referer": "https://x.com/",
            "x-twitter-active-user": "yes",
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-client-language": "zh-cn",
        })
        self.session.cookies.set("auth_token", self.auth_token, domain=".x.com")
        self.session.cookies.set("ct0", self.ct0, domain=".x.com")

    def set_kol_handles(self, handles: list[str]) -> None:
        self._kol_handles = {h.lower() for h in handles}

    def health_check(self) -> dict[str, Any]:
        """检查认证是否有效"""
        status: dict[str, Any] = {
            "platform": "x_api",
            "auth_token_set": bool(self.auth_token),
            "ct0_set": bool(self.ct0),
            "authenticated": False,
        }
        try:
            # 尝试获取当前用户信息来验证
            url = f"{API_BASE}/n5LLy1cXpU8qM2XfZ0e2fA/Viewer"
            params = {"variables": '{"withCommunitiesMemberships":true}', "features": '{"responsive_web_graphql_exclude_directive_enabled":true}'}
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                viewer = data.get("data", {}).get("viewer", {})
                if viewer:
                    status["authenticated"] = True
                    status["username"] = viewer.get("screen_name", "")
        except Exception as e:
            status["error"] = str(e)
        return status

    def _search_tweets(
        self,
        query: str,
        limit: int = 20,
        search_type: str = "Top",
    ) -> list[dict[str, Any]]:
        """
        搜索推文（使用 SearchTimeline GraphQL API）

        Args:
            query: 搜索关键词
            limit: 返回数量
            search_type: "Top" 或 "Latest"
        """
        all_tweets: list[dict[str, Any]] = []
        cursor = None
        max_pages = 3  # 最多翻3页
        page_size = min(limit, 20)

        for page in range(max_pages):
            if len(all_tweets) >= limit:
                break

            # 构造 variables
            variables = {
                "rawQuery": query,
                "count": page_size,
                "querySource": "typed_query",
                "product": "Top" if search_type == "Top" else "Latest",
            }
            if cursor:
                variables["cursor"] = cursor

            # 构造 features（X API 需要一大堆 features 参数）
            features = {
                "responsive_web_graphql_exclude_directive_enabled": True,
                "verified_phone_label_enabled": False,
                "creator_subscriptions_tweet_preview_api_enabled": True,
                "responsive_web_graphql_timeline_navigation_enabled": True,
                "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                "c9s_tweet_anatomy_moderator_badge_enabled": True,
                "tweetypie_unmention_optimization_enabled": True,
                "responsive_web_edit_tweet_api_enabled": True,
                "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
                "view_counts_everywhere_api_enabled": True,
                "longform_notetweets_consumption_enabled": True,
                "responsive_web_twitter_article_tweet_consumption_enabled": False,
                "tweet_awards_web_tipping_enabled": False,
                "freedom_of_speech_not_reach_fetch_enabled": True,
                "standardized_nudges_misinfo": True,
                "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
                "rweb_video_timestamps_enabled": True,
                "longform_notetweets_rich_text_read_enabled": True,
                "longform_notetweets_inline_media_enabled": True,
                "responsive_web_media_download_video_enabled": False,
                "responsive_web_enhance_cards_enabled": False,
            }

            field_toggles = {
                "withArticleRichContentState": True,
                "withAuxiliaryUserLabels": False,
                "withConversationQueryHighlights": False,
                "withDownvotePerspective": False,
                "withGraphqlTimelineNavigation": True,
                "withMutedUsersFiltering": True,
                "withReactionsMetadata": False,
                "withReactionsPerspective": False,
                "withSessions": True,
                "withVoiceInfo": False,
            }

            try:
                # 使用通用的搜索 endpoint（通过 queryId 访问）
                # 不同时间 X 会更新 queryId，这里用一个已知稳定的
                query_id = "7c31s4h0q57s8fr76n2a0g"  # SearchTimeline queryId
                url = f"{API_BASE}/{query_id}/SearchTimeline"

                params = {
                    "variables": __import__("json").dumps(variables),
                    "features": __import__("json").dumps(features),
                    "fieldToggles": __import__("json").dumps(field_toggles),
                }

                resp = self.session.get(url, params=params, timeout=20)

                if resp.status_code != 200:
                    logger.warning(
                        "Search API returned %d for query %r: %s",
                        resp.status_code, query, resp.text[:200],
                    )
                    break

                data = resp.json()
                entries = self._parse_timeline_entries(data)

                if not entries:
                    break

                new_tweets = 0
                for entry in entries:
                    tweet_data = self._extract_tweet_from_entry(entry)
                    if tweet_data:
                        all_tweets.append(tweet_data)
                        new_tweets += 1
                        if len(all_tweets) >= limit:
                            break

                # 找下一页 cursor
                cursor = self._find_cursor(data)
                if not cursor or new_tweets == 0:
                    break

                time.sleep(0.5)  # 限速

            except Exception as e:
                logger.warning("Search failed for %r: %s", query, e)
                break

        return all_tweets[:limit]

    def _parse_timeline_entries(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """从 GraphQL 响应中提取 timeline entries"""
        try:
            timeline = (
                data.get("data", {})
                .get("search_by_raw_query", {})
                .get("search_timeline", {})
                .get("timeline", {})
            )
            instructions = timeline.get("instructions", [])

            entries = []
            for inst in instructions:
                if inst.get("type") == "TimelineAddEntries":
                    entries.extend(inst.get("entries", []))
                elif inst.get("type") == "TimelineAddToModule":
                    # 追加到已有模块
                    module_entries = inst.get("moduleItems", [])
                    entries.extend(module_entries)
            return entries
        except Exception as e:
            logger.debug("Failed to parse timeline entries: %s", e)
            return []

    def _find_cursor(self, data: dict[str, Any]) -> str | None:
        """从响应中提取下一页 cursor"""
        try:
            entries = self._parse_timeline_entries(data)
            for entry in entries:
                entry_id = entry.get("entryId", "")
                if "cursor-bottom" in entry_id or entry.get("content", {}).get("cursorType") == "Bottom":
                    return entry.get("content", {}).get("value")
                # 也可能在 content 的 entries 里
                items = entry.get("content", {}).get("items", [])
                for item in items:
                    if item.get("entryId", "").endswith("cursor-bottom"):
                        return item.get("content", {}).get("value")
            return None
        except Exception:
            return None

    def _extract_tweet_from_entry(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """从 timeline entry 中提取推文数据"""
        try:
            # entry 可能是 tweet 类型，也可能是其他（cursor、promoted 等）
            entry_id = entry.get("entryId", "")

            # 跳过非推文条目
            if not entry_id.startswith("tweet-") and "tweet-" not in entry_id:
                # 可能在 moduleItems 里
                item_content = entry.get("item", {}).get("itemContent", {})
                if not item_content:
                    item_content = entry.get("content", {})
                tweet_results = item_content.get("tweet_results", {})
            else:
                content = entry.get("content", {})
                item_content = content.get("itemContent", {})
                if not item_content:
                    # 可能是 module 类型
                    items = content.get("items", [])
                    if items:
                        item_content = items[0].get("item", {}).get("itemContent", {})
                tweet_results = item_content.get("tweet_results", {})

            if not tweet_results:
                return None

            result = tweet_results.get("result", {})
            if not result:
                return None

            # 可能是 tweet 类型，也可能是 retweet 等
            if result.get("__typename") == "Tweet":
                return self._parse_tweet_result(result)
            elif result.get("__typename") == "TweetWithVisibilityResults":
                return self._parse_tweet_result(result.get("tweet", {}))
            elif result.get("__typename") == "TweetTombstone":
                return None  # 被删除/隐藏的推文

            return None
        except Exception as e:
            logger.debug("Failed to extract tweet from entry: %s", e)
            return None

    def _parse_tweet_result(self, tweet: dict[str, Any]) -> dict[str, Any] | None:
        """解析单条推文数据"""
        try:
            if not tweet:
                return None

            # 处理转推（取原推文）
            legacy = tweet.get("legacy", {})
            if not legacy:
                return None

            # 如果是转推，取原推文
            retweeted = legacy.get("retweeted_status_result", {}).get("result", {})
            if retweeted:
                return self._parse_tweet_result(retweeted)

            user_legacy = tweet.get("core", {}).get("user_results", {}).get("result", {}).get("legacy", {})
            screen_name = user_legacy.get("screen_name", "")
            tweet_id = tweet.get("rest_id", "")

            if not screen_name or not tweet_id:
                return None

            full_text = legacy.get("full_text", "")
            created_at = legacy.get("created_at", "")

            # 互动数据
            favorite_count = legacy.get("favorite_count", 0)
            retweet_count = legacy.get("retweet_count", 0)
            reply_count = legacy.get("reply_count", 0)

            # 构造 URL
            url = f"https://x.com/{screen_name}/status/{tweet_id}"

            return {
                "tweet_id": tweet_id,
                "author": screen_name,
                "content": _normalize_text(full_text),
                "likes": favorite_count,
                "reposts": retweet_count,
                "replies": reply_count,
                "created_at": created_at,
                "url": url,
            }
        except Exception as e:
            logger.debug("Failed to parse tweet result: %s", e)
            return None

    def _raw_to_tweet(self, raw: dict[str, Any]) -> Tweet | None:
        """将原始数据转为 Tweet 对象"""
        if not raw or not raw.get("author") or not raw.get("tweet_id"):
            return None

        text = raw.get("content", "")
        if not text:
            return None

        assets = extract_assets(text)
        themes = extract_themes(text)
        quality = raw.get("likes", 0) * 3 + raw.get("reposts", 0) * 5 + raw.get("replies", 0) * 2

        tweet = Tweet(
            tweet_id=raw["tweet_id"],
            author=raw["author"],
            content=text,
            likes=raw.get("likes", 0),
            reposts=raw.get("reposts", 0),
            replies=raw.get("replies", 0),
            created_at=raw.get("created_at", ""),
            url=raw.get("url", ""),
            tags=_extract_tags(text),
            assets=assets,
            themes=themes,
            quality_score=quality,
        )
        tweet.is_kol = tweet.author.lower() in self._kol_handles
        return tweet

    def collect_daily(
        self,
        kol_handles: list[str],
        keyword_queries: list[str],
        limit: int = 120,
        fetch_comments: bool = False,
        comments_per_tweet: int = 10,
        min_likes_for_comments: int = 100,
    ) -> list[Tweet]:
        """
        每日采集主入口

        Args:
            kol_handles: KOL 账号列表（不含 @）
            keyword_queries: 关键词搜索查询
            limit: 总推文数量上限
            fetch_comments: 是否抓取评论（暂不支持，API 方式较慢）
            comments_per_tweet: 每条推文最多抓多少评论
            min_likes_for_comments: 点赞数达到多少才抓评论
        """
        all_tweets: list[Tweet] = []
        seen_ids: set[str] = set()

        # Phase 1: KOL 定向抓取（每个 KOL 抓最近的推文）
        logger.info("Collecting from %d KOL accounts...", len(kol_handles))
        per_kol = 3  # 每个 KOL 拉 3 条

        for handle in kol_handles:
            try:
                query = f"from:{handle}"
                raw_tweets = self._search_tweets(query, limit=per_kol, search_type="Latest")
                for raw in raw_tweets:
                    if raw["tweet_id"] not in seen_ids and not _is_spam(raw["content"], self._seen_fingerprints):
                        t = self._raw_to_tweet(raw)
                        if t:
                            t.is_kol = True
                            seen_ids.add(t.tweet_id)
                            all_tweets.append(t)
                time.sleep(0.3)
            except Exception as e:
                logger.warning("Failed to collect KOL %s: %s", handle, e)

        # Phase 2: 关键词搜索
        logger.info("Collecting from %d keyword queries...", len(keyword_queries))
        remaining = limit - len(all_tweets)
        if remaining > 0:
            per_keyword = max(remaining // len(keyword_queries) + 2, 5)
            for q in keyword_queries:
                try:
                    raw_tweets = self._search_tweets(q, limit=per_keyword, search_type="Top")
                    for raw in raw_tweets:
                        if raw["tweet_id"] not in seen_ids and not _is_spam(raw["content"], self._seen_fingerprints):
                            t = self._raw_to_tweet(raw)
                            if t:
                                seen_ids.add(t.tweet_id)
                                all_tweets.append(t)
                    time.sleep(0.3)
                except Exception as e:
                    logger.warning("Failed to search %r: %s", q, e)

                if len(all_tweets) >= limit:
                    break

        # 按质量分排序
        all_tweets.sort(key=lambda t: t.quality_score, reverse=True)
        return all_tweets[:limit]
