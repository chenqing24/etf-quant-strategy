"""
P0-2: 风控管理器测试

验收标准:
1. 止损触发 → 持仓亏损5.01% → ExitSignal(reason="stop_loss", pnl=-5.01%)
2. 止盈触发 → 持仓盈利10% → ExitSignal(reason="stop_profit", pnl=10%)
3. 持仓到期 → 持仓4天(>=5天) → ExitSignal(reason="hold_days", days=4)
4. 仓位限制 → 已有1持仓 → CheckResult(allowed=False, code="E2001-01")
5. 亏损限制 → 总亏损>15% → CheckResult(allowed=False, code="E2001-02")
6. 正常入场 → 空仓 → CheckResult(allowed=True)
7. 多策略隔离 → 2个RiskManager实例独立
"""
import pytest
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.risk.errors import (
    RiskError,
    RiskLimitError,
    PositionLimitError,
    LossLimitError,
    StopLossError,
    StopProfitError,
    HoldDaysLimitError,
    ERROR_CODE_TABLE
)
from src.risk.manager import (
    RiskManager,
    CheckResult,
    ExitSignal,
    Position,
    Portfolio
)
from src.risk.config_types import RiskConfig


class TestRiskManagerEntryChecks:
    """入场检查测试"""
    
    @pytest.fixture
    def risk_manager(self):
        """标准风控管理器"""
        return RiskManager(
            stop_loss=-0.05,
            stop_profit=0.10,
            max_position=1,
            max_loss=-0.15,
            hold_days=5
        )
    
    def test_empty_portfolio_allowed(self, risk_manager):
        """测试: 空仓允许入场"""
        portfolio = Portfolio(
            positions=[],
            cash=10000,
            total_value=10000
        )
        
        result = risk_manager.check_entry(portfolio)
        
        assert result.allowed == True
    
    def test_single_position_max(self, risk_manager):
        """测试: 已有1持仓不允许再入场"""
        portfolio = Portfolio(
            positions=[
                Position(
                    code='510300',
                    quantity=1000,
                    avg_price=3.00,
                    current_price=3.00,
                    entry_date='2026-05-25'
                )
            ],
            cash=5000,
            total_value=8000
        )
        
        result = risk_manager.check_entry(portfolio)
        
        assert result.allowed == False
        assert result.code == "E2001-01"
    
    def test_large_loss_portfolio_rejected(self, risk_manager):
        """测试: 总亏损超过限制不允许入场"""
        # 使用 max_position=2 的风控管理器，初始空仓
        risk = RiskManager(
            stop_loss=-0.05,
            stop_profit=0.10,
            max_position=2,  # 允许2个持仓
            max_loss=-0.15,  # 最大亏损15%
            hold_days=5
        )
        
        # 初始资金10000，亏损后总价值8400（亏损16%，确保超过15%）
        # 初始空仓，只有现金和初始资金
        portfolio = Portfolio(
            positions=[],  # 空仓，不触发仓位限制
            cash=10000,
            total_value=8400,  # 总价值8400
            initial_capital=10000  # 初始资金10000，亏损16%
        )
        
        # 验证亏损超过15%
        assert portfolio.total_pnl_pct < -0.15, f"亏损{portfolio.total_pnl_pct*100:.1f}% 超过-15%，应该拒绝入场"
        
        result = risk.check_entry(portfolio)
        
        assert result.allowed == False
        assert result.code == "E2001-02"  # 亏损限制


class TestRiskManagerExitChecks:
    """退出检查测试"""
    
    @pytest.fixture
    def risk_manager(self):
        """标准风控管理器"""
        return RiskManager(
            stop_loss=-0.05,
            stop_profit=0.10,
            max_position=1,
            max_loss=-0.15,
            hold_days=5
        )
    
    def test_stop_loss_trigger(self, risk_manager):
        """测试: 止损触发 - 亏损5%以上"""
        position = Position(
            code='510300',
            quantity=1000,
            avg_price=3.00,
            current_price=2.80,  # 亏损6.67%，确保触发止损
            entry_date='2026-05-25'
        )
        
        signal = risk_manager.check_exit(position, current_price=2.80)
        
        assert signal is not None
        assert signal.reason == "stop_loss"
        assert signal.pnl < -0.05  # 确认亏损超过5%
    
    def test_stop_loss_not_trigger(self, risk_manager):
        """测试: 止损未触发 - 亏损4.99%"""
        position = Position(
            code='510300',
            quantity=1000,
            avg_price=3.00,
            current_price=2.8503,  # 亏损4.99%
            entry_date='2026-05-25'
        )
        
        signal = risk_manager.check_exit(position, current_price=2.8503)
        
        assert signal is None
    
    def test_stop_profit_trigger(self, risk_manager):
        """测试: 止盈触发 - 盈利12%（确保超过10%）"""
        position = Position(
            code='510300',
            quantity=1000,
            avg_price=3.00,
            current_price=3.36,  # 盈利12%
            entry_date='2026-05-25'
        )
        
        signal = risk_manager.check_exit(position, current_price=3.36)
        
        assert signal is not None
        assert signal.reason == "stop_profit"
        assert signal.pnl > 0.10  # 确认盈利超过10%
    
    def test_stop_profit_not_trigger(self, risk_manager):
        """测试: 止盈未触发 - 盈利5%"""
        position = Position(
            code='510300',
            quantity=1000,
            avg_price=3.00,
            current_price=3.15,  # 盈利5%
            entry_date='2026-05-25'
        )
        
        signal = risk_manager.check_exit(position, current_price=3.15)
        
        assert signal is None
    
    def test_hold_days_trigger(self, risk_manager):
        """测试: 持仓天数到期 - 持仓5天(>=5天)"""
        entry_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        
        position = Position(
            code='510300',
            quantity=1000,
            avg_price=3.00,
            current_price=3.10,  # 盈利3.3%，不触发止盈/止损
            entry_date=entry_date
        )
        
        signal = risk_manager.check_exit(position, current_price=3.10)
        
        assert signal is not None
        assert signal.reason == "hold_days"
        assert signal.days >= 5
    
    def test_hold_days_not_trigger(self, risk_manager):
        """测试: 持仓天数未到期 - 持仓3天"""
        entry_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
        
        position = Position(
            code='510300',
            quantity=1000,
            avg_price=3.00,
            current_price=3.10,
            entry_date=entry_date
        )
        
        signal = risk_manager.check_exit(position, current_price=3.10)
        
        assert signal is None
    
    def test_no_exit_needed(self, risk_manager):
        """测试: 无需退出 - 盈利2%且持仓3天"""
        entry_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
        
        position = Position(
            code='510300',
            quantity=1000,
            avg_price=3.00,
            current_price=3.06,  # 盈利2%
            entry_date=entry_date
        )
        
        signal = risk_manager.check_exit(position, current_price=3.06)
        
        assert signal is None


class TestRiskManagerFromConfig:
    """从配置创建风控管理器测试"""
    
    def test_from_config(self):
        """测试: 从RiskConfig创建RiskManager"""
        config = RiskConfig(
            stop_loss=-0.08,
            stop_profit=0.15,
            max_position=2,
            max_loss=-0.20,
            hold_days=10
        )
        
        risk = RiskManager.from_config(config)
        
        assert risk.stop_loss == -0.08
        assert risk.stop_profit == 0.15
        assert risk.max_position == 2
        assert risk.max_loss == -0.20
        assert risk.hold_days == 10


class TestPosition:
    """持仓信息测试"""
    
    def test_pnl_pct_profit(self):
        """测试: 盈利百分比计算"""
        position = Position(
            code='510300',
            quantity=1000,
            avg_price=3.00,
            current_price=3.30,
            entry_date='2026-05-25'
        )
        
        assert abs(position.pnl_pct - 0.10) < 0.001
    
    def test_pnl_pct_loss(self):
        """测试: 亏损百分比计算"""
        position = Position(
            code='510300',
            quantity=1000,
            avg_price=3.00,
            current_price=2.70,
            entry_date='2026-05-25'
        )
        
        assert abs(position.pnl_pct - (-0.10)) < 0.001
    
    def test_hold_days_calculation(self):
        """测试: 持仓天数计算"""
        entry_date = (datetime.now() - timedelta(days=4)).strftime('%Y-%m-%d')
        
        position = Position(
            code='510300',
            quantity=1000,
            avg_price=3.00,
            current_price=3.00,
            entry_date=entry_date
        )
        
        assert position.hold_days >= 4


class TestPortfolio:
    """组合信息测试"""
    
    def test_total_pnl_pct_profitable(self):
        """测试: 盈利组合的总盈亏百分比"""
        portfolio = Portfolio(
            positions=[
                Position(
                    code='510300',
                    quantity=1000,
                    avg_price=3.00,
                    current_price=3.30,  # 盈利10%
                    entry_date='2026-05-25'
                )
            ],
            cash=5000,
            total_value=8300  # 总价值包括盈利
        )
        
        assert portfolio.total_pnl_pct > 0  # 盈利状态
    
    def test_total_pnl_pct_loss(self):
        """测试: 亏损组合的总盈亏百分比"""
        portfolio = Portfolio(
            positions=[
                Position(
                    code='510300',
                    quantity=1000,
                    avg_price=3.00,
                    current_price=2.70,  # 亏损10%，市值2700
                    entry_date='2026-05-25'
                )
            ],
            cash=5000,
            total_value=7700,  # 总价值 = 现金5000 + 市值2700 = 7700
            initial_capital=8000  # 初始资金 = 现金5000 + 成本3000 = 8000
        )
        
        # 亏损 = (7700 - 8000) / 8000 = -3.75%
        assert abs(portfolio.total_pnl_pct - (-0.0375)) < 0.001


class TestErrorCodes:
    """错误码测试"""
    
    def test_error_code_table(self):
        """测试: 错误码对照表"""
        assert "E1001" in ERROR_CODE_TABLE
        assert "E1002" in ERROR_CODE_TABLE
        assert "E1003" in ERROR_CODE_TABLE
        assert "E2001-01" in ERROR_CODE_TABLE
        assert "E2001-02" in ERROR_CODE_TABLE
        assert "E2002-01" in ERROR_CODE_TABLE
        assert "E2002-02" in ERROR_CODE_TABLE
        assert "E2002-03" in ERROR_CODE_TABLE
    
    def test_config_errors(self):
        """测试: 配置错误类"""
        err = RiskError("测试错误", "TEST001")
        assert err.code == "TEST001"
        assert err.message == "测试错误"
        
        err = PositionLimitError()
        assert err.code == "E2001-01"
    
    def test_risk_limit_errors(self):
        """测试: 风控限制错误类"""
        err = StopLossError()
        assert err.code == "E2002-01"
        
        err = StopProfitError()
        assert err.code == "E2002-02"
        
        err = HoldDaysLimitError()
        assert err.code == "E2002-03"


class TestIsolation:
    """隔离测试"""
    
    def test_multiple_risk_managers_isolated(self):
        """测试: 多个风控管理器实例独立"""
        risk1 = RiskManager(stop_loss=-0.05, stop_profit=0.10)
        risk2 = RiskManager(stop_loss=-0.10, stop_profit=0.20)
        
        # 持仓1: 亏损5%，应被risk1止损，不被risk2止损
        pos1 = Position(
            code='510300',
            quantity=1000,
            avg_price=3.00,
            current_price=2.85,  # 亏损5%
            entry_date='2026-05-25'
        )
        
        # risk1触发止损（亏损5% <= -5%）
        signal1 = risk1.check_exit(pos1, 2.85)
        assert signal1 is not None
        assert signal1.reason == "stop_loss"
        
        # risk2不触发止损（亏损5% > -10%）
        pos2 = Position(
            code='510300',
            quantity=1000,
            avg_price=3.00,
            current_price=2.85,
            entry_date='2026-05-25'
        )
        signal2 = risk2.check_exit(pos2, 2.85)
        assert signal2 is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])