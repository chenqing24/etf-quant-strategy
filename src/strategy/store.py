"""
实验配置存储

从 experiments.json 加载配置，执行并保存结果
"""
import json
from pathlib import Path
from typing import Dict, List, Optional
from src.strategy.config import ExperimentConfig
from src.strategy.engine import UniversalExecutor


class ExperimentStore:
    """实验配置存储"""
    
    def __init__(self, store_path: str = "data/experiments/experiments.json"):
        """
        初始化
        
        Args:
            store_path: 存储路径
        """
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.experiments = self._load()
    
    def _load(self) -> List[Dict]:
        """加载实验"""
        if self.store_path.exists():
            with open(self.store_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def _save(self):
        """保存实验"""
        with open(self.store_path, 'w', encoding='utf-8') as f:
            json.dump(self.experiments, f, ensure_ascii=False, indent=2)
    
    def add(self, config: ExperimentConfig) -> int:
        """
        添加配置
        
        Args:
            config: 实验配置
            
        Returns:
            实验ID
        """
        exp_id = len(self.experiments) + 1
        config.id = exp_id
        
        self.experiments.append(config.to_dict())
        self._save()
        
        return exp_id
    
    def get(self, exp_id: int) -> Optional[Dict]:
        """
        获取实验
        
        Args:
            exp_id: 实验ID
            
        Returns:
            实验字典
        """
        for exp in self.experiments:
            if exp.get('id') == exp_id:
                return exp
        return None
    
    def update_result(self, exp_id: int, result: Dict):
        """
        更新实验结果
        
        Args:
            exp_id: 实验ID
            result: 回测结果
        """
        for exp in self.experiments:
            if exp.get('id') == exp_id:
                exp['backtest_result'] = result
                break
        self._save()
    
    def run_experiment(
        self, 
        exp_id: int,
        db_path: str = "data/etf_factors.db"
    ) -> Dict:
        """
        运行实验
        
        Args:
            exp_id: 实验ID
            db_path: 数据库路径
            
        Returns:
            回测结果
        """
        exp = self.get(exp_id)
        if exp is None:
            raise ValueError(f"实验 {exp_id} 不存在")
        
        # 创建执行器
        config = ExperimentConfig.from_dict(exp)
        executor = UniversalExecutor(config)
        
        # 执行
        results = executor.run_single(db_path)
        
        # 保存结果
        result_dict = {
            'train': results['train'].to_dict(),
            'test': results['test'].to_dict()
        }
        self.update_result(exp_id, result_dict)
        
        return results
    
    def list_experiments(self) -> List[Dict]:
        """列出所有实验"""
        return [
            {
                'id': e.get('id'),
                'name': e.get('name'),
                'created_at': e.get('created_at'),
                'has_result': 'backtest_result' in e
            }
            for e in self.experiments
        ]


def quick_run(
    name: str,
    factors: list,
    weights: dict,
    direction: dict,
    stop_loss: float = -0.05,
    stop_profit: float = 0.10,
    threshold: float = 0.6,
    hold_days: int = 5,
    db_path: str = "data/etf_factors.db"
) -> Dict:
    """
    快速运行实验
    
    Args:
        name: 实验名称
        factors: 因子列表
        weights: 因子权重
        direction: 因子方向
        stop_loss: 止损
        stop_profit: 止盈
        threshold: 分数阈值
        hold_days: 持仓天数
        db_path: 数据库路径
        
    Returns:
        回测结果
    """
    from src.strategy.engine import create_config, UniversalExecutor
    
    config = create_config(
        name=name,
        factors=factors,
        weights=weights,
        direction=direction,
        stop_loss=stop_loss,
        stop_profit=stop_profit,
        threshold=threshold,
        hold_days=hold_days
    )
    
    executor = UniversalExecutor(config)
    return executor.run_single(db_path)