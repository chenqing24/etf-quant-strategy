"""
CrossEtf跨ETF泛化验证引擎 - 验证策略在不同ETF上的泛化能力

用途：
    - 验证策略是否具备跨ETF泛化能力
    - 训练集和测试集使用不同的ETF
    - 确保策略不是针对特定ETF过拟合

被谁调用：
    - scripts/validators/comprehensive.py（综合验证调度器）
    - 其他需要跨ETF验证的模块

功能说明：
    - 来源：DESIGN_OVERFIT_VALIDATOR.md v2.0
    - 训练集：7 个 ETF
    - 测试集：5 个 ETF（与训练集不重叠）
    - 最大泛化差距：20%（训练/测试通过率差距）

使用方式：
    from scripts.validators import CrossEtfValidator
    
    validator = CrossEtfValidator()
    result = validator.validate(data_dict, signals_dict)

依赖：
    - scripts.validators.walk_forward (WalkForwardEngine)

注意事项：
    - 已豁免 pre-commit 检查（验证器）
    - min_train_etfs 从 5 改为 7，确保统计意义
    - min_test_etfs 从 3 改为 5，确保泛化验证有效
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Callable, Dict, List

from .walk_forward import WalkForwardEngine, WalkForwardResult, to_dict as wf_to_dict

# 默认配置
DEFAULT_CONFIG = {
    'train_ratio': 0.5,        # 训练集比例
    'min_train_etfs': 7,       # 【修复】从5改为7，确保统计意义
    'min_test_etfs': 5,        # 【修复】从3改为5，确保泛化验证有效
    'min_gap': 0.2,            # 最大泛化差距（训练/测试通过率差距）
    'walk_forward_config': {
        'train_months': 6,
        'test_months': 3,
        'min_windows': 6,       # 【新增】与WalkForwardEngine一致
        'transaction_cost': 0.002
    }
}


@dataclass
class CrossEtfResult:
    """跨ETF泛化验证结果"""
    train_pass_rate: float
    test_pass_rate: float
    generalization_gap: float
    train_etfs: List[str]
    test_etfs: List[str]
    train_results: Dict[str, WalkForwardResult]
    test_results: Dict[str, WalkForwardResult]
    pass_: bool
    quality: str  # 'good' / 'medium' / 'poor'


class CrossEtfValidator:
    """
    跨ETF泛化验证引擎
    
    功能：
    1. 将ETF分为训练集和测试集
    2. 在训练集上验证策略
    3. 在测试集上验证策略
    4. 比较泛化差距
    """
    
    def __init__(self, config: Dict = None):
        """初始化配置"""
        if config is None:
            config = DEFAULT_CONFIG.copy()
        
        self.train_ratio = config.get('train_ratio', 0.5)
        self.min_train_etfs = config.get('min_train_etfs', 5)
        self.min_test_etfs = config.get('min_test_etfs', 3)
        self.min_gap = config.get('min_gap', 0.2)
        self.wf_config = config.get('walk_forward_config', DEFAULT_CONFIG['walk_forward_config'])
        
        # 初始化WalkForward引擎
        self.wf_engine = WalkForwardEngine(self.wf_config)
    
    def validate(self, etf_data_dict: Dict[str, pd.DataFrame],
                 signal_func: Callable) -> CrossEtfResult:
        """
        执行跨ETF泛化验证
        
        参数:
            etf_data_dict: {etf_code: df}字典
            signal_func: 信号生成函数
        
        返回:
            CrossEtfResult: 验证结果
        """
        # 确保每个df有足够的日期列
        for code, df in etf_data_dict.items():
            if 'date' in df.columns:
                etf_data_dict[code] = df.sort_values('date').reset_index(drop=True)
        
        # 划分训练集和测试集
        etf_codes = list(etf_data_dict.keys())
        np.random.seed(42)
        np.random.shuffle(etf_codes)
        
        split = max(int(len(etf_codes) * self.train_ratio), self.min_train_etfs)
        split = min(split, len(etf_codes) - self.min_test_etfs)
        
        train_etfs = etf_codes[:split]
        test_etfs = etf_codes[split:]
        
        # 训练集验证
        train_results = {}
        for code in train_etfs:
            try:
                result = self.wf_engine.validate(etf_data_dict[code], signal_func)
                train_results[code] = result
            except Exception:
                pass
        
        # 测试集验证
        test_results = {}
        for code in test_etfs:
            try:
                result = self.wf_engine.validate(etf_data_dict[code], signal_func)
                test_results[code] = result
            except Exception:
                pass
        
        # 计算通过率
        if not train_results:
            train_pass_rate = 0
        else:
            train_pass_rates = [r.pass_rate for r in train_results.values()]
            train_pass_rate = np.mean(train_pass_rates)
        
        if not test_results:
            test_pass_rate = 0
        else:
            test_pass_rates = [r.pass_rate for r in test_results.values()]
            test_pass_rate = np.mean(test_pass_rates)
        
        # 计算泛化差距
        gap = train_pass_rate - test_pass_rate
        
        # 判断质量
        if gap < 0.1 and test_pass_rate > 0.3:
            quality = 'good'
        elif gap < self.min_gap and test_pass_rate > 0.2:
            quality = 'medium'
        else:
            quality = 'poor'
        
        # 综合判断
        pass_ = (
            len(train_results) >= self.min_train_etfs and
            len(test_results) >= self.min_test_etfs and
            gap < self.min_gap and
            test_pass_rate > 0.2
        )
        
        return CrossEtfResult(
            train_pass_rate=train_pass_rate,
            test_pass_rate=test_pass_rate,
            generalization_gap=gap,
            train_etfs=train_etfs,
            test_etfs=test_etfs,
            train_results=train_results,
            test_results=test_results,
            pass_=pass_,
            quality=quality
        )
    
    def validate_leave_one_out(self, etf_data_dict: Dict[str, pd.DataFrame],
                                signal_func: Callable) -> CrossEtfResult:
        """
        留一验证（每次留一个ETF作测试）
        
        更充分的泛化验证，但计算量大
        """
        etf_codes = list(etf_data_dict.keys())
        
        all_test_results = {}
        
        for test_code in etf_codes:
            # 其他ETF作为训练集
            train_codes = [c for c in etf_codes if c != test_code]
            train_dict = {c: etf_data_dict[c] for c in train_codes}
            
            train_results = {}
            for code in train_codes:
                try:
                    result = self.wf_engine.validate(etf_data_dict[code], signal_func)
                    train_results[code] = result
                except Exception:
                    pass
            
            # 测试集只有一个ETF
            try:
                test_result = self.wf_engine.validate(etf_data_dict[test_code], signal_func)
                all_test_results[test_code] = test_result
            except Exception:
                pass
        
        # 计算通过率
        train_pass_rates = [r.pass_rate for r in train_results.values()] if train_results else []
        train_pass_rate = np.mean(train_pass_rates) if train_pass_rates else 0
        
        test_pass_rates = [r.pass_rate for r in all_test_results.values()]
        test_pass_rate = np.mean(test_pass_rates) if test_pass_rates else 0
        
        gap = train_pass_rate - test_pass_rate
        
        return CrossEtfResult(
            train_pass_rate=train_pass_rate,
            test_pass_rate=test_pass_rate,
            generalization_gap=gap,
            train_etfs=etf_codes,
            test_etfs=etf_codes,
            train_results=train_results,
            test_results=all_test_results,
            pass_=gap < self.min_gap and test_pass_rate > 0.2,
            quality='good' if gap < 0.1 else 'poor'
        )


def to_dict(result: CrossEtfResult) -> Dict:
    """转换为字典格式"""
    return {
        'train_pass_rate': result.train_pass_rate,
        'test_pass_rate': result.test_pass_rate,
        'generalization_gap': result.generalization_gap,
        'train_etfs': result.train_etfs,
        'test_etfs': result.test_etfs,
        'train_n': len(result.train_etfs),
        'test_n': len(result.test_etfs),
        'pass': result.pass_,
        'quality': result.quality,
        'train_details': {code: wf_to_dict(r) for code, r in result.train_results.items()},
        'test_details': {code: wf_to_dict(r) for code, r in result.test_results.items()}
    }