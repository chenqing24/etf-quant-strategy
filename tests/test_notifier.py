#!/usr/bin/env python3
"""钉钉通知测试 - 防止回归

测试决策报告是否使用正确的渠道发送：
- 钉钉/移动端：简化独立模板
- PC端控制台：完整报告
"""
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_send_daily_summary_uses_simplified_template():
    """测试 send_daily_summary 使用钉钉专属简化模板"""
    from src.notifier import SignalNotifier
    import json
    
    notifier = SignalNotifier(enable_console=False, webhook_url='http://test')
    
    # Mock requests.post 来捕获发送的消息
    captured_data = []
    def mock_post(*args, **kwargs):
        captured_data.append(kwargs.get('data', ''))
        return MagicMock(status_code=200)
    
    with patch('requests.post', mock_post):
        notifier.send_daily_summary({
            'action': '买入',
            'new_code': '515050',
            'name': '科技50',
            'price': 1.204,
            # 无 report_file（钉钉模板不需要完整报告）
        })
    
    # 验证发送的是简化消息
    assert len(captured_data) > 0, "应该有钉钉消息发送"
    
    msg_data = json.loads(captured_data[0])
    actual_text = msg_data['text']['content']
    
    # 钉钉模板应包含：操作、标的、价格、止盈止损
    assert '买入' in actual_text, "应包含买入操作"
    assert '515050' in actual_text, "应包含标的代码"
    assert '1.204' in actual_text, "应包含信号价格"
    assert '止损' in actual_text or '止盈' in actual_text, "应包含止盈止损信息"
    
    # 不应该包含完整报告的markdown格式
    assert '======================================================================' not in actual_text, "钉钉模板不应包含完整报告的分隔线"
    
    print("✅ test_send_daily_summary_uses_simplified_template: PASSED")
    return True


def test_send_daily_summary_with_realtime_data():
    """测试 send_daily_summary 包含实时数据"""
    from src.notifier import SignalNotifier
    import json
    
    notifier = SignalNotifier(enable_console=False, webhook_url='http://test')
    
    captured_data = []
    def mock_post(*args, **kwargs):
        captured_data.append(kwargs.get('data', ''))
        return MagicMock(status_code=200)
    
    with patch('requests.post', mock_post):
        notifier.send_daily_summary({
            'action': '买入',
            'new_code': '515050',
            'name': '科技50',
            'price': 1.101,  # 信号价
            'realtime': {
                'price': 1.205,  # 实时价
                'change_pct': 4.51,
            },
            'indicators': {
                'rsi_14': 70.5,  # RSI过热
            }
        })
    
    msg_data = json.loads(captured_data[0])
    actual_text = msg_data['text']['content']
    
    # 应包含实时价格
    assert '1.205' in actual_text, "应包含实时价格"
    assert '4.51' in actual_text, "应包含涨跌幅"
    
    # 应包含RSI状态
    assert 'RSI14' in actual_text, "应包含RSI指标"
    assert '过热' in actual_text, "应包含过热状态"
    
    print("✅ test_send_daily_summary_with_realtime_data: PASSED")
    return True


def test_send_full_report_to_console():
    """测试 send_full_report_to_console 输出完整报告到控制台"""
    from src.notifier import SignalNotifier
    import io
    from contextlib import redirect_stdout
    
    # 创建临时报告文件
    report_content = """======================================================================
📈 ETF量化投资决策报告
======================================================================
🔍 实时校验 (实时数据对比)
======================================================================
实时价: 1.205 | RSI14: 70.5"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(report_content)
        report_file = f.name
    
    try:
        notifier = SignalNotifier(enable_console=True, webhook_url='http://test')
        
        output = io.StringIO()
        with redirect_stdout(output):
            notifier.send_full_report_to_console(report_file)
        
        result = output.getvalue()
        
        # PC端控制台应输出完整报告
        assert '实时校验' in result, "PC控制台应输出完整报告"
        assert '实时价: 1.205' in result, "PC控制台应包含实时价格"
        assert '======================================================================' in result, "PC控制台应包含完整格式"
        
        print("✅ test_send_full_report_to_console: PASSED")
        return True
        
    finally:
        os.unlink(report_file)


def test_decision_cli_sends_simplified_to_dingtalk():
    """测试 decision_cli._send_to_dingtalk 发送简化消息到钉钉"""
    # Mock subprocess
    captured_calls = []
    def mock_run(*args, **kwargs):
        captured_calls.append({'args': args, 'kwargs': kwargs})
        class MockResult:
            stdout = '[{"user_id": "test", "session_id": "test"}]'
        return MockResult()
    
    import importlib
    import src.decision_cli as dc_module
    importlib.reload(dc_module)
    
    import subprocess
    with patch.object(subprocess, 'run', mock_run):
        cli = dc_module.ETFDecisionEngine()
        cli._send_to_dingtalk(
            action='买入',
            code='515050',
            name='科技50',
            price=1.204,
            indicators={'rsi_14': 70.5}
        )
    
    # 验证发送简化消息
    assert len(captured_calls) > 0, "应该有subprocess调用"
    
    send_call = None
    for call in captured_calls:
        args_str = str(call.get('args', ''))
        if 'channels' in args_str:
            send_call = call
            break
    
    assert send_call is not None, "应该有qwenpaw channels send调用"
    
    # 提取发送的文本
    args_list = send_call.get('args', [[]])[0]
    text_arg = None
    for item in args_list:
        if isinstance(item, str) and item == '--text':
            idx = args_list.index(item)
            if idx + 1 < len(args_list):
                text_arg = args_list[idx + 1]
                break
    
    assert text_arg is not None, "应该有--text参数"
    
    # 钉钉消息应该是简化的
    assert '买入' in text_arg, "应包含买入操作"
    assert '515050' in text_arg, "应包含标的"
    assert '======================================================================' not in text_arg, "钉钉不应发送完整报告格式"
    
    print("✅ test_decision_cli_sends_simplified_to_dingtalk: PASSED")
    return True


if __name__ == '__main__':
    print("=" * 60)
    print("钉钉通知测试套件")
    print("=" * 60)
    
    tests = [
        test_send_daily_summary_uses_simplified_template,
        test_send_daily_summary_with_realtime_data,
        test_send_full_report_to_console,
        test_decision_cli_sends_simplified_to_dingtalk,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"❌ {test.__name__}: FAILED - {e}")
            failed += 1
        except Exception as e:
            print(f"❌ {test.__name__}: ERROR - {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("=" * 60)
    print(f"结果: {passed} passed, {failed} failed")
    print("=" * 60)
    
    sys.exit(0 if failed == 0 else 1)
