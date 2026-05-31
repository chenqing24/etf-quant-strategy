"""
ComprehensiveValidator 综合验证调度器

功能：调度三大验证引擎，综合评分
来源：DESIGN_OVERFIT_VALIDATOR.md v2.0
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from datetime import datetime

from .walk_forward import WalkForwardEngine, to_dict as wf_to_dict
from .monte_carlo import MonteCarloEngine, to_dict as mc_to_dict
from .cross_etf import CrossEtfValidator, to_dict as ce_to_dict

# 默认配置
DEFAULT_CONFIG = {
    'walk_forward': {
        'train_months': 6,
        'test_months': 3,
        'min_windows': 6,       # 【修复】与WalkForwardEngine一致
        'transaction_cost': 0.002
    },
    'monte_carlo': {
        'n_simulations': 1000,
        'transaction_cost': 0.002,
        'confidence_level': 0.05
    },
    'cross_etf': {
        'train_ratio': 0.5,
        'min_train_etfs': 7,     # 【修复】与CrossEtfValidator一致
        'min_test_etfs': 5,      # 【修复】与CrossEtfValidator一致
        'min_gap': 0.2
    },
    # 评分权重【修复】降低MC权重（因为MC得分总是1.0）
    'weights': {
        'walk_forward': 0.40,   # 【修复】从0.30改为0.40
        'monte_carlo': 0.15,    # 【修复】从0.30改为0.15
        'cross_etf': 0.35,      # 【修复】从0.30改为0.35
        'consistency': 0.10
    },
    # 通过阈值【修复】从0.5提高到0.6
    'pass_threshold': 0.6,
    # 市场基准
    'market_benchmark': '510300'
}


@dataclass
class ComprehensiveResult:
    """综合验证结果"""
    composite_score: float
    pass_: bool
    confidence: str
    
    # 各模块结果
    walk_forward_score: float
    monte_carlo_score: float
    cross_etf_score: float
    consistency: float
    
    # 详细信息
    walk_forward_details: Dict
    monte_carlo_details: Dict
    cross_etf_details: Dict
    
    # 元信息
    timestamp: str
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class ComprehensiveValidator:
    """
    综合验证调度器
    
    功能：
    1. 调度WalkForward、MonteCarlo、CrossEtf三大验证
    2. 计算综合评分
    3. 输出决策建议
    """
    
    def __init__(self, config: Dict = None):
        """初始化配置"""
        if config is None:
            config = DEFAULT_CONFIG.copy()
        
        self.config = config
        
        # 初始化子引擎
        self.wf_engine = WalkForwardEngine(config.get('walk_forward', {}))
        self.mc_engine = MonteCarloEngine(config.get('monte_carlo', {}))
        self.ce_engine = CrossEtfValidator(config.get('cross_etf', {}))
        
        self.weights = config.get('weights', DEFAULT_CONFIG['weights'])
        self.pass_threshold = config.get('pass_threshold', 0.5)
    
    def validate(self, etf_data_dict: Dict[str, pd.DataFrame],
                signal_func: Callable) -> ComprehensiveResult:
        """
        执行综合验证
        
        参数:
            etf_data_dict: {etf_code: df}字典
            signal_func: 信号生成函数
        
        返回:
            ComprehensiveResult: 综合验证结果
        """
        warnings = []
        results = {}
        
        # Step 1: WalkForward验证（对每个ETF）
        wf_results = {}
        for code, df in etf_data_dict.items():
            try:
                if 'date' in df.columns:
                    df = df.sort_values('date').reset_index(drop=True)
                result = self.wf_engine.validate(df, signal_func)
                wf_results[code] = result
            except Exception as e:
                warnings.append(f"WalkForward验证失败({code}): {str(e)}")
        
        results['walk_forward'] = wf_results
        
        # Step 2: MonteCarlo验证（对每个ETF）
        mc_results = {}
        for code, df in etf_data_dict.items():
            try:
                if 'date' in df.columns:
                    df = df.sort_values('date').reset_index(drop=True)
                result = self.mc_engine.validate(df, signal_func)
                mc_results[code] = result
            except Exception as e:
                warnings.append(f"MonteCarlo验证失败({code}): {str(e)}")
        
        results['monte_carlo'] = mc_results
        
        # Step 3: CrossEtf验证（跨ETF泛化）
        try:
            ce_result = self.ce_engine.validate(etf_data_dict, signal_func)
            results['cross_etf'] = ce_result
        except Exception as e:
            warnings.append(f"CrossEtf验证失败: {str(e)}")
            ce_result = None
        
        # Step 4: 计算综合评分
        composite = self._compute_composite_score(results)
        
        return ComprehensiveResult(
            composite_score=composite['composite_score'],
            pass_=composite['composite_score'] >= self.pass_threshold,
            confidence=composite['confidence'],
            
            walk_forward_score=composite['walk_forward_score'],
            monte_carlo_score=composite['monte_carlo_score'],
            cross_etf_score=composite['cross_etf_score'],
            consistency=composite['consistency'],
            
            walk_forward_details={code: wf_to_dict(r) for code, r in wf_results.items()},
            monte_carlo_details={code: mc_to_dict(r) for code, r in mc_results.items()},
            cross_etf_details=ce_to_dict(ce_result) if ce_result else {},
            
            timestamp=datetime.now().isoformat(),
            warnings=warnings,
            recommendations=composite.get('recommendations', [])
        )
    
    def _compute_composite_score(self, results: Dict) -> Dict:
        """计算综合评分"""
        
        # WalkForward综合通过率
        wf_results = results.get('walk_forward', {})
        if wf_results:
            wf_scores = [r.pass_rate for r in wf_results.values()]
            wf_score = np.mean(wf_scores)
            wf_pass_n = sum(1 for s in wf_scores if s >= 0.3)
        else:
            wf_scores = []
            wf_score = 0
            wf_pass_n = 0
        
        # MonteCarlo显著率
        mc_results = results.get('monte_carlo', {})
        if mc_results:
            mc_scores = [r.significant for r in mc_results.values()]
            mc_score = np.mean(mc_scores) if mc_scores else 0
            mc_sig_n = sum(1 for s in mc_scores if s)
        else:
            mc_scores = []
            mc_score = 0
            mc_sig_n = 0
        
        # CrossEtf
        ce_result = results.get('cross_etf')
        if ce_result:
            ce_score = ce_result.test_pass_rate
        else:
            ce_score = 0
        
        # 一致性（跨ETF通过率的标准差）
        if len(wf_scores) > 1:
            consistency = 1 - min(1.0, np.std(wf_scores))
        else:
            consistency = 1.0
        
        # 加权综合评分
        composite_score = (
            self.weights.get('walk_forward', 0.30) * wf_score +
            self.weights.get('monte_carlo', 0.30) * mc_score +
            self.weights.get('cross_etf', 0.30) * ce_score +
            self.weights.get('consistency', 0.10) * consistency
        )
        
        # 置信度
        n_valid = len(wf_results) + len(mc_results)
        if n_valid >= 10:
            confidence = 'high'
        elif n_valid >= 5:
            confidence = 'medium'
        else:
            confidence = 'low'
        
        # 建议
        recommendations = []
        if wf_score < 0.3:
            recommendations.append("WalkForward通过率偏低，考虑优化策略参数")
        if mc_score < 0.3:
            recommendations.append("MonteCarlo显著性偏低，策略可能无alpha")
        if ce_score < 0.2:
            recommendations.append("跨ETF泛化能力弱，策略可能过度拟合")
        if composite_score < 0.3:
            recommendations.append("综合评分过低，建议重新设计策略")
        
        return {
            'composite_score': composite_score,
            'walk_forward_score': wf_score,
            'monte_carlo_score': mc_score,
            'cross_etf_score': ce_score,
            'consistency': consistency,
            'confidence': confidence,
            'wf_pass_n': wf_pass_n,
            'mc_sig_n': mc_sig_n,
            'recommendations': recommendations
        }
    
    def decision(self, result: ComprehensiveResult) -> Dict:
        """
        基于综合评分给出决策建议
        
        决策矩阵：
        - ≥0.7: 强烈推荐
        - 0.5-0.7: 谨慎推荐
        - 0.3-0.5: 不推荐
        - <0.3: 拒绝
        """
        score = result.composite_score
        
        if score >= 0.7:
            decision = {
                'level': 'strong_recommend',
                'label': '✅强烈推荐',
                'action': '可考虑实盘',
                'risk': 'low'
            }
        elif score >= 0.5:
            decision = {
                'level': 'cautious_recommend',
                'label': '🟡谨慎推荐',
                'action': '需进一步验证',
                'risk': 'medium'
            }
        elif score >= 0.3:
            decision = {
                'level': 'not_recommend',
                'label': '⚠️不推荐',
                'action': '需重大改进',
                'risk': 'high'
            }
        else:
            decision = {
                'level': 'reject',
                'label': '❌拒绝',
                'action': '策略无效',
                'risk': 'very_high'
            }
        
        return decision


def to_dict(result: ComprehensiveResult) -> Dict:
    """转换为字典格式（便于JSON序列化）"""
    return {
        'comprehensive_result': {
            'composite_score': result.composite_score,
            'pass': result.pass_,
            'confidence': result.confidence
        },
        'component_scores': {
            'walk_forward': result.walk_forward_score,
            'monte_carlo': result.monte_carlo_score,
            'cross_etf': result.cross_etf_score,
            'consistency': result.consistency
        },
        'details': {
            'walk_forward': result.walk_forward_details,
            'monte_carlo': result.monte_carlo_details,
            'cross_etf': result.cross_etf_details
        },
        'meta': {
            'timestamp': result.timestamp,
            'warnings': result.warnings,
            'recommendations': result.recommendations
        }
    }