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
        
        for code, df in data.items():
            # 排除规则
            if code in config.exclude_codes:
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
        selected = {r['code'] for r in results[:30]}
        
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


__all__ = ['Selector']