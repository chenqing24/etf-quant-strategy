#!/usr/bin/env python3
"""C16 单因子 alpha 分析

按 L215 教训：3 因子组合可能存在"因子冗余"
测试每个因子单独贡献 alpha：
- MA5 only
- RSI only
- OBV only
- 无因子（随机入场）
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
    add_indicators, market_state
)


def factor_signal(df: pd.DataFrame, factor: str = 'all') -> pd.Series:
    """单因子或多因子买入信号"""
    s = df.copy()
    s['s_ma5'] = (df['close'] > df['ma5']).astype(int)
    s['s_rsi'] = (df['rsi_14'] < RSI_BUY_THRESHOLD).astype(int)
    s['s_obv'] = (df['OBV'] > df['ma_obv_10']).astype(int)
    s['s_sum'] = s['s_ma5'] + s['s_rsi'] + s['s_obv']

    in_boll = (df['close'] >= df['BB_middle']) & (df['close'] <= df['BB_upper'])
    in_trend = (df['close'] > df[f'ma{TREND_FILTER_MA}'])

    if factor == 'all':
        return ((s['s_sum'] >= 2) & in_boll & in_trend).astype(int)
    elif factor == 'ma5':
        return (s['s_ma5'] & in_boll & in_trend).astype(int)
    elif factor == 'rsi':
        return (s['s_rsi'] & in_boll & in_trend).astype(int)
    elif factor == 'obv':
        return (s['s_obv'] & in_boll & in_trend).astype(int)
    elif factor == 'none':
        # 无因子，仅 BOLL + MA60 过滤
        return (in_boll & in_trend).astype(int)
    else:
        raise ValueError(factor)


def sell_signal_simple(df: pd.DataFrame) -> pd.Series:
    """简化卖出：仅趋势破 + RSI>70"""
    trend_break = df['close'] < df[f'ma{TREND_FILTER_MA}']
    sell_rsi = df['rsi_14'] > RSI_SELL_THRESHOLD
    return (trend_break | sell_rsi).astype(int)


def run_with_factor(code: str, df: pd.DataFrame, factor: str) -> dict:
    df = df[(df['date'] >= START_DATE) & (df['date'] <= END_DATE)].copy()
    if len(df) < 60:
        return {'code': code, 'skipped': True}

    df = add_indicators(df)
    buy = factor_signal(df, factor)
    sell = sell_signal_simple(df)

    position = pd.Series(0, index=df.index)
    holding = False
    for i in range(len(df)):
        if not holding and buy.iloc[i] == 1:
            holding = True
        elif holding and sell.iloc[i] == 1:
            holding = False
        position.iloc[i] = 1 if holding else 0

    config = BacktestConfig(
        stop_loss=STOP_LOSS,
        stop_profit=999,
        min_hold_days=3,
        max_hold_days=99999,
        max_positions=2,
    )
    backtester = create_backtester(config)

    def signal_func(d):
        return position.reindex(d.index, fill_value=0).astype(bool)

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
    print("C16 单因子 alpha 分析")
    print("=" * 70)

    loader = DataLoader()
    all_data = {}
    for code in ETF_POOL:
        try:
            d = loader.load(codes=[code]).get(code)
            if d is not None and not d.empty:
                all_data[code] = d
        except Exception:
            pass

    grid_results = []
    for factor in ['none', 'ma5', 'rsi', 'obv', 'all']:
        print(f"\n  ▶ factor={factor}")
        etf_results = []
        for code, df in all_data.items():
            r = run_with_factor(code, df, factor)
            if 'error' not in r and not r.get('skipped'):
                etf_results.append(r)
        if not etf_results:
            print(f"    ❌ 无数据")
            continue

        etf_df = pd.DataFrame(etf_results)
        avg_ret = float(etf_df['total_return'].mean())
        avg_wr = float(etf_df['win_rate'].mean())
        avg_dd = float(etf_df['max_drawdown'].mean())
        pos_pct = float((etf_df['total_return'] > 0).mean())
        total_trades = int(etf_df['trade_count'].sum())

        grid_results.append({
            'factor': factor,
            'avg_return': avg_ret,
            'avg_winrate': avg_wr,
            'avg_max_drawdown': avg_dd,
            'positive_etf_pct': pos_pct,
            'total_trades': total_trades,
        })
        tag = '🟢' if avg_wr >= 0.5 and avg_ret > 0 else '🔴'
        print(f"    {tag} 收益={avg_ret:+.2%} | 胜率={avg_wr:.1%} | 正收益%={pos_pct:.1%} | 交易={total_trades}")

    df_r = pd.DataFrame(grid_results)
    print("\n" + "=" * 70)
    print("📊 单因子结果")
    print("=" * 70)
    print(df_r.to_string(index=False))

    best = df_r.loc[df_r['avg_winrate'].idxmax()]
    print(f"\n🏆 最佳因子: {best['factor']} | 胜率={best['avg_winrate']:.1%}")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/C16_single_factor.json", 'w', encoding='utf-8') as f:
        json.dump({
            'experiment': 'C16_single_factor',
            'best': best.to_dict(),
            'all_results': grid_results,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📁 报告: data/business_understanding/C16_single_factor.json")


if __name__ == "__main__":
    main()
