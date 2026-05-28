"""
多因子评分器测试
"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
from src.strategy.config import FactorStrategy, ScoreConfig
from src.strategy.scorer import FactorScorer


class TestFactorScorer:
    """因子评分器测试"""
    
    @pytest.fixture
    def strategy(self):
        """测试策略配置"""
        return FactorStrategy(
            name="test",
            factors=["ADX", "BB_percent", "SAR_trend", "RSI_5"],
            weights={
                "ADX": 0.5,
                "BB_percent": 0.3,
                "SAR_trend": 0.2,
                "RSI_5": 0.0  # 权重为0
            },
            direction={
                "ADX": "long",
                "BB_percent": "long",
                "SAR_trend": "long",
                "RSI_5": "neutral"  # neutral方向
            },
            score_config=ScoreConfig(threshold=0.6, min_active_factors=2)
        )
    
    @pytest.fixture
    def scorer(self, strategy):
        """测试评分器"""
        return FactorScorer(strategy)
    
    def test_init(self, strategy):
        """测试初始化"""
        scorer = FactorScorer(strategy)
        
        assert scorer.strategy is strategy
        # valid_factors 应该是 direction != 'neutral' 的因子
        assert len(scorer.valid_factors) == 3  # ADX, BB_percent, SAR_trend (DIF是neutral)
        assert len(scorer.factors) == 4  # 全部因子
    
    def test_calculate_high_adx_long(self, scorer):
        """测试ADX高分（多头方向）"""
        # ADX=60 → score=1.0
        row = pd.Series({
            'ADX': 60,
            'BB_percent': 30,
            'SAR_trend': 1
        })
        
        score, factor_scores = scorer.calculate(row)
        
        assert factor_scores['ADX'] == 1.0
        assert score > 0.5  # 综合评分应该较高
    
    def test_calculate_low_adx_long(self, scorer):
        """测试ADX低分（多头方向）"""
        # ADX=20 → score=0.4
        row = pd.Series({
            'ADX': 20,
            'BB_percent': 30,
            'SAR_trend': 1
        })
        
        score, factor_scores = scorer.calculate(row)
        
        assert factor_scores['ADX'] < 0.5  # ADX低，多头评分低
    
    def test_calculate_bb_low(self, scorer):
        """测试BB低分（多头方向，靠近下轨）"""
        # BB_percent=20 → score=(50-20)/50=0.6
        row = pd.Series({
            'ADX': 50,
            'BB_percent': 20,
            'SAR_trend': 1
        })
        
        score, factor_scores = scorer.calculate(row)
        
        assert factor_scores['BB_percent'] == 0.6
    
    def test_calculate_bb_high(self, scorer):
        """测试BB高分（多头方向，在上轨）"""
        # BB_percent=80 → score=(50-80)/50=-0.6 → 0
        row = pd.Series({
            'ADX': 50,
            'BB_percent': 80,
            'SAR_trend': 1
        })
        
        score, factor_scores = scorer.calculate(row)
        
        assert factor_scores['BB_percent'] == 0  # 限制到0
    
    def test_calculate_sar_uptrend(self, scorer):
        """测试SAR上升趋势"""
        row = pd.Series({
            'ADX': 50,
            'BB_percent': 30,
            'SAR_trend': 1
        })
        
        score, factor_scores = scorer.calculate(row)
        
        assert factor_scores['SAR_trend'] == 1
    
    def test_calculate_sar_downtrend(self, scorer):
        """测试SAR下降趋势（多头方向）"""
        row = pd.Series({
            'ADX': 50,
            'BB_percent': 30,
            'SAR_trend': 0
        })
        
        score, factor_scores = scorer.calculate(row)
        
        assert factor_scores['SAR_trend'] == 0
    
    def test_calculate_neutral_factor_ignored(self, scorer):
        """测试中性因子权重为0，不参与评分"""
        row = pd.Series({
            'ADX': 50,
            'BB_percent': 30,
            'SAR_trend': 1,
            'RSI_5': 30  # RSI_5是neutral方向，权重为0
        })
        
        score, factor_scores = scorer.calculate(row)
        
        # RSI_5不在factor_scores中（neutral且权重为0）
        assert 'RSI_5' not in factor_scores
        # 只计算有效因子的分数
        assert len(factor_scores) == 3  # ADX, BB_percent, SAR_trend
    
    def test_calculate_missing_factor(self, scorer):
        """测试缺失因子"""
        row = pd.Series({
            'ADX': 50,
            'BB_percent': 30
            # 缺少SAR_trend
        })
        
        score, factor_scores = scorer.calculate(row)
        
        assert 'SAR_trend' not in factor_scores  # 缺失因子不参与
    
    def test_calculate_full_row(self, scorer):
        """测试完整行"""
        row = pd.Series({
            'ADX': 60,
            'BB_percent': 25,
            'SAR_trend': 1,
            'RSI_5': 35,
            'close': 5.0
        })
        
        score, factor_scores = scorer.calculate(row)
        
        # ADX=60 → 1.0, BB=25 → 0.5, SAR=1 → 1.0
        # 权重: ADX=0.5, BB=0.3, SAR=0.2
        # score = 1.0*0.5 + 0.5*0.3 + 1.0*0.2 = 0.5 + 0.15 + 0.2 = 0.85
        assert 0.8 < score < 0.9
        assert len(factor_scores) == 3
    
    def test_calculate_score_range(self, scorer):
        """测试评分范围"""
        # 所有因子最高
        high_row = pd.Series({
            'ADX': 100,  # score=1.0
            'BB_percent': 0,  # score=1.0
            'SAR_trend': 1  # score=1.0
        })
        
        score_high, _ = scorer.calculate(high_row)
        assert score_high == 1.0  # 100%权重因子都满分
        
        # 所有因子最低
        low_row = pd.Series({
            'ADX': 0,  # score=0
            'BB_percent': 100,  # score=0
            'SAR_trend': 0  # score=0
        })
        
        score_low, _ = scorer.calculate(low_row)
        assert score_low == 0.0  # 所有因子都低分


class TestFactorScorerEdgeCases:
    """边界情况测试"""
    
    def test_empty_row(self):
        """测试空行"""
        strategy = FactorStrategy(
            name="test",
            factors=["ADX"],
            weights={"ADX": 1.0},
            direction={"ADX": "long"}
        )
        scorer = FactorScorer(strategy)
        row = pd.Series(dtype=float)
        
        score, factor_scores = scorer.calculate(row)
        
        assert score == 0
        assert len(factor_scores) == 0
    
    def test_nan_value(self):
        """测试NaN值"""
        strategy = FactorStrategy(
            name="test",
            factors=["ADX"],
            weights={"ADX": 1.0},
            direction={"ADX": "long"}
        )
        scorer = FactorScorer(strategy)
        row = pd.Series({'ADX': float('nan')})
        
        score, factor_scores = scorer.calculate(row)
        
        assert 'ADX' not in factor_scores


if __name__ == "__main__":
    pytest.main([__file__, "-v"])