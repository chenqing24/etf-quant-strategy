"""
多因子评分器

根据因子策略配置计算综合评分
"""
import pandas as pd
from typing import Dict, Tuple
from src.strategy.config import FactorStrategy


class FactorScorer:
    """多因子评分器"""
    
    def __init__(self, factor_strategy: FactorStrategy):
        """
        初始化
        
        Args:
            factor_strategy: 因子策略配置
        """
        self.strategy = factor_strategy
        self.factors = factor_strategy.factors
        self.weights = factor_strategy.weights
        self.direction = factor_strategy.direction
        self.valid_factors = factor_strategy.get_valid_factors()
    
    def calculate(self, row: pd.Series) -> Tuple[float, Dict[str, float]]:
        """
        计算综合评分
        
        Args:
            row: 数据行 (包含因子值)
            
        Returns:
            (综合评分, 各因子得分字典)
        """
        total_score = 0.0
        factor_scores = {}
        
        for factor in self.valid_factors:
            if pd.isna(row.get(factor)):
                continue
            
            value = row[factor]
            direction = self.direction[factor]
            weight = self.weights.get(factor, 0)
            
            # 只处理有效因子（非neutral）和有权重的因子
            if direction == 'neutral' or weight == 0:
                continue
            
            # 计算因子得分 (0~1)
            score = self._calculate_factor_score(factor, value, direction)
            factor_scores[factor] = score
            
            # 加权累加
            total_score += score * weight
        
        return total_score, factor_scores
    
    def _calculate_factor_score(
        self, 
        factor: str, 
        value: float, 
        direction: str
    ) -> float:
        """计算单个因子得分
        
        Args:
            factor: 因子名称
            value: 因子值
            direction: 因子方向 (long/short/neutral)
            
        Returns:
            因子得分 (0~1)
        """
        score = 0.5  # 默认中性
        
        if factor == 'ADX':
            # ADX高 → 强趋势
            # long方向: ADX高=高分, ADX低=低分
            # short方向: ADX低=高分
            score = min(value / 50, 1.0) if direction == 'long' else min((50 - value) / 50, 1.0)
        
        elif factor == 'BB_percent':
            # 布林带位置
            # long方向: BB低=低位=高分, BB高=高位=低分
            # 公式: score = (50 - BB_percent) / 50
            if direction == 'long':
                score = min((50 - value) / 50, 1.0)
            else:
                score = min(value / 50, 1.0)
        
        elif factor == 'SAR_trend':
            # SAR趋势值 (0或1)
            # long方向: SAR=1=上升趋势=高分
            score = value if direction == 'long' else (1 - value)
        
        elif factor == 'RSI_5':
            # RSI(5)
            # long方向: RSI低=超卖=高分
            # short方向: RSI高=超买=高分
            if direction == 'long':
                score = min((50 - value) / 50, 1.0)
            else:
                score = min(value / 50, 1.0)
        
        elif factor == 'K':
            # KDJ K值
            # short方向: K值低=超卖=高分 (做空反转)
            if direction == 'short':
                score = min((100 - value) / 100, 1.0)
            else:
                score = min(value / 100, 1.0)
        
        elif factor == 'DIF':
            # MACD DIF
            # 标准化到0~1
            # short方向: DIF高=高分 (做空超买)
            if direction == 'short':
                score = min((value + 1) / 2, 1.0)
            else:
                score = min((1 - value) / 2, 1.0)
        
        elif factor == 'OBV_diff':
            # OBV差值
            # short方向: OBV差值为负=量能不足=高分
            if direction == 'short':
                score = 0.5 - value / 2000  # 假设范围约-1000~1000
            else:
                score = 0.5 + value / 2000
        
        elif factor == 'DMA':
            # DMA差值
            # 正值=多头排列
            if value >= 0:
                score = min((value + 1) / 2, 1.0)
            else:
                score = min((1 - value) / 2, 1.0)
        
        elif factor == 'RSI_10':
            # RSI(10)
            if direction == 'long':
                score = min((50 - value) / 50, 1.0)
            else:
                score = min(value / 50, 1.0)
        
        elif factor == 'J':
            # KDJ J值
            # short方向: J值低=超卖
            if direction == 'short':
                score = min((100 - value) / 100, 1.0)
            else:
                score = min(value / 100, 1.0)
        
        elif factor == 'MACD_hist':
            # MACD柱状图
            if value >= 0:
                score = min((value + 1) / 2, 1.0)
            else:
                score = min((1 - value) / 2, 1.0)
        
        elif factor == 'DI_plus':
            # ADX DI+
            if direction == 'long':
                score = min(value / 50, 1.0)
            else:
                score = min((50 - value) / 50, 1.0)
        
        elif factor == 'DI_minus':
            # ADX DI-
            if direction == 'short':
                score = min(value / 50, 1.0)
            else:
                score = min((50 - value) / 50, 1.0)
        
        else:
            # 未知因子，使用默认评分
            score = 0.5
        
        # 限制得分范围
        return max(0, min(1, score))
    
    def calculate_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        批量计算评分
        
        Args:
            df: 数据DataFrame
            
        Returns:
            添加了score和factor_scores列的DataFrame
        """
        df = df.copy()
        scores = []
        all_factor_scores = []
        
        for _, row in df.iterrows():
            score, factor_scores = self.calculate(row)
            scores.append(score)
            all_factor_scores.append(factor_scores)
        
        df['score'] = scores
        df['factor_scores'] = all_factor_scores
        
        return df