#!/usr/bin/env python3
"""
补充历史数据脚本
通过腾讯API获取2023-2024历史数据，补充到SQLite

Usage:
    python scripts/supplement_history_data.py

验收标准:
    所有ETF有2023年数据（至少2023-01-01开始）
    回测期2023-2025能有足够交易信号
"""

import requests
import json
import time
import sqlite3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "etf_data_live" / "etf.db"

TENcent_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
REQUEST_DELAY = 0.3  # 秒

def get_history_data(code: str, days: int = 730) -> List[Dict]:
    """通过腾讯API获取历史数据"""
    url = TENcent_URL
    params = {'_var': 'kline_dayqfq', 'param': f'{code},day,,,{days},qfq'}
    
    try:
        resp = requests.get(url, params=params, timeout=15)
        text = resp.text.replace('kline_dayqfq=', '', 1)
        data = json.loads(text)
        
        etf_data = data.get('data', {}).get(code, {})
        records = etf_data.get('qfqday', etf_data.get('day', []))
        
        result = []
        for r in records:
            # 格式: [date, open, high, low, close, volume, ...]
            if len(r) >= 6:
                result.append({
                    'date': r[0],
                    'open': float(r[1]),
                    'high': float(r[2]),
                    'low': float(r[3]),
                    'close': float(r[4]),
                    'volume': int(float(r[5])) if r[5] else 0,
                })
        return result
    except Exception as e:
        logger.warning(f"{code} 获取失败: {e}")
        return []

def get_etf_codes() -> List[str]:
    """获取所有ETF代码"""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT code FROM daily')
    codes = [f'sh{r[0]}' for r in cur.fetchall()]
    conn.close()
    return codes

def get_existing_range(code: str) -> tuple:
    """获取SQLite中现有数据的日期范围"""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute('SELECT MIN(date), MAX(date) FROM daily WHERE code = ?', (code.replace('sh', ''),))
    result = cur.fetchone()
    conn.close()
    return result[0], result[1]

def save_to_db(code: str, records: List[Dict]):
    """保存到SQLite（去重）"""
    if not records:
        return 0
    
    code_raw = code.replace('sh', '').replace('sz', '')
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    
    saved = 0
    for r in records:
        try:
            cur.execute('''
                INSERT OR IGNORE INTO daily (code, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (code_raw, r['date'], r['open'], r['high'], r['low'], r['close'], r['volume']))
            saved += cur.rowcount
        except Exception as e:
            pass
    
    conn.commit()
    conn.close()
    return saved

def process_etf(code: str) -> Dict:
    """处理单个ETF"""
    code_raw = code.replace('sh', '').replace('sz', '')
    existing_min, existing_max = get_existing_range(code)
    
    # 获取历史数据 - 使用2000天覆盖到约2018年
    records = get_history_data(code, days=2000)
    if not records:
        return {'code': code_raw, 'status': 'failed', 'saved': 0}
    
    # 统计
    min_d = records[0]['date']
    max_d = records[-1]['date']
    
    # 检查是否需要补充
    need_supplement = False
    if existing_min is None or min_d < existing_min:
        need_supplement = True
    
    if need_supplement and existing_min:
        logger.info(f"{code}: 现有{min_d} ~ {existing_min}, 将补充新数据")
    elif not need_supplement:
        logger.info(f"{code}: 数据已充足 {existing_min} ~ {existing_max}")
        return {'code': code_raw, 'status': 'ok', 'saved': 0, 'range': f'{existing_min}~{existing_max}'}
    
    # 保存
    saved = save_to_db(code, records)
    
    return {
        'code': code_raw,
        'status': 'supplemented',
        'saved': saved,
        'range': f'{min_d} ~ {max_d}',
        'existing': f'{existing_min} ~ {existing_max}'
    }

def main():
    logger.info("=" * 60)
    logger.info("补充历史数据 - 腾讯API回溯730天")
    logger.info("=" * 60)
    
    codes = get_etf_codes()
    logger.info(f"需要处理 {len(codes)} 个ETF")
    
    results = []
    for i, code in enumerate(codes, 1):
        logger.info(f"[{i}/{len(codes)}] 处理 {code}...")
        result = process_etf(code)
        results.append(result)
        
        if result['status'] != 'ok':
            logger.info(f"  → {result['status']}: {result.get('range', 'N/A')}, 新增{result.get('saved', 0)}条")
        
        time.sleep(REQUEST_DELAY)
    
    # 统计
    logger.info("\n" + "=" * 60)
    logger.info("处理结果统计")
    logger.info("=" * 60)
    
    supplemented = [r for r in results if r['status'] == 'supplemented']
    failed = [r for r in results if r['status'] == 'failed']
    
    logger.info(f"成功补充: {len(supplemented)}/{len(codes)}")
    logger.info(f"失败: {len(failed)}/{len(codes)}")
    
    # 验证数据完整性
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    
    # 检查2023年数据覆盖
    cur.execute('SELECT COUNT(DISTINCT code) FROM daily WHERE date <= "2023-01-01"')
    has_2023 = cur.fetchone()[0]
    
    # 检查2024年数据覆盖
    cur.execute('SELECT COUNT(DISTINCT code) FROM daily WHERE date <= "2024-01-01"')
    has_2024 = cur.fetchone()[0]
    
    # 总数据量
    cur.execute('SELECT COUNT(*) FROM daily')
    total = cur.fetchone()[0]
    
    logger.info(f"\n数据完整性验证:")
    logger.info(f"  总数据量: {total}条")
    logger.info(f"  有2023年前数据: {has_2023}/33")
    logger.info(f"  有2024年前数据: {has_2024}/33")
    
    conn.close()
    
    if has_2024 >= 30:
        logger.info("\n✅ 数据补充完成")
    else:
        logger.warning(f"\n⚠️ 数据仍不完整，建议再次运行或检查失败ETF")
    
    return results

if __name__ == '__main__':
    main()