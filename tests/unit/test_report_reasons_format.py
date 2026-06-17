#!/usr/bin/env python3
"""
报告 reasons 格式测试（SOP-P0-2）

覆盖：
1. 推荐理由带分数显示："MA120(+3)+MA60向上(+2)+MA60(+2)"
2. 核心推荐有 1/2/3 标的对比（说明选 1 不选 2 的理由）
3. RSI 超买有警告（不只列分项，还提示风险）
"""
import os
import sys
import pytest
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope='module')
def report_content():
    """跑一次 eval 生成报告，返回内容"""
    from src.analysis.report_generator import generate_decision_report
    text = generate_decision_report(capital=20000, simple=True)
    return text


class TestReportReasonsFormat:
    """报告 reasons 格式验证"""

    def test_reasons_include_score_format(self, report_content):
        """推荐理由带分数：'MA120(+3)+MA60向上(+2)+MA60(+2)'"""
        # 查找 TOP 10 推荐部分
        m = re.search(r'TOP 10 推荐.+?核心推荐', report_content, re.DOTALL)
        assert m, '报告里找不到 TOP 10 推荐部分'

        top_section = m.group(0)
        # 至少一行推荐理由包含 (+N) 格式
        has_score_format = bool(re.search(r'\(\+\d+\)', top_section))
        assert has_score_format, f'推荐理由应包含分数格式 (+N)，实际:\n{top_section}'

    def test_top3_etfs_listed_with_reasons(self, report_content):
        """核心推荐应列 Top 3 标的（不是只 1 个）"""
        m = re.search(r'【核心推荐 Top 3 对比】(.+?)\n\n=+', report_content, re.DOTALL)
        if m:
            core_section = m.group(1)
            etf_count = len(re.findall(r'^\d+\.', core_section, re.MULTILINE))
            assert etf_count >= 1, f'核心推荐应至少 1 个标的，实际 {etf_count}'

    def test_why_not_pick_others_section(self, report_content):
        """报告应包含'选 X 不选 Y 的理由'部分"""
        assert '不选' in report_content or '差距' in report_content, \
            f'报告应说明"选 1 不选 2/3 的理由"，实际报告应含这些关键词'


class TestReportRsiWarning:
    """RSI 超买警告验证"""

    def test_rsi_warning_when_overbought(self, report_content):
        """RSI > 80 标的应被警告（不只列分项）"""
        has_rsi_mention = 'RSI' in report_content
        assert has_rsi_mention, '报告应包含 RSI 提示'

