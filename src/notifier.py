#!/usr/bin/env python3
"""信号推送模块

注意：钉钉发送功能已迁移到 dingtalk_sender.py
使用 ScenarioAdapter 进行统一的通知发送
"""
from datetime import datetime
from typing import Dict, List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class TradeSignal:
    """交易信号"""
    date: str
    code: str
    action: str  # 'buy' or 'sell'
    price: float
    reason: str
    score: int = 0
    pnl: float = 0  # 盈亏比例


class SignalNotifier:
    """信号通知器（控制台输出）
    
    注意：钉钉发送功能已迁移到 ScenarioAdapter
    本类仅保留控制台输出功能
    """
    
    def __init__(self, enable_console: bool = True):
        self.enable_console = enable_console
        self.signals: List[TradeSignal] = []
    
    def send_signal(self, signal: TradeSignal):
        """发送交易信号（仅控制台）"""
        self.signals.append(signal)
        
        # 格式化消息
        message = self._format_message(signal)
        
        # 控制台输出
        if self.enable_console:
            logger.info("=" * 50)
            logger.info("📢 交易信号通知")
            logger.info("=" * 50)
            logger.info(message)
            logger.info("=" * 50)
    
    def _format_message(self, signal: TradeSignal) -> str:
        """格式化消息"""
        emoji = "🟢" if signal.action == "buy" else "🔴"
        action_text = "买入" if signal.action == "buy" else "卖出"
        
        lines = [
            f"【ETF量化策略信号】",
            f"",
            f"{emoji} 操作: {action_text}",
            f"📅 日期: {signal.date}",
            f"📊 标的: {signal.code}",
            f"💰 价格: {signal.price:.4f}",
            f"📝 原因: {signal.reason}",
        ]
        
        if signal.score > 0:
            lines.append(f"⭐ 分数: {signal.score}")
        
        if signal.pnl != 0:
            pnl_emoji = "📈" if signal.pnl > 0 else "📉"
            lines.append(f"{pnl_emoji} 盈亏: {signal.pnl:+.2%}")
        
        return "\n".join(lines)
    
    def send_full_report_to_console(self, report_file: str):
        """将完整报告输出到控制台
        
        Args:
            report_file: 完整报告文件路径
        """
        if not report_file:
            return
        
        try:
            with open(report_file, 'r', encoding='utf-8') as f:
                full_report = f.read()
            
            if self.enable_console:
                logger.info("=" * 60)
                logger.info("📊 每日策略总结 (完整报告)")
                logger.info("=" * 60)
                logger.info(full_report)
                logger.info("=" * 60)
                
        except Exception as e:
            logger.warning(f"⚠️ 读取报告文件失败: {e}")
    
    def get_signals(self) -> List[TradeSignal]:
        """获取所有信号"""
        return self.signals
    
    def clear_signals(self):
        """清空信号记录"""
        self.signals = []


def test_notifier():
    """测试通知器"""
    notifier = SignalNotifier(enable_console=True)
    
    # 测试买入信号
    signal = TradeSignal(
        date='2025-05-24',
        code='510300',
        action='buy',
        price=3.456,
        reason='MA120+MA60+放量',
        score=8
    )
    notifier.send_signal(signal)
    
    # 测试卖出信号
    signal2 = TradeSignal(
        date='2025-05-24',
        code='510500',
        action='sell',
        price=5.123,
        reason='止盈',
        pnl=0.15
    )
    notifier.send_signal(signal2)
    
    logger.info("✓ 通知器测试通过")
    return True


if __name__ == '__main__':
    test_notifier()


__all__ = ['SignalNotifier', 'TradeSignal', 'test_notifier']
