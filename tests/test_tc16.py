#!/usr/bin/env python3
"""TC-16: 钉钉简版报告数据过期警告测试"""
import sys
sys.path.insert(0, '.')
from src.analysis.report_builder import ReportBuilder

print('=== TC-16: 钉钉简版报告数据过期警告测试 ===')

builder = ReportBuilder()

# TC-16.1: 数据过期
results = {
    'action': '买入',
    'code': '515050',
    'price': 1.101,
    'data_freshness': '❌ 数据过期',
    'data_freshness_warning': '数据超过4天未更新，偏差计算可能失真！'
}
report = builder.build_simple(results)
assert '⚠️ ❌ 数据过期' in report, '❌ 缺少数据过期标识'
assert '数据超过4天未更新' in report, '❌ 缺少警告消息'
print('✅ TC-16.1: 数据过期场景 - 通过')

# TC-16.2: 数据正常
results = {
    'action': '买入',
    'code': '515050',
    'price': 1.101,
    'data_freshness': '✅ 正常',
    'data_freshness_warning': ''
}
report = builder.build_simple(results)
assert '⚠️' not in report, '❌ 数据正常时不应显示警告'
print('✅ TC-16.2: 数据正常场景 - 通过')

print()
print('✅ TC-16 全部通过')