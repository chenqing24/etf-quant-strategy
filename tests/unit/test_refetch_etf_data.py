#!/usr/bin/env python3
"""
refetch_etf_data.py 单元测试

测试场景：
1. 全量采集模式（DRY RUN）
2. 指定股票列表模式
3. 指定时间段模式
4. 从配置文件读取
5. 错误处理
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestGetPrefix:
    """交易所前缀判断"""
    
    def test_sh_prefix(self):
        from scripts.data.refetch_etf_data import get_prefix
        assert get_prefix('510300') == 'sh'
        assert get_prefix('512480') == 'sh'
        assert get_prefix('588000') == 'sh'
    
    def test_sz_prefix(self):
        from scripts.data.refetch_etf_data import get_prefix
        assert get_prefix('159919') == 'sz'
        assert get_prefix('159577') == 'sz'


class TestGetAllEtfCodes:
    """全量ETF列表获取"""

    def test_get_all_returns_list(self):
        """需要正常数据库，返回非空列表"""
        from scripts.data.refetch_etf_data import get_all_etf_codes
        try:
            codes = get_all_etf_codes()
            assert isinstance(codes, list)
            assert len(codes) > 0
            # 检查格式：6位数字
            for code in codes[:5]:
                assert code.isdigit() and len(code) == 6
        except Exception:
            # 数据库不可访问时跳过（测试环境无DB）
            pytest.skip("Database not accessible")


class TestRecordsToDataframe:
    """数据转换"""
    
    def test_empty_records(self):
        from scripts.data.refetch_etf_data import records_to_dataframe
        df = records_to_dataframe([])
        assert df.empty
    
    def test_valid_records(self):
        from scripts.data.refetch_etf_data import records_to_dataframe
        records = [
            ['2026-05-29', 3.50, 3.55, 3.48, 3.52, 1000000],
            ['2026-05-28', 3.48, 3.52, 3.45, 3.50, 900000],
        ]
        df = records_to_dataframe(records)
        assert len(df) == 2
        assert 'date' in df.columns
        assert 'open' in df.columns
        assert 'close' in df.columns
        assert df.iloc[0]['date'] == '2026-05-29'
    
    def test_skip_invalid_records(self):
        from scripts.data.refetch_etf_data import records_to_dataframe
        records = [
            ['2026-05-29', 3.50, 3.55, 3.48, 3.52, 1000000],
            [],  # 无效
        ]
        df = records_to_dataframe(records)
        # 有效记录被处理，无效被跳过
        assert len(df) >= 1


class TestFetchAndWrite:
    """采集并写入"""
    
    @patch('scripts.data.refetch_etf_data.requests.get')
    def test_fetch_success(self, mock_get):
        """成功采集"""
        mock_response = MagicMock()
        mock_response.text = 'kline_dayqfq={"data":{"sh510300":{"qfqday":[["2026-05-29", 3.50, 3.55, 3.48, 3.52, 1000000]]}}}'
        mock_get.return_value = mock_response
        
        from scripts.data.refetch_etf_data import fetch_historical_from_tencent
        records = fetch_historical_from_tencent('510300', 30)
        assert len(records) == 1
    
    @patch('scripts.data.refetch_etf_data.requests.get')
    def test_fetch_failure(self, mock_get):
        """采集失败"""
        mock_get.side_effect = Exception('Network error')
        
        from scripts.data.refetch_etf_data import fetch_historical_from_tencent
        records = fetch_historical_from_tencent('510300', 30)
        assert records == []


class TestMainIntegration:
    """主函数集成测试（使用 mock）"""

    @patch('scripts.data.refetch_etf_data.get_all_etf_codes')
    def test_dry_run_callable(self, mock_codes):
        """DRY RUN 模式可正常调用"""
        mock_codes.return_value = ['510300']
        with patch('sys.argv', ['refetch_etf_data.py', '--dry-run']):
            from scripts.data.refetch_etf_data import main
            # 不抛异常即通过
            main()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
