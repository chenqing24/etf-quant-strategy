#!/usr/bin/env python3
"""
数据预热脚本
============
ETF量化决策系统的数据预热环节

功能：
1. 14:25 执行预热，拉取实时价格
2. 将实时价格写入热数据层 (DataFacade.hot.set)
3. 支持命令行调用和定时任务集成

使用方式：
    # 命令行
    python scripts/prefetch_data.py
    
    # 作为模块
    from scripts.prefetch_data import prefetch_data
    prefetch_data()
"""

import sys
import os
import json
import time
import requests
from datetime import datetime
from typing import Dict, List, Optional

# 确保能导入src模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.manager import DataFacade
from src.data.fetcher import TencentETFetcher


class ETFDataPrefetcher:
    """ETF数据预热器
    
    职责：
    - 14:25 拉取实时价格
    - 更新热数据层
    - 生成预热状态报告
    """
    
    def __init__(self, data_dir: str = 'etf_data_live'):
        self.data_dir = data_dir
        self.fetcher = TencentETFetcher(data_dir)
        self.facade = DataFacade(data_dir)
        self.prefetch_time = datetime.now().isoformat()
    
    def get_realtime_price(self, code: str) -> Optional[Dict]:
        """获取单个ETF实时价格
        
        Args:
            code: ETF代码 (如 'sh510300')
            
        Returns:
            包含 price, change_pct, volume 的字典
        """
        try:
            # 腾讯实时价格接口
            url = f"https://qt.gtimg.cn/q={code}"
            response = requests.get(url, timeout=5)
            
            if response.status_code != 200:
                return None
            
            # 解析返回数据
            # 格式: v_510300="510300,3.856,3.807,3.869,3.798,3.856,78901234..."
            text = response.text.strip()
            if not text or '=' not in text:
                return None
            
            data_str = text.split('=')[1].strip('"')
            fields = data_str.split('~')
            
            if len(fields) < 32:
                return None
            
            # 提取关键字段
            # fields[0]: 标记
            # fields[1]: ETF名称
            # fields[2]: ETF代码
            # fields[3]: 当前价
            # fields[4]: 昨收
            # fields[5]: 今开
            # fields[6]: 最高
            # fields[7]: 最低
            # fields[32]: 涨跌幅 (百分比)
            # fields[36]: 成交量
            
            price = float(fields[3]) if fields[3] else 0
            prev_close = float(fields[4]) if fields[4] else price
            change_pct = float(fields[32]) if fields[32] else 0
            volume = float(fields[36]) if fields[36] else 0
            
            return {
                'price': price,
                'change_pct': change_pct,
                'volume': volume,
                'prev_close': prev_close,
            }
            
        except Exception as e:
            print(f"  获取 {code} 实时价格失败: {e}")
            return None
    
    def prefetch_all(self, etf_codes: List[str] = None, simple: bool = False) -> Dict:
        """预热所有ETF实时数据
        
        Args:
            etf_codes: ETF代码列表，默认使用TencentETFetcher的列表
            simple: 是否简版模式（禁用进度条输出）
            
        Returns:
            预热结果统计
        """
        if etf_codes is None:
            etf_codes = TencentETFetcher.get_etf_codes()
        
        results = {
            'total': len(etf_codes),
            'success': 0,
            'failed': 0,
            'details': [],
            'prefetch_time': self.prefetch_time,
        }
        
        if not simple:
            print(f"\n{'='*60}")
            print(f"📡 数据预热开始 - {self.prefetch_time}")
            print(f"{'='*60}")
            print(f"待预热ETF数量: {results['total']}")
            print()
        
        for i, code in enumerate(etf_codes, 1):
            if not simple:
                print(f"[{i}/{results['total']}] 预热 {code}...", end=" ")
            
            # 获取实时价格
            realtime = self.get_realtime_price(code)
            
            if realtime:
                # 写入热数据层
                pure_code = code.replace('sh', '').replace('sz', '')
                self.facade.hot.set(pure_code, realtime)
                
                results['success'] += 1
                results['details'].append({
                    'code': pure_code,
                    'price': realtime['price'],
                    'change_pct': realtime['change_pct'],
                    'status': 'success',
                })
                if not simple:
                    print(f"✅ {realtime['price']} ({realtime['change_pct']:+.2f}%)")
            else:
                results['failed'] += 1
                results['details'].append({
                    'code': code,
                    'status': 'failed',
                })
                if not simple:
                    print("❌")
            
            # 避免请求过快
            time.sleep(0.1)
        
        return results
    
    def generate_report(self, results: Dict) -> str:
        """生成预热状态报告
        
        Args:
            results: 预热结果
            
        Returns:
            报告文本
        """
        success_rate = (results['success'] / results['total'] * 100) if results['total'] > 0 else 0
        
        report = f"""
╔══════════════════════════════════════════════════════════════╗
║                    📊 数据预热状态报告                          ║
╠══════════════════════════════════════════════════════════════╣
║  预热时间: {results['prefetch_time']}                              ║
║  预热总数: {results['total']}                                          ║
║  成功: {results['success']}                                                ║
║  失败: {results['failed']}                                                  ║
║  成功率: {success_rate:.1f}%                                              ║
╠══════════════════════════════════════════════════════════════╣
║  热数据层状态:                                                  ║
"""
        
        # 添加热数据层信息
        lifecycle = self.facade.get_lifecycle_info()
        report += f"║  生命周期: {lifecycle['stage_desc']:<44}║\n"
        report += f"║  热数据条数: {lifecycle['hot_count']:<46}║\n"
        report += "╠══════════════════════════════════════════════════════════════╣\n"
        report += "║  实时价格明细:                                              ║\n"
        
        for detail in results['details'][:10]:  # 只显示前10条
            if detail['status'] == 'success':
                report += f"║  {detail['code']:<8} {detail['price']:<10.3f} {detail['change_pct']:+.2f}%                             ║\n"
        
        if len(results['details']) > 10:
            report += f"║  ... (还有 {len(results['details']) - 10} 条数据)                                       ║\n"
        
        report += "╚══════════════════════════════════════════════════════════════╝"
        
        return report


def prefetch_data(data_dir: str = 'etf_data_live') -> Dict:
    """预热入口函数
    
    Args:
        data_dir: 数据目录
        
    Returns:
        预热结果
    """
    prefetcher = ETFDataPrefetcher(data_dir)
    results = prefetcher.prefetch_all()
    report = prefetcher.generate_report(results)
    print(report)
    return results


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='ETF数据预热脚本')
    parser.add_argument('--data-dir', default='etf_data_live', help='数据目录')
    parser.add_argument('--codes', nargs='+', help='指定ETF代码列表')
    args = parser.parse_args()
    
    # 执行预热
    if args.codes:
        prefetcher = ETFDataPrefetcher(args.data_dir)
        results = prefetcher.prefetch_all(args.codes)
    else:
        results = prefetch_data(args.data_dir)
    
    # 返回状态码
    if results['failed'] > results['total'] * 0.1:  # 失败率超过10%
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()