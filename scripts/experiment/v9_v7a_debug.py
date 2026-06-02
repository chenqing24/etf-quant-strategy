#!/usr/bin/env python3
"""
V7-A Debug: 诊断 signal_func bug
SOP-03 Phase 2: 根因分析

问题：v7_5fold_walk_forward 的 signal_func 用的是全量 df 的指标数据（df_ind），
而不是 fold 自己的数据。导致 test fold 信号包含未来信息。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator
from scripts.validators.walk_forward_5fold import WalkForward5Fold
import pandas as pd

def signal_func_buggy(df):
    """❌ 有 bug 的 signal_func（v9_v4_v8_combined.py 中的实现）"""
    # 问题：df_ind 是全量数据预计算的指标，这里只是 reindex
    # test fold 看到的信号是用全量数据算的，不是只用 fold 数据
    return multi_factor_signal(df_ind, best_combo, mode='all').reindex(df.index, fill_value=False)

def signal_func_fixed(df, combo):
    """✅ 正确的 signal_func：在 fold 数据上重算指标"""
    # 每折重新计算指标，避免 future look-ahead bias
    df_calc = calc.calculate_all(df)
    signal = multi_factor_signal(df_calc, combo, mode='all')
    return signal.reindex(df.index, fill_value=False)

def multi_factor_signal(df, factors, mode='all'):
    """多因子 AND/OR 信号"""
    from src.indicators.n6_reversal import signal_n1_3d_reversal
    from scripts.experiment.v9_v1_single_factor import get_signal as _get_signal

    signals = [_get_signal(df, f) for f in factors]
    if mode == 'all':
        return pd.concat(signals, axis=1).all(axis=1)
    return pd.concat(signals, axis=1).any(axis=1)

def get_signal(df, factor_name):
    from scripts.experiment.v9_v1_single_factor import FACTOR_SIGNAL_FUNCS
    func = FACTOR_SIGNAL_FUNCS[factor_name]
    signal = func(df)
    if isinstance(signal, pd.Series):
        return signal.fillna(False).astype(bool)
    return signal

best_combo = ['V1_放量', 'T1_MACD红柱']
test_etf = '510300'

loader = DataLoader()
calc = IndicatorCalculator()

df = loader.load_single(test_etf, min_rows=400)
df = df.sort_values('date').reset_index(drop=True)
df_ind = calc.calculate_all(df)  # 全量数据预计算

print("=" * 60)
print("V7-A Debug: signal_func bug 分析")
print("=" * 60)
print(f"\nETF: {test_etf}")
print(f"数据: {df['date'].min()} ~ {df['date'].max()} ({len(df)} 行)")
print(f"\nFold 划分（WalkForward5Fold 默认配置）:")

wf = WalkForward5Fold(config={'n_folds': 5, 'train_years': 1.4, 'test_years': 0.6})
folds = wf._split_folds(df)
for fold in folds:
    print(f"  Fold {fold['fold_idx']}: test={fold['test_start']}~{fold['test_end']} "
          f"(train={len(fold['train_df'])}d, test={len(fold['test_df'])}d)")

print("\n" + "=" * 60)
print("Bug 分析：信号对齐问题")
print("=" * 60)

# Fold 0 的 test_df
fold0 = folds[0]
test_df0 = fold0['test_df']
test_start = fold0['test_start']
test_end = fold0['test_end']

print(f"\nFold 0 test: {test_start} ~ {test_end} ({len(test_df0)} 行)")

# 全量信号
signal_full = multi_factor_signal(df_ind, best_combo, mode='all')
print(f"全量信号触发: {signal_full.sum()} 次 ({signal_full.mean()*100:.1f}%)")

# test_df0 上的信号（全量 reindex）
signal_test_reindexed = signal_full.reindex(test_df0.index, fill_value=False)
print(f"test_df0 信号（从全量 reindex）: {signal_test_reindexed.sum()} 次")

# 正确做法：在 test_df0 上重算指标
signal_test_fixed = signal_func_fixed(test_df0, best_combo)
print(f"test_df0 信号（fold 内重算）: {signal_test_fixed.sum()} 次")

# 对比 test 段的 return
test_ret = test_df0['close'].pct_change().shift(-1).fillna(0)
sig_reindexed_ret = signal_test_reindexed.astype(int) * test_ret
sig_fixed_ret = signal_test_fixed.astype(int) * test_ret

print(f"\n信号加权收益对比:")
print(f"  有 bug（reindex）: 总收益={sig_reindexed_ret.sum():.4f}, Sharpe={sig_reindexed_ret.mean()/max(sig_reindexed_ret.std(), 0.001):.2f}")
print(f"  正确（重算）:     总收益={sig_fixed_ret.sum():.4f}, Sharpe={sig_fixed_ret.mean()/max(sig_fixed_ret.std(), 0.001):.2f}")

# 5 折对比
print("\n" + "=" * 60)
print("5 折对比：有 bug vs 正确")
print("=" * 60)

results = []
for fold in folds:
    test_df = fold['test_df']

    # BUG: 全量 reindex
    signal_bug = signal_full.reindex(test_df.index, fill_value=False)
    ret_bug = signal_bug.astype(int) * test_df['close'].pct_change().shift(-1).fillna(0)

    # FIXED: fold 内重算
    signal_fix = signal_func_fixed(test_df, best_combo)
    ret_fix = signal_fix.astype(int) * test_df['close'].pct_change().shift(-1).fillna(0)

    n_trades_bug = (signal_bug != 0).sum()
    n_trades_fix = (signal_fix != 0).sum()
    sharpe_bug = ret_bug.mean() / max(ret_bug.std(), 0.001) if ret_bug.std() > 0 else 0
    sharpe_fix = ret_fix.mean() / max(ret_fix.std(), 0.001) if ret_fix.std() > 0 else 0
    test_ret_bug = ret_bug.sum()
    test_ret_fix = ret_fix.sum()

    print(f"\nFold {fold['fold_idx']}: test={fold['test_start']}~{fold['test_end']}")
    print(f"  BUG  : trades={n_trades_bug}, ret={test_ret_bug:.4f}, sharpe={sharpe_bug:.3f}")
    print(f"  FIXED: trades={n_trades_fix}, ret={test_ret_fix:.4f}, sharpe={sharpe_fix:.3f}")
    results.append({
        'fold': fold['fold_idx'],
        'bug_sharpe': sharpe_bug,
        'fix_sharpe': sharpe_fix,
        'bug_ret': test_ret_bug,
        'fix_ret': test_ret_fix,
    })

print("\n" + "=" * 60)
print("结论")
print("=" * 60)
bug_passed = sum(1 for r in results if r['bug_sharpe'] > 0.3)
fix_passed = sum(1 for r in results if r['fix_sharpe'] > 0.3)
print(f"\n有 bug  : {bug_passed}/5 通过")
print(f"正确   : {fix_passed}/5 通过")
if fix_passed > bug_passed:
    print("✅ 修复有效！")
elif fix_passed < bug_passed:
    print("⚠️ 修复后反而变差，可能是数据量问题")
else:
    print("⚠️ 两者相同，bug 可能不是根本原因")