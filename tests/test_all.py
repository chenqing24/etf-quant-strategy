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


def test_11_cross_validation():
    """测试交叉验证"""
    from src.cross_validation import CrossValidator, ValidationWindow
    
    validator = CrossValidator(data_dir='../etf_data_50')
    
    # 短窗口测试
    windows = [
        ValidationWindow(
            train_start='2024-01-01',
            train_end='2024-12-31',
            test_start='2025-05-01',
            test_end='2025-06-30',
            name='测试窗口'
        ),
    ]
    
    results = validator.run_cross_validation(windows=windows, rebalance_days=5)
    
    assert len(results) == 1
    assert 'return' in results[0]
    assert results[0]['return'] > -90
    
    # 测试稳定性分析
    stability = validator.analyze_stability()
    assert 'return_mean' in stability
    
    print("✓ test_11_cross_validation 通过")


def test_12_cache():
    """测试缓存机制"""
    from src.cache import CacheManager
    
    cache = CacheManager('.cache/test_unit')
    
    # 测试写入/读取
    test_data = {'key': 'value', 'num': 123}
    cache.set('test', test_data, 'param1')
    retrieved = cache.get('test', 'param1')
    assert retrieved == test_data, "缓存读取失败"
    
    # 测试不存在
    missing = cache.get('nonexistent')
    assert missing is None, "不应返回不存在的数据"
    
    # 统计
    stats = cache.get_stats()
    assert stats['cache_count'] >= 1
    
    # 清理
    cache.clear()
    
    print("✓ test_12_cache 通过")


def test_13_trading_cost():
    """测试交易成本计算"""
    from src.trading_cost import calculate_slippage, apply_trading_cost
    
    # 基础滑点
    slip1 = calculate_slippage(price=1.0, volume=10000, side='buy')
    assert slip1 > 0, "滑点应为正"
    
    # 大单成本更高
    slip2 = calculate_slippage(price=1.0, volume=200000, side='buy')
    assert slip2 > slip1, "大单滑点应更高"
    
    # 卖出滑点更高
    slip3 = calculate_slippage(price=1.0, volume=10000, side='sell')
    assert slip3 > slip1, "卖出滑点应更高"
    
    # 应用成本后的价格
    price = apply_trading_cost(price=1.0, volume=10000, side='buy', fee_rate=0.0003)
    assert price > 1.0, "买入价格应更高"
    
    print("✓ test_13_trading_cost 通过")


def test_14_sensitivity():
    """测试参数敏感性分析"""
    from src.sensitivity_analysis import SensitivityAnalyzer
    
    analyzer = SensitivityAnalyzer(data_dir='../etf_data_50')
    
    # 简单参数网格
    param_grid = {'rebalance_days': [5, 10]}
    
    df = analyzer.grid_search(
        param_grid,
        test_start='2025-05-06',
        test_end='2025-06-30',
    )
    
    # 应该返回结果
    assert len(df) == 2
    assert 'sharpe' in df.columns
    
    # 稳健参数
    robust = analyzer.find_robust_params()
    assert isinstance(robust, dict)
    
    print("✓ test_14_sensitivity 通过")


def test_15_notifier():
    """测试信号推送"""
    from src.notifier import SignalNotifier, TradeSignal
    
    notifier = SignalNotifier(enable_console=True)
    
    # 测试买入信号
    signal = TradeSignal(
        date='2025-05-24',
        code='510300',
        action='buy',
        price=3.456,
        reason='MA120+MA60',
        score=8
    )
    notifier.send_signal(signal)
    
    # 测试卖出信号
    signal2 = TradeSignal(
        date='2025-05-24',
        code='510500',
        action='sell',
        price=5.123,
        reason='止盈',
        pnl=0.15
    )
    notifier.send_signal(signal2)
    
    # 验证信号记录
    signals = notifier.get_signals()
    assert len(signals) == 2
    
    # 测试每日总结
    notifier.send_daily_summary({
        'return': 51.9,
        'drawdown': -22.6,
        'sharpe': 2.07,
        'winrate': 61.1,
        'trades': 37,
    })
    
    print("✓ test_15_notifier 通过")


def test_16_industry_filter():
    """测试行业集中度过滤"""
    from src.industry_filter import IndustryFilter
    
    filter = IndustryFilter(max_industry_pct=0.3)
    
    # 模拟候选
    candidates = {'510300', '510500', '159919', '512880', '512170', 
                  '512200', '159928', '159825', '512010', '512500'}
    
    # 行业过滤
    filtered = filter.filter_by_industry(candidates, max_per_industry=3)
    assert len(filtered) <= len(candidates)
    
    # 行业占比计算
    weights = {code: 1.0/len(filtered) for code in filtered}
    ratio = filter.calculate_industry_ratio(weights)
    assert len(ratio) > 0
    
    # 打印行业配置
    filter.print_industry_allocation(weights)
    
    print("✓ test_16_industry_filter 通过")


def test_17_sensitivity_chart():
    """测试敏感性图表"""
    try:
        import matplotlib
        from src.sensitivity_chart import SensitivityChart
        import pandas as pd
        import numpy as np
        
        # 模拟数据
        np.random.seed(42)
        results = pd.DataFrame({
            'rebalance_days': [5, 10, 15, 20, 5, 10, 15, 20],
            'stop_loss': [-0.08, -0.08, -0.08, -0.08, -0.10, -0.10, -0.10, -0.10],
            'return': np.random.uniform(-10, 30, 8),
            'sharpe': np.random.uniform(-0.5, 2.0, 8),
        })
        
        chart = SensitivityChart()
        chart.plot_single_param(results, 'rebalance_days', 'sharpe')
        chart.plot_heatmap(results, 'rebalance_days', 'stop_loss', 'return')
        
        print("✓ test_17_sensitivity_chart 通过 (matplotlib)")
    except ImportError:
        print("⚠ matplotlib未安装，跳过图表测试")
        print("✓ test_17_sensitivity_chart 通过 (跳过)")


def test_18_slippage_config():
    """测试滑点配置"""
    from src.config import StrategyConfig
    
    config = StrategyConfig(enable_slippage=True, slippage_rate=0.002)
    assert config.enable_slippage == True
    assert config.slippage_rate == 0.002
    
    # 测试默认值
    config2 = StrategyConfig()
    assert config2.enable_slippage == False
    
    print("✓ test_18_slippage_config 通过")


def test_19_report_generator():
    """测试报告生成器"""
    from src.report_generator import ETFReportGenerator
    
    generator = ETFReportGenerator(data_dir='../etf_data_50')
    
    # 加载数据
    latest = generator.load_data()
    assert latest is not None
    assert len(latest) == 10  # YYYY-MM-DD
    
    # 分析市场
    market = generator.analyze_market()
    assert 'total_qualified' in market
    assert market['total_qualified'] > 0
    
    # 验证策略
    results = generator.validate_strategy()
    assert len(results) > 0
    assert 'return' in results[0]
    
    # 生成报告
    report = generator.generate_report(capital=20000)
    assert 'ETF量化投资决策报告' in report
    assert '基本信息' in report
    assert '市场环境分析' in report
    assert '策略历史表现' in report
    assert '当前推荐标的' in report
    assert '资金配置方案' in report
    assert '风险控制' in report
    assert '结论' in report
    
    print("✓ test_19_report_generator 通过")


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
        test_11_cross_validation,
        test_12_cache,
        test_13_trading_cost,
        test_14_sensitivity,
        test_15_notifier,
        test_16_industry_filter,
        test_17_sensitivity_chart,
        test_18_slippage_config,
        test_19_report_generator,
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