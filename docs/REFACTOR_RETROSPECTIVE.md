# 复盘记录 - 2026-05-27 硬编码问题发现与修复

## 问题发现

### 触发点
运行 `python -m src.cli.decision -m eval` 时报错：
```
ValueError: max() arg is an empty sequence
```

### 根因
`ETFReportGenerator` 默认路径指向不存在的 `../etf_data_50`，而实际数据在 `etf_data_live`。

### 同类问题
扫描发现整个代码库存在 **29处硬编码**：
| 类别 | 数量 |
|------|------|
| 数据目录 | 多处 |
| API地址 | 13处 |
| 超时时间 | 13处 |
| 数据库名 | 3处 |

---

## 修复方案

### 1. 建立常量中心
创建 `src/constants.py`，统一管理所有配置值：
```python
DATA_DIR = 'etf_data_live'
DB_NAME = 'etf.db'
TENCENT_BASE_URL = 'https://...'
HTTP_TIMEOUT_SHORT = 10
```

### 2. 重构受影响模块
| 文件 | 修复内容 |
|------|----------|
| router.py | API地址 → 常量 |
| fetcher.py | BASE_URL + 超时 → 常量 |
| facade.py | DB_NAME → 常量 |
| loader.py | DB_NAME → 常量 |
| tracker.py | 文件名 + URL + 超时 → 常量 |
| validator.py | URL + 超时 → 常量 |
| dingtalk.py | 超时 → 常量 |
| etf_pool_updater.py | 超时 → 常量 |

### 3. 建立防护机制
新增 `tests/test_data_path_consistency.py`：
- 检测默认路径是否使用 `DATA_DIR` 常量
- 扫描所有模块，禁止硬编码废弃路径
- 每次 `pytest` 自动运行

---

## 经验教训

### 1. 硬编码是技术债
- **定义**: 多个地方使用相同的值，但未提取为常量
- **问题**: 修改时容易遗漏，导致不一致
- **预防**: 首次出现就应提取为常量

### 2. 测试覆盖不足
- `test_19_report_generator` 被标记 skip，未暴露问题
- **教训**: skip 应是临时的，不应长期存在

### 3. 路径配置混乱
- `etf_data_50` 和 `etf_data_live` 两个目录并存
- **教训**: 目录命名应统一，避免混淆

### 4. 重构需要回归测试
- 大规模重构后必须运行完整测试套件
- **流程**: 改代码 → 跑测试 → 验证 → 提交

---

## 流程规范（更新）

### 新增：硬编码检查清单
```
□ 是否使用 DATA_DIR 常量代替 'etf_data_*'
□ API地址是否使用 constants.py 中的常量
□ 超时配置是否使用 HTTP_TIMEOUT_* 常量
□ 数据库/文件名是否使用 DB_NAME/TRADES_FILE 常量
```

### 新增：重构前检查
```
□ 已有测试覆盖变更点？
□ 测试结果已保存（对比用）？
□ 回归测试已通过？
```

---

## 文件变更统计

| 指标 | 数值 |
|------|------|
| 新增文件 | 2个 |
| 重构文件 | 8个 |
| 测试用例 | +7个 |
| Git提交 | 3个 |
| 测试通过 | 158 passed |

---

## 下次预防措施

1. **Code Review**: 硬编码必须拒绝合并
2. **CI检查**: `test_data_path_consistency.py` 作为强制检查
3. **文档**: `constants.py` 作为唯一配置源