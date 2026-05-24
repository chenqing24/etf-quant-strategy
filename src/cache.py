#!/usr/bin/env python3
"""数据缓存管理"""
import os
import pickle
import hashlib
import pandas as pd
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime


class CacheManager:
    """缓存管理器"""
    
    def __init__(self, cache_dir: str = '.cache'):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 缓存元数据
        self.meta_file = self.cache_dir / 'meta.pkl'
        self._meta: Dict = self._load_meta()
    
    def _load_meta(self) -> Dict:
        """加载缓存元数据"""
        if self.meta_file.exists():
            try:
                with open(self.meta_file, 'rb') as f:
                    return pickle.load(f)
            except:
                return {}
        return {}
    
    def _save_meta(self):
        """保存缓存元数据"""
        with open(self.meta_file, 'wb') as f:
            pickle.dump(self._meta, f)
    
    def _get_cache_key(self, name: str, *args) -> str:
        """生成缓存键"""
        key_str = f"{name}_{'_'.join(str(a) for a in args)}"
        return hashlib.md5(key_str.encode()).hexdigest()[:16]
    
    def _get_cache_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{key}.pkl"
    
    def get(self, name: str, *args, **kwargs) -> Optional[any]:
        """获取缓存
        
        Args:
            name: 缓存名称
            *args: 缓存参数
            **kwargs: 额外参数 (如max_age_days)
            
        Returns:
            缓存数据，如果不存在或过期返回None
        """
        key = self._get_cache_key(name, *args)
        cache_path = self._get_cache_path(key)
        
        if not cache_path.exists():
            return None
        
        # 检查过期
        max_age_days = kwargs.get('max_age_days', 7)
        if name in self._meta:
            cache_time = self._meta[key].get('time', 0)
            age_days = (datetime.now().timestamp() - cache_time) / 86400
            if age_days > max_age_days:
                # 过期删除
                cache_path.unlink()
                del self._meta[key]
                return None
        
        try:
            with open(cache_path, 'rb') as f:
                data = pickle.load(f)
            return data
        except:
            return None
    
    def set(self, name: str, data: any, *args):
        """设置缓存
        
        Args:
            name: 缓存名称
            data: 要缓存的数据
            *args: 缓存参数
        """
        key = self._get_cache_key(name, *args)
        cache_path = self._get_cache_path(key)
        
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
            
            # 更新元数据
            self._meta[key] = {
                'name': name,
                'args': args,
                'time': datetime.now().timestamp(),
            }
            self._save_meta()
        except Exception as e:
            print(f"缓存写入失败: {e}")
    
    def clear(self, name: str = None):
        """清除缓存
        
        Args:
            name: 缓存名称，为None时清除所有
        """
        if name is None:
            # 清除所有
            for f in self.cache_dir.glob('*.pkl'):
                if f != self.meta_file:
                    f.unlink()
            self._meta = {}
            self._save_meta()
        else:
            # 清除指定名称的缓存
            keys_to_delete = [k for k, v in self._meta.items() if v.get('name') == name]
            for key in keys_to_delete:
                cache_path = self._get_cache_path(key)
                if cache_path.exists():
                    cache_path.unlink()
                del self._meta[key]
            self._save_meta()
    
    def get_stats(self) -> Dict:
        """获取缓存统计"""
        total_size = sum(f.stat().st_size for f in self.cache_dir.glob('*.pkl') if f != self.meta_file)
        return {
            'cache_count': len(self._meta),
            'total_size_mb': round(total_size / 1024 / 1024, 2),
            'cache_dir': str(self.cache_dir),
        }


# 全局缓存实例
_global_cache: Optional[CacheManager] = None


def get_cache(cache_dir: str = '.cache') -> CacheManager:
    """获取全局缓存实例"""
    global _global_cache
    if _global_cache is None:
        _global_cache = CacheManager(cache_dir)
    return _global_cache


# 便捷装饰器
def cached(name: str, max_age_days: int = 7):
    """缓存装饰器
    
    Usage:
        @cached('my_data', max_age_days=1)
        def load_data():
            return heavy_computation()
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            cache = get_cache()
            cached_data = cache.get(name, *args, max_age_days=max_age_days)
            
            if cached_data is not None:
                return cached_data
            
            # 计算并缓存
            result = func(*args, **kwargs)
            cache.set(name, result, *args)
            return result
        return wrapper
    return decorator


def test_cache():
    """测试缓存"""
    cache = CacheManager('.cache/test')
    
    # 测试写入
    test_data = {'value': 123, 'list': [1,2,3]}
    cache.set('test_key', test_data, 'param1')
    
    # 测试读取
    retrieved = cache.get('test_key', 'param1')
    assert retrieved == test_data, "缓存读取失败"
    
    # 测试key不存在
    missing = cache.get('nonexistent')
    assert missing is None, "不应返回不存在的缓存"
    
    # 统计
    stats = cache.get_stats()
    print(f"✓ 缓存测试通过: {stats}")
    
    # 清理测试
    cache.clear()
    
    return True


if __name__ == '__main__':
    test_cache()


__all__ = ['CacheManager', 'get_cache', 'cached', 'test_cache']