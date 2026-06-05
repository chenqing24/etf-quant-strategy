#!/usr/bin/env python3
"""
US-023 持仓恢复正常 → 自动 disable 4 个盘中监控 cron

触发条件: 持仓数 <= 2 (从偏离状态恢复)
动作: qwenpaw cron pause 4 个持仓监控 cron (10:00/11:00/13:00/14:00)

诚实标记 (US-023 调研):
- "持仓恢复正常" 定义: 持仓数 <= 2 (与 max_holdings 对齐)
- 不会自动 resume (如想恢复需手动 qwenpaw cron resume)
- 4 个监控 cron 默认 mon-fri (已是), 5 个工作日执行
"""
import os
import sys
import subprocess
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.trade.tracker import TradeTracker


# ── 4 个持仓监控 cron 名称模式 ──────────────────────────────────
MONITOR_CRON_NAME_PATTERNS = ['持仓偏离监控-10:00', '持仓偏离监控-11:00',
                              '持仓偏离监控-13:00', '持仓偏离监控-14:00']

AGENT_ID = 'default'
MAX_HOLDINGS_NORMAL = 2  # 持仓恢复正常阈值


def get_monitor_cron_job_ids() -> list:
    """获取 4 个持仓监控 cron 的 job_id"""
    result = subprocess.run(
        ['qwenpaw', 'cron', 'list', '--agent-id', AGENT_ID],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    return [
        job['id'] for job in data
        if job.get('name', '') in MONITOR_CRON_NAME_PATTERNS
    ]


def is_cron_paused(job_id: str) -> bool:
    """检查 cron 是否已 paused"""
    result = subprocess.run(
        ['qwenpaw', 'cron', 'state', job_id, '--agent-id', AGENT_ID],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        return False
    try:
        data = json.loads(result.stdout)
        return data.get('paused', False) or data.get('state', {}).get('paused', False)
    except json.JSONDecodeError:
        return False


def pause_cron(job_id: str) -> bool:
    """暂停一个 cron, 返回是否成功"""
    result = subprocess.run(
        ['qwenpaw', 'cron', 'pause', job_id, '--agent-id', AGENT_ID],
        capture_output=True, text=True, timeout=10
    )
    return result.returncode == 0


def main() -> int:
    """主逻辑: 检查持仓, 持仓 <= 2 时暂停 4 个监控 cron"""
    # 1. 检查持仓
    holdings = TradeTracker('.').get_holdings()
    holdings_count = len(holdings)
    is_normal = holdings_count <= MAX_HOLDINGS_NORMAL

    print(f'=== US-023 自动 disable 检测 ===')
    print(f'当前持仓数: {holdings_count}')
    print(f'阈值 (正常): ≤ {MAX_HOLDINGS_NORMAL}')
    print(f'状态: {"✅ 正常" if is_normal else "⚠️ 偏离"}')

    if not is_normal:
        print(f'持仓偏离, 监控 cron 保持 enabled')
        return 0

    # 2. 持仓正常, 暂停 4 个监控 cron
    print(f'\n持仓恢复正常, 开始 pause 4 个监控 cron...')
    job_ids = get_monitor_cron_job_ids()
    if not job_ids:
        print('⚠️ 未找到持仓监控 cron (可能已被删除或名称不匹配)')
        return 1

    paused = []
    skipped = []
    failed = []
    for job_id in job_ids:
        if is_cron_paused(job_id):
            skipped.append(job_id)
            print(f'  ⏭️  {job_id[:8]}... 已 paused, 跳过')
            continue
        if pause_cron(job_id):
            paused.append(job_id)
            print(f'  ✅ {job_id[:8]}... paused')
        else:
            failed.append(job_id)
            print(f'  ❌ {job_id[:8]}... pause 失败')

    print(f'\n=== 汇总 ===')
    print(f'持仓恢复正常: ✅')
    print(f'已 pause: {len(paused)}')
    print(f'已 paused 跳过: {len(skipped)}')
    print(f'失败: {len(failed)}')
    return 0 if not failed else 1


if __name__ == '__main__':
    sys.exit(main())
