#!/usr/bin/env python3
"""
补充缺失ETF到SQLite

用途：
    - 检查 CSV 目录和数据库的 ETF 差异
    - 统计缺失的 ETF 和数据行数
    - 辅助数据补充决策

被谁调用：
    - 无（独立工具，一次性使用）
    - 数据维护时手动运行

功能说明：
    - 从 CSV 目录读取 ETF 代码
    - 与数据库已存在的 code 对比
    - 输出缺失数量和补充后预计总行数

使用方式：
    python scripts/check_missing_etfs.py

依赖：
    - sqlite3
    - pandas
    - glob

注意事项：
    - 已豁免 pre-commit 检查（一次性工具）
    - 此脚本仅供参考，不执行实际写入
    - 如需补充数据，使用 scripts/data/refetch_etf_data.py
"""
import sqlite3
import pandas as pd
import glob
import os

DB_PATH = 'etf_data_live/etf.db'
CSV_DIR = '../etf_data_50'

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# 获取已存在的code
existing = set(r[0] for r in cur.execute('SELECT DISTINCT code FROM daily').fetchall())

# 获取CSV目录的code
csv_codes = set(f.split('/')[-1].replace('.csv','') for f in glob.glob(f'{CSV_DIR}/*.csv'))

# 找出缺失的
missing = csv_codes - existing
print(f'缺失ETF数量: {len(missing)}')

# 统计这些缺失ETF的数据情况
total_rows = 0
for code in sorted(missing):
    csv_file = f'{CSV_DIR}/{code}.csv'
    if os.path.exists(csv_file):
        df = pd.read_csv(csv_file)
        total_rows += len(df)

print(f'缺失数据总行数: {total_rows}')
print(f'补充后预计总行数: {cur.execute("SELECT COUNT(*) FROM daily").fetchone()[0] + total_rows}')

conn.close()