"""滚动窗口验证脚本"""
import sys
sys.path.insert(0, '.')

from src.strategy.engine import TradingEngine
from src.strategy.config import FactorConfig, ExperimentConfig
from src.data.database import FactorDatabase
import numpy as np

# Exp48配置 (均衡权重，最稳健)
config = ExperimentConfig(
    factors=[
        FactorConfig(name='ADX', weight=0.25, direction='long'),
        FactorConfig(name='BB_percent', weight=0.25, direction='long'),
        FactorConfig(name='SAR_trend', weight=0.25, direction='long'),
        FactorConfig(name='OBV_diff', weight=0.25, direction='short'),
    ],
    stop_loss=-0.05,
    stop_profit=0.10,
    threshold=0.8,
    hold_days=3
)

db = FactorDatabase()

# 滚动窗口验证
windows = [
    ('W1: 23H1→23H2', '2023-01-01', '2023-06-30', '2023-07-01', '2023-12-31'),
    ('W2: 23H2→24H1', '2023-07-01', '2023-12-31', '2024-01-01', '2024-06-30'),
    ('W3: 24H1→24H2', '2024-01-01', '2024-06-30', '2024-07-01', '2024-12-31'),
    ('W4: 24H2→25H1', '2024-07-01', '2024-12-31', '2025-01-01', '2025-06-30'),
]

print('=' * 80)
print('滚动窗口交叉验证 (Walk-Forward Validation)')
print('=' * 80)
print('模型: Exp48 (均衡权重+阈值0.8+持仓3天)')
print('-' * 80)

results = []
for name, train_start, train_end, test_start, test_end in windows:
    try:
        engine = TradingEngine(config, db)
        
        # 训练期
        train_trades = engine.run(train_start, train_end)
        train_metrics = engine.calculate_metrics(train_trades)
        
        # 测试期
        test_trades = engine.run(test_start, test_end)
        test_metrics = engine.calculate_metrics(test_trades)
        
        print(f'\n{name}')
        print(f'  Train({train_start[:7]}~{train_end[:7]}): {train_metrics.total_return:.1%} 夏普={train_metrics.sharpe_ratio:.2f} 交易={train_metrics.trade_count}')
        print(f'  Test({test_start[:7]}~{test_end[:7]}):  {test_metrics.total_return:.1%} 夏普={test_metrics.sharpe_ratio:.2f} 交易={test_metrics.trade_count}')
        
        results.append({
            'name': name,
            'train_ret': train_metrics.total_return,
            'train_sharpe': train_metrics.sharpe_ratio,
            'test_ret': test_metrics.total_return,
            'test_sharpe': test_metrics.sharpe_ratio,
            'train_trades': train_metrics.trade_count,
            'test_trades': test_metrics.trade_count,
        })
    except Exception as e:
        print(f'\n{name}: 错误 - {e}')

if len(results) >= 3:
    print('\n' + '=' * 80)
    print('过拟合统计检验')
    print('=' * 80)
    
    train_rets = [r['train_ret'] for r in results]
    test_rets = [r['test_ret'] for r in results]
    train_sharpes = [r['train_sharpe'] for r in results]
    test_sharpes = [r['test_sharpe'] for r in results]
    
    print(f'训练期收益: mean={np.mean(train_rets):.1%} std={np.std(train_rets):.1%} CV={np.std(train_rets)/np.mean(train_rets):.2f}')
    print(f'测试期收益: mean={np.mean(test_rets):.1%} std={np.std(test_rets):.1%} CV={np.std(test_rets)/np.mean(test_rets):.2f}')
    print(f'训练期夏普: mean={np.mean(train_sharpes):.2f} std={np.std(train_sharpes):.2f}')
    print(f'测试期夏普: mean={np.mean(test_sharpes):.2f} std={np.std(test_sharpes):.2f}')
    
    # 收益比稳定性
    ratios = [r['test_ret']/r['train_ret'] if r['train_ret'] > 0 else 0 for r in results]
    print(f'收益比: {[f\"{x:.2f}\" for x in ratios]} mean={np.mean(ratios):.2f} std={np.std(ratios):.2f}')
    
    print('\n结论:')
    if np.std(ratios) < 0.5 and np.mean(ratios) < 3:
        print('  ✅ 收益比稳定，滚动验证通过')
    else:
        print('  ⚠️ 收益比波动较大，需进一步分析')