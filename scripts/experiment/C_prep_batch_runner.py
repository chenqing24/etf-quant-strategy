#!/usr/bin/env python3
"""
US-026 C 选项准备工作 - 28 因子批量运行器

按用户"情做准备工作"（不立即跑，先准备）：
- 调研发现：28 因子 = 6 批 × 6 因子 = 36 总数，16 个有 main()，8 个有 compute_XX_signal()，2 个有 vX_signal_func()
- 全部脚本都可独立执行：`python3 scripts/experiment/V6_turnover_rate.py`
- 12 个未跑因子（含 W1/W5/W6 跑过但未 A2/A3/A4）

按"先调研，不要写新代码"原则：
- 复用 28 个现有脚本
- 不写新监控（只写 1 个批量运行器 = 准备工作）

执行：
  python scripts/experiment/C_prep_batch_runner.py --mode inspect  # 只检查
  python scripts/experiment/C_prep_batch_runner.py --mode run     # 实际跑
  python scripts/experiment/C_prep_batch_runner.py --mode report  # 生成报告
"""
import sys
import os
import json
import argparse
import subprocess
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# 36 因子分类（按"是否已 A2/A3/A4 验证"）
FACTORS_36 = {
    # 批 1: 量价 (V)
    'V4_volume_ratio': {'category': 'V', 'status': 'tested_ic_only', 'a234': False},
    'V5_volume_price_divergence': {'category': 'V', 'status': 'tested_ic_only', 'a234': False},
    'V6_turnover_rate': {'category': 'V', 'status': 'untested', 'a234': False},
    'V7_vwap': {'category': 'V', 'status': 'untested', 'a234': False},
    'V8_cmf': {'category': 'V', 'status': 'untested', 'a234': False},
    'V9_ad': {'category': 'V', 'status': 'untested', 'a234': False},
    # 批 2: 趋势 (T)
    'T5_dma_cross': {'category': 'T', 'status': 'untested', 'a234': False},
    'T6_ma_slope': {'category': 'T', 'status': 'untested', 'a234': False},
    'T7_ema': {'category': 'T', 'status': 'untested', 'a234': False},
    'T8_triple_ma': {'category': 'T', 'status': 'untested', 'a234': False},
    'T9_dmi': {'category': 'T', 'status': 'untested', 'a234': False},
    'T10_cci': {'category': 'T', 'status': 'untested', 'a234': False},
    # 批 3: 动量 (M)
    'M5_roc': {'category': 'M', 'status': 'untested', 'a234': False},
    'M6_tsi': {'category': 'M', 'status': 'untested', 'a234': False},
    'M7_cci_momentum': {'category': 'M', 'status': 'tested_a234', 'a234': True, 'verdict': 'weak_a2'},
    'M8_mfi': {'category': 'M', 'status': 'untested', 'a234': False},
    'M9_wr': {'category': 'M', 'status': 'tested_a234', 'a234': True, 'verdict': 'broken_m9'},
    'M10_ulcer': {'category': 'M', 'status': 'untested', 'a234': False},
    # 批 4: 波动 (W)
    'W1_atr': {'category': 'W', 'status': 'tested_ic_only', 'a234': False},
    'W2_bb_width': {'category': 'W', 'status': 'tested_a234', 'a234': True, 'verdict': 'pass_top3'},
    'W3_hist_vol': {'category': 'W', 'status': 'tested_a234', 'a234': True, 'verdict': 'pass_top3'},
    'W4_rv': {'category': 'W', 'status': 'tested_a234', 'a234': True, 'verdict': 'pass_top3_best'},
    'W5_gk': {'category': 'W', 'status': 'tested_a234', 'a234': True, 'verdict': 'weak_a2'},
    'W6_kc': {'category': 'W', 'status': 'tested_a234', 'a234': True, 'verdict': 'weak_a2'},
    # 批 5: 反转/突破 (N+B)
    'N4_bb_lower': {'category': 'N', 'status': 'untested', 'a234': False},
    'N5_kdj_death': {'category': 'N', 'status': 'untested', 'a234': False},
    'N6_wr_reversal': {'category': 'N', 'status': 'untested', 'a234': False},
    'B2_new_high': {'category': 'B', 'status': 'untested', 'a234': False},
    'B3_consolidation_breakout': {'category': 'B', 'status': 'tested_a234', 'a234': True, 'verdict': 'weak_a2'},
    'B4_gap': {'category': 'B', 'status': 'untested', 'a234': False},
    # 批 6: 复合 (C)
    'C1_multi_factor_vote': {'category': 'C', 'status': 'untested', 'a234': False},
    'C2_weighted': {'category': 'C', 'status': 'tested_a234', 'a234': True, 'verdict': 'weak_a4_decay'},
    'C3_mom_reversal': {'category': 'C', 'status': 'untested', 'a234': False},
    'C4_trend_vol': {'category': 'C', 'status': 'untested', 'a234': False},
    'C5_vol_price_resonance': {'category': 'C', 'status': 'untested', 'a234': False},
    'C6_adaptive': {'category': 'C', 'status': 'untested', 'a234': False},
}


def inspect_factors():
    """检查所有因子脚本状态"""
    print("=" * 70)
    print("C 选项准备工作 - 28 因子状态检查")
    print("=" * 70)
    print()

    # 分类统计
    a234_done = [k for k, v in FACTORS_36.items() if v.get('a234')]
    a234_pending = [k for k, v in FACTORS_36.items() if not v.get('a234')]

    print(f"✅ A2/A3/A4 已验证: {len(a234_done)}/36 因子")
    for k in a234_done:
        v = FACTORS_36[k]
        print(f"  - {k}: {v.get('verdict', 'N/A')}")
    print()

    print(f"⏳ A2/A3/A4 待验证: {len(a234_pending)}/36 因子")
    categories = {}
    for k in a234_pending:
        cat = FACTORS_36[k]['category']
        categories.setdefault(cat, []).append(k)
    for cat, factors in sorted(categories.items()):
        print(f"  [{cat}] {len(factors)} 因子: {', '.join(factors)}")
    print()

    # 检查文件存在性
    print("📁 文件检查:")
    missing = []
    for k in FACTORS_36:
        # 文件名可能多个变体
        candidates = list(Path('scripts/experiment').glob(f'{k.split("_")[0]}*.py'))
        if not candidates:
            missing.append(k)
    if missing:
        print(f"  ❌ 缺失文件: {missing}")
    else:
        print(f"  ✅ 全部文件存在")
    print()

    # 估算时间（按 A2/A3/A4 实际耗时）
    print("⏱️ 估算时间（A2 + A3 + A4 跑全部 28 因子）:")
    print(f"  - 28 因子 × 5 min/因子 = 140 分钟（约 2.3 小时）")
    print(f"  - 实际可能 1.5-3 小时（看 WalkForward 性能）")
    print()

    # 输出建议
    print("=" * 70)
    print("💡 建议执行顺序")
    print("=" * 70)
    print()
    print("Step 1 (--mode inspect): 跑当前命令（本脚本）")
    print("Step 2 (--mode run): 跑 28 因子 IC 检验（先 fast 路径）")
    print("Step 3: 用 IC 检验结果筛选前 10")
    print("Step 4: 前 10 跑 A2 (15 ETF WalkForward)")
    print("Step 5: 前 3-5 跑 A4 (IS→OOS)")
    print("Step 6: 生成最终报告 data/US-026_36_factor_full_report.json")
    print()


def main():
    parser = argparse.ArgumentParser(description='US-026 C 选项 - 28 因子批量运行器')
    parser.add_argument('--mode', choices=['inspect', 'run', 'report'], default='inspect',
                        help='运行模式: inspect=检查, run=实际跑, report=报告')
    args = parser.parse_args()

    if args.mode == 'inspect':
        inspect_factors()
    elif args.mode == 'run':
        print("⚠️ 实际跑模式：会调用 28 个脚本的 main()，预计 2.3 小时")
        print("⏸️ 暂未实现（按用户'情做准备工作'原则）")
        print("💡 等用户确认后再实现 run 模式")
    elif args.mode == 'report':
        print("⚠️ report 模式：需要先跑 --mode run")
        print("💡 等用户确认后再实现 report 模式")


if __name__ == "__main__":
    main()
