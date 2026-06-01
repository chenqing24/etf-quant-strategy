#!/usr/bin/env python3
"""
ETF数据重采集脚本

合并自:
- fill_missing_etf_history.py (补全特定ETF)
- supplement_history_data.py (批量补全历史)

功能:
1. 支持全量采集（从etf_names表读取所有ETF）
2. 支持指定股票列表重采集
3. 支持指定时间段（默认最近3年=1095天）
4. 使用统一采集入口DataWriter

Usage:
    # 全量采集（默认最近3年）
    python scripts/refetch_etf_data.py

    # 指定股票列表
    python scripts/refetch_etf_data.py --codes 510300,159919,512480

    # 指定日期范围
    python scripts/refetch_etf_data.py --start 2023-01-01 --end 2026-01-01

    # 指定股票+日期范围
    python scripts/refetch_etf_data.py --codes 510300,159919 --days 365

    # 从配置文件读取ETF列表
    python scripts/refetch_etf_data.py --from-config
"""

import argparse
import json
import time
import sys
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
import logging

import pandas as pd
import requests

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.writer import DataWriter
from src.constants import TENCENT_BASE_URL, HTTP_TIMEOUT_SHORT

# 配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

REQUEST_DELAY = 0.3  # 秒
MAX_WORKERS = 10  # 并发数


def get_prefix(code: str) -> str:
    """获取交易所前缀"""
    if code.startswith(('510', '511', '512', '513', '515', '516', '518', '588')):
        return 'sh'
    return 'sz'


def get_all_etf_codes() -> List[str]:
    """从数据库读取所有ETF代码（使用 DataLoader）"""
    from src.data.loader import DataLoader
    loader = DataLoader()
    codes = loader.get_etf_list()

    logger.info(f"读取到 {len(codes)} 只ETF")
    return codes


def get_core_etf_codes() -> List[str]:
    """从配置文件读取核心ETF列表"""
    try:
        from src.config.etf_pools import ETF_POOLS
        codes = []
        for pool in ETF_POOLS.values():
            codes.extend(pool)
        return list(set(codes))
    except Exception as e:
        logger.warning(f"无法读取配置文件: {e}")
        return []


def get_existing_range(code: str, db_path: str) -> tuple:
    """获取SQLite中现有数据的日期范围（使用 DataLoader）"""
    from src.data.loader import DataLoader
    loader = DataLoader()
    range_info = loader.get_date_range(code)
    return range_info.get('min'), range_info.get('max')


def fetch_historical_from_tencent(code: str, days: int) -> List[Dict]:
    """
    从腾讯API获取历史K线数据（委托给 TencentETFetcher）

    Args:
        code: ETF代码（无前缀）
        days: 获取天数

    Returns:
        list: [date, open, close, high, low, volume] 格式的列表
    """
    from src.data.fetcher import TencentETFetcher
    prefix = get_prefix(code)
    full_code = f"{prefix}{code}"
    df = TencentETFetcher().fetch_etf(full_code, days=days)
    if df is None or df.empty:
        return []
    # 转换为列表格式（兼容下游 records_to_dataframe）
    return df[['date', 'open', 'close', 'high', 'low', 'volume']].values.tolist()


def records_to_dataframe(records: list) -> pd.DataFrame:
    """
    将腾讯API数据转换为DataFrame
    
    腾讯API格式: [date, open, close, high, low, volume]
    DataFrame格式: [date, open, high, low, close, volume]
    """
    if not records:
        return pd.DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    
    data = []
    for item in records:
        try:
            # 腾讯数据顺序: [date, open, close, high, low, volume]
            row = {
                'date': item[0],
                'open': float(item[1]) if item[1] else 0,
                'close': float(item[2]) if item[2] else 0,
                'high': float(item[3]) if item[3] else 0,
                'low': float(item[4]) if item[4] else 0,
                'volume': int(float(item[5])) if item[5] else 0,
            }
            data.append(row)
        except (IndexError, ValueError):
            continue
    
    return pd.DataFrame(data)


def fetch_and_write(
    code: str,
    days: int,
    db_path: str,
    writer: DataWriter
) -> tuple:
    """
    获取并写入单只ETF数据
    
    Returns:
        (code, fetched_count, written_count, error)
    """
    # 获取数据
    records = fetch_historical_from_tencent(code, days)
    
    if not records:
        return (code, 0, 0, "No data from API")
    
    # 转换格式
    df = records_to_dataframe(records)
    
    if df.empty:
        return (code, 0, 0, "Empty DataFrame")
    
    # 写入数据库
    try:
        written = writer.write_daily(code, df)
        return (code, len(df), written, None)
    except Exception as e:
        return (code, len(df), 0, str(e))


def main():
    parser = argparse.ArgumentParser(description='ETF数据重采集脚本')
    
    # ETF列表选项
    parser.add_argument('--codes', type=str, help='指定股票代码，逗号分隔')
    parser.add_argument('--from-config', action='store_true', help='从配置文件读取ETF列表')
    
    # 日期范围选项
    parser.add_argument('--days', type=int, default=1095, help='获取天数（默认3年=1095天）')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD）')
    
    # 其他选项
    parser.add_argument('--workers', type=int, default=MAX_WORKERS, help=f'并发数（默认{MAX_WORKERS}）')
    parser.add_argument('--dry-run', action='store_true', help='只打印将要采集的ETF，不实际采集')
    
    args = parser.parse_args()
    
    # 确定采集的ETF列表
    if args.codes:
        codes = [c.strip() for c in args.codes.split(',')]
        source = "命令行参数"
    elif args.from_config:
        codes = get_core_etf_codes()
        source = "配置文件"
    else:
        codes = get_all_etf_codes()
        source = "etf_names表（全量）"
    
    logger.info(f"=" * 50)
    logger.info(f"ETF数据重采集")
    logger.info(f"=" * 50)
    logger.info(f"ETF来源: {source}")
    logger.info(f"ETF数量: {len(codes)}")
    logger.info(f"采集天数: {args.days}天")
    if args.start:
        logger.info(f"日期范围: {args.start} ~ {args.end or '至今'}")
    
    if args.dry_run:
        logger.info(f"DRY RUN: 前10只ETF: {codes[:10]}")
        return
    
    # 初始化
    base_dir = Path(__file__).parent.parent
    db_path = str(base_dir / "etf_data_live" / "etf.db")
    writer = DataWriter(db_path)
    
    # 统计
    results = {
        'total': len(codes),
        'success': 0,
        'failed': 0,
        'total_fetched': 0,
        'total_written': 0,
    }
    errors = []
    
    # 并发采集
    start_time = time.time()
    logger.info(f"开始并发采集（workers={args.workers}）...")
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(fetch_and_write, code, args.days, db_path, writer): code
            for code in codes
        }
        
        for i, future in enumerate(as_completed(futures), 1):
            code = futures[future]
            try:
                code_res, fetched, written, error = future.result()
                
                if error:
                    errors.append({'code': code_res, 'error': error})
                    logger.warning(f"[{i}/{len(codes)}] {code_res}: 失败 - {error}")
                else:
                    results['success'] += 1
                    results['total_fetched'] += fetched
                    results['total_written'] += written
                    logger.info(f"[{i}/{len(codes)}] {code_res}: 获取{fetched}条，写入{written}条")
                
            except Exception as e:
                results['failed'] += 1
                errors.append({'code': code, 'error': str(e)})
                logger.error(f"[{i}/{len(codes)}] {code}: 异常 - {e}")
            
            # 防止频率过快
            time.sleep(REQUEST_DELAY)
    
    # 汇总
    elapsed = time.time() - start_time
    logger.info(f"")
    logger.info(f"=" * 50)
    logger.info(f"采集完成")
    logger.info(f"=" * 50)
    logger.info(f"总耗时: {elapsed:.1f}秒")
    logger.info(f"成功: {results['success']}/{results['total']}")
    logger.info(f"失败: {results['failed']}")
    logger.info(f"获取: {results['total_fetched']}条记录")
    logger.info(f"写入: {results['total_written']}条新记录")
    
    if errors:
        logger.warning(f"失败列表（前10）:")
        for err in errors[:10]:
            logger.warning(f"  - {err['code']}: {err['error']}")


if __name__ == '__main__':
    main()