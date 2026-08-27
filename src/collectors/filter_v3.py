"""
投资内容过滤器 v3 — 语义分类增强版

改进点：
1. 分类体系：按主题分类（不只是"是/否投资相关"）
2. 语义模式：增加短语级匹配，减少误判
3. 上下文感知：检查关键词周围的语境
4. 多维度评分：相关性 + 信息量 + 情绪强度
5. 资产识别增强：支持更多资产类别和别名
"""
from __future__ import annotations

import re
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class FilterResult:
    """过滤结果"""
    is_investment: bool
    score: float  # 0-100
    categories: List[str] = field(default_factory=list)  # 匹配到的主题分类
    matched_assets: List[tuple] = field(default_factory=list)  # (symbol, name)
    matched_keywords: List[str] = field(default_factory=list)
    sentiment_hint: str = "neutral"  # 初步情绪倾向
    info_density: float = 0.0  # 信息密度 0-1


# ── 主题分类词典 ────────────────────────────────────────────────
# 每个主题对应一组特征词，命中越多置信度越高
THEME_CATEGORIES = {
    "宏观_利率政策": {
        "keywords": [
            "美联储", "fed", "federal reserve", "鲍威尔", "powell", "耶伦", "yellen",
            "加息", "降息", "rate hike", "rate cut", "fomc", "议息",
            "通胀", "inflation", "cpi", "pce", "ppi", "通缩", "deflation",
            "非农", "nfp", "失业率", "unemployment", "gdp", "衰退", "recession",
            "软着陆", "soft landing", "硬着陆", "hard landing", "滞胀", "stagflation",
            "央行", "central bank", "货币政策", "monetary policy", "财政政策", "fiscal policy",
            "杰克逊霍尔", "jackson hole", "ecb", "欧洲央行", "boj", "日本央行",
            "pbo", "人民银行", "lpr", "mlf", "降准", "存款准备金",
        ],
        "weight": 2.0,
    },
    "美债_固定收益": {
        "keywords": [
            "美债", "国债", "收益率曲线", "yield curve", "债券", "treasury",
            "tlt", "ief", "shy", "tbf", "tbt", "tmv",
            "10年期", "10-year", "2年期", "2-year", "30年期", "30-year",
            "债券收益率", "bond yield", "收益率倒挂", "inverted yield",
            "久期", "duration", "信用利差", "credit spread",
            "高收益债", "high yield", "投资级", "investment grade",
            "债市", "bond market", "国债收益率",
        ],
        "weight": 2.0,
    },
    "黄金_贵金属": {
        "keywords": [
            "黄金", "gold", "白银", "silver", "铂金", "platinum", "钯金", "palladium",
            "gld", "slv", "iau", "gdx", "gold miner",
            "金价", "银价", "贵金属", "precious metal",
            "避险", "safe haven", "去美元化", "dedollarization",
            "黄金储备", "gold reserve", "央行购金",
        ],
        "weight": 2.0,
    },
    "原油_能源": {
        "keywords": [
            "原油", "oil", "wti", "brent", "opec", "opec+",
            "天然气", "natural gas", "lng", "石油", "油价",
            "xle", "uso", "usoil", "ukoil",
            "霍尔木兹", "hormuz", "石油禁运", "oil embargo",
            "能源危机", "energy crisis", "能源价格",
            "新能源", "光伏", "储能", "solar", "battery",
            "电动车", "ev", "tesla", "tsla", "比亚迪",
        ],
        "weight": 1.8,
    },
    "AI_科技": {
        "keywords": [
            "人工智能", "artificial intelligence", "大模型", "llm", "ai chip",
            "英伟达", "nvidia", "nvda", "amd", "台积电", "tsmc", "tsm",
            "半导体", "semiconductor", "芯片", "chip", "算力", "computing power", "gpu",
            "soxl", "soxx", "smh", "nvda", "amd",
            "meta", "microsoft", "msft", "google", "googl", "amazon", "amzn", "apple", "aapl",
            "ai capex", "数据中心", "data center", "云计算", "cloud computing",
            "科技股", "tech stock", "纳斯达克", "nasdaq", "qqq",
            "openai", "chatgpt", "claude", "gemini",
        ],
        "weight": 1.8,
    },
    "加密货币": {
        "keywords": [
            "比特币", "bitcoin", "btc", "以太坊", "ethereum", "eth",
            "加密货币", "crypto", "加密", "区块链", "blockchain",
            "solana", "sol", "cardano", "ada", "xrp", "ripple",
            "dogecoin", "doge", "shib", "pepe",
            "减半", "halving", "现货etf", "spot etf", "bitcoin etf",
            "币安", "binance", "coinbase", "coin",
            "链上", "on-chain", "defi", "nft",
        ],
        "weight": 2.0,
    },
    "美股_大盘": {
        "keywords": [
            "标普", "sp500", "s&p 500", "s&p500", "道琼斯", "djia",
            "spy", "qqq", "djia", "vix", "恐慌指数",
            "美股", "us stock", "us equities",
            "牛市", "bull market", "熊市", "bear market", "回调", "correction",
            "财报季", "earnings season",
            "magnificent seven", "mag7", "七巨头",
            "散户", "retail", "机构", "institutional",
            "对冲基金", "hedge fund", "共同基金", "mutual fund",
        ],
        "weight": 1.5,
    },
    "A股_港股": {
        "keywords": [
            "上证指数", "沪指", "深成指", "创业板", "科创板",
            "恒生指数", "hang seng", "恒生科技", "港股", "a股",
            "北向资金", "南向资金", "融资融券", "margin",
            "涨停", "跌停", "茅台", "宁德时代", "腾讯", "阿里巴巴", "baba",
            "中概股", "chinese stocks", "中概",
            "证监会", "金管局", "hkma",
            "港股通", "沪港通", "深港通",
        ],
        "weight": 1.8,
    },
    "外汇_汇率": {
        "keywords": [
            "美元指数", "dxy", "汇率", "外汇", "forex", "fx",
            "美元", "dollar", "人民币", "yuan", "renminbi", "cny",
            "日元", "yen", "jpy", "欧元", "euro", "eur",
            "英镑", "pound", "gbp", "瑞郎", "chf",
            "汇率政策", "汇率干预", "currency intervention",
            "去美元化", "dedollarization", "金砖", "brics",
        ],
        "weight": 1.5,
    },
    "地缘政治": {
        "keywords": [
            "地缘政治", "geopolitical", "战争", "war", "冲突", "conflict",
            "制裁", "sanction", "关税", "tariff", "贸易战", "trade war",
            "伊朗", "iran", "以色列", "israel", "加沙", "gaza",
            "乌克兰", "ukraine", "俄罗斯", "russia",
            "台海", "taiwan", "中东", "middle east",
            "霍尔木兹", "hormuz", "红海", "red sea",
            "选举", "election", "大选", "总统选举",
            "欧佩克", "opec", "opec+",
        ],
        "weight": 1.2,  # 地缘政治本身不算纯投资，但会影响市场
    },
    "公司_财报": {
        "keywords": [
            "财报", "earnings", "业绩", "营收", "revenue", "利润", "profit",
            "eps", "市盈率", "pe ratio", "估值", "valuation",
            "回购", "buyback", "分红", "dividend", "股息",
            "ipo", "上市", "退市", "并购", "merger", "收购", "acquisition",
            "业绩指引", "guidance", "超预期", "beat", "不及预期", "miss",
            "毛利率", "gross margin", "净利率", "net margin",
        ],
        "weight": 1.5,
    },
}

# ── 排除模式（v3：更精细）───────────────────────────────────────
EXCLUDE_CATEGORIES = {
    "娱乐八卦": [
        "明星", "爱豆", "粉丝", "追星", "综艺", "电视剧", "电影", "选秀",
        "微博之夜", "吃瓜", "八卦", "恋情", "出轨", "离婚", "结婚",
        "演唱会", "专辑", "新歌", "红毯", "时尚", "穿搭", "美妆",
    ],
    "社会民生": [
        "车祸", "命案", "凶杀", "强奸", "失踪", "地震", "洪水", "台风",
        "美食", "旅游", "健身", "宠物", "萌宠", "游戏", "电竞",
        "生日快乐", "祝福", "节日祝福", "圣诞快乐", "新年快乐",
    ],
    "纯政治": [
        "选举辩论", "竞选造势", "投票率", "候选人提名", "党代表大会",
        # 注意：涉及经济政策的政治内容不算排除
    ],
    "垃圾营销": [
        "giveaway", "airdrop", "free mint", "join our telegram",
        "click here", "sign up now", "limited offer",
        "抽奖", "转发抽奖", "关注抽奖", "福利", "薅羊毛",
    ],
}

# ── 资产别名映射（更全）─────────────────────────────────────────
ASSET_ALIASES = {
    # 美股科技
    "nvda": ("NVDA", "英伟达"),
    "nvidia": ("NVDA", "英伟达"),
    "aapl": ("AAPL", "苹果"),
    "apple": ("AAPL", "苹果"),
    "msft": ("MSFT", "微软"),
    "microsoft": ("MSFT", "微软"),
    "googl": ("GOOGL", "谷歌"),
    "google": ("GOOGL", "谷歌"),
    "amzn": ("AMZN", "亚马逊"),
    "amazon": ("AMZN", "亚马逊"),
    "meta": ("META", "Meta"),
    "facebook": ("META", "Meta"),
    "tsla": ("TSLA", "特斯拉"),
    "tesla": ("TSLA", "特斯拉"),
    "amd": ("AMD", "AMD"),
    "nvda": ("NVDA", "英伟达"),
    "tsm": ("TSM", "台积电"),
    "taiwan semiconductor": ("TSM", "台积电"),
    
    # ETF
    "spy": ("SPY", "标普500ETF"),
    "qqq": ("QQQ", "纳指100ETF"),
    "tqqq": ("TQQQ", "纳指三倍做多"),
    "sqqq": ("SQQQ", "纳指三倍做空"),
    "soxl": ("SOXL", "半导体三倍做多"),
    "soxs": ("SOXS", "半导体三倍做空"),
    "gld": ("GLD", "黄金ETF"),
    "slv": ("SLV", "白银ETF"),
    "tlt": ("TLT", "美债20年+ETF"),
    "ief": ("IEF", "美债7-10年ETF"),
    "vix": ("VIX", "恐慌指数"),
    "dxy": ("DXY", "美元指数"),
    "uso": ("USO", "原油ETF"),
    "xle": ("XLE", "能源ETF"),
    "arkk": ("ARKK", "方舟创新ETF"),
    
    # 加密
    "btc": ("BTC", "比特币"),
    "bitcoin": ("BTC", "比特币"),
    "eth": ("ETH", "以太坊"),
    "ethereum": ("ETH", "以太坊"),
    "sol": ("SOL", "Solana"),
    "solana": ("SOL", "Solana"),
    
    # 大宗商品
    "gold": ("XAU", "黄金"),
    "silver": ("XAG", "白银"),
    "wti": ("WTI", "WTI原油"),
    "brent": ("Brent", "布伦特原油"),
    
    # A股/港股
    "茅台": ("600519.SH", "贵州茅台"),
    "宁德时代": ("300750.SZ", "宁德时代"),
    "腾讯": ("0700.HK", "腾讯控股"),
    "阿里巴巴": ("BABA", "阿里巴巴"),
}

# 非交易标的排除列表（这些是机构/指标/术语，不是可交易的资产）
NON_TRADING_ASSETS = {
    # 机构/组织
    "fed", "federal reserve", "ecb", "boj", "pboc", "opec", "opec+",
    "美联储", "欧洲央行", "日本央行", "人民银行", "央行", "欧佩克",
    "imf", "world bank", "treasury", "财政部",
    # 经济指标（不是交易标的）
    "cpi", "ppi", "gdp", "nfp", "pce",
    "通胀", "通缩", "衰退", "滞胀",
    # 债券期限（不是独立标的，已通过 TLT/IEF 等 ETF 覆盖）
    "10y", "2y", "30y", "5y", "1y", "20y", "7y", "3m", "6m",
    "10年期", "2年期", "30年期", "5年期",
    # 其他术语
    "yield", "rate", "spread", "收益率", "利率", "利差",
    "ev",  # 电动车缩写太泛，容易误匹配
    "macro",  # 宏观缩写，不是标的
    "intl", "int",  # 国际/内部缩写
}

# 股票代码模式：$AAPL, $NVDA 等 cashtag
CASH_TAG_PATTERN = re.compile(r'\$([A-Z]{1,5})\b')


def classify_text(text: str) -> Dict[str, float]:
    """
    对文本进行多主题分类
    返回: {主题名: 置信度 0-1}
    """
    text_lower = text.lower()

    # 黄金比喻消歧：如果 "gold" 是比喻用法，不归类到黄金_贵金属
    gold_is_metaphor = _is_gold_rush_metaphor(text)

    scores = {}

    for category, config in THEME_CATEGORIES.items():
        keywords = config["keywords"]
        weight = config["weight"]
        matches = 0
        matched_words = []

        for kw in keywords:
            if kw.lower() in text_lower:
                # 黄金主题特殊处理：比喻用法跳过
                if category == "黄金_贵金属" and gold_is_metaphor:
                    continue
                matches += 1
                matched_words.append(kw)

        if matches > 0:
            # 置信度：命中词数 / 总词数的开方，再乘权重
            confidence = min(matches / (len(keywords) ** 0.4) * weight, 1.0)
            scores[category] = round(confidence, 3)

    return scores


def extract_assets(text: str) -> List[tuple]:
    """
    从文本中提取提到的资产
    返回: [(symbol, name), ...]
    """
    text_lower = text.lower()
    found = {}

    # 1. Cashtag 匹配 ($AAPL, $NVDA)
    for match in CASH_TAG_PATTERN.finditer(text):
        sym = match.group(1).upper()
        # 排除非交易标的（cashtag 形式的也要排除）
        if sym.lower() in NON_TRADING_ASSETS:
            continue
        found[sym] = (sym, sym)  # 先用 symbol 当名字

    # 2. 别名匹配（带上下文消歧）
    for alias, (sym, name) in ASSET_ALIASES.items():
        if alias in text_lower:
            # 排除非交易标的
            if sym.lower() in NON_TRADING_ASSETS:
                continue
            if alias.lower() in NON_TRADING_ASSETS:
                continue
            # ── 上下文消歧：避免 "AI gold rush" 被识别为黄金 ──
            if sym == "XAU" and _is_gold_rush_metaphor(text):
                continue
            if sym == "GLD" and _is_gold_rush_metaphor(text):
                continue
            found[sym] = (sym, name)

    return list(found.values())


# ── 黄金比喻消歧 ─────────────────────────────────────────────
# "AI gold rush"、"data is the new gold"、"voice is the new gold"
# 这些都是比喻用法，不是讨论黄金本身
_GOLD_RUSH_NON_METAL_PATTERNS = [
    r"ai\s+gold\s+rush",
    r"data\s+is\s+the\s+new\s+gold",
    r"voice\s+is\s+the\s+new\s+gold",
    r"attention\s+is\s+the\s+new\s+gold",
    r"content\s+is\s+the\s+new\s+gold",
    r"users\s+are\s+the\s+new\s+gold",
    r"gold\s+rush\s+(?:for|of|to)\s+(?:ai|tech|crypto|semiconductor)",
    r"goldmine", r"gold mine",
    r"淘金热",
    r"黄金时代",  # "AI 的黄金时代" 也不是讨论金价
    r"黄金赛道",  # 行业用词
    r"含金量",    # 形容词用法
]

_GOLD_RUSH_PATTERN = re.compile("|".join(_GOLD_RUSH_NON_METAL_PATTERNS), re.IGNORECASE)


def _is_gold_rush_metaphor(text: str) -> bool:
    """
    检测 "gold" 出现在比喻语境（不是讨论黄金价格/资产）
    """
    return bool(_GOLD_RUSH_PATTERN.search(text))



def check_exclusion(text: str) -> Tuple[bool, str]:
    """
    检查是否应该被排除
    返回: (是否排除, 排除原因)
    """
    text_lower = text.lower()
    
    # 硬排除模式
    hard_patterns = [
        r"^(rt\s+@\w+:\s*)?happy birthday",
        r"生日快乐",
        r"giveaway.*free|free.*giveaway",
        r"airdrop.*crypto|crypto.*airdrop",
        r"join.*telegram.*now",
        r"转发.*抽奖|关注.*抽奖",
    ]
    for pat in hard_patterns:
        if re.search(pat, text_lower):
            return True, "硬排除模式"
    
    # 分类排除：如果某个排除分类命中很多词，且没有投资相关词
    for cat_name, keywords in EXCLUDE_CATEGORIES.items():
        exclude_matches = sum(1 for kw in keywords if kw.lower() in text_lower)
        if exclude_matches >= 2:
            # 检查有没有投资关键词抵消
            invest_count = 0
            for cat_config in THEME_CATEGORIES.values():
                invest_count += sum(1 for kw in cat_config["keywords"] if kw.lower() in text_lower)
            if invest_count < exclude_matches:
                return True, f"排除分类: {cat_name}"
    
    return False, ""


def calculate_info_density(text: str) -> float:
    """
    计算信息密度（0-1）
    基于：长度、数字占比、专有名词数量
    """
    if not text:
        return 0.0
    
    # 长度分（100字以上满分）
    length_score = min(len(text) / 200, 1.0)
    
    # 数字/百分比/价格（信息含量高）
    numbers = re.findall(r'\d+(?:\.\d+)?%?', text)
    number_score = min(len(numbers) / 3, 1.0)
    
    # 链接数量（有来源的信息更可信）
    urls = re.findall(r'https?://', text)
    url_score = min(len(urls) * 0.3, 0.3)
    
    density = (length_score * 0.4 + number_score * 0.4 + url_score * 0.2)
    return round(density, 3)


def filter_and_classify(
    text: str,
    source: str = "",
    threshold: float = 25.0,
) -> FilterResult:
    """
    主函数：过滤 + 分类 + 资产提取
    
    返回 FilterResult，包含：
    - 是否投资相关
    - 综合评分
    - 匹配的主题分类
    - 提取的资产
    - 信息密度
    """
    if not text or not text.strip():
        return FilterResult(is_investment=False, score=0.0)
    
    text_lower = text.lower()
    
    # 1. 排除检查
    excluded, reason = check_exclusion(text)
    if excluded:
        return FilterResult(is_investment=False, score=0.0)
    
    # 2. 主题分类
    categories = classify_text(text)
    
    # 3. 资产提取
    assets = extract_assets(text)
    
    # 4. 计算综合评分
    if categories:
        # 取最高的 3 个分类分数加权
        top_cats = sorted(categories.values(), reverse=True)[:3]
        cat_score = sum(top_cats) / len(top_cats) * 70  # 最高 70 分
    else:
        cat_score = 0.0
    
    # 资产加分（提到具体标的说明更相关）
    asset_score = min(len(assets) * 5, 15)
    
    # 信息密度加分
    density = calculate_info_density(text)
    density_score = density * 15
    
    # 来源加权
    source_bonus = {
        "xueqiu": 5, "wallstreetcn": 10, "cls": 10,
        "hackernews": 3, "36kr": 3,
        "x": 0, "twitter": 0,
        "weibo": -5, "zhihu": -3,
    }
    source_score = source_bonus.get(source.lower(), 0)
    
    total_score = cat_score + asset_score + density_score + source_score
    total_score = max(0.0, min(100.0, total_score))
    
    # 5. 初步情绪判断（简单版）
    try:
        from .sentiment_v2 import calculate_sentiment_score
    except ImportError:
        from sentiment_v2 import calculate_sentiment_score
    sent = calculate_sentiment_score(text)
    sentiment_hint = sent["direction"]
    
    # 6. 匹配的关键词列表
    matched_kw = []
    for cat, config in THEME_CATEGORIES.items():
        for kw in config["keywords"]:
            if kw.lower() in text_lower:
                matched_kw.append(f"{cat}:{kw}")
    
    return FilterResult(
        is_investment=total_score >= threshold,
        score=round(total_score, 1),
        categories=sorted(categories.keys(), key=lambda c: categories[c], reverse=True),
        matched_assets=assets,
        matched_keywords=matched_kw[:10],
        sentiment_hint=sentiment_hint,
        info_density=density,
    )


# 兼容旧接口
def is_investment_related(text: str, source: str = "", threshold: float = 25.0) -> bool:
    result = filter_and_classify(text, source, threshold)
    return result.is_investment


def calculate_investment_score(text: str, source: str = "") -> Tuple[float, List[str]]:
    result = filter_and_classify(text, source)
    return result.score, result.matched_keywords
