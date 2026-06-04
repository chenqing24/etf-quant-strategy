#!/usr/bin/env python3
"""
数据迁移脚本 - 导出/导入数据

用途：
1. 导出数据为 JSON 格式（便于版本控制）
2. 从 JSON 导入数据到数据库
3. 数据备份和恢复

使用方式：
    # 导出
    cd etf_strategy
    python scripts/migrate_data.py --export --db etf_data_live/etf.db --output data/export_live.json
    
    # 导入
    python scripts/migrate_data.py --import --db etf_data_live/etf.db --input data/export_live.json
"""
import os
import sys
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


def export_table(conn: sqlite3.Connection, table_name: str) -> List[Dict]:
    """导出单个表的数据"""
    cur = conn.execute(f"SELECT * FROM {table_name}")
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def export_database(db_path: Path, output_path: Path, tables: List[str] = None) -> bool:
    """导出数据库为 JSON"""
    print(f"\n📦 导出数据库: {db_path}")
    
    if not db_path.exists():
        print(f"   ❌ 数据库文件不存在")
        return False
    
    try:
        conn = sqlite3.connect(str(db_path))
        
        # 默认导出所有表
        if tables is None:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
            tables = [row[0] for row in cur.fetchall()]
        
        data = {
            'meta': {
                'source': str(db_path),
                'exported_at': datetime.now().isoformat(),
                'tables': tables
            },
            'tables': {}
        }
        
        for table in tables:
            try:
                data['tables'][table] = export_table(conn, table)
                print(f"   📄 {table}: {len(data['tables'][table])} 条")
            except Exception as e:
                print(f"   ⚠️  {table}: 导出失败 ({e})")
        
        conn.close()
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        print(f"   ✅ 导出成功: {output_path}")
        return True
        
    except Exception as e:
        print(f"   ❌ 导出失败: {e}")
        return False


def import_database(db_path: Path, input_path: Path, tables: List[str] = None) -> bool:
    """从 JSON 导入数据库"""
    print(f"\n📥 导入到数据库: {db_path}")
    
    if not input_path.exists():
        print(f"   ❌ 输入文件不存在: {input_path}")
        return False
    
    try:
        data = json.loads(input_path.read_text())
        
        conn = sqlite3.connect(str(db_path))
        
        # 默认导入所有表
        target_tables = tables or list(data['tables'].keys())
        
        for table in target_tables:
            if table not in data['tables']:
                print(f"   ⚠️  {table}: 源数据中不存在")
                continue
            
            rows = data['tables'][table]
            if not rows:
                continue
            
            # 清理旧数据
            conn.execute(f"DELETE FROM {table}")
            
            # 批量插入
            if rows:
                columns = list(rows[0].keys())
                placeholders = ','.join(['?' for _ in columns])
                sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
                
                for row in rows:
                    values = [row.get(col) for col in columns]
                    try:
                        conn.execute(sql, values)
                    except Exception as e:
                        print(f"   ⚠️  {table}: 插入失败 ({e})")
                        break
                else:
                    conn.commit()
                    print(f"   📄 {table}: 导入 {len(rows)} 条")
        
        conn.close()
        print(f"   ✅ 导入成功")
        return True
        
    except Exception as e:
        print(f"   ❌ 导入失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='数据迁移工具')
    parser.add_argument('--export', action='store_true', help='导出模式')
    parser.add_argument('--import', dest='import_mode', action='store_true', help='导入模式')
    parser.add_argument('--db', required=True, help='数据库路径')
    parser.add_argument('--output', help='导出输出路径')
    parser.add_argument('--input', help='导入输入路径')
    parser.add_argument('--tables', nargs='+', help='指定表名（可选）')
    
    args = parser.parse_args()
    
    if args.export:
        if not args.output:
            print("❌ 需要指定 --output")
            sys.exit(1)
        success = export_database(
            PROJECT_ROOT / args.db,
            PROJECT_ROOT / args.output,
            args.tables
        )
    elif args.import_mode:
        if not args.input:
            print("❌ 需要指定 --input")
            sys.exit(1)
        success = import_database(
            PROJECT_ROOT / args.db,
            PROJECT_ROOT / args.input,
            args.tables
        )
    else:
        print("❌ 需要指定 --export 或 --import")
        sys.exit(1)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()