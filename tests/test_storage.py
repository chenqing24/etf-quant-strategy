"""
存储模块测试

验证数据库和数据迁移的正确性
"""
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from src.data.database import Database, get_database


# 测试数据库路径
TEST_DB_PATH = "data/test_etf_factors.db"


@pytest.fixture
def db():
    """创建测试数据库"""
    db = Database(TEST_DB_PATH)
    yield db
    # 清理测试数据库
    Path(TEST_DB_PATH).unlink(missing_ok=True)


class TestDatabaseInit:
    """数据库初始化测试"""
    
    def test_database_created(self, db):
        """测试数据库文件创建"""
        assert Path(TEST_DB_PATH).exists()
    
    def test_all_tables_created(self, db):
        """测试所有表已创建"""
        tables = db.get_table_info()
        table_names = [t['name'] for t in tables]
        
        expected_tables = [
            'stock_info', 'daily_price', 'factor_data',
            'ic_results', 'trade_records', 'backtest_results'
        ]
        
        for table in expected_tables:
            assert table in table_names, f"表 {table} 未创建"
    
    def test_table_row_count(self, db):
        """测试表初始为空"""
        tables = db.get_table_info()
        for table in tables:
            assert table['row_count'] == 0, f"表 {table['name']} 应为空"


class TestDataMigration:
    """数据迁移验证测试"""
    
    def test_insert_stock_info(self, db):
        """测试插入股票信息"""
        data = {
            'code': '159806',
            'name': '芯片ETF',
            'exchange': 'SZ',
            'full_code': 'sz.159806',
            'category': '芯片',
            'created_at': '2024-01-01',
            'updated_at': '2024-01-01'
        }
        
        db.insert_or_update('stock_info', data, ['code'])
        
        result = db.query("SELECT * FROM stock_info WHERE code = ?", ('159806',))
        assert len(result) == 1
        assert result[0]['name'] == '芯片ETF'
    
    def test_insert_daily_price(self, db):
        """测试插入日线数据"""
        data = {
            'code': '159806',
            'date': '2024-01-02',
            'open': 1.0,
            'high': 1.05,
            'low': 0.98,
            'close': 1.02,
            'volume': 1000000,
            'created_at': '2024-01-02'
        }
        
        db.insert_or_update('daily_price', data, ['code', 'date'])
        
        result = db.query(
            "SELECT * FROM daily_price WHERE code = ? AND date = ?",
            ('159806', '2024-01-02')
        )
        assert len(result) == 1
        assert result[0]['close'] == 1.02
    
    def test_insert_or_update(self, db):
        """测试插入或更新"""
        # 第一次插入
        data = {
            'code': '159806',
            'date': '2024-01-02',
            'close': 1.02,
            'created_at': '2024-01-02'
        }
        db.insert_or_update('daily_price', data, ['code', 'date'])
        
        # 第二次更新（不包含updated_at）
        data['close'] = 1.05
        data['open'] = 1.01
        db.insert_or_update('daily_price', data, ['code', 'date'])
        
        # 验证只有一条记录且值已更新
        result = db.query(
            "SELECT * FROM daily_price WHERE code = ? AND date = ?",
            ('159806', '2024-01-02')
        )
        assert len(result) == 1
        assert result[0]['close'] == 1.05


class TestDataIntegrity:
    """数据完整性验证测试"""
    
    def test_price_positive(self, db):
        """测试价格必须为正"""
        # 插入有效数据
        data = {
            'code': '159806',
            'date': '2024-01-02',
            'open': 1.0,
            'high': 1.1,
            'low': 0.9,
            'close': 1.05,
            'volume': 1000,
            'created_at': '2024-01-02'
        }
        db.insert_or_update('daily_price', data, ['code', 'date'])
        
        # 验证价格正确
        result = db.query(
            "SELECT close FROM daily_price WHERE code = ?",
            ('159806',)
        )
        assert result[0]['close'] > 0
    
    def test_required_fields_not_null(self, db):
        """测试必需字段不为NULL"""
        data = {
            'code': '159806',
            'date': '2024-01-02',
            'open': 1.0,
            'high': 1.1,
            'low': 0.9,
            'close': 1.05,
            'volume': 1000,
            'created_at': '2024-01-02'
        }
        db.insert_or_update('daily_price', data, ['code', 'date'])
        
        result = db.query("SELECT * FROM daily_price WHERE code = ?", ('159806',))
        assert result[0]['code'] == '159806'
        assert result[0]['date'] == '2024-01-02'
        assert result[0]['close'] is not None
    
    def test_unique_constraint(self, db):
        """测试唯一约束"""
        data = {
            'code': '159806',
            'date': '2024-01-02',
            'close': 1.05,
            'volume': 1000,
            'created_at': '2024-01-02'
        }
        
        # 插入两次
        db.insert_or_update('daily_price', data, ['code', 'date'])
        db.insert_or_update('daily_price', data, ['code', 'date'])
        
        # 验证只有一条记录
        result = db.query(
            "SELECT COUNT(*) as cnt FROM daily_price WHERE code = ? AND date = ?",
            ('159806', '2024-01-02')
        )
        assert result[0]['cnt'] == 1


class TestDataQuery:
    """数据查询测试"""
    
    def test_query_as_dataframe(self, db):
        """测试查询返回DataFrame"""
        # 插入测试数据
        for i in range(5):
            data = {
                'code': f'15980{i}',
                'date': '2024-01-02',
                'close': 1.0 + i * 0.1,
                'volume': 1000 * (i + 1),
                'created_at': '2024-01-02'
            }
            db.insert_or_update('daily_price', data, ['code', 'date'])
        
        # 查询
        df = db.query_df("SELECT * FROM daily_price WHERE date = '2024-01-02'")
        assert len(df) == 5
        assert 'code' in df.columns
        assert 'close' in df.columns
    
    def test_query_with_params(self, db):
        """测试带参数的查询"""
        data = {
            'code': '159806',
            'date': '2024-01-02',
            'close': 1.05,
            'volume': 1000,
            'created_at': '2024-01-02'
        }
        db.insert_or_update('daily_price', data, ['code', 'date'])
        
        result = db.query("SELECT * FROM daily_price WHERE code = ?", ('159806',))
        assert len(result) == 1
        
        result = db.query("SELECT * FROM daily_price WHERE close > ?", (1.0,))
        assert len(result) >= 1


class TestFactorData:
    """因子数据测试"""
    
    def test_insert_factor_data(self, db):
        """测试插入因子数据"""
        data = {
            'code': '159806',
            'date': '2024-01-02',
            'RSI_5': 65.5,
            'RSI_10': 60.2,
            'K': 70.0,
            'D': 65.0,
            'J': 80.0,
            'DMA': 0.05,
            'OBV': 1000000.0,
            'MAOBV': 950000.0,
            'ADX': 25.5,
            'created_at': '2024-01-02'
        }
        
        db.insert_or_update('factor_data', data, ['code', 'date'])
        
        result = db.query(
            "SELECT RSI_5, K, D, J FROM factor_data WHERE code = ?",
            ('159806',)
        )
        assert len(result) == 1
        assert result[0]['RSI_5'] == 65.5
        assert result[0]['K'] == 70.0
    
    def test_insert_future_returns(self, db):
        """测试插入未来收益"""
        data = {
            'code': '159806',
            'date': '2024-01-02',
            'return_1d': 0.02,
            'return_5d': 0.05,
            'return_10d': 0.10,
            'return_20d': 0.15,
            'created_at': '2024-01-02'
        }
        
        db.insert_or_update('factor_data', data, ['code', 'date'])
        
        result = db.query(
            "SELECT return_1d, return_5d, return_10d, return_20d FROM factor_data WHERE code = ?",
            ('159806',)
        )
        assert result[0]['return_1d'] == 0.02
        assert result[0]['return_5d'] == 0.05


class TestICResults:
    """IC结果测试"""
    
    def test_insert_ic_result(self, db):
        """测试插入IC结果"""
        data = {
            'factor_name': 'RSI_5',
            'code': 'ALL',
            'period': 5,
            'ic_mean': 0.05,
            'ic_std': 0.03,
            'ir': 1.67,
            'direction': 'long',
            'p_value': 0.05,
            'sample_count': 100,
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
            'created_at': '2024-12-31'
        }
        
        db.insert_or_update('ic_results', data, ['factor_name', 'code', 'period', 'start_date', 'end_date'])
        
        result = db.query(
            "SELECT * FROM ic_results WHERE factor_name = ? AND code = ?",
            ('RSI_5', 'ALL')
        )
        assert len(result) == 1
        assert result[0]['ic_mean'] == 0.05
        assert result[0]['ir'] > 0


class TestBacktestResults:
    """回测结果测试"""
    
    def test_insert_backtest_result(self, db):
        """测试插入回测结果"""
        data = {
            'strategy_name': '8因子策略v1',
            'version': '1.0',
            'start_date': '2024-01-01',
            'end_date': '2024-12-31',
            'total_return': 0.20,
            'annual_return': 0.20,
            'sharpe_ratio': 1.5,
            'max_drawdown': 0.10,
            'win_rate': 0.55,
            'profit_loss_ratio': 1.8,
            'trade_count': 50,
            'stop_profit': 0.10,
            'stop_loss': 0.05,
            'created_at': '2024-12-31'
        }
        
        db.insert_or_update('backtest_results', data, ['strategy_name', 'version', 'start_date', 'end_date'])
        
        result = db.query(
            "SELECT * FROM backtest_results WHERE strategy_name = ?",
            ('8因子策略v1',)
        )
        assert len(result) == 1
        assert result[0]['win_rate'] == 0.55
        assert result[0]['profit_loss_ratio'] == 1.8


class TestDatabaseSingleton:
    """数据库单例测试"""
    
    def test_get_database_singleton(self):
        """测试获取数据库单例"""
        db1 = get_database(TEST_DB_PATH)
        db2 = get_database(TEST_DB_PATH)
        assert db1 is db2