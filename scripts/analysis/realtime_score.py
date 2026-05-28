#!/usr/bin/env python3
"""实时7因子评分 - 基于今日实时数据"""
import requests
import pandas as pd
import json
from datetime import datetime

def load_historical_data(code: str, days: int = 250) -> pd.DataFrame:
    """从腾讯API加载历史K线数据"""
    params = {
        '_var': 'kline_dayqfq',
        'param': f'{code},day,,,{days},qfq'
    }
    headers = {
        'Referer': 'https://finance.qq.com',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    
    try:
        resp = requests.get('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get', params=params, headers=headers, timeout=10)
        text = resp.text
        
        # 解析JSONP格式: kline_dayqfq={...}
        if text.startswith('kline_dayqfq='):
            text = text[len('kline_dayqfq='):]
        
        data = json.loads(text)
        
        # 解析数据
        try:
            raw_data = data.get('data', {}).get(code, {}).get('qfqday', [])
        except:
            raw_data = []
        
        if not raw_data:
            try:
                raw_data = data.get('data', {}).get(code, {}).get('day', [])
            except:
                raw_data = []
        
        records = []
        for item in raw_data[:days]:
            if len(item) >= 6:
                date, open_p, close, high, low, volume = item[:6]
                records.append({
                    'date': date,
                    'open': float(open_p),
                    'close': float(close),
                    'high': float(high),
                    'low': float(low),
                    'volume': float(volume),
                })
        
        df = pd.DataFrame(records)
        if len(df) > 0:
            df['date'] = pd.to_datetime(df['date'])
        
        return df
        
    except Exception as e:
        print(f"  获取 {code} 失败: {e}")
        return pd.DataFrame()

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算技术指标"""
    df = df.copy()
    
    # 移动平均线
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    df['ma120'] = df['close'].rolling(120).mean()
    
    # 成交量均线
    df['vol_ma5'] = df['volume'].rolling(5).mean()
    df['vol_ratio'] = df['volume'] / df['vol_ma5']
    
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # MACD
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    df['macd'] = (ema12 - ema26) * 2
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    
    return df

def score_etf(df: pd.DataFrame, real_price: float) -> tuple:
    """7因子打分
    
    因子: MA120站上(+3), MA60向上(+2), MA60站上(+2), MA20站上(+1), 放量(+2), 近5日涨(+1), RSI未过热(+1)
    """
    if len(df) < 125:
        return 0, [], {}
    
    # 用实时价格替换最后一天
    df = df.copy()
    df.iloc[-1, df.columns.get_loc('close')] = real_price
    df.iloc[-1, df.columns.get_loc('high')] = max(df.iloc[-1]['high'], real_price)
    
    # 重算均线
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    df['ma120'] = df['close'].rolling(120).mean()
    
    # 成交量均线和放量比
    df['vol_ma5'] = df['volume'].rolling(5).mean()
    df['vol_ratio'] = df['volume'] / df['vol_ma5']
    
    row = df.iloc[-1]
    
    score = 0
    reasons = []
    details = {}
    
    # 1. 站上120日线 (+3分)
    if row['close'] > row['ma120']:
        score += 3
        reasons.append('MA120')
        details['ma120_ok'] = True
    else:
        details['ma120_ok'] = False
    
    # 2. 60日均线向上 (+2分)
    ma60_now = row['ma60']
    ma60_5d_ago = df['ma60'].iloc[-6] if len(df) >= 6 else 0
    if not pd.isna(ma60_now) and not pd.isna(ma60_5d_ago) and ma60_now > ma60_5d_ago:
        score += 2
        reasons.append('MA60↑')
        details['ma60_up'] = True
    else:
        details['ma60_up'] = False
    
    # 3. 站上60日线 (+2分)
    if row['close'] > row['ma60']:
        score += 2
        reasons.append('MA60')
        details['ma60_ok'] = True
    else:
        details['ma60_ok'] = False
    
    # 4. 站上20日线 (+1分)
    if row['close'] > row['ma20']:
        score += 1
        reasons.append('MA20')
        details['ma20_ok'] = True
    else:
        details['ma20_ok'] = False
    
    # 5. 放量 (+2分)
    vol_ratio = row['vol_ratio'] if not pd.isna(row.get('vol_ratio')) else 0
    if vol_ratio > 1.5:
        score += 2
        reasons.append(f'放量{vol_ratio:.1f}x')
        details['vol_ok'] = True
    else:
        details['vol_ok'] = False
    
    # 6. 近5日上涨 (+1分)
    if len(df) >= 6:
        ret_5d = (df['close'].iloc[-1] / df['close'].iloc[-6] - 1) * 100
        if ret_5d > 2:
            score += 1
            reasons.append(f'5日+{ret_5d:.1f}%')
            details['ret5d_ok'] = True
        else:
            details['ret5d_ok'] = False
    else:
        details['ret5d_ok'] = False
    
    # 7. RSI < 70 (不过热) (+1分)
    # 简化计算RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = (100 - (100 / (1 + rs))).iloc[-1]
    details['rsi'] = rsi
    
    if not pd.isna(rsi) and rsi < 70:
        score += 1
        reasons.append(f'RSI{int(rsi)}')
        details['rsi_ok'] = True
    else:
        details['rsi_ok'] = False
    
    return score, reasons, details

def main():
    # 读取今日实时数据
    with open('etf_data_live/today_realtime.json') as f:
        today_data = json.load(f)
    
    results = []
    today = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    print(f"\n{'='*75}")
    print(f"📊 实时7因子评分 - {today}")
    print(f"{'='*75}")
    print(f"\n{'排名':<4} {'代码':<8} {'名称':<8} {'现价':<8} {'今日':<8} {'评分':<4} {'7因子详情'}")
    print("-" * 75)
    
    for code, info in today_data.items():
        real_price = info['price']
        name = info['name'][:6]
        pct = info['pct']
        
        # 确定交易所前缀
        if code.startswith(('51', '15')):
            api_code = f'sh{code}'
        else:
            api_code = f'sz{code}'
        
        # 加载历史数据
        df = load_historical_data(api_code)
        
        if len(df) < 125:
            print(f"  {code} {name}: 数据不足({len(df)}天)")
            continue
        
        # 添加技术指标
        df = add_indicators(df)
        
        # 7因子打分
        score, reasons, details = score_etf(df, real_price)
        
        # 格式化因子详情
        factor_str = []
        factor_str.append('✓' if details.get('ma120_ok') else '✗')
        factor_str.append('↑' if details.get('ma60_up') else '↓')
        factor_str.append('✓' if details.get('ma60_ok') else '✗')
        factor_str.append('✓' if details.get('ma20_ok') else '✗')
        factor_str.append('✓' if details.get('vol_ok') else '✗')
        factor_str.append('✓' if details.get('ret5d_ok') else '✗')
        factor_str.append('✓' if details.get('rsi_ok') else '✗')
        
        results.append({
            'code': code,
            'name': info['name'],
            'price': real_price,
            'pct': pct,
            'score': score,
            'factors': ' '.join(factor_str),
            'reasons': reasons,
            'details': details
        })
    
    # 按分数排序
    results.sort(key=lambda x: -x['score'])
    
    for i, r in enumerate(results[:15], 1):
        print(f"{i:<4} {r['code']:<8} {r['name']:<8} {r['price']:<8.3f} {r['pct']:>+6.2f}%   {r['score']:<4} {r['factors']}")
    
    # 最佳推荐
    if results:
        top = results[0]
        target = round(top['price'] * 1.10, 3)
        stop = round(top['price'] * 0.94, 3)
        
        print(f"\n{'='*75}")
        print(f"🏆 今日最佳推荐: {top['code']} {top['name']}")
        print(f"   现价: {top['price']}元 | 目标: {target}元 (+10%) | 止损: {stop}元 (-6%)")
        print(f"   今日涨幅: {top['pct']:+.2f}% | 7因子总分: {top['score']}")
        print(f"   触发信号: {' + '.join(top['reasons'])}")
        print(f"   RSI: {top['details'].get('rsi', 'N/A'):.1f}")
        print(f"{'='*75}")
        
        # TOP3推荐
        if len(results) >= 3:
            print(f"\n📋 今日TOP3推荐:")
            for i, r in enumerate(results[:3], 1):
                target = round(r['price'] * 1.10, 3)
                stop = round(r['price'] * 0.94, 3)
                print(f"   {i}. {r['code']} {r['name'][:6]}: {r['price']}元 → 目标{target}/止损{stop} | 评分{r['score']}分")
        
        # 保存结果
        with open('etf_reports/realtime_score_20260525.json', 'w') as f:
            json.dump({
                'date': today,
                'top1': {
                    'code': top['code'],
                    'name': top['name'],
                    'price': top['price'],
                    'target': target,
                    'stop': stop,
                    'score': top['score'],
                    'pct': top['pct']
                },
                'all': results[:10]
            }, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 结果已保存到 etf_reports/realtime_score_20260525.json")

if __name__ == '__main__':
    main()