#!/usr/bin/env python3
"""M6 TSI（US-026 批 3 第 2 个，动量类）"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_tsi(df, r=25, s=13):
    """M6 TSI = 100 * EMA(EMA(close_diff, r), s) / EMA(EMA(abs(close_diff), r), s)"""
    diff = df['close'].diff()
    abs_diff = diff.abs()
    ema1 = diff.ewm(span=r, adjust=False).mean()
    ema2 = ema1.ewm(span=s, adjust=False).mean()
    abs_ema1 = abs_diff.ewm(span=r, adjust=False).mean()
    abs_ema2 = abs_ema1.ewm(span=s, adjust=False).mean()
    return 100 * ema2 / abs_ema2.replace(0, 1)


def compute_ic(factor, future_return):
    valid = pd.concat([factor, future_return], axis=1).dropna()
    return valid.corr().iloc[0, 1] if len(valid) >= 30 else np.nan


def main():
    print("=" * 70)
    print("M6 TSI（US-026 批 3 第 2 个，动量类）")
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
            df['m6_tsi'] = compute_tsi(df)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
            ic = compute_ic(df['m6_tsi'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic})
                print(f"  ✅ {code}: IC = {ic:.4f}")
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not all_ic:
        return
    ic_df = pd.DataFrame(all_ic)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n📊 M6 TSI IC：均值={ic_mean:.4f} > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/M6_ic_report.json", 'w') as f:
        json.dump({
            'factor': 'M6_tsi',
            'ic_mean': ic_mean,
            'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
            'details': [{'code': r['code'], 'ic': float(r['ic'])} for r in all_ic],
        }, f, ensure_ascii=False, indent=2)

    print("\n## M6 任务结果")
    print(f"- IC 均值: {ic_mean:.4f} | > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")
    print(f"- 下一步: {'自动进入 M7 CCI（再次）' if ic_mean > 0.01 else 'M6 弱通过'}")


if __name__ == "__main__":
    main()
