#!/usr/bin/env python3
"""
投资舆情监控系统 — 多源云端版 (GitHub Actions)
支持 X/Twitter + 雪球 + 华尔街见闻 + 财联社 + 微博 + Hacker News + 36氪 + 知乎

使用方式:
    # 全量采集 + 简报（推荐）
    python main.py run-all --auth-token "$AUTH_TOKEN" --ct0 "$CT0" --output data/brief.json

    # 仅多源采集（不含推特）
    python main.py collect-multi --output data/multi.json

    # 仅推特采集
    python main.py collect-x --auth-token "$AUTH_TOKEN" --ct0 "$CT0" --output data/tweets.json

    # 生成简报
    python main.py brief --input data/tweets.json --output data/brief.json

    # 生成 Markdown 报告
    python main.py report --brief data/brief.json --output report.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.x_playwright_collector import XPlaywrightCollector, Tweet
from src.collectors.multi_source_manager import MultiSourceCollector, UnifiedPost
from src.analysis.signal_aggregator import generate_brief
from src.output.report_generator import generate_markdown_report, save_report, save_brief_json
from src.config.kol_list import get_all_kol_handles
from src.config.keywords import get_all_queries


def cmd_collect_x(args: argparse.Namespace) -> None:
    """采集 X/Twitter 数据"""
    print("🐦 采集 X/Twitter 数据...")

    auth_token = args.auth_token or os.environ.get("AUTH_TOKEN", "")
    ct0 = args.ct0 or os.environ.get("CT0", "")

    if not auth_token or not ct0:
        print("❌ 缺少 auth_token 或 ct0，跳过推特采集")
        return []

    kol_handles = get_all_kol_handles()
    keyword_queries = get_all_queries()

    print(f"   KOL 账号: {len(kol_handles)} 个")
    print(f"   关键词: {len(keyword_queries)} 个")

    collector = XPlaywrightCollector(
        auth_token=auth_token,
        ct0=ct0,
        headless=True,
    )
    collector.set_kol_handles(kol_handles)

    # 健康检查
    health = collector.health_check()
    if not health["cookies_valid"]:
        print(f"❌ auth_token 无效: {health.get('error', '未知错误')}")
        return []
    print("✅ auth_token 验证通过")

    try:
        tweets = collector.collect_daily(
            kol_handles=kol_handles,
            search_queries=keyword_queries,
            limit=args.limit,
            fetch_comments=args.with_comments,
            comments_per_tweet=args.comments_per_tweet,
            min_likes_for_comments=args.min_likes,
        )
    except Exception as e:
        print(f"❌ 推特采集失败: {e}")
        import traceback
        traceback.print_exc()
        return []

    print(f"✅ 推特采集完成，共 {len(tweets)} 条")
    return tweets


def cmd_collect_multi(args: argparse.Namespace) -> list:
    """采集多源数据"""
    print("🌐 采集多源数据...")

    collector = MultiSourceCollector()
    results = collector.collect_all()
    all_posts = collector.get_all_posts(results)

    print(f"✅ 多源采集完成，共 {len(all_posts)} 条")

    # 保存
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    posts_data = [p.to_dict() for p in all_posts]
    output_path.write_text(json.dumps(posts_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📁 数据已保存到: {output_path}")

    return all_posts


def _tweets_to_unified(tweets: list) -> list:
    """将推文转换为统一格式"""
    unified = []
    for t in tweets:
        post = UnifiedPost(
            post_id=f"x_{t.tweet_id}",
            source="twitter",
            author=t.author,
            author_name=t.author_name or t.author,
            content=t.content,
            likes=t.likes,
            reposts=t.reposts,
            replies=t.replies,
            views=t.views,
            created_at=t.created_at,
            url=t.url,
            tags=t.tags,
        )
        unified.append(post)
    return unified


def cmd_run_all(args: argparse.Namespace) -> None:
    """完整流程：推特 + 多源 → 简报 → 报告"""
    print("🔄 运行完整流程（推特 + 多源）...")

    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    tweets_file = data_dir / f"tweets_{today}.json"
    multi_file = data_dir / f"multi_{today}.json"
    brief_file = data_dir / f"brief_{today}.json"

    all_posts = []

    # 1. 采集推特
    print("\n" + "=" * 60)
    print("[1/3] 采集 X/Twitter 数据...")
    print("=" * 60)
    try:
        tweets = cmd_collect_x(args)
        if tweets:
            # 保存原始推文
            tweets_data = []
            for t in tweets:
                tweets_data.append({
                    "tweet_id": t.tweet_id,
                    "author": t.author,
                    "author_name": t.author_name,
                    "content": t.content,
                    "likes": t.likes,
                    "reposts": t.reposts,
                    "replies": t.replies,
                    "views": t.views,
                    "created_at": t.created_at,
                    "url": t.url,
                    "tags": t.tags,
                    "is_kol": t.is_kol,
                })
            tweets_file.write_text(json.dumps(tweets_data, ensure_ascii=False, indent=2), encoding="utf-8")
            x_posts = _tweets_to_unified(tweets)
            all_posts.extend(x_posts)
            print(f"   🐦 推特: {len(x_posts)} 条")
        else:
            print("   ⚠️ 推特采集失败或跳过")
    except Exception as e:
        print(f"   ❌ 推特采集异常: {e}")

    # 2. 采集多源
    print("\n" + "=" * 60)
    print("[2/3] 采集多源数据...")
    print("=" * 60)
    try:
        multi_collector = MultiSourceCollector()
        results = multi_collector.collect_all()
        multi_posts = multi_collector.get_all_posts(results)

        # 保存多源数据
        multi_data = [p.to_dict() for p in multi_posts]
        multi_file.write_text(json.dumps(multi_data, ensure_ascii=False, indent=2), encoding="utf-8")
        all_posts.extend(multi_posts)
        print(f"   🌐 多源: {len(multi_posts)} 条")
    except Exception as e:
        print(f"   ❌ 多源采集异常: {e}")

    if not all_posts:
        print("❌ 没有采集到任何数据，退出")
        sys.exit(1)

    # 按互动分数排序
    all_posts.sort(key=lambda p: p.engagement_score, reverse=True)

    print(f"\n📊 总采集量: {len(all_posts)} 条")
    source_counts = {}
    for p in all_posts:
        source_counts[p.source] = source_counts.get(p.source, 0) + 1
    for src, cnt in sorted(source_counts.items(), key=lambda x: -x[1]):
        print(f"   {src}: {cnt} 条")

    # 3. 生成简报
    print("\n" + "=" * 60)
    print("[3/3] 生成简报...")
    print("=" * 60)

    # 生成简报数据
    brief = _generate_multi_source_brief(all_posts)
    save_brief_json(brief, brief_file)
    print(f"✅ 简报已保存到: {brief_file}")

    # 生成基础 Markdown 报告
    report_path = Path(args.output)
    md = generate_markdown_report(brief, [], datetime.now().strftime("%Y-%m-%d"))
    save_report(md, report_path)
    print(f"✅ 基础报告已保存到: {report_path}")

    print(f"\n🎉 完成！共 {len(all_posts)} 条数据")
    print(f"   简报: {brief_file}")
    print(f"   报告: {report_path}")


def _generate_multi_source_brief(all_posts: list) -> dict:
    """基于多源数据生成简报"""
    # 按来源分组
    by_source = {}
    for p in all_posts:
        src = p.source
        if src not in by_source:
            by_source[src] = []
        by_source[src].append(p)

    # 统计
    total_posts = len(all_posts)
    sources = list(by_source.keys())

    # Top 帖子（按互动分数）
    top_posts = sorted(all_posts, key=lambda p: p.engagement_score, reverse=True)[:20]

    # 提取热门关键词
    all_text = " ".join([p.title + " " + p.content for p in all_posts[:50]])
    keywords = _extract_keywords(all_text)

    brief = {
        "version": "2.0",
        "generated_at": datetime.now().isoformat(),
        "stats": {
            "total_posts": total_posts,
            "sources": sources,
            "source_counts": {s: len(ps) for s, ps in by_source.items()},
        },
        "top_posts": [p.to_dict() for p in top_posts],
        "by_source": {
            src: [p.to_dict() for p in sorted(posts, key=lambda p: p.engagement_score, reverse=True)[:10]]
            for src, posts in by_source.items()
        },
        "hot_keywords": keywords,
        "all_posts": [p.to_dict() for p in all_posts[:100]],  # 保留前100条详细数据
    }

    return brief


def _extract_keywords(text: str, top_n: int = 30) -> list:
    """简单的关键词提取（基于词频）"""
    # 投资相关关键词列表
    investment_keywords = [
        "黄金", "白银", "原油", "铜", "比特币", "以太坊",
        "美联储", "加息", "降息", "利率", "通胀", "CPI", "PCE", "非农",
        "美股", "A股", "港股", "中概股", "纳斯达克", "标普", "道琼斯",
        "英伟达", "NVDA", "特斯拉", "TSLA", "苹果", "AAPL", "微软", "MSFT",
        "谷歌", "GOOG", "亚马逊", "AMZN", "Meta", "META",
        "AI", "人工智能", "芯片", "半导体", "存储", "美光",
        "国债", "美债", "收益率", "美元", "人民币", "汇率",
        "财报", "业绩", "回购", "分红", "估值", "PE", "EPS",
        "衰退", "软着陆", "硬着陆", "滞胀",
        "巴菲特", "芒格", "Burry", "Ackman", "Sacks",
    ]

    found = []
    text_lower = text.lower()
    for kw in investment_keywords:
        count = text_lower.count(kw.lower())
        if count > 0:
            found.append({"keyword": kw, "count": count})

    found.sort(key=lambda x: -x["count"])
    return found[:top_n]


def main() -> None:
    parser = argparse.ArgumentParser(description="投资舆情监控系统 - 多源云端版")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # collect-x
    p_x = subparsers.add_parser("collect-x", help="采集 X/Twitter 数据")
    p_x.add_argument("--auth-token", help="X auth_token cookie")
    p_x.add_argument("--ct0", help="X ct0 cookie")
    p_x.add_argument("--output", "-o", default="data/tweets.json", help="输出文件路径")
    p_x.add_argument("--limit", type=int, default=150, help="采集数量上限")
    p_x.add_argument("--with-comments", action="store_true", help="抓取评论")
    p_x.add_argument("--comments-per-tweet", type=int, default=10)
    p_x.add_argument("--min-likes", type=int, default=100, help="抓评论的最低点赞数")

    # collect-multi
    p_multi = subparsers.add_parser("collect-multi", help="采集多源数据（不含推特）")
    p_multi.add_argument("--output", "-o", default="data/multi.json", help="输出文件路径")

    # run-all
    p_run = subparsers.add_parser("run-all", help="完整流程：推特+多源+简报+报告")
    p_run.add_argument("--auth-token", help="X auth_token cookie")
    p_run.add_argument("--ct0", help="X ct0 cookie")
    p_run.add_argument("--output", "-o", default="report.md", help="报告输出路径")
    p_run.add_argument("--limit", type=int, default=150, help="推特采集数量上限")
    p_run.add_argument("--with-comments", action="store_true", help="抓取评论")
    p_run.add_argument("--skip-x", action="store_true", help="跳过推特采集")

    # brief
    p_brief = subparsers.add_parser("brief", help="生成数据简报")
    p_brief.add_argument("--input", "-i", required=True, help="数据 JSON 文件")
    p_brief.add_argument("--output", "-o", default="data/brief.json", help="输出文件路径")

    # report
    p_report = subparsers.add_parser("report", help="生成 Markdown 报告")
    p_report.add_argument("--brief", "-b", required=True, help="简报 JSON 文件")
    p_report.add_argument("--output", "-o", default="report.md", help="报告输出路径")
    p_report.add_argument("--signals", "-s", help="投资信号 JSON 文件（可选）")

    args = parser.parse_args()

    if args.command == "collect-x":
        cmd_collect_x(args)
    elif args.command == "collect-multi":
        cmd_collect_multi(args)
    elif args.command == "run-all":
        cmd_run_all(args)
    elif args.command == "brief":
        # 兼容旧版
        print("⚠️ brief 命令暂不支持多源格式，请使用 run-all")
    elif args.command == "report":
        print("⚠️ report 命令暂不支持多源格式，请使用 run-all")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
