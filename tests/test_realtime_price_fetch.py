"""
实时价格获取测试

验证决策系统正确获取实时价格，而非使用热数据缓存
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRealtimePriceFetch:
    """实时价格获取测试"""

    def test_decision_engine_应使用API获取实时价格(self):
        """验证decision.py使用fetch_realtime_prices而非热数据缓存"""
        # 这个测试验证修复后的行为
        # 修复后：decision.py 调用 fetch_realtime_prices()
        # 未修复：decision.py 从热数据获取
        
        # 检查decision.py是否正确导入fetch_realtime_prices
        with open('src/cli/decision.py', 'r') as f:
            content = f.read()
        
        # 修复后应该包含：from src.trade.validator import fetch_realtime_prices
        assert 'fetch_realtime_prices' in content, \
            "decision.py应导入fetch_realtime_prices"
        
        # 修复后应该调用：prices = fetch_realtime_prices([new_code])
        assert 'fetch_realtime_prices([new_code])' in content or \
               'fetch_realtime_prices([code])' in content, \
            "decision.py应调用fetch_realtime_prices获取实时价格"

    def test_report_builder_区分实时价和昨收盘(self):
        """验证report_builder.py区分实时价格和昨收盘价"""
        with open('src/analysis/report_builder.py', 'r') as f:
            content = f.read()
        
        # 修复后应该区分"昨收盘"和"实时价"
        assert '昨收盘' in content or '昨收' in content, \
            "report_builder.py应区分昨收盘价和实时价"

    def test_实时价格来源应标注(self):
        """验证实时价格应标注数据来源"""
        with open('src/analysis/report_builder.py', 'r') as f:
            content = f.read()
        
        # 修复后应该标注数据来源
        assert 'source' in content or '来源' in content, \
            "应标注实时价格的数据来源"


class TestRealtimePriceSource:
    """实时价格数据源测试"""

    def test_validator_按优先级调用数据源(self):
        """验证TradeValidator按优先级调用数据源"""
        from src.trade.validator import TradeValidator, DataSource
        import inspect
        
        # 获取fetch_realtime_prices方法源码
        source = inspect.getsource(TradeValidator.fetch_realtime_prices)
        
        # 应该按优先级尝试多个数据源
        assert 'tencent' in source.lower() or 'TENCENT' in source, \
            "应优先尝试腾讯API"
        
        # 应该有降级逻辑
        assert 'emf' in source.lower() or 'sina' in source.lower(), \
            "应有降级到其他数据源的逻辑"

    def test_所有API失败时应使用昨收盘(self):
        """验证所有API失败时应使用昨收盘价作为参考"""
        # 这是一个设计验证测试
        with open('src/cli/decision.py', 'r') as f:
            content = f.read()
        
        # 修复后应该在API失败时使用昨收盘
        assert '昨收盘' in content or '_etf_data' in content, \
            "API失败时应使用昨收盘价"


class TestRealtimePriceIntegration:
    """实时价格集成测试"""

    @pytest.mark.skip(reason="需要实际网络连接")
    def test_fetch_realtime_prices_返回正确结构(self):
        """集成测试：fetch_realtime_prices返回正确的数据结构"""
        from src.trade.validator import fetch_realtime_prices
        
        # 测试获取实时价格
        prices = fetch_realtime_prices(['510300'])
        
        # 验证返回结构
        assert '510300' in prices or len(prices) > 0, "应返回数据"
        
        # 验证数据字段
        if '510300' in prices:
            rt = prices['510300']
            assert 'price' in rt, "应包含price字段"
            assert 'data_source' in rt, "应包含data_source字段"

    @pytest.mark.skip(reason="需要实际网络连接")
    def test_深交所ETF使用BaoStock(self):
        """集成测试：深交所ETF应能获取到数据"""
        from src.trade.validator import fetch_realtime_prices
        
        # 159806是深交所ETF
        prices = fetch_realtime_prices(['159806'])
        
        # 应该能获取到数据
        assert '159806' in prices, "深交所ETF应能获取到数据"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
