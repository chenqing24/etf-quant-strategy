#!/usr/bin/env python3
"""数据层 - 支持SQLite和CSV双数据源"""
from pathlib import Path
from typing import Dict
import pandas as pd
import sqlite3
import logging

logger = logging.getLogger(__name__)


class DataLoader:
    """ETF数据加载器 - 优先从SQLite读取完整数据"""
    
    def __init__(self):
        self.data: Dict[str, pd.DataFrame] = {}
    
    def load(self, data_dir: str = 'etf_data_live') -> Dict[str, pd.DataFrame]:
        """加载ETF数据 - 优先从SQLite读取
        
        优先级:
        1. SQLite (etf_data_live/etf.db) - 完整历史数据
        2. CSV文件 (etf_data_live/*.csv) - 回退方案
        
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
            if not getattr(self, '_simple_mode', False):
                logger.warning(f"数据目录不存在: {data_dir}")
            return self.data
        
        # 优先从SQLite加载
        db_path = data_dir / 'etf.db'
        if db_path.exists():
            self.data = self._load_from_sqlite(db_path)
            if self.data:
                if not getattr(self, '_simple_mode', False):
                    total_rows = sum(len(df) for df in self.data.values())
                    logger.info(f"从SQLite加载 {len(self.data)} 只ETF, 共{total_rows}行")
                return self.data
        
        # 回退: 从CSV加载
        self.data = self._load_from_csv(data_dir)
        
        if not getattr(self, '_simple_mode', False):
            logger.info(f"从CSV加载 {len(self.data)} 只ETF数据")
        return self.data
    
    def _load_from_sqlite(self, db_path: Path) -> Dict[str, pd.DataFrame]:
        """从SQLite加载数据"""
        try:
            conn = sqlite3.connect(str(db_path))
            
            # 获取所有ETF代码
            cur = conn.cursor()
            cur.execute('SELECT DISTINCT code FROM daily ORDER BY code')
            codes = [r[0] for r in cur.fetchall()]
            
            data = {}
            for code in codes:
                df = pd.read_sql(
                    'SELECT date, open, high, low, close, volume FROM daily WHERE code=? ORDER BY date',
                    conn,
                    params=(code,)
                )
                df = self._process_df(df)
                # 过滤数据不足300天(约1年)的ETF
                if len(df) >= 300:
                    data[code] = df
            
            conn.close()
            return data
        except Exception as e:
            logger.warning(f"SQLite加载失败: {e}")
            return {}
    
    def _load_from_csv(self, data_dir: Path) -> Dict[str, pd.DataFrame]:
        """从CSV文件加载数据（回退方案）"""
        data = {}
        for f in data_dir.glob('*.csv'):
            if f.name == 'etf.db':
                continue
            try:
                df = self._process_df(pd.read_csv(f))
                # 过滤数据不足300天(约1年)的ETF，确保指标计算准确
                if len(df) >= 300:
                    # 从文件名提取代码（去掉sh/sz前缀）
                    code = f.stem
                    if code.startswith('sh') or code.startswith('sz'):
                        code = code[2:]
                    data[code] = df
            except Exception as e:
                logger.warning(f"加载CSV失败 {f.name}: {e}")
        return data
    
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
    
    def get_date_range(self, code: str) -> tuple:
        """获取某ETF的数据范围"""
        df = self.get(code)
        if df is not None and len(df) > 0:
            return df['date'].min(), df['date'].max()
        return None, None


__all__ = ['DataLoader']