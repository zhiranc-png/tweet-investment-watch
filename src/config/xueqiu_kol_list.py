# -*- coding: utf-8 -*-
"""
雪球 KOL 名单（已验证活跃）
覆盖：宏观/固收、A股、港股、黄金/大宗商品、基金、价值投资、成长投资
入池标准：搜索解析 + 时间线验活跃（粉丝量级 + 最近30天有发帖 + 认证信息匹配）
"""

XUEQIU_ROSTER = [
    # ── 宏观/策略 ──────────────────────────────────────
    {
        "screen_name": "管清友",
        "uid": 2371289267,
        "weight": 4.0,
        "category": "macro",
        "note": "如是金融研究院院长，宏观经济+政策分析",
    },
    {
        "screen_name": "但斌",
        "uid": 1102105103,
        "weight": 4.0,
        "category": "value",
        "note": "东方港湾董事长，价值投资代表",
    },
    {
        "screen_name": "梁宏",
        "uid": 9887656769,
        "weight": 4.0,
        "category": "growth",
        "note": "希瓦资产创始人，成长股+港股",
    },
    {
        "screen_name": "大道无形我有型",
        "uid": 1247347556,
        "weight": 4.5,
        "category": "value",
        "note": "段永平，价值投资标杆，发言少但分量重",
    },
    {
        "screen_name": "不明真相的群众",
        "uid": 1955602780,
        "weight": 4.0,
        "category": "macro",
        "note": "方三文，雪球创始人，宏观+投资哲学",
    },

    # ── 基金/指数投资 ──────────────────────────────────
    {
        "screen_name": "银行螺丝钉",
        "uid": 3079173340,
        "weight": 3.5,
        "category": "fund",
        "note": "指数基金定投大V，每日估值表",
    },
    {
        "screen_name": "望京博格",
        "uid": 4579887327,
        "weight": 3.5,
        "category": "fund",
        "note": "绿巨人组合主理人，基金+行业配置",
    },
    {
        "screen_name": "闲来一坐s话投资",
        "uid": 3491303582,
        "weight": 3.5,
        "category": "value",
        "note": "价值投资深度分析，消费+医药",
    },

    # ── 科技/成长 ──────────────────────────────────────
    {
        "screen_name": "仓又加错-Leo",
        "uid": 1854211541,
        "weight": 3.5,
        "category": "tech",
        "note": "互联网/科技股深度分析",
    },
    {
        "screen_name": "刘志超",
        "uid": 1210132104,
        "weight": 3.5,
        "category": "tech",
        "note": "互联网+中概股分析",
    },

    # ── 消费/医药 ──────────────────────────────────────
    {
        "screen_name": "最后遇到你",
        "uid": 1434870468,
        "weight": 3.0,
        "category": "consumer",
        "note": "消费股分析",
    },
    {
        "screen_name": "黄建平",
        "uid": 2128248103,
        "weight": 3.5,
        "category": "healthcare",
        "note": "医药行业深度分析",
    },

    # ── 周期/资源 ──────────────────────────────────────
    {
        "screen_name": "草帽路飞",
        "uid": 933714418,
        "weight": 3.0,
        "category": "energy",
        "note": "能源+周期股分析",
    },
    {
        "screen_name": "HIS1963",
        "uid": 1300105360,
        "weight": 3.0,
        "category": "finance",
        "note": "银行+金融股分析",
    },

    # ── 港股/海外 ──────────────────────────────────────
    {
        "screen_name": "山行",
        "uid": 1828979008,
        "weight": 3.0,
        "category": "hk_stock",
        "note": "港股+公用事业分析",
    },
]

# 按类别索引
XUEQIU_BY_CATEGORY = {}
for k in XUEQIU_ROSTER:
    cat = k["category"]
    XUEQIU_BY_CATEGORY.setdefault(cat, []).append(k)
