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
        """测试从文件加载"""
        # 创建测试文件
        pool_file = Path(self.test_dir) / 'test_pool.txt'
        pool_file.write_text('''
# 测试池
ETF_POOL = [
    '510300',  # 沪深300
    '588000',  # 科创50
    '512880',  # 证券
]
''')
        
        loader = ETFListLoader(pool_file=str(pool_file))
        codes = loader.load()
        
        self.assertEqual(len(codes), 3)
        self.assertIn('510300', codes)
        self.assertIn('588000', codes)
        self.assertIn('512880', codes)
    
    def test_load_with_comments(self):
        """测试带注释的文件"""
        pool_file = Path(self.test_dir) / 'test_pool.txt'
        pool_file.write_text('''# ETF池
ETF_POOL = [
    '510300',  # 沪深300ETF华泰柏瑞
    '588000',  # 科创50ETF华夏
    '512170',  # 医疗ETF华宝
]
''')
        
        loader = ETFListLoader(pool_file=str(pool_file))
        codes = loader.load()
        
        self.assertEqual(len(codes), 3)
    
    def test_to_tencent_codes(self):
        """测试转换为腾讯格式"""
        pool_file = Path(self.test_dir) / 'test_pool.txt'
        pool_file.write_text('''
ETF_POOL = [
    '510300',
    '588000',
    '159919',
]
''')
        
        loader = ETFListLoader(pool_file=str(pool_file))
        tencent_codes = loader.get_tencent_codes()
        
        self.assertIn('sh510300', tencent_codes)
        self.assertIn('sh588000', tencent_codes)
        self.assertIn('sz159919', tencent_codes)
    
    def test_fallback_to_hardcode(self):
        """测试回退到硬编码"""
        loader = ETFListLoader(pool_file='/nonexistent/pool.txt')
        codes = loader.load()
        
        self.assertGreater(len(codes), 0)
        self.assertTrue(validate_etf_pool(codes))
    
    def test_caching(self):
        """测试缓存"""
        loader = ETFListLoader()
        codes1 = loader.load()
        codes2 = loader.load()
        
        self.assertEqual(codes1, codes2)
        self.assertIs(codes1, codes2)  # 同一对象
    
    def test_reload(self):
        """测试重新加载"""
        pool_file = Path(self.test_dir) / 'test_pool.txt'
        pool_file.write_text("ETF_POOL = [\n    '510300',\n]")
        
        loader = ETFListLoader(pool_file=str(pool_file))
        codes1 = loader.load()
        self.assertEqual(len(codes1), 1)
        
        # 修改文件
        pool_file.write_text("ETF_POOL = [\n    '510300',\n    '588000',\n]")
        
        # reload后重新加载
        loader.reload()
        codes2 = loader.load()
        self.assertEqual(len(codes2), 2)


class TestConvenienceFunctions(TestCase):
    """测试便捷函数"""
    
    def test_get_default_pool_codes(self):
        """测试获取默认池"""
        codes = get_default_pool_codes()
        self.assertGreater(len(codes), 0)
        self.assertTrue(validate_etf_pool(codes))
    
    def test_get_default_tencent_codes(self):
        """测试获取默认池（腾讯格式）"""
        codes = get_default_tencent_codes()
        self.assertGreater(len(codes), 0)
        
        # 检查格式
        for code in codes:
            self.assertTrue(
                code.startswith('sh') or code.startswith('sz'),
                f"无效格式: {code}"
            )


class TestIntegration(TestCase):
    """集成测试"""
    
    def test_load_real_pool(self):
        """测试加载真实池文件"""
        real_pool_file = PROJECT_ROOT / 'etf_data_live' / 'top500_target_pool.txt'
        
        if not real_pool_file.exists():
            self.skipTest("池文件不存在")
        
        loader = ETFListLoader(pool_file=str(real_pool_file))
        codes = loader.load()
        
        # 应该有15只ETF
        self.assertEqual(len(codes), 15)
        
        # 验证格式
        for code in codes:
            self.assertEqual(len(code), 6)
            self.assertTrue(code.isdigit())
        
        # 转换为腾讯格式
        tencent_codes = loader.get_tencent_codes()
        self.assertEqual(len(tencent_codes), 15)
        
        # 检查510300在列表中
        self.assertIn('sh510300', tencent_codes)


if __name__ == '__main__':
    main()