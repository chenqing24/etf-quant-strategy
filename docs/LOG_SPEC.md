# ETF量化系统 - 日志规范

> 统一输出控制，解决硬编码条件判断问题

## 1. 设计原则

### 1.1 分类分级
- **日志级别**：DEBUG / INFO / WARN / ERROR
- **输出级别**：SILENT / BRIEF / NORMAL / VERBOSE

### 1.2 格式统一
所有日志包含：时间戳、级别、模块名、消息

### 1.3 可配置
运行时可动态切换输出级别

---

## 2. 日志级别定义

| 级别 | 用途 | 钉钉 | 命令行 |
|------|------|------|--------|
| DEBUG | 详细调试信息 | ❌ | ✅ |
| INFO | 一般信息（含进度条） | ❌ | ✅ |
| WARN | 警告信息 | ✅ | ✅ |
| ERROR | 错误信息 | ✅ | ✅ |

### 2.1 输出级别定义

| 级别 | 输出内容 | 使用场景 |
|------|----------|----------|
| SILENT | 无输出 | 静默模式 |
| BRIEF | 仅决策结果 | 钉钉APP |
| NORMAL | 进度+决策 | 命令行默认 |
| VERBOSE | 全部信息 | 开发调试 |

---

## 3. 实现方案

### 3.1 日志模块

```python
# src/logger.py
import logging
from enum import Enum, auto
from typing import Optional
from functools import wraps

class LogLevel(Enum):
    DEBUG = 10
    INFO = 20
    WARN = 30
    ERROR = 40

class OutputLevel(Enum):
    SILENT = 0    # 完全静默
    BRIEF = 1     # 简版输出
    NORMAL = 2    # 正常输出
    VERBOSE = 3    # 详细输出

class ETFLogger:
    """ETF量化系统统一日志器"""
    
    _instance: Optional['ETFLogger'] = None
    _output_level = OutputLevel.NORMAL
    
    def __init__(self, name: str = 'etf'):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # 控制台处理器
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S'
        ))
        self.logger.addHandler(handler)
    
    @classmethod
    def get_instance(cls) -> 'ETFLogger':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def set_output_level(cls, level: OutputLevel):
        """设置输出级别"""
        cls._output_level = level
    
    def should_output(self, min_level: OutputLevel) -> bool:
        """判断是否应该输出"""
        return self._output_level.value >= min_level.value
    
    def debug(self, msg: str):
        if self.should_output(OutputLevel.VERBOSE):
            self.logger.debug(msg)
    
    def info(self, msg: str):
        if self.should_output(OutputLevel.NORMAL):
            self.logger.info(msg)
    
    def warn(self, msg: str):
        if self.should_output(OutputLevel.BRIEF):
            self.logger.warning(msg)
    
    def error(self, msg: str):
        if self.should_output(OutputLevel.BRIEF):
            self.logger.error(msg)
    
    def brief(self, msg: str):
        """简版输出（钉钉专用）"""
        if self.should_output(OutputLevel.BRIEF):
            # 不带格式前缀
            print(msg)
```

### 3.2 快捷函数

```python
# src/logger.py (续)

def get_logger() -> ETFLogger:
    """获取日志器实例"""
    return ETFLogger.get_instance()

def set_level(level: OutputLevel):
    """设置输出级别"""
    ETFLogger.set_output_level(level)

def print_brief(msg: str):
    """简版输出"""
    if ETFLogger.get_instance().should_output(OutputLevel.BRIEF):
        print(msg)
```

---

## 4. 使用规范

### 4.1 旧方式 vs 新方式

```python
# ❌ 旧方式（硬编码条件）
if not getattr(self, '_simple_mode', False):
    print(f"加载 {len(self.data)} 只ETF数据")

# ✅ 新方式（统一日志）
from src.logger import get_logger
log = get_logger()
log.debug(f"加载 {len(self.data)} 只ETF数据")
```

### 4.2 分级输出示例

```python
from src.logger import get_logger, OutputLevel

log = get_logger()

# DEBUG级别 - 开发时看
log.debug(f"原始数据: {len(data)} 条")

# INFO级别 - 正常进度
log.info(f"加载 {len(data)} 只ETF数据")

# WARN级别 - 警告信息
log.warn(f"数据不足500天，跳过: {code}")

# ERROR级别 - 错误信息
log.error(f"无法连接服务器: {e}")
```

### 4.3 简版输出（钉钉）

```python
from src.logger import print_brief

# 钉钉只需要决策结果
print_brief(f"## 📈 ETF量化决策 05-26")
print_brief(f"**🟢 买入** {code}")
print_brief(f"信号价: {price}")
```

---

## 5. 输出级别切换

### 5.1 命令行参数

```python
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--output', choices=['silent', 'brief', 'normal', 'verbose'],
                    default='normal', help='输出级别')
args = parser.parse_args()

from src.logger import set_level, OutputLevel
set_level(OutputLevel[args.output.upper()])
```

### 5.2 环境变量

```python
import os

output_env = os.getenv('ETF_OUTPUT_LEVEL', 'normal')
from src.logger import set_level, OutputLevel
set_level(OutputLevel[output_env.upper()])
```

### 5.3 配置文件

```json
// config.json
{
  "output_level": "brief"
}
```

---

## 6. 日志文件规范

### 6.1 文件输出

```python
# 每日日志文件
log_file = f"logs/etf_{datetime.now().strftime('%Y%m%d')}.log"

file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(name)s - %(message)s'
))
```

### 6.2 日志轮转

```python
from logging.handlers import TimedRotatingFileHandler

handler = TimedRotatingFileHandler(
    'logs/etf.log',
    when='midnight',
    interval=1,
    backupCount=30
)
```

---

## 7. 各模块日志使用

### 7.1 DataLoader

```python
from src.logger import get_logger

class DataLoader:
    def load(self, data_dir: str):
        log = get_logger()
        log.debug(f"开始加载数据: {data_dir}")
        
        data = {}
        for f in data_dir.glob('*.csv'):
            # ... 处理逻辑
            log.debug(f"加载 {f.stem}: {len(df)} 条")
        
        log.info(f"加载 {len(data)} 只ETF数据")
        return data
```

### 7.2 Selector

```python
class Selector:
    def select_etfs(self, data, config):
        log = get_logger()
        log.debug(f"训练期: {config.train_start} ~ {config.train_end}")
        
        # ... 选择逻辑
        log.info(f"选出 {len(selected)} 只ETF")
        
        return selected
```

### 7.3 DecisionEngine

```python
class DecisionEngine:
    def decide(self, date: str):
        log = get_logger()
        log.info(f"开始决策: {date}")
        
        # ... 决策逻辑
        
        log.info(f"决策结果: {result.action} {result.code}")
        return result
```

---

## 8. 日志格式标准

### 8.1 时间戳格式
```
HH:MM:SS [LEVEL] message
12:30:45 [INFO] 加载 54 只ETF数据
```

### 8.2 错误格式
```
12:30:45 [ERROR] 数据加载失败: FileNotFoundError
  File: src/data_loader.py:42
  Context: load('etf_data_50')
```

### 8.3 进度格式
```
12:30:45 [INFO] [1/3] 生成决策报告... OK
12:30:46 [INFO] [2/3] 分析建议... OK
12:30:47 [INFO] [3/3] 发送通知... OK
```

---

## 9. 最佳实践清单

- [ ] 所有 `print()` 替换为日志函数
- [ ] 设置默认输出级别为 NORMAL
- [ ] CLI 支持 `--output` 参数
- [ ] 日志目录存在并可写
- [ ] 错误信息包含上下文
- [ ] 敏感信息不记录日志

---

## 10. 修订历史

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-05-26 | v1.0 | 初始版本 |