#!/usr/bin/env python3
"""C4 趋势+波动（US-026 批 6 第 4 个，复合类）"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_trend_vol(df, trend_n=20, vol_n=10):
    """C4 趋势+波动 = 趋势强度 × 波动扩张（趋势 + 放量）"""
    # 趋势 = close > MA
    ma = df['close'].rolling(trend_n).mean()
    trend = (df['close'] - ma) / ma  # 归一化趋势

    # 波动扩张 = 当前波动率 - 历史均值
    log_ret = np.log(df['close'] / df['close'].shift(1))
    vol = log_ret.rolling(vol_n).std()
    vol_ma = vol.rolling(vol_n * 2).mean()
    vol_expansion = (vol - vol_ma).fillna(0)

    return trend * vol_expansion


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
    print("C4 趋势+波动（US-026 批 6 第 4 个，复合类）")
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
            df['c4_trend_vol'] = compute_trend_vol(df)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
            ic = compute_ic(df['c4_trend_vol'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic})
                print(f"  ✅ {code}: IC = {ic:.4f}")
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not all_ic:
        return
    ic_df = pd.DataFrame(all_ic)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n📊 C4 趋势+波动 IC：均值={ic_mean:.4f} > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/C4_ic_report.json", 'w') as f:
        json.dump({
            'factor': 'C4_trend_vol',
            'ic_mean': ic_mean,
            'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
            'details': [{'code': r['code'], 'ic': float(r['ic'])} for r in all_ic],
        }, f, ensure_ascii=False, indent=2)

    print("\n## C4 任务结果")
    print(f"- IC 均值: {ic_mean:.4f} | > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")
    print(f"- 下一步: {'自动进入 C5 量价共振' if ic_mean > 0.01 else 'C4 弱通过'}")


if __name__ == "__main__":
    main()
