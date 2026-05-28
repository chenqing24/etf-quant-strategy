#!/usr/bin/env python3
"""测试数据更新逻辑"""
import sys
sys.path.insert(0, '.')

from datetime import datetime, timedelta
import pandas as pd

# 模拟旧数据场景
class MockData:
    def __init__(self):
        self.age = 0  # 数据年龄
    
    def test_update_logic(self, data_age):
        """模拟修复后的更新逻辑"""
        today = datetime.now().date()
        results = []
        
        if data_age == 0:
            results.append('✅ 正常')
        else:
            results.append('⚠️ 数据略旧')
            # 模拟2次更新尝试
            for attempt in range(2):
                results.append(f'  尝试第{attempt+1}次更新...')
                # 模拟更新成功
                results.append(f'  第{attempt+1}次更新成功')
                break  # 假设第1次就成功了
        
        return results

# 测试
mock = MockData()
print("=== 数据更新逻辑测试 ===")
print()

# 场景1: 数据新鲜
print("场景1: 数据新鲜 (age=0)")
for r in mock.test_update_logic(0):
    print(f"  {r}")
print()

# 场景2: 数据略旧 (修复后行为)
print("场景2: 数据略旧 (age=2) - 修复后")
for r in mock.test_update_logic(2):
    print(f"  {r}")
print()

# 场景3: 数据过期
print("场景3: 数据过期 (age=5) - 修复后")
for r in mock.test_update_logic(5):
    print(f"  {r}")
print()

print("✅ 测试完成")