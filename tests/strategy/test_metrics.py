"""
绩效指标计算测试
"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from datetime import datetime
from src.strategy.metrics import MetricsCalculator


class TestMetricsCalculator:
    """绩效指标计算测试"""
    
    @pytest.fixture
    def calculator(self):
        """测试计算器"""
        return MetricsCalculator()
    
    def test_empty_trades(self, calculator):
        """测试空交易"""
        result = calculator.calculate([], "2025-01-01", "2025-12-31")
        
        assert result.total_return == 0
        assert result.trade_count == 0
    
    def test_single_profitable_trade(self, calculator):
        """测试单笔盈利交易"""
        trades = [{
            'code': 'TEST',
            'entry_date': '2025-01-01',
            'exit_date': '2025-01-10',
            'entry_price': 1.0,
            'exit_price': 1.1,
            'pnl_pct': 0.1,
            'hold_days': 9,
            'exit_reason': '止盈',
            'entry_score': 0.8
        }]
        
        result = calculator.calculate(trades, "2025-01-01", "2025-12-31")
        
        assert result.total_return == pytest.approx(0.1, rel=0.01)
        assert result.trade_count == 1
        assert result.win_rate == 1.0
    
    def test_single_losing_trade(self, calculator):
        """测试单笔亏损交易"""
        trades = [{
            'code': 'TEST',
            'entry_date': '2025-01-01',
            'exit_date': '2025-01-05',
            'entry_price': 1.0,
            'exit_price': 0.95,
            'pnl_pct': -0.05,
            'hold_days': 4,
            'exit_reason': '止损',
            'entry_score': 0.8
        }]
        
        result = calculator.calculate(trades, "2025-01-01", "2025-12-31")
        
        assert result.total_return == pytest.approx(-0.05, rel=0.01)
        assert result.win_rate == 0
    
    def test_win_rate_calculation(self, calculator):
        """测试胜率计算"""
        trades = [
            {'code': 'A', 'exit_date': '2025-01-10', 'pnl_pct': 0.1, 'hold_days': 5, 'exit_reason': '止盈', 'entry_score': 0.8, 'entry_price': 1, 'entry_date': '2025-01-01', 'exit_price': 1.1},
            {'code': 'B', 'exit_date': '2025-01-15', 'pnl_pct': -0.05, 'hold_days': 5, 'exit_reason': '止损', 'entry_score': 0.7, 'entry_price': 1, 'entry_date': '2025-01-05', 'exit_price': 0.95},
            {'code': 'C', 'exit_date': '2025-01-20', 'pnl_pct': 0.08, 'hold_days': 5, 'exit_reason': '止盈', 'entry_score': 0.9, 'entry_price': 1, 'entry_date': '2025-01-10', 'exit_price': 1.08},
            {'code': 'D', 'exit_date': '2025-01-25', 'pnl_pct': 0.02, 'hold_days': 5, 'exit_reason': '到期', 'entry_score': 0.6, 'entry_price': 1, 'entry_date': '2025-01-15', 'exit_price': 1.02},
        ]
        
        result = calculator.calculate(trades, "2025-01-01", "2025-12-31")
        
        assert result.win_rate == pytest.approx(0.75, rel=0.01)  # 3/4胜率
    
    def test_profit_loss_ratio(self, calculator):
        """测试盈亏比计算"""
        trades = [
            {'code': 'A', 'exit_date': '2025-01-10', 'pnl_pct': 0.1, 'hold_days': 5, 'exit_reason': '止盈', 'entry_score': 0.8, 'entry_price': 1, 'entry_date': '2025-01-01', 'exit_price': 1.1},
            {'code': 'B', 'exit_date': '2025-01-15', 'pnl_pct': -0.05, 'hold_days': 5, 'exit_reason': '止损', 'entry_score': 0.7, 'entry_price': 1, 'entry_date': '2025-01-05', 'exit_price': 0.95},
        ]
        
        result = calculator.calculate(trades, "2025-01-01", "2025-12-31")
        
        # 盈亏比 = 平均盈利 / |平均亏损|
        assert result.profit_loss_ratio == pytest.approx(2.0, rel=0.01)  # 0.1/0.05=2
        assert result.avg_profit == pytest.approx(0.1, rel=0.01)
        assert result.avg_loss == pytest.approx(-0.05, rel=0.01)
    
    def test_annual_return(self, calculator):
        """测试年化收益计算"""
        trades = [{
            'code': 'TEST',
            'entry_date': '2025-01-01',
            'exit_date': '2025-12-31',
            'entry_price': 1.0,
            'exit_price': 2.0,
            'pnl_pct': 1.0,  # 100%收益
            'hold_days': 365,
            'exit_reason': '到期',
            'entry_score': 0.8
        }]
        
        result = calculator.calculate(trades, "2025-01-01", "2025-12-31")
        
        assert result.total_return == pytest.approx(1.0, rel=0.01)
        assert result.annual_return == pytest.approx(1.0, rel=0.1)  # 约100%
    
    def test_max_drawdown(self, calculator):
        """测试最大回撤计算"""
        trades = [
            {'code': 'A', 'exit_date': '2025-01-10', 'pnl_pct': 0.1, 'hold_days': 5, 'exit_reason': '止盈', 'entry_score': 0.8, 'entry_price': 1, 'entry_date': '2025-01-01', 'exit_price': 1.1},
            {'code': 'B', 'exit_date': '2025-01-15', 'pnl_pct': -0.2, 'hold_days': 5, 'exit_reason': '止损', 'entry_score': 0.7, 'entry_price': 1, 'entry_date': '2025-01-05', 'exit_price': 0.8},
            {'code': 'C', 'exit_date': '2025-01-20', 'pnl_pct': 0.05, 'hold_days': 5, 'exit_reason': '止盈', 'entry_score': 0.9, 'entry_price': 1, 'entry_date': '2025-01-10', 'exit_price': 1.05},
        ]
        
        result = calculator.calculate(trades, "2025-01-01", "2025-12-31")
        
        # 累计收益: 1.0 → 1.1 → 0.88 → 0.924
        # 回撤: 0 → (1.1-1.1)/1.1=0 → (0.88-1.1)/1.1=-0.2 → 
        assert result.max_drawdown > 0  # 有回撤


if __name__ == "__main__":
    pytest.main([__file__, "-v"])