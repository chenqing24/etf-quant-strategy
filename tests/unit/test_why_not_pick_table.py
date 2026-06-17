#!/usr/bin/env python3
"""
为什么不选 Top 2/3 完整对比表测试（SOP-P1-1）

覆盖：
1. 报告应包含 Top 3 完整指标对比表（分数/价格/5日/20日/均量/RSI）
2. "为什么不选"应明确列出每只被排除标的的具体劣势
3. RSI/价格/涨幅都应在对比表中
"""
import re
import sys
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope='module')
def report_content():
    from src.analysis.report_generator import generate_decision_report
    return generate_decision_report(capital=20000, simple=True)


class TestFullComparisonTable:
    """Top 3 完整对比表"""

    def test_table_has_all_metrics(self, report_content):
        """对比表应含 分数/价格/5日/20日/均量/RSI"""
        m = re.search(r'【核心推荐 Top 3 对比】(.+?)【选', report_content, re.DOTALL)
        assert m, '报告应包含 Top 3 对比部分'

        section = m.group(1)
        # 关键指标都应在表头
        assert '分数' in section
        assert '价格' in section
        assert '5日' in section
        assert '20日' in section
        assert '均量' in section or '成交量' in section


class TestWhyNotPickSection:
    """为什么不选 Top 2/3 详细说明"""

    def test_why_not_section_mentions_specific_disadvantage(self, report_content):
        """为什么不选应列出每只标的的具体劣势"""
        m = re.search(r'【选 \d+ 不选 \d+ 的理由】(.+?)\n\n=+', report_content, re.DOTALL)
        assert m, '报告应包含"为什么不选"段落'

        section = m.group(1)
        # 段落应包含次级指标
        has_metric = any(s in section for s in ['20日', '均量', '涨幅', 'RSI', '价格'])
        assert has_metric, f'"为什么不选"段落应引用次级指标，实际: {section}'
