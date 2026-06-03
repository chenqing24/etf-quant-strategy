#!/usr/bin/env python3
"""
US-006 单元测试：market_mode 语义修正

覆盖：
- MarketRegimeDetector.detect() 各种市场环境
- can_trade() 业务规则（只有 trend_up 允许交易）
- ETFDecisionEngine._detect_market_mode() 集成
- _regime_to_label() 翻译正确
"""
import os
import sys
import pytest
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


def make_strong_trend():
    """强趋势: 200% 上涨"""
    dates = pd.date_range('2025-01-01', periods=200, freq='D')
    return pd.DataFrame({
        'date': dates,
        'close': np.linspace(1.0, 3.0, 200),
        'high': np.linspace(1.0, 3.0, 200) * 1.01,
        'low': np.linspace(1.0, 3.0, 200) * 0.99,
    })


def make_range_bound():
    """震荡市: 正弦波 ±5%"""
    dates = pd.date_range('2025-01-01', periods=200, freq='D')
    sin_wave = 2.0 + 0.1 * np.sin(np.linspace(0, 4 * np.pi, 200))
    return pd.DataFrame({
        'date': dates,
        'close': sin_wave,
        'high': sin_wave + 0.05,
        'low': sin_wave - 0.05,
    })


def make_down_trend():
    """下跌趋势: 200% 下跌"""
    dates = pd.date_range('2025-01-01', periods=200, freq='D')
    return pd.DataFrame({
        'date': dates,
        'close': np.linspace(3.0, 1.0, 200),
        'high': np.linspace(3.0, 1.0, 200) * 1.01,
        'low': np.linspace(3.0, 1.0, 200) * 0.99,
    })


def make_crash():
    """暴跌: 5 天内跌 50%"""
    dates = pd.date_range('2025-01-01', periods=200, freq='D')
    close = np.concatenate([
        np.linspace(3.0, 2.0, 195),
        np.linspace(2.0, 1.0, 5),
    ])
    return pd.DataFrame({
        'date': dates,
        'close': close,
        'high': close * 1.05,
        'low': close * 0.95,
    })


class TestMarketRegimeDetector:
    """MarketRegimeDetector.detect 测试"""

    def test_strong_trend(self):
        from src.analysis.market_regime import MarketRegimeDetector
        d = MarketRegimeDetector()
        assert d.detect(make_strong_trend()) == 'trend_up'

    def test_range_bound(self):
        from src.analysis.market_regime import MarketRegimeDetector
        d = MarketRegimeDetector()
        assert d.detect(make_range_bound()) == 'range_bound'

    def test_down_trend(self):
        from src.analysis.market_regime import MarketRegimeDetector
        d = MarketRegimeDetector()
        assert d.detect(make_down_trend()) == 'trend_down'

    def test_crash(self):
        from src.analysis.market_regime import MarketRegimeDetector
        d = MarketRegimeDetector()
        assert d.detect(make_crash()) == 'crash'

    def test_insufficient_data_defaults_to_range(self):
        """数据不足默认震荡市"""
        from src.analysis.market_regime import MarketRegimeDetector
        d = MarketRegimeDetector()
        df = make_strong_trend().head(50)  # 只有 50 行
        assert d.detect(df) == 'range_bound'

    def test_empty_data_returns_range(self):
        """空数据返回震荡市"""
        from src.analysis.market_regime import MarketRegimeDetector
        d = MarketRegimeDetector()
        df = pd.DataFrame({'date': [], 'close': [], 'high': [], 'low': []})
        assert d.detect(df) == 'range_bound'


class TestCanTrade:
    """can_trade 业务规则"""

    def test_trend_up_allows_trade(self):
        from src.analysis.market_regime import MarketRegimeDetector
        d = MarketRegimeDetector()
        assert d.can_trade('trend_up') is True

    def test_range_bound_blocks_trade(self):
        """震荡市必须空仓"""
        from src.analysis.market_regime import MarketRegimeDetector
        d = MarketRegimeDetector()
        assert d.can_trade('range_bound') is False

    def test_down_trend_blocks_trade(self):
        from src.analysis.market_regime import MarketRegimeDetector
        d = MarketRegimeDetector()
        assert d.can_trade('trend_down') is False

    def test_crash_blocks_trade(self):
        from src.analysis.market_regime import MarketRegimeDetector
        d = MarketRegimeDetector()
        assert d.can_trade('crash') is False


class TestRegimeLabels:
    """标签翻译测试"""

    def test_trend_up_label(self):
        from src.analysis.market_regime import MarketRegimeDetector
        d = MarketRegimeDetector()
        assert '趋势市' in d.get_label('trend_up')
        assert d.get_emoji('trend_up') == '📈'

    def test_range_bound_label(self):
        from src.analysis.market_regime import MarketRegimeDetector
        d = MarketRegimeDetector()
        assert '震荡市' in d.get_label('range_bound')
        assert d.get_emoji('range_bound') == '📊'

    def test_down_trend_label(self):
        from src.analysis.market_regime import MarketRegimeDetector
        d = MarketRegimeDetector()
        assert '下跌市' in d.get_label('trend_down')
        assert d.get_emoji('trend_down') == '🔻'

    def test_crash_label(self):
        from src.analysis.market_regime import MarketRegimeDetector
        d = MarketRegimeDetector()
        assert '暴跌市' in d.get_label('crash')
        assert d.get_emoji('crash') == '🚨'


class TestDecisionEngineIntegration:
    """ETFDecisionEngine 集成测试"""

    def test_detect_market_mode(self):
        """_detect_market_mode 返回合法 regime"""
        from unittest.mock import patch
        with patch('src.cli.decision.ETFDecisionEngine.__init__', return_value=None):
            from src.cli.decision import ETFDecisionEngine
            engine = ETFDecisionEngine()
        regime = engine._detect_market_mode()
        assert regime in ('trend_up', 'range_bound', 'trend_down', 'crash')

    def test_regime_to_label_all(self):
        """所有 4 个 regime 都有标签"""
        from unittest.mock import patch
        with patch('src.cli.decision.ETFDecisionEngine.__init__', return_value=None):
            from src.cli.decision import ETFDecisionEngine
            engine = ETFDecisionEngine()
        for regime in ['trend_up', 'range_bound', 'trend_down', 'crash']:
            label = engine._regime_to_label(regime)
            # 包含 emoji + 中文
            assert any(emoji in label for emoji in ['📈', '📊', '🔻', '🚨'])
            assert any(word in label for word in ['趋势市', '震荡市', '下跌市', '暴跌市'])


class TestRealMarketData:
    """真实数据集成"""

    def test_real_510300_data(self):
        """真实 510300 数据能判断 regime"""
        from src.analysis.market_regime import MarketRegimeDetector
        import sqlite3

        conn = sqlite3.connect(ROOT / 'etf_data_live' / 'etf.db')
        try:
            df = pd.read_sql_query(
                "SELECT date, close, high, low FROM daily WHERE code='510300' ORDER BY date",
                conn
            )
        finally:
            conn.close()

        if df.empty or len(df) < 130:
            pytest.skip("510300 数据不足")

        d = MarketRegimeDetector()
        regime = d.detect(df)
        # 真实数据应该返回合法 regime
        assert regime in ('trend_up', 'range_bound', 'trend_down', 'crash')
        print(f"\\n真实 510300 regime: {regime}")
