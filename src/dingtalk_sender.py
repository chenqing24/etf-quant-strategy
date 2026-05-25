#!/usr/bin/env python3
"""统一钉钉发送器

支持QwenPaw渠道和Webhook两种发送模式
"""
import json
import subprocess
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class DingTalkSender:
    """统一钉钉发送器"""
    
    def __init__(self, mode: str = 'qwenpaw', webhook_url: str = None):
        """初始化发送器
        
        Args:
            mode: 发送模式，'qwenpaw' 或 'webhook'
            webhook_url: Webhook URL（webhook模式使用）
        """
        self.mode = mode
        self.webhook_url = webhook_url
    
    def send(self, message: str, format: str = 'markdown') -> bool:
        """统一发送接口
        
        Args:
            message: 消息内容
            format: 消息格式，'markdown' 或 'text'
        Returns:
            bool: 发送是否成功
        """
        if self.mode == 'qwenpaw':
            return self._send_via_qwenpaw(message, format)
        elif self.mode == 'webhook':
            return self._send_via_webhook(message, format)
        else:
            logger.error(f"Unknown mode: {self.mode}")
            return False
    
    def _send_via_qwenpaw(self, message: str, format: str = 'markdown') -> bool:
        """通过QwenPaw渠道发送
        
        Args:
            message: 消息内容
            format: 消息格式
        Returns:
            bool: 发送是否成功
        """
        try:
            # 1. 获取钉钉会话列表
            result = subprocess.run(
                ['qwenpaw', 'chats', 'list', '--channel', 'dingtalk'],
                capture_output=True, text=True, timeout=15
            )
            
            if result.returncode != 0:
                logger.error(f"获取钉钉会话失败: {result.stderr}")
                return False
            
            sessions = json.loads(result.stdout)
            if not sessions:
                logger.warning("未找到钉钉会话")
                return False
            
            session = sessions[0]
            user_id = session.get('user_id', '')
            
            if not user_id:
                logger.warning("无法获取用户ID")
                return False
            
            # 2. 发送消息
            # QwenPaw渠道支持markdown格式
            msg_payload = {
                'content': message
            }
            
            result = subprocess.run([
                'qwenpaw', 'channels', 'send',
                '--agent-id', 'default',
                '--channel', 'dingtalk',
                '--target-user', user_id,
                '--content', message,
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                logger.info("钉钉消息发送成功")
                return True
            else:
                logger.error(f"钉钉消息发送失败: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("钉钉消息发送超时")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"解析会话列表失败: {e}")
            return False
        except Exception as e:
            logger.error(f"钉钉消息发送异常: {e}")
            return False
    
    def _send_via_webhook(self, message: str, format: str = 'text') -> bool:
        """通过Webhook发送
        
        Args:
            message: 消息内容
            format: 消息格式
        Returns:
            bool: 发送是否成功
        """
        if not self.webhook_url:
            logger.error("Webhook URL未设置")
            return False
        
        try:
            import requests
            
            if format == 'markdown':
                payload = {
                    'msgtype': 'markdown',
                    'markdown': {
                        'title': 'ETF量化决策',
                        'text': message
                    }
                }
            else:
                payload = {
                    'msgtype': 'text',
                    'text': {
                        'content': message
                    }
                }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("Webhook消息发送成功")
                return True
            else:
                logger.error(f"Webhook消息发送失败: {response.status_code}")
                return False
                
        except ImportError:
            logger.error("requests库未安装")
            return False
        except Exception as e:
            logger.error(f"Webhook消息发送异常: {e}")
            return False
    
    @staticmethod
    def is_available() -> bool:
        """检查QwenPaw渠道是否可用"""
        try:
            result = subprocess.run(
                ['qwenpaw', 'chats', 'list', '--channel', 'dingtalk'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                sessions = json.loads(result.stdout)
                return len(sessions) > 0
            return False
        except Exception:
            return False


# 单例实例
_sender = None

def get_sender(mode: str = 'qwenpaw', webhook_url: str = None) -> DingTalkSender:
    """获取发送器单例"""
    global _sender
    if _sender is None or _sender.mode != mode:
        _sender = DingTalkSender(mode=mode, webhook_url=webhook_url)
    return _sender
