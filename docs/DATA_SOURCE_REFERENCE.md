# ETF量化系统 - 数据源完整文档 v4.0

> 更新: 2026-05-30 | 基于全面测试验证

---

## 一、概述

本文档描述ETF量化系统使用的所有外部数据源、接口格式、字段说明和使用约束。

**验证状态说明**：
- ✅ 已验证：接口测试通过，数据可用
- ⚠️ 部分验证：部分接口可用
- ❌ 不可用：接口不稳定或被限制

---

### 1.1 数据源总览

| # | 数据源 | 用途 | 可靠性 | 限速 | 官方文档 | 验证状态 |
|---|--------|------|--------|------|----------|----------|
| 1 | 腾讯行情API | 实时价格、日线数据 | ⭐⭐⭐⭐⭐ | 2-5秒 | ❌ 无 | ✅ 已验证 |
| 2 | 新浪财经API | 小时线、实时备源 | ⭐⭐⭐⭐ | 2-5秒 | ❌ 无 | ✅ 已验证 |
| 3 | 天天基金网 | ETF基本信息、净值 | ⭐⭐⭐⭐ | 3-6秒 | ❌ 无 | ✅ 已验证 |
| 4 | BaoStock | ETF/股票日线 | ⭐⭐⭐⭐ | 无严格 | ✅ 有 | ✅ 已验证 |
| 5 | AKShare 新浪接口 | ETF历史日线 | ⭐⭐⭐⭐ | 5秒 | ✅ 有 | ✅ 已验证 |
| 6 | AKShare 东财接口 | ETF实时/净值 | ⭐⭐⭐⭐ | 5秒 | ✅ 有 | ⚠️ 部分验证 |
| 7 | AKShare 上交所接口 | ETF规模 | ⭐⭐⭐ | 5秒 | ✅ 有 | ✅ 已验证 |
| 8 | **AKTools HTTP API** | **本地HTTP API（通过akshare调用）** | ⭐⭐⭐⭐ | 5秒 | ✅ 有 | ✅ **已验证** |
| 9 | Tushare Pro | 日线备源 | ⭐⭐⭐⭐ | 有限制 | ✅ 有 | ⚠️ 待验证 |
| 10 | 雪球Xueqiu | 基金详情 | ⭐⭐⭐⭐ | 需Cookie | ❌ 无 | ❌ 不可用 |
| 11 | 百度百科 | ETF基础知识 | ⭐⭐ | 限流 | ✅ 有 | ⚠️ 限流严重 |

---

## 二、腾讯行情API ✅ 已验证

### 2.1 接口列表

| 接口 | 用途 | 参数 | 返回字段 | 限速 |
|------|------|------|----------|------|
| 实时行情 | 实时价格 | `q=sz159919` | 88字段 | 2-5秒 |
| 日线历史 | 历史日线 | `param=sz159919,day,,,320,qfq` | date,open,high,low,close,volume | 2-5秒 |

### 2.2 实时行情

**URL**: `https://qt.gtimg.cn/q={prefix}{code}`

**示例**:
```bash
curl "https://qt.gtimg.cn/q=sz159919"
```

**返回字段**:
| 索引 | 字段名 | 说明 | 来源 |
|------|--------|------|------|
| 0 | market_status | 市场状态（51=正常） | ✅实测 |
| 1 | name | ETF名称 | ✅实测 |
| 2 | code | 代码 | ✅实测 |
| 3 | price | 当前价格 | ✅实测 |
| 4 | prev_close | 昨收价 | ✅实测 |
| 5 | high | 今日最高 | ✅实测 |
| 6 | volume | 成交量 | ✅实测 |
| 41 | day_high | 日最高 | ✅实测 |
| 42 | day_low | 日最低 | ✅实测 |
| 32 | change_pct | 涨跌幅(%) | ✅实测 |

### 2.3 日线历史

**URL**: `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param={prefix}{code},day,,,{count},qfq`

**示例**:
```bash
curl "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param=sz159919,day,,,5,qfq"
```

**返回字段** (qfqday数组):
| 索引 | 字段名 | 说明 | 来源 |
|------|--------|------|------|------|
| 0 | date | 日期 YYYY-MM-DD | ✅实测 |
| 1 | open | 开盘价 | ✅实测 |
| 2 | close | 收盘价 | ✅实测 |
| 3 | high | 最高价 | ✅实测 |
| 4 | low | 最低价 | ✅实测 |
| 5 | volume | 成交量 | ✅实测 |

---

## 三、新浪财经API ✅ 已验证

### 3.1 接口列表

| 接口 | 用途 | 参数 | 返回字段 | 限速 |
|------|------|------|----------|------|
| 实时行情 | 实时价格 | `list=sz159919` (需Referer) | 34字段 | 2-5秒 |
| 30分钟K线 | 分钟线 | `symbol=sz159919&scale=30&datalen=5` | day,open,high,low,close,volume,amount | 2-5秒 |

### 3.2 实时行情

**URL**: `https://hq.sinajs.cn/list={prefix}{code}`
**Header**: `Referer: https://finance.sina.com.cn/`

**示例**:
```bash
curl -H "Referer: https://finance.sina.com.cn" "https://hq.sinajs.cn/list=sz159919"
```

**返回字段**:
| 索引 | 字段名 | 说明 | 来源 |
|------|--------|------|------|
| 0 | name | 名称（无ETF后缀） | ✅实测 |
| 1 | open | 开盘价 | ✅实测 |
| 2 | prev_close | 昨收价 | ✅实测 |
| 3 | price | 当前价 | ✅实测 |
| 4 | high | 今日最高 | ✅实测 |
| 5 | low | 今日最低 | ✅实测 |
| 6 | volume | 成交量 | ✅实测 |
| 7 | amount | 成交额 | ✅实测 |

### 3.3 30分钟K线

**URL**: `https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol={prefix}{code}&scale=30&ma=no&datalen={count}`

**示例**:
```bash
curl "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol=sz159919&scale=30&ma=no&datalen=5"
```

**返回字段** (JSON数组):
| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| day | string | 时间戳 | ✅实测 |
| open | float | 开盘价 | ✅实测 |
| high | float | 最高价 | ✅实测 |
| low | float | 最低价 | ✅实测 |
| close | float | 收盘价 | ✅实测 |
| volume | int | 成交量 | ✅实测 |
| amount | float | 成交额 | ✅实测 |

---

## 四、天天基金网 ✅ 已验证

### 4.1 接口列表

| 接口 | 用途 | 参数 | 返回字段 | 限速 | 状态 |
|------|------|------|----------|------|------|
| 实时估值 | 盘中净值 | `/js/{code}.js?rt={timestamp}` | fundcode,name,jzrq,dwjz,gsz,gszzl,gztime | 3-6秒 | ✅ |
| 历史净值 | 收盘净值 | `/f10/lsjz?fundCode={code}` | FSRQ,DWJZ,LJJZ,JZZZL,SGZT,SHZT | 3-6秒 | ✅ |

### 4.2 实时估值

**URL**: `https://fundgz.1234567.com.cn/js/{code}.js?rt={timestamp}`

**示例**:
```bash
curl "https://fundgz.1234567.com.cn/js/159919.js?rt=$(date +%s)"
```

**返回格式**: `jsonpgz({...})`

**返回字段**:
| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| fundcode | string | ETF代码 | ✅实测 |
| name | string | ETF名称 | ✅实测 |
| jzrq | string | 净值日期 | ✅实测 |
| dnjz | float | 单位净值 | ✅实测 |
| gsz | float | 估算净值 | ✅实测 |
| gszzl | float | 估算涨跌幅(%) | ✅实测 |
| gztime | string | 估算时间 | ✅实测 |

### 4.3 历史净值

**URL**: `https://api.fund.eastmoney.com/f10/lsjz?callback=jQuery&fundCode={code}&pageIndex=1&pageSize={count}`

**示例**:
```bash
curl "https://api.fund.eastmoney.com/f10/lsjz?callback=jQuery&fundCode=159919&pageIndex=1&pageSize=5"
```

**返回字段**:
| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| FSRQ | string | 日期 YYYY-MM-DD | ✅实测 |
| DWJZ | float | 单位净值 | ✅实测 |
| LJJZ | float | 累计净值 | ✅实测 |
| JZZZL | float | 日涨跌幅(%) | ✅实测 |
| SGZT | string | 申购状态 | ✅实测 |
| SHZT | string | 赎回状态 | ✅实测 |

---

## 五、BaoStock ✅ 已验证

### 5.1 日线数据接口

**Python示例**:
```python
import baostock as bs

bs.login()
rs = bs.query_history_k_data_plus(
    'sz.159919',
    'date,open,high,low,close,volume',
    start_date='2026-01-01',
    end_date='2026-05-30',
    frequency='d'
)
while rs.error_code == '0' and rs.next():
    print(rs.get_row_data())
bs.logout()
```

**返回字段**:
| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| date | string | 日期 YYYY-MM-DD | ✅官方文档 |
| open | float | 开盘价 | ✅官方文档 |
| high | float | 最高价 | ✅官方文档 |
| low | float | 最低价 | ✅官方文档 |
| close | float | 收盘价 | ✅官方文档 |
| volume | float | 成交量 | ✅官方文档 |

### 5.2 代码格式

| 市场 | 前缀 | 示例 |
|------|------|------|
| 深圳 | `sz.` | `sz.159919` |
| 上海 | `sh.` | `sh.510300` |

---

## 六、AKShare 新浪接口 ✅ 已验证（非东财）

### 6.1 接口列表

| 接口 | 用途 | 参数 | 返回字段 | 限速 | 状态 |
|------|------|------|----------|------|------|
| `fund_etf_hist_sina` | ETF历史日线 | symbol=`sz159919` | date,open,high,low,close,volume,amount | 5秒 | ✅ |
| `fund_etf_category_sina` | ETF/LOF分类 | 无参数 | 代码,名称,最新价,涨跌额,涨跌幅等 | 5秒 | ✅ |
| `fund_etf_dividend_sina` | ETF分红历史 | symbol=`sz159919` | 日期,累计分红 | 5秒 | ✅ |

### 6.2 新浪ETF历史日线（推荐）

**Python接口**: `fund_etf_hist_sina(symbol)`

**示例**:
```python
import akshare as ak

# 获取沪深300ETF嘉实历史日线
df = ak.fund_etf_hist_sina(symbol="sz159919")
# 返回约3400条，从2012年开始
```

**返回字段**:
| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| date | string | YYYY-MM-DD | ✅官方文档 |
| open | float | 开盘价 | ✅官方文档 |
| high | float | 最高价 | ✅官方文档 |
| low | float | 最低价 | ✅官方文档 |
| close | float | 收盘价 | ✅官方文档 |
| volume | int | 成交量 | ✅官方文档 |
| amount | float | 成交额 | ✅官方文档 |

### 6.3 新浪ETF分类

**Python接口**: `fund_etf_category_sina()`

**示例**:
```python
df = ak.fund_etf_category_sina()  # 382条ETF/LOF
df[df['名称'].str.contains('沪深300')]
```

**返回字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| 代码 | string | ETF代码（含sz/sh前缀） |
| 名称 | string | ETF名称 |
| 最新价 | float | 当前价格 |
| 涨跌额 | float | 涨跌额 |
| 涨跌幅 | float | 涨跌幅(%) |
| 买入/卖出 | float | 买卖价 |
| 昨收/今开 | float | 昨收价/今开盘 |
| 最高/最低 | float | 日最高/最低价 |
| 成交量/成交额 | float | 成交数量/金额 |

---

## 七、AKShare 东财接口 ⚠️ 部分验证

### 7.1 接口列表

| 接口 | 用途 | 参数 | 返回字段 | 限速 | 状态 |
|------|------|------|----------|------|------|
| `fund_etf_spot_em` | ETF实时行情 | 无参数 | 代码,名称,IOPV,涨跌幅,成交量等30+字段 | 5秒 | ✅ |
| `fund_etf_fund_info_em` | ETF净值详情 | fund=`159919`, start_date, end_date | 净值日期,单位净值,累计净值,日增长率 | 5秒 | ✅ |
| `fund_etf_hist_em` | ETF历史日线 | symbol,period,start_date,end_date,adjust | 日期,开盘,收盘,最高,最低,成交量等 | 5秒 | ❌ |

### 7.2 ETF实时行情

**Python接口**: `fund_etf_spot_em()`

**示例**:
```python
df = ak.fund_etf_spot_em()  # 1486条全市场ETF
```

**返回字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| 代码 | string | ETF代码 |
| 名称 | string | ETF名称 |
| 最新价 | float | 当前价格 |
| IOPV实时估值 | float | IOPV净值估算 |
| 涨跌幅 | float | 涨跌幅(%) |
| 成交量 | float | 成交量 |
| 成交额 | float | 成交额 |
| 数据日期 | string | 更新日期 |

### 7.3 ETF净值详情

**Python接口**: `fund_etf_fund_info_em(fund, start_date, end_date)`

**示例**:
```python
df = ak.fund_etf_fund_info_em(fund="159919", start_date="20260101", end_date="20260530")
```

**返回字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| 净值日期 | string | YYYY-MM-DD |
| 单位净值 | float | 单位净值 |
| 累计净值 | float | 累计净值 |
| 日增长率 | float | 日涨跌幅(%) |
| 申购状态 | string | 申购状态 |
| 赎回状态 | string | 赎回状态 |

---

## 八、AKShare 上交所接口 ✅ 已验证

### 8.1 接口列表

| 接口 | 用途 | 参数 | 返回字段 | 限速 | 状态 |
|------|------|------|----------|------|------|
| `fund_etf_scale_sse` | 上交所ETF规模 | 无参数 | 序号,基金代码,基金简称,ETF类型,统计日期,基金份额 | 5秒 | ✅ |
| `fund_name_em` | 基金名称列表 | 无参数 | 基金代码,基金简称 | 5秒 | ✅ |

### 8.2 上交所ETF规模

**Python接口**: `fund_etf_scale_sse()`

**示例**:
```python
df = ak.fund_etf_scale_sse()  # 593条ETF
```

**返回字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| 序号 | int | 序号 |
| 基金代码 | string | ETF代码 |
| 基金简称 | string | ETF名称 |
| ETF类型 | string | 单市/跨沪/跨深 |
| 统计日期 | string | YYYY-MM-DD |
| 基金份额 | float | 份额数量 |

---

## 九、AKTools HTTP API ✅ **已验证**

### 9.1 概述
- **服务地址**: `http://127.0.0.1:8080`
- **工作目录**: `/home/qwenpaw/.qwenpaw/workspaces/default/aktools-server`
- **启动命令**: `cd aktools-server && python -m aktools`
- **AKTools版本**: 0.0.91
- **AKShare版本**: 1.18.63
- **用途**: 本地HTTP API，通过akshare调用各数据源

### 9.2 HTTP API 接口验证

| 接口 | HTTP路径 | 返回 | 耗时 | 状态 |
|------|----------|------|------|------|
| 版本信息 | `/version` | {"ak_version":"1.18.63"...} | 0.01s | ✅ |
| ETF实时行情 | `/api/public/fund_etf_spot_em` | 1486条 | 16.88s | ✅ |
| ETF历史日线 | `/api/public/fund_etf_hist_sina?symbol=sz159919` | 3400条 | 0.24s | ✅ |
| ETF分类 | `/api/public/fund_etf_category_sina` | 382条 | 0.62s | ✅ |

### 9.3 调用示例

```bash
# 获取版本信息
curl "http://127.0.0.1:8080/version"

# 获取ETF实时行情（全市场1486条）
curl "http://127.0.0.1:8080/api/public/fund_etf_spot_em"

# 获取ETF历史日线
curl "http://127.0.0.1:8080/api/public/fund_etf_hist_sina?symbol=sz159919"

# 获取ETF分类
curl "http://127.0.0.1:8080/api/public/fund_etf_category_sina"
```

### 9.4 返回格式

```json
// 成功返回 JSON 数组
[
  {
    "date": "2012-05-28T00:00:00.000",
    "open": 0.951,
    "high": 0.983,
    "low": 0.951,
    "close": 0.983,
    "volume": 1079199232,
    "amount": 1037835072
  }
]
```

### 9.5 限速规则

⚠️ **重要**: HTTP API 调用间隔至少 **5秒**，每次请求耗时 0.5-17 秒不等。

| 接口 | 建议间隔 |
|------|---------|
| 轻量接口（如版本） | 无限制 |
| ETF历史日线 | 5秒+ |
| ETF实时行情 | 10秒+ |

---

## 十、数据源路由表

### 10.1 优先级配置

| 数据类型 | 优先级1 | 优先级2 | 优先级3 | 最后 |
|---------|---------|---------|--------|------|
| **ETF实时价格** | 腾讯API | AKShare东财 | AKShare新浪 | 昨收价 |
| **ETF历史日线** | AKShare新浪 | 腾讯API | BaoStock | - |
| **ETF净值（盘中）** | 天天基金 | AKShare东财 | - | - |
| **ETF净值（历史）** | 天天基金 | AKShare东财 | - | - |
| **ETF小时线** | 新浪scale=30 | - | - | - |

### 9.2 降级策略

```
主数据源 → 备数据源1 → 备数据源2 → 错误日志 + 告警
```

---

## 十一、限速规则

| 数据源 | 最小间隔 | 最大间隔 | 说明 |
|--------|---------|---------|------|
| 腾讯API | 2秒 | 5秒 | 随机 |
| 新浪API | 2秒 | 5秒 | 随机 |
| 天天基金 | 3秒 | 6秒 | 随机 |
| BaoStock | 无严格 | - | 可批量 |
| **AKShare/AKTools** | **5秒** | **10秒** | **每次调用间隔≥5秒** |
| 雪球API | 3秒 | 6秒 | 需Cookie |

---

## 十二、接口映射表

### 11.1 统一数据格式

```python
@dataclass
class ETFData:
    """ETF数据统一格式"""
    code: str           # 代码（无前缀）
    date: str          # 日期 YYYY-MM-DD
    name: str          # 名称
    open: float        # 开盘价
    high: float        # 最高价
    low: float         # 最低价
    close: float       # 收盘价
    volume: int        # 成交量
    amount: float      # 成交额
    change_pct: float  # 涨跌幅(%)
```

### 11.2 来源 → 统一字段

| 统一字段 | 腾讯实时 | 腾讯日线 | 新浪实时 | 新浪K线 | 天天基金 | BaoStock | AKShare新浪 |
|----------|---------|----------|----------|---------|----------|----------|------------|
| code | 索引2 | - | 索引2 | - | fundcode | code字段 | 代码字段 |
| name | 索引1 | - | 索引0 | - | name | - | 名称 |
| date | - | 索引0 | - | day字段 | jzrq | date字段 | date |
| open | - | 索引1 | 索引1 | open | - | open | open |
| high | 索引41 | 索引3 | 索引4 | high | - | high | high |
| low | 索引42 | 索引4 | 索引5 | low | - | low | low |
| close | 索引3 | 索引2 | 索引3 | close | dnjz/gsz | close | close |
| volume | 索引6 | 索引5 | 索引6 | volume | - | volume | volume |
| amount | - | - | 索引7 | amount | - | - | amount |

---

## 十三、测试脚本

| 脚本 | 说明 |
|------|------|
| `scripts/verify_all_datasources.py` | 验证10个数据源 |
| `aktools-server/full_api_test.py` | 全面测试17个接口 |

---

## 十四、更新记录

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| v1.0 | 2026-05-27 | 初始版本 |
| v2.0 | 2026-05-30 | 新增字段说明、天天基金接口、BaoStock示例 |
| v2.1 | 2026-05-30 | 新增雪球Xueqiu、百度百科两个数据源 |
| v3.0 | 2026-05-30 | 全面验证，修正字段映射 |
| v3.1 | 2026-05-30 | 新增AKTools本地部署HTTP API |
| v3.2 | 2026-05-30 | 验证AKTools非东财接口 |
| v3.3 | 2026-05-30 | 记录AKTools 5秒限速规则 |
| **v4.0** | **2026-05-30** | **全面测试17个接口：13通过，4失败** |
| **v4.1** | **2026-05-30** | **新增AKTools HTTP API验证结果：本地API已部署并测试通过（4个接口验证）** |

---

*文档版本: v4.1 | 更新: 2026-05-30 | 测试脚本: scripts/verify_all_datasources.py, aktools-server/test_http_api.py*