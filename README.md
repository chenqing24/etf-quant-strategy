# ETF量化投资决策系统

> ⚠️ **本项目（v1）已重构为 v2（etf-quant-v2），仅做历史归档，不再维护。**
>
> 本仓库（`etf-quant-strategy` v1）的最终快照 tag 为 [`v1-deprecated-v2-refactor`](https://github.com/chenqing24/etf-quant-strategy/releases/tag/v1-deprecated-v2-refactor)。
>
> **后续功能开发、bug 修复、新因子实验均在 v2 进行：**
>
> | 项目 | 位置 |
> |------|------|
> | v2 仓库 | https://github.com/chenqing24/etf-quant-v2 （待创建） |
> | v2 本地路径 | `/home/qwenpaw/.qwenpaw/workspaces/default/etf_quant_v2` |
> | v2 触发词 | ETF 决策 / ETF 每日检查 / 跑 ETF / ETF 评估 |
> | v2 skill | `~/.qwenpaw/workspaces/default/skills/{etf-daily, etf-research, quant-knowledge, stock-analyze, stock-portfolio}` |
>
> **v1 → v2 演进说明**：[docs/V1_TO_V2_MIGRATION.md](docs/V1_TO_V2_MIGRATION.md)
>
> 归档日期：2026-06-20

---

基于7因子模型的ETF量化投资决策工具，支持自动推送钉钉通知。

## 快速开始

```bash
cd /Users/qingchen/.qwenpaw/workspaces/default/etf_strategy

# 每日决策 (自动推送到钉钉)
python -m src.cli.decision -m daily

# 完整评估
python -m src.cli.decision -m eval
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
| 2023-2025 | +20.8% | -26.2% | 0.29 |
| 2024-2026 | +135.5% | -5.6% | 1.96 |
| **平均** | **+78.2%** | **-15.9%** | **1.12** |

## 项目结构

```
etf_strategy/
├── src/              # 核心代码
│   ├── cli/          # 命令行入口
│   │   ├── decision.py   # ETF量化决策（daily/eval/trade）
│   │   └── main.py       # 回测入口
│   ├── data/         # 数据层（统一入口）
│   ├── strategy/     # 策略层
│   ├── risk/         # 风控层
│   └── ...
├── docs/             # 文档
├── etf_data_live/    # SQLite数据库 + 热数据
└── etf_reports/      # 历史报告
```

## 配置定时任务

```bash
# 每日14:30
30 14 * * 1-5 cd /path/to/etf_strategy && python -m src.cli.decision -m daily

# 每2周(1日、15日) 9:00
0 9 1,15 * * cd /path/to/etf_strategy && python -m src.cli.decision -m update_pool
```

## 文档

- [使用说明](docs/USAGE.md)
- [架构设计](docs/ARCHITECTURE.md)
- [Cron配置](docs/CRON_SETUP.md)