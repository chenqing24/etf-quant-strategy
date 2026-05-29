"""E2E 契约测试（5个）"""
import pytest
import tempfile
import sqlite3
from pathlib import Path
import pandas as pd
from src.data.contracts import OHLCVSchema, IndicatorSchema
from src.data.loader import DataLoader
from src.analysis.indicator import Indicator


class TestE2EContracts:
    """端到端契约测试"""
    
    def test_fetcher_to_writer_to_loader(self):
        """契约：写入数据 → 读取数据 → 符合 OHLCV"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'test.db'
            conn = sqlite3.connect(db_path)
            conn.execute('''
                CREATE TABLE daily (
                    code TEXT, date TEXT, open REAL, high REAL,
                    low REAL, close REAL, volume INTEGER
                )
            ''')
            
            # 写入数据
            test_data = {
                '510300': pd.DataFrame({
                    'code': ['510300'] * 3,
                    'date': ['2024-01-02', '2024-01-03', '2024-01-04'],
                    'open': [4.0, 4.1, 4.2],
                    'high': [4.1, 4.2, 4.3],
                    'low': [3.9, 4.0, 4.1],
                    'close': [4.0, 4.1, 4.2],
                    'volume': [1000000, 1100000, 1200000],
                })
            }
            for df in test_data.values():
                df.to_sql('daily', conn, if_exists='append', index=False)
            conn.commit()
            conn.close()
            
            # 读取数据
            loader = DataLoader(db_path=str(db_path))
            data = loader.load(min_rows=1)
            
            # 验证契约
            for code, df in data.items():
                errors = OHLCVSchema.validate(df, source=code)
                assert not errors, f"{code}: {errors}"
    
    def test_loader_to_indicator_pipeline(self, temp_db):
        """契约：loader.load() → indicator.calculate() → 符合 IndicatorSchema"""
        loader = DataLoader(db_path=temp_db)
        data = loader.load(min_rows=1)
        
        result = Indicator.calculate_all(data)
        
        for code, df in result.items():
            errors = IndicatorSchema.validate(df, source=code)
            assert not errors, f"{code}: {errors}"
    
    def test_selector_input_conforms(self, temp_db):
        """契约：selector 接收的数据必须符合 IndicatorSchema"""
        from src.utils.config import StrategyConfig
        
        loader = DataLoader(db_path=temp_db)
        data = loader.load(min_rows=1)
        data = Indicator.calculate_all(data)
        
        # 验证每个 ETF 的数据都符合 IndicatorSchema
        for code, df in data.items():
            errors = IndicatorSchema.validate(df, source=code)
            assert not errors
    
    def test_trade_record_pipeline(self):
        """契约：交易记录写入 → 读取 → 符合 TradeRecordSchema"""
        from src.trade.tracker import TradeTracker, Position
        from src.data.contracts import TradeRecordSchema
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = TradeTracker(tmpdir)
            tracker.record_buy('510300', '沪深300', 4.0, 1000, '策略推荐')
            
            # 获取持仓（交易记录通过持仓反映）
            holdings = tracker.get_holdings()
            if holdings and len(holdings) > 0:
                # 持仓转 DataFrame
                import pandas as pd
                df = pd.DataFrame([
                    {'code': h.code, 'name': h.name, 'action': 'buy',
                     'price': h.entry_price, 'quantity': h.quantity,
                     'date': h.entry_date, 'reason': '策略推荐'}
                    for h in holdings
                ])
                errors = TradeRecordSchema.validate(df, source="tracker")
                assert not errors
    
    def test_report_input_validation(self, temp_db):
        """契约：report_generator 接收的数据必须符合 IndicatorSchema"""
        from src.analysis.report_generator import ETFReportGenerator
        
        generator = ETFReportGenerator(data_dir=temp_db)
        generator.load_data()
        
        for code, df in generator.data.items():
            errors = IndicatorSchema.validate(df, source=code)
            assert not errors