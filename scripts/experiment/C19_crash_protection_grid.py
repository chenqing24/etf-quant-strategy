#!/usr/bin/env python3
"""C19 暴跌保护阈值网格（基于 L223 原则 2）

按 L223（暴跌保护作为事后风控原则）：
- 当前 C11/C18 用 close<MA60 作为暴跌保护
- 本实验测试不同阈值的暴跌保护效果
- 找最优阈值（用 alpha / 最大回撤 / 救回金额衡量）

阈值网格：
1. MA20   （短线趋势破位，触发频繁）
2. MA60   （中线趋势破位，C11 当前）
3. MA120  （长线趋势破位，触发稀少）
4. ATR2x  （波动率突破，ATR(20) * 2 当日跌幅）
5. DD-20% （从最高点回撤 20%）

控制变量：
- ETF 池：11 只长数据 ETF（C18 已验证）
- 因子信号：C11 同（MA5/RSI/OBV/BOLL）
- max_hold_days=99999
- 数据范围：每只 ETF 实际可用数据

衡量指标：
- 收益 / 胜率 / 最大回撤 / alpha vs buy & hold / 救回金额
- 按 L223 原则 3：风控效果不依赖胜率衡量（用最大回撤/救回金额）
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
from scripts.experiment.LONG_ETFS import LONG_DATA_ETFS
from scripts.experiment.C9_market_state_v4 import (
    START_DATE, END_DATE, STOP_LOSS, RSI_BUY_THRESHOLD, RSI_SELL_THRESHOLD,
    TREND_FILTER_MA, WEIGHTS_TREND, WEIGHTS_RANGE,
    add_indicators, market_state, factor_score,
    buy_signal_state_aware,
)
from src.backtest.engine import BacktestConfig, create_backtester


# ============================================================
# 暴跌保护阈值网格（5 个）
# ============================================================

CRASH_THRESHOLDS = {
    'MA20': 20,         # close < MA20（短线破位）
    'MA60': 60,         # close < MA60（中线破位，C11 当前）
    'MA120': 120,       # close < MA120（长线破位）
    'ATR2x': 'atr2x',   # 当日跌幅 > ATR(20)*2（波动率突破）
    'DD-20%': 'dd20',   # 从最高点回撤 20%
}


def custom_sell_signal(df: pd.DataFrame, threshold_name: str) -> pd.Series:
    """暴跌保护阈值可配置的 sell_signal

    Args:
        df: 包含指标的 DataFrame
        threshold_name: MA20 / MA60 / MA120 / ATR2x / DD-20%
    """
    # 因子反转（与 C11 一致）
    sell_ma5 = df['close'] < df['ma5']
    sell_rsi = df['rsi_14'] > RSI_SELL_THRESHOLD
    sell_obv = df['OBV'] < df['ma_obv_10']

    # 暴跌保护（按阈值）
    if threshold_name in ('MA20', 'MA60', 'MA120'):
        ma_n = CRASH_THRESHOLDS[threshold_name]
        crash = df['close'] < df[f'ma{ma_n}']
    elif threshold_name == 'ATR2x':
        # 当日跌幅 > ATR(20) * 2
        atr_20 = df['close'].rolling(20).std() * np.sqrt(20)  # 简化 ATR
        daily_drop = (df['close'] - df['close'].shift(1)) / df['close'].shift(1)
        crash = daily_drop < -2 * atr_20 / df['close']
    elif threshold_name == 'DD-20%':
        # 从最高点回撤 20%
        rolling_max = df['close'].cummax()
        drawdown = (df['close'] - rolling_max) / rolling_max
        crash = drawdown < -0.20
    else:
        raise ValueError(f"Unknown threshold: {threshold_name}")

    return (sell_ma5 | sell_rsi | sell_obv | crash).astype(int)


def position_series(df: pd.DataFrame, min_n: int, threshold_name: str) -> pd.Series:
    """持仓序列（暴跌保护阈值可配置）"""
    buy = buy_signal_state_aware(df, min_n)
    sell = custom_sell_signal(df, threshold_name)
    position = pd.Series(0, index=df.index)
    holding = False
    for i in range(len(df)):
        if not holding and buy.iloc[i] == 1:
            holding = True
        elif holding and sell.iloc[i] == 1:
            holding = False
        position.iloc[i] = 1 if holding else 0
    return position.astype(float)


def run_single(code: str, df: pd.DataFrame, min_n: int, threshold_name: str) -> dict:
    """单只 ETF 单阈值回测"""
    df = df[(df['date'] >= START_DATE) & (df['date'] <= END_DATE)].copy()
    if len(df) < 60:
        return {'code': code, 'skipped': True}

    df = add_indicators(df)
    sig = position_series(df, min_n, threshold_name)

    config = BacktestConfig(
        stop_loss=STOP_LOSS,
        stop_profit=999,             # 无止盈
        min_hold_days=3,
        max_hold_days=99999,         # 关闭到期平仓（C11 已验证）
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
            'threshold': threshold_name,
            'total_return': float(result.total_return),
            'annual_return': float(result.annual_return),
            'max_drawdown': float(result.max_drawdown),
            'win_rate': float(result.win_rate),
            'trade_count': int(result.trade_count),
        }
    except Exception as e:
        return {'code': code, 'threshold': threshold_name, 'error': f'{type(e).__name__}: {e}'}


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
    }


def main():
    print("=" * 70)
    print("C19 暴跌保护阈值网格（基于 L223 原则 2）")
    print("=" * 70)
    print(f"ETF 池：11 只长数据 ETF（≥ 5 年）")
    print(f"策略基线：C11（max_hold=99999 + 4 因子 + 暴跌保护）")
    print(f"变量：暴跌保护阈值 = {list(CRASH_THRESHOLDS.keys())}")
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
    print("\n📊 buy & hold 基准（每只 ETF 实际数据范围）...")
    bh_results = []
    for code, df in all_data.items():
        bh = buy_hold_single(code, df)
        if 'skipped' not in bh:
            bh_results.append(bh)
    bh_avg = np.mean([r['bh_return'] for r in bh_results])
    print(f"  buy & hold 平均收益: {bh_avg:+.2%}")

    # 5 个阈值 × 11 只 ETF
    all_results = []
    for threshold_name in CRASH_THRESHOLDS.keys():
        print("\n" + "=" * 70)
        print(f"📊 实验：暴跌保护阈值 = {threshold_name}")
        print("=" * 70)
        threshold_results = []
        for code, df in all_data.items():
            r = run_single(code, df, min_n=1, threshold_name=threshold_name)
            if 'error' not in r and not r.get('skipped'):
                threshold_results.append(r)
                all_results.append(r)

        if not threshold_results:
            print(f"  ❌ 无有效结果")
            continue

        t_df = pd.DataFrame(threshold_results)
        avg_ret = float(t_df['total_return'].mean())
        avg_wr = float(t_df['win_rate'].mean())
        avg_dd = float(t_df['max_drawdown'].mean())
        avg_trades = float(t_df['trade_count'].mean())

        # alpha vs buy & hold（配对）
        bh_dict = {r['code']: r['bh_return'] for r in bh_results}
        alphas = []
        rescued = 0  # 救回 ETF 数（C11 收益 > BH 收益）
        for _, row in t_df.iterrows():
            if row['code'] in bh_dict:
                alpha = row['total_return'] - bh_dict[row['code']]
                alphas.append(alpha)
                if row['total_return'] > bh_dict[row['code']]:
                    rescued += 1

        avg_alpha = float(np.mean(alphas))
        alpha_pct = sum(1 for a in alphas if a > 0) / len(alphas) if alphas else 0

        # t 检验（alpha 显著性）
        if len(alphas) >= 3:
            from scipy import stats
            t_stat, p_val = stats.ttest_1samp(alphas, 0)
        else:
            t_stat, p_val = 0, 1

        print(f"  ETF={len(t_df)} | 收益={avg_ret:+.2%} | 胜率={avg_wr:.1%} | "
              f"最大回撤={avg_dd:.2%} | 交易={avg_trades:.1f}")
        print(f"  buy & hold = {bh_avg:+.2%}")
        print(f"  alpha = {avg_alpha:+.2%} (p={p_val:.4f})")
        print(f"  跑赢 BH 的 ETF = {rescued}/{len(alphas)} ({alpha_pct:.1%})")

    # ============================================================
    # 汇总对比
    # ============================================================
    print("\n" + "=" * 70)
    print("📊 C19 暴跌保护阈值网格 - 汇总对比（按 L223 原则 3）")
    print("=" * 70)

    summary_rows = []
    for threshold_name in CRASH_THRESHOLDS.keys():
        t_rows = [r for r in all_results if r['threshold'] == threshold_name]
        if not t_rows:
            continue
        t_df = pd.DataFrame(t_rows)
        avg_ret = float(t_df['total_return'].mean())
        avg_wr = float(t_df['win_rate'].mean())
        avg_dd = float(t_df['max_drawdown'].mean())
        avg_trades = float(t_df['trade_count'].mean())

        bh_dict = {r['code']: r['bh_return'] for r in bh_results}
        alphas = [r['total_return'] - bh_dict[r['code']] for r in t_rows if r['code'] in bh_dict]
        rescued = sum(1 for a in alphas if a > 0)
        avg_alpha = float(np.mean(alphas)) if alphas else 0
        alpha_pct = rescued / len(alphas) if alphas else 0

        from scipy import stats
        if len(alphas) >= 3:
            _, p_val = stats.ttest_1samp(alphas, 0)
        else:
            p_val = 1.0

        summary_rows.append({
            'threshold': threshold_name,
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
    print(summary_df.sort_values('alpha', ascending=False).to_string(index=False))

    # 保存结果
    output_dir = Path('data/business_understanding')
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / 'C19_crash_protection_grid.json'
    summary_df.to_json(json_path, orient='records', force_ascii=False, indent=2)
    print(f"\n✅ 结果已保存：{json_path}")

    # 关键结论
    print("\n" + "=" * 70)
    print("📊 关键结论（按规则 6.1 诚实标注）")
    print("=" * 70)

    best = summary_df.sort_values('alpha', ascending=False).iloc[0]
    print(f"\n🥇 最佳阈值：{best['threshold']}")
    print(f"   alpha = {best['alpha']:+.2%} (p={best['alpha_p']:.4f})")
    print(f"   跑赢 BH = {best['rescued']}/{best['total_etfs']} ETF")
    print(f"   最大回撤 = {best['max_drawdown']:.2%}")

    # 与 C11 (MA60) 对比
    c11_row = summary_df[summary_df['threshold'] == 'MA60']
    if not c11_row.empty:
        c11 = c11_row.iloc[0]
        print(f"\n📌 C11 当前（MA60）：")
        print(f"   alpha = {c11['alpha']:+.2%} (p={c11['alpha_p']:.4f})")
        if best['threshold'] != 'MA60':
            delta = best['alpha'] - c11['alpha']
            print(f"\n🔄 vs MA60：{best['threshold']} 比 MA60 {'更好' if delta > 0 else '更差'} "
                  f"{abs(delta):.2%}（alpha 差）")


if __name__ == '__main__':
    main()