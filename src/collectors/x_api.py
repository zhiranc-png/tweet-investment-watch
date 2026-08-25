"""
X (Twitter) API 采集器 — 基于 GraphQL API + Cookie 认证
纯 HTTP 请求，无需浏览器

优化策略：
- KOL 用 UserTweets API（更高效，限流更松）
- 关键词精选 15 个核心词
- 请求间隔 2-3 秒，避免触发限流
"""

from __future__ import annotations

import json
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

API_BASE = "https://x.com/i/api/graphql"

# ── 已知稳定的 GraphQL queryId ────────────────────────────────────────────
# 这些是 X 网页端使用的 queryId，可能随版本更新
USER_TWEETS_QUERY_ID = "V1ze59qZpB55q2n7-8pX0w"  # UserTweets
SEARCH_TIMELINE_QUERY_ID = "7c31s4h0q57s8fr76n2a0g"  # SearchTimeline

# ── 垃圾内容过滤 ──────────────────────────────────────────────────────────
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


# ── GraphQL features（X API 要求的标准参数） ──────────────────────────────
DEFAULT_FEATURES = {
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


class XApiCollector:
    """
    X/Twitter API 采集器 — GraphQL API + Cookie 认证
    """

    def __init__(self, auth_token: str, ct0: str, request_delay: float = 2.5) -> None:
        self.auth_token = auth_token
        self.ct0 = ct0
        self.request_delay = request_delay  # 请求间隔（秒）
        self.session = requests.Session()
        self._seen_fingerprints: dict[str, int] = {}
        self._kol_handles: set[str] = set()
        self._user_id_cache: dict[str, str] = {}  # handle -> user_id 缓存
        self._setup_session()

    def _setup_session(self) -> None:
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
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://x.com",
            "Referer": "https://x.com/",
            "x-twitter-active-user": "yes",
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-client-language": "en",
        })
        self.session.cookies.set("auth_token", self.auth_token, domain=".x.com")
        self.session.cookies.set("ct0", self.ct0, domain=".x.com")

    def set_kol_handles(self, handles: list[str]) -> None:
        self._kol_handles = {h.lower() for h in handles}

    def _graphql_get(
        self,
        query_id: str,
        endpoint_name: str,
        variables: dict[str, Any],
        features: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """统一的 GraphQL GET 请求封装"""
        if features is None:
            features = DEFAULT_FEATURES

        url = f"{API_BASE}/{query_id}/{endpoint_name}"
        params = {
            "variables": json.dumps(variables),
            "features": json.dumps(features),
        }

        try:
            resp = self.session.get(url, params=params, timeout=20)

            if resp.status_code == 429:
                logger.warning("Rate limited (429) on %s, waiting 10s...", endpoint_name)
                time.sleep(10)
                # 重试一次
                resp = self.session.get(url, params=params, timeout=20)

            if resp.status_code != 200:
                logger.warning(
                    "API %s returned %d: %s",
                    endpoint_name, resp.status_code, resp.text[:200],
                )
                return None

            return resp.json()

        except Exception as e:
            logger.warning("API %s failed: %s", endpoint_name, e)
            return None
        finally:
            time.sleep(self.request_delay)  # 限速

    def _get_user_id(self, screen_name: str) -> str | None:
        """通过用户名获取 user_id（使用 UserByScreenName API）"""
        if screen_name in self._user_id_cache:
            return self._user_id_cache[screen_name]

        # 使用 UserByScreenName endpoint
        query_id = "GazOglc51Yt9qYd7gMf8XQ"  # UserByScreenName
        variables = {
            "screen_name": screen_name,
            "withSafetyModeUserFields": True,
        }
        features = {
            "hidden_profile_subscriptions_enabled": True,
            "rweb_tipjar_consumption_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "subscriptions_verification_info_is_identity_verified_enabled": True,
            "subscriptions_verification_info_verified_since_enabled": True,
            "highlights_tweets_tab_ui_enabled": True,
            "responsive_web_twitter_article_notes_tab_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
        }

        data = self._graphql_get(query_id, "UserByScreenName", variables, features)
        if not data:
            return None

        try:
            user = data.get("data", {}).get("user", {}).get("result", {})
            user_id = user.get("rest_id")
            if user_id:
                self._user_id_cache[screen_name] = user_id
                return user_id
        except Exception:
            pass

        return None

    def _get_user_tweets(self, user_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """获取用户推文（UserTweets API）"""
        variables = {
            "userId": user_id,
            "count": min(limit + 10, 40),  # 多要一些，过滤后可能不够
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": False,
            "withVoice": False,
            "withV2Timeline": True,
        }

        data = self._graphql_get(
            USER_TWEETS_QUERY_ID, "UserTweets", variables
        )
        if not data:
            return []

        # 解析 timeline
        try:
            timeline = (
                data.get("data", {})
                .get("user", {})
                .get("result", {})
                .get("timeline_v2", {})
                .get("timeline", {})
            )
            instructions = timeline.get("instructions", [])

            tweets = []
            for inst in instructions:
                if inst.get("type") == "TimelineAddEntries":
                    for entry in inst.get("entries", []):
                        tweet = self._extract_tweet_from_entry(entry)
                        if tweet:
                            tweets.append(tweet)
                            if len(tweets) >= limit:
                                break

            return tweets[:limit]
        except Exception as e:
            logger.debug("Failed to parse user tweets: %s", e)
            return []

    def _search_tweets(
        self,
        query: str,
        limit: int = 10,
        search_type: str = "Top",
    ) -> list[dict[str, Any]]:
        """搜索推文（SearchTimeline API）"""
        variables = {
            "rawQuery": query,
            "count": min(limit + 5, 20),
            "querySource": "typed_query",
            "product": search_type,
        }

        data = self._graphql_get(
            SEARCH_TIMELINE_QUERY_ID, "SearchTimeline", variables
        )
        if not data:
            return []

        try:
            timeline = (
                data.get("data", {})
                .get("search_by_raw_query", {})
                .get("search_timeline", {})
                .get("timeline", {})
            )
            instructions = timeline.get("instructions", [])

            tweets = []
            for inst in instructions:
                if inst.get("type") == "TimelineAddEntries":
                    for entry in inst.get("entries", []):
                        tweet = self._extract_tweet_from_entry(entry)
                        if tweet:
                            tweets.append(tweet)
                            if len(tweets) >= limit:
                                break

            return tweets[:limit]
        except Exception as e:
            logger.debug("Failed to parse search results: %s", e)
            return []

    def _extract_tweet_from_entry(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """从 timeline entry 中提取推文数据"""
        try:
            entry_id = entry.get("entryId", "")

            # 跳过 cursor、promoted 等非推文条目
            if entry_id.startswith("cursor-") or entry_id.startswith("who-to-follow"):
                return None

            # 获取 itemContent
            content = entry.get("content", {})
            if content.get("entryType") == "TimelineTimelineModule":
                # module 类型，取第一个 item
                items = content.get("items", [])
                if not items:
                    return None
                item_content = items[0].get("item", {}).get("itemContent", {})
            else:
                item_content = content.get("itemContent", {})

            if not item_content:
                return None

            tweet_results = item_content.get("tweet_results", {})
            if not tweet_results:
                return None

            result = tweet_results.get("result", {})
            if not result:
                return None

            typename = result.get("__typename", "")
            if typename == "Tweet":
                return self._parse_tweet_result(result)
            elif typename == "TweetWithVisibilityResults":
                return self._parse_tweet_result(result.get("tweet", {}))
            elif typename == "TweetTombstone":
                return None

            return None
        except Exception as e:
            logger.debug("Failed to extract tweet from entry: %s", e)
            return None

    def _parse_tweet_result(self, tweet: dict[str, Any]) -> dict[str, Any] | None:
        """解析单条推文数据"""
        try:
            if not tweet:
                return None

            legacy = tweet.get("legacy", {})
            if not legacy:
                return None

            # 如果是转推，取原推文
            retweeted_result = legacy.get("retweeted_status_result", {}).get("result", {})
            if retweeted_result:
                return self._parse_tweet_result(retweeted_result)

            # 获取用户信息
            core = tweet.get("core", {})
            user_result = core.get("user_results", {}).get("result", {})
            user_legacy = user_result.get("legacy", {})
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

    def health_check(self) -> dict[str, Any]:
        """检查认证是否有效（通过获取用户信息）"""
        status: dict[str, Any] = {
            "platform": "x_api",
            "auth_token_set": bool(self.auth_token),
            "ct0_set": bool(self.ct0),
            "authenticated": False,
        }
        try:
            # 用一个已知的用户来测试
            user_id = self._get_user_id("elonmusk")
            if user_id:
                status["authenticated"] = True
                status["test_user_id"] = user_id
        except Exception as e:
            status["error"] = str(e)
        return status

    def collect_daily(
        self,
        kol_handles: list[str],
        keyword_queries: list[str],
        limit: int = 100,
        fetch_comments: bool = False,
        comments_per_tweet: int = 10,
        min_likes_for_comments: int = 100,
    ) -> list[Tweet]:
        """
        每日采集主入口

        策略：
        - KOL 用 UserTweets API（更高效）
        - 关键词精选核心词，用 Search API
        - 控制总请求量，避免限流
        """
        all_tweets: list[Tweet] = []
        seen_ids: set[str] = set()

        # Phase 1: KOL 推文（用 UserTweets API）
        logger.info("Collecting from %d KOL accounts (UserTweets API)...", len(kol_handles))
        per_kol = 4  # 每个 KOL 拉 4 条

        successful_kols = 0
        for handle in kol_handles:
            try:
                user_id = self._get_user_id(handle)
                if not user_id:
                    logger.debug("Failed to get user_id for %s", handle)
                    continue

                raw_tweets = self._get_user_tweets(user_id, limit=per_kol)
                new_count = 0
                for raw in raw_tweets:
                    if raw["tweet_id"] not in seen_ids:
                        t = self._raw_to_tweet(raw)
                        if t and not _is_spam(t.content, self._seen_fingerprints):
                            t.is_kol = True
                            seen_ids.add(t.tweet_id)
                            all_tweets.append(t)
                            new_count += 1

                if new_count > 0:
                    successful_kols += 1

            except Exception as e:
                logger.warning("Failed to collect KOL %s: %s", handle, e)

        logger.info("KOL 采集完成: %d/%d 个账号有新推文", successful_kols, len(kol_handles))

        # Phase 2: 关键词搜索（精选核心词，避免限流）
        remaining = limit - len(all_tweets)
        if remaining > 0 and keyword_queries:
            # 精选关键词，最多 15 个
            selected_keywords = keyword_queries[:15]
            per_keyword = max(remaining // len(selected_keywords) + 2, 5)

            logger.info(
                "Collecting from %d keyword queries (Top results, %d each)...",
                len(selected_keywords), per_keyword,
            )

            for q in selected_keywords:
                try:
                    raw_tweets = self._search_tweets(q, limit=per_keyword, search_type="Top")
                    for raw in raw_tweets:
                        if raw["tweet_id"] not in seen_ids:
                            t = self._raw_to_tweet(raw)
                            if t and not _is_spam(t.content, self._seen_fingerprints):
                                seen_ids.add(t.tweet_id)
                                all_tweets.append(t)
                except Exception as e:
                    logger.warning("Failed to search %r: %s", q, e)

                if len(all_tweets) >= limit:
                    break

        # 按质量分排序
        all_tweets.sort(key=lambda t: t.quality_score, reverse=True)
        result = all_tweets[:limit]

        logger.info(
            "采集完成: 共 %d 条推文 (KOL: %d, 搜索: %d)",
            len(result),
            sum(1 for t in result if t.is_kol),
            sum(1 for t in result if not t.is_kol),
        )
        return result
