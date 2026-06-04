# US-019 设计文档 v1.0

## 1. 问题背景
US-018 修复了 17 处硬编码散落问题。但 SOUL 规则 9（提取常量）没有强制执行机制，
未来改参数时仍可能再次散落。需要在 commit 阶段自动拦截硬编码策略参数。

## 2. 设计清单 4 项

| # | 检查项 | 答案 |
|---|--------|------|
| 1 | 检测范围 | `src/` 下所有 .py（业务代码），但豁免 `src/constants.py` 和 `src/risk/manager.py` |
| 2 | 检测模式 | 5 个数字字面量 + 5 个字符串硬编码 |
| 3 | 误报控制 | 边界正则 `[^0-9.]` 避免误伤日期/版本号 |
| 4 | 性能 | < 1 秒（仅 grep staged files）|

## 3. 检测的硬编码模式

**数字字面量**（5 个）：
- 0.06（止损率）
- 0.10（止盈率）
- 0.94（止损价 ratio）
- 1.10（止盈价 ratio）
- 0.04（移动止盈率）

**字符串硬编码**（5 个）：
- `"-6%"` 止损
- `"+10%"` 止盈
- `"回撤4%"` 移动止盈
- `"最长15天"` 持仓周期
- `"仓位90%"` 仓位上限

## 4. 豁免清单

| 路径 | 原因 |
|------|------|
| `src/constants.py` | 单一真相源 |
| `src/risk/manager.py` | 参数化已有（保留 fallback）|
| `tests/` | 测试期望值 |
| `scripts/` | 一次性运维脚本 |
| `docs/` | 文档 |

## 5. 调研参考（SOUL 规则 13）

- **pre-commit framework** (https://pre-commit.com/) — 业界标准 hook 框架
- **项目现有 pre-commit** (`.git/hooks/pre-commit`) — 已有 5 个检查的代码风格

## 6. 自评

设计 80/100，实现 90/100。

---

*US-019 实现: docs/US-019-DESIGN.md + tests/unit/test_us019_precommit_hook.py + .git/hooks/pre-commit*
