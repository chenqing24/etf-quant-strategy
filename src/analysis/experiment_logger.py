"""
因子挖掘实验记录器

每次实验记录:
- 实验编号
- 挖掘时间
- 数据范围
- 因子组合
- IC结果
- 权重配置
- 回测绩效
"""
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd


class ExperimentLogger:
    """因子挖掘实验记录器"""
    
    def __init__(self, log_dir: str = "data/experiments"):
        """
        初始化
        
        Args:
            log_dir: 实验记录目录
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.experiments_file = self.log_dir / "experiments.json"
        self.experiments = self._load_experiments()
    
    def _load_experiments(self) -> List[Dict]:
        """加载实验记录"""
        if self.experiments_file.exists():
            with open(self.experiments_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def _save_experiments(self):
        """保存实验记录"""
        with open(self.experiments_file, 'w', encoding='utf-8') as f:
            json.dump(self.experiments, f, ensure_ascii=False, indent=2)
    
    def _get_next_id(self) -> int:
        """获取下一个实验ID"""
        if not self.experiments:
            return 1
        return max(exp['id'] for exp in self.experiments) + 1
    
    def log_experiment(
        self,
        name: str,
        description: str,
        factors: List[str],
        ic_results: Dict[str, float],
        factor_direction: Dict[str, str],
        weights: Dict[str, float],
        backtest_result: Optional[Dict] = None,
        tags: List[str] = None
    ) -> int:
        """
        记录实验
        
        Args:
            name: 实验名称
            description: 实验描述
            factors: 因子列表
            ic_results: IC结果 {因子: IC值}
            factor_direction: 因子方向 {因子: long/short/neutral}
            weights: 权重配置
            backtest_result: 回测结果
            tags: 标签
            
        Returns:
            实验ID
        """
        exp_id = self._get_next_id()
        
        experiment = {
            'id': exp_id,
            'name': name,
            'description': description,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'factors': factors,
            'ic_results': ic_results,
            'factor_direction': factor_direction,
            'weights': weights,
            'backtest_result': backtest_result,
            'tags': tags or [],
            'round': self._get_current_round()
        }
        
        self.experiments.append(experiment)
        self._save_experiments()
        
        print(f"📝 实验 #{exp_id} 已记录: {name}")
        
        return exp_id
    
    def _get_current_round(self) -> int:
        """获取当前轮次 (每10次实验为1轮)"""
        return (len(self.experiments) - 1) // 10 + 1
    
    def get_round_summary(self, round_num: int) -> Dict:
        """获取轮次汇总"""
        round_exps = [e for e in self.experiments if e.get('round') == round_num]
        
        if not round_exps:
            return {'count': 0, 'experiments': []}
        
        summary = {
            'round': round_num,
            'count': len(round_exps),
            'experiments': [
                {
                    'id': e['id'],
                    'name': e['name'],
                    'created_at': e['created_at'],
                    'best_return': e.get('backtest_result', {}).get('total_return', None)
                }
                for e in round_exps
            ],
            'has_backtest': any(e.get('backtest_result') for e in round_exps)
        }
        
        # 如果有回测结果，计算平均绩效
        backtest_results = [e['backtest_result'] for e in round_exps if e.get('backtest_result')]
        if backtest_results:
            summary['avg_return'] = sum(r.get('total_return', 0) for r in backtest_results) / len(backtest_results)
            summary['avg_sharpe'] = sum(r.get('sharpe_ratio', 0) for r in backtest_results) / len(backtest_results)
            summary['avg_win_rate'] = sum(r.get('win_rate', 0) for r in backtest_results) / len(backtest_results)
        
        return summary
    
    def review_round(self, round_num: int) -> str:
        """
        复盘轮次
        
        Args:
            round_num: 轮次号
            
        Returns:
            复盘报告
        """
        summary = self.get_round_summary(round_num)
        
        if summary['count'] == 0:
            return f"轮次 #{round_num} 没有实验记录"
        
        report = []
        report.append("=" * 70)
        report.append(f"📊 轮次 #{round_num} 复盘报告")
        report.append("=" * 70)
        report.append(f"实验次数: {summary['count']}/10")
        report.append("")
        
        if summary.get('avg_return') is not None:
            report.append("📈 平均绩效:")
            report.append(f"  - 总收益: {summary['avg_return']:.2%}")
            report.append(f"  - 夏普比率: {summary['avg_sharpe']:.2f}")
            report.append(f"  - 胜率: {summary['avg_win_rate']:.2%}")
            report.append("")
        
        report.append("🔬 实验列表:")
        for exp in summary['experiments']:
            return_str = f"{exp['best_return']:.2%}" if exp['best_return'] is not None else "未回测"
            report.append(f"  #{exp['id']:2d} {exp['name']:<30} 返回:{return_str}")
        
        report.append("")
        report.append("💡 发现:")
        
        # 分析最佳实验
        best_exp = None
        if summary.get('avg_return') is not None:
            best_exp = max(
                [e for e in self.experiments if e.get('round') == round_num and e.get('backtest_result')],
                key=lambda x: x['backtest_result'].get('total_return', 0),
                default=None
            )
        
        if best_exp:
            report.append(f"  - 最佳实验: #{best_exp['id']} {best_exp['name']}")
            report.append(f"  - 最佳配置: {best_exp.get('weights', {})}")
            report.append(f"  - 关键因子: {', '.join(best_exp.get('factors', []))}")
        
        report.append("=" * 70)
        
        return "\n".join(report)
    
    def get_best_experiments(self, n: int = 3) -> List[Dict]:
        """获取最佳实验"""
        valid_exps = [e for e in self.experiments if e.get('backtest_result')]
        if not valid_exps:
            return []
        
        return sorted(
            valid_exps,
            key=lambda x: x['backtest_result'].get('total_return', 0),
            reverse=True
        )[:n]
    
    def print_recent(self, n: int = 10):
        """打印最近N次实验"""
        recent = self.experiments[-n:] if len(self.experiments) >= n else self.experiments
        
        print("\n" + "=" * 70)
        print(f"📋 最近 {len(recent)} 次实验")
        print("=" * 70)
        
        for exp in reversed(recent):
            status = "✅" if exp.get('backtest_result') else "⏳"
            ret = exp.get('backtest_result', {}).get('total_return', None)
            ret_str = f"{ret:.2%}" if ret is not None else "-"
            
            print(f"{status} #{exp['id']:2d} {exp['created_at'][:10]} "
                  f"{exp['name']:<25} 返回:{ret_str}")
        
        print("=" * 70)
    
    def should_review(self) -> bool:
        """是否应该复盘"""
        current_round = self._get_current_round()
        last_reviewed_round = getattr(self, '_last_reviewed_round', 0)
        
        return current_round > last_reviewed_round and current_round > 0
    
    def mark_reviewed(self):
        """标记已复盘"""
        self._last_reviewed_round = self._get_current_round()


# 全局实例
_logger = None

def get_logger() -> ExperimentLogger:
    """获取记录器实例"""
    global _logger
    if _logger is None:
        _logger = ExperimentLogger()
    return _logger