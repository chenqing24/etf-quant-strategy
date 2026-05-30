# ETF量化系统 - 数据源完整文档 v3.0

> 更新: 2026-05-30 | 基于实际API验证

---

## 一、概述

本文档描述ETF量化系统使用的所有外部数据源、接口格式、字段说明和使用约束。

**验证状态说明**：
- ✅ 已验证：接口测试通过，数据可用
- ⚠️ 待验证：需Token或特殊条件
- ❌ 不可用：接口不稳定或被限制

---

### 1.1 数据源总览

| # | 数据源 | 用途 | 可靠性 | 限速 | 官方文档 | 验证状态 |
|---|--------|------|--------|------|----------|----------|
| 1 | 腾讯行情API | 实时价格、日线数据 | ⭐⭐⭐⭐⭐ | 2-5秒 | ❌ 无 | ✅ 已验证 |
| 2 | 新浪财经API | 小时线、实时备源 | ⭐⭐⭐⭐ | 2-5秒 | ❌ 无 | ✅ 已验证 |
| 3 | 天天基金网 | ETF基本信息、净值 | ⭐⭐⭐⭐ | 3-6秒 | ❌ 无 | ✅ 已验证 |
| 4 | BaoStock | ETF/股票日线 | ⭐⭐⭐⭐ | 无严格 | ✅ 有 | ✅ 已验证 |
| 5 | 东方财富EMF | 股票数据 | ⭐⭐⭐ | 3-6秒 | ❌ 无 | ❌ ETF不可用 |
| 6 | Tushare Pro | 日线备源（需Token） | ⭐⭐⭐⭐ | 有限制 | ✅ 有 | ⚠️ 待验证 |
| 7 | AKShare | 股票分钟线 | ⭐⭐⭐ | 无严格 | ✅ 有 | ⚠️ 待验证 |
| 8 | 雪球Xueqiu | 基金详情 | ⭐⭐⭐⭐ | 需Cookie | ❌ 无 | ✅ 页面已验证 |
| 9 | 百度百科 | ETF基础知识 | ⭐⭐ | 限流 | ✅ 有 | ⚠️ 限流严重 |

---

## 二、腾讯行情API (Tencent) ✅ 已验证

### 2.1 概述
- **基础URL**: `https://qt.gtimg.cn/q=`
- **日线URL**: `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get`
- **用途**: 实时价格（首选）、日线历史数据
- **返回格式**: 文本解析 → JSON
- **可靠性**: 最高，国内行情首选

### 2.2 实时行情接口

**URL格式**:
```
https://qt.gtimg.cn/q={prefix}{code}
```

**参数说明**:
| 参数 | 说明 | 示例 |
|------|------|------|
| prefix | 代码前缀 | `sz`（深圳）、`sh`（上海）|
| code | ETF代码 | `159919`、`510300` |

**请求示例**:
```bash
curl "https://qt.gtimg.cn/q=sz159919"
```

**返回格式**:
```
v_sz159919="51~沪深300ETF嘉实~159919~5.132~5.143~5.153~1271218~..."
```

**核心字段**（88字段）:
| 索引 | 字段名 | 示例值 | 说明 | 来源 |
|------|--------|--------|------|------|
| 0 | market_status | 51 | 市场状态（51=正常，0=停牌） | ✅实测 |
| 1 | name | 沪深300ETF嘉实 | ETF名称 | ✅实测 |
| 2 | code | 159919 | 证券代码 | ✅实测 |
| 3 | price | 5.132 | 当前价格 | ✅实测 |
| 4 | prev_close | 5.143 | 昨收价 | ✅实测 |
| 5 | high | 5.153 | 今日最高 | ✅实测 |
| 6 | volume | 1271218 | 成交量（股） | ✅实测 |
| 30 | time | 20260529161439 | 数据时间 YYYYMMDDHHMMSS | ✅实测 |
| 31 | change | -0.011 | 涨跌额 | ✅实测 |
| 32 | change_pct | -0.21 | 涨跌幅(%) | ✅实测 |
| 41 | day_high | 5.184 | 日最高 | ✅实测 |
| 42 | day_low | 5.106 | 日最低 | ✅实测 |
| 49 | nav | 5.149 | 基金净值 | ✅实测 |
| 57 | scale | 123.87 | 规模（亿元） | ✅实测 |
| 61 | type | ETF | 类型 | ✅实测 |

### 2.3 日线历史接口

**URL格式**:
```
https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param={prefix}{code},day,,,{count},qfq
```

**参数说明**:
| 参数 | 说明 | 示例 |
|------|------|------|
| prefix | 代码前缀 | `sz`、`sh` |
| code | ETF代码 | `159919` |
| count | 获取条数 | 320（约1年交易日）|

**请求示例**:
```bash
curl "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param=sz159919,day,,,10,qfq"
```

**返回格式** (JSON):
```json
{
  "data": {
    "sz159919": {
      "qfqday": [
        ["2026-05-29", "5.153", "5.132", "5.184", "5.106", "1271218.000"],
        ...
      ]
    }
  }
}
```

**返回字段** (qfqday数组):
| 索引 | 字段名 | 类型 | 说明 | 来源 |
|------|--------|------|------|------|
| 0 | date | string | 日期 YYYY-MM-DD | ✅实测 |
| 1 | open | float | 开盘价 | ✅实测 |
| 2 | close | float | 收盘价 | ✅实测 |
| 3 | high | float | 最高价 | ✅实测 |
| 4 | low | float | 最低价 | ✅实测 |
| 5 | volume | float | 成交量 | ✅实测 |

### 2.4 适用场景

| 场景 | 状态 | 说明 |
|------|------|------|
| 实时价格 | ✅ 主要 | 优先使用，支持批量 |
| 日线历史（上交所） | ✅ 主要 | 510xxx系列完全支持 |
| 日线历史（深交所） | ✅ 可用 | 159xxx系列支持 |
| 小时线 | ❌ 不支持 | 使用新浪API |

---

## 三、新浪财经API (Sina) ✅ 已验证

### 3.1 概述
- **实时URL**: `https://hq.sinajs.cn/list=`
- **K线URL**: `https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData`
- **用途**: 实时价格（备源）、30分钟K线
- **Referer**: `https://finance.sina.com.cn/`（必须）

### 3.2 实时行情接口

**URL格式**:
```
https://hq.sinajs.cn/list={prefix}{code}
```

**请求示例**:
```bash
curl -H "Referer: https://finance.sina.com.cn" "https://hq.sinajs.cn/list=sz159919"
```

**返回格式**:
```
var hq_str_sz159919="沪深300,5.153,5.143,5.132,5.184,5.106,5.132,5.133,127121814,654509291.772,...";
```

**核心字段**（约34字段）:
| 索引 | 字段名 | 示例值 | 说明 | 来源 |
|------|--------|--------|------|------|
| 0 | name | 沪深300 | 名称（无ETF后缀） | ✅实测 |
| 1 | open | 5.153 | 开盘价 | ✅实测 |
| 2 | prev_close | 5.143 | 昨收价 | ✅实测 |
| 3 | price | 5.132 | 当前价 | ✅实测 |
| 4 | high | 5.184 | 今日最高 | ✅实测 |
| 5 | low | 5.106 | 今日最低 | ✅实测 |
| 6 | volume | 127121814 | 成交量 | ✅实测 |
| 7 | amount | 654509291.772 | 成交额 | ✅实测 |

### 3.3 30分钟K线接口

**URL格式**:
```
https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol={prefix}{code}&scale=30&ma=no&datalen={count}
```

**参数说明**:
| 参数 | 说明 | 示例 |
|------|------|------|
| symbol | 完整代码（含前缀） | `sz159919` |
| scale | 时间周期（分钟） | 30 |
| ma | 均线 | no（不要均线）|
| datalen | 获取条数 | 1800（约1.5年）|

**请求示例**:
```bash
curl "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol=sz159919&scale=30&ma=no&datalen=5"
```

**返回格式** (JSON):
```json
[
  {
    "day": "2026-05-29 11:30:00",
    "open": "5.151",
    "high": "5.156",
    "low": "5.136",
    "close": "5.147",
    "volume": "9519100",
    "amount": "48976279.6135"
  }
]
```

**返回字段**:
| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| day | string | 时间戳 YYYY-MM-DD HH:MM:SS | ✅实测 |
| open | float | 开盘价 | ✅实测 |
| high | float | 最高价 | ✅实测 |
| low | float | 最低价 | ✅实测 |
| close | float | 收盘价 | ✅实测 |
| volume | int | 成交量 | ✅实测 |
| amount | float | 成交额 | ✅实测 |

### 3.4 历史覆盖能力

| 数据类型 | 理论上限 | 实际覆盖 | 备注 |
|----------|---------|---------|------|
| scale=30（30分钟） | 1800条 | ~340天 | 约11个月 |

### 3.5 适用场景

| 场景 | 状态 | 说明 |
|------|------|------|
| 实时价格 | ⚠️ 备源 | 仅作为腾讯API的备源 |
| 30分钟K线 | ✅ 主要 | 唯一来源 |
| 日线历史 | ❌ 不支持 | 使用腾讯或BaoStock |

---

## 四、天天基金网 (EastMoney Fund) ✅ 已验证

### 4.1 概述
- **实时估值URL**: `https://fundgz.1234567.com.cn/js/{code}.js`
- **历史净值URL**: `https://api.fund.eastmoney.com/f10/lsjz`
- **用途**: ETF基本信息、实时估值、历史净值
- **返回格式**: JSONP / JSON

### 4.2 实时估值接口

**URL格式**:
```
https://fundgz.1234567.com.cn/js/{code}.js?rt={timestamp}
```

**请求示例**:
```bash
curl "https://fundgz.1234567.com.cn/js/159919.js?rt=1748601600"
```

**返回格式**:
```json
jsonpgz({
  "fundcode": "159919",
  "name": "沪深300ETF嘉实",
  "jzrq": "2026-05-28",
  "dwjz": "5.1447",
  "gsz": "5.1215",
  "gszzl": "-0.45",
  "gztime": "2026-05-29 15:00"
});
```

**返回字段**:
| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| fundcode | string | ETF代码 | ✅实测 |
| name | string | ETF名称 | ✅实测 |
| jzrq | string | 净值日期 YYYY-MM-DD | ✅实测 |
| dnjz | float | 单位净值 | ✅实测 |
| gsz | float | 估算净值（盘中） | ✅实测 |
| gszzl | float | 估算涨跌幅(%) | ✅实测 |
| gztime | string | 估算时间 | ✅实测 |

### 4.3 历史净值接口

**URL格式**:
```
https://api.fund.eastmoney.com/f10/lsjz?callback=jQuery&fundCode={code}&pageIndex=1&pageSize={count}&endDate={endDate}
```

**请求示例**:
```bash
curl "https://api.fund.eastmoney.com/f10/lsjz?callback=jQuery&fundCode=159919&pageIndex=1&pageSize=5"
```

**返回格式**:
```json
{
  "Data": {
    "LSJZList": [
      {
        "FSRQ": "2026-05-29",
        "DWJZ": "5.1228",
        "LJJZ": "2.3472",
        "JZZZL": "-0.43",
        "SGZT": "场内买入",
        "SHZT": "场内卖出"
      }
    ],
    "TotalCount": 3418
  }
}
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

### 4.4 适用场景

| 场景 | 状态 | 说明 |
|------|------|------|
| ETF名称 | ✅ 主要 | 快速获取 |
| 实时估值 | ✅ 主要 | 盘中参考 |
| 历史净值 | ✅ 主要 | 收盘后数据 |
| 基金详情 | ❌ 不可用 | 需爬虫 |

---

## 五、BaoStock ✅ 已验证

### 5.1 概述
- **安装**: `pip install baostock`
- **官网**: https://www.baostock.com
- **用途**: ETF/股票日线（深交所优先）
- **返回格式**: 游标迭代

### 5.2 日线数据接口

**Python示例**:
```python
import baostock as bs

# 登录
bs.login()

# 查询ETF日线
rs = bs.query_history_k_data_plus(
    'sz.159919',  # 注意加前缀 sz. 或 sh.
    'date,open,high,low,close,volume,code',
    start_date='2026-01-01',
    end_date='2026-05-30',
    frequency='d'  # d=日线, w=周线, m=月线
)

# 处理结果
while rs.error_code == '0' and rs.next():
    print(rs.get_row_data())

# 登出
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
| code | string | 证券代码 | ✅官方文档 |

### 5.3 代码格式

| 市场 | 前缀 | 示例 |
|------|------|------|
| 深圳 | `sz.` | `sz.159919` |
| 上海 | `sh.` | `sh.510300` |

### 5.4 适用场景

| 场景 | 状态 | 说明 |
|------|------|------|
| 深交所ETF日线 | ✅ 主要 | 159xxx系列最佳 |
| 上交所ETF日线 | ✅ 可用 | 510xxx系列 |
| 个股日线 | ✅ 主要 | 股票数据 |
| 小时线 | ❌ 不支持 | 使用新浪 |

### 5.5 数据覆盖对比

| ETF | 腾讯API | BaoStock |
|-----|---------|----------|
| sh510300（上交所） | ✅ 完全 | ✅ 可用 |
| sz159919（深交所） | ✅ 可用 | ✅ 最好 |
| sz159338（深交所） | ❌ 不支持 | ✅ 支持 |

---

## 六、东方财富EMF (EastMoney) ❌ ETF不可用

### 6.1 概述
- **实时URL**: `https://push2.eastmoney.com/api/qt/ulist.np/get`
- **用途**: 股票数据（ETF数据不稳定）
- **返回格式**: JSON

### 6.2 实时行情接口

**URL格式**:
```
https://push2.eastmoney.com/api/qt/ulist.np/get?ut=fa5fd1943c7b386f172d6893dbfba10b&invt=2&fltt=2&fields=f57,f58,f60,f84,f116&secids=0.{code}
```

**请求示例**:
```bash
curl "https://push2.eastmoney.com/api/qt/ulist.np/get?ut=fa5fd1943c7b386f172d6893dbfba10b&invt=2&fltt=2&fields=f57,f58,f60,f84,f116&secids=0.159919"
```

**返回格式**:
```json
{
  "data": {
    "total": 1,
    "diff": [{
      "f57": "-",
      "f58": "-",
      "f60": "-",
      "f84": -19833410.0,
      "f116": "-"
    }]
  }
}
```

### 6.3 验证结论

| ETF代码 | 返回状态 | 说明 |
|---------|---------|------|
| 159919 | f57="-" | **ETF数据不可用** |
| 510300 | f57="-" | **ETF数据不可用** |

**结论**: 东方财富EMF的ulist接口对ETF支持不稳定，返回空数据。建议使用腾讯API或天天基金。

### 6.4 适用场景

| 场景 | 状态 | 说明 |
|------|------|------|
| 股票实时价格 | ⚠️ 备源 | 可用 |
| ETF实时价格 | ❌ 不可用 | 返回空数据 |
| ETF元信息 | ❌ 不可用 | 不可用 |

---

## 七、Tushare Pro ⚠️ 待验证

### 7.1 概述
- **官网**: https://tushare.pro
- **用途**: 日线备源
- **限制**: 需要注册Token，有积分要求
- **返回格式**: DataFrame

### 7.2 ETF日线接口

**Python示例**:
```python
import tushare as ts

# 设置Token
ts.set_token('your_token_here')
pro = ts.pro_api()

# 查询ETF日线
df = pro.fund_daily(
    ts_code='159919.SZ',
    start_date='20260101',
    end_date='20260530'
)
```

### 7.3 适用场景

| 场景 | 状态 | 说明 |
|------|------|------|
| 日线历史 | ⚠️ 备源 | 需要Token |
| 实时价格 | ❌ 不推荐 | 延迟较大 |

---

## 八、AKShare ⚠️ 待验证

### 8.1 概述
- **安装**: `pip install akshare`
- **官网**: https://akshare.akfamily.xyz
- **用途**: 股票分钟线
- **返回格式**: DataFrame

### 8.2 股票日线接口

**Python示例**:
```python
import akshare as ak

# 东方财富-股票日线数据
df = ak.stock_zh_a_hist(
    symbol="159919",
    period="daily",
    start_date="20260101",
    end_date="20260530",
    adjust="qfq"
)
```

### 8.3 适用场景

| 场景 | 状态 | 说明 |
|------|------|------|
| 股票日线 | ⚠️ 可用 | 参考用 |
| ETF日线 | ⚠️ 不稳定 | 数据可能不完整 |
| 分钟线 | ⚠️ 可用 | 参考用 |

---

## 九、雪球Xueqiu ✅ 页面已验证

### 9.1 概述
- **官网**: https://xueqiu.com
- **用途**: 基金详情页
- **返回格式**: HTML
- **可靠性**: ⭐⭐⭐⭐（需Cookie）

### 9.2 行情页面

**URL格式**:
```
https://xueqiu.com/S/{prefix}{code}
```

**请求示例**:
```bash
curl -H "User-Agent: Mozilla/5.0" "https://xueqiu.com/S/SZ159919"
```

**返回内容**:
- ETF基本信息（名称、代码）
- 实时行情（当前价、涨跌幅）
- 基金详情（规模、成立日期）
- 讨论区（舆情参考）

### 9.3 行情API接口

**URL格式**:
```
https://stock.xueqiu.com/v5/stock/quote.json?symbol={prefix}{code}&extend=detail
```

**请求头**:
```
User-Agent: Mozilla/5.0
Cookie: xq_a_token=xxx  # 必须
Referer: https://xueqiu.com
```

**⚠️ 注意**: API接口需要有效的Cookie，否则返回400016错误。

### 9.4 适用场景

| 场景 | 状态 | 说明 |
|------|------|------|
| ETF详情页 | ✅ 可用 | HTML页面可访问 |
| 实时价格 | ⚠️ 备源 | 需Cookie |
| 舆情信息 | ✅ 可用 | 讨论区参考 |
| 历史数据 | ❌ 不推荐 | 使用腾讯/BaoStock |

---

## 十、百度百科 ⚠️ 限流严重

### 10.1 概述
- **官网**: https://baike.baidu.com
- **用途**: ETF基础知识
- **返回格式**: HTML
- **可靠性**: ⭐⭐（限流）

### 10.2 搜索接口

**URL格式**:
```
https://baike.baidu.com/item/{关键词}
```

**请求示例**:
```bash
curl -H "User-Agent: Mozilla/5.0" "https://baike.baidu.com/item/ETF"
```

**⚠️ 注意**: 经常触发安全验证，批量访问不可行。

### 10.3 适用场景

| 场景 | 状态 | 说明 |
|------|------|------|
| ETF基础知识 | ✅ 手动参考 | 术语解释 |
| 产品背景 | ✅ 手动参考 | 跟踪指数说明 |
| 批量获取 | ❌ 不可行 | 限流严重 |
| 实时数据 | ❌ 不适用 | 非行情数据源 |

---

## 十一、数据源路由表

### 11.1 优先级配置

| 数据类型 | 优先级1 | 优先级2 | 优先级3 | 最后 |
|---------|---------|---------|--------|------|
| ETF实时价格 | 腾讯API | 新浪API | 天天基金 | 昨收价 |
| ETF日线（上交所） | 腾讯API | BaoStock | - | - |
| ETF日线（深交所） | BaoStock | 腾讯API | - | - |
| ETF小时线 | 新浪scale=30 | - | - | - |
| ETF历史净值 | 天天基金 | BaoStock | - | - |
| 股票日线 | BaoStock | Tushare | AKShare | - |
| 股票分钟线 | AKShare | - | - | - |

### 11.2 降级策略

```
主数据源 → 备数据源1 → 备数据源2 → 错误日志 + 告警
```

---

## 十二、接口使用约束

### 12.1 限速规则

| 数据源 | 最小间隔 | 最大间隔 | 说明 |
|--------|---------|---------|------|
| 腾讯API | 2秒 | 5秒 | 随机 |
| 新浪API | 2秒 | 5秒 | 随机 |
| 天天基金 | 3秒 | 6秒 | 随机 |
| BaoStock | 无严格 | - | 可批量 |
| 雪球API | 3秒 | 6秒 | 需Cookie |
| 百度百科 | ❌ 禁止批量 | - | 限流严重 |

### 12.2 缓存策略

| 数据类型 | TTL | 说明 |
|----------|-----|------|
| 实时价格 | 5分钟 | 盘中避免重复请求 |
| 日线历史 | 1小时 | 历史数据变动少 |
| 小时线 | 5分钟 | 盘中更新 |
| ETF净值 | 1天 | 变化不频繁 |

### 12.3 禁止规则

```python
# ❌ 禁止：裸请求
import requests
requests.get("https://qt.gtimg.cn/q=sz159919")

# ✅ 正确：通过 DataSourceRouter
router = DataSourceRouter()
data = router.fetch('realtime', ['sz159919'])
```

### 12.4 异常处理

| 异常 | 处理方式 |
|------|---------|
| 超时 | 降级到备源，重试3次 |
| 无数据 | 记录日志，使用缓存 |
| API错误 | 切换备源，告警 |
| 全部失败 | 使用昨收价，标记"数据过期" |

---

## 十三、字段映射表

### 13.1 统一数据格式

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

### 13.2 来源 → 统一字段

| 统一字段 | 腾讯实时 | 腾讯日线 | 新浪实时 | 新浪K线 | 天天基金 | BaoStock |
|----------|---------|----------|----------|---------|----------|-----------|
| code | 索引2 | - | - | - | fundcode | code字段 |
| date | - | 索引0 | - | day | jzrq | date字段 |
| name | 索引1 | - | 索引0 | - | name | - |
| open | - | 索引1 | 索引1 | open | - | open字段 |
| high | 索引41 | 索引3 | 索引4 | high | - | high字段 |
| low | 索引42 | 索引4 | 索引5 | low | - | low字段 |
| close | 索引3 | 索引2 | 索引3 | close | dnjz/gsz | close字段 |
| volume | 索引6 | 索引5 | 索引6 | volume | - | volume字段 |
| change_pct | 索引32 | - | - | - | gszzl | - |

---

## 十四、验证脚本

验证脚本: `scripts/verify_all_datasources.py`

运行验证:
```bash
cd etf_strategy
python scripts/verify_all_datasources.py
```

**最新验证结果**:
- ✅ 通过: 21 个
- ❌ 失败: 4 个（东方财富EMF - ETF不可用）

---

## 十五、更新记录

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| v1.0 | 2026-05-27 | 初始版本 |
| v2.0 | 2026-05-30 | 新增字段说明、天天基金接口、BaoStock示例 |
| v2.1 | 2026-05-30 | 新增雪球Xueqiu、百度百科两个数据源 |
| v3.0 | 2026-05-30 | **全面验证**：修正字段映射，标注数据来源（实测/官方），东方财富EMF标记为ETF不可用 |

---

*文档版本: v3.0 | 更新: 2026-05-30 | 验证脚本: scripts/verify_all_datasources.py*