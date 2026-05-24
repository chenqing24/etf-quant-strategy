#!/usr/bin/env python3
"""ETF量化决策 - 命令行入口"""
import argparse
import sys
from datetime import datetime, timedelta
from typing import Optional

# 确保能导入src模块
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.report_generator import generate_decision_report
from src.data_fetcher import TencentETFetcher
from src.trade_tracker import TradeTracker
from src.performance_analyzer import PerformanceAnalyzer
from src.notifier import SignalNotifier


class ETFDecisionEngine:
    """ETF量化决策引擎"""
    
    def __init__(self, 
                 data_dir: str = 'etf_data_live',
                 capital: float = 20000,
                 webhook_url: str = None):
        self.data_dir = data_dir
        self.capital = capital
        self.webhook_url = webhook_url
        
        self.fetcher = TencentETFetcher(data_dir)
        self.tracker = TradeTracker(data_dir)
        self.analyzer = PerformanceAnalyzer(data_dir)
        self.notifier = SignalNotifier(webhook_url=webhook_url)
    
    def run_daily_check(self):
        """每日检查"""
        print("\n" + "="*60)
        print(f"📅 每日检查 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("="*60)
        
        # 1. 更新数据
        print("\n[1/4] 更新数据...")
        try:
            self.fetcher.update_all(days=7)
        except Exception as e:
            print(f"  数据更新失败: {e}")
        
        # 2. 检查持仓状态
        print("\n[2/4] 检查持仓...")
        positions = self.tracker.get_holdings()
        
        if positions:
            print(f"  当前持仓: {len(positions)}只")
            for p in positions:
                print(f"    {p.code} {p.name}: 盈亏{p.pnl_pct:+.1f}%")
                
                # 检查止损/止盈
                if self.tracker.check_stop_loss(p.code, -5):
                    print(f"    ⚠️ 触发止损!")
                if self.tracker.check_take_profit(p.code, 8):
                    print(f"    ⚠️ 触发止盈!")
        else:
            print("  (空仓)")
        
        # 3. 检查是否需要调仓
        print("\n[3/4] 检查是否需要调仓...")
        need_rebalance = self.tracker.need_rebalance(10)
        
        if need_rebalance:
            print("  → 需要重新评估，执行完整策略...")
            return self.run_full_evaluation()
        else:
            print("  → 持仓正常，无需调仓")
        
        # 4. 绩效汇总
        print("\n[4/4] 绩效汇总...")
        perf = self.tracker.get_performance_summary()
        print(f"  总资产: {perf['current_capital']:,.0f}元")
        print(f"  累计盈亏: {perf['total_pnl']:+.1f}%")
        
        return {
            'action': 'hold',
            'message': '持仓正常，无需操作'
        }
    
    def run_full_evaluation(self):
        """完整策略评估"""
        print("\n" + "="*60)
        print("🔄 完整策略评估")
        print("="*60)
        
        # 1. 生成决策报告
        print("\n[1/3] 生成决策报告...")
        report = generate_decision_report(self.capital)
        
        # 保存报告
        report_file = f"etf_reports/report_{datetime.now().strftime('%Y%m%d')}.txt"
        os.makedirs('etf_reports', exist_ok=True)
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"  报告已保存: {report_file}")
        
        # 2. 提取关键建议
        print("\n[2/3] 分析建议...")
        # 简化解析，提取买入建议
        action = 'hold'
        new_code = None
        
        if '516050' in report and '首推' in report:
            # 检查是否已经在仓
            positions = self.tracker.get_holdings()
            codes = [p.code for p in positions]
            
            if '516050' not in codes:
                action = 'buy'
                new_code = '516050'
                print(f"  建议买入: 516050 科创成长")
        
        # 3. 发送通知
        print("\n[3/3] 发送通知...")
        if self.webhook_url:
            self.notifier.send_daily_summary({
                'action': action,
                'new_code': new_code,
                'report_file': report_file,
            })
        
        return {
            'action': action,
            'new_code': new_code,
            'report': report,
        }
    
    def execute_trade(self, code: str, action: str, price: float, quantity: int):
        """执行交易"""
        from .industry_mapping import INDUSTRY_MAPPING
        
        name = INDUSTRY_MAPPING.get(code, code)
        
        if action == 'buy':
            self.tracker.record_buy(code, name, price, quantity, '策略推荐')
            print(f"✓ 已记录买入: {code} {name}")
        else:
            pnl = (price - 1.0) * quantity  # TODO: 准确计算
            self.tracker.record_sell(code, price, pnl)
            print(f"✓ 已记录卖出: {code} {name}")
    
    def input_actual_result(self, code: str):
        """要求用户输入实际结果"""
        print("\n" + "="*60)
        print(f"📝 请输入 {code} 的实际交易结果")
        print("="*60)
        
        try:
            entry_price = float(input("  买入价格: "))
            exit_price = float(input("  卖出价格 (若未卖出则回车): ") or "0")
            quantity = int(input("  买入数量: "))
            
            if exit_price > 0:
                # 已卖出
                actual_pnl = (exit_price - entry_price) * quantity
                print(f"\n  实际盈亏: {actual_pnl:+.2f}元")
                
                # 更新记录
                trade = self.tracker.record_sell(code, exit_price, actual_pnl)
                self.tracker.update_performance(actual_pnl)
                
                print("✓ 已更新交易记录")
            else:
                # 持有中，更新买入价
                print("  记录为持仓...")
                
        except ValueError as e:
            print(f"  输入错误: {e}")
    
    def print_trade_history(self):
        """打印交易历史"""
        trades = self.tracker.load_trades()
        
        print("\n" + "="*60)
        print("📜 交易历史")
        print("="*60)
        
        for t in trades[-10:]:  # 最近10笔
            pnl_str = f" 盈亏:{t.actual_pnl:+.2f}元" if t.action == 'sell' else ""
            print(f"  {t.date} {t.code} {t.name} {t.action} "
                  f"价格:{t.price} 数量:{t.quantity}{pnl_str}")
        
        print()


def main():
    parser = argparse.ArgumentParser(description='ETF量化决策引擎')
    parser.add_argument('--mode', '-m', choices=['daily', 'eval', 'trade', 'history', 'perf'],
                       default='daily', help='运行模式')
    parser.add_argument('--capital', '-c', type=float, default=20000,
                       help='本金')
    parser.add_argument('--code', type=str, help='ETF代码')
    parser.add_argument('--action', type=str, choices=['buy', 'sell'], help='交易动作')
    parser.add_argument('--price', type=float, help='价格')
    parser.add_argument('--quantity', type=int, help='数量')
    parser.add_argument('--webhook', type=str, help='钉钉Webhook URL')
    
    args = parser.parse_args()
    
    # 初始化引擎
    engine = ETFDecisionEngine(
        capital=args.capital,
        webhook_url=args.webhook
    )
    
    # 执行
    if args.mode == 'daily':
        engine.run_daily_check()
    elif args.mode == 'eval':
        engine.run_full_evaluation()
    elif args.mode == 'trade':
        if args.code and args.action and args.price and args.quantity:
            engine.execute_trade(args.code, args.action, args.price, args.quantity)
        else:
            print("错误: 需要指定 --code --action --price --quantity")
    elif args.mode == 'history':
        engine.print_trade_history()
    elif args.mode == 'perf':
        engine.analyzer.print_summary()


if __name__ == '__main__':
    main()


# 使用示例:
"""
# 每日检查
python -m src.decision_cli -m daily

# 完整评估
python -m src.decision_cli -m eval

# 记录交易
python -m src.decision_cli -m trade --code 516050 --action buy --price 1.384 --quantity 13000

# 查看历史
python -m src.decision_cli -m history

# 绩效分析
python -m src.decision_cli -m perf
"""


__all__ = ['ETFDecisionEngine', 'main']