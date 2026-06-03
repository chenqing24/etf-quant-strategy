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
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import requests
import logging

from src.constants import TRADES_FILE, TENCENT_QT_URL, HTTP_TIMEOUT_SHORT


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


class TradeTracker:
    """交易追踪器"""
    
    def __init__(self, data_dir: str = '.'):
        self.data_dir = data_dir
        from src.constants import TRADES_FILE, TENCENT_QT_URL
        self.trades_file = os.path.join(data_dir, TRADES_FILE)
        self.positions_file = os.path.join(data_dir, 'etf_positions.json')
        self.performance_file = os.path.join(data_dir, 'etf_performance.json')
        
        # US-005: 审计日志
        self.audit_log_file = os.path.join(data_dir, 'etf_audit_log.json')
        self._ensure_files()
    
    def _ensure_files(self):
        """初始化文件"""
        for f in [self.trades_file, self.positions_file, self.performance_file, self.audit_log_file]:
            if not os.path.exists(f):
                with open(f, 'w') as fp:
                    json.dump({
                        'trades': [],
                        'positions': [],
                        'performance': {
                            'initial_capital': 20000,
                            'current_capital': 20000,
                            'total_pnl': 0,
                            'total_trades': 0,
                            'win_rate': 0,
                        }
                    }, fp, indent=2)
    
    def load_trades(self) -> List[TradeRecord]:
        """加载交易记录"""
        with open(self.trades_file, 'r') as f:
            data = json.load(f)
            return [TradeRecord(**t) for t in data.get('trades', [])]
    
    def save_trade(self, trade: TradeRecord):
        """保存交易记录"""
        with open(self.trades_file, 'r') as f:
            data = json.load(f)
        
        data['trades'].append(asdict(trade))
        
        with open(self.trades_file, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def load_positions(self) -> List[Position]:
        """加载当前持仓"""
        with open(self.positions_file, 'r') as f:
            data = json.load(f)
            return [Position(**p) for p in data.get('positions', [])]
    
    def save_positions(self, positions: List[Position]):
        """保存持仓"""
        with open(self.positions_file, 'w') as f:
            json.dump({
                'positions': [asdict(p) for p in positions],
            }, f, indent=2, ensure_ascii=False)
    
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
                   session: str = "") -> TradeRecord:
        """
        记录买入（SOP-06 v2.0: 信号快照 + 情绪 + 时段）
        
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
        )
        positions.append(new_pos)
        self.save_positions(positions)
        self._audit(code, 'EMPTY', 'HOLDING', f"买入 {quantity}股 @ {price}")
        return trade
    
    def record_sell(self, code: str, price: float, actual_pnl: float = 0,
                     signal_price: float = 0.0, score: int = 0) -> Optional[TradeRecord]:
        """
        记录卖出（US-005: 填充实时快照字段，sell端留0）
        
        Args:
            code:           ETF代码
            price:          成交价格
            actual_pnl:     实际盈亏
            signal_price:   信号价（sell时未使用，留0）
            score:          评分（sell时未使用，留0）
        """
        positions = self.load_positions()
        pos = next((p for p in positions if p.code == code), None)
        
        if pos:
            trade = TradeRecord(
                date=datetime.now().strftime('%Y-%m-%d'),
                code=code,
                name=pos.name,
                action='sell',
                price=price,
                quantity=pos.quantity,
                amount=price * pos.quantity,
                reason='卖出',
                actual_pnl=actual_pnl,
                # US-005: sell时无法提供有效实时快照，填0
                realtime_price=price,
                price_deviation=0.0,
                rsi_14=0.0,
                day_change_pct=0.0,
                score=0,
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
            # 移除持仓
            positions = [p for p in positions if p.code != code]
            self.save_positions(positions)
            self._audit(code, 'CLOSING', 'EMPTY', f"已卖出 @ {price}, pnl={actual_pnl}")

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
        """获取当前持仓（从positions文件 + 交易记录重建）"""
        # 优先从positions文件读取
        positions = self.load_positions()
        
        # 如果positions为空，从交易记录重建
        if not positions:
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
        """从交易记录重建持仓状态"""
        positions = []
        trades = self.load_trades()
        
        # 按代码分组，获取每只ETF的买入记录
        buy_records = {}  # code -> (date, name, price, quantity)
        sell_records = {}  # code -> [(date, quantity), ...]
        
        for trade in trades:
            if trade.action == 'buy':
                buy_records[trade.code] = {
                    'date': trade.date,
                    'name': trade.name,
                    'price': trade.price,
                    'quantity': trade.quantity,
                }
            elif trade.action == 'sell':
                if trade.code not in sell_records:
                    sell_records[trade.code] = []
                sell_records[trade.code].append({
                    'date': trade.date,
                    'quantity': trade.quantity,
                })
        
        # 计算当前持仓
        for code, buy_info in buy_records.items():
            total_bought = buy_info['quantity']
            total_sold = sum(s['quantity'] for s in sell_records.get(code, []))
            remaining = total_bought - total_sold
            
            if remaining > 0:
                positions.append(Position(
                    code=code,
                    name=buy_info['name'],
                    entry_date=buy_info['date'],
                    entry_price=buy_info['price'],
                    quantity=remaining,
                    current_price=buy_info['price'],
                    pnl_pct=0,
                    hold_days=0,
                ))
        
        return positions
    
    # ===== US-005: 状态机 + 事务保护 + 审计日志 =====

    def _audit(self, code: str, from_state: str, to_state: str, reason: str = ""):
        """写审计日志"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'code': code,
            'from_state': from_state,
            'to_state': to_state,
            'reason': reason,
        }
        try:
            with open(self.audit_log_file, 'a') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as e:
            _logger = logging.getLogger(__name__)
            _logger.error(f"audit log 写入失败: {e}")

    def _validate_transition(self, from_state: str, to_state: str) -> bool:
        """验证状态转换是否合法"""
        valid = VALID_TRANSITIONS.get(from_state, set())
        return to_state in valid

    def can_buy(self, code: str, max_holdings: int = 1) -> tuple:
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
