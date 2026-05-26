#!/usr/bin/env python3
"""交易成本模拟 - 滑点和流动性"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class TradingCost:
    """交易成本配置"""
    base_slippage: float = 0.0001    # 基础滑点 (万一)
    min_slippage: float = 0.0001     # 最小滑点
    max_slippage: float = 0.001      # 最大滑点 (千一)
    
    # 大单冲击成本
    large_order_threshold: float = 100000  # 大单阈值 (10万)
    large_order_impact: float = 0.0002     # 大单额外冲击 (万分之2)
    
    # 流动性系数 (价格越高，流动性越好，滑点越小)
    price_factor: float = 0.5
    
    # 涨跌幅影响 (波动大时滑点大)
    volatility_factor: float = 0.5


def calculate_slippage(
    price: float,
    volume: float,
    side: str = 'buy',
    cost_config: Optional[TradingCost] = None
) -> float:
    """计算滑点成本
    
    Args:
        price: 当前价格
        volume: 成交金额(元)
        side: 'buy' 或 'sell'
        cost_config: 成本配置
        
    Returns:
        滑点比例 (如0.001表示千分之一)
    """
    if cost_config is None:
        cost_config = TradingCost()
    
    # 基础滑点
    slippage = cost_config.base_slippage
    
    # 价格因子 - 价格越高，滑点相对越小
    if price > 0:
        price_adjusted = min(price / 1.0, 2.0)  # 限制范围
        slippage *= (1 / price_adjusted) * cost_config.price_factor
    
    # 大单冲击成本
    if volume > cost_config.large_order_threshold:
        # 超过阈值后，额外冲击成本
        excess_ratio = min(volume / cost_config.large_order_threshold, 10)
        slippage += cost_config.large_order_impact * (excess_ratio - 1)
    
    # 限制范围
    slippage = max(cost_config.min_slippage, min(slippage, cost_config.max_slippage))
    
    # 卖出时滑点更大(流动性折价)
    if side == 'sell':
        slippage *= 1.5
    
    return slippage


def apply_trading_cost(
    price: float,
    volume: float,
    side: str = 'buy',
    fee_rate: float = 0.0003,
    cost_config: Optional[TradingCost] = None
) -> float:
    """应用交易成本后的价格
    
    Args:
        price: 当前价格
        volume: 成交金额(元)
        side: 'buy' 或 'sell'
        fee_rate: 手续费率 (万一)
        cost_config: 成本配置
        
    Returns:
        实际成交价格
    """
    slippage = calculate_slippage(price, volume, side, cost_config)
    total_cost = fee_rate + slippage
    
    if side == 'buy':
        # 买入: 价格更高
        return price * (1 + total_cost)
    else:
        # 卖出: 价格更低
        return price * (1 - total_cost)


def calculate_cost_impact(
    price: float,
    volume: float,
    side: str = 'buy',
    fee_rate: float = 0.0003,
    cost_config: Optional[TradingCost] = None
) -> dict:
    """计算成本影响明细
    
    Returns:
        包含各项成本明细的字典
    """
    if cost_config is None:
        cost_config = TradingCost()
    
    slippage = calculate_slippage(price, volume, side, cost_config)
    
    return {
        'original_price': price,
        'fee_rate': fee_rate,
        'slippage': slippage,
        'total_cost_rate': fee_rate + slippage,
        'total_cost_amount': price * (fee_rate + slippage),
        'final_price': apply_trading_cost(price, volume, side, fee_rate, cost_config),
    }


def test_trading_cost():
    """测试交易成本"""
    # 测试基础滑点
    cost1 = calculate_slippage(price=1.0, volume=10000, side='buy')
    print(f"基础滑点: {cost1:.6f}")
    assert cost1 > 0, "滑点应为正"
    
    # 测试大单成本
    cost2 = calculate_slippage(price=1.0, volume=200000, side='buy')
    print(f"大单滑点: {cost2:.6f}")
    assert cost2 > cost1, "大单滑点应更高"
    
    # 测试卖出成本更高
    cost3 = calculate_slippage(price=1.0, volume=10000, side='sell')
    print(f"卖出滑点: {cost3:.6f}")
    assert cost3 > cost1, "卖出滑点应更高"
    
    # 测试成本明细
    detail = calculate_cost_impact(price=2.0, volume=50000, side='buy', fee_rate=0.0003)
    print(f"成本明细: {detail}")
    
    print("✓ 交易成本测试通过")
    return True


if __name__ == '__main__':
    test_trading_cost()


__all__ = ['TradingCost', 'calculate_slippage', 'apply_trading_cost', 'calculate_cost_impact', 'test_trading_cost']