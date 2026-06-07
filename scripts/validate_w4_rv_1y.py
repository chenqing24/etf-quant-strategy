#!/usr/bin/env python3
"""
W4 RV 1 年窗口验证（按用户 B 指令）

按用户"看更长窗口（1 年）"：
- 跑 1 年内**所有** W4 RV 触发信号
- 计算触发信号的平均未来 5 日收益
- 报告触发率 + 累计收益

按"先调研，不要写新代码"：
- 复用 src/data/loader.py
- 复用 compute_w4_rv
- 不写新监控
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

sys.path.insert(0, '/home/qwenpaw/.qwenpaw/workspaces/default/etf_strategy')

from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader
from scripts.monitoring.monitor_top3_volatility import compute_w4_rv


def main():
    print("=" * 70)
    print("W4 RV 1 年窗口验证（跑 1 年内所有触发信号）")
    print("=" * 70)

    loader = DataLoader()
    today = datetime.now()
    start_date = (today - timedelta(days=365)).strftime('%Y-%m-%d')

    print(f"\n验证窗口: {start_date} ~ {today.strftime('%Y-%m-%d')}")

    # 跑 15 ETF × 1 年验证
    results = []
    for code in CORE_ETF_POOL_15:
        try:
            all_data = loader.load(codes=[code])
            df = all_data.get(code)
            if df is None or df.empty:
                continue
            if 'date' in df.columns:
                df = df[(df['date'] >= start_date)].copy()
            if len(df) < 100:
                print(f"  ⚠️ {code}: 数据不足 100 行 ({len(df)} 行)")
                continue

            # 计算 W4 RV 信号
            df['_w4_rv_signal'] = compute_w4_rv(df).fillna(False).astype(int)
            df['_next_5d_return'] = df['close'].shift(-5) / df['close'] - 1

            # 1 年内**所有**触发信号（不去最后 5 天）
            trigger_days = df[(df['_w4_rv_signal'] == 1) & (df['_next_5d_return'].notna())]
            all_days_valid = df[df['_next_5d_return'].notna()]

            n_triggers = len(trigger_days)
            n_total = len(all_days_valid)
            trigger_rate = n_triggers / n_total if n_total > 0 else 0
            trigger_return_mean = float(trigger_days['_next_5d_return'].mean()) if n_triggers > 0 else np.nan
            baseline_return_mean = float(all_days_valid['_next_5d_return'].mean()) if n_total > 0 else np.nan
            # 触发信号的累计收益（如果每次信号都买入）
            cum_return = float(np.prod([1 + r for r in trigger_days['_next_5d_return']]) - 1) if n_triggers > 0 else 0

            results.append({
                'code': code,
                'n_days': len(df),
                'n_triggers': n_triggers,
                'n_total': n_total,
                'trigger_rate': trigger_rate,
                'trigger_return_mean': trigger_return_mean,
                'baseline_return_mean': baseline_return_mean,
                'trigger_cum_return': cum_return,
                'last_close': float(df['close'].iloc[-1]),
            })
        except Exception as e:
            print(f"  ❌ {code}: {e}")

    # 报告
    print("\n" + "=" * 70)
    print("📊 W4 RV 1 年验证结果（15 ETF × 1 年内所有信号）")
    print("=" * 70)
    print(f"{'代码':<10} {'触发数':<6} {'总日数':<6} {'触发率':<7} {'触发日均':<10} {'基准日均':<10} {'累计收益':<10}")
    print("-" * 80)
    for r in results:
        print(f"{r['code']:<10} {r['n_triggers']:<6} {r['n_total']:<6} {r['trigger_rate']*100:<6.1f}% {r['trigger_return_mean']*100:<9.2f}% {r['baseline_return_mean']*100:<9.2f}% {r['trigger_cum_return']*100:<9.2f}%")

    # 汇总
    n_etfs = len(results)
    total_triggers = sum(r['n_triggers'] for r in results)
    total_days = sum(r['n_total'] for r in results)
    avg_trigger_rate = total_triggers / total_days if total_days > 0 else 0
    trigger_returns = [r['trigger_return_mean'] for r in results if not np.isnan(r['trigger_return_mean'])]
    avg_trigger_return = float(np.mean(trigger_returns)) if trigger_returns else 0
    n_profitable = sum(1 for r in results if r['trigger_return_mean'] > 0)
    n_above_baseline = sum(1 for r in results if r['trigger_return_mean'] > r['baseline_return_mean'])

    print("\n" + "=" * 70)
    print("💡 关键结论（1 年内所有 W4 RV 触发信号）")
    print("=" * 70)
    print(f"ETF 数: {n_etfs}/15")
    print(f"总触发数: {total_triggers}/{total_days} = {avg_trigger_rate*100:.1f}%")
    print(f"平均触发日均 5 日收益: {avg_trigger_return*100:.2f}%")
    print(f"正收益 ETF: {n_profitable}/{n_etfs} ({n_profitable*100/n_etfs if n_etfs else 0:.0f}%)")
    print(f"高于基准 ETF: {n_above_baseline}/{n_etfs} ({n_above_baseline*100/n_etfs if n_etfs else 0:.0f}%)")

    # 验证 W4 RV 假设
    print("\n" + "=" * 70)
    print("🔍 W4 RV 假设验证（1 年窗口）")
    print("=" * 70)
    avg_baseline = float(np.mean([r['baseline_return_mean'] for r in results]))
    print(f"  基准日均 5 日收益: {avg_baseline*100:.2f}%")
    if avg_trigger_return > avg_baseline and avg_trigger_return > 0:
        print(f"  ✅ 假设成立: 触发 {avg_trigger_return*100:.2f}% > 基准 {avg_baseline*100:.2f}%")
    elif avg_trigger_return > 0:
        print(f"  ⚠️ 部分成立: 触发 {avg_trigger_return*100:.2f}% > 0 但 < 基准 {avg_baseline*100:.2f}%")
    else:
        print(f"  ❌ 假设不成立: 触发 {avg_trigger_return*100:.2f}% < 0 (基准 {avg_baseline*100:.2f}%)")
        print(f"  ❌ 这与 US-026 验证矛盾！W4 RV 在最近 1 年 = 反向指标")

    # 报告 JSON
    report_path = Path("data/W4_RV_1y_validation.json")
    report_path.write_text(json.dumps({
        'verify_date': today.strftime('%Y-%m-%d'),
        'start_date': start_date,
        'n_etfs': n_etfs,
        'total_triggers': total_triggers,
        'total_days': total_days,
        'avg_trigger_rate': avg_trigger_rate,
        'avg_trigger_return': avg_trigger_return,
        'avg_baseline': avg_baseline,
        'n_profitable': n_profitable,
        'n_above_baseline': n_above_baseline,
        'detail': results,
    }, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(f"\n📄 报告: {report_path}")


if __name__ == "__main__":
    main()
