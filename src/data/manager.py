#!/usr/bin/env python3
"""
热冷数据分离管理器
=====================
数据生命周期管理：
- 热数据层 (hot/): 今日实时价格，JSON格式含时间戳，随时间变动
- 冷数据层 (etf.db): 收盘确认数据，SQLite格式，T日23:00后归档

生命周期阶段：
1. TRADING_HOUR 盘中更新 - 热数据层持续更新
2. CLOSING确认 - 15:00-15:30收盘验证
3. MIGRATED归档 - 15:30后热数据迁移至冷数据层

使用方式:
    from src.data.manager import DataFacade
    
    facade = DataFacade('etf_data_live')
    
    # 获取今日实时价格
    hot_data = facade.hot.get('510300')
    
    # 更新热数据
    facade.hot.set('510300', {'price': 3.85, 'change': 0.5})
    
    # 获取日线数据（从SQLite）
    df = facade.get_daily('510300', days=60)
    
    # 获取合并数据（热价格+冷历史）
    merged = facade.get_merged_data('510300')
    
    # 收盘后迁移
    facade.migrate()
    
    # 查看生命周期状态
    lifecycle = facade.get_lifecycle_info()
"""

import json
import os
import sqlite3
from datetime import datetime, time
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum

import pandas as pd


class LifecycleStage(Enum):
    """数据生命周期阶段"""
    UNKNOWN = "unknown"
    TRADING_HOUR = "trading"      # 盘中更新中
    CLOSING = "closing"           # 收盘确认中 (15:00-15:30)
    MIGRATED = "migrated"         # 已归档至冷数据层
    MIGRATING = "migrating"       # 迁移中


@dataclass
class HotDataRecord:
    """热数据记录结构"""
    code: str           # ETF代码
    price: float       # 当前价格
    change_pct: float  # 涨跌幅%
    volume: float      # 成交量
    timestamp: str      # 更新时间戳 ISO格式
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'HotDataRecord':
        return cls(**data)


class HotDataManager:
    """热数据管理器
    
    职责：
    - 存储今日实时价格数据
    - JSON格式，含时间戳
    - 盘中持续更新，收盘后清空
    """
    
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.hot_dir = self.base_dir / 'hot'
        self.hot_dir.mkdir(parents=True, exist_ok=True)
        
        # 热数据缓存（内存）
        self._cache: Dict[str, HotDataRecord] = {}
        self._load_cache()
    
    def _load_cache(self):
        """从磁盘加载热数据到内存缓存"""
        if not self.hot_dir.exists():
            return
            
        for f in self.hot_dir.glob('*.json'):
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                    record = HotDataRecord.from_dict(data)
                    self._cache[record.code] = record
            except Exception:
                pass
    
    def _get_file_path(self, code: str) -> Path:
        return self.hot_dir / f"{code}.json"
    
    def get(self, code: str) -> Optional[Dict]:
        """读取单个ETF实时数据
        
        Returns:
            dict: 包含 code, price, change_pct, volume, timestamp 的字典
        """
        record = self._cache.get(code)
        if record:
            return record.to_dict()
        return None
    
    def set(self, code: str, data: Dict):
        """写入单个ETF实时数据"""
        if isinstance(data, dict):
            # 构建HotDataRecord
            record = HotDataRecord(
                code=code,
                price=float(data.get('price', 0)),
                change_pct=float(data.get('change_pct', 0)),
                volume=float(data.get('volume', 0)),
                timestamp=data.get('timestamp', datetime.now().isoformat()),
            )
        else:
            record = data
        
        # 更新内存缓存
        self._cache[code] = record
        
        # 持久化到磁盘
        path = self._get_file_path(code)
        path.write_text(json.dumps(record.to_dict(), ensure_ascii=False))
    
    def get_all(self) -> Dict[str, HotDataRecord]:
        """读取所有实时数据"""
        return dict(self._cache)
    
    def clear(self):
        """清空热数据（收盘归档后调用）"""
        for f in self.hot_dir.glob('*.json'):
            try:
                os.remove(f)
            except Exception:
                pass
        
        self._cache.clear()
    
    def count(self) -> int:
        """热数据条数"""
        return len(self._cache)


class ColdDataManager:
    """冷数据管理器
    
    职责：
    - 存储收盘确认的历史数据
    - SQLite格式（etf.db），用于历史回测和分析
    """
    
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.db_path = self.base_dir / 'etf.db'
        self._ensure_db()
    
    def _ensure_db(self):
        """确保数据库和表存在"""
        if not self.db_path.exists():
            # 创建数据库和表
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily (
                    code TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    PRIMARY KEY (code, date)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_info (
                    code TEXT PRIMARY KEY,
                    name TEXT,
                    sector TEXT,
                    created_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS etf_names (
                    code TEXT PRIMARY KEY,
                    name TEXT,
                    full_name TEXT,
                    sector TEXT,
                    updated_at TEXT
                )
            """)
            conn.commit()
            conn.close()
    
    def _connect(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return sqlite3.connect(str(self.db_path))
    
    def get_code_list(self) -> List[str]:
        """获取所有ETF代码"""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT code FROM daily ORDER BY code")
        codes = [r[0] for r in cur.fetchall()]
        conn.close()
        return codes
    
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
    
    def get(self, code: str) -> Optional[List[Dict[str, Any]]]:
        """获取冷数据（兼容旧接口）
        
        Args:
            code: ETF代码
            
        Returns:
            包含 date, open, high, low, close, volume 的字典列表
        """
        df = self.get_daily(code)
        if df.empty:
            return None
        return df.to_dict('records')
    
    def get_latest(self, code: str) -> Optional[Dict[str, Any]]:
        """获取最新一条冷数据"""
        df = self.get_daily(code, limit=1)
        if df.empty:
            return None
        return df.iloc[-1].to_dict()
    
    def append(self, code: str, data: Dict[str, Any]):
        """追加冷数据（收盘归档时调用）
        
        Args:
            code: ETF代码
            data: 包含 date, open, high, low, close, volume
        """
        conn = self._connect()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO daily (code, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                code,
                data.get('date'),
                float(data.get('open', 0)),
                float(data.get('high', 0)),
                float(data.get('low', 0)),
                float(data.get('close', 0)),
                float(data.get('volume', 0)),
            ))
            conn.commit()
        finally:
            conn.close()
    
    def count(self) -> int:
        """获取冷数据总条数"""
        conn = self._connect()
        result = conn.execute("SELECT COUNT(*) FROM daily").fetchone()[0]
        conn.close()
        return result


class DataFacade:
    """数据访问统一接口
    
    合并热冷数据层，提供统一的数据访问接口
    """
    
    # 交易时段定义
    TRADING_START = time(9, 30)
    TRADING_END = time(15, 0)
    MIGRATION_TIME = time(15, 30)
    
    def __init__(self, base_dir: str = 'etf_data_live'):
        self.base_dir = Path(base_dir)
        self.hot = HotDataManager(base_dir)
        self.cold = ColdDataManager(base_dir)
        self._lifecycle_stage = self._detect_lifecycle_stage()
    
    def _detect_lifecycle_stage(self) -> LifecycleStage:
        """检测当前生命周期阶段"""
        now = datetime.now()
        current_time = now.time()
        
        # 工作日判断
        if now.weekday() >= 5:  # 周六日
            return LifecycleStage.TRADING_HOUR
        
        # 交易时段判断
        if current_time < self.TRADING_START:
            return LifecycleStage.TRADING_HOUR
        elif self.TRADING_START <= current_time < self.TRADING_END:
            return LifecycleStage.TRADING_HOUR
        elif self.TRADING_END <= current_time < self.MIGRATION_TIME:
            return LifecycleStage.CLOSING
        elif current_time >= self.MIGRATION_TIME:
            return LifecycleStage.MIGRATED
        else:
            return LifecycleStage.UNKNOWN
    
    def get_merged_data(self, code: str) -> Dict[str, Any]:
        """获取合并后的数据（热数据覆盖冷数据对应字段）
        
        合并逻辑：
        - 热数据存在时，用热数据覆盖冷数据的价格/涨跌幅/成交量
        - 热数据不存在时，仅使用冷数据
        - 完全不存在时返回空字典
        
        Args:
            code: ETF代码
        
        Returns:
            合并后的数据字典
        """
        hot_record = self.hot.get(code)
        df = self.cold.get_daily(code, limit=1)
        
        result = {}
        
        # 先取冷数据作为基础
        if not df.empty:
            latest_cold = df.iloc[-1].to_dict()
            result = {
                'date': latest_cold.get('date', ''),
                'open': float(latest_cold.get('open', 0)),
                'high': float(latest_cold.get('high', 0)),
                'low': float(latest_cold.get('low', 0)),
                'close': float(latest_cold.get('close', 0)),
                'volume': float(latest_cold.get('volume', 0)),
            }
        else:
            result = {
                'date': '',
                'open': 0,
                'high': 0,
                'low': 0,
                'close': 0,
                'volume': 0,
            }
        
        # 热数据覆盖（只覆盖价格相关字段）
        if hot_record:
            result.update({
                'price': hot_record.price,
                'change_pct': hot_record.change_pct,
                'hot_timestamp': hot_record.timestamp,
                # 如果热数据有成交量，用热数据
                'volume': hot_record.volume if hot_record.volume > 0 else result['volume'],
            })
            # 收盘价用热数据价格
            if hot_record.price > 0:
                result['close'] = hot_record.price
        
        return result
    
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
    
    def get_merged(self, code: str, days: int = 300) -> pd.DataFrame:
        """
        获取合并数据（冷数据日线 + 热数据最新价格）
        
        Args:
            code: 标的代码，如 '510300'
            days: 获取天数（默认300）
        
        Returns:
            DataFrame: date, open, high, low, close, volume, price, change_pct
        """
        # 获取冷数据
        df = self.cold.get_daily(code, limit=days)
        
        if df.empty:
            return df
        
        # 获取热数据
        hot_dict = self.hot.get(code)
        
        if hot_dict:
            # 在最后一行附加热数据的价格
            last_row = df.iloc[-1].copy()
            last_row['price'] = hot_dict.get('price')
            last_row['change_pct'] = hot_dict.get('change_pct')
            last_row['volume'] = hot_dict.get('volume', last_row['volume'])
            
            # 更新最后一行的close为热数据价格
            last_row['close'] = hot_dict.get('price')
            df.iloc[-1] = last_row
            
            # 确保列顺序
            for col in ['price', 'change_pct']:
                if col not in df.columns:
                    df[col] = None
            df = df[['date', 'open', 'high', 'low', 'close', 'volume', 'price', 'change_pct']]
        
        return df
    
    def get_daily_batch(self, codes: List[str], start_date: str = None) -> pd.DataFrame:
        """
        批量获取多只ETF的日线数据
        
        Args:
            codes: ETF代码列表
            start_date: 开始日期 YYYY-MM-DD
        
        Returns:
            DataFrame: 包含所有ETF的数据，code列标识来源
        """
        dfs = []
        for code in codes:
            df = self.cold.get_daily(code, start_date=start_date)
            if not df.empty:
                df = df.copy()
                df['code'] = code
                dfs.append(df)
        
        if not dfs:
            return pd.DataFrame()
        
        return pd.concat(dfs, ignore_index=True)
    
    def get_realtime(self, codes: List[str]) -> Dict[str, Dict]:
        """获取实时价格（热数据）
        
        Args:
            codes: 代码列表（不带前缀）
        
        Returns:
            {code: {code, price, change_pct, volume, timestamp}, ...}
        """
        result = {}
        for code in codes:
            record = self.hot.get(code)
            if record:
                result[code] = record.to_dict()
        return result
    
    def get_all_realtime(self) -> Dict[str, Dict]:
        """获取所有ETF实时价格"""
        return self.hot.get_all()
    
    def migrate(self) -> Dict[str, str]:
        """热数据迁移至冷数据
        
        执行步骤：
        1. 检查是否为交易时段后（15:30后）
        2. 遍历热数据目录
        3. 将每条热数据追加/更新到冷数据SQLite
        
        Returns:
            {code: status} 迁移结果
        """
        results = {}
        hot_data = self.hot.get_all()
        
        if not hot_data:
            return {'status': 'no_data'}
        
        for code, record in hot_data.items():
            try:
                # 构建冷数据格式
                cold_record = {
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'open': record.price,
                    'high': record.price,
                    'low': record.price,
                    'close': record.price,
                    'volume': record.volume,
                }
                
                self.cold.append(code, cold_record)
                results[code] = 'migrated'
                
            except Exception as e:
                results[code] = f'error: {str(e)}'
        
        # 清空热数据
        self.hot.clear()
        
        # 更新生命周期状态
        self._lifecycle_stage = LifecycleStage.MIGRATED
        
        return results
    
    def get_lifecycle_info(self) -> Dict[str, Any]:
        """获取当前数据生命周期阶段信息
        
        Returns:
            {
                'stage': str,          # 当前阶段
                'stage_desc': str,     # 阶段描述
                'hot_count': int,     # 热数据条数
                'cold_count': int,    # 冷数据条数
                'next_milestone': str # 下一里程碑
            }
        """
        stage_descriptions = {
            LifecycleStage.UNKNOWN: "状态未知",
            LifecycleStage.TRADING_HOUR: "盘中更新中 - 热数据持续更新",
            LifecycleStage.CLOSING: "收盘确认中 - 等待15:30归档",
            LifecycleStage.MIGRATED: "已归档完成 - 热数据已迁移至冷数据层",
            LifecycleStage.MIGRATING: "迁移中 - 正在处理数据",
        }
        
        next_milestones = {
            LifecycleStage.UNKNOWN: "等待系统初始化",
            LifecycleStage.TRADING_HOUR: "15:00 收盘确认",
            LifecycleStage.CLOSING: "15:30 自动迁移",
            LifecycleStage.MIGRATED: "下一个交易日",
            LifecycleStage.MIGRATING: "迁移完成",
        }
        
        return {
            'stage': self._lifecycle_stage.value,
            'stage_desc': stage_descriptions.get(self._lifecycle_stage, "未知"),
            'hot_count': self.hot.count(),
            'cold_count': self.cold.count(),
            'next_milestone': next_milestones.get(self._lifecycle_stage, "未知"),
            'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
    
    def is_trading_time(self) -> bool:
        """判断当前是否为交易时间"""
        return self._lifecycle_stage in [LifecycleStage.TRADING_HOUR, LifecycleStage.CLOSING]
    
    def sync_from_csv(self, code: str, csv_path: str):
        """从现有CSV文件同步冷数据
        
        Args:
            code: ETF代码
            csv_path: CSV文件路径
        """
        if not os.path.exists(csv_path):
            return
        
        df = pd.read_csv(csv_path)
        
        for _, row in df.iterrows():
            self.cold.append(code, {
                'date': row['date'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume'],
            })


def demo():
    """演示热冷数据管理器的使用"""
    print("=== 热冷数据分离管理器演示 ===\n")
    
    facade = DataFacade('etf_data_live')
    
    # 查看生命周期
    lifecycle = facade.get_lifecycle_info()
    print(f"生命周期状态: {lifecycle['stage_desc']}")
    print(f"热数据条数: {lifecycle['hot_count']}")
    print(f"冷数据条数: {lifecycle['cold_count']}\n")
    
    # 模拟更新热数据
    print("模拟写入热数据...")
    facade.hot.set('510300', {
        'price': 3.856,
        'change_pct': 1.23,
        'volume': 1234567,
    })
    
    hot = facade.hot.get('510300')
    if hot:
        print(f"热数据: 代码={hot.code}, 价格={hot.price}, 涨幅={hot.change_pct}%\n")
    
    # 获取日线数据演示
    print("获取日线数据演示...")
    df = facade.get_daily('510300', days=5)
    print(f"日线数据: {len(df)} 条")
    if not df.empty:
        print(df.tail(3).to_string())
    print()
    
    # 合并数据演示
    print("合并数据演示...")
    merged = facade.get_merged_data('510300')
    print(f"合并结果: {merged}\n")
    
    return facade


if __name__ == '__main__':
    facade = demo()
    
    print("\n=== 生命周期信息 ===")
    info = facade.get_lifecycle_info()
    for k, v in info.items():
        print(f"  {k}: {v}")


__all__ = [
    'HotDataManager',
    'ColdDataManager', 
    'DataFacade',
    'LifecycleStage',
    'HotDataRecord',
]