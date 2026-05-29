#!/usr/bin/env python3
"""腾讯ETF数据采集器 - 统一数据层版本

重构说明（v3.0 Phase 2）：
- 写入使用 DataWriter（统一数据入口）
- CSV 作为外部备份，不参与业务逻辑
"""
import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time

import pandas as pd
import requests

from src.constants import TENCENT_BASE_URL, HTTP_TIMEOUT_SHORT, DB_NAME, DATA_DIR
from src.utils.logger import get_logger

logger = get_logger()


class TencentETFetcher:
    """腾讯ETF数据采集器"""
    
    BASE_URL = TENCENT_BASE_URL
    HTTP_TIMEOUT_SHORT = HTTP_TIMEOUT_SHORT
    
    # ETF代码列表 (需要带sh/sz前缀)
    _cached_codes = None
    
    @classmethod
    def get_etf_codes(cls) -> List[str]:
        """获取ETF代码列表 (支持动态池)"""
        if cls._cached_codes is not None:
            return cls._cached_codes
        
        # 尝试从池文件加载
        try:
            from .etf_pool_updater import ETFListUpdater
            updater = ETFListUpdater('etf_pool.json')
            codes = updater.get_tencent_codes()
            if codes:
                cls._cached_codes = codes
                return codes
        except:
            pass
        
        # 使用默认列表
        cls._cached_codes = [
            'sh510300', 'sh510500', 'sz159919', 'sh159915',
            'sh512880', 'sh512170', 'sh512200',
            'sh159928', 'sh159825',
            'sh512010', 'sh512500', 'sh159952',
            'sh159997', 'sh159995', 'sh512760', 'sh159801',
            'sh159823', 'sh515050',
            'sh159857', 'sh516160', 'sh159806',
            'sh159942', 'sh510050',
            'sh512660',
            'sh159920', 'sh159867',
            'sh518880', 'sh159934',
            'sh511010',
            'sh516050', 'sh159577', 'sh515000', 'sh513100',
        ]
        return cls._cached_codes
    
    ETF_CODES = property(lambda self: self.get_etf_codes())
    
    def __init__(self, data_dir: str = None):
        """
        初始化采集器
        
        Args:
            data_dir: 数据目录，默认使用 DATA_DIR
        """
        self.data_dir = data_dir or DATA_DIR
        self._ensure_dir()
    
    def _ensure_dir(self):
        """确保目录存在"""
        os.makedirs(self.data_dir, exist_ok=True)
    
    def fetch_etf(self, code: str, days: int = 30) -> pd.DataFrame:
        """获取单个ETF数据
        
        Args:
            code: ETF代码 (如 'sh510300')
            days: 获取天数
            
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        params = {
            '_var': 'kline_dayqfq',
            'param': f'{code},day,,,{days},qfq'
        }
        
        try:
            response = requests.get(self.BASE_URL, params=params, timeout=self.HTTP_TIMEOUT_SHORT)
            text = response.text.replace('kline_dayqfq=', '', 1)
            data = json.loads(text)
            
            # 解析数据
            etf_data = data.get('data', {}).get(code, {})
            records_data = None
            for field in ['qfqday', 'day']:
                records_data = etf_data.get(field)
                if records_data:
                    break
            
            if not records_data:
                logger.debug(f"  无数据: {code}")
                return pd.DataFrame()
            
            # 转换为DataFrame
            # 腾讯API数组顺序: [date, open, close, high, low, volume]
            records = []
            for item in records_data:
                records.append({
                    'date': item[0],
                    'open': float(item[1]),
                    'close': float(item[2]),
                    'high': float(item[3]),
                    'low': float(item[4]),
                    'volume': float(item[5])
                })
            
            df = pd.DataFrame(records)
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            
            return df
            
        except Exception as e:
            logger.debug(f"  获取失败: {code}, {e}")
            return pd.DataFrame()
    
    def get_code_without_prefix(self, code: str) -> str:
        """去掉前缀"""
        return code.replace('sh', '').replace('sz', '')
    
    def save_etf(self, code: str, df: pd.DataFrame):
        """保存ETF数据（使用统一 DataWriter）
        
        Args:
            code: ETF代码（如 'sh510300'）
            df: 日线数据
        """
        if df.empty:
            return
        
        try:
            # 使用 DataWriter 写入（统一入口）
            from src.data.writer import DataWriter
            writer = DataWriter()
            
            save_code = self.get_code_without_prefix(code)
            
            # 格式化 date 列
            df = df.copy()
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            
            count = writer.write_daily(save_code, df)
            if count > 0:
                logger.debug(f"  SQLite已更新: {code} (+{count}条)")
            else:
                logger.debug(f"  SQLite已是最新: {code}")
                
        except Exception as e:
            logger.warning(f"  SQLite更新失败 {code}: {e}")
    
    def fetch_all(self, days: int = 30) -> Dict[str, pd.DataFrame]:
        """获取所有ETF数据
        
        Returns:
            {code: DataFrame}
        """
        results = {}
        
        logger.info(f"开始采集 {len(self.ETF_CODES)} 只ETF数据...")
        
        for i, code in enumerate(self.ETF_CODES, 1):
            logger.debug(f"  [{i}/{len(self.ETF_CODES)}] 获取 {code} ... ")
            df = self.fetch_etf(code, days)
            if len(df) > 0:
                save_code = self.get_code_without_prefix(code)
                results[save_code] = df
                logger.debug(f"OK ({len(df)}条)")
            else:
                logger.debug("失败")
            
            time.sleep(0.2)
        
        logger.info(f"成功获取 {len(results)} 只ETF")
        return results
    
    def get_local_latest_date(self, code: str) -> Optional[str]:
        """获取本地存储的最新日期（从 SQLite）
        
        Args:
            code: ETF代码（如 'sh510300'）
        """
        try:
            from src.data.writer import DataWriter
            writer = DataWriter()
            save_code = self.get_code_without_prefix(code)
            return writer.get_latest_date(save_code)
        except:
            return None
    
    def fetch_etf_incremental(self, code: str, days: int = 7) -> pd.DataFrame:
        """增量获取ETF数据
        
        1. 检查本地最新日期
        2. 计算需要补充的天数
        3. 只获取缺失的数据
        """
        save_code = self.get_code_without_prefix(code)
        local_latest = self.get_local_latest_date(code)
        
        if local_latest:
            from datetime import datetime as dt
            local_date = dt.strptime(local_latest, '%Y-%m-%d')
            today = dt.now()
            days_diff = (today - local_date).days
            
            if days_diff == 0:
                # 本地已是最新
                logger.debug(f"  {code}: 本地已是最新 ({local_latest})")
                return pd.DataFrame()
            
            # 需要补充的天数 + 缓冲
            fetch_days = min(days_diff + 3, days)
            logger.debug(f"  {code}: 本地最新 {local_latest}, 补充 {fetch_days}天 ... ")
        else:
            # 首次获取，获取足够的历史数据
            fetch_days = 365
            logger.debug(f"  {code}: 首次获取 {fetch_days}天 ... ")
        
        df = self.fetch_etf(code, days=fetch_days)
        
        if len(df) > 0:
            logger.debug(f"OK ({len(df)}条)")
        else:
            logger.debug("失败")
        
        return df
    
    def update_all(self, days: int = 7) -> Dict[str, pd.DataFrame]:
        """增量更新所有ETF
        
        Returns:
            {code: DataFrame}
        """
        results = {}
        for code in self.get_etf_codes():
            df = self.fetch_etf_incremental(code, days=days)
            if len(df) > 0:
                self.save_etf(code, df)
                results[code] = df
        return results
    
    def update_all_incremental(self, days: int = 7) -> Dict[str, pd.DataFrame]:
        """增量更新所有ETF (别名，兼容旧代码)"""
        return self.update_all(days)
    
    def get_latest_date(self) -> Optional[str]:
        """获取本地数据最新日期"""
        try:
            from src.data.writer import DataWriter
            writer = DataWriter()
            return writer.get_latest_date()
        except:
            return None


def quick_fetch():
    """快速测试"""
    fetcher = TencentETFetcher()
    
    # 测试获取1只ETF
    df = fetcher.fetch_etf('sh510300', days=5)
    print(f"获取到 {len(df)} 条数据")
    if not df.empty:
        print(df.tail(3))
    
    return df


# === ETF名称获取方法 ===

def _get_prefix(code: str) -> str:
    """获取交易所前缀"""
    if code.startswith(('510', '511', '512', '513', '515', '516', '518', '588')):
        return 'sh'
    return 'sz'


def _fetch_name_from_api(code: str) -> Optional[str]:
    """从腾讯API获取ETF名称"""
    prefix = _get_prefix(code)
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    
    try:
        response = requests.get(url, timeout=10)
        text = response.content.decode('gbk', errors='replace')
        
        match = text.split('="')
        if len(match) < 2:
            return None
        
        parts = match[1].strip('";').split('~')
        if len(parts) > 1:
            name = parts[1].strip()
            return name if name else None
        return None
    except Exception as e:
        logger.warning(f"获取ETF名称失败 {code}: {e}")
        return None


if __name__ == '__main__':
    quick_fetch()


__all__ = ['TencentETFetcher', 'quick_fetch', '_fetch_name_from_api', '_get_prefix']