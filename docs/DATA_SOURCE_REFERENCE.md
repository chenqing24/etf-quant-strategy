# ETF量化系统 - 数据源完整文档 v2.0

> 更新: 2026-05-30 | 基于实际API测试

---

## 一、概述

本文档描述ETF量化系统使用的所有外部数据源、接口格式、字段说明和使用约束。

### 1.1 数据源总览

| # | 数据源 | 用途 | 可靠性 | 限速 | 官方文档 |
|---|--------|------|--------|------|----------|
| 1 | 腾讯行情API | 实时价格、日线数据 | ⭐⭐⭐⭐⭐ | 2-5秒 | ❌ 无 |
| 2 | 新浪财经API | 小时线、实时备源 | ⭐⭐⭐⭐ | 2-5秒 | ❌ 无 |
| 3 | 天天基金网 | ETF基本信息 | ⭐⭐⭐⭐ | 3-6秒 | ❌ 无 |
| 4 | BaoStock | ETF/股票日线（深交所） | ⭐⭐⭐⭐ | 无严格限制 | ✅ 有 |
| 5 | 东方财富EMF | 实时备源、个股数据 | ⭐⭐⭐ | 3-6秒 | ❌ 无 |
| 6 | AKShare | 股票分钟线（参考） | ⭐⭐⭐ | 无严格限制 | ✅ 有 |
| 7 | Tushare | 日线备源（需Token） | ⭐⭐⭐⭐ | 有限制 | ✅ 有 |
| 8 | 雪球Xueqiu | 基金详情、实时行情 | ⭐⭐⭐⭐ | 需Cookie | ❌ 无 |
| 9 | 百度百科 | ETF基础知识 | ⭐⭐ | 限流 | ✅ 有 |

---

## 二、腾讯行情API (Tencent)

### 2.1 概述
- **基础URL**: `https://qt.gtimg.cn/q=`
- **用途**: 实时价格（首选）、日线历史数据
- **返回格式**: 文本解析
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

**示例**:
```bash
curl "https://qt.gtimg.cn/q=sz159919"
```

**返回格式**:
```
v_sz159919="51~沪深300ETF嘉实~159919~5.132~5.143~5.153~1271218~..."
```

### 2.3 字段说明（88字段）

| 索引 | 字段名 | 示例值 | 说明 |
|------|--------|--------|------|
| 0 | 市场状态 | 51 | 51=正常，0=停牌 |
| 1 | ETF名称 | 沪深300ETF嘉实 | |
| 2 | 代码 | 159919 | |
| 3 | 当前价格 | 5.132 | |
| 4 | 昨收价 | 5.143 | |
| 5 | 今日最高 | 5.153 | |
| 6 | 成交量（股） | 1271218 | |
| 7 | 外盘量 | 656012 | |
| 8 | 内盘量 | 615206 | |
| 9 | 现价 | 5.132 | 等于索引3 |
| 10-27 | 买卖盘 | 各档位价格和数量 | 10档行情 |
| 30 | 数据时间 | 20260529161439 | YYYYMMDDHHMMSS |
| 31 | 涨跌额 | -0.011 | |
| 32 | 涨跌幅% | -0.21 | |
| 33 | 52周最高 | 5.184 | |
| 34 | 52周最低 | 4.629 | |
| 35 | 汇总信息 | 5.132/1271218/654509292 | 价格/成交量/成交额 |
| 36 | 成交量（手） | 1271218 | |
| 37 | 成交额（元） | 65451 | 单位万元 |
| 38 | 成交量（万手） | 1.03 | |
| 41 | 日最高 | 5.184 | |
| 42 | 日最低 | 5.106 | |
| 43 | 振幅 | 1.52% | |
| 44 | 52周最高 | 5.657 | |
| 45 | 52周最低 | 4.629 | |
| 46 | 涨跌额 | 0.00 | |
| 47 | 涨停价 | 5.657 | |
| 48 | 跌停价 | 4.629 | |
| 49 | 基金净值 | 5.149 | |
| 50 | 溢价率 | 2579 | 百分比×100 |
| 51 | 估算净值 | 5.149 | |
| 57 | 规模（亿元） | 123.87 | |
| 58 | 日涨跌 | -0.04% | |
| 61 | 类型 | ETF | |
| 62 | 估算规模（亿） | 6.32 | |
| 63 | 估算溢价率 | 1.24% | |
| 74 | 52周涨跌 | +0.28% | |
| 75 | 年化收益 | 11.27% | |
| 76 | 总市值 | 12386916676 | |
| 82 | 货币单位 | CNY | |
| 85 | 最新价 | 5.126 | |
| 86 | 成交量 | 819 | |

### 2.4 日线历史接口

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

**示例**:
```bash
curl "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?_var=kline_dayqfq&param=sz159919,day,,,320,qfq"
```

**返回格式**:
```json
{
  "data": {
    "sz159919": {
      "day": [
        ["2026-05-29", "5.100", "5.150", "5.080", "5.120", "1271218"],
        ["2026-05-28", "5.130", "5.180", "5.090", "5.100", "2345678"],
        ...
      ]
    }
  }
}
```

**返回字段**:
| 索引 | 字段名 | 说明 |
|------|--------|------|
| 0 | 日期 | YYYY-MM-DD |
| 1 | 开盘价 | |
| 2 | 最高价 | |
| 3 | 最低价 | |
| 4 | 收盘价 | |
| 5 | 成交量 | |

### 2.5 适用场景

| 场景 | 使用 | 说明 |
|------|------|------|
| 实时价格 | ✅ 主要 | 优先使用，支持批量 |
| 日线历史 | ✅ 主要 | 上交所ETF完全支持 |
| 深交所ETF | ⚠️ 部分 | 159xxx系列可能不支持 |
| 小时线 | ❌ 不支持 | 使用新浪API |

---

## 三、新浪财经API (Sina)

### 3.1 概述
- **实时URL**: `https://hq.sinajs.cn/list=`
- **小时线URL**: `https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData`
- **用途**: 实时价格（备源）、30分钟K线
- **Referer**: `https://finance.sina.com.cn/`

### 3.2 实时行情接口

**URL格式**:
```
https://hq.sinajs.cn/list={prefix}{code}
```

**示例**:
```bash
curl -H "Referer: https://finance.sina.com.cn" "https://hq.sinajs.cn/list=sz159919"
```

**返回格式**:
```
var hq_str_sz159919="51,沪深300ETF嘉实,159919,5.132,5.143,5.153,1271218,656012,615206,5.132,742,...";
```

**字段说明**（前20字段）:
| 索引 | 字段名 | 示例值 |
|------|--------|--------|
| 0 | 市场状态 | 51 |
| 1 | ETF名称 | 沪深300ETF嘉实 |
| 2 | 代码 | 159919 |
| 3 | 当前价格 | 5.132 |
| 4 | 昨收价 | 5.143 |
| 5 | 今日最高 | 5.153 |
| 6 | 成交量 | 1271218 |

### 3.3 小时线接口

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

**示例**:
```bash
curl "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData?symbol=sz159919&scale=30&ma=no&datalen=10"
```

**返回格式**:
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
  },
  ...
]
```

**返回字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| day | string | 时间戳（YYYY-MM-DD HH:MM:SS）|
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | int | 成交量 |
| amount | float | 成交额 |

### 3.4 历史覆盖能力

| 数据类型 | 理论上限 | 实际覆盖 | 备注 |
|----------|---------|---------|------|
| scale=30（30分钟） | 1800条 | ~340天 | 约11个月 |

### 3.5 适用场景

| 场景 | 使用 | 说明 |
|------|------|------|
| 实时价格 | ⚠️ 备源 | 仅作为腾讯API的备源 |
| 小时线 | ✅ 主要 | 唯一来源 |
| 日线历史 | ❌ 不支持 | 使用腾讯或BaoStock |

---

## 四、天天基金网 (EastMoney Fund)

### 4.1 概述
- **基本信息URL**: `https://fundgz.1234567.com.cn/js/{code}.js`
- **用途**: ETF基本信息、实时估值
- **返回格式**: JSONP

### 4.2 ETF基本信息接口

**URL格式**:
```
https://fundgz.1234567.com.cn/js/{code}.js?rt={timestamp}
```

**示例**:
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
| 字段 | 类型 | 说明 |
|------|------|------|
| fundcode | string | ETF代码 |
| name | string | ETF名称 |
| jzrq | string | 净值日期 |
| dnjz | float | 单位净值 |
| gsz | float | 估算净值 |
| gszzl | float | 估算涨跌幅(%) |
| gztime | string | 估算时间 |

### 4.3 适用场景

| 场景 | 使用 | 说明 |
|------|------|------|
| ETF名称 | ✅ 可用 | 快速获取 |
| 实时估值 | ✅ 可用 | 盘中参考 |
| 基金详情 | ❌ 不可用 | 需爬虫 |
| 历史净值 | ✅ 可用 | 见下节 |

### 4.4 基金历史净值接口

**URL格式**:
```
https://api.fund.eastmoney.com/f10/lsjz?callback=jQuery&fundCode={code}&pageIndex=1&pageSize={count}&endDate={endDate}
```

**示例**:
```bash
curl "https://api.fund.eastmoney.com/f10/lsjz?callback=jQuery&fundCode=159919&pageIndex=1&pageSize=10"
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
    "FundType": "001",
    "TotalCount": 3418
  }
}
```

**返回字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| FSRQ | string | 日期 |
| DWJZ | float | 单位净值 |
| LJJZ | float | 累计净值 |
| JZZZL | float | 日涨跌幅(%) |
| SGZT | string | 申购状态 |
| SHZT | string | 赎回状态 |

---

## 五、BaoStock

### 5.1 概述
- **安装**: `pip install baostock`
- **用途**: ETF/股票日线（深交所优先）
- **官网**: https://www.baostock.com

### 5.2 日线数据接口

**Python示例**:
```python
import baostock as bs

# 登录
bs.login()

# 查询ETF日线
rs = bs.query_history_k_data_plus(
    'sz.159919',  # 注意加前缀 sz. 或 sh.
    'date,open,high,low,close,volume,padjust,code',
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
| 字段 | 类型 | 说明 |
|------|------|------|
| date | string | 日期 YYYY-MM-DD |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量 |
| padjust | float | 前复权因子 |
| code | string | 证券代码 |

### 5.3 代码格式

| 市场 | 前缀 | 示例 |
|------|------|------|
| 深圳 | `sz.` | `sz.159919` |
| 上海 | `sh.` | `sh.510300` |

### 5.4 适用场景

| 场景 | 使用 | 说明 |
|------|------|------|
| 深交所ETF日线 | ✅ 主要 | 159xxx系列 |
| 上交所ETF日线 | ✅ 可用 | 510xxx系列 |
| 个股日线 | ✅ 主要 | 股票数据 |
| 小时线 | ❌ 不支持 | 使用新浪 |

### 5.5 数据覆盖对比

| ETF | 腾讯API | BaoStock |
|-----|---------|----------|
| sh510300（上交所） | ✅ 完全 | ✅ 可用 |
| sz159919（深交所） | ✅ 可用 | ✅ 最好 |
| sz159338（深交所） | ❌ 不支持 | ✅ 支持 |

**结论**: 两者互补使用

---

## 六、东方财富EMF (EastMoney)

### 6.1 概述
- **实时URL**: `https://push2.eastmoney.com/api/qt/ulist.np/get`
- **用途**: 实时价格（备源）、股票列表
- **返回格式**: JSON

### 6.2 实时行情接口

**URL格式**:
```
https://push2.eastmoney.com/api/qt/ulist.np/get?ut=fa5fd1943c7b386f172d6893dbfba10b&invt=2&fltt=2&fields=f57,f58,f60,f84,f85&secid=0.159919
```

**参数说明**:
| 参数 | 说明 |
|------|------|
| ut | 用户token（固定值） |
| invt | 请求类型 |
| fltt | 浮点类型 |
| fields | 字段ID列表 |
| secid | 证券ID（0=深交所，1=上交所）|

**可用字段ID**:
| 字段ID | 名称 | 示例 |
|--------|------|------|
| f57 | 代码 | 159919 |
| f58 | 名称 | 沪深300ETF嘉实 |
| f60 | 当前价格 | 5.143 |
| f84 | 规模 | 12386916608.0 |
| f85 | 估算规模 | 12386916608.0 |
| f116 | 市值 | 63569656032.256 |
| f189 | 成立日期 | 20120528 |
| f190 | 上市状态 | - |

**示例**:
```bash
curl "https://push2.eastmoney.com/api/qt/stock/get?ut=fa5fd1943c7b386f172d6893dbfba10b&invt=2&fltt=2&fields=f57,f58,f60,f84,f189&secid=0.159919"
```

**返回格式**:
```json
{
  "data": {
    "f57": "159919",
    "f58": "沪深300ETF嘉实",
    "f60": 5.143,
    "f84": 12386916608.0,
    "f189": 20120528
  }
}
```

### 6.3 适用场景

| 场景 | 使用 | 说明 |
|------|------|------|
| 实时价格 | ⚠️ 备源 | 仅腾讯API失败时使用 |
| ETF元信息 | ⚠️ 部分 | 成立日期、规模 |
| 个股数据 | ✅ 可用 | 股票日线备源 |

---

## 七、AKShare

### 7.1 概述
- **安装**: `pip install akshare`
- **用途**: 股票分钟线（参考）
- **官网**: https://akshare.akfamily.xyz

### 7.2 股票分钟线接口

**Python示例**:
```python
import akshare as ak

# 东方财富-股票分钟数据
df = ak.stock_zh_a_hist(
    symbol="159919",
    period="daily",
    start_date="20260101",
    end_date="20260530",
    adjust="qfq"
)
print(df)
```

### 7.3 适用场景

| 场景 | 使用 | 说明 |
|------|------|------|
| 股票分钟线 | ✅ 可用 | 参考用 |
| ETF分钟线 | ⚠️ 不稳定 | 数据可能不完整 |
| 日线 | ❌ 不推荐 | 使用腾讯/BaoStock |

---

## 八、Tushare Pro

### 8.1 概述
- **官网**: https://tushare.pro
- **用途**: 日线备源（需注册Token）
- **限制**: 有积分要求

### 8.2 ETF日线接口

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

### 8.3 适用场景

| 场景 | 使用 | 说明 |
|------|------|------|
| 日线历史 | ⚠️ 备源 | 需要Token |
| 实时价格 | ❌ 不推荐 | 延迟较大 |

---

## 九、雪球Xueqiu

### 9.1 概述
- **官网**: https://xueqiu.com
- **用途**: 基金详情页、实时行情、讨论信息
- **返回格式**: HTML + JSON API（需Cookie）
- **可靠性**: ⭐⭐⭐⭐（需登录Cookie）

### 9.2 行情页面

**URL格式**:
```
https://xueqiu.com/S/{prefix}{code}
```

**示例**:
```bash
curl -H "User-Agent: Mozilla/5.0" "https://xueqiu.com/S/SZ159919"
```

**页面内容**:
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

**返回字段**（JSON）:
| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| symbol | string | 证券代码 | 实测 |
| name | string | 名称 | 实测 |
| current | float | 当前价格 | 实测 |
| percent | float | 涨跌幅(%) | 实测 |
| change | float | 涨跌额 | 实测 |
| volume | int | 成交量 | 实测 |
| amount | float | 成交额 | 实测 |
| marketCapital | float | 总市值 | 实测 |
| pe_ttm | float | 市盈率TTM | 实测 |
| dividend | float | 分红率 | 实测 |

### 9.4 适用场景

| 场景 | 使用 | 说明 |
|------|------|------|
| ETF详情页 | ✅ 主要 | 基金信息丰富 |
| 实时价格 | ⚠️ 备源 | 需Cookie |
| 舆情信息 | ✅ 可用 | 讨论区参考 |
| 历史数据 | ❌ 不推荐 | 使用腾讯/BaoStock |

### 9.5 数据来源标注
- **字段定义**: 实测（无官方文档）
- **API格式**: 基于雪球旧版API推测

---

## 十、百度百科

### 10.1 概述
- **官网**: https://baike.baidu.com
- **用途**: ETF基础知识、背景信息
- **返回格式**: HTML
- **可靠性**: ⭐⭐（限流，需验证码）
- **注意**: 百度百科有反爬机制，经常触发安全验证

### 10.2 搜索接口

**URL格式**:
```
https://baike.baidu.com/item/{关键词}
```

**示例**:
```bash
curl -H "User-Agent: Mozilla/5.0" "https://baike.baidu.com/item/沪深300ETF"
```

**页面内容**:
- ETF定义与简介
- 投资目标
- 跟踪指数
- 相关术语解释

### 10.3 适用场景

| 场景 | 使用 | 说明 |
|------|------|------|
| ETF基础知识 | ✅ 可用 | 术语解释 |
| 产品背景 | ✅ 可用 | 跟踪指数说明 |
| 实时数据 | ❌ 不适用 | 非行情数据源 |
| 批量获取 | ❌ 不可行 | 限流严重 |

### 10.4 数据来源标注
- **字段定义**: 人工整理（基于页面内容）
- **反爬限制**: 高（触发安全验证概率大）

---

## 十一、数据源路由表

### 11.1 优先级配置

| 数据类型 | 优先级1 | 优先级2 | 优先级3 | 最后 |
|---------|---------|---------|--------|------|
| ETF实时价格 | 腾讯API | 东方财富EMF | 雪球 | 昨收价 |
| ETF日线（上交所） | 腾讯API | BaoStock | - | - |
| ETF日线（深交所） | BaoStock | 腾讯API | - | - |
| ETF小时线 | 新浪scale=30 | - | - | - |
| 股票日线 | BaoStock | 东方财富EMF | Tushare | - |
| 股票分钟线 | AKShare | - | - | - |
| ETF基本信息 | 天天基金 | 腾讯API | 雪球 | - |

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
| 东方财富EMF | 3秒 | 6秒 | 随机 |
| 雪球API | 3秒 | 6秒 | 需Cookie |

### 12.2 缓存策略

| 数据类型 | TTL | 说明 |
|----------|-----|------|
| 实时价格 | 5分钟 | 盘中避免重复请求 |
| 日线历史 | 1小时 | 历史数据变动少 |
| 小时线 | 5分钟 | 盘中更新 |
| ETF基本信息 | 1天 | 变化不频繁 |

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

| 统一字段 | 腾讯API | 新浪API | BaoStock | 雪球 |
|----------|---------|---------|----------|------|
| code | 索引2 | 索引2 | code字段 | symbol字段 |
| date | 日线接口 | - | date字段 | - |
| name | 索引1 | 索引1 | - | name字段 |
| open | 日线[1] | - | open字段 | - |
| high | 日线[2] | - | high字段 | - |
| low | 日线[3] | - | low字段 | - |
| close | 日线[4] | 索引3 | close字段 | current字段 |
| volume | 日线[5] | volume字段 | volume字段 | volume字段 |

---

## 十四、测试脚本

详见: `scripts/test_datasources.py`

运行测试:
```bash
cd etf_strategy
python scripts/test_datasources.py
```

测试覆盖:
1. 腾讯实时行情
2. 新浪小时线
3. 天天基金基本信息
4. 东方财富基金历史
5. BaoStock ETF日线
6. 雪球基金页面
7. 百度百科ETF词条

---

## 十五、更新记录

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| v1.0 | 2026-05-27 | 初始版本 |
| v2.1 | 2026-05-30 | 新增雪球Xueqiu、百度百科两个数据源 |
| v2.0 | 2026-05-30 | 新增字段说明、天天基金接口、BaoStock示例 |

---

*文档版本: v2.1 | 更新: 2026-05-30*