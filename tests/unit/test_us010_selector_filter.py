#!/usr/bin/env python3
"""US-010 单元测试：selector 过滤已持仓"""
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
def mock_data():
    """Mock 14 只 ETF 的 data（用于测试 select_etfs）"""
    import pandas as pd
    import numpy as np
    data = {}
    for code in ['512480', '515050', '515070', '588000', '512880', '512170',
                 '512200', '512400', '512660', '512800', '512980', '515650',
                 '515790', '520900']:
        # 构造 200 天数据（满足训练期 > 100 天）
        dates = pd.date_range('2022-01-01', periods=200, freq='D')
        np.random.seed(hash(code) % 100)
        prices = 1.0 + np.random.rand(200) * 0.5
        df = pd.DataFrame({
            'date': dates.strftime('%Y-%m-%d'),
            'close': prices,
        })
        data[code] = df
    return data


class TestSelectEtfsHeldFilter:
    """ETFSelector.select_etfs(held_codes=...) 过滤已持仓"""

    def test_no_held_codes_default(self, mock_data):
        """默认 held_codes=None，等价于空集合"""
        from src.core.selector import Selector
        from src.utils.config import StrategyConfig
        config = StrategyConfig()
        config.top_n = 5
        selected = Selector().select_etfs(mock_data, config)
        # 14 只都参与，返回前 5
        assert len(selected) == 5

    def test_held_codes_excludes_match(self, mock_data):
        """held_codes 里的代码不入选"""
        from src.core.selector import Selector
        from src.utils.config import StrategyConfig
        config = StrategyConfig()
        config.top_n = 5
        selected = Selector().select_etfs(mock_data, config, held_codes={'515050'})
        assert '515050' not in selected
        # 仍返回 5 只（从剩下 13 选 5）
        assert len(selected) == 5

    def test_held_codes_excludes_multiple(self, mock_data):
        """多个持仓全部被过滤"""
        from src.core.selector import Selector
        from src.utils.config import StrategyConfig
        config = StrategyConfig()
        config.top_n = 5
        selected = Selector().select_etfs(
            mock_data, config, held_codes={'515050', '512480'}
        )
        assert '515050' not in selected
        assert '512480' not in selected
        assert len(selected) == 5

    def test_held_codes_empty_set_explicit(self, mock_data):
        """held_codes=set() 与 None 等价"""
        from src.core.selector import Selector
        from src.utils.config import StrategyConfig
        config = StrategyConfig()
        config.top_n = 5
        selected_a = Selector().select_etfs(mock_data, config, held_codes=None)
        selected_b = Selector().select_etfs(mock_data, config, held_codes=set())
        assert selected_a == selected_b


class TestReportFilterNotice:
    """报告含"过滤说明"段"""

    def test_report_with_no_holdings_no_filter_notice(self):
        """空仓时不显示过滤说明"""
        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        report = gen.generate_report(capital=20000)
        # 无持仓 → 不应有过滤说明
        assert '【过滤说明】' not in report

    def test_report_includes_filter_notice_with_holdings(self, isolated_tracker):
        """持仓时报告含'过滤说明'段"""
        tracker, tmpdir, tmp_db = isolated_tracker
        # 模拟持仓
        tracker.record_buy('515050', '通信ETF华夏', 1.197, 1000, 'test')
        tracker.record_buy('159611', '电力ETF广发', 1.221, 1900, 'test')

        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        report = gen.generate_report(capital=20000, tracker=tracker)

        # US-010 关键断言
        assert '【过滤说明】' in report
        assert '515050' in report
        assert '已持仓' in report
        assert '不重复推荐' in report

    def test_legacy_holding_not_in_filter_notice(self, isolated_tracker):
        """legacy_holding（159611）不在过滤说明中（不在 core 池）"""
        tracker, tmpdir, tmp_db = isolated_tracker
        tracker.record_buy('159611', '电力ETF广发', 1.221, 1900, 'test',
                           is_real=1)
        # 直接改 positions 表的 legacy_holding 字段
        conn = sqlite3.connect(tmp_db)
        conn.execute("UPDATE positions SET legacy_holding=1 WHERE code='159611'")
        conn.commit()
        conn.close()

        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        report = gen.generate_report(capital=20000, tracker=tracker)
        # 159611 不会出现在过滤说明
        filter_section_start = report.find('【过滤说明】')
        filter_section_end = report.find('\n\n【核心推荐】') if filter_section_start >= 0 else -1
        if filter_section_start >= 0 and filter_section_end > filter_section_start:
            filter_section = report[filter_section_start:filter_section_end]
            # 过滤说明段不应含 159611
            assert '159611' not in filter_section
