"""
搜索关键词配置
"""
from __future__ import annotations


# 美股相关关键词
US_STOCK_QUERIES = [
    "stock market",
    "S&P 500",
    "NASDAQ",
    "AAPL stock",
    "TSLA stock",
    "NVDA stock",
    "MSFT stock",
    "earnings season",
    "tech stocks",
    "AI stocks",
    "semiconductor stocks",
    "fed rate decision",
]

# 中概股 / 港股 / A股
HK_CN_QUERIES = [
    "China stocks",
    "Hong Kong stocks",
    "BABA stock",
    "PDD stock",
    "港股",
    "A股",
    "中概股",
    "腾讯 股价",
    "阿里巴巴 股价",
]

# 宏观经济
MACRO_QUERIES = [
    "Federal Reserve",
    "interest rate",
    "inflation",
    "CPI report",
    "recession",
    "gold price",
    "oil price",
    "US dollar",
    "treasury yields",
    "VIX",
    "GDP",
    "nonfarm payroll",
]


def get_all_queries() -> list[str]:
    """获取所有搜索关键词"""
    return US_STOCK_QUERIES + HK_CN_QUERIES + MACRO_QUERIES


def get_kol_search_queries() -> list[str]:
    """KOL 相关搜索查询（从 KOL 名单生成）"""
    from .kol_list import get_all_kol_handles
    return [f"from:{handle}" for handle in get_all_kol_handles()[:10]]
