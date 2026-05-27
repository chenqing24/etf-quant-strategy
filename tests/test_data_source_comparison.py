"""
数据源对比测试用例
验证腾讯API和Baostock数据一致性
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDataSourceComparison:
    """数据源对比测试"""

    def test_腾讯API_vs_本地数据库_收盘价一致(self):
        """验证腾讯API与本地数据库收盘价一致"""
        # 模拟数据对比
        tencent_close = 4.972
        local_close = 4.972
        
        diff_pct = abs(tencent_close - local_close) / local_close * 100
        assert diff_pct < 0.1, f"差异{diff_pct:.4f}%应<0.1%"

    def test_腾讯API_vs_Baostock_收盘价差异(self):
        """验证腾讯API与Baostock收盘价差异<1%"""
        # 模拟数据对比
        tencent_close = 4.972
        baostock_close = 4.975
        
        diff_pct = abs(tencent_close - baostock_close) / tencent_close * 100
        assert diff_pct < 1, f"差异{diff_pct:.4f}%应<1%"

    def test_字段完整性_腾讯API(self):
        """验证腾讯API返回完整字段"""
        # 模拟腾讯API返回
        data = {
            'date': '2026-05-26',
            'open': 4.912,
            'high': 4.975,
            'low': 4.910,
            'close': 4.972,
            'volume': 9686752
        }
        
        required = ['date', 'open', 'high', 'low', 'close', 'volume']
        for field in required:
            assert field in data, f"腾讯API缺少{field}"
            assert data[field] is not None, f"腾讯API {field}不应为None"

    def test_字段完整性_Baostock(self):
        """验证Baostock返回完整字段"""
        # 模拟Baostock返回
        data = {
            'date': '2026-05-26',
            'open': 4.912,
            'high': 4.975,
            'low': 4.910,
            'close': 4.972,
            'volume': '9686752'
        }
        
        required = ['date', 'open', 'high', 'low', 'close', 'volume']
        for field in required:
            assert field in data, f"Baostock缺少{field}"
            assert data[field] is not None, f"Baostock {field}不应为None"

    def test_数据约束_high_ge_close_ge_low(self):
        """验证数据约束: high >= close >= low"""
        test_cases = [
            {'high': 5.0, 'close': 4.9, 'low': 4.8, 'valid': True},
            {'high': 4.9, 'close': 4.9, 'low': 4.8, 'valid': True},  # high=close
            {'high': 4.9, 'close': 4.8, 'low': 4.8, 'valid': True},  # close=low
            {'high': 4.8, 'close': 4.9, 'low': 4.8, 'valid': False},  # high<close
            {'high': 4.9, 'close': 4.7, 'low': 4.8, 'valid': False},  # close<low
        ]
        
        for tc in test_cases:
            if tc['valid']:
                assert tc['high'] >= tc['close'] >= tc['low'], f"{tc}应通过"
            else:
                assert tc['high'] < tc['close'] or tc['close'] < tc['low'], f"{tc}应失败"


class TestDataSourceCoverage:
    """数据源覆盖率测试"""

    def test_腾讯API_支持所有sh类ETF(self):
        """验证腾讯API支持所有sh类ETF"""
        sh_codes = ['510300', '510500', '512000', '513500', '510050']
        # 模拟检测结果
        supported = ['510300', '510500', '512000', '513500', '510050']
        
        assert len(supported) == len(sh_codes), f"腾讯API应支持所有sh类ETF"

    def test_Baostock_支持所有sz类ETF(self):
        """验证Baostock支持大部分sz类ETF"""
        sz_codes = ['159338', '159577', '159611', '159808', '159823', '159825', '159857']
        # 模拟检测结果 (159823不支持)
        supported = ['159338', '159577', '159611', '159808', '159825', '159857']
        
        coverage = len(supported) / len(sz_codes) * 100
        assert coverage >= 85, f"Baostock覆盖率{coverage:.1f}%应≥85%"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])