"""
指标计算封装器

使用pandas-ta库封装8个核心指标的批量计算
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from src.analysis.ic_calculator import CORE_FACTORS


# pandas-ta指标参数配置
INDICATOR_CONFIG = {
    'RSI_5': {'func': 'rsi', 'params': {'length': 5}},
    'RSI_10': {'func': 'rsi', 'params': {'length': 10}},
    'DMA': {'func': 'dma', 'params': {}},  # 自定义实现
    'MACD': {'func': 'macd', 'params': {}},  # 自定义实现
    'KDJ': {'func': 'kdj', 'params': {}},  # 自定义实现
    'OBV': {'func': 'obv', 'params': {}},  # 自定义实现
    'BB': {'func': 'bbands', 'params': {'length': 20, 'std': 2}},
    'SAR': {'func': 'sar', 'params': {}},  # 自定义实现
    'ADX': {'func': 'adx', 'params': {'length': 14}},
}


class IndicatorCalculator:
    """指标计算器"""
    
    def __init__(self):
        """初始化计算器"""
        self._use_pandas_ta = self._check_pandas_ta()
    
    def _check_pandas_ta(self) -> bool:
        """检查pandas-ta是否可用"""
        try:
            import pandas_ta as ta
            return True
        except ImportError:
            return False
    
    def calculate_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算所有8个核心指标
        
        Args:
            df: 包含OHLCV数据的DataFrame
            
        Returns:
            添加了所有指标列的DataFrame
        """
        df = df.copy()
        
        # 趋势类指标
        df = self._calculate_dma(df)
        df = self._calculate_sar(df)
        
        # 动量类指标
        df = self._calculate_rsi(df)
        df = self._calculate_macd(df)
        df = self._calculate_kdj(df)
        
        # 量能类指标
        df = self._calculate_obv(df)
        
        # 波动类指标
        df = self._calculate_bollinger(df)
        
        # 趋势强度
        df = self._calculate_adx(df)
        
        return df
    
    def _calculate_dma(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算DMA指标"""
        close = df['close']
        
        # 短期均线
        ma_short = close.rolling(window=10, min_periods=1).mean()
        # 长期均线
        ma_long = close.rolling(window=50, min_periods=1).mean()
        # DMA = 短期 - 长期
        df['DMA'] = ma_short - ma_long
        df['MA_short'] = ma_short
        df['MA_long'] = ma_long
        
        return df
    
    def _calculate_rsi(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算RSI指标"""
        close = df['close']
        
        # RSI(5)
        delta = close.diff()
        gain = delta.copy()
        loss = delta.copy()
        gain[gain < 0] = 0
        loss[loss > 0] = 0
        loss = loss.abs()
        
        avg_gain = gain.ewm(com=4, adjust=False).mean()
        avg_loss = loss.ewm(com=4, adjust=False).mean()
        rs = avg_gain / avg_loss
        df['RSI_5'] = 100 - (100 / (1 + rs))
        
        # RSI(10)
        avg_gain10 = gain.ewm(com=9, adjust=False).mean()
        avg_loss10 = loss.ewm(com=9, adjust=False).mean()
        rs10 = avg_gain10 / avg_loss10
        df['RSI_10'] = 100 - (100 / (1 + rs10))
        
        return df
    
    def _calculate_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算MACD指标"""
        close = df['close']
        
        # EMA(12) 和 EMA(26)
        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        
        # DIF = 快线 - 慢线
        df['DIF'] = ema_fast - ema_slow
        # DEA = DIF的EMA(9)
        df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
        # MACD柱 = (DIF - DEA) * 2
        df['MACD_hist'] = (df['DIF'] - df['DEA']) * 2
        
        return df
    
    def _calculate_kdj(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算KDJ指标"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        n = 9  # RSV周期
        
        # N日内最低价和最高价
        lowest_low = low.rolling(window=n, min_periods=1).min()
        highest_high = high.rolling(window=n, min_periods=1).max()
        
        # RSV
        rsv = (close - lowest_low) / (highest_high - lowest_low) * 100
        rsv = rsv.fillna(50)
        
        # K值（平滑）
        df['K'] = rsv.ewm(com=2, adjust=False).mean()
        # D值（平滑）
        df['D'] = df['K'].ewm(com=2, adjust=False).mean()
        # J值
        df['J'] = 3 * df['K'] - 2 * df['D']
        
        return df
    
    def _calculate_obv(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算OBV和MAOBV指标"""
        close = df['close']
        volume = df['volume']
        
        # 价格变化方向
        price_change = close.diff()
        price_change.iloc[0] = 0
        
        # OBV累加
        obv = pd.Series(0.0, index=df.index)
        obv[price_change > 0] = volume[price_change > 0]
        obv[price_change < 0] = -volume[price_change < 0]
        
        df['OBV'] = obv.cumsum()
        df['MAOBV'] = df['OBV'].rolling(window=10, min_periods=1).mean()
        # OBV差值（用于信号）
        df['OBV_diff'] = df['OBV'] - df['MAOBV']
        
        return df
    
    def _calculate_bollinger(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算布林带指标"""
        close = df['close']
        
        window = 20
        std = 2
        
        # 中轨
        middle = close.rolling(window=window, min_periods=1).mean()
        # 标准差
        std_dev = close.rolling(window=window, min_periods=1).std()
        
        df['BB_upper'] = middle + std * std_dev
        df['BB_middle'] = middle
        df['BB_lower'] = middle - std * std_dev
        
        # 布林带位置百分比
        band_range = df['BB_upper'] - df['BB_lower']
        band_range = band_range.replace(0, np.nan)
        df['BB_percent'] = (close - df['BB_lower']) / band_range * 100
        df['BB_percent'] = df['BB_percent'].fillna(50)
        
        return df
    
    def _calculate_sar(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算SAR指标"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        n = len(df)
        
        # 初始化
        sar = pd.Series(np.nan, index=df.index)
        trend = pd.Series(1, index=df.index)
        ep = pd.Series(np.nan, index=df.index)
        af = pd.Series(0.02, index=df.index)
        
        # 初始化第一行
        if n > 0:
            sar.iloc[0] = low.iloc[0]
            ep.iloc[0] = high.iloc[0]
            trend.iloc[0] = 1
        
        # 迭代计算
        for i in range(1, n):
            prev_sar = sar.iloc[i-1]
            prev_trend = trend.iloc[i-1]
            prev_ep = ep.iloc[i-1]
            prev_af = af.iloc[i-1]
            
            # 当前SAR
            current_sar = prev_sar + prev_af * (prev_ep - prev_sar)
            
            if prev_trend == 1:  # 多头
                if low.iloc[i] < current_sar:
                    current_sar = prev_ep
                    current_trend = -1
                    current_ep = low.iloc[i]
                    current_af = 0.02
                else:
                    current_trend = 1
                    current_ep = max(prev_ep, high.iloc[i])
                    current_af = min(prev_af + 0.02, 0.2)
            else:  # 空头
                if high.iloc[i] > current_sar:
                    current_sar = prev_ep
                    current_trend = 1
                    current_ep = high.iloc[i]
                    current_af = 0.02
                else:
                    current_trend = -1
                    current_ep = min(prev_ep, low.iloc[i])
                    current_af = min(prev_af + 0.02, 0.2)
            
            sar.iloc[i] = current_sar
            trend.iloc[i] = current_trend
            ep.iloc[i] = current_ep
            af.iloc[i] = current_af
        
        df['SAR'] = sar
        df['SAR_trend'] = trend
        
        return df
    
    def _calculate_adx(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算ADX指标"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        window = 14
        
        # 真实波幅
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # 趋向
        up_move = high.diff()
        down_move = -low.diff()
        
        dm_plus = pd.Series(0.0, index=df.index)
        dm_minus = pd.Series(0.0, index=df.index)
        dm_plus[(up_move > down_move) & (up_move > 0)] = up_move
        dm_minus[(down_move > up_move) & (down_move > 0)] = down_move
        
        # 平滑
        tr_smooth = tr.rolling(window=window, min_periods=window).sum()
        dm_plus_smooth = dm_plus.rolling(window=window, min_periods=window).sum()
        dm_minus_smooth = dm_minus.rolling(window=window, min_periods=window).sum()
        
        # DI
        di_plus = dm_plus_smooth / tr_smooth * 100
        di_minus = dm_minus_smooth / tr_smooth * 100
        
        df['DI_plus'] = di_plus
        df['DI_minus'] = di_minus
        
        # DX
        di_sum = di_plus + di_minus
        di_sum = di_sum.replace(0, np.nan)
        dx = (di_plus - di_minus).abs() / di_sum * 100
        
        # ADX
        df['ADX'] = dx.rolling(window=window, min_periods=1).mean()
        
        return df
    
    def get_factor_columns(self) -> List[str]:
        """获取因子列名"""
        return [
            'DMA', 'MA_short', 'MA_long',
            'RSI_5', 'RSI_10',
            'DIF', 'DEA', 'MACD_hist',
            'K', 'D', 'J',
            'OBV', 'MAOBV', 'OBV_diff',
            'BB_upper', 'BB_middle', 'BB_lower', 'BB_percent',
            'SAR', 'SAR_trend',
            'ADX', 'DI_plus', 'DI_minus'
        ]


def calculate_returns(df: pd.DataFrame, periods: List[int] = [1, 5, 10, 20]) -> pd.DataFrame:
    """
    计算未来收益率
    
    Args:
        df: DataFrame
        periods: 周期列表
        
    Returns:
        添加了未来收益列的DataFrame
    """
    df = df.copy()
    close = df['close']
    
    for period in periods:
        df[f'return_{period}d'] = close.pct_change(period).shift(-period)
    
    return df


def batch_calculate_indicators(
    price_data: Dict[str, pd.DataFrame]
) -> Dict[str, pd.DataFrame]:
    """
    批量计算多个ETF的指标
    
    Args:
        price_data: {code: df} 字典
        
    Returns:
        {code: df} 字典，包含指标
    """
    calculator = IndicatorCalculator()
    result = {}
    
    for code, df in price_data.items():
        try:
            df = calculator.calculate_all(df)
            df = calculate_returns(df)
            result[code] = df
        except Exception as e:
            print(f"计算 {code} 指标失败: {e}")
            result[code] = df
    
    return result