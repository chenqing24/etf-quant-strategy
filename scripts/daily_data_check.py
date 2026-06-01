#!/usr/bin/env python3
"""
每日数据健康检查脚本
收盘后自动运行，检查数据质量和新鲜度
"""
import sys
import os
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.manager import DataFacade
from src.data.loader import DataLoader


def get_latest_dates_sample(codes, sample_size=10):
    """抽查多只ETF的最新日期 - 使用 DataLoader"""
    loader = DataLoader()
    results = {}
    for code in codes[:sample_size]:
        latest = loader.get_latest_date(code)
        results[code] = latest
    return results


def main():
    facade = DataFacade('etf_data_live')
    loader = DataLoader()

    # 获取所有ETF
    codes = loader.get_etf_list()
    print(f'总ETF数: {len(codes)}')

    # 抽查最新日期
    samples = get_latest_dates_sample(codes, 10)
    print('\n抽样最新日期:')
    for code, date in samples.items():
        print(f'  {code}: {date}')

    # 检查新鲜度
    today = datetime.now().date()
    delays = {}
    for code in codes:
        latest = loader.get_latest_date(code)
        if latest:
            try:
                latest_date = datetime.strptime(latest, '%Y-%m-%d').date()
                delay = (today - latest_date).days
                delays[code] = delay
            except:
                pass

    if delays:
        avg_delay = sum(delays.values()) / len(delays)
        max_delay = max(delays.values())
        print(f'\n延迟统计:')
        print(f'  平均延迟: {avg_delay:.1f}天')
        print(f'  最大延迟: {max_delay}天')
        print(f'  延迟>3天的: {sum(1 for d in delays.values() if d > 3)}只')

        # 钉钉告警
        if max_delay > 5:
            print(f'⚠️ 数据延迟告警: 最大延迟{max_delay}天, 平均{avg_delay:.1f}天')


if __name__ == '__main__':
    main()
