"""
X (Twitter) API 爬虫 — 基于 auth_token 调用内部 GraphQL API
轻量、快速，适合 GitHub Actions 等无浏览器环境

使用方式:
    collector = XAPICollector(auth_token="xxx", ct0="yyy")
    tweets = collector.collect_daily()
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .asset_extractor import extract_assets, extract_themes
from .models import Tweet

logger = logging.getLogger(__name__)

# X 内部 GraphQL API 端点
API_BASE = "https://x.com/i/api/graphql"

# GraphQL feature IDs（这些 ID 可能随 X 更新而变化）
# UserTweets 接口：获取用户时间线
USER_TWEETS_FEATURE_ID = "Q1n9rTq9sZiI_p8xX7n0vQ"
# SearchTimeline 接口：搜索
SEARCH_FEATURE_ID = "mWebSearch_202601"
# TweetDetail 接口：推文详情（含评论）
TWEET_DETAIL_FEATURE_ID = "VW7qOy5k3sZ3fV9xQ8zL2w"

# 垃圾内容过滤规则
SPAM_PATTERNS: list[str] = [
    r"^(up|gm|gn|lfg|nice|wow|hi|hello)\b",
    r"^\s*UID\s*[:：]?\s*\d+",
    r"^@\w+\s*@\w+\s*@\w+",
    r"(join|enter).*(giveaway|raffle|lottery)",
    r"(DM|dm)\s*(me|for|to)\s*(collab|promo|marketing|join|access)",
    r"(guaranteed|easy)\s*(profit|money|income|return)",
    r"(telegram|t\.me)/\S+",
    r"(🚀\s*){3,}",
    r"(private|alpha|vip)\s*(TG|telegram|group|channel)",
    r"\d{3,}(\.\d+)?x\s*(return|gain|profit)",
    r"(?:#\w+\s*){7,}",
    r"^(like|retweet|rt|follow|tag)\s.*(to\s*win|for\s*a\s*chance)",
]
_SPAM_RE = [re.compile(p, re.I) for p in SPAM_PATTERNS]


def is_spam(text: str) -> bool:
    """判断是否为垃圾内容"""
    if len(text.strip()) < 20:
        return True
    for pat in _SPAM_RE:
        if pat.search(text):
            return True
    return False


class XAPICollector:
    """基于 auth_token 的 X API 爬虫"""

    def __init__(self, auth_token: str, ct0: str, proxy: str | None = None):
        self.auth_token = auth_token
        self.ct0 = ct0
        self.proxy = proxy
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "X-Twitter-Active-User": "yes",
            "X-Twitter-Client-Language": "en",
            "X-Twitter-Auth-Type": "OAuth2Session",
            "X-CSRF-Token": ct0,
        })
        self.session.cookies.set("auth_token", auth_token, domain=".x.com")
        self.session.cookies.set("ct0", ct0, domain=".x.com")

        if proxy:
            self.session.proxies = {
                "http": proxy,
                "https": proxy,
            }

        self.kol_handles: list[str] = []
        self._user_id_cache: dict[str, str] = {}

    def set_kol_handles(self, handles: list[str]) -> None:
        """设置 KOL 账号列表"""
        self.kol_handles = handles

    def health_check(self) -> dict:
        """检查 auth_token 是否有效"""
        try:
            # 调用一个简单的接口验证
            url = f"{API_BASE}/Y0n-lFeE2Vq_4b5w8fX9Lw/UserByScreenName"
            params = {
                "variables": '{"screen_name":"elonmusk","withSafetyModeUserFields":true}',
                "features": '{"hidden_profile_subscriptions_enabled":true,"rweb_tipjar_consumption_enabled":true,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"subscriptions_verification_info_is_identity_verified_enabled":true,"subscriptions_verification_info_verified_since_enabled":true,"highlights_tweets_tab_ui_enabled":true,"responsive_web_twitter_article_notes_tab_enabled":false,"subscriptions_feature_can_gift_premium":false,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"responsive_web_graphql_timeline_navigation_enabled":true}',
            }
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data and "user" in data["data"]:
                    return {"cookies_valid": True, "error": None}
            return {"cookies_valid": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            return {"cookies_valid": False, "error": str(e)}

    def _get_user_id(self, screen_name: str) -> str | None:
        """通过用户名获取 user_id（带缓存）"""
        if screen_name in self._user_id_cache:
            return self._user_id_cache[screen_name]

        try:
            url = f"{API_BASE}/Y0n-lFeE2Vq_4b5w8fX9Lw/UserByScreenName"
            params = {
                "variables": '{"screen_name":"%s","withSafetyModeUserFields":true}' % screen_name,
                "features": '{"hidden_profile_subscriptions_enabled":true,"rweb_tipjar_consumption_enabled":true,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"subscriptions_verification_info_is_identity_verified_enabled":true,"subscriptions_verification_info_verified_since_enabled":true,"highlights_tweets_tab_ui_enabled":true,"responsive_web_twitter_article_notes_tab_enabled":false,"subscriptions_feature_can_gift_premium":false,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"responsive_web_graphql_timeline_navigation_enabled":true}',
            }
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                user = data.get("data", {}).get("user", {})
                rest_id = user.get("result", {}).get("rest_id")
                if rest_id:
                    self._user_id_cache[screen_name] = rest_id
                    return rest_id
        except Exception as e:
            logger.warning(f"获取用户ID失败 {screen_name}: {e}")

        return None

    def _parse_tweet(self, tweet_data: dict, is_kol: bool = False) -> Tweet | None:
        """解析单条推文数据"""
        try:
            result = tweet_data.get("content", {}).get("itemContent", {}).get("tweet_results", {}).get("result", {})
            if not result:
                # 尝试其他结构
                result = tweet_data.get("tweet_results", {}).get("result", {})
            if not result:
                return None

            # 跳过被删除/受限的推文
            if result.get("__typename") != "Tweet":
                return None

            legacy = result.get("legacy", {})
            if not legacy:
                return None

            # 跳过转推（只看原创）
            if legacy.get("retweeted_status_result"):
                return None

            content = legacy.get("full_text", "")
            if is_spam(content):
                return None

            user = result.get("core", {}).get("user_results", {}).get("result", {})
            user_legacy = user.get("legacy", {})
            author = user_legacy.get("screen_name", "")
            author_name = user_legacy.get("name", "")

            tweet_id = result.get("rest_id", "")
            created_at = legacy.get("created_at", "")
            likes = legacy.get("favorite_count", 0)
            reposts = legacy.get("retweet_count", 0)
            replies = legacy.get("reply_count", 0)
            views = int(result.get("views", {}).get("count", "0") or 0)

            url = f"https://x.com/{author}/status/{tweet_id}"

            # 提取标的和主题
            assets = extract_assets(content)
            themes = extract_themes(content)

            # 质量分
            quality = self._calc_quality(likes, reposts, replies, views, len(content), is_kol)

            return Tweet(
                tweet_id=tweet_id,
                author=author,
                author_name=author_name,
                content=content,
                likes=likes,
                reposts=reposts,
                replies=replies,
                views=views,
                created_at=created_at,
                url=url,
                assets=assets,
                themes=themes,
                quality_score=quality,
                is_kol=is_kol,
            )
        except Exception as e:
            logger.debug(f"解析推文失败: {e}")
            return None

    def _calc_quality(self, likes: int, reposts: int, replies: int, views: int,
                       content_len: int, is_kol: bool) -> float:
        """计算推文质量分"""
        score = 0.0
        score += min(likes / 100.0, 10)
        score += min(reposts / 50.0, 5)
        score += min(replies / 20.0, 5)
        if views > 0:
            score += min(views / 10000.0, 5)
        score += min(content_len / 100.0, 3)
        if is_kol:
            score *= 1.2
        return round(score, 2)

    def fetch_user_tweets(self, screen_name: str, limit: int = 20) -> list[Tweet]:
        """获取指定用户的最新推文"""
        user_id = self._get_user_id(screen_name)
        if not user_id:
            return []

        tweets = []
        cursor = None
        is_kol = screen_name.lower() in [h.lower() for h in self.kol_handles]

        for page in range(3):  # 最多3页
            if len(tweets) >= limit:
                break

            try:
                variables = {
                    "userId": user_id,
                    "count": 20,
                    "includePromotedContent": False,
                    "withQuickPromoteEligibilityTweetFields": False,
                    "withVoice": False,
                    "withV2Timeline": True,
                }
                if cursor:
                    variables["cursor"] = cursor

                features = {
                    "rweb_tipjar_consumption_enabled": True,
                    "responsive_web_graphql_exclude_directive_enabled": True,
                    "verified_phone_label_enabled": False,
                    "creator_subscriptions_tweet_preview_api_enabled": True,
                    "responsive_web_graphql_timeline_navigation_enabled": True,
                    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                    "communities_web_enable_tweet_community_results_fetch": True,
                    "c9s_tweet_anatomy_moderator_badge_enabled": True,
                    "articles_preview_enabled": True,
                    "responsive_web_edit_tweet_api_enabled": True,
                    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
                    "view_counts_everywhere_api_enabled": True,
                    "longform_notetweets_consumption_enabled": True,
                    "responsive_web_twitter_article_tweet_consumption_enabled": True,
                    "tweet_awards_web_tipping_enabled": False,
                    "creator_subscriptions_quote_tweet_preview_enabled": False,
                    "freedom_of_speech_not_reach_fetch_enabled": True,
                    "standardized_nudges_misinfo": True,
                    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
                    "rweb_video_timestamps_enabled": True,
                    "longform_notetweets_rich_text_read_enabled": True,
                    "longform_notetweets_inline_media_enabled": True,
                    "responsive_web_enhance_cards_enabled": False,
                }

                import json
                url = f"{API_BASE}/{USER_TWEETS_FEATURE_ID}/UserTweets"
                params = {
                    "variables": json.dumps(variables),
                    "features": json.dumps(features),
                }

                resp = self.session.get(url, params=params, timeout=20)
                if resp.status_code != 200:
                    logger.warning(f"获取用户推文失败 {screen_name}: HTTP {resp.status_code}")
                    break

                data = resp.json()
                timeline = data.get("data", {}).get("user", {}).get("result", {}).get(
                    "timeline_v2", {}).get("timeline", {})
                entries = timeline.get("instructions", [])

                new_cursor = None
                for instr in entries:
                    if instr.get("type") == "TimelineAddEntries":
                        for entry in instr.get("entries", []):
                            entry_id = entry.get("entryId", "")
                            if entry_id.startswith("tweet-"):
                                tweet = self._parse_tweet(entry.get("content", {}), is_kol=is_kol)
                                if tweet:
                                    tweets.append(tweet)
                            elif "cursor-bottom" in entry_id:
                                new_cursor = entry.get("content", {}).get("value")

                cursor = new_cursor
                if not cursor:
                    break

                time.sleep(1)  # 限速

            except Exception as e:
                logger.warning(f"获取用户推文异常 {screen_name}: {e}")
                break

        return tweets[:limit]

    def search_tweets(self, query: str, limit: int = 30) -> list[Tweet]:
        """搜索推文"""
        tweets = []
        cursor = None

        for page in range(3):
            if len(tweets) >= limit:
                break

            try:
                import json
                variables = {
                    "rawQuery": query,
                    "count": 20,
                    "querySource": "typed_query",
                    "product": "Top",
                }
                if cursor:
                    variables["cursor"] = cursor

                features = {
                    "rweb_tipjar_consumption_enabled": True,
                    "responsive_web_graphql_exclude_directive_enabled": True,
                    "verified_phone_label_enabled": False,
                    "creator_subscriptions_tweet_preview_api_enabled": True,
                    "responsive_web_graphql_timeline_navigation_enabled": True,
                    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                    "communities_web_enable_tweet_community_results_fetch": True,
                    "c9s_tweet_anatomy_moderator_badge_enabled": True,
                    "articles_preview_enabled": True,
                    "tweetypie_unmention_optimization_enabled": True,
                    "responsive_web_edit_tweet_api_enabled": True,
                    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
                    "view_counts_everywhere_api_enabled": True,
                    "longform_notetweets_consumption_enabled": True,
                    "responsive_web_twitter_article_tweet_consumption_enabled": True,
                    "tweet_awards_web_tipping_enabled": False,
                    "creator_subscriptions_quote_tweet_preview_enabled": False,
                    "freedom_of_speech_not_reach_fetch_enabled": True,
                    "standardized_nudges_misinfo": True,
                    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
                    "rweb_video_timestamps_enabled": True,
                    "longform_notetweets_rich_text_read_enabled": True,
                    "longform_notetweets_inline_media_enabled": True,
                    "responsive_web_enhance_cards_enabled": False,
                }

                url = f"{API_BASE}/{SEARCH_FEATURE_ID}/SearchTimeline"
                params = {
                    "variables": json.dumps(variables),
                    "features": json.dumps(features),
                }

                resp = self.session.get(url, params=params, timeout=20)
                if resp.status_code != 200:
                    logger.warning(f"搜索失败 {query}: HTTP {resp.status_code}")
                    break

                data = resp.json()
                search = data.get("data", {}).get("search_by_raw_query", {})
                timeline = search.get("search_timeline", {}).get("timeline", {})
                entries = timeline.get("instructions", [])

                new_cursor = None
                for instr in entries:
                    if instr.get("type") == "TimelineAddEntries":
                        for entry in instr.get("entries", []):
                            entry_id = entry.get("entryId", "")
                            if entry_id.startswith("tweet-"):
                                tweet = self._parse_tweet(entry.get("content", {}))
                                if tweet:
                                    tweets.append(tweet)
                            elif "cursor-bottom" in entry_id:
                                new_cursor = entry.get("content", {}).get("value")

                cursor = new_cursor
                if not cursor:
                    break

                time.sleep(1)

            except Exception as e:
                logger.warning(f"搜索异常 {query}: {e}")
                break

        return tweets[:limit]

    def fetch_tweet_comments(self, tweet_id: str, limit: int = 10) -> list[Tweet]:
        """获取推文评论"""
        comments = []
        cursor = None

        for page in range(2):
            if len(comments) >= limit:
                break

            try:
                import json
                variables = {
                    "focalTweetId": tweet_id,
                    "with_rux_injections": False,
                    "rating": "Everyone",
                    "includePromotedContent": False,
                    "withCommunity": True,
                    "withQuickPromoteEligibilityTweetFields": False,
                    "withBirdwatchNotes": False,
                    "withVoice": True,
                    "withV2Timeline": True,
                }
                if cursor:
                    variables["cursor"] = cursor

                features = {
                    "rweb_tipjar_consumption_enabled": True,
                    "responsive_web_graphql_exclude_directive_enabled": True,
                    "verified_phone_label_enabled": False,
                    "creator_subscriptions_tweet_preview_api_enabled": True,
                    "responsive_web_graphql_timeline_navigation_enabled": True,
                    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                    "communities_web_enable_tweet_community_results_fetch": True,
                    "c9s_tweet_anatomy_moderator_badge_enabled": True,
                    "articles_preview_enabled": True,
                    "tweetypie_unmention_optimization_enabled": True,
                    "responsive_web_edit_tweet_api_enabled": True,
                    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
                    "view_counts_everywhere_api_enabled": True,
                    "longform_notetweets_consumption_enabled": True,
                    "tweet_awards_web_tipping_enabled": False,
                    "creator_subscriptions_quote_tweet_preview_enabled": False,
                    "freedom_of_speech_not_reach_fetch_enabled": True,
                    "standardized_nudges_misinfo": True,
                    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
                    "rweb_video_timestamps_enabled": True,
                    "longform_notetweets_rich_text_read_enabled": True,
                    "longform_notetweets_inline_media_enabled": True,
                    "responsive_web_enhance_cards_enabled": False,
                }

                url = f"{API_BASE}/{TWEET_DETAIL_FEATURE_ID}/TweetDetail"
                params = {
                    "variables": json.dumps(variables),
                    "features": json.dumps(features),
                }

                resp = self.session.get(url, params=params, timeout=20)
                if resp.status_code != 200:
                    break

                data = resp.json()
                thread = data.get("data", {}).get("threaded_conversation_with_injections_v2", {})
                entries = thread.get("instructions", [])

                new_cursor = None
                for instr in entries:
                    if instr.get("type") == "TimelineAddEntries":
                        for entry in instr.get("entries", []):
                            entry_id = entry.get("entryId", "")
                            if entry_id.startswith("conversationthread-"):
                                # 评论在 conversationthread 里
                                items = entry.get("content", {}).get("items", [])
                                for item in items:
                                    tweet_item = item.get("item", {}).get("itemContent", {}).get("tweet_results", {}).get("result", {})
                                    if tweet_item.get("__typename") == "Tweet":
                                        # 构造一个标准结构来复用解析
                                        wrapped = {
                                            "content": {
                                                "itemContent": {
                                                    "tweet_results": {"result": tweet_item}
                                                }
                                            }
                                        }
                                        comment = self._parse_tweet(wrapped)
                                        if comment and comment.tweet_id != tweet_id:
                                            comments.append(comment)
                            elif "cursor-bottom" in entry_id:
                                new_cursor = entry.get("content", {}).get("value")

                cursor = new_cursor
                if not cursor:
                    break

                time.sleep(0.5)

            except Exception as e:
                logger.debug(f"获取评论异常 {tweet_id}: {e}")
                break

        # 按点赞数排序
        comments.sort(key=lambda t: t.likes, reverse=True)
        return comments[:limit]

    def collect_daily(
        self,
        kol_handles: list[str] | None = None,
        search_queries: list[str] | None = None,
        limit: int = 150,
        fetch_comments: bool = False,
        comments_per_tweet: int = 10,
        min_likes_for_comments: int = 100,
    ) -> list[Tweet]:
        """
        采集每日数据：KOL 时间线 + 关键词搜索
        """
        if kol_handles:
            self.kol_handles = kol_handles

        all_tweets: dict[str, Tweet] = {}
        kol_set = {h.lower() for h in self.kol_handles}

        # 1. 抓取 KOL 时间线
        print(f"📱 抓取 {len(self.kol_handles)} 位 KOL 的时间线...")
        for i, handle in enumerate(self.kol_handles):
            print(f"   [{i+1}/{len(self.kol_handles)}] @{handle}")
            user_tweets = self.fetch_user_tweets(handle, limit=15)
            for t in user_tweets:
                t.is_kol = True
                if t.tweet_id not in all_tweets:
                    all_tweets[t.tweet_id] = t
            time.sleep(0.5)

        print(f"   ✅ KOL 推文: {len(all_tweets)} 条")

        # 2. 关键词搜索
        if search_queries:
            print(f"🔍 搜索 {len(search_queries)} 个关键词...")
            for i, query in enumerate(search_queries):
                print(f"   [{i+1}/{len(search_queries)}] {query}")
                results = self.search_tweets(query, limit=20)
                for t in results:
                    t.is_kol = t.author.lower() in kol_set
                    if t.tweet_id not in all_tweets:
                        all_tweets[t.tweet_id] = t
                time.sleep(0.5)

            print(f"   ✅ 搜索结果: {len(all_tweets)} 条（去重后）")

        # 3. 抓取高互动推文的评论
        if fetch_comments:
            high_engagement = [
                t for t in all_tweets.values()
                if t.likes >= min_likes_for_comments
            ]
            high_engagement.sort(key=lambda t: t.likes, reverse=True)
            high_engagement = high_engagement[:10]  # 最多抓10条的评论

            print(f"💬 抓取 {len(high_engagement)} 条高互动推文的评论...")
            for i, tweet in enumerate(high_engagement):
                print(f"   [{i+1}/{len(high_engagement)}] @{tweet.author}: {tweet.content[:50]}...")
                comments = self.fetch_tweet_comments(tweet.tweet_id, limit=comments_per_tweet)
                tweet.comments = comments
                time.sleep(0.5)

            print(f"   ✅ 评论抓取完成")

        # 按质量分排序
        sorted_tweets = sorted(all_tweets.values(), key=lambda t: t.quality_score, reverse=True)
        return sorted_tweets[:limit]
