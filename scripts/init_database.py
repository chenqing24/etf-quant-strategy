#!/usr/bin/env python3
"""
数据库迁移入口（US-002）

用途：
    - 顺序执行 schema/migrations/ 下所有 SQL 文件
    - 幂等：重复执行不会破坏已存在结构

与 scripts/maintenance/init_database.py 区别：
    - maintenance 版本：跑 01_etf_live_schema.sql + 02_etf_factors_schema.sql（基础 schema）
    - 本脚本：跑 schema/migrations/（增量迁移，US-002+ 维护用）

被谁调用：
    - 手动执行（US-002 worker 验证 schema 006/007）
    - 后续 US（如需）也用本入口

使用方式：
    # 在 etf_strategy 目录下执行
    python scripts/init_database.py

依赖：
    - sqlite3
    - pathlib

注意事项：
    - 路径注入使用 PROJECT_ROOT（与 maintenance 风格一致）
    - SQLite ALTER TABLE ADD COLUMN 不支持 IF NOT EXISTS（schema/README.md），
      所以采用"预扫描 + try/except"策略保持幂等
    - CREATE TABLE / CREATE INDEX 用 IF NOT EXISTS（SQLite 原生支持）
"""
import os
import re
import sys
import sqlite3
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / 'etf_data_live' / 'etf.db'
MIGRATIONS_DIR = PROJECT_ROOT / 'schema' / 'migrations'

# 正则：匹配 ALTER TABLE <table> ADD COLUMN <column>
ADD_COLUMN_RE = re.compile(
    r'ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)\b',
    re.IGNORECASE
)


def is_column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """判断列是否存在（处理 SQLite ALTER TABLE 不支持 IF NOT EXISTS）"""
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def split_sql_statements(sql: str) -> list:
    """
    按 ; 切分 SQL 语句，保留非空、非纯注释
    """
    stmts = []
    for raw in sql.split(';'):
        s = raw.strip()
        if not s:
            continue
        # 跳过纯注释块
        non_comment = '\n'.join(
            line for line in s.splitlines()
            if line.strip() and not line.strip().startswith('--')
        )
        if not non_comment.strip():
            continue
        stmts.append(s)
    return stmts


def run_migration(db_path: Path, migration_file: Path) -> bool:
    """
    执行单个迁移文件

    策略：
    - CREATE TABLE / CREATE INDEX：原样执行（自带 IF NOT EXISTS）
    - ALTER TABLE ADD COLUMN：检查列是否存在，存在则跳过该语句
    """
    print(f"\n📦 应用迁移: {migration_file.name}")

    if not db_path.exists():
        print(f"   ❌ 数据库不存在: {db_path}")
        return False

    sql = migration_file.read_text(encoding='utf-8')
    conn = sqlite3.connect(str(db_path))

    try:
        statements = split_sql_statements(sql)
        for stmt in statements:
            # ALTER TABLE ADD COLUMN → 检查列存在性
            m = ADD_COLUMN_RE.search(stmt)
            if m:
                table, column = m.group(1), m.group(2)
                if is_column_exists(conn, table, column):
                    print(f"   ⏭  跳过（已存在）: {table}.{column}")
                    continue
                else:
                    print(f"   ➕ 新增列: {table}.{column}")
            conn.execute(stmt)
        conn.commit()
        print(f"   ✅ 完成: {migration_file.name}")
        return True
    except Exception as e:
        print(f"   ❌ 失败: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def main():
    print("=" * 60)
    print("ETF 量化系统 - 数据库迁移入口（US-002）")
    print("=" * 60)

    if not MIGRATIONS_DIR.exists():
        print(f"\n❌ Migrations 目录不存在: {MIGRATIONS_DIR}")
        sys.exit(1)

    if not DB_PATH.exists():
        print(f"\n❌ 数据库不存在: {DB_PATH}")
        print("   请先运行: python scripts/maintenance/init_database.py")
        sys.exit(1)

    # 按文件名顺序（NNN_xxx.sql）执行
    migration_files = sorted(MIGRATIONS_DIR.glob('*.sql'))

    if not migration_files:
        print(f"\n⚠️  Migrations 目录为空: {MIGRATIONS_DIR}")
        return

    print(f"\n发现 {len(migration_files)} 个迁移文件")
    success_count = 0
    for mf in migration_files:
        if run_migration(DB_PATH, mf):
            success_count += 1

    print("\n" + "=" * 60)
    print(f"迁移完成: {success_count}/{len(migration_files)} 成功")
    print("=" * 60)

    if success_count < len(migration_files):
        sys.exit(1)


if __name__ == '__main__':
    main()
