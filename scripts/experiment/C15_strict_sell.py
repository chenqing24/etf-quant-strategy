#!/usr/bin/env python3
"""C15 因子反转条件加强

按 L215 改进方向：任一因子反转 → 必须全部反转才卖出？
测试模式：
- 原始 (任一): 任一因子反向即卖
- 严格 (全部): 全部因子反向才卖
- 半数: 至少 2/3 因子反向才卖
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
    add_indicators, market_state, factor_score, buy_signal_state_aware
)


def sell_signal_strict(df: pd.DataFrame, mode: str = 'any') -> pd.Series:
    """卖出条件

    mode='any': 任一反向即卖（原始）
    mode='all': 全部反向才卖
    mode='majority': 至少 2/3 反向才卖
    """
    s = factor_score(df)
    # 反向条件
    sell_ma5 = df['close'] < df['ma5']
    sell_rsi = df['rsi_14'] > RSI_SELL_THRESHOLD
    sell_obv = df['OBV'] < df['ma_obv_10']
    trend_break = df['close'] < df[f'ma{TREND_FILTER_MA}']
    reverse_count = sell_ma5.astype(int) + sell_rsi.astype(int) + sell_obv.astype(int) + trend_break.astype(int)

    if mode == 'any':
        return (sell_ma5 | sell_rsi | sell_obv | trend_break).astype(int)
    elif mode == 'all':
        return ((~sell_ma5) & (~sell_rsi) & (~sell_obv) & (~trend_break)).astype(int) == False
        # 全部反向 = 全 True → 注意全反向是 sell
        return ((sell_ma5 & sell_rsi & sell_obv & trend_break)).astype(int)
    elif mode == 'majority':
        return (reverse_count >= 2).astype(int)
    else:
        raise ValueError(f"unknown mode {mode}")


def position_series(df: pd.DataFrame, min_n: int, sell_mode: str) -> pd.Series:
    buy = buy_signal_state_aware(df, min_n)
    sell = sell_signal_strict(df, sell_mode)
    position = pd.Series(0, index=df.index)
    holding = False
    for i in range(len(df)):
        if not holding and buy.iloc[i] == 1:
            holding = True
        elif holding and sell.iloc[i] == 1:
            holding = False
        position.iloc[i] = 1 if holding else 0
    return position.astype(float)


def run_single(code: str, df: pd.DataFrame, min_n: int, sell_mode: str) -> dict:
    df = df[(df['date'] >= START_DATE) & (df['date'] <= END_DATE)].copy()
    if len(df) < 60:
        return {'code': code, 'skipped': True}

    df = add_indicators(df)
    sig = position_series(df, min_n, sell_mode)

    config = BacktestConfig(
        stop_loss=STOP_LOSS,
        stop_profit=999,
        min_hold_days=3,
        max_hold_days=99999,
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
    print("C15 因子反转条件加强")
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
    for mode in ['any', 'majority', 'all']:
        print(f"\n  ▶ sell_mode={mode}")
        etf_results = []
        for code, df in all_data.items():
            r = run_single(code, df, min_n=1, sell_mode=mode)
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
            'sell_mode': mode,
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
    print("📊 卖出模式网格结果")
    print("=" * 70)
    print(df_r.to_string(index=False))

    best = df_r.loc[df_r['avg_winrate'].idxmax()]
    print(f"\n🏆 最佳: mode={best['sell_mode']} | 胜率={best['avg_winrate']:.1%}")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/C15_strict_sell.json", 'w', encoding='utf-8') as f:
        json.dump({
            'experiment': 'C15_strict_sell',
            'best': best.to_dict(),
            'all_results': grid_results,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📁 报告: data/business_understanding/C15_strict_sell.json")


if __name__ == "__main__":
    main()
