"""
X 投资舆情监控系统 — 主入口（基于 UserTweets GraphQL API）

使用方式:
    # 完整流程：采集 + 简报 + 报告
    python main.py run --output report.md

    # 仅采集
    python main.py collect --output data/tweets.json

    # 生成简报
    python main.py brief --input data/tweets.json --output data/brief.json

    # 生成报告
    python main.py report --brief data/brief.json --output report.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.x_api import XCollector, DEFAULT_INFLUENCERS
from src.analysis.signal_aggregator import generate_brief
from src.output.report_generator import generate_markdown_report, save_report, save_brief_json
from src.collectors.models import Tweet


def _dict_to_tweet(t: dict) -> Tweet:
    """将 XCollector 返回的 dict 转换为 Tweet 对象"""
    return Tweet(
        tweet_id=t.get("tweet_id", ""),
        author=t.get("influencer_name", t.get("user_name", "")),
        content=t.get("text", ""),
        likes=t.get("likes", 0),
        reposts=t.get("retweets", 0),
        replies=t.get("replies", 0),
        created_at=t.get("created_at", ""),
        url=t.get("url", ""),
        tags=[],
        assets=[],
        themes=[],
        quality_score=t.get("score", 0),
        is_kol=True,  # 大V账号默认都是 KOL
        comments=[],
    )


def cmd_collect(args: argparse.Namespace) -> list[Tweet]:
    """采集推文数据"""
    print("🚀 开始采集 X/Twitter 数据...")

    auth_token = args.auth_token or __import__("os").environ.get("AUTH_TOKEN", "")
    ct0 = args.ct0 or __import__("os").environ.get("CT0", "")

    if not auth_token or not ct0:
        print("❌ 缺少 AUTH_TOKEN 或 CT0 环境变量")
        sys.exit(1)

    collector = XCollector(auth_token=auth_token, ct0=ct0)

    # 健康检查
    print("🔍 健康检查...")
    health = collector.health_check()
    if not health.get("api_works", False):
        print(f"⚠️  API 测试未返回数据: {health.get('error', '未知')}")
        print("   继续尝试采集...")
    else:
        print(f"✅ API 正常（测试返回 {health.get('test_results', 0)} 条）")

    print(f"📡 大V数量: {len(DEFAULT_INFLUENCERS)} 位")
    print(f"   每人采集: {args.per_user} 条")
    print(f"   时间窗口: 最近 {args.hours} 小时")
    print(f"   投资过滤: {'开启' if not args.no_filter else '关闭'}")
    print()

    result = collector.collect(
        influencers=DEFAULT_INFLUENCERS,
        per_user_count=args.per_user,
        filter_investment=not args.no_filter,
        hours=args.hours,
    )

    print(f"\n✅ 采集完成:")
    print(f"   总推文数: {result['total']} 条（投资相关）")
    print(f"   成功用户: {result['success_users']} / {len(DEFAULT_INFLUENCERS)}")

    if result["failed_users"]:
        print(f"   失败用户: {len(result['failed_users'])} 个")
        for name, err in result["failed_users"][:5]:
            print(f"     - @{name}: {err[:60]}")

    # 转换为 Tweet 对象列表
    tweets = [_dict_to_tweet(t) for t in result["tweets"]]

    # 保存为 JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tweets_data = []
    for t in result["tweets"]:
        tweets_data.append(t)

    output_path.write_text(json.dumps(tweets_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📁 数据已保存到: {output_path}")

    return tweets


def cmd_brief(args: argparse.Namespace) -> dict:
    """生成数据简报（聚合统计）"""
    print("📊 生成数据简报...")

    # 读取推文数据
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 文件不存在: {input_path}")
        sys.exit(1)

    tweets_data = json.loads(input_path.read_text(encoding="utf-8"))

    # 如果是 XCollector 格式（list of dict），转换为 Tweet 对象
    tweets = []
    for td in tweets_data:
        if "text" in td and "user_screen" in td:
            # XCollector 格式
            tweets.append(_dict_to_tweet(td))
        elif "content" in td and "tweet_id" in td:
            # Tweet dataclass 格式
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
    stats = brief.get("stats", {})
    print(f"   涉及标的: {stats.get('unique_assets', 0)} 个")
    print(f"   热门主题: {stats.get('unique_themes', 0)} 个")

    return brief


def cmd_report(args: argparse.Namespace) -> str:
    """生成 Markdown 报告"""
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
    print(f"   报告字数: {len(md)} 字")

    return md


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
        output=str(tweets_file),
        auth_token=args.auth_token,
        ct0=args.ct0,
        per_user=args.per_user,
        hours=args.hours,
        no_filter=args.no_filter,
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

    print(f"\n🎉 完成！报告在 {args.output}")
    print(f"   简报数据在 {brief_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="X 投资舆情监控系统（基于 UserTweets API）")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # collect
    p_collect = subparsers.add_parser("collect", help="采集推文数据")
    p_collect.add_argument("--output", "-o", default="data/tweets.json", help="输出文件路径")
    p_collect.add_argument("--per-user", type=int, default=20, help="每人采集条数")
    p_collect.add_argument("--hours", type=int, default=48, help="时间窗口（小时）")
    p_collect.add_argument("--no-filter", action="store_true", help="不过滤投资关键词")
    p_collect.add_argument("--auth-token", default="", help="X auth_token（也可用环境变量 AUTH_TOKEN）")
    p_collect.add_argument("--ct0", default="", help="X ct0（也可用环境变量 CT0）")

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
    p_run.add_argument("--per-user", type=int, default=20, help="每人采集条数")
    p_run.add_argument("--hours", type=int, default=48, help="时间窗口（小时）")
    p_run.add_argument("--no-filter", action="store_true", help="不过滤投资关键词")
    p_run.add_argument("--auth-token", default="", help="X auth_token")
    p_run.add_argument("--ct0", default="", help="X ct0")

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
