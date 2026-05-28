"""
持仓执行器测试
"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.strategy.config import BacktestConfig
from src.strategy.executor import PositionExecutor


class TestPositionExecutor:
    """持仓执行器测试"""
    
    @pytest.fixture
    def config(self):
        """测试配置"""
        return BacktestConfig(
            stop_loss=-0.05,
            stop_profit=0.10,
            hold_days=5,
            max_positions=2
        )
    
    @pytest.fixture
    def executor(self, config):
        """测试执行器"""
        return PositionExecutor(config)
    
    def test_init(self, config):
        """测试初始化"""
        executor = PositionExecutor(config)
        
        assert len(executor.positions) == 0
        assert len(executor.trades) == 0
        assert executor.equity == 1.0
    
    def test_can_open(self, executor):
        """测试是否可以开仓"""
        assert executor.can_open() is True
        
        # 满仓后不能开仓
        executor.open_position("CODE1", 1.0, "2025-01-01", 0.8)
        assert executor.can_open() is True
        
        executor.open_position("CODE2", 1.0, "2025-01-01", 0.8)
        assert executor.can_open() is False
    
    def test_open_position(self, executor):
        """测试开仓"""
        result = executor.open_position("CODE1", 2.0, "2025-01-01", 0.8)
        
        assert result is True
        assert "CODE1" in executor.positions
        assert executor.positions["CODE1"].entry_price == 2.0
        assert executor.positions["CODE1"].entry_date == "2025-01-01"
        assert executor.positions["CODE1"].entry_score == 0.8
        
        # 检查交易记录
        assert len(executor.trades) == 1
        assert executor.trades[0]['action'] == 'buy'
        assert executor.trades[0]['code'] == 'CODE1'
    
    def test_open_position_max_reached(self, executor):
        """测试满仓后不能开仓"""
        executor.open_position("CODE1", 1.0, "2025-01-01", 0.8)
        executor.open_position("CODE2", 1.0, "2025-01-01", 0.8)
        
        result = executor.open_position("CODE3", 1.0, "2025-01-01", 0.8)
        
        assert result is False
        assert "CODE3" not in executor.positions
    
    def test_check_stop_loss_triggered(self, executor):
        """测试止损触发"""
        executor.open_position("CODE1", 1.0, "2025-01-01", 0.8)
        
        # 亏损6%（触发-5%止损）
        result = executor.check_and_close("CODE1", 0.94, "2025-01-03")
        
        assert result is not None
        assert result['exit_reason'] == '止损'
        assert result['pnl_pct'] == pytest.approx(-0.06, rel=0.01)
    
    def test_check_stop_profit_triggered(self, executor):
        """测试止盈触发"""
        executor.open_position("CODE1", 1.0, "2025-01-01", 0.8)
        
        # 盈利12%（触发+10%止盈）
        result = executor.check_and_close("CODE1", 1.12, "2025-01-10")
        
        assert result is not None
        assert result['exit_reason'] == '止盈'
        assert result['pnl_pct'] == pytest.approx(0.12, rel=0.01)
    
    def test_check_hold_days_triggered(self, executor):
        """测试到期触发"""
        executor.open_position("CODE1", 1.0, "2025-01-01", 0.8)
        
        # 持仓5天内不会触发
        for i in range(4):
            result = executor.check_and_close("CODE1", 1.0, f"2025-01-0{i+2}")
            assert result is None
        
        # 第5天持仓到期，应该触发
        result = executor.check_and_close("CODE1", 1.0, "2025-01-06")
        
        assert result is not None
        assert result['exit_reason'] == '到期'
    
    def test_check_no_trigger(self, executor):
        """测试未触发"""
        executor.open_position("CODE1", 1.0, "2025-01-01", 0.8)
        
        # 小幅盈利（未触发止盈止损）
        result = executor.check_and_close("CODE1", 1.03, "2025-01-02")
        
        assert result is None
        assert "CODE1" in executor.positions
    
    def test_check_position_not_found(self, executor):
        """测试持仓不存在"""
        result = executor.check_and_close("NOTFOUND", 1.0, "2025-01-01")
        
        assert result is None
    
    def test_close_all(self, executor):
        """测试期末平仓"""
        # 使用新实例避免状态污染
        exec1 = PositionExecutor(executor.config)
        exec1.open_position("CODE1", 1.0, "2025-01-01", 0.8)
        exec1.open_position("CODE2", 2.0, "2025-01-02", 0.7)
        
        prices = {"CODE1": 1.1, "CODE2": 2.2}
        exec1.close_all(prices, "2025-12-31")
        
        assert len(exec1.positions) == 0
        
        # 检查交易记录
        sell_trades = [t for t in exec1.trades if t['action'] == 'sell']
        assert len(sell_trades) == 2
        assert all(t['exit_reason'] == '期末平仓' for t in sell_trades)
    
    def test_multiple_positions(self, executor):
        """测试多持仓"""
        executor.open_position("CODE1", 1.0, "2025-01-01", 0.8)
        executor.open_position("CODE2", 2.0, "2025-01-02", 0.7)
        
        assert len(executor.positions) == 2
        
        # CODE1触发止损
        result1 = executor.check_and_close("CODE1", 0.9, "2025-01-05")
        assert result1 is not None
        assert result1['exit_reason'] == '止损'
        
        # CODE2继续持有
        assert "CODE2" in executor.positions
        
        # 可以再开新仓
        result3 = executor.open_position("CODE3", 3.0, "2025-01-06", 0.9)
        assert result3 is True


class TestPositionExecutorEdgeCases:
    """边界情况测试"""
    
    def test_zero_price(self):
        """测试零价格"""
        config = BacktestConfig()
        executor = PositionExecutor(config)
        
        result = executor.open_position("CODE1", 0, "2025-01-01", 0.8)
        
        assert result is False
    
    def test_negative_price(self):
        """测试负价格"""
        config = BacktestConfig()
        executor = PositionExecutor(config)
        
        result = executor.open_position("CODE1", -1.0, "2025-01-01", 0.8)
        
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])