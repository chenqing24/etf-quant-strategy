#!/usr/bin/env python3
"""通知系统模块单元测试

注意：scenario_adapter.py 在架构重组后已被移除
相关功能已整合到 src/notify/dingtalk.py 和 src/notify/notifier.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from src.analysis.report_builder import ReportBuilder, get_builder
from src.notify.dingtalk import DingTalkSender, get_sender


class TestReportBuilder(unittest.TestCase):
    """测试ReportBuilder"""
    
    def setUp(self):
        self.builder = ReportBuilder()
    
    def test_get_etf_name(self):
        """测试ETF名称映射"""
        name = self.builder.get_etf_name('510300')
        assert name is not None, "ETF名称映射失败"
    
    def test_get_builder(self):
        """测试单例获取"""
        builder = get_builder()
        assert builder is not None, "单例获取失败"
        assert isinstance(builder, ReportBuilder), "类型错误"


class TestDingTalkSender(unittest.TestCase):
    """测试DingTalkSender"""
    
    def setUp(self):
        self.sender = DingTalkSender()
    
    def test_get_sender(self):
        """测试单例获取"""
        sender = get_sender()
        assert sender is not None, "单例获取失败"
        assert isinstance(sender, DingTalkSender), "类型错误"


if __name__ == '__main__':
    unittest.main()