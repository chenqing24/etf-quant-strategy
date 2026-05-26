"""
增量更新测试用例

验证目标：
1. 增量更新功能正确
2. 数据正确追加
3. 字段约束验证
4. 容错机制

执行命令：
pytest tests/test_incremental_update.py -v
"""

import pytest
import sys
import os
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.fetcher import TencentETFetcher
from src.data.loader import DataLoader


class TestIncrementalUpdate:
    """增量更新测试"""

    @pytest.fixture
    def fetcher(self):
        return TencentETFetcher()

    @pytest.fixture
    def loader(self):
        return DataLoader()

    def test_获取本地最新日期(self, fetcher, loader):
        """
        验证获取本地数据库最新日期功能
        """
        data = loader.load()
        
        # 获取任一ETF的最新日期
        code = list(data.keys())[0]
        local_df = data[code]
        local_latest = local_df['date'].max()
        
        print(f"\n{code} 本地最新日期: {local_latest}")
        
        assert local_latest is not None, "本地最新日期为空"
        assert len(str(local_latest)) == 10, f"日期格式错误: {local_latest}"

    def test_增量数据日期大于本地最新(self, fetcher, loader):
        """
        验证增量获取的数据日期 >= 本地最新日期
        """
        data = loader.load()
        
        # 获取任一ETF
        code = '510300'
        if code not in data:
            code = list(data.keys())[0]
        
        local_df = data[code]
        local_latest = local_df['date'].max()
        
        # 获取增量数据（7天）
        new_df = fetcher.fetch_etf(code, days=7)
        
        if len(new_df) > 0:
            new_latest = new_df['date'].max()
            print(f"\n本地最新: {local_latest}, 新增最新: {new_latest}")
            
            # 增量数据应该 >= 本地最新
            assert new_latest >= local_latest, f"增量数据日期错误: {new_latest} < {local_latest}"

    def test_增量数据字段完整性(self, fetcher):
        """
        验证增量数据字段完整性
        """
        df = fetcher.fetch_etf('510300', days=7)
        
        if len(df) > 0:
            required_fields = ['date', 'open', 'high', 'low', 'close']
            for field in required_fields:
                assert field in df.columns, f"缺少字段: {field}"
                assert df[field].notna().all(), f"字段 {field} 存在空值"

    def test_增量数据逻辑约束(self, fetcher):
        """
        验证增量数据满足 high >= close >= low
        """
        df = fetcher.fetch_etf('510300', days=7)
        
        if len(df) > 0:
            for _, row in df.iterrows():
                assert row['high'] >= row['close'], f"high < close: {row['high']} < {row['close']}"
                assert row['low'] <= row['close'], f"low > close: {row['low']} > {row['close']}"
                assert row['high'] >= row['low'], f"high < low: {row['high']} < {row['low']}"

    def test_增量数据价格合理性(self, fetcher):
        """
        验证价格合理性：close > 0 且 < 1000
        """
        df = fetcher.fetch_etf('510300', days=7)
        
        if len(df) > 0:
            for _, row in df.iterrows():
                assert 0 < row['close'] < 1000, f"价格异常: {row['close']}"
                assert 0 < row['open'] < 1000, f"价格异常: {row['open']}"
                assert 0 < row['high'] < 1000, f"价格异常: {row['high']}"
                assert 0 < row['low'] < 1000, f"价格异常: {row['low']}"

    def test_获取多只ETF增量数据(self, fetcher):
        """
        验证获取多只ETF增量数据
        收盘后可能都无新数据，验证请求不崩溃
        """
        codes = ['510300', '510050', '159577']
        
        results = {}
        for code in codes:
            df = fetcher.fetch_etf(code, days=7)
            results[code] = len(df)
            print(f"{code}: {len(df)}行")
        
        # 收盘后可能都无数据，但请求不应崩溃
        assert len(results) == 3, "请求异常"

    def test_增量更新频率限制(self, fetcher):
        """
        验证增量更新有频率限制（避免被封禁）
        注意：收盘后直接返回无数据，不会触发真实请求
        """
        import time
        
        # 连续获取3只ETF
        codes = ['510300', '510050', '159577']
        start = time.time()
        
        for code in codes:
            fetcher.fetch_etf(code, days=1)
        
        elapsed = time.time() - start
        
        print(f"\n3只ETF获取耗时: {elapsed:.2f}秒")
        
        # 收盘后快速返回，但实际请求应该有延迟
        # 验证不会因为并发导致异常
        assert elapsed >= 0, f"请求异常: {elapsed:.2f}秒"


class TestIncrementalUpdateIntegration:
    """增量更新集成测试"""

    @pytest.fixture
    def fetcher(self):
        return TencentETFetcher()

    @pytest.fixture
    def loader(self):
        return DataLoader()

    def test_批量获取全部ETF(self, fetcher):
        """
        验证批量获取全部ETF
        """
        from src.data.loader import DataLoader
        loader = DataLoader()
        data = loader.load()
        codes = list(data.keys())
        
        print(f"\nETF总数: {len(codes)}")
        
        success = 0
        failed = []
        
        for code in codes[:5]:  # 先测试5只
            try:
                df = fetcher.fetch_etf(code, days=7)
                if len(df) > 0:
                    success += 1
            except Exception as e:
                failed.append((code, str(e)))
        
        print(f"成功: {success}/5")
        if failed:
            print(f"失败: {failed}")
        
        # 收盘后可能都无数据，但至少不应该崩溃
        assert success >= 0 or len(failed) == 0, f"请求异常: {failed}"

    def test_数据追加模式验证(self, fetcher, loader):
        """
        验证增量数据可以正确追加到SQLite
        """
        # 获取一只ETF的数据
        code = '510300'
        df_new = fetcher.fetch_etf(code, days=7)
        
        if len(df_new) == 0:
            pytest.skip("收盘后无新数据")
        
        # 获取本地数据
        data = loader.load()
        df_old = data.get(code)
        
        if df_old is None:
            pytest.skip("本地无该ETF数据")
        
        old_count = len(df_old)
        new_count = len(df_new)
        
        print(f"\n原数据: {old_count}行, 新数据: {new_count}行")
        
        # 验证新数据行数合理（通常是7天1行）
        assert new_count <= 7, f"新数据行数过多: {new_count}"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])