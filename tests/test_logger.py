#!/usr/bin/env python3
"""日志模块单元测试"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest
from src.logger import (
    ETFLogger, OutputLevel, get_logger, set_level, print_brief, init_logger
)


class TestOutputLevel(unittest.TestCase):
    """测试输出级别枚举"""
    
    def test_level_order(self):
        """测试级别顺序"""
        self.assertLess(OutputLevel.SILENT.value, OutputLevel.BRIEF.value)
        self.assertLess(OutputLevel.BRIEF.value, OutputLevel.NORMAL.value)
        self.assertLess(OutputLevel.NORMAL.value, OutputLevel.VERBOSE.value)


class TestETFLogger(unittest.TestCase):
    """测试ETF日志器"""
    
    def setUp(self):
        # 重置单例状态
        ETFLogger._instance = None
        ETFLogger._output_level = OutputLevel.NORMAL
    
    def test_singleton(self):
        """测试单例模式"""
        logger1 = ETFLogger.get_instance()
        logger2 = ETFLogger.get_instance()
        self.assertIs(logger1, logger2)
    
    def test_default_level(self):
        """测试默认级别"""
        ETFLogger._instance = None
        logger = ETFLogger.get_instance()
        self.assertEqual(logger.get_output_level(), OutputLevel.NORMAL)
    
    def test_set_level(self):
        """测试设置级别"""
        ETFLogger.set_output_level(OutputLevel.BRIEF)
        self.assertEqual(ETFLogger.get_output_level(), OutputLevel.BRIEF)
        
        # 恢复默认
        ETFLogger.set_output_level(OutputLevel.NORMAL)
    
    def test_should_output_silent(self):
        """测试SILENT级别"""
        ETFLogger.set_output_level(OutputLevel.SILENT)
        logger = ETFLogger.get_instance()
        
        self.assertFalse(logger.should_output(OutputLevel.BRIEF))
        self.assertFalse(logger.should_output(OutputLevel.NORMAL))
        self.assertFalse(logger.should_output(OutputLevel.VERBOSE))
    
    def test_should_output_brief(self):
        """测试BRIEF级别"""
        ETFLogger.set_output_level(OutputLevel.BRIEF)
        logger = ETFLogger.get_instance()
        
        self.assertTrue(logger.should_output(OutputLevel.BRIEF))
        self.assertFalse(logger.should_output(OutputLevel.NORMAL))
        self.assertFalse(logger.should_output(OutputLevel.VERBOSE))
    
    def test_should_output_normal(self):
        """测试NORMAL级别"""
        ETFLogger.set_output_level(OutputLevel.NORMAL)
        logger = ETFLogger.get_instance()
        
        self.assertTrue(logger.should_output(OutputLevel.BRIEF))
        self.assertTrue(logger.should_output(OutputLevel.NORMAL))
        self.assertFalse(logger.should_output(OutputLevel.VERBOSE))
    
    def test_should_output_verbose(self):
        """测试VERBOSE级别"""
        ETFLogger.set_output_level(OutputLevel.VERBOSE)
        logger = ETFLogger.get_instance()
        
        self.assertTrue(logger.should_output(OutputLevel.BRIEF))
        self.assertTrue(logger.should_output(OutputLevel.NORMAL))
        self.assertTrue(logger.should_output(OutputLevel.VERBOSE))
    
    def test_init_logger(self):
        """测试初始化函数"""
        ETFLogger._instance = None
        logger = init_logger(OutputLevel.BRIEF)
        
        self.assertEqual(ETFLogger.get_output_level(), OutputLevel.BRIEF)
        
        # 恢复默认
        ETFLogger.set_output_level(OutputLevel.NORMAL)


class TestShortcutFunctions(unittest.TestCase):
    """测试快捷函数"""
    
    def setUp(self):
        # 重置单例状态
        ETFLogger._instance = None
        ETFLogger._output_level = OutputLevel.NORMAL
    
    def test_get_logger(self):
        """测试获取日志器"""
        logger = get_logger()
        self.assertIsInstance(logger, ETFLogger)
    
    def test_set_level(self):
        """测试设置级别"""
        set_level(OutputLevel.VERBOSE)
        self.assertEqual(ETFLogger.get_output_level(), OutputLevel.VERBOSE)
        
        # 恢复默认
        ETFLogger.set_output_level(OutputLevel.NORMAL)


if __name__ == '__main__':
    unittest.main()