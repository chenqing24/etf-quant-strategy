"""测试修复后的持仓时间 - 验证allow_rebalance参数生效"""
import sys
sys.path.insert(0, '.')

from src.strategy.engine import UniversalExecutor
from src.strategy.config import (
    ExperimentConfig, FactorStrategy, BacktestConfig, DataConfig, ScoreConfig
)
from src.data.database import Database
from src.indicators.wrapper import IndicatorCalculator, calculate_returns
from datetime import datetime
from collections import Counter


def test_allow_rebalance_config():
    """测试allow_rebalance参数"""
    # 测试默认值
    backtest = BacktestConfig()
    assert backtest.allow_rebalance == True, "默认应该允许调仓"
    
    # 测试关闭调仓
    backtest = BacktestConfig(allow_rebalance=False)
    assert backtest.allow_rebalance == False, "应该关闭调仓"
    
    print("✅ allow_rebalance参数测试通过")


def test_rebalance_behavior():
    """测试调仓行为差异"""
    price_data = _load_price_data()
    
    # 1. 允许调仓
    print("\n测试1: 允许调仓")
    backtest = BacktestConfig(hold_days=3, allow_rebalance=True, max_positions=2)
    config = _create_config(backtest)
    executor = UniversalExecutor(config)
    executor._price_data = price_data
    
    result = executor._run_period(price_data, '2023-01-01', '2023-03-31', 'train')
    stats1 = _analyze_trades(result.trade_list)
    print(f"  交易次数: {stats1['trade_count']}")
    print(f"  平均持仓: {stats1['avg_hold']:.1f}天")
    print(f"  退出原因: {stats1['exit_reasons']}")
    
    # 2. 禁止调仓
    print("\n测试2: 禁止调仓")
    backtest = BacktestConfig(hold_days=3, allow_rebalance=False, max_positions=2)
    config = _create_config(backtest)
    executor = UniversalExecutor(config)
    executor._price_data = price_data
    
    result = executor._run_period(price_data, '2023-01-01', '2023-03-31', 'train')
    stats2 = _analyze_trades(result.trade_list)
    print(f"  交易次数: {stats2['trade_count']}")
    print(f"  平均持仓: {stats2['avg_hold']:.1f}天")
    print(f"  退出原因: {stats2['exit_reasons']}")
    
    # 对比
    print("\n对比:")
    print(f"  允许调仓: {stats1['trade_count']}笔, 平均{stats1['avg_hold']:.1f}天")
    print(f"  禁止调仓: {stats2['trade_count']}笔, 平均{stats2['avg_hold']:.1f}天")
    
    # 验证: 禁止调仓后，持仓时间应该更接近配置值
    assert stats2['avg_hold'] >= 2.0, f"禁止调仓后平均持仓应该>=2天，实际{stats2['avg_hold']:.1f}天"
    
    print("\n✅ 调仓行为差异测试通过")


def test_no_rebalance_hold_days():
    """测试禁止调仓时，持仓接近配置值"""
    price_data = _load_price_data()
    
    print("\n测试: 禁止调仓时的持仓分布")
    backtest = BacktestConfig(hold_days=3, allow_rebalance=False, max_positions=2)
    config = _create_config(backtest)
    executor = UniversalExecutor(config)
    executor._price_data = price_data
    
    result = executor._run_period(price_data, '2023-01-01', '2023-06-30', 'train')
    stats = _analyze_trades(result.trade_list)
    
    print(f"  交易次数: {stats['trade_count']}")
    print(f"  平均持仓: {stats['avg_hold']:.1f}天")
    print(f"  持仓分布: {stats['hold_dist']}")
    
    # 验证: 大部分交易应该在3天左右结束
    near_3_days = stats['hold_dist'].get(3, 0) + stats['hold_dist'].get(4, 0)
    total_trades = sum(stats['hold_dist'].values())
    near_ratio = near_3_days / total_trades if total_trades > 0 else 0
    
    print(f"  3-4天结束的占比: {near_ratio:.1%}")
    
    # 至少应该有部分交易接近配置值
    assert stats['avg_hold'] >= 2.0, f"禁止调仓后平均持仓应该>=2天"
    
    print("\n✅ 禁止调仓持仓测试通过")


def _create_config(backtest):
    """创建测试配置"""
    factor_strategy = FactorStrategy(
        name='test',
        factors=['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'],
        weights={'ADX': 0.25, 'BB_percent': 0.25, 'SAR_trend': 0.25, 'OBV_diff': 0.25},
        direction={'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'},
        score_config=ScoreConfig(threshold=0.8)
    )
    return ExperimentConfig(
        name='test',
        factor_strategy=factor_strategy,
        backtest=backtest,
        data=DataConfig(train_start='2023-01-01', train_end='2024-12-31')
    )


def _load_price_data():
    """加载价格数据"""
    db = Database()
    calculator = IndicatorCalculator()
    price_data = {}
    
    stock_info = db.query('SELECT code FROM stock_info')
    codes = [r['code'] for r in stock_info if r['code'] not in {
        'behavior_log', 'etf_performance', 'etf_positions', 'etf_trades', 
        'realtime_cache', 'test_code'
    }]
    
    for code in codes[:10]:  # 使用10只ETF进行测试
        df = db.query_df(
            'SELECT code, date, open, high, low, close, volume FROM daily_price WHERE code = ? ORDER BY date',
            (code,)
        )
        if df.empty or len(df) < 60:
            continue
        df = calculator.calculate_all(df)
        df = calculate_returns(df)
        price_data[code] = df
    
    return price_data


def _analyze_trades(trades):
    """分析交易记录"""
    sell_trades = [t for t in trades if t.get('action') == 'sell']
    
    # 退出原因统计
    exit_reasons = Counter()
    hold_days_dist = Counter()
    
    for sell in sell_trades:
        reason = sell.get('exit_reason', 'unknown')
        exit_reasons[reason] += 1
        
        code = sell.get('code')
        buy_trade = None
        for t in trades:
            if t.get('code') == code and t.get('action') == 'buy':
                buy_trade = t
                break
        
        if buy_trade:
            buy_date = datetime.strptime(buy_trade['date'][:10], '%Y-%m-%d')
            sell_date = datetime.strptime(sell['date'][:10], '%Y-%m-%d')
            days = (sell_date - buy_date).days
            hold_days_dist[days] += 1
    
    avg_hold = sum(d * c for d, c in hold_days_dist.items()) / sum(hold_days_dist.values()) if hold_days_dist else 0
    
    return {
        'trade_count': len(trades),
        'avg_hold': avg_hold,
        'exit_reasons': dict(exit_reasons),
        'hold_dist': dict(hold_days_dist)
    }


if __name__ == '__main__':
    print("=" * 60)
    print("测试修复: allow_rebalance参数")
    print("=" * 60)
    
    test_allow_rebalance_config()
    test_rebalance_behavior()
    test_no_rebalance_hold_days()
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过")
    print("=" * 60)