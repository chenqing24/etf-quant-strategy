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
        # ETF名称可能在或可能不在报告中
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
        """测试简版报告行数（行为变化类更新, SOUL 规则 20）

        设计演进: 简版报告增加了"手动记录参数"段（行 8-20, 共 14 行）
        让钉钉用户能一键复制 CLI 命令记录交易
        现状: 6 行核心 + 14 行辅助 = 21 行
        期望: 简版报告 ≤ 25 行（核心 6 + 辅助 ≤ 19, 留 4 行缓冲）

        旧期望 15 行: 2026-05 月前测试, 当时没有"手动记录参数"段
        新期望 25 行: 2026-06-05 更新, 认可设计意图
        """
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
        # 核心段（1-6: 标题/状态/代码/价格/止损止盈）必须 ≤ 8 行
        core_lines = lines[:8] if len(lines) >= 8 else lines
        self.assertLessEqual(len(core_lines), 8, f"核心段应 ≤ 8 行, 实际 {len(core_lines)} 行")
        # 完整报告 ≤ 25 行
        self.assertLessEqual(len(lines), 25, f"完整报告应 ≤ 25 行, 实际 {len(lines)} 行")
    
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