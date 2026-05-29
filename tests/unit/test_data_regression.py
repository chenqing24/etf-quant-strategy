"""
回归测试 - Phase 3
验证现有调用方（decision.py, report_generator.py, tracker.py）不受影响
"""
import os
import sys
import tempfile
import shutil
from pathlib import Path
import pandas as pd
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.data.writer import DataWriter
from src.data.loader import DataLoader
from src.data.fetcher import TencentETFetcher
from src.data.facade import DataFacade, HotDataManager, ColdDataManager


class TestDataFacadeRegression(unittest.TestCase):
    """回归测试：DataFacade 现有功能"""
    
    def setUp(self):
        """创建临时测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        # DataFacade 使用 base_dir / 'etf.db'
        # DataWriter 也使用相同的路径
        self.db_path = os.path.join(self.temp_dir, 'etf.db')
        
        # 写入测试数据
        self.writer = DataWriter(self.db_path)
        df = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-02', '2024-01-03'],
            'open': [3.5, 3.6, 3.7],
            'high': [3.6, 3.7, 3.8],
            'low': [3.4, 3.5, 3.6],
            'close': [3.55, 3.65, 3.75],
            'volume': [1000000, 1100000, 1200000]
        })
        self.writer.write_daily('510300', df)
        
        # 创建 DataFacade（使用相同的 base_dir）
        self.facade = DataFacade(self.temp_dir)
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def test_cold_get_daily(self):
        """测试 ColdDataManager.get_daily()"""
        df = self.facade.cold.get_daily('510300', limit=10)
        
        self.assertFalse(df.empty)
        self.assertIn('date', df.columns)
        self.assertIn('close', df.columns)
        self.assertEqual(len(df), 3)
    
    def test_cold_get_code_list(self):
        """测试 ColdDataManager.get_code_list()"""
        codes = self.facade.cold.get_code_list()
        
        self.assertIn('510300', codes)
    
    def test_get_daily(self):
        """测试 DataFacade.get_daily()"""
        df = self.facade.get_daily('510300', days=60)
        
        self.assertFalse(df.empty)
        self.assertIn('close', df.columns)
    
    def test_get_merged(self):
        """测试 DataFacade.get_merged()"""
        df = self.facade.get_merged('510300', days=60)
        
        self.assertFalse(df.empty)
    
    def test_hot_manager(self):
        """测试 HotDataManager"""
        # 写入热数据
        self.facade.hot.set('510300', {
            'price': 4.0,
            'change': 0.1,
            'timestamp': '1704067200'
        })
        
        # 读取热数据
        hot = self.facade.hot.get('510300')
        self.assertIsNotNone(hot)
        self.assertEqual(hot['price'], 4.0)
    
    def test_lifecycle_info(self):
        """测试 DataFacade.get_lifecycle_info()"""
        info = self.facade.get_lifecycle_info()
        
        self.assertIn('total_rows', info)
        self.assertIn('etf_count', info)
        self.assertEqual(info['etf_count'], 1)
    
    def test_get_daily_batch(self):
        """测试批量获取"""
        # 先写入另一只ETF
        df = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-02', '2024-01-03'],
            'open': [1.5, 1.6, 1.7],
            'high': [1.6, 1.7, 1.8],
            'low': [1.4, 1.5, 1.6],
            'close': [1.55, 1.65, 1.75],
            'volume': [500000, 600000, 700000]
        })
        self.writer.write_daily('159577', df)
        
        # 批量获取
        df = self.facade.get_daily_batch(['510300', '159577'], '2024-01-01')
        
        self.assertEqual(len(df), 2)


class TestLoaderFacadeIntegration(unittest.TestCase):
    """测试 DataLoader 与 DataFacade 的配合"""
    
    def setUp(self):
        """创建临时测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'etf.db')
        
        # 写入测试数据
        self.writer = DataWriter(self.db_path)
        for code in ['510300', '159577', '512880']:
            df = pd.DataFrame({
                'date': ['2024-01-01', '2024-01-02', '2024-01-03'],
                'open': [3.5, 3.6, 3.7],
                'high': [3.6, 3.7, 3.8],
                'low': [3.4, 3.5, 3.6],
                'close': [3.55, 3.65, 3.75],
                'volume': [1000000, 1100000, 1200000]
            })
            self.writer.write_daily(code, df)
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def test_loader_load(self):
        """测试 DataLoader.load()"""
        loader = DataLoader(self.db_path)
        data = loader.load(min_rows=1)
        
        self.assertEqual(len(data), 3)
        self.assertIn('510300', data)
        self.assertIn('159577', data)
        self.assertIn('512880', data)
    
    def test_loader_and_facade_consistent(self):
        """验证 DataLoader 和 DataFacade 读取一致"""
        loader = DataLoader(self.db_path)
        data = loader.load(min_rows=1)
        
        facade = DataFacade(self.temp_dir)
        codes = facade.cold.get_code_list()
        
        self.assertEqual(set(data.keys()), set(codes))


class TestFetcherFacadeIntegration(unittest.TestCase):
    """测试 Fetcher 写入后 Facade 能读取"""
    
    def setUp(self):
        """创建临时测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'etf.db')
        
        # 初始化 DataWriter
        self.writer = DataWriter(self.db_path)
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def test_simulate_fetcher_write(self):
        """模拟 fetcher.fetch_etf + save_etf 流程"""
        # 模拟 fetcher.fetch_etf 返回的数据
        df = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-02', '2024-01-03'],
            'open': [3.5, 3.6, 3.7],
            'high': [3.6, 3.7, 3.8],
            'low': [3.4, 3.5, 3.6],
            'close': [3.55, 3.65, 3.75],
            'volume': [1000000, 1100000, 1200000]
        })
        
        # 模拟 fetcher.save_etf 写入
        count = self.writer.write_daily('510300', df)
        self.assertEqual(count, 3)
        
        # 验证 DataFacade 能读取
        facade = DataFacade(self.temp_dir)
        df = facade.cold.get_daily('510300')
        
        # 检查列名
        cols = df.columns.tolist()
        self.assertIn('close', cols)


class TestDataLayerConsistency(unittest.TestCase):
    """验证数据层一致性"""
    
    def setUp(self):
        """创建临时测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'etf.db')
        
        # 初始化
        self.writer = DataWriter(self.db_path)
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def test_write_read_consistency(self):
        """验证写入和读取的数据一致"""
        # 写入数据
        original_df = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-02', '2024-01-03'],
            'open': [3.5, 3.6, 3.7],
            'high': [3.6, 3.7, 3.8],
            'low': [3.4, 3.5, 3.6],
            'close': [3.55, 3.65, 3.75],
            'volume': [1000000, 1100000, 1200000]
        })
        
        self.writer.write_daily('510300', original_df)
        
        # 通过 DataLoader 读取
        loader = DataLoader(self.db_path)
        loaded_df = loader.load_single('510300')
        
        # 验证数据一致
        self.assertEqual(len(loaded_df), len(original_df))
        self.assertAlmostEqual(loaded_df['close'].iloc[0], 3.55)
        self.assertAlmostEqual(loaded_df['close'].iloc[-1], 3.75)
    
    def test_incremental_write_preserves_existing(self):
        """增量写入不破坏已有数据"""
        # 初始写入
        df1 = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-02'],
            'open': [3.5, 3.6],
            'high': [3.6, 3.7],
            'low': [3.4, 3.5],
            'close': [3.55, 3.65],
            'volume': [1000000, 1100000]
        })
        self.writer.write_daily('510300', df1)
        
        # 增量写入（部分重复）
        df2 = pd.DataFrame({
            'date': ['2024-01-02', '2024-01-03'],
            'open': [3.6, 3.7],
            'high': [3.7, 3.8],
            'low': [3.5, 3.6],
            'close': [3.65, 3.75],
            'volume': [1100000, 1200000]
        })
        self.writer.write_daily('510300', df2)
        
        # 读取验证
        loader = DataLoader(self.db_path)
        df = loader.load_single('510300')
        
        # 应该是 3 条（01-01, 01-02, 01-03），不是 4 条
        self.assertEqual(len(df), 3)
        
        # 01-02 的数据应该是原始值（不被覆盖）
        self.assertAlmostEqual(df[df['date'] == '2024-01-02']['close'].iloc[0], 3.65)


if __name__ == '__main__':
    unittest.main()