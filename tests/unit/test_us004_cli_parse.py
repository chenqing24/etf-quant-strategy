#!/usr/bin/env python3
"""
US-004 单元测试：CLI 解析 ETF 代码 + 价格

覆盖：
- 510300/512480/515070/159xxx 各种 6 位数字代码
- 实时价 vs 信号价（first-match-wins）
- 名称从数据库回退
"""
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


class TestParseRecommendation:
    """_parse_recommendation 单元测试"""

    def _engine(self):
        with patch('src.cli.decision.ETFDecisionEngine.__init__', return_value=None):
            from src.cli.decision import ETFDecisionEngine
            return ETFDecisionEngine()

    def test_parse_510300(self):
        """510300 完整解析"""
        engine = self._engine()
        report = """【操作】买入 510300 沪深300ETF华泰柏瑞 3600股
【价格】4.966元
【止损】-6% (4.668元)
【止盈】+10% (5.463元)"""
        action, code, name, price, qty, sl, sp = engine._parse_recommendation(report)
        assert action == '买入'
        assert code == '510300'
        assert name == '沪深300ETF华泰柏瑞'
        assert abs(price - 4.966) < 0.001
        assert qty == 3600
        assert abs(sl - 4.668) < 0.001
        assert abs(sp - 5.463) < 0.001

    def test_parse_512480(self):
        """512480 解析"""
        engine = self._engine()
        report = """【操作】买入 512480 512480 2500股
【价格】2.150元
【止损】-6% (2.021元)
【止盈】+10% (2.365元)"""
        action, code, name, price, qty, sl, sp = engine._parse_recommendation(report)
        assert code == '512480'
        assert abs(price - 2.150) < 0.001
        assert qty == 2500

    def test_parse_515070(self):
        """515070 解析"""
        engine = self._engine()
        report = """【操作】买入 515070 515070 1500股
【价格】2.587元
【止损】-6% (2.432元)
【止盈】+10% (2.846元)"""
        action, code, name, price, qty, sl, sp = engine._parse_recommendation(report)
        assert code == '515070'
        assert abs(price - 2.587) < 0.001

    def test_parse_159611(self):
        """159xxx 系列解析"""
        engine = self._engine()
        report = """【操作】买入 159611 159611 5000股
【价格】1.251元
【止损】-6% (1.176元)
【止盈】+10% (1.376元)"""
        action, code, name, price, qty, sl, sp = engine._parse_recommendation(report)
        assert code == '159611'
        assert abs(price - 1.251) < 0.001
        assert qty == 5000

    def test_parse_588000(self):
        """588000 解析"""
        engine = self._engine()
        report = """【操作】买入 588000 588000 3000股
【价格】1.830元
【止损】-6% (1.720元)
【止盈】+10% (2.013元)"""
        action, code, name, price, qty, sl, sp = engine._parse_recommendation(report)
        assert code == '588000'
        assert abs(price - 1.830) < 0.001

    def test_first_match_wins_for_price(self):
        """【价格】first-match-wins：信号价不被实时价覆盖"""
        engine = self._engine()
        report = """【操作】买入 510300 沪深300ETF华泰柏瑞 3600股
【价格】4.966元
【止损】-6% (4.668元)
【止盈】+10% (5.463元)
======================================================================
🔍 实时校验
======================================================================
【价格】4.970元
【止损】-6% (4.672元)
【止盈】+10% (5.467元)"""
        action, code, name, price, qty, sl, sp = engine._parse_recommendation(report)
        # 应该是 4.966（信号价），不是 4.970（实时价）
        assert abs(price - 4.966) < 0.001
        assert abs(sl - 4.668) < 0.001
        assert abs(sp - 5.463) < 0.001

    def test_no_hardcoded_codes(self):
        """不再依赖硬编码 ['516050', '515050', '159'] 列表"""
        engine = self._engine()
        # 测试一个 512880 (不在硬编码列表里)
        report = """【操作】买入 512880 512880 1000股
【价格】1.200元
【止损】-6% (1.128元)
【止盈】+10% (1.320元)"""
        action, code, name, price, qty, sl, sp = engine._parse_recommendation(report)
        assert code == '512880', f"应解析 512880 (不在硬编码列表)，实际: {code}"

    def test_no_match_returns_empty(self):
        """无匹配时返回空值"""
        engine = self._engine()
        report = """市场正常，无操作"""
        action, code, name, price, qty, sl, sp = engine._parse_recommendation(report)
        assert action == '观望'
        assert code == ''
        assert price == 0.0

    def test_with_today_recommendation_marker(self):
        """有'今日交易建议'标记的报告"""
        engine = self._engine()
        report = """======================================================================
🚨 今日交易建议 (必读)
======================================================================

【操作】买入 588000 588000 3000股
【目标】588000 588000
【价格】1.830元
【数量】3000股 (5,490元)
【止损】-6% (1.720元)
【止盈】+10% (2.013元)"""
        action, code, name, price, qty, sl, sp = engine._parse_recommendation(report)
        assert code == '588000'
        assert abs(price - 1.830) < 0.001


class TestRealReport:
    """真实报告测试"""

    def test_real_report_20260603(self):
        """解析真实生成的报告"""
        with patch('src.cli.decision.ETFDecisionEngine.__init__', return_value=None):
            from src.cli.decision import ETFDecisionEngine
            engine = ETFDecisionEngine()

        report_path = ROOT / 'etf_reports' / 'report_20260603.txt'
        if not report_path.exists():
            pytest.skip("真实报告不存在")

        with open(report_path, 'r') as f:
            report = f.read()

        action, code, name, price, qty, sl, sp = engine._parse_recommendation(report)
        # 报告生成时间 2026-06-03，推荐 510300
        assert action == '买入'
        assert code == '510300'
        assert '沪深300' in name or name == '510300'
        assert abs(price - 4.966) < 0.001, f"price should be 4.966, got {price}"
        assert abs(sl - 4.668) < 0.001, f"sl should be 4.668, got {sl}"
        assert abs(sp - 5.463) < 0.001, f"sp should be 5.463, got {sp}"
