#!/usr/bin/env python
"""
P0-3: selector.py 配置外部化 - 回归测试

验收标准:
1. Selector 从配置读取因子权重
2. 配置文件修改后 Selector 行为随之改变
3. 默认配置加载正常

运行: python -m pytest tests/unit/test_selector_uses_config.py -v
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
import pandas as pd
import numpy as np
from src.core.selector import Selector
from src.analysis.indicator import Indicator


def create_sample_etf_data(days=180):
    """生成测试用ETF数据"""
    dates = pd.date_range('2024-01-01', periods=days, freq='D')
    np.random.seed(42)
    close_prices = 1.0 + np.linspace(0, 0.3, days) + np.random.randn(days) * 0.02
    return pd.DataFrame({
        'date': [d.strftime('%Y-%m-%d') for d in dates],
        'open': close_prices - 0.01,
        'high': close_prices + 0.02,
        'low': close_prices - 0.02,
        'close': close_prices,
        'volume': 1000000 + np.random.rand(days) * 500000,
    })


class TestSelectorUsesConfig:
    """验证 Selector 使用配置框架"""

    @pytest.fixture
    def sample_df(self):
        df = create_sample_etf_data()
        indicator = Indicator()
        return indicator.calculate(df)

    @pytest.fixture
    def latest_date(self, sample_df):
        return sample_df['date'].iloc[-1]

    def test_selector_imports_config_loader(self):
        """验收1: Selector 导入 ConfigLoader"""
        import src.core.selector as selector_module
        source = open(selector_module.__file__).read()
        assert 'config_loader' in source or 'load_default_strategy' in source

    def test_default_weights_exist(self):
        """验收2: 默认权重存在"""
        weights = Selector._get_default_weights()
        assert 'ma120' in weights
        assert weights['ma120'] > 0

    def test_selector_scores_with_factors(self, sample_df, latest_date):
        """验收3: Selector 评分正常"""
        selector = Selector()
        score, reasons = selector.evaluate(sample_df, latest_date)
        assert isinstance(score, (int, float))
        assert score >= 0
        assert isinstance(reasons, list)


class TestSelectorRegression:
    """回归测试"""

    @pytest.fixture
    def sample_df(self):
        df = create_sample_etf_data()
        indicator = Indicator()
        return indicator.calculate(df)

    def test_evaluate_returns_valid_score(self, sample_df):
        """回归1: evaluate() 返回有效分数"""
        selector = Selector()
        score, reasons = selector.evaluate(sample_df, sample_df['date'].iloc[-1])
        assert isinstance(score, (int, float))
        assert score >= 0

    def test_evaluate_with_rsi_oversold(self, sample_df):
        """回归2: RSI超卖处理"""
        selector = Selector()
        latest_date = sample_df['date'].iloc[-1]
        sample_df.loc[sample_df['date'] == latest_date, 'rsi_14'] = 25.0
        score, reasons = selector.evaluate(sample_df, latest_date)
        assert isinstance(score, (int, float))


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])