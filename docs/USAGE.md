# ETF量化决策 - 使用说明

## 一、用户参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 本金 | 20,000元 | 投资金额 |
| 数据目录 | `etf_data_live/` | 本地缓存 |

**钉钉推送**: 自动通过QwenPaw推送，无需配置webhook

---

## 二、命令行调用

### 每日检查 (工作日下午2:30)
```bash
cd /Users/qingchen/.qwenpaw/workspaces/default/etf_strategy
python -m src.decision_cli -m daily
```

### 完整评估
```bash
python -m src.decision_cli -m eval
```

### 记录交易
```bash
# 买入
python -m src.decision_cli -m trade \
  --code 516050 --action buy --price 1.384 --quantity 13000

# 卖出
python -m src.decision_cli -m trade \
  --code 516050 --action sell --price 1.420 --quantity 13000
```

### 查看历史
```bash
python -m src.decision_cli -m history
```

### 绩效分析
```bash
python -m src.decision_cli -m perf
```

### 更新ETF池 (每2周)
```bash
python -m src.decision_cli -m update_pool
```

---

## 三、输出说明

### 钉钉推送 (简化版)
```
📈 ETF量化决策

🟢 操作: 买入
📊 标的: 516050 科创成长
💰 价格: 1.384
🛡️ 止损: 1.315 (-5%)
🎯 止盈: 1.495 (+8%)
```

### 报告文件
- 路径: `etf_reports/report_YYYYMMDD.txt`
- 包含: 市场分析、历史回测、推荐标的、资金配置

---

## 四、定时任务配置

```bash
# 每日14:30 - 决策报告
30 14 * * 1-5 cd /path/to/etf_strategy && python -m src.decision_cli -m daily

# 每2周(1日、15日) 9:00 - ETF池更新
0 9 1,15 * * cd /path/to/etf_strategy && python -m src.decision_cli -m update_pool
```

---

## 五、ETF排除规则

以下ETF不参与7因子模型选股：
- **港股/境外**: 汇率+境外市场影响
- **红利ETF**: 走势与分红基本面相关
- **证券/金融**: 强周期，波动规律不同
- **债券**: 与股票走势不同
- **商品**: 受商品价格主导

---

## 六、策略参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 持仓数量 | 1只 | 降低波动 |
| 止损线 | -5% | 快速止损 |
| 止盈线 | +8% | 落袋为安 |
| 移动止盈 | 回撤4% | 盈利超10%后启用 |
| 调仓周期 | 10天 | 到了强制调仓 |

---

## 七、文件结构

```
etf_strategy/
├── src/
│   ├── data_fetcher.py      # 腾讯API数据采集
│   ├── report_generator.py  # 决策报告生成
│   ├── trade_tracker.py     # 交易追踪
│   ├── performance_analyzer.py  # 绩效分析
│   ├── etf_pool_updater.py  # ETF池管理
│   └── decision_cli.py      # 命令行入口
├── docs/                    # 文档
├── etf_pool.json            # ETF股票池 (25只)
├── etf_data_live/           # 本地缓存数据
├── etf_reports/             # 历史报告
├── etf_trades.json          # 交易记录
└── etf_performance.json     # 绩效数据
```