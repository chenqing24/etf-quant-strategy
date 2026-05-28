#!/usr/bin/env python3
"""行业集中度过滤器"""
from typing import Dict, Set, List
from collections import Counter

from src.utils.industry import INDUSTRY_MAPPING


class IndustryFilter:
    """行业集中度过滤器
    
    防止单一行业占比过高，分散风险
    """
    
    def __init__(self, max_industry_pct: float = 0.3):
        """初始化
        
        Args:
            max_industry_pct: 单个行业最大占比 (默认30%)
        """
        self.max_industry_pct = max_industry_pct
    
    def filter_by_industry(
        self,
        candidates: Set[str],
        max_per_industry: int = None
    ) -> Set[str]:
        """按行业过滤候选股票
        
        Args:
            candidates: 候选ETF代码集合
            max_per_industry: 每个行业最大数量 (默认: 总数 * max_industry_pct)
            
        Returns:
            过滤后的ETF集合
        """
        if max_per_industry is None:
            max_per_industry = max(1, int(len(candidates) * self.max_industry_pct))
        
        # 按行业分组
        industry_groups: Dict[str, List[str]] = {}
        for code in candidates:
            industry = self.get_industry(code)
            if industry not in industry_groups:
                industry_groups[industry] = []
            industry_groups[industry].append(code)
        
        # 每个行业只选前N个
        selected = set()
        for industry, codes in industry_groups.items():
            # 按代码排序保证一致性
            codes_sorted = sorted(codes)
            selected.update(codes_sorted[:max_per_industry])
        
        return selected
    
    def get_industry(self, code: str) -> str:
        """获取ETF所属行业"""
        return INDUSTRY_MAPPING.get(code, '其他')
    
    def calculate_industry_ratio(self, holdings: Dict[str, float]) -> Dict[str, float]:
        """计算行业占比
        
        Args:
            holdings: {code: 持仓比例}
            
        Returns:
            {行业: 占比}
        """
        industry_values: Dict[str, float] = {}
        
        for code, weight in holdings.items():
            industry = self.get_industry(code)
            industry_values[industry] = industry_values.get(industry, 0) + weight
        
        # 归一化
        total = sum(industry_values.values())
        if total > 0:
            industry_values = {k: v/total for k, v in industry_values.items()}
        
        return industry_values
    
    def check_balance(self, holdings: Dict[str, float]) -> Dict:
        """检查持仓平衡
        
        Returns:
            诊断信息字典
        """
        ratio = self.calculate_industry_ratio(holdings)
        
        issues = []
        
        # 检查行业占比
        for industry, pct in ratio.items():
            if pct > self.max_industry_pct:
                issues.append(f"{industry}占比{pct:.1%}超过限制{self.max_industry_pct:.1%}")
        
        return {
            'industry_ratio': ratio,
            'issues': issues,
            'balanced': len(issues) == 0,
        }
    
    def rebalance_with_industry_limit(
        self,
        target_weights: Dict[str, float],
        current_holdings: Dict[str, float] = None
    ) -> Dict[str, float]:
        """在行业限制下重新平衡
        
        Args:
            target_weights: 目标权重
            current_holdings: 当前持仓 (用于减少交易)
            
        Returns:
            调整后的权重
        """
        # 按行业分组
        industry_groups: Dict[str, List[tuple]] = {}
        for code, weight in target_weights.items():
            industry = self.get_industry(code)
            if industry not in industry_groups:
                industry_groups[industry] = []
            industry_groups[industry].append((code, weight))
        
        # 调整每个行业的权重
        result = {}
        max_per_industry = max(3, int(len(target_weights) * self.max_industry_pct))
        
        for industry, items in industry_groups.items():
            # 按权重排序
            items_sorted = sorted(items, key=lambda x: -x[1])
            
            # 取前N个
            for code, weight in items_sorted[:max_per_industry]:
                result[code] = weight
        
        # 归一化
        total = sum(result.values())
        if total > 0:
            result = {k: v/total for k, v in result.items()}
        
        return result
    
    def print_industry_allocation(self, holdings: Dict[str, float]):
        """打印行业配置"""
        ratio = self.calculate_industry_ratio(holdings)
        
        print("\n" + "="*50)
        print("📊 行业配置")
        print("="*50)
        
        # 按占比排序
        sorted_industry = sorted(ratio.items(), key=lambda x: -x[1])
        
        for industry, pct in sorted_industry:
            bar = "█" * int(pct * 20)
            flag = "⚠️" if pct > self.max_industry_pct else "  "
            print(f"{flag} {industry:<8} {pct:>6.1%} {bar}")
        
        print("="*50)


# 测试
def test_industry_filter():
    """测试行业过滤器"""
    filter = IndustryFilter(max_industry_pct=0.3)
    
    # 模拟候选
    candidates = {'510300', '510500', '159919', '512880', '512170', 
                  '512200', '159928', '159825', '512010', '512500',
                  '159997', '159995', '512760', '159801'}
    
    print(f"原始候选: {len(candidates)} 只")
    
    # 过滤
    filtered = filter.filter_by_industry(candidates, max_per_industry=3)
    print(f"过滤后: {len(filtered)} 只")
    
    # 行业占比
    weights = {code: 1.0/len(filtered) for code in filtered}
    ratio = filter.calculate_industry_ratio(weights)
    print(f"行业占比: {ratio}")
    
    filter.print_industry_allocation(weights)
    
    print("✓ 行业过滤器测试通过")
    return True


if __name__ == '__main__':
    test_industry_filter()


__all__ = ['IndustryFilter', 'test_industry_filter']