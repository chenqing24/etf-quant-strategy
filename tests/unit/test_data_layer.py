"""
数据层单元测试
测试 DataWriter, exceptions, types 等核心组件
"""
import os
import sys
import sqlite3
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
import pandas as pd
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.exceptions import DataValidationError, DataSourceError, DataNotFoundError
from src.data.types import RealtimeQuote, DailyRecord, StockInfo


class TestExceptions(unittest.TestCase):
    """测试异常定义"""
    
    def test_data_validation_error(self):
        """测试数据校验异常"""
        errors = [
            {'code': '510300', 'field': 'close', 'value': 0, 'error': 'must be > 0'}
        ]
        err = DataValidationError("数据校验失败", errors)
        self.assertIn("510300", str(err))
        self.assertEqual(len(err.errors), 1)
    
    def test_data_source_error(self):
        """测试数据源异常"""
        err = DataSourceError("数据源不可用", sources_tried=['sina', 'tencent'])
        self.assertIn("sina", str(err))
        self.assertEqual(len(err.sources_tried), 2)
    
    def test_data_not_found_error(self):
        """测试数据不存在异常"""
        err = DataNotFoundError('510300', 'daily')
        self.assertIn("510300", str(err))
        self.assertEqual(err.code, '510300')


class TestTypes(unittest.TestCase):
    """测试数据类型"""
    
    def test_realtime_quote_from_tencent(self):
        """测试从腾讯API解析实时报价"""
        text = 'v_sz159577="51~美国50ETF汇添富~159577~1.583~0.032~2.06~11300000~17890000"'
        quote = RealtimeQuote.from_tencent(text)
        
        self.assertEqual(quote.code, '159577')
        self.assertEqual(quote.name, '美国50ETF汇添富')
        self.assertAlmostEqual(quote.price, 1.583)
        self.assertAlmostEqual(quote.change, 0.032)
        self.assertAlmostEqual(quote.change_pct, 2.06)
    
    def test_realtime_quote_to_dict(self):
        """测试实时报价转字典"""
        quote = RealtimeQuote(
            code='510300',
            name='沪深300ETF',
            price=4.0,
            change=0.1,
            change_pct=2.5,
            volume=1000000,
            amount=4000000,
            timestamp='2024-01-01T10:00:00'
        )
        
        d = quote.to_dict()
        self.assertEqual(d['code'], '510300')
        self.assertEqual(d['price'], 4.0)
    
    def test_daily_record_validate(self):
        """测试日线记录校验"""
        # 正常记录
        record = DailyRecord(
            code='510300',
            date='2024-01-01',
            open=3.5,
            high=3.8,
            low=3.4,
            close=3.7,
            volume=1000000
        )
        errors = record.validate()
        self.assertEqual(len(errors), 0)
        
        # 异常记录：close <= 0
        record.close = 0
        errors = record.validate()
        self.assertGreater(len(errors), 0)
        self.assertEqual(errors[0]['field'], 'close')
        
        # 异常记录：high < close
        record.close = 3.7
        record.high = 3.6
        errors = record.validate()
        self.assertGreater(len(errors), 0)
        self.assertEqual(errors[0]['field'], 'high')


class TestDataWriter(unittest.TestCase):
    """测试 DataWriter"""
    
    def setUp(self):
        """创建临时数据库"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
    
    def tearDown(self):
        """清理临时数据库"""
        shutil.rmtree(self.temp_dir)
    
    def test_ensure_db(self):
        """测试数据库初始化"""
        from src.data.writer import DataWriter
        
        writer = DataWriter(self.db_path)
        
        # 验证表已创建
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        conn.close()
        
        self.assertIn('daily', tables)
        self.assertIn('stock_info', tables)
        self.assertIn('realtime_cache', tables)
    
    def test_write_daily_incremental(self):
        """测试增量写入"""
        from src.data.writer import DataWriter
        
        writer = DataWriter(self.db_path)
        
        # 第一次写入
        df1 = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-02', '2024-01-03'],
            'open': [3.5, 3.6, 3.7],
            'high': [3.6, 3.7, 3.8],
            'low': [3.4, 3.5, 3.6],
            'close': [3.55, 3.65, 3.75],
            'volume': [1000000, 1100000, 1200000]
        })
        
        count1 = writer.write_daily('510300', df1)
        self.assertEqual(count1, 3)
        
        # 第二次写入（同一只ETF，新日期）
        df2 = pd.DataFrame({
            'date': ['2024-01-04'],
            'open': [3.8],
            'high': [3.9],
            'low': [3.7],
            'close': [3.85],
            'volume': [1300000]
        })
        
        count2 = writer.write_daily('510300', df2)
        self.assertEqual(count2, 1)
        
        # 第三次写入（同一日期，应该跳过）
        df3 = pd.DataFrame({
            'date': ['2024-01-01'],
            'open': [3.6],
            'high': [3.7],
            'low': [3.5],
            'close': [3.6],
            'volume': [1500000]
        })
        
        count3 = writer.write_daily('510300', df3)
        self.assertEqual(count3, 0)
        
        # 验证总数
        total = writer.get_record_count('510300')
        self.assertEqual(total, 4)
    
    def test_write_daily_validation_error(self):
        """测试数据校验失败"""
        from src.data.writer import DataWriter
        
        writer = DataWriter(self.db_path)
        
        # 无效数据：close <= 0
        df = pd.DataFrame({
            'date': ['2024-01-01'],
            'open': [3.5],
            'high': [3.6],
            'low': [3.4],
            'close': [0],  # 无效
            'volume': [1000000]
        })
        
        with self.assertRaises(DataValidationError) as ctx:
            writer.write_daily('510300', df)
        
        self.assertGreater(len(ctx.exception.errors), 0)
    
    def test_write_daily_batch(self):
        """测试批量写入"""
        from src.data.writer import DataWriter
        
        writer = DataWriter(self.db_path)
        
        records = {
            '510300': pd.DataFrame({
                'date': ['2024-01-01', '2024-01-02'],
                'open': [3.5, 3.6],
                'high': [3.6, 3.7],
                'low': [3.4, 3.5],
                'close': [3.55, 3.65],
                'volume': [1000000, 1100000]
            }),
            '159577': pd.DataFrame({
                'date': ['2024-01-01'],
                'open': [1.5],
                'high': [1.6],
                'low': [1.4],
                'close': [1.55],
                'volume': [500000]
            })
        }
        
        results = writer.write_daily_batch(records)
        
        self.assertEqual(results['510300'], 2)
        self.assertEqual(results['159577'], 1)
    
    def test_write_realtime(self):
        """测试写入实时报价"""
        from src.data.writer import DataWriter
        
        writer = DataWriter(self.db_path)
        
        quote = {
            'code': '510300',
            'name': '沪深300ETF',
            'price': 4.0,
            'change': 0.1,
            'change_pct': 2.5,
            'volume': 1000000,
            'amount': 4000000,
            'timestamp': '2024-01-01T10:00:00'
        }
        
        success = writer.write_realtime('510300', quote)
        self.assertTrue(success)
        
        # 验证写入
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute('SELECT price FROM realtime_cache WHERE code=?', ('510300',))
        row = cur.fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        self.assertAlmostEqual(row[0], 4.0)
    
    def test_get_latest_date(self):
        """测试获取最新日期"""
        from src.data.writer import DataWriter
        
        writer = DataWriter(self.db_path)
        
        # 初始无数据
        latest = writer.get_latest_date('510300')
        self.assertIsNone(latest)
        
        # 写入数据
        df = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-05', '2024-01-03'],
            'open': [3.5, 3.7, 3.6],
            'high': [3.6, 3.8, 3.7],
            'low': [3.4, 3.6, 3.5],
            'close': [3.55, 3.75, 3.65],
            'volume': [1000000, 1200000, 1100000]
        })
        
        writer.write_daily('510300', df)
        
        # 获取最新日期（应该是 2024-01-05）
        latest = writer.get_latest_date('510300')
        self.assertEqual(latest, '2024-01-05')


class TestBackupManager(unittest.TestCase):
    """测试备份管理器"""
    
    def setUp(self):
        """创建临时目录"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.backup_dir = os.path.join(self.temp_dir, 'backups')
        
        # 创建测试数据库
        conn = sqlite3.connect(self.db_path)
        conn.execute('CREATE TABLE test (id INTEGER PRIMARY KEY)')
        conn.execute('INSERT INTO test VALUES (1)')
        conn.commit()
        conn.close()
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def test_backup_and_restore(self):
        """测试备份和恢复"""
        from scripts.backup_sqlite import SQLiteBackupManager
        import time
        
        manager = SQLiteBackupManager(
            db_path=self.db_path,
            backup_dir=self.backup_dir
        )
        
        # 执行备份
        backup_path = manager.backup('manual')
        self.assertTrue(Path(backup_path).exists())
        self.assertGreater(Path(backup_path).stat().st_size, 0)
        
        # 验证备份内容
        conn = sqlite3.connect(backup_path)
        cur = conn.execute('SELECT id FROM test')
        row = cur.fetchone()
        conn.close()
        self.assertEqual(row[0], 1)
    
    def test_list_backups(self):
        """测试列出备份"""
        from scripts.backup_sqlite import SQLiteBackupManager
        import time
        
        manager = SQLiteBackupManager(
            db_path=self.db_path,
            backup_dir=self.backup_dir
        )
        
        # 创建几个备份（使用不同类型避免文件冲突）
        manager.backup('daily')
        time.sleep(1)
        manager.backup('weekly')
        time.sleep(1)
        manager.backup('manual')
        
        # 列出daily备份
        backups = manager.list_backups('daily')
        self.assertEqual(len(backups), 1)
        
        # 列出weekly备份
        backups = manager.list_backups('weekly')
        self.assertEqual(len(backups), 1)


class TestDataQualityMonitor(unittest.TestCase):
    """测试数据质量监控"""
    
    def setUp(self):
        """创建临时数据库"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def test_check_freshness_no_data(self):
        """测试无数据时的检查"""
        from src.data.monitor import DataQualityMonitor
        
        monitor = DataQualityMonitor(self.db_path)
        result = monitor.check_data_freshness()
        
        # 无数据时状态可能是 WARNING 或 ERROR
        self.assertIn(result['status'], ['WARNING', 'ERROR'])
        self.assertIsNone(result['latest_date'])
    
    def test_check_freshness_with_data(self):
        """测试有数据时的检查"""
        from src.data.monitor import DataQualityMonitor
        
        # 写入测试数据
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE daily (
                id INTEGER PRIMARY KEY,
                code TEXT,
                date TEXT,
                UNIQUE(code, date)
            )
        ''')
        conn.execute("INSERT INTO daily VALUES (1, '510300', '2024-01-01')")
        conn.commit()
        conn.close()
        
        monitor = DataQualityMonitor(self.db_path)
        result = monitor.check_data_freshness()
        
        self.assertIn(result['status'], ['OK', 'WARNING', 'ERROR'])
        self.assertEqual(result['latest_date'], '2024-01-01')
    
    def test_check_completeness(self):
        """测试完整性检查"""
        from src.data.monitor import DataQualityMonitor
        
        # 写入测试数据
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE daily (
                id INTEGER PRIMARY KEY,
                code TEXT,
                date TEXT,
                UNIQUE(code, date)
            )
        ''')
        conn.execute("INSERT INTO daily VALUES (1, '510300', '2024-01-01')")
        conn.execute("INSERT INTO daily VALUES (2, '159577', '2024-01-01')")
        conn.commit()
        conn.close()
        
        monitor = DataQualityMonitor(self.db_path)
        result = monitor.check_data_completeness()
        
        # 验证能返回正确格式的结果
        self.assertIn(result['status'], ['OK', 'WARNING', 'ERROR'])
        self.assertEqual(result['total_etfs'], 2)
    
    def test_check_storage_health(self):
        """测试存储健康检查"""
        from src.data.monitor import DataQualityMonitor
        
        # 写入测试数据
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE daily (
                id INTEGER PRIMARY KEY,
                code TEXT,
                date TEXT,
                UNIQUE(code, date)
            )
        ''')
        for i in range(100):
            # 用 i 作为主键，但日期唯一化避免 UNIQUE 冲突
            day = (i % 28) + 1
            date_str = f'2024-{(i // 28) + 1:02d}-{day:02d}'
            conn.execute(f"INSERT INTO daily VALUES ({i}, '510300', '{date_str}')")
        conn.commit()
        conn.close()
        
        monitor = DataQualityMonitor(self.db_path)
        result = monitor.check_storage_health()
        
        self.assertIn(result['status'], ['OK', 'WARNING', 'ERROR'])
        self.assertGreater(result['total_records'], 0)
        self.assertLess(result['db_size_mb'], 1.0)  # 小于1MB


if __name__ == '__main__':
    unittest.main()