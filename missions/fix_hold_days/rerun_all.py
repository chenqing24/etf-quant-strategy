"""重新运行所有实验 - 使用禁止调仓配置"""
import sys
sys.path.insert(0, '.')

from src.strategy.store import quick_run
import json

print("=" * 80)
print("重新运行所有实验 (allow_rebalance=False)")
print("=" * 80)

# 实验配置列表 (从实验名称中解析)
experiments = [
    # 第2轮
    ('Exp6', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.3, 'BB_percent': 0.1, 'SAR_trend': 0.3, 'OBV_diff': 0.3}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.6, 5),
    ('Exp7', ['ADX', 'SAR_trend'], {'ADX': 0.6, 'SAR_trend': 0.4}, {'ADX': 'long', 'SAR_trend': 'long'}, -0.05, 0.10, 0.6, 5),
    ('Exp8', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.10, 0.15, 0.6, 5),
    ('Exp9', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.8, 5),
    ('Exp10', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.6, 2),
    ('Exp11', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.5, 5),
    ('Exp12', ['ADX', 'BB_percent', 'SAR_trend'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.3}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long'}, -0.05, 0.10, 0.6, 5),
    ('Exp13', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.03, 0.10, 0.6, 5),
    ('Exp14', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.2, 'BB_percent': 0.2, 'SAR_trend': 0.2, 'OBV_diff': 0.4}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.6, 5),
    ('Exp15', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.6, 10),
    ('Exp16', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.05, 0.6, 5),
    ('Exp17', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.25, 'BB_percent': 0.25, 'SAR_trend': 0.25, 'OBV_diff': 0.25}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.6, 5),
    ('Exp18', ['ADX'], {'ADX': 1.0}, {'ADX': 'long'}, -0.05, 0.10, 0.6, 5),
    ('Exp19', ['ADX'], {'ADX': 1.0}, {'ADX': 'long'}, -0.05, 0.10, 0.7, 5),
    ('Exp20', ['BB_percent', 'SAR_trend'], {'BB_percent': 0.5, 'SAR_trend': 0.5}, {'BB_percent': 'long', 'SAR_trend': 'long'}, -0.05, 0.10, 0.6, 5),
    # 第3轮
    ('Exp21', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.65, 5),
    ('Exp22', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.75, 5),
    ('Exp23', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.6, 5),
    ('Exp24', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.7, 'BB_percent': 0.1, 'SAR_trend': 0.1, 'OBV_diff': 0.1}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.8, 5),
    ('Exp25', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.04, 0.12, 0.6, 5),
    ('Exp26', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.06, 0.15, 0.6, 5),
    ('Exp27', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.8, 5),
    ('Exp28', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.6, 3),
    ('Exp29', ['ADX', 'BB_percent', 'SAR_trend'], {'ADX': 0.33, 'BB_percent': 0.33, 'SAR_trend': 0.34}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long'}, -0.05, 0.10, 0.6, 5),
    ('Exp30', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.08, 0.6, 5),
    # 第4轮
    ('Exp31', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.7, 4),
    ('Exp32', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.75, 3),
    ('Exp33', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.75, 2),
    ('Exp34', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.05, 0.7, 3),
    ('Exp35', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.7, 3),
    ('Exp36', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.8, 3),
    ('Exp37', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.03, 0.10, 0.75, 3),
    ('Exp38', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.08, 0.75, 3),
    ('Exp39', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.85, 3),
    ('Exp40', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.9, 3),
    # 第5轮
    ('Exp41', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.04, 0.10, 0.8, 3),
    ('Exp42', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.06, 0.8, 3),
    ('Exp43', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.03, 0.08, 0.8, 3),
    ('Exp44', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.82, 3),
    ('Exp45', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.78, 3),
    ('Exp46', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.02, 0.10, 0.8, 3),
    ('Exp47', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.12, 0.8, 3),
    ('Exp48', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.25, 'BB_percent': 0.25, 'SAR_trend': 0.25, 'OBV_diff': 0.25}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.10, 0.8, 3),
    ('Exp49', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.07, 0.8, 3),
    ('Exp50', ['ADX', 'BB_percent', 'SAR_trend', 'OBV_diff'], {'ADX': 0.5, 'BB_percent': 0.2, 'SAR_trend': 0.15, 'OBV_diff': 0.15}, {'ADX': 'long', 'BB_percent': 'long', 'SAR_trend': 'long', 'OBV_diff': 'short'}, -0.05, 0.055, 0.8, 3),
]

print(f"\n共 {len(experiments)} 个实验\n")

# 运行所有实验
results = []
errors = []

for i, (name, factors, weights, direction, stop_loss, stop_profit, threshold, hold_days) in enumerate(experiments):
    print(f"[{i+1}/{len(experiments)}] {name}", end=" ", flush=True)
    
    try:
        r = quick_run(
            name=name,
            factors=factors,
            weights=weights,
            direction=direction,
            stop_loss=stop_loss,
            stop_profit=stop_profit,
            threshold=threshold,
            hold_days=hold_days,
            allow_rebalance=False
        )
        
        result = {
            'name': name,
            'round': 2 if i < 15 else (3 if i < 25 else (4 if i < 35 else 5)),
            'config': {
                'factors': factors,
                'weights': weights,
                'direction': direction,
                'stop_loss': stop_loss,
                'stop_profit': stop_profit,
                'threshold': threshold,
                'hold_days': hold_days
            },
            'train': r['train'].to_dict(),
            'test': r['test'].to_dict()
        }
        results.append(result)
        
        print(f"Train={r['train'].total_return:.1%} Test={r['test'].total_return:.1%}")
        
    except Exception as e:
        errors.append({'name': name, 'error': str(e)})
        print(f"❌ 错误: {e}")

print(f"\n{'=' * 80}")
print(f"完成! 成功: {len(results)}, 失败: {len(errors)}")

# 保存结果
with open('data/experiments/round2_fixed.json', 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"结果已保存到 data/experiments/round2_fixed.json")