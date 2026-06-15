#!/usr/bin/env python3
"""C12 buy & hold 基准对比（验证 C11 alpha 是否真实）

按 L217 风险标注：
- C11 持仓直到期末 = 5 年单笔交易
- +68.97% 可能来自"A 股 ETF 长期上行"的 beta
- 必须对比 buy & hold 验证 alpha

⚠️ 数据范围限制：510300 只有 2023-09-26 起的 2.7 年数据（数据延迟问题）
   用每只 ETF 实际可用数据范围做 buy & hold 基准
"""
import sys
import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import ETF_POOL
from src.data.loader import DataLoader
from scripts.experiment.C11_disable_max_hold import run_single as run_c11


def buy_hold_single(code: str, df: pd.DataFrame) -> dict:
    """单只 ETF buy & hold 收益"""
    df = df.sort_values('date').reset_index(drop=True)
    if df.empty:
        return {'code': code, 'skipped': True}

    start_price = df.iloc[0]['close']
    end_price = df.iloc[-1]['close']
    start_date = df.iloc[0]['date']
    end_date = df.iloc[-1]['date']

    # 持仓天数
    hold_days = (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days

    total_return = (end_price / start_price - 1) if start_price > 0 else 0
    annual_return = (1 + total_return) ** (365 / max(hold_days, 1)) - 1 if hold_days > 0 else 0

    return {
        'code': code,
        'bh_return': float(total_return),
        'bh_annual_return': float(annual_return),
        'hold_days': int(hold_days),
        'start_date': str(start_date),
        'end_date': str(end_date),
    }


def main():
    print("=" * 70)
    print("C12 buy & hold 基准对比（验证 C11 alpha）")
    print("=" * 70)
    print("⚠️ 数据范围：etf.db 实际可用日期（受数据延迟影响）")

    loader = DataLoader()
    print("\n📊 加载 ETF 数据...")
    all_data = {}
    for code in ETF_POOL:
        try:
            d = loader.load(codes=[code]).get(code)
            if d is not None and not d.empty:
                all_data[code] = d
        except Exception:
            pass
    print(f"  ETF: {len(all_data)}")

    # 1. buy & hold 基准
    print("\n📊 Step 1: buy & hold 基准（每只 ETF 实际可用范围）")
    bh_results = []
    for code, df in all_data.items():
        r = buy_hold_single(code, df)
        if 'skipped' not in r:
            bh_results.append(r)

    if not bh_results:
        print("❌ 无 buy & hold 数据")
        return

    bh_df = pd.DataFrame(bh_results)
    bh_avg = float(bh_df['bh_return'].mean())
    bh_annual_avg = float(bh_df['bh_annual_return'].mean())
    bh_pos_pct = float((bh_df['bh_return'] > 0).mean())
    avg_hold_days = float(bh_df['hold_days'].mean())

    print(f"  ETF 数: {len(bh_df)}")
    print(f"  平均持仓天数: {avg_hold_days:.0f} ({avg_hold_days/365:.1f} 年)")
    print(f"  buy & hold 平均收益: {bh_avg:+.2%}")
    print(f"  buy & hold 年化收益: {bh_annual_avg:+.2%}")
    print(f"  正收益 ETF%: {bh_pos_pct:.1%}")

    # 2. C11 实测（min_n=1）
    print("\n📊 Step 2: C11 实测（min_n=1）")
    c11_results = []
    for code, df in all_data.items():
        r = run_c11(code, df, min_n=1)
        if 'error' not in r and not r.get('skipped'):
            c11_results.append(r)

    if not c11_results:
        print("❌ 无 C11 数据")
        return

    c11_df = pd.DataFrame(c11_results)
    c11_avg = float(c11_df['total_return'].mean())
    c11_pos_pct = float((c11_df['total_return'] > 0).mean())
    c11_avg_dd = float(c11_df['max_drawdown'].mean())

    print(f"  ETF 数: {len(c11_df)}")
    print(f"  C11 平均收益: {c11_avg:+.2%}")
    print(f"  C11 正收益 ETF%: {c11_pos_pct:.1%}")
    print(f"  C11 平均回撤: {c11_avg_dd:+.2%}")

    # 3. Alpha 计算（按规则 6.1：必须验证 alpha）
    print("\n" + "=" * 70)
    print("📊 Step 3: Alpha 计算（C11 - buy & hold）")
    print("=" * 70)

    # 按 ETF 配对计算 alpha
    merged = c11_df.merge(bh_df, on='code', how='inner')
    if len(merged) > 0:
        merged['alpha'] = merged['total_return'] - merged['bh_return']
        alpha_mean = float(merged['alpha'].mean())
        alpha_pos_pct = float((merged['alpha'] > 0).mean())
        c11_minus_bh = c11_avg - bh_avg

        print(f"  配对 ETF 数: {len(merged)}")
        print(f"  C11 平均收益: {c11_avg:+.2%}")
        print(f"  buy & hold 平均: {bh_avg:+.2%}")
        print(f"  Alpha (C11-BH): {c11_minus_bh:+.2%}")
        print(f"  配对 alpha 均值: {alpha_mean:+.2%}")
        print(f"  配对 alpha > 0 的 ETF: {alpha_pos_pct:.1%}")

        # 验收
        print(f"\n✅ 验收")
        print(f"  Alpha > 0 (策略有效): {'PASS' if c11_minus_bh > 0 else 'FAIL'}")
        print(f"  配对 alpha 均值 > 0: {'PASS' if alpha_mean > 0 else 'FAIL'}")
        print(f"  Alpha ETF 数 > 50%: {'PASS' if alpha_pos_pct > 0.5 else 'FAIL'}")

        # Top 5 alpha ETF
        print(f"\n📊 Top 5 alpha ETF（C11 超越 buy & hold 最多的）")
        top5_alpha = merged.nlargest(5, 'alpha')
        for _, row in top5_alpha.iterrows():
            print(f"  {row['code']}: alpha={row['alpha']:+.2%} | C11={row['total_return']:+.2%} | BH={row['bh_return']:+.2%}")

        # 5. 保存报告
        Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
        with open("data/business_understanding/C12_alpha_verification.json", 'w', encoding='utf-8') as f:
            json.dump({
                'experiment': 'C12_alpha_verification',
                'data_warning': 'etf.db 数据范围受限（实际 ~2.7 年，非完整 5 年）',
                'bh_avg_return': bh_avg,
                'bh_annual_return': bh_annual_avg,
                'bh_positive_pct': bh_pos_pct,
                'bh_avg_hold_days': avg_hold_days,
                'c11_avg_return': c11_avg,
                'c11_positive_pct': c11_pos_pct,
                'c11_avg_drawdown': c11_avg_dd,
                'alpha_avg': c11_minus_bh,
                'alpha_paired_mean': alpha_mean,
                'alpha_positive_pct': alpha_pos_pct,
                'verdict': 'ALPHA' if c11_minus_bh > 0 else 'BETA_ONLY',
                'details': merged.to_dict('records'),
            }, f, ensure_ascii=False, indent=2, default=str)

        # 6. 诚实结论
        print(f"\n📋 诚实结论（按规则 6.1）")
        if c11_minus_bh > 0.02:  # alpha > 2%
            print(f"  ✅ C11 有 alpha = {c11_minus_bh:+.2%}（策略有效）")
        elif c11_minus_bh > 0:
            print(f"  🟡 C11 alpha 微弱 = {c11_minus_bh:+.2%}（需更多验证）")
        else:
            print(f"  🔴 C11 alpha = {c11_minus_bh:+.2%}（无 alpha，只是 beta）")
        print(f"  📊 buy & hold = {bh_avg:+.2%}（ETF 长期上行基准）")
        print(f"\n📁 报告: data/business_understanding/C12_alpha_verification.json")


if __name__ == "__main__":
    main()
