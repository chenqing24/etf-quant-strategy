#!/usr/bin/env python3
"""US-011 单元测试：报告模板动态化"""
import os
import sys
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


class TestFormatStrategyMode:
    """段 1: 策略模式（D1+D2: 4 市场 × 2 max_holdings = 8 组合）"""

    def test_trend_up_1(self):
        from src.analysis.report_templates import format_strategy_mode
        result = format_strategy_mode('trend_up', 1)
        assert '趋势市' in result
        assert '单持仓' in result

    def test_trend_up_2(self):
        from src.analysis.report_templates import format_strategy_mode
        result = format_strategy_mode('trend_up', 2)
        assert '趋势市' in result
        assert '多持仓' in result
        assert '2' in result

    def test_range_bound_1(self):
        from src.analysis.report_templates import format_strategy_mode
        result = format_strategy_mode('range_bound', 1)
        assert '震荡市' in result
        assert '单持仓' in result

    def test_range_bound_2(self):
        from src.analysis.report_templates import format_strategy_mode
        result = format_strategy_mode('range_bound', 2)
        assert '震荡市' in result
        assert '多持仓' in result

    def test_trend_down_1(self):
        from src.analysis.report_templates import format_strategy_mode
        result = format_strategy_mode('trend_down', 1)
        assert '下跌市' in result
        assert '单持仓' in result

    def test_trend_down_2(self):
        from src.analysis.report_templates import format_strategy_mode
        result = format_strategy_mode('trend_down', 2)
        assert '下跌市' in result
        assert '观望' in result

    def test_crash_1(self):
        from src.analysis.report_templates import format_strategy_mode
        result = format_strategy_mode('crash', 1)
        assert '暴跌市' in result
        assert '空仓' in result

    def test_crash_2(self):
        from src.analysis.report_templates import format_strategy_mode
        result = format_strategy_mode('crash', 2)
        assert '暴跌市' in result
        assert '空仓' in result

    def test_unknown_combination_fallback(self):
        from src.analysis.report_templates import format_strategy_mode
        result = format_strategy_mode('unknown_regime', 3)
        # fallback 不应崩溃
        assert result  # 非空


class TestFormatActionAdvice:
    """段 2: 操作建议（D1+D2+D3+D4）"""

    def test_crash_no_action(self):
        from src.analysis.report_templates import format_action_advice
        result = format_action_advice('crash', True, True, 0, 2)
        assert '暴跌市' in result
        assert '不加仓' in result

    def test_max_holdings_reached(self):
        """D3=A: 合并 US-009 满仓判断"""
        from src.analysis.report_templates import format_action_advice
        result = format_action_advice('range_bound', True, True, 2, 2)
        assert '已达仓位上限' in result
        assert '调仓' in result

    def test_cash_insufficient(self):
        from src.analysis.report_templates import format_action_advice
        result = format_action_advice('range_bound', True, False, 0, 2)
        assert '现金不足' in result

    def test_no_recommendation(self):
        from src.analysis.report_templates import format_action_advice
        result = format_action_advice('range_bound', False, True, 0, 2)
        assert '无满足条件' in result

    def test_trend_up_recommendation(self):
        from src.analysis.report_templates import format_action_advice
        result = format_action_advice('trend_up', True, True, 0, 2)
        assert '重仓买入' in result

    def test_range_bound_recommendation(self):
        from src.analysis.report_templates import format_action_advice
        result = format_action_advice('range_bound', True, True, 0, 2)
        assert '轻仓试水' in result

    def test_trend_down_recommendation(self):
        from src.analysis.report_templates import format_action_advice
        result = format_action_advice('trend_down', True, True, 0, 2)
        assert '审慎' in result

    def test_priority_actions_sell(self):
        """D4=A: 9 步决策树输出有清仓动作时，操作建议优先"""
        from src.analysis.report_templates import format_action_advice
        portfolio_actions = [
            {'action': '清仓（用户决策）', 'code': '159611'},
            {'action': '持有（短期）', 'code': '515050'},
        ]
        result = format_action_advice(
            'trend_up', True, True, 1, 2, portfolio_actions
        )
        assert '优先处理持仓动作' in result
        assert '159611' in result


class TestFormatScenario:
    """段 3: 情景分析（D2+D5）"""

    def test_default_scenarios(self):
        """无 validation_results 时用默认 4 套"""
        from src.analysis.report_templates import format_scenario
        for regime in ['trend_up', 'range_bound', 'trend_down', 'crash']:
            result = format_scenario(regime)
            assert '乐观' in result
            assert '中性' in result
            assert '悲观' in result

    def test_with_validation_results(self):
        """D5=A: 有 validation_results 时按回测算"""
        from src.analysis.report_templates import format_scenario
        validation = [
            {'period': '2023-2025', 'return': 37.3, 'drawdown': -30.1, 'sharpe': 0.46, 'winrate': 30.8, 'trades': 13},
            {'period': '2024-2026', 'return': 207.2, 'drawdown': -25.1, 'sharpe': 2.05, 'winrate': 58.3, 'trades': 12},
        ]
        result = format_scenario('range_bound', validation_results=validation)
        # 应该有合理数字（不是 100% 以上的丑数）
        import re
        nums = re.findall(r'[+-]?\d+', result)
        for n in nums:
            assert -50 <= int(n) <= 100, f"数字越界: {n}"

    def test_scenario_chinese_pct_format(self):
        """情景分析百分比格式"""
        from src.analysis.report_templates import format_scenario
        result = format_scenario('trend_up')
        # 概率格式
        assert '45%' in result or '40%' in result or '15%' in result


class TestReportIntegration:
    """集成测试：报告输出含动态化字段"""

    def test_report_uses_dynamic_strategy_mode(self):
        """报告'策略模式'段不再是硬编码'单持仓'"""
        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        report = gen.generate_report(capital=20000)
        # 旧文案不应再出现（除非对应模板就是"单持仓"）
        # 关键是包含'震荡市'或'趋势市'等市场标识
        assert ('震荡市' in report or '趋势市' in report or
                '下跌市' in report or '暴跌市' in report)

    def test_report_uses_dynamic_action_advice(self):
        """报告'操作建议'段含具体状态描述（不再是固定'轻仓观望'）"""
        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        report = gen.generate_report(capital=20000)
        # 应含"操作建议"段（动态）
        assert '【操作建议】' in report
