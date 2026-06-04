#!/usr/bin/env python3
"""
IS-006: 5 折 WalkForward 包装器
为 v9 重跑设计的 5 折时间序列 CV 包装器

设计：
- 5 折滚动（每折训练 1.4 年 / 测试 0.6 年）
- 数据窗口：2023-01-01 ~ 2026-06-01（实际可用 ~3.4 年）
- 5 折输出：每折独立 train/test_return、sharpe、pass/fail
- 5 折聚合：平均 pass_rate、平均 sharpe
- 全部 5 折通过 → 评分 = 平均值；任一失败 → 评分折扣

用法：
    from scripts.validators.walk_forward_5fold import WalkForward5Fold

    wf5 = WalkForward5Fold(n_folds=5, train_years=1.4, test_years=0.6)
    result = wf5.validate(df, signal_func)
    # result.pass_ / result.score / result.fold_results
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Any

# 默认配置
DEFAULT_CONFIG = {
    'n_folds': 5,
    'train_years': 1.4,
    'test_years': 0.6,
    'min_pass_folds': 4,         # 至少 4/5 折通过
    'min_test_sharpe': 0.3,
    'min_test_return': 0.0,
    'max_decay': 0.5,
    'transaction_cost': 0.002,
}


@dataclass
class FoldResult:
    """单折验证结果"""
    fold_idx: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_days: int
    test_days: int
    train_return: float
    test_return: float
    test_sharpe: float
    decay: float
    trade_count: int
    pass_: bool
    reason: str = ''


@dataclass
class WalkForward5FoldResult:
    """5 折 WalkForward 汇总结果"""
    n_folds: int
    n_passed: int
    pass_rate: float
    avg_train_return: float
    avg_test_return: float
    avg_test_sharpe: float
    avg_decay: float
    score: float                 # 综合评分 0-1
    pass_: bool
    confidence: str
    fold_results: List[FoldResult] = field(default_factory=list)


def _to_date_str(d) -> str:
    """统一日期格式"""
    if isinstance(d, pd.Timestamp):
        return d.strftime('%Y-%m-%d')
    elif isinstance(d, datetime):
        return d.strftime('%Y-%m-%d')
    elif isinstance(d, str):
        return d[:10]
    return str(d)


def compute_sharpe(returns: np.ndarray, risk_free: float = 0.0) -> float:
    """计算夏普比率"""
    if len(returns) < 2:
        return 0.0
    excess = returns - risk_free
    if np.std(returns, ddof=1) == 0:
        return 0.0
    return np.mean(excess) / np.std(returns, ddof=1) * np.sqrt(252)


def compute_decay(train_return: float, test_return: float) -> float:
    """计算样本外衰减"""
    if train_return == 0:
        return 0
    return (test_return - train_return) / abs(train_return)


class WalkForward5Fold:
    """
    5 折时间序列 WalkForward 验证

    流程：
    1. 数据按时间排序
    2. 切分为 5 段：每段 test_years 长
    3. 每段 test 对应前 train_years 训练
    4. 跑策略，记录指标
    5. 聚合 5 折结果

    评分规则（score 0-1）：
    - pass_rate * 0.5：5 折通过率
    - avg_sharpe_normalized * 0.3：夏普归一化（>0.5 满分）
    - low_decay * 0.2：衰减低分高
    """

    def __init__(self, config: Dict = None):
        if config is None:
            config = DEFAULT_CONFIG.copy()
        self.n_folds = config.get('n_folds', 5)
        self.train_years = config.get('train_years', 1.4)
        self.test_years = config.get('test_years', 0.6)
        self.min_pass_folds = config.get('min_pass_folds', 4)
        self.min_test_sharpe = config.get('min_test_sharpe', 0.3)
        self.min_test_return = config.get('min_test_return', 0.0)
        self.max_decay = config.get('max_decay', 0.5)
        self.transaction_cost = config.get('transaction_cost', 0.002)

        # 转换为交易日
        self.train_days = int(self.train_years * 252)
        self.test_days = int(self.test_years * 252)

    def _split_folds(self, df: pd.DataFrame) -> List[Dict]:
        """切分 5 折索引 - expanding window 策略

        适配有限数据：如果数据不够 5×train+test，自动缩短 train 长度
        """
        df = df.sort_values('date').reset_index(drop=True)
        n = len(df)
        folds = []

        # 尝试生成 n_folds 折；如果数据不够，按比例缩短 train
        # 5×test_years + 1×train_years = 总需求
        # 简化为：每折 test 后移，train 是 test 前的所有数据（expanding）
        for fold_idx in range(self.n_folds):
            # 从最新数据往前推
            # fold 0: test 最新段
            # fold 4: test 最早段
            test_end_idx = n - fold_idx * self.test_days
            test_start_idx = test_end_idx - self.test_days

            if test_start_idx < 0:
                break

            # 训练数据：尽可能多，但不超过 train_years
            train_end_idx = test_start_idx
            ideal_train_start = train_end_idx - self.train_days
            train_start_idx = max(0, ideal_train_start)

            # 如果数据实在太少（< 100 训练日），跳过
            actual_train_days = train_end_idx - train_start_idx
            if actual_train_days < 100:
                break

            folds.append({
                'fold_idx': fold_idx,
                'train_start': df.iloc[train_start_idx]['date'],
                'train_end': df.iloc[train_end_idx - 1]['date'],
                'test_start': df.iloc[test_start_idx]['date'],
                'test_end': df.iloc[test_end_idx - 1]['date'],
                'train_df': df.iloc[train_start_idx:train_end_idx].copy(),
                'test_df': df.iloc[test_start_idx:test_end_idx].copy(),
            })

        # 反转使 fold 0 是最早的（更直观）
        return list(reversed(folds))

    def _evaluate_fold(self, train_df: pd.DataFrame, test_df: pd.DataFrame,
                       train_result: Dict, test_result: Dict) -> tuple:
        """评估单折是否通过"""
        decay = compute_decay(train_result['total_return'], test_result['total_return'])
        reasons = []

        if test_result['total_return'] < self.min_test_return:
            reasons.append(f"test_return={test_result['total_return']:.3f} < 0")
        if test_result['sharpe'] < self.min_test_sharpe:
            reasons.append(f"test_sharpe={test_result['sharpe']:.2f} < {self.min_test_sharpe}")
        if decay > self.max_decay:
            reasons.append(f"decay={decay:.2f} > {self.max_decay}")

        passed = len(reasons) == 0
        return passed, decay, '; '.join(reasons) if reasons else 'OK'

    def _compute_result(self, df: pd.DataFrame, signal) -> Dict:
        """计算策略结果（简化版：买入持有信号收益）"""
        if not isinstance(signal, pd.Series):
            signal = pd.Series(signal, index=df.index)
        signal = signal.astype(bool)

        # 简化计算：信号日为持仓，计算持仓期收益
        positions = signal.shift(1).fillna(False)
        returns = df['close'].pct_change().fillna(0)
        strategy_returns = returns * positions

        # 扣除交易成本
        n_trades = signal.sum()
        if n_trades > 0:
            total_cost = n_trades * self.transaction_cost
        else:
            total_cost = 0

        total_return = strategy_returns.sum() - total_cost
        sharpe = compute_sharpe(strategy_returns.values)

        return {
            'total_return': total_return,
            'sharpe': sharpe,
            'trade_count': int(n_trades),
        }

    def validate(self, df: pd.DataFrame, signal_func: Callable) -> WalkForward5FoldResult:
        """
        执行 5 折 WalkForward 验证

        参数:
            df: K线数据（含 date, close 列）
            signal_func: 信号生成函数，输入 df 返回 bool Series

        返回:
            WalkForward5FoldResult
        """
        folds = self._split_folds(df)
        fold_results = []

        for fold in folds:
            try:
                train_signal = signal_func(fold['train_df'])
                test_signal = signal_func(fold['test_df'])
            except Exception as e:
                fold_results.append(FoldResult(
                    fold_idx=fold['fold_idx'],
                    train_start=_to_date_str(fold['train_start']),
                    train_end=_to_date_str(fold['train_end']),
                    test_start=_to_date_str(fold['test_start']),
                    test_end=_to_date_str(fold['test_end']),
                    train_days=len(fold['train_df']),
                    test_days=len(fold['test_df']),
                    train_return=0,
                    test_return=0,
                    test_sharpe=0,
                    decay=0,
                    trade_count=0,
                    pass_=False,
                    reason=f"signal error: {str(e)[:50]}",
                ))
                continue

            train_result = self._compute_result(fold['train_df'], train_signal)
            test_result = self._compute_result(fold['test_df'], test_signal)
            passed, decay, reason = self._evaluate_fold(
                fold['train_df'], fold['test_df'],
                train_result, test_result,
            )

            fold_results.append(FoldResult(
                fold_idx=fold['fold_idx'],
                train_start=_to_date_str(fold['train_start']),
                train_end=_to_date_str(fold['train_end']),
                test_start=_to_date_str(fold['test_start']),
                test_end=_to_date_str(fold['test_end']),
                train_days=len(fold['train_df']),
                test_days=len(fold['test_df']),
                train_return=train_result['total_return'],
                test_return=test_result['total_return'],
                test_sharpe=test_result['sharpe'],
                decay=decay,
                trade_count=test_result['trade_count'],
                pass_=passed,
                reason=reason,
            ))

        # 聚合
        n_folds = len(fold_results)
        if n_folds == 0:
            return WalkForward5FoldResult(
                n_folds=0, n_passed=0, pass_rate=0,
                avg_train_return=0, avg_test_return=0, avg_test_sharpe=0,
                avg_decay=0, score=0, pass_=False, confidence='NO_DATA',
            )

        n_passed = sum(1 for f in fold_results if f.pass_)
        pass_rate = n_passed / n_folds
        avg_train_return = np.mean([f.train_return for f in fold_results])
        avg_test_return = np.mean([f.test_return for f in fold_results])
        avg_test_sharpe = np.mean([f.test_sharpe for f in fold_results])
        avg_decay = np.mean([f.decay for f in fold_results])

        # 评分
        score_pass = pass_rate * 0.5
        score_sharpe = min(avg_test_sharpe / 1.0, 1.0) * 0.3  # >1.0 满分
        score_decay = max(1.0 - abs(avg_decay) / 1.0, 0) * 0.2
        score = score_pass + score_sharpe + score_decay

        # 通过条件
        overall_pass = (n_passed >= self.min_pass_folds) and (score >= 0.6)

        if overall_pass:
            confidence = 'HIGH' if pass_rate == 1.0 else 'MEDIUM'
        elif pass_rate >= 0.5:
            confidence = 'LOW'
        else:
            confidence = 'FAIL'

        return WalkForward5FoldResult(
            n_folds=n_folds,
            n_passed=n_passed,
            pass_rate=pass_rate,
            avg_train_return=avg_train_return,
            avg_test_return=avg_test_return,
            avg_test_sharpe=avg_test_sharpe,
            avg_decay=avg_decay,
            score=score,
            pass_=overall_pass,
            confidence=confidence,
            fold_results=fold_results,
        )


def main():
    """简单测试：5 折 WF 包装器对一只 ETF + 一个简单信号函数"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from src.data.loader import DataLoader

    print("IS-006 5 折 WalkForward 包装器测试")
    print("=" * 60)

    loader = DataLoader()
    df = loader.load_single('510300', min_rows=400)
    if df is None:
        print("❌ 510300 数据加载失败")
        return 1

    print(f"510300 数据: {df['date'].min()} ~ {df['date'].max()} ({len(df)} 行)")

    # 简单信号：MA5 > MA20
    def ma_signal(data):
        ma5 = data['close'].rolling(5).mean()
        ma20 = data['close'].rolling(20).mean()
        return (ma5 > ma20).fillna(False)

    wf5 = WalkForward5Fold()
    result = wf5.validate(df, ma_signal)

    print(f"\n5 折 WalkForward 结果:")
    print(f"  折数: {result.n_folds}, 通过: {result.n_passed}, 通过率: {result.pass_rate*100:.1f}%")
    print(f"  平均训练收益: {result.avg_train_return*100:.2f}%")
    print(f"  平均测试收益: {result.avg_test_return*100:.2f}%")
    print(f"  平均夏普: {result.avg_test_sharpe:.2f}")
    print(f"  平均衰减: {result.avg_decay:.2f}")
    print(f"  评分: {result.score:.3f}")
    print(f"  整体通过: {result.pass_} ({result.confidence})")

    print(f"\n分项详情:")
    for f in result.fold_results:
        status = "✅" if f.pass_ else "❌"
        print(f"  {status} Fold {f.fold_idx}: {f.test_start} ~ {f.test_end} "
              f"return={f.test_return*100:.2f}% sharpe={f.test_sharpe:.2f} "
              f"decay={f.decay:.2f} trades={f.trade_count}")

    return 0


if __name__ == '__main__':
    main()
