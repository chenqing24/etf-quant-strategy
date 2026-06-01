# TODO: 脚本重构走 DataLoader

> 创建日期：2026-06-01
> 创建人：福猫管家
> 关联：T2 pre-commit 钩子改进

## 背景

Mission-20260601-111629 期间，pre-commit 钩子（US-017）对 `scripts/.*\.py$` 检查 `sqlite3.connect`，
导致合理使用直接连接的运维工具被误判。

为解决误判问题，钩子**豁免**了以下目录：
- `scripts/maintenance/` - 运维工具（备份/迁移/初始化/修复）
- `scripts/analysis/` - 一次性分析脚本
- `scripts/filter/` - 一次性筛选脚本
- `src/data/` - 数据层实现（DataLoader/DataWriter/monitor 等）

但**严格来说** `scripts/analysis/` 和 `scripts/filter/` 仍违反 SOUL.md 规则 15（统一数据入口）。

## 待重构脚本

### scripts/analysis/（6 个）
- [ ] `analyze_etf_selection.py` - ETF筛选标准分析
- [ ] `analyze_etf_suitability.py` - ETF池适合性分析
- [ ] `analyze_volatility.py` - 价格波动分析
- [ ] `compare_data.py` - 数据对比
- [ ] `cross_validate_data.py` - 数据源交叉验证
- [ ] `full_validation.py` - 完整性验证

### scripts/filter/（4 个）
- [ ] `filter_top500_amount.py` - 流动性Top500筛选
- [ ] `filter_top500_etf.py` - Top500 ETF筛选
- [ ] `filter_top500_target.py` - Top500（成交额+规模）
- [ ] `merge_etf_pool.py` - ETF池合并

## 重构方案

将直接 `sqlite3.connect` 替换为 `DataLoader`：
```python
# 之前
import sqlite3
conn = sqlite3.connect('etf_data_live/etf.db')
df = pd.read_sql_query("SELECT * FROM daily WHERE code=?", conn, params=('510300',))

# 之后
from src.data.loader import DataLoader
loader = DataLoader()
df = loader.get_daily('510300')
```

## 优先级

**低** - 这些是一次性分析/筛选脚本，不影响日常运行。建议在下次 Mission 周期中处理。

## 验收标准

- [ ] 所有 scripts/analysis/ 和 scripts/filter/ 脚本通过钩子检查
- [ ] 脚本功能与原版一致（数据输出相同）
- [ ] 单元测试覆盖（如果脚本是常用工具）
