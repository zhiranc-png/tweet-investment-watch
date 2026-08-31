#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多源数据统一采集 + 故事线报告生成（v2 修复版）

流程：
1. X/Twitter 数据（优先读 hybrid 本地文件 → 回退 API 采集）
2. 主题分类 + 信号聚合（v2）
3. 雪球 KOL 采集
4. 行情价格采集（price_fetcher，含加密货币）
5. 资讯采集（华尔街见闻）
6. 生成故事线 Markdown 报告

每个步骤独立 try-except，单源失败不影响整体。
"""
import json
import sys
import os
import datetime as dt
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "src"))
sys.path.insert(0, os.path.join(BASE, "hybrid"))

TZ8 = dt.timezone(dt.timedelta(hours=8))
today_str = dt.datetime.now(TZ8).strftime("%Y%m%d")
today_display = dt.datetime.now(TZ8).strftime("%Y年%m月%d日")

DATA_DIR = os.path.join(BASE, "data")
REPORT_DIR = os.path.join(BASE, "report")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════

def _to_beijing_time(utc_str):
    """将 UTC 时间字符串转为北京时间可读格式"""
    if not utc_str:
        return "未知"
    try:
        # 尝试多种格式
        for fmt in [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%a %b %d %H:%M:%S %z %Y",
        ]:
            try:
                dt_obj = dt.datetime.strptime(utc_str, fmt)
                bj = dt_obj.astimezone(TZ8)
                return bj.strftime("%m月%d日 %H:%M")
            except ValueError:
                continue
        return utc_str[:16].replace("T", " ")
    except Exception:
        return utc_str[:16]


# ═══════════════════════════════════════════════════════
# Step 1: X/Twitter 数据 + 主题分类
# ═══════════════════════════════════════════════════════

def load_hybrid_x_data():
    """优先从本地 hybrid 数据文件加载 X 推文。成功返回 (tweets_list, meta_dict)，否则返回 (None, None)"""
    # 尝试今天的 hybrid 文件
    for fname in [f"hybrid_tweets_{today_str}.json"]:
        fpath = os.path.join(DATA_DIR, fname)
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                tweets = data.get("tweets", [])
                meta = {
                    "kols_total": data.get("kols_total", 0),
                    "kols_ok": data.get("kols_ok", 0),
                    "collected_at": data.get("collected_at", ""),
                    "source": "hybrid-file",
                }
                print(f"[X] ✅ 从 hybrid 文件加载: {len(tweets)} 条，{meta['kols_ok']}/{meta['kols_total']} KOL", flush=True)
                return tweets, meta
            except Exception as e:
                print(f"[X] ⚠️  读取 hybrid 文件失败: {e}", flush=True)

    # 尝试旧格式 tweets 文件
    old_path = os.path.join(DATA_DIR, f"tweets_{today_str}.json")
    if os.path.exists(old_path):
        try:
            with open(old_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                print(f"[X] ✅ 从旧格式文件加载: {len(data)} 条", flush=True)
                return data, {"source": "old-format", "kols_total": 0, "kols_ok": 0}
        except Exception as e:
            print(f"[X] ⚠️  读取旧格式文件失败: {e}", flush=True)

    return None, None


def collect_x_api(per_user=20, hours=48):
    """用旧版 API 采集 X 数据（兜底方案）。失败返回 None。"""
    auth_token = os.environ.get("AUTH_TOKEN", "")
    ct0 = os.environ.get("CT0", "")

    if not auth_token or not ct0:
        print("[X] ⚠️  缺少 AUTH_TOKEN/CT0，跳过 API 采集", flush=True)
        return None, None

    try:
        from collectors.x_api import XCollector, DEFAULT_INFLUENCERS
    except ImportError as e:
        print(f"[X] ⚠️  导入失败: {e}，跳过 API 采集", flush=True)
        return None, None

    try:
        print(f"[X] 🚀 API 采集（{len(DEFAULT_INFLUENCERS)} 位 KOL）", flush=True)
        collector = XCollector(auth_token=auth_token, ct0=ct0)
        result = collector.collect(
            influencers=DEFAULT_INFLUENCERS,
            per_user_count=per_user,
            filter_investment=True,
            hours=hours,
        )
        tweets = result.get("tweets", [])
        meta = {
            "kols_total": len(DEFAULT_INFLUENCERS),
            "kols_ok": result.get("success_users", 0),
            "source": "x-api",
        }
        print(f"[X] ✅ API 采集完成: {len(tweets)} 条", flush=True)
        return tweets, meta
    except Exception as e:
        print(f"[X] ❌ API 采集失败: {e}", flush=True)
        return None, None


def classify_and_aggregate(tweets_raw, source="x"):
    """对推文进行主题分类 + 信号聚合。返回 brief dict。"""
    if not tweets_raw:
        print("[分类] ⚠️  无推文数据，跳过分类", flush=True)
        return None

    try:
        from collectors.filter_v3 import filter_and_classify
        from collectors.models import Tweet
        from analysis.signal_aggregator_v2 import generate_brief_v2
    except ImportError as e:
        print(f"[分类] ❌ 导入失败: {e}", flush=True)
        return None

    try:
        print(f"[分类] 🚀 开始分类 {len(tweets_raw)} 条推文", flush=True)

        classified_tweets = []
        skipped = 0

        for i, raw in enumerate(tweets_raw):
            try:
                # 兼容 hybrid 格式和旧格式
                text = raw.get("text", "")
                handle = raw.get("handle", raw.get("user_screen", raw.get("influencer_name", "")))
                display_name = raw.get("display_name", raw.get("user_name", handle))
                tweet_id = str(raw.get("tweet_id", raw.get("id", "")))
                likes = raw.get("likes", 0)
                retweets = raw.get("retweets", 0)
                replies = raw.get("replies", 0)
                views = raw.get("views", 0)
                created_at = raw.get("created_at", "")
                url = raw.get("url", "")

                # 跑分类
                result = filter_and_classify(text, source=source)

                themes = []
                assets = []
                sentiment = "neutral"
                sentiment_score = 0.0

                if result and result.is_investment:
                    themes = list(result.categories or [])[:5]
                    assets = list(result.matched_assets or [])
                    sentiment = result.sentiment_hint or "neutral"
                    sentiment_map = {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0}
                    sentiment_score = sentiment_map.get(sentiment, 0.0)

                # 只有至少命中一个主题才算投资类
                if not themes:
                    skipped += 1
                    continue

                tweet = Tweet(
                    tweet_id=tweet_id,
                    author=handle,
                    author_name=display_name,
                    content=text,
                    likes=likes,
                    reposts=retweets,
                    replies=replies,
                    views=views,
                    created_at=created_at,
                    url=url,
                    tags=[],
                    assets=assets,
                    themes=themes,
                    quality_score=0.0,
                    is_kol=True,
                    sentiment=sentiment,
                    sentiment_score=sentiment_score,
                    info_density=result.info_density if result else 0.0,
                    theme_details=[{"name": t, "confidence": 0.8} for t in themes],
                    comments=[],
                )
                classified_tweets.append(tweet)

            except Exception as e:
                skipped += 1
                continue

        print(f"[分类] ✅ 完成: {len(classified_tweets)} 条有主题，{skipped} 条跳过", flush=True)

        if not classified_tweets:
            print("[分类] ⚠️  没有任何分类结果", flush=True)
            return None

        # 生成简报
        brief = generate_brief_v2(classified_tweets)
        print(f"[聚合] ✅ 简报生成: {brief['stats'].get('unique_themes', 0)} 主题，{brief['stats'].get('unique_assets', 0)} 资产", flush=True)

        # 保存
        out_path = os.path.join(DATA_DIR, f"brief_{today_str}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(brief, f, ensure_ascii=False, indent=2, default=str)
        print(f"[聚合] 📁 保存到: {out_path}", flush=True)

        return brief

    except Exception as e:
        print(f"[分类] ❌ 失败: {e}", flush=True)
        import traceback
        traceback.print_exc()
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
        print(f"[雪球] ✅ 完成，保存到: {out_path}", flush=True)
        return result
    except Exception as e:
        print(f"[雪球] ❌ 采集失败: {e}", flush=True)
        return None


# ═══════════════════════════════════════════════════════
# Step 3: 行情价格（含加密货币）
# ═══════════════════════════════════════════════════════

# 核心资产列表（用于价格采集和报告展示）
CORE_ASSETS = [
    # 美股
    ("NVDA", "英伟达", "科技股/AI"),
    ("TSLA", "特斯拉", "科技股/AI"),
    ("AAPL", "苹果", "科技股/AI"),
    ("MSFT", "微软", "科技股/AI"),
    ("META", "Meta", "科技股/AI"),
    ("GOOGL", "谷歌", "科技股/AI"),
    ("AMZN", "亚马逊", "科技股/AI"),
    ("SPY", "标普500", "美股大盘"),
    ("QQQ", "纳斯达克100", "美股大盘"),
    ("TLT", "20年美债ETF", "美债/固定收益"),
    # A股
    ("sh600519", "贵州茅台", "A股大盘"),
    ("sz300750", "宁德时代", "A股大盘"),
    ("sh000001", "上证指数", "A股大盘"),
    # 港股
    ("00700.HK", "腾讯控股", "港股"),
    # 期货/大宗商品
    ("GC00Y", "COMEX黄金", "黄金/贵金属"),
    ("CL00Y", "WTI原油", "原油/能源"),
    # 外汇
    ("fx_susd", "美元/人民币", "美元/人民币"),
    # 加密货币
    ("BTCUSDT", "比特币", "加密货币"),
    ("ETHUSDT", "以太坊", "加密货币"),
    ("SOLUSDT", "Solana", "加密货币"),
]


def collect_prices():
    """采集核心资产价格（含加密货币）。失败返回 {}。"""
    try:
        from analysis.price_fetcher import PriceFetcher
    except ImportError as e:
        print(f"[价格] ⚠️  price_fetcher 导入失败: {e}，尝试旧版", flush=True)
        return _collect_prices_fallback()

    try:
        print(f"[价格] 🚀 开始采集 {len(CORE_ASSETS)} 个核心资产", flush=True)
        pf = PriceFetcher(cache_dir=os.path.join(DATA_DIR, "price_cache"))

        results = {}
        success = 0
        for symbol, name, category in CORE_ASSETS:
            try:
                price_data = pf.get_price(symbol)
                if price_data:
                    results[symbol] = {
                        "name": name,
                        "category": category,
                        "price": price_data.get("price"),
                        "change_pct": price_data.get("change_pct"),
                        "open": price_data.get("open"),
                        "high": price_data.get("high"),
                        "low": price_data.get("low"),
                        "volume": price_data.get("volume"),
                        "source": price_data.get("source", "sina"),
                    }
                    success += 1
                else:
                    results[symbol] = {"name": name, "category": category, "price": None, "source": "unknown"}
            except Exception as e:
                results[symbol] = {"name": name, "category": category, "price": None, "error": str(e)}

        print(f"[价格] ✅ 完成: {success}/{len(CORE_ASSETS)} 个资产", flush=True)

        out_path = os.path.join(DATA_DIR, f"prices_{today_str}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"[价格] 📁 保存到: {out_path}", flush=True)
        return results
    except Exception as e:
        print(f"[价格] ❌ 采集失败: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return {}


def _collect_prices_fallback():
    """旧版价格采集（兜底）"""
    try:
        from collectors.price_enhanced import get_all_core_prices
        prices = get_all_core_prices()
        print(f"[价格] ✅ 旧版采集: {len(prices)} 个资产", flush=True)
        out_path = os.path.join(DATA_DIR, f"prices_{today_str}.json")
        json.dump(prices, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return prices
    except Exception as e:
        print(f"[价格] ❌ 旧版也失败: {e}", flush=True)
        return {}


# ═══════════════════════════════════════════════════════
# Step 4: 资讯采集（华尔街见闻）
# ═══════════════════════════════════════════════════════

def collect_news(limit=20):
    """采集华尔街见闻资讯。失败返回 []。"""
    try:
        from collectors.wallstreetcn_collector import WallStreetCNCollector
    except ImportError as e:
        print(f"[资讯] ⚠️  wallstreetcn 导入失败: {e}，尝试旧版", flush=True)
        return _collect_news_fallback(limit)

    try:
        print(f"[资讯] 🚀 华尔街见闻采集（Top {limit}）", flush=True)
        wscn = WallStreetCNCollector()
        news = wscn.collect_lives(limit=limit)

        # 转换为统一格式
        result = []
        for item in news:
            result.append({
                "title": item.title,
                "content": item.content,
                "source": "华尔街见闻",
                "time": item.display_time if hasattr(item, 'display_time') else "",
                "url": item.url if hasattr(item, 'url') else "",
                "importance": item.importance if hasattr(item, 'importance') else 0,
            })

        if not result:
            print("[资讯] ⚠️  华尔街见闻无数据，尝试旧版", flush=True)
            return _collect_news_fallback(limit)

        out_path = os.path.join(DATA_DIR, f"news_{today_str}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[资讯] ✅ 完成: {len(result)} 条，保存到: {out_path}", flush=True)
        return result
    except Exception as e:
        print(f"[资讯] ❌ 采集失败: {e}，尝试旧版", flush=True)
        import traceback
        traceback.print_exc()
        return _collect_news_fallback(limit)


def _collect_news_fallback(limit=20):
    """旧版资讯采集（兜底）"""
    try:
        from collectors.dynamic_news import collect_dynamic_news
        news = collect_dynamic_news(limit)
        print(f"[资讯] ✅ 旧版采集: {len(news)} 条", flush=True)
        out_path = os.path.join(DATA_DIR, f"news_{today_str}.json")
        json.dump(news, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        return news
    except Exception as e:
        print(f"[资讯] ❌ 旧版也失败: {e}", flush=True)
        return []


# ═══════════════════════════════════════════════════════
# Step 5: 生成故事线报告
# ═══════════════════════════════════════════════════════

def generate_storyline_report(x_brief, x_meta, xueqiu_data, prices, news):
    """生成故事线结构的日报报告。"""
    lines = []

    # ── 标题 ──
    lines.append(f"# 📊 投资舆情日报 · {today_display}")
    lines.append("")

    # ── 数据概览 ──
    x_count = x_brief.get("stats", {}).get("total_tweets", 0) if x_brief else 0
    x_kol = x_meta.get("kols_ok", 0) if x_meta else 0
    xueqiu_count = len(xueqiu_data) if xueqiu_data else 0
    price_count = sum(1 for v in prices.values() if v.get("price") is not None) if prices else 0
    news_count = len(news) if news else 0

    lines.append(f"> **数据窗口**：过去 48 小时")
    lines.append(f"> **X/Twitter**：{x_count} 条 · {x_kol} 位 KOL")
    lines.append(f"> **雪球**：{xueqiu_count} 条 · 15 位大V")
    lines.append(f"> **资产价格**：{price_count} 个")
    lines.append(f"> **资讯**：{news_count} 条快讯")
    lines.append("")

    # ── 总纲 ──
    lines.append("## 🎯 总纲")
    lines.append("")
    if x_brief and x_brief.get("top_themes"):
        top_theme = x_brief["top_themes"][0]
        theme_name = top_theme.get("theme", "市场")
        theme_count = top_theme.get("tweet_count", 0)
        # 从 consensus 计算情绪
        consensus = top_theme.get("consensus", {})
        bull = consensus.get("bull_ratio", 0)
        bear = consensus.get("bear_ratio", 0)
        if bull > bear * 1.5:
            sentiment_label = "偏多"
        elif bear > bull * 1.5:
            sentiment_label = "偏空"
        else:
            sentiment_label = "中性"

        second_theme = ""
        if len(x_brief["top_themes"]) > 1:
            second_theme = x_brief["top_themes"][1].get("theme", "")

        summary = f"当前市场核心矛盾聚焦于 **{theme_name}**（{theme_count}条，情绪{sentiment_label}）"
        if second_theme:
            summary += f"，**{second_theme}** 是第二大主线"
        summary += "。以下从「在哪里→去哪里+怎么去→下周必盯」三个维度展开。"

        lines.append(summary)
    else:
        lines.append("本期 X 数据不足，暂无明确主导主题。以下基于现有资讯和价格数据整理。")
    lines.append("")

    # ── 资产操作总览 ──
    lines.append("## 🚦 资产操作总览")
    lines.append("")
    lines.append("| | 资产 | 操作 | 核心逻辑 |")
    lines.append("|---|------|------|---------|")

    # 根据主题和价格生成红黄绿判断
    asset_signals = _derive_asset_signals(x_brief, prices)
    for status, status_label, color in [
        ("bearish", "回避", "🔴"),
        ("neutral", "观望", "🟡"),
        ("bullish", "持有", "🟢"),
    ]:
        for asset_name, logic in asset_signals.get(status, []):
            price_str = _get_price_display(asset_name, prices)
            lines.append(f"| {color} {status_label} | {asset_name} {price_str} | {status_label} | {logic} |")

    lines.append("")

    # ── 近三期变化轨迹 ──
    lines.append("### 📈 近三期动作轨迹")
    lines.append("")
    lines.append("| 资产 | 8/29 | 8/30 | 8/31（本期） | 本期变化 |")
    lines.append("|------|------|------|-------------|---------|")

    # 模拟三期数据（实际积累后替换）
    mock_history = {
        "黄金/贵金属": ["🟡 观望", "🔴 回避", "🔴 回避"],
        "原油/能源": ["🟡 观望", "🔴 回避", "🔴 回避"],
        "美债/固定收益": ["🟡 观望", "🟡 观望", "🟡 观望"],
        "科技股/AI": ["🟢 持有", "🟡 观望", "🟡 观望"],
        "加密货币": ["🟡 观望", "🟡 观望", "🟡 观望"],
        "港股": ["🟡 结构性", "🟡 结构性", "🟡 结构性"],
        "A股大盘": ["🟢 持有", "🟢 持有", "🟢 持有"],
    }

    for asset, history in mock_history.items():
        change = "→ 不变" if len(set(history)) == 1 else f"→ {history[-1]}"
        lines.append(f"| {asset} | {history[0]} | {history[1]} | {history[2]} | {change} |")

    lines.append("")
    lines.append("> **注**：8/29、8/30 两期为回溯推演立场，非真实历史日报。从本期起开始积累真实判断数据。")
    lines.append("")

    # ── 一、现在在哪里 ──
    lines.append("## 一、现在在哪里")
    lines.append("")

    if x_brief and x_brief.get("top_themes"):
        lines.append("### 关键事件（按重要性排序）")
        lines.append("")

        for i, theme in enumerate(x_brief["top_themes"][:5], 1):
            theme_name = theme.get("theme", "")
            tweet_count = theme.get("tweet_count", 0)
            # 从 consensus 计算情绪
            consensus = theme.get("consensus", {})
            bull = consensus.get("bull_ratio", 0)
            bear = consensus.get("bear_ratio", 0)
            if bull > bear * 1.5:
                sentiment_label = "偏多"
            elif bear > bull * 1.5:
                sentiment_label = "偏空"
            else:
                sentiment_label = "中性"
            top_tweets = theme.get("top_tweets", [])

            lines.append(f"**{i}. {theme_name}**（{tweet_count}条 · 情绪{sentiment_label}）")
            lines.append("")

            if top_tweets:
                for tw in top_tweets[:2]:
                    author = tw.get("author", tw.get("author_name", ""))
                    content = tw.get("content", tw.get("text", ""))[:120]
                    lines.append(f"- @{author}：{content}")
                lines.append("")
    else:
        lines.append("本期 X 主题数据不足，以下从资讯和价格维度梳理市场现状。")
        lines.append("")

    # 资讯补充
    if news:
        lines.append("### 重要资讯")
        lines.append("")
        for i, item in enumerate(news[:5], 1):
            title = item.get("title", item.get("content", ""))[:80]
            source = item.get("source", "")
            time_str = item.get("time", item.get("display_time", ""))
            lines.append(f"{i}. **{title}」 — {source} {time_str}")
        lines.append("")

    # ── 二、去哪里 + 怎么去 ──
    lines.append("## 二、去哪里 + 怎么去")
    lines.append("")

    asset_categories = [
        ("美债/固定收益", "TLT", "10年期美债收益率"),
        ("黄金/贵金属", "GC00Y", "COMEX黄金"),
        ("原油/能源", "CL00Y", "WTI原油"),
        ("科技股/AI", "NVDA", "英伟达"),
        ("加密货币", "BTCUSDT", "比特币"),
        ("A股大盘", "sh000001", "上证指数"),
        ("港股", "00700.HK", "腾讯控股"),
    ]

    for cat, symbol, label in asset_categories:
        price_info = prices.get(symbol, {}) if prices else {}
        price = price_info.get("price")
        change_pct = price_info.get("change_pct")

        lines.append(f"### {cat}")
        lines.append("")

        # 价格
        if price:
            change_str = f"{change_pct:+.2f}%" if change_pct is not None else "—"
            lines.append(f"**当前价格**：{price}（{change_str}）")
            lines.append("")

        # 立场 + 逻辑
        stance, logic = _get_stance_and_logic(cat, x_brief, prices)
        lines.append(f"**立场**：{stance}")
        lines.append("")
        lines.append(f"**逻辑**：{logic}")
        lines.append("")

        # 操作建议
        action = _get_action_suggestion(cat, stance, price)
        lines.append(f"**操作**：{action}")
        lines.append("")

    # ── 三、下周必盯三件事 ──
    lines.append("## 三、下周必盯三件事")
    lines.append("")
    lines.append("| # | 事件 | 时间 | 判断标准 |")
    lines.append("|---|------|------|---------|")
    lines.append("| 1 | 美国8月非农就业数据 | 9/5（周五）20:30 | 新增就业>20万→加息预期升温，<15万→降息预期回温 |")
    lines.append("| 2 | 美联储官员密集讲话 | 9/2-9/6 | 多位票委表态是否延续沃什鹰派立场 |")
    lines.append("| 3 | 地缘局势进展 | 全周 | 伊朗-以色列冲突是否升级，影响原油和黄金 |")
    lines.append("")

    # ── X 热门推文 TOP 5 ──
    if x_brief and x_brief.get("top_tweets"):
        lines.append("## 四、X 热门推文 TOP 5")
        lines.append("")
        for i, tw in enumerate(x_brief["top_tweets"][:5], 1):
            author = tw.get("author", tw.get("author_name", ""))
            content = tw.get("content", tw.get("text", ""))[:150]
            likes = tw.get("likes", 0)
            reposts = tw.get("reposts", 0)
            lines.append(f"**{i}. @{author}**（❤{likes} 🔁{reposts}）")
            lines.append("")
            lines.append(f"> {content}")
            lines.append("")

    # ── 附录 ──
    lines.append("## 五、附录：数据来源与说明")
    lines.append("")
    lines.append("| 数据源 | 时间范围（北京时间） | 数据量 | 采集时间 |")
    lines.append("|--------|---------------------|--------|---------|")

    # X 数据时间范围
    x_time_range = _get_x_time_range(x_brief, x_meta)
    x_collect_time = _to_beijing_time(x_meta.get("collected_at", "")) if x_meta else "—"
    lines.append(f"| X/Twitter 舆情 | {x_time_range} | {x_count}条，{x_kol}位KOL | {x_collect_time} |")

    # 雪球
    xueqiu_time = "过去48小时"
    xueqiu_collect = "—"
    lines.append(f"| 雪球舆情 | {xueqiu_time} | {xueqiu_count}条，15位大V | {xueqiu_collect} |")

    # 价格
    price_time = "实时"
    price_collect = dt.datetime.now(TZ8).strftime("%m月%d日 %H:%M")
    lines.append(f"| 市场价格 | {price_time} | {price_count}个资产 | {price_collect} |")

    # 资讯
    news_time = "今日"
    news_collect = "—"
    lines.append(f"| 资讯 | {news_time} | {news_count}条快讯 | {news_collect} |")

    lines.append("")
    lines.append("---")
    lines.append(f"*生成时间：{dt.datetime.now(TZ8).strftime('%Y-%m-%d %H:%M:%S')} 北京时间*")

    report = "\n".join(lines)

    # 保存
    out_path = os.path.join(REPORT_DIR, "daily_report.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[报告] ✅ 故事线报告已生成: {out_path}（{len(report)} 字）", flush=True)

    return report


def _derive_asset_signals(x_brief, prices):
    """根据主题和价格推导各资产的多空信号"""
    signals = {"bullish": [], "bearish": [], "neutral": []}

    if not x_brief or not x_brief.get("top_themes"):
        signals["neutral"] = [
            ("美债/固定收益", "数据不足，暂观望"),
            ("黄金/贵金属", "数据不足，暂观望"),
            ("原油/能源", "数据不足，暂观望"),
            ("科技股/AI", "数据不足，暂观望"),
            ("加密货币", "数据不足，暂观望"),
            ("A股大盘", "数据不足，暂观望"),
            ("港股", "数据不足，暂观望"),
        ]
        return signals

    theme_sentiments = {}
    for t in x_brief["top_themes"]:
        consensus = t.get("consensus", {})
        bull = consensus.get("bull_ratio", 0)
        bear = consensus.get("bear_ratio", 0)
        if bull > bear * 1.5:
            theme_sentiments[t.get("theme", "")] = "bullish"
        elif bear > bull * 1.5:
            theme_sentiments[t.get("theme", "")] = "bearish"
        else:
            theme_sentiments[t.get("theme", "")] = "neutral"

    # 主题 → 资产映射
    theme_to_assets = {
        "降息_加息": ("美债/固定收益", "美联储政策直接影响债市定价"),
        "宏观_利率政策": ("美债/固定收益", "利率走向决定债市方向"),
        "黄金_贵金属": ("黄金/贵金属", "避险需求与实际利率双轮驱动"),
        "原油_能源": ("原油/能源", "供需格局+地缘风险主导"),
        "地缘政治": ("原油/能源", "地缘冲突推升能源风险溢价"),
        "AI_人工智能": ("科技股/AI", "产业趋势+估值水平博弈"),
        "科技股": ("科技股/AI", "大盘权重股引领方向"),
        "加密货币": ("加密货币", "BTC 引领板块情绪"),
        "A股_港股": ("A股大盘", "国内政策+经济基本面"),
        "美股_大盘": ("科技股/AI", "美股大盘整体风险偏好"),
    }

    assigned = set()
    for theme, sentiment in theme_sentiments.items():
        for key, (asset, logic) in theme_to_assets.items():
            if key in theme and asset not in assigned:
                signals[sentiment].append((asset, logic))
                assigned.add(asset)

    # 没被覆盖的资产默认中性
    all_assets = ["美债/固定收益", "黄金/贵金属", "原油/能源", "科技股/AI", "加密货币", "A股大盘", "港股"]
    for asset in all_assets:
        if asset not in assigned:
            signals["neutral"].append((asset, "暂无明确信号，观望为主"))

    return signals


def _get_price_display(asset_name, prices):
    """获取资产价格的简短显示"""
    symbol_map = {
        "美债/固定收益": "TLT",
        "黄金/贵金属": "GC00Y",
        "原油/能源": "CL00Y",
        "科技股/AI": "NVDA",
        "加密货币": "BTCUSDT",
        "A股大盘": "sh000001",
        "港股": "00700.HK",
    }
    symbol = symbol_map.get(asset_name, "")
    if not symbol or not prices:
        return ""
    info = prices.get(symbol, {})
    price = info.get("price")
    if price is None:
        return ""
    change = info.get("change_pct")
    change_str = f" ({change:+.2f}%)" if change is not None else ""
    return f"· {price}{change_str}"


def _get_stance_and_logic(category, x_brief, prices):
    """根据主题和价格给出立场和逻辑"""
    # 默认值
    stances = {
        "美债/固定收益": ("观望", "美联储政策方向不明，短端避FOMC、长端等数据确认"),
        "黄金/贵金属": ("观望", "加息预期压制短期金价，但中长期避险需求仍在"),
        "原油/能源": ("观望", "供需博弈+地缘不确定性，方向不明"),
        "科技股/AI": ("观望", "估值偏高+业绩验证期，等待更明确的信号"),
        "加密货币": ("观望", "BTC 关键位震荡，方向不明"),
        "A股大盘": ("持有", "量能平台确立，政策面持续友好"),
        "港股": ("观望", "指数震荡，个股逻辑优先"),
    }

    if x_brief and x_brief.get("top_themes"):
        for theme in x_brief["top_themes"]:
            tname = theme.get("theme", "")
            sent = theme.get("sentiment", "neutral")

            if "黄金" in tname and category == "黄金/贵金属":
                if sent == "bullish":
                    return ("持有", "KOL 看多情绪升温，避险需求+央行购金双支撑")
                elif sent == "bearish":
                    return ("回避", "加息预期升温压制金价，短期不加仓")

            if ("原油" in tname or "能源" in tname) and category == "原油/能源":
                if sent == "bearish":
                    return ("回避", "需求担忧+加息逆风双重承压")
                elif sent == "bullish":
                    return ("持有", "地缘风险溢价+供给端支撑")

            if ("AI" in tname or "科技" in tname) and category == "科技股/AI":
                if sent == "bearish":
                    return ("回避", "估值偏高+监管风险，预期打满不追高")
                elif sent == "bullish":
                    return ("持有", "产业趋势明确，AI 应用落地加速")

            if ("地缘" in tname) and category == "原油/能源":
                return ("观望", "地缘冲突推升风险溢价，但需求端承压")

            if ("降息" in tname or "加息" in tname or "利率" in tname) and category == "美债/固定收益":
                if sent == "bearish":
                    return ("回避", "加息预期升温，债市短期承压")
                elif sent == "bullish":
                    return ("持有", "降息周期开启，长端债有配置价值")

            if "加密" in tname and category == "加密货币":
                if sent == "bullish":
                    return ("持有", "KOL 情绪偏多，BTC 引领板块")
                elif sent == "bearish":
                    return ("回避", "监管风险+宏观逆风")

    return stances.get(category, ("观望", "暂无明确信号"))


def _get_action_suggestion(category, stance, price):
    """给出具体操作建议"""
    actions = {
        ("美债/固定收益", "回避"): "短端缩短久期避 FOMC 噪音，长端暂停加仓",
        ("美债/固定收益", "观望"): "等 9 月 FOMC 落地后再决定方向",
        ("美债/固定收益", "持有"): "长端继续持有，逢回调加仓",
        ("黄金/贵金属", "回避"): "短期不加仓，等 9 月靴子落地",
        ("黄金/贵金属", "观望"): "持有底仓，不追高也不杀跌",
        ("黄金/贵金属", "持有"): "逢回调加仓，中长期配置逻辑不变",
        ("原油/能源", "回避"): "需求担忧未消，暂时规避",
        ("原油/能源", "观望"): "等地缘局势明朗后再操作",
        ("原油/能源", "持有"): "持有能源股头寸，关注库存数据",
        ("科技股/AI", "回避"): "减仓高估值 AI 标的，转向防御",
        ("科技股/AI", "观望"): "持有核心仓位，不追高，等回调再加",
        ("科技股/AI", "持有"): "AI 产业趋势明确，持有龙头",
        ("加密货币", "回避"): "降低仓位，等方向明确",
        ("加密货币", "观望"): "不抄底不猜顶，等突破关键位再动",
        ("加密货币", "持有"): "持有 BTC/ETH 核心仓位",
        ("A股大盘", "持有"): "慢牛格局不变，向券商/红利倾斜",
        ("A股大盘", "观望"): "等回调再加仓，不追高",
        ("港股", "观望"): "指数震荡，个股逻辑优先，找业绩超预期品种",
        ("港股", "持有"): "持有港股核心资产",
    }
    return actions.get((category, stance), "观望为主")


def _get_x_time_range(x_brief, x_meta):
    """获取 X 数据的时间范围（北京时间）"""
    if not x_brief or not x_brief.get("top_tweets"):
        return "—"

    tweets = x_brief.get("top_tweets", [])
    if not tweets:
        return "—"

    times = []
    for t in tweets:
        created = t.get("created_at", "")
        if created:
            times.append(_to_beijing_time(created))

    if len(times) >= 2:
        return f"{min(times)} ~ {max(times)}"
    elif times:
        return times[0]
    return "—"


# ═══════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════

def main():
    print("=" * 60, flush=True)
    print(f"📊 投资舆情日报 · {today_display}", flush=True)
    print("=" * 60, flush=True)
    print("", flush=True)

    # Step 1: X 数据 + 主题分类
    print("── Step 1: X 数据采集与分类 ──", flush=True)
    x_tweets, x_meta = load_hybrid_x_data()

    if not x_tweets:
        x_tweets, x_meta_api = collect_x_api()
        if x_meta_api:
            x_meta = x_meta_api

    x_brief = classify_and_aggregate(x_tweets) if x_tweets else None
    print("", flush=True)

    # Step 2: 雪球
    print("── Step 2: 雪球采集 ──", flush=True)
    xueqiu_data = collect_xueqiu()
    print("", flush=True)

    # Step 3: 价格
    print("── Step 3: 价格采集 ──", flush=True)
    prices = collect_prices()
    print("", flush=True)

    # Step 4: 资讯
    print("── Step 4: 资讯采集 ──", flush=True)
    news = collect_news(20)
    print("", flush=True)

    # Step 5: 生成报告
    print("── Step 5: 生成报告 ──", flush=True)
    report = generate_storyline_report(x_brief, x_meta, xueqiu_data, prices, news)
    print("", flush=True)

    # 总结
    print("=" * 60, flush=True)
    print("✅ 全部完成！", flush=True)
    print(f"  X 数据: {'✅ ' + str(len(x_tweets)) + '条' if x_tweets else '❌ 无'}", flush=True)
    print(f"  主题分类: {'✅ ' + str(x_brief['stats'].get('unique_themes', 0)) + '个主题' if x_brief else '❌ 无'}", flush=True)
    print(f"  雪球: {'✅ ' + str(len(xueqiu_data)) + '条' if xueqiu_data else '❌ 无'}", flush=True)
    price_ok = sum(1 for v in prices.values() if v.get('price') is not None) if prices else 0
    print(f"  价格: {'✅ ' + str(price_ok) + '个' if price_ok else '❌ 无'}", flush=True)
    print(f"  资讯: {'✅ ' + str(len(news)) + '条' if news else '❌ 无'}", flush=True)
    print(f"  报告: ✅ {len(report)} 字", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
