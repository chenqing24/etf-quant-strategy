# ETF量化策略 - 工作记录

## 版本历史
- **v0.2.0**: 配置驱动执行框架完成 (2026-05-27)
  - UniversalExecutor: 统一执行引擎
  - 每日评分检查持仓、低分平仓
  - 调仓逻辑 (评分差>0.1时替换)
  - ETF筛选 (TopN=30训练期表现)
- **v0.1.0-dev**: 因子挖掘实验框架 (2026-05-27)
  - 8因子IC计算完成
  - 第1轮5个实验完成
  - 回测引擎三层解耦

## 数据状态
- **数据范围**: 2017-04-24 ~ 2026-05-27
- **有效数据**: 2023年后 (之前年份数据稀疏)
- **训练期**: 2020-01-01 ~ 2023-06-30
- **测试期**: 2023-07-01 ~ 2024-12-31

## 因子IC结果 (5日收益)
| 因子 | IC均值 | IR | 方向 |
|------|--------|------|------|
| ADX | 0.1219 | 1.28 | long |
| BB_percent | 0.0228 | 0.29 | long |
| SAR_trend | 0.0219 | 0.38 | long |
| RSI_5 | 0.0094 | 0.15 | neutral |
| DMA | -0.0148 | -0.19 | neutral |
| K | -0.0181 | -0.24 | neutral |
| DIF | -0.0209 | -0.26 | short |
| OBV_diff | -0.0281 | -0.40 | short |

## 关键文件
- `src/strategy/`: 配置驱动执行框架
  - config.py: 配置类
  - scorer.py: 因子评分器
  - executor.py: 持仓执行器
  - metrics.py: 绩效计算
  - engine.py: 统一执行引擎
  - store.py: 实验存储
- `tests/strategy/`: 48个测试用例

## 待办
1. 调仓逻辑优化
2. 第2轮实验 (Exp6-10)
3. 新因子挖掘

## Git 操作规范（2026-05-28 总结）

### 正确的 GitHub 交互流程
```bash
# 1. 配置 SOCKS5 代理（本地 1080 端口）
git config --global http.proxy "socks5://127.0.0.1:1080"
git config --global https.proxy "socks5://127.0.0.1:1080"

# 2. 先 fetch 再 push
git fetch github
git merge github/main --allow-unrelated-histories  # 首次合并需要此参数
git push github main

# 3. 不要强制推送，除非明确知道远程不需要保留历史
```

### 隐私文件处理
- .env 文件必须从 Git 历史中清除：`git filter-repo --path .env --invert-paths --force`
- 备份恢复后立即检查是否包含敏感文件

### 遇到的问题和解决方案
| 问题 | 原因 | 解决方案 |
|------|------|----------|
| git push 超时 | 直接连接 GitHub 被阻断 | 配置 SOCKS5 代理 |
| 拒绝合并无关历史 | 本地仓库和远程仓库无共同祖先 | 使用 `--allow-unrelated-histories` |
| .env 被跟踪 | 备份恢复时带入了 Git 跟踪的文件 | 从 Git 历史中删除 (`git rm --cached .env`) |