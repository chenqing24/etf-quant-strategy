#!/usr/bin/env python3
"""
ETF池配置
=========
定义市场主流ETF（不含跨境）

结构：
- core: 核心池（规模大、成交高）
- extended: 扩展池（规模中等）

注意：不包含跨境ETF（海外API不纳入本系统）
"""

from typing import Tuple, List

# 采集间隔配置（秒）
INTERVAL_CORE = (1.0, 2.0)      # 核心池：1~2秒
INTERVAL_EXTENDED = (1.5, 3.0)  # 扩展池：1.5~3秒

# 每批数量
BATCH_SIZE_CORE = 20
BATCH_SIZE_EXTENDED = 15

# ETF池定义
ETF_POOLS = {
    'core': {
        'name': '核心池（规模大、成交高）',
        'description': '规模超50亿、日均成交超1亿的ETF',
        'codes': [
            # ===== 宽基指数 =====
            '510300',  # 沪深300ETF华泰柏瑞
            '510500',  # 中证500ETF南方
            '159919',  # 沪深300ETF嘉实
            '159915',  # 创业板ETF易方达
            '510050',  # 上证50ETF华夏
            '588000',  # 科创50ETF
            '159949',  # 科创50ETF华夏
            '588080',  # 科创50ETF工银
            '159788',  # 科创50ETF易方达
            
            # ===== 行业ETF（高成交）=====
            '512760',  # 芯片ETF国泰
            '512880',  # 证券ETF国泰
            '512170',  # 医疗ETF华宝
            '159928',  # 消费ETF汇添富
            '512010',  # 医药ETF易方达
            '159995',  # 芯片ETF华夏
            '515050',  # 通信ETF华夏
            '159801',  # 芯片ETF广发
            '512660',  # 军工ETF国泰
            '159997',  # 电子ETF天弘
            
            # ===== 商品ETF =====
            '518880',  # 黄金ETF华安
            '159934',  # 黄金ETF易方达
            '159330',  # 黄金ETF基金
            '518680',  # 黄金ETF博时
            
            # ===== 跨境（国内交易所）=====
            '159920',  # 恒生ETF华夏
            '159823',  # H股ETF
            
            # ===== 策略ETF =====
            '510310',  # 沪深300ETF易方达（低波）
            '512980',  # 红利ETF
            
            # ===== 更多宽基 =====
            '159692',  # 科创50ETF华安
            '510230',  # 沪深300ETF国泰
            '510100',  # 上证50ETF易方达
            
            # ===== 更多行业 =====
            '512000',  # 券商ETF华宝
            '512400',  # 有色ETF
            '512800',  # 银行ETF
            '159837',  # 电池ETF
            '516110',  # 地产ETF
            '159865',  # 畜牧ETF
            '159867',  # 养殖ETF
            '159825',  # 农业ETF
            '159806',  # 新能源车ETF国泰
            '159857',  # 光伏ETF天弘
            '516160',  # 新能源ETF南方
            '515700',  # 光伏ETF平安
            '159766',  # 旅游ETF
            '159855',  # 教育ETF
            '512690',  # 酒ETF
            '159847',  # 医疗器械ETF
            '159828',  # 医疗ETF
            '515030',  # 新能源车ETF
        ],
        'interval': INTERVAL_CORE,
        'batch_size': BATCH_SIZE_CORE,
    },
    
    'extended': {
        'name': '扩展池（规模中等）',
        'description': '规模10~50亿、日均成交1000万~1亿的ETF',
        'codes': [
            # ===== 科技 =====
            '515000',  # 科技ETF华宝
            '516050',  # 科技龙头ETF工银
            '159812',  # 5GETF
            '515980',  # 人工智能ETF
            '515400',  # 云计算ETF
            
            # ===== 医药 =====
            '512290',  # 生物医药ETF
            '159859',  # 创新药ETF
            '516950',  # 疫苗ETF
            '159858',  # 医疗ETF
            
            # ===== 消费 =====
            '512600',  # 消费ETF
            '159752',  # 消费ETF
            '515650',  # 消费ETF
            
            # ===== 金融 =====
            '512900',  # 证券ETF
            
            # ===== 周期 =====
            '159876',  # 有色ETF
            '516470',  # 农业ETF
            
            # ===== 制造 =====
            '512050',  # 芯片ETF
            '159813',  # 芯片ETF
            '516760',  # 芯片ETF
            
            # ===== 债券 =====
            '511260',  # 国债ETF
            '511030',  # 企债ETF
            '511090',  # 国债ETF
            
            # ===== 策略 =====
            '512890',  # 红利ETF
            '159601',  # 价值ETF
        ],
        'interval': INTERVAL_EXTENDED,
        'batch_size': BATCH_SIZE_EXTENDED,
    },
}

# 合并所有codes
def get_all_codes() -> List[str]:
    """获取所有ETF代码"""
    codes = set()
    for pool in ETF_POOLS.values():
        codes.update(pool['codes'])
    return sorted(list(codes))

def get_codes_by_pool(pool_type: str) -> List[str]:
    """获取指定池的ETF代码"""
    pool = ETF_POOLS.get(pool_type, {})
    return pool.get('codes', [])

def get_pool_config(pool_type: str) -> dict:
    """获取池配置"""
    return ETF_POOLS.get(pool_type, {})

# 验证配置
def validate_config():
    """验证配置完整性"""
    all_codes = get_all_codes()
    
    # 检查重复
    if len(all_codes) != len(set(all_codes)):
        from collections import Counter
        counts = Counter(all_codes)
        duplicates = [c for c, n in counts.items() if n > 1]
        raise ValueError(f"ETF代码重复: {duplicates}")
    
    print(f"✅ 配置验证通过: {len(ETF_POOLS)} 个池, {len(all_codes)} 只ETF")
    for pool_type, pool in ETF_POOLS.items():
        print(f"  - {pool_type}: {len(pool['codes'])} 只, 间隔 {pool['interval']}秒")


if __name__ == '__main__':
    validate_config()
    print(f"\n总计: {len(get_all_codes())} 只ETF")
    print(f"核心池: {len(get_codes_by_pool('core'))} 只")
    print(f"扩展池: {len(get_codes_by_pool('extended'))} 只")