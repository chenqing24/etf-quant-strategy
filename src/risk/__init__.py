"""
P0-2: 风控模块

功能:
- 错误码定义
- 风控配置类型
- 风控管理器

版本: 1.0
"""
from .errors import (
    RiskError,
    ConfigNotFoundError,
    ConfigFormatError,
    ConfigVersionError,
    RiskLimitError,
    PositionLimitError,
    LossLimitError,
    StopLossError,
    StopProfitError,
    HoldDaysLimitError,
    ERROR_CODE_TABLE
)
from .config_types import RiskConfig
from .manager import (
    RiskManager,
    CheckResult,
    ExitSignal,
    Position,
    Portfolio
)

__all__ = [
    # 错误类
    'RiskError',
    'ConfigNotFoundError',
    'ConfigFormatError',
    'ConfigVersionError',
    'RiskLimitError',
    'PositionLimitError',
    'LossLimitError',
    'StopLossError',
    'StopProfitError',
    'HoldDaysLimitError',
    'ERROR_CODE_TABLE',
    # 配置
    'RiskConfig',
    # 管理器
    'RiskManager',
    'CheckResult',
    'ExitSignal',
    'Position',
    'Portfolio',
]