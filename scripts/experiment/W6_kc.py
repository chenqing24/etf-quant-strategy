#!/usr/bin/env python3
"""W6 Keltner 通道（US-026 批 4 第 6 个，波动类）— 批 4 最后 1 个"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_keltner(df, n=20, m=2):
    """W6 Keltner 通道宽度 = (upper - lower) / mid, upper = EMA + m*ATR, lower = EMA - m*ATR"""
    ema = df['close'].ewm(span=n, adjust=False).mean()
    high = df['high']
    low = df['low']
    close_prev = df['close'].shift(1)
    tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean()
    upper = ema + m * atr
    lower = ema - m * atr
    return (upper - lower) / ema


def compute_kc_change(df, n=20, m=2):
    """W6 KC 变化"""
    kc = compute_keltner(df, n, m)
    return kc - kc.shift(n)


def compute_ic(factor, future_return):
    valid = pd.concat([factor, future_return], axis=1).dropna()
    return valid.corr().iloc[0, 1] if len(valid) >= 30 else np.nan


def main():
    print("=" * 70)
    print("W6 Keltner 通道宽度变化（US-026 批 4 第 6 个）— 批 4 最后 1 个")
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
            df['w6_kc_chg'] = compute_kc_change(df)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
            ic = compute_ic(df['w6_kc_chg'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic})
                print(f"  ✅ {code}: IC = {ic:.4f}")
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not all_ic:
        return
    ic_df = pd.DataFrame(all_ic)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n📊 W6 KC 变化 IC：均值={ic_mean:.4f} > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/W6_ic_report.json", 'w') as f:
        json.dump({
            'factor': 'W6_kc_change',
            'ic_mean': ic_mean,
            'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
            'details': [{'code': r['code'], 'ic': float(r['ic'])} for r in all_ic],
        }, f, ensure_ascii=False, indent=2)

    print("\n## W6 任务结果（批 4 完成）")
    print(f"- IC 均值: {ic_mean:.4f} | > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")
    print(f"- 下一步: 自动进入批 5（反转/突破 N4-N6/B2-B4）")


if __name__ == "__main__":
    main()
