#!/usr/bin/env python3
"""验证 weekly 备份完整性"""
import sqlite3
import sys

backup_path = sys.argv[1] if len(sys.argv) > 1 else 'etf_backups/etf_backup_weekly_20260605_163021.db'
print(f"=== 验证备份: {backup_path} ===")
print()

conn = sqlite3.connect(backup_path)
cur = conn.cursor()

print("=== Schema 验证 ===")
tables = sorted([r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()])
for t in tables:
    print(f"  {t}")

print()
print("=== 关键表 row count ===")
for table in ['trade_history', 'positions', 'audit_log', 'etf_names', 'etf_daily']:
    try:
        count = cur.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        print(f"  {table}: {count} 行")
    except Exception as e:
        print(f"  {table}: ❌ {e}")

print()
print("=== trade_history 最近 5 条 ===")
for row in cur.execute("SELECT id, date, code, action, price, quantity, is_real FROM trade_history ORDER BY id DESC LIMIT 5"):
    print(f"  {row}")

print()
print("=== audit_log 最近 5 条 ===")
for row in cur.execute("SELECT id, code, from_state, to_state, detail FROM audit_log ORDER BY id DESC LIMIT 5"):
    print(f"  {row}")

conn.close()
