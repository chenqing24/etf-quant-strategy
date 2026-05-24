# ETF量化投资决策系统

基于7因子选股的ETF量化交易策略，包含完整的策略回测、信号生成、交易追踪和绩效分析功能。

## 功能特性

- ✅ **7因子选股** - MA120/MA60/MA20 + 放量 + RSI + MACD
- ✅ **多时段验证** - 交叉验证，过拟合检验
- ✅ **移动止盈** - 盈利超10%后，回撤8%止盈
- ✅ **市场过滤** - 下跌趋势空仓回避
- ✅ **固定模板报告** - 定量数据 + 定性分析
- ✅ **交易追踪** - 记录实盘，绩效对比
- ✅ **钉钉推送** - 信号即时通知
- ✅ **定时执行** - 每工作日下午2:30自动运行

## 策略表现

| 指标 | 数值 |
|------|------|
| 平均收益 | +38.3% |
| 最大回撤 | ~25% |
| 夏普比率 | 0.69 |
| 胜率 | ~52% |

## 快速开始

### 安装依赖

```bash
cd etf_strategy
pip install pandas requests
```

### 首次运行

```bash
# 生成决策报告
python -m src.decision_cli -m eval
```

### 每日使用

```bash
# 每日检查 (数据更新 + 持仓检查 + 决策建议)
python -m src.decision_cli -m daily
```

### 记录交易

```bash
# 买入后记录
python -m src.decision_cli -m trade --code 516050 --action buy --price 1.384 --quantity 13000

# 卖出后记录
python -m src.decision_cli -m trade --code 516050 --action sell --price 1.420 --quantity 13000
```

## 项目结构

```
etf_strategy/
├── src/                      # 核心代码
│   ├── data_fetcher.py       # 腾讯API数据采集
│   ├── data_loader.py        # 数据加载
│   ├── indicator.py          # 技术指标计算
│   ├── selector.py           # 7因子选股
│   ├── market_filter.py      # 市场过滤
│   ├── trade.py              # 交易执行
│   ├── backtest.py           # 回测引擎
│   ├── metrics.py            # 绩效指标
│   ├── report_generator.py   # 决策报告生成
│   ├── trade_tracker.py      # 交易追踪
│   ├── performance_analyzer.py # 绩效分析
│   └── decision_cli.py       # 命令行入口
├── tests/                    # 单元测试
│   └── test_all.py          # 全部测试
├── docs/                     # 文档
│   ├── USAGE.md             # 使用说明
│   ├── CRON_SETUP.md        # 定时任务配置
│   └── ETF_SKILL_PLAN.md    # 整体规划
├── etf_data_50/             # 历史数据 (54只ETF)
├── etf_data_live/           # 实时数据缓存
└── etf_reports/             # 历史报告
```

## 策略参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 持仓数量 | 1只 | 降低波动 |
| 止损线 | -5% | 单笔最大亏损 |
| 止盈线 | +8% | 固定止盈 |
| 移动止盈 | 回撤4% | 盈利超10%后启用 |
| 调仓周期 | 10天 | 强制调仓间隔 |
| 评分阈值 | 6分 | 选股最低分数 |

## 定时任务

每个工作日下午2:30自动执行：

```bash
# 添加到crontab
30 14 * * 1-5 cd /path/to/etf_strategy && python -m src.decision_cli -m daily
```

## 数据采集

- **数据源**: 腾讯API
- **缓存策略**: 本地CSV文件 + 增量更新
- **ETF数量**: 40只 (覆盖主要宽基/行业)

## 单元测试

```bash
# 运行全部测试
python tests/test_all.py

# 运行回归测试
python tests/test_regression.py
```

## 钉钉推送 (可选)

```bash
# 设置Webhook
export DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=xxx"

# 带推送执行
python -m src.decision_cli -m daily --webhook "$DINGTALK_WEBHOOK"
```

## 文档

- [使用说明](docs/USAGE.md)
- [定时任务配置](docs/CRON_SETUP.md)
- [整体规划](docs/ETF_SKILL_PLAN.md)

## 技术栈

- Python 3.11+
- pandas - 数据处理
- requests - API请求
- json - 数据存储

## License

MIT