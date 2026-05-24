#!/usr/bin/env python3
"""
ETF量化策略 - 测试套件
========================================
运行:
    python tests/test_all.py        # 单元测试
    python tests/test_regression.py # 回归测试
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ==================== 单元测试 ====================

def test_01_config():
    """测试配置"""
    from src.config import StrategyConfig
    
    config = StrategyConfig()
    
    # 默认参数
    assert config.rebalance_days == 10
    assert config.score_threshold == 6
    assert config.hold_count == 2
    
    # 排除码
    assert '159825' in config.exclude_codes
    assert '513360' in config.exclude_codes
    
    # 可配置参数
    config2 = StrategyConfig(rebalance_days=5, score_threshold=4)
    assert config2.rebalance_days == 5
    assert config2.score_threshold == 4
    
    print("✓ test_01_config 通过")


def test_02_data_loader():
    """测试数据加载"""
    from src.data_loader import DataLoader
    
    loader = DataLoader()
    data = loader.load('../etf_data_50')
    
    assert len(data) > 0, "应加载到数据"
    assert '510300' in data, "应包含沪深300"
    
    # 数据格式
    df = data['510300']
    assert 'date' in df.columns
    assert 'close' in df.columns
    assert df['close'].dtype in ['float64', 'float32']
    
    print("✓ test_02_data_loader 通过")


def test_03_indicator():
    """测试指标计算"""
    from src.indicator import Indicator
    import pandas as pd
    import numpy as np
    
    # 创建测试数据
    df = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=150).strftime('%Y-%m-%d'),
        'close': np.linspace(100, 150, 150),
        'volume': np.random.randint(1000000, 5000000, 150),
    })
    
    result = Indicator.calculate(df)
    
    # 验证MA
    assert 'ma20' in result.columns
    assert abs(result['ma20'].iloc[-1] - 145) < 5  # 接近最后价格
    
    # 验证量比
    assert 'vol_ratio' in result.columns
    
    # 验证RSI
    assert 'rsi_14' in result.columns
    assert (result['rsi_14'].dropna() >= 0).all()
    assert (result['rsi_14'].dropna() <= 100).all()
    
    print("✓ test_03_indicator 通过")


def test_04_selector():
    """测试选股"""
    from src.selector import Selector
    from src.config import StrategyConfig
    from src.data_loader import DataLoader
    from src.indicator import Indicator
    
    # 加载真实数据
    loader = DataLoader()
    data = loader.load('../etf_data_50')
    
    # 选ETF
    config = StrategyConfig()
    selector = Selector()
    selected = selector.select_etfs(data, config)
    
    assert 20 <= len(selected) <= 50, "应选出合理数量"
    
    # 测试打分
    data_with_indicator = Indicator.calculate_all(data)
    score, reasons = selector.score(data_with_indicator['510300'], '2025-06-01')
    
    assert isinstance(score, int)
    assert score >= 0
    assert isinstance(reasons, list)
    
    print("✓ test_04_selector 通过")


def test_05_market_filter():
    """测试市场过滤"""
    from src.market_filter import MarketFilter
    import pandas as pd
    
    # 上涨趋势
    df1 = pd.DataFrame({
        'date': ['2025-01-01', '2025-01-02', '2025-01-03'],
        'close': [100, 110, 120],
        'volume': [1000, 1000, 1000]
    })
    mf1 = MarketFilter(df1, ma=2)
    assert mf1.is_bullish('2025-01-03') == True
    
    # 下跌趋势
    df2 = pd.DataFrame({
        'date': ['2025-01-01', '2025-01-02', '2025-01-03'],
        'close': [120, 110, 100],
        'volume': [1000, 1000, 1000]
    })
    mf2 = MarketFilter(df2, ma=2)
    assert mf2.is_bullish('2025-01-03') == False
    
    print("✓ test_05_market_filter 通过")


def test_06_trade_executor():
    """测试交易执行"""
    from src.trade import TradeExecutor
    from src.config import StrategyConfig
    
    config = StrategyConfig(rebalance_days=5, hold_count=2)
    executor = TradeExecutor(config)
    
    assert executor.equity == 1.0
    assert len(executor.holdings) == 0
    assert executor.cooldown_days == 0
    
    # 重置测试
    executor.equity = 0.8
    executor.reset()
    assert executor.equity == 1.0
    
    print("✓ test_06_trade_executor 通过")


def test_07_metrics():
    """测试指标计算"""
    from src.metrics import calculate_metrics
    
    # 场景1: 盈利
    m = calculate_metrics(
        equity=2.0,
        equity_history=[1.0, 1.5, 2.0],
        trades=[],
        all_dates=['2025-01-01', '2025-01-02', '2025-01-03'],
        holding_dates={'2025-01-02'}
    )
    assert m['return'] == 100.0
    assert m['trade_days_ratio'] > 0
    
    # 场景2: 无交易
    m2 = calculate_metrics(
        equity=1.0,
        equity_history=[1.0],
        trades=[],
        all_dates=['2025-01-01'],
        holding_dates=set()
    )
    assert m2['return'] == 0.0
    
    print("✓ test_07_metrics 通过")


def test_08_integration():
    """集成测试"""
    from src.config import run_strategy
    
    # 短周期测试
    result = run_strategy(
        test_start='2025-05-06',
        test_end='2025-06-30',
        rebalance_days=10,
        data_dir='../etf_data_50'
    )
    
    # 验证返回值
    required_keys = ['return', 'drawdown', 'winrate', 'trades', 
                     'annual_return', 'sharpe', 'calmar']
    
    for key in required_keys:
        assert key in result, f"缺少字段: {key}"
    
    # 验证合理性
    assert result['return'] > -90, "不应该亏超过90%"
    assert -100 <= result['drawdown'] <= 0, "回撤应在-100~0之间"
    assert 0 <= result['winrate'] <= 100, "胜率应在0~100之间"
    
    print(f"✓ test_08_integration 通过 (收益{result['return']:+.1f}%)")


def test_09_factor_analysis():
    """测试因子有效性分析"""
    from src.factor_analysis import FactorAnalysis
    import numpy as np
    import pandas as pd
    
    # 测试IC计算 - 正相关
    f1 = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    r1 = np.array([0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10])
    ic1 = FactorAnalysis.calculate_ic(f1, r1)
    assert abs(ic1 - 1.0) < 0.01, "正相关IC应接近1"
    
    # 测试IC计算 - 负相关
    r2 = np.array([0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01])
    ic2 = FactorAnalysis.calculate_ic(f1, r2)
    assert abs(ic2 + 1.0) < 0.01, "负相关IC应接近-1"
    
    # 测试含NaN的IC
    f3 = np.array([1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    ic3 = FactorAnalysis.calculate_ic(f3, r1)
    assert abs(ic3 - 1.0) < 0.01, "NaN应被忽略"
    
    # 测试IR计算
    rolling_ic = np.array([0.1, 0.15, 0.08, 0.12, 0.2, 0.18, 0.1, 0.15, 0.12, 0.08])
    ic_mean, ic_std, ir = FactorAnalysis.calculate_ir(pd.Series(rolling_ic))
    assert ic_mean > 0, "IC均值应为正"
    assert ir > 0, "IR应大于0"
    
    print("✓ test_09_factor_analysis 通过")


def test_10_trailing_stop():
    """测试移动止盈"""
    from src.config import StrategyConfig, run_strategy
    
    # 测试配置
    config = StrategyConfig(enable_trailing_stop=True)
    assert config.enable_trailing_stop == True
    assert config.trailing_threshold == 0.10
    assert config.trailing_stop == 0.08
    
    # 关闭移动止盈
    config2 = StrategyConfig(enable_trailing_stop=False)
    assert config2.enable_trailing_stop == False
    
    # 集成测试 - 移动止盈功能
    result = run_strategy(
        test_start='2025-05-06',
        test_end='2025-06-30',
        rebalance_days=5,
        enable_trailing_stop=True,
        trailing_threshold=0.10,
        trailing_stop=0.08,
        data_dir='../etf_data_50'
    )
    
    # 验证返回
    assert 'return' in result
    assert 'drawdown' in result
    assert result['return'] > -90
    
    print("✓ test_10_trailing_stop 通过")


# ==================== 主入口 ====================

def run_unit_tests():
    """运行单元测试"""
    print("="*50)
    print("单元测试")
    print("="*50)
    
    tests = [
        test_01_config,
        test_02_data_loader,
        test_03_indicator,
        test_04_selector,
        test_05_market_filter,
        test_06_trade_executor,
        test_07_metrics,
        test_08_integration,
        test_09_factor_analysis,
        test_10_trailing_stop,
    ]
    
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"✗ {t.__name__} 失败: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print()
    if failed == 0:
        print("="*50)
        print("✓ 所有单元测试通过!")
        print("="*50)
    else:
        print("="*50)
        print(f"✗ {failed} 个测试失败")
        print("="*50)
    
    return failed == 0


if __name__ == '__main__':
    success = run_unit_tests()
    sys.exit(0 if success else 1)