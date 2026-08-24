#!/usr/bin/env python3
"""
推特投资舆情监控系统 — 云端版 (GitHub Actions)
基于 auth_token 的轻量爬虫，无需浏览器

使用方式:
    # 采集 + 生成简报（GitHub Actions 主要用这个）
    python main.py run --auth-token "$AUTH_TOKEN" --ct0 "$CT0" --output data/brief.json

    # 仅采集
    python main.py collect --auth-token "$AUTH_TOKEN" --ct0 "$CT0" --output data/tweets.json

    # 仅生成简报
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

# 确保 src 在路径中
sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.x_api_collector import XAPICollector, Tweet
from src.analysis.signal_aggregator import generate_brief
from src.output.report_generator import generate_markdown_report, save_report, save_brief_json
from src.config.kol_list import get_all_kol_handles
from src.config.keywords import get_all_queries


def cmd_collect(args: argparse.Namespace) -> None:
    """采集推文数据"""
    print("🚀 开始采集 X/Twitter 数据...")

    auth_token = args.auth_token or os.environ.get("AUTH_TOKEN", "")
    ct0 = args.ct0 or os.environ.get("CT0", "")
    proxy = args.proxy or os.environ.get("HTTP_PROXY", "")

    if not auth_token or not ct0:
        print("❌ 缺少 auth_token 或 ct0")
        print("   请通过 --auth-token 和 --ct0 参数传入，或设置环境变量 AUTH_TOKEN 和 CT0")
        sys.exit(1)

    kol_handles = get_all_kol_handles()
    keyword_queries = get_all_queries()

    print(f"   KOL 账号: {len(kol_handles)} 个")
    print(f"   关键词: {len(keyword_queries)} 个")

    collector = XAPICollector(
        auth_token=auth_token,
        ct0=ct0,
        proxy=proxy if proxy else None,
    )
    collector.set_kol_handles(kol_handles)

    # 健康检查
    health = collector.health_check()
    if not health["cookies_valid"]:
        print(f"❌ auth_token 无效: {health.get('error', '未知错误')}")
        sys.exit(1)
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
        print(f"❌ 采集失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print(f"✅ 采集完成，共 {len(tweets)} 条推文")

    # 保存为 JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

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
            "assets": [list(a) for a in t.assets],
            "themes": t.themes,
            "quality_score": t.quality_score,
            "is_kol": t.is_kol,
            "comments": [
                {
                    "tweet_id": c.tweet_id,
                    "author": c.author,
                    "author_name": c.author_name,
                    "content": c.content,
                    "likes": c.likes,
                    "url": c.url,
                }
                for c in t.comments
            ],
        })

    output_path.write_text(json.dumps(tweets_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📁 数据已保存到: {output_path}")


def cmd_brief(args: argparse.Namespace) -> None:
    """生成数据简报（聚合统计）"""
    print("📊 生成数据简报...")

    # 读取推文数据
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 文件不存在: {input_path}")
        sys.exit(1)

    tweets_data = json.loads(input_path.read_text(encoding="utf-8"))

    # 重建 Tweet 对象
    tweets = []
    for td in tweets_data:
        t = Tweet(
            tweet_id=td["tweet_id"],
            author=td["author"],
            author_name=td.get("author_name", ""),
            content=td["content"],
            likes=td["likes"],
            reposts=td["reposts"],
            replies=td["replies"],
            views=td.get("views", 0),
            created_at=td["created_at"],
            url=td["url"],
            tags=td.get("tags", []),
            assets=[tuple(a) for a in td.get("assets", [])],
            themes=td.get("themes", []),
            quality_score=td.get("quality_score", 0),
            is_kol=td.get("is_kol", False),
        )
        # 评论
        for cd in td.get("comments", []):
            t.comments.append(Tweet(
                tweet_id=cd["tweet_id"],
                author=cd["author"],
                author_name=cd.get("author_name", ""),
                content=cd["content"],
                likes=cd["likes"],
                reposts=0,
                replies=0,
                views=0,
                created_at="",
                url=cd["url"],
            ))
        tweets.append(t)

    print(f"   读取 {len(tweets)} 条推文")

    # 生成简报
    brief = generate_brief(tweets)

    # 保存
    output_path = Path(args.output)
    save_brief_json(brief, output_path)
    print(f"✅ 简报已保存到: {output_path}")
    print(f"   涉及标的: {brief['stats']['unique_assets']} 个")
    print(f"   热门主题: {brief['stats']['unique_themes']} 个")


def cmd_report(args: argparse.Namespace) -> None:
    """生成 Markdown 报告"""
    print("📝 生成报告...")

    brief_path = Path(args.brief)
    if not brief_path.exists():
        print(f"❌ 简报文件不存在: {brief_path}")
        sys.exit(1)

    brief_data = json.loads(brief_path.read_text(encoding="utf-8"))

    # 投资信号（如果有信号文件就读取）
    investment_signals = []
    if args.signals and Path(args.signals).exists():
        signals_data = json.loads(Path(args.signals).read_text(encoding="utf-8"))
        investment_signals = signals_data.get("signals", [])
        print(f"   读取 {len(investment_signals)} 个投资信号")

    # 生成报告
    report_date = datetime.now().strftime("%Y-%m-%d")
    md = generate_markdown_report(brief_data, investment_signals, report_date)

    output_path = Path(args.output)
    save_report(md, output_path)
    print(f"✅ 报告已保存到: {output_path}")


def cmd_run(args: argparse.Namespace) -> None:
    """完整流程：采集 → 简报 → 报告"""
    print("🔄 运行完整流程...")

    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    tweets_file = data_dir / f"tweets_{today}.json"
    brief_file = data_dir / f"brief_{today}.json"

    # 1. 采集
    print("\n[1/3] 采集数据...")
    collect_args = argparse.Namespace(
        auth_token=args.auth_token,
        ct0=args.ct0,
        proxy=args.proxy,
        output=str(tweets_file),
        limit=args.limit,
        with_comments=args.with_comments,
        comments_per_tweet=10,
        min_likes=100,
    )
    cmd_collect(collect_args)

    # 2. 简报
    print("\n[2/3] 生成简报...")
    brief_args = argparse.Namespace(
        input=str(tweets_file),
        output=str(brief_file),
    )
    cmd_brief(brief_args)

    # 3. 生成基础报告（无投资信号）
    print("\n[3/3] 生成基础报告...")
    report_args = argparse.Namespace(
        brief=str(brief_file),
        output=args.output,
        signals=None,
    )
    cmd_report(report_args)

    print(f"\n🎉 完成！简报数据在 {brief_file}")
    print(f"   基础报告在 {args.output}")
    print("   下一步：将 brief JSON 传给 Agent 进行投资信号分析")


def main() -> None:
    parser = argparse.ArgumentParser(description="推特投资舆情监控系统 - 云端版")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # collect
    p_collect = subparsers.add_parser("collect", help="采集推文数据")
    p_collect.add_argument("--auth-token", help="X auth_token cookie")
    p_collect.add_argument("--ct0", help="X ct0 cookie (CSRF token)")
    p_collect.add_argument("--proxy", help="HTTP 代理地址")
    p_collect.add_argument("--output", "-o", default="data/tweets.json", help="输出文件路径")
    p_collect.add_argument("--limit", type=int, default=150, help="采集数量上限")
    p_collect.add_argument("--with-comments", action="store_true", help="抓取评论")
    p_collect.add_argument("--comments-per-tweet", type=int, default=10)
    p_collect.add_argument("--min-likes", type=int, default=100, help="抓评论的最低点赞数")

    # brief
    p_brief = subparsers.add_parser("brief", help="生成数据简报")
    p_brief.add_argument("--input", "-i", required=True, help="推文 JSON 文件")
    p_brief.add_argument("--output", "-o", default="data/brief.json", help="输出文件路径")

    # report
    p_report = subparsers.add_parser("report", help="生成 Markdown 报告")
    p_report.add_argument("--brief", "-b", required=True, help="简报 JSON 文件")
    p_report.add_argument("--output", "-o", default="report.md", help="报告输出路径")
    p_report.add_argument("--signals", "-s", help="投资信号 JSON 文件（可选）")

    # run
    p_run = subparsers.add_parser("run", help="完整流程：采集+简报+报告")
    p_run.add_argument("--auth-token", help="X auth_token cookie")
    p_run.add_argument("--ct0", help="X ct0 cookie (CSRF token)")
    p_run.add_argument("--proxy", help="HTTP 代理地址")
    p_run.add_argument("--output", "-o", default="report.md", help="报告输出路径")
    p_run.add_argument("--limit", type=int, default=150, help="采集数量上限")
    p_run.add_argument("--with-comments", action="store_true", help="抓取评论")

    args = parser.parse_args()

    if args.command == "collect":
        cmd_collect(args)
    elif args.command == "brief":
        cmd_brief(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "run":
        cmd_run(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
