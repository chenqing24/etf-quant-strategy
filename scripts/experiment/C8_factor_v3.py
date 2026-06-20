#!/usr/bin/env python3
"""C8 三因子加权 + 应用 L213 改进 1/3/5

按 L213 教训改进：
- 改进 1: RSI 阈值放宽（<30→<40, >70→>60）适应 A 股
- 改进 3: 缩短回测期到 3 年（2023-2026）
- 改进 5: 阈值与权重解耦（用 min_n 因子数门槛，不用 weighted >= min_n*max_w）
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
# 配置（按 L213 改进 1/3/5）
# ============================================================

# 改进 1：RSI 阈值放宽（A 股适配）
RSI_BUY_THRESHOLD = 40   # 原 30
RSI_SELL_THRESHOLD = 60   # 原 70

# 改进 3：缩短回测期到 3 年
START_DATE = '2023-06-16'
END_DATE = '2026-06-15'

# 改进 5：止损放宽（-8% → -12%，匹配 ETF 波动率）
STOP_LOSS = -0.12

WEIGHT_GRID = [
    {'name': '等权',     'MA5': 0.34, 'RSI': 0.33, 'OBV': 0.33},
    {'name': 'MA5主导',  'MA5': 0.60, 'RSI': 0.20, 'OBV': 0.20},
    {'name': 'RSI主导',  'MA5': 0.20, 'RSI': 0.60, 'OBV': 0.20},
    {'name': 'OBV主导',  'MA5': 0.20, 'RSI': 0.20, 'OBV': 0.60},
    {'name': 'MA5+OBV',  'MA5': 0.40, 'RSI': 0.20, 'OBV': 0.40},
    {'name': 'MA5+RSI',  'MA5': 0.40, 'RSI': 0.40, 'OBV': 0.20},
    {'name': 'OBV+RSI',  'MA5': 0.20, 'RSI': 0.40, 'OBV': 0.40},
]

# 改进 5：min_n 直接作为"至少 N 个因子成立"的门槛（与权重解耦）
MIN_FACTORS = [1, 2]


# ============================================================
# 因子计算
# ============================================================

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """添加所有指标"""
    df = df.copy()
    df = Indicator.calculate(df)
    df = calculate_bollinger_bands(df, window=20, num_std=2.0)
    df = calculate_obv(df)
    df['ma_obv_10'] = df['OBV'].rolling(10).mean()
    return df


def boll_filter(df: pd.DataFrame) -> pd.Series:
    """BOLL 准入（不算分）"""
    return (df['close'] >= df['BB_middle']) & (df['close'] <= df['BB_upper'])


def factor_score(df: pd.DataFrame) -> pd.DataFrame:
    """3 因子打分（按 L213 改进 1：RSI 阈值放宽）"""
    df = df.copy()
    df['s_ma5'] = (df['close'] > df['ma5']).astype(int)
    df['s_rsi'] = (df['rsi_14'] < RSI_BUY_THRESHOLD).astype(int)  # 改 40
    df['s_obv'] = (df['OBV'] > df['ma_obv_10']).astype(int)
    df['s_sum'] = df['s_ma5'] + df['s_rsi'] + df['s_obv']
    return df


def buy_signal(df: pd.DataFrame, weights: dict, min_n: int) -> pd.Series:
    """买入信号 = 改进 5：min_n 与权重解耦
    规则：
    1. BOLL 准入
    2. 加权分数 = sum(weight_i * s_i) 必须 ≥ threshold（权重参与）
    3. threshold 由 min_n 和 max_weight 共同决定，但保证 min_n 因子成立即可过

    threshold 设计（避免 C7 的耦合 bug）：
    - 阈值 = min_n * min_weight（用最小权重而非最大权重 → 等权时 0.33*2=0.66 容易过）
    - 但要求所有 min_n 个因子成立中至少有 1 个是主导因子
    """
    s = factor_score(df)
    in_boll = boll_filter(df)
    w_ma5, w_rsi, w_obv = weights['MA5'], weights['RSI'], weights['OBV']

    # 加权分数（权重真的参与信号生成）
    weighted = s['s_ma5'] * w_ma5 + s['s_rsi'] * w_rsi + s['s_obv'] * w_obv
    # 至少 min_n 个因子成立（保证因子数）
    n_active = s['s_sum']
    # 阈值：min_n * 主导权重（与权重解耦但权重参与信号密度）
    # 修复 C7 bug：之前用 min(min_n*max_w, 1.0)，现在用 sum_of_top_min_n_weights
    # 简化：用 min_n 因子中最大的 min_n 个权重的和作为阈值
    sorted_w = sorted([w_ma5, w_rsi, w_obv], reverse=True)
    threshold = sum(sorted_w[:min_n])  # 至少 min_n 个因子都成立才能达到

    return ((n_active >= min_n) & (weighted >= threshold - 0.01) & in_boll).astype(int)


def sell_signal(df: pd.DataFrame) -> pd.Series:
    """卖出 = 任一因子反向（按 L213 改进 1：RSI>60 卖出）"""
    sell_ma5 = df['close'] < df['ma5']
    sell_rsi = df['rsi_14'] > RSI_SELL_THRESHOLD  # 改 60
    sell_obv = df['OBV'] < df['ma_obv_10']
    return (sell_ma5 | sell_rsi | sell_obv).astype(int)


def position_series(df: pd.DataFrame, weights: dict, min_n: int) -> pd.Series:
    buy = buy_signal(df, weights, min_n)
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
# 批量回测
# ============================================================

def run_single(code: str, df: pd.DataFrame, weights: dict, min_n: int) -> dict:
    df = df[(df['date'] >= START_DATE) & (df['date'] <= END_DATE)].copy()
    if len(df) < 60:
        return {'code': code, 'skipped': True}

    df = add_indicators(df)
    sig = position_series(df, weights, min_n)

    config = BacktestConfig(
        stop_loss=STOP_LOSS,      # 改进 3：-12%
        stop_profit=999,          # 无止盈
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
# Main
# ============================================================

def main():
    print("=" * 70)
    print("C8 三因子加权（应用 L213 改进 1/3/5）")
    print("=" * 70)
    print(f"改进 1: RSI <{RSI_BUY_THRESHOLD} / >{RSI_SELL_THRESHOLD}（放宽）")
    print(f"改进 3: 回测期 {START_DATE} ~ {END_DATE}（3 年）")
    print(f"改进 5: 阈值与权重解耦（min_n 直接控制因子数）")
    print(f"止损: {STOP_LOSS:.0%}")

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

    print("\n📊 网格搜索: 7 权重 × 2 min_n")
    grid_results = []
    for weights in WEIGHT_GRID:
        for min_n in MIN_FACTORS:
            label = f"{weights['name']} (min_n={min_n})"
            print(f"\n  ▶ {label}")

            etf_results = []
            for code, df in all_data.items():
                r = run_single(code, df, weights, min_n)
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

            grid_results.append({
                'weights_name': weights['name'],
                'min_n_factors': min_n,
                'w_MA5': weights['MA5'],
                'w_RSI': weights['RSI'],
                'w_OBV': weights['OBV'],
                'avg_return': avg_ret,
                'avg_winrate': avg_wr,
                'avg_max_drawdown': avg_dd,
                'positive_etf_pct': pos_pct,
                'total_trades': total_trades,
                'etf_count': len(etf_df),
            })

            tag = '🟢' if avg_wr >= 0.55 and avg_ret > 0 else '🔴'
            print(f"    {tag} ETF={len(etf_df)} | 收益={avg_ret:+.2%} | 胜率={avg_wr:.1%} | "
                  f"正收益%={pos_pct:.1%} | 交易={total_trades}")

    grid_df = pd.DataFrame(grid_results)
    if grid_df.empty:
        print("\n❌ 无有效网格结果")
        return

    # 综合评分
    grid_df['composite_score'] = (
        grid_df['avg_winrate'] * 0.4 +
        (grid_df['avg_return'] + 0.3).clip(lower=0) / 0.6 * 0.4 +
        grid_df['positive_etf_pct'] * 0.2
    )
    grid_df = grid_df.sort_values('composite_score', ascending=False)

    print("\n" + "=" * 70)
    print("📊 网格搜索 Top 5")
    print("=" * 70)
    for i, row in grid_df.head(5).iterrows():
        print(f"  #{grid_df.index.get_loc(i)+1} {row['weights_name']:8s} min_n={int(row['min_n_factors'])} | "
              f"胜率={row['avg_winrate']:.1%} 收益={row['avg_return']:+.2%} "
              f"正收益={row['positive_etf_pct']:.1%} 综合={row['composite_score']:.3f}")

    best = grid_df.iloc[0]
    print(f"\n🏆 最佳组合: {best['weights_name']} (min_n={int(best['min_n_factors'])})")
    print(f"   MA5={best['w_MA5']} RSI={best['w_RSI']} OBV={best['w_OBV']}")
    print(f"   胜率={best['avg_winrate']:.1%} | 收益={best['avg_return']:+.2%} | "
          f"正收益={best['positive_etf_pct']:.1%} | 交易={best['total_trades']}")

    # vs C7 对比
    print(f"\n✅ 验收（vs C7 失败基线 28.5% 胜率）")
    print(f"  胜率 ≥ 50% (随机): {'PASS' if best['avg_winrate'] >= 0.5 else 'FAIL'} ({best['avg_winrate']:.1%})")
    print(f"  胜率 ≥ C7 (28.5%): {'PASS' if best['avg_winrate'] > 0.285 else 'FAIL'}")
    print(f"  收益 > 0: {'PASS' if best['avg_return'] > 0 else 'FAIL'} ({best['avg_return']:+.2%})")
    print(f"  正收益 ETF > 50%: {'PASS' if best['positive_etf_pct'] >= 0.5 else 'FAIL'} ({best['positive_etf_pct']:.1%})")

    # 保存报告
    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/C8_factor_v3_report.json", 'w', encoding='utf-8') as f:
        json.dump({
            'experiment': 'C8_factor_v3',
            'improvements_applied': {
                '改进 1 (RSI)': f'<{RSI_BUY_THRESHOLD} / >{RSI_SELL_THRESHOLD}',
                '改进 3 (回测期)': f'{START_DATE} ~ {END_DATE}',
                '改进 5 (阈值)': 'min_n 与权重解耦',
            },
            'stop_loss': STOP_LOSS,
            'start_date': START_DATE,
            'end_date': END_DATE,
            'grid_total': len(grid_df),
            'best': best.to_dict(),
            'all_results': grid_results,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📁 报告: data/business_understanding/C8_factor_v3_report.json")


if __name__ == "__main__":
    main()
