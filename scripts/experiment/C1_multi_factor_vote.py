#!/usr/bin/env python3
"""C1 多因子投票（US-026 批 6 第 1 个，复合类）"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_multi_factor_vote(df):
    """C1 多因子投票 = 5 个已通过因子的信号计数"""
    # 5 个已通过因子（来自批 1-5）
    # V4 量比 + T9 DMI + M7 CCI动量 + M9 WR + B3 盘整突破

    # V4 量比信号
    vol_ratio = df['volume'] / df['volume'].rolling(5).mean()
    v4_signal = (vol_ratio > 1.5).astype(int)

    # T9 DMI 信号（简化）
    high = df['high']
    low = df['low']
    close = df['close']
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(0.0, index=df.index)
    minus_dm = pd.Series(0.0, index=df.index)
    plus_dm[(up > down) & (up > 0)] = up
    minus_dm[(down > up) & (down > 0)] = down
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    plus_di = 100 * plus_dm.rolling(14).mean() / atr
    minus_di = 100 * minus_dm.rolling(14).mean() / atr
    dmi_diff = plus_di - minus_di
    t9_signal = (dmi_diff > 0).astype(int)

    # M9 WR 简化（取负使越高越好）
    high_n = df['high'].rolling(14).max()
    low_n = df['low'].rolling(14).min()
    wr = -(high_n - df['close']) / (high_n - low_n).replace(0, 1) * 100
    m9_signal = (wr > 50).astype(int)  # WR > 50 = 中等偏上

    # B3 盘整突破信号
    returns = df['close'].pct_change()
    vol_n = returns.rolling(20).std()
    high_n_b3 = df['high'].rolling(20).max().shift(1)
    b3_signal = ((vol_n < 0.02) & (df['close'] > high_n_b3)).astype(int)

    # 投票 = 5 因子信号之和
    vote = v4_signal + t9_signal + m9_signal + b3_signal
    return vote.astype(float)


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
    print("C1 多因子投票（US-026 批 6 第 1 个，复合类）")
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
            df['c1_vote'] = compute_multi_factor_vote(df)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
            ic = compute_ic(df['c1_vote'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic})
                print(f"  ✅ {code}: IC = {ic:.4f}")
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not all_ic:
        return
    ic_df = pd.DataFrame(all_ic)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n📊 C1 多因子投票 IC：均值={ic_mean:.4f} > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/C1_ic_report.json", 'w') as f:
        json.dump({
            'factor': 'C1_multi_factor_vote',
            'ic_mean': ic_mean,
            'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
            'details': [{'code': r['code'], 'ic': float(r['ic'])} for r in all_ic],
        }, f, ensure_ascii=False, indent=2)

    print("\n## C1 任务结果")
    print(f"- IC 均值: {ic_mean:.4f} | > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")
    print(f"- 下一步: {'自动进入 C2 因子加权' if ic_mean > 0.01 else 'C1 弱通过'}")


if __name__ == "__main__":
    main()
