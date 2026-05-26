#!/usr/bin/env python3
"""
CSV迁移到SQLite脚本
将 etf_data_live/*.csv 迁移到 etf_data_live/etf.db daily表

Usage:
    python scripts/migrate_csv_to_sqlite.py

验收标准:
    SELECT COUNT(*) FROM daily ≈ 12092 ±5%
    SELECT COUNT(DISTINCT code) FROM daily = 33
"""

import sqlite3, glob, os, re
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
COLD_DIR = BASE_DIR / "etf_data_live"
DB_PATH = COLD_DIR / "etf.db"

def extract_code(filename: str) -> str:
    """从文件名提取代码（去掉sh/sz前缀）"""
    name = os.path.basename(filename)
    # sh510300.csv -> 510300
    m = re.match(r'^(sh|sz)(\d+)\.csv$', name, re.I)
    if m:
        return m.group(2)
    return name.replace('.csv', '')

def migrate():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    csv_files = sorted(COLD_DIR.glob("*.csv"))
    print(f"找到 {len(csv_files)} 个CSV文件")

    total_rows = 0
    for fpath in csv_files:
        code = extract_code(str(fpath))
        rows = 0
        with open(fpath, 'r') as f:
            next(f)  # 跳过表头
            for line in f:
                parts = line.strip().split(',')
                if len(parts) < 6:
                    continue
                date, open_, high, low, close, vol = parts[:6]
                try:
                    cur.execute(
                        'INSERT OR REPLACE INTO daily (code, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)',
                        (code, date, float(open_), float(high), float(low), float(close), int(float(vol)))
                    )
                    rows += 1
                except Exception as e:
                    print(f"  ⚠️  {code}@{date}: {e}")
        total_rows += rows
        print(f"  {code}: {rows} rows")

    conn.commit()

    # 验证
    cur.execute('SELECT COUNT(*) FROM daily')
    db_total = cur.fetchone()[0]
    cur.execute('SELECT COUNT(DISTINCT code) FROM daily')
    etf_count = cur.fetchone()[0]
    cur.execute('SELECT MIN(date), MAX(date) FROM daily')
    date_range = cur.fetchone()

    print(f"\n=== 迁移结果 ===")
    print(f"总数据量: {db_total} (CSV总行数≈12092)")
    print(f"ETF数量: {etf_count}")
    print(f"日期范围: {date_range[0]} ~ {date_range[1]}")

    conn.close()
    return db_total

if __name__ == '__main__':
    migrate()