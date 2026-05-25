#!/usr/bin/env python3
"""场景适配器

根据场景（移动端/PC端）构建并发送适当格式的报告
"""
from typing import Dict, Optional
import logging

from .report_builder import ReportBuilder, get_builder
from .dingtalk_sender import DingTalkSender, get_sender

logger = logging.getLogger(__name__)


class ScenarioAdapter:
    """场景适配器
    
    统一处理不同场景的报告构建和发送
    """
    
    # 场景常量
    SCENARIO_MOBILE = 'mobile'    # 钉钉/定时任务
    SCENARIO_PC = 'pc'            # PC网页端
    SCENARIO_CONSOLE = 'console'  # 命令行
    
    def __init__(self, scenario: str = SCENARIO_MOBILE):
        """初始化适配器
        
        Args:
            scenario: 场景类型，'mobile', 'pc', 'console'
        """
        self.scenario = scenario
        self.builder: ReportBuilder = get_builder()
        self.sender: DingTalkSender = get_sender()
    
    def build_report(self, results: Dict, report_file: str = None) -> str:
        """根据场景构建报告
        
        Args:
            results: 决策结果
            report_file: 完整报告文件路径（PC端使用）
        Returns:
            str: 报告内容
        """
        if self.scenario == self.SCENARIO_MOBILE:
            # 移动端：简版报告
            return self.builder.build_simple(results)
        elif self.scenario == self.SCENARIO_PC:
            # PC端：详细报告
            return self.builder.build_full(results, report_file)
        else:
            # 控制台：详细报告
            return self.builder.build_full(results, report_file)
    
    def send_report(self, message: str) -> bool:
        """发送报告
        
        Args:
            message: 报告内容
        Returns:
            bool: 发送是否成功
        """
        # 只在移动端场景才发送钉钉消息
        if self.scenario == self.SCENARIO_MOBILE:
            action = '观望'  # 默认不发送
            if '🟢 买入' in message or '🔴 卖出' in message:
                return self.sender.send(message, format='markdown')
            else:
                logger.info("观望操作，跳过钉钉推送")
                return True
        else:
            # PC/控制台：直接打印到标准输出
            print("\n" + "=" * 60)
            print("📊 报告内容")
            print("=" * 60)
            print(message)
            print("=" * 60 + "\n")
            return True
    
    def build_and_send(self, results: Dict, report_file: str = None) -> bool:
        """构建并发送报告
        
        完整的业务流程：根据场景构建报告，然后发送
        
        Args:
            results: 决策结果
            report_file: 完整报告文件路径
        Returns:
            bool: 是否成功
        """
        # 1. 构建报告
        message = self.build_report(results, report_file)
        
        # 2. 发送报告
        return self.send_report(message)
    
    @classmethod
    def for_mobile(cls) -> 'ScenarioAdapter':
        """创建移动端适配器"""
        return cls(scenario=cls.SCENARIO_MOBILE)
    
    @classmethod
    def for_pc(cls) -> 'ScenarioAdapter':
        """创建PC端适配器"""
        return cls(scenario=cls.SCENARIO_PC)
    
    @classmethod
    def for_console(cls) -> 'ScenarioAdapter':
        """创建控制台适配器"""
        return cls(scenario=cls.SCENARIO_CONSOLE)


def notify_decision(results: Dict, scenario: str = 'mobile', 
                    report_file: str = None) -> bool:
    """便捷函数：通知决策结果
    
    Args:
        results: 决策结果
        scenario: 场景类型
        report_file: 完整报告文件路径
    Returns:
        bool: 是否成功
    """
    adapter = ScenarioAdapter(scenario=scenario)
    return adapter.build_and_send(results, report_file)
