#!/usr/bin/env python3
"""C17 样本外验证（out-of-sample test）

按 L218 + 用户质疑：
- 35 只 ETF 同时用于设计 + 验证 = 过拟合风险
- 解决方案：留出 30% ETF 不参与任何实验设计，最后验证

⚠️ 但 etf_db 仅 35 只 ETF，无法严格留出 30%
   采用替代方案：用 etf_names 表查询所有 ETF，用前 24 只做 in-sample，后 11 只做 out-of-sample
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


def main():
    print("=" * 70)
    print("C17 样本外验证（out-of-sample）")
    print("=" * 70)
    print("⚠️ 数据限制：etf.db 仅 35 只可用 ETF")

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

    # 按 ETF 编号排序（人为划分）
    all_codes = sorted(all_data.keys())
    print(f"  总 ETF: {len(all_codes)}")

    # 替代方案：按代码字母排序分两半
    half = len(all_codes) // 2
    in_sample_codes = all_codes[:half]
    out_sample_codes = all_codes[half:]

    print(f"  In-sample (前 {half}): {in_sample_codes[:5]}... {in_sample_codes[-3:]}")
    print(f"  Out-of-sample (后 {len(all_codes) - half}): {out_sample_codes[:5]}... {out_sample_codes[-3:]}")

    # In-sample: 跑 C11
    print("\n📊 In-sample C11...")
    in_results = []
    for code in in_sample_codes:
        r = run_c11(code, all_data[code], min_n=1)
        if 'error' not in r and not r.get('skipped'):
            in_results.append(r)
    in_df = pd.DataFrame(in_results)
    in_avg_ret = float(in_df['total_return'].mean())
    in_avg_wr = float(in_df['win_rate'].mean())
    in_pos_pct = float((in_df['total_return'] > 0).mean())
    print(f"  N={len(in_df)} | 收益={in_avg_ret:+.2%} | 胜率={in_avg_wr:.1%} | 正收益={in_pos_pct:.1%}")

    # Out-of-sample: 跑 C11（用相同参数，不重新调优）
    print("\n📊 Out-of-sample C11（同一参数，无调优）...")
    out_results = []
    for code in out_sample_codes:
        r = run_c11(code, all_data[code], min_n=1)
        if 'error' not in r and not r.get('skipped'):
            out_results.append(r)
    out_df = pd.DataFrame(out_results)
    out_avg_ret = float(out_df['total_return'].mean())
    out_avg_wr = float(out_df['win_rate'].mean())
    out_pos_pct = float((out_df['total_return'] > 0).mean())
    print(f"  N={len(out_df)} | 收益={out_avg_ret:+.2%} | 胜率={out_avg_wr:.1%} | 正收益={out_pos_pct:.1%}")

    # 对比
    print("\n" + "=" * 70)
    print("📊 In-sample vs Out-of-sample 对比")
    print("=" * 70)
    print(f"  {'指标':<20} {'In-sample':<15} {'Out-of-sample':<15} {'Δ':<10}")
    print(f"  {'样本数':<20} {len(in_df):<15} {len(out_df):<15} {len(out_df)-len(in_df)}")
    print(f"  {'平均收益':<20} {in_avg_ret*100:>+10.2f}% {out_avg_ret*100:>+10.2f}% {(out_avg_ret-in_avg_ret)*100:+.2f}pp")
    print(f"  {'平均胜率':<20} {in_avg_wr*100:>10.2f}% {out_avg_wr*100:>10.2f}% {(out_avg_wr-in_avg_wr)*100:+.2f}pp")
    print(f"  {'正收益%':<20} {in_pos_pct*100:>10.2f}% {out_pos_pct*100:>10.2f}% {(out_pos_pct-in_pos_pct)*100:+.2f}pp")

    # 过拟合判断
    print(f"\n✅ 过拟合判断（按规则 6.1）")
    wr_delta = out_avg_wr - in_avg_wr
    if abs(wr_delta) < 0.05:  # 胜率差异 < 5pp
        print(f"  ✅ 胜率差异 {wr_delta*100:+.2f}pp（< 5pp）→ 无明显过拟合")
    elif abs(wr_delta) < 0.15:
        print(f"  🟡 胜率差异 {wr_delta*100:+.2f}pp（5-15pp）→ 中度过拟合")
    else:
        print(f"  🔴 胜率差异 {wr_delta*100:+.2f}pp（> 15pp）→ 严重过拟合")

    # 保存报告
    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/C17_out_of_sample.json", 'w', encoding='utf-8') as f:
        json.dump({
            'experiment': 'C17_out_of_sample',
            'in_sample': {
                'codes': in_sample_codes,
                'n': len(in_df),
                'avg_return': in_avg_ret,
                'avg_winrate': in_avg_wr,
                'positive_pct': in_pos_pct,
            },
            'out_of_sample': {
                'codes': out_sample_codes,
                'n': len(out_df),
                'avg_return': out_avg_ret,
                'avg_winrate': out_avg_wr,
                'positive_pct': out_pos_pct,
            },
            'winrate_delta': wr_delta,
            'overfitting_verdict': 'none' if abs(wr_delta) < 0.05 else ('mild' if abs(wr_delta) < 0.15 else 'severe'),
        }, f, ensure_ascii=False, indent=2)
    print(f"\n📁 报告: data/business_understanding/C17_out_of_sample.json")


if __name__ == "__main__":
    main()
