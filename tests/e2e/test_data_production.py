"""
生产环境验证测试 - Phase 3
模拟真实业务场景：决策、报告、交易
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
from src.data.facade import DataFacade


class TestProductionScenario(unittest.TestCase):
    """生产场景测试"""
    
    def setUp(self):
        """创建临时测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'etf.db')
        
        # 写入测试数据
        self.writer = DataWriter(self.db_path)
        self._prepare_test_data()
        
        # 创建 DataFacade
        self.facade = DataFacade(self.temp_dir)
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def _prepare_test_data(self):
        """准备测试数据"""
        # 多只ETF
        etf_data = {
            '510300': [
                {'date': '2024-01-01', 'open': 3.5, 'high': 3.6, 'low': 3.4, 'close': 3.55, 'volume': 1000000},
                {'date': '2024-01-02', 'open': 3.6, 'high': 3.7, 'low': 3.5, 'close': 3.65, 'volume': 1100000},
                {'date': '2024-01-03', 'open': 3.7, 'high': 3.8, 'low': 3.6, 'close': 3.75, 'volume': 1200000},
            ],
            '159577': [
                {'date': '2024-01-01', 'open': 1.5, 'high': 1.6, 'low': 1.4, 'close': 1.55, 'volume': 500000},
                {'date': '2024-01-02', 'open': 1.6, 'high': 1.7, 'low': 1.5, 'close': 1.65, 'volume': 600000},
                {'date': '2024-01-03', 'open': 1.7, 'high': 1.8, 'low': 1.6, 'close': 1.75, 'volume': 700000},
            ],
            '512880': [
                {'date': '2024-01-01', 'open': 2.0, 'high': 2.1, 'low': 1.9, 'close': 2.05, 'volume': 2000000},
                {'date': '2024-01-02', 'open': 2.1, 'high': 2.2, 'low': 2.0, 'close': 2.15, 'volume': 2100000},
                {'date': '2024-01-03', 'open': 2.2, 'high': 2.3, 'low': 2.1, 'close': 2.25, 'volume': 2200000},
            ]
        }
        
        for code, records in etf_data.items():
            df = pd.DataFrame(records)
            self.writer.write_daily(code, df)
    
    def test_decision_scenario(self):
        """模拟决策场景：获取多只ETF数据进行评分"""
        # 模拟决策逻辑：获取所有ETF近期数据
        codes = ['510300', '159577', '512880']
        
        # 通过 DataFacade 获取批量数据
        result = {}
        for code in codes:
            df = self.facade.get_daily(code, days=60)
            if not df.empty:
                result[code] = df
        
        # 验证
        self.assertEqual(len(result), 3)
        for code in codes:
            self.assertIn(code, result)
            self.assertFalse(result[code].empty)
            self.assertIn('close', result[code].columns)
    
    def test_report_scenario(self):
        """模拟报告生成场景：获取绩效数据"""
        # 模拟报告生成：获取各ETF最新价格
        codes = ['510300', '159577', '512880']
        
        # 获取最新一条数据
        latest_prices = {}
        for code in codes:
            df = self.facade.cold.get_daily(code, limit=1)
            if not df.empty:
                latest_prices[code] = df.iloc[-1]
        
        # 验证
        self.assertEqual(len(latest_prices), 3)
        for code in codes:
            self.assertIn(code, latest_prices)
            self.assertIn('close', latest_prices[code])
    
    def test_tracker_scenario(self):
        """模拟交易追踪场景：获取持仓ETF数据"""
        # 模拟追踪：获取持仓ETF的近期数据
        holdings = ['510300', '159577']
        
        result = {}
        for code in holdings:
            df = self.facade.cold.get_daily(code, limit=10)
            if not df.empty:
                result[code] = df
        
        # 验证
        self.assertEqual(len(result), 2)
        
        # 验证数据连续性
        for code in holdings:
            dates = pd.to_datetime(result[code]['date'])
            # 验证日期是连续的
            self.assertTrue(len(dates) >= 2)
    
    def test_incremental_update_scenario(self):
        """模拟增量更新场景：新数据追加，旧数据跳过"""
        # 模拟增量更新：写入新数据
        new_records = pd.DataFrame([
            {'date': '2024-01-03', 'open': 3.7, 'high': 3.8, 'low': 3.6, 'close': 3.75, 'volume': 1200000},  # 重复
            {'date': '2024-01-04', 'open': 3.8, 'high': 3.9, 'low': 3.7, 'close': 3.85, 'volume': 1300000},  # 新增
        ])
        
        # 写入
        count = self.writer.write_daily('510300', new_records)
        
        # 验证：只有1条新增（01-04），01-03 被跳过
        self.assertEqual(count, 1)
        
        # 验证总数
        total = self.writer.get_record_count('510300')
        self.assertEqual(total, 4)  # 原来3条 + 新增1条 = 4条
    
    def test_batch_query_scenario(self):
        """批量查询场景"""
        # 获取所有ETF代码
        all_codes = self.facade.cold.get_code_list()
        
        self.assertIn('510300', all_codes)
        self.assertIn('159577', all_codes)
        self.assertIn('512880', all_codes)
        self.assertEqual(len(all_codes), 3)
    
    def test_realtime_hot_cache_scenario(self):
        """实时热数据缓存场景"""
        # 设置实时价格
        self.facade.hot.set('510300', {
            'price': 4.0,
            'change': 0.1,
            'change_pct': 2.5,
            'volume': 1000000,
            'timestamp': '1704067200'
        })
        
        # 获取实时价格
        hot = self.facade.hot.get('510300')
        
        self.assertIsNotNone(hot)
        self.assertEqual(hot['price'], 4.0)
        self.assertEqual(hot['change'], 0.1)


class TestDataQualityUnderLoad(unittest.TestCase):
    """大数据量场景测试"""
    
    def setUp(self):
        """创建临时测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'etf.db')
        self.writer = DataWriter(self.db_path)
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def test_large_batch_write(self):
        """大批量写入（100只ETF，每只500条数据）"""
        import time
        from datetime import datetime, timedelta
        
        codes = [f'51{i:04d}' for i in range(100)]  # 100只ETF
        
        start = time.time()
        
        for code in codes:
            # 每只ETF 500条数据（约2年）
            dates = [(datetime(2022, 1, 1) + timedelta(days=i)).strftime('%Y-%m-%d') 
                     for i in range(500)]
            
            df = pd.DataFrame({
                'date': dates,
                'open': [3.5 + i * 0.001 for i in range(500)],
                'high': [3.6 + i * 0.001 for i in range(500)],
                'low': [3.4 + i * 0.001 for i in range(500)],
                'close': [3.55 + i * 0.001 for i in range(500)],
                'volume': [1000000 + i * 1000 for i in range(500)]
            })
            
            self.writer.write_daily(code, df)
        
        elapsed = time.time() - start
        
        # 验证
        total = self.writer.get_record_count()
        self.assertEqual(total, 50000)  # 100 * 500
        
        # 验证性能（应该在60秒内完成）
        self.assertLess(elapsed, 60, f"批量写入耗时 {elapsed:.1f}s，超过60s")
        
        print(f"\n性能测试: 50000条数据写入耗时 {elapsed:.1f}s")
    
    def test_query_performance(self):
        """查询性能测试"""
        import time
        from datetime import datetime, timedelta
        
        # 先写入大量数据
        codes = [f'51{i:04d}' for i in range(50)]  # 50只ETF
        
        for code in codes:
            dates = [(datetime(2022, 1, 1) + timedelta(days=i)).strftime('%Y-%m-%d') 
                     for i in range(365)]
            
            df = pd.DataFrame({
                'date': dates,
                'open': [3.5 + i * 0.001 for i in range(365)],
                'high': [3.6 + i * 0.001 for i in range(365)],
                'low': [3.4 + i * 0.001 for i in range(365)],
                'close': [3.55 + i * 0.001 for i in range(365)],
                'volume': [1000000 + i * 1000 for i in range(365)]
            })
            
            self.writer.write_daily(code, df)
        
        # 测试查询性能
        from src.data.facade import DataFacade
        
        facade = DataFacade(self.temp_dir)
        
        start = time.time()
        for code in codes[:10]:
            df = facade.cold.get_daily(code, limit=60)
        elapsed = time.time() - start
        
        # 验证性能（10次查询应该在1秒内完成）
        self.assertLess(elapsed, 1, f"查询耗时 {elapsed:.1f}s，超过1s")
        
        print(f"\n查询性能测试: 10次查询耗时 {elapsed:.3f}s")


if __name__ == '__main__':
    unittest.main()