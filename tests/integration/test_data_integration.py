"""
Phase 2: 集成测试
验证 DataWriter 与现有 fetcher/loader 的集成
"""
import os
import sys
import sqlite3
import tempfile
import shutil
from pathlib import Path
import pandas as pd
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.data.writer import DataWriter
from src.data.types import DailyRecord


class TestFetcherWriterIntegration(unittest.TestCase):
    """测试 fetcher 与 writer 的集成"""
    
    def setUp(self):
        """创建临时测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.writer = DataWriter(self.db_path)
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def test_incremental_write_from_fetcher(self):
        """模拟 fetcher 的增量写入场景"""
        # 第一次写入：历史数据
        df1 = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-02', '2024-01-03'],
            'open': [3.5, 3.6, 3.7],
            'high': [3.6, 3.7, 3.8],
            'low': [3.4, 3.5, 3.6],
            'close': [3.55, 3.65, 3.75],
            'volume': [1000000, 1100000, 1200000]
        })
        
        count1 = self.writer.write_daily('510300', df1)
        self.assertEqual(count1, 3)
        
        # 第二次写入：部分重复 + 新数据（模拟 fetcher 增量更新）
        df2 = pd.DataFrame({
            'date': ['2024-01-02', '2024-01-03', '2024-01-04'],  # 01-02, 01-03 重复
            'open': [3.6, 3.7, 3.8],
            'high': [3.7, 3.8, 3.9],
            'low': [3.5, 3.6, 3.7],
            'close': [3.65, 3.75, 3.85],
            'volume': [1100000, 1200000, 1300000]
        })
        
        count2 = self.writer.write_daily('510300', df2)
        self.assertEqual(count2, 1)  # 只写入 01-04
        
        # 验证总数
        total = self.writer.get_record_count('510300')
        self.assertEqual(total, 4)
    
    def test_multi_etf_batch_write(self):
        """测试多 ETF 批量写入（模拟 fetcher.fetch_all）"""
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
                'date': ['2024-01-01', '2024-01-02'],
                'open': [1.5, 1.6],
                'high': [1.6, 1.7],
                'low': [1.4, 1.5],
                'close': [1.55, 1.65],
                'volume': [500000, 600000]
            }),
            '512880': pd.DataFrame({
                'date': ['2024-01-01', '2024-01-02'],
                'open': [2.0, 2.1],
                'high': [2.1, 2.2],
                'low': [1.9, 2.0],
                'close': [2.05, 2.15],
                'volume': [2000000, 2100000]
            })
        }
        
        results = self.writer.write_daily_batch(records)
        
        # 验证每只ETF写入成功
        self.assertEqual(results['510300'], 2)
        self.assertEqual(results['159577'], 2)
        self.assertEqual(results['512880'], 2)
        
        # 验证总记录数
        total = self.writer.get_record_count()
        self.assertEqual(total, 6)


class TestLoaderWriterIntegration(unittest.TestCase):
    """测试 loader 与 writer 的集成"""
    
    def setUp(self):
        """创建临时测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.writer = DataWriter(self.db_path)
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def test_write_then_load(self):
        """写入后可以被正确读取"""
        # 写入数据
        df = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-02', '2024-01-03'],
            'open': [3.5, 3.6, 3.7],
            'high': [3.6, 3.7, 3.8],
            'low': [3.4, 3.5, 3.6],
            'close': [3.55, 3.65, 3.75],
            'volume': [1000000, 1100000, 1200000]
        })
        
        self.writer.write_daily('510300', df)
        
        # 通过 SQL 直接读取验证
        conn = sqlite3.connect(self.db_path)
        loaded = pd.read_sql(
            'SELECT * FROM daily WHERE code=? ORDER BY date',
            conn,
            params=('510300',)
        )
        conn.close()
        
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded['close'].iloc[0], 3.55)
        self.assertEqual(loaded['close'].iloc[2], 3.75)
    
    def test_data_integrity(self):
        """验证数据完整性约束"""
        # 写入数据
        df = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-02'],
            'open': [3.5, 3.6],
            'high': [3.6, 3.7],
            'low': [3.4, 3.5],
            'close': [3.55, 3.65],
            'volume': [1000000, 1100000]
        })
        
        self.writer.write_daily('510300', df)
        
        # 尝试写入重复数据
        df2 = pd.DataFrame({
            'date': ['2024-01-01'],  # 重复日期
            'open': [4.0],
            'high': [4.1],
            'low': [3.9],
            'close': [4.0],
            'volume': [2000000]
        })
        
        count = self.writer.write_daily('510300', df2)
        self.assertEqual(count, 0)  # 不应写入
        
        # 验证数据未变化
        conn = sqlite3.connect(self.db_path)
        result = conn.execute(
            'SELECT close FROM daily WHERE code=? AND date=?',
            ('510300', '2024-01-01')
        ).fetchone()
        conn.close()
        
        self.assertAlmostEqual(result[0], 3.55)  # 应该是原始值，不是 4.0


class TestRealtimeWriterIntegration(unittest.TestCase):
    """测试实时行情写入"""
    
    def setUp(self):
        """创建临时测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.writer = DataWriter(self.db_path)
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def test_realtime_update(self):
        """测试实时行情更新"""
        quote1 = {
            'code': '510300',
            'name': '沪深300ETF',
            'price': 4.0,
            'change': 0.1,
            'change_pct': 2.5,
            'volume': 1000000,
            'amount': 4000000,
            'timestamp': '2024-01-01T10:00:00'
        }
        
        self.writer.write_realtime('510300', quote1)
        
        # 再次更新（同一代码）
        quote2 = {
            'code': '510300',
            'name': '沪深300ETF',
            'price': 4.1,  # 价格变化
            'change': 0.2,
            'change_pct': 5.1,
            'volume': 1100000,
            'amount': 4510000,
            'timestamp': '2024-01-01T10:05:00'
        }
        
        self.writer.write_realtime('510300', quote2)
        
        # 验证只保留最新一条
        conn = sqlite3.connect(self.db_path)
        result = conn.execute('SELECT COUNT(*) FROM realtime_cache WHERE code=?', ('510300',)).fetchone()
        conn.close()
        
        self.assertEqual(result[0], 1)
        
        # 验证价格是最新值
        conn = sqlite3.connect(self.db_path)
        result = conn.execute('SELECT price FROM realtime_cache WHERE code=?', ('510300',)).fetchone()
        conn.close()
        
        self.assertAlmostEqual(result[0], 4.1)


class TestStockInfoWriter(unittest.TestCase):
    """测试证券信息写入"""
    
    def setUp(self):
        """创建临时测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.writer = DataWriter(self.db_path)
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def test_write_stock_info(self):
        """测试写入证券基本信息"""
        info = {
            'name': '沪深300ETF',
            'exchange': 'SH',
            'category': 'ETF'
        }
        
        result = self.writer.write_stock_info('510300', info)
        self.assertTrue(result)
        
        # 验证
        conn = sqlite3.connect(self.db_path)
        result = conn.execute('SELECT name, exchange FROM stock_info WHERE code=?', ('510300',)).fetchone()
        conn.close()
        
        self.assertEqual(result[0], '沪深300ETF')
        self.assertEqual(result[1], 'SH')


class TestEndToEnd(unittest.TestCase):
    """端到端集成测试"""
    
    def setUp(self):
        """创建临时测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.writer = DataWriter(self.db_path)
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def test_full_pipeline(self):
        """完整流程：写入 → 读取 → 验证"""
        # Step 1: 批量写入多只ETF
        records = {
            '510300': pd.DataFrame({
                'date': ['2024-01-01', '2024-01-02', '2024-01-03'],
                'open': [3.5, 3.6, 3.7],
                'high': [3.6, 3.7, 3.8],
                'low': [3.4, 3.5, 3.6],
                'close': [3.55, 3.65, 3.75],
                'volume': [1000000, 1100000, 1200000]
            }),
            '159577': pd.DataFrame({
                'date': ['2024-01-01', '2024-01-02', '2024-01-03'],
                'open': [1.5, 1.6, 1.7],
                'high': [1.6, 1.7, 1.8],
                'low': [1.4, 1.5, 1.6],
                'close': [1.55, 1.65, 1.75],
                'volume': [500000, 600000, 700000]
            })
        }
        
        results = self.writer.write_daily_batch(records)
        
        # Step 2: 验证写入结果
        total_records = self.writer.get_record_count()
        self.assertEqual(total_records, 6)
        
        # Step 3: 验证最新日期
        latest_510300 = self.writer.get_latest_date('510300')
        latest_159577 = self.writer.get_latest_date('159577')
        self.assertEqual(latest_510300, '2024-01-03')
        self.assertEqual(latest_159577, '2024-01-03')
        
        # Step 4: 模拟增量更新（新增一天数据）
        df_new = pd.DataFrame({
            'date': ['2024-01-04'],
            'open': [3.8],
            'high': [3.9],
            'low': [3.7],
            'close': [3.85],
            'volume': [1300000]
        })
        
        self.writer.write_daily('510300', df_new)
        
        # Step 5: 验证增量更新
        latest_510300 = self.writer.get_latest_date('510300')
        self.assertEqual(latest_510300, '2024-01-04')
        
        total_records = self.writer.get_record_count()
        self.assertEqual(total_records, 7)


if __name__ == '__main__':
    unittest.main()