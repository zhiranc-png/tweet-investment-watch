"""
信号聚合器 — 从推文中提取统计信息和投资信号
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from ..collectors.models import Tweet


def generate_brief(tweets: list[Tweet]) -> dict[str, Any]:
    """
    生成数据简报：统计信息 + 热门标的 + 热门主题 + 精选推文
    """
    if not tweets:
        return {"stats": {}, "assets": {}, "themes": {}, "top_tweets": [], "kol_tweets": []}

    # ── 基础统计 ──────────────────────────────────────────────────────────
    total_tweets = len(tweets)
    kol_tweets = [t for t in tweets if t.is_kol]
    total_likes = sum(t.likes for t in tweets)
    total_reposts = sum(t.reposts for t in tweets)
    total_replies = sum(t.replies for t in tweets)

    unique_authors = len(set(t.author for t in tweets))
    kol_count = len(set(t.author for t in kol_tweets))

    # ── 标的统计 ──────────────────────────────────────────────────────────
    asset_counter: Counter = Counter()
    asset_tweets: dict[str, list[Tweet]] = defaultdict(list)
    asset_engagement: dict[str, int] = defaultdict(int)

    for t in tweets:
        for sym, name in t.assets:
            key = f"{sym}|{name}"
            asset_counter[key] += 1
            asset_tweets[key].append(t)
            asset_engagement[key] += t.likes + t.reposts

    # 按讨论热度排序
    top_assets = []
    for key, count in asset_counter.most_common(15):
        sym, name = key.split("|", 1)
        tw_list = asset_tweets[key]
        eng = asset_engagement[key]
        kol_mentions = sum(1 for t in tw_list if t.is_kol)

        # 简单情感倾向（基于关键词）
        bullish = sum(1 for t in tw_list if _is_bullish(t.content))
        bearish = sum(1 for t in tw_list if _is_bearish(t.content))
        sentiment = "neutral"
        if bullish > bearish * 1.5:
            sentiment = "bullish"
        elif bearish > bullish * 1.5:
            sentiment = "bearish"

        top_assets.append({
            "symbol": sym,
            "name": name,
            "mention_count": count,
            "engagement": eng,
            "kol_mentions": kol_mentions,
            "sentiment": sentiment,
            "bullish_count": bullish,
            "bearish_count": bearish,
            "sample_tweets": [
                {
                    "author": t.author,
                    "content": t.content[:200],
                    "likes": t.likes,
                    "url": t.url,
                    "is_kol": t.is_kol,
                }
                for t in sorted(tw_list, key=lambda x: x.likes, reverse=True)[:3]
            ],
        })

    # ── 主题统计 ──────────────────────────────────────────────────────────
    theme_counter: Counter = Counter()
    theme_engagement: dict[str, int] = defaultdict(int)
    theme_tweets: dict[str, list[Tweet]] = defaultdict(list)

    for t in tweets:
        for theme in t.themes:
            theme_counter[theme] += 1
            theme_engagement[theme] += t.likes + t.reposts
            theme_tweets[theme].append(t)

    top_themes = []
    for theme, count in theme_counter.most_common(10):
        top_themes.append({
            "theme": theme,
            "tweet_count": count,
            "engagement": theme_engagement[theme],
            "top_tweets": [
                {
                    "author": t.author,
                    "content": t.content[:150],
                    "likes": t.likes,
                    "url": t.url,
                }
                for t in sorted(theme_tweets[theme], key=lambda x: x.likes, reverse=True)[:3]
            ],
        })

    # ── Top 推文（按质量分） ──────────────────────────────────────────────
    top_tweets = []
    for t in sorted(tweets, key=lambda x: x.quality_score, reverse=True)[:20]:
        top_tweets.append({
            "author": t.author,
            "author_name": t.author_name,
            "content": t.content,
            "likes": t.likes,
            "reposts": t.reposts,
            "replies": t.replies,
            "views": t.views,
            "created_at": t.created_at,
            "url": t.url,
            "assets": [list(a) for a in t.assets],
            "themes": t.themes,
            "quality_score": t.quality_score,
            "is_kol": t.is_kol,
            "comments_count": len(t.comments),
            "top_comments": [
                {
                    "author": c.author,
                    "content": c.content[:150],
                    "likes": c.likes,
                    "url": c.url,
                }
                for c in t.comments[:5]
            ],
        })

    # ── KOL 观点汇总 ──────────────────────────────────────────────────────
    kol_summary = []
    for t in sorted(kol_tweets, key=lambda x: x.likes, reverse=True)[:15]:
        kol_summary.append({
            "author": t.author,
            "author_name": t.author_name,
            "content": t.content,
            "likes": t.likes,
            "url": t.url,
            "assets": [list(a) for a in t.assets],
            "themes": t.themes,
        })

    return {
        "generated_at": datetime.now().isoformat(),
        "stats": {
            "total_tweets": total_tweets,
            "kol_tweets": len(kol_tweets),
            "unique_authors": unique_authors,
            "kol_count": kol_count,
            "total_likes": total_likes,
            "total_reposts": total_reposts,
            "total_replies": total_replies,
            "unique_assets": len(asset_counter),
            "unique_themes": len(theme_counter),
        },
        "top_assets": top_assets,
        "top_themes": top_themes,
        "top_tweets": top_tweets,
        "kol_summary": kol_summary,
    }


def _is_bullish(text: str) -> bool:
    """简单判断看多"""
    bullish_words = [
        "bullish", "buy", "long", "rally", "surge", "soar", "jump",
        "gain", "rise", "higher", "breakout", "uptrend", "accumulate",
        "看好", "买入", "上涨", "涨", "做多", "突破", "反弹", "牛市",
        "低估", "便宜", "抄底", "加仓",
    ]
    text_lower = text.lower()
    return any(w in text_lower for w in bullish_words)


def _is_bearish(text: str) -> bool:
    """简单判断看空"""
    bearish_words = [
        "bearish", "sell", "short", "crash", "drop", "fall", "decline",
        "lower", "downtrend", "overvalued", "bubble", "risk", "dump",
        "看空", "卖出", "下跌", "跌", "做空", "熊市", "回调",
        "高估", "泡沫", "风险", "减持", "清仓", "抛售",
    ]
    text_lower = text.lower()
    return any(w in text_lower for w in bearish_words)
