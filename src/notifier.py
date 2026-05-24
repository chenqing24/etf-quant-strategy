#!/usr/bin/env python3
"""信号推送"""
import json
import time
from typing import Dict, List, Optional
from dataclasses import dataclass


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
    """信号通知器
    
    支持多种推送方式:
    - 钉钉Webhook
    - 控制台输出(测试用)
    """
    
    def __init__(self, 
                 webhook_url: str = None,
                 enable_console: bool = True):
        self.webhook_url = webhook_url
        self.enable_console = enable_console
        self.signals: List[TradeSignal] = []
    
    def send_signal(self, signal: TradeSignal):
        """发送交易信号"""
        self.signals.append(signal)
        
        # 格式化消息
        message = self._format_message(signal)
        
        # 控制台输出
        if self.enable_console:
            print(f"\n{'='*50}")
            print(f"📢 交易信号通知")
            print(f"{'='*50}")
            print(message)
            print(f"{'='*50}\n")
        
        # 钉钉推送 (可选)
        if self.webhook_url:
            self._send_dingtalk(message)
    
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
    
    def _send_dingtalk(self, message: str):
        """发送钉钉消息"""
        try:
            import requests
            
            headers = {'Content-Type': 'application/json'}
            data = {
                'msgtype': 'text',
                'text': {
                    'content': f"[ETF量化] {message}"
                }
            }
            
            response = requests.post(
                self.webhook_url,
                headers=headers,
                data=json.dumps(data),
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"✓ 钉钉消息发送成功")
            else:
                print(f"✗ 钉钉消息发送失败: {response.status_code}")
                
        except ImportError:
            print("⚠️ requests库未安装，跳过钉钉推送")
        except Exception as e:
            print(f"✗ 钉钉推送异常: {e}")
    
    def send_daily_summary(self, results: Dict):
        """发送每日总结 - 简化的移动端版本"""
        action = results.get('action', '观望')
        code = results.get('new_code', '')
        name = results.get('name', '')
        price = results.get('price', 0)
        
        # 简化版钉钉消息 (移动端友好)
        if action == '买入':
            message = [
                "📈 ETF量化决策",
                "",
                f"🟢 操作: 买入",
                f"📊 标的: {code} {name}",
                f"💰 价格: {price:.3f}",
                f"🛡️ 止损: {price*0.95:.3f} (-5%)",
                f"🎯 止盈: {price*1.08:.3f} (+8%)",
            ]
        elif action == '卖出':
            message = [
                "📈 ETF量化决策",
                "",
                f"🔴 操作: 卖出 | {code}",
            ]
        else:
            message = [
                "📈 ETF量化决策",
                "",
                f"⚪ 操作: 观望",
                f"📊 等待更好的机会",
            ]
        
        # 控制台输出 (完整版)
        if self.enable_console:
            print(f"\n{'='*50}")
            print("📊 每日策略总结")
            print(f"{'='*50}")
            for line in message:
                print(line)
            print(f"{'='*50}\n")
        
        # 钉钉推送 (简化版)
        if self.webhook_url and action != '观望':
            self._send_dingtalk("\n".join(message))
    
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
    
    # 测试每日总结
    notifier.send_daily_summary({
        'return': 51.9,
        'drawdown': -22.6,
        'sharpe': 2.07,
        'winrate': 61.1,
        'trades': 37,
    })
    
    print("✓ 通知器测试通过")
    return True


if __name__ == '__main__':
    test_notifier()


__all__ = ['SignalNotifier', 'TradeSignal', 'test_notifier']