# main.py - 美股盤整突破轉勢掃描器 V20.1
# ============================================
# V20.1 改動（相對 V20.0）：
#   1. 放寬參數：-30% → -20%、12% → 15%、2.0x → 1.5x
#   2. 「背離」改成可選（有 ⭐，冇普通）
#   3. 修正：加 hasDivergence 欄位
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

# ==================== 參數（放寬版）====================

# 底部轉勢
BOTTOM_PARAMS = {
    'from_high_pct': -20,      # 距 52 週高位跌 ≥ 20%（放寬）
    'consolidation_days': 30,
    'consolidation_range': 15, # 盤整波幅 < 15%（放寬）
    'volume_ratio': 1.5,       # 成交量放大 ≥ 1.5x（放寬）
}

# 頂部轉勢
TOP_PARAMS = {
    'from_low_pct': 50,        # 距 52 週低位升 ≥ 50%
    'consolidation_days': 30,
    'consolidation_range': 15, # 放寬
    'volume_ratio': 1.5,       # 放寬
}

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


def get_market_cap(ticker, price):
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        mcap = info.get('market_cap', None)
        if mcap and not np.isnan(mcap) and mcap > 0:
            return mcap
        shares = info.get('shares', None)
        if shares and shares > 0 and price > 0:
            return shares * price
    except Exception:
        pass
    return None


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
        tickers = {"AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX", "INTC"}

    return sorted(list(tickers))


# ==================== 技術指標 ====================

def calculate_macd(close, fast=5, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = dif - dea
    return dif, dea, hist


def check_52w_position(df):
    if len(df) < 252:
        return None
    high_52w = float(df['High'].tail(252).max())
    low_52w = float(df['Low'].tail(252).min())
    current = float(df['Close'].iloc[-1])
    from_high = (current - high_52w) / high_52w * 100
    from_low = (current - low_52w) / low_52w * 100
    return {
        'from_high_pct': round(from_high, 1),
        'from_low_pct': round(from_low, 1),
        'high_52w': round(high_52w, 2),
        'low_52w': round(low_52w, 2),
    }


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
    """Pivot-to-pivot 背離（可選加分）"""
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


# ==================== 主篩選邏輯 ====================

def screen_stock(ticker, df):
    if df is None or len(df) < 252:
        return None

    current = float(df['Close'].iloc[-1])

    # 52 週位置
    pos = check_52w_position(df)
    if not pos:
        return None

    # 盤整檢測
    cons = check_consolidation(df, days=30)
    if not cons:
        return None

    # 成交量
    vol = check_volume_breakout(df, days=30, ratio=1.5)
    if not vol:
        return None

    # MACD 動能
    dif, _, _ = calculate_macd(df['Close'])
    dif_now = float(dif.iloc[-1])
    dif_prev = float(dif.iloc[-2])

    result = None

    # 底部轉勢
    if (pos['from_high_pct'] <= BOTTOM_PARAMS['from_high_pct']
        and cons['range_pct'] < BOTTOM_PARAMS['consolidation_range']
        and vol['vol_ratio'] >= BOTTOM_PARAMS['volume_ratio']
        and dif_now > dif_prev):

        has_div = has_pivot_divergence(df, 'bottom')

        result = {
            'type': '底部轉勢',
            'hasDivergence': has_div,
            'from_high_pct': pos['from_high_pct'],
            'from_low_pct': pos['from_low_pct'],
            'consolidation_range': cons['range_pct'],
            'consolidation_days': 30,
            'vol_ratio': vol['vol_ratio'],
            'macd_dif': round(dif_now, 4),
        }

    # 頂部轉勢
    elif (pos['from_low_pct'] >= TOP_PARAMS['from_low_pct']
        and cons['range_pct'] < TOP_PARAMS['consolidation_range']
        and vol['vol_ratio'] >= TOP_PARAMS['volume_ratio']
        and dif_now < dif_prev):

        has_div = has_pivot_divergence(df, 'top')

        result = {
            'type': '頂部轉勢',
            'hasDivergence': has_div,
            'from_high_pct': pos['from_high_pct'],
            'from_low_pct': pos['from_low_pct'],
            'consolidation_range': cons['range_pct'],
            'consolidation_days': 30,
            'vol_ratio': vol['vol_ratio'],
            'macd_dif': round(dif_now, 4),
        }

    if not result:
        return None

    result['ticker'] = ticker
    result['price'] = round(current, 2)
    return result


# ==================== 主程式 ====================

def process_stocks():
    tickers = get_all_us_stocks()
    total_scanned = len(tickers)
    success_count = 0
    failed_count = 0

    print(f"🚀 [階段 1/2] 下載 {total_scanned} 隻日線數據（252 日）...")

    candidates = []
    batch_size = 100

    for i in range(0, total_scanned, batch_size):
        batch = tickers[i:i + batch_size]
        try:
            daily_data = yf.download(batch, period="1y", interval="1d",
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

                    if df is None or len(df) < 252:
                        failed_count += 1
                        continue

                    latest_price = float(df['Close'].iloc[-1])
                    if latest_price < 2.0:
                        success_count += 1
                        continue

                    vol_today = float(df['Volume'].iloc[-1])
                    if vol_today < 20000:
                        success_count += 1
                        continue

                    result = screen_stock(ticker, df)
                    if result:
                        candidates.append(result)

                    success_count += 1
                except Exception:
                    failed_count += 1
                    continue
        except Exception as e:
            print(f"⚠️ Batch {i} 失敗: {e}")
            failed_count += len(batch)
            continue

        if i % 1000 == 0:
            print(f"  進度：{i}/{total_scanned}，候選 {len(candidates)} 隻")
        time.sleep(0.1)

    print(f"✅ 階段 1 完成！候選 {len(candidates)} 隻")

    print("🚀 [階段 2/2] 下載市值...")
    results = []

    for c in candidates:
        ticker = c['ticker']
        mcap_raw = get_market_cap(ticker, c['price'])
        mcap_str, mcap_num = format_market_cap(mcap_raw)

        futu_url = f"https://www.futunn.com/hk/stock/{ticker}-US"
        tradingview_url = f"https://www.tradingview.com/symbols/{ticker}/"

        results.append({
            'ticker': ticker,
            'price': c['price'],
            'marketCap': mcap_str,
            'marketCapNum': float(mcap_num),
            'type': c['type'],
            'hasDivergence': c['hasDivergence'],
            'fromHighPct': c['from_high_pct'],
            'fromLowPct': c['from_low_pct'],
            'consolidationRange': c['consolidation_range'],
            'consolidationDays': c['consolidation_days'],
            'volRatio': c['vol_ratio'],
            'macdDif': c['macd_dif'],
            'futuUrl': futu_url,
            'tvUrl': tradingview_url,
        })

    # 排序：有背離優先 + 量比高
    results.sort(key=lambda x: (
        0 if x['hasDivergence'] else 1,
        0 if x['type'] == '底部轉勢' else 1,
        -x['volRatio']
    ))

    hkt = timezone(timedelta(hours=8))
    now_hkt = datetime.now(hkt).strftime("%Y-%m-%d %H:%M")

    bottom_count = sum(1 for r in results if r['type'] == '底部轉勢')
    top_count = sum(1 for r in results if r['type'] == '頂部轉勢')
    div_count = sum(1 for r in results if r['hasDivergence'])

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
