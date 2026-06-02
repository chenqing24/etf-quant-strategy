#!/usr/bin/env python3
"""
新浪小时线API实测脚本
测试目标：验证新浪直连API的历史回溯边界（理论值：1800条约1.5年）

Usage:
    python scripts/test_sina_hourly_api.py [code]
    
Examples:
    python scripts/test_sina_hourly_api.py sh510300
    python scripts/test_sina_hourly_api.py sh510500
"""

import requests
import time
import random
import sys
from datetime import datetime

SINA_BASE_URL = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"

def fetch_hourly(code: str, scale: int = 30, datalen: int = 1800) -> list:
    """
    获取新浪小时线数据
    
    Args:
        code: 标的代码（如 sh510300）
        scale: 时间周期（30=30分钟）
        datalen: 数据条数
    
    Returns:
        JSON响应列表
    """
    url = f"{SINA_BASE_URL}?symbol={code}&scale={scale}&ma=no&datalen={datalen}"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://finance.sina.com.cn/"
    }
    
    # 随机等待2-5秒（避免反爬）
    wait = random.uniform(2, 5)
    print(f"  等待 {wait:.1f}秒...")
    time.sleep(wait)
    
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()

def analyze(data: list, code: str) -> dict:
    """分析数据"""
    if not data:
        return {"error": "无数据返回"}
    
    # 第一条和最后一条
    first = data[0]
    last = data[-1]
    
    # 解析日期
    first_ts = first.get("day", "")
    last_ts = last.get("day", "")
    
    # 计算覆盖天数
    try:
        first_date = datetime.strptime(first_ts[:10], "%Y-%m-%d")
        last_date = datetime.strptime(last_ts[:10], "%Y-%m-%d")
        days_span = (last_date - first_date).days
    except:
        days_span = "解析失败"
    
    return {
        "code": code,
        "total": len(data),
        "first_ts": first_ts,
        "last_ts": last_ts,
        "days_span": days_span,
        "first": first,
        "last": last
    }

def main():
    codes = sys.argv[1:] if len(sys.argv) > 1 else ["sh510300", "sh510500"]
    
    results = []
    for code in codes:
        print(f"\n=== 测试 {code} ===")
        try:
            data = fetch_hourly(code)
            result = analyze(data, code)
            results.append(result)
            
            print(f"  总条数: {result['total']}")
            print(f"  最早时间: {result['first_ts']}")
            print(f"  最新时间: {result['last_ts']}")
            print(f"  覆盖天数: {result['days_span']}天")
            
            # 计算偏差（理论值：1800条≈1.5年≈547天）
            if isinstance(result['days_span'], int):
                theory_days = 547
                deviation = (result['days_span'] - theory_days) / theory_days * 100
                print(f"  理论值偏差: {deviation:+.1f}% (理论547天)")
        except Exception as e:
            print(f"  ❌ 错误: {e}")
            results.append({"code": code, "error": str(e)})
    
    # 对比两只ETF
    if len(results) == 2 and all("days_span" in r and isinstance(r["days_span"], int) for r in results):
        r1, r2 = results[0], results[1]
        same_cutoff = r1["first_ts"][:10] == r2["first_ts"][:10]
        print(f"\n=== 截断行为对比 ===")
        print(f"  {r1['code']} 最早: {r1['first_ts'][:10]}")
        print(f"  {r2['code']} 最早: {r2['first_ts'][:10]}")
        print(f"  同一截断点: {'✅' if same_cutoff else '❌'}")
    
    return results

if __name__ == "__main__":
    main()