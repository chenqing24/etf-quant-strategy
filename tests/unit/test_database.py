#!/usr/bin/env python3
"""
数据库初始化脚本 - 测试用例
"""
import os
import sys
import tempfile
import sqlite3
from pathlib import Path
from unittest import TestCase, main

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestInitDatabase(TestCase):
    """测试 init_database.py"""
    
    def setUp(self):
        """测试前准备"""
        self.test_dir = tempfile.mkdtemp()
        self.original_root = PROJECT_ROOT
        
    def test_schema_files_exist(self):
        """验证 schema 文件存在"""
        schema_dir = self.original_root / 'schema'
        self.assertTrue(schema_dir.exists(), "schema 目录不存在")
        
        self.assertTrue((schema_dir / '01_etf_live_schema.sql').exists())
        self.assertTrue((schema_dir / '02_etf_factors_schema.sql').exists())
    
    def test_schema_sql_syntax(self):
        """验证 SQL 语法正确"""
        schema_file = self.original_root / 'schema' / '01_etf_live_schema.sql'
        sql = schema_file.read_text()
        
        # 创建临时数据库验证语法
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            tmp_db = f.name
        
        try:
            conn = sqlite3.connect(tmp_db)
            conn.executescript(sql)
            conn.close()
        except sqlite3.OperationalError as e:
            self.fail(f"SQL 语法错误: {e}")
        finally:
            os.unlink(tmp_db)
    
    def test_schema_creates_required_tables(self):
        """验证 schema 创建必需的表"""
        schema_file = self.original_root / 'schema' / '01_etf_live_schema.sql'
        sql = schema_file.read_text()
        
        required_tables = ['daily', 'etf_names', 'stock_info']
        
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            tmp_db = f.name
        
        try:
            conn = sqlite3.connect(tmp_db)
            conn.executescript(sql)
            
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in cur.fetchall()]
            
            for table in required_tables:
                self.assertIn(table, tables, f"缺少表: {table}")
            
            conn.close()
        finally:
            os.unlink(tmp_db)
    
    def test_factor_schema_creates_required_tables(self):
        """验证因子 schema 创建必需的表"""
        schema_file = self.original_root / 'schema' / '02_etf_factors_schema.sql'
        sql = schema_file.read_text()
        
        required_tables = ['daily_price', 'factor_data', 'trade_records']
        
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            tmp_db = f.name
        
        try:
            conn = sqlite3.connect(tmp_db)
            conn.executescript(sql)
            
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = [row[0] for row in cur.fetchall()]
            
            for table in required_tables:
                self.assertIn(table, tables, f"缺少表: {table}")
            
            conn.close()
        finally:
            os.unlink(tmp_db)


class TestMigrateData(TestCase):
    """测试 migrate_data.py"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def test_export_import_roundtrip(self):
        """测试导出-导入往返"""
        # 创建测试数据库
        db_path = Path(self.test_dir) / 'test.db'
        conn = sqlite3.connect(str(db_path))
        conn.execute('''CREATE TABLE test_table (
            id INTEGER PRIMARY KEY,
            name TEXT,
            value REAL
        )''')
        conn.execute("INSERT INTO test_table VALUES (1, 'test', 3.14)")
        conn.commit()
        conn.close()
        
        # 导出
        export_path = Path(self.test_dir) / 'export.json'
        
        # 运行迁移脚本的导出逻辑
        from scripts.maintenance.migrate_data import export_database
        
        result = export_database(db_path, export_path, ['test_table'])
        self.assertTrue(result)
        self.assertTrue(export_path.exists())
        
        # 验证导出内容
        import json
        data = json.loads(export_path.read_text())
        self.assertIn('tables', data)
        self.assertIn('test_table', data['tables'])
        self.assertEqual(len(data['tables']['test_table']), 1)
        
        # 修改数据后导入
        conn = sqlite3.connect(str(db_path))
        conn.execute("UPDATE test_table SET name='modified'")
        conn.commit()
        conn.close()
        
        # 导入
        from scripts.maintenance.migrate_data import import_database
        
        result = import_database(db_path, export_path, ['test_table'])
        self.assertTrue(result)
        
        # 验证数据恢复
        conn = sqlite3.connect(str(db_path))
        cur = conn.execute("SELECT name FROM test_table WHERE id=1")
        name = cur.fetchone()[0]
        conn.close()
        
        self.assertEqual(name, 'test', "导入后数据不一致")


class TestExportSchema(TestCase):
    """测试 export_schema.py"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def test_export_produces_valid_sql(self):
        """测试导出生成有效 SQL"""
        # 创建测试数据库
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            tmp_db = Path(f.name)
        
        try:
            conn = sqlite3.connect(str(tmp_db))
            conn.execute('''CREATE TABLE test_export (
                id INTEGER PRIMARY KEY,
                data TEXT NOT NULL
            )''')
            conn.execute('CREATE INDEX idx_test ON test_export(id)')
            conn.commit()
            conn.close()
            
            # 导出
            output_path = Path(self.test_dir) / 'export.sql'
            
            from scripts.maintenance.export_schema import export_db_schema
            
            result = export_db_schema(tmp_db, output_path)
            self.assertTrue(result)
            self.assertTrue(output_path.exists())
            
            # 验证导出的 SQL 可以执行
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f2:
                tmp_db2 = f2.name
            
            try:
                conn = sqlite3.connect(tmp_db2)
                conn.executescript(output_path.read_text())
                conn.close()
                
                # 验证表已创建
                conn = sqlite3.connect(tmp_db2)
                cur = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                tables = [row[0] for row in cur.fetchall()]
                conn.close()
                
                self.assertIn('test_export', tables)
            finally:
                os.unlink(tmp_db2)
                
        finally:
            os.unlink(str(tmp_db))


if __name__ == '__main__':
    main()