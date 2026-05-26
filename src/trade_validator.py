#!/usr/bin/env python3
"""
ETF交易校验器 - 买入前实时校验 + 行为追踪
支持多数据源降级：腾讯API > 东方财富API > 新浪API
"""
import json
import time
import requests
import pandas as pd
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from enum import Enum


class DataSource(Enum):
    """数据源枚举"""
    TENCENT = "tencent"
    EMF = "emf"  # East Money Fortune (东方财富)
    SINA = "sina"


class ActionType(Enum):
    """用户行为类型"""
    ASK_BUY = "ask_buy"           # 询问是否买入
    ASK_HOLD = "ask_hold"         # 询问是否持有
    ASK_SELL = "ask_sell"         # 询问是否卖出
    CONFIRM_BUY = "confirm_buy"   # 确认买入
    CONFIRM_SELL = "confirm_sell" # 确认卖出
    IGNORE = "ignore"             # 忽略建议
    CUSTOM = "custom"             # 自定义行为


class Recommendation(Enum):
    """校验建议"""
    STRONG_BUY = "STRONG_BUY"     # 强烈建议买入
    BUY = "BUY"                   # 建议买入
    HOLD = "HOLD"                 # 建议观望
    CAUTION = "CAUTION"           # 谨慎买入
    SKIP = "SKIP"                 # 建议跳过


@dataclass
class ValidationResult:
    """信号校验结果"""
    code: str
    signal_price: float           # 信号发出时的价格
    current_price: float          # 当前价格
    price_deviation: float        # 价格偏差率 (%) = (current - signal) / signal * 100
    
    # RSI温度
    rsi_5: float = 0.0            # 5日RSI
    rsi_14: float = 0.0           # 14日RSI
    rsi_temperature: str = "NORMAL"  # RSI温度: OVERHEATED/NEUTRAL/COOL/OVERSOLD
    
    # 止盈止损空间
    target_price: float = 0.0     # 目标止盈价
    stop_price: float = 0.0       # 止损价
    target_gap: float = 0.0       # 距止盈空间 (%) 正数=还有空间
    stop_gap: float = 0.0         # 距止损空间 (%) 负数=已亏损
    
    # 持仓状态 (如果有)
    holding: bool = False
    cost: float = 0.0
    current_pnl: float = 0.0
    
    # 校验项
    deviation_passed: bool = True   # 价格偏差校验是否通过
    rsi_passed: bool = True        # RSI校验是否通过
    gap_passed: bool = True        # 空间校验是否通过
    
    # 综合建议
    recommendation: str = Recommendation.HOLD.value
    warning_messages: List[str] = field(default_factory=list)
    
    # 元数据
    timestamp: str = ""
    data_source: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class BehaviorRecord:
    """行为记录"""
    id: str
    timestamp: str
    date: str                      # 交易日期 YYYY-MM-DD
    code: str
    name: str                      # ETF名称
    action: str                    # 行为类型
    current_price: float
    signal_price: float            # 信号价格 (如果是重新入场)
    
    # 校验结果摘要
    price_deviation: float
    rsi: float
    target_gap: float
    stop_gap: float
    recommendation: str
    
    # 持仓信息
    holding: bool = False
    cost: float = 0.0
    pnl: float = 0.0
    
    # 上下文
    score: int = 0                 # 选股分数
    market_status: str = "UNKNOWN" # 市场状态
    notes: str = ""


class TradeValidator:
    """
    ETF交易校验器
    
    功能:
    1. 实时价格获取 (多数据源降级)
    2. 买入信号校验
    3. 用户行为追踪
    4. 收盘摘要生成
    """
    
    # 数据源配置
    TENCENT_BASE_URL = "https://qt.gtimg.cn/q="
    EMF_BASE_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    SINA_BASE_URL = "https://hq.sinajs.cn/list="
    
    # 校验阈值
    PRICE_DEVIATION_WARN = 1.0     # 价格偏差警告阈值 (%)
    PRICE_DEVIATION_REJECT = 3.0  # 价格偏差拒绝阈值 (%)
    RSI_OVERHEATED = 70           # RSI过热阈值
    RSI_OVERCOOL = 40             # RSI过冷阈值 (可买入)
    TARGET_GAP_MIN = 1.0          # 止盈空间最小要求 (%)
    STOP_GAP_WARN = -5.0          # 距止损警告阈值 (%)
    
    def __init__(self, data_dir: str = 'etf_data_live'):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.behavior_log_path = self.data_dir / 'behavior_log.json'
        self.positions_path = self.data_dir / 'etf_positions.json'
        self.realtime_cache_path = self.data_dir / 'realtime_cache.json'
        
        # 加载持仓数据
        self._positions: Dict[str, dict] = self._load_positions()
        
        # 行为记录
        self._behavior_records: List[BehaviorRecord] = self._load_behavior_log()
        
        # 市场状态 (收盘后更新)
        self._market_status = "UNKNOWN"
        
        # 初始化ID计数器
        self._record_counter = len(self._behavior_records)
    
    def _load_positions(self) -> Dict[str, dict]:
        """加载持仓数据"""
        if self.positions_path.exists():
            try:
                with open(self.positions_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'positions' in data:
                        return {p['code']: p for p in data['positions']}
            except Exception:
                pass
        return {}
    
    def _load_behavior_log(self) -> List[BehaviorRecord]:
        """加载行为日志"""
        if self.behavior_log_path.exists():
            try:
                with open(self.behavior_log_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return [BehaviorRecord(**r) for r in data.get('records', [])]
            except Exception:
                pass
        return []
    
    def _save_behavior_log(self):
        """保存行为日志"""
        records = [asdict(r) for r in self._behavior_records]
        with open(self.behavior_log_path, 'w', encoding='utf-8') as f:
            json.dump({'records': records, 'last_updated': datetime.now().isoformat()}, 
                     f, ensure_ascii=False, indent=2)
    
    # ==================== 数据获取 ====================
    
    def _fetch_tencent(self, codes: List[str]) -> Dict[str, Dict]:
        """腾讯API获取实时价格"""
        # 腾讯需要sh/sz前缀
        prefix_codes = []
        for code in codes:
            if code.startswith(('sh', 'sz')):
                prefix_codes.append(code)
            elif code.isdigit():
                prefix_codes.append(f'sh{code}' if code.startswith(('5', '1', '11')) else f'sz{code}')
            else:
                prefix_codes.append(code)
        
        url = f"{self.TENCENT_BASE_URL}{','.join(prefix_codes)}"
        
        try:
            resp = requests.get(url, timeout=10)
            resp.encoding = 'gbk'
            lines = resp.text.strip().split('\n')
            
            result = {}
            for line in lines:
                parts = line.split('~')
                if len(parts) > 32:
                    code_raw = parts[2]  # 如 'sh515050' 或 'sz159915'
                    name = parts[1]
                    price = float(parts[3])
                    yclose = float(parts[4])
                    today_pct = float(parts[32]) if parts[32] else 0.0
                    
                    # 去掉前缀
                    clean_code = code_raw[2:] if code_raw.startswith(('sh', 'sz')) else code_raw
                    
                    result[clean_code] = {
                        'name': name,
                        'price': price,
                        'yclose': yclose,
                        'pct': today_pct,
                        'code_raw': code_raw,
                        'data_source': DataSource.TENCENT.value
                    }
            
            return result
        except Exception as e:
            raise ConnectionError(f"腾讯API失败: {e}")
    
    def _fetch_emf(self, codes: List[str]) -> Dict[str, Dict]:
        """东方财富API获取实时价格"""
        # 东方财富需要带市场前缀的代码
        prefix_codes = []
        for code in codes:
            if code.startswith(('sh', 'sz')):
                prefix_codes.append(code.upper())
            elif code.isdigit():
                # ETF通常是1或5开头
                prefix_codes.append(f'SH{code}' if code.startswith(('5', '1', '11')) else f'SZ{code}')
            else:
                prefix_codes.append(code.upper())
        
        url = f"{self.EMF_BASE_URL}?fltyp=0&secids={','.join(prefix_codes)}&fields=f2,f3,f4,f12,f14,f15,f16"
        
        try:
            resp = requests.get(url, timeout=10)
            resp.encoding = 'utf-8'
            data = resp.json()
            
            result = {}
            data_content = data.get('data', {})
            
            # 处理不同的响应格式
            if data_content:
                # 东方财富返回格式可能是 data.diff 或直接在data中
                items = data_content.get('diff', []) or [data_content]
                
                for item in items:
                    if not item:
                        continue
                    code = item.get('f12', '')
                    # 去掉SH/SZ前缀
                    clean_code = code[2:] if code.startswith(('SH', 'SZ')) else code
                    
                    price = item.get('f2', 0)
                    pct = item.get('f3', 0)
                    yclose = item.get('f4', 0)
                    
                    # 价格单位处理
                    if price and price > 10000:  # 可能是分
                        price = price / 100
                    if pct and abs(pct) > 1000:  # 可能是万分比
                        pct = pct / 100
                    
                    result[clean_code] = {
                        'name': item.get('f14', ''),
                        'price': price,
                        'pct': pct,
                        'yclose': yclose,
                        'data_source': DataSource.EMF.value
                    }
                    # 如果没有昨收，反推
                    if not result[clean_code]['yclose'] and result[clean_code]['price'] and result[clean_code]['pct']:
                        result[clean_code]['yclose'] = result[clean_code]['price'] / (1 + result[clean_code]['pct'] / 100)
            
            return result
        except Exception as e:
            raise ConnectionError(f"东方财富API失败: {e}")
    
    def _fetch_sina(self, codes: List[str]) -> Dict[str, Dict]:
        """新浪API获取实时价格"""
        # 新浪需要sh/sz前缀
        prefix_codes = []
        for code in codes:
            if code.startswith(('sh', 'sz')):
                prefix_codes.append(code)
            elif code.isdigit():
                prefix_codes.append(f'sh{code}' if code.startswith(('5', '1', '11')) else f'sz{code}')
            else:
                prefix_codes.append(code)
        
        url = f"{self.SINA_BASE_URL}{','.join(prefix_codes)}"
        headers = {'Referer': 'https://finance.sina.com.cn'}
        
        try:
            resp = requests.get(url, timeout=10, headers=headers)
            resp.encoding = 'gbk'
            lines = resp.text.strip().split('\n')
            
            result = {}
            for i, line in enumerate(lines):
                # 解析格式: var hq_str_sh515050="..."
                parts = line.split('"')
                if len(parts) < 2:
                    continue
                
                data = parts[1].split(',')
                if len(data) < 32:
                    continue
                
                name = data[0]
                yclose = float(data[2])
                open_p = float(data[1])
                price = float(data[3])
                high = float(data[4])
                low = float(data[5])
                vol = float(data[8])
                
                code = codes[i] if i < len(codes) else ''
                
                result[code] = {
                    'name': name,
                    'price': price,
                    'yclose': yclose,
                    'pct': (price - yclose) / yclose * 100 if yclose else 0,
                    'data_source': DataSource.SINA.value
                }
            
            return result
        except Exception as e:
            raise ConnectionError(f"新浪API失败: {e}")
    
    def fetch_realtime_prices(self, codes: List[str]) -> Dict[str, Dict]:
        """
        获取实时价格 - 多数据源降级
        
        Args:
            codes: ETF代码列表
            
        Returns:
            Dict[code, {
                'name': str,
                'price': float,
                'yclose': float,
                'pct': float,
                'data_source': str
            }]
        """
        if not codes:
            return {}
        
        # 检查缓存 (5分钟内有效)
        cache = self._get_cached_prices()
        cache_time = cache.get('_cache_time', 0)
        now = datetime.now().timestamp()
        
        if now - cache_time < 300:  # 5分钟缓存
            cached = {k: v for k, v in cache.items() if k != '_cache_time'}
            # 检查是否所有代码都有缓存
            if all(c in cached for c in codes):
                return cached
        
        # 尝试腾讯API (优先)
        sources = [
            (self._fetch_tencent, DataSource.TENCENT),
            (self._fetch_emf, DataSource.EMF),
            (self._fetch_sina, DataSource.SINA),
        ]
        
        for fetcher, source in sources:
            try:
                result = fetcher(codes)
                if result and len(result) > 0:
                    # 添加缓存时间戳
                    result['_cache_time'] = now
                    self._save_cached_prices(result)
                    return result
            except ConnectionError:
                continue
            except Exception as e:
                print(f"警告: {source.value} API异常: {e}")
                continue
        
        # 全部失败，返回缓存 (即使过期)
        return {k: v for k, v in cache.items() if k != '_cache_time'}
    
    def _get_cached_prices(self) -> Dict:
        """获取缓存的价格"""
        if self.realtime_cache_path.exists():
            try:
                with open(self.realtime_cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def _save_cached_prices(self, prices: Dict):
        """保存价格缓存"""
        with open(self.realtime_cache_path, 'w', encoding='utf-8') as f:
            json.dump(prices, f, ensure_ascii=False, indent=2)
    
    # ==================== 信号校验 ====================
    
    def _get_rsi_from_cache_or_calc(self, code: str) -> tuple:
        """
        获取RSI值 (从缓存或实时计算)
        
        Returns:
            (rsi_5, rsi_14, temperature)
        """
        # 尝试从缓存读取历史数据
        try:
            from .indicator import Indicator
            
            # 简单实现: 使用最近5日的涨跌幅估算RSI
            # 完整实现需要历史K线数据
            # 这里返回默认值，实际使用时应该从指标计算获取
            
            # 返回中性RSI (实际应从历史数据计算)
            return 50.0, 50.0, "NEUTRAL"
        except ImportError:
            return 50.0, 50.0, "NEUTRAL"
    
    def validate_signal(self, code: str, signal_price: float, score: int = 0,
                       rsi_5: float = None, rsi_14: float = None,
                       target_price: float = None, stop_price: float = None) -> ValidationResult:
        """
        校验买入信号
        
        Args:
            code: ETF代码
            signal_price: 信号发出时的价格
            score: 选股分数
            rsi_5: 5日RSI (可选)
            rsi_14: 14日RSI (可选)
            target_price: 目标止盈价 (可选)
            stop_price: 止损价 (可选)
            
        Returns:
            ValidationResult: 校验结果
        """
        # 获取实时价格
        prices = self.fetch_realtime_prices([code])
        price_data = prices.get(code, {})
        
        current_price = price_data.get('price', signal_price)
        data_source = price_data.get('data_source', 'unknown')
        
        # 检查持仓状态
        holding = code in self._positions
        pos = self._positions.get(code, {})
        cost = pos.get('cost', 0)
        current_pnl = (current_price - cost) / cost if cost > 0 else 0
        
        # 计算价格偏差率
        price_deviation = (current_price - signal_price) / signal_price * 100 if signal_price > 0 else 0
        
        # RSI处理
        if rsi_5 is None or rsi_14 is None:
            rsi_5, rsi_14, rsi_temp = self._get_rsi_from_cache_or_calc(code)
        else:
            if rsi_14 >= self.RSI_OVERHEATED:
                rsi_temp = "OVERHEATED"
            elif rsi_14 <= self.RSI_OVERCOOL:
                rsi_temp = "COOL"
            else:
                rsi_temp = "NEUTRAL"
        
        # 止盈止损空间
        if target_price is None:
            # 默认止盈: 当前价 + 15%
            target_price = current_price * 1.15
        if stop_price is None:
            # 默认止损: 当前价 - 10%
            stop_price = current_price * 0.90
        
        target_gap = (target_price - current_price) / current_price * 100
        stop_gap = (stop_price - current_price) / current_price * 100
        
        # 校验逻辑
        warnings = []
        
        # 1. 价格偏差校验
        deviation_passed = abs(price_deviation) <= self.PRICE_DEVIATION_REJECT
        if abs(price_deviation) > self.PRICE_DEVIATION_WARN:
            warnings.append(f"价格已变动 {price_deviation:+.2f}%，{'高于' if price_deviation > 0 else '低于'}信号价")
        
        # 2. RSI校验
        rsi_passed = rsi_14 < self.RSI_OVERHEATED
        if rsi_14 >= self.RSI_OVERHEATED:
            warnings.append(f"RSI14={rsi_14:.1f} 过热，短期可能有回调风险")
        elif rsi_14 <= self.RSI_OVERCOOL:
            warnings.append(f"RSI14={rsi_14:.1f} 偏低，可能是买入机会")
        
        # 3. 止盈止损空间校验
        gap_passed = target_gap >= self.TARGET_GAP_MIN and stop_gap >= self.STOP_GAP_WARN
        if target_gap < self.TARGET_GAP_MIN:
            warnings.append(f"止盈空间仅 {target_gap:.1f}%，预期收益有限")
        if stop_gap < self.STOP_GAP_WARN:
            warnings.append(f"距止损仅 {stop_gap:.1f}%，风险较高")
        
        # 综合建议
        recommendation = self._generate_recommendation(
            price_deviation, rsi_14, target_gap, stop_gap,
            deviation_passed, rsi_passed, gap_passed, holding
        )
        
        return ValidationResult(
            code=code,
            signal_price=signal_price,
            current_price=current_price,
            price_deviation=price_deviation,
            rsi_5=rsi_5,
            rsi_14=rsi_14,
            rsi_temperature=rsi_temp,
            target_price=target_price,
            stop_price=stop_price,
            target_gap=target_gap,
            stop_gap=stop_gap,
            holding=holding,
            cost=cost,
            current_pnl=current_pnl,
            deviation_passed=deviation_passed,
            rsi_passed=rsi_passed,
            gap_passed=gap_passed,
            recommendation=recommendation,
            warning_messages=warnings,
            timestamp=datetime.now().isoformat(),
            data_source=data_source
        )
    
    def _generate_recommendation(self, price_dev: float, rsi: float,
                                  target_gap: float, stop_gap: float,
                                  dev_passed: bool, rsi_passed: bool,
                                  gap_passed: bool, holding: bool) -> str:
        """生成综合建议"""
        # 全部通过
        if dev_passed and rsi_passed and gap_passed:
            if rsi <= self.RSI_OVERCOOL:
                return Recommendation.STRONG_BUY.value
            elif price_dev < 0:
                return Recommendation.BUY.value  # 比信号价低，机会
            else:
                return Recommendation.HOLD.value
        
        # 有警告但可接受
        if not rsi_passed:
            return Recommendation.CAUTION.value
        
        if not dev_passed:
            return Recommendation.SKIP.value
        
        if not gap_passed:
            return Recommendation.CAUTION.value
        
        return Recommendation.HOLD.value
    
    # ==================== 行为追踪 ====================
    
    def track_behavior(self, code: str, action: str, validation: ValidationResult,
                      name: str = "", score: int = 0, notes: str = "") -> str:
        """
        追踪用户行为
        
        Args:
            code: ETF代码
            action: 行为类型 (ActionType枚举值或自定义字符串)
            validation: 校验结果
            name: ETF名称
            score: 选股分数
            notes: 备注
            
        Returns:
            记录ID
        """
        self._record_counter += 1
        record_id = f"BH{self._record_counter:04d}"
        
        # 获取名称
        if not name:
            prices = self.fetch_realtime_prices([code])
            name = prices.get(code, {}).get('name', code)
        
        record = BehaviorRecord(
            id=record_id,
            timestamp=datetime.now().isoformat(),
            date=date.today().isoformat(),
            code=code,
            name=name,
            action=action,
            current_price=validation.current_price,
            signal_price=validation.signal_price,
            price_deviation=validation.price_deviation,
            rsi=validation.rsi_14,
            target_gap=validation.target_gap,
            stop_gap=validation.stop_gap,
            recommendation=validation.recommendation,
            holding=validation.holding,
            cost=validation.cost,
            pnl=validation.current_pnl,
            score=score,
            market_status=self._market_status,
            notes=notes
        )
        
        self._behavior_records.append(record)
        self._save_behavior_log()
        
        return record_id
    
    def get_behavior_records(self, date_filter: str = None) -> List[BehaviorRecord]:
        """获取行为记录"""
        if date_filter:
            return [r for r in self._behavior_records if r.date == date_filter]
        return self._behavior_records
    
    # ==================== 收盘摘要 ====================
    
    def get_eod_summary(self, date_filter: str = None) -> str:
        """
        生成收盘行为摘要
        
        Args:
            date_filter: 可选，指定日期 (YYYY-MM-DD)，默认今天
            
        Returns:
            str: 格式化的摘要文本
        """
        if date_filter is None:
            date_filter = date.today().isoformat()
        
        records = [r for r in self._behavior_records if r.date == date_filter]
        
        if not records:
            return f"[{date_filter}] 今日无行为记录"
        
        # 统计
        actions_count = {}
        for r in records:
            actions_count[r.action] = actions_count.get(r.action, 0) + 1
        
        # 分类统计
        buys = [r for r in records if 'buy' in r.action.lower()]
        sells = [r for r in records if 'sell' in r.action.lower()]
        asks = [r for r in records if 'ask' in r.action.lower()]
        ignores = [r for r in records if r.action == ActionType.IGNORE.value]
        
        # 建议采纳情况
        recommendations = {}
        for r in records:
            rec = r.recommendation
            recommendations[rec] = recommendations.get(rec, 0) + 1
        
        # 构建摘要
        lines = [
            f"═══════════════════════════════════════════════════════",
            f"📊 {date_filter} 行为摘要",
            f"═══════════════════════════════════════════════════════",
            f"",
            f"📈 行为统计",
            f"  • 总询问: {len(asks)} 次",
            f"  • 确认买入: {len(buys)} 次",
            f"  • 确认卖出: {len(sells)} 次",
            f"  • 忽略建议: {len(ignores)} 次",
            f"",
        ]
        
        # 建议采纳情况
        lines.append(f"📋 校验建议统计")
        for rec, count in sorted(recommendations.items()):
            emoji = "✅" if "BUY" in rec else "⏸️" if "HOLD" in rec else "⚠️"
            lines.append(f"  {emoji} {rec}: {count} 次")
        lines.append("")
        
        # 详细记录
        if records:
            lines.append(f"📝 详细记录")
            for r in records:
                action_emoji = {
                    'ask_buy': '🔍',
                    'ask_sell': '🔍',
                    'ask_hold': '🔍',
                    'confirm_buy': '✅',
                    'confirm_sell': '✅',
                    'ignore': '⬇️',
                }.get(r.action, '•')
                
                rec_color = "🟢" if "BUY" in r.recommendation else "🟡" if "HOLD" in r.recommendation else "🔴"
                
                lines.append(
                    f"  {action_emoji} {r.code} {r.name[:8]:<8} | "
                    f"价差:{r.price_deviation:+.1f}% | "
                    f"RSI:{r.rsi:.0f} | "
                    f"{rec_color}{r.recommendation}"
                )
            lines.append("")
        
        # 与用户确认部分
        lines.append(f"═══════════════════════════════════════════════════════")
        lines.append(f"💡 操作建议")
        lines.append("")
        
        # 基于今日行为给出建议
        if buys:
            lines.append(f"  今日已确认买入 {len(buys)} 只ETF，请关注后续表现。")
        
        if ignores:
            lines.append(f"  今日忽略 {len(ignores)} 次建议，如需可重新评估。")
        
        lines.append("")
        lines.append(f"═══════════════════════════════════════════════════════")
        
        return "\n".join(lines)
    
    def update_market_status(self, status: str):
        """更新市场状态"""
        self._market_status = status


# ==================== 便捷函数 ====================

_validator_instance: Optional[TradeValidator] = None


def get_validator(data_dir: str = 'etf_data_live') -> TradeValidator:
    """获取校验器单例"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = TradeValidator(data_dir)
    return _validator_instance


def fetch_realtime_prices(codes: List[str], data_dir: str = 'etf_data_live') -> Dict[str, Dict]:
    """便捷函数: 获取实时价格"""
    return get_validator(data_dir).fetch_realtime_prices(codes)


def validate_signal(code: str, signal_price: float, score: int = 0, **kwargs) -> ValidationResult:
    """便捷函数: 校验信号"""
    return get_validator().validate_signal(code, signal_price, score, **kwargs)


def track_behavior(code: str, action: str, validation: ValidationResult, **kwargs) -> str:
    """便捷函数: 追踪行为"""
    return get_validator().track_behavior(code, action, validation, **kwargs)


def get_eod_summary(date_filter: str = None, data_dir: str = 'etf_data_live') -> str:
    """便捷函数: 获取收盘摘要"""
    return get_validator(data_dir).get_eod_summary(date_filter)


# ==================== 主程序 ====================

if __name__ == '__main__':
    # 测试用例
    print("=== ETF交易校验器测试 ===\n")
    
    # 1. 测试实时价格获取
    print("1. 测试实时价格获取...")
    codes = ['515050', '159915', '510300', '512880']
    prices = fetch_realtime_prices(codes)
    for code, data in prices.items():
        if code != '_cache_time':
            print(f"   {code}: {data.get('name', 'N/A')} = {data.get('price', 0):.3f} ({data.get('pct', 0):+.2f}%) [via {data.get('data_source', 'unknown')}]")
    
    print()
    
    # 2. 测试信号校验
    print("2. 测试信号校验...")
    result = validate_signal('515050', signal_price=1.15, score=7)
    print(f"   代码: {result.code}")
    print(f"   信号价: {result.signal_price:.3f} -> 当前价: {result.current_price:.3f}")
    print(f"   价格偏差: {result.price_deviation:+.2f}%")
    print(f"   RSI5/14: {result.rsi_5:.1f}/{result.rsi_14:.1f}")
    print(f"   距止盈: {result.target_gap:+.1f}%  距止损: {result.stop_gap:+.1f}%")
    print(f"   建议: {result.recommendation}")
    if result.warning_messages:
        print(f"   警告: {'; '.join(result.warning_messages)}")
    
    print()
    
    # 3. 测试行为追踪
    print("3. 测试行为追踪...")
    record_id = track_behavior('515050', ActionType.ASK_BUY.value, result, score=7, notes='测试记录')
    print(f"   记录ID: {record_id}")
    
    print()
    
    # 4. 测试收盘摘要
    print("4. 测试收盘摘要...")
    summary = get_eod_summary()
    print(summary)
