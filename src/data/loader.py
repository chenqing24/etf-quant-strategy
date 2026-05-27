#!/usr/bin/env python3
"""数据层 - 从SQLite加载ETF历史数据"""
from pathlib import Path
from src.constants import DB_NAME
from typing import Dict
import pandas as pd
import sqlite3
import logging

logger = logging.getLogger(__name__)


class DataLoader:
    """ETF数据加载器 - 从SQLite加载（核心数据源）"""
    
    def __init__(self):
        self.data: Dict[str, pd.DataFrame] = {}
    
    def load(self, data_dir: str = 'etf_data_live') -> Dict[str, pd.DataFrame]:
        """加载ETF数据
        
        从 {data_dir}/etf.db 加载所有ETF历史数据。
        
        Args:
            data_dir: 数据目录（默认 etf_data_live）
            
        Returns:
            {code: DataFrame}
        """
        self.data = {}
        
        # 从SQLite加载
        sqlite_path = Path.cwd() / data_dir / DB_NAME
        if sqlite_path.exists():
            self.data = self._load_from_sqlite(sqlite_path)
            if not getattr(self, '_simple_mode', False):
                total_rows = sum(len(df) for df in self.data.values())
                logger.info(f"从SQLite加载 {len(self.data)} 只ETF, 共{total_rows}行")
        else:
            if not getattr(self, '_simple_mode', False):
                logger.warning(f"SQLite文件不存在: {sqlite_path}")
        
        return self.data
    
    def _load_from_sqlite(self, db_path: Path) -> Dict[str, pd.DataFrame]:
        """从SQLite加载数据"""
        try:
            conn = sqlite3.connect(str(db_path))
            
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
                if len(df) >= 300:
                    data[code] = df
            
            conn.close()
            return data
        except Exception as e:
            logger.warning(f"SQLite加载失败: {e}")
            return {}
    
    def _process_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化处理"""
        cols = {c: c.lower() if c != 'date' else c for c in df.columns}
        df = df.rename(columns=cols)
        
        if 'vol' in df.columns:
            df = df.rename(columns={'vol': 'volume'})
        
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