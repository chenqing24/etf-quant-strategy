#!/usr/bin/env python3
import json
"""腾讯ETF数据采集"""
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List
import time
import os

from src.utils.logger import get_logger

logger = get_logger()


class TencentETFetcher:
    """腾讯ETF数据采集器"""
    
    # 腾讯API地址
    BASE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    
    # ETF代码列表 (需要带sh/sz前缀)
    # 优先使用动态池，否则使用默认列表
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
    
    def __init__(self, data_dir: str = 'etf_data_live'):
        self.data_dir = data_dir
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
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            # 腾讯API返回带前缀的JSON: kline_dayqfq={...}，需要去掉前缀
            text = response.text.replace('kline_dayqfq=', '', 1)
            data = json.loads(text)
            
            # 解析数据: data.{code}.{field}，字段名可能是 qfqday 或 day
            etf_data = data.get('data', {}).get(code, {})
            records_data = None
            for field in ['qfqday', 'day']:
                records_data = etf_data.get(field)
                if records_data:
                    break
            
            if not records_data:
                logger.warn(f"  警告: {code} 无数据")
                return pd.DataFrame()
            
            # 转换为DataFrame
            # ⚠️ 腾讯API数组顺序: [date, open, close, high, low, volume]
            #   索引:                [0]    [1]   [2]    [3]   [4]   [5]
            records = []
            for item in records_data:
                records.append({
                    'date': item[0],      # 日期
                    'open': float(item[1]),    # 开盘价
                    'close': float(item[2]),   # 收盘价 ← 注意：是索引2
                    'high': float(item[3]),    # 最高价 ← 注意：是索引3
                    'low': float(item[4]),      # 最低价 ← 注意：是索引4
                    'volume': float(item[5])    # 成交量
                })
            
            df = pd.DataFrame(records)
            df['date'] = pd.to_datetime(df['date'])
            
            return df
            
        except Exception as e:
            logger.info(f"  收盘后无新数据: {code}")
            return pd.DataFrame()
    
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
                # 去掉前缀保存
                save_code = code.replace('sh', '').replace('sz', '')
                results[save_code] = df
                logger.debug(f"OK ({len(df)}条)")
            else:
                logger.debug("失败")
            
            # 避免请求过快
            time.sleep(0.2)
        
        logger.info(f"成功获取 {len(results)} 只ETF")
        return results
    
    def save_etf(self, code: str, df: pd.DataFrame):
        """保存ETF数据"""
        path = os.path.join(self.data_dir, f"{code}.csv")
        
        # 读取现有数据
        if os.path.exists(path):
            existing = pd.read_csv(path)
            existing['date'] = pd.to_datetime(existing['date'])
            
            # 合并数据，去重
            combined = pd.concat([existing, df])
            combined = combined.drop_duplicates(subset=['date'], keep='last')
            combined = combined.sort_values('date')
            combined.to_csv(path, index=False)
        else:
            df.to_csv(path, index=False)
    
    def get_local_latest_date(self, code: str) -> str:
        """获取本地存储的最新日期"""
        path = os.path.join(self.data_dir, f"{code}.csv")
        if os.path.exists(path):
            df = pd.read_csv(path)
            return pd.to_datetime(df['date']).max().strftime('%Y-%m-%d')
        return None
    
    def fetch_etf_incremental(self, code: str, days: int = 7) -> pd.DataFrame:
        """增量获取ETF数据
        
        1. 检查本地最新日期
        2. 计算需要补充的天数
        3. 只获取缺失的数据
        """
        local_latest = self.get_local_latest_date(code)
        
        if local_latest:
            # 计算需要获取的天数
            from datetime import datetime, timedelta
            local_date = datetime.strptime(local_latest, '%Y-%m-%d')
            today = datetime.now()
            days_diff = (today - local_date).days
            
            if days_diff <= 1:
                # 本地数据已是最新，无需请求
                logger.debug(f"  {code}: 本地已是最新 ({local_latest})")
                return pd.DataFrame()
            
            # 需要补充的天数 + 缓冲
            fetch_days = min(days_diff + 3, days)
            logger.debug(f"  {code}: 本地最新{local_latest}, 补充{fetch_days}天 ... ")
        else:
            # 首次获取，获取足够的历史数据
            fetch_days = 365  # 首次获取1年数据
            logger.debug(f"  {code}: 首次获取 {fetch_days}天 ... ")
        
        df = self.fetch_etf(code, days=fetch_days)
        
        if len(df) > 0:
            logger.debug(f"OK ({len(df)}条)")
        else:
            logger.debug("失败")
        
        return df
    
    def update_all(self, days: int = 7):
        """增量更新所有ETF (检查本地缓存，只获取最新)
        
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
    
    def update_all_incremental(self, days: int = 7):
        """增量更新所有ETF (别名，兼容旧代码)
        
        Returns:
            {code: DataFrame}
        """
        return self.update_all(days)
    
    def get_latest_date(self) -> str:
        """获取本地数据最新日期"""
        latest = None
        
        for f in os.listdir(self.data_dir):
            if f.endswith('.csv'):
                df = pd.read_csv(os.path.join(self.data_dir, f))
                date = pd.to_datetime(df['date']).max()
                if latest is None or date > latest:
                    latest = date
        
        return latest.strftime('%Y-%m-%d') if latest else None


def quick_fetch():
    """快速测试"""
    fetcher = TencentETFetcher('etf_data_live')
    
    # 测试获取1只ETF
    df = fetcher.fetch_etf('sh510300', days=5)
    print(f"获取到 {len(df)} 条数据")
    print(df.tail(3))
    
    return df


if __name__ == '__main__':
    quick_fetch()


__all__ = ['TencentETFetcher', 'quick_fetch']