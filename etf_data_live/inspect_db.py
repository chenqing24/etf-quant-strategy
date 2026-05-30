#!/usr/bin/env python3
"""查看数据库表结构"""
import sqlite3
import sys

db_path = 'etf_data_live/etf.db'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 获取所有表
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
print("="*60)
print("数据库表清单")
print("="*60)
for t in tables:
    print(f"  - {t[0]}")

print()

# 查看每个表的结构
for t in tables:
    table_name = t[0]
    print(f"\n{'='*60}")
    print(f"表: {table_name}")
    print("="*60)
    
    # 获取列信息
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    for col in columns:
        print(f"  {col[1]:30s} {col[2]:15s} null={col[3]} default={col[4]}")
    
    # 获取行数
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"  → 共 {count} 行")

conn.close()
print("\n" + "="*60)