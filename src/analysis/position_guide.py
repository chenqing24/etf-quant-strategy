#!/usr/bin/env python3
"""
持仓策略指导（US-007: Position Guide）

调研来源（按 SOUL 规则 13）：
- 本地 docs/POSITION_MANAGEMENT.md v8: stop_loss=-10%, sp=+15%, max_hold=15
- 本地 docs/SOP_06_MANUAL_TRADE.md v2.0: emotion 联动
- 本地 docs/SOP_06_V2_DESIGN.md: 5 情绪枚举
- 本地 SOP-17: 触发顺序（止损任意 > 止盈需 min_hold > 到期）
- 本地教训 22/67: 基于外部数据判断，不用 action 反推
- 本地 US-006 MarketRegimeDetector: 市场过滤
- GitHub DawnSyndrome: 情绪追踪
- GitHub leionion: session_analyzer

默认参数对齐 v8 POSITION_MANAGEMENT.md（用户 2026-06-03 决策）。
"""
import os
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Dict, List, Optional

from src.constants import DB_PATH


# ── 默认参数（对齐 v8 POSITION_MANAGEMENT.md）────────────────
DEFAULT_STOP_LOSS_PCT = -0.10      # -10% (v8)
DEFAULT_TAKE_PROFIT_PCT = 0.15     # +15% (v8)
DEFAULT_MIN_HOLD_DAYS = 3          # SOP-17 经验
DEFAULT_MAX_HOLD_DAYS = 15         # v8
DEFAULT_MAX_HOLDINGS = 2           # v8 + 用户 B 决策
DEFAULT_REBALANCE_THRESHOLD = 2    # 候选分差


@dataclass
class PositionGuide:
    """持仓策略指导（18 字段）"""
    code: str
    name: str

    # ── 现状 (5) ──
    quantity: int
    entry_price: float
    current_price: float
    pnl_pct: float
    hold_days: int

    # ── 阈值 (4) ──
    stop_loss_price: float
    take_profit_price: float
    expire_in_days: int
    min_hold_remaining: int

    # ── 信号 (3) ──
    market_regime: str
    current_score: int
    emotion_flag: str

    # ── 触发 (3) ──
    should_stop_loss: bool
    should_take_profit: bool
    should_expire: bool

    # ── 多持仓 (3) ──
    should_add_position: bool
    should_reduce_position: bool
    should_go_cash: bool

    # ── 建议 (2) ──
    action: str
    reason: str


class PositionGuideAnalyzer:
    """持仓策略指导分析器

    决策树（按 SOP-17 顺序 + v8 规则 + 用户 B 决策）：
      1. legacy_holding → 清仓（用户决策）
      2. 止损触发 → 止损
      3. 持仓 < min_hold → 持有（短期）
      4. 止盈触发 → 止盈
      5. 到期 → 到期评估
      6. 市场非 trend_up → 清仓空仓
      7. 持仓 < max_holdings + 评分高 → 可加仓
      8. 持仓 == max_holdings + 最低分低 → 换仓
      9. 默认 → 持有
    """

    def __init__(self,
                 db_path: str = None,
                 stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT,
                 take_profit_pct: float = DEFAULT_TAKE_PROFIT_PCT,
                 min_hold_days: int = DEFAULT_MIN_HOLD_DAYS,
                 max_hold_days: int = DEFAULT_MAX_HOLD_DAYS,
                 max_holdings: int = DEFAULT_MAX_HOLDINGS,
                 rebalance_threshold: int = DEFAULT_REBALANCE_THRESHOLD):
        self.db_path = db_path or DB_PATH
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.min_hold_days = min_hold_days
        self.max_hold_days = max_hold_days
        self.max_holdings = max_holdings
        self.rebalance_threshold = rebalance_threshold

    # ── 核心方法 ─────────────────────────────────────────

    def analyze_position(self,
                         code: str,
                         current_price: float = None,
                         market_regime: str = 'range_bound',
                         current_score: int = 0,
                         emotion_flag: str = '') -> Optional[PositionGuide]:
        """对单只持仓 ETF 输出操作建议

        Args:
            code:           ETF 代码
            current_price:  当前价（None 则查 realtime_cache）
            market_regime:  市场环境 trend_up/range_bound/trend_down/crash
            current_score:  当前策略评分
            emotion_flag:   最近交易情绪（空则查 trade_history）

        Returns:
            PositionGuide 或 None（无持仓时）
        """
        pos = self._load_position(code)
        if pos is None:
            return None

        # 实时价（如未传）
        if current_price is None:
            rt = self._get_realtime_price(code)
            current_price = rt if rt is not None else pos['entry_price']

        # 情绪（空则查 trade_history）
        if not emotion_flag:
            emotion_flag = self._get_recent_emotion(code)

        # 计算衍生字段
        pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
        stop_loss_price = pos['entry_price'] * (1 + self.stop_loss_pct)
        take_profit_price = pos['entry_price'] * (1 + self.take_profit_pct)
        hold_days = (date.today() - date.fromisoformat(pos['entry_date'])).days
        expire_in_days = max(0, self.max_hold_days - hold_days)
        min_hold_remaining = max(0, self.min_hold_days - hold_days)

        # 触发判断
        should_sl = current_price <= stop_loss_price
        should_sp = hold_days >= self.min_hold_days and current_price >= take_profit_price
        should_expire = hold_days >= self.max_hold_days

        # 多持仓 / 市场过滤
        active_count = self._count_active_positions()
        is_legacy = pos.get('legacy_holding', 0) == 1

        should_go_cash = market_regime in ('range_bound', 'trend_down', 'crash')
        should_add = (market_regime == 'trend_up'
                      and active_count < self.max_holdings
                      and current_score > 8)
        # 减仓需要明确低分（0 表示未传评分，不应触发）
        should_reduce = (active_count >= self.max_holdings
                        and 0 < current_score < 4)

        # 决策树
        action, reason = self._decide(
            is_legacy=is_legacy,
            should_sl=should_sl,
            should_sp=should_sp,
            should_expire=should_expire,
            hold_days=hold_days,
            current_price=current_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            min_hold_remaining=min_hold_remaining,
            should_go_cash=should_go_cash,
            market_regime=market_regime,
            should_add=should_add,
            should_reduce=should_reduce,
            pnl_pct=pnl_pct,
        )

        return PositionGuide(
            code=pos['code'],
            name=pos['name'],
            quantity=pos['quantity'],
            entry_price=pos['entry_price'],
            current_price=current_price,
            pnl_pct=pnl_pct,
            hold_days=hold_days,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            expire_in_days=expire_in_days,
            min_hold_remaining=min_hold_remaining,
            market_regime=market_regime,
            current_score=current_score,
            emotion_flag=emotion_flag,
            should_stop_loss=should_sl,
            should_take_profit=should_sp,
            should_expire=should_expire,
            should_add_position=should_add,
            should_reduce_position=should_reduce,
            should_go_cash=should_go_cash,
            action=action,
            reason=reason,
        )

    def analyze_portfolio(self,
                          market_regime: str = 'range_bound',
                          market_scores: Dict[str, int] = None) -> List[PositionGuide]:
        """对所有持仓批量分析

        Args:
            market_regime:  当前市场环境
            market_scores:  {code: score} 来自 core 池的当前评分
        """
        market_scores = market_scores or {}
        positions = self._load_all_positions()
        guides = []
        for pos in positions:
            code = pos['code']
            # emotion 取最近一笔交易
            emotion = self._get_recent_emotion(code)
            guide = self.analyze_position(
                code=code,
                current_price=None,  # 用 realtime
                market_regime=market_regime,
                current_score=market_scores.get(code, 0),
                emotion_flag=emotion,
            )
            if guide:
                guides.append(guide)
        return guides

    # ── 决策树 ─────────────────────────────────────────────

    def _decide(self, *, is_legacy, should_sl, should_sp, should_expire,
                hold_days, current_price, stop_loss_price, take_profit_price,
                min_hold_remaining, should_go_cash, market_regime,
                should_add, should_reduce, pnl_pct) -> tuple:
        """按 SOP-17 顺序决策"""
        # Step 1: legacy_holding 优先
        if is_legacy:
            return '清仓（用户决策）', '此标的为 legacy_holding，策略不再覆盖，按用户 2026-06-03 决策清仓'

        # Step 2: 止损
        if should_sl:
            return '止损', f"价格 {current_price:.3f} ≤ 止损价 {stop_loss_price:.3f}"

        # Step 3: 持仓 < min_hold（止盈窗口未到）
        if min_hold_remaining > 0:
            return '持有（短期）', f"持仓 {hold_days} 天 < min_hold，还需 {min_hold_remaining} 天进入止盈窗口"

        # Step 4: 止盈
        if should_sp:
            return '止盈', f"持仓 {hold_days} 天 ≥ min_hold，价格 {current_price:.3f} ≥ 止盈价 {take_profit_price:.3f}"

        # Step 5: 到期
        if should_expire:
            return '到期评估', f"持仓 {hold_days} 天 ≥ max_hold {self.max_hold_days}，强制评估"

        # Step 6: 市场过滤
        if should_go_cash:
            return '清仓空仓', f"市场 {market_regime}（非 trend_up），按规则空仓"

        # Step 7: 加仓
        if should_add:
            return '可加仓到第 2 只', f"市场 trend_up，当前评分 {self.max_holdings} 之下，可加仓"

        # Step 8: 换仓
        if should_reduce:
            return '换仓到高分', f"持仓已满 {self.max_holdings} 只，评分低，可换高分"

        # Step 9: 默认
        return '持有', f"盈亏 {pnl_pct:.1%}，持仓 {hold_days} 天，趋势正常"

    # ── 数据访问 ─────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _load_position(self, code: str) -> Optional[dict]:
        conn = self._get_conn()
        try:
            row = conn.execute("""
                SELECT code, name, entry_date, entry_price, quantity, status,
                       is_real, legacy_holding
                FROM positions WHERE code = ?
            """, (code,)).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return {
            'code': row[0], 'name': row[1], 'entry_date': row[2],
            'entry_price': row[3], 'quantity': row[4], 'status': row[5],
            'is_real': row[6], 'legacy_holding': row[7],
        }

    def _load_all_positions(self) -> List[dict]:
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT code, name, entry_date, entry_price, quantity, status,
                       is_real, legacy_holding
                FROM positions
            """).fetchall()
        finally:
            conn.close()
        return [{
            'code': r[0], 'name': r[1], 'entry_date': r[2],
            'entry_price': r[3], 'quantity': r[4], 'status': r[5],
            'is_real': r[6], 'legacy_holding': r[7],
        } for r in rows]

    def _count_active_positions(self) -> int:
        conn = self._get_conn()
        try:
            row = conn.execute("""
                SELECT COUNT(*) FROM positions
                WHERE status IN ('HOLDING', 'REBALANCING', 'CLOSING')
            """).fetchone()
        finally:
            conn.close()
        return row[0] if row else 0

    def _get_realtime_price(self, code: str) -> Optional[float]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT price FROM realtime_cache WHERE code = ?", (code,)
            ).fetchone()
        finally:
            conn.close()
        return row[0] if row and row[0] else None

    def _get_recent_emotion(self, code: str) -> str:
        """取最近一笔交易的 emotion（用于情绪预警）"""
        conn = self._get_conn()
        try:
            row = conn.execute("""
                SELECT emotion FROM trade_history
                WHERE code = ? AND emotion IS NOT NULL
                ORDER BY id DESC LIMIT 1
            """, (code,)).fetchone()
        finally:
            conn.close()
        return row[0] if row else ''
