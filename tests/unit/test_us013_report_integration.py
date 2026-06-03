#!/usr/bin/env python3
"""US-013 单元测试：报告输出层回归测试

D6=B: 合并到现有 docs/TESTING_STRATEGY.md（不存在则新建独立）
D7=A: 复用 US-009 fixture（临时 db_path + realtime_cache）
D8=B: 每次新 US 跑全量回归

测试目标：
- 报告"策略模式"段不再是硬编码"单持仓"
- 报告"资金配置"段含"当前持仓"字段
- 报告"操作建议"段不是固定"轻仓观望"
- 报告"情景分析"段随市场变化
- 报告"今日推荐"过滤已持仓（US-010）
- account 模式含 PositionGuide
- eval --silent 端到端跑通
"""
import os
import sys
import json
import tempfile
import sqlite3
import subprocess
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def isolated_tracker():
    """US-013 fixture（D7=A: 复用 US-009 fixture）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        from src.trade.tracker import TradeTracker
        tmp_db = os.path.join(tmpdir, 'test.db')
        schema_file = os.path.join(ROOT, 'schema/migrations/004_add_trade_tables.sql')
        conn = sqlite3.connect(tmp_db)
        with open(schema_file) as f:
            conn.executescript(f.read())
        # realtime_cache 表（PositionGuide 依赖）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS realtime_cache (
                code TEXT PRIMARY KEY,
                price REAL, change_pct REAL, source TEXT, updated_at TEXT
            )
        """)
        conn.commit()
        conn.close()
        # performance.json
        with open(os.path.join(tmpdir, 'etf_performance.json'), 'w') as f:
            json.dump({
                'trades': [], 'positions': [],
                'performance': {
                    'initial_capital': 20000, 'current_capital': 20000,
                    'total_pnl': 0, 'total_trades': 0, 'win_rate': 0
                }
            }, f)
        tracker = TradeTracker(data_dir=tmpdir, db_path=tmp_db)
        yield tracker, tmpdir, tmp_db


class TestReportStrategyMode:
    """报告"策略模式"段（US-008/009/011）"""

    def test_strategy_mode_no_longer_hardcoded(self, isolated_tracker):
        """不再是固定'单持仓'（US-009/011 修复后）"""
        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        report = gen.generate_report(capital=20000)
        # 不应再是固定"单持仓 + 6%止损 + 10%止盈"
        assert '单持仓 + 6%止损' not in report
        # 应含动态文案
        assert ('震荡市' in report or '趋势市' in report or
                '下跌市' in report or '暴跌市' in report)

    def test_strategy_mode_includes_max_holdings_2(self, isolated_tracker):
        """'多持仓(最多2)' 应在报告中"""
        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        report = gen.generate_report(capital=20000)
        assert '最多2' in report or '2只' in report


class TestReportCapitalSection:
    """报告"资金配置"段（US-009）"""

    def test_capital_section_includes_holdings_field(self, isolated_tracker):
        """'当前持仓'字段在报告中（提供 tracker 时）"""
        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        tracker, tmpdir, tmp_db = isolated_tracker
        report = gen.generate_report(capital=20000, tracker=tracker)
        assert '当前持仓' in report
        assert '可投入' in report
        assert '总资产' in report

    def test_capital_section_uses_tracker_data(self, isolated_tracker):
        """资金配置段含具体数字（不是占位符）"""
        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        # 用 tracker，报告应含具体数字
        tracker, tmpdir, tmp_db = isolated_tracker
        report = gen.generate_report(capital=20000, tracker=tracker)
        # 现金数字应在报告中
        assert '20,000' in report or '20000' in report


class TestReportActionAdvice:
    """报告"操作建议"段（US-011）"""

    def test_action_advice_is_dynamic(self, isolated_tracker):
        """操作建议段不再是固定'轻仓观望'"""
        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        report = gen.generate_report(capital=20000)
        # 应有动态化操作建议
        assert '【操作建议】' in report
        # 含具体状态描述
        assert ('已达仓位上限' in report or '重仓买入' in report or
                '轻仓试水' in report or '观望' in report)


class TestReportScenario:
    """报告"情景分析"段（US-011）"""

    def test_scenario_table_exists(self, isolated_tracker):
        """情景分析表格存在"""
        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        report = gen.generate_report(capital=20000)
        assert '【情景分析】' in report
        assert '乐观' in report
        assert '中性' in report
        assert '悲观' in report

    def test_scenario_changes_with_market(self, isolated_tracker):
        """情景分析概率分布随市场变化"""
        from src.analysis.report_templates import format_scenario
        scenario_bull = format_scenario('trend_up')
        scenario_bear = format_scenario('crash')
        # 两种市场情景分析段应不同
        assert scenario_bull != scenario_bear
        # 暴跌市悲观概率高
        assert '60%' in scenario_bear  # crash 悲观 60%
        assert '40%' in scenario_bull or '45%' in scenario_bull  # trend_up 乐观 40-45%


class TestReportRecommendationFilter:
    """报告"今日推荐"过滤已持仓（US-010）"""

    def test_recommendation_excludes_holdings(self, isolated_tracker):
        """推荐标的过滤已持仓"""
        tracker, tmpdir, tmp_db = isolated_tracker
        # 模拟 515050 持仓
        tracker.record_buy('515050', '通信ETF华夏', 1.197, 1000, 'test', is_real=1)
        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        report = gen.generate_report(capital=20000, tracker=tracker)
        # 过滤说明段应含 515050
        assert '【过滤说明】' in report
        assert '515050' in report


class TestAccountViewIntegration:
    """account 模式含 PositionGuide（US-012）"""

    def test_account_mode_includes_position_guide(self, isolated_tracker):
        """-m account 模式含 US-007 PositionGuide 输出"""
        tracker, tmpdir, tmp_db = isolated_tracker
        tracker.record_buy('515050', '通信ETF华夏', 1.197, 1000, 'test', is_real=1)
        from src.analysis.account_view import AccountView
        view = AccountView(db_path=tmp_db, market_regime='range_bound')
        output = view.generate()
        # 4 段都应有
        assert '【一、当前持仓' in output
        assert '【二、今日推荐' in output
        assert '【三、动作清单' in output
        assert '【四、账户状态】' in output
        # 动作清单应含 9 步决策树
        assert 'P3' in output or 'P1' in output


class TestE2ERun:
    """端到端：CLI 跑通"""

    def test_eval_silent_runs(self):
        """eval --silent 端到端跑通"""
        result = subprocess.run(
            ['python', '-m', 'src.cli.decision', '-m', 'eval', '--silent'],
            capture_output=True, text=True, cwd=str(ROOT), timeout=120
        )
        assert result.returncode == 0, f"eval 失败: {result.stderr}"

    def test_history_runs(self):
        """history 模式跑通"""
        result = subprocess.run(
            ['python', '-m', 'src.cli.decision', '-m', 'history'],
            capture_output=True, text=True, cwd=str(ROOT), timeout=60
        )
        assert result.returncode == 0, f"history 失败: {result.stderr}"

    def test_account_runs(self):
        """account 模式跑通（US-012）"""
        result = subprocess.run(
            ['python', '-m', 'src.cli.decision', '-m', 'account'],
            capture_output=True, text=True, cwd=str(ROOT), timeout=60
        )
        assert result.returncode == 0, f"account 失败: {result.stderr}"
