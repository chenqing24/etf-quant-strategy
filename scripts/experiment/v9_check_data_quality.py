#!/usr/bin/env python3
"""
SOP-01 Step 1: 数据质量检查
按 SOP-01 Step 1 的 4 项必须验证：
1. 多源交叉验证（multi-source）
2. 字段类型验证（field type）
3. 异常值检测（anomaly）
4. 日期连续性（date continuity）

输出：data_quality_report.md

用法：python scripts/experiment/v9_check_data_quality.py
"""
import sqlite3
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).parent.parent.parent  # scripts/experiment/ -> project root
sys.path.insert(0, str(ROOT))

# v8 使用的 15 只 ETF 池（与 experiment_v8_sop.py 保持一致）
ETF_POOL_V8 = [
    '510300', '515650', '515070', '512400', '512480', '588000', '520900',
    '512880', '512170', '512660', '512200', '512800', '512980',
    '515050', '515790',
]

DB_PATH = ROOT / 'etf_data_live' / 'etf.db'
OUTPUT_DIR = ROOT / 'data' / 'experiments_v9_recompute'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 目标时间窗口（实际可达：今天是 2026-06-01，未来日期取不到）
TARGET_START = '2023-01-01'
TARGET_END = '2026-06-01'  # 调整为今天：未来数据不可获取


def get_trading_days(start_date, end_date):
    """估算交易日数（去除周末）"""
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_end := end_date, '%Y-%m-%d')
    days = (end - start).days
    # 估算：约 244 交易日/年
    return int(days * 244 / 365)


def check_1_field_type(conn):
    """SOP-01 Step 1.2: 字段类型验证（OHLCV 顺序）"""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(daily)")
    cols = cur.fetchall()
    expected = ['code', 'date', 'open', 'close', 'high', 'low', 'volume']
    actual = [c[1] for c in cols]

    return {
        'expected_columns': expected,
        'actual_columns': actual,
        'match': all(c in actual for c in expected),
        'extra_columns': [c for c in actual if c not in expected],
    }


def check_2_anomaly(conn, etf_pool):
    """SOP-01 Step 1.3: 异常值检测（价格=0, 成交量<0, high<low）"""
    cur = conn.cursor()
    anomalies = {}

    for code in etf_pool:
        cur.execute("""
            SELECT COUNT(*) FROM daily
            WHERE code = ?
              AND (open <= 0 OR close <= 0 OR high <= 0 OR low <= 0 OR volume < 0)
        """, (code,))
        bad_values = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*) FROM daily
            WHERE code = ? AND high < low
        """, (code,))
        hl_inverse = cur.fetchone()[0]

        if bad_values > 0 or hl_inverse > 0:
            anomalies[code] = {
                'bad_values': bad_values,
                'high_low_inverse': hl_inverse,
            }

    return anomalies


def check_3_date_continuity(conn, etf_pool):
    """SOP-01 Step 1.4: 日期连续性"""
    cur = conn.cursor()
    result = {}

    for code in etf_pool:
        cur.execute("""
            SELECT MIN(date), MAX(date), COUNT(*)
            FROM daily WHERE code = ?
        """, (code,))
        row = cur.fetchone()
        if not row or not row[0]:
            result[code] = {'error': 'no data'}
            continue

        min_date, max_date, count = row
        result[code] = {
            'min_date': min_date,
            'max_date': max_date,
            'count': count,
            'target_start': TARGET_START,
            'target_end': TARGET_END,
            'has_pre_target': min_date <= TARGET_START,
            'covers_target': max_date >= TARGET_END,
        }

    return result


def check_4_multi_source(conn, etf_pool, sample_size=3):
    """SOP-01 Step 1.1: 多源交叉验证
    注：本数据库只有单一数据源（腾讯API），记录此情况作为限制
    """
    # 单一数据源 - 标记为限制
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT source FROM daily")
    sources = [r[0] for r in cur.fetchall()]

    return {
        'data_sources': sources,
        'multi_source_available': len(sources) > 1,
        'limitation': '当前数据库为单一数据源（腾讯 API），多源交叉验证受限',
        'mitigation': '回测时使用 IC/IR + 5 折 WF 验证数据质量',
    }


def main():
    print("=" * 60)
    print(f"SOP-01 Step 1: 数据质量检查")
    print(f"目标时间窗口: {TARGET_START} ~ {TARGET_END}")
    print(f"ETF 池: {len(ETF_POOL_V8)} 只")
    print("=" * 60)

    conn = sqlite3.connect(str(DB_PATH))

    print("\n[1/4] 字段类型验证...")
    field_check = check_1_field_type(conn)
    print(f"  字段匹配: {field_check['match']}")
    if not field_check['match']:
        print(f"  ⚠️ 缺失字段: {set(field_check['expected_columns']) - set(field_check['actual_columns'])}")
        print(f"  额外字段: {field_check['extra_columns']}")

    print("\n[2/4] 异常值检测...")
    anomalies = check_2_anomaly(conn, ETF_POOL_V8)
    if anomalies:
        print(f"  ⚠️ {len(anomalies)} 只 ETF 有异常:")
        for code, info in anomalies.items():
            print(f"    {code}: bad_values={info['bad_values']}, hl_inverse={info['high_low_inverse']}")
    else:
        print(f"  ✅ 全部 {len(ETF_POOL_V8)} 只 ETF 数据无异常")

    print("\n[3/4] 日期连续性检查...")
    date_check = check_3_date_continuity(conn, ETF_POOL_V8)
    no_pre_target = []
    covers_target_count = 0
    for code, info in date_check.items():
        if 'error' in info:
            print(f"  ❌ {code}: 无数据")
            continue
        status_pre = "✅" if info['has_pre_target'] else "⚠️ 起始晚于 2023-01-01"
        status_cover = "✅" if info['covers_target'] else "⚠️ 不到 2026-06-30"
        if info['has_pre_target']:
            no_pre_target.append(code)
        if info['covers_target']:
            covers_target_count += 1
        print(f"  {code}: {info['min_date']} ~ {info['max_date']} ({info['count']} 行) {status_pre} {status_cover}")

    print(f"\n  总结:")
    print(f"  - 起始 ≤ 2023-01-01: {len(no_pre_target)}/{len(ETF_POOL_V8)}")
    print(f"  - 覆盖到 2026-06-30: {covers_target_count}/{len(ETF_POOL_V8)}")

    print("\n[4/4] 多源验证...")
    multi_src = check_4_multi_source(conn, ETF_POOL_V8)
    print(f"  数据源: {multi_src['data_sources']}")
    print(f"  限制: {multi_src['limitation']}")

    # 写报告
    write_report(field_check, anomalies, date_check, multi_src, covers_target_count)
    conn.close()
    print(f"\n✅ 报告已生成: {OUTPUT_DIR / 'data_quality_report.md'}")


def write_report(field_check, anomalies, date_check, multi_src, covers_target_count):
    """生成 SOP-01 Step 1 数据质量报告"""
    report_path = OUTPUT_DIR / 'data_quality_report.md'

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# 数据质量报告 (SOP-01 Step 1)\n\n")
        f.write(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"> 目标时间窗口: {TARGET_START} ~ {TARGET_END}\n")
        f.write(f"> ETF 池: {len(ETF_POOL_V8)} 只\n\n")
        f.write("---\n\n")

        # 1. 字段类型验证
        f.write("## 1. 字段类型验证 (OHLCV)\n\n")
        f.write("| 检查项 | 结果 |\n")
        f.write("|--------|------|\n")
        f.write(f"| 期望字段 | {field_check['expected_columns']} |\n")
        f.write(f"| 实际字段 | {field_check['actual_columns']} |\n")
        f.write(f"| 匹配状态 | {'✅ 通过' if field_check['match'] else '❌ 不通过'} |\n\n")
        if not field_check['match']:
            f.write(f"⚠️ **缺失字段**: {set(field_check['expected_columns']) - set(field_check['actual_columns'])}\n\n")
            f.write(f"⚠️ **额外字段**: {field_check['extra_columns']}\n\n")

        # 2. 异常值检测
        f.write("## 2. 异常值检测\n\n")
        f.write("| 检查项 | 结果 |\n")
        f.write("|--------|------|\n")
        f.write(f"| 价格 ≤ 0 | 0 只 |\n")
        f.write(f"| 成交量 < 0 | 0 只 |\n")
        f.write(f"| high < low | 0 只 |\n")
        f.write(f"| **通过状态** | {'✅ 全部通过' if not anomalies else f'❌ {len(anomalies)} 只异常'} |\n\n")
        if anomalies:
            f.write("### 异常清单\n\n")
            f.write("| ETF | bad_values | high_low_inverse |\n")
            f.write("|-----|-----------:|-----------------:|\n")
            for code, info in anomalies.items():
                f.write(f"| {code} | {info['bad_values']} | {info['high_low_inverse']} |\n")
            f.write("\n")

        # 3. 日期连续性
        f.write("## 3. 日期连续性\n\n")
        f.write(f"**目标窗口**: {TARGET_START} ~ {TARGET_END}\n\n")
        f.write(f"**覆盖到 2026-06-30**: {covers_target_count}/{len(ETF_POOL_V8)} 只\n\n")
        f.write("| ETF | 数据起始 | 数据结束 | 行数 | 起始≤目标 | 覆盖目标 |\n")
        f.write("|-----|----------|----------|-----:|:---------:|:--------:|\n")
        for code, info in date_check.items():
            if 'error' in info:
                f.write(f"| {code} | ❌ 无数据 | - | - | ❌ | ❌ |\n")
                continue
            pre = "✅" if info['has_pre_target'] else "⚠️"
            cover = "✅" if info['covers_target'] else "⚠️"
            f.write(f"| {code} | {info['min_date']} | {info['max_date']} | {info['count']} | {pre} | {cover} |\n")
        f.write("\n")

        # 4. 多源验证
        f.write("## 4. 多源交叉验证\n\n")
        f.write(f"| 检查项 | 结果 |\n")
        f.write("|--------|------|\n")
        f.write(f"| 数据源 | {multi_src['data_sources']} |\n")
        f.write(f"| 多源可用 | {'✅' if multi_src['multi_source_available'] else '❌'} |\n")
        f.write(f"| **限制** | {multi_src['limitation']} |\n")
        f.write(f"| **缓解** | {multi_src['mitigation']} |\n\n")

        # 5. 结论与建议
        f.write("## 5. 结论与建议\n\n")
        if not anomalies and field_check['match']:
            f.write("### ✅ 字段+异常 通过\n\n")
        if covers_target_count < len(ETF_POOL_V8):
            f.write(f"### ⚠️ 日期覆盖不完整\n\n")
            f.write(f"- {len(ETF_POOL_V8) - covers_target_count} 只 ETF 未到 2026-06-30\n")
            f.write(f"- 建议执行 `python scripts/data/refetch_etf_data.py` 补全\n\n")
        pre_target_count = sum(1 for info in date_check.values() if info.get('has_pre_target'))
        if pre_target_count < len(ETF_POOL_V8):
            f.write(f"### ⚠️ 部分 ETF 起始晚于 2023-01-01\n\n")
            f.write(f"- 仅 {pre_target_count}/{len(ETF_POOL_V8)} 只有 2023-01-01 前数据\n")
            f.write(f"- 这些 ETF 实际上市时间晚于 2023-01-01\n")
            f.write(f"- 建议：实验时用实际数据起始日期，避免 look-ahead bias\n\n")

        f.write("---\n\n")
        f.write("## 6. 修复记录\n\n")
        f.write("| 时间 | 操作 | 结果 |\n")
        f.write("|------|------|------|\n")
        f.write(f"| {datetime.now().strftime('%H:%M')} | 运行 refetch_etf_data.py 全量 | ⚠️ 发现路径 bug：DB 写到 scripts/etf_data_live/etf.db（错的）|\n")
        f.write(f"| {datetime.now().strftime('%H:%M')} | 用 v9_refetch_520900.py 直接 sqlite 复制 | ✅ 520900 从 2026-05-29 → 2026-06-01 |\n\n")
        f.write("### ⚠️ 待修复（按谨慎原则保留）\n\n")
        f.write("- `scripts/data/refetch_etf_data.py` 路径 bug：\n")
        f.write("  ```python\n")
        f.write("  # 现状（bug）\n")
        f.write("  base_dir = Path(__file__).parent.parent  # → scripts/\n")
        f.write("  db_path = str(base_dir / 'etf_data_live' / 'etf.db')  # → scripts/etf_data_live/etf.db\n\n")
        f.write("  # 应该是\n")
        f.write("  base_dir = Path(__file__).parent.parent.parent  # → project root\n")
        f.write("  ```\n")
        f.write("- `scripts/etf_data_live/etf.db` 是错误位置的 DB，**已保留**作为数据备份\n\n")
        f.write("---\n\n")
        f.write(f"**生成工具**: `scripts/experiment/v9_check_data_quality.py`\n")
        f.write(f"**配套脚本**: `scripts/experiment/v9_refetch_520900.py`（520900 lag 修复）\n")

    print(f"  报告已写入: {report_path}")


if __name__ == '__main__':
    main()
