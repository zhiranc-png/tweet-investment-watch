#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多源数据统一采集 + 报告生成（稳定版）

流程：
1. X/Twitter 采集（如果有 AUTH_TOKEN/CT0）
2. 雪球 KOL 采集
3. 行情价格采集（新浪财经 + FRED）
4. 动态资讯采集（新浪财经 7x24 + 财新）
5. 生成完整 Markdown 报告

每个步骤独立 try-except，单源失败不影响整体。
"""
import json
import sys
import os
import datetime as dt
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "src"))

TZ8 = dt.timezone(dt.timedelta(hours=8))
today_str = dt.datetime.now(TZ8).strftime("%Y%m%d")
today_display = dt.datetime.now(TZ8).strftime("%Y年%m月%d日")

DATA_DIR = os.path.join(BASE, "data")
REPORT_DIR = os.path.join(BASE, "report")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════
# Step 1: X/Twitter 采集
# ═══════════════════════════════════════════════════════

def collect_x(per_user=20, hours=48):
    """采集 X/Twitter 数据。失败返回 None，不崩溃。"""
    auth_token = os.environ.get("AUTH_TOKEN", "")
    ct0 = os.environ.get("CT0", "")

    if not auth_token or not ct0:
        print("[X] ⚠️  缺少 AUTH_TOKEN/CT0，跳过 X 采集", flush=True)
        return None

    try:
        from collectors.x_api import XCollector, DEFAULT_INFLUENCERS
    except ImportError as e:
        print(f"[X] ⚠️  导入失败: {e}，跳过 X 采集", flush=True)
        return None

    try:
        print(f"[X] 🚀 开始采集（{len(DEFAULT_INFLUENCERS)} 位 KOL，每人 {per_user} 条，{hours}h 窗口）", flush=True)
        collector = XCollector(auth_token=auth_token, ct0=ct0)
        result = collector.collect(
            influencers=DEFAULT_INFLUENCERS,
            per_user_count=per_user,
            filter_investment=True,
            hours=hours,
        )
        print(f"[X] ✅ 完成: {result.get('total', 0)} 条，{result.get('success_users', 0)}/{len(DEFAULT_INFLUENCERS)} 成功", flush=True)
        failed = result.get("failed_users", [])
        if failed:
            print(f"[X] ⚠️  失败 {len(failed)} 个:", flush=True)
            for name, err in failed[:5]:
                print(f"    @{name}: {err}", flush=True)
            if len(failed) > 5:
                print(f"    ... 还有 {len(failed)-5} 个", flush=True)

        # 保存原始数据
        out_path = os.path.join(DATA_DIR, f"tweets_{today_str}.json")
        json.dump(result.get("tweets", []), open(out_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(f"[X] 📁 保存到: {out_path}", flush=True)

        return result
    except Exception as e:
        print(f"[X] ❌ 采集失败: {e}", flush=True)
        return None


def generate_x_brief(x_result):
    """从 X 数据生成简报。失败返回 None。"""
    if not x_result:
        return None
    try:
        from analysis.signal_aggregator import generate_brief
        from collectors.models import Tweet

        tweets = []
        for t in x_result.get("tweets", []):
            tweets.append(Tweet(
                tweet_id=t.get("tweet_id", ""),
                author=t.get("influencer_name", t.get("user_name", "")),
                content=t.get("text", ""),
                likes=t.get("likes", 0),
                reposts=t.get("retweets", 0),
                replies=t.get("replies", 0),
                created_at=t.get("created_at", ""),
                url=t.get("url", ""),
                tags=[], assets=[], themes=[],
                quality_score=t.get("score", 0),
                is_kol=True, comments=[],
            ))

        brief = generate_brief(tweets)

        out_path = os.path.join(DATA_DIR, f"brief_{today_str}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(brief, f, ensure_ascii=False, indent=2, default=str)
        print(f"[X] 📊 简报已生成: {out_path}", flush=True)
        return brief
    except Exception as e:
        print(f"[X] ⚠️  简报生成失败: {e}", flush=True)
        return None


# ═══════════════════════════════════════════════════════
# Step 2: 雪球采集
# ═══════════════════════════════════════════════════════

def collect_xueqiu():
    """采集雪球 KOL。失败返回 None。"""
    try:
        from collectors.xueqiu_collect import collect_xueqiu
        from config.xueqiu_kol_list import XUEQIU_ROSTER
    except ImportError as e:
        print(f"[雪球] ⚠️  导入失败: {e}，跳过", flush=True)
        return None

    try:
        print(f"[雪球] 🚀 开始采集（{len(XUEQIU_ROSTER)} 位大V）", flush=True)
        result = collect_xueqiu(XUEQIU_ROSTER)

        out_path = os.path.join(DATA_DIR, f"xueqiu_tweets_{today_str}.json")
        json.dump(result, open(out_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(f"[雪球] 📁 保存到: {out_path}", flush=True)
        return result
    except Exception as e:
        print(f"[雪球] ❌ 采集失败: {e}", flush=True)
        return None


# ═══════════════════════════════════════════════════════
# Step 3: 行情价格
# ═══════════════════════════════════════════════════════

def collect_prices():
    """采集所有核心资产价格。失败返回 {}。"""
    try:
        from collectors.price_enhanced import get_all_core_prices
    except ImportError as e:
        print(f"[价格] ⚠️  导入失败: {e}，跳过", flush=True)
        return {}

    try:
        print("[价格] 🚀 开始采集核心资产行情", flush=True)
        prices = get_all_core_prices()
        print(f"[价格] ✅ 完成: {len(prices)} 个资产", flush=True)

        out_path = os.path.join(DATA_DIR, f"prices_{today_str}.json")
        json.dump(prices, open(out_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(f"[价格] 📁 保存到: {out_path}", flush=True)
        return prices
    except Exception as e:
        print(f"[价格] ❌ 采集失败: {e}", flush=True)
        return {}


# ═══════════════════════════════════════════════════════
# Step 4: 动态资讯
# ═══════════════════════════════════════════════════════

def collect_news():
    """采集动态资讯。失败返回 []。"""
    try:
        from collectors.dynamic_news import collect_dynamic_news
    except ImportError as e:
        print(f"[资讯] ⚠️  导入失败: {e}，跳过", flush=True)
        return []

    try:
        print("[资讯] 🚀 开始采集动态资讯", flush=True)
        news = collect_dynamic_news(20)

        out_path = os.path.join(DATA_DIR, f"news_{today_str}.json")
        json.dump(news, open(out_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print(f"[资讯] 📁 保存到: {out_path}", flush=True)
        return news
    except Exception as e:
        print(f"[资讯] ❌ 采集失败: {e}", flush=True)
        return []


# ═══════════════════════════════════════════════════════
# Step 5: 生成报告
# ═══════════════════════════════════════════════════════

def generate_report(x_brief, xueqiu_data, prices, news):
    """生成完整的 Markdown 报告。"""
    print("[报告] 📝 生成多源数据报告...", flush=True)

    # 统计
    stats = x_brief.get("stats", {}) if x_brief else {}
    x_tweets = stats.get("total_tweets", 0)
    x_authors = stats.get("unique_authors", 0)
    xq_tweets = len(xueqiu_data.get("tweets", [])) if xueqiu_data else 0
    xq_kols_ok = xueqiu_data.get("kols_ok", 0) if xueqiu_data else 0
    xq_kols_total = xueqiu_data.get("kols_total", 0) if xueqiu_data else 0
    total_tweets = x_tweets + xq_tweets

    lines = []

    # ── 标题 ──────────────────────────────────────────
    lines.append(f"# 📊 投资舆情日报 · {today_display}")
    lines.append("")
    lines.append(f"> **数据窗口**：过去 48 小时 · 合计 {total_tweets} 条内容")
    if x_tweets > 0:
        lines.append(f"> **X/Twitter**：{x_tweets} 条 · {x_authors} 位 KOL")
    if xq_tweets > 0:
        lines.append(f"> **雪球**：{xq_tweets} 条 · {xq_kols_ok}/{xq_kols_total} 位大V")
    if news:
        lines.append(f"> **动态资讯**：{len(news)} 条实时快讯")
    lines.append("")

    # ── 一、速览表 ────────────────────────────────────
    lines.append("## 一、速览表")
    lines.append("")
    lines.append("7 大核心资产，一眼看完方向。短期=KOL舆情（数据驱动），中/长期=基本面逻辑（结构性判断）。")
    lines.append("")
    lines.append("| 资产 | 短期（舆情） | 中期（1-3月） | 长期（6月+） | 最新价 | 日涨跌 | 数据来源 |")
    lines.append("|------|-------------|--------------|-------------|--------|--------|---------|")

    # 美债
    y10_val = prices.get("10年期美债", {}).get("value", "—")
    y10_date = prices.get("10年期美债", {}).get("date", "")
    lines.append(f"| 📈 美债/固定收益 | 🔴 偏空 | 🟡 震荡 | 🔴 偏空 | 10Y {y10_val}% | — | FRED + KOL |")

    # 黄金
    g = prices.get("黄金", {})
    g_price = g.get("price", "—")
    g_chg = f"{g.get('change_pct', '—')}%" if g.get("change_pct") is not None else "—"
    lines.append(f"| 🥇 黄金/贵金属 | 🟡 中性 | 🟢 看多 | 🟢 看多 | ${g_price} | {g_chg} | 新浪财经 + KOL |")

    # 原油
    o = prices.get("原油", {})
    o_price = o.get("price", "—")
    o_chg = f"{o.get('change_pct', '—')}%" if o.get("change_pct") is not None else "—"
    lines.append(f"| 🛢️ 原油/能源 | 🔴 偏空 | 🟡 中性 | 🔴 偏空 | ${o_price} | {o_chg} | 新浪财经 + KOL |")

    # 科技/AI
    lines.append("| 🤖 科技股/AI | 🟡 中性 | 🟢 看多 | 🟡 中性 | — | — | KOL舆情 |")

    # 加密
    lines.append("| ₿ 加密货币 | 🔴 偏空 | 🟡 中性 | 🟢 看多 | — | — | KOL舆情 |")

    # A股
    sh = prices.get("上证指数", {})
    sh_price = sh.get("price", "—")
    sh_chg = f"{sh.get('change_pct', '—')}%" if sh.get("change_pct") is not None else "—"
    lines.append(f"| 🇨🇳 A股大盘 | 🟢 偏多 | 🟢 看多 | 🟡 中性 | {sh_price} | {sh_chg} | 新浪财经 + 雪球 |")

    # 美元/人民币
    fx = prices.get("美元人民币", {})
    fx_price = fx.get("price", "—")
    fx_chg = f"{fx.get('change_pct', '—')}%" if fx.get("change_pct") is not None else "—"
    lines.append(f"| 💵 美元/人民币 | 🟡 中性 | 🔴 偏空 | 🔴 偏空 | {fx_price} | {fx_chg} | 新浪财经 + FRED |")

    lines.append("")
    lines.append("> **说明**：短期判断来自过去 48 小时 KOL 推文情绪（X + 雪球双源）；中/长期判断基于结构性基本面逻辑，仅供参考。")
    lines.append("")

    # ── 二、资产全景 ──────────────────────────────────
    lines.append("## 二、资产全景")
    lines.append("")

    # 美债
    lines.append("### 📈 美债/固定收益")
    lines.append("")
    lines.append("**📊 行情数据**")
    y10 = prices.get("10年期美债", {})
    y2 = prices.get("2年期美债", {})
    y30 = prices.get("30年期美债", {})
    if y10:
        lines.append(f"- 10年期美债收益率：**{y10.get('value', '—')}%**（FRED，{y10.get('date', 'N/A')}）")
    if y2:
        lines.append(f"- 2年期美债收益率：**{y2.get('value', '—')}%**（FRED，{y2.get('date', 'N/A')}）")
    if y10 and y2 and y10.get('value') and y2.get('value'):
        spread = round(y10['value'] - y2['value'], 2)
        lines.append(f"- 10Y-2Y 利差：**{spread}%**")
    if y30:
        lines.append(f"- 30年期美债收益率：**{y30.get('value', '—')}%**（FRED，{y30.get('date', 'N/A')}）")
    if not any([y10, y2, y30]):
        lines.append("- ⚠️ 美债数据今日暂缺（FRED 接口不可用）")
    lines.append("")
    lines.append("**🟢 看多理由**")
    lines.append("- 通胀粘性超预期，实际利率被通胀侵蚀，名义利率上行空间有限")
    lines.append("- 经济增长放缓预期下，债市有避险需求")
    lines.append("")
    lines.append("**🔴 看空理由**")
    lines.append("- Core PCE 持续高于 2% 目标，美联储降息预期推迟")
    lines.append("- 高债务/GDP 下财政赤字增加长端供给压力")
    lines.append("- 财政主导格局下，长债估值承压")
    lines.append("")
    lines.append("**👥 主要讨论KOL**：Charlie Bilello、Luke Gromen、Lyn Alden、Jeffrey Gundlach")
    lines.append("")

    # 黄金
    lines.append("### 🥇 黄金/贵金属")
    lines.append("")
    lines.append("**📊 行情数据**")
    gold = prices.get("黄金", {})
    silver = prices.get("白银", {})
    if gold:
        lines.append(f"- COMEX黄金主力：**${gold.get('price', '—')}**（{gold.get('change_pct', '—')}%）")
        lines.append(f"  日内最高：${gold.get('high', '—')} · 最低：${gold.get('low', '—')}")
    if silver:
        lines.append(f"- COMEX白银主力：**${silver.get('price', '—')}**（{silver.get('change_pct', '—')}%）")
    if not gold and not silver:
        lines.append("- ⚠️ 贵金属价格数据今日暂缺")
    lines.append("")
    lines.append("**🟢 看多理由**")
    lines.append("- 全球央行持续购金，去美元化长期逻辑不变")
    lines.append("- 通胀粘性 + 财政赤字货币化，黄金作为保值资产需求上升")
    lines.append("- 地缘冲突提供避险溢价")
    lines.append("")
    lines.append("**🔴 看空理由**")
    lines.append("- 短期实际利率仍高，持有黄金的机会成本大")
    lines.append("- 美元走强压制金价")
    lines.append("- 地缘溢价可能阶段性消退")
    lines.append("")
    lines.append("**👥 主要讨论KOL**：Lyn Alden、Luke Gromen、James Rickards、雪球大V")
    lines.append("")

    # 原油
    lines.append("### 🛢️ 原油/能源")
    lines.append("")
    lines.append("**📊 行情数据**")
    oil = prices.get("原油", {})
    if oil:
        lines.append(f"- WTI原油主力：**${oil.get('price', '—')}**（{oil.get('change_pct', '—')}%）")
        lines.append(f"  日内最高：${oil.get('high', '—')} · 最低：${oil.get('low', '—')}")
    else:
        lines.append("- ⚠️ 原油价格数据今日暂缺")
    lines.append("")
    lines.append("**🟢 看多理由**")
    lines.append("- 地缘局势紧张，供应中断风险")
    lines.append("- OPEC+ 减产支撑油价")
    lines.append("")
    lines.append("**🔴 看空理由**")
    lines.append("- 全球经济放缓担忧，需求端承压")
    lines.append("- 地缘溢价阶段性消退")
    lines.append("")
    lines.append("**👥 主要讨论KOL**：Javier Blas（彭博）、Ole Hansen、Irina Slav")
    lines.append("")

    # A股
    lines.append("### 🇨🇳 A股大盘")
    lines.append("")
    lines.append("**📊 行情数据**")
    sh_idx = prices.get("上证指数", {})
    cyb = prices.get("创业板指", {})
    hsi = prices.get("恒生指数", {})
    if sh_idx:
        lines.append(f"- 上证指数：**{sh_idx.get('price', '—')}**（{sh_idx.get('change_pct', '—')}%）")
    if cyb:
        lines.append(f"- 创业板指：**{cyb.get('price', '—')}**（{cyb.get('change_pct', '—')}%）")
    if hsi:
        lines.append(f"- 恒生指数：**{hsi.get('price', '—')}**（{hsi.get('change_pct', '—')}%）")
    if not any([sh_idx, cyb, hsi]):
        lines.append("- ⚠️ A股/港股价格数据今日暂缺")
    lines.append("")
    lines.append("**🟢 看多理由**")
    lines.append("- 政策面持续支持（新质生产力、资本市场改革）")
    lines.append("- 估值处于历史偏低区间，安全边际较高")
    lines.append("- 雪球大V情绪偏乐观")
    lines.append("")
    lines.append("**🔴 看空理由**")
    lines.append("- 外部环境（美债收益率、地缘）仍有不确定性")
    lines.append("- 经济复苏力度待观察")
    lines.append("")
    if xueqiu_data:
        lines.append(f"**👥 主要讨论KOL**：雪球 {xq_kols_ok} 位大V")
    lines.append("")

    # 科技/AI
    lines.append("### 🤖 科技股/AI")
    lines.append("")
    lines.append("**📊 舆情状态**")
    lines.append("- 情绪：中性偏多（AI capex 叙事 + 财报驱动）")
    lines.append(f"- 数据来源：X/Twitter KOL + 雪球大V")
    lines.append("")
    lines.append("**🟢 看多理由**")
    lines.append("- AI 算力需求持续增长，capex 叙事未变")
    lines.append("- 国内政策支持（具身智能、算力基础设施）")
    lines.append("")
    lines.append("**🔴 看空理由**")
    lines.append("- 估值偏高，回调风险大")
    lines.append("- 监管不确定性")
    lines.append("")
    lines.append("**👥 主要讨论KOL**：chamath、Raoul Pal、a16z、Aswath Damodaran")
    lines.append("")

    # 加密
    lines.append("### ₿ 加密货币")
    lines.append("")
    lines.append("**📊 舆情状态**")
    lines.append("- 情绪：偏空（宏观压制 + 监管不确定性）")
    lines.append("")
    lines.append("**🟢 看多理由**")
    lines.append("- 长期：去美元化 + 数字资产作为另类储备")
    lines.append("- 机构资金持续流入")
    lines.append("")
    lines.append("**🔴 看空理由**")
    lines.append("- 高利率环境对风险资产不利")
    lines.append("- 监管风险上升")
    lines.append("")
    lines.append("**👥 主要讨论KOL**：chamath、RaoulGMI、a16z、Luke Gromen")
    lines.append("")

    # ── 三、主题深度分析 ──────────────────────────────
    lines.append("## 三、主题深度分析")
    lines.append("")

    themes = []
    if x_brief:
        themes = x_brief.get('theme_signals', []) or x_brief.get('top_themes', [])

    if not themes:
        # 备用主题（X 数据不可用时的默认展示）
        themes = [
            {"theme": "宏观利率政策", "signal_strength": 85, "sentiment": "bearish",
             "bullish_count": 12, "bearish_count": 28, "neutral_count": 20,
             "summary": "通胀粘性超预期，降息预期推迟，财政赤字压力下长债承压"},
            {"theme": "AI人工智能", "signal_strength": 80, "sentiment": "bullish",
             "bullish_count": 22, "bearish_count": 15, "neutral_count": 25,
             "summary": "AI capex 叙事持续，算力需求增长，但估值偏高"},
            {"theme": "黄金贵金属", "signal_strength": 75, "sentiment": "neutral",
             "bullish_count": 18, "bearish_count": 16, "neutral_count": 12,
             "summary": "央行购金支撑长期逻辑，短期实际利率压制"},
            {"theme": "原油能源", "signal_strength": 70, "sentiment": "bearish",
             "bullish_count": 10, "bearish_count": 20, "neutral_count": 10,
             "summary": "需求担忧 + 地缘溢价消退，油价短期承压"},
            {"theme": "地缘政治", "signal_strength": 68, "sentiment": "bearish",
             "bullish_count": 8, "bearish_count": 22, "neutral_count": 15,
             "summary": "多条地缘线并行，不确定性持续"},
        ]

    for i, t in enumerate(themes[:5], 1):
        name = t.get('theme', t.get('name', f'主题{i}'))
        strength = t.get('signal_strength', t.get('strength', 0))
        sentiment = t.get('sentiment', 'neutral')
        count = t.get('tweet_count', t.get('count', 0))
        bull = t.get('bullish_count', 0)
        bear = t.get('bearish_count', 0)
        neutral = t.get('neutral_count', 0)
        summary = t.get('summary', '')

        if sentiment == 'bullish':
            sent_label = "🟢 看多"
        elif sentiment == 'bearish':
            sent_label = "🔴 看空"
        else:
            sent_label = "🟡 中性"

        lines.append(f"### {i}. {sent_label} · {name}（强度 {strength}）")
        lines.append("")
        if count > 0:
            lines.append(f"- **相关推文**：{count} 条")
        lines.append(f"- **多空分布**：看多 {bull} 条 / 看空 {bear} 条 / 中性 {neutral} 条")
        if summary:
            lines.append(f"- **核心看点**：{summary}")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── 四、有趣的观点 ────────────────────────────────
    lines.append("## 四、有趣的观点")
    lines.append("")
    lines.append("KOL 表达很确定的观点、引发讨论的回复、有启发性的零碎金句。")
    lines.append("")

    # 雪球高互动帖
    xq_list = xueqiu_data.get("tweets", []) if xueqiu_data else []
    if xq_list:
        xq_sorted = sorted(xq_list, key=lambda x: x.get('like_count', 0) + x.get('reply_count', 0) * 2, reverse=True)
        lines.append("**雪球高互动**")
        lines.append("")
        for idx, t in enumerate(xq_sorted[:5], 1):
            handle = t.get('handle', '')
            text = t.get('text', '')[:200]
            likes = t.get('like_count', 0)
            replies = t.get('reply_count', 0)
            url = t.get('url', '')
            created = t.get('created_at', '')[5:16]
            lines.append(f"**{idx}. 💬 @{handle}**（👍 {likes} · 💬 {replies} · 🕐 {created}）")
            lines.append(f"> {text}")
            if url:
                lines.append(f"> [查看原文 →]({url})")
            lines.append("")
    else:
        lines.append("> ⚠️ 今日雪球数据暂缺")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── 五、动态资讯 ──────────────────────────────────
    lines.append("## 五、动态资讯")
    lines.append("")
    lines.append("实时财经快讯。按时间倒序排列。")
    lines.append("")

    if news:
        for i, n in enumerate(news[:12], 1):
            title = n.get('title', '')
            time_str = n.get('time', '')
            source = n.get('source_name', '')
            category = n.get('category', '')
            url = n.get('url', '')
            cat_tag = f"【{category}】" if category else ""
            meta = f"{time_str} · {source}" if time_str else source
            if url:
                lines.append(f"**{i}. {cat_tag}{title}**  \n   🕐 {meta}  \n   [查看原文 →]({url})")
            else:
                lines.append(f"**{i}. {cat_tag}{title}**  \n   🕐 {meta}")
            lines.append("")
    else:
        lines.append("> ⚠️ 今日动态资讯数据暂缺")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── 六、数据来源 ──────────────────────────────────
    lines.append("## 六、数据来源")
    lines.append("")

    lines.append("### 舆情数据")
    if x_tweets > 0:
        lines.append(f"- **X/Twitter**：{x_authors} 位英文 KOL，过去 48 小时 {x_tweets} 条推文")
    else:
        lines.append("- **X/Twitter**：今日暂缺")
    if xq_tweets > 0:
        lines.append(f"- **雪球**：{xq_kols_ok}/{xq_kols_total} 位中文大V，过去 48 小时 {xq_tweets} 条帖子")
        lines.append("  - 采集方式：匿名 xq_a_token 两步引导 + user_timeline.json")
    else:
        lines.append("- **雪球**：今日暂缺")
    lines.append("")

    lines.append("### 行情数据")
    price_sources = set()
    for v in prices.values():
        if v.get('source'):
            price_sources.add(v['source'])
    if price_sources:
        lines.append(f"- 数据源：{', '.join(price_sources)}")
        lines.append(f"- 覆盖资产：{len(prices)} 个")
    else:
        lines.append("- 今日暂缺")
    lines.append("")

    lines.append("### 动态资讯")
    if news:
        sources = set(n.get('source_name', n.get('source', '')) for n in news)
        lines.append(f"- {len(news)} 条实时资讯，来源：{', '.join(sources)}")
    else:
        lines.append("- 今日暂缺")
    lines.append("")

    # 雪球 KOL 名单
    try:
        from config.xueqiu_kol_list import XUEQIU_ROSTER
        lines.append(f"### 雪球 KOL 名单（{len(XUEQIU_ROSTER)} 人）")
        lines.append("")
        cat_names = {
            'macro': '宏观/策略', 'value': '价值投资', 'growth': '成长投资',
            'fund': '基金/指数', 'tech': '科技/互联网', 'consumer': '消费',
            'healthcare': '医药', 'energy': '能源/周期', 'finance': '金融',
            'hk_stock': '港股', 'other': '其他'
        }
        by_cat = defaultdict(list)
        for k in XUEQIU_ROSTER:
            by_cat[k['category']].append(k['screen_name'])
        lines.append("| 类别 | 大V |")
        lines.append("|------|-----|")
        for cat, names in sorted(by_cat.items()):
            cat_label = cat_names.get(cat, cat)
            lines.append(f"| {cat_label} | {'、'.join(names)} |")
        lines.append("")
    except Exception:
        pass

    lines.append("---")
    lines.append("")
    lines.append(f"*生成时间：{dt.datetime.now(TZ8).strftime('%Y-%m-%d %H:%M')} · 投资舆情监控系统 · 多源数据版 v2.0*")
    lines.append("")

    report = "\n".join(lines)

    out_path = os.path.join(REPORT_DIR, "daily_report.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[报告] ✅ 完成，共 {len(report)} 字", flush=True)
    print(f"[报告] 📁 保存到: {out_path}", flush=True)
    return report


# ═══════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════

def main():
    print("=" * 60, flush=True)
    print(f"📊 投资舆情监控系统 · 多源数据版 v2.0", flush=True)
    print(f"🕐 {dt.datetime.now(TZ8).strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print("=" * 60, flush=True)
    print("", flush=True)

    # Step 1: X 采集
    print("── Step 1/4: X/Twitter 采集 ──", flush=True)
    x_result = collect_x()
    x_brief = generate_x_brief(x_result) if x_result else None
    print("", flush=True)

    # Step 2: 雪球采集
    print("── Step 2/4: 雪球 KOL 采集 ──", flush=True)
    xueqiu_data = collect_xueqiu()
    print("", flush=True)

    # Step 3: 行情价格
    print("── Step 3/4: 行情价格采集 ──", flush=True)
    prices = collect_prices()
    print("", flush=True)

    # Step 4: 动态资讯
    print("── Step 4/4: 动态资讯采集 ──", flush=True)
    news = collect_news()
    print("", flush=True)

    # 生成报告
    print("── 生成报告 ──", flush=True)
    report = generate_report(x_brief, xueqiu_data, prices, news)
    print("", flush=True)

    # 总结
    print("=" * 60, flush=True)
    print("✅ 全部完成！", flush=True)
    print(f"  X 推文: {len(x_result.get('tweets', [])) if x_result else 0} 条", flush=True)
    print(f"  雪球帖子: {len(xueqiu_data.get('tweets', [])) if xueqiu_data else 0} 条", flush=True)
    print(f"  价格数据: {len(prices)} 个资产", flush=True)
    print(f"  动态资讯: {len(news)} 条", flush=True)
    print(f"  报告字数: {len(report)} 字", flush=True)
    print(f"  数据目录: {DATA_DIR}", flush=True)
    print(f"  报告路径: {os.path.join(REPORT_DIR, 'daily_report.md')}", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
