#!/usr/bin/env python3
"""
DB → top500_target_pool.txt 导出脚本

SOP-13 + v2.0 文档：.txt 文件是导出产物
本脚本把 etf_names.pool_role='core' 的代码导出到 .txt
DB 是 single source of truth，.txt 仅为方便人看

使用：
    cd etf_strategy
    python3 scripts/export_pool_to_txt.py
"""
import sys
from datetime import datetime
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.data.etf_pool_repository import ETFRepository

OUT_FILE = ROOT / 'etf_data_live' / 'top500_target_pool.txt'


def main():
    """导出 CORE 池 → .txt"""
    repo = ETFRepository()
    core = repo.list_codes('core')

    if not core:
        print('❌ CORE 池为空，请先跑 migrate_pool_roles.py')
        sys.exit(1)

    # 检查是否有 300ETF 误入 CORE
    csi300_in_core = []
    for code in core:
        meta = repo.get_meta(code)
        if meta and meta.get('name', '').find('沪深300') >= 0:
            csi300_in_core.append(code)
    if csi300_in_core:
        print(f'⚠️ 警告：CORE 池含 300ETF: {csi300_in_core}')
        print('   应标 reference 而非 core')

    # 写头部注释
    lines = [
        f'# ETF 池（DB 导出）',
        f'# 导出时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
        f'# CORE 池: {len(core)} 只',
        f'# 筛选标准：成交额>=10亿 + 规模>=10亿',
        f'# 排除：货币基金、债券基金、QDII海外、商品ETF',
        f'# 仅保留：宽基指数+行业ETF，同主题去重',
        f'# 510300 已剔除（沪深300 ETF 全部为 reference 池，参考 SOP-13）',
        f'#',
        f'# 注意：DB（etf_names.pool_role="core"）是单一真相源',
        f'#       本文件为导出产物，由 scripts/export_pool_to_txt.py 重新生成',
        '',
        'ETF_POOL = [',
    ]
    for i, code in enumerate(core):
        meta = repo.get_meta(code)
        name = meta.get('name', '') if meta else ''
        comma = ',' if i < len(core) - 1 else ''
        lines.append(f"    '{code}',{('  # ' + name) if name else ''}")
    lines.append(']')
    lines.append('')

    OUT_FILE.write_text('\n'.join(lines), encoding='utf-8')
    print(f'✅ 导出 {len(core)} 只 CORE 到 {OUT_FILE}')

    if csi300_in_core:
        print(f'⚠️ 警告：包含 300ETF {csi300_in_core}（建议标 reference）')
        sys.exit(2)


if __name__ == '__main__':
    main()
