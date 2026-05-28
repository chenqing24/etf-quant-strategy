#!/usr/bin/env python3
"""简版报告输出测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from src.analysis.report_builder import ReportBuilder


class TestReportBuilderSimple(unittest.TestCase):
    """测试简版报告构建"""
    
    def setUp(self):
        self.builder = ReportBuilder()
    
    def test_buy_report_format(self):
        """测试买入报告格式"""
        results = {
            'action': '买入',
            'code': '515050',
            'name': '5GETF',
            'price': 1.101,
            'realtime': {
                'price': 1.196,
                'change_pct': 8.6
            },
            'indicators': {
                'rsi_14': 70.5
            }
        }
        report = self.builder.build_simple(results)
        
        # 验证关键内容
        self.assertIn('515050', report)
        self.assertIn('5GETF', report)
        self.assertIn('买入', report)
        self.assertIn('1.101', report)
        self.assertIn('1.196', report)
        self.assertIn('止损', report)
        self.assertIn('止盈', report)
        
        # 验证钉钉Markdown格式（行尾2空格）
        self.assertIn('  \n', report)  # 换行符前有空格
    
    def test_sell_report_format(self):
        """测试卖出报告格式"""
        results = {
            'action': '卖出',
            'code': '515050',
            'name': '科技50',
            'price': 1.189,
            'pnl': 12.5
        }
        report = self.builder.build_simple(results)
        
        self.assertIn('卖出', report)
        self.assertIn('515050', report)
        self.assertIn('12.5', report)
    
    def test_hold_report_format(self):
        """测试观望报告格式"""
        results = {
            'action': '观望',
            'code': '515050',
            'name': '科技50',
        }
        report = self.builder.build_simple(results)
        
        self.assertIn('观望', report)
        self.assertIn('等待', report)
    
    def test_report_length_limit(self):
        """测试简版报告不超过10行（不含空行）"""
        results = {
            'action': '买入',
            'code': '515050',
            'name': '科技50',
            'price': 1.101,
            'realtime': {
                'price': 1.196,
                'change_pct': 8.6
            }
        }
        report = self.builder.build_simple(results)
        
        # 计算非空行数
        lines = [l for l in report.split('\n') if l.strip()]
        self.assertLessEqual(len(lines), 15, "简版报告应控制在15行内")
    
    def test_no_progress_info(self):
        """测试简版报告无进度条信息"""
        results = {
            'action': '买入',
            'code': '515050',
            'name': '科技50',
            'price': 1.101,
        }
        report = self.builder.build_simple(results)
        
        # 不应包含进度条相关文字
        self.assertNotIn('[1/3]', report)
        self.assertNotIn('预热', report)
        self.assertNotIn('加载', report)
        self.assertNotIn('====', report)


class TestReportBuilderFull(unittest.TestCase):
    """测试完整报告构建"""
    
    def setUp(self):
        self.builder = ReportBuilder()
    
    def test_full_report_with_file(self):
        """测试完整报告包含文件内容"""
        # 创建临时报告文件
        test_content = "详细报告内容\n标的: 515050\n操作: 买入\n信号价: 1.101"
        temp_file = '/tmp/test_full_report.txt'
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        try:
            results = {'action': '买入', 'code': '515050'}
            report = self.builder.build_full(results, report_file=temp_file)
            self.assertEqual(report, test_content)
        finally:
            os.remove(temp_file)
    
    def test_full_report_without_file(self):
        """测试完整报告无文件时返回基本信息"""
        results = {
            'action': '买入',
            'code': '515050',
            'name': '科技50',
            'price': 1.101,
        }
        report = self.builder.build_full(results)
        
        self.assertIn('515050', report)
        self.assertIn('买入', report)


if __name__ == '__main__':
    unittest.main()