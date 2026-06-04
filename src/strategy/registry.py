#!/usr/bin/env python3
"""
策略注册中心（US-003, US-016 v3 新增）

按业界最佳实践:
- 1 模型 = N 策略 (Lopez de Prado 2018)
- 策略生命周期 (Bahnsen 2015)
- 独立仓位管理 (Tharp 2006)

设计原则:
- 策略注册到 dict + SQLite
- 每个 StrategyMeta 含 meta (created/retired/regimes) + params + risk_limits
- 持久化到 strategies 表

使用:
    from src.strategy.registry import StrategyRegistry, StrategyMeta

    registry = StrategyRegistry()
    meta = StrategyMeta(code='trend_following', name='趋势跟踪', ...)
    registry.register(meta)
    active = registry.get_active(regime='trend_up')
"""
import json
import os
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any

from src.constants import DB_PATH


@dataclass
class StrategyMeta:
    """策略元信息（注册中心的数据类）"""
    code: str                                  # 策略代码（唯一）
    name: str                                  # 策略名称
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    retired_at: Optional[str] = None           # 退役时间
    applicable_regimes: List[str] = field(default_factory=list)  # 适用市态
    params: Dict[str, Any] = field(default_factory=dict)         # 策略参数
    risk_limits: Dict[str, Any] = field(default_factory=dict)    # 风控限制

    def to_dict(self) -> dict:
        d = asdict(self)
        # list/dict 转 JSON 字符串 (SQLite 存储)
        d['applicable_regimes'] = json.dumps(d['applicable_regimes'], ensure_ascii=False)
        d['params'] = json.dumps(d['params'], ensure_ascii=False)
        d['risk_limits'] = json.dumps(d['risk_limits'], ensure_ascii=False)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'StrategyMeta':
        d = dict(d)
        d['applicable_regimes'] = json.loads(d.get('applicable_regimes', '[]'))
        d['params'] = json.loads(d.get('params', '{}'))
        d['risk_limits'] = json.loads(d.get('risk_limits', '{}'))
        return cls(**d)

    def is_active(self) -> bool:
        """是否活跃（未退役）"""
        return self.retired_at is None

    def applies_to(self, regime: str) -> bool:
        """是否适用于指定市态"""
        return regime in self.applicable_regimes


class StrategyRegistry:
    """策略注册中心（dict + SQLite 持久化）"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DB_PATH
        self._registry: Dict[str, StrategyMeta] = {}
        self._ensure_table()
        self._load_from_db()

    def _ensure_table(self):
        """确保 strategies 表存在"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS strategies (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    retired_at TEXT,
                    applicable_regimes TEXT,
                    params TEXT,
                    risk_limits TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def _load_from_db(self):
        """从 DB 加载到内存"""
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute("SELECT code, name, created_at, retired_at, applicable_regimes, params, risk_limits FROM strategies").fetchall()
            for row in rows:
                meta = StrategyMeta.from_dict({
                    'code': row[0], 'name': row[1], 'created_at': row[2],
                    'retired_at': row[3], 'applicable_regimes': row[4],
                    'params': row[5], 'risk_limits': row[6],
                })
                self._registry[row[0]] = meta
        finally:
            conn.close()

    def register(self, meta: StrategyMeta) -> bool:
        """
        注册策略（已存在则更新）

        Returns:
            True 成功
        """
        if not meta.code or not meta.name:
            raise ValueError("StrategyMeta.code 和 name 必填")
        self._registry[meta.code] = meta
        conn = sqlite3.connect(self.db_path)
        try:
            d = meta.to_dict()
            conn.execute("""
                INSERT OR REPLACE INTO strategies
                (code, name, created_at, retired_at, applicable_regimes, params, risk_limits)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (d['code'], d['name'], d['created_at'], d['retired_at'],
                  d['applicable_regimes'], d['params'], d['risk_limits']))
            conn.commit()
            return True
        finally:
            conn.close()

    def deregister(self, code: str) -> bool:
        """
        退役策略（标记 retired_at）

        Returns:
            True 成功, False 不存在
        """
        if code not in self._registry:
            return False
        self._registry[code].retired_at = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE strategies SET retired_at = ? WHERE code = ?",
                (self._registry[code].retired_at, code)
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def get(self, code: str) -> Optional[StrategyMeta]:
        """获取策略元信息"""
        return self._registry.get(code)

    def get_active(self) -> List[StrategyMeta]:
        """获取所有活跃策略"""
        return [m for m in self._registry.values() if m.is_active()]

    def get_by_regime(self, regime: str) -> List[StrategyMeta]:
        """获取适用于指定市态的活跃策略"""
        return [m for m in self.get_active() if m.applies_to(regime)]

    def list_all(self) -> List[StrategyMeta]:
        """列出所有策略（含退役）"""
        return list(self._registry.values())

    def __len__(self):
        return len(self._registry)

    def __contains__(self, code):
        return code in self._registry
