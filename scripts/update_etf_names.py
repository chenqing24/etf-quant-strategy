#!/usr/bin/env python3
"""
回填ETF名称到数据库（一次性使用）

从腾讯API获取所有ETF的真实名称，存入stock_info表
"""
import sys
import os
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.fetcher import TencentETFetcher, _fetch_name_from_api, _get_prefix
from src.data.database import Database
from src.utils.logger import get_logger

logger = get_logger()


def backfill_etf_names(dry_run: bool = False):
    """回填所有ETF名称
    
    Args:
        dry_run: True 则只打印，不写入数据库
    """
    fetcher = TencentETFetcher()
    db = Database()
    
    # 确保表结构已扩展
    logger.info("检查数据库表结构...")
    db.migrate_schema()
    
    # 获取所有ETF代码
    codes = fetcher.get_etf_codes()
    logger.info(f"共 {len(codes)} 只ETF待处理")
    
    success = 0
    skipped = 0
    failed = 0
    
    results = []
    
    for code_with_prefix in codes:
        # 去掉前缀
        code = code_with_prefix.replace('sh', '').replace('sz', '')
        
        # 检查数据库中是否已有正确名称
        existing = db.get_etf_name(code)
        if existing and not existing.startswith('ETF_'):
            logger.debug(f"跳过 {code}: 已有名称 '{existing}'")
            skipped += 1
            results.append(('skip', code, existing))
            continue
        
        # 从API获取名称
        name = _fetch_name_from_api(code)
        
        if name:
            if dry_run:
                logger.info(f"[Dry Run] {code}: {name}")
                results.append(('dry', code, name))
            else:
                db.update_etf_name(code, name)
                logger.info(f"✅ {code}: {name}")
                results.append(('success', code, name))
            success += 1
        else:
            logger.warning(f"❌ {code}: 获取失败")
            results.append(('fail', code, None))
            failed += 1
        
        # 避免API限流
        time.sleep(0.2)
    
    # 打印统计
    print("\n" + "="*50)
    print("回填完成")
    print("="*50)
    print(f"  成功: {success}")
    print(f"  跳过: {skipped}")
    print(f"  失败: {failed}")
    print(f"  总计: {len(codes)}")
    
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description='回填ETF名称到数据库')
    parser.add_argument('--dry', action='store_true', help='模拟运行，不写入数据库')
    args = parser.parse_args()
    
    if args.dry:
        print("⚠️  Dry Run 模式，不写入数据库\n")
    
    backfill_etf_names(dry_run=args.dry)


if __name__ == '__main__':
    main()