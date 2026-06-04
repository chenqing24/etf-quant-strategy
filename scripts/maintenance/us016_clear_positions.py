#!/usr/bin/env python3
"""US-016 清理脚本: 备份 + 清空 positions 派生表

按 SOUL 规则 21: 业务数据删除前确认"数据 vs 角色"（标记角色，不删数据）
本脚本: 备份数据到 JSON, 然后清空 positions 表（事实源是 trade_history）
保留表结构以便其他模块继续引用（向后兼容）
"""
import sqlite3
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
os.chdir(ROOT)

DB_PATH = 'etf_data_live/etf.db'
BACKUP_PATH = f'etf_data_live/positions_legacy_backup_{datetime.now().strftime("%Y%m%d")}.json'

print("=" * 60)
print("US-016 positions 派生表清理")
print("=" * 60)

conn = sqlite3.connect(DB_PATH)

# 1. 检查 positions 表是否存在
c = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name='positions'"
)
if not c.fetchone():
    print("✅ positions 表不存在，无需清理")
    sys.exit(0)

# 2. 导出数据
c = conn.execute("SELECT * FROM positions")
cols = [d[0] for d in c.description]
rows = c.fetchall()
print(f"\n当前 positions 表: {len(rows)} 行")
print(f"字段: {cols}")

if rows:
    # 3. 备份到 JSON
    with open(BACKUP_PATH, 'w') as f:
        json.dump({
            'backup_time': datetime.now().isoformat(),
            'reason': 'US-016 清理 positions 派生表 (事实源迁移到 trade_history)',
            'columns': cols,
            'rows': [list(r) for r in rows],
        }, f, indent=2, ensure_ascii=False, default=str)
    print(f"✅ 已备份到: {BACKUP_PATH}")
else:
    print("positions 表已为空，跳过备份")

# 4. 清空 positions 表（DELETE FROM, 保留 schema）
conn.execute("DELETE FROM positions")
conn.commit()
print(f"✅ positions 表已清空（保留 schema）")

# 5. 验证
c = conn.execute("SELECT COUNT(*) FROM positions")
count = c.fetchone()[0]
print(f"✅ 验证: positions 表当前 {count} 行")

conn.close()
print("\n" + "=" * 60)
print("清理完成")
print("=" * 60)
print("""
后续:
- 1 周后 (2026-06-11) DROP TABLE positions (US-016-task-001)
- 其他模块 SELECT FROM positions 会返回空 (安全)
- 真相源已统一: trade_history
""")
