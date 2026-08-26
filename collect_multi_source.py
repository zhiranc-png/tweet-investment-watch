"""
多源数据采集脚本（GitHub Actions 用）
采集中文投资社区数据，作为 X 数据的补充
"""
import sys
import json
sys.path.insert(0, '.')

from src.collectors.multi_source_manager import MultiSourceCollector
from src.collectors.filter import filter_investment_posts

def main():
    mgr = MultiSourceCollector()
    results = mgr.collect_all()
    all_posts = mgr.get_all_posts(results)
    filtered = filter_investment_posts(all_posts)
    
    # 保存
    import os
    os.makedirs('data', exist_ok=True)
    with open('data/multi_source.json', 'w', encoding='utf-8') as f:
        json.dump([p.to_dict() for p in filtered], f, ensure_ascii=False, indent=2)
    
    print(f'多源采集: {len(all_posts)} 条 → 投资相关 {len(filtered)} 条')
    
    # 打印各来源统计
    source_counts = {}
    for p in filtered:
        s = p.source if hasattr(p, 'source') else p.get('source', 'unknown')
        source_counts[s] = source_counts.get(s, 0) + 1
    for src, cnt in sorted(source_counts.items(), key=lambda x: -x[1]):
        print(f'  {src}: {cnt} 条')

if __name__ == '__main__':
    main()
