```yaml
---
file: SOP_04_DATA_SOURCE.md
purpose: 接入新数据源（调研→验证→部署→测试→文档）
used_by:
  - 数据采集任务
  - 新API验证
status: active
last_review: 2026-06-08
review_interval: weekly
---
```

# SOP-04: 数据源接入与验证标准流程

> 来源: DATA_SOURCE_REFERENCE.md / 架构设计经验
> 版本: 1.0 | 创建: 2026-05-31

---

## 一、流程概览

```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1: 数据源调研 → Phase 2: 接口验证   → Phase 3: 文档归档   │
│  测试候选数据源     验证字段格式+限速       写入参考文档         │
└─────────────────────────────────────────────────────────────────┘
            ↓                   ↓                   ↓
┌─────────────────────────────────────────────────────────────────┐
│  Phase 4: 部署配置   → Phase 5: 集成测试                       │
│  本地服务+限流配置    小批量→全量验证                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、网络访问规则（强制）

| 类型 | 数据源 | 访问方式 | 示例 |
|------|--------|----------|------|
| **✅ 国内** | 腾讯、新浪、天天基金、东方财富、百度百科 | 直接访问 | `https://qt.gtimg.cn/...` |
| **❌ 国外** | GitHub、官方文档（英文）、PyPI备用 | 必须走代理 | `socks5://127.0.0.1:1080` |

**代理配置**：
```bash
# 终端代理
export http_proxy=socks5://127.0.0.1:1080
export https_proxy=socks5://127.0.0.1:1080

# Python requests
proxies = {
    'http': 'socks5://127.0.0.1:1080',
    'https': 'socks5://127.0.0.1:1080'
}
```

---

## 三、数据源可靠性排序

| 优先级 | 数据源 | 说明 |
|:------:|--------|------|
| **1** | 腾讯API | 实时价格、日线数据，⭐⭐⭐⭐⭐ |
| **2** | 新浪API | 小时线、实时备源，⭐⭐⭐⭐ |
| **3** | 天天基金 | ETF基本信息、净值，⭐⭐⭐⭐ |
| **4** | BaoStock | ETF/股票日线，⭐⭐⭐⭐ |
| **5** | AKShare新浪接口 | ETF历史日线，⭐⭐⭐⭐ |
| **6** | AKTools本地API | 通过本地服务调用akshare，⭐⭐⭐⭐ |
| **7** | AKShare东财接口 | ETF实时/净值（部分不可用），⭐⭐⭐ |

---

## 四、限速规则（强制）

| 数据源 | 最小间隔 | 最大间隔 | 超过后果 |
|--------|:--------:|:--------:|----------|
| 腾讯API | 2秒 | 5秒 | IP被封 |
| 新浪API | 2秒 | 5秒 | 返回空数据 |
| 天天基金 | 3秒 | 6秒 | 限流 |
| **AKTools** | **5秒** | **10秒** | **拒绝服务** |
| AKShare东财 | 5秒 | 10秒 | 返回错误 |

**实现示例**：
```python
import time
import random

def fetch_with_limit(data_source: str, func):
    """带限流的获取函数"""
    min_interval = {
        'tencent': 2,
        'sina': 2,
        'tiantian': 3,
        'aktools': 5,
        'akshare_em': 5
    }.get(data_source, 5)
    
    interval = min_interval + random.uniform(0, 1)
    time.sleep(interval)
    return func()
```

---

## 五、不可用接口清单

| 接口 | 原因 | 替代方案 |
|------|------|----------|
| 雪球Xueqiu | 数据格式异常 | 无需替代 |
| 百度百科 | 限流严重 | 无需替代 |
| 东方财富EMF | ETF不可用 | AKShare东财 |
| AKShare东财fund_etf_hist_em | 不可用 | AKShare新浪 |

---

## 六、Phase 1: 数据源调研

### 6.1 调研清单

| # | 检查项 | 方法 | 记录 |
|---|--------|------|------|
| 1 | 多数据源交叉验证 | 对比不同来源的同一数据 | 差异百分比 |
| 2 | 字段类型验证 | 确认OHLCV顺序 | 字段映射表 |
| 3 | 异常值检测 | 价格=0, 成交量<0 | 异常记录 |
| 4 | 日期连续性 | 节假日处理 | 补齐/标记 |
| 5 | 限速测试 | 测试不同间隔的效果 | 最小可用间隔 |

### 6.2 调研记录模板

```markdown
# 数据源调研报告 - [名称]

## 1. 接口信息
| 项目 | 值 |
|------|---|
| 接口名称 | xxx |
| HTTP路径 | /api/xxx |
| 官方文档 | url |
| 验证状态 | ✅/⚠️/❌ |

## 2. 调用示例
```python
# 示例代码
```

## 3. 返回格式
| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| field1 | string | 日期 YYYY-MM-DD | 实测 |

## 4. 限速测试
| 间隔 | 结果 |
|------|------|
| 2秒 | 正常 |
| 1秒 | 限流 |

## 5. 验证结论
- [ ] 接口可用
- [ ] 数据准确
- [ ] 建议使用场景
```

---

## 七、Phase 2: 接口验证

### 7.1 必做验证项

| # | 验证项 | 方法 | 通过标准 |
|---|--------|------|----------|
| 1 | 返回格式 | 调用接口，解析JSON | 无报错 |
| 2 | 字段数量 | 检查返回字段数 | 与文档一致 |
| 3 | 数据类型 | 检查字段类型 | number/string正确 |
| 4 | 日期格式 | 检查日期字段 | YYYY-MM-DD |
| 5 | 价格验证 | 验证HIGH >= LOW | true |
| 6 | 交叉验证 | 对比两个数据源 | 差异 < 0.5% |

### 7.2 验证脚本模板

```python
import requests
import json

def verify_data_source(name: str, url: str, expected_fields: list):
    """验证数据源接口"""
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        # 1. 检查返回格式
        assert isinstance(data, (list, dict)), "返回类型错误"
        
        # 2. 检查字段
        if isinstance(data, list):
            first_item = data[0]
        else:
            first_item = data
        
        for field in expected_fields:
            assert field in first_item, f"缺少字段: {field}"
        
        # 3. 交叉验证（可选）
        # compare_with_another_source(data)
        
        print(f"✅ {name} 验证通过")
        return True
    except Exception as e:
        print(f"❌ {name} 验证失败: {e}")
        return False
```

---

## 八、Phase 3: 文档归档

### 8.1 文档要求

接入新数据源后，必须更新 `docs/DATA_SOURCE_REFERENCE.md`：

```markdown
## [数据源名称] ✅ 已验证 / ⚠️ 部分验证 / ❌ 不可用

### 接口列表

| 接口 | 用途 | 参数 | 返回字段 | 限速 | 状态 |
|------|------|------|----------|------|------|
| name | desc | params | fields | X秒 | ✅ |

### 调用示例

```python
# 示例代码
```

### 返回字段

| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| field | string | desc | ✅实测 / ✅官方 |
```

### 8.2 数据字典模板

```markdown
## 数据字段映射

### 统一格式 → 原始格式

| 统一字段 | 腾讯实时 | 腾讯日线 | 新浪实时 | AKShare |
|----------|---------|----------|----------|---------|
| code | 索引2 | - | 索引2 | 代码字段 |
| date | - | 索引0 | - | date |
| open | - | 索引1 | 索引1 | open |
| close | 索引3 | 索引2 | 索引3 | close |
| volume | 索引6 | 索引5 | 索引6 | volume |
```

---

## 九、Phase 4: 部署配置

### 9.1 AKTools本地部署

**适用场景**：限流严重时，通过本地服务缓存和合并请求

**部署步骤**：
```bash
# 1. 启动服务
cd aktools-server && python -m aktools

# 2. 验证服务
curl "http://127.0.0.1:8080/version"

# 3. 调用接口
curl "http://127.0.0.1:8080/api/public/fund_etf_spot_em"
```

**限速规则**：
| 接口 | 建议间隔 |
|------|---------|
| 轻量接口（如版本） | 无限制 |
| ETF历史日线 | 5秒+ |
| ETF实时行情 | 10秒+ |

### 9.2 路由配置

```python
# src/data/router.py

DATA_SOURCE_PRIORITY = {
    'realtime_price': ['tencent', 'akshare_em', 'sina', 'last_close'],
    'daily_history': ['akshare_sina', 'tencent', 'baostock'],
    'fund_nav': ['tiantian', 'akshare_em'],
    'minute_kline': ['sina_scale30']
}

def fetch_data(data_type: str, code: str):
    """按优先级获取数据"""
    for source in DATA_SOURCE_PRIORITY.get(data_type, []):
        try:
            data = fetch_from_source(source, code)
            if data:
                return data
        except Exception as e:
            log.warning(f"{source} failed: {e}")
            continue
    return None  # 所有源都失败
```

---

## 十、Phase 5: 集成测试

### 10.1 测试计划

| 阶段 | 数量 | 说明 |
|------|------|------|
| 小批量 | 3-5只ETF | 验证基本功能 |
| 中批量 | 20-30只ETF | 验证限流和稳定性 |
| 全量 | 所有ETF | 验证完整数据 |

### 10.2 测试用例

```python
def test_fetch_etf_realtime():
    """测试获取ETF实时价格"""
    codes = ['510300', '159919', '515650']
    for code in codes:
        data = fetch_realtime(code)
        assert data['close'] > 0
        assert data['prev_close'] > 0
        assert abs(data['change_pct']) < 10  # 涨跌幅不超过10%

def test_fetch_etf_history():
    """测试获取ETF历史日线"""
    codes = ['510300', '159919', '515650']
    for code in codes:
        data = fetch_history(code, count=100)
        assert len(data) == 100
        assert all(row['close'] > 0 for row in data)
        # 验证日期连续性
        dates = [row['date'] for row in data]
        assert dates == sorted(dates)

def test_fetch_multiple():
    """测试批量获取"""
    codes = load_etf_pool()
    results = []
    for code in codes:
        data = fetch_realtime(code)
        results.append(data)
    assert len(results) == len(codes)
```

---

## 十一、版本对照表

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-05-31 | 初始版本 |

---

## 附录：数据源速查表

| 数据源 | URL/接口 | 限速 | 字段数 | 状态 |
|--------|----------|:----:|:------:|------|
| 腾讯实时 | `qt.gtimg.cn/q={code}` | 2-5秒 | 88 | ✅ |
| 腾讯日线 | `web.ifzq.gtimg.cn/.../param={code},day` | 2-5秒 | 6 | ✅ |
| 新浪实时 | `hq.sinajs.cn/list={code}` | 2-5秒 | 34 | ✅ |
| 新浪K线 | `quotes.sina.cn/cn/api/json_v2.php/...?scale=30` | 2-5秒 | 7 | ✅ |
| 天天基金估值 | `fundgz.1234567.com.cn/js/{code}.js` | 3-6秒 | 7 | ✅ |
| BaoStock | `bs.query_history_k_data_plus()` | 无 | 6 | ✅ |
| AKShare新浪 | `ak.fund_etf_hist_sina(symbol)` | 5秒 | 7 | ✅ |
| AKShare东财 | `ak.fund_etf_spot_em()` | 5秒 | 30+ | ⚠️ |
| AKTools HTTP | `http://127.0.0.1:8080/api/...` | 5秒 | - | ✅ |

---

*SOP版本: 1.0 | 创建: 2026-05-31*
*来源: DATA_SOURCE_REFERENCE.md + 架构设计经验*