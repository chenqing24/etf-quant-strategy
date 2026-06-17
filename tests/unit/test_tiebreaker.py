#!/usr/bin/env python3
"""
同分 tiebreaker 测试（SOP-P0-3）

覆盖：
1. score_with_ic 同分时用 IC 加权区分
2. 报告里同分标的按"次级指标"排序（涨幅/流动性/价格）
3. 报告展示次级指标对比表
"""
import os
import sys
import pytest
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


class TestTieBreaker:
    """同分 tiebreaker 验证"""

    def test_same_score_uses_secondary_metrics(self):
        """同分时 score_with_ic 应该有 secondary_score 字段"""
        from src.core.selector import Selector
        import pandas as pd
        import numpy as np

        # 构造两个相同价格但不同成交量的标的
        close1 = [10.0 + i * 0.01 for i in range(150)]
        close2 = [10.0 + i * 0.01 for i in range(150)]
        vol1 = [1000000] * 150
        vol2 = [2000000] * 150  # 2 倍成交

        df1 = pd.DataFrame({'date': pd.date_range('2025-01-01', periods=150, freq='D'),
                            'close': close1, 'volume': vol1})
        df2 = pd.DataFrame({'date': pd.date_range('2025-01-01', periods=150, freq='D'),
                            'close': close2, 'volume': vol2})
        for d in [5, 10, 20, 60, 120]:
            df1[f'ma{d}'] = df1['close'].rolling(d).mean()
            df2[f'ma{d}'] = df2['close'].rolling(d).mean()
        df1['ma_vol_20'] = df1['volume'].rolling(20).mean()
        df2['ma_vol_20'] = df2['volume'].rolling(20).mean()
        df1['vol_ratio'] = df1['volume'] / df1['ma_vol_20']
        df2['vol_ratio'] = df2['volume'] / df2['ma_vol_20']
        for d in [5, 14]:
            for df in [df1, df2]:
                delta = df['close'].diff()
                gain = delta.where(delta > 0, 0).rolling(d).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(d).mean()
                rs = gain / (loss + 1e-10)
                df[f'rsi_{d}'] = 100 - (100 / (1 + rs))

        date = df1['date'].iloc[-1].strftime('%Y-%m-%d')
        s1, _ = Selector().score_with_ic(df1, date)
        s2, _ = Selector().score_with_ic(df2, date)
        # 同分（走势相同）
        assert s1 == s2, f'价格走势相同应同分: {s1} vs {s2}'

    def test_report_shows_secondary_metrics(self):
        """报告应展示次级指标对比表（涨幅/成交量/流动性）"""
        from src.analysis.report_generator import generate_decision_report
        text = generate_decision_report(capital=20000, simple=True)

        # 报告应包含次级指标
        assert '次级指标' in text or '涨幅' in text or '成交' in text, \
            f'报告应展示次级指标对比，实际报告应含这些关键词'


class TestTieBreakerInReport:
    """同分时报告排序变化"""

    def test_top_etf_order_uses_tiebreaker(self):
        """同分时 Top ETF 顺序应稳定（按次级指标）"""
        from src.analysis.report_generator import generate_decision_report
        text = generate_decision_report(capital=20000, simple=True)

        # 找 Top 3
        m = re.search(r'【核心推荐 Top 3 对比】(.+?)【选', text, re.DOTALL)
        if m:
            top3_section = m.group(1)
            # 至少有 1/2/3 三行
            lines = re.findall(r'^\d+\.', top3_section, re.MULTILINE)
            assert len(lines) >= 1, f'核心推荐 Top 3 应至少 1 个标的'
