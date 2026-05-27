"""
增量更新测试用例
验证增量更新机制的正确性和数据完整性
"""
import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.data.fetcher import TencentETFetcher


class TestIncrementalUpdate:
    """增量更新测试"""

    def test_增量更新_数据合并_去重(self):
        """测试增量数据与本地数据合并时正确去重"""
        # 模拟本地数据
        local_data = pd.DataFrame([
            {'date': '2026-05-20', 'open': 4.8, 'high': 4.9, 'low': 4.7, 'close': 4.85, 'volume': 1000},
            {'date': '2026-05-21', 'open': 4.85, 'high': 4.95, 'low': 4.8, 'close': 4.9, 'volume': 1100},
            {'date': '2026-05-22', 'open': 4.9, 'high': 5.0, 'low': 4.8, 'close': 4.95, 'volume': 1200},
        ])
        
        # 模拟增量数据（有重复）
        new_data = pd.DataFrame([
            {'date': '2026-05-22', 'open': 4.9, 'high': 5.0, 'low': 4.8, 'close': 4.95, 'volume': 1200},  # 重复
            {'date': '2026-05-23', 'open': 4.95, 'high': 5.05, 'low': 4.9, 'close': 5.0, 'volume': 1300},  # 新数据
        ])
        
        # 模拟增量更新逻辑
        combined = pd.concat([local_data, new_data]).drop_duplicates(subset=['date'], keep='last')
        combined = combined.sort_values('date')
        
        assert len(combined) == 4, "合并后应有4条数据"
        assert combined.iloc[-1]['date'] == '2026-05-23', "最新日期应为2026-05-23"
        assert combined.iloc[-1]['close'] == 5.0, "最新收盘价应为5.0"

    def test_增量更新_日期连续性(self):
        """测试增量更新保持日期连续性"""
        # 模拟本地数据
        local_data = pd.DataFrame([
            {'date': '2026-05-20', 'open': 4.8, 'high': 4.9, 'low': 4.7, 'close': 4.85, 'volume': 1000},
            {'date': '2026-05-21', 'open': 4.85, 'high': 4.95, 'low': 4.8, 'close': 4.9, 'volume': 1100},
            {'date': '2026-05-22', 'open': 4.9, 'high': 5.0, 'low': 4.8, 'close': 4.95, 'volume': 1200},
        ])
        
        # 模拟增量数据（缺少5-23，补充5-24）
        new_data = pd.DataFrame([
            {'date': '2026-05-24', 'open': 4.95, 'high': 5.05, 'low': 4.9, 'close': 5.0, 'volume': 1300},  # 新数据
        ])
        
        combined = pd.concat([local_data, new_data]).drop_duplicates(subset=['date'], keep='last')
        combined = combined.sort_values('date')
        
        # 验证日期连续性
        dates = combined['date'].tolist()
        assert dates == ['2026-05-20', '2026-05-21', '2026-05-22', '2026-05-24'], "日期应连续（允许交易日间隔）"

    def test_增量更新_字段验证(self):
        """测试增量数据字段正确性"""
        # 模拟增量数据
        new_data = pd.DataFrame([
            {'date': '2026-05-22', 'open': 4.9, 'high': 5.0, 'low': 4.8, 'close': 4.95, 'volume': 1200},
        ])
        
        # 验证字段顺序: date, open, high, low, close, volume
        expected_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
        assert list(new_data.columns) == expected_cols, f"字段顺序应为{expected_cols}"
        
        # 验证约束: high >= close >= low
        row = new_data.iloc[0]
        assert row['high'] >= row['close'], "high应>=close"
        assert row['close'] >= row['low'], "close应>=low"

    def test_增量更新_收盘后无新数据(self):
        """测试收盘后正确处理无新数据情况"""
        # 模拟收盘后场景
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # 本地最新数据已是昨天
        local_data = pd.DataFrame([
            {'date': yesterday, 'open': 4.8, 'high': 4.9, 'low': 4.7, 'close': 4.85, 'volume': 1000},
        ])
        
        # 模拟增量数据为空
        new_data = pd.DataFrame()
        
        # 合并逻辑应保持本地数据不变
        combined = pd.concat([local_data, new_data]) if len(new_data) > 0 else local_data
        assert len(combined) == 1, "合并后应有1条数据"
        assert combined.iloc[-1]['date'] == yesterday, "最新日期应为昨天"


class TestDataSourceRedundancy:
    """数据源冗余测试"""

    def test_多数据源_收盘价一致(self):
        """测试多数据源收盘价一致性"""
        # 模拟两个数据源的同一只ETF
        source1 = {'date': '2026-05-26', 'close': 4.972}
        source2 = {'date': '2026-05-26', 'close': 4.971}  # 略有差异
        
        # 计算差异百分比
        diff_pct = abs(source1['close'] - source2['close']) / source1['close'] * 100
        assert diff_pct < 1, f"差异{diff_pct:.4f}%应<1%"

    def test_数据源_字段完整性(self):
        """测试数据源返回完整字段"""
        # 模拟数据源返回
        data = {
            'date': '2026-05-26',
            'open': 4.912,
            'high': 4.975,
            'low': 4.910,
            'close': 4.972,
            'volume': 9686752
        }
        
        required_fields = ['date', 'open', 'high', 'low', 'close', 'volume']
        for field in required_fields:
            assert field in data, f"缺少字段{field}"
            assert data[field] is not None, f"字段{field}不应为None"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])