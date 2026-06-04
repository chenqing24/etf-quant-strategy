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

Regime = Literal['trend_up', 'range_bound', 'trend_down', 'reversal_point', 'crash']  # US-002

REGIME_LABELS = {
    'trend_up': '趋势市',
    'range_bound': '震荡市',
    'trend_down': '下跌市',
    'crash': '暴跌市',
    'reversal_point': '反转点',
}

REGIME_EMOJI = {
    'trend_up': '📈',
    'range_bound': '📊',
    'trend_down': '🔻',
    'crash': '🚨',
    'reversal_point': '🔄',
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

        # 4. 反转点检测（US-002，优先级高于 trend）
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
