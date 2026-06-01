#!/usr/bin/env python3
"""
SQLite定期备份脚本

功能：
- 每日备份（收盘后自动执行）
- 每周备份（周五保留）
- 手动备份（重大变更前）
- 自动清理过期备份

使用方式：
    # 每日备份
    python scripts/backup_sqlite.py --type daily
    
    # 每周备份
    python scripts/backup_sqlite.py --type weekly
    
    # 手动备份
    python scripts/backup_sqlite.py --type manual
    
    # 恢复
    python scripts/backup_sqlite.py --restore backup_20260529.db
"""
import os
import sys
import shutil
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.constants import DATA_DIR

# 默认路径
DEFAULT_DB_PATH = os.path.join(DATA_DIR, 'etf.db')
DEFAULT_BACKUP_DIR = os.path.join(os.path.dirname(DATA_DIR), 'etf_backups')


class SQLiteBackupManager:
    """SQLite定期备份管理器"""
    
    # 备份保留策略
    RETENTION = {
        'daily': 7,    # 保留7天
        'weekly': 4,   # 保留4周
        'manual': 10   # 保留10份
    }
    
    def __init__(self, db_path: str = None, backup_dir: str = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.backup_dir = backup_dir or DEFAULT_BACKUP_DIR
        
        # 确保备份目录存在
        Path(self.backup_dir).mkdir(parents=True, exist_ok=True)
    
    def backup(self, backup_type: str = 'daily') -> str:
        """
        执行备份
        
        Args:
            backup_type: 'daily' | 'weekly' | 'manual'
        
        Returns:
            备份文件路径
        """
        if not Path(self.db_path).exists():
            raise FileNotFoundError(f"数据库文件不存在: {self.db_path}")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"etf_backup_{backup_type}_{timestamp}.db"
        backup_path = os.path.join(self.backup_dir, filename)
        
        # 使用 SQLite VACUUM INTO 实现热备份（无需关闭数据库）
        try:
            conn = sqlite3.connect(self.db_path)
            
            # 检查 SQLite 版本（VACUUM INTO 从 3.27.0 开始支持）
            version = sqlite3.sqlite_version
            version_tuple = tuple(map(int, version.split('.')))
            
            if version_tuple < (3, 27, 0):
                # 老版本使用 shutil 备份
                conn.close()
                shutil.copy(self.db_path, backup_path)
            else:
                conn.execute(f"VACUUM INTO '{backup_path}'")
                conn.close()
            
            print(f"✅ 备份成功: {backup_path}")
            
            # 清理过期备份
            self.cleanup_old_backups(backup_type)
            
            return backup_path
            
        except sqlite3.Error as e:
            raise Exception(f"备份失败: {e}")
    
    def restore(self, backup_path: str) -> bool:
        """
        从备份恢复
        
        Args:
            backup_path: 备份文件路径
        
        Returns:
            bool: 恢复是否成功
        """
        if not Path(backup_path).exists():
            raise FileNotFoundError(f"备份文件不存在: {backup_path}")
        
        # 先备份当前数据库（以防万一）
        current_backup = self.backup('manual')
        print(f"⚠️ 当前数据库已备份: {current_backup}")
        
        # 恢复
        try:
            shutil.copy(backup_path, self.db_path)
            print(f"✅ 恢复成功: {self.db_path}")
            return True
        except Exception as e:
            raise Exception(f"恢复失败: {e}")
    
    def cleanup_old_backups(self, backup_type: str):
        """清理过期备份"""
        keep = self.RETENTION.get(backup_type, 1)
        prefix = f"etf_backup_{backup_type}_"
        
        # 获取所有备份文件
        backup_files = []
        for f in Path(self.backup_dir).glob(f"{prefix}*.db"):
            backup_files.append((f.stat().st_mtime, str(f)))
        
        # 按时间排序
        backup_files.sort(reverse=True)
        
        # 删除多余的
        deleted = 0
        for _, filepath in backup_files[keep:]:
            try:
                os.remove(filepath)
                deleted += 1
            except Exception as e:
                print(f"⚠️ 删除备份失败: {filepath}, error: {e}")
        
        if deleted > 0:
            print(f"🗑️ 清理了 {deleted} 个过期备份")
    
    def list_backups(self, backup_type: str = None) -> list:
        """列出所有备份"""
        if backup_type:
            prefix = f"etf_backup_{backup_type}_"
        else:
            prefix = "etf_backup_"
        
        backups = []
        for f in sorted(Path(self.backup_dir).glob(f"{prefix}*.db"), reverse=True):
            stat = f.stat()
            backups.append({
                'filename': f.name,
                'path': str(f),
                'size_mb': round(stat.st_size / 1024 / 1024, 2),
                'created': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return backups
    
    def get_status(self) -> dict:
        """获取备份状态"""
        status = {
            'db_path': self.db_path,
            'db_exists': Path(self.db_path).exists(),
            'backup_dir': self.backup_dir,
            'backups': {}
        }
        
        if status['db_exists']:
            stat = Path(self.db_path).stat()
            status['db_size_mb'] = round(stat.st_size / 1024 / 1024, 2)
            status['db_modified'] = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        
        for backup_type in ['daily', 'weekly', 'manual']:
            backups = self.list_backups(backup_type)
            status['backups'][backup_type] = {
                'count': len(backups),
                'latest': backups[0] if backups else None,
                'retention': self.RETENTION[backup_type]
            }
        
        return status


def main():
    parser = argparse.ArgumentParser(description='SQLite备份管理')
    parser.add_argument('--type', choices=['daily', 'weekly', 'manual'], 
                        default='daily', help='备份类型')
    parser.add_argument('--restore', type=str, help='从备份恢复')
    parser.add_argument('--list', action='store_true', help='列出所有备份')
    parser.add_argument('--status', action='store_true', help='查看备份状态')
    parser.add_argument('--db-path', type=str, help='数据库路径')
    parser.add_argument('--backup-dir', type=str, help='备份目录')
    
    args = parser.parse_args()
    
    manager = SQLiteBackupManager(
        db_path=args.db_path,
        backup_dir=args.backup_dir
    )
    
    if args.restore:
        manager.restore(args.restore)
    elif args.list:
        backups = manager.list_backups()
        print("\n📦 备份列表:")
        for b in backups:
            print(f"  {b['filename']} ({b['size_mb']} MB, {b['created']})")
    elif args.status:
        status = manager.get_status()
        print("\n📊 备份状态:")
        print(f"  数据库: {status['db_path']}")
        print(f"  大小: {status.get('db_size_mb', 'N/A')} MB")
        print(f"  修改时间: {status.get('db_modified', 'N/A')}")
        print(f"  备份目录: {status['backup_dir']}")
        for bt, info in status['backups'].items():
            latest = info['latest']
            print(f"  {bt}: {info['count']} 个备份 (保留{info['retention']}份)")
            if latest:
                print(f"    最新: {latest['filename']} ({latest['size_mb']} MB)")
    else:
        manager.backup(args.type)


if __name__ == '__main__':
    main()