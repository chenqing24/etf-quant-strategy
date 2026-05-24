#!/usr/bin/env python3
"""选股层"""
import pandas as pd
from typing import Dict, List, Tuple, Set

from .config import StrategyConfig


class Selector:
    """ETF选股器"""
    
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
        
        print(f"选出 {len(selected)} 只ETF (训练期: {config.train_start} ~ {config.train_end})")
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
    
    # IC加权因子 (通过历史数据验证的因子权重)
    IC_WEIGHTS = {
        'ma120': 3,      # IC最高的因子，给最高权重
        'ma60': 2,
        'ma60_up': 2,
        'ma20': 1,
        'vol': 2,
        'rsi': 1,
        'macd': 1,
    }
    
    def score_with_ic(self, df: pd.DataFrame, date: str) -> Tuple[int, List[str]]:
        """IC加权7因子打分
        
        根据因子IC值动态调整权重，目前使用预设的IC权重
        未来可通过factor_analysis.IC分析结果动态调整
        
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
        
        weighted_score = 0
        reasons = []
        
        # 1. 站上120日线 (+IC权重: 3)
        if not pd.isna(row.get('ma120')) and row['close'] > row['ma120']:
            weighted_score += self.IC_WEIGHTS['ma120']
            reasons.append('MA120')
        
        # 2. 60日均线向上 (+IC权重: 2)
        if len(df[df['date'] <= date]) >= 5:
            recent = df[df['date'] <= date].tail(5)
            if (len(recent) >= 5 and 
                not pd.isna(recent['ma60'].iloc[-1]) and 
                not pd.isna(recent['ma60'].iloc[0]) and
                recent['ma60'].iloc[-1] > recent['ma60'].iloc[0]):
                weighted_score += self.IC_WEIGHTS['ma60_up']
                reasons.append('MA60向上')
        
        # 3. 站上60日线 (+IC权重: 2)
        if not pd.isna(row.get('ma60')) and row['close'] > row['ma60']:
            weighted_score += self.IC_WEIGHTS['ma60']
            reasons.append('MA60')
        
        # 4. 站上20日线 (+IC权重: 1)
        if row['close'] > row['ma20']:
            weighted_score += self.IC_WEIGHTS['ma20']
            reasons.append('MA20')
        
        # 5. 放量 (+IC权重: 2)
        if not pd.isna(row.get('vol_ratio')) and row['vol_ratio'] > 1.5:
            weighted_score += self.IC_WEIGHTS['vol']
            reasons.append(f"放量{int(row['vol_ratio']*100-100)}%")
        
        # 6. RSI健康 (+IC权重: 1) 或 超买扣分
        if not pd.isna(row.get('rsi_14')):
            rsi = row['rsi_14']
            if rsi < 70:
                weighted_score += self.IC_WEIGHTS['rsi']
                reasons.append('RSI')
            elif rsi < 80:
                # 超买警告，不扣分但也不加分
                reasons.append('RSI⚠️')
            else:
                # 严重超买，扣分
                weighted_score -= 2
                reasons.append('RSI⚠️⚠️')
        
        # 7. MACD金叉 (+IC权重: 1)
        if not pd.isna(row.get('macd')) and row['macd'] > 0:
            weighted_score += self.IC_WEIGHTS['macd']
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