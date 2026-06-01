#!/usr/bin/env python3
"""
每日决策快照生成（Q-014）

在每个工作日 14:25 由 cron 自动调用
生成 decision_snapshot.json 用于交易决策追溯

Usage:
    python scripts/maintenance/daily_snapshot.py
"""
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# 调用 snapshot_decision.py 的核心逻辑
from scripts.maintenance.snapshot_decision import (
    get_experiment_info,
    get_current_strategy_config,
    get_evaluation_metrics,
    get_top_models,
    get_top10_recommendations,
    get_trade_history,
)


def main():
    snapshot = {
        'snapshot_time': datetime.now().isoformat(),
        'snapshot_version': '1.0',
        'auto_generated': True,
        'trigger': 'cron_daily_1425',
    }

    # 1. 当前模型信息
    snapshot['model_info'] = {
        'name': 'ETF量化决策v8_sop',
        'experiment_file': 'data/experiments_v8_sop/results_sop.json',
        'experiment_info': get_experiment_info(),
    }

    # 2. 策略配置
    snapshot['strategy_config'] = get_current_strategy_config()

    # 3. 评价指标
    snapshot['evaluation_metrics'] = get_evaluation_metrics()

    # 4. Top 5 模型
    snapshot['top_5_models'] = get_top_models(5)

    # 5. 今日推荐
    snapshot['today_top_10'] = get_top10_recommendations()

    # 6. 回测最后 10 条
    snapshot['backtest_last_10_trades'] = get_trade_history(10)

    # 写文件
    output_path = Path('etf_data_live/decision_snapshot.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        import json
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print(f'✅ 自动快照: {output_path}')
    print(f'   时间: {snapshot["snapshot_time"]}')


if __name__ == '__main__':
    main()
