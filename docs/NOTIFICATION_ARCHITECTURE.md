# 通知系统架构设计

> 重构日期: 2026-05-25 | 状态: ✅ 已完成

## 1. 背景与目标

### 1.1 现状问题

- 两处钉钉推送入口（`notifier.py`、`decision_cli.py`）
- 三套模板，互不相关
- 维护困难，容易遗漏

### 1.2 目标

统一通知架构，解耦业务逻辑与通知渠道。

## 2. 业务场景

| 场景 | 入口 | 报告类型 |
|------|------|----------|
| 钉钉移动端 | 用户发起/定时任务 | 简版报告 |
| PC网页端 | 用户发起 | 详细报告 |
| 背后流程 | 共享 | 统一业务逻辑 |

## 3. 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                    目标架构                              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   ┌─────────────┐    ┌─────────────┐                   │
│   │ 场景适配层   │    │  场景适配层   │                   │
│   │ (钉钉/定时) │    │  (PC网页端)  │                   │
│   └──────┬──────┘    └──────┬──────┘                   │
│          │                   │                          │
│          └────────┬──────────┘                          │
│                   ▼                                     │
│          ┌────────────────┐                              │
│          │  ReportBuilder │     ← 统一报告构建           │
│          │  .build_simple()│                            │
│          │  .build_full()  │                            │
│          └────────┬───────┘                              │
│                   │                                      │
│                   ▼                                      │
│          ┌────────────────┐                              │
│          │  DingTalkSender│     ← 统一通知发送           │
│          └────────┬───────┘                              │
│                   │                                      │
│          ┌────────┴────────┐                            │
│          ▼                   ▼                           │
│   ┌─────────────┐    ┌─────────────┐                   │
│   │ 钉钉Markdown │    │ QwenPaw渠道 │                   │
│   │  (文本模板)  │    │ (qwenpaw)   │                   │
│   └─────────────┘    └─────────────┘                   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## 4. 核心模块

### 4.1 ReportBuilder

```python
class ReportBuilder:
    """统一报告构建器"""
    
    def build_simple(self, results: Dict) -> str:
        """构建简版报告（钉钉/移动端）
        
        包含: 操作、标的、价格、实时价、RSI、止盈止损
        """
        
    def build_full(self, results: Dict, report_file: str = None) -> str:
        """构建详细报告（PC端）
        
        包含: 完整分析、市场状态、持仓建议、详细指标
        """
```

### 4.2 DingTalkSender

```python
class DingTalkSender:
    """统一钉钉发送器"""
    
    def __init__(self, mode: str = 'qwenpaw'):
        """mode: 'qwenpaw' | 'webhook'"""
        
    def send(self, message: str, format: str = 'markdown') -> bool:
        """统一发送接口"""
        
    def _send_via_qwenpaw(self, message: str) -> bool:
        """通过QwenPaw渠道发送"""
        
    def _send_via_webhook(self, message: str) -> bool:
        """通过Webhook发送"""
```

### 4.3 ScenarioAdapter

```python
class ScenarioAdapter:
    """场景适配器"""
    
    def __init__(self, scenario: str = 'mobile'):
        """scenario: 'mobile' | 'pc'"""
        
    def build_and_send(self, results: Dict, report_file: str = None) -> bool:
        """根据场景构建并发送报告"""
```

## 5. 文件结构

```
src/
├── notifier.py          # 修改：保留SignalNotifier，移除钉钉实现
├── report_builder.py    # 新增：统一报告构建
├── dingtalk_sender.py   # 新增：统一钉钉发送
├── scenario_adapter.py  # 新增：场景适配
└── decision_cli.py     # 修改：调用ScenarioAdapter
```

## 6. 简版报告模板（钉钉/移动端）

```markdown
## 📈 ETF量化决策 05-25 18:20  
**🟢 买入** 515050 5GETF  
信号价: **1.101**  
实时价: **1.205** (+4.51%)  
⚠️ 偏离信号 +9.4%  
RSI14: **70.5** ✅正常  

---

🛡️ 止损: **1.046** (-5%)  
🎯 止盈: **1.189** (+8%)  
```

### 钉钉Markdown格式规范

| 功能 | 支持 | 说明 |
|------|------|------|
| ## 标题 | ✅ | 标题语法正常 |
| **加粗** | ✅ | 加粗语法正常 |
| --- 分隔线 | ✅ | 分隔线正常 |
| 列表(-) | ✅ | 列表语法正常 |
| 表格语法 | ❌ | 钉钉不支持，改用列表布局 |
| 换行 | ⚠️ | **行尾必须加2个空格** |

**关键：换行必须用2空格**

```python
# report_builder.py 中的实现
def ln(text): return text + "  " if text else text

lines = [
    ln(f"## 📈 ETF量化决策 {msg_time}"),
    ln(f"**🟢 买入** {code} {name}"),
    # ...
]
```

不加空格会合并成一行，加上2空格才能正确换行。

## 7. 详细报告模板（PC端）

包含完整分析、市场状态、持仓建议、详细指标等。

## 8. 测试计划

- [ ] 单元测试：ReportBuilder.build_simple()
- [ ] 单元测试：ReportBuilder.build_full()
- [ ] 单元测试：DingTalkSender.send()
- [ ] 单元测试：ScenarioAdapter
- [ ] 集成测试：完整流程验证

## 9. 验收标准

- [x] 两处推送入口统一到ScenarioAdapter
- [x] 简版/详细报告模板正确
- [x] QwenPaw渠道正常工作
- [x] 所有测试通过

### 实现记录

| 日期 | 提交 | 变更 |
|------|------|------|
| 2026-05-25 | `7bba878` | 新增report_builder.py, dingtalk_sender.py, scenario_adapter.py |
| 2026-05-25 | `cd39fcb` | decision_cli.py使用ScenarioAdapter |
| 2026-05-25 | `533c0d0` | 简化notifier.py，移除钉钉发送逻辑 |
| 2026-05-25 | `4b0b3d5` | 新增通知系统模块单元测试（15个测试通过） |
| 2026-05-25 | `2306af4` | **修复钉钉换行问题**：行尾加2空格，修复相对导入 |
| 2026-05-25 | `0c7ce1b` | 更新文档：MEMORY.md、memory/2026-05-25.md |

---

*设计版本: v1.1 | 日期: 2026-05-25*
