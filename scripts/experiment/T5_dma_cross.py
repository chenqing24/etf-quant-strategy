#!/usr/bin/env python3
"""T5 DMA 交叉（US-026 批 2 第 1 个，趋势类）"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_dma_cross(df, fast=5, slow=20):
    """T5 DMA 交叉 = (MA5 - MA20) / MA20"""
    return (df['close'].rolling(fast).mean() - df['close'].rolling(slow).mean()) / df['close'].rolling(slow).mean()


def compute_ic(factor, future_return):
    valid = pd.concat([factor, future_return], axis=1).dropna()
    return valid.corr().iloc[0, 1] if len(valid) >= 30 else np.nan


def main():
    print("=" * 70)
    print("T5 DMA 交叉（US-026 批 2 第 1 个，趋势类）")
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
            df['t5_dma_cross'] = compute_dma_cross(df)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
            ic = compute_ic(df['t5_dma_cross'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic})
                print(f"  ✅ {code}: IC = {ic:.4f}")
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not all_ic:
        return
    ic_df = pd.DataFrame(all_ic)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n📊 T5 DMA 交叉 IC：均值={ic_mean:.4f} > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/T5_ic_report.json", 'w') as f:
        json.dump({
            'factor': 'T5_dma_cross',
            'n_etfs': int(len(ic_df)),
            'ic_mean': ic_mean,
            'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
            'details': [{'code': r['code'], 'ic': float(r['ic'])} for r in all_ic],
        }, f, ensure_ascii=False, indent=2)

    print("\n## T5 任务结果")
    print(f"- 做了什么: T5 DMA 交叉 + IC 检验")
    print(f"- 结果: IC 均值 {ic_mean:.4f}")
    print(f"- 下一步: {'自动进入 T6 均线斜率' if ic_mean > 0.01 else 'T5 弱通过'}")


if __name__ == "__main__":
    main()
