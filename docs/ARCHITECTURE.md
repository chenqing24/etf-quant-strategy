# 热冷数据分离架构 v2.0

> US-002 数据分层管理方案 | ETF量化决策系统
> 更新：存储层 CSV → SQLite，增加 DataSourceRouter 采集路由器

## 1. 概述

本架构将数据分为三层分离管理：
- **热数据层 (Hot)**: 今日实时价格，内存缓存，盘中持续更新
- **冷数据层 (Cold)**: 历史数据，SQLite持久化，归档后只读
- **采集层 (Fetch)**: 通过 DataSourceRouter 统一访问外部API

### 核心约束
- **禁止裸 requests.get**：所有外部API请求必须经过 DataSourceRouter
- **统一随机等待**：所有请求经过 RateLimiter(2-5秒随机)
- **统一缓存**：内存缓存5分钟TTL，避免重复请求

## 2. 存储结构

```
etf_data_live/
├── hot/                    # 热数据层（每日重建，JSON）
│   ├── 510300.json
│   └── ...
├── etf.db                 # 冷数据层（SQLite主库）
│   ├── daily              # 日线数据
│   ├── hourly             # 小时线（信号参考）
│   ├── min30              # 30分钟线（股票扩展）
│   ├── metadata           # 标的属性缓存
│   └── trades             # 交易记录
├── today_realtime.json    # 今日实时汇总
├── etf_trades.json        # 交易记录（兼容）
└── etf_performance.json   # 绩效数据
```

## 3. SQLite表结构

### daily（日线数据）
```sql
CREATE TABLE daily (
    code TEXT,
    date TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    UNIQUE(code, date) ON CONFLICT REPLACE,
    INDEX idx_code_date ON (code, date)
);
```

### hourly（小时线，仅信号参考）
```sql
CREATE TABLE hourly (
    code TEXT,
    timestamp TEXT,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    UNIQUE(code, timestamp) ON CONFLICT REPLACE,
    INDEX idx_code_ts ON (code, timestamp)
);
```

### metadata（标的属性缓存）
```sql
CREATE TABLE metadata (
    code TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    list_date TEXT,
    updated_at TEXT
);
```

## 4. 数据源路由规则

所有数据请求必须通过 DataSourceRouter：

| 数据类型 | 主力源 | 备源1 | 备源2 | 最后备源 |
|---------|-------|-------|-------|----------|
| **ETF日线（上交所）** | 腾讯API | Tushare | — | — |
| **ETF日线（深交所）** | BaoStock | Tushare | — | — |
| **ETF实时价格** | 新浪 | BaoStock | 东方财富EMF | **浏览器搜索** |
| ETF小时线 | 新浪scale=30 | — | — | — |
| 股票日线 | BaoStock | Tushare | — | — |
| 股票分钟 | AKShare | — | — | — |

### 浏览器搜索备源

当所有API数据源都失败时，使用Chrome浏览器访问搜索引擎获取实时信息：

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | 打开Chrome | 访问搜索引擎 |
| 2 | 搜索ETF代码 | 如"159806 新能源车" |
| 3 | 解析搜索结果 | 提取实时价格 |

### 实测结果（2026-05-27）

| 数据源 | 159806（深交所） | 510300（上交所） |
|--------|------------------|------------------|
| 新浪实时 | ❌ FAILED | ❌ 不可用 |
| 腾讯日线 | ❌ 无数据 | ✅ 301条 |
| BaoStock | ✅ 成功 | ✅ 成功 |

**结论**：BaoStock对深交所ETF（159xxx）支持最好，腾讯API对上证ETF（510xxx）支持最好

### 小时线定位约束
- **仅作信号增强**，不能单独触发交易决策
- 工作流：小时线信号 → 回测验证 → 日线决策

## 5. 三层架构

```
                    ┌──────────────────────┐
                    │      上层模块         │
                    │ (评分/报告/校验/交易)  │
                    └──────────┬───────────┘
                               │  统一契约
                               ▼
                    ┌──────────────────────┐
                    │     DataFacade        │
                    │   (唯一统一入口)       │
                    └──┬───────────┬───────┘
                       │           │
                       ▼           ▼
            ┌──────────────┐  ┌──────────────┐
            │ HotDataManager│  │ ColdDataManager│
            │  (内存JSON)   │  │  (SQLite)     │
            └──────────────┘  └──────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │   DataSourceRouter   │
                    │  (采集路由器)         │
                    └──┬───────────┬───────┘
                       │           │
         ┌─────────────┼───────────┼─────────────┐
         ▼            ▼           ▼             ▼
    ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
    │ 腾讯API │ │ 新浪API │ │Tushare  │ │BaoStock │
    └─────────┘ └─────────┘ └─────────┘ └─────────┘
                       │                    │
                       │                    │
                  ┌────┴────┐        ┌─────┴────┐
                  │ AKShare │        │东方财富EMF│ ← 备源
                  └─────────┘        └──────────┘
                                          │
                                   ┌──────┴──────┐
                                   │ 浏览器搜索   │ ← 最后备源
                                   │ (Chrome)    │
                                   └─────────────┘
```

## 6. DataSourceRouter

```python
class DataSourceRouter:
    """采集路由器 - 唯一外部数据入口"""
    
    # 数据源配置（优先级从高到低）
    SOURCES = {
        'realtime': 'sina',           # 1. 新浪（优先）
        'realtime_backup': 'browser', # 2. 浏览器搜索
        'realtime_last': 'emf',       # 3. 东方财富EMF（最后）
        'daily': 'tencent',           # 1. 腾讯API（优先）
        'daily_backup': 'tushare',    # 2. Tushare
        'hourly': 'sina',             # 1. 新浪（优先）
        'stock_min': 'akshare',       # 1. AKShare
        'stock_daily': 'baostock',    # 1. BaoStock
    }
    
    def __init__(self):
        self._cache = {}          # 统一缓存（内存）
        self._rate_limiter = RateLimiter(interval=(2, 5))
    
    def fetch(self, data_type: str, codes: List[str], **kwargs) -> Dict:
        """统一采集接口，带5分钟缓存TTL + 2-5秒随机等待"""
        ...
```

### RateLimiter（限速器）
```python
class RateLimiter:
    def __init__(self, interval=(2, 5)):
        self.interval = interval  # 随机2-5秒
    
    def wait(self):
        time.sleep(random.uniform(*self.interval))
```

## 7. DataFacade 接口

```python
class DataFacade:
    """数据层唯一统一入口"""
    
    # ===== 热数据 =====
    def get_realtime(self, codes: List[str]) -> Dict[str, RealtimeRecord]:
        """获取实时价格（新浪），5分钟缓存"""
    
    # ===== 冷数据（SQLite）=====
    def get_daily(self, code: str, days: int = 60) -> pd.DataFrame:
        """获取日线数据（SQLite优先，降级腾讯API）"""
    
    def get_hourly(self, code: str, days: int = 30) -> pd.DataFrame:
        """获取小时线数据（新浪），is_signal_only=True"""
    
    def get_daily_batch(self, codes: List[str], date: str) -> pd.DataFrame:
        """批量获取某日多只ETF日线（用于市场情绪聚合）"""
    
    # ===== 合并数据 =====
    def get_merged(self, code: str) -> MergedRecord:
        """合并热+冷数据，用于评分"""
    
    def get_with_signal(self, code: str) -> SignalRecord:
        """合并热+冷+小时线，用于信号验证"""
    
    # ===== 采集触发 =====
    def prefetch(self, codes: List[str], data_types: List[str] = None):
        """预采集数据（定时任务用）"""
```

### 接口约束
| 约束 | 说明 |
|------|------|
| 禁止裸调API | 上层必须通过 DataFacade，不得 requests.get |
| 统一缓存 | 所有数据先查缓存（5分钟TTL） |
| 统一等待 | 所有请求经过 RateLimiter(2-5秒) |
| 多源降级 | 主源失败时自动切换备源，上层无感知 |
| 东方财富末位 | EMF仅作为最后的备源，避免频繁调用 |

## 8. 生命周期阶段

```
┌─────────────────────────────────────────────────────────────┐
│                    数据生命周期                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   [9:30]          [15:00]         [15:30]        [次日9:30] │
│      │               │              │               │      │
│      ▼               ▼              ▼               ▼      │
│  ┌────────┐    ┌──────────┐   ┌─────────┐   ┌───────────┐  │
│  │ TRADE  │───▶│ CLOSING  │──▶│MIGRATED │───▶│  NEW DAY  │  │
│  │ 盘中   │    │ 收盘确认  │   │  已归档  │   │  重置热层  │  │
│  └────────┘    └──────────┘   └─────────┘   └─────────┘  │
│      │               │              │               │      │
│      ▼               ▼              ▼               ▼      │
│   热数据更新    等待确认        迁移至SQLite    热层重建    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 迁移流程
```
1. 触发：15:30后自动 或 手动调用 facade.migrate()
2. 遍历热数据目录 hot/*.json
3. 每条记录写入 etf.db daily 表（UNIQUE约束去重）
4. 清空热数据目录
5. 更新生命周期状态为 MIGRATED
```

## 9. 与现有系统集成

### 数据采集
```python
# ❌ 旧方式（禁止）
requests.get('https://hq.sinajs.cn/list=sh510300')

# ✅ 新方式
router = DataSourceRouter()
data = router.fetch('realtime', ['sh510300'])
```

### 评分系统
```python
facade = DataFacade('etf_data_live')
for code in etf_codes:
    data = facade.get_merged(code)  # 热+冷合并
    score = calculate_7_factor_score(data)
```

### 定时任务
```bash
# 每日收盘后迁移到SQLite
30 15 * * 1-5 cd /path/etf_strategy && python -c "
from src.data.manager import DataFacade
DataFacade('etf_data_live').migrate()
"
```

## 10. 调用方约束

| 模块 | 当前状态 | 目标 |
|------|---------|------|
| decision.py | DataFacade + TencentETFetcher | DataFacade ✅ |
| report_generator.py | DataFacade | DataFacade ✅ |
| tracker.py | DataFacade + 腾讯API直调 | 仅DataFacade ⚠️ |
| validator.py | 腾讯/东财(末位)/新浪API直调 | 仅DataFacade ❌ |

## 11. 文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/data/manager.py` | Python | DataFacade + Hot/ColdDataManager |
| `src/data/fetcher.py` | Python | DataSourceRouter + 各适配器 |
| `etf_data_live/hot/` | 目录 | 热数据存储（JSON） |
| `etf.db` | SQLite | 冷数据主库 |
| `scripts/migrate_csv_to_sqlite.py` | 脚本 | CSV迁移脚本 |
| `docs/ARCHITECTURE.md` | 文档 | 本文档 |

## 12. 验收标准

- [ ] etf.db 建有 daily/hourly/min30/metadata 表，索引存在
- [ ] DataSourceRouter 是唯一外部数据入口（grep验证无裸requests.get）
- [ ] RateLimiter 强制随机2-5秒等待
- [ ] DataFacade.get_merged() 能合并热+冷数据
- [ ] DataFacade.migrate() 能触发热→SQLite迁移
- [ ] 生命周期包含：盘中更新 → 收盘确认 → 归档到SQLite
- [ ] 现有决策系统评分/报告功能正常
- [ ] 东方财富EMF仅作为备源，不优先调用
- [ ] **数据源实测：159806(深交所)用BaoStock，510300(上交所)用腾讯API**
- [ ] **浏览器搜索作为最后备源，所有API失败后使用**

---

*文档版本: v2.3 | 创建日期: 2026-05-25 | 更新: 2026-05-27 - 新增浏览器搜索作为最后备源*