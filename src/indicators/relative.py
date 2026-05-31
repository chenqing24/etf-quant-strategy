# -*- coding: utf-8 -*-
"""
相对大盘指标计算器 v7.0
========================
计算ETF相对于大盘（510300）的各类相对指标
"""
import pandas as pd
import numpy as np
from typing import Optional


class RelativeCalculator:
    """相对大盘指标计算器"""

    def __init__(self, benchmark_code: str = '510300'):
        """
        Args:
            benchmark_code: 大盘ETF代码，默认510300
        """
        self.benchmark_code = benchmark_code

    def calc_rel_return(self, df_etf: pd.DataFrame, df_benchmark: pd.DataFrame,
                        n: int = 5) -> pd.Series:
        """
        计算N日相对收益率

        Args:
            df_etf: ETF数据（含return_Nd列）
            df_benchmark: 大盘数据（含return_Nd列）
            n: 回望天数

        Returns:
            相对收益率序列 = ETF收益率 - 大盘收益率
        """
        col_etf = f'return_{n}d'
        col_bm = f'return_{n}d'

        if col_etf not in df_etf.columns or col_bm not in df_benchmark.columns:
            return pd.Series(0, index=df_etf.index)

        rel = df_etf[col_etf] - df_benchmark[col_bm]
        return rel.rename(f'rel_return_{n}d')

    def calc_rel_MACD(self, df_etf: pd.DataFrame, df_benchmark: pd.DataFrame) -> pd.Series:
        """
        计算相对MACD差值

        Returns:
            相对MACD直方图 = ETF_MACD_hist - 大盘_MACD_hist
        """
        if 'MACD_hist' not in df_etf.columns or 'MACD_hist' not in df_benchmark.columns:
            return pd.Series(0, index=df_etf.index)

        rel = df_etf['MACD_hist'] - df_benchmark['MACD_hist']
        return rel.rename('rel_MACD')

    def calc_rel_strength(self, df_etf: pd.DataFrame, df_benchmark: pd.DataFrame,
                         n: int = 5) -> pd.Series:
        """
        计算相对强弱指数（弹性系数）

        Returns:
            相对强弱 = ETF涨幅 / (大盘涨幅 + ε)
            > 1: ETF涨得比大盘快
            < 1: ETF涨得比大盘慢
            < 0: 大盘涨但ETF跌
        """
        col_etf = f'return_{n}d'
        col_bm = f'return_{n}d'

        if col_etf not in df_etf.columns or col_bm not in df_benchmark.columns:
            return pd.Series(1.0, index=df_etf.index)

        bm_return = df_benchmark[col_bm]
        rel = df_etf[col_etf] / (bm_return + 1e-8)
        return rel.rename(f'rel_strength_{n}d')

    def calc_rel_money_flow(self, df_etf: pd.DataFrame, df_benchmark: pd.DataFrame) -> pd.Series:
        """
        计算相对资金流向

        Returns:
            相对资金流 = ETF_OBV_diff - 大盘_OBV_diff
            > 0: 资金主动买入强于大盘
            < 0: 资金主动买入弱于大盘
        """
        if 'OBV_diff' not in df_etf.columns or 'OBV_diff' not in df_benchmark.columns:
            return pd.Series(0, index=df_etf.index)

        rel = df_etf['OBV_diff'] - df_benchmark['OBV_diff']
        return rel.rename('rel_money_flow')

    def calc_rel_RSI(self, df_etf: pd.DataFrame, df_benchmark: pd.DataFrame) -> pd.Series:
        """
        计算相对RSI

        Returns:
            相对RSI = ETF_RSI - 大盘_RSI
            > 0: ETF超买超卖程度高于大盘
        """
        if 'RSI_10' not in df_etf.columns or 'RSI_10' not in df_benchmark.columns:
            return pd.Series(0, index=df_etf.index)

        rel = df_etf['RSI_10'] - df_benchmark['RSI_10']
        return rel.rename('rel_RSI')

    def calc_rel_volume_ratio(self, df_etf: pd.DataFrame, df_benchmark: pd.DataFrame) -> pd.Series:
        """
        计算相对成交量比

        Returns:
            相对量比 = (ETF成交量/MA10) / (大盘成交量/MA10)
        """
        for vol_col in ['volume', 'amount']:
            if vol_col in df_etf.columns:
                break
        else:
            return pd.Series(1.0, index=df_etf.index)

        bm_vol = 'volume' if 'volume' in df_benchmark.columns else 'amount'

        if vol_col not in df_etf.columns or bm_vol not in df_benchmark.columns:
            return pd.Series(1.0, index=df_etf.index)

        etf_ratio = df_etf[vol_col] / df_etf.get(f'{vol_col}_MA10', df_etf[vol_col])
        bm_ratio = df_benchmark[bm_vol] / df_benchmark.get(f'{bm_vol}_MA10', df_benchmark[bm_vol])

        rel = etf_ratio / (bm_ratio + 1e-8)
        return rel.rename('rel_volume_ratio')

    def calc_rel_ADX(self, df_etf: pd.DataFrame, df_benchmark: pd.DataFrame) -> pd.Series:
        """
        计算相对ADX趋势强度

        Returns:
            相对ADX = ETF_ADX - 大盘_ADX
        """
        if 'ADX' not in df_etf.columns or 'ADX' not in df_benchmark.columns:
            return pd.Series(0, index=df_etf.index)

        rel = df_etf['ADX'] - df_benchmark['ADX']
        return rel.rename('rel_ADX')

    def calc_all_relative(self, df_etf: pd.DataFrame, df_benchmark: pd.DataFrame) -> pd.DataFrame:
        """
        计算所有相对指标

        Args:
            df_etf: ETF数据（已计算技术指标）
            df_benchmark: 大盘数据（已计算技术指标）

        Returns:
            在df_etf基础上添加所有相对指标列
        """
        df = df_etf.copy()

        # 相对收益率（3日、5日）
        df['rel_return_3d'] = self.calc_rel_return(df_etf, df_benchmark, 3)
        df['rel_return_5d'] = self.calc_rel_return(df_etf, df_benchmark, 5)

        # 相对MACD
        df['rel_MACD'] = self.calc_rel_MACD(df_etf, df_benchmark)

        # 相对强弱
        df['rel_strength_3d'] = self.calc_rel_strength(df_etf, df_benchmark, 3)
        df['rel_strength_5d'] = self.calc_rel_strength(df_etf, df_benchmark, 5)

        # 相对资金流
        df['rel_money_flow'] = self.calc_rel_money_flow(df_etf, df_benchmark)

        # 相对RSI
        df['rel_RSI'] = self.calc_rel_RSI(df_etf, df_benchmark)

        # 相对成交量比
        df['rel_volume_ratio'] = self.calc_rel_volume_ratio(df_etf, df_benchmark)

        # 相对ADX
        df['rel_ADX'] = self.calc_rel_ADX(df_etf, df_benchmark)

        return df


# ============================================================
# 因子定义（v7.0扩展版）
# ============================================================
# 绝对指标（保留）
FACTORS_ABSOLUTE = {
    'MACD红柱': {'col': 'MACD_hist', 'op': 'gt', 'threshold': 0},
    'DMA多头': {'col': 'DMA', 'op': 'gt', 'threshold': 0},
    '布林上轨突破': {'col': 'close', 'op': 'gt', 'ref': 'BB_upper'},
    'SAR趋势': {'col': 'SAR_trend', 'op': 'gt', 'threshold': 0.5},
    '大盘多头': {'col': 'market_bullish', 'op': 'eq', 'threshold': True},
    'ADX趋势': {'col': 'ADX', 'op': 'gt', 'threshold': 25},
    '动量3日': {'col': 'return_3d', 'op': 'gt', 'threshold': 0},
    '动量5日': {'col': 'return_5d', 'op': 'gt', 'threshold': 0},
    'RSI适中': {'col': 'RSI_10', 'op': 'between', 'low': 40, 'high': 70},
    'KDJ金叉': {'col': 'K', 'op': 'gt', 'ref': 'D'},
    'OBV多头': {'col': 'OBV', 'op': 'gt', 'ref': 'MAOBV'},
    '放量': {'col': 'volume', 'op': 'gt_ratio', 'ref': 'volume_MA10', 'ratio': 1.2},
    '资金流入': {'col': 'OBV_diff', 'op': 'gt', 'threshold': 0},
}

# 相对大盘指标（新增）
FACTORS_RELATIVE = {
    '相对3日收益': {'col': 'rel_return_3d', 'op': 'gt', 'threshold': 0},
    '相对5日收益': {'col': 'rel_return_5d', 'op': 'gt', 'threshold': 0},
    '相对MACD强势': {'col': 'rel_MACD', 'op': 'gt', 'threshold': 0},
    '相对强弱5日': {'col': 'rel_strength_5d', 'op': 'gt', 'threshold': 1.0},
    '相对资金流入': {'col': 'rel_money_flow', 'op': 'gt', 'threshold': 0},
    '相对RSI强势': {'col': 'rel_RSI', 'op': 'gt', 'threshold': 0},
    '相对量比强势': {'col': 'rel_volume_ratio', 'op': 'gt', 'threshold': 1.0},
    '相对ADX强势': {'col': 'rel_ADX', 'op': 'gt', 'threshold': 0},
}

# 合并所有因子
FACTORS_V7 = {**FACTORS_ABSOLUTE, **FACTORS_RELATIVE}

# 因子分类
FACTOR_CATEGORIES = {
    '趋势类': ['MACD红柱', 'DMA多头', 'SAR趋势', 'ADX趋势', '布林上轨突破'],
    '动量类': ['动量3日', '动量5日', 'RSI适中', 'KDJ金叉'],
    '量能类': ['OBV多头', '放量', '资金流入'],
    '相对大盘类': ['相对3日收益', '相对5日收益', '相对MACD强势', '相对强弱5日', '相对资金流入', '相对RSI强势', '相对量比强势', '相对ADX强势'],
}
