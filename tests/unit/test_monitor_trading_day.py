#!/usr/bin/env python3
"""
数据质量监控 - 交易日判断测试

测试场景：
1. 工作日延迟1天 → OK（正常）
2. 工作日延迟2天 → WARNING
3. 工作日延迟3天 → WARNING（延迟3天=ERROR阈值边界）
4. 周末延迟1天 → OK（正常）
5. 周末延迟2天 → OK
6. 周末延迟3天 → WARNING
7. 节假日判断需要外部补充
"""
import pytest
from datetime import datetime
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


class TestFreshness判断:
    """新鲜度告警逻辑测试"""
    
    def test_工作日_延迟1天_OK(self):
        """工作日延迟1天，正常"""
        delay = 1
        is_trade = True
        max_delay = 3
        
        if delay > max_delay:
            status = 'ERROR'
        elif is_trade and delay > 1:
            status = 'WARNING'
        elif not is_trade and delay > 2:
            status = 'WARNING'
        else:
            status = 'OK'
        
        assert status == 'OK'
    
    def test_工作日_延迟2天_WARNING(self):
        """工作日延迟2天，警告"""
        delay = 2
        is_trade = True
        max_delay = 3
        
        if delay > max_delay:
            status = 'ERROR'
        elif is_trade and delay > 1:
            status = 'WARNING'
        elif not is_trade and delay > 2:
            status = 'WARNING'
        else:
            status = 'OK'
        
        assert status == 'WARNING'
    
    def test_工作日_延迟4天_ERROR(self):
        """工作日延迟4天，错误"""
        delay = 4
        is_trade = True
        max_delay = 3
        
        if delay > max_delay:
            status = 'ERROR'
        elif is_trade and delay > 1:
            status = 'WARNING'
        elif not is_trade and delay > 2:
            status = 'WARNING'
        else:
            status = 'OK'
        
        assert status == 'ERROR'
    
    def test_周末_延迟2天_OK(self):
        """周末延迟2天，正常（周末正常情况）"""
        delay = 2
        is_trade = False
        max_delay = 3
        
        if delay > max_delay:
            status = 'ERROR'
        elif is_trade and delay > 1:
            status = 'WARNING'
        elif not is_trade and delay > 2:
            status = 'WARNING'
        else:
            status = 'OK'
        
        assert status == 'OK'
    
    def test_周末_延迟3天_WARNING(self):
        """周末延迟3天，警告（超过正常周末范围）"""
        delay = 3
        is_trade = False
        max_delay = 3
        
        if delay > max_delay:
            status = 'ERROR'
        elif is_trade and delay > 1:
            status = 'WARNING'
        elif not is_trade and delay > 2:
            status = 'WARNING'
        else:
            status = 'OK'
        
        assert status == 'WARNING'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])