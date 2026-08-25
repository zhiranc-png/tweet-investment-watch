"""
搜索关键词配置 — 美股 / A股港股 / 宏观 三大领域
用于 X/Twitter 搜索补充 KOL 之外的热点内容
"""

# ── 美股关键词 ──────────────────────────────────────────────────────────────
US_STOCK_QUERIES: list[str] = [
    # 大盘指数
    "SPY OR S&P 500 min_faves:100",
    "QQQ OR Nasdaq min_faves:100",
    "DOW OR Dow Jones min_faves:80",
    # 科技股七巨头
    "AAPL OR Apple min_faves:200",
    "MSFT OR Microsoft min_faves:200",
    "NVDA OR Nvidia min_faves:300",
    "GOOGL OR Google min_faves:150",
    "AMZN OR Amazon min_faves:150",
    "META OR Facebook min_faves:150",
    "TSLA OR Tesla min_faves:200",
    # AI 主题
    "AI stock OR artificial intelligence stocks min_faves:200",
    "semiconductor OR chip stocks min_faves:150",
    # 中概股
    "BABA OR Alibaba min_faves:100",
    "PDD OR Pinduoduo min_faves:80",
    "JD.com OR $JD min_faves:80",
    "NIO OR $NIO min_faves:80",
    # 财报季
    "earnings season min_faves:100",
    "stock market today min_faves:150",
]

# ── A股 / 港股关键词 ────────────────────────────────────────────────────────
CN_STOCK_QUERIES: list[str] = [
    # A股大盘
    "上证指数 OR 沪深300 min_faves:50",
    "A股 OR 中国股市 min_faves:80",
    # 港股
    "恒生指数 OR Hang Seng min_faves:50",
    "港股 OR Hong Kong stocks min_faves:50",
    # 热门板块
    "新能源汽车 OR 比亚迪 min_faves:50",
    "AI 人工智能 中国 min_faves:50",
    "中概股 OR China stocks min_faves:100",
    # 政策
    "中国 央行 降息 OR 降准 min_faves:80",
    "中国经济 OR China economy min_faves:100",
    # 房地产
    "中国房地产 OR 恒大 OR 碧桂园 min_faves:80",
]

# ── 宏观关键词 ──────────────────────────────────────────────────────────────
MACRO_QUERIES: list[str] = [
    # 美联储 / 利率
    "Fed rate hike OR rate cut min_faves:200",
    "FOMC OR Powell min_faves:200",
    "interest rate OR yields min_faves:150",
    "treasury OR bonds min_faves:150",
    # 通胀 / 经济数据
    "inflation OR CPI min_faves:200",
    "recession OR soft landing min_faves:150",
    "GDP OR economic data min_faves:100",
    "jobs report OR NFP min_faves:150",
    # 美元 / 外汇
    "dollar OR DXY min_faves:100",
    "yen OR yuan min_faves:80",
    # 黄金 / 大宗商品
    "gold OR $GLD min_faves:200",
    "silver min_faves:80",
    "oil OR crude OR WTI min_faves:150",
    "copper OR commodities min_faves:80",
    # 地缘政治
    "geopolitical OR tariff min_faves:150",
    "election 2026 min_faves:100",
    # 全球宏观
    "global economy min_faves:100",
    "China US trade min_faves:100",
]

# ── 全部搜索词（精选核心，避免限流）───────────────────────────────────────
def get_all_queries() -> list[str]:
    """获取精选搜索词（12个核心，避免 API 限流）"""
    return [
        # 宏观（4个）
        "Fed rate OR interest rate min_faves:200",
        "inflation OR CPI min_faves:200",
        "gold price OR $GLD min_faves:200",
        "recession OR soft landing min_faves:150",
        # 美股科技（4个）
        "NVDA OR Nvidia min_faves:300",
        "AI stock OR artificial intelligence min_faves:200",
        "semiconductor OR chip stocks min_faves:150",
        "stock market today min_faves:150",
        # 中概/中国（2个）
        "BABA OR Alibaba min_faves:100",
        "China stocks OR 中概股 min_faves:100",
        # 大宗商品（2个）
        "oil OR crude WTI min_faves:150",
        "dollar OR DXY min_faves:100",
    ]


def get_kol_search_queries() -> list[str]:
    """获取 KOL 定向搜索的 from: 查询列表"""
    from .kol_list import get_all_kol_handles
    return [f"from:{h}" for h in get_all_kol_handles()]
