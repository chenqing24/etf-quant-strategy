#!/usr/bin/env python3
"""C14 移动止损（trailing stop）

按 L217 教训 C：固定 -12% 止损触发率仅 5%
测试最高价回撤 N% 平仓（N=5, 10, 15, 20）

实现：在持仓期间跟踪最高价，若现价 < 最高价 * (1 - N%) → 平仓
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
    START_DATE, END_DATE, RSI_BUY_THRESHOLD, RSI_SELL_THRESHOLD,
    TREND_FILTER_MA, WEIGHTS_TREND, WEIGHTS_RANGE,
    add_indicators, market_state, factor_score, buy_signal_state_aware, sell_signal, position_series
)

TRAILING_STOP_GRID = [None, 0.05, 0.10, 0.15, 0.20]


def run_with_trailing_stop(code: str, df: pd.DataFrame, min_n: int = 1,
                            trailing_pct: float = None) -> dict:
    """带移动止损的回测

    注：原生 BacktestConfig 不支持移动止损，需要用自定义逻辑：
    在因子反转卖出条件中追加"移动止损"
    """
    df = df[(df['date'] >= START_DATE) & (df['date'] <= END_DATE)].copy()
    if len(df) < 60:
        return {'code': code, 'skipped': True}

    df = add_indicators(df)

    # 自定义卖出：原因子反转 + 移动止损
    buy = buy_signal_state_aware(df, min_n)
    sell_factor = sell_signal(df)

    # 移动止损逻辑
    if trailing_pct is not None:
        position = pd.Series(0, index=df.index)
        holding = False
        entry_price = 0
        peak_price = 0
        for i in range(len(df)):
            price = df.iloc[i]['close']
            if not holding and buy.iloc[i] == 1:
                holding = True
                entry_price = price
                peak_price = price
                position.iloc[i] = 1
            elif holding:
                # 更新最高价
                if price > peak_price:
                    peak_price = price
                # 移动止损：现价 < 最高价 * (1 - trailing_pct)
                if price < peak_price * (1 - trailing_pct):
                    holding = False
                    position.iloc[i] = 0
                elif sell_factor.iloc[i] == 1:
                    holding = False
                    position.iloc[i] = 0
                else:
                    position.iloc[i] = 1
    else:
        position = position_series(df, weights=None, min_n=min_n) if False else None
        # 退回到普通 backtest（用 C11 函数）
        from scripts.experiment.C11_disable_max_hold import run_single as run_c11
        return run_c11(code, df, min_n)

    config = BacktestConfig(
        stop_loss=-0.12,
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
    print("C14 移动止损（trailing stop）")
    print("=" * 70)
    print(f"测试回撤阈值: {[f'{p:.0%}' if p else '无' for p in TRAILING_STOP_GRID]}")

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
    for ts in TRAILING_STOP_GRID:
        label = f"trailing={ts:.0%}" if ts else "无 trailing"
        print(f"\n  ▶ {label}")
        etf_results = []
        for code, df in all_data.items():
            r = run_with_trailing_stop(code, df, min_n=1, trailing_pct=ts)
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
            'trailing_stop': ts,
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
    print("📊 trailing stop 网格结果")
    print("=" * 70)
    print(df_r.to_string(index=False))

    best = df_r.loc[df_r['avg_winrate'].idxmax()]
    ts_label = f"{best['trailing_stop']:.0%}" if best['trailing_stop'] else "无"
    print(f"\n🏆 最佳: trailing={ts_label} | 胜率={best['avg_winrate']:.1%}")

    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/C14_trailing_stop.json", 'w', encoding='utf-8') as f:
        json.dump({
            'experiment': 'C14_trailing_stop',
            'best': best.to_dict(),
            'all_results': grid_results,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📁 报告: data/business_understanding/C14_trailing_stop.json")


if __name__ == "__main__":
    main()
