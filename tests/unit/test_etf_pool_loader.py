#!/usr/bin/env python3
"""
ETF池加载器 - 单元测试
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main

# 添加项目路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data.etf_pool_loader import (
    ETFListLoader,
    validate_etf_pool,
    determine_exchange,
    get_default_pool_codes,
    get_default_tencent_codes,
    FALLBACK_ETF_CODES
)


class TestValidateETF(TestCase):
    """测试ETF池验证"""
    
    def test_validate_valid_pool(self):
        """测试合法池"""
        codes = ['510300', '588000', '512880']
        self.assertTrue(validate_etf_pool(codes))
    
    def test_validate_empty_pool(self):
        """测试空池"""
        self.assertFalse(validate_etf_pool([]))
    
    def test_validate_invalid_code(self):
        """测试无效代码（长度不对）"""
        codes = ['123', '12345', '1234567']
        self.assertFalse(validate_etf_pool(codes))
    
    def test_validate_tencent_format(self):
        """测试腾讯格式"""
        codes = ['sh510300', 'sz159919']
        self.assertTrue(validate_etf_pool(codes))
    
    def test_validate_mixed_format(self):
        """测试混合格式"""
        codes = ['510300', 'sh588000', 'sz159919']
        self.assertTrue(validate_etf_pool(codes))


class TestDetermineExchange(TestCase):
    """测试交易所判断"""
    
    def test_shanghai_codes(self):
        """上交所代码"""
        self.assertEqual(determine_exchange('510300'), 'sh')
        self.assertEqual(determine_exchange('510500'), 'sh')
        self.assertEqual(determine_exchange('588000'), 'sh')
        self.assertEqual(determine_exchange('515050'), 'sh')
    
    def test_shenzhen_codes(self):
        """深交所代码"""
        self.assertEqual(determine_exchange('159919'), 'sz')
        self.assertEqual(determine_exchange('159915'), 'sz')
        self.assertEqual(determine_exchange('159952'), 'sz')
    
    def test_with_prefix(self):
        """带前缀"""
        self.assertEqual(determine_exchange('sh510300'), 'sh')
        self.assertEqual(determine_exchange('sz159919'), 'sz')


class TestETFListLoader(TestCase):
    """测试ETFListLoader"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def test_load_from_file(self):
        # US-001 后：池文件已废弃，加载由数据库接管
        loader = ETFListLoader()
        codes = loader.load()
        self.assertIn('588000', codes)
    
    def test_load_with_comments(self):
        # US-085 后: 池大小变为 15（核心池）
        loader = ETFListLoader()
        codes = loader.load()
        self.assertEqual(len(codes), 15)
    
    def test_to_tencent_codes(self):
        # US-085 后: 15 只转腾讯格式（不含 510300，510300 是 excluded）
        loader = ETFListLoader()
        tencent_codes = loader.get_tencent_codes()
        self.assertEqual(len(tencent_codes), 15)
        
        # 510300 不在 core 池（excluded）
        self.assertNotIn('sh510300', tencent_codes)
        # 588000（核心池）应该在
        self.assertIn('sh588000', tencent_codes)


if __name__ == '__main__':
    main()