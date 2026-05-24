# ETF量化投资决策系统 - 架构设计

## 一、系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         ETF量化决策系统                              │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         入口层 (CLI)                                 │
│                    src/decision_cli.py                              │
└─────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌───────────────┐         ┌───────────────┐         ┌───────────────┐
│  数据采集层   │         │  决策分析层   │         │  交易执行层   │
│  data_fetcher │         │  report_gen   │         │  trade_tracker│
│  data_loader  │         │  selector     │         │  notifier     │
└───────────────┘         │  indicator    │         └───────────────┘
        │                 │  backtest     │
        ▼                 └───────────────┘
┌───────────────┐                 │
│  数据存储层   │                 │
│  CSV/JSON     │                 ▼
└───────────────┘         ┌───────────────┐
                          │  绩效分析层   │
                          │  perf_analyzer│
                          └───────────────┘
```

---

## 二、分层说明

### 1. 入口层 (CLI)

**文件**: `src/decision_cli.py`

**职责**:
- 统一命令行入口
- 解析用户参数
- 协调各模块执行
- 日志输出

**对外接口**:
```bash
python -m src.decision_cli -m daily
python -m src.decision_cli -m eval
python -m src.decision_cli -m trade --code 516050 --action buy ...
```

---

### 2. 数据采集层

**文件**: 
- `src/data_fetcher.py` - 腾讯API采集
- `src/data_loader.py` - 本地数据加载
- `src/indicator.py` - 技术指标计算

**职责**:
- 从腾讯API获取实时数据
- 本地缓存 + 增量更新
- 计算MA/RSI/MACD等技术指标
- 数据质量校验

**数据流**:
```
腾讯API → fetch_etf() → save_etf() → etf_data_live/*.csv
                              ↓
                         load_data() → calculate() → indicator.py
```

---

### 3. 决策分析层

**文件**:
- `src/selector.py` - 7因子选股
- `src/report_generator.py` - 决策报告
- `src/backtest.py` - 回测引擎

**职责**:
- 7因子打分 (MA120/MA60/MA20 + 放量 + RSI + MACD)
- 多时段策略验证
- 生成固定模板报告 (定量+定性)
- 策略参数优化

**核心类**:
```python
class Selector:
    def score(self, df, date) -> (int, List[str]): ...
    def select_etfs(self, data, config) -> Set[str]: ...

class ETFReportGenerator:
    def load_data(self) -> str: ...
    def analyze_market(self) -> Dict: ...
    def validate_strategy(self) -> List[Dict]: ...
    def generate_report(self, capital) -> str: ...
```

---

### 4. 交易执行层

**文件**:
- `src/trade_tracker.py` - 交易追踪
- `src/notifier.py` - 通知推送

**职责**:
- 记录实盘交易 (买入/卖出)
- 持仓状态追踪
- 止损/止盈检查
- 钉钉/微信推送

**核心类**:
```python
class TradeTracker:
    def record_buy(self, code, name, price, quantity, reason): ...
    def record_sell(self, code, price, actual_pnl): ...
    def get_holdings(self) -> List[Position]: ...
    def check_stop_loss(self, code, threshold) -> bool: ...
    def need_rebalance(self, days) -> bool: ...
```

---

### 5. 绩效分析层

**文件**: `src/performance_analyzer.py`

**职责**:
- 加载历史交易记录
- 计算胜率/盈亏比
- vs 预期对比
- vs 基准对比 (沪深300)
- 生成绩效报告

---

## 三、数据存储

### 文件说明

| 文件/目录 | 类型 | 内容 |
|-----------|------|------|
| `etf_data_50/` | 目录 | 历史ETF数据 (54只) |
| `etf_data_live/` | 目录 | 实时缓存数据 |
| `etf_trades.json` | JSON | 交易记录 |
| `etf_positions.json` | JSON | 当前持仓 |
| `etf_performance.json` | JSON | 累计绩效 |
| `etf_reports/` | 目录 | 历史报告 |

### 数据格式

**etf_trades.json**:
```json
{
  "trades": [
    {
      "date": "2025-05-24",
      "code": "516050",
      "name": "科创成长",
      "action": "buy",
      "price": 1.384,
      "quantity": 13000,
      "amount": 17992,
      "reason": "策略推荐",
      "actual_pnl": 0
    }
  ]
}
```

**etf_performance.json**:
```json
{
  "initial_capital": 20000,
  "current_capital": 21000,
  "total_pnl": 5.0,
  "total_trades": 3,
  "win_rate": 66.7
}
```

---

## 四、核心流程

### 流程1: 每日检查

```
CLI -m daily
    ↓
data_fetcher.update_all()  [检查本地，增量更新]
    ↓
trade_tracker.get_holdings()  [检查持仓]
    ↓
check_stop_loss() / check_take_profit()  [风控检查]
    ↓
need_rebalance()  [是否需要调仓]
    ├─ YES → run_full_evaluation()
    └─ NO  → 输出持仓状态
    ↓
report_generator.generate_report()  [生成报告]
    ↓
notifier.send_daily_summary()  [推送]
```

### 流程2: 交易记录

```
CLI -m trade --code 516050 --action buy ...
    ↓
trade_tracker.record_buy()  [记录买入]
    ↓
update positions.json
    ↓
notify "已记录买入"
    ↓
用户执行实际交易
    ↓
再次运行 -m trade --action sell 记录实际盈亏
    ↓
performance_analyzer 对比预期vs实际
```

---

## 五、策略参数配置

### 风控参数 (默认)

```python
STOP_LOSS = 0.05        # 止损 5%
TAKE_PROFIT = 0.08      # 止盈 8%
TRAILING_THRESHOLD = 0.06  # 移动止盈启动 6%
TRAILING_STOP = 0.04    # 移动止盈回撤 4%
REBALANCE_DAYS = 10     # 调仓周期 10天
SCORE_THRESHOLD = 6     # 选股分数 >= 6
HOLD_COUNT = 1          # 持仓 1只
```

### 数据参数

```python
ETF_COUNT = 40          # 覆盖ETF数量
TRAIN_PERIOD = '2年'    # 训练期
TEST_PERIOD = '1年+'    # 测试期
FACTORS = ['MA120', 'MA60', 'MA20', 'vol', 'RSI', 'MACD']
```

---

## 六、扩展点

### 可扩展功能

1. **多策略切换** - 添加更多选股策略
2. **数据库存储** - MongoDB/PostgreSQL
3. **实时推送** - 微信/ tg bot
4. **模拟交易** - 对接券商API
5. **组合优化** - 多标的组合推荐

### 模块依赖

```
decision_cli (入口)
    ├── data_fetcher (数据)
    ├── report_generator (分析)
    │   ├── selector (选股)
    │   ├── indicator (指标)
    │   └── backtest (回测)
    ├── trade_tracker (交易)
    │   └── notifier (通知)
    └── performance_analyzer (绩效)
```

---

## 七、部署方式

### 本地运行

```bash
# 手动执行
python -m src.decision_cli -m daily
```

### 定时任务

```bash
# Cron - 每个工作日下午2:30
30 14 * * 1-5 cd /path/to/etf_strategy && python -m src.decision_cli -m daily
```

### Docker (可选)

```dockerfile
FROM python:3.11
WORKDIR /app
COPY . .
RUN pip install pandas requests
CMD ["python", "-m", "src.decision_cli", "-m", "daily"]
```

---

## 八、安全考虑

1. **数据备份** - 定期备份交易记录
2. **异常处理** - API失败降级处理
3. **日志审计** - 完整操作记录
4. **参数校验** - 防止异常输入

---

版本: 1.0  
最后更新: 2026-05-24