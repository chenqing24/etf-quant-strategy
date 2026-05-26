#!/usr/bin/env python3
"""场景适配器测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from unittest.mock import patch, MagicMock
from src.scenario_adapter import ScenarioAdapter


class TestScenarioAdapter(unittest.TestCase):
    """测试场景适配器"""
    
    def test_for_mobile(self):
        """测试移动端场景创建"""
        adapter = ScenarioAdapter.for_mobile()
        self.assertEqual(adapter.scenario, ScenarioAdapter.SCENARIO_MOBILE)
    
    def test_for_pc(self):
        """测试PC端场景创建"""
        adapter = ScenarioAdapter.for_pc()
        self.assertEqual(adapter.scenario, ScenarioAdapter.SCENARIO_PC)
    
    def test_for_console(self):
        """测试控制台场景创建"""
        adapter = ScenarioAdapter.for_console()
        self.assertEqual(adapter.scenario, ScenarioAdapter.SCENARIO_CONSOLE)
    
    def test_mobile_build_simple(self):
        """测试移动端使用简版报告"""
        adapter = ScenarioAdapter.for_mobile()
        results = {
            'action': '买入',
            'code': '515050',
            'name': '科技50',
            'price': 1.101,
        }
        
        report = adapter.build_report(results)
        
        # 移动端应使用简版报告
        self.assertIn('515050', report)
        self.assertIn('买入', report)
        # 不应有详细指标
        self.assertNotIn('市场环境', report)
        self.assertNotIn('策略历史', report)
    
    def test_pc_build_full(self):
        """测试PC端使用完整报告"""
        adapter = ScenarioAdapter.for_pc()
        results = {
            'action': '买入',
            'code': '515050',
            'name': '5GETF',
        }
        
        # PC端需要报告文件
        report = adapter.build_report(results, report_file='/tmp/test_report.txt')
        
        # 应包含代码信息
        self.assertIn('515050', report)
    
    @patch('src.scenario_adapter.get_sender')
    def test_mobile_send_decision_buy(self, mock_sender):
        """测试移动端发送买入决策"""
        mock_instance = MagicMock()
        mock_sender.return_value = mock_instance
        mock_instance.send.return_value = True
        
        adapter = ScenarioAdapter.for_mobile()
        message = "**🟢 买入** 515050 科技50"
        
        result = adapter.send_report(message)
        
        # 买入操作应发送钉钉通知
        mock_instance.send.assert_called_once()
        self.assertTrue(result)
    
    @patch('src.scenario_adapter.get_sender')
    def test_mobile_send_decision_hold(self, mock_sender):
        """测试移动端发送观望（不发送钉钉）"""
        mock_instance = MagicMock()
        mock_sender.return_value = mock_instance
        mock_instance.send.return_value = True
        
        adapter = ScenarioAdapter.for_mobile()
        message = "**⚪ 观望** 等待机会"
        
        result = adapter.send_report(message)
        
        # 观望操作不发送钉钉
        mock_instance.send.assert_not_called()
        self.assertTrue(result)
    
    def test_console_output(self):
        """测试控制台输出"""
        adapter = ScenarioAdapter.for_console()
        message = "测试消息"
        
        # 控制台输出现在使用logger.info (logging.getLogger)
        with patch('src.scenario_adapter.logger') as mock_logger:
            adapter.send_report(message)
            mock_logger.info.assert_called()


class TestCLIScenarioMode(unittest.TestCase):
    """测试CLI场景参数"""
    
    def test_simple_mode_param(self):
        """测试--simple参数存在"""
        # 验证decision_cli.py支持--simple参数
        import subprocess
        result = subprocess.run(
            ['python', '-m', 'src.decision_cli', '-m', 'eval', '--help'],
            capture_output=True, text=True,
            cwd='/home/qwenpaw/.qwenpaw/workspaces/default/etf_strategy'
        )
        self.assertIn('--simple', result.stdout)
    
    def test_full_mode_param(self):
        """测试--full参数存在"""
        # 验证decision_cli.py支持--full参数
        import subprocess
        result = subprocess.run(
            ['python', '-m', 'src.decision_cli', '-m', 'eval', '--help'],
            capture_output=True, text=True,
            cwd='/home/qwenpaw/.qwenpaw/workspaces/default/etf_strategy'
        )
        self.assertIn('--full', result.stdout)


if __name__ == '__main__':
    unittest.main()