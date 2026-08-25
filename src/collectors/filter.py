"""
投资内容过滤器
从多源数据中筛选出与投资/财经/科技相关的内容
"""
from __future__ import annotations

import re
from typing import List

from .multi_source_manager import UnifiedPost


# 投资相关关键词（用于过滤）
INVESTMENT_KEYWORDS = [
    # 市场
    "股市", "股票", "A股", "港股", "美股", "中概股", "纳斯达克", "标普", "道琼斯",
    "大盘", "指数", "沪指", "深成指", "创业板", "科创板", "恒生",
    # 资产
    "黄金", "白银", "原油", "铜", "铁矿石", "大宗商品", "期货",
    "比特币", "以太坊", "加密货币", "数字货币", "BTC", "ETH",
    "美债", "国债", "债券", "收益率", "利率",
    "美元", "人民币", "汇率", "外汇",
    # 宏观
    "美联储", "加息", "降息", "通胀", "CPI", "PCE", "非农", "GDP",
    "央行", "货币政策", "财政政策", "衰退", "软着陆", "滞胀",
    "经济", "金融危机", "衰退", "复苏",
    # 公司/行业
    "财报", "业绩", "营收", "利润", "亏损", "盈利",
    "回购", "分红", "估值", "PE", "市盈率", "EPS",
    "英伟达", "NVDA", "特斯拉", "TSLA", "苹果", "AAPL", "微软", "MSFT",
    "谷歌", "GOOG", "亚马逊", "AMZN", "Meta", "META",
    "AI", "人工智能", "芯片", "半导体", "存储芯片", "美光",
    "新能源", "电动车", "光伏", "储能",
    "房地产", "楼市", "房价",
    "银行", "保险", "券商", "基金",
    # 人物
    "巴菲特", "芒格", "Burry", "Ackman", "Sacks", "Dalio",
    "马斯克", "Musk", "黄仁勋", "Jensen",
    "鲍威尔", "Powell", "耶伦", "Yellen",
    # 事件
    "IPO", "上市", "退市", "并购", "收购", "重组",
    "监管", "政策", "制裁", "关税", "贸易战",
    "Jackson Hole", "杰克逊霍尔", "FOMC", "议息",
    # 中文投资圈
    "大盘", "抄底", "逃顶", "牛市", "熊市", "震荡",
    "北向资金", "南向资金", "融资融券",
    "涨停", "跌停", "停牌", "复牌",
]

# 排除关键词（明显非投资的娱乐/社会新闻）
EXCLUDE_KEYWORDS = [
    "明星", "爱豆", "粉丝", "追星", "综艺", "电视剧", "电影", "选秀",
    "微博之夜", "热搜", "吃瓜", "八卦",
    "车祸", "命案", "凶杀", "强奸", "诈骗",
    "离婚", "结婚", "恋情", "出轨",
    "美食", "旅游", "穿搭", "美妆", "健身",
    "宠物", "萌宠", "猫咪", "狗狗",
]


def is_investment_related(post: UnifiedPost) -> bool:
    """判断帖子是否与投资相关"""
    text = (post.title + " " + post.content).lower()
    
    # 检查排除关键词（如果排除关键词太多，直接过滤）
    exclude_count = sum(1 for kw in EXCLUDE_KEYWORDS if kw.lower() in text)
    if exclude_count >= 2:
        return False
    
    # 检查投资关键词
    match_count = sum(1 for kw in INVESTMENT_KEYWORDS if kw.lower() in text)
    
    # 如果匹配到至少1个投资关键词，保留
    if match_count >= 1:
        return True
    
    # 以下来源默认保留（因为本身就是财经/科技类）
    if post.source in ["xueqiu", "wallstreetcn", "cls", "hackernews", "36kr"]:
        return True
    
    # 微博和知乎需要有投资关键词才保留
    return False


def filter_investment_posts(posts: List[UnifiedPost]) -> List[UnifiedPost]:
    """筛选投资相关帖子"""
    filtered = [p for p in posts if is_investment_related(p)]
    return filtered


def get_matched_keywords(post: UnifiedPost) -> List[str]:
    """获取帖子匹配到的投资关键词"""
    text = (post.title + " " + post.content).lower()
    matched = [kw for kw in INVESTMENT_KEYWORDS if kw.lower() in text]
    return matched
