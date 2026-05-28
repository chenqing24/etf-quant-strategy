"""
数据Facade - 统一数据入口
封装HotDataManager + ColdDataManager + DataSourceRouter，提供统一读写接口

所有上层模块必须通过DataFacade访问数据，禁止直接调用fetcher或requests
"""

import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd

from src.data.router import DataSourceRouter


class HotDataManager:
    """热数据管理器 - 实时价格内存缓存"""
    
    def __init__(self, base_dir: str = 'etf_data_live'):
        self.base_dir = Path(base_dir)
        self.hot_dir = self.base_dir / 'hot'
        self.hot_dir.mkdir(parents=True, exist_ok=True)

    def get(self, code: str) -> Optional[Dict]:
        """读取单个ETF实时数据"""
        path = self.hot_dir / f"{code}.json"
        if path.exists():
            try:
                return json.loads(path.read_text())
            except:
                pass
        return None

    def set(self, code: str, data: Dict):
        """写入单个ETF实时数据"""
        path = self.hot_dir / f"{code}.json"
        path.write_text(json.dumps(data, ensure_ascii=False))

    def get_all(self) -> Dict[str, Dict]:
        """读取所有实时数据"""
        result = {}
        for path in self.hot_dir.glob("*.json"):
            code = path.stem
            try:
                result[code] = json.loads(path.read_text())
            except:
                pass
        return result


class ColdDataManager:
    """冷数据管理器 - SQLite etf.db"""
    
    def __init__(self, base_dir: str = 'etf_data_live'):
        self.base_dir = Path(base_dir)
        self.db_path = self.base_dir / 'etf.db'
    
    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    def get_daily(self, code: str, start_date: str = None, end_date: str = None, limit: int = None) -> pd.DataFrame:
        """
        获取日线数据
        
        Args:
            code: ETF代码（不含前缀）
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            limit: 最大返回条数（优先取最新）
        
        Returns:
            DataFrame: date, open, high, low, close, volume
        """
        conn = self._connect()
        query = "SELECT date, open, high, low, close, volume FROM daily WHERE code = ?"
        params = [code]
        
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        
        query += " ORDER BY date DESC"
        if limit:
            query += f" LIMIT {limit}"
        
        df = pd.read_sql_query(query, conn, params=params)
        conn.close()
        
        if limit and len(df) > limit:
            df = df.head(limit)
        return df.sort_values('date')

    def get_code_list(self) -> List[str]:
        """获取所有ETF代码"""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT code FROM daily ORDER BY code")
        codes = [r[0] for r in cur.fetchall()]
        conn.close()
        return codes


class DataFacade:
    """
    数据层统一入口
    
    所有上层模块（评分/报告/校验/交易）必须通过DataFacade访问数据，
    禁止直接调用fetcher或requests。
    """
    
    def __init__(self, base_dir: str = 'etf_data_live'):
        self.base_dir = Path(base_dir)
        self.hot = HotDataManager(base_dir)
        self.cold = ColdDataManager(base_dir)
        self.router = DataSourceRouter()

    # ========== 热数据（实时价格）==========

    def get_realtime(self, codes: List[str]) -> Dict[str, Dict]:
        """
        获取实时价格（优先缓存，降级采集）
        
        Args:
            codes: 代码列表（带sh/sz前缀）
        
        Returns:
            {code: {code, name, price, prev_close, ...}, ...}
        """
        result = {}
        missing = []
        
        # 先查缓存
        for code in codes:
            cached = self.hot.get(code)
            if cached:
                # 5分钟内有效
                ts = cached.get('timestamp', '')
                if ts:
                    try:
                        age = time.time() - float(ts)
                        if age < 300:
                            result[code] = cached
                            continue
                    except:
                        pass
            missing.append(code)
        
        # 降级采集
        if missing:
            fetched = self.router.fetch_realtime(missing)
            for code, data in fetched.items():
                if data:
                    data['timestamp'] = str(time.time())
                    self.hot.set(code, data)
                    result[code] = data
        
        return result

    def get_all_realtime(self) -> Dict[str, Dict]:
        """获取所有ETF实时价格"""
        codes = self.cold.get_code_list()
        # 添加前缀
        codes_with_prefix = []
        for code in codes:
            if code.startswith(('51', '15')):
                codes_with_prefix.append(f"sh{code}")
            else:
                codes_with_prefix.append(f"sz{code}")
        return self.get_realtime(codes_with_prefix)

    # ========== 冷数据（日线，从SQLite）==========

    def get_daily(self, code: str, days: int = 60) -> pd.DataFrame:
        """
        获取日线数据（从etf.db daily表）
        
        Args:
            code: 标的代码，如 '510300'
            days: 获取天数（默认60）
        
        Returns:
            DataFrame: date, open, high, low, close, volume
        """
        return self.cold.get_daily(code, limit=days)

    def get_hourly(self, code: str, count: int = 1800) -> pd.DataFrame:
        """
        获取小时线数据（从新浪API）
        仅信号参考，不用于实盘决策
        
        Args:
            code: 标的代码（如 sh510300）
            count: 数据条数（默认1800）
        
        Returns:
            DataFrame: day, open, high, low, close, volume, is_signal_only=True
        """
        codes = [code] if isinstance(code, str) else code
        result = self.router.fetch_hourly(codes, count=count)
        
        data = result.get(code, [])
        if not data:
            return pd.DataFrame(columns=['day', 'open', 'high', 'low', 'close', 'volume', 'is_signal_only'])
        
        df = pd.DataFrame(data)
        if 'day' in df.columns:
            df = df.rename(columns={'day': 'timestamp'})
        df['is_signal_only'] = True
        return df

    # ========== 合并数据（历史+今日实时）==========

    def get_merged(self, code: str, days: int = 300) -> pd.DataFrame:
        """
        合并冷数据（历史日线）+ 热数据（今日实时）
        用于评分时需要最新价格
        
        Args:
            code: 标的代码（不含前缀）
            days: 获取天数
        
        Returns:
            DataFrame: date, open, high, low, close, volume
        """
        # 冷数据
        df = self.cold.get_daily(code, limit=days)
        
        # 热数据（今日实时）
        hot = self.hot.get(code)
        if hot and 'price' in hot:
            today = time.strftime('%Y-%m-%d')
            # 检查是否已有今日数据
            if df.empty or df.iloc[-1]['date'] != today:
                new_row = pd.DataFrame([{
                    'date': today,
                    'open': hot.get('open', hot['price']),
                    'high': hot.get('high', hot['price']),
                    'low': hot.get('low', hot['price']),
                    'close': hot['price'],
                    'volume': hot.get('volume', 0)
                }])
                df = pd.concat([df, new_row], ignore_index=True)
        
        return df

    # ========== 批量操作 ==========

    def get_daily_batch(self, codes: List[str], date: str) -> pd.DataFrame:
        """
        批量获取某日多只ETF日线（用于市场情绪聚合）
        
        Args:
            codes: 代码列表
            date: 日期 YYYY-MM-DD
        
        Returns:
            DataFrame: code, date, open, high, low, close, volume
        """
        conn = self.cold._connect()
        placeholders = ','.join(['?' for _ in codes])
        query = f"SELECT code, date, open, high, low, close, volume FROM daily WHERE code IN ({placeholders}) AND date = ?"
        df = pd.read_sql_query(query, conn, params=codes + [date])
        conn.close()
        return df

    # ========== 生命周期 ==========

    def is_trading_time(self) -> bool:
        """判断是否交易时间（9:30-15:00）"""
        now = time.localtime()
        hour, minute = now.tm_hour, now.tm_min
        weekday = now.tm_wday
        if weekday >= 5:  # 周末
            return False
        # 9:30-11:30, 13:00-15:00
        if 9 < hour < 11 or (hour == 9 and minute >= 30) or (hour == 11 and minute < 30):
            return True
        if 13 <= hour < 15 or (hour == 15 and minute == 0):
            return True
        return False

    def get_lifecycle_info(self) -> Dict:
        """获取生命周期状态"""
        conn = self.cold._connect()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM daily")
        total_rows = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT code) FROM daily")
        etf_count = cur.fetchone()[0]
        cur.execute("SELECT MIN(date), MAX(date) FROM daily")
        date_range = cur.fetchone()
        conn.close()
        
        return {
            'db_path': str(self.cold.db_path),
            'total_rows': total_rows,
            'etf_count': etf_count,
            'date_range': f"{date_range[0]} ~ {date_range[1]}"
        }