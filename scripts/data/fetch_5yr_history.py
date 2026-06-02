#!/usr/bin/env python3
"""
采集 5 年历史数据（精简版）

数据现状（2026-06-02）：
  ✅ 已有 5 年+: 512880, 512660, 512980, 515650, 515070, 515790
  ❌ 缺早期: 510300, 512400, 512480, 588000, 520900, 512170, 512200, 512800, 515050

数据源：
  腾讯日线 API（ifzq.gtimg.cn）+ 前复权
  备源：AKTools HTTP API (127.0.0.1:8080)
  写入：DataWriter（统一数据入口）

限速：2-5 秒/请求
"""
import sys, time, json, logging, os
from pathlib import Path

_ROOT = Path('/home/qwenpaw/.qwenpaw/workspaces/default/etf_strategy')
sys.path.insert(0, str(_ROOT))
os.chdir(str(_ROOT))

import requests
import pandas as pd
import sqlite3

def get_db_info(code: str) -> tuple:
    """查本地数据范围"""
    conn = sqlite3.connect(str(_ROOT / 'etf_data_live' / 'etf.db'))
    r = conn.execute(
        'SELECT MIN(date), MAX(date), COUNT(*) FROM daily WHERE code=?', (code,)
    ).fetchone()
    conn.close()
    return r[0] or '', r[1] or '', r[2]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# 需要采集的 9 只 ETF
FETCH_ETFS = [
    ('510300', 'sh'),  # 沪深300
    ('512400', 'sh'),  # 有色金属
    ('512480', 'sh'),  # 半导体
    ('588000', 'sh'),  # 科创50
    ('520900', 'sh'),  # 光伏
    ('512170', 'sh'),  # 医疗
    ('512200', 'sh'),  # 房地产
    ('512800', 'sh'),  # 银行
    ('515050', 'sh'),  # 5G
]

TARGET_DATE = '2021-01-01'
MAX_DAYS = 3000  # 腾讯最多约 3000 条（留缓冲）
AKTOOLS_URL = 'http://127.0.0.1:8080/api/public/fund_etf_hist_sina'
TENCENT_URL = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'


def fetch_from_tencent(code: str, days: int = 3000) -> pd.DataFrame:
    """从腾讯 API 获取历史数据（前复权）"""
    params = {
        '_var': 'kline_dayqfq',
        'param': f'{code},day,,,{days},qfq'
    }
    try:
        r = requests.get(TENCENT_URL, params=params, timeout=15)
        text = r.text.replace('kline_dayqfq=', '', 1)
        obj = json.loads(text)
        records_data = obj['data'][code].get('qfqday') or obj['data'][code].get('day', [])
        if not records_data:
            return pd.DataFrame()

        records = []
        for item in records_data:
            records.append({
                'date': item[0],
                'open': float(item[1]),
                'close': float(item[2]),
                'high': float(item[3]),
                'low': float(item[4]),
                'volume': float(item[5]),
            })
        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        return df
    except Exception as e:
        logger.error(f"腾讯失败: {e}")
        return pd.DataFrame()


def fetch_from_aktools(code: str) -> pd.DataFrame:
    """从 AKTools 获取历史数据（备源）"""
    try:
        r = requests.get(AKTOOLS_URL, params={'symbol': code}, timeout=15)
        data = r.json()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        if 'date' not in df.columns:
            return pd.DataFrame()
        df = df.rename(columns={
            'date': 'date',
            'open': 'open',
            'close': 'close',
            'high': 'high',
            'low': 'low',
            'volume': 'volume',
        })
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        for col in ['open', 'close', 'high', 'low', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    except Exception as e:
        logger.error(f"AKTools失败: {e}")
        return pd.DataFrame()


def fetch_with_retry(code: str, days: int = 3000) -> pd.DataFrame:
    """采集主流程：腾讯 → AKTools"""
    # 主源：腾讯
    time.sleep(2.5)
    df = fetch_from_tencent(code, days)
    if len(df) >= 500:  # 有实质数据
        return df

    # 备源：AKTools
    logger.info(f"  腾讯数据不足，尝试 AKTools...")
    time.sleep(6)
    df2 = fetch_from_aktools(code)
    return df2


def main():
    from src.data.writer import DataWriter
    writer = DataWriter()
    results = {}

    logger.info(f"目标: 扩展数据到 {TARGET_DATE} 之前 | 共 {len(FETCH_ETFS)} 只 ETF")
    logger.info("=" * 55)

    for i, (code, prefix) in enumerate(FETCH_ETFS, 1):
        full_code = f'{prefix}{code}'
        local_earliest, local_latest, local_count = get_db_info(code)

        logger.info(f"[{i}/{len(FETCH_ETFS)}] {code} | 本地: {local_earliest} ~ {local_latest} ({local_count}条)")

        if local_earliest and local_earliest <= TARGET_DATE:
            logger.info(f"  ✅ 已有 {TARGET_DATE} 前数据，跳过")
            results[code] = {'status': 'skipped', 'reason': f'已有{local_earliest}'}
            continue

        # 采集
        df = fetch_with_retry(full_code, MAX_DAYS)

        if df.empty:
            logger.error(f"  ❌ 两源均失败")
            results[code] = {'status': 'failed', 'error': '两源均返回空'}
            continue

        # 按日期过滤到 TARGET_DATE
        df = df[df['date'] <= TARGET_DATE].copy()
        logger.info(f"  📥 获取 {len(df)} 条 (截至 {TARGET_DATE})")

        # 去重（防重复）
        df = df.drop_duplicates(subset=['date'], keep='first')

        # 写入
        count = writer.write_daily(code, df)

        # 验证
        new_earliest, new_latest, new_count = get_db_info(code)

        logger.info(f"  ✅ 写入 {count} 条 | 新范围: {new_earliest} ~ {new_latest} ({new_count}条)")

        results[code] = {
            'status': 'success',
            'fetched': len(df),
            'written': count,
            'earliest': new_earliest,
            'latest': new_latest,
        }

    # 汇总
    logger.info("")
    logger.info("=" * 55)
    logger.info("采集完成")
    logger.info("=" * 55)

    success = [r for r in results.values() if r['status'] == 'success']
    failed = [r for r in results.values() if r['status'] == 'failed']
    skipped = [r for r in results.values() if r['status'] == 'skipped']

    logger.info(f"成功: {len(success)} | 失败: {len(failed)} | 跳过: {len(skipped)}")

    for code, r in results.items():
        icon = {'success': '✅', 'failed': '❌', 'skipped': '⏭'}[r['status']]
        if r['status'] == 'success':
            logger.info(f"  {icon} {code}: {r['earliest']} ~ {r['latest']} (+{r['written']}条)")
        elif r['status'] == 'failed':
            logger.info(f"  {icon} {code}: {r['error']}")
        else:
            logger.info(f"  {icon} {code}: {r['reason']}")

    # 全部范围验证
    logger.info("")
    logger.info("--- 全部 15 只 ETF 范围 ---")
    conn = sqlite3.connect(str(_ROOT / "etf_data_live" / "etf.db"))
    all_etfs = [c for c, _ in FETCH_ETFS] + ['512880', '512660', '512980', '515650', '515070', '515790']
    cur = conn.execute('''
        SELECT code, MIN(date), MAX(date), COUNT(*) 
        FROM daily WHERE code IN (%s)
        GROUP BY code ORDER BY MIN(date)
    ''' % ','.join(f"'{c}'" for c in all_etfs))
    rows = cur.fetchall()
    logger.info(f"{'ETF':<8} {'最早':<12} {'最晚':<12} {'天数':>5} {'够5年':>6}")
    logger.info("-" * 50)
    all_ok = True
    for code, md, xd, cnt in rows:
        ok = '✅' if md and md <= TARGET_DATE else '❌'
        if md and md > TARGET_DATE:
            all_ok = False
        logger.info(f"{code:<8} {md or 'N/A':<12} {xd or 'N/A':<12} {cnt:>5} {ok}")
    conn.close()

    # 保存结果
    out = _ROOT / "data" / "experiments_v9_recompute" / 'data' / 'experiments_v9_recompute' / 'fetch_5yr_result.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        'timestamp': datetime.now().isoformat(),
        'target': TARGET_DATE,
        'results': results,
        'summary': {
            'total': len(FETCH_ETFS),
            'success': len(success),
            'failed': len(failed),
            'skipped': len(skipped),
        }
    }, ensure_ascii=False, indent=2))
    logger.info(f"结果已保存: {out}")

    if all_ok:
        logger.info("\n🎉 15 只 ETF 全部覆盖到 2021-01-01 之前")
    else:
        logger.info("\n⚠ 部分 ETF 仍缺早期数据")

    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
