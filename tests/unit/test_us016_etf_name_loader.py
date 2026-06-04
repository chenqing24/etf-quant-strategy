#!/usr/bin/env python3
"""US-016 单元测试: ETFNameLoader.get_name() 修复重复显示 bug

根因: 原实现只查 stock_info，515070 不在表里就 fallback 到 name=code
      导致报告"目标"字段显示 "515070 515070" (重复)

修复: 优先查 etf_names (1486 条全市场 ETF)，fallback stock_info
"""
import os
import sys
import sqlite3
import tempfile
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def isolated_db():
    """隔离 DB，etf_names 有数据，stock_info 无"""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'etf.db')
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE etf_names (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE TABLE stock_info (
            code TEXT PRIMARY KEY,
            name TEXT
        );
    """)
    # etf_names: 1486 条 (515070 在里面)
    conn.execute("INSERT INTO etf_names VALUES ('515070', '人工智能ETF华夏')")
    conn.execute("INSERT INTO etf_names VALUES ('512480', '国联安半导体ETF')")
    # stock_info: 只有 510300 (历史遗留)
    conn.execute("INSERT INTO stock_info VALUES ('510300', '沪深300ETF华泰柏瑞')")
    conn.commit()
    conn.close()
    yield db_path
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


class TestUS016GetNameFix:
    """US-016: get_name() 必须返回真实名称, 不能再 fallback 到 code"""

    def test_get_name_from_etf_names(self, isolated_db):
        """515070 在 etf_names, 返回真实名称"""
        from src.data.loader import ETFNameLoader
        loader = ETFNameLoader(db_path=isolated_db)
        name = loader.get_name('515070')
        assert name == '人工智能ETF华夏', f"expected '人工智能ETF华夏', got '{name}'"
        # 关键断言: 不再是 code 本身
        assert name != '515070', f"name should not equal code"

    def test_get_name_fallback_to_stock_info(self, isolated_db):
        """510300 在 stock_info, 返回 stock_info 名称"""
        from src.data.loader import ETFNameLoader
        loader = ETFNameLoader(db_path=isolated_db)
        name = loader.get_name('510300')
        assert name == '沪深300ETF华泰柏瑞', f"got '{name}'"

    def test_get_name_ultimate_fallback(self, isolated_db):
        """未知 code, fallback 到 code 本身 (终极 fallback)"""
        from src.data.loader import ETFNameLoader
        loader = ETFNameLoader(db_path=isolated_db)
        name = loader.get_name('999999')
        assert name == '999999', f"ultimate fallback should return code, got '{name}'"

    def test_get_name_cache_works(self, isolated_db):
        """缓存工作正常"""
        from src.data.loader import ETFNameLoader
        loader = ETFNameLoader(db_path=isolated_db)
        # 第一次从 DB
        name1 = loader.get_name('515070')
        # 第二次从 cache
        name2 = loader.get_name('515070')
        assert name1 == name2 == '人工智能ETF华夏'


class TestUS016ReportTargetNoDuplication:
    """US-016: 报告"目标"字段不能重复 code"""

    def test_target_field_format_no_duplicate_code(self, isolated_db):
        """报告"目标"字段格式: {code} {name}, name 必须 != code

        这是回归测试: US-016 之前报告里显示 "515070 515070"
        修复后: 应该显示 "515070 人工智能ETF华夏"
        """
        from src.data.loader import ETFNameLoader
        loader = ETFNameLoader(db_path=isolated_db)

        # 模拟报告生成
        codes_to_test = ['515070', '512480', '510300']
        for code in codes_to_test:
            name = loader.get_name(code)
            target_field = f"{code} {name}"
            # 关键: 不能是 "code code"
            assert f"{code} {code}" != target_field, \
                f"目标字段重复: '{target_field}' (US-016 修复未生效)"
