"""
IS-001 补漏：从腾讯 API 拉取 520900 最新数据，写入原 DB
避免使用 refetch_etf_data.py（有路径 bug 写到 scripts/etf_data_live/）
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.data.writer import DataWriter
import sqlite3

# 尝试用 DataWriter 自带的方法
print("原 DB:", ROOT / 'etf_data_live' / 'etf.db')

# 用 sqlite3 直接 COPY（更稳妥）
src = sqlite3.connect(str(ROOT / 'scripts' / 'etf_data_live' / 'etf.db'))
dst = sqlite3.connect(str(ROOT / 'etf_data_live' / 'etf.db'))

# 1. 查原 DB 中 520900 最新日期
cur = dst.cursor()
cur.execute("SELECT MAX(date) FROM daily WHERE code='520900'")
old_max = cur.fetchone()[0]
print(f"原 DB 520900 最大日期: {old_max}")

# 2. 查新 DB 中 520900 最新日期
cur2 = src.cursor()
cur2.execute("SELECT MAX(date) FROM daily WHERE code='520900'")
new_max = cur2.fetchone()[0]
print(f"新 DB 520900 最大日期: {new_max}")

# 3. 把新 DB 中 520900 的新数据复制到原 DB
if new_max > old_max:
    cur2.execute("SELECT code, date, open, close, high, low, volume, amount FROM daily WHERE code='520900' AND date > ?", (old_max,))
    new_rows = cur2.fetchall()
    print(f"待插入 520900 新数据: {len(new_rows)} 条")
    cur.executemany("INSERT OR IGNORE INTO daily (code, date, open, close, high, low, volume, amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", new_rows)
    dst.commit()
    print(f"已写入 {cur.rowcount} 条新数据到原 DB")
else:
    print("新 DB 没有更新数据，无需补充")

# 4. 验证
cur.execute("SELECT MIN(date), MAX(date), COUNT(*) FROM daily WHERE code='520900'")
print(f"原 DB 520900 验证: {cur.fetchone()}")

src.close()
dst.close()
print("✅ 520900 数据补全完成")
