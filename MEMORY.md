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

## 数据源状态

### 验证通过的数据源（14个接口）

| 数据源 | 接口 | 状态 |
|--------|------|------|
| 腾讯API | 实时行情、日线历史 | ✅ |
| 新浪财经API | 实时行情、30分钟K线 | ✅ |
| 天天基金 | 实时估值 | ✅ |
| BaoStock | ETF日线 | ✅ |
| AKShare 新浪 | fund_etf_hist_sina (3400条) | ✅ |
| AKShare 上交所 | fund_name_em, fund_etf_scale_sse | ✅ |
| AKShare 东财 | fund_etf_spot_em, fund_etf_fund_info_em | ⚠️ 部分 |
| **AKTools HTTP API** | **本地API（8080端口）** | ✅ **新增** |

### 待验证
- Tushare Pro（需要Token）
- 雪球API（需要Cookie）

### 不可用接口
- 雪球Xueqiu（数据格式异常）
- 百度百科（限流严重）
- 东方财富EMF（ETF不可用）

---

## 关键文件
- `src/strategy/`: 配置驱动执行框架
  - config.py: 配置类
  - scorer.py: 因子评分器
  - executor.py: 持仓执行器
  - metrics.py: 绩效计算
  - engine.py: 统一执行引擎
  - store.py: 实验存储
- `tests/strategy/`: 48个测试用例
- `src/core/selector.py`: 因子评分选择器（P0-3改造后从配置读取权重）
- `scripts/fill_etf_metadata.py`: ETF元数据填充脚本（新增）

## ETF元数据表

- **表名**: `etf_names`
- **记录数**: 1486条（全市场ETF）
- **字段**: code, name, exchange, aum, verified等
- **数据来源**: AKTools HTTP API
  - `/api/public/fund_etf_spot_em`: 实时行情
  - `/api/public/fund_etf_scale_sse`: 上交所规模（571条更新）

## 待办
1. 调仓逻辑优化（禁止频繁调仓可提升收益19%）
2. 交易记录 hold_days 字段修复
3. 第2轮实验 (Exp6-10)
4. 新因子挖掘（"只吃鱼身"原则）

---

## 项目经验教训

### 💰 数据源从0到1486的全流程复盘

#### 一、问题起点
系统只覆盖约70只ETF（硬编码列表），无法获取全市场1486只ETF信息。缺乏：
- ETF完整列表
- 实时行情
- 历史日线
- 元数据管理

#### 二、解决步骤

**Step 1: 全面调研数据源**
- 调研11个数据源（腾讯、新浪、天天基金、BaoStock、AKShare、雪球等）
- 测试17个接口：13通过，4失败
- 发现关键数据源：AKShare + AKTools

**Step 2: 部署本地HTTP API (AKTools)**
- 部署 `aktools-server/`，解决限流问题
- 本地服务 `http://127.0.0.1:8080`
- 封装为统一HTTP接口，调用间隔≥5秒

**Step 3: 验证接口可用性**
- `/api/public/fund_etf_spot_em`: 1486条全市场ETF ✅
- `/api/public/fund_etf_scale_sse`: 593条上交所规模 ✅
- `/api/public/fund_etf_hist_sina`: 单只ETF历史3400条 ✅

**Step 4: 填充元数据表**
- 编写 `scripts/fill_etf_metadata.py`
- 从AKTools API获取全市场ETF列表
- 写入 `etf_names` 表（code, name, exchange, aum）

#### 三、关键决策

| 决策 | 原因 | 结果 |
|------|------|------|
| 部署AKTools本地服务 | 解决限流问题 | 稳定调用 |
| 使用HTTP API封装 | 统一接口，隔离底层 | 便于扩展 |
| 代理只用于国外网站 | 国内网站直连更快 | 避免超时 |
| 非东财接口优先 | 东财接口不稳定 | 提高成功率 |

#### 四、技术沉淀

**数据源可靠性排序**：
```
腾讯API > 新浪API > AKShare新浪 > 天天基金 > BaoStock > AKShare东财
```

**数据路由优先级**：
- ETF实时价格 → 腾讯API → AKShare东财
- ETF历史日线 → AKShare新浪 → 腾讯API → BaoStock
- ETF净值 → 天天基金 → AKShare东财

#### 五、经验总结

1. **调研先行**：不要急着写代码，先测试所有数据源
2. **本地服务**：限流严重时，部署本地服务（aktools-server）更可靠
3. **数据契约**：每个数据源必须验证字段格式，形成文档
4. **渐进验证**：逐步验证每个接口，先小批量再全量
5. **统一入口**：通过HTTP API封装，避免直接调用底层库

#### 六、交付成果

| 成果 | 说明 |
|------|------|
| `docs/DATA_SOURCE_REFERENCE.md` | 数据源完整文档 v4.1 |
| `aktools-server/` | AKTools本地服务 |
| `scripts/fill_etf_metadata.py` | ETF元数据填充工具 |
| `etf_names` 表 | 1486条全市场ETF元数据 |
| `docs/TOOLS.md` | 工具清单（更新至2026-05-30） |

---

### 调仓陷阱
- 禁止调仓后收益反而增加19% (574.8% → 686.2%)
- 频繁调仓损害收益，应设置持仓最低天数限制

### 过拟合检验
- Train/Test收益比需 < 2
- 滚动窗口交叉验证收益比需 < 1.2
- Exp48过拟合风险最低（训练期夏普4.37, 测试期8.46）

### 技术指标无未来函数
- ADX/BB/SAR/OBV代码审查：无shift(-)引用，只使用历史数据
- 滚动窗口W4反转验证：收益比<1，证明无系统性未来偏差

### 隐私安全
- Tushare Token 必须存放在 .env 文件
- 使用 git-filter-repo 清理 Git 历史中的敏感信息