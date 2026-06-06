#!/usr/bin/env python3
"""M10 Ulcer 指标（US-026 批 3 第 6 个，动量类）— 批 3 最后 1 个"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_ulcer(df, n=14):
    """M10 Ulcer Index = 100 * sqrt(mean(dd^2)) where dd = (close - max_close_n) / max_close_n * 100"""
    roll_max = df['close'].rolling(n).max()
    dd = (df['close'] - roll_max) / roll_max * 100
    return 100 * np.sqrt((dd ** 2).rolling(n).mean())


def compute_ulcer_signal(df, n=14):
    """Ulcer 信号 = -Ulcer（取负使越低越好 → 越高代表跌得少）"""
    return -compute_ulcer(df, n)


def compute_ic(factor, future_return):
    valid = pd.concat([factor, future_return], axis=1).dropna()
    return valid.corr().iloc[0, 1] if len(valid) >= 30 else np.nan


def main():
    print("=" * 70)
    print("M10 Ulcer 指标（US-026 批 3 第 6 个）— 批 3 最后 1 个")
    print("=" * 70)
    loader = DataLoader()
    start_date = '2021-06-06'
    end_date = '2026-06-05'

    all_ic = []
    for code in CORE_ETF_POOL_15:
        try:
            all_data = loader.load(codes=[code])
            df = all_data.get(code)
            if df is None or df.empty:
                continue
            if 'date' in df.columns:
                df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
            df['m10_ulcer_signal'] = compute_ulcer_signal(df)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
            ic = compute_ic(df['m10_ulcer_signal'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic})
                print(f"  ✅ {code}: IC = {ic:.4f}")
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not all_ic:
        return
    ic_df = pd.DataFrame(all_ic)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n📊 M10 Ulcer IC：均值={ic_mean:.4f} > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/M10_ic_report.json", 'w') as f:
        json.dump({
            'factor': 'M10_ulcer_signal',
            'ic_mean': ic_mean,
            'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
            'details': [{'code': r['code'], 'ic': float(r['ic'])} for r in all_ic],
        }, f, ensure_ascii=False, indent=2)

    print("\n## M10 任务结果（批 3 完成）")
    print(f"- IC 均值: {ic_mean:.4f} | > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")
    print(f"- 下一步: 自动进入批 4（波动类 W1-W6）")


if __name__ == "__main__":
    main()
