"""
KOL 名单配置 — 美股 / A股港股 / 宏观 三大领域
按影响力和信息质量排序，优先抓取顶部账号
"""

# ── 美股领域 KOL ────────────────────────────────────────────────────────────
US_STOCK_KOLS: list[dict] = [
    # 顶级机构 / 官方
    {"handle": "FederalReserve", "name": "美联储", "category": "官方", "weight": 10},
    {"handle": "federalreserve", "name": "美联储", "category": "官方", "weight": 10},
    {"handle": "SecDev", "name": "美国SEC", "category": "监管", "weight": 9},
    {"handle": "BLS_gov", "name": "美国劳工统计局", "category": "数据", "weight": 9},
    {"handle": "BEA_News", "name": "美国经济分析局", "category": "数据", "weight": 9},
    # 快讯 / 新闻（速度优先）
    {"handle": "DeItaone", "name": "Delta One", "category": "快讯", "weight": 9},
    {"handle": "LiveSquawk", "name": "LiveSquawk", "category": "快讯", "weight": 9},
    {"handle": "financialjuice", "name": "Financial Juice", "category": "快讯", "weight": 8},
    {"handle": "Reuters", "name": "路透社", "category": "媒体", "weight": 8},
    {"handle": "BloombergTV", "name": "彭博电视", "category": "媒体", "weight": 8},
    {"handle": "WSJ", "name": "华尔街日报", "category": "媒体", "weight": 8},
    {"handle": "CNBC", "name": "CNBC", "category": "媒体", "weight": 7},
    # 顶级投资人
    {"handle": "RayDalio", "name": "瑞·达利欧 (桥水)", "category": "宏观/价值", "weight": 10},
    {"handle": "chamath", "name": "Chamath (Social Capital)", "category": "科技成长", "weight": 9},
    {"handle": "jimcramer", "name": "Jim Cramer (CNBC)", "category": "综合", "weight": 8},
    {"handle": "pmarca", "name": "Marc Andreessen (a16z)", "category": "科技/VC", "weight": 9},
    {"handle": "Naval", "name": "Naval Ravikant", "category": "投资哲学", "weight": 8},
    # 策略师 / 分析师
    {"handle": "biancoresearch", "name": "Jesse Felder (Bianco)", "category": "宏观策略", "weight": 9},
    {"handle": "downtownjbrown", "name": "Downtown Josh Brown", "category": "财富管理", "weight": 8},
    {"handle": "markminervini", "name": "Mark Minervini", "category": "技术分析", "weight": 8},
    {"handle": "traderstewie", "name": "TraderStewie", "category": "技术分析", "weight": 7},
    {"handle": "michaeljburry", "name": "Michael Burry", "category": "价值/空头", "weight": 9},
    # 科技股专项
    {"handle": "Techmeme", "name": "Techmeme", "category": "科技新闻", "weight": 8},
    {"handle": "verge", "name": "The Verge", "category": "科技媒体", "weight": 7},
]

# ── A股 / 港股领域 KOL ──────────────────────────────────────────────────────
CN_STOCK_KOLS: list[dict] = [
    # 宏观策略
    {"handle": "HaoHongCFA", "name": "洪灏", "category": "中国宏观策略", "weight": 10},
    {"handle": "maoxian", "name": "茅侃侃/猫眼看市", "category": "港股策略", "weight": 8},
    {"handle": "realDawningW", "name": "Dawning W", "category": "中概股", "weight": 8},
    # 财经媒体
    {"handle": "caixin", "name": "财新网", "category": "财经媒体", "weight": 9},
    {"handle": "FTChinese", "name": "FT中文网", "category": "财经媒体", "weight": 8},
    {"handle": "SCMPNews", "name": "南华早报", "category": "香港媒体", "weight": 8},
    {"handle": "hkejnews", "name": "信报", "category": "香港财经", "weight": 7},
    # 官方 / 数据
    {"handle": "PDChina", "name": "人民日报", "category": "官方", "weight": 9},
    {"handle": "xinhua", "name": "新华社", "category": "官方", "weight": 9},
    # 投资人 / 分析师
    {"handle": "lgtcapital", "name": "李录 (喜马拉雅资本)", "category": "价值投资", "weight": 9},
    {"handle": "ShengyinWang", "name": "王胜 (申万)", "category": "A股策略", "weight": 7},
]

# ── 宏观领域 KOL ────────────────────────────────────────────────────────────
MACRO_KOLS: list[dict] = [
    # 央行 / 官方
    {"handle": "federalreserve", "name": "美联储", "category": "央行", "weight": 10},
    {"handle": "ecb", "name": "欧洲央行", "category": "央行", "weight": 9},
    {"handle": "bankofengland", "name": "英格兰银行", "category": "央行", "weight": 8},
    {"handle": "IMFNews", "name": "IMF", "category": "国际组织", "weight": 9},
    {"handle": "WorldBank", "name": "世界银行", "category": "国际组织", "weight": 8},
    # 宏观经济学家 / 策略师
    {"handle": "RayDalio", "name": "瑞·达利欧", "category": "宏观", "weight": 10},
    {"handle": "biancoresearch", "name": "Bianco Research", "category": "宏观策略", "weight": 9},
    {"handle": "LynAldenContact", "name": "Lyn Alden", "category": "宏观/价值", "weight": 9},
    {"handle": "RaoulGMI", "name": "Raoul Pal (Real Vision)", "category": "宏观/周期", "weight": 9},
    {"handle": "LukeGromen", "name": "Luke Gromen", "category": "宏观/美元", "weight": 8},
    # 大宗商品 / 能源
    {"handle": "JavierBlas", "name": "Javier Blas (彭博)", "category": "大宗商品", "weight": 8},
    {"handle": "OPEC", "name": "OPEC", "category": "石油", "weight": 9},
    {"handle": "IEA", "name": "国际能源署", "category": "能源", "weight": 8},
    # 黄金 / 贵金属
    {"handle": "GOLDCOUNCIL", "name": "世界黄金协会", "category": "黄金", "weight": 8},
]

# ── 合并去重后的 KOL 账号列表（用于爬虫 from: 查询）──────────────────────────
def get_all_kol_handles() -> list[str]:
    """获取精选 KOL handle（20个核心，避免 API 限流）"""
    # 按影响力精选：官方/央行 + 顶级投资人 + 核心媒体 + 宏观策略
    return [
        # 官方/央行 (4)
        "federalreserve",    # 美联储
        "ecb",               # 欧洲央行
        "IMFNews",           # IMF
        "BLS_gov",           # 美国劳工统计局
        # 快讯/媒体 (4)
        "DeItaone",          # Delta One 快讯
        "LiveSquawk",        # LiveSquawk 快讯
        "Reuters",           # 路透社
        "WSJ",               # 华尔街日报
        # 顶级投资人 (4)
        "RayDalio",          # 瑞·达利欧
        "michaeljburry",     # Michael Burry
        "chamath",           # Chamath
        "pmarca",            # Marc Andreessen (a16z)
        # 宏观策略师 (4)
        "biancoresearch",    # Bianco Research
        "LynAldenContact",   # Lyn Alden
        "RaoulGMI",          # Raoul Pal
        "LukeGromen",        # Luke Gromen
        # 中概/中国 (2)
        "HaoHongCFA",        # 洪灏
        "caixin",            # 财新网
        # 科技/大宗商品 (2)
        "Techmeme",          # Techmeme 科技新闻
        "JavierBlas",        # 彭博大宗商品
    ]


def get_kol_weight(handle: str) -> int:
    """获取某个 KOL 的权重，用于信号加权"""
    handle_lower = handle.lower()
    for kol_list in [US_STOCK_KOLS, CN_STOCK_KOLS, MACRO_KOLS]:
        for kol in kol_list:
            if kol["handle"].lower() == handle_lower:
                return kol["weight"]
    return 5  # 默认权重
