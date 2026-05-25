#!/usr/bin/env python3
"""通知系统模块单元测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from src.report_builder import ReportBuilder, get_builder
from src.dingtalk_sender import DingTalkSender, get_sender
from src.scenario_adapter import ScenarioAdapter, notify_decision


class TestReportBuilder(unittest.TestCase):
    """测试ReportBuilder"""
    
    def setUp(self):
        self.builder = ReportBuilder()
    
    def test_get_etf_name(self):
        """测试ETF名称映射"""
        self.assertEqual(self.builder.get_etf_name('510300'), '沪深300')
        self.assertEqual(self.builder.get_etf_name('510500'), '中证500')
        self.assertEqual(self.builder.get_etf_name('159919'), '沪深300ETF')
        # 未知代码应返回原代码
        self.assertEqual(self.builder.get_etf_name('999999'), '999999')
    
    def test_build_simple_buy(self):
        """测试构建简版买入报告"""
        results = {
            'action': '买入',
            'code': '510300',
            'price': 3.856,
            'realtime': {'price': 3.860, 'change_pct': 1.5},
            'indicators': {'rsi_14': 72}
        }
        report = self.builder.build_simple(results)
        
        self.assertIn('买入', report)
        self.assertIn('510300', report)
        self.assertIn('3.856', report)
        self.assertIn('3.860', report)
        self.assertIn('RSI14', report)
        self.assertIn('止损', report)
        self.assertIn('止盈', report)
    
    def test_build_simple_sell(self):
        """测试构建简版卖出报告"""
        results = {
            'action': '卖出',
            'code': '510300',
            'price': 3.856,
            'pnl': 5.2
        }
        report = self.builder.build_simple(results)
        
        self.assertIn('卖出', report)
        self.assertIn('510300', report)
        self.assertIn('5.2', report)
    
    def test_build_simple_hold(self):
        """测试构建简版观望报告"""
        results = {
            'action': '观望',
        }
        report = self.builder.build_simple(results)
        
        self.assertIn('观望', report)
        self.assertIn('等待', report)
    
    def test_build_full_with_file(self):
        """测试构建详细报告（带文件）"""
        # 创建临时报告文件
        test_report = "详细报告内容\n标的: 510300\n操作: 买入"
        temp_file = '/tmp/test_report.txt'
        with open(temp_file, 'w') as f:
            f.write(test_report)
        
        try:
            results = {'action': '买入', 'code': '510300'}
            report = self.builder.build_full(results, report_file=temp_file)
            self.assertEqual(report, test_report)
        finally:
            os.remove(temp_file)
    
    def test_singleton(self):
        """测试单例模式"""
        builder1 = get_builder()
        builder2 = get_builder()
        self.assertIs(builder1, builder2)


class TestDingTalkSender(unittest.TestCase):
    """测试DingTalkSender"""
    
    def test_init_qwenpaw(self):
        """测试QwenPaw模式初始化"""
        sender = DingTalkSender(mode='qwenpaw')
        self.assertEqual(sender.mode, 'qwenpaw')
    
    def test_init_webhook(self):
        """测试Webhook模式初始化"""
        url = 'https://oapi.dingtalk.com/robot/send?access_token=xxx'
        sender = DingTalkSender(mode='webhook', webhook_url=url)
        self.assertEqual(sender.mode, 'webhook')
        self.assertEqual(sender.webhook_url, url)
    
    def test_singleton(self):
        """测试单例模式"""
        sender1 = get_sender(mode='qwenpaw')
        sender2 = get_sender(mode='qwenpaw')
        self.assertIs(sender1, sender2)


class TestScenarioAdapter(unittest.TestCase):
    """测试ScenarioAdapter"""
    
    def test_for_mobile(self):
        """测试移动端适配器创建"""
        adapter = ScenarioAdapter.for_mobile()
        self.assertEqual(adapter.scenario, 'mobile')
    
    def test_for_pc(self):
        """测试PC端适配器创建"""
        adapter = ScenarioAdapter.for_pc()
        self.assertEqual(adapter.scenario, 'pc')
    
    def test_for_console(self):
        """测试控制台适配器创建"""
        adapter = ScenarioAdapter.for_console()
        self.assertEqual(adapter.scenario, 'console')
    
    def test_build_report_mobile(self):
        """测试移动端报告构建"""
        adapter = ScenarioAdapter.for_mobile()
        results = {
            'action': '买入',
            'code': '510300',
            'price': 3.856,
        }
        report = adapter.build_report(results)
        
        self.assertIn('买入', report)
        self.assertIn('510300', report)
    
    def test_build_report_pc(self):
        """测试PC端报告构建"""
        adapter = ScenarioAdapter.for_pc()
        results = {
            'action': '买入',
            'code': '510300',
            'price': 3.856,
        }
        report = adapter.build_report(results)
        
        self.assertIn('510300', report)


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def test_full_flow_mobile(self):
        """测试完整移动端流程"""
        results = {
            'action': '买入',
            'code': '510300',
            'price': 3.856,
            'realtime': {'price': 3.860, 'change_pct': 1.5},
            'indicators': {'rsi_14': 72}
        }
        
        # 构建报告
        builder = get_builder()
        report = builder.build_simple(results)
        
        # 验证报告内容
        self.assertIn('买入', report)
        self.assertIn('510300', report)
        self.assertIn('3.856', report)
        
        # 发送报告（控制台模式）
        adapter = ScenarioAdapter.for_mobile()
        # 注意：不实际发送钉钉，只测试构建


if __name__ == '__main__':
    unittest.main(verbosity=2)
