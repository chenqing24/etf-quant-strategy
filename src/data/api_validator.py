#!/usr/bin/env python3
"""
API格式验证器
============
检测API响应格式变化，发送告警

功能：
- 验证响应格式
- 检测格式变化
- 记录异常
"""

import re
from typing import Optional, Dict
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.logger import get_logger

logger = get_logger()

# 已知的正常格式
EXPECTED_FORMATS = {
    'tencent': {
        'pattern': r'~[^~]+~[0-9]',  # 名称后是数字代码
        'min_length': 10,
        'name_index': 1,
        'separator': '~',
    },
    'sina': {
        'pattern': r'"[^"]+",',  # 名称在引号内，后面是逗号
        'min_length': 20,
    },
}

# 格式变化告警阈值
FORMAT_CHANGE_THRESHOLD = 3  # 连续3次异常才告警


class APIFormatValidator:
    """API格式验证器"""
    
    def __init__(self):
        self._anomaly_count = {}  # 每个渠道的异常计数
        self._last_normal = {}    # 每个渠道最后正常时间
    
    def validate(self, channel: str, raw_response: str) -> bool:
        """验证API响应格式是否正常
        
        Args:
            channel: 渠道名称（tencent/sina）
            raw_response: 原始响应
            
        Returns:
            True 正常，False 异常
        """
        format_config = EXPECTED_FORMATS.get(channel)
        if not format_config:
            return True  # 未知的channel，跳过验证
        
        # 检查长度
        if len(raw_response) < format_config['min_length']:
            logger.info(f"[{channel}] 响应长度过短: {len(raw_response)} < {format_config['min_length']}")
            return False
        
        # 检查正则
        pattern = format_config['pattern']
        if not re.search(pattern, raw_response):
            logger.info(f"[{channel}] 响应格式不匹配: {pattern}")
            return False
        
        # 正常
        self._anomaly_count[channel] = 0
        self._last_normal[channel] = datetime.now().isoformat()
        return True
    
    def detect_format_change(self, channel: str, raw_response: str) -> bool:
        """检测格式变化
        
        Returns:
            True 格式变化，False 正常
        """
        is_valid = self.validate(channel, raw_response)
        
        if not is_valid:
            # 异常计数+1
            self._anomaly_count[channel] = self._anomaly_count.get(channel, 0) + 1
            
            count = self._anomaly_count[channel]
            
            if count >= FORMAT_CHANGE_THRESHOLD:
                # 连续3次异常，认为格式变化
                message = f"⚠️ [{channel}] API格式可能变化\n"
                message += f"连续异常: {count}次\n"
                message += f"响应样本: {raw_response[:200]}"
                
                logger.info(message)
                
                # 重置计数（避免重复告警）
                self._anomaly_count[channel] = 0
                
                return True
        
        return False
    
    def is_format_stable(self, channel: str) -> bool:
        """检查格式是否稳定（最近1小时无异常）"""
        if channel not in self._last_normal:
            return True  # 无记录，默认稳定
        
        last = datetime.fromisoformat(self._last_normal[channel])
        elapsed = (datetime.now() - last).total_seconds()
        
        return elapsed < 3600  # 1小时内有正常响应


# 全局实例
_validator = None

def get_validator() -> APIFormatValidator:
    """获取验证器单例"""
    global _validator
    if _validator is None:
        _validator = APIFormatValidator()
    return _validator