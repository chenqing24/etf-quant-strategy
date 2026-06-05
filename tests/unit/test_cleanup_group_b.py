#!/usr/bin/env python3
"""Group B: 顶层重复文件清理契约测试

US-021 / Group B 清理: 6 个顶层重复文件
1. etf_quant_decision_skill.md  - 0 引用, 被 skills/etf-quant-decision/SKILL.md v2.0 替代
2. analyze_v8_sop.py             - 顶层简化版, scripts/experiment/analyze_v8_sop.py 完整版
3. etf_performance.json          - 与 etf_data_live/etf_performance.json 重复
4. etf_positions.json            - 孤立（etf_data_live/ 已迁 SQLite, US-015/016）
5. etf_trades.json               - 孤立（同上, US-008）
6. etf.db                        - 顶层 28KB 旧 db, etf_data_live/etf.db 19MB 主 db

设计: docs/CLEANUP_PLAN_v1.md
TDD: 红 → 绿
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────
# 契约: 6 个顶层重复文件应已删除
# ─────────────────────────────────────────────────────────────

class TestGroupBTopLevelCleaned:
    """Group B: 顶层 6 个重复文件应已删除"""

    def test_etf_quant_decision_skill_md_removed(self):
        """顶层 etf_quant_decision_skill.md 应已删除 (被 skills/ 替代)"""
        path = ROOT / 'etf_quant_decision_skill.md'
        assert not path.exists(), f"应删除 {path}"

    def test_analyze_v8_sop_py_removed(self):
        """顶层 analyze_v8_sop.py 应已删除 (scripts/experiment/ 完整版)"""
        path = ROOT / 'analyze_v8_sop.py'
        assert not path.exists(), f"应删除 {path}"

    def test_etf_performance_json_removed(self):
        """顶层 etf_performance.json 应已删除 (etf_data_live/ 重复)"""
        path = ROOT / 'etf_performance.json'
        assert not path.exists(), f"应删除 {path}"

    def test_etf_positions_json_removed(self):
        """顶层 etf_positions.json 应已删除 (已迁 SQLite)"""
        path = ROOT / 'etf_positions.json'
        assert not path.exists(), f"应删除 {path}"

    def test_etf_trades_json_removed(self):
        """顶层 etf_trades.json 应已删除 (已迁 SQLite)"""
        path = ROOT / 'etf_trades.json'
        assert not path.exists(), f"应删除 {path}"

    def test_top_level_etf_db_removed(self):
        """顶层 etf.db (28KB) 应已删除 (etf_data_live/etf.db 19MB 主 db)"""
        path = ROOT / 'etf.db'
        assert not path.exists(), f"应删除 {path}"


# ─────────────────────────────────────────────────────────────
# 契约: 主本文件保留
# ─────────────────────────────────────────────────────────────

class TestMainSourceIntact:
    """契约: Group B 清理后, 主本文件必须保留"""

    def test_skill_md_intact(self):
        """skills/etf-quant-decision/SKILL.md v2.0 应保留 (顶层删的是旧版)"""
        # SKILL.md 在工作区根目录的 skills/ 下, 不在 etf_strategy/
        skill_path = ROOT.parent / 'skills' / 'etf-quant-decision' / 'SKILL.md'
        assert skill_path.exists(), f"主 skill 应保留 {skill_path}"
        # v2.0 标记
        content = skill_path.read_text()
        assert 'builtin_skill_version: "2.0"' in content, "应保留 v2.0"

    def test_analyze_v8_sop_main_intact(self):
        """scripts/experiment/analyze_v8_sop.py (完整版) 应保留"""
        path = ROOT / 'scripts' / 'experiment' / 'analyze_v8_sop.py'
        assert path.exists(), f"完整版应保留 {path}"
        # 完整版有 shebang 和 docstring
        content = path.read_text()
        assert content.startswith('#!/usr/bin/env python3'), "完整版应含 shebang"
        assert '"""' in content, "完整版应含 docstring"

    def test_etf_data_live_performance_intact(self):
        """etf_data_live/etf_performance.json 应保留 (active)"""
        path = ROOT / 'etf_data_live' / 'etf_performance.json'
        assert path.exists(), f"主本应保留 {path}"

    def test_main_db_intact(self):
        """etf_data_live/etf.db 19MB 主 db 应保留"""
        path = ROOT / 'etf_data_live' / 'etf.db'
        assert path.exists(), f"主 db 应保留 {path}"
        assert path.stat().st_size > 1_000_000, "主 db 应 > 1MB"


# ─────────────────────────────────────────────────────────────
# 契约: 主动配置文件 etf_pool.json 不删
# ─────────────────────────────────────────────────────────────

class TestActiveConfigIntact:
    """契约: etf_pool.json 顶层是 active 配置文件, 不删"""

    def test_etf_pool_json_intact(self):
        """etf_pool.json 顶层 (active 配置) 应保留"""
        path = ROOT / 'etf_pool.json'
        assert path.exists(), f"active 配置应保留 {path}"
        # 验证是 JSON
        import json
        with open(path) as f:
            data = json.load(f)
        assert 'etfs' in data, "应是 ETF 池配置"
        assert len(data['etfs']) > 0, "ETF 列表非空"
