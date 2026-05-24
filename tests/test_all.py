#!/usr/bin/env python3
"""测试用例入口"""
import sys
from pathlib import Path

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_trade_executor():
    """测试交易执行器"""
    from src.config import StrategyConfig
    from src.trade import TradeExecutor
    
    config = StrategyConfig(rebalance_days=5)
    executor = TradeExecutor(config)
    
    # 测试初始化
    assert executor.equity == 1.0
    assert len(executor.holdings) == 0
    assert executor.cooldown_days == 0
    
    # 测试重置
    executor.equity = 0.5
    executor.reset()
    assert executor.equity == 1.0
    
    print("✓ TradeExecutor 测试通过")


def test_metrics():
    """测试指标计算"""
    from src.metrics import calculate_metrics
    
    # 简单场景
    metrics = calculate_metrics(
        equity=1.5,
        equity_history=[1.0, 1.1, 1.2, 1.5],
        trades=[],
        all_dates=['2025-01-01', '2025-01-02', '2025-01-03', '2025-01-04'],
        holding_dates={'2025-01-02', '2025-01-03'}
    )
    
    assert metrics['return'] == 50.0  # 50%收益
    assert metrics['trade_days_ratio'] == 50.0  # 50%持仓
    
    print("✓ 指标计算 测试通过")


def test_selector():
    """测试选股器"""
    from src.config import StrategyConfig
    from src.selector import Selector
    
    config = StrategyConfig()
    selector = Selector()
    
    # 验证排除码
    assert '159825' in config.exclude_codes
    assert '513360' in config.exclude_codes
    
    print("✓ 选股器 测试通过")


def test_market_filter():
    """测试市场过滤"""
    from src.market_filter import MarketFilter
    import pandas as pd
    
    # 创建测试数据
    df = pd.DataFrame({
        'date': ['2025-01-01', '2025-01-02', '2025-01-03'],
        'close': [100, 110, 105],
        'volume': [1000, 1000, 1000]
    })
    
    mf = MarketFilter(df, ma=2)
    
    # 第一天ma2还没形成
    assert mf.is_bullish('2025-01-01') == True
    
    # 第二天价格110 > ma105
    assert mf.is_bullish('2025-01-02') == True
    
    # 第三天价格105 < ma108.33(按ma=2计算: (110+105)/2)
    assert mf.is_bullish('2025-01-03') == False
    
    print("✓ 市场过滤 测试通过")


def test_backtest_integration():
    """集成测试: 完整回测流程"""
    from src.config import run_strategy
    
    # 使用最小数据快速测试
    try:
        result = run_strategy(
            test_start='2025-05-06',
            test_end='2025-06-30',
            rebalance_days=5,
            data_dir='../etf_data_50'
        )
        
        # 验证返回值
        assert 'return' in result
        assert 'drawdown' in result
        assert 'winrate' in result
        assert 'trades' in result
        
        # 验证基本合理性
        assert result['return'] > -100  # 不会亏光
        assert result['drawdown'] <= 0  # 回撤是负数
        assert 0 <= result['winrate'] <= 100  # 胜率0-100%
        
        print(f"✓ 集成测试通过: 收益{result['return']:+.1f}%, 回撤{result['drawdown']:.1f}%")
        
    except Exception as e:
        print(f"✗ 集成测试失败: {e}")
        raise


def run_all_tests():
    """运行所有测试"""
    print("="*50)
    print("运行测试用例")
    print("="*50)
    
    try:
        test_trade_executor()
        test_metrics()
        test_selector()
        test_market_filter()
        test_backtest_integration()
        
        print("\n" + "="*50)
        print("✓ 所有测试通过!")
        print("="*50)
        return True
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)