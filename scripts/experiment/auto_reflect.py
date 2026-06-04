#!/usr/bin/env python3
"""
IS-002: 自动化反思机制
按 SOP-01/SOP-03 流程，每 Sprint 结束自动检查 ComprehensiveValidator 通过率。
< 5% 触发反思机制，写入 memory/YYYY-MM-DD-v9-reflection.md

用法：
    # 检查指定 Sprint 结果
    python scripts/experiment/auto_reflect.py check --sprint v1 --results data/experiments_v9_recompute/v1_report.json

    # 只查看状态（不写入反思）
    python scripts/experiment/auto_reflect.py check --sprint v1 --results v1.json --dry-run

    # 继续执行（用户决策后）
    python scripts/experiment/auto_reflect.py continue --sprint v1

    # 终止任务
    python scripts/experiment/auto_reflect.py abort --sprint v1

设计原则（来自用户确认）：
- 谨慎模式：所有 cleanup 决策需用户确认
- 反思记录: memory/YYYY-MM-DD-v9-reflection.md
- 决策命令: continue / abort
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

# ==================== 配置 ====================
PASS_RATE_THRESHOLD = 0.05  # 5%
COMPREHENSIVE_THRESHOLD = 0.6  # ComprehensiveValidator 通过分
MEMORY_DIR = ROOT / 'memory'
REFLECTION_FILE_PREFIX = 'v9-reflection'

# ==================== 状态文件 ====================
STATE_FILE = Path('/tmp/v9_mission_state.json')


def load_results(results_path: Path) -> dict:
    """加载 Sprint 结果 JSON"""
    with open(results_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def calculate_pass_rate(results: dict) -> dict:
    """计算 ComprehensiveValidator 通过率"""
    models = []

    # 格式 1: {"results": [{"composite_score": 0.65, ...}, ...]}
    if 'results' in results and isinstance(results['results'], list):
        models = results['results']
    # 格式 2: {"single_factor": {"T1_MACD红柱": {"composite_score": 0.7, ...}}}
    elif 'single_factor' in results and isinstance(results['single_factor'], dict):
        for factor_name, factor_data in results['single_factor'].items():
            if isinstance(factor_data, dict):
                factor_data['_factor_name'] = factor_name
                models.append(factor_data)
    # 格式 3: {"combinations": [...]}
    elif 'combinations' in results and isinstance(results['combinations'], list):
        models = results['combinations']
    # 格式 4: list 直接
    elif isinstance(results, list):
        models = results

    total = len(models)
    if total == 0:
        return {
            'total': 0,
            'passed': 0,
            'pass_rate': 0.0,
            'models': [],
        }

    passed = sum(1 for m in models
                 if m.get('composite_score', 0) >= COMPREHENSIVE_THRESHOLD
                 or m.get('passed', False))

    return {
        'total': total,
        'passed': passed,
        'pass_rate': passed / total,
        'models': models,
    }


def generate_reflection(sprint_id: str, stats: dict) -> str:
    """生成反思记录 markdown"""
    now = datetime.now()
    time_str = now.strftime('%H:%M:%S')

    # 分析异常模式
    models = stats['models']
    negative_models = [m for m in models
                        if m.get('avg_single_trade', 0) < 0
                        or m.get('avg_profit', 0) < 0
                        or m.get('test_return', 0) < 0]
    low_sharpe = [m for m in models
                  if m.get('avg_sharpe', 99) < 0.5
                  and m.get('sharpe_ratio', 99) < 0.5]

    # 提取 ETF 分布
    etf_dist = {}
    for m in models:
        etf = m.get('code', 'unknown')
        etf_dist[etf] = etf_dist.get(etf, 0) + 1
    top_etfs = sorted(etf_dist.items(), key=lambda x: -x[1])[:5]

    # 提取因子分布
    factor_dist = {}
    for m in models:
        factors = m.get('factors', [m.get('factor', m.get('factor_name', 'unknown'))])
        if isinstance(factors, str):
            factors = [factors]
        for f in factors:
            if isinstance(f, str):
                factor_dist[f] = factor_dist.get(f, 0) + 1
    top_factors = sorted(factor_dist.items(), key=lambda x: -x[1])[:5]

    md = f"""## 反思 #{sprint_id} - {now.strftime('%Y-%m-%d %H:%M')}

**触发时间**: {time_str}
**Sprint**: {sprint_id}
**通过率**: {stats['pass_rate']*100:.1f}% (< 5% 阈值)
**模型数**: {stats['total']} (通过 {stats['passed']})

### 现象

- 负收益模型: {len(negative_models)}/{stats['total']}
- 低夏普模型 (< 0.5): {len(low_sharpe)}/{stats['total']}
- 异常占比: {len(negative_models)/max(stats['total'],1)*100:.1f}%

### ETF 分布（Top 5）

| ETF | 模型数 |
|-----|-------:|
"""
    for etf, cnt in top_etfs:
        md += f"| {etf} | {cnt} |\n"

    md += "\n### 因子分布（Top 5）\n\n| 因子 | 出现次数 |\n|------|--------:|\n"
    for fac, cnt in top_factors:
        md += f"| {fac} | {cnt} |\n"

    md += """
### 假设

H1: 数据质量问题 - 缺失/异常日期导致信号失真
H2: 参数过紧 - SL=-5% 在震荡市频繁止损
H3: 因子选择问题 - 当前因子不适用 2023-2026 市场环境
H4: 训练期过拟合 - 训练期 vs 测试期分布不一致
H5: 因子组合冲突 - 多个因子同时触发时相互抵消

### 下一步（用户决策）

- [ ] H1 验证：检查数据完整性
- [ ] H2 验证：测试 SL=-3% / -4% 对照组
- [ ] H3 验证：检查单因子 IC/IR 是否 > 0.02
- [ ] H4 验证：拆训练/测试期分别评估
- [ ] H5 验证：单因子逐一启用测试

### 决策

- [ ] continue（继续）
- [ ] retry（重新尝试，调整参数）
- [ ] abort（放弃当前方向）
"""
    return md


def write_reflection(sprint_id: str, content: str) -> Path:
    """写入反思文件"""
    today = datetime.now().strftime('%Y-%m-%d')
    reflection_file = MEMORY_DIR / f'{today}-v9-reflection.md'
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    # 追加模式（保留历史反思）
    with open(reflection_file, 'a', encoding='utf-8') as f:
        f.write('\n---\n\n')
        f.write(content)

    return reflection_file


def update_state(sprint_id: str, status: str, pass_rate: float):
    """更新任务状态文件"""
    state = {
        'sprint': sprint_id,
        'status': status,
        'pass_rate': pass_rate,
        'updated_at': datetime.now().isoformat(),
    }
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def cmd_check(args):
    """检查 Sprint 通过率"""
    results_path = Path(args.results)
    if not results_path.exists():
        print(f"❌ 结果文件不存在: {results_path}")
        return 1

    print(f"\n{'='*60}")
    print(f"IS-002 自动化反思检查: {args.sprint}")
    print(f"结果文件: {results_path}")
    print(f"{'='*60}\n")

    results = load_results(results_path)
    stats = calculate_pass_rate(results)

    print(f"总模型数: {stats['total']}")
    print(f"通过模型数: {stats['passed']}")
    print(f"通过率: {stats['pass_rate']*100:.1f}%")
    print(f"阈值: {PASS_RATE_THRESHOLD*100:.0f}%")

    if stats['pass_rate'] < PASS_RATE_THRESHOLD:
        print(f"\n⚠️  通过率 < 5% 阈值！触发反思机制")
        reflection = generate_reflection(args.sprint, stats)
        if not args.dry_run:
            reflection_file = write_reflection(args.sprint, reflection)
            update_state(args.sprint, 'BLOCKED', stats['pass_rate'])
            print(f"反思已写入: {reflection_file}")
            print(f"\n下一步决策:")
            print(f"  python scripts/experiment/auto_reflect.py continue --sprint {args.sprint}")
            print(f"  python scripts/experiment/auto_reflect.py abort --sprint {args.sprint}")
        else:
            print(f"\n[DRY RUN] 反思内容预览（前 20 行）:")
            for line in reflection.split('\n')[:20]:
                print(f"  {line}")
        return 2  # 退出码 2 表示 BLOCKED
    else:
        print(f"\n✅ 通过率 ≥ 5% 阈值，继续执行")
        if not args.dry_run:
            update_state(args.sprint, 'CONTINUE', stats['pass_rate'])
        return 0


def cmd_continue(args):
    """继续执行（用户决策后）"""
    update_state(args.sprint or 'unknown', 'CONTINUE_MANUAL', 0.0)
    print(f"✅ Sprint {args.sprint} 状态: CONTINUE（用户决策继续）")
    return 0


def cmd_abort(args):
    """终止任务"""
    update_state(args.sprint or 'unknown', 'ABORTED', 0.0)
    print(f"🛑 Sprint {args.sprint} 状态: ABORTED（用户决策终止）")
    return 0


def main():
    parser = argparse.ArgumentParser(description='SOP-01/SOP-03 自动化反思')
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # check 子命令
    p_check = subparsers.add_parser('check', help='检查 Sprint 通过率')
    p_check.add_argument('--sprint', required=True, help='Sprint ID (v1, v2, ...)')
    p_check.add_argument('--results', required=True, help='结果 JSON 路径')
    p_check.add_argument('--dry-run', action='store_true', help='只查看，不写入')

    # continue 子命令
    p_cont = subparsers.add_parser('continue', help='继续（用户决策后）')
    p_cont.add_argument('--sprint', help='Sprint ID')

    # abort 子命令
    p_abort = subparsers.add_parser('abort', help='终止任务')
    p_abort.add_argument('--sprint', help='Sprint ID')

    args = parser.parse_args()

    if args.command == 'check':
        return cmd_check(args)
    elif args.command == 'continue':
        return cmd_continue(args)
    elif args.command == 'abort':
        return cmd_abort(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
