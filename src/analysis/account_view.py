#!/usr/bin/env python3
"""
账户视图生成器（US-012 方案 B）

设计原则：
- 9 步决策树作单一真相源（复用 US-007 PositionGuideAnalyzer）
- 输出 4 段：① 当前持仓 ② 今日推荐 ③ 动作清单 ④ 账户状态
- 细粒度字段：数量/价格/金额/止损止盈线
- 钉钉推送规则：有动作/警告推，全静默不推
- 只展示情况：legacy_holding 标"⚠️ legacy_holding"由用户决定

被谁调用：
    - src/cli/decision.py（-m account 模式）
    - cron_etf.txt 14:30 自动跑
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any

from src.analysis.position_guide import PositionGuideAnalyzer, PositionGuide
from src.trade.tracker import TradeTracker
from src.analysis.report_generator import generate_decision_report


# ── 9 步决策树 → 优先级映射（US-012 方案 B）──────────────
# 9 步决策树作单一真相源，输出时按 9 步序号排序
ACTION_PRIORITY = {
    # 9 步决策树 P1-P9
    "清仓（用户决策）": 1,           # legacy
    "止损": 2,
    "持有（短期）": 3,               # 短期持有
    "止盈": 4,
    "到期评估": 5,
    "清仓空仓": 6,                   # 市场空仓
    "可加仓到第 2 只": 7,
    "换仓到高分": 8,
    "持有": 9,
}

ACTION_REASON_EN = {
    "清仓（用户决策）": "legacy_holding (user decision required)",
    "止损": "stop loss triggered",
    "持有（短期）": "hold period not met",
    "止盈": "take profit triggered",
    "到期评估": "max hold days reached",
    "清仓空仓": "market regime unfavorable",
    "可加仓到第 2 只": "add position allowed",
    "换仓到高分": "rotate to higher score",
    "持有": "hold",
}


@dataclass
class ActionItem:
    """动作清单条目（细粒度）"""
    code: str
    name: str
    action: str                  # 9 步决策树输出
    action_priority: int         # 1-9
    quantity: int                # 数量
    entry_price: float           # 入场价
    current_price: float         # 当前价
    amount: float                # 金额 = quantity × current_price
    pnl_pct: float               # 盈亏 %
    hold_days: int               # 持仓天数
    stop_loss_price: float       # 止损价
    take_profit_price: float     # 止盈价
    expire_in_days: int          # 剩余到期天数
    reason: str                  # 触发原因
    legacy_holding: bool = False # 是否 legacy
    is_user_decision_required: bool = False  # 是否需用户决定

    def format_one_line(self) -> str:
        """单行摘要（钉钉推送用）"""
        return (f"P{self.action_priority} {self.action} {self.code} {self.name} "
                f"{self.quantity}股 @{self.current_price:.3f} "
                f"盈亏 {self.pnl_pct:+.1f}% 持仓{self.hold_days}天")


class AccountView:
    """统一账户视图生成器（US-012 方案 B）

    9 步决策树作单一真相源，输出 4 段：
    ① 当前持仓（细粒度）
    ② 今日推荐（细粒度）
    ③ 动作清单（按 9 步决策树 P1-P9 排序）
    ④ 账户状态
    """

    def __init__(self,
                 db_path: str = None,
                 market_regime: str = None,
                 webhook_url: str = None):
        """
        Args:
            db_path: DB 路径（默认 constants.DB_PATH）
            market_regime: 市场环境（None=自动检测）
            webhook_url: 钉钉 webhook（None=不推送）
        """
        self.tracker = TradeTracker(data_dir='.', db_path=db_path)
        self.position_analyzer = PositionGuideAnalyzer(db_path=db_path)
        # 市场环境自动检测
        if market_regime is None:
            try:
                from src.analysis.market_regime import MarketRegimeDetector
                from src.data.loader import DataLoader
                loader = DataLoader()
                df = loader.load_etf_history('510300')
                self.market_regime = MarketRegimeDetector().detect(df)
            except Exception:
                self.market_regime = 'range_bound'
        else:
            self.market_regime = market_regime
        self.webhook_url = webhook_url
        self._action_items: List[ActionItem] = []
        self._recommendation: Optional[Dict[str, Any]] = None
        self._holdings_guides: List[PositionGuide] = []

    def generate(self) -> str:
        """生成完整账户视图"""
        # ① 当前持仓（9 步决策树）
        self._holdings_guides = self.position_analyzer.analyze_portfolio(
            market_regime=self.market_regime
        )
        # ② 今日推荐（复用 US-009/010）
        try:
            self._recommendation = self._extract_recommendation()
        except Exception as e:
            self._recommendation = {'error': str(e)}
        # ③ 动作清单（按 9 步优先级）
        self._action_items = self._build_action_items()
        # ④ 账户状态
        account = self.tracker.get_account_summary()

        return self._format(account)

    def _extract_recommendation(self) -> Dict[str, Any]:
        """从 ETFReportGenerator 提取今日推荐"""
        from src.analysis.report_generator import ETFReportGenerator
        gen = ETFReportGenerator()
        report = gen.generate_report(capital=20000, tracker=self.tracker)
        # 提取关键字段
        return {
            'report': report,
            'top_etf': gen.current_etfs[0] if gen.current_etfs else None,
        }

    def _build_action_items(self) -> List[ActionItem]:
        """按 9 步决策树生成动作清单"""
        items = []
        for guide in self._holdings_guides:
            priority = ACTION_PRIORITY.get(guide.action, 9)
            item = ActionItem(
                code=guide.code,
                name=guide.name,
                action=guide.action,
                action_priority=priority,
                quantity=int(guide.quantity),
                entry_price=guide.entry_price,
                current_price=guide.current_price,
                amount=guide.current_price * guide.quantity,
                pnl_pct=guide.pnl_pct,
                hold_days=guide.hold_days,
                stop_loss_price=guide.stop_loss_price,
                take_profit_price=guide.take_profit_price,
                expire_in_days=guide.expire_in_days,
                reason=guide.reason,
                legacy_holding=(guide.action == "清仓（用户决策）"),
                is_user_decision_required=(guide.action == "清仓（用户决策）"),
            )
            items.append(item)

        # 按 9 步优先级排序（P1 → P9）
        items.sort(key=lambda x: (x.action_priority, x.code))
        return items

    def _format(self, account: dict) -> str:
        """格式化 4 段输出"""
        lines = []
        # 顶部
        regime_emoji = {
            'trend_up': '📈', 'range_bound': '📊',
            'trend_down': '🔻', 'crash': '🚨'
        }.get(self.market_regime, '📊')
        lines.append("=" * 80)
        lines.append(
            f"📊 账户视图 (US-012) | {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
            f"市场: {regime_emoji} {self.market_regime}"
        )
        lines.append("=" * 80)

        # ① 当前持仓（细粒度）
        lines.append("")
        lines.append("【一、当前持仓（细粒度）】")
        if not self._holdings_guides:
            lines.append("  (无)")
        for g in self._holdings_guides:
            legacy_tag = "  ⚠️ legacy_holding" if g.action == "清仓（用户决策）" else ""
            lines.append(f"  【{g.code} {g.name}】{legacy_tag}")
            lines.append(
                f"    数量 {int(g.quantity)} @ 入场 {g.entry_price:.3f} / "
                f"现价 {g.current_price:.3f}"
            )
            lines.append(
                f"    盈亏 {g.pnl_pct:+.2f}% / 持仓 {g.hold_days} 天"
            )
            lines.append(
                f"    止损 {g.stop_loss_price:.3f} (-10%) / "
                f"止盈 {g.take_profit_price:.3f} (+15%) / "
                f"到期 {g.expire_in_days} 天"
            )
            lines.append(f"    决策树 P{ACTION_PRIORITY.get(g.action, 9)}：{g.reason}")

        # ② 今日推荐（细粒度）
        lines.append("")
        lines.append("【二、今日推荐（细粒度）】")
        if self._recommendation and self._recommendation.get('top_etf'):
            top = self._recommendation['top_etf']
            lines.append(f"  推荐: {top['code']} {top['name']}")
            lines.append(
                f"  价格 {top['price']:.3f} / 分数 {top['score']} / "
                f"理由 {top.get('reasons', [])}"
            )
        else:
            lines.append(f"  ⚠️ 推荐生成失败: {self._recommendation.get('error', '未知')}")

        # 资金配置状态
        cash = account.get('cash', 0)
        positions_value = account.get('positions_value', 0)
        total_asset = account.get('total_asset', 0)
        hold_count = account.get('hold_count', 0)
        max_holdings = account.get('max_holdings', 2)
        available = max(0, total_asset * 0.9 - positions_value)
        if hold_count >= max_holdings:
            lines.append(f"  状态: ⚠️ 已达仓位上限（{hold_count}/{max_holdings}），暂不买入")
        else:
            lines.append(
                f"  状态: 可投入 {available:,.0f}元 / "
                f"持仓 {hold_count}/{max_holdings}只"
            )

        # ③ 动作清单（按 9 步优先级 P1-P9）
        lines.append("")
        lines.append("【三、动作清单（9 步决策树优先级）】")
        if not self._action_items:
            lines.append("  (无持仓，无动作)")
        else:
            # 按优先级分组输出
            by_priority = {}
            for item in self._action_items:
                by_priority.setdefault(item.action_priority, []).append(item)
            for p in range(1, 10):
                if p in by_priority:
                    for item in by_priority[p]:
                        legacy_mark = " ⚠️ 用户决策" if item.is_user_decision_required else ""
                        lines.append(
                            f"  P{p} {item.action}{legacy_mark} | "
                            f"{item.code} {item.name} | "
                            f"{item.quantity}股 @ {item.current_price:.3f} | "
                            f"盈亏 {item.pnl_pct:+.1f}% | "
                            f"持仓{item.hold_days}天"
                        )
                        # 细粒度补充
                        lines.append(
                            f"        止损 {item.stop_loss_price:.3f} | "
                            f"止盈 {item.take_profit_price:.3f} | "
                            f"到期 {item.expire_in_days}天 | "
                            f"金额 {item.amount:,.0f}元"
                        )

        # ④ 账户状态
        lines.append("")
        lines.append("【四、账户状态】")
        lines.append(
            f"  现金 {cash:,.0f}元 / 持仓市值 {positions_value:,.0f}元 / "
            f"总资产 {total_asset:,.0f}元"
        )
        lines.append(
            f"  可投入 {available:,.0f}元（仓位90%上限） / "
            f"已持仓 {hold_count}/{max_holdings}只"
        )

        # 钉钉推送
        if self.webhook_url:
            self._send_dingtalk(lines, account)

        return "\n".join(lines)

    def _send_dingtalk(self, lines: List[str], account: dict) -> None:
        """钉钉推送（按 SOUL 规则 4.3：有动作/警告推）"""
        import requests
        # 触发条件：有动作/有警告
        has_action = any(not item.is_user_decision_required for item in self._action_items)
        has_warning = (
            "⚠️" in "\n".join(lines) or
            account.get('hold_count', 0) >= account.get('max_holdings', 2)
        )
        if not (has_action or has_warning):
            return  # 全静默不推

        # 推送（简化：只推摘要 + 钉钉标题）
        title = "📊 ETF账户视图"
        summary = "\n".join(lines[:30])  # 前 30 行
        try:
            requests.post(
                self.webhook_url,
                json={"msgtype": "markdown", "markdown": {
                    "title": title,
                    "text": f"## {title}\n\n{summary}"
                }},
                timeout=10
            )
        except Exception as e:
            print(f"[WARN] 钉钉推送失败: {e}")


if __name__ == '__main__':
    import sys
    webhook = sys.argv[1] if len(sys.argv) > 1 else None
    view = AccountView(webhook_url=webhook)
    print(view.generate())
