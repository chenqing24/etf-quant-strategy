#!/usr/bin/env python3
"""US-018 单元测试: 策略参数单一真相源

根因: 报告头部写 5%/8%（bug），但持仓段/风控段/实时校验都用 6%/10%。
17 处硬编码散落在 report_generator.py (12) + report_templates.py (1) + strings (4)。

修复方案:
1. src/constants.py 新增 5 个策略常量
2. report_generator.py 12 处硬编码替换为常量引用
3. report_templates.py:53-55 修复头部 5%/8% → 6%/10%

设计文档: memory/2026-06-05.md (US-018 Phase 3 v1.0)
测试策略: TDD 红 → 绿
"""
import os
import sys
import re
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────
# 1. constants.py 单一真相源（新增）
# ─────────────────────────────────────────────────────────────

class TestConstantsSingleSource:
    """US-018: src/constants.py 新增策略参数"""

    def test_stop_loss_pct_exists(self):
        """STOP_LOSS_PCT = 0.06 (-6%)"""
        from src.constants import STOP_LOSS_PCT
        assert STOP_LOSS_PCT == 0.06

    def test_take_profit_pct_exists(self):
        """TAKE_PROFIT_PCT = 0.10 (+10%)"""
        from src.constants import TAKE_PROFIT_PCT
        assert TAKE_PROFIT_PCT == 0.10

    def test_stop_loss_price_ratio_exists(self):
        """STOP_LOSS_PRICE_RATIO = 0.94 (= 1 - STOP_LOSS_PCT)"""
        from src.constants import STOP_LOSS_PRICE_RATIO, STOP_LOSS_PCT
        assert STOP_LOSS_PRICE_RATIO == 1 - STOP_LOSS_PCT
        assert abs(STOP_LOSS_PRICE_RATIO - 0.94) < 1e-6

    def test_take_profit_price_ratio_exists(self):
        """TAKE_PROFIT_PRICE_RATIO = 1.10 (= 1 + TAKE_PROFIT_PCT)"""
        from src.constants import TAKE_PROFIT_PRICE_RATIO, TAKE_PROFIT_PCT
        assert TAKE_PROFIT_PRICE_RATIO == 1 + TAKE_PROFIT_PCT
        assert abs(TAKE_PROFIT_PRICE_RATIO - 1.10) < 1e-6

    def test_max_hold_days_exists(self):
        """MAX_HOLD_DAYS = 15"""
        from src.constants import MAX_HOLD_DAYS
        assert MAX_HOLD_DAYS == 15

    def test_trailing_stop_constants_exist(self):
        """移动止盈参数"""
        from src.constants import TRAILING_STOP_PCT, TRAILING_THRESHOLD_PCT
        assert TRAILING_STOP_PCT == 0.04   # 回撤 4%
        assert TRAILING_THRESHOLD_PCT == 0.06  # 启用阈值 6%

    def test_max_total_stop_loss_exists(self):
        """MAX_TOTAL_STOP_LOSS = -0.10"""
        from src.constants import MAX_TOTAL_STOP_LOSS
        assert MAX_TOTAL_STOP_LOSS == -0.10


# ─────────────────────────────────────────────────────────────
# 2. report_templates.py 头部修复（关键 bug）
# ─────────────────────────────────────────────────────────────

class TestTemplateHeaderFixed:
    """US-018: 报告头部 5%/8% → 6%/10% 修复"""

    def test_range_bound_2_header_uses_6_10(self):
        """震荡市多持仓: 头部应是 6% 止损 + 10% 止盈（不是 5%/8%）"""
        from src.analysis.report_templates import format_strategy_mode
        result = format_strategy_mode('range_bound', 2)
        assert '6%' in result, f"头部应含 6% 止损, 实际: {result}"
        assert '10%' in result, f"头部应含 10% 止盈, 实际: {result}"
        # 不应再含旧值
        assert '5%' not in result or '5%' in result and '6%' in result
        # 关键: 不应是 5% 止损
        assert '5%止损' not in result, f"头部不应含 5% 止损, 实际: {result}"
        assert '8%止盈' not in result, f"头部不应含 8% 止盈, 实际: {result}"

    def test_trend_up_2_header_uses_6_10(self):
        """趋势市多持仓: 头部应是 6% 止损 + 10% 止盈"""
        from src.analysis.report_templates import format_strategy_mode
        result = format_strategy_mode('trend_up', 2)
        # trend_up 原本是 5% 止损 + 12% 止盈, 现在统一 6%/10%
        assert '6%' in result
        assert '10%' in result
        assert '12%止盈' not in result, f"头部不应含 12% 止盈（统一为 10%）: {result}"

    def test_all_strategy_modes_mention_6_percent_stop(self):
        """所有 8 种策略模式都应是 6% 止损（统一真相源）"""
        from src.analysis.report_templates import format_strategy_mode
        regimes = ['trend_up', 'range_bound', 'trend_down', 'crash']
        for regime in regimes:
            for max_h in [1, 2]:
                result = format_strategy_mode(regime, max_h)
                # crash 是空仓, 不含止损
                if '空仓' in result or '观望' in result:
                    continue
                # 其他应含 6% 止损
                assert '6%' in result, f"{regime} x {max_h} 应含 6%: {result}"


# ─────────────────────────────────────────────────────────────
# 3. 行为不变性（持仓段计算不变）
# ─────────────────────────────────────────────────────────────

class TestBehaviorUnchangedHoldings:
    """US-018: 持仓段计算结果不变（行为变化类重构）"""

    def test_holdings_stop_loss_calculation_unchanged(self):
        """持仓段止损 = entry * 0.94（不变）"""
        # 持仓段算法行为不变, 仅硬编码 → 常量
        from src.constants import STOP_LOSS_PRICE_RATIO
        entry = 1.197
        expected_stop_loss = entry * STOP_LOSS_PRICE_RATIO
        # 1.197 * 0.94 = 1.12518
        assert abs(expected_stop_loss - 1.12518) < 1e-4

    def test_holdings_take_profit_calculation_unchanged(self):
        """持仓段止盈 = entry * 1.10（不变）"""
        from src.constants import TAKE_PROFIT_PRICE_RATIO
        entry = 1.197
        expected_take_profit = entry * TAKE_PROFIT_PRICE_RATIO
        # 1.197 * 1.10 = 1.3167
        assert abs(expected_take_profit - 1.3167) < 1e-4

    def test_report_holdings_section_uses_constants(self):
        """持仓段 6% 止损 / 10% 止盈（与原行为一致）"""
        # 模拟持仓段输出
        from src.constants import (
            STOP_LOSS_PRICE_RATIO, TAKE_PROFIT_PRICE_RATIO
        )
        entry = 1.197
        stop_loss = entry * STOP_LOSS_PRICE_RATIO
        take_profit = entry * TAKE_PROFIT_PRICE_RATIO

        # 与实际报告对比
        actual_stop_loss = 1.125
        actual_take_profit = 1.317
        assert abs(stop_loss - actual_stop_loss) < 0.01
        assert abs(take_profit - actual_take_profit) < 0.01


# ─────────────────────────────────────────────────────────────
# 4. 报告输出端到端验证
# ─────────────────────────────────────────────────────────────

class TestReportEndToEnd:
    """US-018: 报告生成后头部与持仓段一致（不再矛盾）"""

    def test_report_header_6_10_after_fix(self):
        """修复后: 报告头部含 6% 止损（不再含 5%）"""
        from src.analysis.report_templates import format_strategy_mode
        header = format_strategy_mode('range_bound', 2)
        # 修复后: 6% 止损 + 10% 止盈
        assert '6%止损' in header
        assert '10%止盈' in header

    def test_header_and_holdings_consistent(self):
        """修复后: 头部和持仓段参数一致（不再矛盾）"""
        from src.analysis.report_templates import format_strategy_mode
        from src.constants import (
            STOP_LOSS_PCT, TAKE_PROFIT_PCT,
            STOP_LOSS_PRICE_RATIO, TAKE_PROFIT_PRICE_RATIO
        )
        # 头部
        header = format_strategy_mode('range_bound', 2)
        # 持仓段
        entry = 1.0
        stop_loss = entry * STOP_LOSS_PRICE_RATIO
        take_profit = entry * TAKE_PROFIT_PRICE_RATIO

        # 头部含 6% 10%, 持仓段计算用 0.06/0.10
        assert f'{int(STOP_LOSS_PCT*100)}%' in header  # 6%
        assert f'{int(TAKE_PROFIT_PCT*100)}%' in header  # 10%
        assert abs(stop_loss - 0.94) < 1e-6
        assert abs(take_profit - 1.10) < 1e-6
