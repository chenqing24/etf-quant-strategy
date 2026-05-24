#!/usr/bin/env python3
"""选股器测试"""
import pytest
import pandas as pd
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.selector import Selector
from src.config import StrategyConfig
from src.indicator import Indicator


class TestSelector:
    """选股器测试"""
    
    @pytest.fixture
    def sample_data(self):
        """创建测试数据"""
        np.random.seed(42)
        
        # 创建2只ETF
        data = {}
        
        for code in ['510500', '510880']:
            dates = pd.date_range('2022-01-01', periods=500).strftime('%Y-%m-%d')
            
            # ETF1: 上涨
            base = 100
            prices1 = []
            for i in range(500):
                base += np.random.randn() * 2 + 0.1
                prices1.append(base)
            
            df = pd.DataFrame({
                'date': dates,
                'close': prices1,
                'volume': np.random.randint(1000000, 5000000, 500),
            })
            
            # 计算指标
            df = Indicator.calculate(df)
            data[code] = df
        
        return data
    
    def test_exclude_codes(self):
        """测试排除规则"""
        config = StrategyConfig()
        
        assert '159825' in config.exclude_codes  # 港股通
        assert '513360' in config.exclude_codes  # 红利
        assert '512880' in config.exclude_codes  # 证券
    
    def test_select_etfs(self, sample_data):
        """测试ETF筛选"""
        selector = Selector()
        config = StrategyConfig()
        
        selected = selector.select_etfs(sample_data, config)
        
        # 应该选出一定数量的ETF
        assert len(selected) > 0
        assert len(selected) <= len(sample_data)
    
    def test_score_etf(self, sample_data):
        """测试打分"""
        selector = Selector()
        
        # 随便取一个日期
        test_date = sample_data['510500']['date'].iloc[100]
        
        score, reasons = selector.score(sample_data['510500'], test_date)
        
        # 分数应该是整数
        assert isinstance(score, int)
        assert score >= 0
        
        # 原因应该是列表
        assert isinstance(reasons, list)
    
    def test_score_no_data(self, sample_data):
        """测试无数据日期"""
        selector = Selector()
        
        score, reasons = selector.score(sample_data['510500'], '2021-01-01')
        
        assert score == 0
        assert reasons == []


if __name__ == '__main__':
    pytest.main([__file__, '-v'])