"""
loader.py 覆盖率提升测试用例

目标：覆盖率 81% → 90%

执行命令：
pytest tests/test_loader_coverage.py -v --cov=src.data.loader --cov-report=term-missing
"""

import pytest
import sys
import os
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import DataLoader


class TestDataLoader:
    """DataLoader完整测试"""

    @pytest.fixture
    def loader(self):
        return DataLoader()

    def test_初始化_默认配置(self, loader):
        """测试初始化使用默认配置"""
        data = loader.load(min_rows=100)
        assert isinstance(data, dict), "初始化失败"

    def test_load_返回类型(self, loader):
        """测试load方法返回类型"""
        data = loader.load(min_rows=100)
        assert isinstance(data, dict), "返回类型错误"

    def test_load_单只ETF(self, loader):
        """测试加载单只ETF数据"""
        df = loader.load_single('510300')
        # 可能返回None或DataFrame
        assert df is None or isinstance(df, pd.DataFrame), "获取失败"

    def test_load_多只ETF(self, loader):
        """测试加载多只ETF数据"""
        data = loader.load(min_rows=100)
        assert isinstance(data, dict), "返回类型错误"
        assert len(data) > 0, "应有数据"

    def test_load_获取日期范围_存在数据(self, loader):
        """测试获取日期范围（存在数据时）"""
        result = loader.get_date_range('510300')
        assert 'min_date' in result
        assert 'max_date' in result
        if result['min_date'] and result['max_date']:
            assert result['min_date'] <= result['max_date'], "日期范围错误"

    def test_load_获取日期范围_不存在数据(self, loader):
        """测试获取日期范围（不存在数据时）"""
        result = loader.get_date_range('nonexistent_code_xyz')
        # 返回空dict或带None值的dict
        assert isinstance(result, dict)

    def test_load_验证数据完整性(self, loader):
        """测试加载数据后数据完整性"""
        data = loader.load(min_rows=100)
        
        for code, df in list(data.items())[:3]:
            # 验证必要字段
            required_fields = ['date', 'open', 'high', 'low', 'close']
            for field in required_fields:
                assert field in df.columns, f"ETF {code} 缺少字段: {field}"

    def test_load_验证数据类型(self, loader):
        """测试加载数据后数据类型正确"""
        data = loader.load(min_rows=100)
        
        for code, df in list(data.items())[:1]:
            # 验证数值字段类型
            numeric_fields = ['open', 'high', 'low', 'close', 'volume']
            for field in numeric_fields:
                if field in df.columns:
                    assert pd.api.types.is_numeric_dtype(df[field]), f"字段{field}类型错误"

    def test_load_数据量验证(self, loader):
        """测试加载数据量合理"""
        data = loader.load(min_rows=100)
        
        for code, df in list(data.items())[:3]:
            assert len(df) > 0, f"ETF {code} 无数据"
            # ETF应该有足够的历史数据
            assert len(df) >= 100, f"ETF {code} 数据量过少: {len(df)}"

    def test_load_部分ETF不存在(self, loader):
        """测试部分ETF不存在"""
        # load_single 对不存在的代码返回 None
        df = loader.load_single('nonexistent_code_xyz')
        assert df is None


class TestDataLoaderEdgeCases:
    """边界情况测试"""

    @pytest.fixture
    def loader(self):
        return DataLoader()

    def test_无效数据库路径(self):
        """测试无效数据库路径"""
        loader = DataLoader(db_path='/fake/path/nonexistent.db')
        data = loader.load(min_rows=100)
        assert data == {}, "不存在的数据库应返回空字典"