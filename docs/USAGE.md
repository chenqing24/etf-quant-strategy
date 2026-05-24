# ETF量化决策 - 使用说明

## 一、用户需要提供的参数

### 必需参数

| 参数 | 说明 | 示例 |
|------|------|------|
| **本金** | 投资金额 | 20000 (2万元) |
| **钉钉Webhook** | (可选) 推送通知 | https://oapi.dingtalk.com/robot/send?access_token=xxx |

### 可选参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 数据目录 | `etf_data_live/` | 本地缓存目录 |

---

## 二、如何调用

### 方式1: 命令行 (推荐)

```bash
cd /Users/qingchen/.qwenpaw/workspaces/default/etf_strategy
```

#### 每日检查 (每天下午2:30执行)
```bash
# 不带推送
python -m src.decision_cli -m daily

# 带钉钉推送 (需要设置webhook)
python -m src.decision_cli -m daily --webhook "你的钉钉webhook地址"
```

#### 手动触发完整评估
```bash
python -m src.decision_cli -m eval
```

#### 记录交易
```bash
# 买入
python -m src.decision_cli -m trade \
  --code 516050 \
  --action buy \
  --price 1.384 \
  --quantity 13000

# 卖出 (平仓)
python -m src.decision_cli -m trade \
  --code 516050 \
  --action sell \
  --price 1.420 \
  --quantity 13000
```

#### 查看交易历史
```bash
python -m src.decision_cli -m history
```

#### 绩效分析
```bash
python -m src.decision_cli -m perf
```

### 方式2: Python代码

```python
from src.report_generator import generate_decision_report

# 生成决策报告
report = generate_decision_report(capital=20000)
print(report)
```

---

## 三、定时任务配置

### Cron设置

```bash
# 每个工作日下午2:30执行 (周一至周五)
30 14 * * 1-5 cd /Users/qingchen/.qwenpaw/workspaces/default/etf_strategy && python -m src.decision_cli -m daily >> /tmp/etf_daily.log 2>&1
```

### 解释
- `30 14 * * 1-5` = 每天下午2:30，工作日(Mon-Fri)
- `cd ...` = 进入项目目录
- `-m daily` = 每日检查模式
- `>> /tmp/etf_daily.log 2>&1` = 输出日志

### 查看日志
```bash
tail -f /tmp/etf_daily.log
```

### 停止定时任务
```bash
crontab -e
# 删除对应行，保存退出
```

---

## 四、钉钉Webhook配置

### 1. 创建机器人
1. 打开钉钉群 → 设置 → 智能群助手
2. 添加机器人 → 自定义
3. 记录Webhook地址

### 2. 设置安全
- 方式1: 加签 (推荐，更安全)
- 方式2: IP白名单

### 3. 使用
```bash
export DINGTALK_WEBHOOK="https://oapi.dingtalk.com/robot/send?access_token=你的token"
python -m src.decision_cli -m daily --webhook "$DINGTALK_WEBHOOK"
```

---

## 五、数据流程

```
┌─────────────────────────────────────────────────────────────┐
│  定时任务触发: 每天 14:30                                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  1. 数据采集 (腾讯API → 本地缓存)                            │
│     - 检查本地最新日期                                       │
│     - 只获取缺失的天数 (增量更新)                            │
│     - 保存到 etf_data_live/                                 │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  2. 决策分析                                                │
│     - 加载本地数据                                           │
│     - 计算评分，筛选Top ETF                                 │
│     - 生成决策报告                                           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  3. 输出结果                                                │
│     - 控制台输出                                             │
│     - 报告保存到 etf_reports/                               │
│     - 钉钉推送 (如配置)                                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  4. 用户操作                                                │
│     - 参考报告执行交易                                       │
│     - 记录实际结果: python -m src.decision_cli -m trade     │
└─────────────────────────────────────────────────────────────┘
```

---

## 六、文件结构

```
etf_strategy/
├── src/
│   ├── data_fetcher.py      # 数据采集 (本地缓存+增量更新)
│   ├── report_generator.py  # 报告生成
│   ├── trade_tracker.py     # 交易记录
│   ├── decision_cli.py      # 命令行入口
│   └── ...
├── etf_data_live/           # 本地缓存数据 (自动创建)
├── etf_reports/             # 历史报告 (自动创建)
├── etf_trades.json          # 交易记录 (自动创建)
└── etf_performance.json     # 绩效数据 (自动创建)
```

---

## 七、常见问题

### Q: 首次运行需要做什么?
A: 只需运行一次完整评估:
```bash
python -m src.decision_cli -m eval
```
会自动获取1年历史数据。

### Q: 数据会自动更新吗?
A: 是的，`update_all()` 会检查本地数据，只获取最新几天。

### Q: 如何修改本金?
A: 在生成报告时指定:
```python
generate_decision_report(capital=50000)  # 5万元
```
或在命令行使用 `--capital 50000`

### Q: 止损/止盈条件是什么?
A: 
- 止损: -5%
- 止盈: +8% 或移动止盈(回撤4%)