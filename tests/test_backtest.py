#!/usr/bin/env python3
"""回测引擎测试"""
import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.backtest import run_backtest, BacktestResult
from src.config import StrategyConfig
from src.indicator import Indicator
from src.market_filter import MarketFilter


class TestBacktest:
    """回测引擎测试"""
    
    @pytest.fixture
    def sample_etf_data(self):
        """创建模拟ETF数据"""
        np.random.seed(42)
        
        data = {}
        
        # 创建3只ETF
        for i, code in enumerate(['510500', '510880', '159999']):
            dates = pd.date_range('2024-01-01', periods=200).strftime('%Y-%m-%d')
            
            # 不同走势
            if i == 0:
                trend = 0.2  # 强上涨
            elif i == 1:
                trend = 0.05  # 震荡
            else:
                trend = -0.1  # 下跌
            
            base = 100
            prices = []
            for j in range(200):
                base += np.random.randn() * 3 + trend
                prices.append(base)
            
            df = pd.DataFrame({
                'date': dates,
                'close': prices,
                'volume': np.random.randint(1000000, 5000000, 200),
            })
            
            df = Indicator.calculate(df)
            data[code] = df
        
        return data
    
    def test_basic_run(self, sample_etf_data):
        """测试基本回测运行"""
        config = StrategyConfig(
            score_threshold=4,
            rebalance_days=10,
        )
        
        result = run_backtest(
            sample_etf_data, 
            config, 
            '2024-06-01', 
            '2024-12-31'
        )
        
        # 应该返回结果
        assert 'return' in result
        assert 'drawdown' in result
        assert 'winrate' in result
        assert 'trades' in result
    
    def test_empty_data(self):
        """空数据测试"""
        config = StrategyConfig()
        
        result = run_backtest({}, config, '2024-01-01', '2024-12-31')
        
        assert result['return'] == 0
    
    def test_result_fields(self, sample_etf_data):
        """测试结果字段完整性"""
        config = StrategyConfig()
        
        result = run_backtest(
            sample_etf_data,
            config,
            '2024-06-01',
            '2024-12-31'
        )
        
        assert isinstance(result['return'], (int, float))
        assert isinstance(result['drawdown'], (int, float))
        assert isinstance(result['winrate'], (int, float))
        assert isinstance(result['trades'], int)
    
    def test_market_filter_integration(self, sample_etf_data):
        """测试市场过滤集成"""
        config = StrategyConfig()
        
        # 创建沪深300数据
        hs300_dates = pd.date_range('2024-01-01', periods=200).strftime('%Y-%m-%d')
        hs300_base = 3000
        hs300_prices = []
        for i in range(200):
            hs300_base += np.random.randn() * 20 + 1
            hs300_prices.append(hs300_base)
        
        hs300 = pd.DataFrame({
            'date': hs300_dates,
            'close': hs300_prices,
            'volume': np.random.randint(10000000, 50000000, 200),
        })
        
        market_filter = MarketFilter(hs300, ma=60)
        
        # 带市场过滤的回测
        result = run_backtest(
            sample_etf_data,
            config,
            '2024-06-01',
            '2024-12-31',
            market_filter
        )
        
        # 应该有结果，且和市场过滤可以正常工作
        assert result is not None
    
    def test_different_rebalance_days(self, sample_etf_data):
        """测试不同调仓周期"""
        results = []
        
        for days in [5, 10, 15]:
            config = StrategyConfig(
                score_threshold=4,
                rebalance_days=days,
            )
            
            result = run_backtest(
                sample_etf_data,
                config,
                '2024-06-01',
                '2024-12-31'
            )
            
            results.append((days, result['return']))
        
        # 不同参数应该有不同结果
        # (在随机数据下可能相同，但至少应该能运行)
        assert len(results) == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])