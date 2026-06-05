#!/usr/bin/env python3
"""debug US-024 can_buy 实际行为"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, '.')
os.chdir('/home/qwenpaw/.qwenpaw/workspaces/default/etf_strategy')

from src.trade.tracker import TradeTracker, TradeRecord
from src.trade.exceptions import BusinessConstraintError

# 临时 db
tmpdir = tempfile.mkdtemp()
db_path = os.path.join(tmpdir, 'test.db')
conn = sqlite3.connect(db_path)
conn.executescript(open('schema/migrations/004_add_trade_tables.sql').read())
try:
    conn.execute("ALTER TABLE positions ADD COLUMN is_reference INTEGER DEFAULT 0")
except Exception:
    pass
conn.commit()
conn.close()

tracker = TradeTracker(db_path=db_path)

# 写 515050 + 512480 的 trade_history
tracker.save_trade(TradeRecord(date='2026-06-02', code='515050', name='通信ETF华夏', action='buy', price=1.197, quantity=2600, amount=3112.2, reason='test', is_real=1))
tracker.save_trade(TradeRecord(date='2026-06-04', code='512480', name='半导体ETF国联安', action='buy', price=2.174, quantity=3500, amount=7609, reason='test', is_real=1))

print("=== 1. can_buy('515070') 结果 ===")
ok, reason = tracker.can_buy('515070')
print(f"  ok={ok}, reason={reason!r}")

print("\n=== 2. _rebuild_positions_from_trades() 结果 ===")
positions = tracker._rebuild_positions_from_trades()
print(f"  持仓数 = {len(positions)}")
for p in positions:
    print(f"  {p.code} {p.name} qty={p.quantity} status={p.status} is_real={p.is_real}")

print("\n=== 3. record_buy('515070', ...) 实际行为 ===")
try:
    result = tracker.record_buy(code='515070', name='人工智能ETF华夏', price=2.574, quantity=1500, reason='test', is_real=1)
    print(f"  返回 TradeRecord: {result.code if result else None}")
except BusinessConstraintError as e:
    print(f"  ✅ 抛 BusinessConstraintError: {e}")
except Exception as e:
    print(f"  ❌ 抛其他异常: {type(e).__name__}: {e}")

import shutil
shutil.rmtree(tmpdir, ignore_errors=True)
