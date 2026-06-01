#!/usr/bin/env python3
"""
生成完整的交易决策快照

包括：
1. 模型/策略信息
2. 策略全维度参数
3. 回测评估指标
4. 推荐TOP 10
5. 回测最后10条交易记录
6. 当前交易上下文
"""
import json
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.utils.config import StrategyConfig, run_strategy
from src.data.loader import DataLoader


def get_top_models(n: int = 5) -> list:
    """从实验结果读取 Top N 模型"""
    exp_path = Path('data/experiments_v8_sop/results_sop.json')
    if not exp_path.exists():
        return []
    with open(exp_path) as f:
        d = json.load(f)
    return d.get('top_models', [])[:n]


def get_experiment_info() -> dict:
    """获取实验基础信息"""
    exp_path = Path('data/experiments_v8_sop/results_sop.json')
    if not exp_path.exists():
        return {}
    with open(exp_path) as f:
        d = json.load(f)
    return d.get('experiment_info', {})


def get_top10_recommendations() -> list:
    """获取今日 Top 10 推荐（来自决策报告）"""
    report_files = sorted(Path('etf_reports').glob('report_*.txt'), reverse=True)
    if not report_files:
        return []
    content = report_files[0].read_text(encoding='utf-8')
    # 解析TOP 10部分
    in_top10 = False
    lines = []
    for line in content.split('\n'):
        if 'TOP 10 推荐' in line:
            in_top10 = True
            continue
        if in_top10:
            if '【核心推荐】' in line or '四、资金配置' in line:
                break
            if line.strip() and not line.startswith('=') and not line.startswith('排名') and not line.startswith('-'):
                lines.append(line.strip())
    return lines


def get_trade_history(limit: int = 10) -> list:
    """获取历史回测交易记录快照

    由于原始回测中保存的是组合级指标而非逐笔交易，
    这里展示最近一次回测的Top组合作为'交易快照'。
    """
    exp_path = Path('data/experiments_v8_sop/results_sop.json')
    if not exp_path.exists():
        return []
    with open(exp_path) as f:
        d = json.load(f)

    # 提取 top_models 字段（每条相当于一个策略在某ETF上的完整回测）
    top = d.get('top_models', [])[:limit]
    trade_snapshot = []
    for m in top:
        trade_snapshot.append({
            'model_id': f"{'+'.join(m.get('factors', []))}@{m.get('etf_code', '')}",
            'etf_code': m.get('etf_code', ''),
            'factors': m.get('factors', []),
            'trade_count': m.get('trade_count', 0),
            'total_return': round(m.get('total_return', 0), 4),
            'avg_profit': round(m.get('avg_profit', 0), 6),
            'sharpe': round(m.get('sharpe', 0), 4),
            'win_rate': round(m.get('win_rate', 0), 4),
            'pass_core': m.get('pass_core', False),
            'overfit': {
                'rolling_window_pass_rate': m.get('overfit_rolling', 0),
                'mc_pvalue': m.get('overfit_mc_pvalue', 1.0),
                'cv_score': m.get('overfit_cv', 0),
                'overfit_pass': m.get('overfit_pass', False),
            },
        })
    return trade_snapshot


def get_current_strategy_config() -> dict:
    """获取当前运行的策略配置"""
    config = StrategyConfig()
    return {
        'train_period': {
            'start': config.train_start,
            'end': config.train_end,
        },
        'selection': {
            'score_threshold': config.score_threshold,
            'top_n': config.top_n,
        },
        'position': {
            'hold_count': config.hold_count,
            'weights': list(config.weights),
        },
        'rebalance': {
            'rebalance_days': config.rebalance_days,
        },
        'risk_control': {
            'stop_loss': config.stop_loss,
            'stop_gain': config.stop_gain,
            'max_hold_days': config.max_hold_days,
        },
        'trailing_stop': {
            'enabled': config.enable_trailing_stop,
            'threshold': config.trailing_threshold,
            'stop': config.trailing_stop,
        },
        'market_filter': {
            'ma_period': config.market_ma,
            'enabled': config.enable_market_filter,
        },
    }


def get_evaluation_metrics() -> dict:
    """获取策略全维度评估指标"""
    exp_path = Path('data/experiments_v8_sop/results_sop.json')
    if not exp_path.exists():
        return {}

    with open(exp_path) as f:
        d = json.load(f)

    # 单因子 IC/IR
    single = d.get('single_factor', {})
    factor_metrics = {}
    for name, m in single.items():
        factor_metrics[name] = {
            'ic_mean': round(m.get('ic_mean', 0), 4),
            'ic_std': round(m.get('ic_std', 0), 4),
            'ir': round(m.get('ir', 0), 4),
            'avg_sharpe': round(m.get('avg_sharpe', 0), 4),
            'avg_win_rate': round(m.get('avg_win_rate', 0), 4),
            'avg_single_trade': round(m.get('avg_single_trade', 0), 6),
        }

    # 组合回测汇总
    combos = d.get('combinations', [])
    if combos:
        sharpes = [c.get('sharpe', 0) for c in combos]
        returns = [c.get('total_return', 0) for c in combos]
        win_rates = [c.get('win_rate', 0) for c in combos]

        portfolio_metrics = {
            'total_combinations': len(combos),
            'avg_sharpe': round(sum(sharpes) / len(sharpes), 4),
            'max_sharpe': round(max(sharpes), 4),
            'min_sharpe': round(min(sharpes), 4),
            'avg_return': round(sum(returns) / len(returns), 4),
            'max_return': round(max(returns), 4),
            'avg_win_rate': round(sum(win_rates) / len(win_rates), 4),
        }
    else:
        portfolio_metrics = {}

    # 过拟合验证
    passed_all = d.get('passed_all', 0)
    passed_core = d.get('passed_core', 0)
    overfit_validation = {
        'total_passed_all': passed_all if isinstance(passed_all, int) else len(passed_all),
        'total_passed_core': passed_core if isinstance(passed_core, int) else len(passed_core),
        'pass_rate_all': round((passed_all if isinstance(passed_all, int) else len(passed_all)) / max(1, len(combos)) * 100, 2),
        'pass_rate_core': round((passed_core if isinstance(passed_core, int) else len(passed_core)) / max(1, len(combos)) * 100, 2),
    }

    return {
        'single_factor_metrics': factor_metrics,
        'portfolio_metrics': portfolio_metrics,
        'overfit_validation': overfit_validation,
    }


def main():
    """生成完整交易快照"""
    snapshot = {
        'snapshot_time': datetime.now().isoformat(),
        'snapshot_version': '1.0',
        'data_date': None,
    }

    # 1. 当前运行模型信息
    snapshot['model_info'] = {
        'name': 'ETF量化决策v8_sop',
        'experiment_file': 'data/experiments_v8_sop/results_sop.json',
        'experiment_info': get_experiment_info(),
    }

    # 2. 策略配置
    snapshot['strategy_config'] = get_current_strategy_config()

    # 3. 评估指标（全维度）
    snapshot['evaluation_metrics'] = get_evaluation_metrics()

    # 4. 选股模型 Top 5
    snapshot['top_5_models'] = get_top_models(5)

    # 5. 今日 Top 10 推荐
    snapshot['today_top_10'] = get_top10_recommendations()

    # 6. 回测最近 10 条交易记录
    snapshot['backtest_last_10_trades'] = get_trade_history(10)

    # 7. 写文件
    output_path = Path('etf_data_live/decision_snapshot.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f'✅ 完整决策快照已保存: {output_path}')
    print(f'  - 策略配置: {len(snapshot["strategy_config"])} 项')
    print(f'  - 单因子指标: {len(snapshot["evaluation_metrics"].get("single_factor_metrics", {}))} 个')
    print(f'  - Top 5 模型: {len(snapshot["top_5_models"])} 个')
    print(f'  - 今日推荐: {len(snapshot["today_top_10"])} 条')
    print(f'  - 回测交易: {len(snapshot["backtest_last_10_trades"])} 条')


if __name__ == '__main__':
    main()
