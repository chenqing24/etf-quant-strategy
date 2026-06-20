#!/usr/bin/env python3
"""
US-002 + SOP-13 回归测试：300ETF 永不进 trade 候选

覆盖：
1. CORE 池大小 = 14（动态池 - 510300）
2. 510300 / 159919 不在 CORE
3. ETFListLoader.load() 也不含 300ETF
4. REFERENCE 池含所有 40 只沪深300
5. CORE 池跟 top500_target_pool.txt 一致
"""
import os
import sys
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.data.etf_pool_repository import ETFRepository
from src.data.etf_pool_loader import ETFListLoader

DB_PATH = ROOT / 'etf_data_live' / 'etf.db'
POOL_FILE = ROOT / 'etf_data_live' / 'top500_target_pool.txt'

# 40 只沪深300 ETF（部分）
CSI300_CODES = [
    '510300', '510310', '510330', '510350', '510360', '510370',
    '510380', '510390', '159919', '159925', '512530', '515130',
    '515310', '515330', '515350', '515360', '515380', '515390',
    '515660', '516830', '560180', '560330', '561000', '561300',
    '561900', '561930', '561990', '562070', '562310', '562320',
    '563520', '159238', '159300', '159330', '159393', '159510',
    '159523', '159656', '159673', '510320',
]


@pytest.fixture
def repo():
    """真实 DB 的 ETFRepository fixture（需要 migration 已跑）"""
    if not DB_PATH.exists():
        pytest.skip(f'etf.db 不存在: {DB_PATH}')
    return ETFRepository(str(DB_PATH))


class TestCorePool:
    """CORE 池验证"""

    def test_core_pool_size_is_14(self, repo):
        """CORE 池大小 = 14（动态池 15 - 510300）"""
        codes = repo.list_codes('core')
        assert len(codes) == 14, f'CORE 池期望 14 只，实际 {len(codes)}: {codes}'

    def test_csi300_excluded_from_core(self, repo):
        """所有沪深300 ETF 都不在 CORE 池"""
        core = set(repo.list_codes('core'))
        for code in CSI300_CODES:
            assert code not in core, f'{code} 不应在 CORE 池'

    def test_510300_and_159919_in_reference(self, repo):
        """510300 / 159919 必须在 REFERENCE 池（不删数据）"""
        ref = set(repo.list_codes('reference'))
        assert '510300' in ref
        assert '159919' in ref

    def test_core_pool_matches_dynamic_pool(self, repo):
        """CORE 池应该 = 动态池（top500_target_pool.txt - 510300）"""
        core = set(repo.list_codes('core'))

        # 解析 top500_target_pool.txt
        import re
        content = POOL_FILE.read_text(encoding='utf-8')
        # 匹配 'XXXXXX' 格式的代码
        dynamic = set(re.findall(r"'(\d{6})'", content))
        # 去掉 510300
        dynamic.discard('510300')

        assert core == dynamic, f'CORE 池与动态池不一致\nCORE: {sorted(core)}\n动态: {sorted(dynamic)}'


class TestETFListLoader:
    """ETFListLoader 验证（兼容层）"""

    def test_loader_returns_no_300etf(self):
        """ETFListLoader.load() 不应含任何 300ETF"""
        if not DB_PATH.exists():
            pytest.skip(f'etf.db 不存在: {DB_PATH}')
        loader = ETFListLoader()
        codes = loader.load()
        for code in CSI300_CODES:
            assert code not in codes, f'{code} 不应在 ETFListLoader.load() 返回中'

    def test_loader_returns_14_codes(self):
        """ETFListLoader.load() 应返回 14 只（与 CORE 池一致）"""
        if not DB_PATH.exists():
            pytest.skip(f'etf.db 不存在: {DB_PATH}')
        loader = ETFListLoader()
        codes = loader.load()
        assert len(codes) == 14, f'ETFListLoader 期望 14 只，实际 {len(codes)}: {codes}'


class TestReferencePool:
    """REFERENCE 池验证（数据保留）"""

    def test_reference_contains_all_csi300(self, repo):
        """REFERENCE 池必须含全部 40 只沪深300"""
        ref = set(repo.list_codes('reference'))
        for code in CSI300_CODES:
            assert code in ref, f'{code} 缺失于 REFERENCE 池'

    def test_reference_count_at_least_40(self, repo):
        """REFERENCE 池大小 ≥ 40"""
        codes = repo.list_codes('reference')
        assert len(codes) >= 40, f'REFERENCE 池期望 ≥ 40，实际 {len(codes)}'


class TestExcludedPool:
    """EXCLUDED 池验证"""

    def test_510300_510310_not_in_core(self, repo):
        """主指 510300 和 510310 都不在 CORE（兜底排除）"""
        core = set(repo.list_codes('core'))
        assert '510300' not in core
        assert '510310' not in core

    def test_excluded_not_in_core(self, repo):
        """EXCLUDED 池与 CORE 池不重叠"""
        core = set(repo.list_codes('core'))
        excluded = set(repo.list_codes('excluded'))
        overlap = core & excluded
        assert len(overlap) == 0, f'CORE 与 EXCLUDED 重叠: {overlap}'
