#!/usr/bin/env python3
"""
ETF名称获取单元测试

测试 _fetch_name_from_api() 和数据库操作
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.data.fetcher import _fetch_name_from_api, _get_prefix
from src.data.database import Database


class TestGetPrefix:
    """测试 _get_prefix() 函数"""
    
    def test_shanghai_codes(self):
        """上海交易所代码"""
        assert _get_prefix('510300') == 'sh'
        assert _get_prefix('510500') == 'sh'
        assert _get_prefix('512880') == 'sh'
        assert _get_prefix('515050') == 'sh'
        assert _get_prefix('588000') == 'sh'
    
    def test_shenzhen_codes(self):
        """深圳交易所代码"""
        assert _get_prefix('159577') == 'sz'
        assert _get_prefix('159915') == 'sz'
        assert _get_prefix('159920') == 'sz'


class TestFetchNameFromApi:
    """测试 _fetch_name_from_api() 函数"""
    
    def test_fetch_name_success(self):
        """API正常返回"""
        name = _fetch_name_from_api('159577')
        assert name is not None
        assert len(name) > 0
        assert 'ETF' in name or 'ETF' in name  # 确认是ETF名称
        print(f"159577 名称: {name}")
    
    def test_fetch_name_standard(self):
        """测试标准ETF"""
        name = _fetch_name_from_api('510300')
        assert name is not None
        assert len(name) > 0
        print(f"510300 名称: {name}")
    
    def test_fetch_name_invalid(self):
        """无效代码"""
        name = _fetch_name_from_api('000000')
        # 无效代码可能返回 None 或 空字符串
        assert name is None or name == ''


class TestDatabaseMethods:
    """测试数据库ETF名称相关方法"""
    
    @pytest.fixture
    def db(self):
        """创建测试数据库"""
        test_db_path = 'data/test_etf_names.db'
        # 删除旧测试数据库
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
        return Database(test_db_path)
    
    def test_migrate_schema(self, db):
        """测试表结构扩展"""
        db.migrate_schema()
        # 验证字段存在（通过尝试查询）
        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(stock_info)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        
        assert 'etf_type' in columns, "etf_type 字段应存在"
        assert 'name_updated_at' in columns, "name_updated_at 字段应存在"
    
    def test_update_and_get_name(self, db):
        """测试更新和获取名称"""
        code = 'test_159577'
        name = '测试ETF名称'
        
        # 更新
        result = db.update_etf_name(code, name)
        assert result == True
        
        # 获取
        retrieved = db.get_etf_name(code)
        assert retrieved == name
    
    def test_update_overwrites(self, db):
        """测试更新会覆盖旧名称"""
        code = 'test_159577'
        
        # 第一次写入
        db.update_etf_name(code, '旧名称')
        
        # 第二次写入
        db.update_etf_name(code, '新名称')
        
        # 验证
        retrieved = db.get_etf_name(code)
        assert retrieved == '新名称'
    
    def test_get_nonexistent(self, db):
        """获取不存在的ETF"""
        name = db.get_etf_name('nonexistent_999')
        assert name is None
    
    def test_get_all_etf_names(self, db):
        """测试获取所有名称"""
        # 写入测试数据
        db.update_etf_name('test_001', '测试ETF1')
        db.update_etf_name('test_002', '测试ETF2')
        db.update_etf_name('test_003', 'ETF_default')  # 这个不应被返回
        
        names = db.get_all_etf_names()
        assert 'test_001' in names
        assert 'test_002' in names
        # ETF_default 格式不应被返回
        assert 'ETF_default' not in names.values()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])