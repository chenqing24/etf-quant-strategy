"""B 调研：3 个 bug 根因深入"""
import sys
sys.path.insert(0, '.')
import time
import numpy as np
import pandas as pd
from src.constants import CORE_ETF_POOL_15
from src.data.loader import DataLoader
from scripts.validators.walk_forward import WalkForwardEngine
import importlib.util
spec = importlib.util.spec_from_file_location("u027", "scripts/experiment/US-027_27_factor_full.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


# 调研 1: WalkForward 实际跑几个窗口？
print('=' * 70)
print('调研 1: T9_dmi WalkForward 实际跑几个窗口？')
print('=' * 70)
loader = DataLoader()
df = loader.load(codes=['512660'])['512660']
df = df[(df['date'] >= '2021-06-06') & (df['date'] <= '2026-06-05')].copy()
print(f'数据范围: {df["date"].iloc[0]} ~ {df["date"].iloc[-1]}, 总 {len(df)} 行')

engine = WalkForwardEngine()  # 默认 config
print(f'WalkForward 配置: train_days={engine.train_days}, test_days={engine.test_days}, step={engine.step}')

expected_windows = (len(df) - engine.train_days - engine.test_days) // engine.step
print(f'预期窗口数: {expected_windows}')

t0 = time.time()
result = engine.validate(df, m.FACTOR_SIGNALS['T9_dmi'])
print(f'实际 n_windows: {result.n_windows}')
print(f'n_passed: {result.n_passed}')
print(f'avg_train_return: {result.avg_train_return:.6f}')
print(f'avg_test_return: {result.avg_test_return:.6f}')
oos_is = result.avg_test_return / max(abs(result.avg_train_return), 1e-9)
print(f'→ OOS/IS = {oos_is:.2f}')
print(f'耗时: {time.time()-t0:.2f}s')
print()

# 调研 2: C1 NaN 根因 - _vote 函数
print('=' * 70)
print('调研 2: C1 NaN 根因 - _vote 函数')
print('=' * 70)
print('C1 引用: V4, T9, M5, B4')
print('FACTOR_SIGNALS 实际有:', list(m.FACTOR_SIGNALS.keys())[:10])
print()
vote = m._vote(df, ['V4', 'T9', 'M5', 'B4'])
print(f'_vote 返回类型: {type(vote)}')
print(f'_vote 前 5 个值: {vote.head(5).tolist()}')
print(f'_vote NaN 数: {vote.isna().sum()}')
print(f'_vote 唯一值: {vote.unique()[:5]}')

# 检查每个分量
for k in ['V4', 'T9', 'M5', 'B4']:
    if k in m.FACTOR_SIGNALS:
        try:
            v = m.FACTOR_SIGNALS[k](df)
            print(f'  {k}: 类型={type(v).__name__}, NaN={v.isna().sum() if hasattr(v, "isna") else "N/A"}, 唯一值={v.unique()[:3] if hasattr(v, "unique") else "N/A"}')
        except Exception as e:
            print(f'  {k}: ❌ 错误: {e}')
    else:
        print(f'  {k}: ❌ 不在 FACTOR_SIGNALS 字典')
print()

# 调研 3: 5 秒过快
print('=' * 70)
print('调研 3: 5 秒跑完 27 因子 根因')
print('=' * 70)
print('27 因子 × 15 ETF = 405 次 WalkForward')
print('每次 13 窗口 × 5 年数据 = ~13 × 1211 = 15,743 收益计算')
print('预期总时间: 405 × 0.1s = 40s（保守估计）')
print('实际 5s = 每次 0.012s = 极快 → 可能只跑 1 个窗口 或 用 cached 结果')
print()

# 验证：单次 WalkForward 实际耗时
t0 = time.time()
result = engine.validate(df, m.FACTOR_SIGNALS['T9_dmi'])
t1 = time.time() - t0
print(f'单 ETF 单因子耗时: {t1:.3f}s')
print(f'405 次预期总耗时: {405 * t1:.1f}s = {405 * t1 / 60:.1f} min')
print(f'实际 5s = 严重异常：可能 WalkForwardEngine 用 cached 或只跑 1 窗口')
