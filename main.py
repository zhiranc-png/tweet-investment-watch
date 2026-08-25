"""
推特投资舆情监控系统 — 主入口

使用方式:
    # 1. 采集数据（需要 Firefox + 已登录 X）
    python main.py collect --output data/today.json

    # 2. 生成简报（数据聚合 + 统计）
    python main.py brief --input data/today.json --output data/brief.json

    # 3. 生成完整报告（需要 Agent 做 LLM 分析）
    python main.py report --brief data/brief.json --output report.md

完整流程:
    python main.py run --output report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 确保 src 在路径中
sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.x_twitter import XTwitterCollector
from src.collectors.x_api import XApiCollector
from src.analysis.signal_aggregator import generate_brief
from src.output.report_generator import generate_markdown_report, save_report, save_brief_json
from src.config.kol_list import get_all_kol_handles
from src.config.keywords import get_all_queries, get_kol_search_queries

import os


def _collect_with_playwright(args, kol_handles, kol_queries, keyword_queries):
    """使用 Playwright 浏览器模式采集（备用方案）"""
    collector = XTwitterCollector(
        headless=not args.visible,
        firefox_profile=args.profile,
    )
    collector.set_kol_handles(kol_handles)

    # 健康检查
    health = collector.health_check()
    if not health["cookies_valid"]:
        print(f"❌ Cookie 无效: {health.get('error', '未知错误')}")
        print("   请确保 Firefox 已登录 X/Twitter")
        sys.exit(1)
    print("✅ Cookie 验证通过")

    tweets = collector.collect_daily(
        kol_queries=kol_queries,
        keyword_queries=keyword_queries,
        limit=args.limit,
        fetch_comments=args.with_comments,
        comments_per_tweet=args.comments_per_tweet,
        min_likes_for_comments=args.min_likes,
    )
    return tweets


def cmd_collect(args: argparse.Namespace) -> None:
    """采集推文数据"""
    print("🚀 开始采集 X/Twitter 数据...")

    kol_handles = get_all_kol_handles()
    kol_queries = get_kol_search_queries()
    keyword_queries = get_all_queries()

    print(f"   KOL 账号: {len(kol_handles)} 个")
    print(f"   关键词: {len(keyword_queries)} 个")

    # 选择采集模式：优先用 API 模式（需要 AUTH_TOKEN 和 CT0 环境变量）
    auth_token = os.environ.get("AUTH_TOKEN", "")
    ct0 = os.environ.get("CT0", "")

    if auth_token and ct0:
        print("📡 使用 GraphQL API 模式采集")
        collector = XApiCollector(auth_token=auth_token, ct0=ct0)
        collector.set_kol_handles(kol_handles)

        # 健康检查
        health = collector.health_check()
        if not health["authenticated"]:
            print(f"⚠️  API 认证可能有问题: {health.get('error', '未知错误')}")
            print("   继续尝试采集...")
        else:
            print(f"✅ API 认证通过（用户: @{health.get('username', 'unknown')}）")

        try:
            tweets = collector.collect_daily(
                kol_handles=kol_handles,
                keyword_queries=keyword_queries,
                limit=args.limit,
                fetch_comments=False,
            )
        except Exception as e:
            print(f"❌ API 采集失败: {e}")
            print("   尝试降级到 Playwright 模式...")
            tweets = _collect_with_playwright(args, kol_handles, kol_queries, keyword_queries)
    else:
        print("🌐 使用 Playwright 浏览器模式采集")
        tweets = _collect_with_playwright(args, kol_handles, kol_queries, keyword_queries)

    print(f"✅ 采集完成，共 {len(tweets)} 条推文")

    # 保存为 JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tweets_data = []
    for t in tweets:
        tweets_data.append({
            "tweet_id": t.tweet_id,
            "author": t.author,
            "content": t.content,
            "likes": t.likes,
            "reposts": t.reposts,
            "replies": t.replies,
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

    from src.collectors.x_twitter import Tweet

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
            content=td["content"],
            likes=td["likes"],
            reposts=td["reposts"],
            replies=td["replies"],
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
                content=cd["content"],
                likes=cd["likes"],
                reposts=0,
                replies=0,
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
    """生成 Markdown 报告（投资信号需另外传入）"""
    print("📝 生成报告...")

    brief_path = Path(args.brief)
    if not brief_path.exists():
        print(f"❌ 简报文件不存在: {brief_path}")
        sys.exit(1)

    brief_data = json.loads(brief_path.read_text(encoding="utf-8"))

    # 投资信号（如果有信号文件就读取，否则留空）
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
    # 这里只做采集和简报，投资信号分析需要 Agent 完成
    print("🔄 运行完整流程...")

    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    tweets_file = data_dir / f"tweets_{today}.json"
    brief_file = data_dir / f"brief_{today}.json"

    # 1. 采集
    print("\n[1/3] 采集数据...")
    collect_args = argparse.Namespace(
        output=str(tweets_file),
        visible=args.visible,
        profile=args.profile,
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
    print("   下一步：将 brief JSON 传给 Agent 进行投资信号分析")


def main() -> None:
    parser = argparse.ArgumentParser(description="推特投资舆情监控系统")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # collect
    p_collect = subparsers.add_parser("collect", help="采集推文数据")
    p_collect.add_argument("--output", "-o", default="data/tweets.json", help="输出文件路径")
    p_collect.add_argument("--limit", type=int, default=150, help="采集数量上限")
    p_collect.add_argument("--visible", action="store_true", help="显示浏览器窗口")
    p_collect.add_argument("--profile", help="Firefox profile 路径")
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
    p_report.add_argument("--output", "-o", default="report.md", help="输出文件路径")
    p_report.add_argument("--signals", "-s", help="投资信号 JSON 文件（可选）")

    # run
    p_run = subparsers.add_parser("run", help="完整流程：采集+简报+报告")
    p_run.add_argument("--output", "-o", default="report.md", help="报告输出路径")
    p_run.add_argument("--limit", type=int, default=150, help="采集数量上限")
    p_run.add_argument("--visible", action="store_true", help="显示浏览器窗口")
    p_run.add_argument("--profile", help="Firefox profile 路径")
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
