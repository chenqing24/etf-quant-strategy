#!/usr/bin/env python3
"""US-024: 交易业务约束异常

按教训 47（return None 是危险信号）：
- 业务约束失败应抛异常，让调用方明确知道"失败"
- 而不是 return None 让调用方误判

参考 PEP 3109 异常处理 + SQLAlchemy 2.0 IntegrityError 模式
"""
from typing import Optional


class BusinessConstraintError(Exception):
    """业务约束违反异常

    US-024: 替代 record_buy/sell 的 return None 模式
    触发场景:
        - 持仓数已达 max_holdings
        - 重复持仓（已有 HOLDING/PENDING/REBALANCING）
        - 卖出数量超过持仓
        - 卖出非持仓标的

    Args:
        code: ETF 代码
        action: 'buy' 或 'sell'
        reason: 失败原因（用户友好）
        hint: 修复建议（可选）
    """

    def __init__(self, code: str, action: str, reason: str, hint: Optional[str] = None):
        self.code = code
        self.action = action
        self.reason = reason
        self.hint = hint or self._default_hint(action)

        msg = f"[{action.upper()}] {code} 失败: {reason}"
        if self.hint:
            msg += f"\n💡 {self.hint}"

        super().__init__(msg)

    def _default_hint(self, action: str) -> str:
        """根据 action 给出默认修复建议"""
        if action == 'buy':
            return "持仓数已达上限或已持仓，请先卖出或调整 max_holdings"
        elif action == 'sell':
            return "未持有该标的或持仓状态不允许卖出"
        return "请检查业务约束"


__all__ = ['BusinessConstraintError']
