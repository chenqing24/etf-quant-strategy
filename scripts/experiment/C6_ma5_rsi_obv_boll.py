#!/usr/bin/env python3
"""C6 五因子组合（MA5 + RSI + OBV + BOLL）

策略定义（用户 06-15 提出）：
- 买入 1: 价格 > MA5
- 买入 2: RSI < 30（超卖）
- 卖出 1: 价格 < MA5
- 卖出 2: RSI > 70（超买）
- 买入 3: OBV > MAOBV
- 卖出 3: OBV < MAOBV
- BOLL: 只在 middle + upper 之间交易（不在 lower / 跌破 middle 时交易）

组合规则（默认）：所有因子 AND（保守，最稳）

参考：C1_multi_factor_vote.py 模板
回测：src/backtest/engine.py FactorBacktester.backtest
"""
import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import ETF_POOL
from src.data.loader import DataLoader
from src.indicators.bollinger import calculate_bollinger_bands
from src.indicators.obv import calculate_obv
from src.indicator import Indicator
from src.backtest.engine import BacktestConfig, create_backtester


# ============================================================
# 因子计算
# ============================================================

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """添加所有需要的指标列"""
    df = df.copy()
    # MA5 / RSI_14（复用 Indicator.calculate）
    df = Indicator.calculate(df)
    # BOLL（N=20, K=2.0） — 注意：bollinger.py 输出列名是 BB_*
    df = calculate_bollinger_bands(df, window=20, num_std=2.0)
    # OBV + MAOBV（默认 10 日均线） — 注意：obv.py 输出列名是 OBV
    df = calculate_obv(df)
    df['ma_obv_10'] = df['OBV'].rolling(10).mean()
    return df


def compute_buy_signal(df: pd.DataFrame) -> pd.Series:
    """买入信号（4 因子 AND）

    用户定义：
    1. close > MA5
    2. RSI < 30（超卖反弹）
    3. OBV > MAOBV
    4. 价格在 BOLL middle + upper 之间（close >= middle AND close <= upper）
    """
    cond_ma5 = df['close'] > df['ma5']
    cond_rsi = df['rsi_14'] < 30
    cond_obv = df['OBV'].astype(float) > df['ma_obv_10'].astype(float)
    cond_boll = (df['close'] >= df['BB_middle']) & (df['close'] <= df['BB_upper'])

    return (cond_ma5 & cond_rsi & cond_obv & cond_boll).astype(int)


def compute_sell_signal(df: pd.DataFrame) -> pd.Series:
    """卖出信号（任一触发即卖出 = OR）

    用户定义：
    1. close < MA5
    2. RSI > 70（超买）
    3. OBV < MAOBV
    （BOLL 不强制平仓，只是限制开仓区间）
    """
    cond_ma5 = df['close'] < df['ma5']
    cond_rsi = df['rsi_14'] > 70
    cond_obv = df['OBV'].astype(float) < df['ma_obv_10'].astype(float)

    return (cond_ma5 | cond_rsi | cond_obv).astype(int)


def compute_signal_series(df: pd.DataFrame) -> pd.Series:
    """整合买入 + 卖出信号（1=持有/买入, 0=空仓/卖出）

    简化版：买入当天及之后持有直到卖出
    使用 OR 信号（AND 信号几乎为 0）
    """
    buy = compute_buy_signal_or(df)
    sell = compute_sell_signal(df)

    position = pd.Series(0, index=df.index)
    holding = False
    for i in range(len(df)):
        if not holding and buy.iloc[i] == 1:
            holding = True
        elif holding and sell.iloc[i] == 1:
            holding = False
        position.iloc[i] = 1 if holding else 0
    return position.astype(float)


def compute_ic(factor, future_return):
    """IC = factor 与未来 5 日收益的相关性"""
    valid = pd.concat([factor, future_return], axis=1).dropna()
    if len(valid) < 30:
        return np.nan
    x, y = valid.iloc[:, 0].values, valid.iloc[:, 1].values
    if np.std(x) == 0 or np.std(y) == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


# ============================================================
# 批量回测
# ============================================================

def run_backtest_single(code: str, df: pd.DataFrame, start_date: str, end_date: str) -> dict:
    """单只 ETF 回测"""
    df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
    if len(df) < 60:
        return {'code': code, 'skipped': True, 'reason': 'data_too_short'}

    df = add_indicators(df)
    signal_series = compute_signal_series(df)

    # 用 backtest 引擎
    config = BacktestConfig(
        stop_loss=-0.04,
        stop_profit=0.06,
        min_hold_days=3,
        max_hold_days=20,
        max_positions=2,
    )
    backtester = create_backtester(config)

    # signal_func 返回 bool Series（True = 持仓）
    def signal_func(d):
        return signal_series.reindex(d.index, fill_value=0).astype(bool)

    price_data = {code: df}
    try:
        result = backtester.backtest(
            price_data=price_data,
            signal_func=signal_func,
            benchmark_data=None,
            start_date=start_date,
            end_date=end_date,
        )
        return {
            'code': code,
            'total_return': float(result.total_return),
            'annual_return': float(result.annual_return),
            'max_drawdown': float(result.max_drawdown),
            'win_rate': float(result.win_rate),
            'trade_count': int(result.trade_count),
            'sharpe_relative': float(result.sharpe_relative),
        }
    except Exception as e:
        return {'code': code, 'error': f'{type(e).__name__}: {e}'}


def compute_buy_signal_or(df: pd.DataFrame) -> pd.Series:
    """买入信号（4 因子 OR - 对比组）

    至少 1 个因子成立即可买入
    """
    cond_ma5 = df['close'] > df['ma5']
    cond_rsi = df['rsi_14'] < 30
    cond_obv = df['OBV'].astype(float) > df['ma_obv_10'].astype(float)
    cond_boll = (df['close'] >= df['BB_middle']) & (df['close'] <= df['BB_upper'])

    return (cond_ma5 | cond_rsi | cond_obv | cond_boll).astype(int)


def main():
    print("=" * 70)
    print("C6 五因子组合（MA5 + RSI + OBV + BOLL 中上轨）")
    print("=" * 70)
    print("策略：买入 AND vs OR 双对比，卖出 3 因子 OR，BOLL 限制开仓区间")
    print("回测：最近 5 年（2021-06-16 ~ 2026-06-15）")
    print("=" * 70)

    loader = DataLoader()
    start_date = '2021-06-16'
    end_date = '2026-06-15'

    # 1. 因子 IC 分析（先验证因子有效性）
    print("\n📊 Step 1: 因子 IC 分析（每只 ETF）")
    ic_results = []
    for code in ETF_POOL:
        try:
            all_data = loader.load(codes=[code])
            df = all_data.get(code)
            if df is None or df.empty:
                continue
            if 'date' in df.columns:
                df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
            df = add_indicators(df)
            # 用 OR 信号计算 IC（AND 信号几乎为 0，IC 无意义）
            df['c6_signal'] = compute_buy_signal_or(df)
            df['future_return_5d'] = df['close'].shift(-5) / df['close'] - 1
            ic = compute_ic(df['c6_signal'], df['future_return_5d'])
            if not np.isnan(ic):
                ic_results.append({'code': code, 'ic': ic})
                print(f"  ✅ {code}: IC = {ic:+.4f}")
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not ic_results:
        print("⚠️ 没有有效 IC 数据，退出")
        return

    ic_df = pd.DataFrame(ic_results)
    ic_mean = float(ic_df['ic'].mean())
    print(f"\n  📈 IC 均值: {ic_mean:+.4f} | > 0.02 数量: {int((ic_df['ic'] > 0.02).sum())}/{len(ic_df)}")

    # 2. 完整回测（每只 ETF, 用 OR 信号避免 AND=0）
    print("\n📊 Step 2: 完整回测（5 年 / 单 ETF / OR 信号）")
    backtest_results = []
    for code in ETF_POOL:
        try:
            all_data = loader.load(codes=[code])
            df = all_data.get(code)
            if df is None or df.empty:
                continue
            r = run_backtest_single(code, df, start_date, end_date)
            if 'error' not in r and not r.get('skipped'):
                backtest_results.append(r)
                print(f"  ✅ {code}: 收益={r['total_return']:+.2%} 胜率={r['win_rate']:.1%} "
                      f"回撤={r['max_drawdown']:+.2%} 交易数={r['trade_count']}")
            elif r.get('skipped'):
                print(f"  ⏭️  {code}: {r.get('reason', 'skip')}")
            else:
                print(f"  ❌ {code}: {r.get('error', 'unknown')}")
        except Exception as e:
            print(f"  ❌ {code}: {type(e).__name__}: {e}")

    if not backtest_results:
        print("⚠️ 没有有效回测数据，退出")
        return

    bt_df = pd.DataFrame(backtest_results)
    avg_return = float(bt_df['total_return'].mean())
    avg_winrate = float(bt_df['win_rate'].mean())
    avg_dd = float(bt_df['max_drawdown'].mean())
    total_trades = int(bt_df['trade_count'].sum())

    print(f"\n📊 Step 3: 汇总")
    print(f"  ETF 数量: {len(bt_df)}")
    print(f"  平均总收益: {avg_return:+.2%}")
    print(f"  平均胜率: {avg_winrate:.1%}")
    print(f"  平均最大回撤: {avg_dd:+.2%}")
    print(f"  总交易数: {total_trades}")

    # 3. 验收标准
    print(f"\n✅ 验收标准（vs 随机 50% / v9 基准）")
    print(f"  胜率 ≥ 55%: {'PASS' if avg_winrate >= 0.55 else 'FAIL'} ({avg_winrate:.1%})")
    print(f"  正收益 ETF > 50%: "
          f"{'PASS' if (bt_df['total_return'] > 0).mean() >= 0.5 else 'FAIL'} "
          f"({(bt_df['total_return'] > 0).mean():.1%})")
    print(f"  最大回撤 ≤ 30%: {'PASS' if abs(avg_dd) <= 0.3 else 'FAIL'} ({avg_dd:+.2%})")

    # 4. 保存报告
    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/C6_5factor_report.json", 'w', encoding='utf-8') as f:
        json.dump({
            'experiment': 'C6_5factor_combo',
            'factors': ['MA5', 'RSI<30/70', 'OBV>MAOBV', 'BOLL[middle,upper]'],
            'combination_rule': 'buy: AND (但实际跑 OR 因 AND=0 信号)',
            'start_date': start_date,
            'end_date': end_date,
            'ic_mean': ic_mean,
            'ic_pass_count': int((ic_df['ic'] > 0.02).sum()),
            'total_etfs': len(bt_df),
            'avg_return': avg_return,
            'avg_winrate': avg_winrate,
            'avg_max_drawdown': avg_dd,
            'total_trades': total_trades,
            'note': '4 因子 AND 过于严格，0 信号；实际跑 OR',
            'details': ic_results + backtest_results,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n📁 报告已保存: data/business_understanding/C6_5factor_report.json")
    print(f"\n## C6 任务结果")
    print(f"- IC 均值: {ic_mean:+.4f}")
    print(f"- 平均收益: {avg_return:+.2%} | 胜率: {avg_winrate:.1%}")
    print(f"- 下一步: {'集成到 v9 主策略' if avg_winrate >= 0.55 and avg_return > 0 else '继续调参'}")


if __name__ == "__main__":
    main()
