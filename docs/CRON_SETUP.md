# ETF量化决策 - Cron定时任务配置

# ============================================================
# 工作日每天下午2:30执行 (股市收市前)
# ============================================================

# 每日检查 - 每个工作日下午2:30
30 14 * * 1-5 cd /Users/qingchen/.qwenpaw/workspaces/default/etf_strategy && python -m src.decision_cli -m daily

# ============================================================
# 可选：带钉钉推送 (需要先设置webhook)
# ============================================================

# 带推送 (需要先设置环境变量或直接传入webhook)
# 30 14 * * 1-5 cd /Users/qingchen/.qwenpaw/workspaces/default/etf_strategy && python -m src.decision_cli -m daily --webhook "你的钉钉webhook" >> /tmp/etf_daily.log 2>&1

# ============================================================
# 命令行手动执行
# ============================================================

# 每日检查
python -m src.decision_cli -m daily

# 完整评估
python -m src.decision_cli -m eval

# 查看历史
python -m src.decision_cli -m history

# 绩效分析
python -m src.decision_cli -m perf

# 记录买入
python -m src.decision_cli -m trade --code 516050 --action buy --price 1.384 --quantity 13000

# 记录卖出
python -m src.decision_cli -m trade --code 516050 --action sell --price 1.420 --quantity 13000

# ============================================================
# 注意
# ============================================================
# 1. 执行前确保已进入项目目录
# 2. 首次运行会自动获取1年历史数据
# 3. 日常只增量更新最新几天数据
# 4. 查看输出: tail -f /tmp/etf_daily.log