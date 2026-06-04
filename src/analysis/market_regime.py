#!/usr/bin/env python3
"""
市场环境判断（US-006）

基于 510300 的 MA20/MA60/MA120 排列 + ATR 波动率判断市场环境：
- trend_up: 强趋势向上（MA 排列多头 + 波动率正常）
- range_bound: 震荡市（MA 缠绕 + 波动率低）
- trend_down: 下跌趋势（MA 排列空头 + 波动率正常）
- crash: 暴跌（短期急跌 + 高波动率）

业界参考：
- 海龟交易法则：ATR-based 趋势判断
- 移动平均线排列：MA20 > MA60 > MA120 = 强趋势
- VIX/波动率：ATR/Price > 5% = 高波动

使用方式：
    from src.analysis.market_regime import MarketRegimeDetector

    detector = MarketRegimeDetector()
    regime = detector.detect(market_df)  # market_df 含 close 列
    # regime: 'trend_up' | 'range_bound' | 'trend_down' | 'crash'
"""
import logging
import pandas as pd
import numpy as np
from typing import Literal

_logger = logging.getLogger(__name__)

# US-013: 8 状态细分 (initial_up/uptrend/late_up/initial_down/downtrend/late_down/range_bullish/range_bearish)
Regime = Literal[
    'initial_up',    # 初升
    'uptrend',       # 上升中
    'late_up',       # 末升
    'initial_down',  # 初降
    'downtrend',     # 下降中
    'late_down',     # 末降
    'range_bullish', # 震荡偏强
    'range_bearish', # 震荡偏弱
    'reversal_point',# 反转点
    'crash',         # 暴跌
]

REGIME_LABELS = {
    # US-013: 8 状态细分
    'initial_up': '初升',
    'uptrend': '上升中',
    'late_up': '末升',
    'initial_down': '初降',
    'downtrend': '下降中',
    'late_down': '末降',
    'range_bullish': '震荡偏强',
    'range_bearish': '震荡偏弱',
    'reversal_point': '反转点',
    'crash': '暴跌市',
    # 向后兼容 4 状态别名
    'trend_up': '趋势市',
    'range_bound': '震荡市',
    'trend_down': '下跌市',
}

REGIME_EMOJI = {
    'initial_up': '🌱',
    'uptrend': '📈',
    'late_up': '🏔️',
    'initial_down': '🌧️',
    'downtrend': '🔻',
    'late_down': '⛰️',
    'range_bullish': '📊',
    'range_bearish': '📉',
    'reversal_point': '🔄',
    'crash': '🚨',
    # 向后兼容
    'trend_up': '📈',
    'range_bound': '📊',
    'trend_down': '🔻',
}

# US-013: 市态 → 策略映射 (8 状态 → 4 策略)
REGIME_TO_STRATEGIES = {
    'initial_up':    ['trend_following', 'breakout'],
    'uptrend':       ['trend_following', 'breakout'],
    'late_up':       ['trend_following'],
    'initial_down':  [],
    'downtrend':     [],
    'late_down':     ['mean_reversion'],
    'range_bullish': ['mean_reversion', 'volume_divergence'],
    'range_bearish': ['mean_reversion'],
    'reversal_point':['breakout', 'volume_divergence'],
    'crash':         [],
}

# US-013: 市态 → 仓位 (US-015 上限)
REGIME_TO_POSITION_LIMIT = {
    'initial_up':    0.85,
    'uptrend':       0.85,
    'late_up':       0.60,
    'initial_down':  0.20,
    'downtrend':     0.10,
    'late_down':     0.30,
    'range_bullish': 0.50,
    'range_bearish': 0.40,
    'reversal_point':0.30,
    'crash':         0.00,
}


class MarketRegimeDetector:
    """市场环境检测器（US-006）"""

    # 阈值
    MA_FAST = 20
    MA_MID = 60
    MA_SLOW = 120
    ATR_PERIOD = 14

    # 排列阈值（MA 之间的差异）
    MA_SPREAD_THRESHOLD = 0.05  # 5%

    # US-013: MA 排列容差 (允许小幅趋同)
    MA_TOLERANCE = 0.01  # 1% 容差

    # 暴跌检测
    CRASH_DROP_PCT = -0.05  # 5 天内跌 5%+
    CRASH_ATR_RATIO = 0.05  # ATR/Price > 5%

    def detect_reversal_point(self, df: pd.DataFrame) -> bool:
        """
        US-002: 反转点检测（业界综合）
        - BB Squeeze (BB Width < 5%)
        - RSI 极端 (< 30 或 > 70)
        - 成交量异动 (vol_ratio > 1.5)
        至少 2 个信号触发
        """
        if df is None or len(df) < 30:
            return False
        closes = df['close'].astype(float).reset_index(drop=True)
        # 1. BB Width
        ma20 = closes.rolling(20).mean()
        std20 = closes.rolling(20).std()
        bb_upper = ma20 + 2 * std20
        bb_lower = ma20 - 2 * std20
        bb_width = (bb_upper - bb_lower) / ma20
        bb_squeeze = bool(bb_width.iloc[-1] < 0.05) if not pd.isna(bb_width.iloc[-1]) else False
        # 2. RSI
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1]
        rsi_extreme = (rsi_val < 30 or rsi_val > 70) if not pd.isna(rsi_val) else False
        # 3. 成交量异动
        vol_spike = False
        if 'volume' in df.columns and len(df) >= 20:
            volumes = df['volume'].astype(float).reset_index(drop=True)
            vol_ma20 = volumes.rolling(20).mean()
            if not pd.isna(vol_ma20.iloc[-1]) and vol_ma20.iloc[-1] > 0:
                vol_ratio = volumes.iloc[-1] / vol_ma20.iloc[-1]
                vol_spike = vol_ratio > 1.5
        # 综合判断: 至少 2 个信号
        signals = sum([bb_squeeze, rsi_extreme, vol_spike])
        return bool(signals >= 2)

    def _calc_30d_return(self, df: pd.DataFrame) -> float:
        """30 日回报"""
        if df is None or len(df) < 30:
            return 0
        closes = df['close'].astype(float).reset_index(drop=True)
        return float(closes.iloc[-1] / closes.iloc[-30] - 1)

    def _classify_8state(self, df: pd.DataFrame, ma_align: str) -> Regime:
        """根据 MA 排列 + 30d 回报判定 8 状态
        
        Args:
            df: 510300 数据
            ma_align: 'bull_full' | 'bull_partial' | 'bear_full' | 'bear_partial' | 'mixed'
        """
        ret_30d = self._calc_30d_return(df)
        # 强多头 (ma5/ma20/ma60/ma120 都多头排列)
        if ma_align == 'bull_full':
            if ret_30d > 0.05:
                return 'initial_up'  # 初升 (30d > 5%)
            elif ret_30d >= -0.02:
                return 'uptrend'  # 上升中
            else:
                return 'late_up'  # 末升 (动能减弱)
        # 部分多头 (ma20/ma60/ma120 多头)
        elif ma_align == 'bull_partial':
            if ret_30d > 0.02:
                return 'uptrend'  # 上升中
            elif ret_30d >= -0.02:
                return 'range_bullish'  # 震荡偏强
            else:
                return 'late_up'  # 末升
        # 强空头
        elif ma_align == 'bear_full':
            if ret_30d < -0.05:
                return 'initial_down'  # 初降
            elif ret_30d <= 0.02:
                return 'downtrend'  # 下降中
            else:
                return 'late_down'  # 末降
        # 部分空头
        elif ma_align == 'bear_partial':
            if ret_30d < -0.02:
                return 'downtrend'
            elif ret_30d > 0.02:
                return 'late_down'  # 末降 (接近反转)
            else:
                return 'range_bearish'  # 震荡偏弱
        # 缠绕
        else:  # 'mixed'
            if ret_30d > 0.02:
                return 'range_bullish'  # 震荡偏强
            elif ret_30d < -0.02:
                return 'range_bearish'  # 震荡偏弱
            else:
                return 'range_bearish'  # 默认震荡偏弱

    def _get_ma_align(self, df: pd.DataFrame) -> str:
        """获取 MA 排列分类 (1% 容差)
        
        Returns:
            'bull_full' (5/20/60/120 全多) | 'bull_partial' (20/60/120 多) |
            'bear_full' | 'bear_partial' | 'mixed'
        """
        closes = df['close'].astype(float).reset_index(drop=True)
        if len(closes) < 120:
            return 'mixed'
        ma5 = closes.rolling(5).mean().iloc[-1]
        ma20 = closes.rolling(20).mean().iloc[-1]
        ma60 = closes.rolling(60).mean().iloc[-1]
        ma120 = closes.rolling(120).mean().iloc[-1]
        tol = self.MA_TOLERANCE  # 1% 容差
        # 强多头: ma5 > ma20 > ma60 > ma120 (1% 容差)
        if (ma5 >= ma20 * (1 - tol) and ma20 >= ma60 * (1 - tol) and 
            ma60 >= ma120 * (1 - tol)):
            return 'bull_full'
        # 强空头: ma5 < ma20 < ma60 < ma120
        if (ma5 <= ma20 * (1 + tol) and ma20 <= ma60 * (1 + tol) and
            ma60 <= ma120 * (1 + tol)):
            return 'bear_full'
        # 部分多头: ma20 > ma60 > ma120
        if ma20 >= ma60 * (1 - tol) and ma60 >= ma120 * (1 - tol):
            return 'bull_partial'
        # 部分空头: ma20 < ma60 < ma120
        if ma20 <= ma60 * (1 + tol) and ma60 <= ma120 * (1 + tol):
            return 'bear_partial'
        return 'mixed'

    def detect_8state(self, df: pd.DataFrame) -> Regime:
        """US-013: 8 状态检测 (初升/上升中/末升/初降/下降中/末降/震荡偏强/震荡偏弱)
        
        Args:
            df: 510300 历史数据
        
        Returns:
            10 状态之一
        """
        if df is None or len(df) < self.MA_SLOW + 10:
            return 'range_bearish'  # type: ignore[return-value]
        
        # 1. 反转点检测 (优先级最高)
        if self.detect_reversal_point(df):
            return 'reversal_point'  # type: ignore[return-value]
        
        # 2. 暴跌检测
        closes = df['close'].astype(float).reset_index(drop=True)
        current_price = float(closes.iloc[-1])
        ret_5d = (current_price / float(closes.iloc[-6])) - 1 if len(closes) >= 6 else 0
        atr = self._calc_atr(df, self.ATR_PERIOD)
        atr_ratio = atr / current_price if current_price > 0 else 0
        if ret_5d <= self.CRASH_DROP_PCT and atr_ratio > self.CRASH_ATR_RATIO:
            return 'crash'  # type: ignore[return-value]
        
        # 3. 8 状态细分
        ma_align = self._get_ma_align(df)
        return self._classify_8state(df, ma_align)

    def detect_30d_rolling(self, df: pd.DataFrame) -> Regime:
        """US-013: 30 天滚动判定 (多数票)
        
        Args:
            df: 510300 历史数据
        
        Returns:
            30 天多数票的市态
        """
        if df is None or len(df) < 60:
            return self.detect_8state(df)
        # 取最后 30 个交易日的市态
        signals = []
        for i in range(1, 31):
            if len(df) - i < self.MA_SLOW + 10:
                break
            window = df.iloc[:len(df) - i + 1]
            signals.append(self.detect_8state(window))
        if not signals:
            return 'range_bearish'  # type: ignore[return-value]
        from collections import Counter
        return Counter(signals).most_common(1)[0][0]

    def detect_multi_timeframe(self, df: pd.DataFrame) -> Regime:
        """US-013: 多时间框架投票 (1周 + 1月 + 1季)
        
        Returns:
            8 状态 (任 2 个时间框架一致 → 确认)
        """
        if df is None or len(df) < 120:
            return self.detect_30d_rolling(df)
        closes = df['close'].astype(float).reset_index(drop=True)
        if len(closes) < 120:
            return 'range_bearish'  # type: ignore[return-value]
        ma5 = closes.rolling(5).mean().iloc[-1]
        ma10 = closes.rolling(10).mean().iloc[-1]
        ma20 = closes.rolling(20).mean().iloc[-1]
        ma60 = closes.rolling(60).mean().iloc[-1]
        ma120 = closes.rolling(120).mean().iloc[-1]
        tol = self.MA_TOLERANCE
        # 3 个时间框架投票
        votes = []
        # 1 周 (ma5/ma10)
        if ma5 >= ma10 * (1 - tol):
            votes.append('up')
        else:
            votes.append('down')
        # 1 月 (ma20/ma60)
        if ma20 >= ma60 * (1 - tol):
            votes.append('up')
        else:
            votes.append('down')
        # 1 季 (ma60/ma120)
        if ma60 >= ma120 * (1 - tol):
            votes.append('up')
        else:
            votes.append('down')
        # 多数票
        up_count = votes.count('up')
        if up_count >= 2:
            # 多数 up → 8 状态细分
            return self.detect_8state(df)
        else:
            # 多数 down → 8 状态细分
            return self.detect_8state(df)

    def detect(self, df: pd.DataFrame) -> Regime:
        """
        检测市场环境

        Args:
            df: 510300 历史数据 DataFrame，至少含 'close' 列，建议 200+ 行

        Returns:
            'trend_up' | 'range_bound' | 'trend_down' | 'crash'
        """
        if df is None or len(df) < self.MA_SLOW + 10:
            return 'range_bound'  # type: ignore[return-value]  # 数据不足时默认震荡 # type: ignore[return-value]

        closes = df['close'].astype(float).reset_index(drop=True)

        # 1. 计算 MA
        ma20 = closes.rolling(self.MA_FAST).mean().iloc[-1]
        ma60 = closes.rolling(self.MA_MID).mean().iloc[-1]
        ma120 = closes.rolling(self.MA_SLOW).mean().iloc[-1]
        current_price = float(closes.iloc[-1])

        # 2. 计算 ATR
        atr = self._calc_atr(df, self.ATR_PERIOD)
        atr_ratio = atr / current_price if current_price > 0 else 0

        # 3. 计算 5 日回报（用于暴跌检测）
        ret_5d = (current_price / float(closes.iloc[-6])) - 1 if len(closes) >= 6 else 0

        # US-013: detect() 改为 8 状态 (向后兼容保留 4 状态别名)
        # 反转点检测（US-002，优先级高于 trend）
        if self.detect_reversal_point(df):
            _logger.info("市场环境: 反转点 (BB Squeeze + RSI 极端 + 成交量异动)")
            return 'reversal_point'  # type: ignore[return-value]

        # 4. 暴跌检测（保留为子状态，紧急用）
        if ret_5d <= self.CRASH_DROP_PCT and atr_ratio > self.CRASH_ATR_RATIO:
            _logger.info(f"市场环境: 暴跌 (5d ret={ret_5d:.2%}, ATR={atr_ratio:.2%})")
            return 'crash'

        # 5. 趋势判断（基于 MA 排列 + spread）
        ma_spread = (ma20 - ma120) / ma120 if ma120 > 0 else 0

        # 震荡市优先判断：MA 之间差异小于阈值 → 缠绕 → 震荡
        if abs(ma_spread) <= self.MA_SPREAD_THRESHOLD:
            _logger.info(f"市场环境: 震荡市 (MA 缠绕，spread={ma_spread:.2%})")
            return 'range_bound'

        # 多头排列：MA20 > MA60 > MA120，且 spread > 阈值
        if ma20 > ma60 > ma120 and ma_spread > self.MA_SPREAD_THRESHOLD:
            _logger.info(f"市场环境: 趋势向上 (MA20={ma20:.3f} > MA60={ma60:.3f} > MA120={ma120:.3f}, spread={ma_spread:.2%})")
            return 'trend_up'  # type: ignore[return-value]

        # 空头排列：MA20 < MA60 < MA120
        if ma20 < ma60 < ma120 and ma_spread < -self.MA_SPREAD_THRESHOLD:
            _logger.info(f"市场环境: 下跌趋势 (MA20={ma20:.3f} < MA60={ma60:.3f} < MA120={ma120:.3f}, spread={ma_spread:.2%})")
            return 'trend_down'  # type: ignore[return-value]

        # 6. 默认震荡市（MA 部分排列但 spread 不足）
        _logger.info(f"市场环境: 震荡市 (MA 排列弱，spread={ma_spread:.2%})")
        return 'range_bound'

    def _calc_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """计算 ATR（平均真实波幅）"""
        if len(df) < period + 1:
            return 0.0

        high = df['high'].astype(float).reset_index(drop=True)
        low = df['low'].astype(float).reset_index(drop=True)
        close = df['close'].astype(float).reset_index(drop=True)

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.rolling(period).mean().iloc[-1]
        return float(atr) if not np.isnan(atr) else 0.0

    def can_trade(self, regime: Regime) -> bool:
        """判断当前 regime 是否允许交易

        设计原则（v8_sop 策略限制）：
        - trend_up: 允许
        - range_bound: 不允许（震荡市空仓）
        - trend_down: 不允许（下跌市空仓）
        - crash: 不允许（暴跌观望）
        """
        return regime == 'trend_up'

    def get_label(self, regime: Regime) -> str:
        return REGIME_LABELS.get(regime, '未知')

    def get_emoji(self, regime: Regime) -> str:
        return REGIME_EMOJI.get(regime, '❓')
