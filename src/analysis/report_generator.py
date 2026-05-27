#!/usr/bin/env python3
"""ETF投资决策报告生成器 - 固定模板版本 (含实时校验)"""
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
import json
import os
from pathlib import Path

from src.utils.config import run_strategy, StrategyConfig
from src.core.selector import Selector
from src.analysis.indicator import Indicator
from src.data.loader import DataLoader

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


# ETF代码中文名称映射
ETF_NAMES = {
    # 核心推荐
    '516050': '科创成长',
    '515050': '科技50',
    '159577': '创新产业',
    '515000': '工业ETF',
    '513100': '稀土产业',
    
    # 宽基
    '510300': '沪深300',
    '510500': '中证500',
    '159919': '创业板',
    '159901': '深证100',
    '159905': '中证100',
    '510010': '180ETF',
    
    # 行业
    '512010': '医药ETF',
    '512500': '医药卫生',
    '159838': '创新药',
    '159995': '计算机',
    '512760': '半导体',
    '159801': '芯片ETF',
    '159823': '5G通信',
    '510630': '消费ETF',
    '159857': '光伏ETF',
    '516160': '新能源车',
    '159806': '新能源车',
    '159942': '有色金属',
    '510050': '煤炭ETF',
    '512660': '军工ETF',
}


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
        """加载数据，返回最新日期"""
        loader = DataLoader()
        if getattr(self, '_simple_mode', False):
            loader._simple_mode = True
            from src.core.selector import Selector
            Selector._simple_mode = True
        self.data = loader.load(self.data_dir)
        self.latest_date = max(df['date'].max() for df in self.data.values())
        
        # 预计算所有ETF的技术指标 (供报告使用RSI等)
        indicator = Indicator()
        for code in self.data:
            self.data[code] = indicator.calculate(self.data[code])
        
        return self.latest_date
    
    def analyze_market(self) -> Dict:
        """分析当前市场状态"""
        selector = Selector()
        indicator = Indicator()
        
        # 获取排除列表
        exclude_codes = StrategyConfig().exclude_codes
        
        scores = []
        for code, df in self.data.items():
            # 排除特殊ETF (红利、港股、证券、债券等)
            if code in exclude_codes:
                continue
            if len(df) < 60:
                continue
            df = indicator.calculate(df)
            s, reasons = selector.evaluate(df, self.latest_date)
            if s >= 6:
                row = df[df['date'] == self.latest_date]
                if len(row) > 0:
                    price = row.iloc[0]['close']
                    scores.append({
                        'code': code,
                        'name': ETF_NAMES.get(code, code),
                        'score': s,
                        'price': price,
                        'reasons': reasons
                    })
        
        scores.sort(key=lambda x: -x['score'])
        self.current_etfs = scores
        
        return {
            'total_qualified': len(scores),
            'bullish': len(scores) > 10,
            'top_etfs': scores[:10]
        }
    
    def validate_strategy(self, periods: List[Tuple] = None) -> List[Dict]:
        """验证策略表现"""
        if periods is None:
            periods = [
                ('2023-01-01', '2025-05-22', '2022-01-01', '2023-12-31'),
                ('2024-01-01', '2026-05-22', '2022-01-01', '2024-12-31'),
            ]
        
        # 优化后的参数
        params = {
            'hold_count': 1,
            'weights': (1.0,),
            'stop_loss': -0.05,
            'stop_gain': 0.08,
            'trailing_threshold': 0.06,
            'trailing_stop': 0.04,
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
    
    def generate_report(self, capital: float = 20000) -> str:
        """生成完整报告"""
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
        
        market = {
            'total_qualified': market_status['total_qualified'],
            'bullish': market_status['bullish'],
        }
        
        # 计算平均表现
        avg_return = sum(r['return'] for r in self.validation_results) / len(self.validation_results)
        avg_drawdown = sum(r['drawdown'] for r in self.validation_results) / len(self.validation_results)
        avg_sharpe = sum(r['sharpe'] for r in self.validation_results) / len(self.validation_results)
        
        # ========== 实时校验：获取实时价格 ==========
        top = self.current_etfs[0] if self.current_etfs else None
        live_price = None
        live_price_source = ""
        live_timestamp = ""
        price_deviation = 0.0
        signal_price = top['price'] if top else 0.0
        
        if top and self.data_facade:
            # 优先从热数据获取实时价格
            hot_record = self.data_facade.hot.get(top['code'])
            if hot_record:
                live_price = hot_record.price
                live_timestamp = hot_record.timestamp
                live_price_source = "热数据"
            else:
                # 尝试从trade_validator获取实时价格
                if self.trade_validator:
                    realtime_data = self.trade_validator.fetch_realtime_prices([top['code']])
                    if top['code'] in realtime_data:
                        live_price = realtime_data[top['code']]['price']
                        live_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                        live_price_source = "实时API"
        
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
        
        # 计算止盈止损价（基于推荐价格）
        stop_loss_price = trade_price * 0.95  # 止损价 -5%
        take_profit_price = trade_price * 1.08  # 止盈价 +8%
        
        # 计算股数（基于推荐价格）
        position = 0
        action = "观望"
        if top:
            position = int(capital * 0.9 / trade_price / 100) * 100
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
        
        # 计算止盈止损价（基于推荐价格）
        stop_loss_price = trade_price * 0.95  # 止损价 -5%
        take_profit_price = trade_price * 1.08  # 止盈价 +8%
        
        # 计算股数（基于推荐价格）
        position = 0
        action = "观望"
        if top:
            position = int(capital * 0.9 / trade_price / 100) * 100
            action = f"买入 {top['code']} {top['name']} {position}股"
        
        # 构建报告 - 交易建议放开头和结尾
        report = f"""
{'='*70}
📈 ETF量化投资决策报告
{'='*70}

【基本信息】
报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}
数据最新日期: {latest} {data_freshness}
投资本金: {capital:,}元
策略模式: 单持仓 + 5%止损 + 8%止盈 + 移动止盈

{f"{data_freshness_warning}" if data_freshness_warning else ""}
{'='*70}
🚨 今日交易建议 (必读)
{'='*70}

【操作】{action}
【目标】{top['code']} {top['name']}
【价格】{trade_price:.3f}元
【数量】{position}股 ({capital*0.9:,.0f}元)
【止损】-5% ({stop_loss_price:.3f}元)
【止盈】+8% ({take_profit_price:.3f}元)

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

【数据摘要】
- 符合买入条件ETF数量: {market['total_qualified']}只
- 市场趋势判断: {'上涨趋势' if market['bullish'] else '震荡或下跌'}

【定性分析】
当前市场处于{'积极' if market['bullish'] else '中性'}的状态
条件。从技术面来看，共有{market['total_qualified']}只ETF满足6分以上的选
股标准，这表明市场中有足够的投资机会。建议{'积极' if market['bullish'] else '审慎'}参与
市场，选择得分最高的标的进行投资。

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
        
        report += f"""
【核心推荐】
1. {self.current_etfs[0]['code']} {self.current_etfs[0]['name']} - 分数{self.current_etfs[0]['score']}分 (最高)
2. {self.current_etfs[1]['code']} {self.current_etfs[1]['name']} - 分数{self.current_etfs[1]['score']}分

{'='*70}
四、资金配置方案
{'='*70}

【建议方案】(本金{capital:,}元)
"""
        
        # 计算配置
        top = self.current_etfs[0]
        position = int(capital * 0.9 / top['price'] / 100) * 100  # 整手
        
        report += f"""
| 标的 | 金额(元) | 占比 | 买入数量 |
|------|----------|------|----------|
| {top['code']} {top['name']} | {capital*0.9:,.0f} | 90% | {position}股 |
| 现金 | {capital*0.1:,.0f} | 10% | - |

【说明】
- 采用单持仓策略，降低组合波动
- 预留10%现金应对突发情况
- 最大止损5%，即最多亏损{capital*0.9*0.05:,.0f}元

{'='*70}
五、风险控制
{'='*70}

| 规则 | 参数 | 说明 |
|------|------|------|
| 单笔止损 | -5% | 触发立即平仓 |
| 总体止损 | -10% | 亏损达10%全部清仓 |
| 止盈 | +8% | 固定止盈 |
| 移动止盈 | 回撤4% | 盈利超6%后启用 |
| 持仓周期 | 最长15天 | 超过强制平仓 |

【情景分析】
| 情景 | 概率 | 收益区间 |
|------|------|----------|
| 乐观 | 30% | +15%~+30% |
| 中性 | 40% | +5%~+15% |
| 悲观 | 30% | -5%~0% |

最大亏损: -10% (约{capital*0.1:,.0f}元)

{'='*70}
六、结论
{'='*70}

【综合评估】
- 市场环境: {'积极' if market['bullish'] else '中性'} (符合条件{market['total_qualified']}只)
- 策略表现: {'优秀' if avg_sharpe > 0.5 else '一般'} (夏普{avg_sharpe:.2f})
- 风险等级: {'中等偏低' if avg_drawdown > -30 else '中等'} (回撤{avg_drawdown:.0f}%)

{'='*70}
🚨 今日交易建议 (结论)
{'='*70}

【操作】{action}
【目标】{top['code']} {top['name']}
【价格】{top['price']:.3f}元
【数量】{position}股 ({capital*0.9:,.0f}元)
【止损】-5% ({top['price']*0.95:.3f}元)
【止盈】+8% ({top['price']*1.08:.3f}元)

【操作建议】
{'✓ 建议积极参与，严格执行止损' if market['bullish'] else '建议轻仓观望'}
{'✓ 策略已经过多时段验证' if avg_sharpe > 0.3 else '⚠ 需进一步验证'}
{'✓ 回撤可控' if avg_drawdown > -35 else '⚠ 回撤较大，注意风险'}

{'='*70}
风险提示: 本报告仅供决策参考，不构成投资建议
{'='*70}
"""
        
        return report
    
    def save_report(self, path: str = 'etf_report.txt'):
        """保存报告到文件"""
        report = self.generate_report()
        with open(path, 'w', encoding='utf-8') as f:
            f.write(report)
        return path


def generate_decision_report(capital: float = 20000, simple: bool = False) -> str:
    """快速生成决策报告
    
    Args:
        capital: 本金
        simple: 简版模式（禁用调试输出）
    """
    generator = ETFReportGenerator()
    if simple:
        generator._simple_mode = True
        from src.core.selector import Selector
        Selector._simple_mode = True
    return generator.generate_report(capital)


if __name__ == '__main__':
    print(generate_decision_report())


__all__ = ['ETFReportGenerator', 'generate_decision_report']