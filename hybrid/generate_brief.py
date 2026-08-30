"""
Hybrid 数据 → 信号分类 → 简报生成

桥接脚本：把 hybrid/main.py 采集的原始推文，经过 filter_v3 分类和 signal_aggregator_v2 聚合，
生成与旧管道兼容的 brief.json，供报告生成器使用。

用法:
    python hybrid/generate_brief.py --input data/hybrid_tweets_20260830.json --output data/brief_20260830.json
"""
import argparse
import json
import sys
import os
from datetime import datetime

# 确保能 import src 下的模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from collectors.filter_v3 import classify_and_score
from collectors.models import Tweet
from analysis.signal_aggregator_v2 import generate_brief_v2


def hybrid_to_tweet(hybrid_tweet: dict) -> Tweet:
    """将 hybrid 格式的推文转换为 Tweet model"""
    text = hybrid_tweet.get('text', '')
    handle = hybrid_tweet.get('handle', '')
    display_name = hybrid_tweet.get('display_name', '')
    
    # 跑分类
    classification = classify_and_score(text, source=handle)
    
    themes = []
    assets = []
    sentiment = 'neutral'
    sentiment_score = 0.0
    
    if classification:
        themes = [
            {'name': t['theme'], 'confidence': t['confidence']}
            for t in classification.get('themes', [])
        ]
        assets = [
            {'symbol': sym, 'name': name}
            for sym, name in classification.get('assets', [])
        ]
        sentiment = classification.get('sentiment', 'neutral')
        # 简单映射到数值
        sentiment_map = {'bullish': 1.0, 'bearish': -1.0, 'neutral': 0.0}
        sentiment_score = sentiment_map.get(sentiment, 0.0)
    
    return Tweet(
        tweet_id=str(hybrid_tweet.get('tweet_id', '')),
        author=handle,
        author_name=display_name,
        content=text,
        likes=hybrid_tweet.get('likes', 0),
        reposts=hybrid_tweet.get('retweets', 0),
        replies=hybrid_tweet.get('replies', 0),
        views=hybrid_tweet.get('views', 0),
        created_at=hybrid_tweet.get('created_at', ''),
        url=hybrid_tweet.get('url', ''),
        tags=[],
        assets=[(a['symbol'], a['name']) for a in assets],
        themes=[t['name'] for t in themes],
        quality_score=0.0,
        is_kol=True,
        sentiment=sentiment,
        sentiment_score=sentiment_score,
        info_density=classification.get('info_density', 0.0) if classification else 0.0,
        theme_details=themes,
        comments=[],
    )


def main():
    parser = argparse.ArgumentParser(description='Hybrid 数据生成简报')
    parser.add_argument('--input', required=True, help='hybrid_tweets JSON 文件路径')
    parser.add_argument('--output', required=True, help='输出 brief JSON 文件路径')
    args = parser.parse_args()

    # 读取 hybrid 数据
    with open(args.input, 'r', encoding='utf-8') as f:
        hybrid_data = json.load(f)

    tweets_raw = hybrid_data.get('tweets', [])
    print(f"读取到 {len(tweets_raw)} 条 hybrid 推文")

    # 转换 + 分类
    classified_tweets = []
    skipped = 0
    for i, ht in enumerate(tweets_raw):
        try:
            tweet = hybrid_to_tweet(ht)
            # 只保留有主题分类的（至少命中一个主题）
            if tweet.themes:
                classified_tweets.append(tweet)
            else:
                skipped += 1
        except Exception as e:
            print(f"  处理第 {i} 条失败: {e}")
            skipped += 1

    print(f"分类完成：{len(classified_tweets)} 条有主题，{skipped} 条无主题跳过")

    if not classified_tweets:
        print("警告：没有分类出任何主题，生成空简报")

    # 生成简报
    brief = generate_brief_v2(classified_tweets)

    # 补充元信息
    brief['generated_at'] = datetime.utcnow().isoformat()
    brief['source'] = 'hybrid'
    brief['version'] = '2.0-hybrid'
    brief['stats']['total_tweets'] = len(tweets_raw)
    brief['stats']['classified_tweets'] = len(classified_tweets)
    brief['stats']['kols_total'] = hybrid_data.get('kols_total', 0)
    brief['stats']['kols_ok'] = hybrid_data.get('kols_ok', 0)

    # 写入输出
    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(brief, f, ensure_ascii=False, indent=2)

    print(f"简报已生成: {args.output}")
    print(f"  主题数: {brief['stats'].get('unique_themes', 0)}")
    print(f"  资产数: {brief['stats'].get('unique_assets', 0)}")
    print(f"  Top 主题: {[t['theme'] for t in brief.get('top_themes', [])[:5]]}")


if __name__ == '__main__':
    main()
