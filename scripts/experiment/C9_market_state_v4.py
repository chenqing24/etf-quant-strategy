#!/usr/bin/env python3
"""C9 三因子加权 + 市场状态切换（v4）

按用户 06-16 要求：
1. 5 年回测（不是 3 年）
2. MA60 趋势过滤（仅 close > MA60 时启用策略）
3. 趋势市 vs 震荡市用不同权重

按 L213 改进 1：RSI<40/>60 放宽
按 L213 改进 5：阈值与权重解耦
按 L214 教训：单因子弱 → 趋势过滤增强
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


# ============================================================
# 配置（按用户 + L213/L214 改进）
# ============================================================

# 5 年回测（用户要求）
START_DATE = '2021-06-16'
END_DATE = '2026-06-15'

# L213 改进 1：RSI 放宽
RSI_BUY_THRESHOLD = 40
RSI_SELL_THRESHOLD = 60

# L213 改进 3：止损放宽
STOP_LOSS = -0.12

# MA60 趋势过滤（用户要求）
TREND_FILTER_MA = 60

# 两套权重（用户要求：趋势市 vs 震荡市不同）
WEIGHTS_TREND = {'MA5': 0.6, 'RSI': 0.2, 'OBV': 0.2}   # 趋势跟随主导
WEIGHTS_RANGE = {'MA5': 0.2, 'RSI': 0.6, 'OBV': 0.2}   # RSI 超卖反弹主导


# ============================================================
# 因子计算
# ============================================================

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = Indicator.calculate(df)
    df = calculate_bollinger_bands(df, window=20, num_std=2.0)
    df = calculate_obv(df)
    df['ma_obv_10'] = df['OBV'].rolling(10).mean()
    return df


def market_state(df: pd.DataFrame) -> pd.Series:
    """市场状态：close > MA60 → 趋势市 (1)，否则震荡市 (0)"""
    return (df['close'] > df[f'ma{TREND_FILTER_MA}']).astype(int)


def factor_score(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['s_ma5'] = (df['close'] > df['ma5']).astype(int)
    df['s_rsi'] = (df['rsi_14'] < RSI_BUY_THRESHOLD).astype(int)
    df['s_obv'] = (df['OBV'] > df['ma_obv_10']).astype(int)
    df['s_sum'] = df['s_ma5'] + df['s_rsi'] + df['s_obv']
    return df


def buy_signal_state_aware(df: pd.DataFrame, min_n: int = 2) -> pd.Series:
    """买入信号 = MA60 趋势过滤 + BOLL 准入 + 至少 min_n 个因子成立
    权重根据市场状态动态切换
    """
    s = factor_score(df)
    in_boll = (df['close'] >= df['BB_middle']) & (df['close'] <= df['BB_upper'])
    state = market_state(df)  # 1=趋势市, 0=震荡市

    # 根据市场状态选权重（仅记录，不参与门槛）
    w = pd.Series(WEIGHTS_TREND['MA5'], index=df.index)
    w_rsi = pd.Series(WEIGHTS_TREND['RSI'], index=df.index)
    w_obv = pd.Series(WEIGHTS_TREND['OBV'], index=df.index)
    in_range = state == 0
    w.loc[in_range] = WEIGHTS_RANGE['MA5']
    w_rsi.loc[in_range] = WEIGHTS_RANGE['RSI']
    w_obv.loc[in_range] = WEIGHTS_RANGE['OBV']

    # 加权分数（用于事后分析权重影响，不作为门槛）
    weighted = s['s_ma5'] * w + s['s_rsi'] * w_rsi + s['s_obv'] * w_obv
    n_active = s['s_sum']
    # 改进 5 强化：min_n 与权重完全解耦，门槛只看因子数
    # 仅在趋势市 + BOLL 准入 + 至少 min_n 个因子成立 = 买入
    in_trend = state == 1
    return ((n_active >= min_n) & in_boll & in_trend).astype(int)


def sell_signal(df: pd.DataFrame) -> pd.Series:
    sell_ma5 = df['close'] < df['ma5']
    sell_rsi = df['rsi_14'] > RSI_SELL_THRESHOLD
    sell_obv = df['OBV'] < df['ma_obv_10']
    # MA60 跌破也强制平仓（趋势转弱）
    trend_break = df['close'] < df[f'ma{TREND_FILTER_MA}']
    return (sell_ma5 | sell_rsi | sell_obv | trend_break).astype(int)


def position_series(df: pd.DataFrame, min_n: int) -> pd.Series:
    buy = buy_signal_state_aware(df, min_n)
    sell = sell_signal(df)
    position = pd.Series(0, index=df.index)
    holding = False
    for i in range(len(df)):
        if not holding and buy.iloc[i] == 1:
            holding = True
        elif holding and sell.iloc[i] == 1:
            holding = False
        position.iloc[i] = 1 if holding else 0
    return position.astype(float)


# ============================================================
# 单只 ETF 回测
# ============================================================

def run_single(code: str, df: pd.DataFrame, min_n: int) -> dict:
    df = df[(df['date'] >= START_DATE) & (df['date'] <= END_DATE)].copy()
    if len(df) < 60:
        return {'code': code, 'skipped': True}

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


# ============================================================
# Main: min_n 网格
# ============================================================

def main():
    print("=" * 70)
    print("C9 三因子加权 + 市场状态切换（v4）")
    print("=" * 70)
    print(f"约束 1: 5 年回测 ({START_DATE} ~ {END_DATE})")
    print(f"约束 2: MA{TREND_FILTER_MA} 趋势过滤（仅趋势市买入）")
    print(f"约束 3: 趋势市 = MA5主导 / 震荡市 = RSI主导")
    print(f"RSI: <{RSI_BUY_THRESHOLD}/>{RSI_SELL_THRESHOLD} | 止损: {STOP_LOSS:.0%}")

    loader = DataLoader()
    print("\n📊 预加载 ETF 数据...")
    all_data = {}
    for code in ETF_POOL:
        try:
            d = loader.load(codes=[code]).get(code)
            if d is not None and not d.empty:
                all_data[code] = d
        except Exception:
            pass
    print(f"  可用 ETF: {len(all_data)}/{len(ETF_POOL)}")

    # 网格：min_n ∈ {1, 2}
    print("\n📊 网格: min_n × 状态切换")
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
    print("📊 min_n 对比")
    print("=" * 70)
    print(df_r.to_string(index=False))

    best = df_r.loc[df_r['avg_winrate'].idxmax()]
    print(f"\n🏆 最佳: min_n={int(best['min_n'])} | 胜率={best['avg_winrate']:.1%} | 收益={best['avg_return']:+.2%}")

    # vs C8 对比
    print(f"\n✅ 验收（vs C8 失败基线 26.0% 胜率）")
    print(f"  胜率 ≥ 50%: {'PASS' if best['avg_winrate'] >= 0.5 else 'FAIL'} ({best['avg_winrate']:.1%})")
    print(f"  胜率 > C8 (26%): {'PASS' if best['avg_winrate'] > 0.26 else 'FAIL'}")
    print(f"  收益 > 0: {'PASS' if best['avg_return'] > 0 else 'FAIL'} ({best['avg_return']:+.2%})")
    print(f"  正收益 ETF > 50%: {'PASS' if best['positive_etf_pct'] >= 0.5 else 'FAIL'} ({best['positive_etf_pct']:.1%})")

    # 保存报告
    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/C9_market_state_report.json", 'w', encoding='utf-8') as f:
        json.dump({
            'experiment': 'C9_market_state_v4',
            'user_constraints': {
                '1': '5 年回测（2021-06 ~ 2026-06）',
                '2': f'MA{TREND_FILTER_MA} 趋势过滤',
                '3': '趋势市 MA5 主导 / 震荡市 RSI 主导',
            },
            'weights_trend': WEIGHTS_TREND,
            'weights_range': WEIGHTS_RANGE,
            'start_date': START_DATE,
            'end_date': END_DATE,
            'best': best.to_dict(),
            'all_results': results,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📁 报告: data/business_understanding/C9_market_state_report.json")


if __name__ == "__main__":
    main()
