#!/usr/bin/env python3
"""W1 ATR（US-026 批 4 第 1 个，波动类）"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_atr(df, n=14):
    """W1 ATR = 真实波幅均值（n 日）"""
    high = df['high']
    low = df['low']
    close_prev = df['close'].shift(1)
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(n).mean() / df['close']  # 归一化


def compute_ic(factor, future_return):
    valid = pd.concat([factor, future_return], axis=1).dropna()
    return valid.corr().iloc[0, 1] if len(valid) >= 30 else np.nan


def main():
    print("=" * 70)
    print("W1 ATR（US-026 批 4 第 1 个，波动类）")
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
            df['w1_atr'] = compute_atr(df)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
            ic = compute_ic(df['w1_atr'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic})
                print(f"  ✅ {code}: IC = {ic:.4f}")
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not all_ic:
        return
    ic_df = pd.DataFrame(all_ic)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n📊 W1 ATR IC：均值={ic_mean:.4f} > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/W1_ic_report.json", 'w') as f:
        json.dump({
            'factor': 'W1_atr',
            'ic_mean': ic_mean,
            'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
            'details': [{'code': r['code'], 'ic': float(r['ic'])} for r in all_ic],
        }, f, ensure_ascii=False, indent=2)

    print("\n## W1 任务结果")
    print(f"- IC 均值: {ic_mean:.4f} | > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")
    print(f"- 下一步: {'自动进入 W2 布林带宽' if ic_mean > 0.01 else 'W1 弱通过'}")


if __name__ == "__main__":
    main()
