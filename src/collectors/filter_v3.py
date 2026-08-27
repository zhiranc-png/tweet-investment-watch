"""
投资内容过滤器 v3 — 语义分类版
从多源数据中筛选投资相关内容，并自动分类到 11 个主题 + 提取资产

相比 v2 的改进：
1. 从"是/否投资相关"升级为"11 个主题分类"
2. 每个主题有独立关键词词典和权重
3. 增强资产提取（支持 $cashtag + 50+ 别名映射）
4. 输出信息密度评分
5. 初步情绪倾向判断
"""
from __future__ import annotations

import re
from typing import List, Tuple, Optional


# ═══════════════════════════════════════════════════════════════
# 11 个主题分类 + 关键词词典
# ═══════════════════════════════════════════════════════════════

THEME_KEYWORDS = {
    "美债_固定收益": {
        "weight": 1.2,
        "strong": [
            "美债", "国债", "treasury", "tlt", "tlh", "ief", "shy",
            "收益率曲线", "yield curve", "长端利率", "短端利率",
            "债券收益率", "bond yield", "债市", "bond market",
            "久期", "duration", "息差", "spread", "信用债", "credit",
            "利率债", "固收", "fixed income", "debt ceiling", "债务上限",
            "bessent", "债王", "gundlach", "jeff gundlach", "danielle dimartino",
            "jim grant", "grants interest rate",
        ],
        "weak": [
            "yield", "treasuries", "bonds", "bond", "rates", "rate",
            "coupon", "maturity", "default",
        ],
    },
    "黄金_贵金属": {
        "weight": 1.1,
        "strong": [
            "黄金", "gold", "金价", "gold price", "bullion",
            "白银", "silver", "铂金", "platinum", "钯金", "palladium",
            "gld", "slv", "贵金属", "precious metal",
            "黄金储备", "gold reserve", "金本位", "gold standard",
            "黄金重估", "gold revaluation", "世界黄金协会", "gold council",
            "lyn alden", "luke gromen",
        ],
        "weak": [
            "xau", "xag", "金饰", "金币", "金条", "mining", "金矿",
        ],
    },
    "原油_能源": {
        "weight": 1.0,
        "strong": [
            "原油", "oil", "wti", "brent", "油价", "oil price",
            "opec", "opec+", "欧佩克", "减产", "production cut",
            "天然气", "natural gas", "lng", "煤炭", "coal",
            "能源危机", "energy crisis", "战略石油储备", "spr",
            "霍尔木兹", "hormuz", "马六甲", "malacca",
            "eia", "iea",
        ],
        "weak": [
            "energy", "石油", "gas", "fuel", "汽油", "柴油",
            "pipeline", "管道", "炼油", "refinery",
        ],
    },
    "宏观_利率政策": {
        "weight": 1.2,
        "strong": [
            "美联储", "federal reserve", "fed", "鲍威尔", "powell",
            "加息", "降息", "rate hike", "rate cut", "fomc", "议息",
            "通胀", "inflation", "cpi", "pce", "ppi", "通缩", "deflation",
            "非农", "nfp", "失业率", "unemployment", "gdp", "衰退", "recession",
            "软着陆", "soft landing", "硬着陆", "hard landing", "滞胀", "stagflation",
            "央行", "central bank", "货币政策", "monetary policy", "财政政策", "fiscal policy",
            "杰克逊霍尔", "jackson hole", "点阵图", "dot plot",
            "财政赤字", "deficit", "债务", "debt", "财政主导", "fiscal dominance",
        ],
        "weak": [
            "economy", "economic", "growth", "employment", "jobs",
            "宏观", "macro", "经济", "物价", "就业",
        ],
    },
    "AI_科技": {
        "weight": 1.0,
        "strong": [
            "人工智能", "artificial intelligence", "大模型", "llm", "ai chip",
            "算力", "computing power", "gpu", "半导体", "semiconductor", "芯片",
            "英伟达", "nvidia", "nvda", "台积电", "tsmc", "asml",
            "ai capex", "资本开支", "capex",
            "agent", "智能体", "多模态", "multimodal",
            "openai", "chatgpt", "gpt", "claude", "gemini",
        ],
        "weak": [
            "tech", "technology", "科技", "软件", "software",
            "硬件", "hardware", "数据中心", "data center",
            "cloud", "云", "aws", "azure",
        ],
    },
    "加密货币": {
        "weight": 1.0,
        "strong": [
            "比特币", "bitcoin", "btc", "以太坊", "ethereum", "eth",
            "加密货币", "crypto", "加密", "区块链", "blockchain",
            "solana", "sol", "币安", "binance", "coinbase",
            "减半", "halving", "现货etf", "spot etf",
            "链上", "on-chain", "defi", "nft",
            "saylor", "michael saylor", "microstrategy",
        ],
        "weak": [
            "coin", "token", "wallet", "交易所", "exchange",
            "挖矿", "mining", "公链", "layer2",
        ],
    },
    "美股_大盘": {
        "weight": 0.9,
        "strong": [
            "标普", "sp500", "s&p 500", "s&p500", "纳斯达克", "nasdaq",
            "道琼斯", "djia", "qqq", "spy", "tqqq", "sqqq",
            "美股", "us stocks", "us equities",
            "牛市", "bull market", "熊市", "bear market",
            "回调", "correction", "反弹", "rally",
            "波动率", "vix", "恐慌指数",
        ],
        "weak": [
            "stock", "stocks", "equity", "equities", "market",
            "index", "indices", "大盘", "指数",
        ],
    },
    "A股_港股": {
        "weight": 0.9,
        "strong": [
            "恒生指数", "hang seng", "上证指数", "沪指", "深成指",
            "创业板", "科创板", "港股", "a股", "中概股", "chinese stocks",
            "北向资金", "南向资金", "融资融券", "margin",
            "涨停", "跌停", "证监会", "csrc",
            "港股通", "沪港通", "深港通",
        ],
        "weak": [
            "中国经济", "china economy", "中国市场", "china market",
            "地产", "房地产", "楼市", "房价",
        ],
    },
    "外汇_汇率": {
        "weight": 0.9,
        "strong": [
            "美元指数", "dxy", "汇率", "外汇", "forex", "fx",
            "美元", "dollar", "usd", "人民币", "yuan", "renminbi", "cny",
            "欧元", "euro", "eur", "日元", "yen", "jpy",
            "英镑", "pound", "gbp", "瑞郎", "chf",
            "汇率政策", "exchange rate", "货币贬值", "devaluation",
            "货币升值", "appreciation", "外汇储备",
            "去美元化", "dedollarization", "美元霸权",
        ],
        "weak": [
            "currency", "货币", "汇率制度", "固定汇率", "浮动汇率",
        ],
    },
    "地缘政治": {
        "weight": 0.8,
        "strong": [
            "地缘政治", "geopolitical", "地缘风险", "geopolitical risk",
            "战争", "war", "冲突", "conflict", "制裁", "sanction",
            "关税", "tariff", "贸易战", "trade war",
            "中东", "middle east", "伊朗", "iran", "以色列", "israel",
            "俄乌", "russia", "ukraine", "台海", "taiwan",
            "北约", "nato", "金砖", "brics", "g7", "g20",
            "选举", "election", "大选", "总统选举",
        ],
        "weak": [
            "政治", "political", "外交", "diplomatic",
            "国际", "international", "全球秩序", "global order",
        ],
    },
    "公司_财报": {
        "weight": 0.8,
        "strong": [
            "财报", "earnings", "业绩", "营收", "revenue", "利润", "profit",
            "亏损", "loss", "eps", "市盈率", "pe ratio",
            "估值", "valuation", "回购", "buyback", "分红", "dividend",
            "ipo", "上市", "退市", "并购", "merger", "收购", "acquisition",
            "季报", "年报", "q1", "q2", "q3", "q4",
            "guidance", "指引", "业绩指引",
        ],
        "weak": [
            "公司", "company", "企业", "corporate", "行业", "industry",
            "板块", "sector", "财报季", "earnings season",
        ],
    },
}


# ═══════════════════════════════════════════════════════════════
# 资产别名映射（符号 → 标准名 + 类型）
# ═══════════════════════════════════════════════════════════════

ASSET_ALIASES = {
    # 美股大盘 ETF
    "spy": ("SPY", "美股_ETF"), "spx": ("SPX", "美股_指数"), "sp500": ("S&P 500", "美股_指数"),
    "qqq": ("QQQ", "美股_ETF"), "ndx": ("NDX", "美股_指数"), "nasdaq": ("纳斯达克", "美股_指数"),
    "djia": ("道琼斯", "美股_指数"), "dia": ("DIA", "美股_ETF"),
    "iwm": ("IWM", "美股_ETF"), "vti": ("VTI", "美股_ETF"),
    "vix": ("VIX", "波动率"),

    # 美债 ETF
    "tlt": ("TLT", "美债_ETF"), "tlh": ("TLH", "美债_ETF"),
    "ief": ("IEF", "美债_ETF"), "shy": ("SHY", "美债_ETF"),
    "gld": ("GLD", "黄金_ETF"), "slv": ("SLV", "白银_ETF"),

    # 科技股
    "nvda": ("NVDA", "美股_科技"), "nvidia": ("NVDA", "美股_科技"),
    "aapl": ("AAPL", "美股_科技"), "apple": ("AAPL", "美股_科技"),
    "msft": ("MSFT", "美股_科技"), "microsoft": ("MSFT", "美股_科技"),
    "googl": ("GOOGL", "美股_科技"), "google": ("GOOGL", "美股_科技"),
    "amzn": ("AMZN", "美股_科技"), "amazon": ("AMZN", "美股_科技"),
    "meta": ("META", "美股_科技"), "facebook": ("META", "美股_科技"),
    "tsla": ("TSLA", "美股_科技"), "tesla": ("TSLA", "美股_科技"),
    "tsmc": ("TSMC", "美股_科技"), "台积电": ("TSMC", "美股_科技"),
    "asml": ("ASML", "美股_科技"),
    "amd": ("AMD", "美股_科技"),

    # 加密货币
    "btc": ("BTC", "加密货币"), "bitcoin": ("BTC", "加密货币"),
    "eth": ("ETH", "加密货币"), "ethereum": ("ETH", "加密货币"),
    "sol": ("SOL", "加密货币"), "solana": ("SOL", "加密货币"),

    # 外汇
    "dxy": ("DXY", "外汇"), "美元指数": ("DXY", "外汇"),
    "usd": ("USD", "外汇"), "cny": ("CNY", "外汇"), "人民币": ("CNY", "外汇"),
    "eur": ("EUR", "外汇"), "jpy": ("JPY", "外汇"), "日元": ("JPY", "外汇"),
    "gbp": ("GBP", "外汇"), "chf": ("CHF", "外汇"),

    # 大宗商品
    "wti": ("WTI原油", "大宗商品"), "brent": ("布伦特原油", "大宗商品"),
    "原油": ("WTI原油", "大宗商品"), "oil": ("WTI原油", "大宗商品"),
    "gold": ("黄金", "贵金属"), "黄金": ("黄金", "贵金属"),
    "silver": ("白银", "贵金属"), "白银": ("白银", "贵金属"),
    "天然气": ("天然气", "大宗商品"), "natural gas": ("天然气", "大宗商品"),

    # A股/港股指数
    "上证指数": ("上证指数", "A股_指数"), "沪指": ("上证指数", "A股_指数"),
    "深成指": ("深证成指", "A股_指数"),
    "创业板": ("创业板指", "A股_指数"),
    "恒生指数": ("恒生指数", "港股_指数"), "hang seng": ("恒生指数", "港股_指数"),
}


# ═══════════════════════════════════════════════════════════════
# 排除关键词（降低评分）
# ═══════════════════════════════════════════════════════════════

EXCLUDE_KEYWORDS = [
    "明星", "爱豆", "粉丝", "追星", "综艺", "电视剧", "电影", "选秀",
    "微博之夜", "吃瓜", "八卦", "恋情", "出轨", "离婚", "结婚",
    "车祸", "命案", "凶杀", "强奸", "诈骗案", "失踪",
    "美食", "旅游", "穿搭", "美妆", "健身", "宠物", "萌宠",
    "生日快乐", "祝福", "圣诞", "新年", "节日",
    "抽奖", "giveaway", "空投", "airdrop",
]

HARD_EXCLUDE_PATTERNS = [
    r"happy birthday",
    r"生日快乐",
    r"merry christmas",
    r"新年快乐",
    r"抽奖.*关注",
    r"关注.*抽奖",
    r"giveaway",
]


# ═══════════════════════════════════════════════════════════════
# 情感关键词词典（用于初步情感判断）
# ═══════════════════════════════════════════════════════════════

BULLISH_KEYWORDS = [
    "bullish", "看多", "看涨", "买入", "buy", "long", "做多",
    "上涨", "涨", "新高", "突破", "surge", "rally", "soar", "jump",
    "利好", "positive", "optimistic", "乐观",
    "超预期", "beat", "exceed", "strong", "强劲",
    "复苏", "recovery", "rebound", "反弹",
]

BEARISH_KEYWORDS = [
    "bearish", "看空", "看跌", "卖出", "sell", "short", "做空",
    "下跌", "跌", "新低", "破位", "crash", "plunge", "drop", "tumble",
    "利空", "negative", "pessimistic", "悲观",
    "不及预期", "miss", "weak", "疲软", "下滑",
    "衰退", "recession", "危机", "crisis", "崩盘",
    "风险", "risk", "警告", "warning", "担忧", "concern",
]


# ═══════════════════════════════════════════════════════════════
# 核心函数
# ═══════════════════════════════════════════════════════════════

def classify_and_score(text: str) -> dict:
    """
    对文本进行主题分类 + 投资相关性评分 + 资产提取 + 情绪判断

    返回:
    {
        "is_investment_related": bool,
        "investment_score": float,  # 0-100
        "themes": [{"theme": str, "score": float, "confidence": str}],
        "assets": [(symbol, asset_type), ...],
        "sentiment": "bullish" | "bearish" | "neutral",
        "sentiment_score": float,  # -1 到 1
        "info_density": float,  # 信息密度 0-1
    }
    """
    text_lower = text.lower()
    result = {
        "is_investment_related": False,
        "investment_score": 0.0,
        "themes": [],
        "assets": [],
        "sentiment": "neutral",
        "sentiment_score": 0.0,
        "info_density": 0.0,
    }

    # ── 硬排除 ────────────────────────────────────────────────
    for pattern in HARD_EXCLUDE_PATTERNS:
        if re.search(pattern, text_lower):
            return result

    # ── 主题分类 + 评分 ───────────────────────────────────────
    theme_scores = {}
    for theme, config in THEME_KEYWORDS.items():
        score = 0.0
        matched_strong = []
        matched_weak = []

        for kw in config["strong"]:
            count = text_lower.count(kw.lower())
            if count > 0:
                score += count * 15 * config["weight"]
                matched_strong.append(kw)

        for kw in config["weak"]:
            count = text_lower.count(kw.lower())
            if count > 0:
                score += count * 5 * config["weight"]
                matched_weak.append(kw)

        if score > 0:
            # 限制弱关键词贡献上限
            weak_score = len(matched_weak) * 5 * config["weight"]
            if weak_score > score * 0.4:
                score = score - weak_score + score * 0.4
            theme_scores[theme] = {
                "score": round(score, 1),
                "matched_strong": matched_strong,
                "matched_weak": matched_weak,
            }

    # ── 排除关键词扣分 ────────────────────────────────────────
    exclude_hits = sum(1 for kw in EXCLUDE_KEYWORDS if kw.lower() in text_lower)
    exclude_penalty = exclude_hits * 10

    # ── 总投资相关性评分 ──────────────────────────────────────
    if theme_scores:
        # 取最高主题分 + 其他主题的 30% 加权
        sorted_themes = sorted(theme_scores.items(), key=lambda x: x[1]["score"], reverse=True)
        top_score = sorted_themes[0][1]["score"]
        other_score = sum(t[1]["score"] for t in sorted_themes[1:]) * 0.3
        total_score = top_score + other_score - exclude_penalty

        # 长度加成（太短的内容信息量低）
        length = len(text)
        if length < 50:
            total_score *= 0.6
        elif length < 100:
            total_score *= 0.8
        elif length > 500:
            total_score *= 1.1  # 长文加成

        # 数字/数据含量加成
        num_count = len(re.findall(r'\d+\.?\d*%?', text))
        if num_count >= 3:
            total_score *= 1.15

        result["investment_score"] = max(0.0, min(100.0, round(total_score, 1)))
        result["is_investment_related"] = result["investment_score"] >= 15

        # 整理主题列表
        for theme, data in sorted_themes:
            confidence = "high" if data["score"] >= 30 else "medium" if data["score"] >= 15 else "low"
            if data["score"] >= 10:
                result["themes"].append({
                    "theme": theme,
                    "score": data["score"],
                    "confidence": confidence,
                })

    # ── 资产提取 ──────────────────────────────────────────────
    assets = extract_assets(text)
    result["assets"] = assets

    # ── 情绪判断 ──────────────────────────────────────────────
    bullish_hits = sum(text_lower.count(kw.lower()) for kw in BULLISH_KEYWORDS)
    bearish_hits = sum(text_lower.count(kw.lower()) for kw in BEARISH_KEYWORDS)
    total_sentiment_hits = bullish_hits + bearish_hits

    if total_sentiment_hits > 0:
        sentiment_score = (bullish_hits - bearish_hits) / total_sentiment_hits
        result["sentiment_score"] = round(sentiment_score, 2)
        if sentiment_score > 0.3:
            result["sentiment"] = "bullish"
        elif sentiment_score < -0.3:
            result["sentiment"] = "bearish"
        else:
            result["sentiment"] = "neutral"

    # ── 信息密度 ──────────────────────────────────────────────
    word_count = len(text.split())
    unique_words = len(set(text.lower().split()))
    diversity = unique_words / max(word_count, 1)
    number_density = num_count / max(word_count, 1) * 10
    result["info_density"] = round(min(1.0, diversity * 0.5 + number_density * 0.5), 2)

    return result


def extract_assets(text: str) -> List[Tuple[str, str]]:
    """从文本中提取资产符号"""
    text_lower = text.lower()
    found = {}

    # 1. $cashtag 格式
    cashtags = re.findall(r'\$([a-zA-Z]{1,5})', text)
    for tag in cashtags:
        tag_lower = tag.lower()
        if tag_lower in ASSET_ALIASES:
            sym, atype = ASSET_ALIASES[tag_lower]
            found[sym] = atype
        else:
            found[tag.upper()] = "股票_未知"

    # 2. 别名匹配
    for alias, (symbol, atype) in ASSET_ALIASES.items():
        if alias in text_lower:
            found[symbol] = atype

    return list(found.items())


def filter_tweets(tweets: list, min_score: float = 25.0) -> list:
    """
    过滤推文列表，只保留投资相关的，并附上分类结果

    返回: list of (tweet_dict, classification_result)
    """
    filtered = []
    for tweet in tweets:
        text = tweet.get("text", "") or tweet.get("content", "")
        cls = classify_and_score(text)
        if cls["is_investment_related"] and cls["investment_score"] >= min_score:
            # 把分类结果注入 tweet
            enriched = dict(tweet)
            enriched["themes"] = [t["theme"] for t in cls["themes"]]
            enriched["theme_details"] = cls["themes"]
            enriched["assets"] = cls["assets"]
            enriched["investment_score"] = cls["investment_score"]
            enriched["sentiment"] = cls["sentiment"]
            enriched["sentiment_score"] = cls["sentiment_score"]
            enriched["info_density"] = cls["info_density"]
            filtered.append((enriched, cls))
    return filtered


def get_theme_list() -> list:
    """返回所有主题名称列表"""
    return list(THEME_KEYWORDS.keys())


if __name__ == "__main__":
    # 快速测试
    test_texts = [
        "Fed 主席鲍威尔暗示可能再次加息，美债收益率飙升，TLT 暴跌 2%",
        "黄金价格突破 2500 美元，GLD 创历史新高，央行持续增持",
        "英伟达 NVDA 财报超预期，AI capex 继续增长",
        "生日快乐！今天天气真好",
        "伊朗袭击以色列，油价暴涨，地缘风险升级",
        "BTC 突破 7 万，MicroStrategy 继续加仓",
    ]
    for i, text in enumerate(test_texts, 1):
        result = classify_and_score(text)
        print(f"\n[{i}] {text[:50]}...")
        print(f"  投资相关: {result['is_investment_related']}")
        print(f"  评分: {result['investment_score']}")
        print(f"  主题: {[t['theme'] for t in result['themes'][:3]]}")
        print(f"  资产: {result['assets']}")
        print(f"  情绪: {result['sentiment']} ({result['sentiment_score']})")
        print(f"  信息密度: {result['info_density']}")
