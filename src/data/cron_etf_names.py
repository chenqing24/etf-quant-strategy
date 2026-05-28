#!/usr/bin/env python3
"""
ETF名称采集定时任务
==================
定时任务入口，支持以下命令：
- fetch_core: 采集核心池
- fetch_extended: 采集扩展池
- fetch_all: 采集全部
- recover: 恢复失败的任务
- status: 查看状态
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.etf_name_collector import ETFNameCollector
from src.data.etf_lifecycle import ETFLifecycleManager
from src.config.etf_pools import get_codes_by_pool, get_all_codes, validate_config
from src.utils.logger import get_logger
from datetime import datetime

logger = get_logger()


def fetch_core():
    """采集核心池"""
    logger.info("="*60)
    logger.info("开始采集核心池")
    logger.info("="*60)
    
    collector = ETFNameCollector()
    results = collector.fetch_all_by_pool('core')
    
    # 打印摘要
    success = sum(1 for r in results.values() if r.success)
    failed = len(results) - success
    
    print(f"\n核心池采集完成:")
    print(f"  总数: {len(results)}")
    print(f"  成功: {success}")
    print(f"  失败: {failed}")
    
    return results


def fetch_extended():
    """采集扩展池"""
    logger.info("="*60)
    logger.info("开始采集扩展池")
    logger.info("="*60)
    
    collector = ETFNameCollector()
    results = collector.fetch_all_by_pool('extended')
    
    # 打印摘要
    success = sum(1 for r in results.values() if r.success)
    failed = len(results) - success
    
    print(f"\n扩展池采集完成:")
    print(f"  总数: {len(results)}")
    print(f"  成功: {success}")
    print(f"  失败: {failed}")
    
    return results


def fetch_all():
    """采集全部池"""
    logger.info("="*60)
    logger.info("开始采集全部ETF")
    logger.info("="*60)
    
    collector = ETFNameCollector()
    
    # 先采集核心池
    core_results = collector.fetch_all_by_pool('core')
    core_success = sum(1 for r in core_results.values() if r.success)
    
    print(f"\n核心池: {len(core_results)}只, 成功{core_success}只")
    
    # 批次间休息
    import time
    logger.info("批次间休息60秒...")
    time.sleep(60)
    
    # 再采集扩展池
    extended_results = collector.fetch_all_by_pool('extended')
    extended_success = sum(1 for r in extended_results.values() if r.success)
    
    print(f"扩展池: {len(extended_results)}只, 成功{extended_success}只")
    
    # 总计
    total = len(core_results) + len(extended_results)
    total_success = core_success + extended_success
    
    print(f"\n总计: {total}只, 成功{total_success}只, 成功率{total_success/total:.1%}")
    
    return {'core': core_results, 'extended': extended_results}


def recover():
    """恢复失败的任务"""
    logger.info("="*60)
    logger.info("恢复失败任务")
    logger.info("="*60)
    
    collector = ETFNameCollector()
    results = collector.fetch_failed_only()
    
    if results:
        success = sum(1 for r in results.values() if r.success)
        print(f"\n恢复完成: {len(results)}只, 成功{success}只")
    else:
        print("\n无待恢复任务")
    
    return results


def status():
    """查看状态"""
    from src.data.database import Database
    
    db = Database()
    
    # 监控指标
    metrics = db.get_metrics_summary(hours=24)
    
    # 重试队列
    retry_tasks = db.get_retry_tasks(limit=20)
    
    # 池摘要
    manager = ETFLifecycleManager()
    pool_summary = manager.get_pool_summary()
    
    print("\n" + "="*60)
    print("ETF名称采集状态")
    print("="*60)
    
    print(f"\n【最近24小时监控】")
    print(f"  总采集: {metrics['total']}")
    print(f"  成功率: {metrics['success_rate']:.1%}")
    print(f"  平均耗时: {metrics['avg_duration_ms']:.0f}ms")
    if metrics['failed_codes']:
        print(f"  失败: {len(metrics['failed_codes'])}只")
        print(f"    {metrics['failed_codes'][:5]}{'...' if len(metrics['failed_codes']) > 5 else ''}")
    
    print(f"\n【重试队列】")
    print(f"  待处理: {len(retry_tasks)}")
    if retry_tasks:
        for task in retry_tasks[:5]:
            print(f"    {task['code']} (第{task['attempt_count']}次)")
    
    print(f"\n【ETF池】")
    for pool_type, stats in pool_summary.items():
        print(f"  {pool_type}: {stats['total']}只 (活跃:{stats['active']}, 停牌:{stats['inactive']}, 失败:{stats['failed']})")
    
    print()


def sync_config():
    """同步配置"""
    logger.info("同步ETF池配置...")
    
    validate_config()
    
    manager = ETFLifecycleManager()
    manager.sync_pool_config()
    
    print("配置同步完成")


# ========== 主入口 ==========

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='ETF名称采集定时任务')
    
    # 子命令
    subparsers = parser.add_subparsers(dest='command', help='子命令')
    
    subparsers.add_parser('fetch_core', help='采集核心池')
    subparsers.add_parser('fetch_extended', help='采集扩展池')
    subparsers.add_parser('fetch_all', help='采集全部')
    subparsers.add_parser('recover', help='恢复失败任务')
    subparsers.add_parser('status', help='查看状态')
    subparsers.add_parser('sync', help='同步配置')
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    # 执行
    if args.command == 'fetch_core':
        fetch_core()
    elif args.command == 'fetch_extended':
        fetch_extended()
    elif args.command == 'fetch_all':
        fetch_all()
    elif args.command == 'recover':
        recover()
    elif args.command == 'status':
        status()
    elif args.command == 'sync':
        sync_config()