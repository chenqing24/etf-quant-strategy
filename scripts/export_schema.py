#!/usr/bin/env python3
"""
导出数据库 schema 为 SQL 文件

用途：
1. 从现有 .db 文件导出表结构
2. 用于版本控制和文档

使用方式：
    cd etf_strategy
    python scripts/export_schema.py
"""
import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


def get_tables(conn: sqlite3.Connection) -> list:
    """获取所有表名"""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    return [row[0] for row in cur.fetchall()]


def export_table_schema(conn: sqlite3.Connection, table_name: str) -> str:
    """导出单个表的 CREATE TABLE 语句"""
    lines = []
    
    # 获取表信息
    cur = conn.execute(f"PRAGMA table_info({table_name})")
    columns = cur.fetchall()
    
    # 获取创建语句
    cur = conn.execute(
        f"SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    create_sql = cur.fetchone()[0]
    
    if create_sql:
        lines.append(f"\n-- {table_name}")
        lines.append(f"{create_sql};")
    
    # 获取索引
    cur = conn.execute(
        f"SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
        (table_name,)
    )
    for row in cur.fetchall():
        if row[0]:
            lines.append(f"{row[0]};")
    
    return "\n".join(lines)


def export_db_schema(db_path: Path, output_file: Path) -> bool:
    """导出整个数据库的 schema"""
    print(f"\n📦 导出数据库: {db_path}")
    
    if not db_path.exists():
        print(f"   ❌ 数据库文件不存在")
        return False
    
    try:
        conn = sqlite3.connect(str(db_path))
        tables = get_tables(conn)
        
        header = f"""-- ============================================================
-- 数据库 Schema 导出
-- 来源: {db_path}
-- 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
-- 表数量: {len(tables)}
-- ============================================================
"""
        
        content = [header]
        for table in tables:
            content.append(export_table_schema(conn, table))
        
        conn.close()
        
        output_file.write_text("\n".join(content))
        print(f"   ✅ 导出成功: {output_file}")
        return True
        
    except Exception as e:
        print(f"   ❌ 导出失败: {e}")
        return False


def main():
    print("=" * 60)
    print("ETF 量化系统 - 导出数据库 Schema")
    print("=" * 60)
    
    results = {}
    
    # 1. 导出行情数据库
    results['live'] = export_db_schema(
        PROJECT_ROOT / 'etf_data_live' / 'etf.db',
        PROJECT_ROOT / 'schema' / 'export_01_etf_live_schema.sql'
    )
    
    # 2. 导出因子数据库
    results['factors'] = export_db_schema(
        PROJECT_ROOT / 'data' / 'etf_factors.db',
        PROJECT_ROOT / 'schema' / 'export_02_etf_factors_schema.sql'
    )
    
    # 总结
    print("\n" + "=" * 60)
    print("导出结果")
    print("=" * 60)
    
    all_success = True
    for name, success in results.items():
        status = "✅ 成功" if success else "❌ 失败"
        print(f"  {name}: {status}")
        all_success = all_success and success
    
    if all_success:
        print("\n✅ 所有 Schema 导出完成")
        sys.exit(0)
    else:
        print("\n❌ 部分导出失败")
        sys.exit(1)


if __name__ == '__main__':
    main()