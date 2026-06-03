#!/usr/bin/env python3
"""
US-002 迁移脚本：etf_names 加 tradable + pool_role 字段（修正版）

设计决策：
- 默认值采用保守策略：tradable=0, pool_role='unclassified'
- 显式标注 14 core + 1 reference + ~30 excluded
- 其余 1431 只保持 unclassified

执行流程：
1. 备份 etf.db → .archive/pre-us002-<时间戳>/etf.db
2. 执行 schema/migrations/003_add_tradable_pool_role.sql
3. UPDATE 14 core（v9 池）
4. UPDATE 510300 → reference
5. UPDATE 港股/海外/红利/低波/债券/商品 → excluded
6. 验证：SELECT pool_role, COUNT(*) FROM etf_names GROUP BY pool_role

幂等性：
- ALTER TABLE 重复执行会报错（先检查列是否存在）
- UPDATE 重复执行幂等（相同 WHERE 不会重复改）

使用方式：
    cd etf_strategy
    python scripts/migrate_pool_roles.py
"""
import os
import sys
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'etf_data_live' / 'etf.db'
MIGRATION_FILE = PROJECT_ROOT / 'schema/migrations/003_add_tradable_pool_role.sql'
ARCHIVE_DIR = PROJECT_ROOT.parent / '.archive'

# v9 池 14 只核心（与 top500_target_pool.txt 一致，除 510300）
CORE_CODES = [
    '588000',  # 科创50ETF华夏
    '512480',  # 证券ETF国泰
    '512880',  # 证券ETF华泰柏瑞
    '512170',  # 医疗ETF华宝
    '520900',  # 红利低波ETF
    '515790',  # 光伏ETF华夏
    '515050',  # 通信ETF华夏
    '512400',  # 有色金属ETF
    '512660',  # 军工ETF
    '515070',  # 人工智能ETF
    '512800',  # 银行ETF华宝
    '512980',  # 传媒ETF
    '512200',  # 房地产ETF
    '515650',  # 消费ETF
]

# 510300 标为大盘参考
REFERENCE_CODES = ['510300']

# 港股/海外/红利/低波/债券/商品（来自 src/utils/config.py exclude_codes）
EXCLUDED_CODES = [
    # 港股/境外
    '159825', '159902', '159915', '159928', '159952', '159997',
    '159920', '159867', '513360', '513050',
    # 红利/分红
    '510880', '513880', '512590', '515460', '513500',
    # 低波/价值
    '159916', '159934',
    # 强周期证券（与 v9 池重叠的不动）
    '512690', '159815',
    # 债券
    '511010', '511880', '511990', '511220', '511210',
    # 商品
    '518880', '518800', '159912',
]


def backup_db():
    """备份 etf.db 到 .archive/"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_path = ARCHIVE_DIR / f'pre-us002-{timestamp}'
    archive_path.mkdir(parents=True, exist_ok=True)
    backup_file = archive_path / 'etf.db'
    shutil.copy2(DB_PATH, backup_file)
    print(f"   ✅ 备份完成: {backup_file}")
    return backup_file


def has_column(conn, table, column):
    """检查表是否有某列"""
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}
    return column in cols


def run_migration():
    """执行 schema 迁移"""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        # 检查列是否已存在（幂等性）
        if has_column(conn, 'etf_names', 'tradable') and has_column(conn, 'etf_names', 'pool_role'):
            print("   ⏭️  tradable + pool_role 已存在，跳过 ALTER")
        else:
            sql = MIGRATION_FILE.read_text()
            conn.executescript(sql)
            conn.commit()
            print("   ✅ ALTER TABLE 成功")
    finally:
        conn.close()


def update_role(conn, codes, role, tradable):
    """批量更新 pool_role 和 tradable"""
    if not codes:
        return
    placeholders = ','.join('?' * len(codes))
    sql = f"UPDATE etf_names SET tradable = ?, pool_role = ? WHERE code IN ({placeholders})"
    cur = conn.cursor()
    cur.execute(sql, [tradable, role] + list(codes))
    print(f"   ✅ 标记 {len(codes)} 只 {role} (tradable={tradable})")


def update_all_roles():
    """标注 core / reference / excluded"""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        # 注意顺序：先标 excluded 和 reference，最后标 core
        # 这样如果某 ETF 在多个列表中（如 512880 在 excluded 和 core），
        # 最后一次标会胜出（按优先级 core > reference > excluded）
        update_role(conn, EXCLUDED_CODES, 'excluded', 0)
        update_role(conn, REFERENCE_CODES, 'reference', 0)
        update_role(conn, CORE_CODES, 'core', 1)
        conn.commit()
    finally:
        conn.close()


def verify():
    """验证迁移结果"""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT pool_role, COUNT(*) AS cnt,
                   SUM(CASE WHEN tradable = 1 THEN 1 ELSE 0 END) AS tradable_count
            FROM etf_names
            GROUP BY pool_role
            ORDER BY pool_role
        """)
        print("\n   📊 验证结果（按 pool_role 分组）:")
        print(f"   {'role':<15} {'count':<8} {'tradable':<10}")
        print("   " + "-" * 33)
        for row in cur.fetchall():
            role, count, tradable = row
            print(f"   {role:<15} {count:<8} {tradable:<10}")

        # 核心池
        cur.execute("SELECT code FROM etf_names WHERE pool_role = 'core' AND tradable = 1 ORDER BY code")
        core_codes = [r[0] for r in cur.fetchall()]
        print(f"\n   📋 核心池 ({len(core_codes)} 只): {core_codes}")

        # 510300
        cur.execute("SELECT code, pool_role, tradable FROM etf_names WHERE code = '510300'")
        row = cur.fetchone()
        if row:
            print(f"   📍 510300: pool_role={row[1]}, tradable={row[2]}")

        # 总数
        cur.execute("SELECT COUNT(*) FROM etf_names")
        total = cur.fetchone()[0]
        print(f"\n   📈 总记录: {total}")
    finally:
        conn.close()


def main():
    print("=" * 60)
    print("US-002 迁移（修正版）：etf_names 加 tradable + pool_role")
    print("=" * 60)

    if not DB_PATH.exists():
        print(f"   ❌ 数据库不存在: {DB_PATH}")
        sys.exit(1)

    print(f"\n📦 数据库: {DB_PATH}")

    # 1. 备份
    print(f"\n[1/4] 备份 etf.db...")
    backup_db()

    # 2. ALTER TABLE
    print(f"\n[2/4] 执行 schema 迁移...")
    run_migration()

    # 3. 标注 core / reference / excluded
    print(f"\n[3/4] 标注 pool_role...")
    update_all_roles()

    # 4. 验证
    print(f"\n[4/4] 验证...")
    verify()

    print("\n" + "=" * 60)
    print("✅ 迁移完成")
    print("=" * 60)


if __name__ == '__main__':
    main()
