"""
数据库模块 - 数据库初始化和操作

提供SQLite数据库的初始化、连接和基础操作
"""
import sqlite3
from typing import List, Dict, Optional, Any
from pathlib import Path
import pandas as pd
from datetime import datetime

from src.utils.logger import get_logger
logger = get_logger()


class Database:
    """SQLite数据库操作类"""
    
    def __init__(self, db_path: str = "data/etf_factors.db"):
        """
        初始化数据库
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._ensure_data_dir()
        self._init_database()
        self.migrate_schema()  # 执行增量扩展
    
    def _ensure_data_dir(self):
        """确保数据目录存在"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_database(self):
        """初始化数据库表结构"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 1. ETF/股票基本信息表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stock_info (
                code TEXT PRIMARY KEY,
                name TEXT,
                exchange TEXT,
                full_code TEXT,
                list_date TEXT,
                category TEXT,
                sub_category TEXT,
                total_shares REAL,
                float_shares REAL,
                net_asset REAL,
                price REAL,
                pe_ratio REAL,
                pb_ratio REAL,
                dividend REAL,
                data_source TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        
        # 2. 日线行情数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_price (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                pre_close REAL,
                volume REAL,
                amount REAL,
                adj_open REAL,
                adj_high REAL,
                adj_low REAL,
                adj_close REAL,
                change REAL,
                pct_change REAL,
                turnover REAL,
                amplitude REAL,
                volatility REAL,
                vwap REAL,
                created_at TEXT,
                UNIQUE(code, date)
            )
        """)
        
        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_code ON daily_price(code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_date ON daily_price(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_price_code_date ON daily_price(code, date)")
        
        # 3. 因子数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS factor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                date TEXT NOT NULL,
                DMA REAL, MA_short REAL, MA_long REAL, SAR REAL, SAR_trend INTEGER,
                RSI_5 REAL, RSI_10 REAL, K REAL, D REAL, J REAL,
                DIF REAL, DEA REAL, MACD_hist REAL,
                OBV REAL, MAOBV REAL, volume_ratio REAL, money_flow REAL,
                BB_upper REAL, BB_middle REAL, BB_lower REAL, BB_percent REAL, ATR REAL,
                ADX REAL, DI_plus REAL, DI_minus REAL,
                return_1d REAL, return_5d REAL, return_10d REAL, return_20d REAL,
                created_at TEXT,
                UNIQUE(code, date)
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_factor_code ON factor_data(code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_factor_date ON factor_data(date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_factor_code_date ON factor_data(code, date)")
        
        # 4. IC计算结果表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ic_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factor_name TEXT NOT NULL,
                code TEXT NOT NULL,
                period INTEGER,
                ic_mean REAL, ic_std REAL, ir REAL, ic_cum REAL,
                p_value REAL, t_stat REAL, sample_count INTEGER, hit_rate REAL,
                direction TEXT, confidence REAL,
                start_date TEXT, end_date TEXT,
                created_at TEXT,
                UNIQUE(factor_name, code, period, start_date, end_date)
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ic_factor ON ic_results(factor_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ic_code ON ic_results(code)")
        
        # 5. 交易记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                date TEXT NOT NULL,
                signal TEXT,
                signal_reason TEXT,
                price REAL, quantity INTEGER, amount REAL, commission REAL,
                position REAL, position_qty INTEGER,
                profit REAL, profit_pct REAL, hold_days INTEGER,
                strategy TEXT, factors TEXT,
                created_at TEXT
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_code ON trade_records(code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trade_date ON trade_records(date)")
        
        # 6. 策略回测结果表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                version TEXT,
                start_date TEXT, end_date TEXT,
                total_return REAL, annual_return REAL, benchmark_return REAL,
                sharpe_ratio REAL, max_drawdown REAL, max_drawdown_days INTEGER, volatility REAL,
                win_rate REAL, profit_loss_ratio REAL, avg_profit REAL, avg_loss REAL, trade_count INTEGER,
                stop_profit REAL, stop_loss REAL,
                params TEXT, factor_weights TEXT,
                created_at TEXT,
                UNIQUE(strategy_name, version, start_date, end_date)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """执行SQL"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        return cursor
    
    def query(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        """查询数据"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return cursor.fetchall()
    
    def query_df(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        """查询数据返回DataFrame"""
        conn = sqlite3.connect(self.db_path)
        return pd.read_sql_query(sql, conn, params=params)
    
    def insert_or_update(self, table: str, data: Dict[str, Any], unique_cols: List[str]):
        """
        插入或更新数据
        
        Args:
            table: 表名
            data: 字段数据字典
            unique_cols: 唯一约束列（用于判断是否存在）
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 构建WHERE条件
        where_clause = " AND ".join([f"{col} = ?" for col in unique_cols])
        where_values = tuple(data[col] for col in unique_cols)
        
        # 检查是否存在
        cursor.execute(f"SELECT 1 FROM {table} WHERE {where_clause}", where_values)
        exists = cursor.fetchone() is not None
        
        if exists:
            # 更新
            set_clause = ", ".join([f"{col} = ?" for col in data.keys() if col not in unique_cols])
            set_values = tuple(data[col] for col in data.keys() if col not in unique_cols)
            sql = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
            cursor.execute(sql, set_values + where_values)
        else:
            # 插入
            cols = ", ".join(data.keys())
            placeholders = ", ".join(["?"] * len(data))
            sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
            cursor.execute(sql, tuple(data.values()))
        
        conn.commit()
        conn.close()
    
    def get_table_info(self) -> List[Dict]:
        """获取所有表信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        result = []
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            result.append({
                'name': table,
                'row_count': count
            })
        
        conn.close()
        return result
    
    def close(self):
        """关闭连接"""
        pass  # SQLite自动管理
    
    # === ETF名称相关方法 ===
    
    def migrate_schema(self):
        """增量扩展表结构（非破坏性）
        
        添加 etf_type 和 name_updated_at 字段
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        migrations = [
            "ALTER TABLE stock_info ADD COLUMN etf_type TEXT",
            "ALTER TABLE stock_info ADD COLUMN name_updated_at TEXT",
        ]
        
        for sql in migrations:
            try:
                cursor.execute(sql)
                conn.commit()
                logger.info(f"✅ 迁移成功: {sql}")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    logger.debug(f"字段已存在，跳过: {sql}")
                else:
                    logger.warning(f"迁移警告: {e}")
        
        conn.close()
    
    def update_etf_name(self, code: str, name: str) -> bool:
        """更新ETF名称
        
        Args:
            code: ETF代码
            name: ETF名称
            
        Returns:
            是否成功
        """
        conn = self._get_connection()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO stock_info (code, name, name_updated_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    name_updated_at = excluded.name_updated_at,
                    updated_at = excluded.updated_at
            """, (code, name, now, now))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"更新ETF名称失败: {code} -> {name}: {e}")
            conn.close()
            return False
    
    def get_etf_name(self, code: str) -> Optional[str]:
        """获取ETF名称
        
        Args:
            code: ETF代码
            
        Returns:
            ETF名称，不存在返回 None
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM stock_info WHERE code = ?", (code,))
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else None
    
    def get_all_etf_names(self) -> Dict[str, str]:
        """获取所有ETF名称
        
        Returns:
            {code: name} 字典
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT code, name FROM stock_info WHERE name IS NOT NULL AND name NOT LIKE 'ETF_%'")
        rows = cursor.fetchall()
        conn.close()
        
        return {row[0]: row[1] for row in rows}


# 全局数据库实例
_db_instance = None

def get_database(db_path: str = "data/etf_factors.db") -> Database:
    """获取数据库单例"""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(db_path)
    return _db_instance