#!/usr/bin/env python3
"""US-009 单元测试：报告接入 TradeTracker"""
import os
import sys
import json
import tempfile
import sqlite3
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def isolated_tracker(isolated_tracker):
    """US-014: 用 conftest 全局 fixture（自动加载所有 migrations）"""
    t, tmpdir, tmp_db = isolated_tracker
    yield t



class TestGetAccountSummary:
    """TradeTracker.get_account_summary()"""

    def test_empty_account(self, isolated_tracker):
        """空仓账户：cash=20000, positions_value=0, total_asset=20000"""
        summary = isolated_tracker.get_account_summary()
        assert summary['cash'] == 20000
        assert summary['positions_value'] == 0
        assert summary['total_asset'] == 20000
        assert summary['hold_count'] == 0
        assert summary['holdings'] == []
        assert summary['max_holdings'] == 2

    def test_default_max_holdings_is_2(self, isolated_tracker):
        """默认 max_holdings=2（US-008 修复后）"""
        summary = isolated_tracker.get_account_summary()
        assert summary['max_holdings'] == 2

    def test_custom_max_holdings(self, isolated_tracker):
        """可自定义 max_holdings"""
        summary = isolated_tracker.get_account_summary(max_holdings=5)
        assert summary['max_holdings'] == 5


class TestReportWithTracker:
    """generate_report(tracker=...) 输出含账户信息"""

    def test_report_contains_account_status(self, isolated_tracker, capsys):
        """报告'基本信息'段含 '当前持仓' 字段"""
        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        report = gen.generate_report(capital=20000, tracker=isolated_tracker)
        # US-009 关键字段
        assert '当前持仓' in report
        assert '现金' in report
        assert '可投入' in report
        assert 'max_holdings' not in report or '最多2' in report

    def test_report_strategy_mode_is_dynamic(self, isolated_tracker):
        """报告'策略模式'段不是固定'单持仓'（US-009 修复）"""
        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        report = gen.generate_report(capital=20000, tracker=isolated_tracker)
        # US-009 修复: 报告应反映 max_holdings=2
        assert '单持仓' not in report  # 不再写"单持仓"
        assert '多持仓' in report or '最多2' in report  # 动态文案

    def test_report_capital_section_includes_holdings_count(self, isolated_tracker):
        """资金配置段含'已持仓 N只'"""
        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        report = gen.generate_report(capital=20000, tracker=isolated_tracker)
        assert '已持仓' in report
        assert '2只' in report or '2 只' in report  # 持仓数显示

    def test_report_full_holdings_says_maxed_out(self, isolated_tracker):
        """满仓（2只持仓）报告说'已达仓位上限'"""
        from src.trade.tracker import TradeTracker
        # 模拟 2 只持仓
        isolated_tracker.record_buy('512480', '512480', 2.150, 1000, 'test')
        isolated_tracker.record_buy('515050', '通信ETF华夏', 1.197, 1000, 'test')
        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        report = gen.generate_report(capital=20000, tracker=isolated_tracker)
        assert '已达仓位上限' in report
        assert '暂不买入' in report

    def test_report_backward_compatible_no_tracker(self):
        """tracker=None 时走旧逻辑（向后兼容）"""
        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        # 不传 tracker，报告按 capital 算
        # 不报错即 OK
        try:
            report = gen.generate_report(capital=20000)
        except Exception as e:
            pytest.fail(f"backward compatible failed: {e}")

    def test_generate_decision_report_accepts_tracker(self, isolated_tracker):
        """generate_decision_report 接受 tracker 参数"""
        from src.analysis.report_generator import generate_decision_report
        report = generate_decision_report(capital=20000, simple=True, tracker=isolated_tracker)
        assert '当前持仓' in report


class TestUS008BugFix:
    """US-008 漏改的 self.performance_file 修复"""

    def test_performance_file_attribute_exists(self, isolated_tracker):
        """TradeTracker 应有 self.performance_file 属性（US-008 漏改）"""
        assert hasattr(isolated_tracker, 'performance_file')
        assert isolated_tracker.performance_file.endswith('etf_performance.json')

    def test_get_performance_summary_works(self, isolated_tracker):
        """get_performance_summary() 能读 performance.json"""
        result = isolated_tracker.get_performance_summary()
        assert 'current_capital' in result
        assert result['current_capital'] == 20000
