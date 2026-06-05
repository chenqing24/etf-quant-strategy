#!/usr/bin/env python3
"""记录 512480 清仓交易（实盘，2.078 @ 3500 股）

⚠️ 绕开 record_sell 的 pos=None bug（US-024 待修）
   直接手工 INSERT trade_history + 更新 performance file
"""
import sys
import os
import json
import sqlite3
from datetime import datetime

sys.path.insert(0, '.')
os.chdir('/home/qwenpaw/.qwenpaw/workspaces/default/etf_strategy')

from src.trade.tracker import TradeTracker, TradeRecord

# 1. 准备数据
SELL_PRICE = 2.078
QUANTITY = 3500
ENTRY_PRICE = 2.174
PNL = (SELL_PRICE - ENTRY_PRICE) * QUANTITY  # -336 元
SELL_AMOUNT = SELL_PRICE * QUANTITY  # 7273 元
TRADE_DATE = '2026-06-05'
TRADE_TIME = '2026-06-05 14:32:00'

print(f"=== 准备卖单 ===")
print(f"  512480 3500股 @ {SELL_PRICE}")
print(f"  金额 = {SELL_AMOUNT} 元")
print(f"  盈亏 = {PNL} 元 (亏损)")
print(f"  实际 3500*2.078 = {3500*SELL_PRICE}")
print(f"  PNL 验证 = (2.078-2.174)*3500 = {(2.078-2.174)*3500}")
print()

# 2. 手工 INSERT trade_history（模拟 record_sell 应做的逻辑）
conn = sqlite3.connect('etf_data_live/etf.db')
cur = conn.cursor()

print(f"=== INSERT trade_history ===")
cur.execute("""
    INSERT INTO trade_history (
        date, code, name, action, price, quantity, amount, reason,
        actual_pnl, realtime_price, price_deviation, rsi_14, day_change_pct, score,
        emotion, session, is_real, is_paper,
        model, strategy, evaluation, snapshot_ref
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    TRADE_DATE, '512480', '国联安半导体ETF', 'sell',
    SELL_PRICE, QUANTITY, SELL_AMOUNT,
    'fomo追高纪律止损 (US-023方案E监控触发)',
    PNL,
    SELL_PRICE, 0.0, 0.0, 0.0, 0,  # sell端实时数据填0
    'calm', 'D', 1, 0,  # emotion=calm(纪律止损), session=D(下午)
    'US-023-方案E', '纪律止损(fomo追高)', 'fomo追高纪律止损, 监控规则跌破2.10触发', 'us023-512480-stop-20260605'
))
trade_id = cur.lastrowid
conn.commit()
print(f"  ✅ INSERT 成功, id={trade_id}")
print()

# 3. 验证 trade_history
print(f"=== 验证 trade_history[id={trade_id}] ===")
row = cur.execute(
    "SELECT id, date, code, action, price, quantity, amount, actual_pnl, is_real, emotion, reason FROM trade_history WHERE id = ?",
    (trade_id,)
).fetchone()
print(f"  id={row[0]} date={row[1]} code={row[2]} action={row[3]}")
print(f"  price={row[4]} qty={row[5]} amount={row[6]}")
print(f"  pnl={row[7]} is_real={row[8]} emotion={row[9]}")
print(f"  reason={row[10]}")
print()

# 4. 验证 recompute_cash
print(f"=== 验证 recompute_cash() ===")
tracker = TradeTracker()
new_cash = tracker.recompute_cash()
print(f"  旧现金 = 5309.3")
print(f"  卖单回收 = +{SELL_AMOUNT}")
print(f"  新现金预期 = 5309.3 + {SELL_AMOUNT} = {5309.3 + SELL_AMOUNT}")
print(f"  实际 recompute_cash() = {new_cash}")
assert abs(new_cash - (5309.3 + SELL_AMOUNT)) < 0.01, f"现金计算错误!"
print(f"  ✅ 现金计算正确")
print()

# 5. 验证 get_holdings()
print(f"=== 验证 get_holdings() ===")
holdings = tracker.get_holdings()
print(f"  持仓数 = {len(holdings)} (预期 2)")
for h in holdings:
    print(f"  {h.code} {h.name} qty={h.quantity} entry={h.entry_price}")
assert len(holdings) == 2, f"持仓数错误! 实际={len(holdings)}"
assert all(h.code != '512480' for h in holdings), "512480 应已清仓!"
print(f"  ✅ 持仓数 = 2, 512480 已清仓")
print()

# 6. 验证 total_asset
print(f"=== 验证总资产 ===")
account = tracker.get_account_summary()
print(f"  现金 = {account['cash']}")
print(f"  持仓市值 = {account['positions_value']}")
print(f"  总资产 = {account['total_asset']}")
print(f"  持仓数 = {account['hold_count']}")
print()

# 7. 列出 is_real=1 的所有交易
print(f"=== 验证 trade_history 全部 is_real=1 交易 ===")
for row in cur.execute("SELECT id, date, code, action, price, quantity, is_real, reason FROM trade_history WHERE is_real=1 ORDER BY id"):
    print(f"  id={row[0]} {row[1]} {row[2]} {row[3]} @{row[4]} qty={row[5]} is_real={row[6]} reason={row[7]!r}")
conn.close()

print()
print(f"=== 总结 ===")
print(f"  ✅ 512480 卖单已入库 trade_history (id={trade_id}, is_real=1)")
print(f"  ✅ 现金 = {new_cash} 元 (预期 12582.3)")
print(f"  ✅ 持仓 = 2 只 (515050 + 515070), 512480 已清仓")
print(f"  ⚠️ 诚实标记: 走的是手工 INSERT，不是 record_sell API（US-024 待修 bug）")
print(f"  ⚠️ 诚实标记: audit_log 没记录 (同样原因 record_sell 被 pos=None 跳过)")
print()
print(f"=== 下一步 ===")
print(f"  1. 重跑日报覆盖 09:58 旧报告:")
print(f"     python -m src.cli.decision -m daily --output brief --force")
print(f"  2. 验证 report_20260605.txt 显示 '当前持仓 2只'")
print(f"  3. 监控 cron 13:00/14:00 看到 2 只持仓自动安静")
