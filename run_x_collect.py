"""X 投资舆情采集 - 简化版主入口
直接用 UserTweets API 采集大V推文，生成投资简报
"""
import os
import sys
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.collectors.x_api import XCollector, DEFAULT_INFLUENCERS


def collect_tweets(per_user=20, filter_investment=True):
    """采集所有大V推文"""
    auth_token = os.environ.get("AUTH_TOKEN", "")
    ct0 = os.environ.get("CT0", "")
    
    if not auth_token or not ct0:
        print("❌ 缺少 AUTH_TOKEN 或 CT0 环境变量")
        sys.exit(1)
    
    collector = XCollector(auth_token=auth_token, ct0=ct0)
    
    print(f"📡 开始采集 X 推文...")
    print(f"   大V数量: {len(DEFAULT_INFLUENCERS)} 位")
    print(f"   每人采集: {per_user} 条")
    print()
    
    result = collector.collect(
        influencers=DEFAULT_INFLUENCERS,
        per_user_count=per_user,
        filter_investment=filter_investment,
    )
    
    print(f"\n✅ 采集完成:")
    print(f"   总推文数: {result['total']} 条")
    print(f"   成功用户: {result['success_users']} / {len(DEFAULT_INFLUENCERS)}")
    
    if result["failed_users"]:
        print(f"   失败用户: {len(result['failed_users'])} 个")
        for name, err in result["failed_users"][:5]:
            print(f"     - @{name}: {err[:50]}")
    
    return result["tweets"]


def generate_brief(tweets, top_n=30):
    """生成简报数据"""
    # 按热度排序
    sorted_tweets = sorted(tweets, key=lambda x: x["score"], reverse=True)
    
    # 统计
    sources = {}
    for t in tweets:
        src = t.get("source_detail", "@unknown")
        sources[src] = sources.get(src, 0) + 1
    
    # 关键词统计
    keywords_count = {}
    investment_kw = ["ai", "stock", "market", "fed", "inflation", "bitcoin", "crypto", 
                     "tesla", "nvidia", "apple", "microsoft", "gold", "oil", "bond", "recession"]
    for t in tweets:
        text_lower = t["text"].lower()
        for kw in investment_kw:
            if kw in text_lower:
                keywords_count[kw] = keywords_count.get(kw, 0) + 1
    
    top_keywords = sorted(keywords_count.items(), key=lambda x: x[1], reverse=True)[:15]
    
    return {
        "version": "2.0",
        "platform": "x",
        "total": len(tweets),
        "collected_at": datetime.now().isoformat(),
        "influencers_count": len(sources),
        "top_tweets": sorted_tweets[:top_n],
        "all_tweets": sorted_tweets,
        "sources": dict(sorted(sources.items(), key=lambda x: x[1], reverse=True)),
        "top_keywords": top_keywords,
    }


def generate_markdown_report(brief):
    """生成 Markdown 报告"""
    lines = []
    today = datetime.now().strftime("%Y年%m月%d日")
    
    lines.append(f"# X 投资舆情日报 - {today}")
    lines.append("")
    lines.append(f"> 数据来源：X/Twitter {brief['influencers_count']} 位投资大V")
    lines.append(f"> 采集时间：{brief['collected_at']}")
    lines.append(f"> 总推文数：{brief['total']} 条（投资相关）")
    lines.append("")
    
    # 热门关键词
    lines.append("## 🔥 热门关键词")
    lines.append("")
    for kw, count in brief["top_keywords"][:10]:
        lines.append(f"- **{kw}**: {count} 条提及")
    lines.append("")
    
    # Top 推文
    lines.append("## 📈 热门投资推文 Top 20")
    lines.append("")
    
    for i, t in enumerate(brief["top_tweets"][:20], 1):
        rt = "🔁 " if t.get("is_retweet") else ""
        influencer = t.get("influencer_name", t.get("user_name", ""))
        screen = t.get("user_screen", "")
        score = t.get("score", 0)
        views = t.get("views", 0)
        retweets = t.get("retweets", 0)
        replies = t.get("replies", 0)
        
        lines.append(f"### {i}. {influencer} (@{screen})")
        lines.append("")
        lines.append(f"{rt}{t['text']}")
        lines.append("")
        lines.append(f"📊 热度: **{score}** 分 | 👁 {views:,} 浏览 | 🔁 {retweets} 转推 | 💬 {replies} 回复")
        lines.append(f"🔗 [查看原文]({t.get('url', '')})")
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # 大V分布
    lines.append("## 👥 大V发文分布")
    lines.append("")
    for src, count in list(brief["sources"].items())[:15]:
        lines.append(f"- {src}: {count} 条")
    lines.append("")
    
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="X 投资舆情采集")
    parser.add_argument("--per-user", type=int, default=20, help="每人采集条数")
    parser.add_argument("--top", type=int, default=30, help="Top N 推文")
    parser.add_argument("--output", type=str, default="data/x_brief.json", help="输出 JSON 路径")
    parser.add_argument("--report", type=str, default="report/x_report.md", help="输出报告路径")
    parser.add_argument("--no-filter", action="store_true", help="不过滤投资关键词")
    args = parser.parse_args()
    
    # 采集
    tweets = collect_tweets(per_user=args.per_user, filter_investment=not args.no_filter)
    
    if not tweets:
        print("❌ 没有采集到任何推文")
        sys.exit(1)
    
    # 生成简报
    brief = generate_brief(tweets, top_n=args.top)
    
    # 保存 JSON
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📁 简报已保存: {out_path}")
    
    # 生成报告
    report = generate_markdown_report(brief)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"📄 报告已保存: {report_path}")
    print(f"   报告字数: {len(report)} 字")


if __name__ == "__main__":
    main()
