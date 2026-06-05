#!/usr/bin/env python3
"""US-024 Phase 2 复现 record_buy 事务回滚 bug + 验证修复方案

模拟 6/5 13:50 之前的持仓：515050 + 512480
模拟 6/5 13:50 之后调 record_buy('515070') 看实际行为
"""
import sys
import os
import tempfile
import sqlite3

sys.path.insert(0, '.')
os.chdir('/home/qwenpaw/.qwenpaw/workspaces/default/etf_strategy')

from src.trade.tracker import TradeTracker, TradeRecord

tmpdir = tempfile.mkdtemp()
db_path = os.path.join(tmpdir, 'test.db')
print(f"tmp db = {db_path}")

# 1. 初始化 schema - 用 004（trade tables）足够 record_buy 跑
from pathlib import Path
from scripts.init_database import init_database
# 004 schema 包含 trade_history，但 positions 表需要 is_reference 字段（003 加的）
# 这里直接手动建表，更可控
import sqlite3
conn = sqlite3.connect(db_path)
conn.executescript(open('schema/migrations/004_add_trade_tables.sql').read())
# positions 表补 is_reference 字段（从 003 推断）
try:
    conn.execute("ALTER TABLE positions ADD COLUMN is_reference INTEGER DEFAULT 0")
except Exception:
    pass
conn.commit()
conn.close()
print("✅ schema 初始化完成")

# 2. 写入 515050 + 512480 的 trade_history
tracker = TradeTracker(db_path=db_path)
tracker.save_trade(TradeRecord(date='2026-06-02', code='515050', name='通信ETF华夏', action='buy', price=1.197, quantity=2600, amount=3112.2, reason='MA20突破', is_real=1))
tracker.save_trade(TradeRecord(date='2026-06-04', code='512480', name='半导体ETF国联安', action='buy', price=2.174, quantity=3500, amount=7609, reason='低开追高', is_real=1))

# 3. 初始持仓
print("\n=== 初始持仓 (从 trade_history 重建) ===")
holdings = tracker.get_holdings()
print(f"持仓数 = {len(holdings)}")
for h in holdings:
    print(f"  {h.code} qty={h.quantity} entry={h.entry_price}")

# 4. 调用 record_buy('515070', is_real=0 默认)
print("\n=== 调用 record_buy('515070', is_real=0 默认 - execute_trade 不传) ===")
result = tracker.record_buy(
    code='515070', name='人工智能ETF华夏',
    price=2.574, quantity=1500,
    reason='股票猛拉, 用户追高入场',
    is_real=0  # ← execute_trade 不传，默认 0（模拟）
)
print(f"record_buy 返回: {result}")

# 5. 后状态
print("\n=== record_buy 后状态 ===")
conn = sqlite3.connect(db_path)
cur = conn.cursor()
print("trade_history:")
for row in cur.execute("SELECT id, code, action, quantity, is_real, reason FROM trade_history ORDER BY id"):
    print(f"  {row}")
print("positions:")
for row in cur.execute("SELECT code, entry_date, quantity, is_real, status FROM positions"):
    print(f"  {row}")

# 6. 验证 get_holdings
print("\n=== get_holdings() (US-016 真相源) ===")
holdings = tracker.get_holdings()
print(f"持仓数 = {len(holdings)}")
for h in holdings:
    print(f"  {h.code} qty={h.quantity}")

# 7. 验证 recompute_cash
print(f"\n=== 现金 (recompute_cash) ===")
cash = tracker.recompute_cash()
print(f"  cash = {cash}")

# 8. 清理
import shutil
shutil.rmtree(tmpdir, ignore_errors=True)
