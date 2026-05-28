"""
ETF代码映射器单元测试

验证各数据源代码格式转换的正确性
"""
import pytest
from src.data.code_mapper import ETFCodeMapper


class TestToStandard:
    """to_standard() 测试 - 任意格式转为标准6位码"""

    def test_标准码不变(self):
        """标准码保持不变"""
        assert ETFCodeMapper.to_standard('159806') == '159806'
        assert ETFCodeMapper.to_standard('510300') == '510300'

    def test_baostock格式_深圳(self):
        """BaoStock深圳格式 sz.159806"""
        assert ETFCodeMapper.to_standard('sz.159806') == '159806'
        assert ETFCodeMapper.to_standard('sz159806') == '159806'

    def test_baostock格式_上海(self):
        """BaoStock上海格式 sh.510300"""
        assert ETFCodeMapper.to_standard('sh.510300') == '510300'
        assert ETFCodeMapper.to_standard('sh510300') == '510300'

    def test_东方财富格式_深圳(self):
        """东方财富深圳格式 sz159806"""
        assert ETFCodeMapper.to_standard('sz159806') == '159806'

    def test_东方财富格式_上海(self):
        """东方财富上海格式 sh510300"""
        assert ETFCodeMapper.to_standard('sh510300') == '510300'

    def test_带点混合格式(self):
        """带点的混合格式"""
        assert ETFCodeMapper.to_standard('sz.159806') == '159806'
        assert ETFCodeMapper.to_standard('sh.510300') == '510300'

    def test_空字符串返回空(self):
        """空字符串返回空"""
        assert ETFCodeMapper.to_standard('') == ''

    def test_非法字符过滤(self):
        """非数字字符被过滤"""
        assert ETFCodeMapper.to_standard('abc159806xyz') == '159806'
        assert ETFCodeMapper.to_standard('1-5-9-8-0-6') == '159806'


class TestToSource:
    """to_source() 测试 - 标准码转为目标数据源格式"""

    def test_转腾讯_保持不变(self):
        """腾讯格式就是标准码"""
        assert ETFCodeMapper.to_source('159806', 'tencent') == '159806'
        assert ETFCodeMapper.to_source('510300', 'tencent') == '510300'

    def test_转baostock_深圳(self):
        """BaoStock深圳格式 sz.159806"""
        assert ETFCodeMapper.to_source('159806', 'baostock') == 'sz.159806'

    def test_转baostock_上海(self):
        """BaoStock上海格式 sh.510300"""
        assert ETFCodeMapper.to_source('510300', 'baostock') == 'sh.510300'

    def test_转东方财富_深圳(self):
        """东方财富深圳格式 sz159806"""
        assert ETFCodeMapper.to_source('159806', 'eastmoney') == 'sz159806'

    def test_转东方财富_上海(self):
        """东方财富上海格式 sh510300"""
        assert ETFCodeMapper.to_source('510300', 'eastmoney') == 'sh510300'

    def test_转新浪_深圳(self):
        """新浪深圳格式 sz159806"""
        assert ETFCodeMapper.to_source('159806', 'sina') == 'sz159806'

    def test_转新浪_上海(self):
        """新浪上海格式 sh510300"""
        assert ETFCodeMapper.to_source('510300', 'sina') == 'sh510300'

    def test_转标准码保持不变(self):
        """转标准格式保持不变"""
        assert ETFCodeMapper.to_source('159806', 'standard') == '159806'

    def test_未知数据源返回原始码(self):
        """未知数据源返回原始标准码"""
        assert ETFCodeMapper.to_source('159806', 'unknown') == '159806'


class TestGetMarket:
    """get_market() 测试 - 判断市场"""

    def test_深圳ETF(self):
        """159xxx 系列是深圳"""
        assert ETFCodeMapper.get_market('159806') == 'SZ'
        assert ETFCodeMapper.get_market('159919') == 'SZ'
        assert ETFCodeMapper.get_market('159577') == 'SZ'

    def test_上海ETF(self):
        """510xxx 系列是上海"""
        assert ETFCodeMapper.get_market('510300') == 'SH'
        assert ETFCodeMapper.get_market('510500') == 'SH'
        assert ETFCodeMapper.get_market('515050') == 'SH'

    def test_芯片ETF(self):
        """515xxx 也是上海"""
        assert ETFCodeMapper.get_market('515050') == 'SH'

    def test_创业板ETF(self):
        """159xxx 是创业板（深圳）"""
        assert ETFCodeMapper.get_market('159919') == 'SZ'

    def test_科创50ETF(self):
        """588xxx 是科创板（上海）"""
        assert ETFCodeMapper.get_market('588050') == 'SH'
        assert ETFCodeMapper.get_market('588000') == 'SH'

    def test_中概互联ETF(self):
        """513xxx 是上海"""
        assert ETFCodeMapper.get_market('513050') == 'SH'
        assert ETFCodeMapper.get_market('513500') == 'SH'


class TestEdgeCases:
    """边界情况测试"""

    def test_带空格的标准码(self):
        """带空格的标准码"""
        assert ETFCodeMapper.to_standard(' 159806 ') == '159806'
        assert ETFCodeMapper.to_source('159806', 'baostock') == 'sz.159806'

    def test_沪深300ETF(self):
        """510300 沪深300"""
        assert ETFCodeMapper.get_market('510300') == 'SH'
        assert ETFCodeMapper.to_source('510300', 'baostock') == 'sh.510300'

    def test_创业板ETF(self):
        """159919 创业板"""
        assert ETFCodeMapper.get_market('159919') == 'SZ'
        assert ETFCodeMapper.to_source('159919', 'baostock') == 'sz.159919'

    def test_完整往返转换(self):
        """标准码 → 目标格式 → 标准码 = 原始值"""
        original = '159806'
        baostock = ETFCodeMapper.to_source(original, 'baostock')
        back = ETFCodeMapper.to_standard(baostock)
        assert back == original

        original = '510300'
        baostock = ETFCodeMapper.to_source(original, 'baostock')
        back = ETFCodeMapper.to_standard(baostock)
        assert back == original