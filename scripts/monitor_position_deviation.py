#!/usr/bin/env python3
"""
US-023 持仓偏离监控 + 分批处理（方案 E）

背景 (2026-06-05):
- 实际持仓 3 只 (515050/512480/515070), 违反 max_holdings=2
- 515050 卖单 1.317 已挂, 需撤单
- 用户选 E: 分批处理 (不立即强平)

监控规则:
- 515050: 突破 1.30 不卖 (让利润跑), 跌至 1.30 警惕
- 512480: 跌破 2.10 卖出 (提前止损, 优于 -6% = 2.044)
- 515070: 跌破 2.50 卖出 (提前止损, 优于 -6% = 2.419)
- 任一持仓触发 +10% 止盈 → 卖出
- 任一持仓跌破 -6% 止损 → 卖出

输出: 钉钉告警 (如配置) + 控制台
"""
import sys
import os
import argparse
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.data.loader import DataLoader
from src.trade.tracker import TradeTracker
from src.constants import (
    STOP_LOSS_PCT, TAKE_PROFIT_PCT, MAX_HOLD_DAYS,
    TRAILING_THRESHOLD_PCT, TRAILING_STOP_PCT
)


# ── 方案 E 自定义规则 ─────────────────────────────────────
# 跌破触发价: 用户自定义提前止损 (优于系统 -6%)
# 突破触发价: 用户自定义保护利润
E_RULES = {
    '515050': {
        'name': '通信ETF华夏',
        'break_above': 1.30,   # 突破 1.30 不卖 (让利润跑)
        'break_below': None,   # 不设
        'take_profit': 1.197 * (1 + TAKE_PROFIT_PCT),  # 1.317
        'stop_loss':   1.197 * (1 - STOP_LOSS_PCT),    # 1.125
    },
    '512480': {
        'name': '国联安半导体ETF',
        'break_above': None,   # 不设
        'break_below': 2.10,   # 跌破 2.10 卖出 (提前止损, 优于 -6% = 2.044)
        'take_profit': 2.174 * (1 + TAKE_PROFIT_PCT),  # 2.391
        'stop_loss':   2.174 * (1 - STOP_LOSS_PCT),    # 2.044
    },
    '515070': {
        'name': '人工智能ETF华夏',
        'break_above': None,   # 不设
        'break_below': 2.50,   # 跌破 2.50 卖出 (提前止损, 优于 -6% = 2.419)
        'take_profit': 2.574 * (1 + TAKE_PROFIT_PCT),  # 2.831
        'stop_loss':   2.574 * (1 - STOP_LOSS_PCT),    # 2.420
    },
}


def check_holdings() -> list:
    """检查持仓, 返回触发预警的列表"""
    alerts = []
    holdings_map = {h.code: h for h in TradeTracker('.').get_holdings()}

    for code, rule in E_RULES.items():
        h = holdings_map.get(code)
        if not h:
            continue

        current = h.current_price
        pnl_pct = h.pnl_pct
        hold_days = h.hold_days

        # 突破预警
        if rule['break_above'] and current >= rule['break_above']:
            alerts.append({
                'code': code, 'name': rule['name'],
                'type': 'BREAK_ABOVE',
                'msg': f'突破 {rule["break_above"]} (现 {current}), 让利润跑',
                'price': current, 'pnl_pct': pnl_pct, 'hold_days': hold_days,
            })

        # 跌破预警
        if rule['break_below'] and current <= rule['break_below']:
            alerts.append({
                'code': code, 'name': rule['name'],
                'type': 'BREAK_BELOW',
                'msg': f'跌破 {rule["break_below"]} (现 {current}), 建议卖出',
                'price': current, 'pnl_pct': pnl_pct, 'hold_days': hold_days,
            })

        # 止盈预警
        if current >= rule['take_profit']:
            alerts.append({
                'code': code, 'name': rule['name'],
                'type': 'TAKE_PROFIT',
                'msg': f'触发止盈 {rule["take_profit"]:.3f} (现 {current}), 立即卖出',
                'price': current, 'pnl_pct': pnl_pct, 'hold_days': hold_days,
            })

        # 止损预警
        if current <= rule['stop_loss']:
            alerts.append({
                'code': code, 'name': rule['name'],
                'type': 'STOP_LOSS',
                'msg': f'触发止损 {rule["stop_loss"]:.3f} (现 {current}), 立即卖出',
                'price': current, 'pnl_pct': pnl_pct, 'hold_days': hold_days,
            })

        # 持仓天数到期 (max_hold_days=15)
        if hold_days >= MAX_HOLD_DAYS:
            alerts.append({
                'code': code, 'name': rule['name'],
                'type': 'MAX_HOLD_DAYS',
                'msg': f'持仓 {hold_days} 天 ≥ {MAX_HOLD_DAYS} 天, 强制平仓',
                'price': current, 'pnl_pct': pnl_pct, 'hold_days': hold_days,
            })

    return alerts


def main():
    parser = argparse.ArgumentParser(description='US-023 持仓偏离监控 (方案 E)')
    parser.add_argument('--dingtalk', action='store_true', help='告警发钉钉')
    parser.add_argument('--silent', action='store_true', help='静默模式 (cron)')
    args = parser.parse_args()

    alerts = check_holdings()

    if not alerts:
        if not args.silent:
            print('✅ 方案 E: 持仓正常, 无预警')
        return 0

    print('🚨 方案 E 持仓预警:')
    for a in alerts:
        emoji = {
            'BREAK_ABOVE': '🟢', 'BREAK_BELOW': '🔴',
            'TAKE_PROFIT': '🎯', 'STOP_LOSS': '⛔', 'MAX_HOLD_DAYS': '⏰'
        }.get(a['type'], '⚠️')
        print(f'  {emoji} {a["code"]} {a["name"]}: {a["msg"]}')
        print(f'     价 {a["price"]:.3f} 盈亏 {a["pnl_pct"]:+.2f}% 持 {a["hold_days"]}天')

    if args.dingtalk:
        try:
            from src.notify.dingtalk import DingTalkSender
            sender = DingTalkSender(mode='qwenpaw')
            msg = '🚨 方案 E 持仓预警:\n'
            for a in alerts:
                msg += f'- {a["code"]} {a["name"]}: {a["msg"]}\n'
            sender.send(msg)
            print('📨 钉钉通知已发送')
        except Exception as e:
            print(f'⚠️ 钉钉发送失败: {e}')

    return 1  # 有告警返回非零 (cron 退出码)


if __name__ == '__main__':
    sys.exit(main())
