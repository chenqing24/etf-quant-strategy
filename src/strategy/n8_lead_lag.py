#!/usr/bin/env python3
"""
N8 跨 ETF 领先-滞后策略（IS-005）
按 SOP-01 Step 6 规范：利用 ETF 间领先关系增强信号

核心假设：
- 大盘 ETF（510300）领先行业/主题 ETF
- 强势主题 ETF 领先弱势主题
- 领先 ETF 突破 → 跟随 ETF 同向突破 = 强信号

实现：
1. 计算领先 ETF 池（默认 510300）的趋势状态
2. 计算跟随 ETF 自身的趋势状态
3. 当两者共振时：信号强度 × 1.5（增强）
4. 当领先 ETF 反对时：信号强度 × 0.5（弱化）
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass


# 预设的领先 ETF 关系
# key = 跟随 ETF, value = (主领先 ETF, [次领先 ETF 列表])
LEAD_LAG_MAP = {
    # 沪深300 领先所有
    '510300': ('510300', []),
    '515650': ('510300', ['515070']),  # 消费 跟随沪深300 + 食品
    '515070': ('510300', []),           # 人工智能 跟随沪深300
    '512400': ('510300', ['512480']),   # 有色 跟随沪深300 + 钢铁
    '512480': ('510300', ['512400']),   # 钢铁 跟随沪深300 + 有色
    '588000': ('510300', ['512480']),   # 科创50 跟随沪深300 + 钢铁（弱关联）
    '520900': ('510300', []),           # 红利
    '512880': ('510300', []),           # 证券
    '512170': ('510300', ['512880']),   # 医疗 跟随沪深300 + 证券（避险）
    '512660': ('510300', []),           # 军工
    '512200': ('510300', ['512660']),   # 房地产 跟随沪深300 + 军工
    '512800': ('510300', []),           # 银行
    '512980': ('510300', ['512800']),   # 传媒 跟随沪深300 + 银行
    '515050': ('510300', []),           # 5G
    '515790': ('510300', []),           # 光伏
}

# 备用：默认 510300 为通用领先
DEFAULT_LEADER = '510300'


@dataclass
class LeadLagSignal:
    """领先-滞后信号"""
    base_signal: bool  # 跟随 ETF 自身信号
    leader_signal: bool  # 领先 ETF 信号
    resonance: str  # 'resonance' / 'divergence' / 'neutral'
    strength: float  # 1.5 / 0.5 / 1.0
    leader_code: str


def calc_trend_state(df: pd.DataFrame, fast: int = 5, slow: int = 20) -> pd.Series:
    """计算趋势状态：MA5 > MA20 → 1（上升），否则 0

    Returns:
        Series of 0/1
    """
    ma_fast = df['close'].rolling(fast, min_periods=1).mean()
    ma_slow = df['close'].rolling(slow, min_periods=1).mean()
    return (ma_fast > ma_slow).astype(int)


def get_leader_code(follower_code: str) -> str:
    """获取领先 ETF 代码"""
    if follower_code in LEAD_LAG_MAP:
        return LEAD_LAG_MAP[follower_code][0]
    return DEFAULT_LEADER


def calc_lead_lag_signal(
    follower_df: pd.DataFrame,
    leader_df: Optional[pd.DataFrame] = None,
    follower_code: str = '',
    fast: int = 5,
    slow: int = 20,
) -> pd.DataFrame:
    """计算领先-滞后信号

    Args:
        follower_df: 跟随 ETF 数据
        leader_df: 领先 ETF 数据（None 则用同 df 自身）
        follower_code: 跟随 ETF 代码
        fast: 快线周期
        slow: 慢线周期

    Returns:
        DataFrame 新增 leader_signal, resonance, strength 列
    """
    df = follower_df.copy()

    if leader_df is None:
        # 同 df 内部分 leader/follower
        df['follower_signal'] = calc_trend_state(df, fast, slow)
        df['leader_signal'] = df['follower_signal'].shift(1).fillna(0).astype(int)  # 用昨日作为 leader
        leader_code = follower_code
    else:
        # 跨 ETF 领先
        df['follower_signal'] = calc_trend_state(df, fast, slow)
        leader_signal = calc_trend_state(leader_df, fast, slow)
        # 对齐日期
        leader_signal.index = leader_df['date']
        df['leader_signal'] = df['date'].map(leader_signal).fillna(0).astype(int)
        leader_code = get_leader_code(follower_code)

    # 计算共振
    def _resonance(row):
        if row['follower_signal'] == 1 and row['leader_signal'] == 1:
            return 'resonance'
        elif row['follower_signal'] == 1 and row['leader_signal'] == 0:
            return 'divergence'
        elif row['follower_signal'] == 0 and row['leader_signal'] == 1:
            return 'leader_alone'
        else:
            return 'neutral'

    df['resonance'] = df.apply(_resonance, axis=1)
    df['strength'] = df['resonance'].map({
        'resonance': 1.5,
        'divergence': 0.5,
        'leader_alone': 0.7,
        'neutral': 1.0,
    })
    df['leader_code'] = leader_code

    return df


def aggregate_resonance(df: pd.DataFrame) -> Dict:
    """聚合共振统计"""
    return {
        'resonance': int((df['resonance'] == 'resonance').sum()),
        'divergence': int((df['resonance'] == 'divergence').sum()),
        'leader_alone': int((df['resonance'] == 'leader_alone').sum()),
        'neutral': int((df['resonance'] == 'neutral').sum()),
        'avg_strength': float(df['strength'].mean()),
    }


def main():
    """测试 N8 跨 ETF 领先-滞后"""
    import sys
    from pathlib import Path

    ROOT = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(ROOT))

    from src.data.loader import DataLoader

    loader = DataLoader()
    print("IS-005 N8 跨 ETF 领先-滞后测试")
    print("=" * 60)

    # 测试 1: 同 df 内部 leader/follower（用昨日作为 leader）
    df_510300 = loader.load_single('510300', min_rows=400)
    if df_510300 is None:
        print("❌ 510300 数据加载失败")
        return 1

    df_with_ll = calc_lead_lag_signal(df_510300, leader_df=None, follower_code='510300')
    stats = aggregate_resonance(df_with_ll)
    print(f"\n测试 1: 510300 同 df leader/follower")
    print(f"  共振: {stats['resonance']} 次")
    print(f"  背离: {stats['divergence']} 次")
    print(f"  leader 单独: {stats['leader_alone']} 次")
    print(f"  中性: {stats['neutral']} 次")
    print(f"  平均强度: {stats['avg_strength']:.3f}")

    # 测试 2: 跨 ETF（515070 跟随 510300）
    df_515070 = loader.load_single('515070', min_rows=400)
    if df_515070 is not None:
        df_cross = calc_lead_lag_signal(df_515070, leader_df=df_510300, follower_code='515070')
        stats_cross = aggregate_resonance(df_cross)
        print(f"\n测试 2: 515070 跟随 510300")
        print(f"  共振: {stats_cross['resonance']} 次")
        print(f"  背离: {stats_cross['divergence']} 次")
        print(f"  leader 单独: {stats_cross['leader_alone']} 次")
        print(f"  中性: {stats_cross['neutral']} 次")
        print(f"  平均强度: {stats_cross['avg_strength']:.3f}")

    return 0


if __name__ == '__main__':
    main()
