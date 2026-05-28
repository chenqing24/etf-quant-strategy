#!/usr/bin/env python3
"""市场过滤层"""
import pandas as pd


class MarketFilter:
    """市场环境过滤器
    
    基于沪深300指数与均线的比较，判断市场趋势
    """
    
    def __init__(self, hs300: pd.DataFrame, ma: int = 60):
        """初始化
        
        Args:
            hs300: 沪深300指数数据
            ma: 均线周期，默认60日
        """
        self.data = hs300.copy()
        self.ma_col = f'ma{ma}'
        self.data[self.ma_col] = self.data['close'].rolling(ma).mean()
        self.ma = ma
    
    def is_bullish(self, date: str) -> bool:
        """判断市场是否处于上涨趋势
        
        Args:
            date: 判断日期
            
        Returns:
            True: 上涨趋势，可以做多
            False: 下跌趋势，应空仓
        """
        row = self.data[self.data['date'] == date]
        
        if len(row) == 0:
            return True  # 无数据默认做多
        
        r = row.iloc[0]
        
        # 均线未形成
        if pd.isna(r.get(self.ma_col)):
            return True
        
        # 价格在均线上方 = 上涨趋势
        return r['close'] > r[self.ma_col]
    
    def get_status(self, date: str) -> str:
        """获取市场状态描述"""
        row = self.data[self.data['date'] == date]
        if len(row) == 0:
            return "未知"
        
        r = row.iloc[0]
        if pd.isna(r.get(self.ma_col)):
            return "均线未形成"
        
        if r['close'] > r[self.ma_col]:
            return f"上涨 (价格{r['close']:.2f} > MA{self.ma}{r[self.ma_col]:.2f})"
        else:
            return f"下跌 (价格{r['close']:.2f} < MA{self.ma}{r[self.ma_col]:.2f})"


__all__ = ['MarketFilter']