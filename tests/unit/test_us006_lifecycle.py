#!/usr/bin/env python3
"""US-006 单元测试: 策略生命周期（Q4=月度评估）"""
import os
import sys
import sqlite3
import tempfile
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def isolated_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db = os.path.join(tmpdir, 'test.db')
        conn = sqlite3.connect(tmp_db)
        conn.close()
        from src.strategy.registry import StrategyRegistry
        from src.strategy.lifecycle import LifecycleManager
        reg = StrategyRegistry(db_path=tmp_db)
        # 注册 4 策略
        from src.strategy.registry import StrategyMeta
        for code in ['trend_following', 'mean_reversion', 'breakout', 'volume_divergence']:
            reg.register(StrategyMeta(
                code=code, name=code,
                applicable_regimes=['trend_up', 'range_bound', 'trend_up', 'reversal_point'],
                risk_limits={'max_pos': 0.3, 'stop_loss': -0.05, 'max_hold_days': 10},
            ))
        mgr = LifecycleManager(registry=reg)
        yield mgr, reg


def add_perf(mgr, code, sharpes):
    from src.strategy.lifecycle import PerformanceRecord
    for i, s in enumerate(sharpes):
        mgr.record_performance(PerformanceRecord(
            strategy_code=code, month=f'2024-{i+1:02d}',
            sharpe=s, total_return=0, trades=10,
        ))


class TestUS006Lifecycle:
    """US-006: 策略生命周期（月度评估 + 降权 + 退役）"""

    def test_active_strategy_unchanged(self, isolated_lifecycle):
        """健康策略保持 active"""
        mgr, reg = isolated_lifecycle
        add_perf(mgr, 'trend_following', [1.5, 1.2, 1.8])  # 3 月正收益
        result = mgr.evaluate()
        assert result['trend_following'] == 'active'

    def test_demote_after_3_negative_months(self, isolated_lifecycle):
        """连续 3 月负收益 → 降权"""
        mgr, reg = isolated_lifecycle
        add_perf(mgr, 'mean_reversion', [-0.5, -0.3, -0.8])  # 3 月负
        result = mgr.evaluate()
        assert result['mean_reversion'] == 'demoted'
        # 验证仓位降权
        meta = reg.get('mean_reversion')
        assert meta.risk_limits['max_pos'] == 0.15  # 0.3 * 0.5

    def test_retire_after_6_negative_months(self, isolated_lifecycle):
        """连续 6 月负收益 → 退役"""
        mgr, reg = isolated_lifecycle
        add_perf(mgr, 'breakout', [-0.5, -0.3, -0.8, -0.4, -0.2, -0.6])  # 6 月负
        result = mgr.evaluate()
        assert result['breakout'] == 'retired'
        # 退役后 active 不含
        active = reg.get_active()
        assert all(s.code != 'breakout' for s in active)

    def test_mixed_sharpe_keeps_active(self, isolated_lifecycle):
        """混合 Sharpe 保持 active（不连续负）"""
        mgr, reg = isolated_lifecycle
        add_perf(mgr, 'volume_divergence', [-0.5, 0.5, -0.8])  # 混合
        result = mgr.evaluate()
        assert result['volume_divergence'] == 'active'

    def test_insufficient_data_keeps_active(self, isolated_lifecycle):
        """数据不足时保持 active（保守）"""
        mgr, reg = isolated_lifecycle
        add_perf(mgr, 'trend_following', [-0.5, -0.3])  # 只 2 月
        result = mgr.evaluate()
        assert result['trend_following'] == 'active'

    def test_lifecycle_stats(self, isolated_lifecycle):
        """生命周期统计"""
        mgr, reg = isolated_lifecycle
        add_perf(mgr, 'breakout', [-0.5, -0.3, -0.8, -0.4, -0.2, -0.6])
        mgr.evaluate()
        stats = mgr.get_lifecycle_stats()
        assert stats['retired'] == 1
        assert stats['active'] == 3
        assert stats['total'] == 4
