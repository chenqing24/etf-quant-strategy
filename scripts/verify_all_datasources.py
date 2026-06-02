#!/usr/bin/env python3
"""
数据源接口验证脚本
只验证实际可用的接口，确保文档与实现一致
"""
import json
import re
import sqlite3
import time
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

import requests

# 验证结果存储
VERIFICATION_RESULTS = []

@dataclass
class VerificationResult:
    source: str
    interface: str
    url: str
    status: str  # ✅通过 | ❌失败 | ⚠️警告
    message: str
    data_sample: Optional[Dict] = None

def verify_tencent_realtime(codes: List[str]) -> List[VerificationResult]:
    """验证腾讯实时行情接口"""
    results = []
    base_url = "https://qt.gtimg.cn/q="
    
    for code in codes[:3]:  # 只测3个
        prefix = "sz" if code.startswith("1") else "sh"
        url = f"{base_url}{prefix}{code}"
        
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200 and resp.text:
                # 解析返回数据
                text = resp.text.strip()
                if text.startswith('v_'):
                    # 提取数据字段
                    match = re.search(r'"([^"]*)"', text)
                    if match:
                        fields = match.group(1).split('~')
                        if len(fields) > 6:
                            results.append(VerificationResult(
                                source="腾讯行情API",
                                interface="实时行情",
                                url=url,
                                status="✅通过",
                                message=f"返回{len(fields)}个字段",
                                data_sample={
                                    "code": fields[2],
                                    "name": fields[1],
                                    "price": fields[3],
                                    "prev_close": fields[4],
                                    "volume": fields[6]
                                }
                            ))
                        else:
                            results.append(VerificationResult(
                                source="腾讯行情API",
                                interface="实时行情",
                                url=url,
                                status="⚠️警告",
                                message="字段数不足"
                            ))
                    else:
                        results.append(VerificationResult(
                            source="腾讯行情API",
                            interface="实时行情",
                            url=url,
                            status="❌失败",
                            message="无法解析数据"
                        ))
            else:
                results.append(VerificationResult(
                    source="腾讯行情API",
                    interface="实时行情",
                    url=url,
                    status="❌失败",
                    message=f"HTTP {resp.status_code}"
                ))
        except Exception as e:
            results.append(VerificationResult(
                source="腾讯行情API",
                interface="实时行情",
                url=url,
                status="❌失败",
                message=str(e)
            ))
        
        time.sleep(1)
    
    return results

def verify_tencent_daily(codes: List[str]) -> List[VerificationResult]:
    """验证腾讯日线接口"""
    results = []
    base_url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    
    for code in codes[:3]:
        prefix = "sz" if code.startswith("1") else "sh"
        url = f"{base_url}?_var=kline_dayqfq&param={prefix}{code},day,,,10,qfq"
        
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200 and resp.text:
                # 解析JSON
                text = resp.text.replace('kline_dayqfq=', '', 1)
                data = json.loads(text)
                
                if 'data' in data:
                    key = f"{prefix}{code}"
                    if key in data['data']:
                        # 优先取qfqday（复权日线），其次取day
                        day_data = data['data'][key]
                        days = day_data.get('qfqday') or day_data.get('day') or []
                        if days:
                            results.append(VerificationResult(
                                source="腾讯行情API",
                                interface="日线历史",
                                url=url,
                                status="✅通过",
                                message=f"返回{len(days)}条日线",
                                data_sample=days[0] if days else None
                            ))
                        else:
                            results.append(VerificationResult(
                                source="腾讯行情API",
                                interface="日线历史",
                                url=url,
                                status="⚠️警告",
                                message="日线数据为空"
                            ))
                    else:
                        results.append(VerificationResult(
                            source="腾讯行情API",
                            interface="日线历史",
                            url=url,
                            status="❌失败",
                            message=f"缺少{key}数据"
                        ))
        except Exception as e:
            results.append(VerificationResult(
                source="腾讯行情API",
                interface="日线历史",
                url=url,
                status="❌失败",
                message=str(e)
            ))
        
        time.sleep(1)
    
    return results

def verify_sina_realtime(codes: List[str]) -> List[VerificationResult]:
    """验证新浪实时行情接口"""
    results = []
    base_url = "https://hq.sinajs.cn/list="
    
    for code in codes[:3]:
        prefix = "sz" if code.startswith("1") else "sh"
        url = f"{base_url}{prefix}{code}"
        
        try:
            resp = requests.get(
                url,
                headers={"Referer": "https://finance.sina.com.cn/"},
                timeout=10
            )
            if resp.status_code == 200 and resp.text:
                text = resp.text.strip()
                if 'hq_str_' in text:
                    match = re.search(r'"([^"]*)"', text)
                    if match:
                        fields = match.group(1).split(',')
                        if len(fields) > 6:
                            results.append(VerificationResult(
                                source="新浪财经API",
                                interface="实时行情",
                                url=url,
                                status="✅通过",
                                message=f"返回{len(fields)}个字段",
                                data_sample={
                                    "name": fields[0],  # 名称
                                    "price": fields[3],  # 当前价
                                    "prev_close": fields[2],  # 昨收
                                    "open": fields[1],  # 开盘
                                }
                            ))
                        else:
                            results.append(VerificationResult(
                                source="新浪财经API",
                                interface="实时行情",
                                url=url,
                                status="⚠️警告",
                                message="字段数不足"
                            ))
        except Exception as e:
            results.append(VerificationResult(
                source="新浪财经API",
                interface="实时行情",
                url=url,
                status="❌失败",
                message=str(e)
            ))
        
        time.sleep(1)
    
    return results

def verify_sina_minline(codes: List[str]) -> List[VerificationResult]:
    """验证新浪小时线接口"""
    results = []
    base_url = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
    
    for code in codes[:3]:
        prefix = "sz" if code.startswith("1") else "sh"
        url = f"{base_url}?symbol={prefix}{code}&scale=30&ma=no&datalen=5"
        
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    results.append(VerificationResult(
                        source="新浪财经API",
                        interface="30分钟K线",
                        url=url,
                        status="✅通过",
                        message=f"返回{len(data)}条K线",
                        data_sample=data[0]
                    ))
                else:
                    results.append(VerificationResult(
                        source="新浪财经API",
                        interface="30分钟K线",
                        url=url,
                        status="⚠️警告",
                        message="数据为空或格式错误"
                    ))
        except Exception as e:
            results.append(VerificationResult(
                source="新浪财经API",
                interface="30分钟K线",
                url=url,
                status="❌失败",
                message=str(e)
            ))
        
        time.sleep(1)
    
    return results

def verify_tiantian_fund(codes: List[str]) -> List[VerificationResult]:
    """验证天天基金实时估值接口"""
    results = []
    base_url = "https://fundgz.1234567.com.cn/js/"
    
    for code in codes[:3]:
        url = f"{base_url}{code}.js?rt={int(time.time())}"
        
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200 and resp.text:
                # JSONP格式: jsonpgz({...})
                text = resp.text.strip()
                if text.startswith('jsonpgz('):
                    json_str = text.replace('jsonpgz(', '').rstrip(');')
                    data = json.loads(json_str)
                    
                    results.append(VerificationResult(
                        source="天天基金网",
                        interface="实时估值",
                        url=url,
                        status="✅通过",
                        message="获取成功",
                        data_sample={
                            "fundcode": data.get("fundcode"),
                            "name": data.get("name"),
                            "gsz": data.get("gsz"),
                            "gszzl": data.get("gszzl")
                        }
                    ))
                else:
                    results.append(VerificationResult(
                        source="天天基金网",
                        interface="实时估值",
                        url=url,
                        status="❌失败",
                        message="非JSONP格式"
                    ))
        except Exception as e:
            results.append(VerificationResult(
                source="天天基金网",
                interface="实时估值",
                url=url,
                status="❌失败",
                message=str(e)
            ))
        
        time.sleep(1)
    
    return results

def verify_tiantian_history(codes: List[str]) -> List[VerificationResult]:
    """验证天天基金历史净值接口"""
    results = []
    base_url = "https://api.fund.eastmoney.com/f10/lsjz"
    
    for code in codes[:3]:
        url = f"{base_url}?callback=jQuery&fundCode={code}&pageIndex=1&pageSize=5"
        
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200 and resp.text:
                text = resp.text.strip()
                if text.startswith('jQuery'):
                    json_str = re.sub(r'^jQuery\([^)]*\(",|\)\);?$', '', text)
                    # 提取JSON部分
                    match = re.search(r'(\{.*\})', text)
                    if match:
                        data = json.loads(match.group(1))
                        if 'Data' in data and 'LSJZList' in data['Data']:
                            list_data = data['Data']['LSJZList']
                            if list_data:
                                results.append(VerificationResult(
                                    source="天天基金网",
                                    interface="历史净值",
                                    url=url,
                                    status="✅通过",
                                    message=f"返回{len(list_data)}条记录",
                                    data_sample=list_data[0]
                                ))
                            else:
                                results.append(VerificationResult(
                                    source="天天基金网",
                                    interface="历史净值",
                                    url=url,
                                    status="⚠️警告",
                                    message="净值列表为空"
                                ))
                    else:
                        results.append(VerificationResult(
                            source="天天基金网",
                            interface="历史净值",
                            url=url,
                            status="❌失败",
                            message="无法解析JSON"
                        ))
        except Exception as e:
            results.append(VerificationResult(
                source="天天基金网",
                interface="历史净值",
                url=url,
                status="❌失败",
                message=str(e)
            ))
        
        time.sleep(1)
    
    return results

def verify_baostock(codes: List[str]) -> List[VerificationResult]:
    """验证BaoStock接口"""
    results = []
    
    try:
        import baostock as bs
        
        # 登录
        bs.login()
        
        for code in codes[:3]:
            bs_code = f"sz.{code}" if code.startswith("1") else f"sh.{code}"
            url = f"baostock:query_history_k_data_plus({bs_code})"
            
            try:
                rs = bs.query_history_k_data_plus(
                    bs_code,
                    'date,open,high,low,close,volume',
                    start_date='2026-01-01',
                    end_date='2026-05-30',
                    frequency='d'
                )
                
                if rs.error_code == '0':
                    rows = []
                    while rs.next():
                        rows.append(rs.get_row_data())
                    
                    if rows:
                        results.append(VerificationResult(
                            source="BaoStock",
                            interface="日线数据",
                            url=url,
                            status="✅通过",
                            message=f"返回{len(rows)}条记录",
                            data_sample=rows[0]
                        ))
                    else:
                        results.append(VerificationResult(
                            source="BaoStock",
                            interface="日线数据",
                            url=url,
                            status="⚠️警告",
                            message="数据为空"
                        ))
                else:
                    results.append(VerificationResult(
                        source="BaoStock",
                        interface="日线数据",
                        url=url,
                        status="❌失败",
                        message=rs.error_msg
                    ))
            except Exception as e:
                results.append(VerificationResult(
                    source="BaoStock",
                    interface="日线数据",
                    url=url,
                    status="❌失败",
                    message=str(e)
                ))
            
            time.sleep(0.5)
        
        bs.logout()
        
    except ImportError:
        results.append(VerificationResult(
            source="BaoStock",
            interface="日线数据",
            url="pip install baostock",
            status="⚠️警告",
            message="未安装BaoStock"
        ))
    except Exception as e:
        results.append(VerificationResult(
            source="BaoStock",
            interface="日线数据",
            url="baostock",
            status="❌失败",
            message=str(e)
        ))
    
    return results

def verify_eastmoney_emf(codes: List[str]) -> List[VerificationResult]:
    """验证东方财富EMF接口"""
    results = []
    base_url = "https://push2.eastmoney.com/api/qt/stock/get"
    
    for code in codes[:3]:
        secid = f"0.{code}" if code.startswith("1") else f"1.{code}"
        url = f"{base_url}?ut=fa5fd1943c7b386f172d6893dbfba10b&invt=2&fltt=2&fields=f57,f58,f60,f84,f116&secid={secid}"
        
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if 'data' in data and data['data']:
                    results.append(VerificationResult(
                        source="东方财富EMF",
                        interface="实时行情",
                        url=url,
                        status="✅通过",
                        message="获取成功",
                        data_sample={
                            "f57": data['data'].get('f57'),
                            "f58": data['data'].get('f58'),
                            "f60": data['data'].get('f60')
                        }
                    ))
                else:
                    results.append(VerificationResult(
                        source="东方财富EMF",
                        interface="实时行情",
                        url=url,
                        status="❌失败",
                        message="数据为空"
                    ))
        except Exception as e:
            results.append(VerificationResult(
                source="东方财富EMF",
                interface="实时行情",
                url=url,
                status="❌失败",
                message=str(e)
            ))
        
        time.sleep(1)
    
    return results

def verify_xueqiu_page(codes: List[str]) -> List[VerificationResult]:
    """验证雪球页面"""
    results = []
    
    for code in codes[:3]:
        prefix = "SZ" if code.startswith("1") else "SH"
        url = f"https://xueqiu.com/S/{prefix}{code}"
        
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10
            )
            if resp.status_code == 200 and 'xueqiu' in resp.text.lower():
                results.append(VerificationResult(
                    source="雪球Xueqiu",
                    interface="基金页面",
                    url=url,
                    status="✅通过",
                    message="页面可访问",
                    data_sample={"title": "雪球ETF页面"}
                ))
            else:
                results.append(VerificationResult(
                    source="雪球Xueqiu",
                    interface="基金页面",
                    url=url,
                    status="❌失败",
                    message=f"HTTP {resp.status_code}"
                ))
        except Exception as e:
            results.append(VerificationResult(
                source="雪球Xueqiu",
                interface="基金页面",
                url=url,
                status="❌失败",
                message=str(e)
            ))
        
        time.sleep(1)
    
    return results

def verify_baidu_baike() -> List[VerificationResult]:
    """验证百度百科"""
    results = []
    url = "https://baike.baidu.com/item/ETF"
    
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        if resp.status_code == 200:
            if '百度安全验证' in resp.text:
                results.append(VerificationResult(
                    source="百度百科",
                    interface="词条搜索",
                    url=url,
                    status="⚠️警告",
                    message="触发安全验证"
                ))
            elif 'ETF' in resp.text:
                results.append(VerificationResult(
                    source="百度百科",
                    interface="词条搜索",
                    url=url,
                    status="✅通过",
                    message="页面可访问",
                    data_sample={"title": "ETF词条"}
                ))
            else:
                results.append(VerificationResult(
                    source="百度百科",
                    interface="词条搜索",
                    url=url,
                    status="❌失败",
                    message="内容解析失败"
                ))
        else:
            results.append(VerificationResult(
                source="百度百科",
                interface="词条搜索",
                url=url,
                status="❌失败",
                message=f"HTTP {resp.status_code}"
            ))
    except Exception as e:
        results.append(VerificationResult(
            source="百度百科",
            interface="词条搜索",
            url=url,
            status="❌失败",
            message=str(e)
        ))
    
    return results

def main():
    """主函数"""
    print("=" * 60)
    print("数据源接口验证")
    print("=" * 60)
    
    # 从数据库获取ETF代码
    conn = sqlite3.connect('etf_data_live/etf.db')
    cursor = conn.execute("SELECT code FROM etf_names LIMIT 10")
    codes = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    if not codes:
        codes = ['159919', '510300', '510050', '512010', '515000']
    
    print(f"\n使用测试代码: {codes[:5]}")
    print("-" * 60)
    
    all_results = []
    
    # 验证所有接口
    print("\n[1/10] 验证腾讯实时行情...")
    all_results.extend(verify_tencent_realtime(codes))
    
    print("[2/10] 验证腾讯日线...")
    all_results.extend(verify_tencent_daily(codes))
    
    print("[3/10] 验证新浪实时行情...")
    all_results.extend(verify_sina_realtime(codes))
    
    print("[4/10] 验证新浪30分钟K线...")
    all_results.extend(verify_sina_minline(codes))
    
    print("[5/10] 验证天天基金实时估值...")
    all_results.extend(verify_tiantian_fund(codes))
    
    print("[6/10] 验证天天基金历史净值...")
    all_results.extend(verify_tiantian_history(codes))
    
    print("[7/10] 验证BaoStock...")
    all_results.extend(verify_baostock(codes))
    
    print("[8/10] 验证东方财富EMF...")
    all_results.extend(verify_eastmoney_emf(codes))
    
    print("[9/10] 验证雪球页面...")
    all_results.extend(verify_xueqiu_page(codes))
    
    print("[10/10] 验证百度百科...")
    all_results.extend(verify_baidu_baike())
    
    # 输出结果
    print("\n" + "=" * 60)
    print("验证结果汇总")
    print("=" * 60)
    
    passed = [r for r in all_results if r.status == "✅通过"]
    warning = [r for r in all_results if r.status == "⚠️警告"]
    failed = [r for r in all_results if r.status == "❌失败"]
    
    print(f"\n✅ 通过: {len(passed)} 个")
    print(f"⚠️ 警告: {len(warning)} 个")
    print(f"❌ 失败: {len(failed)} 个")
    
    print("\n" + "-" * 60)
    print("详细结果:")
    print("-" * 60)
    
    for r in all_results:
        status_icon = "✅" if r.status == "✅通过" else "⚠️" if r.status == "⚠️警告" else "❌"
        print(f"\n{status_icon} [{r.source}] {r.interface}")
        print(f"   状态: {r.status}")
        print(f"   消息: {r.message}")
        print(f"   示例: {r.data_sample}")
    
    # 输出JSON格式结果供文档使用
    print("\n" + "=" * 60)
    print("JSON格式结果（供文档使用）")
    print("=" * 60)
    
    json_results = [
        {
            "source": r.source,
            "interface": r.interface,
            "status": r.status,
            "message": r.message,
            "data_sample": r.data_sample
        }
        for r in all_results
    ]
    print(json.dumps(json_results, ensure_ascii=False, indent=2))
    
    # 保存结果
    with open('docs/verification_results.json', 'w', encoding='utf-8') as f:
        json.dump(json_results, f, ensure_ascii=False, indent=2)
    print("\n结果已保存到 docs/verification_results.json")
    
    return all_results

if __name__ == "__main__":
    main()