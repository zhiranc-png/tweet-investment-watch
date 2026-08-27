"""
信号聚合器 v2 — 增加共识度指标 + 增强情感分析

新增功能：
1. consensus_score（共识度）：量化多空分歧程度
2. kol_weighted_sentiment（KOL加权情感）：按影响力加权
3. signal_strength（信号强度）：综合热度+共识+互动量
4. trend_direction（趋势方向）：从推文中提取明确的方向性判断
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

# 兼容两种导入方式
try:
    from ..collectors.models import Tweet
except ImportError:
    from collectors.models import Tweet


# ── 情感词典 v2（更丰富、带权重）──────────────────────────────────
BULLISH_WORDS = {
    # 强看多（+2）
    "strong buy": 2, "conviction buy": 2, "all in": 2, "mooning": 2,
    "to the moon": 2, "parabolic": 2, "massive rally": 2, "blow off top": 2,
    "强烈看好": 2, "满仓": 2, "all-in": 2, "爆涨": 2, "暴涨": 2,
    # 中等看多（+1.5）
    "bullish": 1.5, "buy the dip": 1.5, "accumulate": 1.5, "breakout": 1.5,
    "uptrend": 1.5, "outperform": 1.5, "overweight": 1.5,
    "看好": 1.5, "买入": 1.5, "做多": 1.5, "突破": 1.5, "加仓": 1.5,
    "抄底": 1.5, "低估": 1.5, "便宜": 1.5,
    # 弱看多（+1）
    "rally": 1, "surge": 1, "soar": 1, "jump": 1, "gain": 1,
    "rise": 1, "higher": 1, "rebound": 1, "recovery": 1,
    "上涨": 1, "涨": 1, "反弹": 1, "回升": 1, "走牛": 1,
    "牛市": 1, "上行": 1, "走高": 1, "收涨": 1, "走强": 1,
    "利好": 1, "利多": 1, "超预期": 1.5, "beat": 1.5,
    "增持": 1, "跑赢": 1, "买入评级": 1,
    # 弱信号看多（+0.5）— 有倾向但不强烈
    "optimistic": 0.5, "bull": 0.5, "green": 0.5,
    "positive": 0.5, "improve": 0.5, "improvement": 0.5,
    "growth": 0.5, "expansion": 0.5, "upside": 0.5,
    "support": 0.5, "bottom": 0.5, "recovery": 0.5,
    "看好": 1.5, "乐观": 0.5, "复苏": 1, "增长": 0.5,
    "支撑": 0.5, "企稳": 0.5, "回暖": 0.5,
}

BEARISH_WORDS = {
    # 强看空（-2）
    "crash": -2, "collapse": -2, "meltdown": -2, "bloodbath": -2,
    "capitulation": -2, "hard landing": -2, "depression": -2,
    "暴跌": -2, "崩盘": -2, "爆仓": -2, "清仓": -2, "熔断": -2,
    # 中等看空（-1.5）
    "bearish": -1.5, "short": -1.5, "sell": -1.5, "overvalued": -1.5,
    "bubble": -1.5, "downtrend": -1.5, "underweight": -1.5,
    "underperform": -1.5, "tanking": -1.5,
    "看空": -1.5, "卖出": -1.5, "做空": -1.5, "高估": -1.5,
    "泡沫": -1.5, "减持": -1.5, "抛售": -1.5,
    # 弱看空（-1）
    "drop": -1, "fall": -1, "decline": -1, "lower": -1, "dump": -1,
    "pullback": -1, "correction": -1, "sell-off": -1, "selloff": -1,
    "下跌": -1, "跌": -1, "回调": -1, "走熊": -1, "熊市": -1,
    "走低": -1, "走弱": -1, "下挫": -1, "回落": -1, "收跌": -1,
    "下行": -1, "跑输": -1, "减持评级": -1,
    # 弱信号看空（-0.5）— 有倾向但不强烈
    "pessimistic": -0.5, "bear": -0.5, "red": -0.5,
    "negative": -0.5, "concern": -0.5, "worried": -0.5,
    "risk": -0.5, "danger": -0.5, "warning": -0.5,
    "slowdown": -0.5, "contraction": -0.5, "downside": -0.5,
    "pressure": -0.5, "weak": -0.5, "weakness": -0.5,
    "stress": -0.5, "crisis": -1, "default": -1,
    "悲观": -0.5, "担忧": -0.5, "风险": -0.5, "压力": -0.5,
    "疲软": -0.5, "放缓": -0.5, "下行压力": -1,
    "利空": -1.5, "不及预期": -1.5, "低于预期": -1.5,
    "减持": -1.5, "抛售": -1.5, "清仓": -2,
    "高估": -1.5, "泡沫": -1.5, "过热": -1,
}

NEUTRAL_PHRASES = [
    "sideways", "range bound", "consolidation", "wait and see",
    "on hold", "neutral", "hold", "uncertain", "unclear",
    "震荡", "横盘", "观望", "中性", "持有", "不确定",
]


def calculate_sentiment_score(text: str) -> dict:
    """
    计算单条推文的情感分数
    返回: {score, bullish_words, bearish_words, intensity, direction}
    """
    text_lower = text.lower()
    bull_score = 0.0
    bear_score = 0.0
    bull_matched = []
    bear_matched = []

    for word, weight in BULLISH_WORDS.items():
        if word in text_lower:
            bull_score += weight
            bull_matched.append(word)

    for word, weight in BEARISH_WORDS.items():
        if word in text_lower:
            bear_score += abs(weight)
            bear_matched.append(word)

    total = bull_score + bear_score
    if total == 0:
        return {
            "score": 0.0,
            "direction": "neutral",
            "intensity": 0.0,
            "bullish_words": [],
            "bearish_words": [],
        }

    # 净情感分：-1 到 +1
    net = (bull_score - bear_score) / total
    intensity = min(total / 3.0, 1.0)  # 强度：命中越多越强，上限3个词

    if net > 0.3:
        direction = "bullish"
    elif net < -0.3:
        direction = "bearish"
    else:
        direction = "neutral"

    return {
        "score": round(net, 3),
        "direction": direction,
        "intensity": round(intensity, 3),
        "bullish_words": bull_matched,
        "bearish_words": bear_matched,
    }


def calculate_consensus(tweets: list[Tweet]) -> dict:
    """
    计算一组推文的共识度
    
    共识度 = 1 - 分歧度
    分歧度 = 看空比例 × 看多比例 × 4（最大值为1，当多空各50%时）
    
    还计算：
    - kol_weighted_score: 按KOL影响力加权的情感分
    - engagement_weighted_score: 按互动量加权的情感分
    """
    if not tweets:
        return {
            "consensus_score": 0.0,
            "kol_consensus": 0.0,
            "bull_ratio": 0.0,
            "bear_ratio": 0.0,
            "neutral_ratio": 0.0,
            "kol_weighted_sentiment": 0.0,
            "engagement_weighted_sentiment": 0.0,
            "bull_count": 0,
            "bear_count": 0,
            "neutral_count": 0,
        }

    sentiments = []
    for t in tweets:
        text = t.content or ""
        sent = calculate_sentiment_score(text)
        sent["tweet"] = t
        sent["is_kol"] = t.is_kol
        views = getattr(t, "views", 0)
        sent["engagement"] = t.likes + t.reposts + views * 0.01
        sentiments.append(sent)

    bull_count = sum(1 for s in sentiments if s["direction"] == "bullish")
    bear_count = sum(1 for s in sentiments if s["direction"] == "bearish")
    neutral_count = sum(1 for s in sentiments if s["direction"] == "neutral")
    total = len(sentiments)

    bull_ratio = bull_count / total
    bear_ratio = bear_count / total
    neutral_ratio = neutral_count / total

    # 观点密度 = 有明确观点的推文占比（看多+看空）/总数
    opinion_density = (bull_count + bear_count) / total if total > 0 else 0.0

    # 分歧度：多空比例差异越小，分歧越大
    # 共识度 = |看多比例 - 看空比例| / (看多比例 + 看空比例)
    # 最大值 = 1.0（全部看多 或 全部看空）
    # 最小值 = 0.0（多空各50%）
    if (bull_ratio + bear_ratio) > 0:
        raw_consensus = abs(bull_ratio - bear_ratio) / (bull_ratio + bear_ratio)
    else:
        raw_consensus = 0.0

    # 共识度 = 纯多空分歧度（只在有明确观点的推文中计算）
    # 最大值 = 1.0（有观点的人全部看多 或 全部看空）
    # 最小值 = 0.0（有观点的人多空各50%）
    # 观点密度是独立指标：有多少推文表达了明确观点
    # 两者不相乘 — "观点少"和"分歧大"是两回事
    # 例：100条里99条新闻+1条买入 → 共识度=100%，观点密度=1%
    consensus_score = raw_consensus

    # KOL 共识度（只看KOL的推文）
    kol_sents = [s for s in sentiments if s["is_kol"]]
    if kol_sents:
        kol_bull = sum(1 for s in kol_sents if s["direction"] == "bullish")
        kol_bear = sum(1 for s in kol_sents if s["direction"] == "bearish")
        kol_total = len(kol_sents)
        if (kol_bull + kol_bear) > 0:
            kol_consensus = abs(kol_bull - kol_bear) / (kol_bull + kol_bear)
        else:
            kol_consensus = 0.0
    else:
        kol_consensus = 0.0

    # KOL 加权情感分（KOL权重更高）
    kol_weight = 3.0  # KOL权重是普通的3倍
    total_weight = 0.0
    weighted_sum = 0.0
    for s in sentiments:
        w = kol_weight if s["is_kol"] else 1.0
        weighted_sum += s["score"] * w
        total_weight += w
    kol_weighted_sent = weighted_sum / total_weight if total_weight > 0 else 0.0

    # 互动量加权情感分
    total_eng = sum(s["engagement"] for s in sentiments)
    if total_eng > 0:
        eng_weighted = sum(s["score"] * s["engagement"] for s in sentiments) / total_eng
    else:
        eng_weighted = 0.0

    return {
        "consensus_score": round(consensus_score, 3),
        "opinion_density": round(opinion_density, 3),
        "kol_consensus": round(kol_consensus, 3),
        "bull_ratio": round(bull_ratio, 3),
        "bear_ratio": round(bear_ratio, 3),
        "neutral_ratio": round(neutral_ratio, 3),
        "kol_weighted_sentiment": round(kol_weighted_sent, 3),
        "engagement_weighted_sentiment": round(eng_weighted, 3),
        "bull_count": bull_count,
        "bear_count": bear_count,
        "neutral_count": neutral_count,
        "total_count": total,
    }


MIN_RELIABLE_SAMPLE = 5  # 低于这个数量的样本，情绪/共识度标记为不可靠


def calculate_signal_strength(
    mention_count: int,
    engagement: int,
    consensus: float,
    kol_mentions: int,
    total_tweets: int,
    sample_reliable: bool = True,
) -> float:
    """
    计算信号强度（0-100分）
    综合考虑：讨论热度、互动量、共识度、KOL参与度
    样本量不足时打折扣
    """
    # 热度分：讨论量占比
    heat_score = min(mention_count / max(total_tweets * 0.1, 1) * 40, 30)
    
    # 互动分（对数缩放）
    import math
    eng_score = min(math.log1p(max(engagement, 0)) / 3 * 25, 25)
    
    # 共识分
    cons_score = consensus * 25
    
    # KOL 分
    kol_score = min(kol_mentions * 5, 20)
    
    total = heat_score + eng_score + cons_score + kol_score

    # 样本量不足惩罚：最多扣 30 分
    if not sample_reliable:
        total = total * 0.6

    return round(min(total, 100), 1)


def generate_brief_v2(tweets: list[Tweet]) -> dict[str, Any]:
    """
    v2 版本：增加共识度、信号强度、KOL加权情感
    """
    if not tweets:
        return {"stats": {}, "assets": {}, "themes": {}, "top_tweets": [], "kol_tweets": []}

    # ── 基础统计 ──────────────────────────────────────────────────
    total_tweets = len(tweets)
    kol_tweets = [t for t in tweets if t.is_kol]
    total_likes = sum(t.likes for t in tweets)
    total_reposts = sum(t.reposts for t in tweets)
    total_replies = sum(t.replies for t in tweets)
    total_views = sum(getattr(t, "views", 0) for t in tweets)

    unique_authors = len(set(t.author for t in tweets))
    kol_count = len(set(t.author for t in kol_tweets))

    # ── 整体市场情绪 ──────────────────────────────────────────────
    overall_sentiment = calculate_consensus(tweets)

    # ── 标的统计（v2：带共识度）───────────────────────────────────
    asset_counter: Counter = Counter()
    asset_tweets: dict[str, list[Tweet]] = defaultdict(list)
    asset_engagement: dict[str, int] = defaultdict(int)

    for t in tweets:
        for sym, name in t.assets:
            key = f"{sym}|{name}"
            asset_counter[key] += 1
            asset_tweets[key].append(t)
            asset_engagement[key] += t.likes + t.reposts

    top_assets = []
    for key, count in asset_counter.most_common(15):
        sym, name = key.split("|", 1)
        tw_list = asset_tweets[key]
        eng = asset_engagement[key]
        kol_mentions = sum(1 for t in tw_list if t.is_kol)

        # 共识度分析
        consensus = calculate_consensus(tw_list)
        sample_reliable = count >= MIN_RELIABLE_SAMPLE

        # 信号强度
        signal_strength = calculate_signal_strength(
            count, eng, consensus["consensus_score"], kol_mentions, total_tweets,
            sample_reliable=sample_reliable,
        )

        # 数据不足标记
        reliability_flag = "数据不足" if not sample_reliable else "可靠"

        top_assets.append({
            "symbol": sym,
            "name": name,
            "mention_count": count,
            "engagement": eng,
            "kol_mentions": kol_mentions,
            "signal_strength": signal_strength,
            "consensus": consensus,
            "reliability": reliability_flag,
            "sample_reliable": sample_reliable,
            "sample_tweets": [
                {
                    "author": t.author,
                    "author_name": getattr(t, "author_name", t.author),
                    "content": t.content[:200],
                    "likes": t.likes,
                    "url": t.url,
                    "is_kol": t.is_kol,
                    "sentiment": calculate_sentiment_score(t.content or "")["direction"],
                }
                for t in sorted(tw_list, key=lambda x: x.likes, reverse=True)[:5]
            ],
        })

    # ── 主题统计（v2：带共识度 + 主题归属修正）───────────────
    theme_counter: Counter = Counter()
    theme_engagement: dict[str, int] = defaultdict(int)
    theme_tweets: dict[str, list[Tweet]] = defaultdict(list)

    # 主题归属修正：每条推文只分配给置信度最高的 TOP_N_THEMES 个主题
    # 避免一条推文的情绪被重复计算到多个主题（串扰问题）
    TOP_N_THEMES = 2  # 每条推文最多归属 2 个主题

    for t in tweets:
        # 只取前 N 个置信度最高的主题
        top_themes = t.themes[:TOP_N_THEMES]
        for theme in top_themes:
            theme_counter[theme] += 1
            theme_engagement[theme] += t.likes + t.reposts
            theme_tweets[theme].append(t)

    top_themes = []
    for theme, count in theme_counter.most_common(10):
        tw_list = theme_tweets[theme]
        consensus = calculate_consensus(tw_list)
        kol_mentions = sum(1 for t in tw_list if t.is_kol)

        sample_reliable = count >= MIN_RELIABLE_SAMPLE
        signal_strength = calculate_signal_strength(
            count, theme_engagement[theme], consensus["consensus_score"],
            kol_mentions, total_tweets,
            sample_reliable=sample_reliable,
        )
        reliability_flag = "数据不足" if not sample_reliable else "可靠"

        top_themes.append({
            "theme": theme,
            "tweet_count": count,
            "engagement": theme_engagement[theme],
            "kol_mentions": kol_mentions,
            "signal_strength": signal_strength,
            "consensus": consensus,
            "reliability": reliability_flag,
            "sample_reliable": sample_reliable,
            "top_tweets": [
                {
                    "author": t.author,
                    "author_name": getattr(t, "author_name", t.author),
                    "content": t.content[:150],
                    "likes": t.likes,
                    "url": t.url,
                    "is_kol": t.is_kol,
                    "sentiment": calculate_sentiment_score(t.content or "")["direction"],
                }
                for t in sorted(tw_list, key=lambda x: x.likes, reverse=True)[:3]
            ],
        })

    # ── Top 推文（按质量分）───────────────────────────────────────
    top_tweets = []
    for t in sorted(tweets, key=lambda x: x.quality_score, reverse=True)[:20]:
        sent = calculate_sentiment_score(t.content or "")
        top_tweets.append({
            "author": t.author,
            "author_name": getattr(t, "author_name", t.author),
            "content": t.content,
            "likes": t.likes,
            "reposts": t.reposts,
            "replies": t.replies,
            "views": getattr(t, "views", 0),
            "created_at": t.created_at,
            "url": t.url,
            "assets": [list(a) for a in t.assets],
            "themes": t.themes,
            "quality_score": t.quality_score,
            "is_kol": t.is_kol,
            "sentiment": sent["direction"],
            "sentiment_score": sent["score"],
            "sentiment_intensity": sent["intensity"],
        })

    # ── KOL 观点汇总 ──────────────────────────────────────────────
    kol_summary = []
    for t in sorted(kol_tweets, key=lambda x: x.likes, reverse=True)[:15]:
        sent = calculate_sentiment_score(t.content or "")
        kol_summary.append({
            "author": t.author,
            "author_name": getattr(t, "author_name", t.author),
            "content": t.content,
            "likes": t.likes,
            "url": t.url,
            "assets": [list(a) for a in t.assets],
            "themes": t.themes,
            "sentiment": sent["direction"],
            "sentiment_score": sent["score"],
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
            "total_views": total_views,
            "unique_assets": len(asset_counter),
            "unique_themes": len(theme_counter),
        },
        "overall_market_sentiment": overall_sentiment,
        "top_assets": top_assets,
        "top_themes": top_themes,
        "top_tweets": top_tweets,
        "kol_summary": kol_summary,
    }


# 兼容旧接口
def generate_brief(tweets: list[Tweet]) -> dict[str, Any]:
    return generate_brief_v2(tweets)
