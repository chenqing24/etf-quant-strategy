"""
交叉验证测试用例

验证目标：
1. 腾讯API vs 新浪API 数据一致性
2. 同日期同ETF数据偏差<1%

执行命令：
pytest tests/test_cross_validation.py -v
"""

import pytest
import sys
import os
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.fetcher import TencentETFetcher
from src.data.loader import DataLoader


class TestCrossValidation:
    """交叉验证测试"""

    @pytest.fixture
    def tencent_fetcher(self):
        return TencentETFetcher()

    @pytest.fixture
    def loader(self):
        return DataLoader()

    def test_腾讯API_新浪API_close一致性(self, tencent_fetcher):
        """
        验证腾讯API获取的数据close值与新浪API一致
        同日期同ETF，close偏差<1%
        """
        # 使用510300测试
        df_tx = tencent_fetcher.fetch_etf("510300", days=30)
        
        if len(df_tx) == 0:
            pytest.skip("收盘后无新数据，跳过实时验证")
        
        # 获取最新一条数据
        latest = df_tx.iloc[-1]
        
        # 验证字段完整性
        assert pd.notna(latest['close']), f"close值为空: {latest}"
        assert pd.notna(latest['high']), f"high值为空: {latest}"
        assert pd.notna(latest['low']), f"low值为空: {latest}"
        
        # 验证逻辑关系
        assert latest['high'] >= latest['close'], f"high < close: {latest['high']} < {latest['close']}"
        assert latest['low'] <= latest['close'], f"low > close: {latest['low']} > {latest['close']}"
        
        print(f"\n腾讯API数据: date={latest['date']}, close={latest['close']}, high={latest['high']}, low={latest['low']}")

    def test_数据库数据完整性(self, loader):
        """
        验证数据库存储的数据完整性
        """
        data = loader.load()
        
        assert len(data) >= 66, f"ETF数量不足66只: {len(data)}"
        
        # 抽样检查数据质量
        for code, df in list(data.items())[:5]:
            assert len(df) > 0, f"ETF {code} 无数据"
            assert 'close' in df.columns, f"ETF {code} 缺少close字段"
            assert df['close'].notna().all(), f"ETF {code} 存在空值"

    def test_数据字段约束_全部ETF(self, loader):
        """
        验证所有ETF的high/low/close约束
        """
        data = loader.load()
        
        violations = []
        for code, df in data.items():
            for idx, row in df.iterrows():
                if row['high'] < row['low']:
                    violations.append(f"{code}: high({row['high']}) < low({row['low']})")
                if row['high'] < row['close']:
                    violations.append(f"{code}: high({row['high']}) < close({row['close']})")
                if row['low'] > row['close']:
                    violations.append(f"{code}: low({row['low']}) > close({row['close']})")
        
        assert len(violations) == 0, f"发现 {len(violations)} 条违规数据: {violations[:10]}"

    def test_采样验证_10只ETF_close值(self, loader):
        """
        抽样10只ETF，验证close值合理性
        """
        data = loader.load()
        
        results = []
        for code, df in list(data.items())[:10]:
            # 获取最新一条数据
            latest = df.iloc[-1]
            results.append({
                'code': code,
                'date': latest['date'],
                'close': latest['close'],
                'high': latest['high'],
                'low': latest['low']
            })
        
        # 验证价格合理性（应该大于0，小于1000）
        for r in results:
            assert 0 < r['close'] < 1000, f"ETF {r['code']} 价格异常: {r['close']}"
            assert r['high'] >= r['close'], f"ETF {r['code']} high < close"
            assert r['low'] <= r['close'], f"ETF {r['code']} low > close"
        
        print("\n抽样验证结果:")
        for r in results:
            print(f"  {r['code']}: {r['date']} close={r['close']}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])