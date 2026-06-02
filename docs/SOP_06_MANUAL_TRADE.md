# SOP-06: 用户手动交易记录

**版本**：v1.0  
**作者**：福猫管家  
**创建日期**：2026-06-02  
**参考来源**：
- Investopedia: "Why Traders Need a Trade Journal"
- Bogleheads: Investment Journal Guidelines

---

## 1. 目的

标准化用户手动记录 ETF 买卖操作，确保交易历史完整、可追溯、可分析。

---

## 2. 触发场景

| 场景 | 说明 |
|------|------|
| 用户手动买入 | 用户自行在券商 App 买入 ETF 后，需要记录到系统 |
| 用户手动卖出 | 用户自行在券商 App 卖出 ETF 后，需要记录到系统 |
| 止损/止盈执行 | 策略触发信号，用户手动执行后记录 |

---

## 3. 字段标准

### 必填字段

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `code` | str | ETF代码 | `159611` |
| `name` | str | ETF名称 | `159611` |
| `price` | float | 成交价格 | `1.251` |
| `quantity` | int | 成交数量 | `4700` |
| `action` | str | 行为类型 | `buy` / `sell` |
| `date` | str | 交易日期（自动填充） | `2026-06-02` |

### 推荐字段

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `reason` | str | 交易原因 | `手动止损`、`MA20突破` |
| `signal_price` | float | 信号发出时的价格（买入时填写） | `1.240` |
| `actual_pnl` | float | 实际盈亏（卖出时填写） | `-128.0` |
| `notes` | str | 备注 | `盘中突发下跌` |

### 自动填充字段（系统完成）

| 字段 | 说明 | 来源 |
|------|------|------|
| `realtime_price` | 记录时的实时价格 | 腾讯API |
| `price_deviation` | 偏差率：(实时价-信号价)/信号价*100 | 自动计算 |
| `rsi_14` | RSI(14) 指标值 | 历史数据 |
| `day_change_pct` | 当日涨跌幅 | 腾讯API |
| `amount` | 成交金额 | 自动计算 |

---

## 4. 录入方式

### 4.1 命令行方式

```bash
# 买入记录
python -m src.decision_cli -m trade \
  --action buy \
  --code 159611 \
  --name 159611 \
  --price 1.251 \
  --quantity 4700 \
  --reason "手动买入"
```

```bash
# 卖出记录
python -m src.decision_cli -m trade \
  --action sell \
  --code 159611 \
  --price 1.200 \
  --quantity 4700 \
  --actual_pnl -239.0 \
  --reason "止损"
```

### 4.2 参数说明

| 参数 | 必填 | 说明 |
|------|:----:|------|
| `--action` | ✅ | `buy` 或 `sell` |
| `--code` | ✅ | ETF代码 |
| `--name` | ✅ | ETF名称 |
| `--price` | ✅ | 成交价格 |
| `--quantity` | ✅ | 成交数量 |
| `--reason` | ❌ | 交易原因 |
| `--actual_pnl` | ❌ | 实际盈亏（仅卖出时） |
| `--notes` | ❌ | 备注 |

---

## 5. 验证流程

### 5.1 记录后验证

```bash
# 查看最近记录
python -m src.decision_cli -m history --date 2026-06

# 导出CSV
python -m src.decision_cli -m export --filepath trades_backup.csv
```

### 5.2 验证清单

- [ ] 记录出现在 `history` 中
- [ ] 买入后 `positions` 显示持仓
- [ ] 卖出后 `positions` 移除该ETF
- [ ] 金额计算正确（price * quantity）

---

## 6. 钉钉通知（可选）

用户手动交易后，可发送钉钉通知：

```bash
# 买入通知
curl -X POST "https://oapi.dingtalk.com/robot/send" \
  -H "Content-Type: application/json" \
  -d '{
    "msgtype": "text",
    "text": {
      "content": "📝 手动买入记录\nETF: 159611\n价格: 1.251\n数量: 4700\n金额: 5881.7"
    }
  }'
```

---

## 7. 定期复盘

### 周度复盘（每周一）

```bash
python -m src.decision_cli -m eval --days 7
```

检查项：
- [ ] 本周交易笔数
- [ ] 胜率
- [ ] 总盈亏

### 月度复盘（每月1日）

```bash
python -m src.decision_cli -m eval --days 30
```

检查项：
- [ ] 本月交易笔数
- [ ] 胜率
- [ ] 盈亏比
- [ ] 最大单笔亏损
- [ ] 持仓天数分布

---

## 8. 常见问题

### Q1: 交易记录填错了怎么办？

**A**：暂不支持修改，只能删除后重新录入。删除方法：
```bash
# 编辑 etf_data_live/etf_trades.json，手动删除错误记录
```

### Q2: 忘记记录怎么办？

**A**：可以补录，但日期字段会显示为录入日期而非实际交易日期。建议尽快补录。

### Q3: 买入和卖出的数量必须一致吗？

**A**：不一定。如果分批卖出，每次卖出记录独立累积，系统会自动计算剩余持仓。

---

## 9. 相关文档

| 文档 | 说明 |
|------|------|
| `SOP_INDEX.md` | SOP索引 |
| `TRADE_RECORD_SPEC.md` | 交易记录字段规范 |
| `src/trade/tracker.py` | 交易追踪器实现 |

---

## 10. 更新记录

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v1.0 | 2026-06-02 | 初始版本 |