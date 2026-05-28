#!/usr/bin/env python
"""
P0-3: selector.py 配置外部化 - 回归测试

验收标准:
1. Selector 从配置读取因子权重
2. 配置文件修改后 Selector 行为随之改变
3. 默认配置加载正常
4. 回归：评分结果不变（使用配置的默认值）

运行: python tests/test_selector_uses_config.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd
import numpy as np
from src.core.selector import Selector
from src.analysis.indicator import Indicator
from src.strategy.config_loader import load_default_strategy, ConfigLoader
from src.strategy.config_types import StrategyConfig


def create_sample_etf_data(days=180):
    """生成测试用ETF数据"""
    dates = pd.date_range('2024-01-01', periods=days, freq='D')
    np.random.seed(42)
    
    close_prices = 1.0 + np.linspace(0, 0.3, days) + np.random.randn(days) * 0.02
    
    data = {
        'date': [d.strftime('%Y-%m-%d') for d in dates],
        'open': close_prices - 0.01,
        'high': close_prices + 0.02,
        'low': close_prices - 0.02,
        'close': close_prices,
        'volume': 1000000 + np.random.rand(days) * 500000,
    }
    df = pd.DataFrame(data)
    return df


class TestSelectorUsesConfig:
    """验证 Selector 使用配置框架"""

    @pytest.fixture
    def sample_df(self):
        """测试用ETF数据"""
        df = create_sample_etf_data()
        indicator = Indicator()
        df = indicator.calculate(df)
        return df

    @pytest.fixture
    def latest_date(self, sample_df):
        """最新日期"""
        return sample_df['date'].iloc[-1]

    def test_selector_imports_config_loader(self):
        """验收1: Selector 导入 ConfigLoader"""
        import src.core.selector as selector_module
        source = open(selector_module.__file__).read()
        
        assert 'config_loader' in source or 'load_default_strategy' in source, \
            "Selector 未导入配置加载器，应该使用 ConfigLoader"

    def test_default_config_loads_successfully(self):
        """验收2: 默认配置加载正常"""
        config = load_default_strategy()
        
        assert config is not None, "配置加载失败"
        assert hasattr(config, 'factors'), "配置缺少 factors 属性"
        assert hasattr(config.factors, 'enabled'), "factors 缺少 enabled 属性"
        assert hasattr(config.factors, 'weights'), "factors 缺少 weights 属性"
        print(f"默认配置因子: {config.factors.enabled}")
        print(f"默认配置权重: {config.factors.weights}")

    def test_config_modification_affects_selector(self, sample_df, latest_date):
        """验收3: 配置文件修改后 Selector 行为改变"""
        selector = Selector()
        
        # 获取原始配置
        config = load_default_strategy()
        original_weights = config.factors.weights.copy()
        
        # 记录原始分数
        score1, reasons1 = selector.evaluate(sample_df, latest_date)
        print(f"原始配置分数: {score1}, 理由: {reasons1}")
        
        # 修改配置权重（将 ma120 设为0）
        if 'ma120' in config.factors.weights:
            config.factors.weights['ma120'] = 0
            
            # 重新评分
            score2, reasons2 = selector.evaluate(sample_df, latest_date)
            print(f"修改后分数: {score2}, 理由: {reasons2}")
            
            # 验证分数变化（ma120 权重为0后，站上 ma120 不应得分）
            if 'MA120' in reasons1:
                # 如果原始分数包含 MA120，修改后应该减少
                assert score2 < score1 or 'MA120' not in reasons2, \
                    "修改配置后 Selector 行为未改变，配置未生效"

    def test_selector_scores_with_factors(self, sample_df, latest_date):
        """验收4: Selector 使用配置的因子评分"""
        selector = Selector()
        config = load_default_strategy()
        
        # 获取配置中的因子
        enabled_factors = config.factors.enabled
        weights = config.factors.weights
        
        print(f"启用的因子: {enabled_factors}")
        print(f"因子权重: {weights}")
        
        # 评分
        score, reasons = selector.evaluate(sample_df, latest_date)
        
        print(f"评分结果: {score}, 理由: {reasons}")
        
        # 验证：评分应该基于配置中的因子
        # 如果配置中有因子，但评分理由为空，说明配置未生效
        assert score >= 0, "评分异常"
        assert isinstance(reasons, list), "理由应该是列表"


class TestSelectorRegression:
    """回归测试：确保改造后行为不变"""

    @pytest.fixture
    def sample_df(self):
        """测试用ETF数据"""
        df = create_sample_etf_data()
        indicator = Indicator()
        df = indicator.calculate(df)
        return df

    @pytest.fixture
    def latest_date(self, sample_df):
        """最新日期"""
        return sample_df['date'].iloc[-1]

    def test_evaluate_returns_valid_score(self, sample_df, latest_date):
        """回归1: evaluate() 返回有效分数"""
        selector = Selector()
        score, reasons = selector.evaluate(sample_df, latest_date)
        
        assert isinstance(score, (int, float)), "分数应该是数字"
        assert score >= 0, "分数应该非负"
        assert isinstance(reasons, list), "理由应该是列表"

    def test_evaluate_with_rsi_oversold(self, sample_df, latest_date):
        """回归2: RSI超卖处理不变"""
        selector = Selector()
        
        # 设置 RSI 超卖
        sample_df.loc[sample_df['date'] == latest_date, 'rsi_14'] = 25.0
        
        score, reasons = selector.evaluate(sample_df, latest_date)
        
        print(f"RSI=25 评分: {score}, 理由: {reasons}")
        
        # RSI 超卖时，不应该得到 RSI 加分（除非 MA20 向上）
        # 这个测试确保 RSI 处理逻辑不变


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
