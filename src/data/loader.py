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


__all__ = ['DataLoader', 'ETFNameLoader']


class ETFNameLoader:
    """ETF名称加载器 - 从数据库/腾讯API获取ETF名称"""
    
    def __init__(self, db_name: str = None):
        from src.constants import DB_NAME
        if db_name is None:
            db_name = DB_NAME
        self.db_path = Path.cwd() / 'etf_data_live' / db_name
        self._cache = {}  # 名称缓存
    
    def load_all_names(self) -> Dict[str, str]:
        """从数据库加载所有ETF名称
        
        Returns:
            {code: name, ...}
            如果数据库或表不存在，返回空字典（不抛异常）
        """
        if self._cache:
            return self._cache
        
        try:
            conn = sqlite3.connect(str(self.db_path))
            cur = conn.cursor()
            
            # 检查表是否存在
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_info'")
            if not cur.fetchone():
                logger.debug("stock_info表不存在，跳过加载")
                return {}
            
            cur.execute("SELECT code, name FROM stock_info")
            rows = cur.fetchall()
            conn.close()
            
            # 过滤掉机器生成的默认名称
            for code, name in rows:
                if name and not name.startswith('ETF_'):
                    self._cache[code] = name
                elif name:
                    # 如果是默认名称，标记为需要更新
                    self._cache[code] = name
            
            return self._cache
        except Exception as e:
            logger.debug(f"加载ETF名称: {e}")
            return {}
    
    def get_name(self, code: str) -> str:
        """获取单个ETF名称
        
        优先级：
        1. 数据库中有非默认名称 → 使用数据库名称
        2. 数据库中无名称或默认名称 → 从腾讯API实时获取
        """
        # 先尝试从数据库获取
        names = self.load_all_names()
        if names:  # 数据库有数据
            name = names.get(code)
            if name and not name.startswith('ETF_'):
                return name
        
        # 数据库没有或默认名称，从API获取
        api_name = self.get_name_from_api(code)
        return api_name
    
    @staticmethod
    def get_name_from_api(code: str) -> str:
        """从腾讯API获取ETF名称（静态方法，无需实例化）
        
        Args:
            code: ETF代码
            
        Returns:
            ETF名称
        """
        import requests
        from src.constants import TENCENT_REALTIME_URL, HTTP_TIMEOUT_SHORT
        
        # 标准化代码（添加sh/sz前缀）
        if code.startswith(('510', '511', '512', '513', '515', '516', '518', '588')):
            prefix = 'sh'
        else:
            prefix = 'sz'
        
        url = TENCENT_REALTIME_URL.format(code=f"{prefix}{code}")
        
        try:
            response = requests.get(url, timeout=HTTP_TIMEOUT_SHORT)
            # 腾讯API返回格式: v_sz159577="51~名称~代码~..."
            text = response.content.decode('gbk', errors='replace')
            # 解析返回数据
            import re
            match = re.search(r'="([^"]+)"', text)
            if match:
                parts = match.group(1).split('~')
                if len(parts) > 1:
                    return parts[1]  # 返回ETF名称
        except Exception as e:
            logger.warning(f"获取ETF名称失败 {code}: {e}")
        
        return code  # 失败时返回代码本身
    
    def update_all_names(self) -> Dict[str, str]:
        """从腾讯API批量获取并更新所有ETF名称到数据库
        
        Returns:
            {code: name, ...} 更新后的名称映射
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cur = conn.cursor()
            
            # 获取所有ETF代码
            cur.execute("SELECT code FROM stock_info")
            codes = [row[0] for row in cur.fetchall()]
            
            updated = {}
            for code in codes:
                name = self.get_name_from_api(code)
                if name != code:  # 获取成功
                    cur.execute(
                        "UPDATE stock_info SET name = ?, updated_at = ? WHERE code = ?",
                        (name, pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'), code)
                    )
                    updated[code] = name
            
            conn.commit()
            conn.close()
            
            # 清除缓存
            self._cache = {}
            
            logger.info(f"更新了 {len(updated)} 个ETF名称")
            return updated
            
        except Exception as e:
            logger.warning(f"批量更新ETF名称失败: {e}")
            return {}