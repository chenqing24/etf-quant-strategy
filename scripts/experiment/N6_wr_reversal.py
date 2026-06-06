#!/usr/bin/env python3
"""N6 WR 反向（US-026 批 5 第 3 个，反转类）"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_wr_rebound(df, n=14, oversold=30):
    """N6 RSI 超卖反弹（修复 WR 范围错：WR 是 0~100，不是负数；改用 RSI 标准超卖）"""
    # RSI = 100 - 100/(1+RS), RS = avg_gain/avg_loss
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(n).mean()
    avg_loss = loss.rolling(n).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    rsi = 100 - 100 / (1 + rs)
    return (rsi < oversold).astype(float)  # RSI < 30 → 超卖信号


def compute_ic(factor, future_return):
    valid = pd.concat([factor, future_return], axis=1).dropna()
    if len(valid) < 30:
        return np.nan
    x, y = valid.iloc[:, 0].values, valid.iloc[:, 1].values
    if np.std(x) == 0 or np.std(y) == 0:
        return np.nan  # 修复 stddev=0 卡住
    return float(np.corrcoef(x, y)[0, 1])


def main():
    print("=" * 70)
    print("N6 WR 超卖反弹（US-026 批 5 第 3 个，反转类）")
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
            df['n6_wr_rebound'] = compute_wr_rebound(df)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
            # 诊断：打印因子值分布
            n6_nunique = df['n6_wr_rebound'].nunique()
            n6_pct = df['n6_wr_rebound'].mean() * 100
            print(f"  ... {code}: n6 unique={n6_nunique}, mean={n6_pct:.2f}%", flush=True)
            ic = compute_ic(df['n6_wr_rebound'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic})
                print(f"  ✅ {code}: IC = {ic:.4f}", flush=True)
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}", flush=True)

    if not all_ic:
        return
    ic_df = pd.DataFrame(all_ic)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n📊 N6 WR 反弹 IC：均值={ic_mean:.4f} > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/N6_ic_report.json", 'w') as f:
        json.dump({
            'factor': 'N6_wr_rebound',
            'ic_mean': ic_mean,
            'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
            'details': [{'code': r['code'], 'ic': float(r['ic'])} for r in all_ic],
        }, f, ensure_ascii=False, indent=2)

    print("\n## N6 任务结果")
    print(f"- IC 均值: {ic_mean:.4f} | > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")
    print(f"- 下一步: {'自动进入 B2 新高（突破类）' if ic_mean > 0.01 else 'N6 弱通过'}")


if __name__ == "__main__":
    main()
