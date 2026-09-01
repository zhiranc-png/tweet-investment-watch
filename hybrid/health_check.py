#!/usr/bin/env python3
"""
X 采集健康检查脚本

三级响应机制：
- 🟡 一级（告警）：单次采集有 1 个指标异常 → 发告警通知
- 🟠 二级（降频）：连续 2 次同一指标异常 → 自动跳过下一次采集（冷却 6 小时）
- 🔴 三级（暂停）：连续 3 次异常 → 自动暂停所有采集 24 小时

用法：
    # 采集前检查：是否需要跳过本次采集
    python hybrid/health_check.py --check-skip
    
    # 采集后评估：检查本次采集质量
    python hybrid/health_check.py --evaluate --tweets data/hybrid_tweets_XXX.json --brief data/brief_XXX.json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

# ============================================================
# 配置
# ============================================================

# 预期基准值（基于历史数据的合理下限）
EXPECTED_TWEETS = 200          # 每次采集预期至少 200 条推文
EXPECTED_KOL_RATIO = 0.75      # 至少 75% 的 KOL 成功采集（94 × 0.75 ≈ 70）
MIN_DURATION_SEC = 300         # 采集耗时下限（秒），少于 5 分钟可能被限流
MAX_DURATION_SEC = 3600        # 采集耗时上限（秒），超过 1 小时可能卡住

# 三级响应阈值
WARNING_THRESHOLD = 1          # 1 次异常 = 告警
COOLDOWN_THRESHOLD = 2         # 连续 2 次异常 = 降频（跳过下一次）
PAUSE_THRESHOLD = 3            # 连续 3 次异常 = 暂停 24 小时

# 冷却/暂停时长（小时）
COOLDOWN_SKIP_HOURS = 6
PAUSE_DURATION_HOURS = 24

# 状态文件路径
STATE_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'health_status.json')


# ============================================================
# 状态管理
# ============================================================

def load_state() -> dict:
    """加载健康状态"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        'current_level': 'normal',       # normal / warning / cooling / paused
        'consecutive_failures': 0,
        'last_failure_reason': '',
        'last_check_time': None,
        'last_check_result': 'normal',
        'skip_until': None,              # ISO 格式时间，此时间前跳过采集
        'history': []                    # 最近 20 次检查记录
    }


def save_state(state: dict):
    """保存健康状态"""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def add_history(state: dict, record: dict):
    """添加历史记录（保留最近 20 条）"""
    record['time'] = datetime.utcnow().isoformat()
    state['history'].insert(0, record)
    state['history'] = state['history'][:20]


# ============================================================
# 健康检查
# ============================================================

def check_tweet_count(tweets_data: dict) -> tuple[bool, str]:
    """检查推文数量"""
    total = len(tweets_data.get('tweets', []))
    if total < EXPECTED_TWEETS * 0.6:
        return False, f"推文数严重不足：{total} 条（预期 ≥ {int(EXPECTED_TWEETS * 0.6)}）"
    if total < EXPECTED_TWEETS:
        return False, f"推文数偏少：{total} 条（预期 ≥ {EXPECTED_TWEETS}）"
    return True, f"推文数正常：{total} 条"


def check_kol_success(tweets_data: dict) -> tuple[bool, str]:
    """检查 KOL 采集成功率"""
    total_kols = tweets_data.get('kols_total', 94)
    ok_kols = tweets_data.get('kols_ok', 0)
    if total_kols == 0:
        return False, "KOL 总数为 0，数据异常"
    ratio = ok_kols / total_kols
    if ratio < EXPECTED_KOL_RATIO:
        return False, f"KOL 成功率偏低：{ok_kols}/{total_kols}（{ratio:.0%}，预期 ≥ {EXPECTED_KOL_RATIO:.0%}）"
    return True, f"KOL 成功率正常：{ok_kols}/{total_kols}（{ratio:.0%}）"


def check_duration(duration_sec: float) -> tuple[bool, str]:
    """检查采集耗时"""
    if duration_sec < MIN_DURATION_SEC:
        return False, f"采集耗时过短：{duration_sec:.0f} 秒（预期 ≥ {MIN_DURATION_SEC} 秒，可能被限流）"
    if duration_sec > MAX_DURATION_SEC:
        return False, f"采集耗时过长：{duration_sec:.0f} 秒（预期 ≤ {MAX_DURATION_SEC} 秒，可能卡住）"
    return True, f"采集耗时正常：{duration_sec:.0f} 秒"


def evaluate_health(tweets_file: str, brief_file: str, duration_sec: float = None) -> dict:
    """
    评估本次采集健康状态
    
    Returns:
        {
            'overall': 'normal' | 'warning',
            'checks': [{'name': str, 'passed': bool, 'message': str}],
            'failure_reasons': [str]
        }
    """
    checks = []
    failure_reasons = []
    
    # 读取推文数据
    tweets_data = {}
    if os.path.exists(tweets_file):
        with open(tweets_file, 'r', encoding='utf-8') as f:
            tweets_data = json.load(f)
    else:
        checks.append({'name': '文件存在', 'passed': False, 'message': f'推文文件不存在：{tweets_file}'})
        failure_reasons.append('推文文件不存在')
        return {'overall': 'warning', 'checks': checks, 'failure_reasons': failure_reasons}
    
    # 检查 1：推文数量
    passed, msg = check_tweet_count(tweets_data)
    checks.append({'name': '推文数量', 'passed': passed, 'message': msg})
    if not passed:
        failure_reasons.append(msg)
    
    # 检查 2：KOL 成功率
    passed, msg = check_kol_success(tweets_data)
    checks.append({'name': 'KOL 成功率', 'passed': passed, 'message': msg})
    if not passed:
        failure_reasons.append(msg)
    
    # 检查 3：采集耗时（如果提供了的话）
    if duration_sec is not None:
        passed, msg = check_duration(duration_sec)
        checks.append({'name': '采集耗时', 'passed': passed, 'message': msg})
        if not passed:
            failure_reasons.append(msg)
    
    overall = 'warning' if failure_reasons else 'normal'
    return {'overall': overall, 'checks': checks, 'failure_reasons': failure_reasons}


# ============================================================
# 三级响应
# ============================================================

def update_state_after_check(state: dict, result: dict) -> str:
    """
    根据检查结果更新状态，返回新的级别
    
    Returns: new_level (normal / warning / cooling / paused)
    """
    now = datetime.utcnow()
    state['last_check_time'] = now.isoformat()
    state['last_check_result'] = result['overall']
    
    if result['overall'] == 'normal':
        # 恢复正常，清零连续失败计数
        state['consecutive_failures'] = 0
        state['last_failure_reason'] = ''
        if state['current_level'] in ('cooling', 'paused'):
            # 从冷却/暂停中恢复
            state['current_level'] = 'normal'
            state['skip_until'] = None
        else:
            state['current_level'] = 'normal'
    else:
        # 有异常
        state['consecutive_failures'] += 1
        state['last_failure_reason'] = '; '.join(result['failure_reasons'])
        
        if state['consecutive_failures'] >= PAUSE_THRESHOLD:
            # 三级：暂停 24 小时
            state['current_level'] = 'paused'
            state['skip_until'] = (now + timedelta(hours=PAUSE_DURATION_HOURS)).isoformat()
        elif state['consecutive_failures'] >= COOLDOWN_THRESHOLD:
            # 二级：降频，跳过下一次（6 小时）
            state['current_level'] = 'cooling'
            state['skip_until'] = (now + timedelta(hours=COOLDOWN_SKIP_HOURS)).isoformat()
        else:
            # 一级：告警
            state['current_level'] = 'warning'
    
    # 记录历史
    add_history(state, {
        'result': result['overall'],
        'level': state['current_level'],
        'failures': state['consecutive_failures'],
        'reasons': result['failure_reasons'],
    })
    
    return state['current_level']


def should_skip(state: dict) -> tuple[bool, str]:
    """
    检查是否应该跳过本次采集
    
    Returns: (should_skip, reason)
    """
    now = datetime.utcnow()
    
    if state.get('skip_until'):
        skip_until = datetime.fromisoformat(state['skip_until'])
        if now < skip_until:
            remaining = skip_until - now
            hours = remaining.total_seconds() / 3600
            level = state.get('current_level', 'unknown')
            return True, f"处于{level}状态，跳过采集（还剩 {hours:.1f} 小时，至 {skip_until.isoformat()} UTC）"
    
    return False, "正常，可以采集"


# ============================================================
# 飞书告警
# ============================================================

def send_feishu_alert(level: str, result: dict, state: dict):
    """
    发送飞书告警
    
    通过飞书自定义机器人 webhook 发送消息。
    webhook URL 从环境变量 FEISHU_WEBHOOK_URL 读取。
    如果没有配置 webhook，只打印日志不报错。
    """
    webhook_url = os.environ.get('FEISHU_WEBHOOK_URL', '')
    if not webhook_url:
        print("[告警] 未配置 FEISHU_WEBHOOK_URL，跳过飞书通知")
        return
    
    import urllib.request
    
    level_emoji = {
        'warning': '🟡',
        'cooling': '🟠',
        'paused': '🔴',
    }
    emoji = level_emoji.get(level, '⚪')
    
    level_text = {
        'warning': '一级告警',
        'cooling': '二级降频',
        'paused': '三级暂停',
    }
    level_name = level_text.get(level, level)
    
    now_str = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    
    # 构造消息
    checks_text = '\n'.join([
        f"  {'✅' if c['passed'] else '❌'} {c['message']}"
        for c in result['checks']
    ])
    
    content = f"""{emoji} **X 采集健康告警 · {level_name}**

**时间**：{now_str}（北京时间）
**连续异常次数**：{state['consecutive_failures']} 次
**当前状态**：{state['current_level']}

**检查结果**：
{checks_text}
"""
    
    if level == 'cooling':
        content += f"\n⚠️ 已自动降频：跳过下一次采集（冷却 {COOLDOWN_SKIP_HOURS} 小时）"
    elif level == 'paused':
        content += f"\n🚨 已自动暂停：暂停采集 {PAUSE_DURATION_HOURS} 小时，请人工检查 X 账号状态"
    
    payload = {
        'msg_type': 'text',
        'content': {
            'text': content
        }
    }
    
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = resp.read().decode('utf-8')
            print(f"[告警] 飞书消息发送成功: {resp_body[:100]}")
    except Exception as e:
        print(f"[告警] 飞书消息发送失败: {e}")


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='X 采集健康检查')
    parser.add_argument('--check-skip', action='store_true', help='采集前检查：是否跳过本次采集')
    parser.add_argument('--evaluate', action='store_true', help='采集后评估：检查本次采集质量')
    parser.add_argument('--tweets', type=str, help='hybrid_tweets JSON 文件路径')
    parser.add_argument('--brief', type=str, help='brief JSON 文件路径')
    parser.add_argument('--duration', type=float, help='采集耗时（秒）')
    args = parser.parse_args()
    
    state = load_state()
    
    if args.check_skip:
        # 采集前检查
        skip, reason = should_skip(state)
        print(f"健康检查（采集前）：{reason}")
        if skip:
            # 退出码 42 表示跳过（workflow 中根据这个判断）
            sys.exit(42)
        sys.exit(0)
    
    elif args.evaluate:
        # 采集后评估
        if not args.tweets:
            print("错误：--evaluate 需要 --tweets 参数")
            sys.exit(1)
        
        result = evaluate_health(args.tweets, args.brief, args.duration)
        
        print("=" * 50)
        print("X 采集健康检查报告")
        print("=" * 50)
        for c in result['checks']:
            status = '✅' if c['passed'] else '❌'
            print(f"  {status} {c['message']}")
        print("-" * 50)
        print(f"综合结果：{'正常 ✅' if result['overall'] == 'normal' else '异常 ⚠️'}")
        
        # 更新状态
        old_level = state.get('current_level', 'normal')
        new_level = update_state_after_check(state, result)
        save_state(state)
        
        print(f"状态变化：{old_level} → {new_level}")
        print(f"连续异常：{state['consecutive_failures']} 次")
        
        # 发送告警（状态变化时才发，避免刷屏）
        if result['overall'] == 'warning' and new_level in ('warning', 'cooling', 'paused'):
            send_feishu_alert(new_level, result, state)
        
        # 状态文件也作为 artifact 保存
        print(f"\n状态文件：{STATE_FILE}")
        
        sys.exit(0 if result['overall'] == 'normal' else 1)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
