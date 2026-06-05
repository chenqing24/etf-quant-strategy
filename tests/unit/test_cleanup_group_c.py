#!/usr/bin/env python3
"""Group C: Tracked-but-ignored 文件清理契约测试

US-021 / Group C 清理: 27 个 tracked 但 .gitignore 排除的文件
设计: docs/CLEANUP_PLAN_v1.md

策略: git rm --cached (从 git 索引删除, 保留本地)

诚实标记 (TDD 红发现):
- data/experiments/round2_fixed.json (14MB) 已被 git 跟踪
- 多个 .json/.txt/.pyc 是历史 commit 残留
- 这些都是运行时/历史数据, 不应在 git 中

TDD: 红 → 绿
"""
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────

def get_tracked_ignored():
    """获取所有 tracked 但被 .gitignore 排除的文件"""
    result = subprocess.run(
        ['git', 'ls-files', '-i', '-c', '--exclude-standard'],
        cwd=str(ROOT), capture_output=True, text=True
    )
    return [f for f in result.stdout.strip().split('\n') if f]


# ─────────────────────────────────────────────────────────────
# 契约: tracked-but-ignored 文件应已从 git 索引删除
# ─────────────────────────────────────────────────────────────

class TestGroupCTrackedIgnoredRemoved:
    """Group C: tracked-but-ignored 文件应从 git 索引删除"""

    def test_no_tracked_ignored_files(self):
        """git 跟踪中不应再有被 .gitignore 排除的文件"""
        tracked_ignored = get_tracked_ignored()
        assert len(tracked_ignored) == 0, \
            f"仍有 {len(tracked_ignored)} 个 tracked-but-ignored: {tracked_ignored[:5]}..."

    def test_coverage_not_tracked(self):
        """.coverage (测试覆盖率) 不应在 git 中"""
        result = subprocess.run(
            ['git', 'ls-files', '.coverage'],
            cwd=str(ROOT), capture_output=True, text=True
        )
        assert result.stdout.strip() == '', ".coverage 仍 tracked"

    def test_data_experiments_json_not_tracked(self):
        """data/experiments/*.json 不应在 git 中"""
        result = subprocess.run(
            ['git', 'ls-files', 'data/experiments/'],
            cwd=str(ROOT), capture_output=True, text=True
        )
        files = [f for f in result.stdout.strip().split('\n') if f]
        assert len(files) == 0, f"data/experiments/ 仍 tracked: {files}"

    def test_etf_data_live_json_not_tracked(self):
        """etf_data_live/*.json (运行时) 不应在 git 中"""
        result = subprocess.run(
            ['git', 'ls-files', 'etf_data_live/'],
            cwd=str(ROOT), capture_output=True, text=True
        )
        files = [f for f in result.stdout.strip().split('\n') if f.endswith('.json')]
        assert len(files) == 0, f"etf_data_live/*.json 仍 tracked: {files}"

    def test_etf_reports_txt_not_tracked(self):
        """etf_reports/*.txt (历史报告) 不应在 git 中"""
        result = subprocess.run(
            ['git', 'ls-files', 'etf_reports/'],
            cwd=str(ROOT), capture_output=True, text=True
        )
        files = [f for f in result.stdout.strip().split('\n') if f.endswith('.txt')]
        assert len(files) == 0, f"etf_reports/*.txt 仍 tracked: {files[:3]}..."

    def test_src_etf_data_live_json_not_tracked(self):
        """src/etf_data_live/*.json (废弃目录) 不应在 git 中"""
        result = subprocess.run(
            ['git', 'ls-files', 'src/etf_data_live/'],
            cwd=str(ROOT), capture_output=True, text=True
        )
        files = [f for f in result.stdout.strip().split('\n') if f.endswith('.json')]
        assert len(files) == 0, f"src/etf_data_live/ 仍 tracked: {files}"

    def test_src_pycache_not_tracked(self):
        """src/__pycache__/*.pyc 不应在 git 中"""
        result = subprocess.run(
            ['git', 'ls-files', 'src/__pycache__/'],
            cwd=str(ROOT), capture_output=True, text=True
        )
        assert result.stdout.strip() == '', "src/__pycache__ 仍 tracked"

    def test_etf_db_not_tracked(self):
        """顶层 etf.db (冷数据层) 不应在 git 中 (US-021 加 .gitignore)"""
        result = subprocess.run(
            ['git', 'ls-files', 'etf.db'],
            cwd=str(ROOT), capture_output=True, text=True
        )
        assert result.stdout.strip() == '', "etf.db 仍 tracked (应 .gitignore 排除)"

    def test_scripts_etf_data_live_db_not_tracked(self):
        """scripts/etf_data_live/etf.db (pre-existing) 不应在 git 中"""
        result = subprocess.run(
            ['git', 'ls-files', 'scripts/etf_data_live/etf.db'],
            cwd=str(ROOT), capture_output=True, text=True
        )
        assert result.stdout.strip() == '', \
            "scripts/etf_data_live/etf.db 仍 tracked (pre-existing 2.3MB)"


# ─────────────────────────────────────────────────────────────
# 契约: 本地文件保留 (--cached 不删本地)
# ─────────────────────────────────────────────────────────────

class TestLocalFilesPreserved:
    """Group C: 本地文件应保留 (git rm --cached 不删本地)"""

    def test_local_experiments_json_preserved(self):
        """本地 data/experiments/round2_fixed.json 应保留 (新基线)"""
        path = ROOT / 'data' / 'experiments' / 'round2_fixed.json'
        assert path.exists(), f"本地新基线应保留 {path}"

    def test_local_reports_preserved(self):
        """本地 etf_reports/*.txt 应保留"""
        report_path = ROOT / 'etf_reports' / 'report_20260605.txt'
        assert report_path.exists(), f"今日报告应保留 {report_path}"

    def test_local_data_live_performance_preserved(self):
        """本地 etf_data_live/etf_performance.json 应保留 (active)"""
        path = ROOT / 'etf_data_live' / 'etf_performance.json'
        assert path.exists(), f"active 性能文件应保留 {path}"
