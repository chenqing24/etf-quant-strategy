#!/usr/bin/env python3
"""绩效分析 - 对比预期vs实际"""
import json
import pandas as pd
from datetime import datetime
from typing import Dict, List


class PerformanceAnalyzer:
    """绩效分析器"""
    
    def __init__(self, data_dir: str = '.'):
        self.data_dir = data_dir
        self.trades_file = f'{data_dir}/etf_trades.json'
        self.reports_dir = f'{data_dir}/etf_reports'
    
    def load_trades(self) -> List[Dict]:
        """加载交易记录"""
        try:
            with open(self.trades_file, 'r') as f:
                data = json.load(f)
                return data.get('trades', [])
        except:
            return []
    
    def analyze_trade(self, trade: Dict) -> Dict:
        """分析单笔交易"""
        analysis = {
            'code': trade['code'],
            'name': trade['name'],
            'date': trade['date'],
            'action': trade['action'],
            'price': trade['price'],
            'quantity': trade['quantity'],
        }
        
        if trade['action'] == 'buy':
            # 买入时的预期分析
            analysis['expected_exit_days'] = 10  # 假设持有10天
            analysis['expected_pnl_range'] = [-5, 15]  # 预期收益区间
        else:
            # 卖出时的实际vs预期
            analysis['actual_pnl'] = trade.get('actual_pnl', 0)
            # 这里需要从报告中读取预期
            analysis['expected_pnl'] = 0  # TODO: 从报告获取
            
            if analysis['actual_pnl'] > 0:
                analysis['result'] = '盈利'
            elif analysis['actual_pnl'] < 0:
                analysis['result'] = '亏损'
            else:
                analysis['result'] = '持平'
        
        return analysis
    
    def compare_with_benchmark(self, trades: List[Dict]) -> Dict:
        """与基准对比 (沪深300)"""
        # 简化的基准对比
        # 实际应该获取沪深300同期收益
        
        if not trades:
            return {}
        
        # 假设基准收益
        # TODO: 实际获取沪深300数据
        
        # 计算策略收益
        buy_trades = [t for t in trades if t['action'] == 'buy']
        sell_trades = [t for t in trades if t['action'] == 'sell']
        
        strategy_return = 0
        if sell_trades:
            total_pnl = sum(t.get('actual_pnl', 0) for t in sell_trades if t.get('actual_pnl'))
            # 简单计算
            initial = sum(t['amount'] for t in buy_trades[:len(sell_trades)])
            if initial > 0:
                strategy_return = total_pnl / initial * 100
        
        return {
            'strategy_return': strategy_return,
            'benchmark_return': 0,  # TODO: 填入沪深300收益
            'alpha': strategy_return,  # 超额收益
        }
    
    def generate_performance_report(self) -> str:
        """生成绩效报告"""
        trades = self.load_trades()
        
        if not trades:
            return "暂无交易记录"
        
        report = []
        report.append("="*60)
        report.append("📊 绩效分析报告")
        report.append("="*60)
        
        # 交易统计
        buy_count = sum(1 for t in trades if t['action'] == 'buy')
        sell_count = sum(1 for t in trades if t['action'] == 'sell')
        
        report.append(f"\n【交易统计】")
        report.append(f"  买入次数: {buy_count}")
        report.append(f"  卖出次数: {sell_count}")
        
        # 盈亏统计
        sell_trades = [t for t in trades if t['action'] == 'sell' and t.get('actual_pnl')]
        if sell_trades:
            wins = sum(1 for t in sell_trades if t['actual_pnl'] > 0)
            losses = sum(1 for t in sell_trades if t['actual_pnl'] < 0)
            total_pnl = sum(t['actual_pnl'] for t in sell_trades)
            
            report.append(f"\n【盈亏统计】")
            report.append(f"  盈利次数: {wins}")
            report.append(f"  亏损次数: {losses}")
            report.append(f"  胜率: {wins/(wins+losses)*100:.1f}%")
            report.append(f"  总盈亏: {total_pnl:+.2f}元")
        
        # 持仓分析
        from .trade_tracker import TradeTracker
        tracker = TradeTracker(self.data_dir)
        positions = tracker.load_positions()
        
        report.append(f"\n【当前持仓】")
        if positions:
            for p in positions:
                report.append(f"  {p['code']} {p['name']}: "
                            f"盈亏{p['pnl_pct']:+.1f}%, 持有{p['hold_days']}天")
        else:
            report.append("  (空仓)")
        
        # 与基准对比
        benchmark = self.compare_with_benchmark(trades)
        if benchmark:
            report.append(f"\n【基准对比】")
            report.append(f"  策略收益: {benchmark['strategy_return']:+.1f}%")
            report.append(f"  基准收益: {benchmark['benchmark_return']:+.1f}%")
            report.append(f"  超额收益: {benchmark['alpha']:+.1f}%")
        
        report.append("\n" + "="*60)
        
        return "\n".join(report)
    
    def print_summary(self):
        """打印汇总"""
        print(self.generate_performance_report())


def test_analyzer():
    """测试"""
    analyzer = PerformanceAnalyzer('.')
    print(analyzer.generate_performance_report())


if __name__ == '__main__':
    test_analyzer()


__all__ = ['PerformanceAnalyzer', 'test_analyzer']