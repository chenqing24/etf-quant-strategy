#!/usr/bin/env python3
"""
V7-A Debug v2: 深度诊断

按 SOP-03 Phase 2 根因分析规范：

根因 A: look-ahead bias（信号用全量指标 reindex，非 fold 内重算）
根因 B: positions offset bug（signal[day]=True → 第一天 position 漏掉）
根因 C: 因子本身无泛化能力（单因子 IC 样本内虚高）
根因 D: 5 折 WF 配置太严格

测试策略：
1. 干净的单因子（MA5>MA20）+ 干净 positions 计算 → 看基准
2. V1_放量 + T1_MACD红柱 原始实现 → 对比 v7 结果
3. 逐折详细分析每个因子
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator
from scripts.validators.walk_forward_5fold import WalkForward5Fold
import pandas as pd
import numpy as np

ETF = '510300'
FACTORS_V1 = ['T1_MACD红柱', 'V1_放量', 'M1_动量3日', 'N1_3日反转', 'N2_5日反转']

# ======== 干净实现 =========

def simple_ma_signal(df):
    """MA5 > MA20 - 最简单的趋势信号"""
    ma5 = df['close'].rolling(5, min_periods=1).mean()
    ma20 = df['close'].rolling(20, min_periods=1).mean()
    return (ma5 > ma20).fillna(False)

def compute_result_clean(df, signal):
    """干净的 positions 计算（无 offset bug）"""
    positions = signal.shift(1).fillna(False)  # 信号后第二天开始持仓（正确）
    returns = df['close'].pct_change().fillna(0)
    strategy_returns = returns * positions.astype(float)
    n_trades = signal.sum()
    total_cost = n_trades * 0.002
    total_return = strategy_returns.sum() - total_cost
    sharpe = strategy_returns.mean() / max(strategy_returns.std(), 1e-9) * np.sqrt(252) if strategy_returns.std() > 0 else 0
    return {
        'total_return': float(total_return),
        'sharpe': float(sharpe),
        'n_trades': int(n_trades),
    }

def evaluate_clean(total_return, sharpe, min_ret=-1.0, min_sharpe=0.3):
    """评估单折"""
    if total_return < min_ret:
        return False, f"ret={total_return:.3f}<{min_ret}"
    if sharpe < min_sharpe:
        return False, f"sharpe={sharpe:.2f}<{min_sharpe}"
    return True, "OK"

def run_wf_clean(df, signal_func, name):
    """5 折 WF 干净实现"""
    wf = WalkForward5Fold(config={'n_folds': 5, 'train_years': 1.4, 'test_years': 0.6})
    folds = wf._split_folds(df)
    results = []
    for fold in folds:
        train_df = fold['train_df']
        test_df = fold['test_df']
        try:
            signal = signal_func(test_df)
        except Exception as e:
            results.append({'fold': fold['fold_idx'], 'error': str(e)})
            continue
        train_r = compute_result_clean(train_df, signal.reindex(train_df.index, fill_value=False))
        test_r = compute_result_clean(test_df, signal)
        passed, reason = evaluate_clean(test_r['total_return'], test_r['sharpe'])
        results.append({
            'fold': fold['fold_idx'],
            'test_start': fold['test_start'],
            'test_end': fold['test_end'],
            'train_ret': train_r['total_return'],
            'test_ret': test_r['total_return'],
            'test_sharpe': test_r['sharpe'],
            'n_trades': test_r['n_trades'],
            'passed': passed,
            'reason': reason,
        })
    return results

# ======== 主诊断 =========

print("=" * 70)
print("V7-A Debug v2: 深度根因分析")
print("=" * 70)

loader = DataLoader()
calc = IndicatorCalculator()
df = loader.load_single(ETF, min_rows=400)
df = df.sort_values('date').reset_index(drop=True)
print(f"\n{ETF}: {df['date'].min()} ~ {df['date'].max()} ({len(df)} 行)")

# 测试 1: 简单 MA 信号
print("\n" + "=" * 70)
print("测试 1: MA5>MA20 (简单趋势信号)")
print("=" * 70)
results_ma = run_wf_clean(df, simple_ma_signal, "MA5>MA20")
passed = sum(1 for r in results_ma if r.get('passed'))
print(f"通过: {passed}/{len(results_ma)}")
for r in results_ma:
    print(f"  Fold {r['fold']}: test={r.get('test_start','?')}~{r.get('test_end','?')} "
          f"ret={r.get('test_ret',0):.4f} sharpe={r.get('test_sharpe',0):.3f} trades={r.get('n_trades',0)} {'✅' if r.get('passed') else '❌'}")

# 测试 2: V1_放量
print("\n" + "=" * 70)
print("测试 2: V1_放量")
print("=" * 70)
def signal_v1(df):
    df_calc = calc.calculate_all(df)
    return df_calc['volume'] > df_calc['volume'].rolling(20, min_periods=1).mean() * 1.5

results_v1 = run_wf_clean(df, signal_v1, "V1_放量")
passed_v1 = sum(1 for r in results_v1 if r.get('passed'))
print(f"通过: {passed_v1}/{len(results_v1)}")
for r in results_v1:
    print(f"  Fold {r['fold']}: ret={r.get('test_ret',0):.4f} sharpe={r.get('test_sharpe',0):.3f} trades={r.get('n_trades',0)} {'✅' if r.get('passed') else '❌'}")

# 测试 3: N2_5日反转
print("\n" + "=" * 70)
print("测试 3: N2_5日反转")
print("=" * 70)
def signal_n2(df):
    df_calc = calc.calculate_all(df)
    mom5 = df_calc['close'].pct_change(5)
    return (mom5 < -0.05).fillna(False)

results_n2 = run_wf_clean(df, signal_n2, "N2_5日反转")
passed_n2 = sum(1 for r in results_n2 if r.get('passed'))
print(f"通过: {passed_n2}/{len(results_n2)}")
for r in results_n2:
    print(f"  Fold {r['fold']}: ret={r.get('test_ret',0):.4f} sharpe={r.get('test_sharpe',0):.3f} trades={r.get('n_trades',0)} {'✅' if r.get('passed') else '❌'}")

# 测试 4: AND 组合 (V1 + T1_MACD)
print("\n" + "=" * 70)
print("测试 4: V1_放量 AND T1_MACD红柱")
print("=" * 70)
def signal_and(df):
    df_calc = calc.calculate_all(df)
    v1 = df_calc['volume'] > df_calc['volume'].rolling(20, min_periods=1).mean() * 1.5
    macd = df_calc['MACD_hist'] > 0
    return (v1 & macd).fillna(False)

results_and = run_wf_clean(df, signal_and, "V1+T1")
passed_and = sum(1 for r in results_and if r.get('passed'))
print(f"通过: {passed_and}/{len(results_and)}")
for r in results_and:
    print(f"  Fold {r['fold']}: ret={r.get('test_ret',0):.4f} sharpe={r.get('test_sharpe',0):.3f} trades={r.get('n_trades',0)} {'✅' if r.get('passed') else '❌'}")

# 综合结论
print("\n" + "=" * 70)
print("综合结论")
print("=" * 70)
summary = [
    ("MA5>MA20", passed, len(results_ma)),
    ("V1_放量", passed_v1, len(results_v1)),
    ("N2_5日反转", passed_n2, len(results_n2)),
    ("V1+T1 AND", passed_and, len(results_and)),
]
for name, p, t in summary:
    bar = "█" * p + "░" * (t - p)
    print(f"  {name:20s}: {p}/{t} ({p/max(t,1)*100:5.1f}%) {bar}")

# 诊断结论
best = max(summary, key=lambda x: x[1]/max(x[2],1))
print(f"\n最佳表现: {best[0]} ({best[1]}/{best[2]} = {best[1]/max(best[2],1)*100:.1f}%)")

if best[1] == 0:
    print("\n🚨 所有因子 0 通过！因子本身无泛化能力（根因 C）")
elif best[0] == "MA5>MA20":
    print("\n✅ 简单趋势信号可通过，问题在于 V1/V1+T1 的信号构造")
else:
    print("\n✅ 特定因子有泛化能力，问题在于特定组合")