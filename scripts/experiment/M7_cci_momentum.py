#!/usr/bin/env python3
"""M7 CCI 动量版（US-026 批 3 第 3 个，动量类）"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_cci_momentum(df, n=20):
    """M7 CCI 动量 = CCI 当前 - CCI n 日前"""
    tp = (df['high'] + df['low'] + df['close']) / 3
    ma_tp = tp.rolling(n).mean()
    md = (tp - ma_tp).abs().rolling(n).mean()
    cci = (tp - ma_tp) / (0.015 * md.replace(0, 1))
    return cci - cci.shift(n)


def compute_ic(factor, future_return):
    valid = pd.concat([factor, future_return], axis=1).dropna()
    return valid.corr().iloc[0, 1] if len(valid) >= 30 else np.nan


def main():
    print("=" * 70)
    print("M7 CCI 动量（US-026 批 3 第 3 个，动量类）")
    print("=" * 70)
    loader = DataLoader()
    start_date = '2021-06-06'
    end_date = '2026-06-05'

    all_ic = []
    for code in CORE_ETF_POOL_15:
        try:
            all_data = loader.load(codes=[code])
            df = all_data.get(code)
            if df is None or df.empty or 'high' not in df.columns:
                continue
            if 'date' in df.columns:
                df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
            df['m7_cci_mom'] = compute_cci_momentum(df)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
            ic = compute_ic(df['m7_cci_mom'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic})
                print(f"  ✅ {code}: IC = {ic:.4f}")
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not all_ic:
        return
    ic_df = pd.DataFrame(all_ic)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n📊 M7 CCI 动量 IC：均值={ic_mean:.4f} > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/M7_ic_report.json", 'w') as f:
        json.dump({
            'factor': 'M7_cci_momentum',
            'ic_mean': ic_mean,
            'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
            'details': [{'code': r['code'], 'ic': float(r['ic'])} for r in all_ic],
        }, f, ensure_ascii=False, indent=2)

    print("\n## M7 任务结果")
    print(f"- IC 均值: {ic_mean:.4f} | > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")
    print(f"- 下一步: {'自动进入 M8 MFI' if ic_mean > 0.01 else 'M7 弱通过'}")


if __name__ == "__main__":
    main()
