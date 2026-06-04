#!/usr/bin/env python3
"""
SOP-03 Phase 2: 4折Walk-Forward验证脚本 v2.0

⚠️ 严格按设计文档的日期分段，禁止用索引均分替代

功能：
- 对14只交易ETF跑4折WF验证
- 使用主力维护的回测引擎 FactorBacktester（src/backtest/engine.py）
- 测试 hold_count = 1/2/3 分别验证
- 输出JSON结果到 data/wf4_results_v2.json

4折切分（按设计文档）：
  Fold 1: IS[2023-09-26 ~ 2024-12-31] → OOS[2025-01-01 ~ 2025-06-30]
  Fold 2: IS[2023-09-26 ~ 2025-06-30] → OOS[2025-07-01 ~ 2025-12-31]
  Fold 3: IS[2023-09-26 ~ 2025-12-31] → OOS[2026-01-01 ~ 2026-03-31]
  Fold 4: IS[2023-09-26 ~ 2026-03-31] → OOS[2026-04-01 ~ 2026-06-02]

通过标准：
  - Sharpe ≥ 0.5
  - 胜率 ≥ 40%
  - 盈亏比 × 胜率 > 1

参考来源：
  - src/backtest/engine.py（主力维护版本）
  - Backtrader/Zipline/FMZ 最佳实践
"""
import json
import sys
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict

import numpy as np
import pandas as pd

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data.loader import DataLoader
from src.indicators.wrapper import IndicatorCalculator
from src.backtest.engine import FactorBacktester, BacktestConfig


# ============================================================
# ETF 池配置
# ============================================================

# 交易 ETF（14只，不含510300大盘参考）
TRADE_ETFS = [
    '588000',  # 科创50
    '512480',  # 半导体
    '512880',  # 证券
    '512170',  # 医疗
    '520900',  # 畜牧
    '515790',  # 光伏
    '515050',  # 游戏
    '512400',  # 有色
    '512660',  # 军工
    '515070',  # AI
    '512800',  # 银行
    '512980',  # 传媒
    '512200',  # 房地产
    '515650',  # 消费
]

# 大盘参考 ETF（510300 沪深300，不参与交易）
MARKET_ETF = '510300'

# 所有 ETF（交易 + 大盘参考）
ALL_ETFS = [MARKET_ETF] + TRADE_ETFS


# ============================================================
# 折数配置
# ============================================================

FOLD_CONFIGS = [
    # fold, is_start, is_end, oos_start, oos_end
    (1, '2023-09-26', '2024-12-31', '2025-01-01', '2025-06-30'),
    (2, '2023-09-26', '2025-06-30', '2025-07-01', '2025-12-31'),
    (3, '2023-09-26', '2025-12-31', '2026-01-01', '2026-03-31'),
    (4, '2023-09-26', '2026-03-31', '2026-04-01', '2026-06-02'),
]


# ============================================================
# 数据处理
# ============================================================

def _add_ma_vol_rsi(df: pd.DataFrame) -> pd.DataFrame:
    """添加 Selector 需要的 ma/vol/rsi 列"""
    # 均线
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    df['ma120'] = df['close'].rolling(120).mean()
    
    # 放量比率
    df['vol_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
    
    # RSI(14)
    if 'rsi_14' not in df.columns:
        delta = df['close'].diff()
        gain = delta.copy()
        loss = delta.copy()
        gain[gain < 0] = 0
        loss[loss > 0] = 0
        loss = loss.abs()
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / avg_loss
        df['rsi_14'] = 100 - (100 / (1 + rs))
    
    df['rsi'] = df['RSI_5'] if 'RSI_5' in df.columns else df['rsi_14']
    
    return df


def load_etf_data(loader: DataLoader, calc: IndicatorCalculator) -> Dict[str, pd.DataFrame]:
    """加载并处理所有 ETF 数据
    
    Returns:
        {code: df} 其中 df 已包含完整指标和 ma/vol/rsi 列
    """
    data = {}
    for code in ALL_ETFS:
        df = loader.load_single(code, min_rows=400)
        if df is None or len(df) < 200:
            print(f"  ⚠️ {code} 数据不足，跳过")
            continue
        
        df = df.sort_values('date').reset_index(drop=True)
        df = calc.calculate_all(df)
        df = _add_ma_vol_rsi(df)
        data[code] = df
        print(f"  加载 {code}: {len(df)} 行")
    
    return data


# ============================================================
# 回测执行
# ============================================================

def run_wf_backtest(
    all_data: Dict[str, pd.DataFrame],
    oos_start: str,
    oos_end: str,
    hold_count: int,
    score_threshold: int = 6,
) -> Dict:
    """执行单次回测（多 ETF 组合）
    
    Args:
        all_data: 所有 ETF 数据（完整数据，已计算指标）
        oos_start: OOS 开始日期
        oos_end: OOS 结束日期
        hold_count: 持仓数量
        score_threshold: 评分阈值
    
    Returns:
        回测结果
    
    注意：
        - all_data 是完整数据，用于 Selector 评分
        - 回测引擎会在内部根据日期过滤数据
    """
    # 过滤 OOS 期数据（用于持仓计算）
    oos_data = {}
    for code, df in all_data.items():
        oos_df = df[(df['date'] >= oos_start) & (df['date'] <= oos_end)].copy()
        if len(oos_df) >= 30:
            oos_data[code] = oos_df
    
    if len(oos_data) < 5:  # 至少需要 5 只 ETF
        return {
            'sharpe': 0, 'return': 0, 'win_rate': 0, 
            'profit_loss_ratio': 0, 'trades': 0,
            'error': '数据不足'
        }
    
    # 配置回测参数
    config = BacktestConfig(
        max_positions=hold_count,
        score_threshold=score_threshold,
        use_selector=True,                    # 使用 Selector 评分
        enable_signal_persistence=True,       # 启用信号持续性
        signal_consecutive_days=2,            # 连续2天低分才卖出
        min_hold_days=3,                      # 最小持仓3天
        max_hold_days=15,                     # 最大持仓15天
        stop_loss=-0.10,                      # 止损10%
        stop_profit=0.15,                     # 止盈15%
        rebalance_only_when_empty=True,        # 只有空仓才重新选择
    )
    
    # 创建回测器
    backtester = FactorBacktester(config=config)
    
    # 注入完整数据用于评分（Selector 需要完整历史计算 ma120）
    backtester._full_data = all_data
    
    # 注入排除列表（510300 是大盘参考，不参与交易）
    backtester._exclude_codes = {MARKET_ETF}
    
    try:
        # 执行回测
        result = backtester.backtest(
            price_data=oos_data,
            start_date=oos_start,
            end_date=oos_end,
            valid_factors=[],  # Selector 模式不需要
        )
        
        # 计算指标
        return {
            'sharpe': result.sharpe_relative or 0,
            'return': result.total_return * 100,
            'win_rate': result.win_rate * 100,
            'profit_loss_ratio': result.profit_loss_ratio or 0,
            'trades': result.trade_count,
            'avg_hold_days': np.mean([t.get('hold_days', 0) for t in result.trades]) if result.trades else 0,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'sharpe': 0, 'return': 0, 'win_rate': 0,
            'profit_loss_ratio': 0, 'trades': 0,
            'error': str(e)
        }


# ============================================================
# 4折验证
# ============================================================

@dataclass
class WFFoldResult:
    """单折验证结果"""
    fold: int
    oos_start: str
    oos_end: str
    sharpe: float
    return_pct: float
    win_rate: float
    profit_loss_ratio: float
    trades: int
    pass_: bool
    reason: str
    
    def to_dict(self) -> Dict:
        """转换为可序列化的字典"""
        return {
            'fold': self.fold,
            'oos_start': self.oos_start[:7],
            'oos_end': self.oos_end[:7],
            'sharpe': round(self.sharpe, 2),
            'return_pct': round(self.return_pct, 1),
            'win_rate': round(self.win_rate, 1),
            'profit_loss_ratio': round(self.profit_loss_ratio, 2),
            'trades': self.trades,
            'pass': bool(self.pass_),  # 确保原生 bool
            'reason': self.reason
        }


def validate_4fold(
    all_data: Dict[str, pd.DataFrame],
    hold_count: int,
    score_threshold: int = 6,
) -> Dict:
    """执行4折WF验证
    
    Args:
        all_data: 所有 ETF 数据
        hold_count: 持仓数量
        score_threshold: 评分阈值
    
    Returns:
        验证结果
    """
    fold_results = []
    
    for fold, is_start, is_end, oos_start, oos_end in FOLD_CONFIGS:
        result = run_wf_backtest(
            all_data, oos_start, oos_end,
            hold_count, score_threshold
        )
        
        # 判断通过
        sharpe = result.get('sharpe', 0)
        win_rate = result.get('win_rate', 0) / 100
        profit_loss_ratio = result.get('profit_loss_ratio', 0)
        profit_x_win = profit_loss_ratio * win_rate
        
        pass_ = bool(sharpe >= 0.5 and win_rate >= 0.4 and profit_x_win > 1.0)
        
        if pass_:
            reason = "通过"
        else:
            reasons = []
            if sharpe < 0.5:
                reasons.append(f"Sharpe={sharpe:.2f}<0.5")
            if win_rate < 0.4:
                reasons.append(f"胜率={win_rate*100:.1f}%<40%")
            if profit_x_win <= 1.0:
                reasons.append(f"盈亏比×胜率={profit_x_win:.2f}≤1.0")
            reason = "; ".join(reasons)
        
        fold_results.append(WFFoldResult(
            fold=fold,
            oos_start=oos_start,
            oos_end=oos_end,
            sharpe=float(sharpe),
            return_pct=float(result.get('return', 0)),
            win_rate=float(result.get('win_rate', 0)),
            profit_loss_ratio=float(profit_loss_ratio),
            trades=int(result.get('trades', 0)),
            pass_=pass_,
            reason=reason,
        ))
        
        print(f"    Fold {fold}: Sharpe={sharpe:.2f}, 胜率={win_rate*100:.1f}%, "
              f"盈亏比={profit_loss_ratio:.2f}, 交易={result.get('trades', 0)} → {'✅' if pass_ else '❌'}")
    
    n_passed = sum(1 for f in fold_results if f.pass_)
    
    return {
        'hold_count': hold_count,
        'score_threshold': score_threshold,
        'n_folds': len(fold_results),
        'n_passed': n_passed,
        'pass_rate': n_passed / len(fold_results) * 100 if fold_results else 0,
        'avg_sharpe': np.mean([f.sharpe for f in fold_results]) if fold_results else 0,
        'avg_win_rate': np.mean([f.win_rate for f in fold_results]) if fold_results else 0,
        'overall_pass': n_passed == len(fold_results),
        'folds': fold_results,
    }


# ============================================================
# 主入口
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description='4折Walk-Forward验证 v2.0（多ETF组合）')
    parser.add_argument('--hold-counts', nargs='+', type=int, default=[1, 2, 3],
                        help='持仓数量列表，默认 1 2 3')
    parser.add_argument('--score-threshold', type=int, default=6,
                        help='评分阈值，默认 6')
    parser.add_argument('--output', default='data/wf4_results_v2.json',
                        help='输出JSON路径')
    args = parser.parse_args()
    
    print("=" * 60)
    print(f"4折WF验证 v2.0（多ETF组合）")
    print(f"持仓数量: {args.hold_counts}")
    print(f"评分阈值: {args.score_threshold}")
    print("=" * 60)
    
    # 加载数据
    print("\n📊 加载 ETF 数据...")
    loader = DataLoader()
    calc = IndicatorCalculator()
    all_data = load_etf_data(loader, calc)
    
    if len(all_data) < 5:
        print("❌ ETF 数据不足，无法验证")
        return
    
    print(f"\n✅ 加载完成：{len(all_data)} 只 ETF")
    
    # 执行验证
    all_results = {}
    
    for hold_count in args.hold_counts:
        print(f"\n📈 持仓数量 = {hold_count}:")
        result = validate_4fold(all_data, hold_count, args.score_threshold)
        all_results[f'hold_count_{hold_count}'] = result
        
        # 打印汇总
        status = "✅" if result['overall_pass'] else "❌"
        print(f"  汇总: {result['n_passed']}/{result['n_folds']}折通过 {status}")
        print(f"  平均 Sharpe={result['avg_sharpe']:.2f}, 平均胜率={result['avg_win_rate']:.1f}%")
    
    # 保存结果
    output = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'etf_pool': {
            'trade_etfs': TRADE_ETFS,
            'market_etf': MARKET_ETF,
            'total': len(ALL_ETFS),
        },
        'fold_configs': [(f, s, e, o, o2) for f, s, e, o, o2 in FOLD_CONFIGS],
        'pass_criteria': {
            'sharpe': '>=0.5',
            'win_rate': '>=40%',
            'profit_x_win': '>1.0',
        },
        'results': {
            k: {
                'n_folds': v['n_folds'],
                'n_passed': v['n_passed'],
                'pass_rate': round(v['pass_rate'], 1),
                'avg_sharpe': round(v['avg_sharpe'], 2),
                'avg_win_rate': round(v['avg_win_rate'], 1),
                'overall_pass': v['overall_pass'],
                'folds': [
                    {
                        'fold': f.fold,
                        'oos_range': f'{f.oos_start[:7]}~{f.oos_end[:7]}',
                        'sharpe': round(f.sharpe, 2),
                        'return': round(f.return_pct, 1),
                        'win_rate': round(f.win_rate, 1),
                        'profit_loss_ratio': round(f.profit_loss_ratio, 2),
                        'trades': f.trades,
                        'pass': f.pass_,
                        'reason': f.reason,
                    }
                    for f in v['folds']
                ]
            }
            for k, v in all_results.items()
        }
    }
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'=' * 60}")
    print(f"✅ 结果已保存: {output_path}")
    
    # 汇总
    n_pass_all = sum(1 for v in all_results.values() if v['overall_pass'])
    print(f"汇总: {n_pass_all}/{len(all_results)} 种持仓配置全部4折通过")


if __name__ == '__main__':
    main()