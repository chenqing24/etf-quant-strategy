#!/usr/bin/env python3
"""ETF量化系统 - 统一日志器

解决硬编码条件判断问题，统一输出控制
"""
import logging
import sys
from enum import Enum, auto
from typing import Optional
from functools import wraps


class OutputLevel(Enum):
    """输出级别"""
    SILENT = 0    # 完全静默
    BRIEF = 1     # 简版输出
    NORMAL = 2    # 正常输出（含进度）
    VERBOSE = 3   # 详细输出（含调试）


class ETFLogger:
    """ETF量化系统统一日志器"""
    
    _instance: Optional['ETFLogger'] = None
    _output_level = OutputLevel.NORMAL
    
    def __init__(self, name: str = 'etf'):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # 避免重复添加handler
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(logging.DEBUG)
            handler.setFormatter(logging.Formatter(
                '%(asctime)s [%(levelname)s] %(message)s',
                datefmt='%H:%M:%S'
            ))
            self.logger.addHandler(handler)
    
    @classmethod
    def get_instance(cls) -> 'ETFLogger':
        """获取单例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def set_output_level(cls, level: OutputLevel):
        """设置输出级别"""
        cls._output_level = level
    
    @classmethod
    def get_output_level(cls) -> OutputLevel:
        """获取输出级别"""
        return cls._output_level
    
    def should_output(self, min_level: OutputLevel) -> bool:
        """判断是否应该输出"""
        return self._output_level.value >= min_level.value
    
    def _log(self, level: int, msg: str):
        """内部日志方法"""
        if level == logging.DEBUG:
            self.logger.debug(msg)
        elif level == logging.INFO:
            self.logger.info(msg)
        elif level == logging.WARNING:
            self.logger.warning(msg)
        elif level == logging.ERROR:
            self.logger.error(msg)
    
    def debug(self, msg: str):
        """调试信息（VERBOSE级别）"""
        if self.should_output(OutputLevel.VERBOSE):
            self.logger.debug(msg)
    
    def info(self, msg: str):
        """一般信息（NORMAL级别）"""
        if self.should_output(OutputLevel.NORMAL):
            self.logger.info(msg)
    
    def warn(self, msg: str):
        """警告信息（BRIEF级别）"""
        if self.should_output(OutputLevel.BRIEF):
            self.logger.warning(msg)
    
    def error(self, msg: str):
        """错误信息（BRIEF级别）"""
        if self.should_output(OutputLevel.BRIEF):
            self.logger.error(msg)
    
    def brief(self, msg: str):
        """简版输出（钉钉专用，无前缀）"""
        if self.should_output(OutputLevel.BRIEF):
            print(msg)


# 全局快捷函数
def get_logger() -> ETFLogger:
    """获取日志器实例"""
    return ETFLogger.get_instance()


def set_level(level: OutputLevel):
    """设置输出级别"""
    ETFLogger.set_output_level(level)


def print_brief(msg: str):
    """简版输出（钉钉专用）"""
    logger = get_logger()
    logger.brief(msg)


def init_logger(output_level: OutputLevel = OutputLevel.NORMAL) -> ETFLogger:
    """初始化日志器
    
    Args:
        output_level: 输出级别，默认NORMAL
        
    Returns:
        ETFLogger实例
    """
    ETFLogger.set_output_level(output_level)
    return ETFLogger.get_instance()


__all__ = [
    'ETFLogger',
    'OutputLevel',
    'get_logger',
    'set_level',
    'print_brief',
    'init_logger',
]