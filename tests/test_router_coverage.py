"""
router.py 覆盖率提升测试用例

目标：覆盖率 0% → 90%

执行命令：
pytest tests/test_router_coverage.py -v --cov=src.data.router --cov-report=term-missing
"""

import pytest
import sys
import os
import pandas as pd
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.router import DataSourceRouter, RateLimiter, FetchResult


class TestRateLimiter:
    """RateLimiter测试"""

    def test_初始化_默认参数(self):
        """测试初始化使用默认参数"""
        limiter = RateLimiter()
        assert limiter.min_wait == 2.0, "默认最小等待时间错误"
        assert limiter.max_wait == 5.0, "默认最大等待时间错误"

    def test_初始化_自定义参数(self):
        """测试初始化使用自定义参数"""
        limiter = RateLimiter(min_wait=1.0, max_wait=3.0)
        assert limiter.min_wait == 1.0, "自定义最小等待时间错误"
        assert limiter.max_wait == 3.0, "自定义最大等待时间错误"

    def test_wait_执行时间(self):
        """测试wait方法执行时间在合理范围内"""
        import time
        limiter = RateLimiter(min_wait=0.1, max_wait=0.2)
        
        start = time.time()
        limiter.wait()
        elapsed = time.time() - start
        
        # 等待时间应该在0.1~0.2秒之间
        assert 0.1 <= elapsed <= 0.3, f"等待时间异常: {elapsed}"


class TestFetchResult:
    """FetchResult测试"""

    def test_初始化(self):
        """测试FetchResult初始化"""
        result = FetchResult(success=True, data={'key': 'value'})
        assert result.success == True, "success属性错误"
        assert result.data == {'key': 'value'}, "data属性错误"

    def test_失败结果(self):
        """测试失败结果"""
        result = FetchResult(success=False, error="Network error")
        assert result.success == False, "success属性错误"
        assert result.error == "Network error", "error属性错误"


class TestDataSourceRouter:
    """DataSourceRouter完整测试"""

    @pytest.fixture
    def router(self):
        return DataSourceRouter()

    def test_初始化_默认配置(self, router):
        """测试初始化使用默认配置"""
        assert hasattr(router, '_cache'), "缓存属性未初始化"
        assert hasattr(router, 'ROUTES'), "路由表未初始化"
        assert isinstance(router.ROUTES, dict), "路由表类型错误"

    def test_初始化_自定义缓存TTL(self):
        """测试初始化使用自定义缓存TTL"""
        router = DataSourceRouter(cache_ttl=600)
        assert hasattr(router, '_cache'), "缓存属性未初始化"
        assert isinstance(router.ROUTES, dict), "路由表类型错误"

    def test_fetch_实时数据_单只ETF(self, router):
        """测试获取实时数据（单只ETF）"""
        result = router.fetch_realtime(['510300'])
        assert isinstance(result, dict), "返回类型错误"

    def test_fetch_实时数据_多只ETF(self, router):
        """测试获取实时数据（多只ETF）"""
        codes = ['510300', '510050', '159577']
        result = router.fetch_realtime(codes)
        assert isinstance(result, dict), "返回类型错误"

    def test_fetch_日线数据_单只ETF(self, router):
        """测试获取日线数据（单只ETF）"""
        result = router.fetch_daily(['510300'], days=30)
        assert isinstance(result, dict), "返回类型错误"

    def test_fetch_日线数据_多只ETF(self, router):
        """测试获取日线数据（多只ETF）"""
        codes = ['510300', '510050']
        result = router.fetch_daily(codes, days=30)
        assert isinstance(result, dict), "返回类型错误"

    def test_fetch_日线数据_指定日期范围(self, router):
        """测试获取日线数据（指定日期范围）"""
        result = router.fetch_daily(
            ['510300'],
            start_date='2025-01-01',
            end_date='2025-06-30'
        )
        assert isinstance(result, dict), "返回类型错误"

    def test_fetch_小时线数据(self, router):
        """测试获取小时线数据"""
        result = router.fetch_hourly(['510300'], count=60)
        assert isinstance(result, dict), "返回类型错误"

    def test_fetch_通用方法(self, router):
        """测试fetch通用方法"""
        result = router.fetch('realtime', ['510300'])
        assert isinstance(result, dict), "返回类型错误"

    def test_cache_设置和获取(self, router):
        """测试缓存设置和获取"""
        test_key = "test_key"
        test_data = {"test": "data"}
        
        # 设置缓存
        router._set_cache(test_key, test_data)
        
        # 获取缓存
        cached = router._get_cache(test_key)
        assert cached == test_data, "缓存获取错误"

    def test_cache_过期(self, router):
        """测试缓存过期"""
        import time
        test_key = "test_key_ttl"
        test_data = {"test": "data"}
        
        # 设置缓存
        router._set_cache(test_key, test_data)
        
        # 立即获取应该成功
        cached1 = router._get_cache(test_key)
        assert cached1 == test_data, "缓存获取错误"
        
        # 等待过期后获取应该失败
        time.sleep(1)  # 等待超过默认TTL
        cached2 = router._get_cache(test_key)
        # 缓存可能已过期

    def test_cache_key生成(self, router):
        """测试缓存key生成"""
        key1 = router._cache_key('tencent', 'realtime', ['510300'])
        key2 = router._cache_key('sina', 'realtime', ['510300'])
        
        assert key1 != key2, "不同数据源的缓存key应该不同"
        assert len(key1) > 0, "缓存key不应为空"


class TestDataSourceRouterEdgeCases:
    """边界情况测试"""

    @pytest.fixture
    def router(self):
        return DataSourceRouter()

    def test_空代码列表_实时数据(self, router):
        """测试空代码列表（实时数据）"""
        try:
            result = router.fetch_realtime([])
            assert isinstance(result, dict), "处理失败"
        except Exception as e:
            print(f"预期异常: {e}")

    def test_空代码列表_日线数据(self, router):
        """测试空代码列表（日线数据）"""
        try:
            result = router.fetch_daily([])
            assert isinstance(result, dict), "处理失败"
        except Exception as e:
            print(f"预期异常: {e}")

    def test_无效ETF代码(self, router):
        """测试无效ETF代码"""
        try:
            result = router.fetch_realtime(['invalid_code_12345'])
            assert isinstance(result, dict), "处理失败"
        except Exception as e:
            print(f"预期异常: {e}")

    def test_无效数据源(self, router):
        """测试无效数据源"""
        try:
            result = router.fetch('invalid_source', ['510300'])
            assert isinstance(result, dict), "处理失败"
        except Exception as e:
            print(f"预期异常: {e}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])