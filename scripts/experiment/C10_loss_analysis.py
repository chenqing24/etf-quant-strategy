#!/usr/bin/env python3
"""C10 失败交易分析（基于 C9 实验）

目标：分析 C9 实验中所有亏损交易，按多维度分类：
1. 盈亏分布
2. exit_reason 分布
3. 持仓时长分布
4. 市场状态分布（入场时 close vs MA60）
"""
import sys
import json
import warnings
from pathlib import Path
from collections import Counter, defaultdict

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


def run_single_collect_trades(code: str, df: pd.DataFrame, min_n: int) -> list:
    """跑单只 ETF 回测，返回所有 trades（含亏损）"""
    df = df[(df['date'] >= START_DATE) & (df['date'] <= END_DATE)].copy()
    if len(df) < 60:
        return []

    df = add_indicators(df)
    sig = position_series(df, min_n)

    config = BacktestConfig(
        stop_loss=STOP_LOSS,
        stop_profit=999,
        min_hold_days=3,
        max_hold_days=20,
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
        return result.trades if hasattr(result, 'trades') else []
    except Exception as e:
        return []


def categorize_trade(trade: dict, market_state_at_entry: str) -> dict:
    """给每笔交易打多个标签"""
    pnl = trade.get('pnl_pct', 0)
    hold = trade.get('hold_days', 0)
    reason = trade.get('exit_reason', 'unknown')

    return {
        'pnl_pct': pnl,
        'is_win': pnl > 0,
        'is_loss': pnl < 0,
        'exit_reason': reason,
        'hold_days': hold,
        'hold_bucket': (
            '<3天' if hold < 3 else
            '3-7天' if hold <= 7 else
            '8-20天' if hold <= 20 else
            '>20天'
        ),
        'market_state_at_entry': market_state_at_entry,  # trend / range
    }


def main():
    print("=" * 70)
    print("C10 失败交易深度分析")
    print("=" * 70)
    print(f"基于 C9 实验（min_n=1 + 5年 + MA60 + 状态切换）")

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

    print("\n📊 收集所有交易（min_n=1）...")
    all_trades = []
    for code, df in all_data.items():
        trades = run_single_collect_trades(code, df, min_n=1)
        for t in trades:
            # 计算入场时的市场状态
            df_full = df[(df['date'] >= START_DATE) & (df['date'] <= END_DATE)]
            df_full = add_indicators(df_full)
            entry_date = t.get('entry_date')
            entry_row = df_full[df_full['date'] == entry_date]
            if not entry_row.empty:
                state_val = (entry_row.iloc[0]['close'] > entry_row.iloc[0][f'ma{TREND_FILTER_MA}'])
                market_state_at_entry = 'trend' if state_val else 'range'
            else:
                market_state_at_entry = 'unknown'
            t['market_state_at_entry'] = market_state_at_entry
            all_trades.append(t)

    if not all_trades:
        print("❌ 无交易")
        return

    print(f"  总交易数: {len(all_trades)}")

    # 分类
    categorized = [categorize_trade(t, t.get('market_state_at_entry', 'unknown')) for t in all_trades]
    df_t = pd.DataFrame(categorized)

    # ============================================================
    # 1. 盈亏分布
    # ============================================================
    print("\n" + "=" * 70)
    print("📊 1. 盈亏分布")
    print("=" * 70)
    wins = df_t['is_win'].sum()
    losses = df_t['is_loss'].sum()
    flat = len(df_t) - wins - losses
    print(f"  盈利: {wins} ({wins/len(df_t):.1%})")
    print(f"  亏损: {losses} ({losses/len(df_t):.1%})")
    print(f"  平局: {flat} ({flat/len(df_t):.1%})")
    print(f"  平均盈利: {df_t.loc[df_t['is_win'], 'pnl_pct'].mean():+.2%}" if wins > 0 else "  平均盈利: N/A")
    print(f"  平均亏损: {df_t.loc[df_t['is_loss'], 'pnl_pct'].mean():+.2%}" if losses > 0 else "  平均亏损: N/A")

    # ============================================================
    # 2. exit_reason 分布（仅亏损）
    # ============================================================
    print("\n" + "=" * 70)
    print("📊 2. 亏损交易的 exit_reason 分布")
    print("=" * 70)
    losses_df = df_t[df_t['is_loss']]
    if len(losses_df) > 0:
        reason_counts = losses_df['exit_reason'].value_counts()
        reason_pnl = losses_df.groupby('exit_reason')['pnl_pct'].agg(['count', 'mean', 'sum']).sort_values('sum')
        print(f"  {'exit_reason':<15} {'笔数':<8} {'占比':<10} {'平均亏损':<12} {'累计亏损':<12}")
        for reason, row in reason_pnl.iterrows():
            cnt = int(row['count'])
            pct = cnt / len(losses_df)
            print(f"  {reason:<15} {cnt:<8} {pct:.1%}{'':5} {row['mean']:+.2%}{'':5} {row['sum']:+.2%}")
    else:
        print("  无亏损")

    # ============================================================
    # 3. 持仓时长分布（仅亏损）
    # ============================================================
    print("\n" + "=" * 70)
    print("📊 3. 亏损交易的持仓时长分布")
    print("=" * 70)
    if len(losses_df) > 0:
        hold_counts = losses_df.groupby('hold_bucket').size().sort_index()
        hold_pnl = losses_df.groupby('hold_bucket')['pnl_pct'].agg(['count', 'mean'])
        print(f"  {'持仓时长':<12} {'笔数':<8} {'占比':<10} {'平均亏损':<12}")
        for bucket, cnt in hold_counts.items():
            pct = cnt / len(losses_df)
            mean_loss = hold_pnl.loc[bucket, 'mean']
            print(f"  {bucket:<12} {cnt:<8} {pct:.1%}{'':5} {mean_loss:+.2%}")
    else:
        print("  无亏损")

    # ============================================================
    # 4. 市场状态分布（入场时）
    # ============================================================
    print("\n" + "=" * 70)
    print("📊 4. 入场时市场状态分布（全部交易）")
    print("=" * 70)
    state_counts = df_t['market_state_at_entry'].value_counts()
    state_pnl = df_t.groupby('market_state_at_entry')['pnl_pct'].agg(['count', 'mean', 'sum'])
    print(f"  {'市场状态':<10} {'总笔数':<8} {'亏损笔数':<10} {'亏损占比':<10} {'平均盈亏':<12} {'累计盈亏':<12}")
    for state, cnt in state_counts.items():
        loss_in_state = ((df_t['market_state_at_entry'] == state) & df_t['is_loss']).sum()
        loss_rate = loss_in_state / cnt
        mean_pnl = state_pnl.loc[state, 'mean']
        sum_pnl = state_pnl.loc[state, 'sum']
        print(f"  {state:<10} {cnt:<8} {loss_in_state:<10} {loss_rate:.1%}{'':5} {mean_pnl:+.2%}{'':5} {sum_pnl:+.2%}")

    # ============================================================
    # 5. 交叉分析：exit_reason × 市场状态
    # ============================================================
    print("\n" + "=" * 70)
    print("📊 5. 交叉分析：亏损 exit_reason × 入场市场状态")
    print("=" * 70)
    if len(losses_df) > 0:
        cross = losses_df.groupby(['market_state_at_entry', 'exit_reason']).size().unstack(fill_value=0)
        print(cross.to_string())

    # ============================================================
    # 6. ETF 维度（哪些 ETF 贡献最多亏损）
    # ============================================================
    print("\n" + "=" * 70)
    print("📊 6. 亏损 ETF TOP 10（贡献最多亏损）")
    print("=" * 70)
    if len(losses_df) > 0:
        # 加回 code 字段
        losses_with_code = pd.DataFrame([t for t in all_trades if t.get('pnl_pct', 0) < 0])
        if not losses_with_code.empty:
            etf_loss = losses_with_code.groupby('code')['pnl_pct'].agg(['count', 'sum']).sort_values('sum').head(10)
            print(f"  {'ETF':<10} {'亏损笔数':<10} {'累计亏损':<12}")
            for code, row in etf_loss.iterrows():
                print(f"  {code:<10} {int(row['count']):<10} {row['sum']:+.2%}")

    # ============================================================
    # 保存详细数据
    # ============================================================
    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    df_t['_raw'] = all_trades  # 保留原始 trade dict
    summary = {
        'experiment_base': 'C9',
        'total_trades': len(all_trades),
        'wins': int(wins),
        'losses': int(losses),
        'flat': int(flat),
        'exit_reason_loss_count': losses_df['exit_reason'].value_counts().to_dict() if len(losses_df) > 0 else {},
        'hold_bucket_loss_count': losses_df['hold_bucket'].value_counts().to_dict() if len(losses_df) > 0 else {},
        'state_loss_count': losses_df['market_state_at_entry'].value_counts().to_dict() if len(losses_df) > 0 else {},
    }
    with open("data/business_understanding/C10_loss_analysis.json", 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    # 保存完整 trades
    pd.DataFrame(all_trades).to_csv("data/business_understanding/C10_all_trades.csv", index=False)

    print(f"\n📁 报告: data/business_understanding/C10_loss_analysis.json")
    print(f"📁 明细: data/business_understanding/C10_all_trades.csv ({len(all_trades)} 笔)")


if __name__ == "__main__":
    main()
