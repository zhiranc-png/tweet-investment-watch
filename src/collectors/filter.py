"""
投资内容过滤器 v2 — 增强版
从多源数据中筛选出与投资/财经/市场相关的内容
支持分级评分、排除规则、来源白名单
"""
from __future__ import annotations

import re
from typing import List, Tuple

from .multi_source_manager import UnifiedPost


# ── 强相关关键词（命中即判定为投资相关）────────────────────────────────
STRONG_INVESTMENT_KEYWORDS = [
    # 市场指数 & ETF
    "标普", "sp500", "s&p 500", "s&p500", "纳斯达克", "nasdaq", "道琼斯", "djia",
    "恒生指数", "hang seng", "上证指数", "沪指", "深成指", "创业板", "科创板",
    "qqq", "spy", "tqqq", "sqqq", "soxl", "soxs", "arkk", "gld", "tlt", "vxx",
    # 资产类别
    "美债", "国债", "收益率曲线", "yield curve", "债券", "treasury",
    "黄金", "gold", "白银", "silver", "铂金", "钯金",
    "原油", "oil", "wti", "brent", "opec", "天然气", "natural gas",
    "比特币", "bitcoin", "btc", "以太坊", "ethereum", "eth", "加密货币", "crypto",
    "美元指数", "dxy", "汇率", "外汇", "forex",
    # 宏观政策
    "美联储", "federal reserve", "fed", "鲍威尔", "powell", "耶伦", "yellen",
    "加息", "降息", "rate hike", "rate cut", "fomc", "议息",
    "通胀", "inflation", "cpi", "pce", "ppi", "通缩", "deflation",
    "非农", "nfp", "失业率", "unemployment", "gdp", "衰退", "recession",
    "软着陆", "soft landing", "硬着陆", "hard landing", "滞胀", "stagflation",
    "央行", "central bank", "货币政策", "monetary policy", "财政政策", "fiscal policy",
    "杰克逊霍尔", "jackson hole",
    # 财报 & 估值
    "财报", "earnings", "业绩", "营收", "revenue", "利润", "profit", "亏损", "loss",
    "eps", "市盈率", "pe ratio", "估值", "valuation", "回购", "buyback", "分红", "dividend",
    "ipo", "上市", "退市", "并购", "merger", "收购", "acquisition",
    # 投资术语
    "牛市", "bull market", "熊市", "bear market", "回调", "correction", "反弹", "rally",
    "抄底", "逃顶", "做多", "long", "做空", "short", "杠杆", "leverage",
    "波动率", "vix", "恐慌指数",
    "北向资金", "南向资金", "融资融券", "margin",
    "涨停", "跌停",
    # 行业术语
    "半导体", "semiconductor", "芯片", "chip", "算力", "computing power", "gpu",
    "人工智能", "artificial intelligence", "大模型", "llm", "ai chip",
    "新能源", "光伏", "储能", "电动车", "ev",
    "房地产", "楼市", "房价", "地产",
    "银行", "保险", "券商", "基金", "hedge fund", "对冲基金",
]

# ── 弱相关关键词（需结合上下文或多个命中才算）────────────────────────────
WEAK_INVESTMENT_KEYWORDS = [
    "stock", "shares", "equity", "market", "economy", "economic", "growth",
    "trade", "tariff", "sanction", "risk", "return", "portfolio", "asset",
    "fund", "index", "bond", "yield", "dollar", "yuan", "renminbi",
    "公司", "企业", "行业", "板块", "资金", "资本", "投资", "投资者",
    "上涨", "下跌", "涨", "跌", "新高", "新低",
    "ai", "nvidia", "nvda", "tesla", "tsla", "apple", "aapl", "microsoft", "msft",
    "google", "googl", "amazon", "amzn", "meta",
    "芯片", "科技股", "tech stock",
    "美股", "港股", "a股", "中概股", "chinese stocks",
]

# ── 排除关键词（命中则降低相关性评分）───────────────────────────────────
EXCLUDE_KEYWORDS = [
    # 娱乐/八卦
    "明星", "爱豆", "粉丝", "追星", "综艺", "电视剧", "电影", "选秀",
    "微博之夜", "吃瓜", "八卦", "恋情", "出轨", "离婚", "结婚",
    # 社会新闻（非财经类）
    "车祸", "命案", "凶杀", "强奸", "诈骗案", "失踪", "地震", "洪水",
    "美食", "旅游", "穿搭", "美妆", "健身", "宠物", "萌宠",
    # 政治（纯政治，不含经济政策）
    "选举辩论", "竞选", "投票率", "候选人提名", "党代表",
    # 其他
    "生日快乐", "祝福", "节日", "圣诞", "新年",
]

# ── 强排除模式（命中直接过滤，不管有没有投资关键词）──────────────────────
HARD_EXCLUDE_PATTERNS = [
    r"^rt @\w+:\s*(happy birthday|生日快乐)",
    r"^\s*🎉+\s*$",
    r"^\s*🎂+\s*$",
    r"giveaway.*free",
    r"free.*giveaway",
    r"airdrop.*crypto",
    r"join.*telegram",
]


def calculate_investment_score(text: str, source: str = "") -> Tuple[float, List[str]]:
    """
    计算投资相关性评分（0-100分）
    返回: (分数, 匹配到的强关键词列表)
    """
    text_lower = text.lower()
    score = 0.0
    matched_strong = []
    matched_weak = []
    matched_exclude = []

    # 强关键词：每个 +15 分
    for kw in STRONG_INVESTMENT_KEYWORDS:
        if kw.lower() in text_lower:
            matched_strong.append(kw)
            score += 15

    # 弱关键词：每个 +5 分（最多 +20 分）
    weak_count = 0
    for kw in WEAK_INVESTMENT_KEYWORDS:
        if kw.lower() in text_lower:
            matched_weak.append(kw)
            weak_count += 1
    score += min(weak_count * 5, 20)

    # 排除关键词：每个 -10 分
    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in text_lower:
            matched_exclude.append(kw)
            score -= 10

    # 硬排除模式：直接 0 分
    for pat in HARD_EXCLUDE_PATTERNS:
        if re.search(pat, text_lower):
            return 0.0, []

    # 来源加分：财经/科技类来源默认 +10 分基础分
    source_bonus = {
        "xueqiu": 10,
        "wallstreetcn": 15,
        "cls": 15,
        "hackernews": 5,
        "36kr": 5,
        "x": 0,
        "twitter": 0,
        "weibo": -5,
        "zhihu": -5,
    }
    score += source_bonus.get(source.lower(), 0)

    # 限制在 0-100 分
    score = max(0.0, min(100.0, score))

    return score, matched_strong


def is_investment_related(post: UnifiedPost, threshold: float = 20.0) -> bool:
    """
    判断帖子是否与投资相关
    threshold: 最低评分阈值（默认20分）
    """
    text = (post.title or "") + " " + (post.content or "")
    score, _ = calculate_investment_score(text, post.source)
    return score >= threshold


def is_tweet_investment_related(tweet_text: str, threshold: float = 15.0) -> bool:
    """
    判断推文是否与投资相关（适用于 X/Twitter 数据）
    推文通常较短，阈值稍低
    """
    score, _ = calculate_investment_score(tweet_text, "x")
    return score >= threshold


def filter_investment_posts(posts: List[UnifiedPost], threshold: float = 20.0) -> List[UnifiedPost]:
    """筛选投资相关帖子，按相关性评分降序排列"""
    scored = []
    for p in posts:
        text = (p.title or "") + " " + (p.content or "")
        score, matched = calculate_investment_score(text, p.source)
        if score >= threshold:
            scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored]


def get_matched_keywords(post: UnifiedPost) -> List[str]:
    """获取帖子匹配到的强投资关键词"""
    text = (post.title or "") + " " + (post.content or "")
    _, matched = calculate_investment_score(text, post.source)
    return matched
