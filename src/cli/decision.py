#!/usr/bin/env python3
"""
ETF量化决策 - 命令行入口

用途：
    - 运行每日量化投资决策
    - 生成决策报告（top_5 / top_10 / all）
    - 发送钉钉告警（含交易信号）
    - 生成交易快照（decision_snapshot.json）

被谁调用：
    - QwenPaw cron 定时任务（每日 14:30 工作日）
    - CLI 直接调用：`python -m src.cli.decision -m daily/eval`

功能说明：
    - 核心决策引擎：ETFDecisionEngine
    - 支持回测模式（-m backtest）和每日评估模式（-m daily/eval）
    - 读取 v8_sop 实验结果作为模型信息（训练期/ETF池/过拟合验证）
    - 当前打分逻辑使用通用 MA 趋势策略（待与 7 因子组合打通）

使用方式：
    # 每日评估（生成报告 + 发送钉钉）
    python -m src.cli.decision -m daily/eval
    
    # 回测模式
    python -m src.cli.decision -m backtest
    
    # 指定日期
    python -m src.cli.decision -m daily/eval --date 2026-06-01

依赖：
    - src.analysis.report_generator
    - src.data.fetcher (TencentETFetcher)
    - src.trade.tracker (TradeTracker)
    - src.notify.notifier (SignalNotifier)
    - src.data.manager (DataFacade)

注意事项：
    - 使用腾讯 API 获取实时行情
    - 钉钉告警包含买入/卖出信号
    - 决策快照保存到 etf_data_live/decision_snapshot.json
"""
import argparse
import sys
import time
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
from src.utils.execution_source import (
    ExecutionSource,
    add_source_argument,
    get_source_from_argv,
)
from src.utils.safety_gate import (
    require_force,
    add_dry_run_argument,
    SafetyGateError,
)
# US-003: Audit Logger
from src.utils.audit_logger import get_audit

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
            'codes': results.get('codes', []),
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
    
    def _parse_recommendation(self, report: str):
        """US-004: 通用报告解析器

        输入: report 文本
        输出: (action, code, name, price, quantity, stop_loss, stop_profit)

        解析规则：
        1. 【操作】买入 510300 沪深300ETF华泰柏瑞 3600股 → action=买入, code=510300, name=沪深300ETF华泰柏瑞, quantity=3600
        2. 【价格】4.966元 → price=4.966
        3. 【止损】-6% (4.668元) → stop_loss=4.668
        4. 【止盈】+10% (5.463元) → stop_profit=5.463

        通用：r'\b\d{6}\b' 匹配 6 位数字代码
        价格：r'\d+\.\d+' 匹配小数
        数量：r'\d+股' 匹配 N股
        """
        import re
        action = '观望'
        new_code = ''
        new_name = ''
        new_price = 0.0
        new_quantity = 0
        stop_loss_price = 0.0
        stop_profit_price = 0.0

        # 找到"今日交易建议"区块（US-004: 兼容多种报告格式）
        lines = report.split('\n')
        in_recommendation = False
        for i, line in enumerate(lines):
            # 进入建议区：遇到 今日交易建议 行 或 第一个 【操作】行
            if '今日交易建议' in line or ('【操作】' in line and not in_recommendation):
                in_recommendation = True
            if not in_recommendation:
                continue
            # US-004: 不在循环里 break（避免误判）
            # 改为：找到【价格】后立即记录（first-match-wins）

            # 1. 解析【操作】行
            if '【操作】' in line and '买入' in line:
                action = '买入'
                # 提取 6 位代码（US-004: 通用正则，移除硬编码）
                code_match = re.search(r'\b(\d{6})\b', line)
                if code_match:
                    new_code = code_match.group(1)
                # 提取名称（代码后到 NNNN股 之间的部分）
                name_match = re.search(r'\b\d{6}\b\s+(.+?)\s+\d+股', line)
                if name_match:
                    new_name = name_match.group(1).strip()
                # 提取数量
                qty_match = re.search(r'\d+股', line)
                if qty_match:
                    new_quantity = int(re.search(r'\d+', qty_match.group(0)).group(0))
                continue

            # 2. 解析【价格】行（US-004: first-match-wins，避免被实时价覆盖）
            if '【价格】' in line and new_price == 0.0:
                price_match = re.search(r'(\d+\.\d+)', line)
                if price_match:
                    new_price = float(price_match.group(1))
                continue

            # 3. 解析【止损】行（first-match-wins）
            if '【止损】' in line and stop_loss_price == 0.0:
                sl_match = re.search(r'\((\d+\.\d+)元\)', line)
                if sl_match:
                    stop_loss_price = float(sl_match.group(1))
                continue

            # 4. 解析【止盈】行（first-match-wins）
            if '【止盈】' in line and stop_profit_price == 0.0:
                sp_match = re.search(r'\((\d+\.\d+)元\)', line)
                if sp_match:
                    stop_profit_price = float(sp_match.group(1))
                continue

        # 5. 如果没找到名称，从 Repository 查（数据库是单一来源）
        if new_code and not new_name:
            try:
                from src.data.etf_pool_repository import ETFRepository
                new_name = ETFRepository().get_name(new_code) or new_code
            except Exception:
                new_name = new_code

        return action, new_code, new_name, new_price, new_quantity, stop_loss_price, stop_profit_price


    def _detect_market_mode(self) -> str:
        """US-006: 用 MarketRegimeDetector 基于市场结构判断

        Returns:
            'trend_up' | 'range_bound' | 'trend_down' | 'crash'
        """
        try:
            from src.analysis.market_regime import MarketRegimeDetector
            from src.data.loader import DataLoader

            # 走 DataLoader 统一入口
            loader = DataLoader()
            df = loader.load_single('510300', min_rows=1)

            if df is None or df.empty or len(df) < 130:
                logger.warning("510300 数据不足 130 天，默认震荡市")
                return 'range_bound'

            detector = MarketRegimeDetector()
            regime = detector.detect(df)
            return regime
        except Exception as e:
            logger.error(f"_detect_market_mode 失败: {e}")
            return 'range_bound'

    def _regime_to_label(self, regime: str) -> str:
        """US-006: 把 regime 翻译为中文标签"""
        from src.analysis.market_regime import REGIME_LABELS, REGIME_EMOJI
        label = REGIME_LABELS.get(regime, '震荡市')
        emoji = REGIME_EMOJI.get(regime, '📊')
        return f"{emoji} {label}"

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
        # 预热成功的ETF代码列表（用于只加载这些ETF）
        prefetch_codes = prefetch_result.get('codes', [])
        
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
        
        # 加载数据（只加载预热过的ETF）
        from src.data.loader import DataLoader
        loader = DataLoader()
        if simple:
            loader._simple_mode = True
            from src.core.selector import Selector
            Selector._simple_mode = True
        self._etf_data = loader.load(min_rows=100, codes=prefetch_codes)
        logger.info(f"使用预热池: {len(prefetch_codes)} 只ETF")
        
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
            else:
                # 数据不新鲜，尝试更新（最多2次）
                data_freshness = '⚠️ 数据略旧'
                data_warning = f'数据距今{data_age}天'
                logger.warn(f"⚠️ 数据略旧 ({data_age}天)，尝试更新...")
                
                update_success = False
                for attempt in range(2):
                    try:
                        self.fetcher.update_all(days=7)
                        # 重新加载数据
                        self._etf_data = loader.load(min_rows=100, codes=prefetch_codes)
                        # 重新检查数据新鲜度
                        latest_data_date_new = None
                        for code, df in self._etf_data.items():
                            if 'date' in df.columns:
                                max_date = pd.to_datetime(df['date']).max()
                                if latest_data_date_new is None or max_date > latest_data_date_new:
                                    latest_data_date_new = max_date
                                break
                        if latest_data_date_new:
                            new_data_date = latest_data_date_new.date()
                            new_data_age = (today - new_data_date).days
                            if new_data_age == 0:
                                data_freshness = '✅ 已更新'
                                data_warning = ''
                                logger.info(f"  数据更新成功 (原{data_age}天 → 今日)")
                                update_success = True
                                break
                            else:
                                logger.warn(f"  第{attempt+1}次更新后仍为{new_data_age}天")
                                if attempt < 1:
                                    logger.warn("  尝试第2次...")
                                else:
                                    data_freshness = '⚠️ 更新后仍略旧'
                                    data_warning = f'数据距今{new_data_age}天'
                    except Exception as e:
                        if attempt < 1:
                            logger.warn(f"  第{attempt+1}次更新失败: {e}，尝试第2次...")
                        else:
                            logger.error(f"  2次更新都失败: {e}")
                            data_freshness = '❌ 更新失败'
                            data_warning = f'数据距今{data_age}天，更新异常'
        
        # 1. 生成决策报告
        logger.info("[1/3] 生成决策报告...")

        # 设置简版模式（传递给report_generator内部组件）
        from src.core.selector import Selector
        Selector._simple_mode = simple

        # US-009: 传入 TradeTracker 让报告查持仓+现金
        from src.trade.tracker import TradeTracker
        tracker = TradeTracker('.')

        report = generate_decision_report(self.capital, simple=simple, tracker=tracker)

        # US-016: 报告幂等性 - 今日已生成则默认不覆盖 (除非 --force)
        report_file = f"etf_reports/report_{datetime.now().strftime('%Y%m%d')}.txt"
        os.makedirs('etf_reports', exist_ok=True)
        if os.path.exists(report_file) and not getattr(self, 'force', False):
            # 已存在且未要求覆盖：在报告开头追加"已生成 N 次"标识
            with open(report_file, 'r', encoding='utf-8') as f:
                existing = f.read()
            # 简单策略: 追加生成时间戳到文件末尾
            with open(report_file, 'a', encoding='utf-8') as f:
                f.write(f"\n\n[US-016] 再次生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')} "
                        f"(未覆盖原报告, 用 --force 强制覆盖)\n")
            logger.info(f"  报告已存在 (未覆盖): {report_file}")
            logger.info(f"  用 --force 强制覆盖")
        else:
            # 生成新报告 (或强制覆盖)
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report)
            action_label = "已保存" if not os.path.exists(report_file) else "已覆盖"
            logger.info(f"  报告{action_label}: {report_file}")
        
        # 2. 提取关键建议（US-004 改进：通用解析，不再硬编码）
        logger.info("[2/3] 分析建议...")
        action, new_code, new_name, new_price, new_quantity, stop_loss_price, stop_profit_price =             self._parse_recommendation(report)
        
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
                    'adx_14': latest.get('adx_14', 0),  # v9 双模式
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
        # US-006: 用 MarketRegimeDetector 基于市场结构判断
        market_mode_regime = self._detect_market_mode()
        market_mode = self._regime_to_label(market_mode_regime)
        
        # 获取持仓数量（US-024: 修复钉钉通知"空仓"误判）
        hold_count = 0
        if self.tracker:
            account = self.tracker.get_account_summary()
            hold_count = account.get('hold_count', 0)
        
        results = {
            'action': action,
            'code': new_code,
            'name': new_name,
            'price': new_price,
            'market_mode': market_mode,  # v9 双模式标注
            'hold_count': hold_count,     # US-024: 持仓数量（修复空仓误判）
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
    
    def execute_trade(self, code: str, action: str, price: float, quantity: int,
                     reason: str = "", actual_pnl: float = 0, name: str = None,
                     signal_time: str = "", signal_price: float = 0,
                     signal_rsi: float = 0, signal_adx: float = 0,
                     signal_score: int = 0, trade_time: str = "",
                     emotion: str = "", session: str = "",
                     is_real: int = 0):  # 🆕 US-024: 默认 0（向后兼容）
        """执行交易（SOP-06 v2.0: 信号快照 + 情绪 + 时段 + US-024: is_real 传递）

        Args:
            code:           ETF代码
            action:         'buy' 或 'sell'
            price:          成交价格
            quantity:       成交数量
            reason:         交易原因
            actual_pnl:     实际盈亏（仅卖出时）
            name:           ETF名称（自动查找）
            signal_time:    信号发出时间
            signal_price:   信号价格
            signal_rsi:     信号RSI(14)
            signal_adx:     信号ADX(14)
            signal_score:   信号评分
            trade_time:     实际成交时间
            emotion:        交易情绪
            session:        交易时段
            is_real:        1=实盘, 0=模拟（默认 0，向后兼容）— US-024
        """
        from src.utils.industry import INDUSTRY_MAPPING

        # 自动获取名称
        if name is None:
            name = INDUSTRY_MAPPING.get(code, code)

        if action == 'buy':
            self.tracker.record_buy(
                code=code,
                name=name,
                price=price,
                quantity=quantity,
                reason=reason or '手动买入',
                signal_price=signal_price,
                signal_time=signal_time,
                signal_rsi=signal_rsi,
                signal_adx=signal_adx,
                signal_score=signal_score,
                trade_time=trade_time,
                emotion=emotion,
                session=session,
                is_real=is_real,  # 🆕 US-024: 显式传递
            )
            logger.info(f"✓ 已记录买入: {code} {name} (is_real={is_real})")
        else:
            self.tracker.record_sell(
                code=code,
                price=price,
                actual_pnl=actual_pnl,
                quantity=quantity,  # 🆕 US-024: 传 quantity 支持部分卖
                is_real=is_real,    # 🆕 US-024
                emotion=emotion,
                session=session,
            )
            logger.info(f"✓ 已记录卖出: {code} {name} (is_real={is_real})")
    
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
                       choices=['daily', 'eval', 'trade', 'history', 'perf', 'update_pool', 'export', 'account', 'sync', 'check'],
                       default='daily', help='运行模式')
    parser.add_argument('--capital', '-c', type=float, default=20000,
                       help='本金')
    parser.add_argument('--code', type=str, help='ETF代码')
    parser.add_argument('--action', type=str, choices=['buy', 'sell'], help='交易动作')
    parser.add_argument('--price', type=float, help='价格')
    parser.add_argument('--quantity', type=int, help='数量')
    parser.add_argument('--webhook', type=str, help='钉钉Webhook URL')
    parser.add_argument('--silent', action='store_true', help='静默模式（不发送钉钉，由cron响应代替）')
    parser.add_argument('--force', action='store_true', help='强制覆盖今日报告（默认今日已生成则跳过）')
    # ── US-002: Safety Gate（--force-target + --dry-run） ─────────────
    parser.add_argument('--force-target', type=str, default=None,
                       help='Severe 操作的对象名确认（如 --force-target=positions，'
                            '对应 --mode=trade --action=clear 类破坏性操作）')
    add_dry_run_argument(parser)
    # ─────────────────────────────────────────────────────────────
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
    
    # ── SOP-06 v2.0: 交易参数 ───────────────────────────────────
    parser.add_argument('--name', type=str, help='ETF名称（可选）')
    parser.add_argument('--reason', type=str, help='交易原因')
    parser.add_argument('--actual_pnl', type=float, default=0, help='实际盈亏（仅卖出时）')
    parser.add_argument('--signal_time', type=str, help='信号发出时间 (YYYY-MM-DD HH:MM)')
    parser.add_argument('--signal_price', type=float, help='信号价格')
    parser.add_argument('--signal_rsi', type=float, help='信号RSI(14)')
    parser.add_argument('--signal_adx', type=float, help='信号ADX(14)')
    parser.add_argument('--signal_score', type=int, help='信号评分')
    parser.add_argument('--trade_time', type=str, help='实际成交时间 (YYYY-MM-DD HH:MM)')
    parser.add_argument('--emotion', type=str, 
                       choices=['calm', 'euphoria', 'fear', 'fomo', 'regret'],
                       help='交易情绪 (calm/euphoria/fear/fomo/regret)')
    parser.add_argument('--session', type=str,
                       choices=['A', 'B', 'C', 'D', 'E', 'F'],
                       help='交易时段 (A-F，对应UTC 00-24)')
    # 🆕 US-024: 实盘标记（US-016 设计的"实盘必填"落地）
    parser.add_argument('--is_real', type=int, choices=[0, 1], default=0,
                       help='是否实盘（1=实盘, 0=模拟，默认 0）。实盘必传 1（US-016 设计）')
    # ─────────────────────────────────────────────────────────────

    # ── US-001: 执行源标识（audit / 未来门禁） ──────────────────
    add_source_argument(parser)
    # ─────────────────────────────────────────────────────────────

    args = parser.parse_args()

    # US-001: 解析执行源（argv 缺省 → 走 get_source_from_argv 默认 MANUAL）
    execution_source = get_source_from_argv() if args.source is None else ExecutionSource(args.source)

    # US-003: Audit 日志 — start 事件（在解析完 args 后立即写）
    _audit = get_audit()
    _t0 = time.time()
    _cmd = "decision.py " + " ".join(sys.argv[1:])
    _audit.write_event(
        event_type="started",
        command=_cmd,
        source=execution_source.value,
        actor="月海巫师" if execution_source != ExecutionSource.CRON else None,
        args={"mode": args.mode, "capital": args.capital, "code": args.code, "action": args.action},
    )
    logger.info(f"🔖 execution_source = {execution_source.value} "
                f"(argv={args.source!r}, env={os.environ.get('EXECUTION_SOURCE')!r})")

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
    if args.force:
        engine.force = True

    # US-002: Safety Gate 参数注入到 engine
    engine._execution_source = execution_source
    engine._dry_run = args.dry_run
    engine._force_target = args.force_target

    # 执行
    if args.mode == 'daily':
        engine.run_daily_check()
    elif args.mode == 'eval':
        # US-002: eval 模式含钉钉推送，是 Moderate 破坏性操作（dingtalk_send）
        try:
            require_force(
                "dingtalk_send",
                source=execution_source,
                force=args.force,
                dry_run=args.dry_run,
                target=None,
            )
        except SafetyGateError as e:
            logger.error(str(e))
            # US-003: SafetyGate 拒绝时写 audit
            _audit.write_event(
                event_type="denied_by_safety_gate",
                command=_cmd,
                source=execution_source.value,
                outcome="denied",
                duration_ms=(time.time() - _t0) * 1000,
                error_msg=str(e),
                op="dingtalk_send",
            )
            sys.exit(2)
        if args.dry_run:
            logger.info("[dry-run] eval 模式 dry-run 完成，未实际推送钉钉")
            _audit.write_event(
                event_type="dry_run",
                command=_cmd,
                source=execution_source.value,
                outcome="success",
                duration_ms=(time.time() - _t0) * 1000,
                op="dingtalk_send",
            )
            sys.exit(0)
        engine.run_full_evaluation(silent=args.silent, simple=args.simple)
    elif args.mode == 'trade':
        # US-002: trade 写入是 Moderate 破坏性操作（trade_record）
        try:
            require_force(
                "trade_record",
                source=execution_source,
                force=args.force,  # 复用现有 --force 标志
                dry_run=args.dry_run,
                target=None,
            )
        except SafetyGateError as e:
            logger.error(str(e))
            # US-003: SafetyGate 拒绝时写 audit
            _audit.write_event(
                event_type="denied_by_safety_gate",
                command=_cmd,
                source=execution_source.value,
                outcome="denied",
                duration_ms=(time.time() - _t0) * 1000,
                error_msg=str(e),
                op="trade_record",
            )
            sys.exit(2)
        if args.dry_run:
            logger.info("[dry-run] trade 模式 dry-run 完成，未实际执行")
            sys.exit(0)
        if args.code and args.action and args.price and args.quantity:
            engine.execute_trade(
                args.code, args.action, args.price, args.quantity,
                reason=args.reason, actual_pnl=args.actual_pnl, name=args.name,
                signal_time=args.signal_time, signal_price=args.signal_price,
                signal_rsi=args.signal_rsi, signal_adx=args.signal_adx,
                signal_score=args.signal_score, trade_time=args.trade_time,
                emotion=args.emotion, session=args.session,
                is_real=args.is_real,  # 🆕 US-024: 传递 CLI 参数
            )
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
    elif args.mode == 'account':
        # US-012: 统一账户视图
        _run_account_view(engine, args)
    elif args.mode == 'update_pool':
        from src.etf_pool_updater import ETFListUpdater
        updater = ETFListUpdater('etf_pool.json')
        updater.run_full_update()
    elif args.mode == 'sync':
        # 数据一致性检查 + 钉钉提醒
        _run_data_sync(engine, args)
    elif args.mode == 'check':
        # 仅检查，不发送钉钉
        _run_data_check(engine, args)

    # US-003: Audit 日志 — success 事件（main 末尾）
    _audit.write_event(
        event_type="success",
        command=_cmd,
        source=execution_source.value,
        outcome="success",
        duration_ms=(time.time() - _t0) * 1000,
        mode=args.mode,
    )


# ── 数据一致性检查（预防 US-014 再次发生）─────────────────────────

def _run_data_check(engine: ETFDecisionEngine, args):
    """仅检查数据一致性，不发送钉钉"""
    print("\n📋 数据一致性检查")
    print("=" * 40)
    
    result = engine.tracker.check_data_consistency()
    print(result['summary'])
    
    if result['issues']:
        print("\n问题详情：")
        for issue in result['issues']:
            print(f"  [{issue['type']}] {issue['code']}: {issue['msg']}")
        
        print("\n快速修复命令：")
        print("  python -m src.cli.decision -m sync --fix")
    else:
        print("\n✅ 无需修复")


def _run_data_sync(engine: ETFDecisionEngine, args):
    """数据一致性检查 + 钉钉提醒 + 修复"""
    print("\n📋 数据一致性检查 + 同步")
    print("=" * 40)
    
    result = engine.tracker.check_data_consistency()
    print(result['summary'])
    
    if result['issues']:
        print("\n问题详情：")
        for issue in result['issues']:
            print(f"  [{issue['type']}] {issue['code']}: {issue['msg']}")
        
        # 钉钉提醒
        print("\n📤 发送钉钉提醒...")
        try:
            from src.notify.dingtalk import DingTalkSender
            sender = DingTalkSender()
            
            msg_parts = [f"⚠️ 数据不一致，发现 {len(result['issues'])} 个问题："]
            for issue in result['issues'][:5]:  # 最多显示5条
                msg_parts.append(f"• {issue['code']}: {issue['msg']}")
            if len(result['issues']) > 5:
                msg_parts.append(f"• ...还有 {len(result['issues']) - 5} 条")
            msg_parts.append("")
            msg_parts.append("请回复 '同步' 或手动执行：")
            msg_parts.append("  python -m src.cli.decision -m sync --fix")
            
            sender.send_text("\n".join(msg_parts))
            print("✅ 钉钉提醒已发送")
        except Exception as e:
            print(f"⚠️ 钉钉发送失败: {e}")
            print("请手动检查数据一致性")
    else:
        print("\n✅ 数据一致，无需修复")
    
    # 自动刷新 pnl_pct
    print("\n🔄 刷新持仓盈亏...")
    updated = engine.tracker.refresh_positions_pnl()
    print(f"   更新了 {updated} 条记录")
    
    # 验证
    print("\n📊 当前持仓状态：")
    for pos in engine.tracker.load_positions():
        print(f"   {pos.code} {pos.name}: {pos.pnl_pct/100:+.2%} ({pos.hold_days}天)")


# ── US-005: 新增 CLI 子命令实现 ─────────────────────────────────

def _run_account_view(engine: ETFDecisionEngine, args):
    """
    US-012: 统一账户视图（-m account）

    Examples:
        python -m src.cli.decision -m account
        python -m src.cli.decision -m account --webhook https://oapi.dingtalk.com/robot/send?access_token=xxx
    """
    from src.analysis.account_view import AccountView
    webhook = getattr(args, 'webhook', None) or engine.webhook_url
    view = AccountView(webhook_url=webhook)
    print(view.generate())


def _run_history_query(engine: ETFDecisionEngine, args):
    """
    US-005: 查询交易记录
    US-007: 增加"持仓策略指导"段

    Examples:
        python -m src.decision_cli -m history
        python -m src.decision_cli -m history --date 20260525
        python -m src.decision_cli -m history --date 2026-05 --code 510300
    """
    # US-007: 持仓策略指导（在交易历史之前显示）
    try:
        from src.analysis.position_guide import PositionGuideAnalyzer
        # 用 US-006 的 market_regime 检测
        market_regime = engine._detect_market_mode() if hasattr(engine, '_detect_market_mode') else 'range_bound'
        analyzer = PositionGuideAnalyzer()
        guides = analyzer.analyze_portfolio(market_regime=market_regime)
        if guides:
            _print_position_guides(guides, market_regime)
    except Exception as e:
        print(f"[WARN] US-007 持仓策略指导失败: {e}")

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


def _print_position_guides(guides, market_regime: str = 'range_bound'):
    """US-007: 打印持仓策略指导"""
    print(f"\n{'=' * 80}")
    print(f"📊 持仓策略指导 (US-007) | 市场: {market_regime}")
    print(f"{'=' * 80}")

    if not guides:
        print("  (无持仓)")
        return

    REGIME_LABEL = {
        'trend_up': '📈 趋势市',
        'range_bound': '📊 震荡市',
        'trend_down': '🔻 下跌市',
        'crash': '🚨 暴跌市',
    }

    for g in guides:
        legacy_tag = '  [legacy]' if g.action == '清仓（用户决策）' else ''
        print(f"\n  【{g.code} {g.name}】{legacy_tag}")
        print(f"    持仓 {g.hold_days} 天 | {g.quantity} 股 @ {g.entry_price:.3f}")
        print(f"    当前 {g.current_price:.3f} | 盈亏 {g.pnl_pct:+.2%}")
        from src.analysis.position_guide import DEFAULT_STOP_LOSS_PCT, DEFAULT_TAKE_PROFIT_PCT
        print(f"    止损 {g.stop_loss_price:.3f} ({DEFAULT_STOP_LOSS_PCT:+.0%}) | "
              f"止盈 {g.take_profit_price:.3f} ({DEFAULT_TAKE_PROFIT_PCT:+.0%}) | "
              f"到期 {g.expire_in_days} 天")
        if g.min_hold_remaining > 0:
            print(f"    min_hold 剩余 {g.min_hold_remaining} 天")
        emotion_warn = f" | 情绪: {g.emotion_flag} ⚠️" if g.emotion_flag in ('fear', 'fomo', 'euphoria') else ""
        print(f"    评分 {g.current_score} | 市场 {REGIME_LABEL.get(g.market_regime, g.market_regime)}{emotion_warn}")
        print(f"    决策：{g.action}")
        print(f"    理由：{g.reason}")

    print()


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