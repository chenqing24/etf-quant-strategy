# 数据质量监控设计

**日期**: 2026-05-27
**状态**: 设计中

---

## 背景

当前数据质量验证主要依靠：
1. 开发阶段的测试用例（一次性）
2. 手动交叉验证（偶尔）

需要建立**自动化的数据质量监控机制**，确保数据长期准确。

---

## 监控目标

1. **数据完整性**：每周验证数据行数、日期范围
2. **数据准确性**：每周抽查3只ETF的字段约束
3. **数据新鲜度**：每日检查数据是否过期
4. **异常告警**：发现异常时通过钉钉告警

---

## 监控机制

### 1. 每日检查（收盘后）

```python
# scripts/daily_data_check.py
def daily_check():
    """每日数据健康检查"""
    issues = []
    
    # 1. 数据新鲜度检查
    latest_date = get_latest_date('510300')
    if is_stale(latest_date, days=2):
        issues.append(f"数据过期: {latest_date}")
    
    # 2. ETF数量检查
    etf_count = get_etf_count()
    if etf_count < 60:
        issues.append(f"ETF数量不足: {etf_count}")
    
    # 3. 数据行数抽查
    for code in random.sample(all_codes, 5):
        row_count = get_row_count(code)
        if row_count < 500:  # 至少2年数据
            issues.append(f"{code}数据不足: {row_count}行")
    
    return issues
```

### 2. 每周深度验证

```python
# scripts/weekly_data_validation.py
def weekly_validation():
    """每周数据质量深度验证"""
    results = {
        'passed': [],
        'failed': []
    }
    
    # 随机抽查10只ETF
    sample_codes = random.sample(all_codes, 10)
    
    for code in sample_codes:
        df = load_etf(code)
        
        # 字段约束验证
        if not all(df['high'] >= df['close']):
            results['failed'].append(f"{code}: high < close")
        
        if not all(df['low'] <= df['close']):
            results['failed'].append(f"{code}: low > close")
        
        # 价格异常检测
        if has_outliers(df['close']):
            results['failed'].append(f"{code}: 价格异常")
    
    return results
```

### 3. 钉钉告警

```python
def send_alert(issues):
    """发送数据异常告警"""
    if not issues:
        return
    
    message = "⚠️ 数据质量告警\n\n"
    for issue in issues:
        message += f"- {issue}\n"
    
    send_dingtalk(message)
```

---

## 监控日程

| 时间 | 任务 | 执行 |
|------|------|------|
| 每日收盘后 | 数据新鲜度检查 | cron |
| 每周一 | 深度验证 | cron |
| 每月1日 | 全面数据审计 | 手动 |

---

## 指标定义

### 数据质量评分

| 指标 | 计算方式 | 目标 |
|------|----------|------|
| 完整性 | ETF数量 / 目标数量 | ≥95% |
| 新鲜度 | 最新日期距今天数 | ≤2天 |
| 准确性 | 字段约束通过率 | 100% |
| 连续性 | 日期无断层率 | ≥99% |

---

## 阈值配置

```python
# data_quality_config.py
THRESHOLDS = {
    'min_etf_count': 60,           # 最少ETF数量
    'max_data_age': 2,             # 最大数据天数
    'min_rows_per_etf': 500,       # 每只ETF最少行数
    'outlier_threshold': 0.1,       # 价格异常阈值(10%)
    'alert_repeat_interval': 3600,  # 告警重复间隔(1小时)
}
```

---

## 待实现

- [ ] scripts/daily_data_check.py
- [ ] scripts/weekly_data_validation.py
- [ ] 钉钉告警集成
- [ ] cron配置
- [ ] 告警历史记录