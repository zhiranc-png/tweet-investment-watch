# -*- coding: utf-8 -*-
"""监测池配置：52 人全量池（2026-08-26 由 5 人扩容；2026-08-27 移出保护账号 KevinRGordon/EPers）"""

# 变量名沿用 PILOT_KOLS 以兼容 main.py；实际已是全量池。
# 名单与 Echo 的 SOP §1 一致；禁用/失效 handle 一律不得加回。
PILOT_KOLS = [
    # ── 宏观组（18）──
    "NickTimiraos", "LizAnnSonders", "KobeissiLetter", "elerianm",
    "RayDalio", "MorganHousel", "financialjuice", "biancoresearch", "balajis",
    "LynAldenContact", "BobEUnlimited", "SoberLook", "convertbond", "dariusdale42",
    "MacroAlf", "DavidBeckworth", "lisaabramowicz1", "TheStalwart",
    # ── 官方机构组（6）──
    "federalreserve", "SECGov", "BLS_gov", "BEA_News", "EIAgov", "USTreasury",
    # ── 美股/消息面组（17）──
    "DeItAone", "LiveSquawk", "charliebilello", "RyanDetrick", "EricBalchunas",
    "chamath", "unusual_whales", "Dan_Niles", "SawyerMerritt", "MikeZaccardi",
    "jimcramer", "michaeljburry", "BillAckman", "CathieDWood",
    "PeterLBrandt", "matt_levine", "John_Hempton",
    # ── 中文圈/A股港股/做空组（11）──
    "aleabitoreddit", "maoxian", "JIEDUJUN", "qinbafrank", "diaomao2023",
    "xiaomustock", "tj_research", "jackli727", "muddywatersre", "JCap_Research",
    "StockMKTNewz",
]

TWEETS_PER_KOL = 20      # 每个 KOL 拉最近 20 条
WINDOW_HOURS = 36        # 保留窗口（覆盖 24h 采集窗口 + 时差余量）

# 验收标准（2026-08-26 起按全量跑）：
#   1. 单次成功率 >= 90%（个别封号/改名允许失败但须跟踪归因）
#   2. 无 429 限流、无账号风控（401/403）
#   3. JSON 结构完整（tweet_id / url / text / created_at / likes / retweets 非空）
