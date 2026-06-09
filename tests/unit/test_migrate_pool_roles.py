#!/usr/bin/env python3
"""
US-002 单元测试：migrate_pool_roles 迁移脚本

覆盖：
- 备份是否创建
- ALTER TABLE 成功（列存在）
- 14 core 标注正确
- 510300 标 reference
- ~22 excluded 标注
- 1449 unclassified 保持默认
- 幂等性：第二次执行不报错
- 验证 Repository 自动适配
"""
import os
import sys
import shutil
import sqlite3
import subprocess
import tempfile
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / 'etf_data_live' / 'etf.db'


@pytest.fixture
def backup_etf_db():
    """备份 etf.db，测试后恢复（保证幂等性测试可重复）"""
    if not DB_PATH.exists():
        pytest.skip("etf.db 不存在，跳过迁移测试")
    # 备份到临时文件
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        backup_path = f.name
    shutil.copy2(DB_PATH, backup_path)
    yield backup_path
    # 恢复
    shutil.copy2(backup_path, DB_PATH)
    os.unlink(backup_path)


def test_migration_creates_columns(backup_etf_db):
    """迁移后 etf_names 应该有 tradable + pool_role 字段"""
    result = subprocess.run(
        [sys.executable, 'scripts/migrate_pool_roles.py'],
        cwd=ROOT,
        capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, f"Migration failed: {result.stderr}"

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(etf_names)")
        cols = {row[1] for row in cur.fetchall()}
        assert 'tradable' in cols
        assert 'pool_role' in cols
    finally:
        conn.close()


def test_migration_labels_14_core(backup_etf_db):
    """迁移后应该有 16 只 core（US-002:14 → US-085:15 → US-095:16）
    US-095: +515050 通信ETF华夏（误标"养老产业ETF"已修正）
    """
    subprocess.run(
        [sys.executable, 'scripts/migrate_pool_roles.py'],
        cwd=ROOT, capture_output=True, text=True, timeout=30
    )

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM etf_names WHERE pool_role = 'core' AND tradable = 1")
        assert cur.fetchone()[0] == 16  # US-095: 14→15→16
    finally:
        conn.close()


def test_migration_labels_510300_as_reference(backup_etf_db):
    """迁移后 510300 应该是 reference"""
    subprocess.run(
        [sys.executable, 'scripts/migrate_pool_roles.py'],
        cwd=ROOT, capture_output=True, text=True, timeout=30
    )

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("SELECT pool_role, tradable FROM etf_names WHERE code = '510300'")
        row = cur.fetchone()
        assert row is not None
        assert row[0] == 'reference'
        assert row[1] == 0
    finally:
        conn.close()


def test_migration_labels_excluded(backup_etf_db):
    """迁移后应该有 12 只 excluded（US-002 13 - US-095 移除 515050 = 12）
    移除原因: 515050 不是"养老产业ETF"而是"通信ETF华夏"（fundgz验证）
    """
    subprocess.run(
        [sys.executable, 'scripts/migrate_pool_roles.py'],
        cwd=ROOT, capture_output=True, text=True, timeout=30
    )

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM etf_names WHERE pool_role = 'excluded'")
        cnt = cur.fetchone()[0]
        assert cnt == 12, f"expected 12 excluded (US-095), got {cnt}"
    finally:
        conn.close()


def test_migration_unclassified_count(backup_etf_db):
    """未显式标注的应该保持 untracked（US-002 改名为 untracked）"""
    subprocess.run(
        [sys.executable, 'scripts/migrate_pool_roles.py'],
        cwd=ROOT, capture_output=True, text=True, timeout=30
    )

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM etf_names WHERE pool_role = 'untracked'")
        cnt = cur.fetchone()[0]
        # US-002 后: 16 core + 1 ref + 12 excluded + 39 legacy_holding + untracked = 1486
        cur.execute("SELECT COUNT(*) FROM etf_names")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM etf_names WHERE pool_role IN ('core', 'reference', 'excluded', 'legacy_holding')")
        categorized = cur.fetchone()[0]
        assert cnt == total - categorized
    finally:
        conn.close()


def test_migration_idempotent(backup_etf_db):
    """第二次执行迁移不报错（幂等性）"""
    r1 = subprocess.run(
        [sys.executable, 'scripts/migrate_pool_roles.py'],
        cwd=ROOT, capture_output=True, text=True, timeout=30
    )
    assert r1.returncode == 0

    # 第二次执行
    r2 = subprocess.run(
        [sys.executable, 'scripts/migrate_pool_roles.py'],
        cwd=ROOT, capture_output=True, text=True, timeout=30
    )
    assert r2.returncode == 0, f"Second run failed: {r2.stderr}"
    assert '跳过 ALTER' in r2.stdout, "应该提示列已存在"


def test_repository_after_migration(backup_etf_db):
    """迁移后 Repository 行为正确（US-095: core=16, excluded=12）"""
    subprocess.run(
        [sys.executable, 'scripts/migrate_pool_roles.py'],
        cwd=ROOT, capture_output=True, text=True, timeout=30
    )

    from src.data.etf_pool_repository import ETFRepository
    repo = ETFRepository()

    # 1. core = 16 (US-002:14 → US-085:15 → US-095:16)
    core = repo.list_codes('core')
    assert len(core) == 16
    assert '588000' in core
    assert '515050' in core  # US-095: 通信ETF华夏
    assert '510300' not in core  # 510300 在 reference

    # 2. reference = ['510300']
    ref = repo.list_codes('reference')
    assert ref == ['510300']

    # 3. excluded = 12 (US-002:13 → US-095:12)
    exc = repo.list_codes('excluded')
    assert len(exc) == 12

    # 4. all = 1486
    assert len(repo.all_codes()) == 1486
