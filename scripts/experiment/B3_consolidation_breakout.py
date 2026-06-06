#!/usr/bin/env python3
"""B3 盘整突破（US-026 批 5 第 5 个，突破类）"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_consolidation_breakout(df, n=20, vol_threshold=0.02):
    """B3 盘整突破 = (n 日内波动率 < vol_threshold) AND (今日 close > n 日最高)"""
    # 盘整 = 近期低波动
    returns = df['close'].pct_change()
    vol_n = returns.rolling(n).std()
    consolidation = vol_n < vol_threshold

    # 突破 = close > n 日最高
    high_n = df['high'].rolling(n).max().shift(1)
    breakout = df['close'] > high_n

    signal = pd.Series(0, index=df.index, dtype=float)
    signal[consolidation & breakout] = 1
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
    print("B3 盘整突破（US-026 批 5 第 5 个，突破类）")
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
            df['b3_consolidation'] = compute_consolidation_breakout(df)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
            ic = compute_ic(df['b3_consolidation'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic})
                print(f"  ✅ {code}: IC = {ic:.4f}")
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not all_ic:
        return
    ic_df = pd.DataFrame(all_ic)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n📊 B3 盘整突破 IC：均值={ic_mean:.4f} > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/B3_ic_report.json", 'w') as f:
        json.dump({
            'factor': 'B3_consolidation_breakout',
            'ic_mean': ic_mean,
            'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
            'details': [{'code': r['code'], 'ic': float(r['ic'])} for r in all_ic],
        }, f, ensure_ascii=False, indent=2)

    print("\n## B3 任务结果")
    print(f"- IC 均值: {ic_mean:.4f} | > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")
    print(f"- 下一步: {'自动进入 B4 跳空（批 5 最后 1 个）' if ic_mean > 0.01 else 'B3 弱通过'}")


if __name__ == "__main__":
    main()
