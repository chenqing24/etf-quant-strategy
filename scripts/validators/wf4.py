#!/usr/bin/env python3
"""
SOP-03 Phase 1: 4折Walk-Forward验证脚本

功能：
- 对TOP ETF跑4折WF验证
- 计算Sharpe/胜率/盈亏比
- 输出JSON结果到 data/wf4_results.json

数据范围: 2023-09-26 ~ 2026-06-01（644天）
4折切分：
  Fold 1: IS[~2024-12] → OOS[2025-01 ~ 2025-06]
  Fold 2: IS[~2025-06] → OOS[2025-07 ~ 2025-12]
  Fold 3: IS[~2025-12] → OOS[2026-01 ~ 2026-03]
  Fold 4: IS[~2026-03] → OOS[2026-04 ~ 2026-06]

通过标准：
  - Sharpe ≥ 0.5
  - 胜率 ≥ 40%
  - 盈亏比 × 胜率 > 1
"""
import json
import sys
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Callable

import numpy as np
import pandas as pd

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.loader import DataLoader
from src.core.selector import Selector
from src.core.position import TradeExecutor
from src.utils.config import StrategyConfig
from src.analysis.metrics import calculate_metrics


@dataclass
class WF4Fold:
    """单折验证结果"""
    fold: int                      # 1-4
    is_range: str                 # "2023-09 ~ 2024-12"
    oos_range: str                # "2025-01 ~ 2025-06"
    sharpe: float                 # 夏普比率
    win_rate: float              # 胜率（0-1）
    profit_loss_ratio: float      # 盈亏比
    profit_x_win: float          # 核心指标 = 盈亏比 × 胜率
    pass_: bool                  # 是否通过
    reason: str                  # 通过/失败原因

    def to_dict(self) -> Dict:
        return {
            'fold': self.fold,
            'is_range': self.is_range,
            'oos_range': self.oos_range,
            'sharpe': round(self.sharpe, 3),
            'win_rate': round(self.win_rate * 100, 1),
            'profit_loss_ratio': round(self.profit_loss_ratio, 2),
            'profit_x_win': round(self.profit_x_win, 3),
            'pass': self.pass_,
            'reason': self.reason
        }


@dataclass
class WF4Result:
    """4折WF验证汇总结果"""
    etf_code: str
    data_range: str
    n_folds: int
    n_passed: int
    pass_rate: float
    avg_sharpe: float
    avg_win_rate: float
    avg_profit_loss_ratio: float
    avg_profit_x_win: float
    overall_pass: bool
    confidence: str              # HIGH/MEDIUM/LOW/FAIL
    folds: List[WF4Fold]

    def to_dict(self) -> Dict:
        return {
            'etf_code': self.etf_code,
            'data_range': self.data_range,
            'n_folds': self.n_folds,
            'n_passed': self.n_passed,
            'pass_rate': round(self.pass_rate * 100, 1),
            'avg_sharpe': round(self.avg_sharpe, 3),
            'avg_win_rate': round(self.avg_win_rate * 100, 1),
            'avg_profit_loss_ratio': round(self.avg_profit_loss_ratio, 2),
            'avg_profit_x_win': round(self.avg_profit_x_win, 3),
            'overall_pass': self.overall_pass,
            'confidence': self.confidence,
            'folds': [f.to_dict() for f in self.folds]
        }


class WalkForward4Fold:
    """4折Walk-Forward验证器"""

    # 通过标准
    MIN_SHARPE = 0.5
    MIN_WIN_RATE = 0.4
    MIN_PROFIT_X_WIN = 1.0

    def __init__(self):
        self.data_loader = DataLoader()
        self.selector = Selector()
        self.config = StrategyConfig()

    def _split_folds(self, df: pd.DataFrame) -> List[Dict]:
        """切分4折索引 - 按设计文档的日期分段

        按设计文档（V9_BACKLOG.md）：
        Fold 1: IS[2023-09-26 ~ 2024-12-31] → OOS[2025-01-01 ~ 2025-06-30]
        Fold 2: IS[2023-09-26 ~ 2025-06-30] → OOS[2025-07-01 ~ 2025-12-31]
        Fold 3: IS[2023-09-26 ~ 2025-12-31] → OOS[2026-01-01 ~ 2026-03-31]
        Fold 4: IS[2023-09-26 ~ 2026-03-31] → OOS[2026-04-01 ~ 2026-06-02]
        
        注意：执行阶段不能擅自改动此配置，必须严格对齐设计文档
        """
        df = df.sort_values('date').reset_index(drop=True)
        
        # 设计文档确认的4折配置
        fold_configs = [
            # (fold_idx, is_end, oos_start, oos_end)
            (1, '2024-12-31', '2025-01-01', '2025-06-30'),  # Fold 1
            (2, '2025-06-30', '2025-07-01', '2025-12-31'),  # Fold 2
            (3, '2025-12-31', '2026-01-01', '2026-03-31'),  # Fold 3
            (4, '2026-03-31', '2026-04-01', '2026-06-02'),  # Fold 4
        ]
        
        folds = []
        
        for fold_idx, is_end, oos_start, oos_end in fold_configs:
            # IS期数据
            train_df = df[(df['date'] >= '2023-09-26') & (df['date'] <= is_end)]
            # OOS期数据
            test_df = df[(df['date'] >= oos_start) & (df['date'] <= oos_end)]
            
            # 检查数据量
            if len(train_df) < 100 or len(test_df) < 10:
                continue

            folds.append({
                'fold_idx': fold_idx,
                'train_start': '2023-09-26',
                'train_end': is_end,
                'test_start': oos_start,
                'test_end': oos_end,
                'train_df': train_df,
                'test_df': test_df,
            })

        return folds

    def _compute_metrics(self, df: pd.DataFrame, config: StrategyConfig) -> Dict:
        """计算单次回测的完整指标

        使用简单的MA多头策略：
        - 买入信号：MA5 > MA20
        - 卖出信号：MA5 < MA20 或止损/止盈
        """
        if len(df) < 30:
            return {
                'sharpe': 0, 'win_rate': 0, 'profit_loss_ratio': 0,
                'profit_x_win': 0, 'trades': 0
            }

        df = df.copy()
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['signal'] = (df['ma5'] > df['ma20']).astype(int)

        # 计算每日收益
        df['ret'] = df['close'].pct_change().fillna(0)

        # 模拟交易
        position = 0
        trades = []
        entry_price = 0
        entry_date = None

        for i, row in df.iterrows():
            if pd.isna(row['signal']):
                continue

            # 买入
            if row['signal'] == 1 and position == 0:
                position = 1
                entry_price = row['close']
                entry_date = row['date']

            # 卖出
            elif row['signal'] == 0 and position == 1:
                pnl = (row['close'] - entry_price) / entry_price
                trades.append({'pnl': pnl, 'hold_days': 1})
                position = 0

        # 最终清仓
        if position == 1:
            last_close = df.iloc[-1]['close']
            pnl = (last_close - entry_price) / entry_price
            hold_days = (pd.to_datetime(df.iloc[-1]['date']) - pd.to_datetime(entry_date)).days
            trades.append({'pnl': pnl, 'hold_days': hold_days})

        if not trades:
            return {
                'sharpe': 0, 'win_rate': 0, 'profit_loss_ratio': 0,
                'profit_x_win': 0, 'trades': 0
            }

        # 计算指标
        sells = trades
        wins = [t['pnl'] for t in sells if t['pnl'] > 0]
        losses = [t['pnl'] for t in sells if t['pnl'] <= 0]

        win_rate = len(wins) / len(sells) if sells else 0
        avg_win = np.mean(wins) if wins else 0
        avg_loss = abs(np.mean(losses)) if losses else 0  # 取绝对值
        # 盈亏比：全胜时 avg_loss=0，需要特殊处理
        if avg_loss == 0:
            profit_loss_ratio = avg_win if avg_win > 0 else 0
        else:
            profit_loss_ratio = avg_win / avg_loss
        profit_x_win = profit_loss_ratio * win_rate

        # 计算Sharpe
        returns = [t['pnl'] for t in sells]
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(len(returns))
        else:
            sharpe = 0

        return {
            'sharpe': round(sharpe, 3),
            'win_rate': round(win_rate, 3),
            'profit_loss_ratio': round(profit_loss_ratio, 2),
            'profit_x_win': round(profit_x_win, 3),
            'trades': len(sells)
        }

    def _evaluate_fold(self, fold: Dict) -> WF4Fold:
        """评估单折是否通过"""
        test_df = fold['test_df']

        # 计算IS期和OOS期的指标
        is_metrics = self._compute_metrics(fold['train_df'], self.config)
        oos_metrics = self._compute_metrics(test_df, self.config)

        sharpe = oos_metrics['sharpe']
        win_rate = oos_metrics['win_rate']
        profit_loss_ratio = oos_metrics['profit_loss_ratio']
        profit_x_win = oos_metrics['profit_x_win']

        # 判断是否通过
        reasons = []
        pass_ = True

        if sharpe < self.MIN_SHARPE:
            reasons.append(f'sharpe={sharpe:.2f}<{self.MIN_SHARPE}')
            pass_ = False

        if win_rate < self.MIN_WIN_RATE:
            reasons.append(f'win_rate={win_rate:.1%}<{self.MIN_WIN_RATE:.0%}')
            pass_ = False

        if profit_x_win <= self.MIN_PROFIT_X_WIN:
            reasons.append(f'profit_x_win={profit_x_win:.2f}<={self.MIN_PROFIT_X_WIN}')
            pass_ = False

        return WF4Fold(
            fold=fold['fold_idx'],
            is_range=f"{fold['train_start'][:7]} ~ {fold['train_end'][:7]}",
            oos_range=f"{fold['test_start'][:7]} ~ {fold['test_end'][:7]}",
            sharpe=sharpe,
            win_rate=win_rate,
            profit_loss_ratio=profit_loss_ratio,
            profit_x_win=profit_x_win,
            pass_=pass_,
            reason=', '.join(reasons) if reasons else '通过'
        )

    def validate(self, code: str) -> WF4Result:
        """对单只ETF执行4折WF验证

        Args:
            code: ETF代码（如'515050'）

        Returns:
            WF4Result: 验证结果
        """
        # 加载数据
        df = self.data_loader.load_single(code, min_rows=400)
        if df is None:
            raise ValueError(f"无法加载ETF {code} 的数据")

        data_range = f"{df['date'].min()} ~ {df['date'].max()}"

        # 切分4折
        folds = self._split_folds(df)
        if len(folds) < 4:
            raise ValueError(f"ETF {code} 数据不足，无法进行4折WF验证（实际{len(folds)}折）")

        # 评估每折
        fold_results = [self._evaluate_fold(fold) for fold in folds]

        # 汇总
        n_passed = sum(1 for f in fold_results if f.pass_)
        pass_rate = n_passed / len(fold_results)
        avg_sharpe = np.mean([f.sharpe for f in fold_results])
        avg_win_rate = np.mean([f.win_rate for f in fold_results])
        avg_profit_loss_ratio = np.mean([f.profit_loss_ratio for f in fold_results])
        avg_profit_x_win = np.mean([f.profit_x_win for f in fold_results])

        overall_pass = n_passed == len(fold_results)

        if overall_pass:
            confidence = 'HIGH' if pass_rate == 1.0 else 'MEDIUM'
        elif pass_rate >= 0.5:
            confidence = 'LOW'
        else:
            confidence = 'FAIL'

        return WF4Result(
            etf_code=code,
            data_range=data_range,
            n_folds=len(fold_results),
            n_passed=n_passed,
            pass_rate=pass_rate,
            avg_sharpe=avg_sharpe,
            avg_win_rate=avg_win_rate,
            avg_profit_loss_ratio=avg_profit_loss_ratio,
            avg_profit_x_win=avg_profit_x_win,
            overall_pass=overall_pass,
            confidence=confidence,
            folds=fold_results
        )


def run_wf4(codes: List[str], output_path: str = None) -> Dict[str, WF4Result]:
    """对多只ETF执行4折WF验证

    Args:
        codes: ETF代码列表
        output_path: JSON输出路径（默认 data/wf4_results.json）

    Returns:
        Dict[str, WF4Result]: 各ETF的验证结果
    """
    if output_path is None:
        output_path = Path(__file__).parent.parent.parent / 'data' / 'wf4_results.json'

    results = {}
    wf4 = WalkForward4Fold()

    print(f"开始4折WF验证，共{len(codes)}只ETF")
    print("=" * 60)

    for i, code in enumerate(codes, 1):
        print(f"\n[{i}/{len(codes)}] 验证 {code}...", end=' ')
        try:
            result = wf4.validate(code)
            results[code] = result

            status = "✅" if result.overall_pass else "❌"
            print(f"{status} {result.n_passed}/{result.n_folds}折通过, "
                  f"Sharpe={result.avg_sharpe:.2f}, "
                  f"胜率={result.avg_win_rate:.1%}, "
                  f"盈亏比×胜率={result.avg_profit_x_win:.2f}")

        except Exception as e:
            print(f"❌ 失败: {e}")

    # 输出JSON
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'data_range': '2023-09-26 ~ 2026-06-01',
        'pass_criteria': {
            'sharpe': f'>={wf4.MIN_SHARPE}',
            'win_rate': f'>={wf4.MIN_WIN_RATE:.0%}',
            'profit_x_win': f'>{wf4.MIN_PROFIT_X_WIN}'
        },
        'results': {code: result.to_dict() for code, result in results.items()}
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存: {output_path}")

    return results


def main():
    """入口"""
    import argparse
    parser = argparse.ArgumentParser(description='4折Walk-Forward验证')
    parser.add_argument('--codes', nargs='+', default=None, help='ETF代码列表')
    parser.add_argument('--codes-file', default=None, help='从文件读取ETF代码')
    parser.add_argument('--output', default=None, help='JSON输出路径')
    parser.add_argument('--top', type=int, default=5, help='验证TOP N ETF（按评分）')
    args = parser.parse_args()

    # 确定要验证的ETF
    if args.codes:
        codes = args.codes
    elif args.codes_file:
        with open(args.codes_file) as f:
            codes = [line.strip() for line in f if line.strip()]
    else:
        # 默认：验证TOP信号ETF
        print("未指定ETF，默认验证TOP 5信号ETF...")
        from src.core.selector import Selector
        from src.data.loader import DataLoader

        loader = DataLoader()
        etf_data = loader.load(min_rows=400)
        selector = Selector()

        latest_date = max(d for df in etf_data.values() for d in df['date'])

        signals = []
        for code, df in etf_data.items():
            score, _ = selector.score_with_ic(df, latest_date)
            if score >= 6:
                signals.append((code, score))

        signals.sort(key=lambda x: -x[1])
        codes = [code for code, score in signals[:args.top]]

        print(f"TOP {args.top} 信号ETF: {codes}")

    if not codes:
        print("没有要验证的ETF")
        return 1

    results = run_wf4(codes, args.output)

    # 汇总统计
    n_passed_total = sum(1 for r in results.values() if r.overall_pass)
    print(f"\n汇总: {n_passed_total}/{len(results)}只ETF全部4折通过")

    return 0


if __name__ == '__main__':
    sys.exit(main())