#!/usr/bin/env python3
"""ETF去重分析 - 识别性质和特征高度相似的ETF"""
import sys
import os
import json
import pandas as pd
from typing import List

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import DataLoader


def get_etf_info(code: str, loader: DataLoader):
    """获取ETF详细信息 - 使用 DataLoader"""
    df = loader.load_single(code, min_rows=1)
    if df is None or df.empty:
        return None
    return {
        'code': code,
        'rows': len(df),
        'start_date': df['date'].min(),
        'end_date': df['date'].max(),
        'latest_close': float(df['close'].iloc[-1])
    }


def main():
    # 最终ETF池（37只）
    ETF_POOL = [
        '159363', '159516', '159558', '159845', '159915', '159949', '159967', '159995',
        '510050', '510300', '510310', '510500', '512000', '512100', '512480', '512760',
        '512800', '513310', '515790', '516160', '588000', '588080', '588170', '588200',
        '588290', '159801', '159806', '159857', '159919', '159928', '159952', '510100',
        '510150', '510660', '512010', '512170', '512500'
    ]

    loader = DataLoader()

    print('ETF信息统计:')
    print('=' * 80)

    info_list = []
    for code in ETF_POOL:
        info = get_etf_info(code, loader)
        if info:
            info_list.append(info)
            print(f'{code}: {info["rows"]}条 {info["start_date"]}~{info["end_date"]}')

    print(f'\n总计: {len(info_list)}/{len(ETF_POOL)}只有数据')

    # 保存为 JSON
    output_path = 'data/deduplicate_etf_info.json'
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(info_list, f, ensure_ascii=False, indent=2)
    print(f'\n已保存: {output_path}')


if __name__ == '__main__':
    main()
