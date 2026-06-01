#!/usr/bin/env python3
"""
v9 V7-001: 5 折 WalkForward 严格验证（修复版）

根因修复：
- 原始 bug：signal_func 用 df_ind 全量 reindex → look-ahead bias
- 修复：每折 test_df 上重新计算指标 → 无 future leak

SOP-03 Phase 4: 验证测试
"""
import json
import sys
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator
from scripts.validators.walk_forward_5fold import WalkForward5Fold

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ETF_POOL = [
    '510300', '515650', '515070', '512400', '512480', '588000', '520900',
    '512880', '512170', '512660', '512200', '512800', '512980',
    '515050', '515790',
]

# 从 v1_v1_single_factor 导入（不在 v9_v4_v8_combined 里重定义）
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.experiment.v9_v1_single_factor import FACTOR_SIGNAL_FUNCS

OUTPUT_DIR = Path(__file__).parent.parent.parent / 'data' / 'experiments_v9_recompute'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_signal(df, factor_name):
    func = FACTOR_SIGNAL_FUNCS[factor_name]
    signal = func(df)
    if isinstance(signal, pd.Series):
        return signal.fillna(False).astype(bool)
    return signal


def compute_result_clean(df, signal, transaction_cost=0.002):
    """干净的 positions 计算（signal → shift → position）"""
    positions = signal.shift(1).fillna(False).astype(float)
    returns = df['close'].pct_change().fillna(0)
    strategy_returns = returns * positions
    n_trades = int(signal.sum())
    total_cost = n_trades * transaction_cost
    total_return = float(strategy_returns.sum() - total_cost)
    sharpe = float(strategy_returns.mean() / max(strategy_returns.std(), 1e-9) * np.sqrt(252)) if strategy_returns.std() > 0 else 0.0
    return {
        'total_return': total_return,
        'sharpe': sharpe,
        'n_trades': n_trades,
    }


def evaluate_fold(total_return, sharpe, min_ret=-1.0, min_sharpe=0.3):
    """评估单折是否通过"""
    if total_return < min_ret:
        return False, f"ret={total_return:.3f}<{min_ret}"
    if sharpe < min_sharpe:
        return False, f"sharpe={sharpe:.2f}<{min_sharpe}"
    return True, "OK"


def run_wf_fixed(df, factor_name):
    """修复版 5 折 WF：在 fold 数据上重算指标"""
    calc = IndicatorCalculator()
    wf = WalkForward5Fold(config={'n_folds': 5, 'train_years': 1.4, 'test_years': 0.6})
    folds = wf._split_folds(df)
    fold_results = []

    for fold in folds:
        train_df = fold['train_df']
        test_df = fold['test_df']

        try:
            # ✅ 修复：每折在 fold 数据上重算指标
            train_ind = calc.calculate_all(train_df)
            test_ind = calc.calculate_all(test_df)
            signal_train = get_signal(train_ind, factor_name).reindex(train_df.index, fill_value=False)
            signal_test = get_signal(test_ind, factor_name).reindex(test_df.index, fill_value=False)
        except Exception as e:
            fold_results.append({
                'fold_idx': fold['fold_idx'],
                'test_start': fold['test_start'],
                'test_end': fold['test_end'],
                'error': str(e)[:80],
                'passed': False,
            })
            continue

        train_r = compute_result_clean(train_df, signal_train)
        test_r = compute_result_clean(test_df, signal_test)
        passed, reason = evaluate_fold(test_r['total_return'], test_r['sharpe'])

        fold_results.append({
            'fold_idx': fold['fold_idx'],
            'test_start': fold['test_start'],
            'test_end': fold['test_end'],
            'train_ret': train_r['total_return'],
            'test_ret': test_r['total_return'],
            'test_sharpe': test_r['sharpe'],
            'n_trades': test_r['n_trades'],
            'passed': passed,
            'reason': reason,
        })

    return fold_results


def main():
    logger.info("=" * 70)
    logger.info("V7-001: 5 折 WalkForward 严格验证（修复版）")
    logger.info("=" * 70)

    loader = DataLoader()
    calc = IndicatorCalculator()

    # 先测 3 只代表性 ETF
    test_etfs = ['510300', '515650', '512880']
    test_factors = ['V1_放量', 'N2_5日反转', 'M1_动量3日', 'N1_3日反转', 'T1_MACD红柱']

    # 全量扫描：15 ETF × 15 因子
    logger.info("\n全量扫描：15 ETF × 15 因子")
    all_results = []
    for code in ETF_POOL:
        df = loader.load_single(code, min_rows=400)
        if df is None:
            continue
        df = df.sort_values('date').reset_index(drop=True)
        for factor_name in FACTOR_SIGNAL_FUNCS.keys():
            fold_results = run_wf_fixed(df, factor_name)
            n_passed = sum(1 for r in fold_results if r.get('passed'))
            n_folds = len(fold_results)
            score = (n_passed / max(n_folds, 1)) * 0.5 + \
                    np.mean([r.get('test_sharpe', 0) for r in fold_results]) * 0.5

            all_results.append({
                'etf': code,
                'factor': factor_name,
                'n_passed': n_passed,
                'n_folds': n_folds,
                'pass_rate': n_passed / max(n_folds, 1),
                'avg_sharpe': float(np.mean([r.get('test_sharpe', 0) for r in fold_results])),
                'score': float(score),
                'fold_details': fold_results,
            })
            if len(all_results) % 50 == 0:
                logger.info(f"  已跑 {len(all_results)}/{15*15} 模型...")

    # 评估
    passed = [r for r in all_results if r['n_passed'] >= 2 and r['n_folds'] >= 2]
    pass_rate = len(passed) / max(len(all_results), 1)
    logger.info(f"\n通过: {len(passed)}/{len(all_results)} ({pass_rate*100:.1f}%)")

    # Top 因子
    factor_stats = {}
    for r in all_results:
        f = r['factor']
        if f not in factor_stats:
            factor_stats[f] = []
        factor_stats[f].append(r['pass_rate'])

    factor_summary = []
    for f, rates in factor_stats.items():
        factor_summary.append({
            'factor': f,
            'avg_pass_rate': float(np.mean(rates)),
            'etfs_passed': sum(1 for r in rates if r >= 0.5),
            'n_etfs': len(rates),
        })
    factor_summary.sort(key=lambda x: x['avg_pass_rate'], reverse=True)

    logger.info(f"\nTop 因子（5 折 WF 通过率）:")
    for f in factor_summary:
        bar = "█" * int(f['avg_pass_rate'] * 10)
        logger.info(f"  {f['factor']:20s}: {f['avg_pass_rate']*100:5.1f}% ({f['etfs_passed']}/{f['n_etfs']}) {bar}")

    # Top 组合
    all_results.sort(key=lambda x: x['score'], reverse=True)
    logger.info(f"\nTop 10 组合（score 排序）:")
    for r in all_results[:10]:
        logger.info(f"  {r['etf']:8s} × {r['factor']:20s}: "
                   f"pass={r['n_passed']}/{r['n_folds']}, sharpe={r['avg_sharpe']:.2f}, score={r['score']:.3f}")

    # 输出
    output = {
        'mission': 'V7-001',
        'step': 'SOP-01 Step 6.3 (修复版)',
        'timestamp': datetime.now().isoformat(),
        'summary': {
            'total_models': len(all_results),
            'passed_models': len(passed),
            'pass_rate': pass_rate,
            'config': '5 折 WF, min_sharpe=0.3, min_ret=-1.0, fold 内重算指标',
        },
        'factor_summary': factor_summary,
        'top_combos': all_results[:20],
        'detail': all_results,
    }

    json_path = OUTPUT_DIR / 'v7_wf_fixed.json'
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    logger.info(f"JSON 报告: {json_path}")

    # Markdown
    md = [
        "# v7 5 折 WF 严格验证（修复版）",
        "",
        f"**修复**: signal_func 在 fold 数据上重算指标（无 look-ahead bias）",
        f"**总模型**: {len(all_results)}",
        f"**通过**: {len(passed)} ({pass_rate*100:.1f}%)",
        "",
        "## Top 因子（5 折 WF 通过率）",
        "",
        "| 因子 | 平均通过率 | 通过 ETF | 总 ETF |",
        "|------|-----------|---------|-------|",
    ]
    for f in factor_summary:
        md.append(f"| {f['factor']} | {f['avg_pass_rate']*100:.1f}% | {f['etfs_passed']} | {f['n_etfs']} |")

    md.extend(["", "## Top 10 组合", "", "| ETF | 因子 | 通过 | Sharpe | Score |",
              "|------|------|-----|-------|-------|"])
    for r in all_results[:10]:
        md.append(f"| {r['etf']} | {r['factor']} | {r['n_passed']}/{r['n_folds']} | {r['avg_sharpe']:.3f} | {r['score']:.3f} |")

    if pass_rate < 0.05:
        md.append("\n⚠️ **通过率 < 5%！触发 IS-002 反思机制**")
    else:
        md.append(f"\n✅ 通过率 {pass_rate*100:.1f}% >= 5%")

    md_path = OUTPUT_DIR / 'v7_wf_fixed.md'
    md_path.write_text('\n'.join(md))
    logger.info(f"MD 报告: {md_path}")

    return 0 if pass_rate >= 0.05 else 2


if __name__ == '__main__':
    sys.exit(main())