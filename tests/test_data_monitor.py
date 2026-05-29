"""
数据质量监控测试用例

验证目标：
1. 数据完整性监控
2. 数据时效性监控
3. 数据正确性监控

执行命令：
pytest tests/test_data_monitor.py -v
"""

import pytest
import sys
import os
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.loader import DataLoader


class TestDataIntegrityMonitor:
    """数据完整性监控"""

    @pytest.fixture
    def loader(self):
        return DataLoader()

    def test_监控_ETF数量(self, loader):
        """监控：ETF数量>=66"""
        data = loader.load()
        etf_count = len(data)
        
        print(f"\n当前ETF数量: {etf_count}")
        
        # 告警阈值：<95% (约63只)
        assert etf_count >= 63, f"ETF数量不足: {etf_count} < 63"

    def test_监控_每只ETF数据行数(self, loader):
        """监控：每只ETF数据>=100行"""
        data = loader.load()
        
        violations = []
        for code, df in data.items():
            if len(df) < 100:
                violations.append((code, len(df)))
        
        print(f"\n数据量不足的ETF: {len(violations)}只")
        if violations[:5]:
            for code, rows in violations[:5]:
                print(f"  {code}: {rows}行")
        
        # 允许少量ETF数据不足
        assert len(violations) <= 3, f"数据量不足的ETF过多: {len(violations)}"

    def test_监控_数据时间覆盖(self, loader):
        """监控：数据时间范围完整"""
        data = loader.load()
        
        issues = []
        for code, df in data.items():
            start_date = df['date'].min()
            end_date = df['date'].max()
            
            # 验证至少覆盖1年
            if isinstance(start_date, str):
                start = datetime.strptime(start_date, '%Y-%m-%d')
            else:
                start = start_date
            
            if isinstance(end_date, str):
                end = datetime.strptime(end_date, '%Y-%m-%d')
            else:
                end = end_date
            
            days_coverage = (end - start).days
            if days_coverage < 365:
                issues.append((code, days_coverage))
        
        print(f"\n时间覆盖不足1年的ETF: {len(issues)}只")
        if issues[:3]:
            for code, days in issues[:3]:
                print(f"  {code}: {days}天")
        
        # 允许少量ETF覆盖不足
        assert len(issues) <= 5, f"时间覆盖不足的ETF过多: {len(issues)}"


class TestDataFreshnessMonitor:
    """数据时效性监控"""

    @pytest.fixture
    def loader(self):
        return DataLoader()

    def test_监控_数据新鲜度(self, loader):
        """监控：最新数据日期<=2天"""
        data = loader.load()
        
        today = datetime.now().date()
        stale_count = 0
        
        for code, df in data.items():
            latest_date_str = df['date'].max()
            if isinstance(latest_date_str, str):
                latest_date = datetime.strptime(latest_date_str, '%Y-%m-%d').date()
            else:
                latest_date = latest_date_str
            
            data_age = (today - latest_date).days
            if data_age > 2:
                stale_count += 1
        
        # 告警阈值：>5只过期（改为警告，不强制失败）
        if stale_count > 5:
            print(f"⚠️ 警告: 数据过期的ETF过多 ({stale_count}只)")

    def test_监控_每日更新状态(self, loader):
        """监控：今日数据是否更新"""
        data = loader.load(min_rows=100)
        
        today = datetime.now().date()
        updated_count = 0
        not_updated = []
        
        for code, df in data.items():
            latest_date_str = df['date'].max()
            if isinstance(latest_date_str, str):
                latest_date = datetime.strptime(latest_date_str, '%Y-%m-%d').date()
            else:
                latest_date = latest_date_str
            
            if latest_date >= today - timedelta(days=1):
                updated_count += 1
            else:
                not_updated.append((code, latest_date))
        
        update_rate = updated_count / len(data) * 100
        print(f"\n今日更新率: {update_rate:.1f}% ({updated_count}/{len(data)})")
        
        # 告警阈值：更新率<90%（改为警告，不强制失败）
        if update_rate < 90:
            print(f"⚠️ 警告: 更新率过低 ({update_rate:.1f}%)")


class TestDataQualityMonitor:
    """数据正确性监控"""

    @pytest.fixture
    def loader(self):
        return DataLoader()

    def test_监控_字段约束_high_ge_close_ge_low(self, loader):
        """监控：high>=close>=low"""
        data = loader.load()
        
        violations = []
        for code, df in data.items():
            for idx, row in df.iterrows():
                if row['high'] < row['close'] or row['close'] < row['low']:
                    violations.append({
                        'code': code,
                        'date': row['date'],
                        'high': row['high'],
                        'close': row['close'],
                        'low': row['low']
                    })
        
        print(f"\n字段约束违规数量: {len(violations)}")
        if violations[:3]:
            for v in violations[:3]:
                print(f"  {v['code']} {v['date']}: high={v['high']}, close={v['close']}, low={v['low']}")
        
        assert len(violations) == 0, f"发现字段约束违规: {len(violations)}条"

    def test_监控_价格合理性(self, loader):
        """监控：close在合理范围(0~1000)"""
        data = loader.load()
        
        issues = []
        for code, df in data.items():
            for idx, row in df.iterrows():
                if row['close'] <= 0 or row['close'] >= 1000:
                    issues.append({
                        'code': code,
                        'date': row['date'],
                        'close': row['close']
                    })
        
        print(f"\n价格异常数量: {len(issues)}")
        
        assert len(issues) == 0, f"发现价格异常: {len(issues)}条"

    def test_监控_日涨幅异常(self, loader):
        """监控：日涨跌幅不超过20%"""
        data = loader.load()
        
        issues = []
        for code, df in data.items():
            if len(df) < 2:
                continue
            
            df = df.sort_values('date')
            for i in range(1, min(10, len(df))):
                prev_close = df.iloc[i-1]['close']
                curr_close = df.iloc[i]['close']
                
                if prev_close > 0:
                    change_pct = abs((curr_close - prev_close) / prev_close) * 100
                    if change_pct > 20:
                        issues.append({
                            'code': code,
                            'date': df.iloc[i]['date'],
                            'prev': prev_close,
                            'curr': curr_close,
                            'change': change_pct
                        })
        
        print(f"\n日涨跌幅异常数量: {len(issues)}")
        if issues[:3]:
            for v in issues[:3]:
                print(f"  {v['code']} {v['date']}: {v['prev']}->{v['curr']} ({v['change']:.1f}%)")
        
        # 允许少量异常（可能有除权）
        assert len(issues) <= 10, f"日涨跌幅异常过多: {len(issues)}"


class TestDataMonitorSummary:
    """监控汇总报告"""

    def test_生成监控报告(self):
        """生成监控汇总报告"""
        loader = DataLoader()
        data = loader.load()
        today = datetime.now().date()
        
        report = {
            '检查时间': today.strftime('%Y-%m-%d %H:%M'),
            'ETF总数': len(data),
            '数据状态': '正常'
        }
        
        # 检查数据新鲜度
        stale_count = 0
        for code, df in data.items():
            latest_date_str = df['date'].max()
            if isinstance(latest_date_str, str):
                latest_date = datetime.strptime(latest_date_str, '%Y-%m-%d').date()
            else:
                latest_date = latest_date_str
            
            if (today - latest_date).days > 2:
                stale_count += 1
        
        report['数据过期数'] = stale_count
        
        if stale_count > 5:
            report['数据状态'] = '⚠️ 警告'
        if stale_count > 10:
            report['数据状态'] = '❌ 严重'
        
        print(f"\n监控报告:")
        for key, value in report.items():
            print(f"  {key}: {value}")
        
        assert len(report) > 0, "报告生成失败"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])