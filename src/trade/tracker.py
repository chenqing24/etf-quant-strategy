#!/usr/bin/env python3
"""
交易追踪与记录模块

用途：
    - 记录买入/卖出交易
    - 追踪持仓状态
    - 计算收益和绩效
    - 管理止损止盈

被谁调用：
    - src/cli/decision.py（决策引擎执行交易时调用）
    - src/risk/manager.py（风控检查时调用）
    - 其他需要交易记录的模块

功能说明：
    - TradeRecord 数据类定义交易记录格式
    - TradeTracker 类管理交易状态
    - 自动计算持仓天数和收益
    - 支持止损止盈触发

使用方式：
    from src.trade.tracker import TradeTracker
    
    tracker = TradeTracker()
    tracker.record_buy(code, price, quantity)
    tracker.check_stop_loss()
    tracker.check_take_profit()

依赖：
    - src.constants (TRADES_FILE, TENCENT_QT_URL, HTTP_TIMEOUT_SHORT)
    - requests（获取实时价格）

注意事项：
    - 交易记录保存到 etf_data_live/etf_trades.json
    - 持仓记录保存到 etf_data_live/etf_positions.json
    - 符合 TRADE_RECORD_SPEC.md 规范
"""
import csv
import json
import os
import time
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import requests
import logging

from src.constants import TRADES_FILE, TENCENT_QT_URL, HTTP_TIMEOUT_SHORT, DB_PATH


# ── 情绪/时段常量（SOP-06 v2.0）────────────────────────────────
EMOTION_OPTIONS = ["calm", "euphoria", "fear", "fomo", "regret"]
SESSION_OPTIONS = [
    ("A", "00:00-04:00 UTC 亚洲尾盘"),
    ("B", "04:00-08:00 UTC 欧洲早盘"),
    ("C", "08:00-12:00 UTC 欧洲午盘"),
    ("D", "12:00-16:00 UTC 美洲早盘"),
    ("E", "16:00-20:00 UTC 美洲午盘"),
    ("F", "20:00-24:00 UTC 美洲尾盘"),
]


@dataclass
class TradeRecord:
    """交易记录（SOP-06 v2.0: 信号快照 + 情绪 + 时段）"""
    date: str           # 交易日期
    code: str           # ETF代码
    name: str           # ETF名称
    action: str         # buy/sell
    price: float        # 成交价格
    quantity: int       # 数量
    amount: float       # 金额
    reason: str         # 交易原因
    expected_return: float = 0    # 预期收益
    actual_pnl: float = 0         # 实际盈亏
    note: str = ""                # 备注

    # ── US-005 增强字段（买入时快照）─────────────────────────────
    realtime_price: float = 0.0   # 实时价格
    price_deviation: float = 0.0  # 偏差率 (%)
    rsi_14: float = 0.0           # RSI(14) 值
    day_change_pct: float = 0.0   # 当日涨跌幅 (%)
    score: int = 0               # 策略评分
    # ─────────────────────────────────────────────────────────────

    # ── SOP-06 信号快照 ─────────────────────────────────────────
    signal_time: str = ""         # 信号发出时间 (YYYY-MM-DD HH:MM)
    signal_price: float = 0.0     # 信号发出时的价格
    signal_rsi: float = 0.0       # RSI(14)
    signal_adx: float = 0.0       # ADX(14)
    signal_score: int = 0         # 信号评分
    # ─────────────────────────────────────────────────────────────

    # ── SOP-06 v2.0 增强字段 ───────────────────────────────────
    trade_time: str = ""          # 实际成交时间 (YYYY-MM-DD HH:MM)
    emotion: str = ""            # 交易情绪 (calm/euphoria/fear/fomo/regret)
    session: str = ""            # 交易时段 (A/B/C/D/E/F)
    # ─────────────────────────────────────────────────────────────

    # ── US-008 新增：区分实盘/模拟（默认保守 0）────────────
    is_real: int = 0             # 0=模拟, 1=实盘
    is_paper: int = 0            # 0=非纸面, 1=纸面（回测用）
    # ─────────────────────────────────────────────────────────────

    # ── Q-009 决策上下文（之前漏的）──────────────────────────
    model: str = ""              # 模型名 'ETF量化决策v8_sop'
    strategy: str = ""           # 策略配置 JSON 字符串
    evaluation: str = ""         # 评价指标 JSON 字符串
    snapshot_ref: str = ""       # 决策快照文件路径
    # ─────────────────────────────────────────────────────────────


def _infer_session(trade_time: str) -> str:
    """从交易时间推断UTC时段
    
    来源：参考 leionion/ai-trading-journal-audit-tool/session_analyzer.py
    """
    if not trade_time:
        return ""
    
    try:
        # 支持格式: "2026-06-02 10:40" 或 "10:40"
        if len(trade_time) > 5 and " " in trade_time:
            time_part = trade_time.split(" ")[1]
        else:
            time_part = trade_time
        
        hour = int(time_part.split(":")[0])
        
        # UTC时段划分（+8转北京时间）
        utc_hour = (hour - 8) % 24
        
        if 0 <= utc_hour < 4:
            return "A"  # 亚洲尾盘
        elif 4 <= utc_hour < 8:
            return "B"  # 欧洲早盘
        elif 8 <= utc_hour < 12:
            return "C"  # 欧洲午盘
        elif 12 <= utc_hour < 16:
            return "D"  # 美洲早盘
        elif 16 <= utc_hour < 20:
            return "E"  # 美洲午盘
        else:
            return "F"  # 美洲尾盘
    except:
        return ""


def _validate_emotion(emotion: str) -> str:
    """校验情绪值，无效则返回空"""
    if emotion in EMOTION_OPTIONS:
        return emotion
    return ""


# ── US-005: 持仓状态机 ─────────────────────────────────────
# 状态流转：EMPTY → PENDING → HOLDING → CLOSING → EMPTY
#                              ↘ REBALANCING ↗
POSITION_STATUS = {
    'EMPTY': '空仓',
    'PENDING': '待买入',
    'HOLDING': '持仓中',
    'REBALANCING': '换仓中',
    'CLOSING': '待平仓',
}

# 合法状态转换图
VALID_TRANSITIONS = {
    'EMPTY': {'PENDING'},
    'PENDING': {'HOLDING', 'EMPTY'},  # 取消买入 → EMPTY
    'HOLDING': {'CLOSING', 'REBALANCING'},
    'REBALANCING': {'HOLDING', 'EMPTY'},  # 换仓完成 → 新持仓 或 失败 → 空仓
    'CLOSING': {'EMPTY'},
}


@dataclass
class Position:
    """持仓（US-005: 含状态机）"""
    code: str
    name: str
    entry_date: str
    entry_price: float
    quantity: int
    current_price: float = 0
    pnl_pct: float = 0
    hold_days: int = 0
    status: str = 'EMPTY'  # US-005: 状态机字段
    score: int = 0  # US-005: 持仓评分（用于换仓决策）

    # ── US-008 新增 ───────────────────────────────────────────
    is_real: int = 0             # 0=模拟, 1=实盘
    legacy_holding: int = 0      # 0=否, 1=是（legacy_holding 角色）
    # ─────────────────────────────────────────────────────────────
    # ── US-014 R2 新增 ─────────────────────────────────────────
    is_reference: int = 0        # 0=否, 1=是（reference 池，可交易但非 core）
    # ─────────────────────────────────────────────────────────────


class TradeTracker:
    """交易追踪器（US-008: 数据从 JSON 迁到 SQLite）

    数据存储：
      - trade_history: 交易记录（替代 etf_trades.json）
      - positions:     持仓（替代 etf_positions.json）
      - audit_log:     状态机审计（替代 etf_audit_log.json）

    API 兼容性：
      - load_trades() / save_trade() 签名不变
      - load_positions() / save_positions() 签名不变
      - record_buy / record_sell 加 is_real 默认参数
    """

    def __init__(self, data_dir: str = '.', db_path: str = None):
        self.data_dir = data_dir
        # US-008: 默认用常量 DB_PATH，测试可传临时 db_path
        from src.constants import DB_PATH
        self.db_path = db_path or DB_PATH
        # US-009 修复: US-008 改 __init__ 时漏了 self.performance_file
        # （get_account_summary() 依赖此属性读现金余额）
        self.performance_file = os.path.join(data_dir, 'etf_performance.json')
        self._ensure_db()

    def _get_conn(self):
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)

    def _ensure_db(self):
        """验证 3 张表存在，不存在则提示运行迁移"""
        conn = self._get_conn()
        try:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('trade_history','positions','audit_log')"
            ).fetchall()]
            if not all(t in tables for t in ['trade_history', 'positions', 'audit_log']):
                print(f'[WARN] DB 缺表 {tables}，请运行 scripts/migrate_trade_to_db.py')
        finally:
            conn.close()

    def load_trades(self) -> List[TradeRecord]:
        """加载交易记录（US-008: 查 trade_history 表）"""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT date, code, name, action, price, quantity, amount, reason,
                       expected_return, actual_pnl, note,
                       realtime_price, price_deviation, rsi_14, day_change_pct, score,
                       signal_time, signal_price, signal_rsi, signal_adx, signal_score,
                       trade_time, emotion, session,
                       is_real, is_paper,
                       model, strategy, evaluation, snapshot_ref
                FROM trade_history ORDER BY id
            """).fetchall()
        finally:
            conn.close()
        return [TradeRecord(
            date=r[0], code=r[1], name=r[2], action=r[3],
            price=r[4], quantity=r[5], amount=r[6], reason=r[7] or '',
            expected_return=r[8] or 0, actual_pnl=r[9] or 0, note=r[10] or '',
            realtime_price=r[11] or 0.0, price_deviation=r[12] or 0.0,
            rsi_14=r[13] or 0.0, day_change_pct=r[14] or 0.0, score=r[15] or 0,
            signal_time=r[16] or '', signal_price=r[17] or 0.0,
            signal_rsi=r[18] or 0.0, signal_adx=r[19] or 0.0, signal_score=r[20] or 0,
            trade_time=r[21] or '', emotion=r[22] or '', session=r[23] or '',
            is_real=r[24] or 0, is_paper=r[25] or 0,
            model=r[26] or '', strategy=r[27] or '',
            evaluation=r[28] or '', snapshot_ref=r[29] or '',
        ) for r in rows]

    def save_trade(self, trade: TradeRecord):
        """保存交易记录（US-008: 写 trade_history 表）"""
        # US-008: emotion/session 空字符串转 None（CHECK 约束要求）
        emotion = trade.emotion if trade.emotion else None
        session = trade.session if trade.session else None
        model = trade.model if trade.model else None
        strategy = trade.strategy if trade.strategy else None
        evaluation = trade.evaluation if trade.evaluation else None
        snapshot_ref = trade.snapshot_ref if trade.snapshot_ref else None

        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT INTO trade_history (
                    date, code, name, action, price, quantity, amount, reason,
                    expected_return, actual_pnl, note,
                    realtime_price, price_deviation, rsi_14, day_change_pct, score,
                    signal_time, signal_price, signal_rsi, signal_adx, signal_score,
                    trade_time, emotion, session,
                    is_real, is_paper,
                    model, strategy, evaluation, snapshot_ref
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                trade.date, trade.code, trade.name, trade.action,
                trade.price, trade.quantity, trade.amount, trade.reason,
                trade.expected_return, trade.actual_pnl, trade.note,
                trade.realtime_price, trade.price_deviation,
                trade.rsi_14, trade.day_change_pct, trade.score,
                trade.signal_time, trade.signal_price,
                trade.signal_rsi, trade.signal_adx, trade.signal_score,
                trade.trade_time, emotion, session,
                trade.is_real, trade.is_paper,
                model, strategy, evaluation, snapshot_ref,
            ))
            conn.commit()
        finally:
            conn.close()

    def load_positions(self) -> List[Position]:
        """加载当前持仓（US-008: 查 positions 表，US-014 R2: 含 is_reference）"""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT code, name, entry_date, entry_price, quantity,
                       current_price, pnl_pct, hold_days, status, score,
                       is_real, legacy_holding, is_reference
                FROM positions
            """).fetchall()
        finally:
            conn.close()
        return [Position(
            code=r[0], name=r[1], entry_date=r[2], entry_price=r[3],
            quantity=r[4], current_price=r[5] or 0, pnl_pct=r[6] or 0,
            hold_days=r[7] or 0, status=r[8] or 'EMPTY', score=r[9] or 0,
            is_real=r[10] or 0, legacy_holding=r[11] or 0,
            is_reference=r[12] or 0,  # US-014 R2
        ) for r in rows]

    def save_positions(self, positions: List[Position]):
        """保存持仓（US-008: 写 positions 表，全量替换语义）

        实现：先 DELETE 不在传入列表中的 code，再 INSERT OR REPLACE 传入列表。
        这与原 JSON "全量替换" 行为一致：传入什么就保存什么。

        状态机原子操作请用 transition_position()，它内部用 save_positions 实现。
        """
        conn = self._get_conn()
        try:
            # 1. 删除不在传入列表中的 code
            new_codes = {p.code for p in positions}
            existing = [r[0] for r in conn.execute("SELECT code FROM positions").fetchall()]
            for old_code in existing:
                if old_code not in new_codes:
                    conn.execute("DELETE FROM positions WHERE code = ?", (old_code,))

            # 2. INSERT OR REPLACE 传入列表
            for p in positions:
                conn.execute("""
                    INSERT OR REPLACE INTO positions (
                        code, name, entry_date, entry_price, quantity,
                        current_price, pnl_pct, hold_days, status, score,
                        is_real, legacy_holding, is_reference, updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, datetime('now'))
                """, (
                    p.code, p.name, p.entry_date, p.entry_price, p.quantity,
                    p.current_price, p.pnl_pct, p.hold_days, p.status, p.score,
                    p.is_real, p.legacy_holding,
                    getattr(p, 'is_reference', 0),  # US-014 R2
                ))
            conn.commit()
        finally:
            conn.close()
    
    # ── US-005: 实时数据获取 ────────────────────────────────────
    
    def _fetch_realtime_data(self, code: str) -> Dict:
        """
        获取ETF实时数据（价格、涨跌幅、RSI）
        
        优先使用热数据管理器(DataFacade)，降级使用腾讯API直调。
        
        Returns:
            {'price': float, 'change_pct': float, 'rsi_14': float,
             'price_deviation': float, 'data_source': str}
        """
        # 策略1: 使用 DataFacade 热数据层
        try:
            from src.data.manager import DataFacade
            facade = DataFacade(self.data_dir)
            merged = facade.get_merged_data(code)
            
            if merged.get('price') and merged['price'] > 0:
                change_pct = merged.get('change_pct', 0.0)
                return {
                    'price': merged['price'],
                    'change_pct': change_pct,
                    'rsi_14': merged.get('rsi_14', 50.0),
                    'price_deviation': 0.0,   # 热数据无信号价，无法计算偏差
                    'data_source': 'hot_data',
                }
        except Exception:
            pass
        
        # 策略2: 直接调用腾讯API（轻量，不依赖 DataFacade）
        return self._fetch_tencent_realtime(code)
    
    def _fetch_tencent_realtime(self, code: str) -> Dict:
        """腾讯API直接获取实时数据（RSI由指标模块计算）"""
        # ETF代码前缀处理
        # 上海ETF: 5开头（510xxx, 588xxx）
        # 深圳ETF: 1开头（159xxx）
        if code.startswith(('sh', 'sz')):
            prefix = code
        elif code.isdigit():
            if code.startswith('5') or code.startswith('11'):
                prefix = f'sh{code}'
            else:
                prefix = f'sz{code}'
        else:
            prefix = code
        
        url = f"{TENCENT_QT_URL}{prefix}"
        try:
            resp = requests.get(url, timeout=HTTP_TIMEOUT_SHORT)
            resp.encoding = 'gbk'
            parts = resp.text.split('~')
            
            if len(parts) > 32:
                price = float(parts[3])
                yclose = float(parts[4])
                change_pct = float(parts[32]) if parts[32] else 0.0
                
                # 计算RSI(14) from cold data
                rsi_14 = self._calc_rsi_14(code)
                
                return {
                    'price': price,
                    'change_pct': change_pct,
                    'rsi_14': rsi_14,
                    'price_deviation': 0.0,
                    'data_source': 'tencent',
                }
        except Exception:
            pass
        
        # 降级: 返回空数据
        return {
            'price': 0.0,
            'change_pct': 0.0,
            'rsi_14': 50.0,
            'price_deviation': 0.0,
            'data_source': 'none',
        }
    
    def _calc_rsi_14(self, code: str) -> float:
        """计算RSI(14) from cold CSV data"""
        try:
            from src.data.manager import ColdDataManager
            cold = ColdDataManager(self.data_dir)
            records = cold.get(code)
            
            if not records or len(records) < 15:
                return 50.0
            
            # 取最近14个收盘价计算RSI
            closes = [float(r['close']) for r in records[-15:]]
            
            gains, losses = [], []
            for i in range(1, len(closes)):
                delta = closes[i] - closes[i-1]
                gains.append(max(delta, 0))
                losses.append(max(-delta, 0))
            
            avg_gain = sum(gains[-14:]) / 14 if gains else 0
            avg_loss = sum(losses[-14:]) / 14 if losses else 0
            
            if avg_loss == 0:
                return 100.0
            rs = avg_gain / avg_loss
            return round(100 - 100 / (1 + rs), 2)
        except Exception:
            return 50.0
    
    # ─────────────────────────────────────────────────────────────
    
    def record_buy(self, code: str, name: str, price: float,
                   quantity: int, reason: str = "",
                   signal_price: float = 0.0,
                   signal_time: str = "",
                   signal_rsi: float = 0.0,
                   signal_adx: float = 0.0,
                   signal_score: int = 0,
                   trade_time: str = "",
                   emotion: str = "",
                   session: str = "",
                   is_real: int = 0,                 # 🆕 US-008: 0=模拟, 1=实盘
                   model: str = "",                  # 🆕 Q-009 决策上下文
                   strategy: str = "",               # 🆕 Q-009
                   evaluation: str = "",             # 🆕 Q-009
                   snapshot_ref: str = "") -> TradeRecord:
        """
        记录买入（SOP-06 v2.0 + US-008 区分实盘/模拟 + Q-009 决策上下文）

        Args:
            code:           ETF代码
            name:           ETF名称
            price:          成交价格
            quantity:       数量
            reason:         交易原因
            signal_price:   信号发出时的价格
            signal_time:    信号发出时间 (YYYY-MM-DD HH:MM)
            signal_rsi:     信号时的RSI(14)
            signal_adx:     信号时的ADX(14)
            signal_score:   信号评分
            trade_time:     实际成交时间 (YYYY-MM-DD HH:MM)
            emotion:        交易情绪 (calm/euphoria/fear/fomo/regret)
            session:        交易时段 (A/B/C/D/E/F)
        """
        # ── 自动获取实时快照（买入时） ──
        rt = self._fetch_realtime_data(code)
        realtime_price = rt.get('price', price)
        day_change_pct = rt.get('change_pct', 0.0)
        rsi_14 = rt.get('rsi_14', 50.0)
        
        # 偏差率: (实时价 - 信号价) / 信号价 * 100
        if signal_price > 0 and realtime_price > 0:
            price_deviation = (realtime_price - signal_price) / signal_price * 100
        else:
            price_deviation = 0.0
        
        amount = price * quantity
        
        # 交易时间处理
        if trade_time:
            trade_date = trade_time.split(' ')[0] if ' ' in trade_time else trade_time
        else:
            trade_date = datetime.now().strftime('%Y-%m-%d')
        
        # 情绪校验
        validated_emotion = _validate_emotion(emotion)
        
        # 时段推断（未指定时自动推断）
        if not session and trade_time:
            session = _infer_session(trade_time)
        
        trade = TradeRecord(
            date=trade_date,
            code=code,
            name=name,
            action='buy',
            price=price,
            quantity=quantity,
            amount=amount,
            reason=reason,
            # US-005 增强字段（买入时快照）
            realtime_price=realtime_price,
            price_deviation=price_deviation,
            rsi_14=rsi_14,
            day_change_pct=day_change_pct,
            score=signal_score,
            # SOP-06 信号快照
            signal_time=signal_time,
            signal_price=signal_price,
            signal_rsi=signal_rsi,
            signal_adx=signal_adx,
            signal_score=signal_score,
            # SOP-06 v2.0 增强字段
            trade_time=trade_time,
            emotion=validated_emotion,
            session=session,
            # US-008 区分实盘/模拟
            is_real=is_real,
            # Q-009 决策上下文
            model=model,
            strategy=strategy,
            evaluation=evaluation,
            snapshot_ref=snapshot_ref,
        )

        self.save_trade(trade)

        # 更新持仓
        positions = self.load_positions()
        # US-005: 事务保护 - 检查是否可买入
        ok, reason = self.can_buy(code)
        if not ok:
            _logger = logging.getLogger(__name__)
            _logger.warning(f"record_buy 拒绝: {code} - {reason}")
            return None
        new_pos = Position(
            code=code,
            name=name,
            entry_date=trade.date,
            entry_price=price,
            quantity=quantity,
            current_price=price,
            pnl_pct=0,
            hold_days=0,
            status='HOLDING',  # US-005: 直接到 HOLDING 状态
            score=signal_score,  # US-005: 记录评分
            is_real=is_real,  # US-008
        )
        positions.append(new_pos)
        self.save_positions(positions)
        # US-014 R1: 同步更新 current_capital（买 = 钱出去）
        self._update_performance_capital(-amount)
        self._audit(code, 'EMPTY', 'HOLDING', f"买入 {quantity}股 @ {price}")
        return trade

    def record_sell(self, code: str, price: float, actual_pnl: float = 0,
                     signal_price: float = 0.0, score: int = 0,
                     quantity: int = None,                # 🆕 US-008: 部分卖出（None=全仓）
                     is_real: int = 0,                    # 🆕 US-008
                     emotion: str = "",                   # 🆕 SOP-06
                     session: str = "",                   # 🆕 SOP-06
                     model: str = "",                     # 🆕 Q-009
                     strategy: str = "",                  # 🆕 Q-009
                     evaluation: str = "",                # 🆕 Q-009
                     snapshot_ref: str = "") -> Optional[TradeRecord]:
        """
        记录卖出（US-005: 填充实时快照字段，sell端留0 + US-008: 部分卖 + Q-009: 决策上下文）

        Args:
            code:           ETF代码
            price:          成交价格
            actual_pnl:     实际盈亏
            signal_price:   信号价（sell时未使用，留0）
            score:          评分（sell时未使用，留0）
            quantity:       卖出数量（None = 全部卖出，US-008 支持部分卖）
            is_real:        1=实盘, 0=模拟
            emotion/session/model/strategy/evaluation/snapshot_ref: Q-009/SOP-06 字段
        """
        positions = self.load_positions()
        pos = next((p for p in positions if p.code == code), None)

        if pos:
            # US-008: 部分卖出支持（quantity=None 表示全仓）
            sell_qty = quantity if quantity is not None else pos.quantity
            actual_pnl_partial = actual_pnl if quantity is None else (
                (price - pos.entry_price) * sell_qty
            )

            trade = TradeRecord(
                date=datetime.now().strftime('%Y-%m-%d'),
                code=code,
                name=pos.name,
                action='sell',
                price=price,
                quantity=sell_qty,
                amount=price * sell_qty,
                reason='卖出',
                actual_pnl=actual_pnl_partial,
                # US-005: sell时无法提供有效实时快照，填0
                realtime_price=price,
                price_deviation=0.0,
                rsi_14=0.0,
                day_change_pct=0.0,
                score=0,
                # SOP-06 字段
                emotion=emotion,
                session=session,
                # US-008 字段
                is_real=is_real,
                # Q-009 字段
                model=model,
                strategy=strategy,
                evaluation=evaluation,
                snapshot_ref=snapshot_ref,
            )
            self.save_trade(trade)
            
            # US-005: 事务保护 - 检查是否可卖出
            ok, reason, pos_checked = self.can_sell(code)
            if not ok:
                _logger = logging.getLogger(__name__)
                _logger.warning(f"record_sell 拒绝: {code} - {reason}")
                return None

            # 状态转换：HOLDING → CLOSING → EMPTY
            self.transition_position(code, 'CLOSING', f"准备卖出 @ {price}")
            # US-008: 部分卖：扣减持仓数量而非移除
            if quantity is not None and quantity < pos.quantity:
                # 部分卖：更新数量
                conn = self._get_conn()
                try:
                    conn.execute("""
                        UPDATE positions
                        SET quantity = quantity - ?, updated_at = datetime('now')
                        WHERE code = ?
                    """, (sell_qty, code))
                    conn.commit()
                finally:
                    conn.close()
                # US-014 R1: 部分卖：current_capital 加回部分金额
                self._update_performance_capital(+(price * sell_qty))
                self._audit(code, 'HOLDING', 'HOLDING', f"部分卖出 {sell_qty}股 @ {price}，剩余 {pos.quantity - sell_qty}")
            else:
                # 全仓卖：移除持仓
                positions = [p for p in positions if p.code != code]
                self.save_positions(positions)
                # US-014 R1: 全仓卖：current_capital 加回全部金额
                self._update_performance_capital(+(price * pos.quantity))
                self._audit(code, 'CLOSING', 'EMPTY', f"已卖出 @ {price}, pnl={actual_pnl_partial}")

            return trade
        return None
    
    # ── US-005: 查询接口 ─────────────────────────────────────────
    
    def query_trades(self,
                     date: Optional[str] = None,
                     code: Optional[str] = None,
                     action: Optional[str] = None) -> List[TradeRecord]:
        """
        查询交易记录
        
        Args:
            date:   交易日期，格式 YYYY-MM-DD（支持模糊，如 "2026-05"）
            code:   ETF代码（支持模糊匹配）
            action: 行为类型 'buy' / 'sell'
            
        Returns:
            符合条件的 TradeRecord 列表
        """
        trades = self.load_trades()
        results = trades
        
        if date:
            # 支持完整日期或年月
            if len(date) == 10:
                results = [t for t in results if t.date == date]
            elif len(date) == 7:
                results = [t for t in results if t.date.startswith(date)]
            elif len(date) == 4:
                results = [t for t in results if t.date.startswith(date)]
        
        if code:
            code_upper = code.upper()
            results = [t for t in results if code_upper in t.code.upper()]
        
        if action:
            results = [t for t in results if t.action == action]
        
        return results
    
    def export_csv(self, filepath: str) -> int:
        """
        导出交易记录为CSV
        
        Args:
            filepath:  输出文件路径
            
        Returns:
            导出的记录数
        """
        trades = self.load_trades()
        
        # 定义CSV字段（含US-005新字段）
        fieldnames = [
            'date', 'code', 'name', 'action',
            'price', 'quantity', 'amount', 'reason',
            'expected_return', 'actual_pnl', 'note',
            # US-005 增强字段
            'realtime_price', 'price_deviation',
            'rsi_14', 'day_change_pct', 'score',
        ]
        
        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for t in trades:
                writer.writerow(asdict(t))
        
        return len(trades)
    
    # ─────────────────────────────────────────────────────────────
    
    def update_position_price(self, code: str, current_price: float):
        """更新持仓价格"""
        positions = self.load_positions()
        
        for p in positions:
            if p.code == code:
                p.current_price = current_price
                p.pnl_pct = (current_price - p.entry_price) / p.entry_price * 100
                p.hold_days = (datetime.now() - datetime.strptime(p.entry_date, '%Y-%m-%d')).days
        
        self.save_positions(positions)
        return positions
    
    def get_holdings(self) -> List[Position]:
        """获取当前持仓（US-015: 强制从 trade_history 重建, 不读 positions 缓存）

        US-015 修复: 之前优先读 positions 缓存, 导致 159611 清仓后仍残留
        现在: 每次都从 trade_history (事实源) 重建, 保证一致性
        """
        # US-015: 强制从 trade_history 重建, 不读 positions 缓存
        positions = self._rebuild_positions_from_trades()
        
        # 更新当前价格和盈亏
        from datetime import datetime
        today = datetime.now().date()
        
        updated = []
        for pos in positions:
            # 获取实时价格
            rt = self._fetch_realtime_data(pos.code)
            current_price = rt.get('price', pos.entry_price)
            
            # 计算持仓天数和盈亏
            entry_date = datetime.strptime(pos.entry_date, '%Y-%m-%d').date()
            hold_days = (today - entry_date).days
            
            if pos.entry_price > 0:
                pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100
            else:
                pnl_pct = 0
            
            pos.current_price = current_price
            pos.pnl_pct = pnl_pct
            pos.hold_days = hold_days
            updated.append(pos)
        
        return updated
    
    def _rebuild_positions_from_trades(self) -> List[Position]:
        """从交易记录重建持仓状态（US-014 R2: 支持 reference 池）"""
        positions = []
        trades = self.load_trades()

        # US-014 R2: 加载 reference 池代码集合（用于标 is_reference=1）
        reference_pool = set()
        try:
            from src.data.etf_pool_repository import ETFRepository
            reference_pool = set(ETFRepository().list_codes("reference"))
        except Exception:
            pass

        # US-015: 加载 positions 表的 legacy_holding 标记 (用户手动标)
        legacy_holdings = {}
        try:
            import sqlite3
            conn = sqlite3.connect(self.db_path)
            for row in conn.execute("SELECT code, legacy_holding FROM positions WHERE legacy_holding=1").fetchall():
                legacy_holdings[row[0]] = row[1]
            conn.close()
        except Exception:
            pass

        # US-015: 修 buy_records 覆盖式 bug → 改用 list 累加
        buy_records = {}  # code -> list of {date, name, price, quantity}
        sell_records = {}  # code -> [(date, quantity), ...]

        for trade in trades:
            if trade.action == 'buy':
                if trade.code not in buy_records:
                    buy_records[trade.code] = {
                        'name': trade.name,
                        'buys': [],  # 累加多笔 buy
                    }
                buy_records[trade.code]['buys'].append({
                    'date': trade.date,
                    'price': trade.price,
                    'quantity': trade.quantity,
                })
            elif trade.action == 'sell':
                if trade.code not in sell_records:
                    sell_records[trade.code] = []
                sell_records[trade.code].append({
                    'date': trade.date,
                    'quantity': trade.quantity,
                })

        # 计算当前持仓 (US-015: 多笔 buy 加权平均, 不覆盖)
        for code, info in buy_records.items():
            buys = info['buys']
            total_bought = sum(b['quantity'] for b in buys)
            total_sold = sum(s['quantity'] for s in sell_records.get(code, []))
            remaining = total_bought - total_sold

            if remaining > 0:
                # 加权平均入场价 (按 quantity 加权)
                total_cost = sum(b['price'] * b['quantity'] for b in buys)
                avg_price = total_cost / total_bought if total_bought > 0 else 0
                # 最早入场日 (hold_days 计算用)
                earliest_date = min(b['date'] for b in buys)
                is_reference = 1 if code in reference_pool else 0
                is_legacy = legacy_holdings.get(code, 0)  # US-015: 从原 positions 读
                positions.append(Position(
                    code=code,
                    name=info['name'],
                    entry_date=earliest_date,
                    entry_price=round(avg_price, 4),
                    quantity=remaining,
                    current_price=avg_price,
                    pnl_pct=0,
                    hold_days=0,
                    is_reference=is_reference,  # US-014 R2
                    legacy_holding=is_legacy,   # US-015
                ))

        return positions
    
    # ===== US-005: 状态机 + 事务保护 + 审计日志 =====

    def _audit(self, code: str, from_state: str, to_state: str, reason: str = ""):
        """写审计日志（US-008: 走 audit_log 表）"""
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT INTO audit_log (action, code, from_state, to_state, detail, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                'state_change', code, from_state, to_state,
                json.dumps({'reason': reason}, ensure_ascii=False),
                datetime.now().isoformat(),
            ))
            conn.commit()
        except Exception as e:
            _logger = logging.getLogger(__name__)
            _logger.error(f"audit log 写入失败: {e}")
        finally:
            conn.close()

    def _validate_transition(self, from_state: str, to_state: str) -> bool:
        """验证状态转换是否合法"""
        valid = VALID_TRANSITIONS.get(from_state, set())
        return to_state in valid

    def can_buy(self, code: str, max_holdings: int = 2) -> tuple:  # US-008: 默认 2（沿用 v8 POSITION_MANAGEMENT.md + 用户 B 决策）
        """检查是否能买入（事务前置检查）

        Returns:
            (ok, reason) - ok=True 可买入, ok=False 不可买入及原因
        """
        positions = self.load_positions()

        # 1. 检查持仓数量上限
        active = [p for p in positions if p.status in ('PENDING', 'HOLDING', 'REBALANCING', 'CLOSING')]
        if len(active) >= max_holdings:
            return False, f"持仓数量已达上限 {max_holdings}（当前 {len(active)}）"

        # 2. 检查重复代码
        for p in positions:
            if p.code == code and p.status in ('HOLDING', 'PENDING', 'REBALANCING'):
                return False, f"已持仓 {code}（status={p.status}），不能重复买入"

        return True, ""

    def can_sell(self, code: str, quantity: int = None) -> tuple:
        """检查是否能卖出

        Args:
            code: ETF 代码
            quantity: 要卖出的数量（None = 全部）

        Returns:
            (ok, reason, position) - position 是当前持仓
        """
        positions = self.load_positions()
        pos = next((p for p in positions if p.code == code), None)

        if pos is None:
            return False, f"未持有 {code}", None

        if pos.status not in ('HOLDING', 'REBALANCING', 'CLOSING'):
            return False, f"持仓 {code} 状态 {pos.status} 不能卖出", pos

        if quantity is not None and quantity > pos.quantity:
            return False, f"卖出数量 {quantity} 超过持仓 {pos.quantity}", pos

        return True, "", pos

    def check_portfolio(self, candidates: List[dict] = None,
                         stop_loss: float = -0.06,
                         stop_profit: float = 0.10,
                         max_hold_days: int = 15,
                         rebalance_threshold: int = 2) -> List[dict]:
        """批量检查所有持仓

        Args:
            candidates: 候选 ETF 列表 [{code, name, score, price}, ...]
            stop_loss: 止损比例 (默认 -6%)
            stop_profit: 止盈比例 (默认 +10%)
            max_hold_days: 最大持仓天数
            rebalance_threshold: 换仓阈值（候选分 - 持仓分）

        Returns:
            操作建议列表 [{code, action, reason}, ...]
        """
        positions = self.load_positions()
        actions = []

        for pos in positions:
            if pos.status != 'HOLDING':
                continue

            # 1. 止损
            if pos.pnl_pct <= stop_loss * 100:
                actions.append({
                    'code': pos.code,
                    'action': 'sell',
                    'reason': f"止损 {pos.pnl_pct:.2f}% <= {stop_loss * 100}%",
                    'priority': 'high',
                })
                continue

            # 2. 止盈
            if pos.pnl_pct >= stop_profit * 100:
                actions.append({
                    'code': pos.code,
                    'action': 'sell',
                    'reason': f"止盈 {pos.pnl_pct:.2f}% >= {stop_profit * 100}%",
                    'priority': 'medium',
                })
                continue

            # 3. 到期
            if pos.hold_days >= max_hold_days:
                actions.append({
                    'code': pos.code,
                    'action': 'sell',
                    'reason': f"持仓 {pos.hold_days} 天 >= 上限 {max_hold_days}",
                    'priority': 'medium',
                })
                continue

            # 4. 换仓（候选评分 > 当前评分 + threshold）
            if candidates:
                for cand in candidates:
                    if cand.get('code') == pos.code:
                        continue  # 候选 = 当前，不换
                    cand_score = cand.get('score', 0)
                    if cand_score > pos.score + rebalance_threshold:
                        actions.append({
                            'code': pos.code,
                            'action': 'rebalance',
                            'reason': f"换仓: 候选 {cand.get('code')} 评分 {cand_score} > 当前 {pos.score} + {rebalance_threshold}",
                            'priority': 'low',
                        })
                        break

        return actions

    def transition_position(self, code: str, to_state: str, reason: str = "") -> bool:
        """原子操作：修改持仓状态（带审计日志）

        Returns:
            True 成功, False 失败（非法转换或持仓不存在）
        """
        positions = self.load_positions()
        for p in positions:
            if p.code == code:
                from_state = p.status
                if not self._validate_transition(from_state, to_state):
                    return False
                p.status = to_state
                self.save_positions(positions)
                self._audit(code, from_state, to_state, reason)
                return True
        return False

    def check_stop_loss(self, code: str, threshold: float = -5) -> bool:
        """检查是否触发止损"""
        positions = self.load_positions()
        pos = next((p for p in positions if p.code == code), None)
        
        if pos and pos.pnl_pct <= threshold:
            return True
        return False
    
    def check_take_profit(self, code: str, threshold: float = 8) -> bool:
        """检查是否触发止盈"""
        positions = self.load_positions()
        pos = next((p for p in positions if p.code == code), None)
        
        if pos and pos.pnl_pct >= threshold:
            return True
        return False
    
    def need_rebalance(self, max_hold_days: int = 10) -> bool:
        """检查是否需要调仓"""
        positions = self.load_positions()
        
        for p in positions:
            if p.hold_days >= max_hold_days:
                return True
        return False
    
    def get_performance_summary(self) -> Dict:
        """获取绩效汇总"""
        if os.path.exists(self.performance_file):
            with open(self.performance_file, 'r') as f:
                data = json.load(f)
                return data.get('performance', {})
        return {
            'initial_capital': 20000,
            'current_capital': 20000,
            'total_pnl': 0,
            'total_trades': 0,
            'win_rate': 0,
        }
    
    def update_performance(self, capital: float, pnl: float,
                           total_trades: int, win_rate: float):
        """更新绩效"""
        with open(self.performance_file, 'r') as f:
            data = json.load(f)

        data['performance'].update({
            'current_capital': capital,
            'total_pnl': pnl,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

        with open(self.performance_file, 'w') as f:
            json.dump(data, f, indent=2)

    def _update_performance_capital(self, delta: float):
        """
        US-014 R1: 增量更新 current_capital
        每次 record_buy/record_sell 调用，atomic 调整现金余额

        Args:
            delta: +amount 表示回款（卖），-amount 表示支出（买）
        """
        if not os.path.exists(self.performance_file):
            return
        try:
            with open(self.performance_file, 'r') as f:
                data = json.load(f)
            perf = data.get('performance', {})
            old = float(perf.get('current_capital', 20000))
            new = max(0, old + delta)
            perf['current_capital'] = new
            perf['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            data['performance'] = perf
            # SOUL 规则 18: json.dump + 立即验证
            with open(self.performance_file, 'w') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # 立即验证
            with open(self.performance_file, 'r') as f:
                json.load(f)  # 失败立即抛错
        except Exception as e:
            _logger = logging.getLogger(__name__)
            _logger.warning(f"_update_performance_capital 失败: {e}")

    def get_account_summary(self, max_holdings: int = 2) -> dict:
        """
        账户总览（US-009）

        Returns:
            {
                'cash': float,            # 现金余额（来自 performance_file）
                'positions_value': float, # 持仓市值（实时价×数量）
                'total_asset': float,     # 总资产 = cash + positions_value
                'holdings': [...],        # Position 列表（dict 形式）
                'hold_count': int,        # 持仓数量
                'max_holdings': int,      # 最大持仓数
            }

        Notes:
            - cash 来自 etf_performance.json 的 current_capital（用户/系统认为的可用现金）
            - positions_value 按当前价估算（实时价 × 数量）
            - total_asset = cash + positions_value（资产 = 现金 + 持仓市值）
            - 调用方应用 max(0, total_asset*0.9 - positions_value) 算"可投入"
        """
        holdings = self.get_holdings()

        # 现金：来自 performance_file（可能为 0/默认 20000）
        perf = self.get_performance_summary()
        cash = float(perf.get('current_capital', 20000))

        # 持仓市值
        positions_value = 0.0
        holdings_dicts = []
        for pos in holdings:
            if pos.current_price > 0 and pos.quantity > 0:
                positions_value += pos.current_price * pos.quantity
            holdings_dicts.append({
                'code': pos.code,
                'name': pos.name,
                'quantity': pos.quantity,
                'entry_price': pos.entry_price,
                'current_price': pos.current_price,
                'pnl_pct': pos.pnl_pct,
                'hold_days': pos.hold_days,
                'status': pos.status,
                'is_real': getattr(pos, 'is_real', 0),
                'legacy_holding': getattr(pos, 'legacy_holding', 0),
            })

        return {
            'cash': round(cash, 2),
            'positions_value': round(positions_value, 2),
            'total_asset': round(cash + positions_value, 2),
            'holdings': holdings_dicts,
            'hold_count': len(holdings),
            'max_holdings': max_holdings,
        }
