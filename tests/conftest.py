#!/usr/bin/env python3
"""
US-014: 全局测试 fixture - 自动加载所有 schema migrations

教训：US-014 R2 加了 005 migration（is_reference 列），但
test_us005/007/008/009/010/012/013 的 fixture 只加载 004，导致
47 个回归失败。

本 fixture 解决：自动加载 schema/migrations/ 下所有 .sql，
新 migration 加进来无需改测试。

用法（fixture 自动注入）：
- isolated_db: 临时 DB + 所有 schema 已应用
"""
import os
import sys
import glob
import sqlite3
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

MIGRATIONS_DIR = ROOT / 'schema' / 'migrations'


@pytest.fixture
def isolated_db():
    """
    隔离 SQLite DB（自动加载所有 migrations）

    Yields:
        (db_path, conn) - 临时 DB 路径和连接
    """
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_db = os.path.join(tmpdir, 'test.db')
        conn = sqlite3.connect(tmp_db)
        # 创建基础表（001/002 migrations 引用 daily，需先建）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily (
                code TEXT, date TEXT, open REAL, high REAL, low REAL,
                close REAL, volume INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS etf_names (
                code TEXT PRIMARY KEY, name TEXT, full_name TEXT, sector TEXT,
                updated_at TEXT
            )
        """)
        conn.commit()
        # 按顺序应用所有 migration（按文件名，排除 README.md）
        # 跳过 001/002（依赖 daily 全字段结构，测试用最小 daily）
        migrations = sorted(glob.glob(str(MIGRATIONS_DIR / '[0-9]*.sql')))
        for mig in migrations:
            fname = os.path.basename(mig)
            if fname.startswith('001_') or fname.startswith('002_'):
                continue  # 测试场景不需要 daily 全部列
            with open(mig) as f:
                conn.executescript(f.read())
        conn.commit()
        # realtime_cache 表（PositionGuide 依赖）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS realtime_cache (
                code TEXT PRIMARY KEY,
                price REAL, change_pct REAL, source TEXT, updated_at TEXT
            )
        """)
        conn.commit()
        yield tmp_db, conn
        conn.close()


@pytest.fixture
def isolated_tracker(isolated_db):
    """
    隔离 TradeTracker（基于 isolated_db）

    Yields:
        (tracker, tmpdir, tmp_db) - TradeTracker 实例
    """
    tmp_db, _ = isolated_db
    import tempfile
    tmpdir = os.path.dirname(tmp_db)
    # performance.json
    import json
    with open(os.path.join(tmpdir, 'etf_performance.json'), 'w') as f:
        json.dump({
            'trades': [], 'positions': [],
            'performance': {
                'initial_capital': 20000, 'current_capital': 20000,
                'total_pnl': 0, 'total_trades': 0, 'win_rate': 0
            }
        }, f)
    from src.trade.tracker import TradeTracker
    tracker = TradeTracker(data_dir=tmpdir, db_path=tmp_db)
    yield tracker, tmpdir, tmp_db
