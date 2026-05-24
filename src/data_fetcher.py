#!/usr/bin/env python3
"""腾讯ETF数据采集"""
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List
import time
import os


class TencentETFetcher:
    """腾讯ETF数据采集器"""
    
    # 腾讯API地址
    BASE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    
    # ETF代码列表 (需要带sh/sz前缀)
    ETF_CODES = [
        'sh510300', 'sh510500', 'sh159919', 'sh159915',  # 宽基
        'sh512880', 'sh512170', 'sh512200', 'sh512690',  # 金融
        'sh159928', 'sh159825', 'sh510630',              # 消费
        'sh512010', 'sh512500', 'sh159838', 'sh159952',  # 医药
        'sh159997', 'sh159995', 'sh512760', 'sh159801',  # 科技
        'sh159823', 'sh515050',                           # 科技
        'sh159857', 'sh516160', 'sh159806',              # 新能源
        'sh159942', 'sh510050',                           # 周期
        'sh512660', 'sh159995',                          # 军工
        'sh159920', 'sh159867', 'sh513360',             # 港股
        'sh518880', 'sh159934',                          # 商品
        'sh511010', 'sh511880', 'sh511990',             # 债券
        'sh516050', 'sh159577', 'sh515000', 'sh513100', # 新兴产业
    ]
    
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
            data = response.json()
            
            # 解析数据
            key = f'data.{code}.day.qfq'
            parts = key.split('.')
            for p in parts:
                data = data.get(p, {})
            
            if not data:
                print(f"  警告: {code} 无数据")
                return pd.DataFrame()
            
            # 转换为DataFrame
            records = []
            for item in data:
                date, open_p, high, low, close, volume = item
                records.append({
                    'date': date,
                    'open': float(open_p),
                    'high': float(high),
                    'low': float(low),
                    'close': float(close),
                    'volume': float(volume)
                })
            
            df = pd.DataFrame(records)
            df['date'] = pd.to_datetime(df['date'])
            
            return df
            
        except Exception as e:
            print(f"  错误: {code} - {e}")
            return pd.DataFrame()
    
    def fetch_all(self, days: int = 30) -> Dict[str, pd.DataFrame]:
        """获取所有ETF数据
        
        Returns:
            {code: DataFrame}
        """
        results = {}
        
        print(f"开始采集 {len(self.ETF_CODES)} 只ETF数据...")
        
        for i, code in enumerate(self.ETF_CODES, 1):
            print(f"  [{i}/{len(self.ETF_CODES)}] 获取 {code}...", end=" ")
            df = self.fetch_etf(code, days)
            if len(df) > 0:
                # 去掉前缀保存
                save_code = code.replace('sh', '').replace('sz', '')
                results[save_code] = df
                print(f"OK ({len(df)}条)")
            else:
                print("失败")
            
            # 避免请求过快
            time.sleep(0.2)
        
        print(f"\n成功获取 {len(results)} 只ETF")
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
    
    def update_all(self, days: int = 7):
        """增量更新所有ETF
        
        Args:
            days: 额外获取的天数(用于补全)
        """
        results = self.fetch_all(days=days)
        
        for code, df in results.items():
            self.save_etf(code, df)
        
        return results
    
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