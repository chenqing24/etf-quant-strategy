# ETF池管理规范

> 管理ETF目标池的配置文件、加载机制、更新流程
> 版本: v1.0 | 创建: 2026-05-30

---

## 一、核心概念

### 什么是ETF池
ETF池是策略执行的目标ETF列表，定义了系统关注的所有标的。

### 配置文件
```
etf_data_live/top500_target_pool.txt
```

### 配置格式
```python
# 筛选标准：成交额>=10亿，规模>=10亿
# 排除：货币基金、债券基金、QDII海外、商品ETF
# 仅保留：宽基指数+行业ETF，同主题去重

ETF_POOL = [
    '510300',  # 沪深300ETF华泰柏瑞
    '588000',  # 科创50ETF华夏
    # ...
]
```

---

## 二、文件规范

| 字段 | 说明 |
|------|------|
| `ETF_POOL` | 必须定义为 Python 列表 |
| 元素 | 纯数字代码（如 `'510300'`），不带前缀 |
| 注释 | 包含筛选标准、排除条件、保留条件 |

---

## 三、代码层设计

### 3.1 池加载优先级

```python
# 优先级从高到低
1. etf_data_live/top500_target_pool.txt  # 项目内池文件
2. /path/to/custom_pool.txt              # 自定义池文件（通过参数指定）
3. src/data/fetcher.py 内硬编码列表      # 默认列表（兜底）
```

### 3.2 加载器接口

```python
class ETFListLoader:
    """ETF池加载器"""
    
    def load(self, pool_file: str = None) -> List[str]:
        """
        加载ETF列表
        
        Args:
            pool_file: 池文件路径，None则使用默认路径
            
        Returns:
            ETF代码列表（纯数字，如 ['510300', '588000', ...]）
        """
    
    def to_tencent_codes(self, codes: List[str]) -> List[str]:
        """
        转换为腾讯格式（加 sh/sz 前缀）
        
        Args:
            codes: 纯数字代码
            
        Returns:
            腾讯格式代码（如 ['sh510300', 'sh588000', ...]）
        """
```

### 3.3 与 TencentETFetcher 集成

```python
# fetcher.py 的 get_etf_codes() 需要：
# 1. 优先调用 ETFListLoader 读取池文件
# 2. 无池文件才用硬编码
# 3. 结果缓存
```

---

## 四、模块依赖

```
ETFListLoader (src/data/etf_pool_loader.py)
       │
       ▼
TencentETFetcher.get_etf_codes()
       │
       ▼
prefetch_data.py (预热)
decision.py (决策)
```

---

## 五、更新流程

### 5.1 手动更新

```bash
# 1. 执行筛选脚本
python scripts/filter_top500_target.py

# 2. 查看输出
cat etf_data_live/top500_target_pool.txt

# 3. 提交代码
git add etf_data_live/top500_target_pool.txt
git commit -m "chore: 更新ETF目标池"
```

### 5.2 自动更新（未来）

```bash
# 每日定时任务
0 15 * * 1-5 python -m src.cli.main -m update_pool
```

---

## 六、数据契约

### 6.1 输入契约（池文件）

| 字段 | 类型 | 约束 |
|------|------|------|
| ETF_POOL | list | 非空 |
| 元素 | str | 6位数字 |
| 重复 | - | 不允许 |

### 6.2 输出契约（加载结果）

| 字段 | 类型 | 说明 |
|------|------|------|
| codes | list | 纯数字代码 |
| with_prefix | list | 腾讯格式代码 |

### 6.3 验证函数

```python
def validate_etf_pool(codes: List[str]) -> bool:
    """验证ETF池合法性"""
    if not codes:
        return False
    for code in codes:
        if not (isinstance(code, str) and len(code) == 6 and code.isdigit()):
            return False
    return len(codes) == len(set(codes))
```

---

## 七、异常处理

| 异常情况 | 处理方式 |
|----------|----------|
| 池文件不存在 | 回退到硬编码列表，记录警告日志 |
| 池文件格式错误 | 跳过该文件，回退到硬编码 |
| 列表为空 | 抛出 `ValueError` |
| 有重复代码 | 去重后返回，记录警告日志 |

---

## 八、文件清单

| 文件 | 说明 |
|------|------|
| `etf_data_live/top500_target_pool.txt` | 配置文件 |
| `src/data/etf_pool_loader.py` | 加载器 |
| `src/data/fetcher.py` | 集成点（修改） |
| `tests/unit/test_etf_pool_loader.py` | 单元测试 |

---

## 九、测试用例

```python
# tests/unit/test_etf_pool_loader.py

def test_load_from_file():
    """测试从文件加载"""
    loader = ETFListLoader()
    codes = loader.load()
    assert len(codes) > 0
    assert '510300' in codes

def test_to_tencent_codes():
    """测试转换为腾讯格式"""
    loader = ETFListLoader()
    codes = ['510300', '588000']
    tencent_codes = loader.to_tencent_codes(codes)
    assert 'sh510300' in tencent_codes
    assert 'sh588000' in tencent_codes

def test_validate_pool():
    """测试池验证"""
    from src.data.etf_pool_loader import validate_etf_pool
    assert validate_etf_pool(['510300', '588000']) == True
    assert validate_etf_pool([]) == False
    assert validate_etf_pool(['123']) == False
```