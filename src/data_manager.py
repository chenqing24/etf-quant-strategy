#!/usr/bin/env python3
"""
热冷数据分离管理器
=====================
数据生命周期管理：
- 热数据层 (hot/): 今日实时价格，JSON格式含时间戳，随时间变动
- 冷数据层 (cold/): 收盘确认数据，CSV格式，T日23:00后归档

生命周期阶段：
1. TRADING_HOUR 盘中更新 - 热数据层持续更新
2. CLOSING确认 - 15:00-15:30收盘验证
3. MIGRATED归档 - 15:30后热数据迁移至冷数据层

使用方式:
    from src.data_manager import DataFacade
    
    facade = DataFacade('etf_data_live')
    
    # 获取今日实时价格
    hot_data = facade.hot.get('510300')
    
    # 更新热数据
    facade.hot.set('510300', {'price': 3.85, 'change': 0.5})
    
    # 合并热冷数据（评分时使用）
    merged = facade.get_merged_data('510300')
    
    # 收盘后迁移
    facade.migrate()
    
    # 查看生命周期状态
    lifecycle = facade.get_lifecycle_info()
"""

import json
import os
import csv
from datetime import datetime, time
from typing import Dict, Optional, Any
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum


class LifecycleStage(Enum):
    """数据生命周期阶段"""
    UNKNOWN = "unknown"
    TRADING_HOUR = "trading"      # 盘中更新中
    CLOSING = "closing"           # 收盘确认中 (15:00-15:30)
    MIGRATED = "migrated"         # 已归档至冷数据层
    MIGRATING = "migrating"       # 迁移中


@dataclass
class HotDataRecord:
    """热数据记录结构"""
    code: str           # ETF代码
    price: float       # 当前价格
    change_pct: float  # 涨跌幅%
    volume: float      # 成交量
    timestamp: str      # 更新时间戳 ISO格式
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'HotDataRecord':
        return cls(**data)


class HotDataManager:
    """热数据管理器
    
    职责：
    - 存储今日实时价格数据
    - JSON格式，含时间戳
    - 盘中持续更新，收盘后清空
    """
    
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.hot_dir = self.base_dir / 'hot'
        self.hot_dir.mkdir(parents=True, exist_ok=True)
        
        # 热数据缓存（内存）
        self._cache: Dict[str, HotDataRecord] = {}
        self._load_cache()
    
    def _load_cache(self):
        """从磁盘加载热数据到内存缓存"""
        if not self.hot_dir.exists():
            return
            
        for f in self.hot_dir.glob('*.json'):
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                    record = HotDataRecord.from_dict(data)
                    self._cache[record.code] = record
            except Exception:
                pass
    
    def _get_file_path(self, code: str) -> Path:
        return self.hot_dir / f"{code}.json"
    
    def get(self, code: str) -> Optional[HotDataRecord]:
        """获取热数据
        
        Args:
            code: ETF代码 (如 '510300')
            
        Returns:
            HotDataRecord 或 None
        """
        return self._cache.get(code)
    
    def set(self, code: str, data: Dict[str, Any]):
        """更新热数据
        
        Args:
            code: ETF代码
            data: 包含 price, change_pct, volume 等字段
        """
        record = HotDataRecord(
            code=code,
            price=float(data.get('price', 0)),
            change_pct=float(data.get('change_pct', 0)),
            volume=float(data.get('volume', 0)),
            timestamp=datetime.now().isoformat()
        )
        
        self._cache[code] = record
        
        # 持久化到磁盘
        file_path = self._get_file_path(code)
        with open(file_path, 'w', encoding='utf-8') as fp:
            json.dump(record.to_dict(), fp, ensure_ascii=False, indent=2)
    
    def get_all(self) -> Dict[str, HotDataRecord]:
        """获取所有热数据"""
        return dict(self._cache)
    
    def clear(self):
        """清空热数据（收盘后调用）
        
        将数据迁移到冷数据层后清空热数据目录
        """
        # 备份后清空
        if self.hot_dir.exists():
            for f in self.hot_dir.glob('*.json'):
                try:
                    os.remove(f)
                except Exception:
                    pass
        
        self._cache.clear()
    
    def count(self) -> int:
        """热数据条数"""
        return len(self._cache)


class ColdDataManager:
    """冷数据管理器
    
    职责：
    - 存储收盘确认的历史数据
    - CSV格式，每日归档
    - 用于历史回测和分析
    """
    
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.cold_dir = self.base_dir / 'cold'
        self.cold_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_file_path(self, code: str) -> Path:
        return self.cold_dir / f"{code}.csv"
    
    def get(self, code: str) -> Optional[Dict[str, Any]]:
        """获取冷数据
        
        Args:
            code: ETF代码
            
        Returns:
            包含 date, open, high, low, close, volume 的字典列表
        """
        file_path = self._get_file_path(code)
        if not file_path.exists():
            return None
        
        records = []
        with open(file_path, 'r', encoding='utf-8') as fp:
            reader = csv.DictReader(fp)
            for row in reader:
                records.append(row)
        
        return records
    
    def get_latest(self, code: str) -> Optional[Dict[str, Any]]:
        """获取最新一条冷数据"""
        records = self.get(code)
        return records[-1] if records else None
    
    def append(self, code: str, data: Dict[str, Any]):
        """追加冷数据（收盘归档时调用）
        
        Args:
            code: ETF代码
            data: 包含 date, open, high, low, close, volume
        """
        file_path = self._get_file_path(code)
        
        # 确保目录存在
        self.cold_dir.mkdir(parents=True, exist_ok=True)
        
        # 检查是否已有该日期数据
        new_date = data.get('date')
        if new_date:
            existing_dates = self._get_dates(code)
            if new_date in existing_dates:
                # 更新而非追加
                self._update_record(code, data)
                return
        
        # 追加写入
        is_new_file = not file_path.exists()
        
        with open(file_path, 'a', encoding='utf-8', newline='') as fp:
            writer = csv.DictWriter(fp, fieldnames=['date', 'open', 'high', 'low', 'close', 'volume'])
            
            if is_new_file:
                writer.writeheader()
            
            writer.writerow(data)
    
    def _get_dates(self, code: str) -> set:
        """获取已有日期集合"""
        file_path = self._get_file_path(code)
        if not file_path.exists():
            return set()
        
        dates = set()
        with open(file_path, 'r', encoding='utf-8') as fp:
            reader = csv.DictReader(fp)
            for row in reader:
                dates.add(row.get('date'))
        
        return dates
    
    def _update_record(self, code: str, data: Dict[str, Any]):
        """更新指定日期的记录"""
        file_path = self._get_file_path(code)
        
        # 读取所有记录
        records = []
        with open(file_path, 'r', encoding='utf-8') as fp:
            reader = csv.DictReader(fp)
            records = list(reader)
        
        # 更新或追加
        target_date = data.get('date')
        updated = False
        
        for i, record in enumerate(records):
            if record.get('date') == target_date:
                records[i] = data
                updated = True
                break
        
        if not updated:
            records.append(data)
        
        # 按日期排序后写回
        records.sort(key=lambda x: x.get('date', ''))
        
        with open(file_path, 'w', encoding='utf-8', newline='') as fp:
            writer = csv.DictWriter(fp, fieldnames=['date', 'open', 'high', 'low', 'close', 'volume'])
            writer.writeheader()
            writer.writerows(records)
    
    def exists(self, code: str) -> bool:
        """检查冷数据是否存在"""
        return self._get_file_path(code).exists()


class DataFacade:
    """数据访问统一接口
    
    合并热冷数据层，提供统一的数据访问接口
    """
    
    # 交易时段定义
    TRADING_START = time(9, 30)
    TRADING_END = time(15, 0)
    MIGRATION_TIME = time(15, 30)
    
    def __init__(self, base_dir: str = 'etf_data_live'):
        self.base_dir = Path(base_dir)
        self.hot = HotDataManager(base_dir)
        self.cold = ColdDataManager(base_dir)
        self._lifecycle_stage = self._detect_lifecycle_stage()
    
    def _detect_lifecycle_stage(self) -> LifecycleStage:
        """检测当前生命周期阶段"""
        now = datetime.now()
        current_time = now.time()
        
        # 工作日判断
        if now.weekday() >= 5:  # 周六日
            return LifecycleStage.TRADING_HOUR
        
        # 交易时段判断
        if current_time < self.TRADING_START:
            return LifecycleStage.TRADING_HOUR
        elif self.TRADING_START <= current_time < self.TRADING_END:
            return LifecycleStage.TRADING_HOUR
        elif self.TRADING_END <= current_time < self.MIGRATION_TIME:
            return LifecycleStage.CLOSING
        elif current_time >= self.MIGRATION_TIME:
            return LifecycleStage.MIGRATED
        else:
            return LifecycleStage.UNKNOWN
    
    def get_merged_data(self, code: str) -> Dict[str, Any]:
        """获取合并后的数据（热数据覆盖冷数据对应字段）
        
        合并逻辑：
        - 热数据存在时，用热数据覆盖冷数据的价格/涨跌幅/成交量
        - 热数据不存在时，仅使用冷数据
        - 完全不存在时返回空字典
        
        Args:
            code: ETF代码
            
        Returns:
            合并后的数据字典
        """
        hot_record = self.hot.get(code)
        cold_records = self.cold.get(code)
        
        result = {}
        
        # 先取冷数据作为基础
        if cold_records and len(cold_records) > 0:
            latest_cold = cold_records[-1]
            result = {
                'date': latest_cold.get('date', ''),
                'open': float(latest_cold.get('open', 0)),
                'high': float(latest_cold.get('high', 0)),
                'low': float(latest_cold.get('low', 0)),
                'close': float(latest_cold.get('close', 0)),
                'volume': float(latest_cold.get('volume', 0)),
            }
        else:
            result = {
                'date': '',
                'open': 0,
                'high': 0,
                'low': 0,
                'close': 0,
                'volume': 0,
            }
        
        # 热数据覆盖（只覆盖价格相关字段）
        if hot_record:
            result.update({
                'price': hot_record.price,
                'change_pct': hot_record.change_pct,
                'hot_timestamp': hot_record.timestamp,
                # 如果热数据有成交量，用热数据
                'volume': hot_record.volume if hot_record.volume > 0 else result['volume'],
            })
            # 收盘价用热数据价格
            if hot_record.price > 0:
                result['close'] = hot_record.price
        
        return result
    
    def migrate(self) -> Dict[str, str]:
        """热数据迁移至冷数据
        
        执行步骤：
        1. 检查是否为交易时段后（15:30后）
        2. 遍历热数据目录
        3. 将每条热数据追加/更新到冷数据CSV
        
        Returns:
            {code: status} 迁移结果
        """
        # 检查时间（允许手动触发）
        # if self._lifecycle_stage not in [LifecycleStage.MIGRATED, LifecycleStage.TRADING_HOUR]:
        #     print(f"当前阶段 {self._lifecycle_stage.value} 不允许迁移")
        #     return {}
        
        results = {}
        hot_data = self.hot.get_all()
        
        if not hot_data:
            return {'status': 'no_data'}
        
        for code, record in hot_data.items():
            try:
                # 构建冷数据格式
                cold_record = {
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'open': record.price,  # 使用最新价作为收盘价归档
                    'high': record.price,
                    'low': record.price,
                    'close': record.price,
                    'volume': record.volume,
                }
                
                self.cold.append(code, cold_record)
                results[code] = 'migrated'
                
            except Exception as e:
                results[code] = f'error: {str(e)}'
        
        # 清空热数据
        self.hot.clear()
        
        # 更新生命周期状态
        self._lifecycle_stage = LifecycleStage.MIGRATED
        
        return results
    
    def get_lifecycle_info(self) -> Dict[str, Any]:
        """获取当前数据生命周期阶段信息
        
        Returns:
            {
                'stage': str,          # 当前阶段
                'stage_desc': str,     # 阶段描述
                'hot_count': int,     # 热数据条数
                'next_milestone': str # 下一里程碑
            }
        """
        stage_descriptions = {
            LifecycleStage.UNKNOWN: "状态未知",
            LifecycleStage.TRADING_HOUR: "盘中更新中 - 热数据持续更新",
            LifecycleStage.CLOSING: "收盘确认中 - 等待15:30归档",
            LifecycleStage.MIGRATED: "已归档完成 - 热数据已迁移至冷数据层",
            LifecycleStage.MIGRATING: "迁移中 - 正在处理数据",
        }
        
        next_milestones = {
            LifecycleStage.UNKNOWN: "等待系统初始化",
            LifecycleStage.TRADING_HOUR: "15:00 收盘确认",
            LifecycleStage.CLOSING: "15:30 自动迁移",
            LifecycleStage.MIGRATED: "下一个交易日",
            LifecycleStage.MIGRATING: "迁移完成",
        }
        
        return {
            'stage': self._lifecycle_stage.value,
            'stage_desc': stage_descriptions.get(self._lifecycle_stage, "未知"),
            'hot_count': self.hot.count(),
            'cold_count': len(list(self.cold.cold_dir.glob('*.csv'))) if self.cold.cold_dir.exists() else 0,
            'next_milestone': next_milestones.get(self._lifecycle_stage, "未知"),
            'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
    
    def is_trading_time(self) -> bool:
        """判断当前是否为交易时间"""
        return self._lifecycle_stage in [LifecycleStage.TRADING_HOUR, LifecycleStage.CLOSING]
    
    def sync_from_csv(self, code: str, csv_path: str):
        """从现有CSV文件同步冷数据
        
        Args:
            code: ETF代码
            csv_path: CSV文件路径
        """
        import pandas as pd
        
        if not os.path.exists(csv_path):
            return
        
        df = pd.read_csv(csv_path)
        
        for _, row in df.iterrows():
            self.cold.append(code, {
                'date': row['date'],
                'open': row['open'],
                'high': row['high'],
                'low': row['low'],
                'close': row['close'],
                'volume': row['volume'],
            })


def demo():
    """演示热冷数据管理器的使用"""
    print("=== 热冷数据分离管理器演示 ===\n")
    
    facade = DataFacade('etf_data_live')
    
    # 查看生命周期
    lifecycle = facade.get_lifecycle_info()
    print(f"生命周期状态: {lifecycle['stage_desc']}")
    print(f"热数据条数: {lifecycle['hot_count']}")
    print(f"冷数据条数: {lifecycle['cold_count']}\n")
    
    # 模拟更新热数据
    print("模拟写入热数据...")
    facade.hot.set('510300', {
        'price': 3.856,
        'change_pct': 1.23,
        'volume': 1234567,
    })
    
    hot = facade.hot.get('510300')
    if hot:
        print(f"热数据: 代码={hot.code}, 价格={hot.price}, 涨幅={hot.change_pct}%\n")
    
    # 合并数据演示
    print("合并数据演示...")
    merged = facade.get_merged_data('510300')
    print(f"合并结果: {merged}\n")
    
    return facade


if __name__ == '__main__':
    facade = demo()
    
    print("\n=== 生命周期信息 ===")
    info = facade.get_lifecycle_info()
    for k, v in info.items():
        print(f"  {k}: {v}")


__all__ = [
    'HotDataManager',
    'ColdDataManager', 
    'DataFacade',
    'LifecycleStage',
    'HotDataRecord',
]