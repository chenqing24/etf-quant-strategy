"""
过拟合验证模块

包含四大验证引擎：
- walk_forward: 时序稳健性验证
- monte_carlo: 统计显著性验证
- cross_etf: 跨ETF泛化验证
- comprehensive: 综合验证调度器

使用示例：
```python
from scripts.validators import ComprehensiveValidator

validator = ComprehensiveValidator()
result = validator.validate(etf_data_dict, signal_func)
print(f"综合评分: {result.composite_score}")
print(f"通过: {result.pass_}")
```
"""

from .walk_forward import WalkForwardEngine, WalkForwardResult, WindowResult, to_dict as wf_to_dict
from .monte_carlo import MonteCarloEngine, MCResult, to_dict as mc_to_dict
from .cross_etf import CrossEtfValidator, CrossEtfResult, to_dict as ce_to_dict
from .comprehensive import ComprehensiveValidator, ComprehensiveResult, to_dict as comp_to_dict

__all__ = [
    'WalkForwardEngine',
    'WalkForwardResult',
    'WindowResult',
    'wf_to_dict',
    'MonteCarloEngine',
    'MCResult',
    'mc_to_dict',
    'CrossEtfValidator',
    'CrossEtfResult',
    'ce_to_dict',
    'ComprehensiveValidator',
    'ComprehensiveResult',
    'comp_to_dict',
]