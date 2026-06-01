#!/usr/bin/env python3
"""检查缺失的ETF - 对比配置池和数据库"""
import sys
import os
from typing import List

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import DataLoader


def get_etf_pool() -> List[str]:
    """获取配置的ETF池"""
    try:
        from src.config.etf_pools import ETF_POOLS
        codes = []
        for pool in ETF_POOLS.values():
            codes.extend(pool)
        return list(set(codes))
    except Exception as e:
        print(f'读取配置失败: {e}')
        return []


def main():
    loader = DataLoader()
    pool = get_etf_pool()
    db_codes = set(loader.get_etf_list())

    if not pool:
        print('配置池为空，无法检查')
        return

    print(f'配置ETF池: {len(pool)}只')
    print(f'数据库ETF: {len(db_codes)}只')

    # 找出缺失
    missing = [c for c in pool if c not in db_codes]
    extra = [c for c in db_codes if c not in pool]

    print(f'\n缺失: {len(missing)}只')
    for code in missing[:20]:
        print(f'  - {code}')

    if extra:
        print(f'\n数据库有但配置无: {len(extra)}只')
        for code in extra[:20]:
            print(f'  + {code}')

    if not missing:
        print('\n✅ 所有配置ETF都已在数据库')


if __name__ == '__main__':
    main()
