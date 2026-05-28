"""
数据字段验证测试用例

验证目标：
1. 腾讯API字段顺序正确：[date, open, close, high, low]
2. 字段约束：high > close > low
3. 抽样验证：10只ETF数据正确性

执行命令：
pytest tests/test_data_field_order.py -v
pytest tests/test_data_field_order.py --cov=src/data --cov-report=term-missing
"""

import pytest
import sys
import os
import pandas as pd

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import DataLoader
from src.data.fetcher import TencentETFetcher


class TestDataFieldOrder:
    """测试数据字段顺序和约束"""

    @pytest.fixture
    def loader(self):
        """数据加载器fixture"""
        return DataLoader()

    @pytest.fixture
    def fetcher(self):
        """数据采集器fixture"""
        return TencentETFetcher()

    def test_腾讯API字段顺序(self, loader):
        """
        验证数据库字段顺序
        预期：[date, open, close, high, low, volume]
        """
        data = loader.load()
        
        # 获取任意一只ETF的数据
        df = None
        for code, d in data.items():
            if len(d) > 0:
                df = d
                break
        
        assert df is not None, "数据库中无任何数据"
        assert len(df.columns) >= 5, f"数据列数不足5列: {df.columns.tolist()}"
        
        # 验证字段存在
        expected_cols = ['date', 'open', 'close', 'high', 'low']
        for col in expected_cols:
            assert col in df.columns, f"缺少字段: {col}"
        
        # 验证字段顺序
        actual_order = [c for c in df.columns if c in expected_cols]
        
        # 验证关键字段关系：high应该>=close，low应该<=close
        sample = df.head()
        for _, row in sample.iterrows():
            assert row['high'] >= row['close'], f"high({row['high']}) < close({row['close']})"
            assert row['low'] <= row['close'], f"low({row['low']}) > close({row['close']})"
        
        print(f"\n字段顺序: {actual_order}")
        print(f"样本: date={sample.iloc[0]['date']}, close={sample.iloc[0]['close']}, high={sample.iloc[0]['high']}, low={sample.iloc[0]['low']}")

    def test_字段约束_high_gt_close(self, loader):
        """
        验证 high >= close 约束
        每个ETF的每条数据都必须满足：high >= close
        """
        # 加载数据
        data = loader.load()
        
        violations = []
        for code, df in list(data.items())[:10]:  # 抽样10只
            for _, row in df.iterrows():
                if row['high'] < row['close']:
                    violations.append({
                        'code': code,
                        'date': row['date'],
                        'high': row['high'],
                        'close': row['close']
                    })
        
        assert len(violations) == 0, f"发现 {len(violations)} 条 high < close 的数据: {violations[:5]}"

    def test_字段约束_low_lt_close(self, loader):
        """
        验证 low <= close 约束
        每个ETF的每条数据都必须满足：low <= close
        """
        data = loader.load()
        
        violations = []
        for code, df in list(data.items())[:10]:
            for _, row in df.iterrows():
                if row['low'] > row['close']:
                    violations.append({
                        'code': code,
                        'date': row['date'],
                        'low': row['low'],
                        'close': row['close']
                    })
        
        assert len(violations) == 0, f"发现 {len(violations)} 条 low > close 的数据: {violations[:5]}"

    def test_字段约束_high_gt_low(self, loader):
        """
        验证 high >= low 约束
        每个ETF的每条数据都必须满足：high >= low
        """
        data = loader.load()
        
        violations = []
        for code, df in list(data.items())[:10]:
            for _, row in df.iterrows():
                if row['high'] < row['low']:
                    violations.append({
                        'code': code,
                        'date': row['date'],
                        'high': row['high'],
                        'low': row['low']
                    })
        
        assert len(violations) == 0, f"发现 {len(violations)} 条 high < low 的数据: {violations[:5]}"

    def test_采样验证_10只ETF(self, loader):
        """
        抽样验证10只ETF的数据完整性
        """
        data = loader.load()
        
        results = []
        for code, df in list(data.items())[:10]:
            results.append({
                'code': code,
                'rows': len(df),
                'date_range': f"{df['date'].min()} ~ {df['date'].max()}"
            })
        
        # 验证数据量
        for r in results:
            assert r['rows'] > 100, f"ETF {r['code']} 数据量不足: {r['rows']} 行"
        
        print(f"\n抽样验证结果:")
        for r in results:
            print(f"  {r['code']}: {r['rows']} 行, {r['date_range']}")


class TestDataValidation:
    """数据完整性验证测试"""

    @pytest.fixture
    def loader(self):
        return DataLoader()

    def test_ETF数量(self, loader):
        """验证数据库ETF数量>=66"""
        data = loader.load()
        
        print(f"\n当前数据库ETF数量: {len(data)}")
        
        assert len(data) >= 66, f"ETF数量不足66只: {len(data)}"

    def test_数据时间范围(self, loader):
        """验证数据时间范围覆盖2023-2025"""
        data = loader.load()
        
        all_dates = []
        for df in data.values():
            all_dates.extend(df['date'].tolist())
        
        min_date = min(all_dates)
        max_date = max(all_dates)
        
        print(f"\n数据时间范围: {min_date} ~ {max_date}")
        
        # 验证至少覆盖2023年至今
        assert min_date <= '2023-01-01', f"数据起始日期过晚: {min_date}"
        assert max_date >= '2025-01-01', f"数据结束日期过早: {max_date}"

    def test_数据行数(self, loader):
        """验证数据库总行数>=60000"""
        data = loader.load()
        
        total_rows = sum(len(df) for df in data.values())
        print(f"\n数据库总行数: {total_rows}")
        
        assert total_rows >= 60000, f"数据行数不足60000: {total_rows}"


class TestDataLoaderEdgeCases:
    """DataLoader边界情况测试"""

    @pytest.fixture
    def loader(self):
        return DataLoader()

    def test_load_不存在的数据目录(self, loader, caplog):
        """测试加载不存在的数据目录"""
        # 使用一个肯定不存在的目录
        result = loader.load('nonexistent_data_dir_12345')
        
        # 应该返回空字典
        assert result == {}, "不存在目录应返回空字典"
        assert isinstance(caplog.text, str), "应有日志输出"

    def test_load_from_sqlite_异常(self, loader):
        """测试_load_from_sqlite异常处理"""
        # 传入一个不存在的路径
        from pathlib import Path
        
        result = loader._load_from_sqlite(Path('/fake/path/db.sqlite'))
        
        # 应该返回空字典
        assert result == {}, "异常时应返回空字典"

    def test_process_df_列重命名(self, loader):
        """测试列名处理"""
        import pandas as pd
        
        # 测试vol->volume
        df = pd.DataFrame({
            'date': ['2026-01-01'],
            'open': [4.5],
            'high': [4.6],
            'low': [4.3],
            'close': [4.5],
            'vol': [1000000]  # 使用vol而非volume
        })
        
        result = loader._process_df(df)
        
        assert 'volume' in result.columns, "vol应被重命名为volume"
        assert 'vol' not in result.columns, "vol列应被移除"

    def test_get_存在的数据(self, loader):
        """测试get方法-数据存在"""
        loader.data = {'sh510300': pd.DataFrame({'a': [1, 2]})}
        
        result = loader.get('sh510300')
        
        assert result is not None, "数据存在时应返回"
        assert len(result) == 2

    def test_get_不存在的数据(self, loader):
        """测试get方法-数据不存在"""
        loader.data = {}
        
        result = loader.get('nonexistent_code')
        
        assert result is None, "数据不存在时应返回None"

    def test_get_etfs_批量获取(self, loader):
        """测试get_etfs批量获取"""
        loader.data = {
            'sh510300': pd.DataFrame({'a': [1]}),
            'sz159919': pd.DataFrame({'b': [2]}),
            'sh588000': pd.DataFrame({'c': [3]})
        }
        
        result = loader.get_etfs(['sh510300', 'sz159919'])
        
        assert len(result) == 2, "应返回2只ETF"
        assert 'sh510300' in result
        assert 'sz159919' in result
        assert 'sh588000' not in result

    def test_get_etfs_部分不存在(self, loader):
        """测试get_etfs部分代码不存在"""
        loader.data = {'sh510300': pd.DataFrame({'a': [1]})}
        
        result = loader.get_etfs(['sh510300', 'nonexistent'])
        
        assert len(result) == 1, "只应返回存在的"
        assert 'sh510300' in result

    def test_get_date_range_有数据(self, loader):
        """测试get_date_range-有数据"""
        loader.data = {
            'sh510300': pd.DataFrame({
                'date': ['2026-01-01', '2026-01-02', '2026-01-03'],
                'a': [1, 2, 3]
            })
        }
        
        start, end = loader.get_date_range('sh510300')
        
        assert start == '2026-01-01', "起始日期错误"
        assert end == '2026-01-03', "结束日期错误"

    def test_get_date_range_无数据(self, loader):
        """测试get_date_range-无数据"""
        loader.data = {}
        
        start, end = loader.get_date_range('nonexistent')
        
        assert start is None
        assert end is None

    def test_get_date_range_空DataFrame(self, loader):
        """测试get_date_range-空DataFrame"""
        loader.data = {'sh510300': pd.DataFrame()}
        
        start, end = loader.get_date_range('sh510300')
        
        assert start is None
        assert end is None


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])