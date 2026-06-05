#!/usr/bin/env python3
"""Group A: DEPRECATED 文件清理契约测试

US-021 / Group A 清理: 删除 3 个 .DEPRECATED 文件
- etf_data_live/etf_audit_log.json.DEPRECATED
- etf_data_live/etf_positions.json.DEPRECATED
- etf_data_live/etf_trades.json.DEPRECATED

调研: grep 0 引用, .DEPRECATED 标记为废弃, 安全删除
设计: docs/CLEANUP_PLAN_v1.md

TDD 流程: 红 → 绿
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────
# 契约: 3 个 DEPRECATED 文件应已被删除
# ─────────────────────────────────────────────────────────────

class TestGroupADeprecatedRemoved:
    """Group A: DEPRECATED 文件应已删除"""

    def test_audit_log_deprecated_removed(self):
        """etf_data_live/etf_audit_log.json.DEPRECATED 应已删除"""
        path = ROOT / 'etf_data_live' / 'etf_audit_log.json.DEPRECATED'
        assert not path.exists(), f"应删除 {path}"

    def test_positions_deprecated_removed(self):
        """etf_data_live/etf_positions.json.DEPRECATED 应已删除"""
        path = ROOT / 'etf_data_live' / 'etf_positions.json.DEPRECATED'
        assert not path.exists(), f"应删除 {path}"

    def test_trades_deprecated_removed(self):
        """etf_data_live/etf_trades.json.DEPRECATED 应已删除"""
        path = ROOT / 'etf_data_live' / 'etf_trades.json.DEPRECATED'
        assert not path.exists(), f"应删除 {path}"


# ─────────────────────────────────────────────────────────────
# 契约: 主本文件未受影响（US-016 真相源）
# ─────────────────────────────────────────────────────────────

class TestMainSourceIntact:
    """契约: DEPRECATED 删除后, 主本文件 (etf_data_live/etf.db) 必须保留

    诚实标记 (US-021 调研发现):
    - etf_data_live/etf_trades.json: 已迁移到 SQLite trade_history 表 (US-008)
    - etf_data_live/etf_positions.json: 已迁移到 SQLite + get_holdings() 重建 (US-015/016)
    - 这两个 JSON 文件已不存在, 但代码仍有引用 (TRADES_FILE 常量, performance_analyzer)
      → 这些是死代码, 不在本任务 scope, 留给 US-022 清理
    """

    def test_main_db_intact(self):
        """etf_data_live/etf.db (19MB 主 db) 应保留"""
        path = ROOT / 'etf_data_live' / 'etf.db'
        assert path.exists(), f"主 db 应保留 {path}"
        assert path.stat().st_size > 1_000_000, "主 db 应 > 1MB"

    def test_main_bak_intact(self):
        """etf_data_live/etf.db.bak (US-016 备份) 应保留"""
        path = ROOT / 'etf_data_live' / 'etf.db.bak'
        assert path.exists(), f"US-016 备份应保留到 2026-06-11"
