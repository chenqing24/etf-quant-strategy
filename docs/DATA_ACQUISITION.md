# 数据采集规范

> 规范腾讯ETF数据的采集、更新、缓存机制

## 1. 概述

数据采集模块负责从腾讯财经API获取ETF实时和历史数据，是整个系统的数据源头。

```
数据采集层
    │
    ├── TencentETFetcher     # 腾讯API采集器
    ├── DataLoader           # 本地数据加载器
    └── CacheManager         # 缓存管理器
```

## 2. 腾讯API规范

### 2.1 API端点

```
https://web.ifzq.gtimg.cn/appstock/app/fqkline/get
```

### 2.2 请求参数

| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `code` | string | ETF代码（含前缀） | `sh510300` |
| `_var` | string | 回调函数名 | `kline_dayhfq` |
| `param` | string | 数据参数 | `day,,,320,qfq` |

### 2.3 响应格式

```json
kline_dayqfq={"code":0,"data":{"sh510300":{"qfqday":[["2026-05-26","4.950","4.970","4.940","4.960","12345678"]]}}}
```

**注意**：腾讯API返回带变量前缀的JSON，需要去掉`kline_dayqfq=`后再解析。

**返回字段**（可能在`qfqday`或`day`字段下）：
| 索引 | 字段 | 说明 |
|:----:|------|------|
| 0 | date | 日期 |
| 1 | open | 开盘价 |
| 2 | high | 最高价 |
| 3 | low | 最低价 |
| 4 | close | 收盘价 |
| 5 | volume | 成交量 |

### 2.4 错误处理

| 错误类型 | 处理方式 |
|----------|----------|
| 网络超时 | 重试3次，间隔1秒 |
| 数据为空 | 记录警告，返回空DataFrame |
| API异常 | 记录错误，返回空DataFrame |

## 3. 数据采集策略

### 3.1 首次采集

首次运行时，获取最近365天数据：
```python
df = fetcher.fetch_etf('sh510300', days=365)
```

### 3.2 增量更新

检查本地数据日期，只补充缺失数据：
```python
df = fetcher.update_etf('sh510300')  # 自动检测并补充
```

### 3.3 全量更新

定期执行全量采集（每月或每周）：
```python
results = fetcher.fetch_all(days=7)  # 所有ETF更新7天数据
```

### 3.4 采集限流

- 每个ETF请求间隔：**200ms**
- 避免触发API限流

## 4. 数据存储

### 4.1 目录结构

```
etf_data_live/
├── hot/                    # 热数据（近期数据）
│   └── {code}.json         # 实时/近期数据
└── cold/                   # 冷数据（历史数据）
    └── {code}.csv          # 完整历史数据
```

### 4.2 文件格式

**CSV格式**（历史数据）：
```csv
date,open,high,low,close,volume
2026-05-26,4.950,4.970,4.940,4.960,12345678
```

**JSON格式**（实时数据）：
```json
{
  "code": "510300",
  "name": "沪深300ETF",
  "price": 4.960,
  "change_pct": 0.20,
  "volume": 12345678,
  "timestamp": "2026-05-26T14:30:00"
}
```

## 5. 缓存机制

### 5.1 内存缓存

```python
# 数据fetcher内部缓存
self._cache = {}  # {code: (df, timestamp)}
CACHE_TTL = 300   # 5分钟过期
```

### 5.2 本地缓存

使用CacheManager管理本地缓存：
```python
cache = CacheManager('.cache')
df = cache.get_or_compute(
    name='etf_data',
    args={'code': '510300', 'days': 30},
    compute_fn=lambda: fetcher.fetch_etf('sh510300', days=30)
)
```

## 6. 质量检查

### 6.1 数据验证

| 检查项 | 阈值 |
|--------|------|
| 数据条数 | ≥300天（约1年） |
| 缺失值比例 | <5% |
| 异常价格 | 涨幅/跌幅 <20% |

### 6.2 过滤规则

```python
# 过滤数据不足的ETF（腾讯API只返回约365天数据）
if len(df) >= 300:
    self.data[f.stem] = df
```

## 7. 使用示例

```python
from src.data.fetcher import TencentETFetcher

# 初始化
fetcher = TencentETFetcher('etf_data_live')

# 获取单只ETF数据
df = fetcher.fetch_etf('sh510300', days=30)

# 更新所有ETF
results = fetcher.update_all(days=7)
```

## 8. 修订历史

| 日期 | 版本 | 修改内容 |
|------|------|----------|
| 2026-05-26 | 1.0 | 初始版本 |
| 2026-05-26 | 1.1 | 修复API响应格式（带前缀JSON、字段名兼容性）、数据阈值500→300 |
| 2026-05-26 | 1.2 | RSI超卖买入需MA20向上确认，防止接飞刀 |

---

### 附：RSI超卖买入需趋势确认

RSI<30时，需MA20向上确认，避免"接飞刀"。

```python
# RSI超卖需要MA20向上确认
if rsi < 30:
    ma20_up = recent['ma20'].iloc[-1] > recent['ma20'].iloc[0]
    if ma20_up:
        # 加分
    else:
        # 不加分（防止接飞刀）
```

| RSI区间 | 条件 | 说明 |
|---------|------|------|
| RSI < 30 | MA20向上 | 买入 ✅ |
| RSI < 30 | MA20向下 | 不加分（下跌趋势） |
| 30 ≤ RSI < 70 | - | 正常加分 |
| RSI ≥ 70 | - | 超买警告或扣分 |

---

**关联文档**：
- [DATA_DICTIONARY.md](./DATA_DICTIONARY.md) - 字段定义
- [ARCHITECTURE.md](./ARCHITECTURE.md) - 热冷数据分离架构