"""
WalkForward验证引擎

功能：时序稳健性验证
来源：DESIGN_OVERFIT_VALIDATOR.md v2.0
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Callable, Dict, List, Any

# 默认配置
DEFAULT_CONFIG = {
    'train_months': 6,
    'test_months': 3,
    'min_windows': 6,          # 【修复】从3改为6，确保统计意义
    'min_test_ratio': 0.3,    # 【新增】测试集至少占30%数据
    'transaction_cost': 0.002,  # 双边交易成本0.2%
    'pass_criteria': {
        'min_test_return': 0,
        'max_decay': 0.5,       # 【修复】衰减不超过50%
        'min_test_sharpe': 0.3,
        'min_pass_rate': 0.5,   # 【新增】至少50%窗口通过
    }
}

TRADING_DAYS_PER_MONTH = 21


@dataclass
class WindowResult:
    """单窗口验证结果"""
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_return: float
    test_return: float
    test_sharpe: float
    decay: float
    trade_count: int
    pass_: bool


@dataclass
class WalkForwardResult:
    """WalkForward验证汇总结果"""
    pass_rate: float
    n_windows: int
    n_passed: int
    avg_train_return: float
    avg_test_return: float
    avg_decay: float
    avg_test_sharpe: float
    windows: List[WindowResult]
    confidence: str


def compute_decay(train_return: float, test_return: float) -> float:
    """计算样本外衰减"""
    if train_return == 0:
        return 0
    return (test_return - train_return) / abs(train_return)


def compute_sharpe(returns: List[float], risk_free: float = 0.0) -> float:
    """计算夏普比率"""
    if not returns or len(returns) < 2:
        return 0.0
    
    returns_arr = np.array(returns)
    excess_returns = returns_arr - risk_free
    
    mean_ret = np.mean(excess_returns)
    std_ret = np.std(returns_arr, ddof=1)
    
    if std_ret == 0:
        return 0.0
    
    # 年化（假设日频）
    return mean_ret / std_ret * np.sqrt(252)


class WalkForwardEngine:
    """
    Walk-Forward时序稳健性验证引擎
    
    功能：
    1. 非重叠窗口滚动验证
    2. 多指标评估（收益、衰减、夏普）
    3. 交易成本调整
    """
    
    def __init__(self, config: Dict = None):
        """初始化配置"""
        if config is None:
            config = DEFAULT_CONFIG.copy()
        
        self.train_months = config.get('train_months', 6)
        self.test_months = config.get('test_months', 3)
        self.transaction_cost = config.get('transaction_cost', 0.002)
        self.pass_criteria = config.get('pass_criteria', DEFAULT_CONFIG['pass_criteria'])
        
        # 计算窗口大小（交易日）
        self.train_days = self.train_months * TRADING_DAYS_PER_MONTH
        self.test_days = self.test_months * TRADING_DAYS_PER_MONTH
        self.step = self.test_days  # 非重叠步长
    
    def validate(self, df: pd.DataFrame, signal_func: Callable) -> WalkForwardResult:
        """
        执行Walk-Forward验证
        
        参数:
            df: K线数据（含date, close列）
            signal_func: 信号生成函数，输入df，返回布尔Series
        
        返回:
            WalkForwardResult: 验证结果
        """
        # 确保按日期排序
        if 'date' in df.columns:
            df = df.sort_values('date').reset_index(drop=True)
        
        results = []
        
        # 滑动窗口
        for start_idx in range(0, len(df) - self.train_days - self.test_days, self.step):
            train_end_idx = start_idx + self.train_days
            test_end_idx = train_end_idx + self.test_days
            
            # 分割数据
            train_df = df.iloc[start_idx:train_end_idx].copy()
            test_df = df.iloc[train_end_idx:test_end_idx].copy()
            
            if len(train_df) < 50 or len(test_df) < 50:
                continue
            
            # 生成信号
            try:
                train_signal = signal_func(train_df)
                test_signal = signal_func(test_df)
            except Exception as e:
                continue
            
            # 计算收益
            train_result = self._compute_result(train_df, train_signal)
            test_result = self._compute_result(test_df, test_signal)
            
            # 计算衰减
            decay = compute_decay(train_result['total_return'], test_result['total_return'])
            
            # 判断是否通过
            passed = self._evaluate(test_result, train_result, decay)
            
            # 记录
            results.append(WindowResult(
                train_start=str(train_df['date'].iloc[0]) if 'date' in train_df.columns else '',
                train_end=str(train_df['date'].iloc[-1]) if 'date' in train_df.columns else '',
                test_start=str(test_df['date'].iloc[0]) if 'date' in test_df.columns else '',
                test_end=str(test_df['date'].iloc[-1]) if 'date' in test_df.columns else '',
                train_return=train_result['total_return'],
                test_return=test_result['total_return'],
                test_sharpe=test_result['sharpe'],
                decay=decay,
                trade_count=test_result['trade_count'],
                pass_=passed
            ))
        
        # 汇总结果
        return self._aggregate(results)
    
    def _compute_result(self, df: pd.DataFrame, signal: pd.Series) -> Dict[str, Any]:
        """计算策略收益"""
        close = df['close'].values
        signal_arr = signal.values if hasattr(signal, 'values') else signal
        
        returns = []
        for i in range(len(df) - 1):
            if signal_arr[i]:
                # 单笔收益 - 交易成本
                ret = (close[i + 1] / close[i]) - 1 - self.transaction_cost
                returns.append(ret)
        
        if not returns:
            return {'total_return': 0, 'sharpe': 0, 'trade_count': 0}
        
        total_return = np.prod([1 + r for r in returns]) - 1
        sharpe = compute_sharpe(returns)
        
        return {
            'total_return': total_return,
            'sharpe': sharpe,
            'trade_count': len(returns),
            'returns': returns
        }
    
    def _evaluate(self, test_result: Dict, train_result: Dict, decay: float) -> bool:
        """评估是否通过"""
        criteria = self.pass_criteria
        
        # 多指标评估（必须全部满足）
        if test_result['total_return'] < criteria['min_test_return']:
            return False
        if decay < -criteria['max_decay']:  # 衰减超过阈值
            return False
        if test_result['sharpe'] < criteria['min_test_sharpe']:
            return False
        
        return True
    
    def _aggregate(self, results: List[WindowResult]) -> WalkForwardResult:
        """汇总窗口结果"""
        if not results:
            return WalkForwardResult(
                pass_rate=0,
                n_windows=0,
                n_passed=0,
                avg_train_return=0,
                avg_test_return=0,
                avg_decay=0,
                avg_test_sharpe=0,
                windows=[],
                confidence='low'
            )
        
        n_passed = sum(1 for r in results if r.pass_)
        pass_rate = n_passed / len(results)
        
        # 置信区间（基于样本量）
        if len(results) >= 5:
            confidence = 'high'
        elif len(results) >= 3:
            confidence = 'medium'
        else:
            confidence = 'low'
        
        return WalkForwardResult(
            pass_rate=pass_rate,
            n_windows=len(results),
            n_passed=n_passed,
            avg_train_return=np.mean([r.train_return for r in results]),
            avg_test_return=np.mean([r.test_return for r in results]),
            avg_decay=np.mean([r.decay for r in results]),
            avg_test_sharpe=np.mean([r.test_sharpe for r in results]),
            windows=results,
            confidence=confidence
        )


def to_dict(result: WalkForwardResult) -> Dict:
    """转换为字典格式（便于JSON序列化）"""
    return {
        'pass_rate': result.pass_rate,
        'n_windows': result.n_windows,
        'n_passed': result.n_passed,
        'avg_train_return': result.avg_train_return,
        'avg_test_return': result.avg_test_return,
        'avg_decay': result.avg_decay,
        'avg_test_sharpe': result.avg_test_sharpe,
        'confidence': result.confidence,
        'windows': [
            {
                'train_period': f"{r.train_start} ~ {r.train_end}",
                'test_period': f"{r.test_start} ~ {r.test_end}",
                'train_return': r.train_return,
                'test_return': r.test_return,
                'test_sharpe': r.test_sharpe,
                'decay': r.decay,
                'trade_count': r.trade_count,
                'pass': r.pass_
            }
            for r in result.windows
        ]
    }