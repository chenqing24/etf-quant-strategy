#!/usr/bin/env python3
"""B4 跳空缺口（US-026 批 5 第 6 个，突破类）— 批 5 最后 1 个"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_gap_up(df, threshold=0.01):
    """B4 跳空高开 = (open - prev_close) / prev_close > threshold"""
    gap = (df['open'] - df['close'].shift(1)) / df['close'].shift(1)
    return (gap > threshold).astype(float)


def compute_gap_signal(df, threshold=0.01):
    """B4 跳空信号 = 跳空高开为 1（看多），跳空低开 -1"""
    gap = (df['open'] - df['close'].shift(1)) / df['close'].shift(1)
    signal = pd.Series(0, index=df.index, dtype=float)
    signal[gap > threshold] = 1
    signal[gap < -threshold] = -1
    return signal


def compute_ic(factor, future_return):
    valid = pd.concat([factor, future_return], axis=1).dropna()
    if len(valid) < 30:
        return np.nan
    x, y = valid.iloc[:, 0].values, valid.iloc[:, 1].values
    if np.std(x) == 0 or np.std(y) == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def main():
    print("=" * 70)
    print("B4 跳空缺口（US-026 批 5 第 6 个）— 批 5 最后 1 个")
    print("=" * 70)
    loader = DataLoader()
    start_date = '2021-06-06'
    end_date = '2026-06-05'

    all_ic = []
    for code in CORE_ETF_POOL_15:
        try:
            all_data = loader.load(codes=[code])
            df = all_data.get(code)
            if df is None or df.empty or 'open' not in df.columns:
                continue
            if 'date' in df.columns:
                df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
            df['b4_gap'] = compute_gap_signal(df)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
            ic = compute_ic(df['b4_gap'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic})
                print(f"  ✅ {code}: IC = {ic:.4f}")
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not all_ic:
        return
    ic_df = pd.DataFrame(all_ic)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n📊 B4 跳空缺口 IC：均值={ic_mean:.4f} > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/B4_ic_report.json", 'w') as f:
        json.dump({
            'factor': 'B4_gap_signal',
            'ic_mean': ic_mean,
            'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
            'details': [{'code': r['code'], 'ic': float(r['ic'])} for r in all_ic],
        }, f, ensure_ascii=False, indent=2)

    print("\n## B4 任务结果（批 5 完成）")
    print(f"- IC 均值: {ic_mean:.4f} | > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")
    print(f"- 下一步: 自动进入批 6（复合类 C1-C6）")


if __name__ == "__main__":
    main()
