#!/usr/bin/env python3
"""
CSV迁移到SQLite脚本 - ⚠️ 已废弃，请使用 repair_data.py

此脚本用于历史数据迁移，存在以下问题：
1. CSV字段顺序(date,open,high,low,close)与腾讯API(date,open,close,high,low)不一致
2. 直接按位置存储会导致high/low/close错位

**正确做法**：从腾讯API直接获取数据，使用 repair_data.py

Usage:
    python scripts/migrate_csv_to_sqlite.py

⚠️ 警告：此脚本仅用于参考，不建议执行
"""

import sqlite3, glob, os, re
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
COLD_DIR = BASE_DIR / "etf_data_live"
DB_PATH = COLD_DIR / "etf.db"

def extract_code(filename: str) -> str:
    """从文件名提取代码（去掉sh/sz前缀）"""
    name = os.path.basename(filename)
    m = re.match(r'^(sh|sz)(\d+)\.csv$', name, re.I)
    if m:
        return m.group(2)
    return name.replace('.csv', '')

def migrate():
    print("⚠️ 警告：此脚本已废弃，请使用 repair_data.py")
    print("⚠️ 原因：CSV字段顺序与腾讯API不一致，直接迁移会导致数据错误")
    return
    
    # 以下代码仅作参考，不执行
    """
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
                # ⚠️ 注意：CSV格式是 date,open,high,low,close,volume
                # 但腾讯API格式是 date,open,close,high,low,volume
                # 如果直接按位置存储，需要做字段映射！
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
    # ... 验证代码 ...
    conn.close()
    """

if __name__ == '__main__':
    migrate()