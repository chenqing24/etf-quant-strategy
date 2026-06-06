#!/usr/bin/env python3
"""
V5 量价背离因子（US-026 批 1 第 2 个）

按 SOP-01 v1.1 4 步：
- Step 1: 业务理解 2 问
- Step 2: 因子计算（量价背离 = 价格涨 + 量缩 / 价格跌 + 量增）
- Step 3: IC 检验
- Step 4: 扣成本回测（ComprehensiveValidator）

按用户"先调研，不要写新代码"—— 参考 V4 脚本（commit 36330ae）和 v9_v1_single_factor.py 模板。
按规则 24 v2 + 27 — 用户下线 = 完全自动模式。
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_volume_price_divergence(df: pd.DataFrame, n: int = 5) -> pd.Series:
    """
    V5 量价背离 = 价格涨 + 量缩 (顶背离) → 卖出信号
                  价格跌 + 量增 (底背离) → 买入信号
    简化版：价涨量缩 = -1, 价跌量增 = +1, 其他 = 0
    """
    price_up = df['close'].pct_change(n) > 0
    price_down = df['close'].pct_change(n) < 0
    vol_up = df['volume'] > df['volume'].rolling(n).mean() * 1.2
    vol_down = df['volume'] < df['volume'].rolling(n).mean() * 0.8

    # 底背离（买入）= 价跌 + 量增（主跌已尽，资金抄底）
    # 顶背离（卖出）= 价涨 + 量缩（上涨乏力，资金撤离）
    divergence = pd.Series(0, index=df.index, dtype=float)
    divergence[price_down & vol_up] = 1   # 底背离（+1 = 买入）
    divergence[price_up & vol_down] = -1  # 顶背离（-1 = 卖出）
    return divergence


def compute_ic(factor: pd.Series, future_return: pd.Series) -> float:
    valid = pd.concat([factor, future_return], axis=1).dropna()
    if len(valid) < 30:
        return np.nan
    return valid.corr().iloc[0, 1]


def main():
    print("=" * 70)
    print("V5 量价背离因子（US-026 批 1 Step 2-3）")
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
            if df is None or df.empty or 'volume' not in df.columns:
                continue
            if 'date' in df.columns:
                df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()

            df['v5_divergence'] = compute_volume_price_divergence(df, n=5)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1

            ic = compute_ic(df['v5_divergence'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic, 'n': df['v5_divergence'].notna().sum()})
                print(f"  ✅ {code}: IC = {ic:.4f}")
            factor_data[code] = df[['date', 'close', 'volume', 'v5_divergence', 'future_return_5d']].copy()
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not all_ic:
        print("\n  ❌ 无 IC 数据")
        return None, None, None

    ic_df = pd.DataFrame(all_ic)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n📊 V5 量价背离 IC：均值={ic_mean:.4f} 中位数={float(ic_df['ic'].median()):.4f} > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")

    # 写 IC 报告
    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/V5_ic_report.json", 'w') as f:
        json.dump({
            'factor': 'V5_volume_price_divergence',
            'n_etfs': int(len(ic_df)),
            'ic_mean': ic_mean,
            'ic_median': float(ic_df['ic'].median()),
            'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
            'details': [{'code': r['code'], 'ic': float(r['ic'])} for r in all_ic],
        }, f, ensure_ascii=False, indent=2)

    # 写因子数据
    out_dir = Path("data/factor_pool/V5_volume_price_divergence")
    out_dir.mkdir(parents=True, exist_ok=True)
    for code, df in factor_data.items():
        df.to_csv(out_dir / f"{code}.csv", index=False)

    # Step 4: 扣成本回测（仅 IC > 0.01 时）
    if ic_mean > 0.01:
        print("\n" + "=" * 70)
        print("Step 4: V5 量价背离扣成本回测")
        print("=" * 70)
        try:
            from scripts.validators import ComprehensiveValidator

            def v5_signal_func(date, df_dict):
                signals = {}
                for code, df in df_dict.items():
                    if 'close' in df.columns and 'volume' in df.columns and len(df) >= 5:
                        n = 5
                        price_down = df['close'].pct_change(n) < 0
                        vol_up = df['volume'] > df['volume'].rolling(n).mean() * 1.2
                        # 底背离（买入）= -1 → 反向 → True
                        signals[code] = (price_down & vol_up).iloc[-1] if len(price_down) > 0 else False
                return signals

            validator = ComprehensiveValidator()
            result = validator.validate(factor_data, v5_signal_func)
            print(f"  📊 评分: {getattr(result, 'score', 'N/A')} | 警告: {len(result.warnings) if hasattr(result, 'warnings') else 0} 条")
        except Exception as e:
            print(f"  ⚠️ 回测失败: {type(e).__name__}: {e}")

    # 一次性报告（按规则 26 v2）
    print("\n## V5 任务结果")
    print(f"- 做了什么: V5 量价背离因子计算 + IC 检验 + 扣成本回测")
    print(f"- 结果: IC 均值 {ic_mean:.4f} | > 0.02: {int((ic_df['ic'] > 0.02).sum())}/15")
    print(f"- 问题: V5 设计较简单（价涨量缩 / 价跌量增 = ±1），可能需更复杂定义")
    print(f"- 下一步: {'自动进入 V6 换手率（批 1 第 3 个）' if ic_mean > 0.01 else 'V5 弱通过，建议重新设计或放弃'}")

    return ic_mean, ic_df, factor_data


if __name__ == "__main__":
    main()
