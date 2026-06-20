#!/usr/bin/env python3
"""C20 alpha 来源分解（交叉验证）

按 L224（暴跌保护被 sell_ma5 掩盖）+ 用户要求"重新分析 alpha 来自哪里"

6 个场景剥离验证：
1. C11 baseline（max_hold=99999 + 4 因子 + sell_ma5/rsi/obv + MA60）
2. 剥离因子入场（仅 BOLL+MA60 过滤）
3. 剥离 sell_ma5（保留 trend+RSI+OBV 卖出）
4. 剥离所有 sell（仅 max_hold=99999）
5. BH only（无策略）
6. 仅暴跌保护（剥离 sell_ma5/sell_rsi/sell_obv）

核心目的：交叉验证 alpha 真实来源
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
    TREND_FILTER_MA,
    add_indicators, market_state,
)
from src.backtest.engine import BacktestConfig, create_backtester


def buy_hold_only(code: str, df: pd.DataFrame) -> dict:
    df = df.sort_values('date').reset_index(drop=True)
    if df.empty:
        return {'code': code, 'skipped': True}
    start_price = df.iloc[0]['close']
    end_price = df.iloc[-1]['close']
    total_return = (end_price / start_price - 1) if start_price > 0 else 0
    return {'code': code, 'total_return': float(total_return)}


def buy_signal_full(df: pd.DataFrame, min_n: int = 1) -> pd.Series:
    """完整 4 因子入场（MA5/RSI/OBV + BOLL + MA60）"""
    s = df.copy()
    s['s_ma5'] = (df['close'] > df['ma5']).astype(int)
    s['s_rsi'] = (df['rsi_14'] < RSI_BUY_THRESHOLD).astype(int)
    s['s_obv'] = (df['OBV'] > df['ma_obv_10']).astype(int)
    s['s_sum'] = s['s_ma5'] + s['s_rsi'] + s['s_obv']
    in_boll = (df['close'] >= df['BB_middle']) & (df['close'] <= df['BB_upper'])
    in_trend = (df['close'] > df[f'ma{TREND_FILTER_MA}'])
    return ((s['s_sum'] >= min_n) & in_boll & in_trend).astype(int)


def buy_signal_boll_ma60(df: pd.DataFrame) -> pd.Series:
    """仅 BOLL + MA60 过滤（无 4 因子）"""
    in_boll = (df['close'] >= df['BB_middle']) & (df['close'] <= df['BB_upper'])
    in_trend = (df['close'] > df[f'ma{TREND_FILTER_MA}'])
    return (in_boll & in_trend).astype(int)


def sell_signal_full(df: pd.DataFrame) -> pd.Series:
    """完整卖出（sell_ma5 + sell_rsi + sell_obv + MA60）= C11"""
    sell_ma5 = df['close'] < df['ma5']
    sell_rsi = df['rsi_14'] > RSI_SELL_THRESHOLD
    sell_obv = df['OBV'] < df['ma_obv_10']
    trend_break = df['close'] < df[f'ma{TREND_FILTER_MA}']
    return (sell_ma5 | sell_rsi | sell_obv | trend_break).astype(int)


def sell_signal_no_ma5(df: pd.DataFrame) -> pd.Series:
    """剥离 sell_ma5（保留 sell_rsi + sell_obv + MA60）"""
    sell_rsi = df['rsi_14'] > RSI_SELL_THRESHOLD
    sell_obv = df['OBV'] < df['ma_obv_10']
    trend_break = df['close'] < df[f'ma{TREND_FILTER_MA}']
    return (sell_rsi | sell_obv | trend_break).astype(int)


def sell_signal_only_ma60(df: pd.DataFrame) -> pd.Series:
    """仅暴跌保护 MA60（剥离所有因子反转）"""
    return (df['close'] < df[f'ma{TREND_FILTER_MA}']).astype(int)


def sell_signal_none(df: pd.DataFrame) -> pd.Series:
    """完全无卖出（仅 max_hold=99999 控制）"""
    return pd.Series(0, index=df.index)


def make_position(buy: pd.Series, sell: pd.Series) -> pd.Series:
    """构造持仓序列"""
    pos = pd.Series(0, index=buy.index)
    holding = False
    for i in range(len(buy)):
        if not holding and buy.iloc[i] == 1:
            holding = True
        elif holding and sell.iloc[i] == 1:
            holding = False
        pos.iloc[i] = 1 if holding else 0
    return pos.astype(float)


def run_scenario(code: str, df: pd.DataFrame, scenario_name: str,
                 buy_func, sell_func) -> dict:
    df = df[(df['date'] >= START_DATE) & (df['date'] <= END_DATE)].copy()
    if len(df) < 60:
        return {'code': code, 'skipped': True}

    df = add_indicators(df)
    buy = buy_func(df)
    sell = sell_func(df)
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
            'scenario': scenario_name,
            'total_return': float(result.total_return),
            'annual_return': float(result.annual_return),
            'max_drawdown': float(result.max_drawdown),
            'win_rate': float(result.win_rate),
            'trade_count': int(result.trade_count),
        }
    except Exception as e:
        return {'code': code, 'scenario': scenario_name, 'error': f'{type(e).__name__}: {e}'}


# ============================================================
# 6 个测试场景
# ============================================================

SCENARIOS = [
    # (scenario_name, buy_func, sell_func)
    ('S1_C11_baseline (4因子入场 + sell_ma5/rsi/obv + MA60)',
     lambda df: buy_signal_full(df, min_n=1), sell_signal_full),
    ('S2_仅BOLL+MA60入场 (剥离因子入场)',
     buy_signal_boll_ma60, sell_signal_full),
    ('S3_剥离sell_ma5 (保留sell_rsi+sell_obv+MA60)',
     lambda df: buy_signal_full(df, min_n=1), sell_signal_no_ma5),
    ('S4_无sell_signal (仅max_hold=99999控制)',
     lambda df: buy_signal_full(df, min_n=1), sell_signal_none),
    ('S5_buy&hold (无策略)',
     lambda df: pd.Series(0, index=df.index), sell_signal_none),
    ('S6_仅暴跌保护MA60 (剥离sell_ma5/rsi/obv)',
     lambda df: buy_signal_full(df, min_n=1), sell_signal_only_ma60),
]


def main():
    print("=" * 70)
    print("C20 alpha 来源分解（交叉验证）")
    print("=" * 70)
    print(f"ETF 池：11 只长数据 ETF（≥ 5 年）")
    print(f"6 个场景：剥离验证 alpha 真实来源")
    print()

    loader = DataLoader()
    print("📊 加载 11 只长数据 ETF...")
    all_data = {}
    for code in LONG_DATA_ETFS:
        d = loader.load(codes=[code]).get(code)
        if d is not None and not d.empty:
            all_data[code] = d
    print(f"  ETF: {len(all_data)}/11")

    # 跑 6 个场景
    all_results = []
    bh_dict = {}
    for code, df in all_data.items():
        bh = buy_hold_only(code, df)
        if 'skipped' not in bh:
            bh_dict[code] = bh['total_return']

    print(f"\n📊 buy & hold 平均收益：{np.mean(list(bh_dict.values())):+.2%}")

    for scenario_name, buy_func, sell_func in SCENARIOS:
        print("\n" + "=" * 70)
        short_name = scenario_name.split(' ')[0]
        print(f"📊 场景：{scenario_name}")
        print("=" * 70)
        scenario_results = []

        # S5 buy & hold 特殊处理：永远持仓 = buy_hold_only 的结果
        if short_name == 'S5_buy&hold':
            for code in bh_dict:
                scenario_results.append({
                    'code': code,
                    'scenario': short_name,
                    'total_return': bh_dict[code],
                    'annual_return': 0,
                    'max_drawdown': 0,
                    'win_rate': 1.0 if bh_dict[code] > 0 else 0,
                    'trade_count': 1,
                })
                all_results.append({
                    'code': code,
                    'scenario': short_name,
                    'total_return': bh_dict[code],
                })
        else:
            for code, df in all_data.items():
                r = run_scenario(code, df, short_name, buy_func, sell_func)
                if 'error' not in r and not r.get('skipped'):
                    scenario_results.append(r)
                    all_results.append(r)

        if not scenario_results:
            print(f"  ❌ 无有效结果")
            continue

        s_df = pd.DataFrame(scenario_results)
        avg_ret = float(s_df['total_return'].mean())
        avg_wr = float(s_df['win_rate'].mean())
        avg_dd = float(s_df['max_drawdown'].mean())
        avg_trades = float(s_df['trade_count'].mean())

        # alpha vs buy & hold
        alphas = [r['total_return'] - bh_dict[r['code']]
                  for r in scenario_results if r['code'] in bh_dict]
        rescued = sum(1 for a in alphas if a > 0)
        avg_alpha = float(np.mean(alphas)) if alphas else 0
        alpha_pct = rescued / len(alphas) if alphas else 0

        if len(alphas) >= 3:
            _, p_val = stats.ttest_1samp(alphas, 0)
        else:
            p_val = 1.0

        print(f"  ETF={len(s_df)} | 收益={avg_ret:+.2%} | 胜率={avg_wr:.1%} | "
              f"最大回撤={avg_dd:.2%} | 交易={avg_trades:.1f}")
        print(f"  alpha={avg_alpha:+.2%} (p={p_val:.4f}) | 跑赢 BH={rescued}/{len(alphas)}")

    # 汇总对比
    print("\n" + "=" * 70)
    print("📊 C20 alpha 来源分解 - 汇总对比")
    print("=" * 70)

    summary_rows = []
    for scenario_name, buy_func, sell_func in SCENARIOS:
        short_name = scenario_name.split(' ')[0]
        s_rows = [r for r in all_results if r['scenario'] == short_name]
        if not s_rows:
            continue
        s_df = pd.DataFrame(s_rows)
        avg_ret = float(s_df['total_return'].mean())
        avg_wr = float(s_df['win_rate'].mean()) if 'win_rate' in s_df.columns else 0
        avg_dd = float(s_df['max_drawdown'].mean()) if 'max_drawdown' in s_df.columns else 0
        avg_trades = float(s_df['trade_count'].mean()) if 'trade_count' in s_df.columns else 1

        # S5 buy & hold：alpha = 0（自身即基准）
        if short_name == 'S5_buy&hold':
            avg_alpha = 0.0
            p_val = 1.0
            rescued = sum(1 for v in bh_dict.values() if v > 0)
            alpha_pct = rescued / len(bh_dict) if bh_dict else 0
        else:
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
            'scenario': scenario_name,
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
    pd.set_option('display.max_colwidth', 80)
    pd.set_option('display.width', 200)
    print(summary_df.sort_values('alpha', ascending=False).to_string(index=False))

    # 增量分析（剥离验证）
    print("\n" + "=" * 70)
    print("📊 alpha 增量分析（剥离验证）")
    print("=" * 70)

    by_name = {row['scenario']: row for _, row in summary_df.iterrows()}
    S1 = None
    for k, v in by_name.items():
        if k.startswith('S1_'):
            S1 = v
            break

    if S1 is not None and hasattr(S1, 'get'):
        print(f"\nS1 baseline alpha = {S1['alpha']:+.2%}")
        for s in summary_rows:
            delta = s['alpha'] - S1['alpha']
            print(f"  {s['scenario'][:50]:50s} | alpha={s['alpha']:+.2%} | "
                  f"Δ vs S1 = {delta:+.2%}")

    # 保存
    output_dir = Path('data/business_understanding')
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / 'C20_alpha_decomposition.json'
    summary_df.to_json(json_path, orient='records', force_ascii=False, indent=2)
    print(f"\n✅ 结果已保存：{json_path}")


if __name__ == '__main__':
    main()