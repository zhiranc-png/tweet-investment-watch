# -*- coding: utf-8 -*-
"""
KOL 监测池 v3.0 — 全资产覆盖版（2026-08-27）

优化方向：
1. 美债/固收策略师扩充（+4，6→10人）
2. 黄金/贵金属分析师扩充（+4，4→8人）
3. 外汇策略师扩充（+3，3→6人）
4. 宏观策略补充重量级（+3，12→15人）
5. A股/港股提升质量（+4，11→15人）
6. 新增大宗商品/能源组（+4人）
7. 新增信贷/信用策略组（+3人）
8. 快讯类继续保持低权重

净变化：从 66 人到 89 人（+23 净增）
"""

# 全量监测池（按主题分组，便于维护）
KOL_LIST = [
    # ── 美债/固收策略师（10人）──
    "TruthGundlach",       # Jeff Gundlach - DoubleLine创始人，新债王
    "dimartinobooth",      # Danielle DiMartino Booth - QI Research CEO，前达拉斯联储
    "GrantsPub",           # Grants Interest Rate Observer - Jim Grant
    "TheBondFreak",        # Randy Woodward - 30年固收经验
    "convertbond",         # 可转债专家
    "lisaabramowicz1",     # 彭博信贷记者
    "KathyJones",          # Kathy Jones - 嘉信固收策略主管
    "TracyAlloway",        # Tracy Alloway - 彭博Odd Lots，信贷/固收深度
    "johnauthers",         # John Authers - 彭博观点，资深金融编辑
    "LacyHunt",            # Lacy Hunt - Hoisington，长期美债策略

    # ── 黄金/贵金属（8人）──
    "GOLDCOUNCIL",         # World Gold Council - 世界黄金协会
    "LynAldenContact",     # Lyn Alden - 宏观+黄金深度分析
    "biancoresearch",      # Bianco Research - 宏观+贵金属
    "LukeGromen",          # Luke Gromen - 美元/黄金/财政主导
    "KitcoNewsNOW",        # Kitco News - 贵金属新闻与深度访谈
    "GaryWagner",          # Gary Wagner - TheGoldForecast，40年黄金分析师
    "GoldSeek",            # GoldSeek / Peter Spina - 黄金研究
    "SilverInstitute",     # 白银协会

    # ── 外汇策略（6人）──
    "MacroAlf",            # Alf - 宏观+外汇
    "DavidBeckworth",      # 货币经济学
    "SoberLook",           # 全球宏观+外汇图表
    "BrentDonnelly",       # Brent Donnelly - Spectra Markets，前汇丰外汇
    "KathyLienFX",         # Kathy Lien - BK Asset Management，外汇策略
    "RobinBrooksIIF",      # Robin Brooks - IIF，前高盛外汇策略

    # ── 宏观策略（15人）──
    "NickTimiraos",        # 美联储记者，WSJ
    "LizAnnSonders",       # 嘉信首席投资策略师
    "KevinRGordon",        # 嘉信策略师
    "KobeissiLetter",      # 债券+宏观策略
    "elerianm",            # 埃尔埃里安 - 安联首席经济顾问
    "RayDalio",            # 达利欧 - 桥水基金
    "MorganHousel",        # 行为金融学
    "balajis",             # Balaji Srinivasan - 前a16z
    "BobEUnlimited",       # Bob Elliott - 前桥水
    "dariusdale42",        # Darius Dale - 42 Macro
    "TheStalwart",         # The Stalwart - 市场深度评论
    "jessefelder",         # Jesse Felder - Felder Report
    "Hedgeye",             # Hedgeye Risk Management - 宏观四象限框架
    "UrbanKaoboy",         # Michael Kao - 前对冲基金经理，宏观+信贷
    "TimDuy",              # Tim Duy - 美联储观察专家，SIFMA

    # ── 信贷/信用策略（3人）──
    "Markzandi",           # Mark Zandi - Moody's Analytics 首席经济学家
    "BoveResearch",        # Dick Bove - 银行策略分析师
    "MishGEA",             # Mish Shedlock - 信贷/经济分析

    # ── 大宗商品/能源（4人）──
    "JavierBlas",          # Javier Blas - 彭博大宗商品专栏
    "Ole_S_Hansen",        # Ole Hansen - Saxo Bank 大宗商品策略
    "TsvetanaPaskaleva",   # Tsvetana Paskaleva - 大宗商品分析
    "EIAgov",              # 能源信息署（从官方机构移来，更适合放这里）

    # ── 官方机构（5人）──
    "federalreserve",      # 美联储
    "SECGov",              # SEC
    "BLS_gov",             # 劳工统计局
    "BEA_News",            # 经济分析局
    "USTreasury",          # 美国财政部

    # ── 美股/投资大V（15人）──
    "charliebilello",      # Charlie Bilello - 量化图表大师
    "RyanDetrick",         # Ryan Detrick - 市场历史数据
    "EricBalchunas",       # ETF专家
    "chamath",             # Chamath - SPAC之王
    "unusual_whales",      # 异常期权流量
    "Dan_Niles",           # Dan Niles - 科技股空头
    "MikeZaccardi",        # 市场策略
    "EPers",               # EPers
    "jimcramer",           # 吉姆克莱默（反向指标属性）
    "michaeljburry",       # 迈克尔伯里 - 大空头原型
    "BillAckman",          # Bill Ackman - 对冲基金
    "CathieDWood",         # 木头姐 - ARK Invest
    "PeterLBrandt",        # 技术分析大师
    "John_Hempton",        # 做空专家
    "168X_Fortune",        # 168X - 前沿科技+资本

    # ── 知名交易者（5人）──
    "aleabitoreddit",      # Serenity - AI供应链瓶颈挖掘
    "ripster47",           # Ripster - 交易员的交易员
    "matt_levine",         # Matt Levine - 彭博专栏
    "PatrickHillis1",      # Patrick Hillis - 期权交易员
    "ArtofSpecuycky",      # Art of Speculation - AI基本面+宏观分析

    # ── 中文圈/A股港股（15人）──
    "HaoHongCFA",          # 洪灏 - 思睿集团首席经济学家，前交银国际
    "PBOC_Official",       # 中国人民银行
    "caixin",              # 财新网
    "GavekalDragonom",     # 龙洲经讯 - 中国宏观研究
    "maoxian",             # 猫哥
    "JIEDUJUN",            # 解读君
    "qinbafrank",          # Frank秦 - 宏观
    "diaomao2023",         # 雕猫
    "xiaomustock",         # 小莫
    "tj_research",         # TJ Research
    "jackli727",           # Jack Li
    "muddywatersre",       # 浑水研究
    "JCap_Research",       # JCap - 做空研究
    "b1anbin",             # Binbin - 港股/A股深度分析
    "WallStreet0Name",     # 华尔街没有名字 - 加密/交易观点
]

# KOL 权重配置（用于信号聚合加权）
KOL_WEIGHTS = {
    # ── 美债/固收（10人）──
    "TruthGundlach": 5.0,
    "dimartinobooth": 4.5,
    "GrantsPub": 4.0,
    "TheBondFreak": 3.5,
    "convertbond": 3.0,
    "lisaabramowicz1": 3.5,
    "KathyJones": 4.0,
    "TracyAlloway": 3.5,
    "johnauthers": 3.5,
    "LacyHunt": 3.5,

    # ── 黄金/贵金属（8人）──
    "GOLDCOUNCIL": 4.0,
    "LynAldenContact": 4.5,
    "biancoresearch": 4.0,
    "LukeGromen": 4.0,
    "KitcoNewsNOW": 3.5,
    "GaryWagner": 3.5,
    "GoldSeek": 3.0,
    "SilverInstitute": 2.5,

    # ── 外汇策略（6人）──
    "MacroAlf": 4.0,
    "DavidBeckworth": 3.5,
    "SoberLook": 3.0,
    "BrentDonnelly": 4.0,
    "KathyLienFX": 3.5,
    "RobinBrooksIIF": 3.5,

    # ── 宏观策略（15人）──
    "NickTimiraos": 4.0,
    "LizAnnSonders": 4.0,
    "KevinRGordon": 3.5,
    "KobeissiLetter": 4.0,
    "elerianm": 4.5,
    "RayDalio": 4.5,
    "MorganHousel": 3.0,
    "balajis": 3.5,
    "BobEUnlimited": 3.5,
    "dariusdale42": 3.5,
    "TheStalwart": 3.5,
    "jessefelder": 3.5,
    "Hedgeye": 4.0,
    "UrbanKaoboy": 4.0,
    "TimDuy": 3.5,

    # ── 信贷/信用策略（3人）──
    "Markzandi": 3.5,
    "BoveResearch": 3.0,
    "MishGEA": 3.0,

    # ── 大宗商品/能源（4人）──
    "JavierBlas": 4.0,
    "Ole_S_Hansen": 3.5,
    "TsvetanaPaskaleva": 3.0,
    "EIAgov": 3.5,

    # ── 官方机构（5人）──
    "federalreserve": 5.0,
    "SECGov": 4.0,
    "BLS_gov": 4.5,
    "BEA_News": 4.0,
    "USTreasury": 5.0,

    # ── 美股/投资大V（15人）──
    "charliebilello": 4.0,
    "RyanDetrick": 3.5,
    "EricBalchunas": 3.0,
    "chamath": 3.0,
    "unusual_whales": 3.0,
    "Dan_Niles": 3.5,
    "MikeZaccardi": 3.0,
    "EPers": 2.5,
    "jimcramer": 2.0,
    "michaeljburry": 4.0,
    "BillAckman": 4.0,
    "CathieDWood": 3.0,
    "PeterLBrandt": 3.5,
    "John_Hempton": 3.5,
    "168X_Fortune": 3.0,

    # ── 知名交易者（5人）──
    "aleabitoreddit": 4.0,
    "ripster47": 3.5,
    "matt_levine": 3.5,
    "PatrickHillis1": 3.0,
    "ArtofSpecuycky": 3.5,

    # ── 中文圈/A股港股（15人）──
    "HaoHongCFA": 4.0,
    "PBOC_Official": 4.5,
    "caixin": 3.5,
    "GavekalDragonom": 3.5,
    "maoxian": 2.0,
    "JIEDUJUN": 2.5,
    "qinbafrank": 3.0,
    "diaomao2023": 2.0,
    "xiaomustock": 2.0,
    "tj_research": 2.5,
    "jackli727": 3.0,
    "muddywatersre": 3.5,
    "JCap_Research": 3.0,
    "b1anbin": 2.5,
    "WallStreet0Name": 3.0,
}

DEFAULT_KOL_WEIGHT = 2.0

# 兼容旧变量名
ALL_KOLS = KOL_LIST
