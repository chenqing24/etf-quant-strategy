#!/usr/bin/env python3
"""C6 自适应（US-026 批 6 第 6 个）— 全部 6 批最后 1 个"""
import sys, json
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_adaptive(df, short_n=5, long_n=20):
    """C6 自适应 = 短期波动/长期波动（市场状态判断）"""
    log_ret = np.log(df['close'] / df['close'].shift(1))
    short_vol = log_ret.rolling(short_n).std()
    long_vol = log_ret.rolling(long_n).std()
    # 自适应比率 > 1 = 短期波动 > 长期 = 突破/事件
    return (short_vol / long_vol.replace(0, 1)).fillna(1)


def compute_adaptive_signal(df, short_n=5, long_n=20, threshold=1.2):
    """C6 自适应信号 = 短期/长期波动 > 阈值（事件触发）"""
    adaptive = compute_adaptive(df, short_n, long_n)
    return (adaptive > threshold).astype(float)


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
    print("C6 自适应（US-026 批 6 第 6 个）— 全部 6 批最后 1 个")
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
            df['c6_adaptive'] = compute_adaptive_signal(df)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
            ic = compute_ic(df['c6_adaptive'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic})
                print(f"  ✅ {code}: IC = {ic:.4f}")
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not all_ic:
        return
    ic_df = pd.DataFrame(all_ic)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n📊 C6 自适应 IC：均值={ic_mean:.4f} > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/C6_ic_report.json", 'w') as f:
        json.dump({
            'factor': 'C6_adaptive',
            'ic_mean': ic_mean,
            'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
            'details': [{'code': r['code'], 'ic': float(r['ic'])} for r in all_ic],
        }, f, ensure_ascii=False, indent=2)

    print("\n## C6 任务结果（全部 6 批 完成）")
    print(f"- IC 均值: {ic_mean:.4f} | > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")
    print(f"- 下一步: 全部 6 批完成！生成最终报告")


if __name__ == "__main__":
    main()
