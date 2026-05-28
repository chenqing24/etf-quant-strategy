"""
风控错误码定义

错误码体系:
- E1001-E1003: 配置错误
- E2001-E2003: 风控限制错误

版本: 1.0
"""


# ===== 错误码对照表 =====
ERROR_CODE_TABLE = {
    # 配置错误 (E1001-E1003)
    "E1001": "配置文件不存在",
    "E1002": "配置文件格式错误",
    "E1003": "配置版本不兼容",
    
    # 风控限制错误 (E2001-E2003)
    "E2001-01": "仓位已满，无法入场",
    "E2001-02": "总亏损超限，无法入场",
    "E2002-01": "止损触发",
    "E2002-02": "止盈触发",
    "E2002-03": "持仓天数到期"
}


# ===== 错误类定义 =====

class RiskError(Exception):
    """风控基础异常"""
    
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(message)
    
    def __repr__(self):
        return f"{self.__class__.__name__}(code={self.code}, message={self.message})"


# === 配置错误 ===

class ConfigNotFoundError(RiskError):
    """配置文件不存在 (E1001)"""
    
    def __init__(self, path: str):
        super().__init__(
            f"配置文件不存在: {path}",
            "E1001"
        )


class ConfigFormatError(RiskError):
    """配置文件格式错误 (E1002)"""
    
    def __init__(self, path: str, reason: str):
        super().__init__(
            f"配置文件格式错误: {path}, 原因: {reason}",
            "E1002"
        )


class ConfigVersionError(RiskError):
    """配置版本不兼容 (E1003)"""
    
    def __init__(self, version: str, supported: str):
        super().__init__(
            f"配置版本 {version} 不支持, 支持版本: {supported}",
            "E1003"
        )


# === 风控限制错误 ===

class RiskLimitError(RiskError):
    """风控限制触发 (E2001)"""
    pass


class PositionLimitError(RiskLimitError):
    """仓位限制触发 (E2001-01)"""
    
    def __init__(self):
        super().__init__(
            "仓位已满，无法入场",
            "E2001-01"
        )


class LossLimitError(RiskLimitError):
    """亏损限制触发 (E2001-02)"""
    
    def __init__(self):
        super().__init__(
            "总亏损超限，无法入场",
            "E2001-02"
        )


class StopLossError(RiskLimitError):
    """止损触发 (E2002-01)"""
    
    def __init__(self):
        super().__init__(
            "止损触发",
            "E2002-01"
        )


class StopProfitError(RiskLimitError):
    """止盈触发 (E2002-02)"""
    
    def __init__(self):
        super().__init__(
            "止盈触发",
            "E2002-02"
        )


class HoldDaysLimitError(RiskLimitError):
    """持仓天数限制触发 (E2002-03)"""
    
    def __init__(self):
        super().__init__(
            "持仓天数到期",
            "E2002-03"
        )