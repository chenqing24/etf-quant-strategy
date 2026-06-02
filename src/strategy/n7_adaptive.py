#!/usr/bin/env python3
"""
N7 自适应参数策略（IS-004）
按 SOP-01 Step 2/7 规范：根据市场状态动态调整 SL/SP/MH

参数自适应逻辑：
- ATR(14): 14 日平均真实波幅 → 决定 SL/SP 宽度
  - 高波动 (ATR > close * 5%): SL=-8%, SP=+15%
  - 中波动 (ATR 2%~5%):    SL=-5%, SP=+10%（默认）
  - 低波动 (ATR < 2%):     SL=-3%, SP=+6%
- ADX(14): 趋势强度 → 决定 min_hold_days
  - 强趋势 (ADX > 25): min_hold = 5（给趋势时间）
  - 中趋势 (ADX 15-25): min_hold = 3（默认）
  - 弱趋势 (ADX < 15): min_hold = 2（快速出场）
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Tuple, Optional


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """计算 ATR(Average True Range)"""
    high = df['high']
    low = df['low']
    close = df['close']

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period, min_periods=1).mean()
    return atr


def calc_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """简化版 ADX(平均趋向指数)"""
    high = df['high']
    low = df['low']
    close = df['close']

    # +DM, -DM
    up = high.diff()
    down = -low.diff()

    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    # TR
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # 平滑
    atr = tr.rolling(period, min_periods=1).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(period, min_periods=1).sum() / atr.replace(0, np.nan)
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(period, min_periods=1).sum() / atr.replace(0, np.nan)

    # DX, ADX
    di_sum = plus_di + minus_di
    di_diff = (plus_di - minus_di).abs()
    dx = 100 * di_diff / di_sum.replace(0, np.nan)
    adx = dx.rolling(period, min_periods=1).mean()
    return adx.fillna(15.0)


@dataclass
class AdaptiveParams:
    """自适应参数"""
    stop_loss: float
    stop_profit: float
    min_hold_days: int
    regime: str  # 'high_vol' / 'mid_vol' / 'low_vol' / 'strong_trend' / 'weak_trend'


def get_adaptive_params(atr: float, adx: float, close: float) -> AdaptiveParams:
    """根据 ATR 和 ADX 返回自适应参数

    优先级：先按 ATR 分波动档，再按 ADX 微调
    """
    atr_pct = atr / close if close > 0 else 0.03

    # 波动率分档
    if atr_pct > 0.05:
        stop_loss = -0.08
        stop_profit = 0.15
        vol_regime = 'high_vol'
    elif atr_pct > 0.02:
        stop_loss = -0.05
        stop_profit = 0.10
        vol_regime = 'mid_vol'
    else:
        stop_loss = -0.03
        stop_profit = 0.06
        vol_regime = 'low_vol'

    # 趋势强度分档
    if adx > 25:
        min_hold_days = 5
        trend_regime = 'strong_trend'
    elif adx > 15:
        min_hold_days = 3
        trend_regime = 'mid_trend'
    else:
        min_hold_days = 2
        trend_regime = 'weak_trend'

    return AdaptiveParams(
        stop_loss=stop_loss,
        stop_profit=stop_profit,
        min_hold_days=min_hold_days,
        regime=f"{vol_regime}_{trend_regime}"
    )


def calc_signal_with_adaptive_params(
    df: pd.DataFrame,
    signal_col: str,
    atr_period: int = 14,
    adx_period: int = 14,
) -> pd.DataFrame:
    """对每行计算自适应参数

    Args:
        df: 包含 close/high/low 的 DataFrame
        signal_col: 触发信号的列名（如 'buy_signal'）

    Returns:
        DataFrame 新增 stop_loss, stop_profit, min_hold_days, regime 列
    """
    df = df.copy()
    atr = calc_atr(df, atr_period)
    adx = calc_adx(df, adx_period)

    # 对每个有效信号行计算自适应参数
    params_list = []
    for i in range(len(df)):
        if pd.isna(atr.iloc[i]) or pd.isna(adx.iloc[i]) or pd.isna(df['close'].iloc[i]):
            params_list.append(None)
            continue
        params = get_adaptive_params(
            atr=atr.iloc[i],
            adx=adx.iloc[i],
            close=df['close'].iloc[i],
        )
        params_list.append(params)

    df['atr'] = atr
    df['adx'] = adx
    df['stop_loss'] = [p.stop_loss if p else -0.05 for p in params_list]
    df['stop_profit'] = [p.stop_profit if p else 0.10 for p in params_list]
    df['min_hold_days'] = [p.min_hold_days if p else 3 for p in params_list]
    df['regime'] = [p.regime if p else 'unknown' for p in params_list]

    return df


# 自适应参数档位参考（用于参数网格）
ADAPTIVE_PARAM_GRID = {
    'volatility_buckets': [
        {'name': 'low_vol', 'atr_pct_max': 0.02, 'stop_loss': -0.03, 'stop_profit': 0.06},
        {'name': 'mid_vol', 'atr_pct_max': 0.05, 'stop_loss': -0.05, 'stop_profit': 0.10},
        {'name': 'high_vol', 'atr_pct_max': 1.00, 'stop_loss': -0.08, 'stop_profit': 0.15},
    ],
    'trend_buckets': [
        {'name': 'weak_trend', 'adx_max': 15, 'min_hold_days': 2},
        {'name': 'mid_trend', 'adx_max': 25, 'min_hold_days': 3},
        {'name': 'strong_trend', 'adx_max': 100, 'min_hold_days': 5},
    ],
}


def main():
    """测试 N7 自适应参数"""
    import sys
    from pathlib import Path

    ROOT = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(ROOT))

    from src.data.loader import DataLoader

    loader = DataLoader()
    df = loader.load_single('510300', min_rows=400)
    if df is None:
        print("❌ 数据加载失败")
        return 1

    print("IS-004 N7 自适应参数测试（510300）")
    print("=" * 60)
    print(f"数据: {df['date'].min()} ~ {df['date'].max()} ({len(df)} 行)")

    # 计算自适应参数
    df_with_params = calc_signal_with_adaptive_params(df, 'buy_signal')

    # 统计 regime 分布
    print(f"\n市场状态分布:")
    print(df_with_params['regime'].value_counts().to_string())

    # ATR / ADX 统计
    print(f"\nATR(14) 统计:")
    print(f"  mean = {df_with_params['atr'].mean():.4f}")
    print(f"  std  = {df_with_params['atr'].std():.4f}")
    print(f"  min  = {df_with_params['atr'].min():.4f}")
    print(f"  max  = {df_with_params['atr'].max():.4f}")

    print(f"\nADX(14) 统计:")
    print(f"  mean = {df_with_params['adx'].mean():.2f}")
    print(f"  std  = {df_with_params['adx'].std():.2f}")

    # 自适应参数与默认参数对比
    print(f"\n参数分布:")
    print(f"  stop_loss 唯一值: {sorted(df_with_params['stop_loss'].unique())}")
    print(f"  stop_profit 唯一值: {sorted(df_with_params['stop_profit'].unique())}")
    print(f"  min_hold_days 唯一值: {sorted(df_with_params['min_hold_days'].unique())}")

    # 模拟一遍：用 5 日均线 > 20 日均线 作为信号源
    df_with_params['MA5'] = df['close'].rolling(5).mean()
    df_with_params['MA20'] = df['close'].rolling(20).mean()
    df_with_params['buy_signal'] = (df_with_params['MA5'] > df_with_params['MA20']).astype(int)
    n_signals = df_with_params['buy_signal'].sum()
    print(f"\n5日>20日 信号触发: {n_signals} 次")

    return 0


if __name__ == '__main__':
    main()
