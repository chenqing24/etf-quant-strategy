#!/usr/bin/env python3
"""选股层"""
import pandas as pd
from typing import Dict, List, Tuple, Set

from src.utils.config import StrategyConfig
from src.utils.logger import get_logger

# 配置加载器 - 从配置文件读取因子权重
try:
    from src.strategy.config_loader import load_default_strategy
    _CONFIG_LOADER_AVAILABLE = True
except ImportError:
    _CONFIG_LOADER_AVAILABLE = False

logger = get_logger()


class Selector:
    """ETF选股器"""
    
    # 类级别标志：简版模式（禁用输出）
    _simple_mode = False
    
    # 缓存的配置
    _config_cache = None
    _ic_weights_cache = None
    
    @classmethod
    def _get_ic_weights(cls) -> Dict[str, int]:
        """从配置文件获取因子权重
        
        如果配置加载失败或因子未定义，使用默认值
        """
        # 如果配置加载器不可用，返回默认值
        if not _CONFIG_LOADER_AVAILABLE:
            return cls._get_default_weights()
        
        # 使用缓存
        if cls._ic_weights_cache is not None:
            return cls._ic_weights_cache
        
        try:
            config = load_default_strategy()
            factors = config.factors
            
            # 将配置的权重转换为整数分数
            weights = {}
            default_weights = cls._get_default_weights()
            
            for factor_name, factor_weight in factors.weights.items():
                # 配置中权重是浮点数 (0.0-1.0)，转换为分数
                # 默认总分约 12 分，将权重 * 12
                weights[factor_name] = int(factor_weight * 12)
            
            # 确保所有默认因子都有值
            for key, val in default_weights.items():
                if key not in weights:
                    weights[key] = val
            
            cls._ic_weights_cache = weights
            return weights
            
        except Exception as e:
            logger.warning(f"配置加载失败，使用默认权重: {e}")
            return cls._get_default_weights()
    
    @staticmethod
    def _get_default_weights() -> Dict[str, int]:
        """默认因子权重（与原 IC_WEIGHTS 一致）"""
        return {
            'ma120': 3,      # IC最高的因子，给最高权重
            'ma60': 2,
            'ma60_up': 2,
            'ma20': 1,
            'vol': 2,
            'rsi': 1,
            'macd': 1,
        }
    
    @classmethod
    def reload_config(cls):
        """重新加载配置（清除缓存）"""
        cls._config_cache = None
        cls._ic_weights_cache = None
    
    def select_etfs(self, data: Dict[str, pd.DataFrame], 
                    config: StrategyConfig) -> Set[str]:
        """根据训练期收益选出TopN的ETF
        
        Args:
            data: 原始ETF数据
            config: 策略配置
            
        Returns:
            选中的ETF代码集合
        """
        results = []
        
        exclude_codes = config.exclude_codes or set()
        
        for code, df in data.items():
            # 排除规则
            if code in exclude_codes:
                continue
            
            # 训练期筛选
            d = df[(df['date'] >= config.train_start) & 
                   (df['date'] <= config.train_end)]
            
            if len(d) < 100:
                continue
            
            # 计算收益率
            ret = (d.iloc[-1]['close'] / d.iloc[0]['close']) - 1
            results.append({'code': code, 'return': ret})
        
        results.sort(key=lambda x: -x['return'])
        selected = {r['code'] for r in results[:config.top_n]}
        
        if not getattr(Selector, '_simple_mode', False):
            logger.info(f"选出 {len(selected)} 只ETF (训练期: {config.train_start} ~ {config.train_end})")
        return selected
    
    def score(self, df: pd.DataFrame, date: str) -> Tuple[int, List[str]]:
        """7因子打分
        
        Args:
            df: ETF数据（需包含计算好的技术指标）
            date: 评分日期
            
        Returns:
            (总分, 选股理由列表)
        """
        row = df[df['date'] == date]
        
        if len(row) == 0:
            return 0, []
        
        row = row.iloc[0]
        
        # 无效数据
        if pd.isna(row.get('ma20')):
            return 0, []
        
        score = 0
        reasons = []
        
        # 1. 站上120日线 (+3分)
        if not pd.isna(row.get('ma120')) and row['close'] > row['ma120']:
            score += 3
            reasons.append('MA120')
        
        # 2. 60日均线向上 (+2分)
        if len(df[df['date'] <= date]) >= 5:
            recent = df[df['date'] <= date].tail(5)
            if (len(recent) >= 5 and 
                not pd.isna(recent['ma60'].iloc[-1]) and 
                not pd.isna(recent['ma60'].iloc[0]) and
                recent['ma60'].iloc[-1] > recent['ma60'].iloc[0]):
                score += 2
                reasons.append('MA60向上')
        
        # 3. 站上60日线 (+2分)
        if not pd.isna(row.get('ma60')) and row['close'] > row['ma60']:
            score += 2
            reasons.append('MA60')
        
        # 4. 站上20日线 (+1分)
        if row['close'] > row['ma20']:
            score += 1
            reasons.append('MA20')
        
        # 5. 放量 (+2分)
        if not pd.isna(row.get('vol_ratio')) and row['vol_ratio'] > 1.5:
            score += 2
            reasons.append(f"放量{int(row['vol_ratio']*100-100)}%")
        
        return score, reasons
    
    def score_with_ic(self, df: pd.DataFrame, date: str) -> Tuple[int, List[str]]:
        """IC加权7因子打分
        
        根据配置文件中的因子权重计算分数
        默认使用IC加权评分(含RSI扣分)
        
        Returns:
            (加权分数, 选股理由列表)
        """
        row = df[df['date'] == date]
        
        if len(row) == 0:
            return 0, []
        
        row = row.iloc[0]
        
        # 无效数据
        if pd.isna(row.get('ma20')):
            return 0, []
        
        # 获取配置的因子权重
        weights = self._get_ic_weights()
        
        weighted_score = 0
        reasons = []
        
        # 1. 站上120日线 (+IC权重)
        if not pd.isna(row.get('ma120')) and row['close'] > row['ma120']:
            weighted_score += weights.get('ma120', 3)
            reasons.append('MA120')
        
        # 2. 60日均线向上 (+IC权重)
        if len(df[df['date'] <= date]) >= 5:
            recent = df[df['date'] <= date].tail(5)
            if (len(recent) >= 5 and 
                not pd.isna(recent['ma60'].iloc[-1]) and 
                not pd.isna(recent['ma60'].iloc[0]) and
                recent['ma60'].iloc[-1] > recent['ma60'].iloc[0]):
                weighted_score += weights.get('ma60_up', 2)
                reasons.append('MA60向上')
        
        # 3. 站上60日线 (+IC权重)
        if not pd.isna(row.get('ma60')) and row['close'] > row['ma60']:
            weighted_score += weights.get('ma60', 2)
            reasons.append('MA60')
        
        # 4. 站上20日线 (+IC权重)
        if row['close'] > row['ma20']:
            weighted_score += weights.get('ma20', 1)
            reasons.append('MA20')
        
        # 5. 放量 (+IC权重)
        if not pd.isna(row.get('vol_ratio')) and row['vol_ratio'] > 1.5:
            weighted_score += weights.get('vol', 2)
            reasons.append(f"放量{int(row['vol_ratio']*100-100)}%")
        
        # 6. RSI健康 (+IC权重) 或 超买扣分
        # 注意：RSI超卖(<30)时需要MA20向上确认，避免"接飞刀"
        if not pd.isna(row.get('rsi_14')):
            rsi = row['rsi_14']
            if rsi < 70:
                # RSI超卖需要MA20向上确认
                if rsi < 30:
                    # 检查MA20是否向上
                    ma20_up = False
                    if len(df[df['date'] <= date]) >= 5:
                        recent = df[df['date'] <= date].tail(5)
                        if (len(recent) >= 5 and 
                            not pd.isna(recent['ma20'].iloc[-1]) and 
                            not pd.isna(recent['ma20'].iloc[0]) and
                            recent['ma20'].iloc[-1] > recent['ma20'].iloc[0]):
                            ma20_up = True
                    
                    if ma20_up:
                        weighted_score += weights.get('rsi', 1)
                        reasons.append('RSI')
                    else:
                        # RSI超卖但MA20未向上，不加分也不记录（防止接飞刀）
                        pass
                else:
                    weighted_score += weights.get('rsi', 1)
                    reasons.append('RSI')
            elif rsi < 80:
                # 超买警告，不扣分但也不加分
                reasons.append('RSI⚠️')
            else:
                # 严重超买，扣分
                weighted_score -= 2
                reasons.append('RSI⚠️⚠️')
        
        # 7. MACD金叉 (+IC权重)
        if not pd.isna(row.get('macd')) and row['macd'] > 0:
            weighted_score += weights.get('macd', 1)
            reasons.append('MACD')
        
        return int(weighted_score), reasons
    
    def evaluate(self, df: pd.DataFrame, date: str) -> Tuple[int, List[str]]:
        """统一评分入口
        
        所有评分调用应使用此方法
        默认使用IC加权评分(含RSI扣分)
        """
        return self.score_with_ic(df, date)
    
    def evaluate_legacy(self, df: pd.DataFrame, date: str) -> Tuple[int, List[str]]:
        """旧版评分入口(无RSI扣分)
        
        用于对比测试
        """
        return self.score(df, date)


__all__ = ['Selector']
