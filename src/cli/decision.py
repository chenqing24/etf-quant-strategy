#!/usr/bin/env python3
"""ETF量化决策 - 命令行入口"""
import argparse
import sys
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

# 确保能导入src模块
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.report_generator import generate_decision_report
from src.data.fetcher import TencentETFetcher
from src.trade.tracker import TradeTracker
from src.analysis.performance_analyzer import PerformanceAnalyzer
from src.notify.notifier import SignalNotifier
from src.data.manager import DataFacade
from src.notify.scenario import ScenarioAdapter, notify_decision
from src.utils.logger import init_logger, get_logger, OutputLevel

logger = get_logger()


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
        # 注意：钉钉发送已迁移到ScenarioAdapter
        self.notifier = SignalNotifier()
        self._etf_data = {}  # 缓存ETF数据用于趋势图
    
    def run_daily_check(self):
        """每日检查"""
        logger.info("=" * 60)
        logger.info(f"📅 每日检查 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        logger.info("=" * 60)
        
        # 0. 预热实时数据 (14:25环节)
        prefetch_result = self._prefetch_realtime_data()
        data_timestamp = prefetch_result['prefetch_time']
        logger.info(f"  数据更新时间: {data_timestamp}")
        
        # 1. 更新数据
        logger.info("[1/4] 更新数据...")
        try:
            self.fetcher.update_all(days=7)
        except Exception as e:
            logger.error(f"  数据更新失败: {e}")
        
        # 2. 检查持仓状态
        logger.info("[2/4] 检查持仓...")
        positions = self.tracker.get_holdings()
        
        if positions:
            logger.info(f"  当前持仓: {len(positions)}只")
            for p in positions:
                logger.info(f"    {p.code} {p.name}: 盈亏{p.pnl_pct:+.1f}%")
                
                # 检查止损/止盈
                if self.tracker.check_stop_loss(p.code, -5):
                    logger.warn(f"    ⚠️ 触发止损!")
                if self.tracker.check_take_profit(p.code, 8):
                    logger.warn(f"    ⚠️ 触发止盈!")
        else:
            logger.info("  (空仓)")
        
        # 3. 检查是否需要调仓
        logger.info("[3/4] 检查是否需要调仓...")
        need_rebalance = self.tracker.need_rebalance(10)
        
        if need_rebalance:
            logger.info("  → 需要重新评估，执行完整策略...")
            return self.run_full_evaluation()
        else:
            logger.info("  → 持仓正常，无需调仓")
        
        # 4. 绩效汇总
        logger.info("[4/4] 绩效汇总...")
        perf = self.tracker.get_performance_summary()
        logger.info(f"  总资产: {perf['current_capital']:,.0f}元")
        logger.info(f"  累计盈亏: {perf['total_pnl']:+.1f}%")
        
        return {
            'action': 'hold',
            'message': '持仓正常，无需操作'
        }
    
    def _prefetch_realtime_data(self, simple: bool = False) -> dict:
        """预热实时数据 (14:25环节)
        
        Args:
            simple: 是否简版模式（禁用进度条）
        Returns:
            预热结果
        """
        from scripts.prefetch_data import ETFDataPrefetcher
        
        prefetcher = ETFDataPrefetcher(self.data_dir)
        results = prefetcher.prefetch_all(simple=simple)
        
        # 返回预热时间和成功数量
        return {
            'prefetch_time': results.get('prefetch_time', datetime.now().isoformat()),
            'success_count': results.get('success', 0),
            'total_count': results.get('total', 0),
        }
    
    def _get_data_timestamp(self) -> str:
        """获取数据时间戳
        
        优先使用热数据层的时间戳（实时数据）
        其次使用历史数据最新日期
        """
        facade = DataFacade(self.data_dir)
        hot_count = facade.hot.count()
        
        if hot_count > 0:
            # 有热数据，使用热数据的最新时间戳
            hot_data = facade.hot.get_all()
            if hot_data:
                latest_timestamp = max(
                    record.timestamp for record in hot_data.values()
                )
                return f"{latest_timestamp} (实时)"
        
        # 无热数据，使用历史数据
        if self._etf_data:
            latest_date = max(df['date'].max() for df in self._etf_data.values())
            return f"{latest_date} (历史)"
        
        return "未知"
    
    def run_full_evaluation(self, silent: bool = False, simple: bool = False):
        """完整策略评估
        
        Args:
            silent: 是否静默模式（不发送钉钉，由cron的agent响应代替）
            simple: 是否简版输出（钉钉APP专用，禁用进度条）
        """
        # 保存原始日志级别
        from src.utils.logger import ETFLogger, OutputLevel
        original_level = ETFLogger.get_output_level()
        
        # 简版模式：暂时禁用日志输出
        if simple:
            ETFLogger.set_output_level(OutputLevel.SILENT)
        
        # 0. 预热实时数据 (14:25环节)
        prefetch_result = self._prefetch_realtime_data(simple=simple)
        data_timestamp = prefetch_result['prefetch_time']
        
        # 恢复日志级别（预热后输出）
        ETFLogger.set_output_level(original_level)
        
        logger.info("=" * 60)
        logger.info("🔄 完整策略评估")
        logger.info("=" * 60)
        logger.info(f"  数据更新时间: {data_timestamp}")
        logger.info("=" * 60)
        
        # 0. 检查数据新鲜度，如果过期则尝试更新
        from datetime import datetime
        data_freshness = '✅ 正常'
        data_warning = ''
        
        # 加载数据
        from src.data.loader import DataLoader
        loader = DataLoader()
        if simple:
            loader._simple_mode = True
            from src.core.selector import Selector
            Selector._simple_mode = True
        self._etf_data = loader.load('etf_data_live')
        logger.info(f"加载 {len(self._etf_data)} 只ETF数据")
        
        # 获取数据最新日期
        latest_data_date = None
        for code, df in self._etf_data.items():
            if 'date' in df.columns:
                max_date = pd.to_datetime(df['date']).max()
                if latest_data_date is None or max_date > latest_data_date:
                    latest_data_date = max_date
                break
        
        if latest_data_date:
            today = datetime.now().date()
            data_date = latest_data_date.date()
            data_age = (today - data_date).days
            
            if data_age == 0:
                data_freshness = '✅ 正常'
            elif 1 <= data_age <= 2:
                data_freshness = '⚠️ 数据略旧'
                data_warning = f'数据距今{data_age}天'
            else:
                data_freshness = '❌ 数据过期'
                data_warning = f'数据超过{data_age}天未更新'
                logger.warn(f"⚠️ 数据过期 ({data_age}天)，尝试更新...")
                
                # 尝试更新数据
                try:
                    self.fetcher.update_all(days=7)
                    logger.info("  数据更新成功")
                    # 重新加载数据
                    self._etf_data = loader.load('etf_data_live')
                    data_freshness = '✅ 已更新'
                    data_warning = ''
                except Exception as e:
                    logger.error(f"  数据更新失败: {e}")
        
        # 1. 生成决策报告
        logger.info("[1/3] 生成决策报告...")
        
        # 设置简版模式（传递给report_generator内部组件）
        from src.core.selector import Selector
        Selector._simple_mode = simple
        
        report = generate_decision_report(self.capital, simple=simple)
        
        # 保存报告
        report_file = f"etf_reports/report_{datetime.now().strftime('%Y%m%d')}.txt"
        os.makedirs('etf_reports', exist_ok=True)
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        logger.info(f"  报告已保存: {report_file}")
        
        # 2. 提取关键建议
        logger.info("[2/3] 分析建议...")
        # 简化解析，提取买入建议
        action = '观望'
        new_code = ''
        new_name = ''
        new_price = 0
        
        # 从报告中提取交易建议
        lines = report.split('\n')
        for i, line in enumerate(lines):
            if '今日交易建议' in line:
                # 往下找操作信息
                for j in range(i, min(i+10, len(lines))):
                    if '买入' in lines[j]:
                        action = '买入'
                        # 提取代码和名称
                        for k in range(j, min(j+5, len(lines))):
                            if '516050' in lines[k] or '515050' in lines[k] or '159' in lines[k]:
                                parts = lines[k].split()
                                for p in parts:
                                    if p.isdigit() and len(p) == 6:
                                        new_code = p
                                        # 找名称
                                        if k+1 < len(lines):
                                            name_line = lines[k+1]
                                            if '科创' in name_line or '科技' in name_line or '创新' in name_line or '工业' in name_line or '稀土' in name_line or '计算机' in name_line or '新能源' in name_line:
                                                new_name = name_line.strip()
                                # 找价格
                                for m in range(j, min(j+10, len(lines))):
                                    if '价格' in lines[m]:
                                        try:
                                            price_str = ''.join(c for c in lines[m] if c.isdigit() or c == '.')
                                            new_price = float(price_str) if price_str else 0
                                        except:
                                            pass
                        break
                break
        
        if action == '买入':
            positions = self.tracker.get_holdings()
            codes = [p.code for p in positions]
            if new_code in codes:
                action = '持仓'
                new_code = ''
        
        logger.info(f"  今日操作: {action} {new_code} {new_name}")
        
        # 3. 发送通知到钉钉
        logger.info("[3/3] 发送通知...")
        
        # 获取实时数据（按优先级：腾讯 → 东方财富 → 新浪）
        realtime = {}
        if new_code:
            try:
                from src.trade.validator import fetch_realtime_prices
                prices = fetch_realtime_prices([new_code])
                if new_code in prices:
                    rt_info = prices[new_code]
                    realtime = {
                        'price': rt_info.get('price'),
                        'change_pct': rt_info.get('pct'),
                        'volume': rt_info.get('volume'),
                        'source': rt_info.get('data_source', '实时API'),
                    }
                    logger.info(f"  实时价格: {realtime.get('price')} (来源: {realtime.get('source')})")
                else:
                    # API全部失败，使用昨收盘价
                    if self._etf_data and new_code in self._etf_data:
                        df = self._etf_data[new_code]
                        if len(df) > 0:
                            last_row = df.iloc[-1]
                            realtime = {
                                'price': last_row.get('close'),
                                'change_pct': 0,
                                'source': '昨收盘(API不可用)',
                            }
                            logger.info(f"  昨收盘价: {realtime.get('price')} (来源: {realtime.get('source')})")
            except Exception as e:
                logger.warn(f"  ⚠ 获取实时数据失败: {e}")
        
        # 生成趋势数据和指标
        trend_data = None
        indicators = None
        if new_code and self._etf_data and new_code in self._etf_data:
            try:
                from src.trend_chart import get_trend_summary
                from src.analysis.indicator import Indicator
                trend_data = get_trend_summary(self._etf_data[new_code], new_code, 5)
                
                # 计算技术指标
                df_ind = Indicator.calculate(self._etf_data[new_code])
                latest = df_ind.iloc[-1]
                indicators = {
                    'ma20': latest.get('ma20', 0),
                    'ma60': latest.get('ma60', 0),
                    'ma120': latest.get('ma120', 0),
                    'rsi_14': latest.get('rsi_14', 0),
                    'vol_ratio': latest.get('vol_ratio', 0),
                }
            except Exception as e:
                logger.warn(f"  ⚠ 数据处理失败: {e}")
        
        # 获取数据时间戳
        data_timestamp = self._get_data_timestamp()
        
        # 从报告中提取数据状态
        data_freshness = ''
        data_warning = ''
        for line in report.split('\n'):
            if '数据最新日期' in line:
                if '❌' in line:
                    data_freshness = '❌ 数据过期'
                elif '⚠️' in line:
                    data_freshness = '⚠️ 数据略旧'
                elif '✅' in line:
                    data_freshness = '✅ 正常'
            if '未更新' in line or '失真' in line:
                data_warning = line.strip()
        
        # 构建结果数据（供ScenarioAdapter使用）
        results = {
            'action': action,
            'code': new_code,
            'name': new_name,
            'price': new_price,
            'realtime': realtime,
            'indicators': indicators,
            'data_timestamp': data_timestamp,
            'data_freshness': data_freshness,
            'data_freshness_warning': data_warning,
        }
        
        # 发送通知（除非是静默模式）
        if not getattr(self, '_silent_mode', False):
            logger.info("准备发送钉钉通知...")
            # 根据simple参数决定场景
            if getattr(self, '_simple_mode', False):
                # 简版输出（钉钉APP）- 构建并发送
                adapter = ScenarioAdapter.for_mobile()
                message = adapter.build_report(results, report_file=None)
                print(message)  # 打印到控制台
                logger.info(f"报告内容: {message[:100]}...")
                # 发送钉钉通知
                success = adapter.send_report(message)
                logger.info(f"钉钉发送结果: {success}")
            else:
                # 使用新的ScenarioAdapter（钉钉移动端）
                adapter = ScenarioAdapter.for_mobile()
                adapter.build_and_send(results, report_file=None)
        
        # PC端控制台输出完整报告
        if report_file:
            adapter_pc = ScenarioAdapter.for_console()
            adapter_pc.build_report(results, report_file)
        
        return {
            'action': action,
            'new_code': new_code,
            'report': report,
        }
    
    def execute_trade(self, code: str, action: str, price: float, quantity: int):
        """执行交易"""
        from src.utils.industry import INDUSTRY_MAPPING
        
        name = INDUSTRY_MAPPING.get(code, code)
        
        if action == 'buy':
            self.tracker.record_buy(code, name, price, quantity, '策略推荐')
            logger.info(f"✓ 已记录买入: {code} {name}")
        else:
            pnl = (price - 1.0) * quantity  # TODO: 准确计算
            self.tracker.record_sell(code, price, pnl)
            logger.info(f"✓ 已记录卖出: {code} {name}")
    
    def input_actual_result(self, code: str):
        """要求用户输入实际结果"""
        logger.info("=" * 60)
        logger.info(f"📝 请输入 {code} 的实际交易结果")
        logger.info("=" * 60)
        
        try:
            entry_price = float(input("  买入价格: "))
            exit_price = float(input("  卖出价格 (若未卖出则回车): ") or "0")
            quantity = int(input("  买入数量: "))
            
            if exit_price > 0:
                # 已卖出
                actual_pnl = (exit_price - entry_price) * quantity
                logger.info(f"  实际盈亏: {actual_pnl:+.2f}元")
                
                # 更新记录
                trade = self.tracker.record_sell(code, exit_price, actual_pnl)
                self.tracker.update_performance(actual_pnl)
                
                logger.info("✓ 已更新交易记录")
            else:
                # 持有中，更新买入价
                logger.info("  记录为持仓...")
                
        except ValueError as e:
            logger.error(f"  输入错误: {e}")
    
    def print_trade_history(self):
        """打印交易历史"""
        trades = self.tracker.load_trades()
        
        logger.info("=" * 60)
        logger.info("📜 交易历史")
        logger.info("=" * 60)
        
        for t in trades[-10:]:  # 最近10笔
            pnl_str = f" 盈亏:{t.actual_pnl:+.2f}元" if t.action == 'sell' else ""
            logger.info(f"  {t.date} {t.code} {t.name} {t.action} "
                  f"价格:{t.price} 数量:{t.quantity}{pnl_str}")


def main():
    parser = argparse.ArgumentParser(description='ETF量化决策引擎')
    parser.add_argument('--mode', '-m', 
                       choices=['daily', 'eval', 'trade', 'history', 'perf', 'update_pool', 'export'],
                       default='daily', help='运行模式')
    parser.add_argument('--capital', '-c', type=float, default=20000,
                       help='本金')
    parser.add_argument('--code', type=str, help='ETF代码')
    parser.add_argument('--action', type=str, choices=['buy', 'sell'], help='交易动作')
    parser.add_argument('--price', type=float, help='价格')
    parser.add_argument('--quantity', type=int, help='数量')
    parser.add_argument('--webhook', type=str, help='钉钉Webhook URL')
    parser.add_argument('--silent', action='store_true', help='静默模式（不发送钉钉，由cron响应代替）')
    parser.add_argument('--simple', action='store_true', help='简版输出（钉钉APP专用）')
    parser.add_argument('--full', action='store_true', help='完整报告（PC端专用）')
    parser.add_argument('--output', choices=['silent', 'brief', 'normal', 'verbose'],
                       default='normal', help='输出级别')
    
    # ── US-005: 查询参数 ──────────────────────────────────────────
    parser.add_argument('--date', type=str,
                       help='查询日期 (YYYY-MM-DD / YYYY-MM / YYYY)')
    parser.add_argument('--filepath', type=str,
                       help='CSV导出路径 (mode=export)')
    # ─────────────────────────────────────────────────────────────
    
    args = parser.parse_args()
    
    # 初始化日志器
    output_level = OutputLevel[args.output.upper()]
    init_logger(output_level)
    
    # 初始化引擎
    engine = ETFDecisionEngine(
        capital=args.capital,
        webhook_url=args.webhook
    )
    
    # 设置静默模式
    if args.silent:
        engine._silent_mode = True
    
    # 设置简版模式（钉钉APP专用）
    if args.simple:
        engine._simple_mode = True
    
    # 执行
    if args.mode == 'daily':
        engine.run_daily_check()
    elif args.mode == 'eval':
        engine.run_full_evaluation(silent=args.silent, simple=args.simple)
    elif args.mode == 'trade':
        if args.code and args.action and args.price and args.quantity:
            engine.execute_trade(args.code, args.action, args.price, args.quantity)
        else:
            logger.error("错误: 需要指定 --code --action --price --quantity")
    elif args.mode == 'history':
        # US-005: 支持 date / code 过滤
        _run_history_query(engine, args)
    elif args.mode == 'perf':
        engine.analyzer.print_summary()
    elif args.mode == 'export':
        # US-005: CSV导出
        _run_export(engine, args)
    elif args.mode == 'update_pool':
        from src.etf_pool_updater import ETFListUpdater
        updater = ETFListUpdater('etf_pool.json')
        updater.run_full_update()


# ── US-005: 新增 CLI 子命令实现 ─────────────────────────────────

def _run_history_query(engine: ETFDecisionEngine, args):
    """
    US-005: 查询交易记录
    
    Examples:
        python -m src.decision_cli -m history
        python -m src.decision_cli -m history --date 20260525
        python -m src.decision_cli -m history --date 2026-05 --code 510300
    """
    trades = engine.tracker.query_trades(
        date=args.date,
        code=args.code,
        action=args.action,
    )
    
    print(f"\n{'=' * 80}")
    filter_note = f"(过滤: date={args.date}, code={args.code}, action={args.action})" if (args.date or args.code or args.action) else ""
    print(f"📜 交易历史 {filter_note}")
    print(f"{'=' * 80}")
    print(f"{'日期':<12} {'代码':<10} {'名称':<8} {'行为':<6} {'成交价':>8} {'数量':>6} "
          f"{'金额':>10} {'实时价':>8} {'偏差%':>7} {'RSI14':>7} {'涨幅%':>7} {'评分':>5}")
    print("-"*80)
    
    if not trades:
        print("  (无记录)")
        return
    
    for t in trades:
        note_pnl = f" 盈亏:{t.actual_pnl:+.2f}" if t.action == 'sell' else ""
        note_rt = (f" 实时:{t.realtime_price:.3f}" if t.realtime_price > 0
                   else "")
        note_dev = (f" 偏差:{t.price_deviation:+.2f}%" if t.price_deviation != 0
                    else "")
        note_rsi = (f" RSI:{t.rsi_14:.1f}" if t.rsi_14 > 0 else "")
        note_chng = (f" 涨幅:{t.day_change_pct:+.2f}%" if t.day_change_pct != 0
                     else "")
        note_score = f" 评分:{t.score}" if t.score > 0 else ""
        
        print(f"  {t.date:<10} {t.code:<10} {t.name:<8} {t.action:<6} "
              f"{t.price:>8.3f} {t.quantity:>6} {t.amount:>10.1f}"
              f"{note_rt}{note_dev}{note_rsi}{note_chng}{note_score}{note_pnl}")
    
    print("-"*80)
    print(f"  共 {len(trades)} 笔记录")


def _run_export(engine: ETFDecisionEngine, args):
    """
    US-005: 导出CSV
    
    Example:
        python -m src.decision_cli -m export --filepath trades.csv
    """
    filepath = args.filepath or 'etf_trades.csv'
    
    # 确保 data_dir 存在
    import os
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    
    count = engine.tracker.export_csv(filepath)
    print(f"\n✓ 导出完成: {filepath} ({count} 笔记录)")


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