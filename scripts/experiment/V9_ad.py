#!/usr/bin/env python3
"""V9 A/D 累积派发指标（US-026 批 1 第 6 个，批 1 最后 1 个）"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_ad(df):
    """V9 A/D Line = Σ((close-low)-(high-close))/(high-low) * volume 累计"""
    clv = ((df['close'] - df['low']) - (df['high'] - df['close'])) / (df['high'] - df['low']).replace(0, 1)
    clv = clv.fillna(0) * df['volume']
    return clv.cumsum()


def compute_ad_oscillator(df, n=20):
    """A/D 振荡 = A/D Line 短期均值 - 长期均值"""
    ad = compute_ad(df)
    return ad.rolling(n).mean() - ad.rolling(n * 2).mean()


def compute_ic(factor, future_return):
    valid = pd.concat([factor, future_return], axis=1).dropna()
    return valid.corr().iloc[0, 1] if len(valid) >= 30 else np.nan


def main():
    print("=" * 70)
    print("V9 A/D 振荡指标（US-026 批 1 第 6 个，最后 1 个）")
    print("=" * 70)
    loader = DataLoader()
    start_date = '2021-06-06'
    end_date = '2026-06-05'

    all_ic = []
    factor_data = {}
    for code in CORE_ETF_POOL_15:
        try:
            all_data = loader.load(codes=[code])
            df = all_data.get(code)
            if df is None or df.empty:
                continue
            for col in ['high', 'low', 'close', 'volume']:
                if col not in df.columns:
                    continue
            if 'date' in df.columns:
                df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
            df['v9_ad_osc'] = compute_ad_oscillator(df)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
            ic = compute_ic(df['v9_ad_osc'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic})
                print(f"  ✅ {code}: IC = {ic:.4f}")
            factor_data[code] = df[['date', 'close', 'v9_ad_osc', 'future_return_5d']].copy()
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not all_ic:
        return
    ic_df = pd.DataFrame(all_ic)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n📊 V9 A/D 振荡 IC：均值={ic_mean:.4f} 中位数={float(ic_df['ic'].median()):.4f} > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/V9_ic_report.json", 'w') as f:
        json.dump({
            'factor': 'V9_ad_oscillator',
            'n_etfs': int(len(ic_df)),
            'ic_mean': ic_mean,
            'ic_median': float(ic_df['ic'].median()),
            'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
            'details': [{'code': r['code'], 'ic': float(r['ic'])} for r in all_ic],
        }, f, ensure_ascii=False, indent=2)

    out_dir = Path("data/factor_pool/V9_ad_oscillator")
    out_dir.mkdir(parents=True, exist_ok=True)
    for code, df in factor_data.items():
        df.to_csv(out_dir / f"{code}.csv", index=False)

    print("\n## V9 任务结果（批 1 完成）")
    print(f"- 做了什么: V9 A/D 振荡 + IC 检验（批 1 第 6 个，批 1 完）")
    print(f"- 结果: IC 均值 {ic_mean:.4f} | > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")
    print(f"- 下一步: 自动进入批 2（趋势类 T5-T10）")


if __name__ == "__main__":
    main()
