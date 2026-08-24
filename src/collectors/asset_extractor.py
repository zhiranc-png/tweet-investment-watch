"""
标的与主题提取
"""
from __future__ import annotations

import re
from typing import Tuple


# ── 美股标的 ────────────────────────────────────────────────────────────────
US_STOCKS = {
    # 科技巨头
    "AAPL": "苹果", "MSFT": "微软", "GOOGL": "谷歌", "GOOG": "谷歌",
    "AMZN": "亚马逊", "META": "Meta", "NVDA": "英伟达", "TSLA": "特斯拉",
    "NFLX": "奈飞", "AMD": "AMD", "INTC": "英特尔", "ORCL": "甲骨文",
    "CRM": "Salesforce", "ADBE": "Adobe", "PYPL": "PayPal",
    # 中概股
    "BABA": "阿里巴巴", "PDD": "拼多多", "JD": "京东", "BIDU": "百度",
    "NIO": "蔚来", "LI": "理想", "XPEV": "小鹏", "TME": "腾讯音乐",
    "BILI": "B站", "DIDI": "滴滴", "YMM": "满帮", "DOYU": "斗鱼",
    "HUYA": "虎牙", "VIPS": "唯品会", "BEKE": "贝壳",
    # ETF
    "QQQ": "纳指100", "SPY": "标普500", "DIA": "道琼斯", "IWM": "罗素2000",
    "ARKK": "ARK创新", "TLT": "美债20+", "GLD": "黄金ETF", "USO": "原油ETF",
    "VXX": "波动率", "UVXY": "两倍做多VIX", "SQQQ": "三倍做空纳指",
    "TQQQ": "三倍做多纳指", "SOXL": "三倍做多半导体",
    # 半导体
    "AVGO": "博通", "QCOM": "高通", "TXN": "德州仪器", "MU": "美光",
    "ARM": "ARM", "TSM": "台积电", "ASML": "阿斯麦",
}

# ── 港股/A股标的（常见） ────────────────────────────────────────────────────
HK_CN_STOCKS = {
    "0700.HK": "腾讯", "9988.HK": "阿里", "3690.HK": "美团",
    "1810.HK": "小米", "9618.HK": "京东", "9888.HK": "百度",
    "9999.HK": "网易", "0981.HK": "中芯国际", "1347.HK": "华虹半导体",
    "2318.HK": "平安", "0941.HK": "中国移动", "0883.HK": "中海油",
}

# ── 宏观资产 ────────────────────────────────────────────────────────────────
MACRO_ASSETS = {
    "BTC": "比特币", "ETH": "以太坊", "GOLD": "黄金", "SILVER": "白银",
    "OIL": "原油", "WTI": "WTI原油", "BRENT": "布伦特原油",
    "DXY": "美元指数", "USD": "美元", "CNY": "人民币", "EUR": "欧元",
    "JPY": "日元", "GBP": "英镑",
    "10Y": "10年期美债", "2Y": "2年期美债", "30Y": "30年期美债",
    "FED": "美联储", "POWELL": "鲍威尔",
    "CPI": "CPI", "PPI": "PPI", "NFP": "非农",
    "VIX": "VIX恐慌指数",
}

# ── 主题关键词 ──────────────────────────────────────────────────────────────
THEME_KEYWORDS = {
    "AI/人工智能": [
        r"\bai\b", r"artificial intelligence", r"大模型", r"llm", r"gpt",
        r"chatgpt", r"claude", r"gemini", r"deepseek", r"豆包", r"文心",
        r"通义", r"智谱", r"copilot", r"agent", r"agi", r"机器学习",
        r"深度学习", r"神经网络", r"transformer",
    ],
    "降息/加息": [
        r"降息", r"加息", r"rate cut", r"rate hike", r"fed rate",
        r"联邦基金利率", r"点阵图", r"hawkish", r"dovish", r"鸽派", r"鹰派",
        r"fomc", r"美联储", r"powell", r"鲍威尔",
    ],
    "科技股": [
        r"tech", r"科技", r"半导体", r"semiconductor", r"chip",
        r"芯片", r"ai chip", r"算力", r"computing", r"gpu",
    ],
    "中概股": [
        r"中概", r"chinese stock", r"中概股", r"港股", r"hong kong stock",
        r"a股", r"china market", r"中国经济",
    ],
    "黄金/贵金属": [
        r"gold", r"黄金", r"silver", r"白银", r"贵金属",
        r"precious metal", r"避险", r"safe haven",
    ],
    "原油/能源": [
        r"oil", r"原油", r"opec", r"能源", r"energy",
        r"brent", r"wti", r"天然气", r"natural gas",
    ],
    "加密货币": [
        r"bitcoin", r"比特币", r"ethereum", r"以太坊", r"crypto",
        r"加密", r"btc", r"eth", r"sol", r"山寨币", r"altcoin",
        r"defi", r"nft", r"meme",
    ],
    "宏观经济": [
        r"recession", r"衰退", r"inflation", r"通胀", r"deflation", r"通缩",
        r"gdp", r"就业", r"unemployment", r"非农", r"nfp",
        r"cpi", r"ppi", r"经济数据", r"软着陆", r"hard landing",
    ],
    "地缘政治": [
        r"war", r"战争", r"制裁", r"sanction", r"关税", r"tariff",
        r"贸易战", r"trade war", r"地缘", r"geopolitical",
        r"大选", r"election", r"trump", r"biden",
    ],
}


def extract_assets(text: str) -> list[tuple[str, str]]:
    """从文本中提取标的"""
    assets = []
    seen = set()

    # $符号标的 如 $AAPL
    for m in re.finditer(r"\$([A-Z]{2,6}\.?[A-Z]?)\b", text):
        sym = m.group(1).upper()
        if sym in US_STOCKS and sym not in seen:
            assets.append((sym, US_STOCKS[sym]))
            seen.add(sym)

    # 关键词匹配
    all_assets = {**US_STOCKS, **HK_CN_STOCKS, **MACRO_ASSETS}
    for sym, name in all_assets.items():
        if sym in seen:
            continue
        # 匹配 $SYM 或 独立出现的大写缩写
        pattern = r"(?:^|\W)" + re.escape(sym) + r"(?:$|\W)"
        if re.search(pattern, text, re.I):
            # 额外检查：短缩写容易误匹配，需要上下文验证
            if len(sym) <= 3:
                # 3字母及以下需要金融上下文
                context_keywords = [
                    "stock", "price", "涨", "跌", "buy", "sell",
                    "hold", "target", "earnings", "财报", "股价",
                    "etf", "index", "指数",
                ]
                if not any(kw in text.lower() for kw in context_keywords):
                    continue
            assets.append((sym, name))
            seen.add(sym)

    return assets[:5]  # 最多5个


def extract_themes(text: str) -> list[str]:
    """从文本中提取主题"""
    themes = []
    text_lower = text.lower()
    for theme, patterns in THEME_KEYWORDS.items():
        for pat in patterns:
            if re.search(pat, text_lower):
                themes.append(theme)
                break
    return themes
