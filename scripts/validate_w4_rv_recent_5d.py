#!/usr/bin/env python3
"""
W4 RV 最近 5 个交易日数据直接验证

按用户"用最近 5 个交易日的数据来直接验证"：
- 加载最近 5 个交易日（~1 周）
- 跑 W4 RV 因子
- 看 W4 RV 信号 + 5 日累计收益
- 与 W4 RV 预测（RV 放大 → 未来 5 日涨）对比

按"先调研，不要写新代码"：
- 复用 src/data/loader.py
- 复用 monitor_top3_volatility.py 的 compute_w4_rv
- 不写新监控，只写 1 个验证脚本
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, '/home/qwenpaw/.qwenpaw/workspaces/default/etf_strategy')

from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader
from scripts.monitoring.monitor_top3_volatility import compute_w4_rv


def main():
    print("=" * 70)
    print("W4 RV 最近 5 个交易日数据直接验证")
    print("=" * 70)

    loader = DataLoader()
    today = datetime.now()
    # 加载最近 365 天（1 年，确保 200+ 个交易日）
    start_date = (today - timedelta(days=365)).strftime('%Y-%m-%d')
    end_date = today.strftime('%Y-%m-%d')

    print(f"\n验证窗口: {start_date} ~ {end_date}")
    print(f"预期 5 个交易日: ~1 周")

    # 跑 15 ETF × 5 日验证
    results = []
    for code in CORE_ETF_POOL_15:
        try:
            all_data = loader.load(codes=[code])
            df = all_data.get(code)
            if df is None or df.empty:
                continue
            if 'date' in df.columns:
                df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
            if len(df) < 25:
                print(f"  ⚠️ {code}: 数据不足 25 行 ({len(df)} 行)")
                continue

            # 计算 W4 RV 信号
            df['_w4_rv_signal'] = compute_w4_rv(df).fillna(False).astype(int)
            df['_next_5d_return'] = df['close'].shift(-5) / df['close'] - 1

            # 取最近 5 个**有完整 5 日未来数据**的交易日（避免 NaN 污染）
            valid_future = df[df['_next_5d_return'].notna()].tail(5).copy()
            if len(valid_future) == 0:
                continue

            # W4 RV 信号触发率
            n_buy_signal = int(valid_future['_w4_rv_signal'].sum())
            # 5 日累计收益（如果当天买入）
            cum_return = float(np.prod([1 + r for r in valid_future['_next_5d_return']]) - 1)

            # W4 RV 触发日的平均未来 5 日收益（用有效数据日）
            trigger_days = valid_future[valid_future['_w4_rv_signal'] == 1]
            trigger_return = float(trigger_days['_next_5d_return'].mean()) if len(trigger_days) > 0 else np.nan

            results.append({
                'code': code,
                'n_days': len(df),
                'last_5_dates': [str(d)[:10] for d in valid_future['date'].tolist()],
                'n_buy_signal': n_buy_signal,
                'cum_5d_return': cum_return,
                'trigger_5d_return': trigger_return,
                'last_close': float(valid_future['close'].iloc[-1]),
            })
        except Exception as e:
            print(f"  ❌ {code}: {e}")

    # 报告
    print("\n" + "=" * 70)
    print("📊 W4 RV 最近 5 日验证结果（15 ETF）")
    print("=" * 70)
    print(f"{'代码':<10} {'信号数':<6} {'5d 累计收益':<12} {'触发日均收益':<12} {'最新收盘':<10}")
    print("-" * 70)
    for r in results:
        print(f"{r['code']:<10} {r['n_buy_signal']:<6} {r['cum_5d_return']*100:<11.2f}% {r['trigger_5d_return']*100 if not np.isnan(r['trigger_5d_return']) else 0:<11.2f}% {r['last_close']:<10.2f}")

    # 汇总
    n_etfs = len(results)
    avg_buy_signals = float(np.mean([r['n_buy_signal'] for r in results])) if results else 0
    avg_cum_return = float(np.mean([r['cum_5d_return'] for r in results])) if results else 0
    trigger_returns = [r['trigger_5d_return'] for r in results if not np.isnan(r['trigger_5d_return'])]
    avg_trigger_return = float(np.mean(trigger_returns)) if trigger_returns else 0
    n_profitable = sum(1 for r in results if r['cum_5d_return'] > 0)

    print("\n" + "=" * 70)
    print("💡 关键结论")
    print("=" * 70)
    print(f"验证 ETF 数: {n_etfs}/15")
    print(f"平均 W4 RV 信号数: {avg_buy_signals:.2f}/5 日")
    print(f"平均 5 日累计收益: {avg_cum_return*100:.2f}%")
    print(f"触发日均 5 日收益: {avg_trigger_return*100:.2f}%")
    print(f"5 日正收益 ETF 数: {n_profitable}/{n_etfs} ({n_profitable*100/n_etfs if n_etfs else 0:.0f}%)")

    # 验证 W4 RV 假设："信号触发 → 未来 5 日涨"
    print("\n" + "=" * 70)
    print("🔍 W4 RV 假设验证")
    print("=" * 70)
    if avg_trigger_return > 0 and avg_cum_return > 0:
        print(f"  ✅ 假设成立: W4 RV 触发 → 平均 5 日收益 {avg_trigger_return*100:.2f}% > 0")
        print(f"  ✅ 整体: 15 ETF 平均 5 日累计收益 {avg_cum_return*100:.2f}% > 0")
    elif avg_trigger_return > 0:
        print(f"  ⚠️ 部分成立: W4 RV 触发 → 收益 {avg_trigger_return*100:.2f}% > 0")
        print(f"  ⚠️ 但整体累计 {avg_cum_return*100:.2f}% {'>' if avg_cum_return > 0 else '<'} 0")
    else:
        print(f"  ❌ 假设不成立: 触发日均收益 {avg_trigger_return*100:.2f}% < 0")
        print(f"  ❌ 这是新发现！需要诚实标记")

    # 报告 JSON
    report_path = Path("data/W4_RV_recent_5d_validation.json")
    report_path.write_text(json.dumps({
        'verify_date': today.strftime('%Y-%m-%d'),
        'start_date': start_date,
        'end_date': end_date,
        'n_etfs': n_etfs,
        'avg_buy_signals': avg_buy_signals,
        'avg_cum_return': avg_cum_return,
        'avg_trigger_return': avg_trigger_return,
        'n_profitable': n_profitable,
        'detail': results,
    }, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(f"\n📄 报告: {report_path}")


if __name__ == "__main__":
    main()
