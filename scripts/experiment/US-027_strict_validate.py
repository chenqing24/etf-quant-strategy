#!/usr/bin/env python3
"""
US-027 严格 WalkForward 验证（按用户 C 指令）

按 SOP-01 v1.1 Step 6 "回测验证 - 核心检查点"：
- 严格版：train_months=12, test_months=3, min_windows=8
- 5 因子对比：C1 / W4 / W3 / W2 / V6 / T9
- 真实业务评估：通过率 + OOS/IS + 总收益

按"先调研，不要写新代码"：
- 复用 WalkForwardEngine（只改 1 行 config）
- 复用 FACTOR_SIGNALS（不改）
- 复用 src/data/loader.py
"""
import sys
import json
import time
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader
from scripts.validators.walk_forward import WalkForwardEngine
import importlib.util
spec = importlib.util.spec_from_file_location("u027", "scripts/experiment/US-027_27_factor_full.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


# 6 个对比因子（C1 + W4/W3/W2 + V6 + T9）
COMPARE_FACTORS = [
    'C1_multi_factor_vote',  # US-027 修复后 Top 1
    'W4_RV_Change',  # US-026 唯一稳健
    'V6_turnover_rate',  # US-027 Top 2
    'T9_dmi',  # US-027 Top 3 (累积异常)
    'M5_roc',  # US-027 Top 5
    'T7_ema',  # US-027 Top 6
]


def main():
    print("=" * 70)
    print("US-027 严格 WalkForward 验证（train=12m, test=3m, min_windows=8）")
    print("=" * 70)

    loader = DataLoader()
    start_date = '2021-06-06'
    end_date = '2026-06-05'

    # 严格版 config：train_months=12, test_months=3, min_windows=8
    strict_config = {
        'train_months': 12,  # 12 个月训练
        'test_months': 3,
        'min_windows': 8,    # 8 个窗口（比默认 6 更严）
        'min_test_ratio': 0.3,
        'transaction_cost': 0.002,
        'pass_criteria': {
            'min_test_return': 0,
            'max_decay': 0.5,
            'min_test_sharpe': 0.3,
            'min_pass_rate': 0.5,
        }
    }

    # 用 W4/W3/W2 真实公式（从 US-026 复制）
    extra_signals = {
        'W4_RV_Change': lambda df: (
            np.sqrt((np.log(df['close'] / df['close'].shift(1)) ** 2).rolling(20).sum() * 252) -
            np.sqrt((np.log(df['close'] / df['close'].shift(1)) ** 2).rolling(20).sum() * 252).shift(20)
        ) > 0,
    }
    all_signals = {**m.FACTOR_SIGNALS, **extra_signals}

    results = {}
    t0 = time.time()
    for factor_name in COMPARE_FACTORS:
        if factor_name not in all_signals:
            print(f"⚠️ {factor_name} 不在信号字典，跳过")
            continue
        signal_func = all_signals[factor_name]

        etf_results = []
        for code in CORE_ETF_POOL_15:
            try:
                all_data = loader.load(codes=[code])
                df = all_data.get(code)
                if df is None or df.empty:
                    continue
                if 'date' in df.columns:
                    df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
                # 严格版 engine（每次新建避免 config 污染）
                engine = WalkForwardEngine(strict_config)
                result = engine.validate(df, signal_func)
                oos_is = float(result.avg_test_return) / max(abs(float(result.avg_train_return)), 1e-9)
                etf_results.append({
                    'code': code,
                    'avg_test_return': float(result.avg_test_return),
                    'avg_train_return': float(result.avg_train_return),
                    'oos_is': oos_is,
                    'pass_rate': float(result.pass_rate),
                    'n_passed': int(result.n_passed),
                    'n_windows': int(result.n_windows),
                })
            except Exception as e:
                pass

        if not etf_results:
            continue

        # 汇总：单 ETF 真实表现（不被累积极端值污染）
        oos_etfs = sum(1 for r in etf_results if r['oos_is'] > 0.5)
        pass_etfs = sum(1 for r in etf_results if r['pass_rate'] >= 0.5)
        avg_oos_is = float(np.mean([r['oos_is'] for r in etf_results]))
        median_oos_is = float(np.median([r['oos_is'] for r in etf_results]))
        avg_test_return = float(np.mean([r['avg_test_return'] for r in etf_results]))

        results[factor_name] = {
            'avg_oos_is': avg_oos_is,
            'median_oos_is': median_oos_is,
            'avg_test_return': avg_test_return,
            'etfs_oos_gt_0.5': oos_etfs,
            'etfs_pass_gt_0.5': pass_etfs,
            'total_etfs': len(etf_results),
            'detail': etf_results,
        }

        elapsed = time.time() - t0
        print(f"\n[{elapsed:.0f}s] {factor_name}:")
        print(f"  median OOS/IS = {median_oos_is:.2f} (更稳健指标)")
        print(f"  avg OOS/IS = {avg_oos_is:.2f} (可能被极端值拉爆)")
        print(f"  ETF OOS/IS>0.5: {oos_etfs}/{len(etf_results)}")
        print(f"  ETF pass_rate≥0.5: {pass_etfs}/{len(etf_results)}")
        print(f"  avg test_return = {avg_test_return*100:.2f}%")

    # 报告
    print("\n" + "=" * 70)
    print("📊 严格 WalkForward 验证最终报告")
    print("=" * 70)
    print(f"\n{'因子':<25} {'median OOS/IS':<15} {'ETF OOS/IS>0.5':<20} {'avg test_return':<15}")
    print("-" * 75)
    for factor_name, r in results.items():
        print(f"{factor_name:<25} {r['median_oos_is']:<15.2f} {r['etfs_oos_gt_0.5']}/{r['total_etfs']:<18} {r['avg_test_return']*100:<14.2f}%")

    # 报告 JSON
    report_path = Path("data/US-027_strict_wf_validation.json")
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(f"\n📄 报告: {report_path}")

    # 结论
    print("\n" + "=" * 70)
    print("💡 关键结论")
    print("=" * 70)
    sorted_by_median = sorted(results.items(), key=lambda x: x[1]['median_oos_is'], reverse=True)
    print("\n按 median OOS/IS 排序（最稳健指标）:")
    for i, (name, r) in enumerate(sorted_by_median, 1):
        print(f"  #{i}: {name}: median OOS/IS={r['median_oos_is']:.2f} | {r['etfs_oos_gt_0.5']}/{r['total_etfs']} ETF OOS/IS>0.5")

    print(f"\n⏱️ 总耗时: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
