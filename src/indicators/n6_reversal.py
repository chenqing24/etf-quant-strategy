#!/usr/bin/env python3
"""
N6 反转策略因子（IS-003）
按 SOP-01 Step 2 候选因子规范：3 个反转类因子

因子设计：
- N1_3日反转: 3 日跌幅超过阈值 → 买入（均值回归）
- N2_5日反转: 5 日跌幅超过阈值 → 买入（均值回归）
- N3_RSI超卖反弹: RSI < 30 → 买入（超卖反弹）

与现有动量因子的区别：
- M1_动量3日: 3 日涨幅 → 买入（趋势延续）
- N1_3日反转: 3 日跌幅 → 买入（均值回归）
"""
import pandas as pd
import numpy as np
from typing import Dict, List


# 反转因子配置
N6_REVERSAL_FACTORS = {
    'N1_3日反转': {
        'type': 'reversal_momentum',
        'period': 3,
        'threshold': -0.03,  # 3 日跌幅 > 3% 触发
        'direction': 'short_to_long',  # 跌多了要反弹
        'description': '3 日跌幅 > 3% → 买入',
    },
    'N2_5日反转': {
        'type': 'reversal_momentum',
        'period': 5,
        'threshold': -0.05,  # 5 日跌幅 > 5% 触发
        'direction': 'short_to_long',
        'description': '5 日跌幅 > 5% → 买入',
    },
    'N3_RSI超卖反弹': {
        'type': 'rsi_oversold',
        'period': 14,
        'threshold': 30,  # RSI < 30 触发
        'direction': 'oversold_bounce',
        'description': 'RSI(14) < 30 → 买入',
    },
}


def calc_momentum(df: pd.DataFrame, period: int) -> pd.Series:
    """计算 period 日动量（return）"""
    return df['close'].pct_change(period)


def calc_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """计算 RSI"""
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def signal_n1_3d_reversal(df: pd.DataFrame) -> pd.Series:
    """N1_3日反转信号：3 日跌幅 > 3% → True"""
    mom3 = calc_momentum(df, 3)
    return (mom3 < N6_REVERSAL_FACTORS['N1_3日反转']['threshold']).fillna(False)


def signal_n2_5d_reversal(df: pd.DataFrame) -> pd.Series:
    """N2_5日反转信号：5 日跌幅 > 5% → True"""
    mom5 = calc_momentum(df, 5)
    return (mom5 < N6_REVERSAL_FACTORS['N2_5日反转']['threshold']).fillna(False)


def signal_n3_rsi_oversold(df: pd.DataFrame) -> pd.Series:
    """N3_RSI超卖反弹信号：RSI(14) < 30 → True"""
    rsi = calc_rsi(df, 14)
    return (rsi < N6_REVERSAL_FACTORS['N3_RSI超卖反弹']['threshold']).fillna(False)


# 信号函数注册表（与 v8_sop.py 的 FACTORS 格式一致）
N6_SIGNAL_FUNCS = {
    'N1_3日反转': signal_n1_3d_reversal,
    'N2_5日反转': signal_n2_5d_reversal,
    'N3_RSI超卖反弹': signal_n3_rsi_oversold,
}


def get_n6_signals(df: pd.DataFrame) -> pd.DataFrame:
    """一次性计算所有 N6 信号的 DataFrame"""
    return pd.DataFrame({
        'N1_3日反转': signal_n1_3d_reversal(df),
        'N2_5日反转': signal_n2_5d_reversal(df),
        'N3_RSI超卖反弹': signal_n3_rsi_oversold(df),
    })


def main():
    """测试 N6 反转因子"""
    import sys
    from pathlib import Path

    ROOT = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(ROOT))

    from src.data.loader import DataLoader
    loader = DataLoader()

    sys.exit(_run(loader))


def _run(loader):
    """主逻辑"""

    print("IS-003 N6 反转因子测试")
    print("=" * 60)

    df = loader.load_single('510300', min_rows=400)
    if df is None:
        print("❌ 数据加载失败")
        return 1

    print(f"510300 数据: {df['date'].min()} ~ {df['date'].max()} ({len(df)} 行)")

    # 计算 N6 信号
    signals = get_n6_signals(df)

    print(f"\nN6 信号触发统计:")
    for col in signals.columns:
        n = signals[col].sum()
        pct = n / len(signals) * 100
        print(f"  {col}: {n}/{len(signals)} ({pct:.1f}%)")

    # 计算单因子 IC
    df_with_ret = df.copy()
    df_with_ret['next_return_5d'] = df['close'].pct_change(5).shift(-5)
    df_with_ret = df_with_ret.join(signals)

    print(f"\n单因子 IC（5 日未来收益）:")
    for col in signals.columns:
        valid = df_with_ret[[col, 'next_return_5d']].dropna()
        if len(valid) > 10:
            ic = valid[col].astype(int).corr(valid['next_return_5d'])
            print(f"  {col}: IC = {ic:.4f}, 样本数 = {len(valid)}")

    return 0


if __name__ == '__main__':
    main()
