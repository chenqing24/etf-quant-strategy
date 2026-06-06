#!/usr/bin/env python3
"""C2 因子加权（US-026 批 6 第 2 个，复合类）"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_weighted_combo(df, weights=None):
    """C2 因子加权 = Σ(IC_i × signal_i) / Σ(|IC_i|)"""
    if weights is None:
        # 5 个已通过因子的 IC（来自批 1-5）
        weights = {
            'v4': 0.0283,  # 量比
            't9': 0.0218,  # DMI
            'm7': 0.0510,  # CCI 动量
            'm9': 0.0518,  # WR
            'b3': 0.0589,  # 盘整突破
        }

    # V4 量比
    vol_ratio = df['volume'] / df['volume'].rolling(5).mean()
    v4_signal = (vol_ratio > 1.5).astype(int)

    # T9 DMI
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
    t9_signal = ((plus_di - minus_di) > 0).astype(int)

    # M9 WR
    high_n = df['high'].rolling(14).max()
    low_n = df['low'].rolling(14).min()
    wr = -(high_n - df['close']) / (high_n - low_n).replace(0, 1) * 100
    m9_signal = (wr > 50).astype(int)

    # B3 盘整突破
    returns = df['close'].pct_change()
    vol_n = returns.rolling(20).std()
    high_n_b3 = df['high'].rolling(20).max().shift(1)
    b3_signal = ((vol_n < 0.02) & (df['close'] > high_n_b3)).astype(int)

    # M7 CCI 动量
    tp = (df['high'] + df['low'] + df['close']) / 3
    ma_tp = tp.rolling(20).mean()
    md = (tp - ma_tp).abs().rolling(20).mean()
    cci = (tp - ma_tp) / (0.015 * md.replace(0, 1))
    m7_signal = ((cci - cci.shift(20)) > 0).astype(int)

    # 加权（用各因子 IC 作为权重）
    weighted = (
        weights['v4'] * v4_signal +
        weights['t9'] * t9_signal +
        weights['m7'] * m7_signal +
        weights['m9'] * m9_signal +
        weights['b3'] * b3_signal
    ) / sum(abs(w) for w in weights.values())

    return weighted


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
    print("C2 因子加权（US-026 批 6 第 2 个，复合类）")
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
            df['c2_weighted'] = compute_weighted_combo(df)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
            ic = compute_ic(df['c2_weighted'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic})
                print(f"  ✅ {code}: IC = {ic:.4f}")
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not all_ic:
        return
    ic_df = pd.DataFrame(all_ic)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n📊 C2 因子加权 IC：均值={ic_mean:.4f} > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/C2_ic_report.json", 'w') as f:
        json.dump({
            'factor': 'C2_weighted_combo',
            'ic_mean': ic_mean,
            'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
            'details': [{'code': r['code'], 'ic': float(r['ic'])} for r in all_ic],
        }, f, ensure_ascii=False, indent=2)

    print("\n## C2 任务结果")
    print(f"- IC 均值: {ic_mean:.4f} | > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")
    print(f"- 下一步: {'自动进入 C3 动量+反转' if ic_mean > 0.01 else 'C2 弱通过'}")


if __name__ == "__main__":
    main()
