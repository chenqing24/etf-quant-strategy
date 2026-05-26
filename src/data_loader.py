#!/usr/bin/env python3
"""数据层"""
from pathlib import Path
from typing import Dict
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class DataLoader:
    """ETF数据加载器"""
    
    def __init__(self):
        self.data: Dict[str, pd.DataFrame] = {}
    
    def load(self, data_dir: str) -> Dict[str, pd.DataFrame]:
        """加载目录下所有CSV文件
        
        Args:
            data_dir: 数据目录路径
            
        Returns:
            {code: DataFrame}
        """
        data_dir = Path(data_dir)
        
        # 如果不存在，尝试相对路径
        if not data_dir.exists():
            data_dir = Path.cwd() / data_dir
        
        self.data = {}
        
        if not data_dir.exists():
            # 简版模式下静默处理
            if not getattr(self, '_simple_mode', False):
                logger.warning(f"数据目录不存在: {data_dir}")
            return self.data
        
        for f in data_dir.glob('*.csv'):
            df = self._process_df(pd.read_csv(f))
            # 过滤数据不足500天(约2年)的ETF，确保指标计算准确
            if len(df) >= 500:
                self.data[f.stem] = df
        
        # 简版模式下静默处理
        if not getattr(self, '_simple_mode', False):
            logger.info(f"加载 {len(self.data)} 只ETF数据")
        return self.data
    
    def _process_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化处理"""
        # 列名小写化
        cols = {c: c.lower() if c != 'date' else c for c in df.columns}
        df = df.rename(columns=cols)
        
        # volume列名兼容
        if 'vol' in df.columns:
            df = df.rename(columns={'vol': 'volume'})
        
        # 类型转换
        df['date'] = df['date'].astype(str)
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        
        if 'open' in df.columns:
            df['open'] = pd.to_numeric(df['open'], errors='coerce')
        if 'high' in df.columns:
            df['high'] = pd.to_numeric(df['high'], errors='coerce')
        if 'low' in df.columns:
            df['low'] = pd.to_numeric(df['low'], errors='coerce')
        
        return df
    
    def get(self, code: str) -> pd.DataFrame:
        """获取单只ETF数据"""
        return self.data.get(code)
    
    def get_etfs(self, codes: list) -> Dict[str, pd.DataFrame]:
        """批量获取ETF数据"""
        return {c: self.data[c] for c in codes if c in self.data}


__all__ = ['DataLoader']