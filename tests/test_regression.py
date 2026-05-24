#!/usr/bin/env python3
"""回归测试 - 确保每次修改后核心结果一致"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def regression_test():
    """回归测试"""
    from src.config import run_strategy
    
    print("="*60)
    print("回归测试 - 核心参数结果验证")
    print("="*60)
    
    # 基准参数配置
    test_cases = [
        {
            'name': '基准(调仓5天)',
            'rebalance_days': 5,
            'expected_return_range': (45, 60),       # 预期收益范围
            'expected_drawdown_range': (-30, -15),   # 预期回撤范围
        },
        {
            'name': '调仓10天',
            'rebalance_days': 10,
            'expected_return_range': (80, 100),
            'expected_drawdown_range': (-60, -45),
        },
    ]
    
    all_passed = True
    
    for tc in test_cases:
        print(f"\n测试: {tc['name']}")
        
        try:
            result = run_strategy(
                test_start='2025-05-06',
                test_end='2026-05-22',
                rebalance_days=tc['rebalance_days'],
                data_dir='../etf_data_50'
            )
            
            ret = result['return']
            dd = result['drawdown']
            
            # 检查收益范围
            ret_min, ret_max = tc['expected_return_range']
            ret_ok = ret_min <= ret <= ret_max
            
            # 检查回撤范围
            dd_min, dd_max = tc['expected_drawdown_range']
            dd_ok = dd_min <= dd <= dd_max
            
            if ret_ok and dd_ok:
                print(f"  ✓ 收益: {ret:+.1f}% (期望 {ret_min}~{ret_max})")
                print(f"  ✓ 回撤: {dd:.1f}% (期望 {dd_min}~{dd_max})")
            else:
                print(f"  ✗ 收益: {ret:+.1f}% (期望 {ret_min}~{ret_max}) - {'OK' if ret_ok else 'FAIL'}")
                print(f"  ✗ 回撤: {dd:.1f}% (期望 {dd_min}~{dd_max}) - {'OK' if dd_ok else 'FAIL'}")
                all_passed = False
                
        except Exception as e:
            print(f"  ✗ 测试出错: {e}")
            all_passed = False
    
    # 额外检查: 确保没有灾难性亏损
    print("\n灾难性亏损检查:")
    try:
        result = run_strategy(
            test_start='2025-05-06',
            test_end='2026-05-22',
            rebalance_days=5,
            data_dir='../etf_data_50'
        )
        
        # 只要不亏超过90%就算通过（正常回测不会这样）
        if result['return'] > -90:
            print(f"  ✓ 无灾难性亏损: {result['return']:+.1f}%")
        else:
            print(f"  ✗ 灾难性亏损: {result['return']:+.1f}%")
            all_passed = False
            
    except Exception as e:
        print(f"  ✗ 检查出错: {e}")
        all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("✓ 回归测试通过!")
    else:
        print("✗ 回归测试失败 - 请检查修改")
    print("="*60)
    
    return all_passed


if __name__ == '__main__':
    success = regression_test()
    sys.exit(0 if success else 1)