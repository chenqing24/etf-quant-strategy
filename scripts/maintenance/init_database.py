#!/usr/bin/env python3
"""
数据库初始化脚本

用途：
    - 创建 etf_data_live/etf.db（行情数据库）
    - 创建 data/etf_factors.db（因子数据库）
    - 执行 schema 初始化（IF NOT EXISTS）

被谁调用：
    - 无（独立工具，手动执行）
    - 数据库首次部署时使用
    - 数据库 schema 变更后使用

功能说明：
    - 已有数据会被保留（使用 IF NOT EXISTS）
    - 如需重建，先删除 .db 文件
    - Schema 文件位于 schema/ 目录（01_etf_live_schema.sql, 02_etf_factors_schema.sql）

使用方式：
    # 在 etf_strategy 目录下执行
    python scripts/maintenance/init_database.py

依赖：
    - sqlite3
    - pathlib

注意事项：
    - 路径注入使用 3 层（与其他 maintenance 脚本一致）
    - 已豁免 pre-commit 检查（运维工具）
    - 必须在 PROJECT_ROOT（etf_strategy）目录下执行
"""
import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
SCHEMA_DIR = PROJECT_ROOT / 'schema'
DATA_DIR = PROJECT_ROOT / 'etf_data_live'
FACTORS_DIR = PROJECT_ROOT / 'data'


def get_schema_sql(schema_file: Path) -> str:
    """读取 schema SQL 文件"""
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema文件不存在: {schema_file}")
    return schema_file.read_text()


def init_database(db_path: Path, schema_file: Path) -> bool:
    """
    初始化单个数据库
    
    Args:
        db_path: 数据库路径
        schema_file: schema SQL 文件路径
        
    Returns:
        是否成功
    """
    print(f"\n📦 初始化数据库: {db_path}")
    
    # 确保目录存在
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 检查数据库是否已存在
    is_new = not db_path.exists()
    
    try:
        conn = sqlite3.connect(str(db_path))
        schema_sql = get_schema_sql(schema_file)
        
        # 执行 schema
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


def main():
    print("=" * 60)
    print("ETF 量化系统 - 数据库初始化")
    print("=" * 60)
    
    # 检查 schema 目录
    if not SCHEMA_DIR.exists():
        print(f"\n❌ Schema目录不存在: {SCHEMA_DIR}")
        print("   请确保 schema/ 目录下有 SQL 文件")
        sys.exit(1)
    
    results = {}
    
    # 1. 初始化行情数据库
    results['live'] = init_database(
        DATA_DIR / 'etf.db',
        SCHEMA_DIR / '01_etf_live_schema.sql'
    )
    
    # 2. 初始化因子数据库
    results['factors'] = init_database(
        FACTORS_DIR / 'etf_factors.db',
        SCHEMA_DIR / '02_etf_factors_schema.sql'
    )
    
    # 总结
    print("\n" + "=" * 60)
    print("初始化结果")
    print("=" * 60)
    
    all_success = True
    for name, success in results.items():
        status = "✅ 成功" if success else "❌ 失败"
        print(f"  {name}: {status}")
        all_success = all_success and success
    
    if all_success:
        print("\n✅ 所有数据库初始化完成")
        print("\n数据库路径：")
        print(f"  行情库: {DATA_DIR / 'etf.db'}")
        print(f"  因子库: {FACTORS_DIR / 'etf_factors.db'}")
        sys.exit(0)
    else:
        print("\n❌ 部分数据库初始化失败，请检查错误信息")
        sys.exit(1)


if __name__ == '__main__':
    main()