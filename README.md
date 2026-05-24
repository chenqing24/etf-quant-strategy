# ETF量化投资决策系统

基于7因子模型的ETF量化投资决策工具，支持自动推送钉钉通知。

## 快速开始

```bash
cd /Users/qingchen/.qwenpaw/workspaces/default/etf_strategy

# 每日决策 (自动推送到钉钉)
python -m src.decision_cli -m daily

# 完整评估
python -m src.decision_cli -m eval
```

## 功能

- 📊 **7因子选股** - MA趋势/动量/RSI/MACD/成交量
- 🔒 **风控机制** - 5%止损 + 8%止盈 + 移动止盈
- 📈 **多时段验证** - 滚动训练/测试
- 📱 **钉钉推送** - 简化版交易建议
- 🔄 **自动更新** - 每日14:30决策 + 每2周ETF池

## 策略表现

| 测试期 | 收益 | 回撤 | 夏普 |
|--------|------|------|------|
| 2023-2025 | +32.4% | -27.7% | 0.47 |
| 2024-2026 | +66.3% | -21.2% | 1.17 |
| **平均** | **+49.3%** | **-24.4%** | **0.82** |

## 项目结构

```
etf_strategy/
├── src/              # 核心代码
│   ├── decision_cli.py     # 命令行入口
│   ├── data_fetcher.py    # 数据采集
│   ├── report_generator.py # 报告生成
│   └── ...
├── docs/             # 文档
├── etf_pool.json     # ETF股票池 (25只)
├── etf_reports/       # 历史报告
└── etf_trades.json   # 交易记录
```

## 配置定时任务

```bash
# 每日14:30
30 14 * * 1-5 cd /path/to/etf_strategy && python -m src.decision_cli -m daily

# 每2周(1日、15日) 9:00
0 9 1,15 * * cd /path/to/etf_strategy && python -m src.decision_cli -m update_pool
```

## 文档

- [使用说明](docs/USAGE.md)
- [架构设计](docs/ARCHITECTURE.md)
- [Cron配置](docs/CRON_SETUP.md)