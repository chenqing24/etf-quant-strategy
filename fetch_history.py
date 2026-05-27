#!/usr/bin/env python3
"""批量采集ETF历史数据 - 补充2023年历史"""
import requests
import json
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.data.database import Database
from src.data.fetcher import TencentETFetcher


def fetch_etf_history(code: str, days: int = 1500) -> dict:
    """获取ETF历史数据"""
    # 处理code格式
    if not code.startswith(('sh', 'sz')):
        exchange = 'sh' if code.startswith(('510', '511', '512', '513', '515', '516', '518', '588')) else 'sz'
        full_code = f'{exchange}{code}'
    else:
        full_code = code
    
    params = {
        '_var': 'kline_dayqfq',
        'param': f'{full_code},day,,,{days},qfq'
    }
    
    try:
        # 增加超时时间
        response = requests.get(
            'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',
            params=params,
            timeout=60  # 增加超时
        )
        text = response.text.replace('kline_dayqfq=', '', 1)
        data = json.loads(text)
        
        etf_data = data.get('data', {}).get(full_code, {})
        records = etf_data.get('qfqday') or etf_data.get('day') or []
        
        if not records:
            return {'code': code, 'status': 'no_data', 'count': 0}
        
        # 转换为DataFrame
        df = pd.DataFrame(records, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
        df['code'] = code
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        return {
            'code': code,
            'status': 'success',
            'count': len(df),
            'df': df,
            'first_date': df['date'].min().strftime('%Y-%m-%d'),
            'last_date': df['date'].max().strftime('%Y-%m-%d')
        }
    except Exception as e:
        return {'code': code, 'status': 'error', 'error': str(e), 'count': 0}


def main():
    print("=" * 60)
    print("ETF历史数据批量采集")
    print("=" * 60)
    
    # 分批ETF列表
    batches = [
        # Batch 1
        ['512200', '512690', '159928', '159825', '512010'],
        # Batch 2
        ['512500', '159952', '159997', '159995', '512760'],
        # Batch 3
        ['159801', '159823', '515050', '159857', '516160'],
        # Batch 4
        ['159806', '159942', '510050', '512660', '159920'],
        # Batch 5
        ['159867', '518880', '159934', '511010', '516050'],
        # Batch 6
        ['159577', '515000', '513100'],
    ]
    
    db = Database()
    total_success = 0
    total_error = 0
    
    for batch_idx, codes in enumerate(batches):
        print(f"\n--- Batch {batch_idx + 1}/{len(batches)} ---")
        
        for code in codes:
            result = fetch_etf_history(code)
            
            if result['status'] == 'success':
                df = result['df']
                # 写入数据库
                for _, row in df.iterrows():
                    db.insert_or_update('daily_price', {
                        'code': code,
                        'date': row['date'].strftime('%Y-%m-%d'),
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': float(row['volume']) if pd.notna(row['volume']) else 0
                    }, ['code', 'date'])
                
                print(f"✅ {code}: {result['count']}条")
                total_success += 1
            else:
                print(f"❌ {code}: {result['status']}")
                total_error += 1
            
            time.sleep(1)
    
    print()
    print("=" * 60)
    print(f"采集完成: 成功 {total_success}, 失败 {total_error}")
    print("=" * 60)


if __name__ == '__main__':
    main()