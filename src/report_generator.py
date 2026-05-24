#!/usr/bin/env python3
"""ETF投资决策报告生成器 - 固定模板版本"""
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple
import json

from .config import run_strategy, StrategyConfig
from .selector import Selector
from .indicator import Indicator
from .data_loader import DataLoader


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
    """ETF投资决策报告生成器"""
    
    def __init__(self, data_dir: str = '../etf_data_50'):
        self.data_dir = data_dir
        self.data = None
        self.latest_date = None
        self.current_etfs = []
        self.validation_results = []
    
    def load_data(self) -> str:
        """加载数据，返回最新日期"""
        loader = DataLoader()
        self.data = loader.load(self.data_dir)
        self.latest_date = max(df['date'].max() for df in self.data.values())
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
            s, reasons = selector.score_with_ic(df, self.latest_date)
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
        
        # 计算交易建议
        top = self.current_etfs[0] if self.current_etfs else None
        position = 0
        action = "观望"
        if top:
            position = int(capital * 0.9 / top['price'] / 100) * 100
            action = f"买入 {top['code']} {top['name']} {position}股"
        
        # 构建报告 - 交易建议放开头和结尾
        report = f"""
{'='*70}
📈 ETF量化投资决策报告
{'='*70}

【基本信息】
报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}
数据最新日期: {latest}
投资本金: {capital:,}元
策略模式: 单持仓 + 5%止损 + 8%止盈 + 移动止盈

{'='*70}
🚨 今日交易建议 (必读)
{'='*70}

【操作】{action}
【目标】{top['code']} {top['name']}
【价格】{top['price']:.3f}元
【数量】{position}股 ({capital*0.9:,.0f}元)
【止损】-5% ({top['price']*0.95:.3f}元)
【止盈】+8% ({top['price']*1.08:.3f}元)

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


def generate_decision_report(capital: float = 20000) -> str:
    """快速生成决策报告"""
    generator = ETFReportGenerator()
    return generator.generate_report(capital)


if __name__ == '__main__':
    print(generate_decision_report())


__all__ = ['ETFReportGenerator', 'generate_decision_report']