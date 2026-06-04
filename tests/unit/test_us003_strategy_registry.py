#!/usr/bin/env python3
"""US-003 单元测试: 策略注册中心"""
import os
import sys
import sqlite3
import tempfile
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def isolated_registry():
    """隔离 StrategyRegistry（临时 DB）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db = os.path.join(tmpdir, 'test.db')
        # 创建空 DB + 必需表
        conn = sqlite3.connect(tmp_db)
        conn.close()
        from src.strategy.registry import StrategyRegistry
        registry = StrategyRegistry(db_path=tmp_db)
        yield registry, tmp_db


class TestUS003StrategyRegistry:
    """US-003: 策略注册中心（注册/查询/退役）"""

    def test_register_strategy(self, isolated_registry):
        """注册策略 + 内存+DB 同步"""
        registry, _ = isolated_registry
        from src.strategy.registry import StrategyMeta
        meta = StrategyMeta(
            code='trend_following',
            name='趋势跟踪',
            applicable_regimes=['trend_up'],
            params={'ma_period': 60},
            risk_limits={'max_pos': 0.3, 'stop_loss': -0.08}
        )
        assert registry.register(meta)
        assert 'trend_following' in registry
        assert len(registry) == 1

    def test_get_active_filters_retired(self, isolated_registry):
        """退役策略不列入 active"""
        registry, _ = isolated_registry
        from src.strategy.registry import StrategyMeta
        m1 = StrategyMeta(code='s1', name='策略1')
        m2 = StrategyMeta(code='s2', name='策略2')
        registry.register(m1)
        registry.register(m2)
        registry.deregister('s1')
        active = registry.get_active()
        assert len(active) == 1
        assert active[0].code == 's2'

    def test_get_by_regime_filters_applicable(self, isolated_registry):
        """按市态筛 applicable 策略"""
        registry, _ = isolated_registry
        from src.strategy.registry import StrategyMeta
        m1 = StrategyMeta(code='trend_1', name='T1', applicable_regimes=['trend_up'])
        m2 = StrategyMeta(code='range_1', name='R1', applicable_regimes=['range_bound'])
        m3 = StrategyMeta(code='trend_2', name='T2', applicable_regimes=['trend_up', 'reversal_point'])
        registry.register(m1)
        registry.register(m2)
        registry.register(m3)
        trend = registry.get_by_regime('trend_up')
        codes = [m.code for m in trend]
        assert 'trend_1' in codes
        assert 'trend_2' in codes
        assert 'range_1' not in codes
        # reversal_point 应有 trend_2
        reversal = registry.get_by_regime('reversal_point')
        assert 'trend_2' in [m.code for m in reversal]

    def test_persistence_across_instances(self, isolated_registry):
        """持久化: 重新实例化能加载"""
        registry, tmp_db = isolated_registry
        from src.strategy.registry import StrategyMeta, StrategyRegistry
        meta = StrategyMeta(code='persist_test', name='持久化测试', params={'k': 'v'})
        registry.register(meta)
        # 重新实例化
        new_registry = StrategyRegistry(db_path=tmp_db)
        loaded = new_registry.get('persist_test')
        assert loaded is not None
        assert loaded.name == '持久化测试'
        assert loaded.params == {'k': 'v'}

    def test_deregister_returns_false_for_missing(self, isolated_registry):
        """deregister 不存在的 code 返回 False"""
        registry, _ = isolated_registry
        assert registry.deregister('nonexistent') is False

    def test_list_all_includes_retired(self, isolated_registry):
        """list_all 含退役策略"""
        registry, _ = isolated_registry
        from src.strategy.registry import StrategyMeta
        m1 = StrategyMeta(code='a', name='A')
        m2 = StrategyMeta(code='b', name='B')
        registry.register(m1)
        registry.register(m2)
        registry.deregister('a')
        all_strategies = registry.list_all()
        assert len(all_strategies) == 2  # 含退役
        active = registry.get_active()
        assert len(active) == 1
