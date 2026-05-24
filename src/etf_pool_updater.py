#!/usr/bin/env python3
"""ETF股票池更新器 - 每月运行一次"""
import requests
import pandas as pd
from datetime import datetime
from typing import Dict, List, Set
import json
import os


class ETFListUpdater:
    """ETF股票池更新器
    
    每月运行一次，更新ETF池
    基于成交额和规模筛选活跃ETF
    """
    
    # 常用ETF代码模板 (会被动态更新)
    BASE_ETFS = [
        # 宽基指数 - 可用
        ('510300', '沪深300', '宽基'),
        ('510500', '中证500', '宽基'),
        ('159919', '创业板', '宽基'),
        ('159915', '创业板50', '宽基'),
        ('159901', '深证100', '宽基'),
        ('159905', '中证100', '宽基'),
        ('510010', '180ETF', '宽基'),
        
        # 红利ETF - 排除 (7因子不适用)
        ('510880', '红利ETF', '红利'),
        
        # 金融 - 排除 (强周期)
        ('512880', '证券ETF', '金融'),
        ('512170', '券商ETF', '金融'),
        ('512200', '银行ETF', '金融'),
        ('512690', '保险ETF', '金融'),
        ('159815', '金融ETF', '金融'),
        
        # 消费
        ('159928', '食品饮料', '消费'),
        ('159825', '消费ETF', '消费'),
        ('510630', '消费ETF', '消费'),
        
        # 医药
        ('512010', '医药ETF', '医药'),
        ('512500', '医药卫生', '医药'),
        ('159838', '创新药', '医药'),
        ('159952', '医药ETF', '医药'),
        
        # 科技 - 可用
        ('159997', '电子ETF', '科技'),
        ('159995', '计算机', '科技'),
        ('512760', '半导体', '科技'),
        ('159801', '芯片ETF', '科技'),
        ('159823', '5G通信', '科技'),
        ('515050', '科技ETF', '科技'),
        
        # 新能源
        ('159857', '光伏ETF', '新能源'),
        ('516160', '新能源车', '新能源'),
        ('159806', '新能源车', '新能源'),
        
        # 周期
        ('159942', '有色金属', '周期'),
        ('510050', '煤炭ETF', '周期'),
        
        # 军工
        ('512660', '军工ETF', '军工'),
        
        # 港股 - 排除 (汇率+境外市场)
        ('159920', '恒生ETF', '港股'),
        ('159867', '港股通50', '港股'),
        ('513360', '港股ETF', '港股'),
        ('513050', '中证100', '港股'),
        
        # 商品 - 排除 (受商品价格主导)
        ('518880', '黄金ETF', '商品'),
        ('159934', '黄金', '商品'),
        ('518800', '黄金', '商品'),
        
        # 债券 - 排除 (与股票走势不同)
        ('511010', '国债ETF', '债券'),
        ('511880', '可转债', '债券'),
        
        # 新兴产业
        ('516050', '科创成长', '科创'),
        ('159577', '创新产业', '科创'),
        ('515000', '工业ETF', '制造'),
        ('513100', '稀土产业', '资源'),
    ]
    
    def __init__(self, pool_file: str = 'etf_pool.json'):
        self.pool_file = pool_file
        self._ensure_file()
    
    def _ensure_file(self):
        """确保池文件存在"""
        if not os.path.exists(self.pool_file):
            self._save_pool(self.BASE_ETFS)
    
    def _save_pool(self, etfs: List[tuple]):
        """保存ETF池"""
        pool = {
            'updated': datetime.now().strftime('%Y-%m-%d'),
            'etfs': [
                {'code': code, 'name': name, 'category': cat}
                for code, name, cat in etfs
            ]
        }
        with open(self.pool_file, 'w', encoding='utf-8') as f:
            json.dump(pool, f, indent=2, ensure_ascii=False)
    
    def load_pool(self) -> List[tuple]:
        """加载ETF池"""
        with open(self.pool_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [
                (e['code'], e['name'], e['category'])
                for e in data['etfs']
            ]
    
    def get_pool_size(self) -> int:
        """获取池中ETF数量"""
        pool = self.load_pool()
        return len(pool)
    
    def get_by_category(self, category: str) -> List[tuple]:
        """按行业获取ETF"""
        pool = self.load_pool()
        return [(c, n, c) for c, n, c in pool if c == category]
    
    def get_all_codes(self) -> List[str]:
        """获取所有ETF代码"""
        pool = self.load_pool()
        return [e[0] for e in pool]
    
    def check_update_needed(self) -> bool:
        """检查是否需要更新"""
        if not os.path.exists(self.pool_file):
            return True
        
        with open(self.pool_file, 'r') as f:
            data = json.load(f)
            last_update = datetime.strptime(data['updated'], '%Y-%m-%d')
            days_since = (datetime.now() - last_update).days
            
            # 超过14天需要更新 (每2周)
            return days_since >= 14
    
    def update_pool_from_api(self) -> Dict:
        """从API更新ETF池 (模拟)
        
        实际生产中应调用天天基金或其他API获取ETF列表
        这里简化处理，返回当前池信息
        """
        print("\n" + "="*50)
        print("📡 正在更新ETF股票池...")
        print("="*50)
        
        # 模拟API获取
        # 实际应调用: 天天基金ETF列表接口
        
        pool = self.load_pool()
        
        # 分析当前池
        categories = {}
        for code, name, cat in pool:
            categories[cat] = categories.get(cat, 0) + 1
        
        print(f"\n当前ETF池统计:")
        print(f"  总数量: {len(pool)}只")
        for cat, count in categories.items():
            print(f"  {cat}: {count}只")
        
        # 检查流动性 (简化: 检查是否有最近数据)
        import json
        with open(self.pool_file, 'r') as f:
            data = json.load(f)
        last_update = data.get('updated', '未知')
        print(f"\n最后更新: {last_update}")
        
        # 建议添加的新ETF (可以扩展)
        suggestions = self._get_suggestions()
        
        return {
            'total': len(pool),
            'categories': categories,
            'suggestions': suggestions,
            'last_update': datetime.now().strftime('%Y-%m-%d')
        }
    
    def _get_suggestions(self) -> List[Dict]:
        """获取建议添加的ETF"""
        # 实际生产中应根据市场热点、成交量等推荐
        # 这里返回示例
        return [
            {'code': '159899', 'name': '科创50', 'reason': '科创板核心'},
            {'code': '513050', 'name': '中证100', 'reason': '大盘价值'},
        ]
    
    def add_etf(self, code: str, name: str, category: str):
        """添加ETF到池"""
        pool = self.load_pool()
        
        # 检查是否已存在
        if any(e[0] == code for e in pool):
            print(f"  {code} 已在池中")
            return
        
        pool.append((code, name, category))
        self._save_pool(pool)
        print(f"  ✓ 已添加 {code} {name}")
    
    def remove_etf(self, code: str):
        """从池中移除ETF"""
        pool = self.load_pool()
        pool = [e for e in pool if e[0] != code]
        self._save_pool(pool)
        print(f"  ✓ 已移除 {code}")
    
    def run_monthly_update(self):
        """执行月度更新"""
        print("\n" + "="*50)
        print("🗓️  月度ETF池更新")
        print("="*50)
        
        stats = self.update_pool_from_api()
        
        print(f"\n建议操作:")
        if self.check_update_needed():
            print("  - 建议执行完整更新 (超过25天)")
        
        for s in stats['suggestions']:
            print(f"  - 建议添加: {s['code']} {s['name']} ({s['reason']})")
        
        print(f"\n下次更新建议: 每月1日")
        
        return stats
    
    def get_tencent_codes(self) -> List[str]:
        """获取腾讯API格式的代码列表"""
        pool = self.load_pool()
        codes = []
        for code, _, _ in pool:
            # 添加sh前缀
            codes.append(f'sh{code}')
        return codes
    
    def generate_report(self) -> str:
        """生成更新报告"""
        pool = self.load_pool()
        categories = {}
        for code, name, cat in pool:
            categories[cat] = categories.get(cat, 0) + 1
        
        last_update = datetime.now().strftime('%Y-%m-%d')
        
        report = f"""======================================================================
ETF股票池更新报告
======================================================================

【更新信息】
更新日期: {last_update}
ETF总数: {len(pool)}只

【分类统计】
"""
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            report += f"  {cat}: {count}只\n"
        
        report += f"""
【完整列表】
"""
        for code, name, cat in pool:
            report += f"  {code} {name} ({cat})\n"
        
        report += f"""
【建议关注】
  - 科创50 (159899): 科创板核心指数
  - 中证A500: 新一代宽基指数

======================================================================
"""
        return report
    
    def save_report(self, path: str = None):
        """保存报告到文件"""
        if path is None:
            path = f"etf_reports/pool_update_{datetime.now().strftime('%Y%m%d')}.txt"
        
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        
        report = self.generate_report()
        with open(path, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"  报告已保存: {path}")
        return path
    
    def send_to_dingtalk(self):
        """发送简化的钉钉通知"""
        pool = self.load_pool()
        
        # 获取分类统计
        categories = {}
        for code, name, cat in pool:
            categories[cat] = categories.get(cat, 0) + 1
        cat_summary = " ".join([f"{k}:{v}" for k, v in sorted(categories.items(), key=lambda x: -x[1])])
        
        # 计算每个ETF的评分
        scored_etfs = self._get_etf_scores(pool)
        
        # 发送头部
        header_msg = f"""📊 ETF股票池更新

🗓️ 更新日期: {datetime.now().strftime('%Y-%m-%d')}
📈 ETF总数: {len(pool)}只

📋 分类统计:
{cat_summary}"""
        
        self._send_dingtalk(header_msg)
        print("  头部已发送")
        
        # 发送ETF列表 (每条消息一个ETF)
        import threading
        import time
        
        def send_async(item):
            line = f"{item['score']}分 {item['code']}\n{item['name']}"
            self._send_dingtalk(line)
            time.sleep(0.3)  # 避免发送过快
        
        threads = []
        for item in scored_etfs:
            t = threading.Thread(target=send_async, args=(item,))
            t.start()
            threads.append(t)
        
        for t in threads:
            t.join(timeout=30)
        
        print("  ✓ 已推送钉钉 (含评分)")
    
    def _get_etf_scores(self, pool: List) -> List[Dict]:
        """获取ETF评分"""
        from .indicator import Indicator
        from .data_loader import DataLoader
        
        scored_etfs = []
        loader = DataLoader()
        
        for code, name, cat in pool:
            try:
                df = loader.load_etf_data(code)
                if df is None or len(df) < 120:
                    scored_etfs.append({'code': code, 'name': name, 'cat': cat, 'score': 0})
                    continue
                
                # 计算指标
                df_ind = Indicator.calculate(df)
                latest_date = df_ind['date'].iloc[-1]
                latest = df_ind[df_ind['date'] == latest_date].iloc[0]
                
                # 7因子打分
                from .selector import ETFSelector
                selector = ETFSelector()
                score, reasons = selector.score_with_ic(df_ind, latest_date)
                
                scored_etfs.append({
                    'code': code,
                    'name': name,
                    'cat': cat,
                    'score': score,
                    'reasons': reasons
                })
            except Exception:
                scored_etfs.append({'code': code, 'name': name, 'cat': cat, 'score': 0})
        
        # 按评分降序排序
        scored_etfs.sort(key=lambda x: -x['score'])
        return scored_etfs
    
    def _send_dingtalk(self, msg: str, session: dict = None):
        """发送钉钉消息"""
        import subprocess, json
        
        if session is None:
            try:
                result = subprocess.run(
                    ['qwenpaw', 'chats', 'list', '--channel', 'dingtalk'],
                    capture_output=True, text=True, timeout=15
                )
                sessions = json.loads(result.stdout)
                if sessions:
                    session = sessions[0]
            except:
                return
        
        if session:
            subprocess.run([
                'qwenpaw', 'channels', 'send',
                '--agent-id', 'default',
                '--channel', 'dingtalk',
                '--target-user', session.get('user_id', ''),
                '--target-session', session.get('session_id', ''),
                '--text', msg
            ], timeout=20)
    
    def send_to_dingtalk(self):
        """发送简化的钉钉通知"""
        pool = self.load_pool()
        
        # 获取分类统计
        categories = {}
        for code, name, cat in pool:
            categories[cat] = categories.get(cat, 0) + 1
        cat_summary = " ".join([f"{k}:{v}" for k, v in sorted(categories.items(), key=lambda x: -x[1])])
        
        # 计算每个ETF的评分
        scored_etfs = self._get_etf_scores(pool)
        
        # 先获取session（复用）
        import subprocess, json
        session = None
        try:
            result = subprocess.run(
                ['qwenpaw', 'chats', 'list', '--channel', 'dingtalk'],
                capture_output=True, text=True, timeout=15
            )
            sessions = json.loads(result.stdout)
            if sessions:
                session = sessions[0]
        except:
            pass
        
        # 发送头部
        header_msg = f"""📊 ETF股票池更新

🗓️ 更新日期: {datetime.now().strftime('%Y-%m-%d')}
📈 ETF总数: {len(pool)}只

📋 分类统计:
{cat_summary}"""
        
        self._send_dingtalk(header_msg, session)
        print("  头部已发送")
        
        # 发送ETF列表 (每批5个换行显示)
        batch_size = 5
        for i in range(0, len(scored_etfs), batch_size):
            batch = scored_etfs[i:i+batch_size]
            lines = [f"{item['score']}分 {item['code']} {item['name']}" for item in batch]
            msg_batch = '\n'.join(lines)
            self._send_dingtalk(msg_batch, session)
            import time
            time.sleep(0.3)
        
        print("  ✓ 已推送钉钉 (含评分)")
    
    def run_full_update(self):
        """执行完整更新流程"""
        print("\n" + "="*50)
        print("📊 ETF股票池更新")
        print("="*50)
        
        # 1. 检查更新状态
        stats = self.update_pool_from_api()
        
        # 2. 保存报告
        report_file = self.save_report()
        
        # 3. 钉钉推送
        self.send_to_dingtalk()
        
        return stats


def test_updater():
    """测试"""
    updater = ETFListUpdater('etf_pool.json')
    
    print("当前池大小:", updater.get_pool_size())
    print("需要更新:", updater.check_update_needed())
    
    updater.run_monthly_update()
    
    print("\n所有代码:", updater.get_tencent_codes()[:5], "...")


if __name__ == '__main__':
    test_updater()


__all__ = ['ETFListUpdater', 'test_updater']