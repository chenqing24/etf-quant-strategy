#!/usr/bin/env python3
"""C11 关闭到期平仓（修复 L216 模式 A）

按 L216 教训：
- C9 实验 93.2% 亏损来自到期平仓（max_hold_days=20）
- 修复：max_hold_days=99999（关闭到期平仓）
- 持仓只通过因子反转卖出（close<MA5 OR RSI>60 OR OBV<MAOBV OR close<MA60）

预期：胜率应显著提升（不再被 20 天强制平仓伤害）
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
from src.indicators.bollinger import calculate_bollinger_bands
from src.indicators.obv import calculate_obv
from src.indicator import Indicator
from src.backtest.engine import BacktestConfig, create_backtester
from scripts.experiment.C9_market_state_v4 import (
    START_DATE, END_DATE, STOP_LOSS, RSI_BUY_THRESHOLD, RSI_SELL_THRESHOLD,
    TREND_FILTER_MA, WEIGHTS_TREND, WEIGHTS_RANGE,
    add_indicators, market_state, factor_score, buy_signal_state_aware, sell_signal, position_series
)


# ============================================================
# 配置（修复：关闭到期平仓）
# ============================================================

# L216 修复 A：max_hold_days 20 → 99999（关闭到期平仓）
MAX_HOLD_DAYS_DISABLED = 99999


def run_single(code: str, df: pd.DataFrame, min_n: int) -> dict:
    """单只 ETF 回测（max_hold_days=99999 = 关闭到期平仓）"""
    df = df[(df['date'] >= START_DATE) & (df['date'] <= END_DATE)].copy()
    if len(df) < 60:
        return {'code': code, 'skipped': True}

    df = add_indicators(df)
    sig = position_series(df, min_n)

    config = BacktestConfig(
        stop_loss=STOP_LOSS,
        stop_profit=999,            # 无止盈
        min_hold_days=3,
        max_hold_days=MAX_HOLD_DAYS_DISABLED,  # 关闭到期平仓
        max_positions=2,
    )
    backtester = create_backtester(config)

    def signal_func(d):
        return sig.reindex(d.index, fill_value=0).astype(bool)

    try:
        result = backtester.backtest(
            price_data={code: df},
            signal_func=signal_func,
            benchmark_data=None,
            start_date=START_DATE,
            end_date=END_DATE,
        )
        return {
            'code': code,
            'total_return': float(result.total_return),
            'annual_return': float(result.annual_return),
            'max_drawdown': float(result.max_drawdown),
            'win_rate': float(result.win_rate),
            'trade_count': int(result.trade_count),
        }
    except Exception as e:
        return {'code': code, 'error': f'{type(e).__name__}: {e}'}


def main():
    print("=" * 70)
    print("C11 关闭到期平仓（修复 L216 模式 A）")
    print("=" * 70)
    print(f"修复：max_hold_days 20 → {MAX_HOLD_DAYS_DISABLED}（sentinel 关闭）")
    print(f"5 年回测 ({START_DATE} ~ {END_DATE})")

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

    print("\n📊 min_n 网格")
    results = []
    for min_n in [1, 2]:
        print(f"\n  ▶ min_n={min_n}")
        etf_results = []
        for code, df in all_data.items():
            r = run_single(code, df, min_n)
            if 'error' not in r and not r.get('skipped'):
                etf_results.append(r)

        if not etf_results:
            print(f"    ❌ 无有效回测")
            continue

        etf_df = pd.DataFrame(etf_results)
        avg_ret = float(etf_df['total_return'].mean())
        avg_wr = float(etf_df['win_rate'].mean())
        avg_dd = float(etf_df['max_drawdown'].mean())
        pos_pct = float((etf_df['total_return'] > 0).mean())
        total_trades = int(etf_df['trade_count'].sum())

        results.append({
            'min_n': min_n,
            'avg_return': avg_ret,
            'avg_winrate': avg_wr,
            'avg_max_drawdown': avg_dd,
            'positive_etf_pct': pos_pct,
            'total_trades': total_trades,
            'etf_count': len(etf_df),
        })

        tag = '🟢' if avg_wr >= 0.5 and avg_ret > 0 else '🔴'
        print(f"    {tag} ETF={len(etf_df)} | 收益={avg_ret:+.2%} | 胜率={avg_wr:.1%} | "
              f"正收益%={pos_pct:.1%} | 交易={total_trades}")

    if not results:
        print("\n❌ 无有效结果")
        return

    df_r = pd.DataFrame(results)
    print("\n" + "=" * 70)
    print("📊 vs C9 对比（关闭到期平仓）")
    print("=" * 70)
    print(df_r.to_string(index=False))

    best = df_r.loc[df_r['avg_winrate'].idxmax()]
    print(f"\n🏆 最佳: min_n={int(best['min_n'])} | 胜率={best['avg_winrate']:.1%} | 收益={best['avg_return']:+.2%}")

    # vs C9 对比
    c9_baseline = {'min_n=1': 27.6, 'min_n=2': 26.5}  # C9 结果
    print(f"\n✅ 验收（vs C9 基线）")
    print(f"  C9 min_n=1 胜率: 27.6%")
    print(f"  C9 min_n=2 胜率: 26.5%")
    print(f"  C11 min_n=1 胜率: {results[0]['avg_winrate']:.1%}")
    print(f"  C11 min_n=2 胜率: {results[1]['avg_winrate']:.1%}" if len(results) > 1 else "  C11 min_n=2: N/A")
    print()
    for r in results:
        mn = int(r['min_n'])
        base = c9_baseline[f'min_n={mn}']
        delta = r['avg_winrate'] * 100 - base
        print(f"  min_n={mn}: {'+' if delta > 0 else ''}{delta:.1f}pp (vs C9)")

    # 保存报告
    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/C11_disable_max_hold_report.json", 'w', encoding='utf-8') as f:
        json.dump({
            'experiment': 'C11_disable_max_hold',
            'fix': f'max_hold_days 20 → {MAX_HOLD_DAYS_DISABLED}',
            'l216_pattern_fixed': 'A. 到期平仓 (93.2%)',
            'start_date': START_DATE,
            'end_date': END_DATE,
            'best': best.to_dict(),
            'all_results': results,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📁 报告: data/business_understanding/C11_disable_max_hold_report.json")


if __name__ == "__main__":
    main()
