#!/usr/bin/env python3
"""
ETF投资决策报告生成器 - 固定模板版本（含实时校验）

用途：
    - 生成每日量化决策报告
    - 包含 top_5 / top_10 / all 三个版本
    - 包含实时价格校验和交易信号

被谁调用：
    - src/cli/decision.py（决策引擎调用此模块生成报告）
    - 其他需要生成决策报告的模块

功能说明：
    - 从数据库加载 ETF 历史数据
    - 计算技术指标
    - 生成买入/卖出信号
    - 保存到 etf_reports/ 目录

使用方式：
    from src.analysis.report_generator import generate_decision_report
    
    report = generate_decision_report(mode='daily/eval', date=datetime.now())

依赖：
    - src.utils.config (run_strategy, StrategyConfig)
    - src.core.selector (Selector)
    - src.analysis.indicator (Indicator)
    - src.data.loader (DataLoader, ETFNameLoader)
    - src.data.manager (DataFacade)

注意事项：
    - 使用 DataLoader 读取数据（统一数据入口）
    - ETF 名称从数据库读取（不再硬编码）
    - 交易信号包含买入/卖出/观望
"""
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
import json
import os
import sqlite3
from pathlib import Path

from src.utils.config import run_strategy, StrategyConfig
from src.core.selector import Selector
from src.analysis.indicator import Indicator
from src.data.loader import DataLoader, ETFNameLoader
from src.data.etf_pool_repository import ETFRepository
from src.analysis.report_templates import (
    format_strategy_mode, format_action_advice, format_scenario,
    format_regime_label,
    POSITION_LIMITS, format_position_limit
)

# US-018: 策略参数单一真相源（避免 17 处硬编码散落）
from src.constants import (
    STOP_LOSS_PCT, TAKE_PROFIT_PCT,
    STOP_LOSS_PRICE_RATIO, TAKE_PROFIT_PRICE_RATIO,
    MAX_HOLD_DAYS, MAX_TOTAL_STOP_LOSS,
    TRAILING_STOP_PCT, TRAILING_THRESHOLD_PCT,
    MAX_POSITION_RATIO,
)

# 尝试导入热冷数据管理器
try:
    from src.data.manager import DataFacade
except ImportError:
    DataFacade = None

# 尝试导入交易校验器
try:
    from src.trade.validator import TradeValidator, Recommendation
except ImportError:
    TradeValidator = None
    Recommendation = None


# ETF名称加载器（从数据库读取，不再硬编码）
# 首次使用时从数据库加载，数据库无数据时自动从腾讯API获取并更新
_etf_name_loader = None

def _get_etf_name_loader() -> ETFNameLoader:
    """获取ETF名称加载器（懒加载）"""
    global _etf_name_loader
    if _etf_name_loader is None:
        _etf_name_loader = ETFNameLoader()
    return _etf_name_loader

def get_etf_name(code: str) -> str:
    """获取单个ETF名称（数据库优先，无则从API获取）"""
    loader = _get_etf_name_loader()
    return loader.get_name(code)


class ETFReportGenerator:
    """ETF投资决策报告生成器 (含实时校验)"""
    
    def __init__(self, data_dir: str = 'etf_data_live', live_data_dir: str = 'etf_data_live'):
        self.data_dir = data_dir
        self.live_data_dir = live_data_dir
        self.data = None
        self.latest_date = None
        self.current_etfs = []
        self.validation_results = []
        
        # 简版模式标志（传递给子组件）
        self._simple_mode = False
        
        # 实时数据管理器
        self.data_facade = DataFacade(live_data_dir) if DataFacade else None
        
        # 交易校验器
        self.trade_validator = TradeValidator() if TradeValidator else None
        
        # 计算缓存 (避免重复运算)
        self._calc_cache: Dict[str, Any] = {}
        
        # 缓存目录
        self.cache_dir = Path('etf_reports/cache')
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def load_data(self) -> str:
        """加载数据，返回最新日期
        
        使用 DataFacade统一数据入口（教训81-82）：
        - 冷数据：历史日K线（SQLite）
        - 热数据：今日实时价格（JSON）
        - 融合：历史数据 + 实时价格覆盖最后一条
        """
        from src.data.manager import DataFacade
        
        # 使用 DataFacade 获取所有 ETF 代码
        facade = DataFacade(self.data_dir)
        codes = facade.cold.get_code_list()
        
        # 使用 DataFacade.get_merged() 获取融合数据
        self.data = {}
        for code in codes:
            df = facade.get_merged(code, days=300)
            if len(df) >= 100:  # 降低门槛以便加载更多ETF
                self.data[code] = df
        
        if getattr(self, '_simple_mode', False):
            from src.core.selector import Selector
            Selector._simple_mode = True
        
        if not self.data:
            self.latest_date = datetime.now().strftime('%Y-%m-%d')
            return self.latest_date
        
        self.latest_date = max(df['date'].max() for df in self.data.values())
        
        # 预计算所有ETF的技术指标 (供报告使用RSI等)
        indicator = Indicator()
        for code in self.data:
            self.data[code] = indicator.calculate(self.data[code])
        
        return self.latest_date
    
    def analyze_market(self) -> Dict:
        """分析当前市场状态

        US-003：从 Repository 加载 tradable 池，不依赖 config.exclude_codes
        US-010：过滤已持仓（self.held_codes 由 generate_report 注入）
        """
        selector = Selector()
        indicator = Indicator()

        # US-003: 单一过滤入口 = ETFListLoader（动态池）
        # 使用 ETFListLoader.get_tencent_codes() 获取正确的池定义
        from src.data.etf_pool_loader import ETFListLoader
        loader = ETFListLoader()
        tencent_codes = loader.get_tencent_codes()  # 带 sh/sz 前缀
        # 转换为纯数字代码
        tradable_pool = set(code.replace('sh', '').replace('sz', '') for code in tencent_codes)
        
        # reference池（只读）
        reference_pool = {'510300'}  # 沪深300 作为大盘参考

        # US-010: 已持仓过滤集合
        held_codes = getattr(self, 'held_codes', set()) or set()

        scores = []
        filtered_by_held = []  # US-010: 记录被持仓过滤的标的
        filtered_by_held_scores = []  # US-017: 持仓也计算分数（不入选 Top N, 但报告展示）
        for code, df in self.data.items():
            # US-003 单一过滤入口:
            # 1. 不在动态池中 → 跳过
            if code not in tradable_pool:
                continue
            # 2. 是大盘参考（510300）→ 跳过
            if code in reference_pool:
                continue
            if len(df) < 60:
                continue
            df = indicator.calculate(df)
            s, reasons = selector.evaluate(df, self.latest_date)
            # US-017: 持仓也计算分数（不入选 Top N, 但报告展示）
            if code in held_codes:
                filtered_by_held.append(code)
                filtered_by_held_scores.append({
                    'code': code,
                    'name': get_etf_name(code),
                    'score': s,
                    'reasons': reasons,
                })
                continue
            if s >= 6:
                row = df[df['date'] == self.latest_date]
                if len(row) > 0:
                    price = row.iloc[0]['close']
                    scores.append({
                        'code': code,
                        'name': get_etf_name(code),
                        'score': s,
                        'price': price,
                        'reasons': reasons
                    })

        scores.sort(key=lambda x: -x['score'])
        self.current_etfs = scores
        self.filtered_by_held = filtered_by_held  # US-010
        self.held_scores = filtered_by_held_scores  # US-017: 持仓分数

        return {
            'total_qualified': len(scores),
            'bullish': len(scores) > 10,
            'top_etfs': scores[:10],
            'filtered_by_held': filtered_by_held,  # US-010
            'held_scores': filtered_by_held_scores,  # US-017
        }
    
    def validate_strategy(self, periods: List[Tuple] = None) -> List[Dict]:
        """验证策略表现"""
        if periods is None:
            periods = [
                ('2023-01-01', '2025-05-22', '2022-01-01', '2023-12-31'),
                ('2024-01-01', '2026-05-22', '2022-01-01', '2024-12-31'),
            ]
        
        # 优化后的参数 (鱼身实验Top1配置) - US-018: 从 constants 引用
        params = {
            'hold_count': 1,
            'weights': (1.0,),
            'stop_loss': -STOP_LOSS_PCT,
            'stop_gain': TAKE_PROFIT_PCT,
            'trailing_threshold': TRAILING_THRESHOLD_PCT,
            'trailing_stop': TRAILING_STOP_PCT,
            'enable_trailing_stop': True,
            'rebalance_days': 10,
            'enable_market_filter': True,
        }
        
        results = []
        for test_start, test_end, train_start, train_end in periods:
            result = run_strategy(
                test_start=test_start,
                test_end=test_end,
                data_dir=self.data_dir,
                train_start=train_start,
                train_end=train_end,
                **params
            )
            results.append({
                'period': f'{test_start[:4]}-{test_end[:4]}',
                'return': result['return'],
                'drawdown': result['drawdown'],
                'sharpe': result['sharpe'],
                'winrate': result['winrate'],
                'trades': result['trades'],
            })
        
        self.validation_results = results
        return results
    
    def generate_report(self, capital: float = 20000,
                        tracker: Optional['TradeTracker'] = None) -> str:
        """生成完整报告

        Args:
            capital: 用户投入本金（如果提供 tracker，仅作参考；实际以 tracker 账户数据为准）
            tracker: 交易追踪器实例（US-009，提供后资金配置段查持仓+现金）
        """
        # ── US-009: 账户数据集成 ─────────────────────────────
        from typing import Optional
        if tracker is not None:
            account = tracker.get_account_summary()
            cash_available = account['cash']                  # 现金余额
            positions_value = account['positions_value']      # 持仓市值
            total_asset = account['total_asset']              # 总资产
            hold_count = account['hold_count']                # 当前持仓数
            max_holdings = account['max_holdings']            # 最大持仓数
            # US-010: 注入已持仓代码集合给 analyze_market
            self.held_codes = {h['code'] for h in account['holdings']}
            # US-015: 按市场状态分档资金利用率（2026-06-04 用户规则）
            # 震荡 50% / 趋势 90% / 下跌 30% / 暴跌 0%
            # ⚠️ market 变量在 line 304 才设置，这里先用默认 range_bound
            #       真正生效的位置在 US-015 第二次计算（line 234, position_limit）
            position_limit = POSITION_LIMITS.get('range_bound', 0.5)
            available = max(0, total_asset * position_limit - positions_value)
            account_status_note = (
                f"- 现金: {cash_available:,.0f}元\n"
                f"- 持仓市值: {positions_value:,.0f}元（{hold_count}只）\n"
                f"- 总资产: {total_asset:,.0f}元\n"
                f"- 市场仓位上限: {position_limit*100:.0f}%"
            )
        else:
            # 旧行为：按传入本金（US-015: 仍按市场分档，market 尚未检测先用 range_bound）
            cash_available = capital
            positions_value = 0
            total_asset = capital
            hold_count = 0
            max_holdings = 2  # US-008 默认
            self.held_codes = set()  # US-010: 无 tracker 不过滤
            position_limit = POSITION_LIMITS.get('range_bound', 0.5)
            available = capital * position_limit
            account_status_note = (
                f"- 现金: {cash_available:,.0f}元（未接入 TradeTracker）\n"
                f"- 市场仓位上限: {position_limit*100:.0f}%"
            )

        # 获取数据
        latest = self.load_data()
        
        # ========== 数据过期检测 ==========
        from datetime import datetime, timedelta
        today = datetime.now().date()
        try:
            data_date = datetime.strptime(latest, '%Y-%m-%d').date()
        except:
            data_date = None
        
        data_freshness = "未知"
        data_freshness_warning = ""
        data_age_days = 0
        
        if data_date:
            data_age_days = (today - data_date).days
            if data_age_days == 0:
                data_freshness = "✅ 正常"
            elif 1 <= data_age_days <= 2:
                data_freshness = "⚠️ 数据略旧"
                data_freshness_warning = f"数据距今{data_age_days}天，部分指标可能不准确"
            else:
                data_freshness = "❌ 数据过期"
                data_freshness_warning = f"数据超过{data_age_days}天未更新，偏差计算可能失真！"
        
        market_status = self.analyze_market()  # 分析市场
        self.validate_strategy()  # 验证策略

        # US-011: 检测市场环境（trend_up/range_bound/trend_down/crash）
        market_regime = self._detect_market_regime_for_report()

        market = {
            'total_qualified': market_status['total_qualified'],
            'bullish': market_status['bullish'],
            'regime': market_regime,  # US-011
        }
        
        # 计算平均表现
        avg_return = sum(r['return'] for r in self.validation_results) / len(self.validation_results)
        avg_drawdown = sum(r['drawdown'] for r in self.validation_results) / len(self.validation_results)
        avg_sharpe = sum(r['sharpe'] for r in self.validation_results) / len(self.validation_results)

        # US-017: 生成持仓管理段 (有 tracker 且有持仓时显示)
        holdings_section = ""
        if tracker is not None and hold_count > 0:
            holdings_section = self._format_holdings_section(account)
        
        # ========== 实时校验：获取实时价格 ==========
        top = self.current_etfs[0] if self.current_etfs else None
        live_price = None
        live_price_source = ""
        live_timestamp = ""
        price_deviation = 0.0
        signal_price = top['price'] if top else 0.0
        
        if top and self.trade_validator:
            # 按优先级获取实时价格：腾讯 → 东方财富 → 新浪
            realtime_data = self.trade_validator.fetch_realtime_prices([top['code']])
            if top['code'] in realtime_data:
                realtime_info = realtime_data[top['code']]
                live_price = realtime_info.get('price')
                live_price_source = realtime_info.get('data_source', '实时API')
                live_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            else:
                # 所有API失败，返回昨收盘价作为参考
                if top['code'] in self.data:
                    df = self.data[top['code']]
                    if len(df) > 0:
                        live_price = df.iloc[-1]['close']
                        live_price_source = "昨收盘(API不可用)"
                        live_timestamp = self.latest_date
        
        # 计算价格偏差
        if live_price and signal_price > 0:
            price_deviation = (live_price - signal_price) / signal_price * 100
        
        # ========== RSI温度计算 ==========
        rsi_5 = 50.0
        rsi_14 = 50.0
        rsi_temperature = "NORMAL"
        rsi_temp_emoji = ""
        
        if top and top['code'] in self.data:
            df = self.data[top['code']]
            if 'rsi_14' in df.columns and len(df) > 0:
                latest_row = df.iloc[-1]
                rsi_14 = latest_row.get('rsi_14', 50.0)
                rsi_5 = latest_row.get('rsi_5', 50.0)
        
        # RSI温度判断
        if rsi_14 >= 70:
            rsi_temperature = "OVERHEATED"
            rsi_temp_emoji = "🔥过热"
        elif rsi_14 >= 60:
            rsi_temperature = "HIGH"
            rsi_temp_emoji = "⚠️偏高"
        elif rsi_14 <= 40:
            rsi_temperature = "COOL"
            rsi_temp_emoji = "❄️过冷"
        elif rsi_14 <= 50:
            rsi_temperature = "LOW"
            rsi_temp_emoji = "📊偏低"
        else:
            rsi_temperature = "NORMAL"
            rsi_temp_emoji = "✅正常"
        
        # ========== 智能推荐价格算法 ==========
        # 动态加权法：根据偏差程度计算推荐价格
        trade_price = signal_price  # 默认使用信号价
        price_warning = ""
        
        if live_price and signal_price > 0:
            deviation = (live_price - signal_price) / signal_price * 100
            
            if abs(deviation) < 3:
                # 市场稳定，跟随实际价格
                trade_price = live_price
            elif 3 <= abs(deviation) < 8:
                # 轻度偏离，线性调整
                trade_price = signal_price * (1 + deviation * 0.3 / 100)
                price_warning = f"轻度偏离调整({deviation:+.1f}%)"
            else:
                # 重度偏离，以策略信号为准
                trade_price = signal_price
                price_warning = f"⚠️偏离过大({deviation:+.1f}%)，以策略信号价为准"
        
        # 计算止盈止损价（基于推荐价格）- US-018: 从 constants 引用
        stop_loss_price = trade_price * STOP_LOSS_PRICE_RATIO  # 止损价 -6%
        take_profit_price = trade_price * TAKE_PROFIT_PRICE_RATIO  # 止盈价 +10%
        
        # 计算股数（US-009: 用 available 替代 capital*0.9）
        position = 0
        action = "观望"
        if top:
            position = int(available / trade_price / 100) * 100  # 整百股
            # US-009: 满仓 / 现金不足 → 不买入
            if hold_count >= max_holdings:
                action = f"已达仓位上限（{hold_count}/{max_holdings}），暂不买入"
                position = 0
            elif available < trade_price * 100:
                action = f"可用金额不足（{available:,.0f}元），暂不买入"
                position = 0
            elif position > 0:
                action = f"买入 {top['code']} {top['name']} {position}股"
        
        # ========== 计算止盈止损空间（基于实时交易价格）==========
        # 使用实际的交易价格计算止盈止损空间
        target_gap = 0.0  # 距止盈空间 (%)
        stop_gap = 0.0    # 距止损空间 (%)
        
        if live_price and trade_price > 0:
            # 止盈空间: 从当前价到止盈价还有多少百分比
            target_gap = (take_profit_price - live_price) / live_price * 100
            # 止损空间: 从当前价到止损价还有多少百分比
            stop_gap = (stop_loss_price - live_price) / live_price * 100
        
        # ========== 生成策略建议 ==========
        strategy_advice = "建议观望，等待买入时机"
        strategy_emoji = "⚠️"
        
        if live_price and signal_price > 0:
            if rsi_14 >= 70:
                # RSI过热，不建议追高
                if price_deviation > 3:
                    strategy_advice = f"现价{live_price:.3f}已高出信号价{price_deviation:+.1f}%，买入空间有限，建议等待回调"
                    strategy_emoji = "⚠️"
                else:
                    strategy_advice = f"RSI高达{rsi_14:.0f}，短期过热，建议等待回调至{signal_price*1.02:.3f}以下再买入"
                    strategy_emoji = "⚠️"
            elif rsi_14 <= 40:
                # RSI过冷，是买入机会
                strategy_advice = f"RSI仅{rsi_14:.0f}，处于超卖区域，提供较好买入机会"
                strategy_emoji = "💡"
            elif price_deviation < -2:
                # 价格低于信号价，是买入机会
                strategy_advice = f"现价{live_price:.3f}低于信号价，提供买入机会，建议建仓"
                strategy_emoji = "✅"
            elif price_deviation > 5:
                # 价格高出信号价5%以上，空间有限
                strategy_advice = f"现价{live_price:.3f}已高出信号价{price_deviation:+.1f}%，建议等待回调至{signal_price*1.02:.3f}以下"
                strategy_emoji = "⚠️"
            else:
                # 正常状态
                strategy_advice = f"价格适中，RSI{rsi_14:.0f}，建议择机建仓"
                strategy_emoji = "✅"
        
        # ========== 智能推荐价格算法 ==========
        # 动态加权法：根据偏差程度计算推荐价格
        trade_price = signal_price  # 默认使用信号价
        price_warning = ""
        
        if live_price and signal_price > 0:
            deviation = (live_price - signal_price) / signal_price * 100
            
            if abs(deviation) < 3:
                # 市场稳定，跟随实际价格
                trade_price = live_price
            elif 3 <= abs(deviation) < 8:
                # 轻度偏离，线性调整
                trade_price = signal_price * (1 + deviation * 0.3 / 100)
                price_warning = f"轻度偏离调整({deviation:+.1f}%)"
            else:
                # 重度偏离，以策略信号为准
                trade_price = signal_price
                price_warning = f"⚠️偏离过大({deviation:+.1f}%)，以策略信号价为准"
        
        # 计算止盈止损价（基于推荐价格）- US-018: 从 constants 引用
        stop_loss_price = trade_price * STOP_LOSS_PRICE_RATIO  # 止损价 -6%
        take_profit_price = trade_price * TAKE_PROFIT_PRICE_RATIO  # 止盈价 +10%
        
        # 计算股数（US-009: 用 available 替代 capital*0.9）
        position = 0
        action = "观望"
        if top:
            position = int(available / trade_price / 100) * 100  # 整百股
            # US-009: 满仓 / 现金不足 → 不买入
            if hold_count >= max_holdings:
                action = f"已达仓位上限（{hold_count}/{max_holdings}），暂不买入"
                position = 0
            elif available < trade_price * 100:
                action = f"可用金额不足（{available:,.0f}元），暂不买入"
                position = 0
            elif position > 0:
                action = f"买入 {top['code']} {top['name']} {position}股"
        
        # ========== US-016: 近期交易情绪回顾 (FOMO/Fear/Regret 提示) ==========
        emotion_alerts = ""
        if tracker is not None:
            try:
                # 查询最近 7 天有 emotion 标记的交易
                conn = sqlite3.connect(tracker.db_path)
                cur = conn.execute("""
                    SELECT date, code, name, action, emotion, reason
                    FROM trade_history
                    WHERE emotion IN ('fomo', 'fear', 'regret', 'euphoria')
                      AND is_real = 1
                      AND date >= date('now', '-7 days')
                    ORDER BY id DESC
                    LIMIT 5
                """)
                emotion_rows = cur.fetchall()
                conn.close()
                if emotion_rows:
                    emoji_map = {
                        'fomo': '🟡 FOMO (追高)',
                        'fear': '🔴 Fear (恐慌)',
                        'regret': '🟠 Regret (后悔)',
                        'euphoria': '🟢 Euphoria (兴奋)',
                    }
                    lines = ["⚠️ 近期情绪化交易 (实盘/7天内):"]
                    for r in emotion_rows:
                        lines.append(f"  - {r[0]} {r[1]} {r[2]} {r[3]} "
                                     f"[{emoji_map.get(r[4], r[4])}]: {r[5] or '无'}")
                    lines.append("  💡 建议: 情绪化交易通常胜率低, 严格执行策略")
                    emotion_alerts = "\n".join(lines) + "\n"
            except Exception as e:
                # 不影响主报告
                pass

        # 构建报告 - 交易建议放开头和结尾
        report = f"""
{'='*70}
📈 ETF量化投资决策报告
{'='*70}

【基本信息】
报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}
数据最新日期: {latest} {data_freshness}
投资本金: {capital:,}元（参考）
策略模式: {format_strategy_mode(market['regime'], max_holdings)}
当前持仓: {hold_count}只 / 现金: {cash_available:,.0f}元

{f"{data_freshness_warning}" if data_freshness_warning else ""}
{f"{emotion_alerts}" if emotion_alerts else ""}
{holdings_section}
{'='*70}
🚨 今日交易建议 (必读)
{'='*70}

【操作】{action}
【目标】{top['code']} {top['name']}
【价格】{trade_price:.3f}元
【数量】{position}股 ({available:,.0f}元)
【止损】-{int(STOP_LOSS_PCT*100)}% ({stop_loss_price:.3f}元)
【止盈】+{int(TAKE_PROFIT_PCT*100)}% ({take_profit_price:.3f}元)

{'='*70}
🔍 实时校验 (实时数据对比)
{'='*70}

【实时数据】
数据时间: {live_timestamp if live_timestamp else datetime.now().strftime('%Y-%m-%d %H:%M')}
数据来源: {live_price_source if live_price_source else "无实时数据"}
报告推荐价: {signal_price:.3f}元

【价格对比】
{'实时价: {:.3f} | 偏差: {:+.1f}%'.format(live_price, price_deviation) if live_price else "实时价: 暂无数据"}

【止盈止损空间】
{'距止盈: {:.3f} ({:+.1f}%) | 距止损: {:.3f} ({:+.1f}%)'.format(take_profit_price, target_gap, stop_loss_price, stop_gap) if live_price else "暂无实时数据"}

【RSI温度计】
RSI5: {rsi_5:.1f} | RSI14: {rsi_14:.1f}
状态: {rsi_temperature} {rsi_temp_emoji}

{'='*70}
📋 策略建议
{'='*70}

{strategy_emoji} {strategy_advice}

{'='*70}
一、市场环境分析
{'='*70}

【数据摘要】(US-017: 评分阈值显式)
- 符合买入条件（≥6 分）ETF数量: {market['total_qualified']}只
- 市场状态: {format_regime_label(market['regime'])}

【定性分析】
当前市场处于{format_regime_label(market['regime'])}的状态。从技术面来看，共有
{market['total_qualified']}只ETF满足 6 分以上的选股标准（评分阈值 = 6 分），
这表明市场中有足够的投资机会。建议审慎参与市场，
选择得分最高的标的进行投资。

{'='*70}
二、策略历史表现 (多时段验证)
{'='*70}
"""
        
        # 添加验证结果表格
        report += "【回测结果】\n"
        report += "-" * 70 + "\n"
        report += f"{'测试期':<15} {'收益':>10} {'回撤':>10} {'夏普':>8} {'胜率':>8} {'交易':>6}\n"
        report += "-" * 70 + "\n"
        
        for r in self.validation_results:
            report += f"{r['period']:<15} {r['return']:>+9.1f}% {r['drawdown']:>9.1f}% {r['sharpe']:>8.2f} {r['winrate']:>7.1f}% {r['trades']:>6}\n"
        
        report += "-" * 70 + "\n"
        report += f"{'平均':<15} {avg_return:>+9.1f}% {avg_drawdown:>9.1f}% {avg_sharpe:>8.2f}\n"
        
        report += f"""
【定量分析】
- 平均收益率: {avg_return:+.1f}%
- 平均最大回撤: {avg_drawdown:.1f}%
- 平均夏普比率: {avg_sharpe:.2f}
- 风险调整后收益: {'优秀' if avg_sharpe > 0.5 else '一般' if avg_sharpe > 0.2 else '较差'}

【定性分析】
策略在历史回测中表现{'稳定' if avg_sharpe > 0.5 else '一般'}。夏普比率
{avg_sharpe:.2f}表明风险调整后的收益{'较好' if avg_sharpe > 0.5 else '一般'}。
最大回撤{avg_drawdown:.1f}%在可接受范围内。

{'='*70}
三、当前推荐标的
{'='*70}

【TOP 10 推荐】(分数>=6)
"""
        
        # 推荐标的表格
        report += "-" * 70 + "\n"
        report += f"{'排名':<4} {'代码':<8} {'名称':<10} {'价格':>8} {'分数':>6} {'推荐理由'}\n"
        report += "-" * 70 + "\n"
        
        for i, etf in enumerate(self.current_etfs[:10], 1):
            reasons = '+'.join(etf['reasons'][:3])
            report += f"{i:<4} {etf['code']:<8} {etf['name']:<10} {etf['price']:>8.3f} {etf['score']:>6} {reasons}\n"

        # US-010: 过滤说明段
        if getattr(self, 'filtered_by_held', []):
            report += "\n【过滤说明】(US-010)\n"
            for code in self.filtered_by_held:
                report += f"- {code} 已持仓，不重复推荐\n"

        report += f"""
【核心推荐】
1. {self.current_etfs[0]['code']} {self.current_etfs[0]['name']} - 分数{self.current_etfs[0]['score']}分 (最高)
{f"2. {self.current_etfs[1]['code']} {self.current_etfs[1]['name']} - 分数{self.current_etfs[1]['score']}分" if len(self.current_etfs) > 1 else ""}

{'='*70}
四、资金配置方案
{'='*70}

【建议方案】(本金{capital:,}元{', 接入 TradeTracker' if tracker else ', 未接入 TradeTracker'})
"""
        
        # 计算配置
        top = self.current_etfs[0]
        position = int(available / top['price'] / 100) * 100  # US-009: 用 available 替代
        cash_remaining = cash_available - (position * top['price'] if position > 0 else 0)
        
        # 满仓/不足时特殊处理
        if hold_count >= max_holdings:
            capital_table = f"""| 标的 | 金额(元) | 占比 | 买入数量 |
|------|----------|------|----------|
| ⚠️ 已达仓位上限（{hold_count}/{max_holdings}）| - | - | 暂不买入 |
| 现金 | {cash_available:,.0f} | 100% | - |"""
        else:
            capital_table = f"""| 标的 | 金额(元) | 占比 | 买入数量 |
|------|----------|------|----------|
| {top['code']} {top['name']} | {position * top['price']:,.0f} | {(position * top['price'] / total_asset * 100) if total_asset > 0 else 0:.0f}% | {position}股 |
| 现金（剩余） | {cash_remaining:,.0f} | {(cash_remaining / total_asset * 100) if total_asset > 0 else 0:.0f}% | - |
| 当前持仓 | {positions_value:,.0f} | - | {hold_count}只 |"""
        
        report += f"""
{capital_table}

【账户状态】
{account_status_note}
- 可投入: {available:,.0f}元（仓位{int(MAX_POSITION_RATIO*100)}%上限）
- 已持仓: {hold_count} / {max_holdings}只

【说明】
- 多持仓策略（最多{max_holdings}只），降低单标的风险
- 预留{int((1-MAX_POSITION_RATIO)*100)}%现金应对突发情况
- 最大止损{int(STOP_LOSS_PCT*100)}%，即最多亏损{position * top['price'] * STOP_LOSS_PCT if position > 0 else 0:,.0f}元

{'='*70}
五、风险控制
{'='*70}

| 规则 | 参数 | 说明 |
|------|------|------|
| 单笔止损 | -{int(STOP_LOSS_PCT*100)}% | 触发立即平仓 |
| 总体止损 | {int(MAX_TOTAL_STOP_LOSS*100)}% | 亏损达{abs(int(MAX_TOTAL_STOP_LOSS*100))}%全部清仓 |
| 止盈 | +{int(TAKE_PROFIT_PCT*100)}% | 固定止盈 |
| 移动止盈 | 回撤{int(TRAILING_STOP_PCT*100)}% | 盈利超{int(TRAILING_THRESHOLD_PCT*100)}%后启用 |
| 持仓周期 | 最长{MAX_HOLD_DAYS}天 | 超过强制平仓 |

【情景分析】
{format_scenario(market['regime'], validation_results=self.validation_results)}

最大亏损: {int(MAX_TOTAL_STOP_LOSS*100)}% (约{capital*abs(MAX_TOTAL_STOP_LOSS):,.0f}元)

{'='*70}
六、结论
{'='*70}

【综合评估】
- 市场环境: {format_regime_label(market['regime'])} (符合买入条件≥6分: {market['total_qualified']}只)
- 策略表现: {'优秀' if avg_sharpe > 0.5 else '一般'} (夏普{avg_sharpe:.2f})
- 风险等级: {'中等偏低' if avg_drawdown > -30 else '中等'} (回撤{avg_drawdown:.0f}%)

{'='*70}
🚨 今日交易建议 (结论)
{'='*70}

【操作】{action}
【目标】{top['code']} {top['name']}
【价格】{top['price']:.3f}元
【数量】{position}股 ({position * top['price']:,.0f}元)
【止损】-{int(STOP_LOSS_PCT*100)}% ({top['price']*STOP_LOSS_PRICE_RATIO:.3f}元)
【止盈】+{int(TAKE_PROFIT_PCT*100)}% ({top['price']*TAKE_PROFIT_PRICE_RATIO:.3f}元)

【账户状态】{hold_count}只持仓 / 现金 {cash_available:,.0f}元 / 可投入 {available:,.0f}元

{format_action_advice(
    market_regime=market['regime'],
    has_recommendation=bool(top),
    cash_sufficient=available >= (top['price'] * 100 if top else float('inf')),
    hold_count=hold_count,
    max_holdings=max_holdings,
    portfolio_actions=None
)}
{'✓ 策略已经过多时段验证' if avg_sharpe > 0.3 else '⚠ 需进一步验证'}
{'✓ 回撤可控' if avg_drawdown > -35 else '⚠ 回撤较大，注意风险'}

{'='*70}
风险提示: 本报告仅供决策参考，不构成投资建议
{'='*70}
"""

        return report

    def _detect_market_regime_for_report(self) -> str:
        """
        US-011/013: 检测市场环境（10 状态细分：initial_up/uptrend/late_up/initial_down/
                   downtrend/late_down/range_bullish/range_bearish/reversal_point/crash）

        Returns:
            10 状态之一（默认 'range_bound' 兜底）
        """
        try:
            from src.analysis.market_regime import MarketRegimeDetector
            from src.data.loader import DataLoader
            loader = DataLoader()
            # 用 510300（大盘参考）作为市场环境判断基准
            df_510300 = loader.load_etf_history('510300')
            return MarketRegimeDetector().detect(df_510300)
        except Exception:
            return 'range_bound'  # 数据不足时默认震荡

    # ─────────────────────────────────────────────────────────
    # US-017: 持仓管理段
    # ─────────────────────────────────────────────────────────

    def _format_holdings_section(self, account: dict) -> str:
        """生成持仓管理段: 止盈止损 + 评分 + 动作标签

        Args:
            account: TradeTracker.get_account_summary() 返回的字典
        Returns:
            格式化持仓段字符串
        """
        holdings = account.get('holdings', [])
        if not holdings:
            return ""

        # 持仓分数映射 (US-017)
        score_map = {}
        for hs in getattr(self, 'held_scores', []):
            score_map[hs['code']] = hs['score']

        lines = ["=" * 70, "📦 持仓管理", "=" * 70, ""]
        lines.append(f"持仓数量: {len(holdings)}只 | 持仓市值: {account.get('positions_value', 0):,.0f}元")
        lines.append("")
        lines.append(f"{'代码':<8} {'名称':<14} {'成本':>7} {'现价':>7} {'盈亏':>7} "
                      f"{'止盈':>8} {'止损':>8} {'持X天':>7} {'分':>3}  动作")
        lines.append("-" * 90)

        for h in holdings:
            code = h['code']
            name = h.get('name', code)[:10]
            entry = h.get('entry_price', 0)
            current = h.get('current_price', 0)
            pnl = h.get('pnl_pct', 0)
            hold_days = h.get('hold_days', 0)

            stop_profit = entry * TAKE_PROFIT_PRICE_RATIO if entry > 0 else 0  # US-018
            stop_loss = entry * STOP_LOSS_PRICE_RATIO if entry > 0 else 0  # US-018

            # 动作标签
            action = self._holdings_action(pnl, hold_days)

            # 评分
            score = score_map.get(code, '-')

            lines.append(
                f"{code:<8} {name:<14} {entry:>7.3f} {current:>7.3f} {pnl:>+6.1f}% "
                f"{stop_profit:>7.3f} {stop_loss:>7.3f} 持{hold_days:>2d}天 {str(score):>3}  {action}"
            )

        return "\n".join(lines) + "\n"

    def _holdings_action(self, pnl_pct: float, hold_days: int) -> str:
        """根据盈亏和持仓天数生成动作标签

        优先级（SOUL 规则 17）:
        1. 止损（任意时刻）: pnl <= -6% → 🔴
        2. 止盈: 持仓 ≥1 天 且 pnl >= +8% → 🟡 接近止盈（接近 +10% 触发线）
        3. 到期: hold_days >= 15 → ⏰
        4. 刚建仓: hold_days == 0 → 🆕
        5. 默认: 🟢 持有
        """
        if pnl_pct <= -6:
            return "🔴 触发止损"
        if hold_days >= 15:
            return "⏰ 持仓到期"
        if hold_days == 0:
            return "🆕 刚建仓"
        if pnl_pct >= 8:
            return "🟡 接近止盈"
        if pnl_pct >= 5:
            return "🟢 持有(可止盈)"
        return "🟢 持有"

    def save_report(self, path: str = 'etf_report.txt',
                    tracker: Optional['TradeTracker'] = None):
        """保存报告到文件"""
        report = self.generate_report(tracker=tracker)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(report)
        return path


def generate_decision_report(capital: float = 20000, simple: bool = False,
                             tracker: Optional['TradeTracker'] = None) -> str:
    """快速生成决策报告

    Args:
        capital: 本金
        simple: 简版模式（禁用调试输出）
        tracker: 交易追踪器（US-009 提供后，资金配置段查持仓+现金）
    """
    generator = ETFReportGenerator()
    if simple:
        generator._simple_mode = True
        from src.core.selector import Selector
        Selector._simple_mode = True
    return generator.generate_report(capital, tracker=tracker)


if __name__ == '__main__':
    print(generate_decision_report())


__all__ = ['ETFReportGenerator', 'generate_decision_report']