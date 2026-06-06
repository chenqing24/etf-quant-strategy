#!/usr/bin/env python3
"""N5 KDJ 死叉（US-026 批 5 第 2 个，反转类）"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_kdj_death_cross(df, n=9):
    """N5 KDJ 死叉 = K 线从上方下穿 D 线（卖出信号，反向=+1 反弹）"""
    low_n = df['low'].rolling(n).min()
    high_n = df['high'].rolling(n).max()
    rsv = (df['close'] - low_n) / (high_n - low_n).replace(0, 1) * 100
    k = rsv.ewm(alpha=1/3, adjust=False).mean()
    d = k.ewm(alpha=1/3, adjust=False).mean()

    # 死叉：前一日 K > D，今日 K < D
    k_prev = k.shift(1)
    d_prev = d.shift(1)
    death_cross = (k_prev > d_prev) & (k < d)

    signal = pd.Series(0.0, index=df.index)
    signal[death_cross] = 1  # 死叉后可能反弹（反向思维）
    return signal


def compute_ic(factor, future_return):
    valid = pd.concat([factor, future_return], axis=1).dropna()
    return valid.corr().iloc[0, 1] if len(valid) >= 30 else np.nan


def main():
    print("=" * 70)
    print("N5 KDJ 死叉（US-026 批 5 第 2 个，反转类）")
    print("=" * 70)
    loader = DataLoader()
    start_date = '2021-06-06'
    end_date = '2026-06-05'

    all_ic = []
    for code in CORE_ETF_POOL_15:
        try:
            all_data = loader.load(codes=[code])
            df = all_data.get(code)
            if df is None or df.empty or 'low' not in df.columns:
                continue
            if 'date' in df.columns:
                df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
            df['n5_kdj_death'] = compute_kdj_death_cross(df)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
            ic = compute_ic(df['n5_kdj_death'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic})
                print(f"  ✅ {code}: IC = {ic:.4f}")
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not all_ic:
        return
    ic_df = pd.DataFrame(all_ic)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n📊 N5 KDJ 死叉 IC：均值={ic_mean:.4f} > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/N5_ic_report.json", 'w') as f:
        json.dump({
            'factor': 'N5_kdj_death_cross',
            'ic_mean': ic_mean,
            'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
            'details': [{'code': r['code'], 'ic': float(r['ic'])} for r in all_ic],
        }, f, ensure_ascii=False, indent=2)

    print("\n## N5 任务结果")
    print(f"- IC 均值: {ic_mean:.4f} | > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")
    print(f"- 下一步: {'自动进入 N6 WR' if ic_mean > 0.01 else 'N5 弱通过'}")


if __name__ == "__main__":
    main()
