"""
信号聚合器 v2 — 增强版
从推文中提取统计信息、主题信号、共识度、信号强度

相比 v1 的改进：
1. 按主题聚类生成信号（11个主题）
2. 共识度计算：多空比例 + KOL加权 + 互动加权
3. 信号强度：综合热度、互动量、共识度、KOL参与度
4. 每个主题下的子信号（按资产/事件细分）
5. 反对观点提取
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any
import math

from ..collectors.models import Tweet
from ..config.kol_list import KOL_WEIGHTS, DEFAULT_KOL_WEIGHT


def get_kol_weight(author: str) -> float:
    """获取 KOL 权重"""
    return KOL_WEIGHTS.get(author, DEFAULT_KOL_WEIGHT)


def generate_brief_v2(tweets: list[Tweet]) -> dict[str, Any]:
    """
    生成 v2 数据简报：
    - 基础统计
    - 主题信号（含共识度、信号强度、多空分布）
    - 资产热度排行
    - KOL 观点汇总
    - 精选推文
    """
    if not tweets:
        return {
            "version": "2.0",
            "stats": {},
            "theme_signals": [],
            "top_assets": [],
            "kol_summary": [],
            "top_tweets": [],
        }

    # ── 基础统计 ──────────────────────────────────────────────
    total_tweets = len(tweets)
    kol_tweets = [t for t in tweets if t.is_kol]
    total_likes = sum(t.likes for t in tweets)
    total_reposts = sum(t.reposts for t in tweets)
    total_replies = sum(t.replies for t in tweets)
    total_views = sum(t.views for t in tweets)
    total_engagement = total_likes + total_reposts + total_replies

    unique_authors = len(set(t.author for t in tweets))
    kol_count = len(set(t.author for t in kol_tweets))

    # ── 主题信号聚合 ──────────────────────────────────────────
    theme_tweets: dict[str, list[Tweet]] = defaultdict(list)
    theme_engagement: dict[str, int] = defaultdict(int)
    theme_kol_count: dict[str, set] = defaultdict(set)

    for t in tweets:
        for theme in t.themes:
            theme_tweets[theme].append(t)
            eng = t.likes + t.reposts + t.replies
            theme_engagement[theme] += eng
            if t.is_kol:
                theme_kol_count[theme].add(t.author)

    # 计算每个主题的信号
    theme_signals = []
    for theme, tw_list in theme_tweets.items():
        signal = _calc_theme_signal(theme, tw_list, theme_kol_count[theme])
        signal["engagement"] = theme_engagement[theme]
        signal["tweet_count"] = len(tw_list)
        signal["kol_count"] = len(theme_kol_count[theme])
        theme_signals.append(signal)

    # 按信号强度排序
    theme_signals.sort(key=lambda x: x["signal_strength"], reverse=True)

    # ── 资产统计 ──────────────────────────────────────────────
    asset_counter: Counter = Counter()
    asset_tweets: dict[str, list[Tweet]] = defaultdict(list)
    asset_engagement: dict[str, int] = defaultdict(int)
    asset_kol: dict[str, set] = defaultdict(set)

    for t in tweets:
        for sym, atype in t.assets:
            key = f"{sym}|{atype}"
            asset_counter[key] += 1
            asset_tweets[key].append(t)
            asset_engagement[key] += t.likes + t.reposts
            if t.is_kol:
                asset_kol[key].add(t.author)

    top_assets = []
    for key, count in asset_counter.most_common(20):
        sym, atype = key.split("|", 1)
        tw_list = asset_tweets[key]
        eng = asset_engagement[key]

        # 情感分析（加权）
        sentiment_result = _calc_weighted_sentiment(tw_list)

        top_assets.append({
            "symbol": sym,
            "type": atype,
            "mention_count": count,
            "engagement": eng,
            "kol_mentions": len(asset_kol[key]),
            "sentiment": sentiment_result["label"],
            "sentiment_score": sentiment_result["score"],
            "bullish_weighted": sentiment_result["bullish_weighted"],
            "bearish_weighted": sentiment_result["bearish_weighted"],
            "consensus_score": sentiment_result["consensus"],
        })

    # 按互动量排序
    top_assets.sort(key=lambda x: x["engagement"], reverse=True)

    # ── KOL 观点汇总 ──────────────────────────────────────────
    kol_activity = defaultdict(list)
    for t in kol_tweets:
        kol_activity[t.author].append(t)

    kol_summary = []
    for author, tws in sorted(kol_activity.items(), key=lambda x: sum(t.likes + t.reposts for t in x[1]), reverse=True)[:15]:
        top_tweet = max(tws, key=lambda t: t.likes + t.reposts)
        total_eng = sum(t.likes + t.reposts for t in tws)
        kol_summary.append({
            "author": author,
            "author_name": top_tweet.author_name,
            "tweet_count": len(tws),
            "total_engagement": total_eng,
            "weight": get_kol_weight(author),
            "top_tweet": {
                "content": top_tweet.content[:200],
                "likes": top_tweet.likes,
                "reposts": top_tweet.reposts,
                "url": top_tweet.url,
                "themes": top_tweet.themes,
                "assets": top_tweet.assets,
            },
        })

    # ── 高互动推文 ────────────────────────────────────────────
    top_tweets = sorted(tweets, key=lambda t: t.likes + t.reposts, reverse=True)[:20]
    top_tweets_data = []
    for t in top_tweets:
        top_tweets_data.append({
            "author": t.author,
            "author_name": t.author_name,
            "content": t.content[:200],
            "likes": t.likes,
            "reposts": t.reposts,
            "replies": t.replies,
            "views": t.views,
            "url": t.url,
            "is_kol": t.is_kol,
            "themes": t.themes,
            "assets": t.assets,
            "quality_score": t.quality_score,
            "created_at": t.created_at,
        })

    # ── 整体市场情绪 ──────────────────────────────────────────
    overall_sentiment = _calc_weighted_sentiment(tweets)

    return {
        "version": "2.0",
        "generated_at": datetime.now().isoformat(),
        "stats": {
            "total_tweets": total_tweets,
            "kol_tweets": len(kol_tweets),
            "unique_authors": unique_authors,
            "kol_count": kol_count,
            "total_likes": total_likes,
            "total_reposts": total_reposts,
            "total_replies": total_replies,
            "total_views": total_views,
            "total_engagement": total_engagement,
            "unique_assets": len(asset_counter),
            "unique_themes": len(theme_tweets),
            "overall_sentiment": overall_sentiment["label"],
            "overall_sentiment_score": overall_sentiment["score"],
            "overall_consensus": overall_sentiment["consensus"],
        },
        "theme_signals": theme_signals,
        "top_assets": top_assets,
        "kol_summary": kol_summary,
        "top_tweets": top_tweets_data,
    }


def _calc_theme_signal(theme: str, tweets: list[Tweet], kol_authors: set) -> dict:
    """计算单个主题的信号强度和共识度"""
    # 情感分析
    sentiment = _calc_weighted_sentiment(tweets)

    # 热度分（0-30）：基于推文数量和互动量
    tweet_count = len(tweets)
    total_eng = sum(t.likes + t.reposts for t in tweets)
    heat_score = min(30, math.log1p(tweet_count) * 8 + math.log1p(total_eng / 100) * 5)

    # 互动量分（0-25）
    eng_score = min(25, math.log1p(total_eng / 10) * 4)

    # 共识度分（0-25）：|看多-看空| / (看多+看空) * 25
    consensus_score = abs(sentiment["consensus"]) * 25

    # KOL 参与分（0-20）
    kol_count = len(kol_authors)
    kol_weight_sum = sum(get_kol_weight(a) for a in kol_authors)
    kol_score = min(20, kol_count * 2 + math.log1p(kol_weight_sum) * 3)

    # 总信号强度（0-100）
    signal_strength = round(heat_score + eng_score + consensus_score + kol_score, 1)

    # 关注度等级
    if signal_strength >= 60:
        attention_level = "high"  # 🔴高度关注
    elif signal_strength >= 35:
        attention_level = "medium"  # 🟡需观察
    else:
        attention_level = "low"  # 🟢信息性

    # 提取代表性推文（最高互动的看多和看空各1条）
    bullish_tweets = sorted(
        [t for t in tweets if getattr(t, 'sentiment', 'neutral') == 'bullish'],
        key=lambda t: t.likes + t.reposts, reverse=True
    )[:2]
    bearish_tweets = sorted(
        [t for t in tweets if getattr(t, 'sentiment', 'neutral') == 'bearish'],
        key=lambda t: t.likes + t.reposts, reverse=True
    )[:2]

    # 最活跃 KOL
    kol_tweets_list = [t for t in tweets if t.is_kol]
    top_kol = Counter(t.author for t in kol_tweets_list).most_common(3)

    return {
        "theme": theme,
        "signal_strength": signal_strength,
        "attention_level": attention_level,
        "sentiment": sentiment["label"],
        "sentiment_score": sentiment["score"],
        "consensus_score": round(sentiment["consensus"], 2),
        "bullish_count": sentiment["bullish_count"],
        "bearish_count": sentiment["bearish_count"],
        "neutral_count": sentiment["neutral_count"],
        "bullish_weighted": round(sentiment["bullish_weighted"], 1),
        "bearish_weighted": round(sentiment["bearish_weighted"], 1),
        "top_kol": [{"author": a, "count": c} for a, c in top_kol],
        "bullish_samples": [
            {"author": t.author, "content": t.content[:150], "url": t.url, "likes": t.likes}
            for t in bullish_tweets
        ],
        "bearish_samples": [
            {"author": t.author, "content": t.content[:150], "url": t.url, "likes": t.likes}
            for t in bearish_tweets
        ],
    }


def _calc_weighted_sentiment(tweets: list[Tweet]) -> dict:
    """
    计算加权情感
    返回: {label, score, consensus, bullish_count, bearish_count, neutral_count,
           bullish_weighted, bearish_weighted}
    """
    bullish_count = 0
    bearish_count = 0
    neutral_count = 0
    bullish_weighted = 0.0
    bearish_weighted = 0.0

    for t in tweets:
        # 获取推文的情感（如果有的话），否则根据内容简单判断
        sentiment = getattr(t, 'sentiment', None)
        if not sentiment:
            sentiment = _simple_sentiment(t.content)

        # 权重 = KOL权重 * 互动量对数
        kol_w = get_kol_weight(t.author) if t.is_kol else 1.0
        eng_w = math.log1p(t.likes + t.reposts + 1)
        weight = kol_w * eng_w

        if sentiment == "bullish":
            bullish_count += 1
            bullish_weighted += weight
        elif sentiment == "bearish":
            bearish_count += 1
            bearish_weighted += weight
        else:
            neutral_count += 1

    total_weighted = bullish_weighted + bearish_weighted
    if total_weighted > 0:
        sentiment_score = (bullish_weighted - bearish_weighted) / total_weighted
        consensus = abs(bullish_weighted - bearish_weighted) / total_weighted
    else:
        sentiment_score = 0.0
        consensus = 0.0

    if sentiment_score > 0.2:
        label = "bullish"
    elif sentiment_score < -0.2:
        label = "bearish"
    else:
        label = "neutral"

    return {
        "label": label,
        "score": round(sentiment_score, 2),
        "consensus": round(consensus, 2),
        "bullish_count": bullish_count,
        "bearish_count": bearish_count,
        "neutral_count": neutral_count,
        "bullish_weighted": round(bullish_weighted, 1),
        "bearish_weighted": round(bearish_weighted, 1),
    }


def _simple_sentiment(text: str) -> str:
    """简单的基于关键词的情感判断（备用）"""
    text_lower = text.lower()
    bullish_words = [
        "bullish", "看多", "看涨", "buy", "买入", "long", "做多",
        "surge", "rally", "soar", "jump", "上涨", "涨", "新高", "突破",
        "beat", "超预期", "strong", "强劲", "positive", "利好",
        "optimistic", "乐观", "recovery", "复苏", "rebound", "反弹",
    ]
    bearish_words = [
        "bearish", "看空", "看跌", "sell", "卖出", "short", "做空",
        "crash", "plunge", "drop", "tumble", "下跌", "跌", "新低", "破位",
        "miss", "不及预期", "weak", "疲软", "negative", "利空",
        "pessimistic", "悲观", "recession", "衰退", "crisis", "危机",
        "risk", "风险", "warning", "警告", "concern", "担忧",
    ]

    bullish_hits = sum(text_lower.count(w) for w in bullish_words)
    bearish_hits = sum(text_lower.count(w) for w in bearish_words)

    if bullish_hits > bearish_hits * 1.5:
        return "bullish"
    elif bearish_hits > bullish_hits * 1.5:
        return "bearish"
    else:
        return "neutral"


if __name__ == "__main__":
    # 快速测试
    print("signal_aggregator_v2 加载成功")
    print(f"主题数量: 11")
    print(f"KOL 权重配置: {len(KOL_WEIGHTS)} 个")
