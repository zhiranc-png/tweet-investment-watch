"""
KOL 名单配置
按领域分类：美股、A股/港股、宏观
"""
from __future__ import annotations


# 美股科技 / 投资大 V
US_STOCK_KOLS = [
    "elonmusk",            # 马斯克 - Tesla/SpaceX CEO，市场影响力最大
    "WarrenBuffett",       # 巴菲特（非官方但有影响力的账号）
    "chamath",             # Chamath Palihapitiya - SPAC之王，科技投资
    "CathieDWood",         # 木头姐 - ARK Invest创始人
    "BillAckman",          # Bill Ackman - 对冲基金经理
    "RayDalio",            # 达利欧 - 桥水基金创始人
    "sama",                # Sam Altman - OpenAI CEO，AI风向标
    "pmarca",              # Marc Andreessen - a16z创始人
    "naval",               # Naval Ravikant - AngelList创始人
    "paulg",               # Paul Graham - YC创始人
    "michaeljburry",       # Michael Burry - 大空头原型
    "DavidSacks",          # David Sacks - 科技投资人
    "garyblack00",         # Gary Black - 特斯拉多头
    "TeslaBoomerMama",     # 特斯拉散户代表
    "StockMktNewz",        # 股市新闻
    "FirstSquawk",         # 财经快讯
    "business",            # Bloomberg Business
    "WSJ",                 # 华尔街日报
    "Reuters",             # 路透社
    "CNBC",                # CNBC
]

# A股 / 港股相关
HK_CN_KOLS = [
    "lindayu2019",         # 李大霄 - A股知名分析师
    "danilo0755",          # 但斌 - 东方港湾
    "ZhangChenLiang",      # 张承良 - 港股分析师
    "lthomas007",          # 港股相关
    "HongKongHermit",      # 香港隐士
    "chenshiyingcnbc",     # 陈世英 CNBC
    "SCMPNews",            # 南华早报
    "CaixinGlobal",        # 财新英文
    "xhsgedu",             # 雪球（如果有）
]

# 宏观经济 / 美联储 / 全球市场
MACRO_KOLS = [
    "federalreserve",      # 美联储官方
    "EconguyRosie",        # Rosie - 宏观经济学家
    "LizAnnSonders",       # Liz Ann Sonders - Charles Schwab首席投资策略师
    "elerianm",            # Mohamed El-Erian - 安联首席经济顾问
    "Nouriel",             # 鲁比尼 - 末日博士
    "steveliesman",        # Steve Liesman - CNBC经济记者
    "jimcramer",           # 吉姆·克莱默 - Mad Money主持人
    "RaoulGMI",            # Raoul Pal - Real Vision创始人
    "LukeGromen",          # Luke Gromen - 宏观分析师
    "SantiagoAuFund",      # Santiago - 宏观投资者
    "NorthmanTrader",      # Sven Henrich - 技术分析
    "allstarcharts",       # JC Parets - 技术分析
    "BloombergTV",         # Bloomberg TV
    "FinancialTimes",      # 金融时报
    "TheEconomist",        # 经济学人
]


def get_all_kol_handles() -> list[str]:
    """获取所有 KOL 账号"""
    return US_STOCK_KOLS + HK_CN_KOLS + MACRO_KOLS


def get_kol_count() -> dict:
    """各领域 KOL 数量"""
    return {
        "美股": len(US_STOCK_KOLS),
        "A股港股": len(HK_CN_KOLS),
        "宏观": len(MACRO_KOLS),
        "总计": len(US_STOCK_KOLS) + len(HK_CN_KOLS) + len(MACRO_KOLS),
    }
