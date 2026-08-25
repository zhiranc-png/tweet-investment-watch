"""
X (Twitter) API 采集器 — 基于 GraphQL Search API + Cookie 认证
纯 HTTP 请求，无需浏览器

策略：全部用 SearchTimeline API
- KOL 用 from:username 搜索
- 关键词直接搜索
- 控制请求频率，避免限流
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import requests

from .asset_extractor import extract_assets, extract_themes
from .models import Tweet

logger = logging.getLogger(__name__)

# ── X 网页端公开 Bearer Token ─────────────────────────────────────────────
BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

API_BASE = "https://x.com/i/api/graphql"

# SearchTimeline queryId（X 网页端当前使用的）
SEARCH_QUERY_ID = "7c31s4h0q57s8fr76n2a0g"

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


# ── GraphQL features ──────────────────────────────────────────────────────
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
    """X/Twitter API 采集器 — SearchTimeline GraphQL API"""

    def __init__(self, auth_token: str, ct0: str, request_delay: float = 3.0) -> None:
        self.auth_token = auth_token
        self.ct0 = ct0
        self.request_delay = request_delay
        self.session = requests.Session()
        self._seen_fingerprints: dict[str, int] = {}
        self._kol_handles: set[str] = set()
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

    def _search(
        self,
        query: str,
        limit: int = 10,
        search_type: str = "Top",
    ) -> list[dict[str, Any]]:
        """执行搜索（带限流处理和重试）"""
        variables = {
            "rawQuery": query,
            "count": min(limit + 10, 30),
            "querySource": "typed_query",
            "product": search_type,
        }

        url = f"{API_BASE}/{SEARCH_QUERY_ID}/SearchTimeline"
        params = {
            "variables": json.dumps(variables),
            "features": json.dumps(DEFAULT_FEATURES),
        }

        max_retries = 2
        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=20)

                if resp.status_code == 429:
                    wait_time = 15 * (attempt + 1)
                    logger.warning("Rate limited (429), waiting %ds... (attempt %d/%d)",
                                   wait_time, attempt + 1, max_retries)
                    time.sleep(wait_time)
                    continue

                if resp.status_code != 200:
                    logger.debug("Search returned %d for %r: %s",
                                resp.status_code, query, resp.text[:150])
                    return []

                data = resp.json()
                return self._parse_search_results(data)

            except Exception as e:
                logger.debug("Search failed for %r: %s", query, e)
                if attempt < max_retries - 1:
                    time.sleep(5)
            finally:
                time.sleep(self.request_delay)

        return []

    def _parse_search_results(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """解析搜索结果"""
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
            return tweets
        except Exception as e:
            logger.debug("Failed to parse search results: %s", e)
            return []

    def _extract_tweet_from_entry(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """从 timeline entry 提取推文"""
        try:
            entry_id = entry.get("entryId", "")
            if not entry_id.startswith("tweet-"):
                # 可能是 module 类型
                content = entry.get("content", {})
                if content.get("entryType") == "TimelineTimelineModule":
                    items = content.get("items", [])
                    for item in items:
                        item_content = item.get("item", {}).get("itemContent", {})
                        tweet_results = item_content.get("tweet_results", {})
                        if tweet_results:
                            return self._parse_tweet_result(tweet_results.get("result", {}))
                return None

            content = entry.get("content", {})
            item_content = content.get("itemContent", {})
            if not item_content:
                return None

            tweet_results = item_content.get("tweet_results", {})
            if not tweet_results:
                return None

            return self._parse_tweet_result(tweet_results.get("result", {}))
        except Exception:
            return None

    def _parse_tweet_result(self, tweet: dict[str, Any]) -> dict[str, Any] | None:
        """解析单条推文"""
        try:
            if not tweet:
                return None

            typename = tweet.get("__typename", "")
            if typename == "TweetWithVisibilityResults":
                tweet = tweet.get("tweet", {})
            elif typename == "TweetTombstone":
                return None

            legacy = tweet.get("legacy", {})
            if not legacy:
                return None

            # 跳过转推（取原推文）
            retweeted = legacy.get("retweeted_status_result", {}).get("result", {})
            if retweeted:
                return self._parse_tweet_result(retweeted)

            user_legacy = (
                tweet.get("core", {})
                .get("user_results", {})
                .get("result", {})
                .get("legacy", {})
            )
            screen_name = user_legacy.get("screen_name", "")
            tweet_id = tweet.get("rest_id", "")

            if not screen_name or not tweet_id:
                return None

            return {
                "tweet_id": tweet_id,
                "author": screen_name,
                "content": _normalize_text(legacy.get("full_text", "")),
                "likes": legacy.get("favorite_count", 0),
                "reposts": legacy.get("retweet_count", 0),
                "replies": legacy.get("reply_count", 0),
                "created_at": legacy.get("created_at", ""),
                "url": f"https://x.com/{screen_name}/status/{tweet_id}",
            }
        except Exception:
            return None

    def _raw_to_tweet(self, raw: dict[str, Any]) -> Tweet | None:
        """转为 Tweet 对象"""
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
        """简单健康检查：搜索一个常见词看是否返回结果"""
        status = {
            "platform": "x_api",
            "auth_token_set": bool(self.auth_token),
            "ct0_set": bool(self.ct0),
            "api_works": False,
        }
        try:
            results = self._search("stock market", limit=3)
            status["api_works"] = len(results) > 0
            status["test_results"] = len(results)
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
        - KOL: from:username 搜索（Latest，抓最新推文）
        - 关键词: Top 搜索（抓热门讨论）
        - 控制总请求数和频率，避免限流
        """
        all_tweets: list[Tweet] = []
        seen_ids: set[str] = set()

        # Phase 1: KOL 推文
        logger.info("Phase 1: Collecting from %d KOL accounts...", len(kol_handles))
        per_kol = 4
        successful_kols = 0

        for handle in kol_handles:
            query = f"from:{handle}"
            raw_tweets = self._search(query, limit=per_kol, search_type="Latest")

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

        logger.info("KOL 采集: %d/%d 个有有效推文，共 %d 条",
                    successful_kols, len(kol_handles),
                    sum(1 for t in all_tweets if t.is_kol))

        # Phase 2: 关键词搜索
        remaining = limit - len(all_tweets)
        if remaining > 0 and keyword_queries:
            per_keyword = max(remaining // len(keyword_queries) + 3, 5)
            logger.info("Phase 2: Searching %d keywords (%d each)...",
                        len(keyword_queries), per_keyword)

            for q in keyword_queries:
                raw_tweets = self._search(q, limit=per_keyword, search_type="Top")
                for raw in raw_tweets:
                    if raw["tweet_id"] not in seen_ids:
                        t = self._raw_to_tweet(raw)
                        if t and not _is_spam(t.content, self._seen_fingerprints):
                            seen_ids.add(t.tweet_id)
                            all_tweets.append(t)

                if len(all_tweets) >= limit:
                    break

        # 按质量分排序
        all_tweets.sort(key=lambda t: t.quality_score, reverse=True)
        result = all_tweets[:limit]

        kol_count = sum(1 for t in result if t.is_kol)
        logger.info("采集完成: 共 %d 条 (KOL: %d, 搜索: %d)",
                    len(result), kol_count, len(result) - kol_count)
        return result
