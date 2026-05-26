#!/usr/bin/env python3
"""
回归测试 - 确保每次优化后核心结果一致
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

# ==================== 数据验证 ====================

def validate_data():
    """数据质量验证"""
    print("="*60)
    print("数据质量验证")
    print("="*60)
    
    data_dir = Path('../etf_data_50')
    files = list(data_dir.glob('*.csv'))
    
    print(f"数据目录: {data_dir}")
    print(f"ETF数量: {len(files)}")
    
    issues = []
    warnings = []
    ok_count = 0
    
    for f in files:
        df = pd.read_csv(f)
        
        # 1. 必要字段
        required = ['date', 'close', 'volume', 'open', 'high', 'low']
        missing = [c for c in required if c not in df.columns]
        if missing:
            issues.append(f"{f.name}: 缺少字段 {missing}")
            continue
        
        # 2. 空值检查
        if df.isnull().sum().sum() > 0:
            issues.append(f"{f.name}: 存在空值")
            continue
        
        # 3. 价格有效性
        if (df['close'] <= 0).any():
            issues.append(f"{f.name}: 存在非正价格")
            continue
        
        # 4. 涨跌幅异常
        if len(df) > 10:
            ret = df['close'].pct_change().dropna()
            extreme = ret[ret.abs() > 0.5]
            if len(extreme) > 0:
                issues.append(f"{f.name}: 单日涨跌幅>50% ({len(extreme)}次)")
                continue
        
        # 5. 数据长度 (<500天是警告，自动过滤)
        if len(df) < 500:
            warnings.append(f"{f.name}: 数据不足500天 ({len(df)}天) - 将被自动过滤")
            continue
        
        ok_count += 1
    
    print(f"通过验证(>=500天): {ok_count}/{len(files)}")
    
    if warnings:
        print(f"\n⚠️ 数据不足500天 (将被自动过滤): {len(warnings)}个")
        for w in warnings[:5]:
            print(f"  - {w}")
    
    if issues:
        print("\n⚠️ 发现问题:")
        for i in issues[:10]:
            print(f"  - {i}")
        return False  # 致命问题才失败
    
    if warnings:
        print("\n✓ 数据质量验证通过 (有警告但自动过滤)")
    else:
        print("\n✓ 数据质量验证通过")
    
    return True


# ==================== 回归测试 ====================

def regression_test():
    """回归测试"""
    from src.utils.config import run_strategy
    
    print("\n" + "="*60)
    print("回归测试 - 核心参数验证")
    print("="*60)
    
    test_cases = [
        {
            'name': '基准 - 调仓5天',
            'params': {'rebalance_days': 5},
            'return_range': (45, 60),
            'drawdown_range': (-30, -15),
        },
        {
            'name': '调仓10天',
            'params': {'rebalance_days': 10},
            'return_range': (80, 100),
            'drawdown_range': (-60, -45),
        },
    ]
    
    all_passed = True
    
    for tc in test_cases:
        print(f"\n▸ {tc['name']}")
        
        result = run_strategy(
            test_start='2025-05-06',
            test_end='2026-05-22',
            data_dir='../etf_data_50',
            **tc['params']
        )
        
        ret = result['return']
        dd = result['drawdown']
        
        # 验证范围
        r_min, r_max = tc['return_range']
        d_min, d_max = tc['drawdown_range']
        
        ret_ok = r_min <= ret <= r_max
        dd_ok = d_min <= dd <= d_max
        
        status = "✓" if (ret_ok and dd_ok) else "✗"
        print(f"  {status} 收益: {ret:+.1f}% (期望 {r_min}~{r_max})")
        print(f"  {status} 回撤: {dd:.1f}% (期望 {d_min}~{d_max})")
        
        # 额外指标
        print(f"    夏普: {result['sharpe']:.2f}, 胜率: {result['winrate']:.1f}%")
        
        if not (ret_ok and dd_ok):
            all_passed = False
    
    # 灾难性检查
    print("\n▸ 灾难性亏损检查")
    result = run_strategy(
        test_start='2025-05-06',
        test_end='2026-05-22',
        data_dir='../etf_data_50',
        rebalance_days=5
    )
    
    if result['return'] > -90:
        print(f"  ✓ 无灾难性亏损: {result['return']:+.1f}%")
    else:
        print(f"  ✗ 灾难性亏损: {result['return']:+.1f}%")
        all_passed = False
    
    print("\n" + "="*60)
    print("✓ 回归测试通过" if all_passed else "✗ 回归测试失败")
    print("="*60)
    
    return all_passed


# ==================== 主入口 ====================

if __name__ == '__main__':
    # 1. 数据验证
    data_ok = validate_data()
    
    # 2. 回归测试
    reg_ok = regression_test() if data_ok else False
    
    sys.exit(0 if (data_ok and reg_ok) else 1)