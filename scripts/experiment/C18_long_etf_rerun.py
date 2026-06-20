#!/usr/bin/env python3
"""C18 长数据 ETF 重跑所有实验

按 L220 + 用户要求：
- 剔除 < 5 年 ETF（保留 11 只长数据 ETF）
- 重跑 C11/C12/C13/C14/C16（关键实验）
- 验证 alpha 是否被高估

策略：C11 max_hold=99999 + 因子组合 + buy & hold 基准
"""
import sys
import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.loader import DataLoader
from scripts.experiment.LONG_ETFS import LONG_DATA_ETFS
from scripts.experiment.C9_market_state_v4 import (
    START_DATE, END_DATE, STOP_LOSS, RSI_BUY_THRESHOLD, RSI_SELL_THRESHOLD,
    TREND_FILTER_MA, WEIGHTS_TREND, WEIGHTS_RANGE,
    add_indicators, market_state, factor_score, buy_signal_state_aware, sell_signal, position_series
)
from scripts.experiment.C11_disable_max_hold import run_single as run_c11
from scripts.experiment.C16_single_factor import run_with_factor as run_factor


def buy_hold_single(code: str, df: pd.DataFrame) -> dict:
    df = df.sort_values('date').reset_index(drop=True)
    if df.empty:
        return {'code': code, 'skipped': True}
    start_price = df.iloc[0]['close']
    end_price = df.iloc[-1]['close']
    hold_days = (pd.to_datetime(df.iloc[-1]['date']) - pd.to_datetime(df.iloc[0]['date'])).days
    total_return = (end_price / start_price - 1) if start_price > 0 else 0
    return {
        'code': code,
        'bh_return': float(total_return),
        'hold_days': int(hold_days),
        'start_date': str(df.iloc[0]['date']),
        'end_date': str(df.iloc[-1]['date']),
    }


def main():
    print("=" * 70)
    print("C18 长数据 ETF 重跑（11 只 ≥5 年）")
    print("=" * 70)

    loader = DataLoader()
    print("\n📊 加载 11 只长数据 ETF...")
    all_data = {}
    for code in LONG_DATA_ETFS:
        d = loader.load(codes=[code]).get(code)
        if d is not None and not d.empty:
            all_data[code] = d
    print(f"  ETF: {len(all_data)}/11")

    # 显示数据范围
    for code in sorted(all_data.keys()):
        df = all_data[code]
        start = df['date'].min()
        end = df['date'].max()
        days = (pd.to_datetime(end) - pd.to_datetime(start)).days
        print(f"  {code}: {start} ~ {end} ({days/365:.1f} 年)")

    # 1. C11 重跑
    print("\n" + "=" * 70)
    print("📊 实验 1: C11 重跑（max_hold=99999）")
    print("=" * 70)
    c11_results = []
    for code, df in all_data.items():
        r = run_c11(code, df, min_n=1)
        if 'error' not in r and not r.get('skipped'):
            c11_results.append(r)
    c11_df = pd.DataFrame(c11_results)
    c11_avg = float(c11_df['total_return'].mean())
    c11_wr = float(c11_df['win_rate'].mean())
    c11_pos = float((c11_df['total_return'] > 0).mean())
    print(f"  ETF={len(c11_df)} | 收益={c11_avg:+.2%} | 胜率={c11_wr:.1%} | 正收益={c11_pos:.1%}")

    # 2. C12 buy & hold 基准
    print("\n" + "=" * 70)
    print("📊 实验 2: C12 buy & hold 基准")
    print("=" * 70)
    bh_results = []
    for code, df in all_data.items():
        r = buy_hold_single(code, df)
        if 'skipped' not in r:
            bh_results.append(r)
    bh_df = pd.DataFrame(bh_results)
    bh_avg = float(bh_df['bh_return'].mean())
    bh_pos = float((bh_df['bh_return'] > 0).mean())
    print(f"  ETF={len(bh_df)} | 收益={bh_avg:+.2%} | 正收益={bh_pos:.1%}")

    # 3. C12 alpha = C11 - buy & hold
    print("\n" + "=" * 70)
    print("📊 实验 3: C12 alpha 计算")
    print("=" * 70)
    merged = c11_df.merge(bh_df, on='code')
    if len(merged) > 0:
        merged['alpha'] = merged['total_return'] - merged['bh_return']
        alpha_mean = float(merged['alpha'].mean())
        alpha_pos = float((merged['alpha'] > 0).mean())
        alpha_std = float(merged['alpha'].std())

        # t 检验
        from scipy.stats import t as t_dist
        n = len(merged)
        t_stat = alpha_mean / (alpha_std / np.sqrt(n))
        p_val = 2 * (1 - t_dist.cdf(abs(t_stat), df=n-1))

        print(f"  配对 ETF: {n}")
        print(f"  C11 平均收益: {c11_avg:+.2%}")
        print(f"  buy & hold 平均: {bh_avg:+.2%}")
        print(f"  Alpha (C11-BH): {alpha_mean:+.2%}")
        print(f"  Alpha 标准差: {alpha_std:+.2%}")
        print(f"  Alpha t 统计: {t_stat:.3f}")
        print(f"  p 值: {p_val:.4f}")
        print(f"  Alpha ETF %: {alpha_pos:.1%}")

    # 4. C16 单因子（仅长数据 ETF）
    print("\n" + "=" * 70)
    print("📊 实验 4: C16 单因子（长数据 ETF）")
    print("=" * 70)
    factor_results = []
    for factor in ['none', 'ma5', 'rsi', 'obv', 'all']:
        etf_results = []
        for code, df in all_data.items():
            r = run_factor(code, df, factor)
            if 'error' not in r and not r.get('skipped'):
                etf_results.append(r)
        if not etf_results:
            continue
        etf_df = pd.DataFrame(etf_results)
        avg_ret = float(etf_df['total_return'].mean())
        avg_wr = float(etf_df['win_rate'].mean())
        pos = float((etf_df['total_return'] > 0).mean())
        factor_results.append({
            'factor': factor,
            'avg_return': avg_ret,
            'avg_winrate': avg_wr,
            'positive_pct': pos,
            'n': len(etf_df),
        })
        tag = '🟢' if avg_wr >= 0.5 and avg_ret > 0 else '🔴'
        print(f"  {tag} factor={factor:6s} | N={len(etf_df)} | 收益={avg_ret:+.2%} | 胜率={avg_wr:.1%} | 正收益={pos:.1%}")

    # 5. C13 max_hold_days 网格（长数据 ETF）
    print("\n" + "=" * 70)
    print("📊 实验 5: C13 max_hold_days 网格（长数据 ETF）")
    print("=" * 70)
    from src.backtest.engine import BacktestConfig, create_backtester

    def run_custom(code, df, max_hold):
        df = df[(df['date'] >= START_DATE) & (df['date'] <= END_DATE)].copy()
        if len(df) < 60:
            return {'code': code, 'skipped': True}
        df = add_indicators(df)
        sig = position_series(df, 1)
        config = BacktestConfig(
            stop_loss=STOP_LOSS, stop_profit=999,
            min_hold_days=3, max_hold_days=max_hold, max_positions=2,
        )
        backtester = create_backtester(config)

        def signal_func(d):
            return sig.reindex(d.index, fill_value=0).astype(bool)

        try:
            result = backtester.backtest(
                price_data={code: df}, signal_func=signal_func,
                benchmark_data=None, start_date=START_DATE, end_date=END_DATE,
            )
            return {
                'code': code,
                'total_return': float(result.total_return),
                'win_rate': float(result.win_rate),
            }
        except Exception as e:
            return {'code': code, 'error': str(e)}

    grid_results = []
    for mh in [99999, 60, 30, 10, 5]:
        etf_results = []
        for code, df in all_data.items():
            r = run_custom(code, df, mh)
            if 'error' not in r and not r.get('skipped'):
                etf_results.append(r)
        if not etf_results:
            continue
        etf_df = pd.DataFrame(etf_results)
        avg_ret = float(etf_df['total_return'].mean())
        avg_wr = float(etf_df['win_rate'].mean())
        grid_results.append({
            'max_hold_days': mh,
            'avg_return': avg_ret,
            'avg_winrate': avg_wr,
        })
        tag = '🟢' if avg_wr >= 0.5 and avg_ret > 0 else '🔴'
        print(f"  {tag} max_hold={mh:5d} | 收益={avg_ret:+.2%} | 胜率={avg_wr:.1%}")

    # 保存
    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/C18_long_etf_rerun.json", 'w', encoding='utf-8') as f:
        json.dump({
            'experiment': 'C18_long_etf_rerun',
            'n_etfs': len(LONG_DATA_ETFS),
            'c11': {
                'avg_return': c11_avg,
                'avg_winrate': c11_wr,
                'positive_pct': c11_pos,
                'n': len(c11_df),
            },
            'buy_hold': {
                'avg_return': bh_avg,
                'positive_pct': bh_pos,
                'n': len(bh_df),
            },
            'alpha': {
                'alpha_mean': alpha_mean,
                'alpha_std': alpha_std,
                't_stat': t_stat,
                'p_value': p_val,
                'alpha_positive_pct': alpha_pos,
            },
            'factor_results': factor_results,
            'max_hold_grid': grid_results,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📁 报告: data/business_understanding/C18_long_etf_rerun.json")


if __name__ == "__main__":
    main()
