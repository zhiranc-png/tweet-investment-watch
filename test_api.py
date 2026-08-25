"""调试脚本：测试 X API 是否正常工作"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(__file__))

from src.collectors.x_api import XApiCollector

auth_token = os.environ.get("AUTH_TOKEN", "")
ct0 = os.environ.get("CT0", "")

print(f"auth_token: {'已设置' if auth_token else '未设置'} (长度: {len(auth_token)})")
print(f"ct0: {'已设置' if ct0 else '未设置'} (长度: {len(ct0)})")
print()

if not auth_token or not ct0:
    print("❌ 缺少 AUTH_TOKEN 或 CT0 环境变量")
    sys.exit(1)

collector = XApiCollector(auth_token=auth_token, ct0=ct0, request_delay=1)

print("🔍 测试 1: 健康检查...")
health = collector.health_check()
print(f"   结果: {json.dumps(health, indent=2, ensure_ascii=False)}")
print()

print("🔍 测试 2: 搜索 'NVDA' (Top)...")
try:
    results = collector._search("NVDA min_faves:100", limit=5, search_type="Top")
    print(f"   返回 {len(results)} 条")
    for i, r in enumerate(results[:3]):
        print(f"   {i+1}. @{r['author']}: {r['content'][:60]}... ({r['likes']} likes)")
except Exception as e:
    print(f"   ❌ 异常: {e}")
    import traceback
    traceback.print_exc()
print()

print("🔍 测试 3: 搜索 'from:federalreserve' (Latest)...")
try:
    results = collector._search("from:federalreserve", limit=5, search_type="Latest")
    print(f"   返回 {len(results)} 条")
    for i, r in enumerate(results[:3]):
        print(f"   {i+1}. @{r['author']}: {r['content'][:60]}... ({r['likes']} likes)")
except Exception as e:
    print(f"   ❌ 异常: {e}")
    import traceback
    traceback.print_exc()

print("\n🏁 测试完成")
