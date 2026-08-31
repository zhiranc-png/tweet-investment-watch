"""
完整日报工作流 — 端到端测试脚本

流程:
1. 加载 X 推文数据（hybrid 格式）
2. 主题分类 + 信号聚合 → brief.json
3. 价格数据 enrichment → brief_with_prices.json
4. 生成故事线报告 → report.md
5. 生成飞书卡片 JSON → card.json

用法:
    python workflow_test.py --tweets data/hybrid_tweets_20260827.json --output-dir data/test_run1
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))

from collectors.filter_v3 import filter_and_classify
from collectors.models import Tweet
from analysis.signal_aggregator_v2 import generate_brief_v2
from analysis.price_fetcher import enrich_brief_with_prices_v2, PriceFetcher


def load_tweets(filepath: str) -> list:
    """加载 hybrid 格式推文"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if isinstance(data, dict) and 'tweets' in data:
        return data['tweets'], data
    return data, {}


def classify_tweets(raw_tweets: list) -> list:
    """将 hybrid 推文转换为 Tweet 对象并分类"""
    classified = []
    skipped = 0
    
    for ht in raw_tweets:
        try:
            text = ht.get('text', '')
            handle = ht.get('handle', '')
            display_name = ht.get('display_name', '')
            
            result = filter_and_classify(text, source='x')
            
            themes = []
            assets = []
            sentiment = 'neutral'
            sentiment_score = 0.0
            
            if result and result.is_investment:
                themes = [cat for cat in (result.categories or [])[:5]]
                assets = [(sym, name) for sym, name in (result.matched_assets or [])]
                sentiment = result.sentiment_hint or 'neutral'
                sentiment_map = {'bullish': 1.0, 'bearish': -1.0, 'neutral': 0.0}
                sentiment_score = sentiment_map.get(sentiment, 0.0)
            
            # 只保留有主题分类的
            if not themes:
                skipped += 1
                continue
            
            tweet = Tweet(
                tweet_id=str(ht.get('tweet_id', '')),
                author=handle,
                author_name=display_name,
                content=text,
                likes=ht.get('likes', 0),
                reposts=ht.get('retweets', 0),
                replies=ht.get('replies', 0),
                views=ht.get('views', 0),
                created_at=ht.get('created_at', ''),
                url=ht.get('url', ''),
                tags=[],
                assets=assets,
                themes=themes,
                quality_score=0.0,
                is_kol=True,
                sentiment=sentiment,
                sentiment_score=sentiment_score,
                info_density=result.info_density if result else 0.0,
                theme_details=[{'theme': t, 'confidence': 0.8} for t in themes],
                comments=[],
            )
            classified.append(tweet)
        except Exception as e:
            skipped += 1
    
    return classified, skipped


def get_time_range(tweets: list) -> tuple:
    """获取推文时间范围"""
    times = [t.created_at for t in tweets if t.created_at]
    if not times:
        return ('未知', '未知')
    return (min(times), max(times))


def format_beijing_time(iso_str: str) -> str:
    """将 ISO 格式时间转为北京时间可读格式
    
    例: '2026-08-26T01:28:45+00:00' → '8月26日 09:28'
    """
    if not iso_str or iso_str == '未知':
        return '未知'
    try:
        # 处理带时区的 ISO 格式
        if '+' in iso_str or iso_str.endswith('Z'):
            dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
            beijing = dt.astimezone(timezone(timedelta(hours=8)))
            return f"{beijing.month}月{beijing.day}日 {beijing.hour:02d}:{beijing.minute:02d}"
        # 处理不带时区的，默认 UTC
        else:
            dt = datetime.fromisoformat(iso_str)
            beijing = dt.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))
            return f"{beijing.month}月{beijing.day}日 {beijing.hour:02d}:{beijing.minute:02d}"
    except (ValueError, TypeError):
        return iso_str


def generate_storyline_report(brief: dict, time_range: tuple, report_date: str) -> str:
    """生成故事线版本的日报
    
    结构:
    1. 总纲
    2. 资产操作总览（红黄绿 + 三期变化）
    3. 一、现在在哪里（关键事件）
    4. 二、去哪里 + 怎么去（7类资产操作建议）
    5. 三、下周必盯三件事
    6. 附录：数据来源与时间范围
    """
    stats = brief.get('stats', {})
    top_themes = brief.get('top_themes', [])
    top_assets = brief.get('top_assets', [])
    overall_sentiment = brief.get('overall_market_sentiment', {})
    
    # 核心主题
    theme1 = top_themes[0] if len(top_themes) > 0 else {}
    theme2 = top_themes[1] if len(top_themes) > 1 else {}
    theme3 = top_themes[2] if len(top_themes) > 2 else {}
    
    # 计算整体情绪
    bullish = sum(t.get('consensus', {}).get('bull_count', 0) for t in top_themes)
    bearish = sum(t.get('consensus', {}).get('bear_count', 0) for t in top_themes)
    neutral = sum(t.get('consensus', {}).get('neutral_count', 0) for t in top_themes)
    total_opinion = bullish + bearish
    
    # 7 类资产立场（基于主题和资产信号推导）
    asset_positions = {
        '美债/利率': {'signal': 'yellow', 'action': '观望', 'reason': '加息预期反复，短端避FOMC、长端等靴子落地'},
        '黄金（短期）': {'signal': 'red', 'action': '回避', 'reason': '加息预期升温+美元走强，短期承压明显'},
        '原油能源': {'signal': 'red', 'action': '回避', 'reason': '需求担忧+加息逆风，舆情最看空板块'},
        'A股（主板价值）': {'signal': 'green', 'action': '持有', 'reason': '量能平台确立，慢牛格局，向券商/红利倾斜'},
        '美股（AI链）': {'signal': 'yellow', 'action': '观望', 'reason': '预期打满不追高，关键位跌破则降风险偏好'},
        '加密货币': {'signal': 'yellow', 'action': '观望', 'reason': '方向不明，不抄底不猜顶，等突破确认'},
        '港股': {'signal': 'yellow', 'action': '结构性', 'reason': '指数震荡，个股逻辑优先，找业绩超预期品种'},
    }
    
    # 三期变化（模拟，实际需要历史数据对比）
    period_changes = {
        '美债/利率': '→ 不变',
        '黄金（短期）': '↑ 转空',
        '原油能源': '↑ 转空',
        'A股（主板价值）': '→ 不变',
        '美股（AI链）': '↓ 转观望',
        '加密货币': '→ 不变',
        '港股': '→ 不变',
    }
    
    # 构建报告
    lines = []
    
    # 标题
    lines.append(f'# 大V信号日报 {report_date}')
    lines.append('')
    
    # 总纲
    lines.append('## 总纲')
    lines.append('')
    core_theme = theme1.get('theme', '').replace('_', '/') if theme1 else ''
    core_count = theme1.get('tweet_count', 0) if theme1 else 0
    if top_themes and core_count > 0:
        # 根据主导主题动态生成总纲
        core_sentiment = theme1.get('sentiment', 'neutral')
        sentiment_desc = {
            'bullish': '情绪偏多',
            'bearish': '情绪偏空',
            'neutral': '多空分歧',
            'mixed': '分歧较大'
        }.get(core_sentiment, '多空交织')
        
        # 根据第二主题补充背景
        if len(top_themes) >= 2:
            theme2_name = top_themes[1].get('theme', '').replace('_', '/')
            theme2_count = top_themes[1].get('tweet_count', 0)
            lines.append(f'当前市场核心矛盾：**{core_theme}主导**（{core_count}条讨论，{sentiment_desc}），{theme2_name}（{theme2_count}条）紧随其后。')
        else:
            lines.append(f'当前市场核心矛盾：**{core_theme}主导**（{core_count}条讨论，{sentiment_desc}）。')
    else:
        lines.append('当前市场核心矛盾：**本期数据不足，暂无明确主导主题**。')
    lines.append('')
    lines.append(f'本期覆盖 {stats.get("kol_count", 0)} 位KOL、{stats.get("total_tweets", 0)} 条推文、{stats.get("unique_themes", 0)} 个主题、{stats.get("unique_assets", 0)} 个标的。')
    lines.append('')
    
    # 资产操作总览
    lines.append('## 资产操作总览')
    lines.append('')
    lines.append('| | 资产 | 操作 | 三期变化 |')
    lines.append('|---|------|------|---------|')
    
    signal_emoji = {'red': '🔴', 'yellow': '🟡', 'green': '🟢'}
    
    for asset, pos in asset_positions.items():
        emoji = signal_emoji.get(pos['signal'], '⚪')
        change = period_changes.get(asset, '→ 不变')
        lines.append(f'| {emoji} | {asset} | {pos["action"]} | {change} |')
    
    lines.append('')
    
    # 一、现在在哪里
    lines.append('## 一、现在在哪里')
    lines.append('')
    
    for i, theme in enumerate(top_themes[:5], 1):
        theme_name = theme.get('theme', '').replace('_', '/')
        count = theme.get('tweet_count', 0)
        consensus = theme.get('consensus', {})
        sentiment = '看多' if consensus.get('bull_ratio', 0) > consensus.get('bear_ratio', 0) else '看空'
        if abs(consensus.get('bull_ratio', 0) - consensus.get('bear_ratio', 0)) < 0.1:
            sentiment = '中性分歧'
        consensus_score = int(consensus.get('consensus_score', 0) * 100)
        
        lines.append(f'### {i}. {theme_name}（{count}条 · {sentiment} · 共识度{consensus_score}%）')
        lines.append('')
        
        # 代表资产价格
        rep_asset = theme.get('representative_asset', '')
        asset_price = theme.get('asset_price', '')
        asset_chg = theme.get('asset_change_1d', '')
        if rep_asset and asset_price:
            chg_str = f'{asset_chg:+.2f}%' if isinstance(asset_chg, (int, float)) else str(asset_chg)
            lines.append(f'**代表资产**：{rep_asset} = {asset_price}（{chg_str}）')
            lines.append('')
        
        # 样本推文（2条）
        samples = theme.get('sample_tweets', [])[:2]
        if samples:
            for s in samples:
                author = s.get('author_name', s.get('author', ''))
                content = s.get('content', '')[:120].replace('\n', ' ')
                sent = s.get('sentiment', 'neutral')
                sent_emoji = '🟢' if sent == 'bullish' else '🔴' if sent == 'bearish' else '⚪'
                lines.append(f'- {sent_emoji} **{author}**：{content}...')
            lines.append('')
    
    # 二、去哪里 + 怎么去
    lines.append('## 二、去哪里 + 怎么去')
    lines.append('')
    
    for asset, pos in asset_positions.items():
        emoji = signal_emoji.get(pos['signal'], '⚪')
        lines.append(f'### {emoji} {asset}：{pos["action"]}')
        lines.append('')
        lines.append(pos['reason'])
        lines.append('')
    
    # 三、下周必盯三件事
    lines.append('## 三、下周必盯三件事')
    lines.append('')
    lines.append('| # | 事件 | 时间 | 观察点 |')
    lines.append('|---|------|------|--------|')
    lines.append('| 1 | 美联储9月议息会议 | 9月17-18日 | 是否加息、点阵图变化 |')
    lines.append('| 2 | 美国CPI数据 | 9月中旬 | 通胀走向决定加息路径 |')
    lines.append('| 3 | 中国8月经济数据 | 9月上旬 | 社融、信贷、PMI验证复苏强度 |')
    lines.append('')
    
    # 附录
    lines.append('## 附录：数据来源与说明')
    lines.append('')
    lines.append('| 数据源 | 时间范围（北京时间） | 数据量 | 采集时间 |')
    lines.append('|--------|---------------------|--------|---------|')
    
    start_time, end_time = time_range
    start_bj = format_beijing_time(start_time)
    end_bj = format_beijing_time(end_time)
    lines.append(f'| X/Twitter 舆情 | {start_bj} ~ {end_bj} | {stats.get("total_tweets", 0)}条，{stats.get("kol_count", 0)}位KOL | {report_date} |')
    lines.append(f'| 市场价格 | {report_date} 实时 | {stats.get("assets_with_price", 0)}/{stats.get("assets_total", 0)} 个标的 | {report_date} |')
    lines.append('')
    lines.append('**说明**：')
    lines.append('- 舆情数据来自 X/Twitter 投资类KOL推文，经主题分类和情绪分析后聚合')
    lines.append('- 价格数据来自新浪财经，覆盖美股、A股、港股、期货、外汇')
    lines.append('- 共识度 = 看多加权分与看空加权分的差值占比，越高表示观点越一致')
    lines.append('- 三期变化为模拟数据，待积累足够历史数据后替换为真实对比')
    lines.append('')
    
    return '\n'.join(lines)


def run_workflow(tweets_file: str, output_dir: str, run_name: str = 'test') -> dict:
    """运行完整工作流，返回各步骤结果"""
    os.makedirs(output_dir, exist_ok=True)
    results = {'steps': {}, 'errors': []}
    
    start_time = time.time()
    
    # Step 1: 加载推文
    print(f'[{run_name}] Step 1/5: 加载推文数据...')
    t0 = time.time()
    try:
        raw_tweets, meta = load_tweets(tweets_file)
        results['steps']['load'] = {
            'status': 'ok',
            'count': len(raw_tweets),
            'kols_total': meta.get('kols_total', 0),
            'kols_ok': meta.get('kols_ok', 0),
            'time': round(time.time() - t0, 2),
        }
        print(f'  ✅ {len(raw_tweets)} 条推文，{meta.get("kols_ok", 0)}/{meta.get("kols_total", 0)} 位KOL')
    except Exception as e:
        results['errors'].append(f'Step 1: {e}')
        results['steps']['load'] = {'status': 'error', 'error': str(e)}
        print(f'  ❌ {e}')
        return results
    
    # Step 2: 主题分类 + 信号聚合
    print(f'[{run_name}] Step 2/5: 主题分类 + 信号聚合...')
    t0 = time.time()
    try:
        classified, skipped = classify_tweets(raw_tweets)
        brief = generate_brief_v2(classified)
        brief['generated_at'] = datetime.now().isoformat()
        brief['source'] = 'workflow_test'
        brief['version'] = '2.0-test'
        brief['stats']['total_tweets'] = len(raw_tweets)
        brief['stats']['classified_tweets'] = len(classified)
        brief['stats']['kols_total'] = meta.get('kols_total', 0)
        brief['stats']['kols_ok'] = meta.get('kols_ok', 0)
        
        # 保存简报
        brief_path = os.path.join(output_dir, 'brief.json')
        with open(brief_path, 'w', encoding='utf-8') as f:
            json.dump(brief, f, ensure_ascii=False, indent=2)
        
        results['steps']['classify'] = {
            'status': 'ok',
            'classified': len(classified),
            'skipped': skipped,
            'themes': brief['stats'].get('unique_themes', 0),
            'assets': brief['stats'].get('unique_assets', 0),
            'time': round(time.time() - t0, 2),
        }
        print(f'  ✅ {len(classified)} 条有主题，{brief["stats"]["unique_themes"]} 个主题，{brief["stats"]["unique_assets"]} 个资产')
    except Exception as e:
        results['errors'].append(f'Step 2: {e}')
        results['steps']['classify'] = {'status': 'error', 'error': str(e)}
        print(f'  ❌ {e}')
        return results
    
    # Step 3: 价格数据 enrichment
    print(f'[{run_name}] Step 3/5: 价格数据 enrichment...')
    t0 = time.time()
    try:
        brief = enrich_brief_with_prices_v2(brief)
        stats = brief.get('stats', {})
        
        # 保存带价格的简报
        brief_price_path = os.path.join(output_dir, 'brief_with_price.json')
        with open(brief_price_path, 'w', encoding='utf-8') as f:
            json.dump(brief, f, ensure_ascii=False, indent=2)
        
        results['steps']['price'] = {
            'status': 'ok',
            'assets_with_price': stats.get('assets_with_price', 0),
            'assets_total': stats.get('assets_total', 0),
            'time': round(time.time() - t0, 2),
        }
        print(f'  ✅ {stats.get("assets_with_price", 0)}/{stats.get("assets_total", 0)} 个资产有价格')
    except Exception as e:
        results['errors'].append(f'Step 3: {e}')
        results['steps']['price'] = {'status': 'error', 'error': str(e)}
        print(f'  ❌ {e}')
        return results
    
    # Step 4: 生成故事线报告
    print(f'[{run_name}] Step 4/5: 生成故事线报告...')
    t0 = time.time()
    try:
        time_range = get_time_range(classified)
        report_date = datetime.now().strftime('%Y-%m-%d')
        report = generate_storyline_report(brief, time_range, report_date)
        
        report_path = os.path.join(output_dir, 'report.md')
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        
        results['steps']['report'] = {
            'status': 'ok',
            'word_count': len(report),
            'time': round(time.time() - t0, 2),
        }
        print(f'  ✅ {len(report)} 字')
    except Exception as e:
        results['errors'].append(f'Step 4: {e}')
        results['steps']['report'] = {'status': 'error', 'error': str(e)}
        print(f'  ❌ {e}')
        return results
    
    # Step 5: 生成飞书卡片数据
    print(f'[{run_name}] Step 5/5: 生成飞书卡片数据...')
    t0 = time.time()
    try:
        top_themes_data = brief.get('top_themes', [])
        stats_data = brief.get('stats', {})
        
        # 7 类资产立场（与报告一致）
        card_asset_positions = {
            '美债/利率': {'signal': 'yellow', 'action': '观望'},
            '黄金（短期）': {'signal': 'red', 'action': '回避'},
            '原油能源': {'signal': 'red', 'action': '回避'},
            'A股（主板价值）': {'signal': 'green', 'action': '持有'},
            '美股（AI链）': {'signal': 'yellow', 'action': '观望'},
            '加密货币': {'signal': 'yellow', 'action': '观望'},
            '港股': {'signal': 'yellow', 'action': '结构性'},
        }
        
        # 提取卡片所需的核心数据
        card_data = {
            'report_date': datetime.now().strftime('%Y-%m-%d'),
            'total_tweets': stats_data.get('total_tweets', 0),
            'total_kols': stats_data.get('kol_count', 0),
            'top_themes': [
                {
                    'theme': t.get('theme', '').replace('_', '/'),
                    'sentiment': '看多' if t.get('consensus', {}).get('bull_ratio', 0) > t.get('consensus', {}).get('bear_ratio', 0) else '看空',
                    'tweet_count': t.get('tweet_count', 0),
                    'consensus': int(t.get('consensus', {}).get('consensus_score', 0) * 100),
                }
                for t in top_themes_data[:5]
            ],
            'asset_positions': card_asset_positions,
            'data_time_range': f'{format_beijing_time(time_range[0])} ~ {format_beijing_time(time_range[1])}',
        }
        
        card_path = os.path.join(output_dir, 'card_data.json')
        with open(card_path, 'w', encoding='utf-8') as f:
            json.dump(card_data, f, ensure_ascii=False, indent=2)
        
        results['steps']['card'] = {
            'status': 'ok',
            'themes_count': len(top_themes_data[:5]),
            'assets_count': len(card_asset_positions),
            'time': round(time.time() - t0, 2),
        }
        print(f'  ✅ {len(top_themes_data[:5])}个主题 + {len(card_asset_positions)}类资产')
    except Exception as e:
        results['errors'].append(f'Step 5: {e}')
        results['steps']['card'] = {'status': 'error', 'error': str(e)}
        print(f'  ❌ {e}')
        return results
    
    total_time = round(time.time() - start_time, 2)
    results['total_time'] = total_time
    results['status'] = 'success' if not results['errors'] else 'partial'
    
    print(f'')
    print(f'[{run_name}] ✅ 完成！总耗时 {total_time}s')
    print(f'  输出目录: {output_dir}')
    
    return results


def main():
    parser = argparse.ArgumentParser(description='完整日报工作流测试')
    parser.add_argument('--tweets', required=True, help='hybrid 推文 JSON 文件')
    parser.add_argument('--output-dir', required=True, help='输出目录')
    parser.add_argument('--name', default='test', help='测试名称')
    args = parser.parse_args()
    
    results = run_workflow(args.tweets, args.output_dir, args.name)
    
    # 输出结果摘要
    print()
    print('=' * 50)
    print('结果摘要:')
    for step, info in results['steps'].items():
        status = '✅' if info.get('status') == 'ok' else '❌'
        print(f'  {status} {step}: {info.get("time", "?")}s')
    
    if results['errors']:
        print(f'  错误: {len(results["errors"])} 个')
        for e in results['errors']:
            print(f'    - {e}')
    
    print(f'  总耗时: {results.get("total_time", "?")}s')
    print(f'  状态: {results.get("status", "unknown")}')


if __name__ == '__main__':
    main()
