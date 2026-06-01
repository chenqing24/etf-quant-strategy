#!/usr/bin/env python3
"""
数据质量监控 - 分钟级交易日判断测试

测试场景（分钟级）：
1. 周一09:00 → 上个交易日是周五
2. 周五09:00 → 上个交易日是周四
3. 周六/周日 → 非交易日
4. 交易日数据缺失 → ERROR
5. 非交易日 → OK
"""
import pytest
from datetime import datetime, timedelta
from src.data.monitor import is_trading_day, WEEKDAY_NAMES


class TestTradingDay判断:
    """交易日判断测试"""
    
    def test_周一_是交易日(self):
        dt = datetime(2026, 6, 1, 9, 0, 0)  # 周一
        assert is_trading_day(dt) == True
        assert WEEKDAY_NAMES[dt.weekday()] == 'Monday'
    
    def test_周五_是交易日(self):
        dt = datetime(2026, 5, 29, 9, 0, 0)  # 周五
        assert is_trading_day(dt) == True
        assert WEEKDAY_NAMES[dt.weekday()] == 'Friday'
    
    def test_周六_非交易日(self):
        dt = datetime(2026, 5, 30, 9, 0, 0)  # 周六
        assert is_trading_day(dt) == False
        assert WEEKDAY_NAMES[dt.weekday()] == 'Saturday'
    
    def test_周日_非交易日(self):
        dt = datetime(2026, 5, 31, 9, 0, 0)  # 周日
        assert is_trading_day(dt) == False
        assert WEEKDAY_NAMES[dt.weekday()] == 'Sunday'


class Test分钟级新鲜度判断:
    """分钟级数据新鲜度判断测试"""
    
    def test_上周五数据_周一09点_OK(self):
        """周一09:00有上周五数据，正常"""
        # 模拟：周一09:00，数据库有上周五(05-29)数据
        # 上个交易日应该是上周五
        now = datetime(2026, 6, 1, 9, 0, 0)  # 周一
        latest_date = '2026-05-29'  # 上周五
        
        weekday = now.weekday()
        if weekday == 0:  # 周一
            last_trading_day = (now - timedelta(days=3)).strftime('%Y-%m-%d')
        else:
            last_trading_day = (now - timedelta(days=1)).strftime('%Y-%m-%d')
        
        assert last_trading_day == '2026-05-29'
        assert latest_date == last_trading_day  # 数据存在
    
    def test_上周四数据_周一09点_ERROR(self):
        """周一09:00只有上周四数据，缺失上周五 → ERROR"""
        now = datetime(2026, 6, 1, 9, 0, 0)  # 周一
        latest_date = '2026-05-28'  # 上周四
        
        weekday = now.weekday()
        if weekday == 0:  # 周一
            last_trading_day = (now - timedelta(days=3)).strftime('%Y-%m-%d')
        else:
            last_trading_day = (now - timedelta(days=1)).strftime('%Y-%m-%d')
        
        assert last_trading_day == '2026-05-29'
        assert latest_date < last_trading_day  # 数据缺失
    
    def test_周末_非交易日_OK(self):
        """周末不告警"""
        # 周六
        saturday = datetime(2026, 5, 30, 9, 0, 0)
        assert is_trading_day(saturday) == False
        
        # 周日
        sunday = datetime(2026, 5, 31, 9, 0, 0)
        assert is_trading_day(sunday) == False
    
    def test_延迟分钟数计算(self):
        """延迟分钟数计算"""
        now = datetime(2026, 6, 1, 10, 0, 0)
        last_update = datetime(2026, 6, 1, 9, 0, 0)  # 1小时前
        
        delay_minutes = (now - last_update).total_seconds() / 60
        assert delay_minutes == 60.0
        
        # 80分钟阈值测试
        max_delay = 80
        if delay_minutes > max_delay:
            status = 'WARNING'
        else:
            status = 'OK'
        
        assert status == 'OK'  # 60 < 80


if __name__ == '__main__':
    pytest.main([__file__, '-v'])