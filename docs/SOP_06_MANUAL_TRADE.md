# SOP-06: 用户手动交易记录

**版本**：v2.0  
**作者**：福猫管家  
**创建日期**：2026-06-02  
**更新日期**：2026-06-02（v2.0 增强）  
**参考来源**：
- [mransbro/tradingjournal](https://github.com/mransbro/tradingjournal) — 基础交易字段
- [leionion/ai-trading-journal-audit-tool](https://github.com/leionion/ai-trading-journal-audit-tool) — NormalizedTrade schema、session_analyzer.py
- [DawnSyndrome/automated-trading-journal](https://github.com/DawnSyndrome/automated-trading-journal) — 情绪追踪

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
| `emotion` | str | 交易情绪 | `calm` |
| `session` | str | 交易时段 | `D` |

### 自动填充字段（系统完成）

| 字段 | 说明 | 来源 |
|------|------|------|
| `realtime_price` | 记录时的实时价格 | 腾讯API |
| `price_deviation` | 偏差率：(实时价-信号价)/信号价*100 | 自动计算 |
| `rsi_14` | RSI(14) 指标值 | 历史数据 |
| `day_change_pct` | 当日涨跌幅 | 腾讯API |
| `amount` | 成交金额 | 自动计算 |

### 信号快照字段（来源：参考 leionion/ai-trading-journal-audit-tool）

| 字段 | 说明 | 示例 |
|------|------|------|
| `signal_time` | 信号发出时间 (YYYY-MM-DD HH:MM) | `2026-06-02 10:30` |
| `signal_price` | 信号发出时的价格 | `1.197` |
| `signal_rsi` | 信号时的RSI(14) | `50.6` |
| `signal_adx` | 信号时的ADX(14) | `32.3` |
| `signal_score` | 信号评分 | `6` |

### 情绪字段（来源：参考 DawnSyndrome/automated-trading-journal）

| 选项 | 说明 | 场景 |
|------|------|------|
| `calm` | 冷静 - 按计划执行 | ✅ 最佳状态 |
| `euphoria` | 亢奋 - 追涨杀跌 | ❌ 风险信号 |
| `fear` | 恐惧 - 恐慌止损 | ❌ 风险信号 |
| `fomo` | FOMO - 怕错过行情 | ❌ 风险信号 |
| `regret` | 后悔 - 犹豫后买入 | ❌ 风险信号 |

### 时段字段（来源：参考 leionion/ai-trading-journal-audit-tool/session_analyzer.py）

| 选项 | 时间范围 | 说明 |
|------|----------|------|
| `A` | 00:00-04:00 UTC | 亚洲尾盘 |
| `B` | 04:00-08:00 UTC | 欧洲早盘 |
| `C` | 08:00-12:00 UTC | 欧洲午盘 |
| `D` | 12:00-16:00 UTC | 美洲早盘 |
| `E` | 16:00-20:00 UTC | 美洲午盘 |
| `F` | 20:00-24:00 UTC | 美洲尾盘 |

**注意**：时段可不指定，系统自动从 `trade_time` 推断。

---

## 4. 录入方式

### 4.1 命令行方式

```bash
# 买入记录（SOP-06 v2.0）
python -m src.cli.decision -m trade \
  --action buy \
  --code 515050 \
  --name "通信ETF华夏" \
  --price 1.197 \
  --quantity 2600 \
  --reason "MA20突破" \
  --trade_time "2026-06-02 10:40" \
  --signal_time "2026-06-02 10:30" \
  --signal_price 1.197 \
  --signal_rsi 50.6 \
  --signal_adx 32.3 \
  --signal_score 6 \
  --emotion calm \
  --session D
```

```bash
# 卖出记录
python -m src.cli.decision -m trade \
  --action sell \
  --code 515050 \
  --price 1.200 \
  --quantity 2600 \
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
| `--trade_time` | ❌ | 实际成交时间（自动推断 session） |
| `--signal_time` | ❌ | 信号发出时间 |
| `--signal_price` | ❌ | 信号价格 |
| `--signal_rsi` | ❌ | 信号RSI(14) |
| `--signal_adx` | ❌ | 信号ADX(14) |
| `--signal_score` | ❌ | 信号评分 |
| `--emotion` | ❌ | 交易情绪（calm/euphoria/fear/fomo/regret） |
| `--session` | ❌ | 交易时段（A/B/C/D/E/F，自动推断） |

---

## 5. 验证流程

### 5.1 记录后验证

```bash
# 查看最近记录
python -m src.cli.decision -m history --date 2026-06

# 导出CSV
python -m src.cli.decision -m export --filepath trades_backup.csv
```

### 5.2 验证清单

- [ ] 记录出现在 `history` 中
- [ ] 买入后 `positions` 显示持仓
- [ ] 卖出后 `positions` 移除该ETF
- [ ] 金额计算正确（price * quantity）
- [ ] signal_* 字段正确填充
- [ ] emotion/session 字段正确

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
      "content": "📝 手动买入记录\nETF: 515050 通信ETF华夏\n价格: 1.197\n数量: 2600\n金额: 3112.2\n情绪: calm\n时段: D"
    }
  }'
```

---

## 7. 定期复盘

### 周度复盘（每周一）

```bash
python -m src.cli.decision -m eval --days 7
```

检查项：
- [ ] 本周交易笔数
- [ ] 胜率
- [ ] 总盈亏
- [ ] 情绪分布（FOMO/regret 占比）

### 月度复盘（每月1日）

```bash
python -m src.cli.decision -m eval --days 30
```

检查项：
- [ ] 本月交易笔数
- [ ] 胜率
- [ ] 盈亏比
- [ ] 最大单笔亏损
- [ ] 持仓天数分布
- [ ] 时段分布（是否在美洲时段 E/F 亏损最多）

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

### Q4: 时段推断不准确怎么办？

**A**：手动指定 `--session D`，不依赖自动推断。

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
| v2.0 | 2026-06-02 | 增加信号快照、情绪、时段字段 |