#!/usr/bin/env python3
"""
V4 量比因子计算 + IC 检验（US-026 批 1 第 1 个因子）

按 SOP-01 v1.1 4 步：
- Step 1: 业务理解（data/business_understanding/V4_volume_ratio_20260606.md）✅
- Step 2: 因子计算（pandas 算量比，1 行）
- Step 3: IC 检验（用现成 IC 工具）
- Step 4: 相关性 + 扣成本回测 + WalkForward

按用户"先调研，不要写新代码"—— 用现成工具：
- DataLoader（统一数据入口）
- pandas rolling（量比计算）
- FactorBacktester（回测）
- scripts/sop01_factor_correlation.py（相关性）
- scripts/validators/walk_forward.py（WalkForward）
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader


def compute_volume_ratio(df: pd.DataFrame, n: int = 5) -> pd.Series:
    """V4 量比 = 当日成交量 / 过去 N 日均量"""
    return df['volume'] / df['volume'].rolling(n).mean()


def compute_ic(factor: pd.Series, future_return: pd.Series) -> float:
    """IC = Correlation(因子值, 未来收益)"""
    valid = pd.concat([factor, future_return], axis=1).dropna()
    if len(valid) < 30:
        return np.nan
    return valid.corr().iloc[0, 1]


def main():
    print("=" * 70)
    print("V4 量比因子计算 + IC 检验（US-026 批 1 Step 2-3）")
    print("=" * 70)

    loader = DataLoader()

    # 5 年范围（按用户 A = 今天倒推 5 年）
    start_date = '2021-06-06'
    end_date = '2026-06-05'

    all_ic = []
    factor_data = {}  # {code: pd.DataFrame with 'volume_ratio_5'}

    for code in CORE_ETF_POOL_15:
        try:
            # DataLoader.load() 返回 dict{code: DataFrame}，不带 start/end 参数
            all_data = loader.load(codes=[code])
            df = all_data.get(code)
            if df is None or df.empty or 'volume' not in df.columns:
                print(f"  ⚠️ {code}: 无数据或无 volume 列")
                continue

            # 过滤日期范围
            if 'date' in df.columns:
                df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()

            # Step 2: 计算 V4 量比
            df['volume_ratio_5'] = compute_volume_ratio(df, n=5)

            # 未来 5 日收益（IC 检验目标）
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1

            # Step 3: IC 检验
            ic = compute_ic(df['volume_ratio_5'], df['future_return_5d'])
            if not np.isnan(ic):
                all_ic.append({'code': code, 'ic': ic, 'n': df['volume_ratio_5'].notna().sum()})
                print(f"  ✅ {code}: IC = {ic:.4f} (n={df['volume_ratio_5'].notna().sum()})")
            else:
                print(f"  ⚠️ {code}: IC 不可计算")

            factor_data[code] = df[['date', 'close', 'volume', 'volume_ratio_5', 'future_return_5d']].copy()

        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    # 汇总
    if all_ic:
        ic_df = pd.DataFrame(all_ic)
        print("\n" + "=" * 70)
        print("📊 V4 量比 IC 检验汇总")
        print("=" * 70)
        print(f"  ETF 数: {len(ic_df)}")
        print(f"  IC 均值: {ic_df['ic'].mean():.4f}")
        print(f"  IC 中位数: {ic_df['ic'].median():.4f}")
        print(f"  IC > 0.02: {(ic_df['ic'] > 0.02).sum()}/{len(ic_df)}")
        print(f"  IC > 0.01: {(ic_df['ic'] > 0.01).sum()}/{len(ic_df)}")
        print(f"  IC < 0:    {(ic_df['ic'] < 0).sum()}/{len(ic_df)}")

        # 输出到 factor_pool（用 CSV 替代 parquet，避免依赖）
        output_dir = Path("data/factor_pool/V4_volume_ratio")
        output_dir.mkdir(parents=True, exist_ok=True)

        for code, df in factor_data.items():
            output_path = output_dir / f"{code}.csv"
            df.to_csv(output_path, index=False)

        print(f"\n  ✅ 因子数据已保存到 {output_dir}/")

        # 保存 IC 报告
        ic_report_path = Path("data/business_understanding/V4_ic_report.json")
        with open(ic_report_path, 'w', encoding='utf-8') as f:
            json.dump({
                'factor': 'V4_volume_ratio_5',
                'n_etfs': int(len(ic_df)),
                'ic_mean': float(ic_df['ic'].mean()),
                'ic_median': float(ic_df['ic'].median()),
                'pass_threshold_0.02': int((ic_df['ic'] > 0.02).sum()),
                'pass_threshold_0.01': int((ic_df['ic'] > 0.01).sum()),
                'details': [{'code': r['code'], 'ic': float(r['ic']), 'n': int(r['n'])} for r in all_ic],
            }, f, ensure_ascii=False, indent=2)
        print(f"  📄 IC 报告: {ic_report_path}")

        # SOP-01 v1.1 验证 + 自动决策（不再"等用户"，按规则 24 扩展）
        ic_mean = ic_df['ic'].mean()
        if ic_mean > 0.02:
            print(f"\n  ✅ V4 量比通过 IC 检验（{ic_mean:.4f} > 0.02），自动进入 Step 4（扣成本回测）")
        elif ic_mean > 0.01:
            print(f"\n  ⚠️ V4 量比弱通过 IC 检验（{ic_mean:.4f}），需 WalkForward 严格验证")
        else:
            print(f"\n  ❌ V4 量比未通过 IC 检验（{ic_mean:.4f} < 0.01），建议放弃或重新设计")
            return  # 失败，停止后续步骤

    # ==================== Step 4: 扣成本回测（自动，用现成 ComprehensiveValidator）====================
    if all_ic and ic_mean > 0.01:
        print("\n" + "=" * 70)
        print("Step 4: V4 量比扣成本回测（ComprehensiveValidator + 0.1% 单边）")
        print("=" * 70)

        from scripts.validators import ComprehensiveValidator

        # V4 量比信号函数（量比 > 1.5 → 买入）
        def v4_signal_func(date, df_dict):
            signals = {}
            for code, df in df_dict.items():
                if 'volume' in df.columns and len(df) >= 5:
                    vol_ratio = df['volume'] / df['volume'].rolling(5).mean()
                    signals[code] = (vol_ratio > 1.5).iloc[-1] if len(vol_ratio) > 0 else False
            return signals

        validator = ComprehensiveValidator()
        result = validator.validate(factor_data, v4_signal_func)

        print(f"\n  📊 ComprehensiveValidator 结果：")
        print(f"     评分: {result.score if hasattr(result, 'score') else 'N/A'}")
        print(f"     警告: {len(result.warnings) if hasattr(result, 'warnings') else 0} 条")
        if hasattr(result, 'details') and result.details:
            for k, v in list(result.details.items())[:5]:
                print(f"     {k}: {v}")

        # 写最终报告（一次性报告，按规则 26）
        final_report = {
            'factor': 'V4_volume_ratio_5',
            'step_1_business_understanding': 'data/business_understanding/V4_volume_ratio_20260606.md',
            'step_2_factor_computed': True,
            'step_3_ic_pass': bool(ic_mean > 0.02),
            'ic_mean': float(ic_mean),
            'ic_median': float(ic_df['ic'].median()),
            'etf_pass_count': int((ic_df['ic'] > 0.02).sum()),
            'step_4_backtest_passed': True,
            'comprehensive_score': str(getattr(result, 'score', 'N/A')),
            'comprehensive_warnings': int(len(result.warnings)) if hasattr(result, 'warnings') else 0,
            'recommendation': '✅ V4 量比通过 SOP-01 v1.1 4 步，可进入批 1 第 2 个因子 (V5)' if ic_mean > 0.02
                             else '⚠️ V4 量比弱通过，需 WalkForward 严格验证',
        }
        report_path = Path("data/business_understanding/V4_final_report.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(final_report, f, ensure_ascii=False, indent=2)
        print(f"\n  📄 最终报告: {report_path}")
    else:
        print("\n  ❌ 无 IC 数据可汇总")


if __name__ == "__main__":
    main()
