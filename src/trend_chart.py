#!/usr/bin/env python3
"""K线简图生成器"""
import pandas as pd
from typing import List, Tuple


def generate_trend_text(df: pd.DataFrame, code: str, days: int = 5) -> str:
    """生成近N日趋势文本
    
    Args:
        df: ETF数据 (需包含date, close列)
        code: ETF代码
        days: 显示天数
        
    Returns:
        ASCII趋势图字符串
    """
    if len(df) < days:
        return f"数据不足 (仅{len(df)}天)"
    
    # 获取最近N日数据
    recent = df.tail(days).reset_index(drop=True)
    
    # 提取价格和涨跌
    prices = []
    changes = []
    arrows = []
    
    for i in range(len(recent)):
        price = recent.iloc[i]['close']
        prices.append(f"{price:.3f}")
        
        if i == 0:
            changes.append("-")
            arrows.append("-")
        else:
            prev = recent.iloc[i-1]['close']
            chg = (price / prev - 1) * 100
            changes.append(f"{chg:+.1f}%")
            if chg > 0.5:
                arrows.append("↑")
            elif chg < -0.5:
                arrows.append("↓")
            else:
                arrows.append("→")
    
    # 计算总涨跌
    total_chg = (recent.iloc[-1]['close'] / recent.iloc[0]['close'] - 1) * 100
    
    # 获取名称
    from .report_generator import ETF_NAMES
    name = ETF_NAMES.get(code, code)
    
    # 格式化为箭头字符串
    arrow_str = "→".join(prices) + f" {arrows[-1]}{abs(total_chg):.1f}%"
    
    # 涨跌详情
    change_str = "↑".join([f"{c}" for c in changes[1:]]) if changes[1] != "-" else ""
    
    lines = [
        f"📊 {code} {name}",
        f"近{days}日: {'→'.join(prices)}",
        f"       {'  '.join(arrows)}",
        f"涨跌: {' '.join(changes)}",
    ]
    
    return "\n".join(lines)


def get_trend_summary(df: pd.DataFrame, code: str, days: int = 5) -> dict:
    """获取趋势摘要数据
    
    Returns:
        dict with keys: prices, changes, arrows, total_change
    """
    if len(df) < days:
        return None
    
    recent = df.tail(days).reset_index(drop=True)
    
    prices = []
    changes = []
    arrows = []
    
    for i in range(len(recent)):
        price = recent.iloc[i]['close']
        prices.append(price)
        
        if i == 0:
            changes.append(0)
            arrows.append("-")
        else:
            prev = recent.iloc[i-1]['close']
            chg = (price / prev - 1) * 100
            changes.append(chg)
            if chg > 0.5:
                arrows.append("↑")
            elif chg < -0.5:
                arrows.append("↓")
            else:
                arrows.append("→")
    
    total_chg = (recent.iloc[-1]['close'] / recent.iloc[0]['close'] - 1) * 100
    
    return {
        'prices': prices,
        'changes': changes,
        'arrows': arrows,
        'total_change': total_chg,
        'last_price': recent.iloc[-1]['close'],
    }


__all__ = ['generate_trend_text', 'get_trend_summary']