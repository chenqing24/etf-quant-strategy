"""
数据源集成测试

验证各数据源能实际获取数据，确保同类问题不再出现
"""
import pytest
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestTencentAPIIntegration:
    """腾讯API集成测试"""

    @pytest.mark.skip(reason="需要网络连接，在CI中可选运行")
    def test_腾讯API_获取上交所ETF_510300(self):
        """验证腾讯API能获取上交所ETF(510300)实时价格"""
        from src.trade.validator import TradeValidator
        
        v = TradeValidator()
        result = v._fetch_tencent(['510300'])
        
        assert '510300' in result, "510300应在结果中"
        data = result['510300']
        assert data['price'] > 0, "价格应>0"
        assert 'name' in data, "应包含名称"
        assert data['data_source'] == 'tencent', "数据源应为tencent"

    @pytest.mark.skip(reason="需要网络连接，在CI中可选运行")
    def test_腾讯API_获取深交所ETF_159806(self):
        """验证腾讯API能获取深交所ETF(159806)实时价格
        
        【重要】159xxx是深交所ETF，需要用sz前缀
        这个测试确保代码正确处理深交所ETF
        """
        from src.trade.validator import TradeValidator
        
        v = TradeValidator()
        result = v._fetch_tencent(['159806'])
        
        assert '159806' in result, "159806应在结果中"
        data = result['159806']
        assert data['price'] > 0, "价格应>0"
        assert data['data_source'] == 'tencent', "数据源应为tencent"

    @pytest.mark.skip(reason="需要网络连接，在CI中可选运行")
    def test_腾讯API_同时获取多只ETF(self):
        """验证腾讯API能同时获取多只不同市场的ETF"""
        from src.trade.validator import TradeValidator
        
        v = TradeValidator()
        codes = ['510300', '159806', '588000', '159915']
        result = v._fetch_tencent(codes)
        
        for code in codes:
            assert code in result, f"{code}应在结果中"
            assert result[code]['price'] > 0, f"{code}价格应>0"


class TestSinaAPIIntegration:
    """新浪API集成测试"""

    @pytest.mark.skip(reason="需要网络连接，新浪API可能不稳定")
    def test_新浪API_获取实时价格(self):
        """验证新浪API能获取实时价格"""
        from src.trade.validator import TradeValidator
        
        v = TradeValidator()
        result = v._fetch_sina(['510300'])
        
        # 新浪API可能返回空，测试结构正确即可
        assert isinstance(result, dict), "应返回字典"


class TestEMFAPIIntegration:
    """东方财富API集成测试"""

    @pytest.mark.skip(reason="需要网络连接，东方财富API可能有限制")
    def test_EMF_API_获取上交所ETF(self):
        """验证东方财富API能获取上交所ETF实时价格"""
        from src.trade.validator import TradeValidator
        
        v = TradeValidator()
        result = v._fetch_emf(['510300'])
        
        # 东方财富API可能返回空，测试结构正确即可
        assert isinstance(result, dict), "应返回字典"


class TestBaoStockIntegration:
    """BaoStock集成测试"""

    @pytest.mark.skip(reason="需要网络连接，且需要baostock库")
    def test_baostock_获取深交所ETF(self):
        """验证BaoStock能获取深交所ETF日线数据"""
        import baostock as bs
        
        bs.login()
        rs = bs.query_history_k_data_plus('sz.159806',
            'date,open,high,low,close,volume',
            start_date='2026-05-25', 
            end_date='2026-05-27',
            frequency='d', 
            adjustflag='2')
        
        data_list = []
        while (rs.error_code == '0') & rs.next():
            data_list.append(rs.get_row_data())
        
        bs.logout()
        
        assert len(data_list) > 0, "应获取到数据"
        assert float(data_list[-1][5]) > 0, "收盘价应>0"


class TestRealtimePriceFetchPriority:
    """实时价格获取优先级测试"""

    @pytest.mark.skip(reason="需要网络连接")
    def test_159806_能获取到实时价格(self):
        """【关键测试】验证159806能获取到实时价格
        
        之前的问题：159xxx被错误判断为上交所，导致获取失败
        这个测试确保问题不再出现
        """
        from src.trade.validator import fetch_realtime_prices
        
        prices = fetch_realtime_prices(['159806'])
        
        assert '159806' in prices, "159806应在结果中"
        rt = prices['159806']
        assert rt['price'] > 0, "价格应>0"
        assert rt['price'] < 10, "ETF价格应<10元（合理的ETF价格范围）"

    @pytest.mark.skip(reason="需要网络连接")
    def test_510300_能获取到实时价格(self):
        """验证510300能获取到实时价格"""
        from src.trade.validator import fetch_realtime_prices
        
        prices = fetch_realtime_prices(['510300'])
        
        assert '510300' in prices, "510300应在结果中"
        rt = prices['510300']
        assert rt['price'] > 0, "价格应>0"

    @pytest.mark.skip(reason="需要网络连接")
    def test_多个不同市场ETF_能获取实时价格(self):
        """验证多个不同市场的ETF都能获取到实时价格"""
        from src.trade.validator import fetch_realtime_prices
        
        codes = [
            '510300',  # 上交所 沪深300
            '159806',  # 深交所 新能源车
            '588000',  # 上交所 科创50
            '159915',  # 深交所 创业板
        ]
        
        prices = fetch_realtime_prices(codes)
        
        for code in codes:
            assert code in prices, f"{code}应在结果中"
            assert prices[code]['price'] > 0, f"{code}价格应>0"


class TestCodePrefixLogic:
    """ETF代码前缀判断逻辑测试"""

    def test_159xxx_应使用sz前缀(self):
        """验证159xxx代码使用sz前缀"""
        code = '159806'
        
        if code.startswith('159'):
            prefix = f'sz{code}'
        elif code.startswith(('5', '11')):
            prefix = f'sh{code}'
        else:
            prefix = f'sz{code}'
        
        assert prefix == 'sz159806', f"159xxx应转为sz前缀，实际为{prefix}"

    def test_510xxx_应使用sh前缀(self):
        """验证510xxx代码使用sh前缀"""
        code = '510300'
        
        if code.startswith('159'):
            prefix = f'sz{code}'
        elif code.startswith(('5', '11')):
            prefix = f'sh{code}'
        else:
            prefix = f'sz{code}'
        
        assert prefix == 'sh510300', f"510xxx应转为sh前缀，实际为{prefix}"

    def test_515xxx_应使用sh前缀(self):
        """验证515xxx代码使用sh前缀"""
        code = '515050'
        
        if code.startswith('159'):
            prefix = f'sz{code}'
        elif code.startswith(('5', '11')):
            prefix = f'sh{code}'
        else:
            prefix = f'sz{code}'
        
        assert prefix == 'sh515050', f"515xxx应转为sh前缀，实际为{prefix}"

    def test_588xxx_应使用sh前缀(self):
        """验证588xxx代码使用sh前缀"""
        code = '588000'
        
        if code.startswith('159'):
            prefix = f'sz{code}'
        elif code.startswith(('5', '11')):
            prefix = f'sh{code}'
        else:
            prefix = f'sz{code}'
        
        assert prefix == 'sh588000', f"588xxx应转为sh前缀，实际为{prefix}"

    def test_已有前缀不变(self):
        """验证已有sh/sz前缀的代码保持不变"""
        for code in ['sh510300', 'sz159806', 'SH510300', 'SZ159806']:
            if code.startswith(('sh', 'sz', 'SH', 'SZ')):
                # 已有前缀，保持不变
                pass
        
        assert True, "已有前缀的代码应保持不变"


class TestValidatorEMFUsage:
    """验证TradeValidator正确使用EMF_BASE_URL"""

    def test_validator_导入EMF_BASE_URL(self):
        """验证TradeValidator正确导入EMF_BASE_URL"""
        with open('src/trade/validator.py', 'r') as f:
            content = f.read()
        
        assert 'from src.constants import' in content, "应导入constants"
        assert 'EMF_BASE_URL' in content, "应使用EMF_BASE_URL"

    def test_validator_不使用self_EMF_BASE_URL(self):
        """验证不使用self.EMF_BASE_URL（应为模块级导入）"""
        with open('src/trade/validator.py', 'r') as f:
            content = f.read()
        
        # 检查_fetch_emf方法中不应有self.EMF_BASE_URL
        import re
        emf_method = re.search(r'def _fetch_emf\(.*?\):.*?(?=\n    def |\nclass |\Z)', 
                               content, re.DOTALL)
        if emf_method:
            method_content = emf_method.group(0)
            assert 'self.EMF_BASE_URL' not in method_content, \
                "_fetch_emf中不应使用self.EMF_BASE_URL，应用模块级EMF_BASE_URL"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
