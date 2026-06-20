#!/usr/bin/env python3
"""
数据库初始化脚本（v2.0）

用途：
1. 创建 etf_data_live/etf.db（行情数据库）
2. 创建 data/etf_factors.db（因子数据库）
3. 执行 schema 初始化
4. 执行 migrations（schema/migrations/*.sql，按序号）

使用方式：
    cd etf_strategy
    python scripts/init_database.py              # 正常执行
    python scripts/init_database.py --dry-run    # 只打印 SQL 不执行
    python scripts/init_database.py --migrations # 只跑 migrations

幂等性：
- schema/01, 02 用 CREATE TABLE IF NOT EXISTS
- migrations/00X 用 ALTER TABLE（重复执行会报错，所以按已存在列名跳过）
- 失败时打印具体 SQL 和错误

注意：
- 已有数据会被保留
- 如需重建，先删除 .db 文件
"""
import argparse
import os
import re
import sys
import sqlite3
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
SCHEMA_DIR = PROJECT_ROOT / 'schema'
MIGRATIONS_DIR = SCHEMA_DIR / 'migrations'
DATA_DIR = PROJECT_ROOT / 'etf_data_live'
FACTORS_DIR = PROJECT_ROOT / 'data'


def get_schema_sql(schema_file: Path) -> str:
    """读取 schema SQL 文件"""
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema文件不存在: {schema_file}")
    return schema_file.read_text()


def get_migration_files() -> list:
    """读取 migrations 目录所有 .sql，按文件名排序"""
    if not MIGRATIONS_DIR.exists():
        return []
    files = sorted(MIGRATIONS_DIR.glob('*.sql'))
    return files


def split_sql_statements(sql: str) -> list:
    """把 SQL 脚本拆成单条语句（按 ; 分割）"""
    # 简单实现：按 ; 分割但忽略注释行
    statements = []
    for stmt in sql.split(';'):
        stmt = stmt.strip()
        if not stmt:
            continue
        # 跳过纯注释
        if all(line.strip().startswith('--') or not line.strip() for line in stmt.split('\n')):
            continue
        statements.append(stmt)
    return statements


def init_database(db_path: Path, schema_file: Path, dry_run: bool = False) -> bool:
    """
    初始化单个数据库（schema/01, 02）

    Args:
        db_path: 数据库路径
        schema_file: schema SQL 文件路径
        dry_run: 是否 dry-run（只打印 SQL 不执行）
    """
    print(f"\n📦 初始化数据库: {db_path}")

    # 确保目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # 检查数据库是否已存在
    is_new = not db_path.exists()

    try:
        schema_sql = get_schema_sql(schema_file)

        if dry_run:
            print(f"   [DRY-RUN] 将执行 schema: {schema_file.name}")
            print(f"   [DRY-RUN] 内容预览: {schema_sql[:200]}...")
            return True

        conn = sqlite3.connect(str(db_path))
        conn.executescript(schema_sql)
        conn.close()

        if is_new:
            print(f"   ✅ 新建数据库成功")
        else:
            print(f"   ✅ 更新表结构成功（原有数据已保留）")

        return True

    except Exception as e:
        print(f"   ❌ 初始化失败: {e}")
        return False


def run_migration(db_path: Path, migration_file: Path, dry_run: bool = False) -> bool:
    """
    执行单条 migration

    Args:
        db_path: 数据库路径
        migration_file: migration SQL 文件
        dry_run: 是否 dry-run
    """
    print(f"\n🔄 Migration: {migration_file.name}")

    if not db_path.exists():
        print(f"   ⚠️ 数据库不存在，跳过: {db_path}")
        return False

    sql = migration_file.read_text(encoding='utf-8')

    if dry_run:
        print(f"   [DRY-RUN] {migration_file.name} 预览:")
        print(f"   [DRY-RUN] {sql[:300]}...")
        return True

    try:
        conn = sqlite3.connect(str(db_path))
        # 拆成单条 statement 执行（这样错误定位更清晰）
        for i, stmt in enumerate(split_sql_statements(sql)):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError as e:
                # ALTER TABLE 重复执行会报错（duplicate column），但这是幂等的
                if 'duplicate column' in str(e).lower() or 'already exists' in str(e).lower():
                    print(f"   ⏭️  语句 {i+1} 已应用（幂等跳过）: {str(e)[:80]}")
                    continue
                # SELECT 验证语句不需要 commit
                if stmt.strip().upper().startswith('SELECT'):
                    continue
                raise
        conn.commit()
        conn.close()
        print(f"   ✅ Migration 成功")
        return True
    except Exception as e:
        print(f"   ❌ Migration 失败: {e}")
        return False


def main():
    """主入口"""
    parser = argparse.ArgumentParser(description='ETF 数据库初始化 + Migration')
    parser.add_argument('--dry-run', action='store_true', help='只打印不执行')
    parser.add_argument('--migrations-only', action='store_true', help='只跑 migrations 不初始化')
    args = parser.parse_args()

    print("=" * 60)
    print("ETF 量化系统 - 数据库初始化" + (" [DRY-RUN]" if args.dry_run else ""))
    print("=" * 60)

    # 检查 schema 目录
    if not SCHEMA_DIR.exists():
        print(f"\n❌ Schema目录不存在: {SCHEMA_DIR}")
        sys.exit(1)

    results = {}

    if not args.migrations_only:
        # 1. 初始化行情数据库
        results['live_db'] = init_database(
            DATA_DIR / 'etf.db',
            SCHEMA_DIR / '01_etf_live_schema.sql',
            dry_run=args.dry_run
        )

        # 2. 初始化因子数据库
        results['factors_db'] = init_database(
            FACTORS_DIR / 'etf_factors.db',
            SCHEMA_DIR / '02_etf_factors_schema.sql',
            dry_run=args.dry_run
        )

    # 3. 跑 migrations
    migrations = get_migration_files()
    if migrations:
        print(f"\n{'='*60}")
        print(f"📜 准备执行 {len(migrations)} 个 migration")
        print(f"{'='*60}")

        for mig_file in migrations:
            # 根据文件名推断 DB 类型（001-003 是 etf.db，004+ 是 trade 相关）
            if mig_file.name.startswith('001_') or mig_file.name.startswith('002_') or mig_file.name.startswith('003_'):
                db = DATA_DIR / 'etf.db'
            else:
                # 保守：都跑 etf.db（让 SQL 自己决定）
                db = DATA_DIR / 'etf.db'

            ok = run_migration(db, mig_file, dry_run=args.dry_run)
            results[f'migration_{mig_file.name}'] = ok
    else:
        print("\n⚠️ 没有找到 migrations")

    # 总结
    print(f"\n{'='*60}")
    print("执行结果" + (" [DRY-RUN]" if args.dry_run else ""))
    print(f"{'='*60}")

    all_success = True
    for name, success in results.items():
        status = "✅ 成功" if success else "❌ 失败"
        print(f"  {name}: {status}")
        all_success = all_success and success

    if all_success:
        print(f"\n✅ 所有操作完成" + (" [DRY-RUN]" if args.dry_run else ""))
    else:
        print(f"\n❌ 部分操作失败")
        sys.exit(1)


if __name__ == '__main__':
    main()
