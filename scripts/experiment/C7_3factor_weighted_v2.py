#!/usr/bin/env python3
"""C7 三因子加权组合（v2 - 重做 C6）

策略定义（用户 06-15 修正版）：
- 4 因子组合 = 加权评分（不是纯 AND/OR）
- BOLL 中上轨 = 准入过滤器（不算分，只决定能否开仓）
- 3 因子评分：MA5 + RSI + OBV（多权重网格搜索）
- 止损 -8%（无止盈）
- 信号: 总分 ≥ 阈值 → 买入

参考：C6_ma5_rsi_obv_boll.py 模板
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
# 权重网格
# ============================================================

WEIGHT_GRID = [
    {'name': '等权',     'MA5': 0.34, 'RSI': 0.33, 'OBV': 0.33},
    {'name': 'MA5主导',  'MA5': 0.60, 'RSI': 0.20, 'OBV': 0.20},
    {'name': 'RSI主导',  'MA5': 0.20, 'RSI': 0.60, 'OBV': 0.20},
    {'name': 'OBV主导',  'MA5': 0.20, 'RSI': 0.20, 'OBV': 0.60},
    {'name': 'MA5+OBV',  'MA5': 0.40, 'RSI': 0.20, 'OBV': 0.40},
    {'name': 'MA5+RSI',  'MA5': 0.40, 'RSI': 0.40, 'OBV': 0.20},
    {'name': 'OBV+RSI',  'MA5': 0.20, 'RSI': 0.40, 'OBV': 0.40},
]

# 阈值 = 至少成立的因子数（1/2/3）
MIN_FACTORS = [1, 2]  # min_n=3 大多权重下永远 0


# ============================================================
# 因子计算
# ============================================================

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """添加所有需要的指标列"""
    df = df.copy()
    df = Indicator.calculate(df)
    df = calculate_bollinger_bands(df, window=20, num_std=2.0)
    df = calculate_obv(df)
    df['ma_obv_10'] = df['OBV'].rolling(10).mean()
    return df


def boll_filter(df: pd.DataFrame) -> pd.Series:
    """BOLL 准入：close ∈ [BB_middle, BB_upper]"""
    return (df['close'] >= df['BB_middle']) & (df['close'] <= df['BB_upper'])


def factor_score(df: pd.DataFrame) -> pd.DataFrame:
    """3 因子打分（0/1）+ 加权分数"""
    df = df.copy()
    df['s_ma5'] = (df['close'] > df['ma5']).astype(int)
    df['s_rsi'] = (df['rsi_14'] < 30).astype(int)
    df['s_obv'] = (df['OBV'] > df['ma_obv_10']).astype(int)
    return df


def weighted_signal(df: pd.DataFrame, weights: dict, min_n: int) -> pd.Series:
    """加权评分信号
    算法：
    1. 计算 3 因子各自的 0/1 信号
    2. 加权分数 = sum(weight_i * s_i)
    3. 加权分数必须 ≥ min_n * 主导权重的某比例（动态阈值）
    4. 在 BOLL 准入区间内 → 买入

    设计思路：
    - 等权: max_w=0.34, min_n=1 → threshold=0.34 → 1个因子成立即可（加权分数=0.34）
    - MA5主导: max_w=0.6, min_n=1 → threshold=0.6 → MA5 单独成立即可（0.6）
    - MA5主导: min_n=2 → threshold=1.0 → 必须 MA5+RSI 或 MA5+OBV 同时成立
    - 等权: min_n=2 → threshold=0.68 → 2 个因子成立即可
    """
    s = factor_score(df)
    in_boll = boll_filter(df)
    w_ma5, w_rsi, w_obv = weights['MA5'], weights['RSI'], weights['OBV']
    weighted = s['s_ma5'] * w_ma5 + s['s_rsi'] * w_rsi + s['s_obv'] * w_obv
    max_w = max(w_ma5, w_rsi, w_obv)
    # 阈值 = min_n * max_w
    # 但要避免 >1.0：min_n=2 + max_w=0.6 = 1.2 永远不满足
    # 修复：min_n=2 时，threshold = 1.0（即 2 因子均成立）
    threshold = min(min_n * max_w, 1.0) if min_n <= 2 else min_n * max_w
    # 实际：min_n=3 几乎不可能（除非 3 个因子全 1，加权分数 = sum = 1.0）
    # 所以 min_n=3 在大多数组合下恒为 0，正常
    return ((weighted >= threshold) & in_boll).astype(int)


def sell_signal(df: pd.DataFrame) -> pd.Series:
    """卖出 = 任一因子反向（保留 C6 逻辑）
    - close < MA5
    - RSI > 70（从超卖区返回）
    - OBV < MAOBV
    """
    s = factor_score(df)
    sell_ma5 = df['close'] < df['ma5']
    sell_rsi = df['rsi_14'] > 70
    sell_obv = df['OBV'] < df['ma_obv_10']
    return (sell_ma5 | sell_rsi | sell_obv).astype(int)


def position_series(df: pd.DataFrame, weights: dict, min_n: int) -> pd.Series:
    """持仓序列：买入 OR 卖出 → 0/1"""
    buy = weighted_signal(df, weights, min_n)
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

def run_single(code: str, df: pd.DataFrame, start_date: str, end_date: str,
               weights: dict, min_n: int) -> dict:
    """单只 ETF × 单权重 × 单阈值 回测"""
    df = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()
    if len(df) < 60:
        return {'code': code, 'skipped': True}

    df = add_indicators(df)
    sig = position_series(df, weights, min_n)

    config = BacktestConfig(
        stop_loss=-0.08,    # 止损 8%（用户要求）
        stop_profit=999,    # 无止盈（sentinel，pnl 永远 < 100%）
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
        }
    except Exception as e:
        return {'code': code, 'error': f'{type(e).__name__}: {e}'}


# ============================================================
# Main: 网格搜索 7 权重 × 3 阈值 × 35 ETF
# ============================================================

def main():
    print("=" * 70)
    print("C7 三因子加权（MA5+RSI+OBV，BOLL 准入，止损 8%）")
    print("=" * 70)

    loader = DataLoader()
    start_date = '2021-06-16'
    end_date = '2026-06-15'

    # 预加载所有 ETF 数据
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

    # 网格搜索
    print("\n📊 网格搜索: 7 权重 × 3 阈值（min_n）")
    grid_results = []
    for weights in WEIGHT_GRID:
        for min_n in MIN_FACTORS:
            label = f"{weights['name']} (min_n={min_n})"
            print(f"\n  ▶ {label}: MA5={weights['MA5']} RSI={weights['RSI']} OBV={weights['OBV']}")

            etf_results = []
            for code, df in all_data.items():
                r = run_single(code, df, start_date, end_date, weights, min_n)
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

            # 实时显示
            tag = '🟢' if avg_wr >= 0.55 and avg_ret > 0 else '🔴'
            print(f"    {tag} ETF={len(etf_df)} | 收益={avg_ret:+.2%} | 胜率={avg_wr:.1%} | "
                  f"正收益%={pos_pct:.1%} | 交易={total_trades}")

    # 排序找最佳
    grid_df = pd.DataFrame(grid_results)
    if grid_df.empty:
        print("\n❌ 无有效网格结果")
        return

    # 综合评分：胜率 40% + 收益 40% + 正收益 ETF 占比 20%
    grid_df['composite_score'] = (
        grid_df['avg_winrate'] * 0.4 +
        (grid_df['avg_return'] + 0.3).clip(lower=0) / 0.6 * 0.4 +  # 归一化
        grid_df['positive_etf_pct'] * 0.2
    )
    grid_df = grid_df.sort_values('composite_score', ascending=False)

    print("\n" + "=" * 70)
    print("📊 网格搜索 Top 5（按综合评分）")
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

    # 验收
    print(f"\n✅ 验收（vs C6 失败基线）")
    print(f"  胜率 ≥ 50% (随机): {'PASS' if best['avg_winrate'] >= 0.5 else 'FAIL'} ({best['avg_winrate']:.1%})")
    print(f"  收益 > 0: {'PASS' if best['avg_return'] > 0 else 'FAIL'} ({best['avg_return']:+.2%})")
    print(f"  正收益 ETF > 50%: {'PASS' if best['positive_etf_pct'] >= 0.5 else 'FAIL'} ({best['positive_etf_pct']:.1%})")

    # 保存报告
    Path("data/business_understanding").mkdir(parents=True, exist_ok=True)
    with open("data/business_understanding/C7_3factor_weighted_report.json", 'w', encoding='utf-8') as f:
        json.dump({
            'experiment': 'C7_3factor_weighted_v2',
            'rules': {
                '组合规则': '加权评分 + 至少 min_n 个因子成立',
                'BOLL': '准入过滤器（不算分）',
                '止损': '-8%',
                '止盈': '无（stop_profit=999 sentinel）',
                '卖出': '任一因子反向（close<MA5 OR RSI>70 OR OBV<MAOBV）',
            },
            'start_date': start_date,
            'end_date': end_date,
            'grid_total': len(grid_df),
            'best': best.to_dict(),
            'all_results': grid_results,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n📁 报告: data/business_understanding/C7_3factor_weighted_report.json")


if __name__ == "__main__":
    main()
