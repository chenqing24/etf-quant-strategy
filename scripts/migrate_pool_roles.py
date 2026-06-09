#!/usr/bin/env python3
"""
US-088 迁移脚本同步：更新 CORE_CODES + EXCLUDED_CODES

设计决策：
- 默认值采用保守策略：tradable=0, pool_role='unclassified'
- 显式标注 15 core + 1 reference + ~11 excluded（按 SELECTION_RULES.md）
- 其余 1449 只保持 unclassified

执行流程：
1. 备份 etf.db → .archive/pre-us002-<时间戳>/etf.db
2. 执行 schema/migrations/003_add_tradable_pool_role.sql
3. UPDATE 15 core（当前核心池）
4. UPDATE 510300 → reference
5. UPDATE 港股/红利/证券类 → excluded（按 SELECTION_RULES.md 2.2）
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

# 当前核心池 15 只（US-088 更新）
CORE_CODES = [
    '159801',  # 芯片ETF广发
    '159806',  # 新能源车ETF国泰
    '159857',  # 光伏ETF天弘
    '159867',  # 养殖ETF鹏华
    '159919',  # 沪深300ETF嘉实
    '159995',  # 芯片ETF华夏
    '159997',  # 电子ETF天弘
    '510050',  # 上证50ETF华夏
    '510500',  # 中证500ETF南方
    '512660',  # 军工ETF国泰
    '512760',  # 芯片ETF国泰
    '515000',  # 科技ETF华宝
    '515050',  # 通信ETF华夏 - US-095: 误标为"养老产业ETF"已修正（fundgz验证）
    '516050',  # 科技龙头ETF工银
    '516160',  # 新能源ETF南方
    '588000',  # 科创50ETF华夏
]

# 510300 标为大盘参考
REFERENCE_CODES = ['510300']

# 按 SELECTION_RULES.md 2.2 排除规则（US-088 更新）
EXCLUDED_CODES = [
    # 港股通ETF (5只)
    '159825',  # 港股通50
    '159902',  # 港股通100
    '159915',  # 港股通中小盘
    '159928',  # 港股通创新药
    '159952',  # 港股通消费
    # 红利/养老ETF (2只) - US-096 修正: 515050 是通信ETF华夏，不是养老产业ETF
    '513360',  # 红利ETF
    '513080',  # 红利低波动ETF
    # 注: 515050 实际是 通信ETF华夏（fundgz.1234567.com.cn 验证），
    #     之前的"养老产业ETF"注释是错误的，需要重新评估是否入核心池
    # 证券/金融ETF (3只)
    '512880',  # 证券ETF
    '512170',  # 券商ETF
    '512200',  # 金融ETF
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
