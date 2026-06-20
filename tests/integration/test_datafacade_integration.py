#!/usr/bin/env python3
"""
集成测试：DataFacade 被决策流程使用

验证：
- B1: DataFacade.get_merged() 返回融合数据
- B2: report_generator 使用 DataFacade（非 DataLoader）
- B3: 决策报告使用实时价格（非过期数据）
- B4: E2E：决策流程端到端验证

来源：SOP-02 v1.1 架构一致性检查（B1-B4）
"""
import os
import sys
from datetime import datetime

import pytest

# 确保能导入src模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.data.manager import DataFacade
from src.analysis.report_generator import ETFReportGenerator


class TestDataFacadeIntegration:
    """DataFacade 集成测试"""
    
    @pytest.fixture
    def data_dir(self):
        """数据目录"""
        return 'etf_data_live'
    
    @pytest.fixture
    def facade(self, data_dir):
        """DataFacade 实例"""
        return DataFacade(data_dir)
    
    def test_b1_get_merged_returns_merged_data(self, facade):
        """B1: DataFacade.get_merged() 返回融合数据"""
        # 获取一只ETF的融合数据
        df = facade.get_merged('510300', days=60)
        
        # 验证返回的是 DataFrame
        assert not df.empty, "融合数据不应为空"
        assert 'date' in df.columns, "应包含 date 列"
        assert 'close' in df.columns, "应包含 close 列"
        assert 'price' in df.columns, "应包含 price 列（热数据）"
        assert 'change_pct' in df.columns, "应包含 change_pct 列（热数据）"
    
    def test_b1_hot_data_overrides_last_close(self, facade):
        """B1: 热数据覆盖最后一条 close 价格"""
        # 获取冷数据
        cold_df = facade.cold.get_daily('510300', limit=1)
        cold_close = cold_df.iloc[-1]['close']
        
        # 获取融合数据
        merged_df = facade.get_merged('510300', days=10)
        
        #验证最后一条的 close 被热数据价格覆盖
        hot_dict = facade.hot.get('510300')
        if hot_dict:
            assert merged_df.iloc[-1]['close'] == hot_dict['price'], \
                "融合数据的最后一条 close 应等于热数据价格"
    
    def test_b2_report_generator_uses_datafacade(self, data_dir):
        """B2: report_generator 使用 DataFacade（非 DataLoader）"""
        from src.analysis import report_generator as rg
        
        # 读取源码检查
        with open(os.path.join(os.path.dirname(rg.__file__), 'report_generator.py')) as f:
            content = f.read()
        
        # 验证：load_data 方法中使用 DataFacade
        assert 'DataFacade' in content, "report_generator 应导入 DataFacade"
        assert 'facade = DataFacade' in content, "load_data 应实例化 DataFacade"
        
        # 验证：load_data 不使用 DataLoader()
        assert 'DataLoader()' not in content, "load_data 不应使用 DataLoader()"
    
    def test_b3_decision_report_uses_realtime_price(self, data_dir):
        """B3: 决策报告使用实时价格（非过期数据）"""
        generator = ETFReportGenerator(data_dir=data_dir)
        
        # 加载数据
        latest = generator.load_data()
        
        #验证有数据
        assert len(generator.data) > 0, "应加载到 ETF 数据"
        
        # 检查至少一个 ETF 的最后一条有热数据价格
        has_realtime = False
        for code, df in generator.data.items():
            if len(df) > 0 and 'price' in df.columns:
                last_price = df.iloc[-1].get('price')
                if last_price and last_price > 0:
                    has_realtime = True
                    break
        
        assert has_realtime, "至少一个 ETF 应有热数据价格"
    
    def test_b4_e2e_decision_flow(self, data_dir):
        """B4: E2E 决策流程端到端验证"""
        # 1. 预热实时数据
        from scripts.prefetch_data import ETFDataPrefetcher
        prefetcher = ETFDataPrefetcher(data_dir)
        prefetch_result = prefetcher.prefetch_all(simple=True)
        assert prefetch_result['success'] > 0, "预热数据应成功"
        
        # 2. 生成决策报告
        generator = ETFReportGenerator(data_dir=data_dir)
        latest = generator.load_data()
        
        # 3. 分析市场
        market = generator.analyze_market()
        assert market is not None, "市场分析应返回结果"
        
        # 4. 验证有选中的 ETF
        assert len(generator.current_etfs) > 0, "应有选中的 ETF"


class TestDataFacadeCodeFormat:
    """DataFacade 代码格式测试"""
    
    def test_cold_codes_match_hot_files(self):
        """cold 代码列表应与 hot 文件匹配"""
        facade = DataFacade('etf_data_live')
        cold_codes = set(facade.cold.get_code_list())
        
        # 检查热数据文件
        hot_dir = os.path.join('etf_data_live', 'hot')
        if os.path.exists(hot_dir):
            hot_codes = set(
                f.replace('.json', '') 
                for f in os.listdir(hot_dir) 
                if f.endswith('.json')
            )
            
            # 如果有重叠的代码，验证热数据能正确获取
            common = cold_codes & hot_codes
            if common:
                for code in list(common)[:3]:  # 只检查前3个
                    hot = facade.hot.get(code)
                    assert hot is not None, f"代码 {code} 热数据应存在"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])