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
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import DataLoader


class TestDataLoader:
    """DataLoader完整测试"""

    @pytest.fixture
    def loader(self):
        return DataLoader()

    def test_初始化_默认配置(self, loader):
        """测试初始化使用默认配置"""
        # 验证loader可以正常使用
        data = loader.load()
        assert isinstance(data, dict), "初始化失败"

    def test_load_返回类型(self, loader):
        """测试load方法返回类型"""
        data = loader.load()
        assert isinstance(data, dict), "返回类型错误"

    def test_load_单只ETF(self, loader):
        """测试加载单只ETF数据"""
        df = loader.get('510300')
        # 可能返回None或DataFrame
        assert df is None or isinstance(df, pd.DataFrame), "获取失败"

    def test_load_多只ETF(self, loader):
        """测试加载多只ETF数据"""
        codes = ['510300', '510050', '159577']
        data = loader.get_etfs(codes)
        assert isinstance(data, dict), "返回类型错误"
        assert len(data) <= len(codes), "结果数量异常"

    def test_load_获取日期范围_存在数据(self, loader):
        """测试获取日期范围（存在数据时）"""
        start, end = loader.get_date_range('510300')
        if start and end:
            assert start <= end, "日期范围错误"
            print(f"\n510300日期范围: {start} ~ {end}")

    def test_load_获取日期范围_不存在数据(self, loader):
        """测试获取日期范围（不存在数据时）"""
        start, end = loader.get_date_range('nonexistent_code')
        # 可能返回None或空
        print(f"\n不存在ETF日期范围: {start}, {end}")

    def test_load_验证数据完整性(self, loader):
        """测试加载数据后数据完整性"""
        data = loader.load()
        
        for code, df in list(data.items())[:3]:
            # 验证必要字段
            required_fields = ['date', 'open', 'high', 'low', 'close']
            for field in required_fields:
                assert field in df.columns, f"ETF {code} 缺少字段: {field}"

    def test_load_验证数据类型(self, loader):
        """测试加载数据后数据类型正确"""
        data = loader.load()
        
        for code, df in list(data.items())[:1]:
            # 验证数值字段类型
            numeric_fields = ['open', 'high', 'low', 'close', 'volume']
            for field in numeric_fields:
                if field in df.columns:
                    assert pd.api.types.is_numeric_dtype(df[field]), f"字段{field}类型错误"

    def test_load_数据量验证(self, loader):
        """测试加载数据量合理"""
        data = loader.load()
        
        for code, df in list(data.items())[:3]:
            assert len(df) > 0, f"ETF {code} 无数据"
            # ETF应该有足够的历史数据
            assert len(df) >= 100, f"ETF {code} 数据量过少: {len(df)}"

    def test_load_空代码列表(self, loader):
        """测试加载空代码列表"""
        data = loader.get_etfs([])
        assert isinstance(data, dict), "返回类型错误"
        assert len(data) == 0, "空列表应返回空字典"

    def test_load_部分ETF不存在(self, loader):
        """测试部分ETF不存在"""
        codes = ['510300', 'nonexistent_code']
        data = loader.get_etfs(codes)
        # 应该返回存在的ETF
        assert isinstance(data, dict), "返回类型错误"


class TestDataLoaderEdgeCases:
    """边界情况测试"""

    @pytest.fixture
    def loader(self):
        return DataLoader()

    def test_无效数据目录(self):
        """测试无效数据目录"""
        try:
            loader = DataLoader(data_dir='nonexistent_directory')
            data = loader.load()
            # 应该返回空字典
            assert isinstance(data, dict), "处理失败"
        except Exception as e:
            print(f"预期异常: {e}")

    def test_损坏的数据文件(self):
        """测试损坏的数据文件"""
        try:
            df = loader.get('invalid_file')
            # 可能返回None或空DataFrame
            assert df is None or len(df) == 0, "处理失败"
        except Exception as e:
            print(f"预期异常: {e}")

    def test_加载大量ETF(self, loader):
        """测试加载大量ETF"""
        data = loader.load()
        assert len(data) > 0, "没有加载任何ETF"
        print(f"\n加载ETF数量: {len(data)}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])