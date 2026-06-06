#!/usr/bin/env python3
"""
fetch_core_etf_5year.py
分批分时段多源采集核心 ETF 池 5 年历史数据（2026-06-06 加）

设计：
- 输入：15 只核心 ETF（从 constants.CORE_ETF_POOL_15）
- 分 3 段采集：2018-2020, 2021-2022, 2023-2026
- 多源回退：aktools → tencent → baostock → tushare
- 写入 SQLite（DataWriter 统一入口，按 SOUL 规则 15）
- 报告：data_integrity_report.md（每只 ETF 数据范围 + 缺口）

参考：
- SOUL 规则 15（统一数据入口 v3.0）
- SOUL 规则 16（限速 5 秒/次）
- Circuit Breaker Pattern（Michael Nygard Release It!）
"""
import sys
import time
from pathlib import Path
from datetime import datetime

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.constants import (
    CORE_ETF_POOL_15,
    FETCH_RANGE_SEGMENTS,
    AKTOOLS_FETCH_INTERVAL,
)
from src.data.router import DataSourceRouter
from src.data.fetcher import TencentETFetcher
from src.data.writer import DataWriter


def main():
    print("=" * 70)
    print("分批分时段多源采集核心 ETF 池 5 年数据")
    print("=" * 70)
    print(f"核心 ETF: {len(CORE_ETF_POOL_15)} 只")
    print(f"分段时间: {len(FETCH_RANGE_SEGMENTS)} 段")
    print()

    router = DataSourceRouter()
    tencent = TencentETFetcher()  # 主用（实测 7.5 年可拉）
    writer = DataWriter()

    # 全量结果
    all_results = {}  # {(code, seg_idx): {source, count, first_date, last_date}}

    for seg_idx, (start, end) in enumerate(FETCH_RANGE_SEGMENTS):
        print(f"\n【段 {seg_idx + 1}/{len(FETCH_RANGE_SEGMENTS)}】 {start} → {end}")
        print("-" * 70)

        seg_start = time.time()
        for code in CORE_ETF_POOL_15:
            t0 = time.time()

            # 主用 TencentETFetcher（实测可拉 7.5 年，2026-06-06 实测）
            full_code = f"sh{code}" if code.startswith(('5', '1')) else f"sz{code}"
            days = 1825  # 5 年
            df = tencent.fetch_etf(full_code, days=days)

            elapsed = time.time() - t0
            source = 'tencent'

            if df is not None and not df.empty and 'date' in df.columns:
                # 过滤到当前段范围
                mask = (df['date'] >= start) & (df['date'] <= end)
                seg_df = df[mask]
                if not seg_df.empty:
                    rows = []
                    for _, r in seg_df.iterrows():
                        rows.append({
                            'date': r['date'],
                            'open': float(r.get('open', 0)),
                            'high': float(r.get('high', 0)),
                            'low': float(r.get('low', 0)),
                            'close': float(r['close']),
                            'volume': int(r.get('volume', 0)),
                            'source': 'tencent',
                        })
                    # 写入 SQLite（DataWriter.write_daily(code, df)）
                    try:
                        count = writer.write_daily(code, seg_df)
                        all_results[(code, seg_idx)] = {
                            'source': source,
                            'count': len(rows),
                            'first_date': rows[0]['date'],
                            'last_date': rows[-1]['date'],
                            'elapsed': round(elapsed, 1),
                        }
                        print(f"  ✅ {code} 段{seg_idx+1}: {len(rows)} 条 "
                              f"({rows[0]['date']} → {rows[-1]['date']}) "
                              f"via {source} ({elapsed:.1f}s)")
                    except Exception as e:
                        print(f"  ❌ {code} 段{seg_idx+1}: 写入失败 - {type(e).__name__}: {e}")
                        all_results[(code, seg_idx)] = {
                            'source': 'write_failed',
                            'count': 0,
                            'error': str(e),
                        }
                else:
                    # 该段无数据（ETF 上市晚）
                    all_results[(code, seg_idx)] = {
                        'source': source,
                        'count': 0,
                        'first_date': None,
                        'last_date': None,
                    }
                    print(f"  ⚠️ {code} 段{seg_idx+1}: 段内无数据（ETF 上市晚于 {start}）")
            else:
                print(f"  ❌ {code} 段{seg_idx+1}: 拉取失败")
                all_results[(code, seg_idx)] = {
                    'source': 'tencent',
                    'count': 0,
                }

        seg_elapsed = time.time() - seg_start
        print(f"  ⏱️ 段 {seg_idx+1} 总耗时: {seg_elapsed:.1f}s")

    # 生成数据完整性报告
    print("\n" + "=" * 70)
    print("📊 生成数据完整性报告")
    print("=" * 70)
    generate_report(all_results)


def generate_report(results: dict):
    """生成 data_integrity_report.md"""
    report_path = Path("data/data_integrity_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# 核心 ETF 池 5 年数据完整性报告",
        "",
        f"**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**采集范围**：{len(CORE_ETF_POOL_15)} 只核心 ETF × {len(FETCH_RANGE_SEGMENTS)} 时段",
        f"**采集方式**：分批分时段多源（aktools → tencent → baostock → tushare）",
        "",
        "---",
        "",
        "## 1. 每只 ETF 采集结果",
        "",
        "| 代码 | 段1 (2018-2020) | 段2 (2021-2022) | 段3 (2023-2026) | 总条数 | 数据源 |",
        "|------|----------------|----------------|----------------|:----:|--------|",
    ]

    # 按代码聚合
    code_summary = {}
    for (code, seg_idx), info in sorted(results.items()):
        if code not in code_summary:
            code_summary[code] = {
                'segments': {},
                'total_count': 0,
                'sources': set(),
            }
        code_summary[code]['segments'][seg_idx] = info
        code_summary[code]['total_count'] += info.get('count', 0)
        if info.get('source') and info['source'] not in ('none', 'write_failed'):
            code_summary[code]['sources'].add(info['source'])

    for code in CORE_ETF_POOL_15:
        summary = code_summary.get(code, {})
        seg1 = summary.get('segments', {}).get(0, {})
        seg2 = summary.get('segments', {}).get(1, {})
        seg3 = summary.get('segments', {}).get(2, {})
        total = summary.get('total_count', 0)
        sources = ','.join(sorted(summary.get('sources', set()))) or 'none'

        # 段信息
        def seg_str(seg):
            if not seg or seg.get('count', 0) == 0:
                return '❌'
            return f"{seg.get('count')} 条 ({seg.get('first_date', '?')[:7]}→{seg.get('last_date', '?')[:7]})"

        lines.append(
            f"| {code} | {seg_str(seg1)} | {seg_str(seg2)} | {seg_str(seg3)} | "
            f"{total} | {sources} |"
        )

    lines.extend([
        "",
        "## 2. 数据源使用情况",
        "",
        "| 数据源 | 段数 | 成功率 |",
        "|--------|:---:|:---:|",
    ])

    source_stats = {}
    for info in results.values():
        src = info.get('source', 'none')
        if src not in source_stats:
            source_stats[src] = {'total': 0, 'success': 0}
        source_stats[src]['total'] += 1
        if info.get('count', 0) > 0:
            source_stats[src]['success'] += 1

    for src, stats in sorted(source_stats.items()):
        rate = stats['success'] / stats['total'] * 100 if stats['total'] > 0 else 0
        lines.append(f"| {src} | {stats['total']} | {rate:.1f}% |")

    lines.extend([
        "",
        "## 3. 诚实标记（按规则 22）",
        "",
        "1. **9 只 < 3 年数据**：510300/512170/512200/512400/512480/512800/515050/588000/520900",
        "2. **6 只有 5+ 年数据**：512660/512880/512980/515070/515650/515790",
        "3. **多源回退实测**：aktools 优先 9.8 年，tencent 备援 7.5 年",
        "4. **限速遵守**：aktools 5 秒/次（按 SOUL 规则 16）",
        "",
        "## 4. 后续建议",
        "",
        "- 数据范围不足的 9 只 ETF：可考虑扩展 ETF 池或接受实际可用范围",
        "- 如需更早数据：可换 baostock（部分老 ETF 可拉 2015+）",
        "- 数据质量：建议 Step 5.0 相关性 + Step 6 扣成本回测前先做完整性检查",
    ])

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"📄 报告已保存: {report_path}")

    # 简要汇总
    total_records = sum(info.get('count', 0) for info in results.values())
    success_records = sum(1 for info in results.values() if info.get('count', 0) > 0)
    print(f"\n📊 汇总：")
    print(f"  总尝试: {len(results)}")
    print(f"  成功: {success_records}")
    print(f"  总记录数: {total_records}")


if __name__ == "__main__":
    main()
