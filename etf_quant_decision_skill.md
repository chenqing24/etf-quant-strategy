# ETF量化投资决策Skill

## 触发条件

使用此skill当用户提到：
- "ETF量化决策"
- "ETF投资报告"
- "运行ETF策略"
- "ETF每日检查"
- "更新ETF报告"

---

## 功能描述

基于etf_strategy项目，实现完整的ETF量化投资决策工作流：
1. 数据采集 - 腾讯API获取，本地缓存+增量更新
2. 市场分析 - 7因子打分，筛选Top ETF
3. 策略验证 - 多时段回测，评估表现
4. 报告生成 - 固定模板，定量+定性分析
5. 交易追踪 - 记录买卖，绩效对比
6. 定时执行 - 每工作日下午2:30自动运行

---

## 核心模块

| 模块 | 文件 | 功能 |
|------|------|------|
| data_fetcher | `src/data_fetcher.py` | 腾讯API采集，本地缓存增量更新 |
| report_generator | `src/report_generator.py` | 固定模板决策报告 |
| trade_tracker | `src/trade_tracker.py` | 交易记录、持仓追踪 |
| performance_analyzer | `src/performance_analyzer.py` | 绩效分析、vs预期对比 |
| decision_cli | `src/decision_cli.py` | 命令行统一入口 |

---

## 使用方法

### 命令行调用

```bash
cd /Users/qingchen/.qwenpaw/workspaces/default/etf_strategy

# 每日检查 (工作日下午2:30)
python -m src.decision_cli -m daily

# 完整评估
python -m src.decision_cli -m eval

# 每2周ETF池更新 (每月1日、15日)
python -m src.decision_cli -m update_pool

# 记录交易
python -m src.decision_cli -m trade --code 516050 --action buy --price 1.384 --quantity 13000

# 查看历史
python -m src.decision_cli -m history

# 绩效分析
python -m src.decision_cli -m perf
```

### Python调用

```python
from src.report_generator import generate_decision_report
from src.trade_tracker import TradeTracker
from src.data_fetcher import TencentETFetcher

# 生成决策报告
report = generate_decision_report(capital=20000)
print(report)

# 记录交易
tracker = TradeTracker('.')
tracker.record_buy('516050', '科创成长', 1.384, 13000, '策略推荐')

# 增量更新数据
fetcher = TencentETFetcher('etf_data_live')
fetcher.update_all_incremental()
```

---

## 用户参数

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| capital | 否 | 20000 | 投资本金(元) |
| webhook | 否 | None | 钉钉Webhook URL |

---

## 数据流程

```
定时任务 (14:30 工作日)
    ↓
数据采集 (腾讯API → 本地缓存)
    ↓
市场分析 (7因子打分 → Top ETF)
    ↓
策略验证 (多时段回测)
    ↓
报告生成 (定量+定性)
    ↓
输出 (控制台/文件/钉钉)
    ↓
用户执行 → 记录实盘结果 → 绩效对比
```

---

## 文件结构

```
etf_strategy/
├── src/
│   ├── data_fetcher.py      # 腾讯API数据采集
│   ├── report_generator.py  # 决策报告生成
│   ├── trade_tracker.py     # 交易追踪
│   ├── performance_analyzer.py  # 绩效分析
│   ├── etf_pool_updater.py  # ETF池管理
│   ├── decision_cli.py      # 命令行入口
│   └── ...
├── docs/
│   ├── USAGE.md             # 使用说明
│   ├── CRON_SETUP.md        # 定时任务配置
│   └── ARCHITECTURE.md       # 架构设计
├── etf_pool.json            # ETF股票池
├── etf_data_live/           # 本地缓存数据
├── etf_reports/             # 历史报告
├── etf_trades.json          # 交易记录
└── etf_performance.json     # 绩效数据
```

---

## 策略参数 (优化后)

| 参数 | 值 | 说明 |
|------|-----|------|
| 持仓数量 | 1只 | 降低波动 |
| 止损线 | -5% | 快速止损 |
| 止盈线 | +8% | 落袋为安 |
| 移动止盈 | 回撤4% | 持有盈利后启用 |
| 调仓周期 | 10天 | 到了强制调仓 |
| 最大回撤 | ~21% | 历史验证 |
| 夏普比率 | ~0.69 | 风险调整收益 |

---

## 配置定时任务

```bash
# 每个工作日下午2:30
30 14 * * 1-5 cd /path/to/etf_strategy && python -m src.decision_cli -m daily
```

---

## 注意事项

1. 首次运行会自动获取1年历史数据
2. 日常只增量更新最新几天数据
3. 止损/止盈触发时系统会提醒
4. 用户执行交易后需记录实际结果用于绩效分析

---

## 钉钉推送格式

```text
📈 ETF量化决策

🟢 操作: 买入
📊 标的: 516050 科创成长
💰 价格: 1.384
🛡️ 止损: 1.315 (-5%)
🎯 止盈: 1.495 (+8%)

📊 近5日趋势:
1.329→1.337→1.361→1.354→1.384
     ↑     ↑     ↓     ↑
涨跌: -1.1% +1.8% +0.6% +2.3%

📉 技术指标:
MA20:1.352 MA60:1.328 MA120:1.301
RSI14:65.3 量比:1.42
```
