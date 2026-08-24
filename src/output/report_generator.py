"""
报告生成器 — 生成 Markdown 格式的基础报告
（投资信号分析由 Agent 完成，这里只生成数据统计部分）
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def generate_markdown_report(brief: dict, signals: list | None = None, report_date: str = "") -> str:
    """生成 Markdown 报告"""
    if not report_date:
        report_date = datetime.now().strftime("%Y-%m-%d")

    stats = brief.get("stats", {})
    top_assets = brief.get("top_assets", [])
    top_themes = brief.get("top_themes", [])
    kol_summary = brief.get("kol_summary", [])
    top_tweets = brief.get("top_tweets", [])

    lines = []

    # 标题
    lines.append(f"# 📊 推特投资舆情日报 - {report_date}")
    lines.append("")
    lines.append(f"> 生成时间：{brief.get('generated_at', 'N/A')}")
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
    lines.append("")

    # 热门主题
    if top_themes:
        lines.append("## 🔥 热门主题排行")
        lines.append("")
        for i, theme in enumerate(top_themes[:8], 1):
            lines.append(f"{i}. **{theme['theme']}** — {theme['tweet_count']} 条推文，互动量 {theme['engagement']:,}")
        lines.append("")

    # 热门标的
    if top_assets:
        lines.append("## 💹 讨论热度 Top 标的")
        lines.append("")
        lines.append("| 排名 | 标的 | 名称 | 提及数 | 互动量 | KOL提及 | 情绪 |")
        lines.append("|------|------|------|--------|--------|---------|------|")
        for i, asset in enumerate(top_assets[:10], 1):
            sentiment_emoji = {
                "bullish": "🟢 看多",
                "bearish": "🔴 看空",
                "neutral": "⚪ 中性",
            }.get(asset["sentiment"], "⚪ 中性")
            lines.append(
                f"| {i} | {asset['symbol']} | {asset['name']} | {asset['mention_count']} | "
                f"{asset['engagement']:,} | {asset['kol_mentions']} | {sentiment_emoji} |"
            )
        lines.append("")

    # KOL 观点精选
    if kol_summary:
        lines.append("## 🎤 KOL 观点精选")
        lines.append("")
        for i, tweet in enumerate(kol_summary[:10], 1):
            assets_str = ", ".join(f"{a[0]}({a[1]})" for a in tweet["assets"]) if tweet["assets"] else "—"
            themes_str = ", ".join(tweet["themes"]) if tweet["themes"] else "—"
            lines.append(f"### {i}. @{tweet['author']} ({tweet['author_name']})")
            lines.append("")
            lines.append(f"> {tweet['content']}")
            lines.append("")
            lines.append(f"- 👍 {tweet['likes']:,} 赞")
            lines.append(f"- 🔗 [查看原文]({tweet['url']})")
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
            kol_tag = " 🏆KOL" if tweet["is_kol"] else ""
            lines.append(f"### {i}. {author_display}{kol_tag}")
            lines.append("")
            lines.append(f"> {tweet['content']}")
            lines.append("")
            lines.append(
                f"- 👍 {tweet['likes']:,} 赞 · 🔄 {tweet['reposts']:,} 转 · 💬 {tweet['replies']:,} 回复"
            )
            lines.append(f"- 🔗 [查看原文]({tweet['url']})")
            if tweet.get("top_comments"):
                lines.append(f"- 🗨️ 热门评论 ({tweet['comments_count']} 条):")
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
    lines.append("*本报告由推特投资舆情监控系统自动生成，仅供参考，不构成投资建议。*")
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
