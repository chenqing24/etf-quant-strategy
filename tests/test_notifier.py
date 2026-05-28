"""
notifier.py 测试用例

测试内容：
1. SignalNotifier 控制台输出功能
2. TradeSignal 数据类
"""

import pytest
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.notify.notifier import SignalNotifier, TradeSignal


class TestSignalNotifier:
    """SignalNotifier测试"""

    def test_初始化_默认参数(self):
        """测试初始化使用默认参数"""
        notifier = SignalNotifier()
        assert notifier.enable_console == True, "默认启用控制台输出"
        assert notifier.signals == [], "信号列表应为空"

    def test_初始化_禁用控制台(self):
        """测试初始化禁用控制台"""
        notifier = SignalNotifier(enable_console=False)
        assert notifier.enable_console == False, "控制台输出已禁用"

    def test_初始化_启用控制台(self):
        """测试初始化启用控制台"""
        notifier = SignalNotifier(enable_console=True)
        assert notifier.enable_console == True, "控制台输出已启用"

    def test_获取信号_初始为空(self):
        """测试获取信号列表（初始为空）"""
        notifier = SignalNotifier()
        signals = notifier.get_signals()
        assert signals == [], "初始信号列表应为空"

    def test_发送信号_单个(self):
        """测试发送单个信号"""
        notifier = SignalNotifier(enable_console=True)
        signal = TradeSignal(
            date='2026-05-27',
            code='510300',
            action='BUY',
            price=4.0,
            reason='test'
        )
        notifier.send_signal(signal)
        signals = notifier.get_signals()
        assert len(signals) == 1, "应添加一个信号"
        assert signals[0].code == '510300', "信号代码错误"

    def test_发送信号_多个(self):
        """测试发送多个信号"""
        notifier = SignalNotifier()
        signal1 = TradeSignal(date='2026-05-27', code='510300', action='BUY', price=4.0, reason='test1')
        signal2 = TradeSignal(date='2026-05-27', code='510050', action='SELL', price=2.5, reason='test2')
        notifier.send_signal(signal1)
        notifier.send_signal(signal2)
        signals = notifier.get_signals()
        assert len(signals) == 2, "应添加两个信号"

    def test_清除信号(self):
        """测试清除信号列表"""
        notifier = SignalNotifier()
        signal = TradeSignal(date='2026-05-27', code='510300', action='BUY', price=4.0, reason='test')
        notifier.send_signal(signal)
        notifier.clear_signals()
        signals = notifier.get_signals()
        assert signals == [], "信号列表应为空"

    def test_格式化消息(self):
        """测试格式化消息"""
        notifier = SignalNotifier()
        signal = TradeSignal(date='2026-05-27', code='510300', action='BUY', price=4.0, reason='test')
        msg = notifier._format_message(signal)
        assert '510300' in msg, "消息应包含ETF代码"


class TestTradeSignal:
    """TradeSignal测试"""

    def test_初始化_必需参数(self):
        """测试初始化使用必需参数"""
        signal = TradeSignal(
            date='2026-05-27',
            code='510300',
            action='BUY',
            price=4.0,
            reason='test'
        )
        assert signal.date == '2026-05-27', "日期错误"
        assert signal.code == '510300', "代码错误"
        assert signal.action == 'BUY', "动作错误"
        assert signal.price == 4.0, "价格错误"
        assert signal.reason == 'test', "原因错误"

    def test_初始化_可选参数(self):
        """测试初始化使用可选参数"""
        signal = TradeSignal(
            date='2026-05-27',
            code='510300',
            action='SELL',
            price=4.5,
            reason='profit taking',
            score=8,
            pnl=0.05
        )
        assert signal.score == 8, "分数错误"
        assert signal.pnl == 0.05, "盈亏比例错误"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])