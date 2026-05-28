"""
IC计算器

计算因子的IC（信息系数）和IR（信息比率）
"""
import pandas as pd
import numpy as np
from typing import Optional, Dict, Tuple


def calculate_ic(
    factor_values: pd.Series,
    future_returns: pd.Series,
    method: str = 'pearson',
    min_periods: int = 3
) -> float:
    """
    计算IC（信息系数）
    
    IC = Correlation(因子值, 未来收益)
    
    支持两种相关性计算：
    - pearson: 皮尔逊线性相关（默认，速度快）
    - spearman: 斯皮尔曼等级相关（对异常值不敏感）
    
    Args:
        factor_values: 因子值序列
        future_returns: 未来收益序列
        method: 计算方法 'pearson' 或 'spearman'
        min_periods: 最少数据点数
        
    Returns:
        IC值（-1到1之间）
    """
    # 对齐数据
    valid_mask = factor_values.notna() & future_returns.notna()
    
    if valid_mask.sum() < min_periods:
        return np.nan
    
    fv = factor_values[valid_mask].reset_index(drop=True)
    fr = future_returns[valid_mask].reset_index(drop=True)
    
    if len(fv) < min_periods or len(fr) < min_periods:
        return np.nan
    
    try:
        if method == 'pearson':
            ic = fv.corr(fr)
        else:
            # 手动实现Spearman：转换为rank再计算Pearson
            fv_rank = fv.rank()
            fr_rank = fr.rank()
            ic = fv_rank.corr(fr_rank)
    except Exception:
        return np.nan
    
    if pd.isna(ic):
        return 0.0
    
    return float(ic)


def calculate_ir(
    ic_series: pd.Series,
    window: Optional[int] = None
) -> float:
    """
    计算IR（信息比率）
    
    IR = IC均值 / IC标准差
    
    Args:
        ic_series: IC序列
        window: 可选窗口大小
        
    Returns:
        IR值
    """
    if window is not None:
        ic_series = ic_series.iloc[-window:]
    
    valid_ic = ic_series.dropna()
    
    if len(valid_ic) < 2:
        return 0.0
    
    ic_mean = valid_ic.mean()
    ic_std = valid_ic.std()
    
    if ic_std == 0 or np.isnan(ic_std):
        return np.inf if ic_mean > 0 else (-np.inf if ic_mean < 0 else 0.0)
    
    return ic_mean / ic_std


def calculate_rolling_ic(
    factor_values: pd.Series,
    future_returns: pd.Series,
    window: int = 20,
    method: str = 'spearman'
) -> pd.Series:
    """
    计算滚动IC序列
    
    Args:
        factor_values: 因子值
        future_returns: 未来收益
        window: 滚动窗口大小
        method: 计算方法
        
    Returns:
        滚动IC序列
    """
    n = len(factor_values)
    rolling_ic = pd.Series(np.nan, index=factor_values.index)
    
    for i in range(window, n):
        fv = factor_values.iloc[i-window:i]
        fr = future_returns.iloc[i-window:i]
        
        ic = calculate_ic(fv, fr, method)
        rolling_ic.iloc[i] = ic
    
    return rolling_ic


def calculate_factor_ic(
    df: pd.DataFrame,
    factor_col: str,
    return_col: str = 'return_1d',
    window: int = 20,
    min_periods: int = 10
) -> Dict[str, float]:
    """
    计算单个因子的IC统计量
    
    Args:
        df: 包含因子值和收益的DataFrame
        factor_col: 因子列名
        return_col: 收益列名
        window: 窗口大小
        min_periods: 最小周期数
        
    Returns:
        IC统计字典
    """
    factor = df[factor_col]
    returns = df[return_col]
    
    # 有效数据
    valid_mask = factor.notna() & returns.notna()
    
    if valid_mask.sum() < min_periods:
        return {
            'ic_mean': np.nan,
            'ic_std': np.nan,
            'ir': np.nan,
            'hit_rate': np.nan,
            'sample_count': valid_mask.sum()
        }
    
    # 计算滚动IC
    rolling_ic = calculate_rolling_ic(
        factor[valid_mask],
        returns[valid_mask],
        window=window
    )
    
    valid_ic = rolling_ic.dropna()
    
    if len(valid_ic) < 2:
        return {
            'ic_mean': np.nan,
            'ic_std': np.nan,
            'ir': np.nan,
            'hit_rate': np.nan,
            'sample_count': len(valid_ic)
        }
    
    # 统计
    ic_mean = valid_ic.mean()
    ic_std = valid_ic.std()
    ir = ic_mean / ic_std if ic_std > 0 else 0.0
    hit_rate = (valid_ic > 0).sum() / len(valid_ic)
    
    return {
        'ic_mean': ic_mean,
        'ic_std': ic_std,
        'ir': ir,
        'hit_rate': hit_rate,
        'sample_count': len(valid_ic)
    }


def calculate_all_factors_ic(
    df: pd.DataFrame,
    factor_cols: list,
    return_col: str = 'return_1d',
    window: int = 20
) -> pd.DataFrame:
    """
    计算所有因子的IC
    
    Args:
        df: DataFrame
        factor_cols: 因子列名列表
        return_col: 收益列名
        window: 窗口大小
        
    Returns:
        IC结果DataFrame
    """
    results = []
    
    for factor_col in factor_cols:
        stats = calculate_factor_ic(df, factor_col, return_col, window)
        stats['factor_name'] = factor_col
        results.append(stats)
    
    return pd.DataFrame(results)


def determine_direction(ic_mean: float, threshold: float = 0.02) -> str:
    """
    判断因子方向
    
    Args:
        ic_mean: IC均值
        threshold: 阈值（低于此值视为无效）
        
    Returns:
        'long' / 'short' / 'neutral'
    """
    if abs(ic_mean) < threshold:
        return 'neutral'
    
    return 'long' if ic_mean > 0 else 'short'


def format_ic_result(stats: Dict[str, float], factor_name: str) -> str:
    """
    格式化IC结果输出
    
    Args:
        stats: IC统计字典
        factor_name: 因子名称
        
    Returns:
        格式化字符串
    """
    direction = determine_direction(stats.get('ic_mean', 0))
    direction_symbol = '📈' if direction == 'long' else ('📉' if direction == 'short' else '➡️')
    
    return f"""
{factor_name}:
  IC均值: {stats.get('ic_mean', 0):.4f}
  IC标准差: {stats.get('ic_std', 0):.4f}
  IR: {stats.get('ir', 0):.4f}
  胜率: {stats.get('hit_rate', 0):.2%}
  样本数: {stats.get('sample_count', 0)}
  方向: {direction} {direction_symbol}
"""


# 8个核心因子列表
CORE_FACTORS = [
    'DMA',           # 趋势
    'RSI_5',         # 动量
    'OBV_diff',       # 量能
    'DIF',           # 动量
    'K',             # 动量
    'BB_percent',    # 波动
    'SAR_trend',     # 趋势
    'ADX',           # 趋势强度
]

# 可选因子列表
OPTIONAL_FACTORS = [
    'RSI_10',
    'MA_short',
    'MA_long',
    'MAOBV',
    'D',
    'J',
    'MACD_hist',
    'BB_upper',
    'BB_lower',
    'DI_plus',
    'DI_minus',
]