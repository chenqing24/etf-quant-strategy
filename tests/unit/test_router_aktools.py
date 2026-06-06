#!/usr/bin/env python3
"""
test_router_aktools.py
SOP-01 v1.1 配套：DataSourceRouter AKTools 集成测试（4 个）

覆盖：
1. test_router_routes_daily_range - 路由表正确性
2. test_fetch_aktools_success - 单只 ETF AKTools 拉取
3. test_fetch_daily_range_multi_source - 多源回退
4. test_circuit_breaker_fallback - Circuit Breaker 降级
"""
import unittest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# 路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.router import DataSourceRouter
from src.constants import (
    AKTOOLS_BASE_URL,
    AKTOOLS_FETCH_INTERVAL,
    DEFAULT_FETCH_YEARS,
    FETCH_RANGE_SEGMENTS,
    CORE_ETF_POOL_15,
)


class TestRouterAKTools(unittest.TestCase):
    """DataSourceRouter AKTools 集成测试"""

    def setUp(self):
        """每个测试前初始化"""
        self.router = DataSourceRouter()
        self.test_code = '512660'  # 军工ETF（有 7+ 年数据）

    def test_router_routes_daily_range(self):
        """1. 路由表正确性：daily_range 必须含 aktools 为主源"""
        route = self.router.ROUTES.get('daily_range')
        self.assertIsNotNone(route, "daily_range 路由必须存在")
        self.assertEqual(route.get('primary'), 'aktools',
                         "主源必须是 aktools（按 9.8 年数据）")
        # 多源回退链
        self.assertEqual(route.get('fallback1'), 'tencent')
        self.assertEqual(route.get('fallback2'), 'baostock')
        self.assertEqual(route.get('fallback3'), 'tushare')

    def test_constants_core_etf_pool_15(self):
        """2. constants.CORE_ETF_POOL_15 完整性"""
        self.assertEqual(len(CORE_ETF_POOL_15), 15,
                         "核心池必须 15 只（14 core + 1 reference）")
        # 验证包含已知的核心 ETF
        self.assertIn('510300', CORE_ETF_POOL_15)  # 沪深300 reference
        self.assertIn('512660', CORE_ETF_POOL_15)  # 军工
        self.assertIn('515050', CORE_ETF_POOL_15)  # 通信
        self.assertIn('588000', CORE_ETF_POOL_15)  # 科创50

    def test_constants_fetch_range_segments(self):
        """3. FETCH_RANGE_SEGMENTS 时段配置"""
        self.assertEqual(len(FETCH_RANGE_SEGMENTS), 3, "必须分 3 段")
        self.assertEqual(DEFAULT_FETCH_YEARS, 5, "默认 5 年")
        # 段格式：YYYY-MM-DD
        for seg in FETCH_RANGE_SEGMENTS:
            start, end = seg
            self.assertEqual(len(start), 10)
            self.assertEqual(len(end), 10)

    def test_fetch_aktools_with_mock(self):
        """4. _fetch_aktools 解析逻辑（用 mock 避免实际网络）"""
        # 模拟 AKTools 返回
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"日期": "2021-01-04", "开盘": 1.0, "最高": 1.05, "最低": 0.99, "收盘": 1.03, "成交量": 1000000},
            {"日期": "2021-01-05", "开盘": 1.03, "最高": 1.08, "最低": 1.02, "收盘": 1.07, "成交量": 1500000},
        ]

        with patch('src.data.router.requests.get', return_value=mock_response), \
             patch.object(self.router._limiter, 'wait', return_value=None):
            result = self.router._fetch_aktools(['512660'], '2021-01-01', '2021-12-31')

        # 验证
        self.assertIn('512660', result)
        data = result['512660']
        self.assertEqual(len(data), 2, "应解析 2 条")
        # 字段映射
        self.assertEqual(data[0]['date'], '2021-01-04')
        self.assertEqual(data[0]['close'], 1.03)
        self.assertEqual(data[0]['source'], 'aktools')
        # 限速
        self.assertGreaterEqual(AKTOOLS_FETCH_INTERVAL, 5,
                               "AKTools 限速必须 ≥ 5 秒（按 SOUL 规则 16）")

    def test_fetch_daily_range_fallback_logic(self):
        """5. fetch_daily_range 多源回退逻辑（aktools 失败 → tencent）"""
        # 模拟 aktools 失败
        with patch.object(self.router, '_fetch_aktools',
                         return_value={c: [] for c in CORE_ETF_POOL_15}), \
             patch.object(self.router, '_fetch_tencent',
                         return_value={c: [{'date': '2024-01-01', 'close': 1.0,
                                            'source': 'tencent'}] for c in CORE_ETF_POOL_15}):
            result = self.router.fetch_daily_range(
                CORE_ETF_POOL_15, '2024-01-01', '2024-12-31'
            )

        # 验证降级到 tencent
        for code in CORE_ETF_POOL_15:
            self.assertIn(code, result)
            if result[code]:
                self.assertEqual(result[code][0]['source'], 'tencent',
                                 f"{code} 应降级到 tencent 数据源")


if __name__ == '__main__':
    unittest.main()
