"""
报告生成器 — 生成 Markdown 格式的基础报告
（投资信号分析由 Agent 完成，这里只生成数据统计部分）

支持 v1 和 v2 两种简报格式：
- v1: top_themes + top_assets
- v2: theme_signals（主题信号+共识度+信号强度）+ top_assets + 价格联动
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def _fmt_price(price_data: dict | None) -> str:
    """格式化价格数据为可读字符串"""
    if not price_data:
        return "—"
    price = price_data.get("price", "—")
    change_pct = price_data.get("change_pct_1d")
    if change_pct is not None:
        sign = "+" if change_pct >= 0 else ""
        return f"{price} ({sign}{change_pct:.2f}%)"
    return str(price)


def _price_emoji(change_pct: float | None) -> str:
    """根据涨跌幅返回 emoji"""
    if change_pct is None:
        return ""
    if change_pct > 0:
        return "🟢"
    elif change_pct < 0:
        return "🔴"
    return "⚪"


def generate_markdown_report(brief: dict, signals: list | None = None, report_date: str = "") -> str:
    """生成 Markdown 报告"""
    if not report_date:
        report_date = datetime.now().strftime("%Y-%m-%d")

    stats = brief.get("stats", {})
    top_assets = brief.get("top_assets", [])
    top_themes = brief.get("top_themes", [])
    theme_signals = brief.get("theme_signals", [])
    kol_summary = brief.get("kol_summary", [])
    top_tweets = brief.get("top_tweets", [])
    version = brief.get("version", "1.0")
    is_v2 = version.startswith("2") or bool(theme_signals)

    lines = []

    # 标题
    lines.append(f"# 📊 推特投资舆情日报 - {report_date}")
    lines.append("")
    lines.append(f"> 生成时间：{brief.get('generated_at', 'N/A')}")
    lines.append(f"> 版本：v{version}")
    lines.append("")

    # 今日概览
    lines.append("## 📈 今日概览")
    lines.append("")
    lines.append(f"- **推文总数**: {stats.get('total_tweets', 0)} 条")
    lines.append(f"- **KOL 推文**: {stats.get('kol_tweets', 0)} 条")
    lines.append(f"- **涉及作者**: {stats.get('unique_authors', 0)} 位")
    lines.append(f"- **涉及标的**: {stats.get('unique_assets', 0)} 个")
    lines.append(f"- **涉及主题**: {stats.get('unique_themes', 0)} 个")
    lines.append(f"- **总互动量**: {stats.get('total_likes', 0) + stats.get('total_reposts', 0):,}")
    if is_v2:
        lines.append(f"- **整体情绪**: {stats.get('overall_sentiment', 'N/A')}")
        lines.append(f"- **整体共识度**: {stats.get('overall_consensus', 0):.2f}")
    if stats.get("assets_with_price"):
        lines.append(f"- **行情覆盖**: {stats.get('assets_with_price', 0)}/{stats.get('assets_total', 0)} 个标的")
    lines.append("")

    # 主题信号（v2）或热门主题（v1）
    if is_v2 and theme_signals:
        lines.append("## 🔥 主题信号（按强度排序）")
        lines.append("")
        for i, ts in enumerate(theme_signals[:10], 1):
            strength = ts.get("signal_strength", 0)
            attention = ts.get("attention_level", "medium")
            level_map = {"high": "🔴高", "medium": "🟡中", "low": "🟢低"}
            level = level_map.get(attention, "🟡中")
            consensus = ts.get("consensus_score", ts.get("consensus", 0))
            sentiment = ts.get("sentiment", "neutral")
            sentiment_emoji = {"bullish": "🟢 看多", "bearish": "🔴 看空", "neutral": "⚪ 中性"}.get(sentiment, "⚪ 中性")

            # 代表资产价格
            rep_price = ts.get("representative_price")
            price_str = ""
            if rep_price:
                price_emoji = _price_emoji(rep_price.get("change_pct_1d"))
                price_str = f" | 代表标的: {price_emoji} {_fmt_price(rep_price)}"

            lines.append(
                f"### {i}. {level} {ts.get('theme', '')}"
            )
            lines.append("")
            lines.append(
                f"- **信号强度**: {strength:.1f} | **共识度**: {consensus:.2f} | **情绪**: {sentiment_emoji}{price_str}"
            )
            lines.append(
                f"- **推文数**: {ts.get('tweet_count', 0)} | **KOL数**: {ts.get('kol_count', 0)} | **互动量**: {ts.get('engagement', 0):,}"
            )
            bull = ts.get("bullish_count", 0)
            bear = ts.get("bearish_count", 0)
            neutral = ts.get("neutral_count", 0)
            lines.append(f"- **多空分布**: 🟢{bull} / 🔴{bear} / ⚪{neutral}")
            lines.append("")

    elif top_themes:
        lines.append("## 🔥 热门主题排行")
        lines.append("")
        for i, theme in enumerate(top_themes[:8], 1):
            lines.append(f"{i}. **{theme['theme']}** — {theme['tweet_count']} 条推文，互动量 {theme['engagement']:,}")
        lines.append("")

    # 热门标的 + 价格
    if top_assets:
        lines.append("## 💹 讨论热度 Top 标的")
        lines.append("")

        # 检查是否有价格数据
        has_price = any(a.get("price_available") or a.get("price_data") for a in top_assets[:10])

        if has_price:
            lines.append("| 排名 | 标的 | 名称 | 类型 | 提及数 | 互动量 | 情绪 | 最新价 | 涨跌幅 |")
            lines.append("|------|------|------|------|--------|--------|------|--------|--------|")
            for i, asset in enumerate(top_assets[:10], 1):
                sentiment_emoji = {
                    "bullish": "🟢 看多",
                    "bearish": "🔴 看空",
                    "neutral": "⚪ 中性",
                }.get(asset.get("sentiment", ""), "⚪ 中性")

                price_data = asset.get("price_data")
                if price_data:
                    price = price_data.get("price", "—")
                    change_pct = price_data.get("change_pct_1d")
                    if change_pct is not None:
                        sign = "+" if change_pct >= 0 else ""
                        change_str = f"{sign}{change_pct:.2f}%"
                        price_emoji = _price_emoji(change_pct)
                    else:
                        change_str = "—"
                        price_emoji = ""
                else:
                    price = "—"
                    change_str = "—"
                    price_emoji = ""

                name = asset.get("name", asset.get("symbol", ""))
                atype = asset.get("asset_type", asset.get("type", ""))
                lines.append(
                    f"| {i} | {asset.get('symbol', '')} | {name} | {atype} | "
                    f"{asset.get('mention_count', 0)} | {asset.get('engagement', 0):,} | "
                    f"{sentiment_emoji} | {price_emoji} {price} | {change_str} |"
                )
        else:
            lines.append("| 排名 | 标的 | 名称 | 提及数 | 互动量 | KOL提及 | 情绪 |")
            lines.append("|------|------|------|--------|--------|---------|------|")
            for i, asset in enumerate(top_assets[:10], 1):
                sentiment_emoji = {
                    "bullish": "🟢 看多",
                    "bearish": "🔴 看空",
                    "neutral": "⚪ 中性",
                }.get(asset.get("sentiment", ""), "⚪ 中性")
                name = asset.get("name", asset.get("symbol", ""))
                lines.append(
                    f"| {i} | {asset.get('symbol', '')} | {name} | {asset.get('mention_count', 0)} | "
                    f"{asset.get('engagement', 0):,} | {asset.get('kol_mentions', 0)} | {sentiment_emoji} |"
                )
        lines.append("")

    # KOL 观点精选
    if kol_summary:
        lines.append("## 🎤 KOL 观点精选")
        lines.append("")
        for i, tweet in enumerate(kol_summary[:10], 1):
            # v2 格式：kol_summary 里是 KOL 汇总 + top_tweet
            if "top_tweet" in tweet:
                author = tweet.get("author", "")
                author_name = tweet.get("author_name", "")
                top = tweet["top_tweet"]
                content = top.get("content", "")
                url = top.get("url", "")
                likes = top.get("likes", 0)
                tweet_count = tweet.get("tweet_count", 0)
                total_eng = tweet.get("total_engagement", 0)
                assets = top.get("assets", [])
                themes = top.get("themes", [])
            else:
                # v1 格式
                author = tweet.get("author", "")
                author_name = tweet.get("author_name", "")
                content = tweet.get("content", "")
                url = tweet.get("url", "")
                likes = tweet.get("likes", 0)
                tweet_count = 1
                total_eng = likes + tweet.get("reposts", 0) + tweet.get("replies", 0)
                assets = tweet.get("assets", [])
                themes = tweet.get("themes", [])

            assets_str = ", ".join(f"{a[0]}({a[1]})" for a in assets) if assets else "—"
            themes_str = ", ".join(themes) if themes else "—"
            lines.append(f"### {i}. @{author} ({author_name})")
            lines.append("")
            lines.append(f"> {content}")
            lines.append("")
            lines.append(f"- 👍 {likes:,} 赞 · 共 {tweet_count} 条 · 总互动 {total_eng:,}")
            lines.append(f"- 🔗 [查看原文]({url})")
            lines.append(f"- 🏷️ 标的: {assets_str}")
            lines.append(f"- 📂 主题: {themes_str}")
            lines.append("")

    # 高互动推文
    if top_tweets:
        lines.append("## 💬 高互动推文")
        lines.append("")
        for i, tweet in enumerate(top_tweets[:10], 1):
            author_display = f"@{tweet['author']}"
            if tweet.get("author_name"):
                author_display = f"{tweet['author_name']} (@{tweet['author']})"
            kol_tag = " 🏆KOL" if tweet.get("is_kol") else ""
            lines.append(f"### {i}. {author_display}{kol_tag}")
            lines.append("")
            lines.append(f"> {tweet['content']}")
            lines.append("")
            lines.append(
                f"- 👍 {tweet['likes']:,} 赞 · 🔄 {tweet['reposts']:,} 转 · 💬 {tweet['replies']:,} 回复"
            )
            lines.append(f"- 🔗 [查看原文]({tweet['url']})")
            if tweet.get("top_comments"):
                lines.append(f"- 🗨️ 热门评论 ({tweet.get('comments_count', 0)} 条):")
                for c in tweet["top_comments"][:3]:
                    lines.append(f"  - @{c['author']}: {c['content'][:100]}... (👍{c['likes']})")
            lines.append("")

    # 投资信号（如果有）
    if signals:
        lines.append("## 🎯 投资信号")
        lines.append("")
        for i, sig in enumerate(signals, 1):
            signal_emoji = {
                "买入": "🟢",
                "卖出": "🔴",
                "观望": "🟡",
                "持有": "🟢",
            }.get(sig.get("signal", ""), "⚪")
            lines.append(f"### {i}. {signal_emoji} {sig.get('asset', '')} — {sig.get('signal', '')}")
            lines.append("")
            lines.append(f"- **置信度**: {sig.get('confidence', 'N/A')}")
            lines.append(f"- **理由**:")
            for reason in sig.get("reasons", []):
                lines.append(f"  - {reason}")
            if sig.get("evidence"):
                lines.append(f"- **关键证据**:")
                for ev in sig["evidence"]:
                    lines.append(f"  - [{ev.get('author', '')}]({ev.get('url', '')})")
            lines.append("")

    # 尾部
    lines.append("---")
    lines.append("")
    lines.append("*本报告由推特投资舆情监控系统自动生成，仅供参考，不构成投资建议。行情数据来源：新浪财经。*")
    lines.append("")

    return "\n".join(lines)


def save_report(markdown: str, output_path: str | Path) -> None:
    """保存 Markdown 报告"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")


def save_brief_json(brief: dict, output_path: str | Path) -> None:
    """保存简报 JSON"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
