#!/usr/bin/env python3
"""检测日期缺口 - 检查时间间隔是否正常"""
import sys
import os
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import DataLoader


def check_date_gaps(df, name):
    """检查日期间隔是否正常（应该是工作日，即1-3天）"""
    gaps = []
    for i in range(1, min(len(df), 50)):
        d1 = datetime.strptime(df.iloc[i-1]['date'], '%Y-%m-%d')
        d2 = datetime.strptime(df.iloc[i]['date'], '%Y-%m-%d')
        gap = (d2 - d1).days
        if gap > 7:  # 超过7天视为异常
            gaps.append((df.iloc[i-1]['date'], df.iloc[i]['date'], gap))
    return gaps


def main():
    loader = DataLoader()
    codes = loader.get_etf_list()

    print('=' * 70)
    print('日期缺口检测')
    print('=' * 70)

    has_gaps = []
    for code in codes:
        df = loader.load_single(code, min_rows=10)
        if df is not None and len(df) >= 2:
            gaps = check_date_gaps(df, code)
            if gaps:
                has_gaps.append((code, gaps))

    if has_gaps:
        print(f'\n发现 {len(has_gaps)} 只ETF有日期缺口:')
        for code, gaps in has_gaps[:10]:
            print(f'  {code}:')
            for start, end, gap in gaps:
                print(f'    {start} → {end}: {gap}天')
    else:
        print('\n✅ 所有ETF日期连续')


if __name__ == '__main__':
    main()
