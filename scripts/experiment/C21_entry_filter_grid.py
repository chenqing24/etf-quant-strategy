#!/usr/bin/env python3
"""C21 S4 简化版入场过滤网格（基于 C20 真相）

按 L225 + C20（alpha 来源分解）：
- S4 无 sell = 真正最优策略（alpha +47.79%）
- S4 机制：入场过滤（BOLL+MA60）+ 永远满仓
- 本实验测试入场过滤网格，找最优参数

入场过滤网格：
1. BOLL 位置（close vs BOLL）
   - 中轨及以上 (close >= BOLL_middle)
   - 中上轨 (BOLL_middle <= close <= BOLL_upper)
   - 严格中轨 (close == BOLL_middle ± 0.5%)
2. MA 周期（MA60 / MA120 / MA250）
3. 趋势过滤（close > MA AND MA 上升）

控制变量：
- 卖出 = 永远不卖（仅 max_hold=99999）
- ETF 池 = 11 长数据 ETF（C18 验证）
- 数据范围 = 各 ETF 实际可用数据

预期：
- BOLL + MA 严格过滤 → alpha 可能更高
- 简单过滤 > 复杂过滤
"""
import sys
import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.loader import DataLoader
from scripts.experiment.LONG_ETFS import LONG_DATA_ETFS
from scripts.experiment.C9_market_state_v4 import (
    START_DATE, END_DATE, STOP_LOSS, RSI_BUY_THRESHOLD, RSI_SELL_THRESHOLD,
    add_indicators,
)
from scripts.experiment.C20_alpha_decomposition import (
    buy_hold_only, make_position, sell_signal_none,
)
from src.backtest.engine import BacktestConfig, create_backtester


# ============================================================
# 入场过滤网格
# ============================================================

def entry_boll_ma(df: pd.DataFrame, boll_mode: str, ma_period: int) -> pd.Series:
    """入场信号：BOLL + MA 趋势过滤

    Args:
        df: 包含 BOLL 和 MA 指标的 DataFrame
        boll_mode: 'middle' (中轨及以上) / 'middle_upper' (中上轨) / 'strict_middle' (严格中轨)
        ma_period: 60 / 120 / 250
    """
    # ma250 需要单独计算（Indicator.calculate 不提供）
    if ma_period == 250 and 'ma250' not in df.columns:
        df = df.copy()
        df['ma250'] = df['close'].rolling(250).mean()
    ma_col = f'ma{ma_period}' if ma_period != 250 else 'ma250'
    if ma_col not in df.columns:
        raise KeyError(f"MA column not found: {ma_col}")

    in_ma = df['close'] > df[ma_col]

    if boll_mode == 'middle':
        in_boll = df['close'] >= df['BB_middle']
    elif boll_mode == 'middle_upper':
        in_boll = (df['close'] >= df['BB_middle']) & (df['close'] <= df['BB_upper'])
    elif boll_mode == 'strict_middle':
        # 严格中轨 ±0.5%
        diff_pct = (df['close'] - df['BB_middle']) / df['BB_middle']
        in_boll = diff_pct.abs() <= 0.005
    elif boll_mode == 'lower_upper':
        # 下轨到上轨（更宽松）
        in_boll = (df['close'] >= df['BB_lower']) & (df['close'] <= df['BB_upper'])
    else:
        raise ValueError(f"Unknown boll_mode: {boll_mode}")

    return (in_boll & in_ma).astype(int)


# 入场过滤组合
ENTRY_FILTERS = []
for boll in ['middle', 'middle_upper', 'strict_middle', 'lower_upper']:
    for ma in [60, 120, 250]:
        ENTRY_FILTERS.append((f'BOLL_{boll}+MA{ma}', boll, ma))


def run_filter(code: str, df: pd.DataFrame, boll_mode: str, ma_period: int) -> dict:
    df = df[(df['date'] >= START_DATE) & (df['date'] <= END_DATE)].copy()
    if len(df) < 60:
        return {'code': code, 'skipped': True}

    df = add_indicators(df)
    buy = entry_boll_ma(df, boll_mode, ma_period)
    sell = sell_signal_none(df)
    pos = make_position(buy, sell)

    config = BacktestConfig(
        stop_loss=STOP_LOSS,
        stop_profit=999,
        min_hold_days=3,
        max_hold_days=99999,
        max_positions=2,
    )
    backtester = create_backtester(config)

    def signal_func(d):
        return pos.reindex(d.index, fill_value=0).astype(bool)

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
    print("C21 S4 简化版入场过滤网格")
    print("=" * 70)
    print(f"ETF 池：11 只长数据 ETF（≥ 5 年）")
    print(f"策略基线：S4（入场过滤 + 永远满仓）")
    print(f"变量：BOLL 位置 × MA 周期 = {len(ENTRY_FILTERS)} 组合")
    print()

    loader = DataLoader()
    print("📊 加载 11 只长数据 ETF...")
    all_data = {}
    for code in LONG_DATA_ETFS:
        d = loader.load(codes=[code]).get(code)
        if d is not None and not d.empty:
            all_data[code] = d
    print(f"  ETF: {len(all_data)}/11")

    # buy & hold 基准
    bh_dict = {}
    for code, df in all_data.items():
        bh = buy_hold_only(code, df)
        if 'skipped' not in bh:
            bh_dict[code] = bh['total_return']
    print(f"\n📊 buy & hold 平均收益：{np.mean(list(bh_dict.values())):+.2%}")

    # 跑 12 个入场过滤组合
    all_results = []
    for filter_name, boll_mode, ma_period in ENTRY_FILTERS:
        print(f"\n📊 入场过滤: {filter_name}")
        filter_results = []
        for code, df in all_data.items():
            r = run_filter(code, df, boll_mode, ma_period)
            if 'error' not in r and not r.get('skipped'):
                r['filter'] = filter_name
                filter_results.append(r)
                all_results.append(r)

        if not filter_results:
            print(f"  ❌ 无有效结果")
            continue

        s_df = pd.DataFrame(filter_results)
        avg_ret = float(s_df['total_return'].mean())
        avg_wr = float(s_df['win_rate'].mean())
        avg_dd = float(s_df['max_drawdown'].mean())
        avg_trades = float(s_df['trade_count'].mean())

        alphas = [r['total_return'] - bh_dict[r['code']]
                  for r in filter_results if r['code'] in bh_dict]
        rescued = sum(1 for a in alphas if a > 0)
        avg_alpha = float(np.mean(alphas)) if alphas else 0
        alpha_pct = rescued / len(alphas) if alphas else 0

        if len(alphas) >= 3:
            _, p_val = stats.ttest_1samp(alphas, 0)
        else:
            p_val = 1.0

        print(f"  收益={avg_ret:+.2%} | 胜率={avg_wr:.1%} | "
              f"最大回撤={avg_dd:.2%} | 交易={avg_trades:.1f}")
        print(f"  alpha={avg_alpha:+.2%} (p={p_val:.4f}) | 跑赢 BH={rescued}/{len(alphas)}")

    # 汇总
    print("\n" + "=" * 70)
    print("📊 C21 入场过滤网格 - 汇总对比（按 alpha 降序）")
    print("=" * 70)

    summary_rows = []
    for filter_name, boll_mode, ma_period in ENTRY_FILTERS:
        s_rows = [r for r in all_results if r.get('filter') == filter_name]
        if not s_rows:
            continue
        s_df = pd.DataFrame(s_rows)
        avg_ret = float(s_df['total_return'].mean())
        avg_wr = float(s_df['win_rate'].mean())
        avg_dd = float(s_df['max_drawdown'].mean())
        avg_trades = float(s_df['trade_count'].mean())

        alphas = [r['total_return'] - bh_dict[r['code']]
                  for r in s_rows if r['code'] in bh_dict]
        rescued = sum(1 for a in alphas if a > 0)
        avg_alpha = float(np.mean(alphas)) if alphas else 0
        alpha_pct = rescued / len(alphas) if alphas else 0

        if len(alphas) >= 3:
            _, p_val = stats.ttest_1samp(alphas, 0)
        else:
            p_val = 1.0

        summary_rows.append({
            'filter': filter_name,
            'boll_mode': boll_mode,
            'ma_period': ma_period,
            'avg_return': avg_ret,
            'win_rate': avg_wr,
            'max_drawdown': avg_dd,
            'alpha': avg_alpha,
            'alpha_p': p_val,
            'alpha_pct': alpha_pct,
            'rescued': rescued,
            'total_etfs': len(alphas),
            'avg_trades': avg_trades,
        })

    summary_df = pd.DataFrame(summary_rows)
    print("\n按 alpha 降序（推荐 ⭐）：")
    pd.set_option('display.max_colwidth', 60)
    pd.set_option('display.width', 200)
    print(summary_df.sort_values('alpha', ascending=False).to_string(index=False))

    # 保存
    output_dir = Path('data/business_understanding')
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / 'C21_entry_filter_grid.json'
    summary_df.to_json(json_path, orient='records', force_ascii=False, indent=2)
    print(f"\n✅ 结果已保存：{json_path}")

    # 关键发现
    print("\n" + "=" * 70)
    print("📊 关键发现（按规则 6.1 诚实标注）")
    print("=" * 70)

    best = summary_df.sort_values('alpha', ascending=False).iloc[0]
    worst = summary_df.sort_values('alpha', ascending=True).iloc[0]
    print(f"\n🥇 最佳：{best['filter']}")
    print(f"   alpha = {best['alpha']:+.2%} (p={best['alpha_p']:.4f})")
    print(f"   跑赢 BH = {best['rescued']}/{best['total_etfs']}")

    print(f"\n🔴 最差：{worst['filter']}")
    print(f"   alpha = {worst['alpha']:+.2%} (p={worst['alpha_p']:.4f})")
    print(f"   跑赢 BH = {worst['rescued']}/{worst['total_etfs']}")

    print(f"\n📊 alpha 极差：{best['alpha'] - worst['alpha']:+.2%}")
    if abs(best['alpha'] - worst['alpha']) > 0.05:
        print(f"   🟢 入场过滤有显著影响")
    else:
        print(f"   🔴 入场过滤几乎无影响")


if __name__ == '__main__':
    main()