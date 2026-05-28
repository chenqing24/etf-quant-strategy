#!/usr/bin/env python3
"""统一报告构建器

支持简版报告（钉钉/移动端）和详细报告（PC端）
"""
from typing import Dict, Optional
from datetime import datetime


class ReportBuilder:
    """统一报告构建器"""
    
    def __init__(self):
        self._etf_names = self._load_etf_names()
    
    @staticmethod
    def _load_etf_names() -> Dict[str, str]:
        """加载ETF名称映射（已通过腾讯API验证）"""
        return {
            '510300': '沪深300',
            '510500': '中证500',
            '159919': '沪深300ETF',
            '159915': '创业板ETF',
            '512880': '证券ETF',
            '512170': '医疗ETF',
            '512200': '房地产ETF',
            '159928': '消费ETF',
            '159825': '农业ETF',
            '512010': '医药ETF',
            '512500': '中证500ETF',
            '159952': '创业板ETF',
            '159997': '券商ETF',
            '159995': '芯片ETF',
            '512760': '芯片ETF',
            '159801': '芯片ETF',
            '159823': '新能源车',
            '515050': '5GETF',
            '159857': '光伏ETF',
            '516160': '新能源ETF',
            '159806': '新能源车',
            '159942': '教育ETF',
            '510050': '上证50',
            '512660': '军工ETF',
            '159920': '中证500ETF',
            '159867': '农业ETF',
            '518880': '黄金ETF',
            '159934': '黄金ETF',
            '159577': '美国50ETF汇添富',  # 2026-05-28 腾讯API验证
        }
    
    def get_etf_name(self, code: str) -> str:
        """获取ETF名称"""
        return self._etf_names.get(code, code)
    
    def build_simple(self, results: Dict) -> str:
        """构建简版报告（钉钉/移动端）
        
        钉钉Markdown支持：标题(#)、加粗(**)、分隔线(---)、列表(-)
        钉钉Markdown不支持：表格语法
        
        Args:
            results: {
                'action': '买入'|'卖出'|'观望',
                'code': '510300',
                'price': 3.856,
                'realtime': {'price': 3.860, 'change_pct': 1.5},
                'indicators': {'rsi_14': 72},
                'pnl': 5.2,
                'data_freshness': '❌ 数据过期',
                'data_freshness_warning': '数据超过4天未更新'
            }
        Returns:
            str: Markdown格式简版报告
        """
        action = results.get('action', '观望')
        code = results.get('code', '')
        price = results.get('price', 0)
        realtime = results.get('realtime', {})
        indicators = results.get('indicators', {})
        pnl = results.get('pnl', 0)
        data_freshness = results.get('data_freshness', '')
        data_warning = results.get('data_freshness_warning', '')
        
        name = self.get_etf_name(code)
        msg_time = datetime.now().strftime('%m-%d %H:%M')
        
        # 钉钉换行规则：行尾加2个空格
        def ln(text): return text + "  " if text else text
        
        lines = [
            ln(f"## 📈 ETF量化决策 {msg_time}"),
            "",
        ]
        
        # 数据过期警告
        if data_freshness and '过期' in data_freshness:
            lines.append(ln(f"⚠️ {data_freshness}"))
            if data_warning:
                lines.append(ln(f"   {data_warning}"))
            lines.append("")
        
        if action == '买入':
            lines.extend([
                ln(f"**🟢 买入** {code} {name}"),
                ln(f"信号价: **{price:.3f}**"),
            ])
            
            # 添加实时数据
            if realtime and realtime.get('price'):
                rt_price = realtime.get('price', 0)
                rt_change = realtime.get('change_pct', 0)
                rt_source = realtime.get('source', '未知')
                deviation = ((rt_price - price) / price * 100) if price > 0 else 0
                
                # 显示数据来源
                if '昨收盘' in rt_source:
                    lines.append(ln(f"昨收: **{rt_price:.3f}** (API不可用)"))
                else:
                    lines.append(ln(f"实时价: **{rt_price:.3f}** ({rt_change:+.2f}%)"))
                
                # 偏离警告
                if abs(deviation) > 5:
                    lines.append(ln(f"⚠️ 偏离信号 {deviation:+.1f}%"))
            
            # RSI状态
            if indicators:
                rsi = indicators.get('rsi_14', 0)
                if rsi:
                    if rsi > 75:
                        status = "🔥过热"
                    elif rsi > 30:
                        status = "✅正常"
                    else:
                        status = "💤超卖"
                    lines.append(ln(f"RSI14: **{rsi:.1f}** {status}"))
            
            # 分隔线 + 风控
            lines.append("")  # 空行
            lines.append("---")  # 分隔线
            lines.append("")  # 空行
            lines.append(ln(f"🛡️ 止损: **{price*0.94:.3f}** (-6%)"))
            lines.append(ln(f"🎯 止盈: **{price*1.10:.3f}** (+10%)"))
            
        elif action == '卖出':
            lines.append(ln(f"**🔴 卖出** {code} {name}"))
            if pnl:
                lines.append(ln(f"盈亏: **{pnl:+.2f}%**"))
        else:
            lines.append(ln(f"**⚪ 观望**"))
            lines.append("等待更好的机会")
        
        return "\n".join(lines)
    
    def build_full(self, results: Dict, report_file: str = None) -> str:
        """构建详细报告（PC端）
        
        Args:
            results: 决策结果
            report_file: 可选的完整报告文件路径
        Returns:
            str: 详细报告内容
        """
        # 如果提供了报告文件，读取完整内容
        if report_file:
            try:
                with open(report_file, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception:
                pass
        
        # 否则构建标准详细报告
        action = results.get('action', '观望')
        code = results.get('code', '')
        name = self.get_etf_name(code)
        price = results.get('price', 0)
        
        lines = [
            "=" * 60,
            "📊 ETF量化决策详细报告",
            "=" * 60,
            f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            f"操作: {action}",
            f"标的: {code} {name}",
            f"价格: {price:.4f}",
            "",
            "=" * 60,
        ]
        
        return "\n".join(lines)


# 单例实例
_builder = None

def get_builder() -> ReportBuilder:
    """获取报告构建器单例"""
    global _builder
    if _builder is None:
        _builder = ReportBuilder()
    return _builder
