# main.py - 美股盤整突破轉勢掃描器 V21.0
# ============================================
# V21.0 改動：
#   1. 數據源：180d（唔用 1y）
#   2. 兩階段：180d 快篩 → 180d 詳細 → info 攞 52W
#   3. 加 sector（行業）
#   4. 加 info 攞 52W / 市值
# ============================================

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from scipy.signal import find_peaks

yf.set_tz_cache_location("/tmp/yf_cache")
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# ==================== 參數 ====================

BOTTOM_PARAMS = {
    'from_high_pct': -15,      # 距 52 週高位跌 15%
    'consolidation_days': 30,
    'consolidation_range': 20, # 盤整波幅 < 20%
    'volume_ratio': 1.5,
}

TOP_PARAMS = {
    'from_low_pct': 50,
    'consolidation_days': 30,
    'consolidation_range': 20,
    'volume_ratio': 1.5,
}

BATCH_SIZE = 30
BATCH_DELAY = 0.5
REST_EVERY = 500
REST_DURATION = 15

# ==================== 市值 ====================

def format_market_cap(market_cap):
    if market_cap is None or market_cap <= 0:
        return "N/A", 0
    val = float(market_cap)
    if val >= 1e12:
        return f"${round(val / 1e12, 2)}T", val
    elif val >= 1e9:
        return f"${round(val / 1e9, 2)}B", val
    elif val >= 1e6:
        return f"${round(val / 1e6, 2)}M", val
    else:
        return f"${round(val, 0)}", val


# ==================== 全美股名單 ====================

def get_all_us_stocks():
    headers = {'User-Agent': 'Mozilla/5.0'}
    tickers = set()

    try:
        url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/all/all_tickers.txt"
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            for line in res.text.splitlines():
                sym = line.strip().upper()
                if sym and sym.isalpha() and len(sym) <= 5:
                    tickers.add(sym)
            print(f"✅ 成功獲取 {len(tickers)} 隻全美股股票標的")
    except Exception:
        pass

    if not tickers:
        tickers = {"AAPL", "MSFT", "NVDA"}

    return sorted(list(tickers))


# ==================== 技術指標 ====================

def calculate_macd(close, fast=5, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = dif - dea
    return dif, dea, hist


def check_consolidation(df, days=30):
    if len(df) < days + 5:
        return None
    recent = df.tail(days)
    high = float(recent['High'].max())
    low = float(recent['Low'].min())
    if low <= 0:
        return None
    range_pct = (high - low) / low * 100
    return {
        'range_pct': round(range_pct, 1),
        'high': round(high, 2),
        'low': round(low, 2),
    }


def check_volume_breakout(df, days=30, ratio=1.5):
    if len(df) < days + 2:
        return None
    vol_today = float(df['Volume'].iloc[-1])
    vol_avg = float(df['Volume'].tail(days).mean())
    if vol_avg <= 0:
        return None
    vol_ratio = vol_today / vol_avg
    return {
        'vol_ratio': round(min(vol_ratio, 50), 2),
        'vol_today': vol_today,
        'vol_avg': vol_avg,
    }


def has_pivot_divergence(df, direction='bottom'):
    if len(df) < 60:
        return False
    close = df['Close']
    dif, _, _ = calculate_macd(close)
    prominence = close.mean() * 2.0 / 100
    distance = 5

    if direction == 'bottom':
        pivots, _ = find_peaks(-close.values, prominence=prominence, distance=distance)
    else:
        pivots, _ = find_peaks(close.values, prominence=prominence, distance=distance)

    if len(pivots) < 2:
        return False

    p1, p2 = int(pivots[-2]), int(pivots[-1])

    if direction == 'bottom':
        if close.iloc[p2] < close.iloc[p1] and dif.iloc[p2] > dif.iloc[p1]:
            return True
    else:
        if close.iloc[p2] > close.iloc[p1] and dif.iloc[p2] < dif.iloc[p1]:
            return True

    return False


# ==================== 階段 1：180d 快篩 ====================

def stage1_filter(ticker, df):
    """寬鬆快篩，唔要錯殺"""
    if df is None or len(df) < 100:
        return None

    current = float(df['Close'].iloc[-1])
    if current < 2.0:
        return None

    vol_today = float(df['Volume'].iloc[-1])
    if vol_today < 20000:
        return None

    # 寬鬆條件：成交量放大 ≥ 1.2x
    vol_avg = float(df['Volume'].tail(20).mean())
    vol_ratio = vol_today / vol_avg if vol_avg > 0 else 0
    if vol_ratio < 1.2:
        return None

    return {
        'ticker': ticker,
        'price': current,
        'vol_ratio': vol_ratio,
        'df': df,   # 保留 df，階段 2 用
    }


# ==================== 階段 2：180d 詳細分析 ====================

def stage2_screen(candidate):
    """嚴格精篩"""
    ticker = candidate['ticker']
    df = candidate['df']
    current = candidate['price']
    vol_ratio = candidate['vol_ratio']

    # 盤整
    cons = check_consolidation(df, days=30)
    if not cons:
        return None
    if cons['range_pct'] >= BOTTOM_PARAMS['consolidation_range']:
        return None

    # 成交量
    if vol_ratio < BOTTOM_PARAMS['volume_ratio']:
        return None

    # DIF
    dif, _, _ = calculate_macd(df['Close'])
    dif_now = float(dif.iloc[-1])
    dif_prev = float(dif.iloc[-2])

    # 判斷類型
    result = None

    # 底部轉勢（用 180d 高位代替 52 週）
    high_180d = float(df['High'].max())
    from_high = (current - high_180d) / high_180d * 100

    if (from_high <= BOTTOM_PARAMS['from_high_pct']
        and dif_now > dif_prev):
        has_div = has_pivot_divergence(df, 'bottom')
        result = {
            'type': '底部轉勢',
            'hasDivergence': has_div,
            'from_high_pct': round(from_high, 1),
            'consolidation_range': cons['range_pct'],
            'vol_ratio': vol_ratio,
            'macd_dif': round(dif_now, 4),
        }

    # 頂部轉勢
    low_180d = float(df['Low'].min())
    from_low = (current - low_180d) / low_180d * 100

    if not result and (from_low >= TOP_PARAMS['from_low_pct']
        and dif_now < dif_prev):
        has_div = has_pivot_divergence(df, 'top')
        result = {
            'type': '頂部轉勢',
            'hasDivergence': has_div,
            'from_low_pct': round(from_low, 1),
            'consolidation_range': cons['range_pct'],
            'vol_ratio': vol_ratio,
            'macd_dif': round(dif_now, 4),
        }

    if not result:
        return None

    result['ticker'] = ticker
    result['price'] = round(current, 2)
    return result


# ==================== 階段 3：info 攞 52W + 市值 + sector ====================

def stage3_enrich(stock):
    """用 info 攞 52W / 市值 / sector"""
    ticker = stock['ticker']
    try:
        info = yf.Ticker(ticker).info

        high_52w = info.get('fiftyTwoWeekHigh', None)
        low_52w = info.get('fiftyTwoWeekLow', None)
        market_cap = info.get('marketCap', None)
        sector = info.get('sector', None)

        current = stock['price']

        # 計算距 52W 高/低
        if high_52w and current:
            stock['from52wHigh'] = round((current - high_52w) / high_52w * 100, 1)
        else:
            stock['from52wHigh'] = None

        if low_52w and current:
            stock['from52wLow'] = round((current - low_52w) / low_52w * 100, 1)
        else:
            stock['from52wLow'] = None

        mcap_str, mcap_num = format_market_cap(market_cap)
        stock['marketCap'] = mcap_str
        stock['marketCapNum'] = float(mcap_num)
        stock['sector'] = sector if sector else 'Unknown'

        # 用 52W 重新判斷（更準）
        if high_52w and stock['type'] == '底部轉勢':
            stock['fromHighPct'] = stock['from52wHigh']
        if low_52w and stock['type'] == '頂部轉勢':
            stock['fromLowPct'] = stock['from52wLow']

    except Exception as e:
        print(f"  ⚠️ {ticker} info 失敗: {e}")
        stock['marketCap'] = 'N/A'
        stock['marketCapNum'] = 0
        stock['sector'] = 'Unknown'
        stock['from52wHigh'] = None
        stock['from52wLow'] = None

    # 加連結
    stock['futuUrl'] = f"https://www.futunn.com/hk/stock/{ticker}-US"
    stock['tvUrl'] = f"https://www.tradingview.com/symbols/{ticker}/"

    # 移除 df（唔需要輸出）
    stock.pop('df', None)

    return stock


# ==================== 主程式 ====================

def process_stocks():
    tickers = get_all_us_stocks()
    total_scanned = len(tickers)
    success_count = 0
    failed_count = 0

    print(f"🚀 [階段 1/3] 下載 {total_scanned} 隻 180d 日線數據...")
    print(f"   Batch: {BATCH_SIZE}, Delay: {BATCH_DELAY}s, Rest: {REST_EVERY}")

    # ===== 階段 1：快篩 =====
    stage1_candidates = []

    for i in range(0, total_scanned, BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        try:
            daily_data = yf.download(batch, period="180d", interval="1d",
                                      group_by='ticker', threads=True, progress=False)

            for ticker in batch:
                try:
                    if len(batch) > 1:
                        if ticker not in daily_data.columns.levels[0]:
                            failed_count += 1
                            continue
                        df = daily_data[ticker].dropna(how='all')
                    else:
                        df = daily_data.dropna(how='all')

                    if df is None or len(df) < 100:
                        failed_count += 1
                        continue

                    result = stage1_filter(ticker, df)
                    if result:
                        stage1_candidates.append(result)

                    success_count += 1
                except Exception:
                    failed_count += 1
                    continue
        except Exception as e:
            print(f"⚠️ Batch {i} 失敗: {e}")
            failed_count += len(batch)

        if i > 0 and i % REST_EVERY == 0:
            print(f"  ⏸️ 進度 {i}/{total_scanned}，休息 {REST_DURATION} 秒")
            time.sleep(REST_DURATION)
        else:
            time.sleep(BATCH_DELAY)

        if i % 1000 == 0:
            print(f"  進度：{i}/{total_scanned}，階段1候選 {len(stage1_candidates)} 隻")

    print(f"✅ 階段 1 完成！候選 {len(stage1_candidates)} 隻")

    # ===== 階段 2：詳細分析 =====
    print(f"🚀 [階段 2/3] 詳細分析 {len(stage1_candidates)} 隻...")

    stage2_candidates = []
    for c in stage1_candidates:
        try:
            result = stage2_screen(c)
            if result:
                stage2_candidates.append(result)
        except Exception:
            continue

    print(f"✅ 階段 2 完成！候選 {len(stage2_candidates)} 隻")

    # ===== 階段 3：info 攞 52W + 市值 =====
    print(f"🚀 [階段 3/3] 用 info 攞 52W + 市值（{len(stage2_candidates)} 隻）...")

    results = []
    for stock in stage2_candidates:
        enriched = stage3_enrich(stock)
        results.append(enriched)
        time.sleep(0.3)

    # 排序
    results.sort(key=lambda x: (
        0 if x.get('hasDivergence') else 1,
        0 if x['type'] == '底部轉勢' else 1,
        -x.get('volRatio', 0)
    ))

    hkt = timezone(timedelta(hours=8))
    now_hkt = datetime.now(hkt).strftime("%Y-%m-%d %H:%M")

    bottom_count = sum(1 for r in results if r['type'] == '底部轉勢')
    top_count = sum(1 for r in results if r['type'] == '頂部轉勢')
    div_count = sum(1 for r in results if r.get('hasDivergence'))

    output = {
        "stats": {
            "lastUpdated": now_hkt,
            "totalScanned": total_scanned,
            "successCount": success_count,
            "bottomCount": bottom_count,
            "topCount": top_count,
            "divergenceCount": div_count,
            "matchedCount": len(results),
        },
        "stocks": results
    }

    with open("stocks_data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"🎉 完成！底部 {bottom_count} 隻、頂部 {top_count} 隻（有背離 {div_count} 隻）")
    print(f"   總共 {len(results)} 隻，更新時間：{now_hkt}")


if __name__ == "__main__":
    process_stocks()
