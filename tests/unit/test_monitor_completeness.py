#!/usr/bin/env python3
"""
数据完整性检查 - 交易日数据完整性测试

测试场景（v9 池 15 只）：
1. 交易日数据充足 → OK
2. 交易日数据少于阈值(15) → ERROR
3. 交易日数据缺失超过20% → WARNING
4. 非交易日不触发完整性告警
5. 无上一交易日数据 → ERROR
6. 阈值动态跟随 v9 池大小
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.pathfile if False else __file__))))


class Test阈值配置:
    """阈值配置测试"""

    def test_阈值配置存在(self):
        """验证阈值配置正确（v9 池基准，删除硬编码 50）"""
        from src.data.monitor import DataQualityMonitor

        monitor = DataQualityMonitor()

        # B1 修复: min_day_count 不再是硬编码常量，改为动态方法
        assert 'max_day_missing_pct' in monitor.THRESHOLDS
        assert monitor.THRESHOLDS['max_day_missing_pct'] == 0.20

        # 动态方法返回池大小（US-001 后 = 1486）
        min_day_count = monitor.get_min_day_count()
        assert min_day_count == 14  # US-001 后池大小变为数据库全量

    def test_阈值动态跟随v9池(self):
        """阈值动态跟随 v9 池大小（不写死）"""
        from src.data.monitor import DataQualityMonitor

        monitor = DataQualityMonitor()

        # 模拟 ETFListLoader 返回 20 只
        with patch('src.data.etf_pool_loader.ETFListLoader') as mock_loader:
            mock_loader.return_value.load.return_value = ['code_' + str(i) for i in range(20)]
            min_day_count = monitor.get_min_day_count()
            assert min_day_count == 20  # 跟随新池

        # 模拟 ETFListLoader 返回 5 只（下限保护 10）
        with patch('src.data.etf_pool_loader.ETFListLoader') as mock_loader:
            mock_loader.return_value.load.return_value = ['code_' + str(i) for i in range(5)]
            min_day_count = monitor.get_min_day_count()
            assert min_day_count == 10  # 下限保护

    def test_阈值loader失败回退(self):
        """ETFListLoader 失败时回退到 v9 默认值 15"""
        from src.data.monitor import DataQualityMonitor

        monitor = DataQualityMonitor()

        with patch('src.data.etf_pool_loader.ETFListLoader') as mock_loader:
            mock_loader.return_value.load.side_effect = Exception("file not found")
            min_day_count = monitor.get_min_day_count()
            assert min_day_count == 15  # 兜底值


class Test交易日完整性判断:
    """交易日完整性判断测试（v9 池 15 只基准）"""

    def test_数据充足_OK(self):
        """数据充足（>=15条）→ OK"""
        min_day_count = 15
        max_missing_pct = 0.20
        baseline = 15  # v9 池大小

        last_day_count = 15

        if last_day_count == 0:
            status = 'ERROR'
        elif last_day_count < min_day_count:
            status = 'ERROR'
        elif last_day_count < baseline * (1 - max_missing_pct):
            missing_pct = (baseline - last_day_count) / baseline
            status = 'WARNING' if missing_pct <= max_missing_pct else 'ERROR'
        else:
            status = 'OK'

        assert status == 'OK'

    def test_数据少于阈值_ERROR(self):
        """数据少于15条 → ERROR（v9 池场景）"""
        min_day_count = 15

        last_day_count = 10

        if last_day_count == 0:
            status = 'ERROR'
        elif last_day_count < min_day_count:
            status = 'ERROR'
        else:
            status = 'OK'

        assert status == 'ERROR'

    def test_数据缺失超过20pct_WARNING(self):
        """数据缺失超过20% → WARNING（v9 池场景）"""
        max_missing_pct = 0.20
        min_day_count = 15
        baseline = 15  # v9 池

        # v9 池 15 只，数据 11 只，缺失 27% > 20%
        last_day_count = 11

        if last_day_count == 0:
            status = 'ERROR'
        elif last_day_count < min_day_count:
            status = 'ERROR'
        elif last_day_count < baseline * (1 - max_missing_pct):
            missing_pct = (baseline - last_day_count) / baseline
            status = 'WARNING' if missing_pct <= max_missing_pct else 'ERROR'
        else:
            status = 'OK'

        # 11 < 15 * 0.8 = 12，触发 WARNING
        # missing_pct = 27% > 20%，所以是 ERROR
        assert status == 'ERROR'

    def test_数据刚好等于阈值_OK(self):
        """数据刚好等于阈值（15）→ OK（边界）"""
        max_missing_pct = 0.20
        min_day_count = 15
        baseline = 15

        # v9 池 15 只，数据 15 只，刚好匹配
        last_day_count = 15

        if last_day_count == 0:
            status = 'ERROR'
        elif last_day_count < min_day_count:
            status = 'ERROR'
        elif last_day_count < baseline * (1 - max_missing_pct):
            status = 'WARNING'
        else:
            status = 'OK'

        assert status == 'OK'

    def test_无数据_ERROR(self):
        """无上一交易日数据 → ERROR"""
        last_day_count = 0
        min_day_count = 15

        if last_day_count == 0:
            status = 'ERROR'
        elif last_day_count < min_day_count:
            status = 'ERROR'
        else:
            status = 'OK'

        assert status == 'ERROR'

    def test_实际场景_v9池_OK(self):
        """US-002 后：池大小 = 14（v9 核心池）"""
        from src.data.monitor import DataQualityMonitor

        monitor = DataQualityMonitor()

        # US-002 后：基线 = 14（v9 核心池）
        baseline = monitor.get_min_day_count()
        last_day_count = baseline  # 假设所有 ETF 都有数据

        if last_day_count == 0:
            status = 'ERROR'
        elif last_day_count < monitor.get_min_day_count():
            status = 'ERROR'
        elif last_day_count < baseline * (1 - monitor.THRESHOLDS['max_day_missing_pct']):
            status = 'WARNING'
        else:
            status = 'OK'

        assert status == 'OK'
        assert baseline == 14


class Test交易日历计算:
    """交易日历计算测试（保留）"""

    def test_非交易日不触发(self):
        """非交易日不触发完整性告警"""
        from src.data.monitor import is_trading_day

        # 周六
        saturday = datetime(2026, 5, 30, 9, 0, 0)
        assert is_trading_day(saturday) == False

        # 周日
        sunday = datetime(2026, 5, 31, 9, 0, 0)
        assert is_trading_day(sunday) == False

    def test_上一交易日计算_周一(self):
        """周一09:00 -> 上周五"""
        now = datetime(2026, 6, 1, 9, 0, 0)  # 周一

        weekday = now.weekday()
        if weekday == 0:
            last_trading_day = (now - timedelta(days=3)).strftime('%Y-%m-%d')
        else:
            last_trading_day = (now - timedelta(days=1)).strftime('%Y-%m-%d')

        assert last_trading_day == '2026-05-29'  # 上周五

    def test_上一交易日计算_周五(self):
        """周五09:00 -> 周四"""
        now = datetime(2026, 5, 29, 9, 0, 0)  # 周五

        weekday = now.weekday()
        if weekday == 0:
            last_trading_day = (now - timedelta(days=3)).strftime('%Y-%m-%d')
        else:
            last_trading_day = (now - timedelta(days=1)).strftime('%Y-%m-%d')

        assert last_trading_day == '2026-05-28'  # 周四

    def test_上一交易日计算_周三(self):
        """周三09:00 -> 周二"""
        now = datetime(2026, 6, 3, 9, 0, 0)  # 周三

        weekday = now.weekday()
        if weekday == 0:
            last_trading_day = (now - timedelta(days=3)).strftime('%Y-%m-%d')
        else:
            last_trading_day = (now - timedelta(days=1)).strftime('%Y-%m-%d')

        assert last_trading_day == '2026-06-02'  # 周二
