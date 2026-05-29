"""
端到端测试 - 模拟真实采集流程
验证：采集 → 写入 → 读取 → 评分的完整流程
"""
import os
import sys
import sqlite3
import tempfile
import shutil
from pathlib import Path
import pandas as pd
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.data.writer import DataWriter
from src.data.monitor import DataQualityMonitor


class TestE2E_DataCollection(unittest.TestCase):
    """端到端：数据采集流程"""
    
    def setUp(self):
        """创建临时测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.writer = DataWriter(self.db_path)
        self.monitor = DataQualityMonitor(self.db_path)
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def test_collection_pipeline(self):
        """模拟真实采集流程：
        1. 采集多只ETF历史数据
        2. 批量写入
        3. 增量更新（新数据）
        """
        # Step 1: 初始批量采集
        etf_codes = ['510300', '159577', '512880', '515000']
        records = {}
        
        for code in etf_codes:
            # 模拟采集30天数据
            dates = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') 
                     for i in range(30, 0, -1)]
            
            records[code] = pd.DataFrame({
                'date': dates,
                'open': [3.5 + i * 0.01 for i in range(30)],
                'high': [3.6 + i * 0.01 for i in range(30)],
                'low': [3.4 + i * 0.01 for i in range(30)],
                'close': [3.55 + i * 0.01 for i in range(30)],
                'volume': [1000000 + i * 10000 for i in range(30)]
            })
        
        # 批量写入
        results = self.writer.write_daily_batch(records)
        
        # 验证每只ETF写入30条
        for code in etf_codes:
            self.assertEqual(results[code], 30)
        
        # Step 2: 验证存储
        total = self.writer.get_record_count()
        self.assertEqual(total, 120)  # 4 * 30 = 120
        
        # Step 3: 模拟第二天增量采集
        new_records = {
            '510300': pd.DataFrame({
                'date': [datetime.now().strftime('%Y-%m-%d')],
                'open': [3.8],
                'high': [3.9],
                'low': [3.7],
                'close': [3.85],
                'volume': [1500000]
            })
        }
        
        self.writer.write_daily_batch(new_records)
        
        # 验证增量更新成功
        total = self.writer.get_record_count()
        self.assertEqual(total, 121)  # 120 + 1 = 121
        
        latest = self.writer.get_latest_date('510300')
        self.assertEqual(latest, datetime.now().strftime('%Y-%m-%d'))


class TestE2E_DataQuality(unittest.TestCase):
    """端到端：数据质量监控"""
    
    def setUp(self):
        """创建临时测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.writer = DataWriter(self.db_path)
        self.monitor = DataQualityMonitor(self.db_path)
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def test_monitor_after_collection(self):
        """采集后运行监控检查"""
        # 写入测试数据
        today = datetime.now()
        records = {
            '510300': pd.DataFrame({
                'date': [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(5, 0, -1)],
                'open': [3.5, 3.6, 3.7, 3.8, 3.9],
                'high': [3.6, 3.7, 3.8, 3.9, 4.0],
                'low': [3.4, 3.5, 3.6, 3.7, 3.8],
                'close': [3.55, 3.65, 3.75, 3.85, 3.95],
                'volume': [1000000, 1100000, 1200000, 1300000, 1400000]
            })
        }
        
        self.writer.write_daily_batch(records)
        
        # 运行监控
        report = self.monitor.check_all()
        
        # 验证监控结果结构
        self.assertIn('timestamp', report)
        self.assertIn('freshness', report)
        self.assertIn('completeness', report)
        self.assertIn('storage', report)
        
        # 验证新鲜度（延迟1天可接受）
        self.assertIn(report['freshness']['status'], ['OK', 'WARNING'])
        self.assertLessEqual(report['freshness']['delay_days'], 1)
        
        # 验证完整性（只有1只ETF，可能与配置不匹配）
        self.assertIn(report['completeness']['status'], ['OK', 'WARNING', 'ERROR'])
        self.assertEqual(report['completeness']['total_etfs'], 1)
        
        # 验证存储健康
        self.assertIn(report['storage']['status'], ['OK', 'WARNING'])
        self.assertGreater(report['storage']['total_records'], 0)
    
    def test_monitor_alert(self):
        """监控告警检测"""
        # 写入一条很老的数据（模拟数据过期）
        old_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        records = {
            '510300': pd.DataFrame({
                'date': [old_date],
                'open': [3.5],
                'high': [3.6],
                'low': [3.4],
                'close': [3.55],
                'volume': [1000000]
            })
        }
        
        self.writer.write_daily_batch(records)
        
        # 运行监控
        report = self.monitor.check_all()
        
        # 验证数据新鲜度状态是 WARNING
        self.assertIn(report['freshness']['status'], ['WARNING', 'ERROR'])
        self.assertGreater(report['freshness']['delay_days'], 3)  # 延迟超过阈值


class TestE2E_BackupRestore(unittest.TestCase):
    """端到端：备份恢复"""
    
    def setUp(self):
        """创建临时测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.backup_dir = os.path.join(self.temp_dir, 'backups')
        self.writer = DataWriter(self.db_path)
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def test_backup_preserves_data(self):
        """备份后数据保持不变"""
        # 写入测试数据
        records = {
            '510300': pd.DataFrame({
                'date': ['2024-01-01', '2024-01-02', '2024-01-03'],
                'open': [3.5, 3.6, 3.7],
                'high': [3.6, 3.7, 3.8],
                'low': [3.4, 3.5, 3.6],
                'close': [3.55, 3.65, 3.75],
                'volume': [1000000, 1100000, 1200000]
            })
        }
        
        self.writer.write_daily_batch(records)
        original_count = self.writer.get_record_count()
        
        # 执行备份
        from scripts.backup_sqlite import SQLiteBackupManager
        manager = SQLiteBackupManager(self.db_path, self.backup_dir)
        backup_path = manager.backup('manual')
        
        # 验证备份文件存在
        self.assertTrue(Path(backup_path).exists())
        
        # 备份后添加新数据
        new_records = {
            '510300': pd.DataFrame({
                'date': ['2024-01-04'],
                'open': [3.8],
                'high': [3.9],
                'low': [3.7],
                'close': [3.85],
                'volume': [1300000]
            })
        }
        
        self.writer.write_daily_batch(new_records)
        new_count = self.writer.get_record_count()
        self.assertEqual(original_count + 1, new_count)
        
        # 验证备份文件数据（旧数据存在）
        conn = sqlite3.connect(backup_path)
        cur = conn.execute('SELECT COUNT(*) FROM daily WHERE code=?', ('510300',))
        backup_count = cur.fetchone()[0]
        conn.close()
        
        self.assertEqual(backup_count, 3)  # 备份只有旧数据


class TestE2E_ConcurrentScenarios(unittest.TestCase):
    """端到端：并发场景"""
    
    def setUp(self):
        """创建临时测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, 'test.db')
        self.writer = DataWriter(self.db_path)
    
    def tearDown(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir)
    
    def test_repeated_write_same_data(self):
        """重复写入相同数据不影响"""
        df = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-02', '2024-01-03'],
            'open': [3.5, 3.6, 3.7],
            'high': [3.6, 3.7, 3.8],
            'low': [3.4, 3.5, 3.6],
            'close': [3.55, 3.65, 3.75],
            'volume': [1000000, 1100000, 1200000]
        })
        
        # 连续3次写入相同数据
        for _ in range(3):
            count = self.writer.write_daily('510300', df)
        
        # 验证只有3条记录
        total = self.writer.get_record_count('510300')
        self.assertEqual(total, 3)
    
    def test_mixed_batch_write(self):
        """混合批量写入（部分ETF重复）"""
        # 第一次批量写入
        batch1 = {
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
            })
        }
        
        self.writer.write_daily_batch(batch1)
        
        # 第二次批量写入（部分重复 + 新ETF）
        batch2 = {
            '510300': pd.DataFrame({
                'date': ['2024-01-03'],  # 新增
                'open': [3.7],
                'high': [3.8],
                'low': [3.6],
                'close': [3.75],
                'volume': [1200000]
            }),
            '512880': pd.DataFrame({  # 新ETF
                'date': ['2024-01-01'],
                'open': [2.0],
                'high': [2.1],
                'low': [1.9],
                'close': [2.05],
                'volume': [2000000]
            })
        }
        
        self.writer.write_daily_batch(batch2)
        
        # 验证结果
        # 510300: 2 (batch1) + 1 (batch2) = 3
        # 159577: 2 (batch1)
        # 512880: 1 (batch2)
        # total = 3 + 2 + 1 = 6
        total = self.writer.get_record_count()
        self.assertEqual(total, 6)


if __name__ == '__main__':
    unittest.main()