#!/usr/bin/env python3
"""
US-001 单元测试：ETFRepository

覆盖：
- list_codes / list_with_meta / all_codes
- get_name / get_meta
- upsert_name
- US-001 阶段 role 字段未加，行为应保持兼容
"""
import os
import sys
import pytest
import sqlite3
import tempfile
from pathlib import Path

# 让 etf_strategy 可被 import
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.data.etf_pool_repository import ETFRepository


@pytest.fixture
def tmp_db():
    """创建临时 etf.db fixture"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    # 初始化 etf_names 表
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE etf_names (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            name_sina TEXT,
            verified INTEGER DEFAULT 0,
            verify_count INTEGER DEFAULT 0,
            last_verify_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            exchange TEXT,
            category TEXT,
            tracking_index TEXT,
            aum REAL
        );
    """)
    # 插入 3 条测试数据
    test_data = [
        ('510300', '沪深300ETF华泰柏瑞', 'SH', 91062487700.0),
        ('512480', '512480', 'SH', 5000000000.0),
        ('159611', '159611', 'SZ', 1000000000.0),
    ]
    conn.executemany(
        "INSERT INTO etf_names (code, name, exchange, aum) VALUES (?, ?, ?, ?)",
        test_data
    )
    conn.commit()
    conn.close()
    yield db_path
    os.unlink(db_path)


class TestETFRepositoryListCodes:
    """list_codes 系列测试"""

    def test_list_codes_returns_all_when_no_role_field(self, tmp_db):
        """US-001 阶段：role 字段未加，返回全部"""
        repo = ETFRepository(db_path=tmp_db)
        codes = repo.list_codes(role='core')
        assert len(codes) == 3
        assert '510300' in codes
        assert '512480' in codes
        assert '159611' in codes

    def test_list_codes_dedup_no_duplicates(self, tmp_db):
        """list_codes 不应返回重复"""
        repo = ETFRepository(db_path=tmp_db)
        codes = repo.list_codes(role='core')
        assert len(codes) == len(set(codes))

    def test_list_with_meta_returns_dicts(self, tmp_db):
        """list_with_meta 返回 dict 列表（不依赖顺序）"""
        repo = ETFRepository(db_path=tmp_db)
        result = repo.list_with_meta(role='core')
        assert len(result) == 3
        # 检查所有需要的字段
        for r in result:
            assert 'code' in r
            assert 'name' in r
            assert 'exchange' in r
            assert 'aum' in r
        # 检查 510300 在结果中
        r510300 = next(r for r in result if r['code'] == '510300')
        assert r510300['name'] == '沪深300ETF华泰柏瑞'
        assert r510300['exchange'] == 'SH'
        assert r510300['aum'] == 91062487700.0

    def test_all_codes_returns_full_list(self, tmp_db):
        """all_codes 不分角色，返回全部"""
        repo = ETFRepository(db_path=tmp_db)
        codes = repo.all_codes()
        assert len(codes) == 3


class TestETFRepositoryMetadata:
    """get_name / get_meta 测试"""

    def test_get_name_known_code(self, tmp_db):
        """已知 code 查 name"""
        repo = ETFRepository(db_path=tmp_db)
        assert repo.get_name('510300') == '沪深300ETF华泰柏瑞'
        assert repo.get_name('512480') == '512480'

    def test_get_name_unknown_code_returns_none(self, tmp_db):
        """未知 code 返回 None"""
        repo = ETFRepository(db_path=tmp_db)
        assert repo.get_name('999999') is None

    def test_get_meta_known_code(self, tmp_db):
        """已知 code 查 meta"""
        repo = ETFRepository(db_path=tmp_db)
        meta = repo.get_meta('510300')
        assert meta is not None
        assert meta['code'] == '510300'
        assert meta['name'] == '沪深300ETF华泰柏瑞'
        assert meta['exchange'] == 'SH'
        assert meta['aum'] == 91062487700.0
        assert meta['category'] is None  # US-001 阶段未填

    def test_get_meta_unknown_code_returns_none(self, tmp_db):
        """未知 code 返回 None"""
        repo = ETFRepository(db_path=tmp_db)
        assert repo.get_meta('999999') is None


class TestETFRepositoryUpsert:
    """upsert_name 测试"""

    def test_upsert_insert_new(self, tmp_db):
        """插入新 ETF"""
        repo = ETFRepository(db_path=tmp_db)
        ok = repo.upsert_name('515790', '智能制造ETF华夏', exchange='SH', aum=2000000000.0)
        assert ok is True
        assert repo.get_name('515790') == '智能制造ETF华夏'
        meta = repo.get_meta('515790')
        assert meta['exchange'] == 'SH'
        assert meta['aum'] == 2000000000.0

    def test_upsert_update_existing(self, tmp_db):
        """更新已有 ETF"""
        repo = ETFRepository(db_path=tmp_db)
        # 510300 已有
        ok = repo.upsert_name('510300', '沪深300ETF(新名)', aum=999999.0)
        assert ok is True
        assert repo.get_name('510300') == '沪深300ETF(新名)'
        meta = repo.get_meta('510300')
        assert meta['aum'] == 999999.0

    def test_upsert_ignores_invalid_kwargs(self, tmp_db):
        """upsert 忽略不在白名单的 kwargs"""
        repo = ETFRepository(db_path=tmp_db)
        ok = repo.upsert_name('515790', '测试', invalid_field='bad')
        assert ok is True  # 不报错
        assert repo.get_name('515790') == '测试'

    def test_upsert_only_name(self, tmp_db):
        """upsert 只传 name"""
        repo = ETFRepository(db_path=tmp_db)
        ok = repo.upsert_name('515790', '测试名')
        assert ok is True
        assert repo.get_name('515790') == '测试名'


class TestETFRepositoryWithTradableField:
    """US-002 之后：当 etf_names 加了 tradable/pool_role 字段"""

    @pytest.fixture
    def tmp_db_with_tradable(self, tmp_db):
        """加了 tradable / pool_role 字段的 db"""
        conn = sqlite3.connect(tmp_db)
        conn.executescript("""
            ALTER TABLE etf_names ADD COLUMN tradable INTEGER DEFAULT 1;
            ALTER TABLE etf_names ADD COLUMN pool_role TEXT DEFAULT 'core';
        """)
        # 510300 标为 reference
        conn.execute(
            "UPDATE etf_names SET tradable=0, pool_role='reference' WHERE code='510300'"
        )
        # 159611 标为 excluded
        conn.execute(
            "UPDATE etf_names SET tradable=0, pool_role='excluded' WHERE code='159611'"
        )
        conn.commit()
        conn.close()
        return tmp_db

    def test_list_codes_filters_by_role(self, tmp_db_with_tradable):
        """role='core' 只返回 tradable=1 AND pool_role=core"""
        repo = ETFRepository(db_path=tmp_db_with_tradable)
        # 重置 columns cache（fixture 新建了 db）
        if hasattr(repo, '_columns_cache'):
            delattr(repo, '_columns_cache')
        codes = repo.list_codes(role='core')
        assert '512480' in codes  # tradable=1, core
        assert '510300' not in codes  # reference
        assert '159611' not in codes  # excluded
        assert len(codes) == 1

    def test_list_codes_returns_excluded(self, tmp_db_with_tradable):
        """role='excluded' 只返回 159611"""
        repo = ETFRepository(db_path=tmp_db_with_tradable)
        if hasattr(repo, '_columns_cache'):
            delattr(repo, '_columns_cache')
        codes = repo.list_codes(role='excluded')
        assert '159611' in codes
        assert '510300' not in codes
        assert '512480' not in codes
        assert len(codes) == 1

    def test_list_codes_returns_reference(self, tmp_db_with_tradable):
        """role='reference' 只返回 510300"""
        repo = ETFRepository(db_path=tmp_db_with_tradable)
        if hasattr(repo, '_columns_cache'):
            delattr(repo, '_columns_cache')
        codes = repo.list_codes(role='reference')
        assert '510300' in codes
        assert '159611' not in codes
        assert '512480' not in codes
        assert len(codes) == 1
