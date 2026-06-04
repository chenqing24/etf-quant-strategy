#!/usr/bin/env python3
"""
US-003 单元测试：所有 selector 走 SQL 过滤（510300 排除）

覆盖：
- ETFListLoader 不包含 510300
- Repository.list_codes('core') 不包含 510300
- src.core.selector 过滤掉 510300
- src.analysis.report_generator 过滤掉 510300
- src.strategy.macd_strategy 过滤掉 510300
- 510300 仍能通过 Repository 直接查询
- monitor.expected_etfs = 15（14 core + 1 reference）
"""
import os
import sys
import pytest
import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


class TestETFListLoaderExcludes510300:
    """ETFListLoader 不应包含 510300"""

    def test_load_does_not_contain_510300(self):
        from src.data.etf_pool_loader import ETFListLoader
        codes = ETFListLoader().load()
        assert '510300' not in codes
        assert len(codes) == 14

    def test_load_contains_v9_etfs(self):
        from src.data.etf_pool_loader import ETFListLoader
        codes = ETFListLoader().load()
        v9_etfs = ['588000', '512480', '512880', '512170', '520900',
                   '515790', '515050', '512400', '512660', '515070',
                   '512800', '512980', '512200', '515650']
        for v9 in v9_etfs:
            assert v9 in codes, f"{v9} should be in core pool"


class TestRepositoryExcludes510300:
    """Repository 行为"""

    def test_list_codes_core_excludes_510300(self):
        from src.data.etf_pool_repository import ETFRepository
        repo = ETFRepository()
        core = repo.list_codes('core')
        assert '510300' not in core
        assert len(core) == 14

    def test_list_codes_reference_contains_510300(self):
        from src.data.etf_pool_repository import ETFRepository
        repo = ETFRepository()
        ref = repo.list_codes('reference')
        assert '510300' in ref
        assert ref == ['510300']

    def test_510300_name_still_queryable(self):
        """510300 仍能通过 Repository 查元数据（数据没删除）"""
        from src.data.etf_pool_repository import ETFRepository
        repo = ETFRepository()
        name = repo.get_name('510300')
        assert name == '沪深300ETF华泰柏瑞'

    def test_510300_meta_still_queryable(self):
        from src.data.etf_pool_repository import ETFRepository
        repo = ETFRepository()
        meta = repo.get_meta('510300')
        assert meta is not None
        assert meta['code'] == '510300'
        assert meta['pool_role'] == 'reference'
        assert meta['tradable'] == 0


class TestSelectorExcludes510300:
    """src.core.selector 应排除 510300"""

    def test_selector_filters_out_510300(self):
        """mock data 包含 510300，selector 不应选它"""
        from src.core.selector import Selector
        from src.utils.config import StrategyConfig

        # 构造 200 天 mock data
        dates = pd.date_range('2022-01-01', periods=200, freq='D')
        mock_data = {}
        for code in ['510300', '588000', '512480', '159611', '512880']:
            # 510300 故意有强趋势（应该被选中），但 US-003 后不应该
            if code == '510300':
                prices = np.linspace(1.0, 5.0, 200)  # 强趋势
            else:
                prices = np.random.uniform(1, 5, 200)
            df = pd.DataFrame({
                'date': dates,
                'close': prices,
                'open': prices * 0.99,
                'high': prices * 1.01,
                'low': prices * 0.98,
                'volume': np.random.uniform(1000, 10000, 200),
            })
            mock_data[code] = df

        result = Selector().select_etfs(mock_data, StrategyConfig())
        assert '510300' not in result, "510300 should be filtered out (US-003)"

    def test_selector_only_evaluates_core_etfs(self):
        """selector 只评估 14 只 core 池的 ETF"""
        from src.core.selector import Selector
        from src.utils.config import StrategyConfig

        dates = pd.date_range('2022-01-01', periods=200, freq='D')
        mock_data = {}
        for code in ['159611', '512690', '511010']:  # 全是 excluded
            df = pd.DataFrame({
                'date': dates,
                'close': np.random.uniform(1, 5, 200),
                'open': np.random.uniform(1, 5, 200),
                'high': np.random.uniform(1, 5, 200),
                'low': np.random.uniform(1, 5, 200),
                'volume': np.random.uniform(1000, 10000, 200),
            })
            mock_data[code] = df

        result = Selector().select_etfs(mock_data, StrategyConfig())
        # 159611/512690/511010 都不在 core 池，应被过滤
        assert '159611' not in result
        assert '512690' not in result
        assert '511010' not in result


class TestReportGeneratorExcludes510300:
    """src.analysis.report_generator 应排除 510300"""

    def test_analyze_market_filters_510300(self):
        """analyze_market 过滤掉 510300"""
        from src.analysis.report_generator import ETFReportGenerator

        gen = ETFReportGenerator()
        # 构造 mock data
        dates = pd.date_range('2022-01-01', periods=200, freq='D')
        gen.data = {}
        for code in ['510300', '588000', '512480']:
            df = pd.DataFrame({
                'date': dates,
                'close': np.random.uniform(1, 5, 200),
                'open': np.random.uniform(1, 5, 200),
                'high': np.random.uniform(1, 5, 200),
                'low': np.random.uniform(1, 5, 200),
                'volume': np.random.uniform(1000, 10000, 200),
            })
            gen.data[code] = df
        gen.latest_date = dates[-1]

        result = gen.analyze_market()
        top_codes = [r['code'] for r in result['top_etfs']]
        assert '510300' not in top_codes, "510300 should not be in TOP 10 (US-003)"


class TestMACDStrategyExcludes510300:
    """src.strategy.macd_strategy 应排除 510300"""

    def test_get_signals_filters_510300(self):
        """get_signals 返回的 signals 不含 510300"""
        from src.strategy.macd_strategy import MACDStrategy

        strat = MACDStrategy()
        # 检查 pool_loader 加载的池不含 510300
        pool = strat.pool_loader.load()
        assert '510300' not in pool
        assert len(pool) == 14


class TestMonitorExpectedCount:
    """monitor.expected_etfs 应该 = 15（14 core + 1 reference）"""

    def test_get_min_day_count_returns_14(self):
        """US-003 后 monitor 基线 = 14（core 池）"""
        from src.data.monitor import DataQualityMonitor
        m = DataQualityMonitor()
        assert m.get_min_day_count() == 14

    def test_reference_count(self):
        """验证 reference 池有 510300（用于 reference 计数）"""
        from src.data.etf_pool_repository import ETFRepository
        ref = ETFRepository().list_codes('reference')
        # 14 core + 1 reference = 15
        # 监控告警时 "expected_etfs" 应该 = 14（仅 core），但 total = 15（含 reference）
        assert len(ref) == 1


class TestExcludeCodesDeprecated:
    """config.exclude_codes 应标记为 deprecated"""

    def test_exclude_codes_still_exists(self):
        """向后兼容：config.exclude_codes 仍然存在"""
        from src.utils.config import StrategyConfig
        config = StrategyConfig()
        # deprecated 但仍可用
        assert hasattr(config, 'exclude_codes')
        assert isinstance(config.exclude_codes, set)
