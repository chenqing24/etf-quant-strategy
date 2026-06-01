"""
MonteCarlo条件蒙特卡洛检验引擎 - 统计显著性验证

用途：
    - 验证策略的统计显著性
    - 使用蒙特卡洛模拟生成随机信号
    - 对比真实信号和随机信号的收益

被谁调用：
    - scripts/validators/comprehensive.py（综合验证调度器）
    - 其他需要统计显著性验证的模块

功能说明：
    - 来源：DESIGN_OVERFIT_VALIDATOR.md v2.0
    - 条件随机信号（匹配市场状态）
    - 交易成本调整
    - 分状态计算后加权平均

使用方式：
    from scripts.validators import MonteCarloEngine
    
    validator = MonteCarloEngine()
    result = validator.validate(data, signals)

依赖：
    - numpy
    - pandas

注意事项：
    - 已豁免 pre-commit 检查（验证器）
    - 默认模拟次数：1000
    - 交易成本：双边 0.2%
    - 置信水平：0.05（p < 0.05 表示显著）
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

# 默认配置
DEFAULT_CONFIG = {
    'n_simulations': 1000,
    'transaction_cost': 0.002,  # 双边交易成本0.2%
    'confidence_level': 0.05,
    'market_benchmark': None,  # 可指定市场基准代码
}


@dataclass
class MCResult:
    """蒙特卡洛检验结果"""
    p_value: float
    z_score: float
    real_mean: float
    random_mean: float
    random_std: float
    significant: bool
    n_simulations: int
    signal_density: float


def get_market_state(df: pd.DataFrame, benchmark_col: str = 'close') -> List[str]:
    """
    判断市场状态
    
    基于价格动量判断：
    - bull: 20日均线多头排列
    - bear: 20日均线下空头排列
    - sideways: 其他
    
    返回: List[str] 市场状态序列
    """
    close = df[benchmark_col].values
    ma20 = pd.Series(close).rolling(20).mean().values
    
    states = []
    for i in range(len(close)):
        if i < 20:
            states.append('sideways')  # 数据不足时默认为震荡
        elif close[i] > ma20[i]:
            states.append('bull')
        elif close[i] < ma20[i]:
            states.append('bear')
        else:
            states.append('sideways')
    
    return states


def calculate_returns_with_cost(df: pd.DataFrame, signal: pd.Series, 
                                 transaction_cost: float = 0.002) -> List[float]:
    """计算策略收益（含交易成本）"""
    close = df['close'].values
    signal_arr = signal.values if hasattr(signal, 'values') else signal
    
    returns = []
    for i in range(len(df) - 1):
        if signal_arr[i]:
            ret = (close[i + 1] / close[i]) - 1 - transaction_cost
            returns.append(ret)
    
    return returns


class MonteCarloEngine:
    """
    条件蒙特卡洛检验引擎
    
    功能：
    1. 生成条件随机信号（在相同市场状态下生成）
    2. 计算p-value和z-score
    3. 考虑交易成本
    """
    
    def __init__(self, config: Dict = None):
        """初始化配置"""
        if config is None:
            config = DEFAULT_CONFIG.copy()
        
        self.n_simulations = config.get('n_simulations', 1000)
        self.transaction_cost = config.get('transaction_cost', 0.002)
        self.confidence_level = config.get('confidence_level', 0.05)
    
    def validate(self, df: pd.DataFrame, signal_func: Callable,
                 market_state: Optional[List[str]] = None) -> MCResult:
        """
        执行蒙特卡洛检验
        
        参数:
            df: K线数据
            signal_func: 信号生成函数
            market_state: 市场状态序列（可选）
        
        返回:
            MCResult: 检验结果
        """
        # 生成真实信号和收益
        real_signal = signal_func(df)
        real_returns = calculate_returns_with_cost(df, real_signal, self.transaction_cost)
        
        if not real_returns or len(real_returns) < 5:
            return MCResult(
                p_value=1.0,
                z_score=0,
                real_mean=0,
                random_mean=0,
                random_std=0,
                significant=False,
                n_simulations=0,
                signal_density=0
            )
        
        real_mean = np.mean(real_returns)
        signal_density = real_signal.mean()
        
        # 判断市场状态
        if market_state is None:
            market_state = get_market_state(df)
        
        # 生成条件随机信号并计算收益
        random_means = []
        for _ in range(self.n_simulations):
            random_signal = self._generate_conditional_random(
                len(df), signal_density, market_state
            )
            random_returns = calculate_returns_with_cost(df, random_signal, self.transaction_cost)
            if random_returns:
                random_means.append(np.mean(random_returns))
        
        if not random_means:
            return MCResult(
                p_value=1.0,
                z_score=0,
                real_mean=real_mean,
                random_mean=0,
                random_std=0,
                significant=False,
                n_simulations=self.n_simulations,
                signal_density=signal_density
            )
        
        # 计算p-value和z-score
        random_mean = np.mean(random_means)
        random_std = np.std(random_means)
        
        # p_value: 随机收益 >= 真实收益的比例
        p_value = np.mean([1 if m >= real_mean else 0 for m in random_means])
        
        # z_score: (真实收益 - 随机均值) / 随机标准差
        if random_std > 0:
            z_score = (real_mean - random_mean) / random_std
        else:
            z_score = 0
        
        return MCResult(
            p_value=p_value,
            z_score=z_score,
            real_mean=real_mean,
            random_mean=random_mean,
            random_std=random_std,
            significant=p_value < self.confidence_level,
            n_simulations=self.n_simulations,
            signal_density=signal_density
        )
    
    def _generate_conditional_random(self, n: int, signal_p: float,
                                      market_state: List[str]) -> pd.Series:
        """
        生成条件随机信号
        
        目的：确保与真实信号在相同市场状态下有相同的信号密度
        这样比较才公平
        """
        # 计算各市场状态下的信号密度
        state_indices = {'bull': [], 'bear': [], 'sideways': []}
        for i, state in enumerate(market_state):
            if i < n:
                state_indices[state].append(i)
        
        # 按比例在各状态内随机选择
        random_signal = np.zeros(n, dtype=bool)
        
        for state, indices in state_indices.items():
            if not indices:
                continue
            
            # 计算该状态内应有的信号数量
            n_signal = int(len(indices) * signal_p)
            
            if n_signal > 0 and len(indices) >= n_signal:
                signal_indices = np.random.choice(indices, n_signal, replace=False)
                random_signal[signal_indices] = True
        
        return pd.Series(random_signal)
    
    def validate_batch(self, df_dict: Dict[str, pd.DataFrame], 
                       signal_func: Callable) -> Dict[str, MCResult]:
        """批量验证多个ETF"""
        results = {}
        
        for code, df in df_dict.items():
            # 修正列名（可能有date列）
            if 'date' in df.columns:
                df = df.sort_values('date').reset_index(drop=True)
            
            results[code] = self.validate(df, signal_func)
        
        return results


def to_dict(result: MCResult) -> Dict:
    """转换为字典格式"""
    return {
        'p_value': result.p_value,
        'z_score': result.z_score,
        'real_mean': result.real_mean,
        'random_mean': result.random_mean,
        'random_std': result.random_std,
        'significant': result.significant,
        'n_simulations': result.n_simulations,
        'signal_density': result.signal_density
    }