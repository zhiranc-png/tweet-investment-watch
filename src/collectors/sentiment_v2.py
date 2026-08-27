"""
情感分析 v2 — 更丰富的词典 + 强度分级
支持中英文混合文本
"""

BULLISH_WORDS = {
    # 强看多（+2）
    "strong buy": 2, "conviction buy": 2, "all in": 2, "mooning": 2,
    "to the moon": 2, "parabolic": 2, "massive rally": 2, "blow off top": 2,
    "强烈看好": 2, "满仓": 2, "爆涨": 2, "暴涨": 2,
    "创历史新高": 2, "历史新高": 2, "屡创新高": 2,
    "大幅上涨": 2, "大幅攀升": 2, "飙升": 2,
    # 中等看多（+1.5）
    "bullish": 1.5, "buy the dip": 1.5, "accumulate": 1.5, "breakout": 1.5,
    "uptrend": 1.5, "outperform": 1.5, "overweight": 1.5,
    "看好": 1.5, "买入": 1.5, "做多": 1.5, "突破": 1.5, "加仓": 1.5,
    "抄底": 1.5, "低估": 1.5, "便宜": 1.5,
    "新高": 1.5, "上涨": 1.5, "攀升": 1.5, "走强": 1.5,
    "利好": 1.5, "利多": 1.5, "超预期": 1.5, "beat": 1.5,
    "反弹": 1.5, "回升": 1.5, "复苏": 1.5, "recovery": 1.5,
    # 弱看多（+1）
    "rally": 1, "surge": 1, "soar": 1, "jump": 1, "gain": 1,
    "rise": 1, "higher": 1, "rebound": 1,
    "涨": 1, "走牛": 1, "牛市": 1, "上行": 1,
    "上涨": 1, "走高": 1, "收涨": 1,
    "增持": 1, "买入评级": 1, "跑赢": 1,
}

BEARISH_WORDS = {
    # 强看空（-2）
    "crash": -2, "collapse": -2, "meltdown": -2, "bloodbath": -2,
    "capitulation": -2, "hard landing": -2, "depression": -2,
    "暴跌": -2, "崩盘": -2, "爆仓": -2, "清仓": -2, "熔断": -2,
    "创历史新低": -2, "历史新低": -2,
    "大幅下跌": -2, "大幅下挫": -2, "腰斩": -2,
    # 中等看空（-1.5）
    "bearish": -1.5, "short": -1.5, "sell": -1.5, "overvalued": -1.5,
    "bubble": -1.5, "downtrend": -1.5, "underweight": -1.5,
    "underperform": -1.5, "tanking": -1.5,
    "看空": -1.5, "卖出": -1.5, "做空": -1.5, "高估": -1.5,
    "泡沫": -1.5, "减持": -1.5, "抛售": -1.5,
    "下跌": -1.5, "走低": -1.5, "走弱": -1.5,
    "利空": -1.5, "不及预期": -1.5, "miss": -1.5,
    "回调": -1.5, "回落": -1.5, "走熊": -1.5, "熊市": -1.5,
    # 弱看空（-1）
    "drop": -1, "fall": -1, "decline": -1, "lower": -1, "dump": -1,
    "pullback": -1, "correction": -1, "sell-off": -1, "selloff": -1,
    "跌": -1, "下行": -1, "收跌": -1,
    "减持评级": -1, "跑输": -1, "下挫": -1,
}


def calculate_sentiment_score(text: str) -> dict:
    """计算单条文本的情感分数"""
    text_lower = text.lower()
    bull_score = 0.0
    bear_score = 0.0
    bull_matched = []
    bear_matched = []

    for word, weight in BULLISH_WORDS.items():
        if word.lower() in text_lower:
            bull_score += weight
            bull_matched.append(word)

    for word, weight in BEARISH_WORDS.items():
        if word.lower() in text_lower:
            bear_score += abs(weight)
            bear_matched.append(word)

    total = bull_score + bear_score
    if total == 0:
        return {"score": 0.0, "direction": "neutral", "intensity": 0.0,
                "bullish_words": [], "bearish_words": []}

    net = (bull_score - bear_score) / total
    intensity = min(total / 3.0, 1.0)

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
