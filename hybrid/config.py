# -*- coding: utf-8 -*-
"""监测池配置：v3.1 全量池（2026-08-27 扩容至 93 人）

优化方向：
1. 美债/固收策略师大幅扩充（+6，1→7人）
2. 黄金/贵金属分析师扩充（+4，1→5人）
3. 外汇策略师新增（+4人）
4. 宏观策略补充重量级（+3人）
5. 信贷/信用策略新增（+3人）
6. 大宗商品/能源扩充（+2人）
7. 中文圈/A股质量提升（+3人）
8. 美股/估值新增（+2人）
9. 快讯类保持低权重但保留
"""

# 变量名沿用 PILOT_KOLS 以兼容 main.py；实际已是全量池。
PILOT_KOLS = [
    # ── 美债/固收策略师（7人）──
    "TruthGundlach",      # Jeff Gundlach，双线资本创始人，"新债王"
    "dimartinobooth",     # Danielle DiMartino Booth，前达拉斯联储顾问，QI Research CEO
    "GrantsPub",          # Jim Grant 的《利率观察家》，债券史权威
    "TheBondFreak",       # Randy Woodward，30年固收经验，收益率曲线专家
    "lisaabramowicz1",    # 彭博信贷记者
    "convertbond",        # 可转债专家
    "RandyFrederick",     # 嘉信交易与衍生品董事总经理

    # ── 黄金/贵金属（5人）──
    "KitcoNewsNOW",       # Kitco 新闻官方
    "goldseek",           # GoldSeek
    "GaryWagner",         # Gary Wagner，40年黄金分析师
    "JamesGRickards",     # Jim Rickards，货币战争/黄金/地缘政治专家
    "SilverInstitute",    # 白银协会

    # ── 外汇策略（4人）──
    "donnelly_brent",     # Brent Donnelly，Spectra Markets，前汇丰外汇
    "KathyLienFX",        # Kathy Lien，BK Asset Management
    "Ole_S_Hansen",       # Ole Hansen，盛宝银行大宗商品/外汇策略
    "marcmakingsense",    # Marc Chandler，Bannockburn Global Forex，40年外汇经验

    # ── 宏观策略（18人）──
    "NickTimiraos",       # 华尔街时报美联储记者
    "LizAnnSonders",      # 嘉信首席投资策略师
    "KobeissiLetter",     # Kobeissi Letter
    "elerianm",           # Mohamed El-Erian，安联首席经济顾问
    "RayDalio",           # Ray Dalio，桥水创始人
    "MorganHousel",       # Morgan Housel，行为金融学
    "biancoresearch",     # Jim Bianco，Bianco Research
    "balajis",            # Balaji Srinivasan，前a16z合伙人
    "LynAldenContact",    # Lyn Alden，宏观+工程背景
    "BobEUnlimited",      # Bob Elliott，Unlimited Funds
    "SoberLook",          # SoberLook，宏观图表分析
    "dariusdale42",       # Darius Dale，42 Macro
    "MacroAlf",           # Macro Alf，宏观策略
    "DavidBeckworth",     # David Beckworth，Mercatus Center
    "TheStalwart",        # The Stalwart，财经媒体
    "Hedgeye",            # Hedgeye Risk Management
    "UrbanKaoboy",        # Michael Kao，前对冲基金经理
    "RaoulGMI",           # Raoul Pal，Real Vision CEO

    # ── 信贷/信用策略（3人）──
    "Markzandi",          # Mark Zandi，穆迪首席经济学家
    "MishGEA",            # Mish Shedlock，经济/信贷分析
    "bespokeinvest",      # Bespoke Investment Group

    # ── 大宗商品/能源（3人）──
    "IrinaSlav",          # OilPrice.com 主笔
    "CommodityGirl",      # 大宗商品交易与分析
    # "JavierBlas",        # 彭博大宗商品（暂不加，和 EIA 重复度高）

    # ── 官方机构组（6人）──
    "federalreserve",     # 美联储
    "SECGov",             # SEC
    "BLS_gov",            # 劳工统计局
    "BEA_News",           # 经济分析局
    "EIAgov",             # 能源信息署
    "USTreasury",         # 美国财政部

    # ── 美股/消息面组（19人）──
    "DeItAone",           # 快讯（低权重）
    "LiveSquawk",         # 快讯（低权重）
    "financialjuice",     # 快讯（低权重）
    "charliebilello",     # Charlie Bilello，市场数据分析师
    "RyanDetrick",        # Ryan Detrick，市场策略师
    "EricBalchunas",      # Eric Balchunas，彭博 ETF 分析师
    "chamath",            # Chamath Palihapitiya，Social Capital
    "unusual_whales",     # 期权异动
    "Dan_Niles",          # Dan Niles，科技股空头
    "SawyerMerritt",      # Sawyer Merritt，科技新闻
    "MikeZaccardi",       # Mike Zaccardi，市场策略
    "jimcramer",          # Jim Cramer，CNBC
    "michaeljburry",      # Michael Burry，大空头原型
    "BillAckman",         # Bill Ackman，潘兴广场
    "CathieDWood",        # Cathie Wood，方舟投资
    "PeterLBrandt",       # Peter Brandt，技术分析
    "matt_levine",        # Matt Levine，彭博观点
    "John_Hempton",       # John Hempton，Bronte Capital
    "aswathdamodaran",    # Aswath Damodaran，估值教授
    "steve_hanke",        # Steve Hanke，约翰霍普金斯应用经济学

    # ── 知名交易者（5人）──
    "aleabitoreddit",     # Serenity / 白毛股神
    "ArtofSpecuycky",     # Art of Speculation
    "ripster47",          # Ripster
    "PatrickHillis1",     # Patrick Hillis，期权交易员
    "traderstewie",       # TraderStewie

    # ── 中文圈/A股港股（20人）──
    "michaelxpettis",     # Michael Pettis，北大，中国宏观
    "AndrewBatson",       # Gavekal Dragonomics
    "SCMPNews",           # 南华早报
    "GeorgeMagnus1",      # George Magnus
    "LiYuan6",            # NYT 李远
    "maoxian",            # 猫小闲
    "JIEDUJUN",           # 解读君
    "qinbafrank",         # Frank Qin
    "diaomao2023",        # 吊毛
    "xiaomustock",        # 小慕
    "tj_research",        # TJ Research
    "jackli727",          # Jack Li
    "muddywatersre",      # 浑水
    "JCap_Research",      # JCap Research
    "StockMKTNewz",       # 股票市场新闻
    "HaoHong_CFA",         # 洪灏
    "PBOC_Official",      # 中国人民银行
    "caixin",             # 财新网
    "WallStreet0Name",    # 华尔街没有名字
    "168X_Fortune",       # 168X 前沿科技
    "Sino_Market",        # 南华早报市场
    "TechBuzzChina",      # 科技乱炖
    # ── A股/港股个股与策略（2026-08-31 扩容，2人，均经 verify-candidates 实抓验真）──
    "aleabitoreddit",     # Serenity「白毛股神」，A股概念股名单引爆者（绿的谐波/易事特等），66万+粉，日更
    "michaeljburry",      # Michael Burry，港股价值挖掘（7月公开看多港股、加仓京东），8/28 在点评美团盈利
]

TWEETS_PER_KOL = 20      # 每个 KOL 拉最近 20 条
WINDOW_HOURS = 36        # 保留窗口（覆盖 24h 采集窗口 + 时差余量）

# 验收标准：
#   1. 单次成功率 >= 90%（个别封号/改名允许失败但须跟踪归因）
#   2. 无 429 限流、无账号风控（401/403）
#   3. JSON 结构完整（tweet_id / url / text / created_at / likes / retweets 非空）
