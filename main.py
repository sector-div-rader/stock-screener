# main.py - 美股盤整突破轉勢掃描器 V23.0
# ============================================
# V23.0 新功能：
#   1. 歷史紀錄（history.csv）
#   2. 強度評分（⭐ / ⭐⭐ / ⭐⭐⭐）
#   3. 連續訊號（N 日內出現 M 次）
#   4. 財報日期警告（3 日內有財報）
#   5. 更新 T+1 / T+3 / T+5 升跌幅
# ============================================

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import os
import time
import logging
from datetime import datetime, timezone, timedelta
from scipy.signal import find_peaks

yf.set_tz_cache_location("/tmp/yf_cache")
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# ==================== 參數 ====================

BOTTOM_PARAMS = {
    'from_high_pct': -20,
    'consolidation_days': 30,
    'consolidation_range': 20,
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

INFO_DELAY = 1.5
INFO_BATCH_REST = 10
INFO_REST_SEC = 10

# ==================== 技術指標 ====================

def calculate_macd(close, fast=5, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = dif - dea
    return dif, dea, hist


def check_52w_position(df):
    if len(df) < 200:
        return None
    high_52w = float(df['High'].max())
    low_52w = float(df['Low'].min())
    current = float(df['Close'].iloc[-1])
    if high_52w <= 0 or low_52w <= 0:
        return None
    return {
        'from_high_pct': round((current - high_52w) / high_52w * 100, 1),
        'from_low_pct': round((current - low_52w) / low_52w * 100, 1),
    }


def check_consolidation(df, days=30):
    if len(df) < days + 5:
        return None
    recent = df.tail(days)
    high = float(recent['High'].max())
    low = float(recent['Low'].min())
    if low <= 0:
        return None
    return {'range_pct': round((high - low) / low * 100, 1)}


def check_volume_breakout(df, days=30, ratio=1.5):
    if len(df) < days + 2:
        return None
    vol_today = float(df['Volume'].iloc[-1])
    vol_avg = float(df['Volume'].tail(days).mean())
    if vol_avg <= 0:
        return None
    return {'vol_ratio': round(min(vol_today / vol_avg, 50), 2)}


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


# ==================== 強度評分 ====================

def get_strength(has_div, vol_ratio, cons_range):
    """強度評分（1B）
    ⭐⭐⭐ = 有背離 + 量比 ≥ 2.0 + 盤整 < 10%
    ⭐⭐  = 有背離 + 量比 ≥ 1.5
    ⭐   = 其他
    """
    if has_div and vol_ratio >= 2.0 and cons_range < 10:
        return '⭐⭐⭐', 3
    elif has_div and vol_ratio >= 1.5:
        return '⭐⭐', 2
    else:
        return '⭐', 1


# ==================== 連續訊號 ====================

def load_history():
    """讀取 history.csv"""
    if not os.path.exists('history.csv'):
        return pd.DataFrame()
    try:
        return pd.read_csv('history.csv', encoding='utf-8-sig')
    except Exception:
        return pd.DataFrame()


def get_consecutive_count(ticker, history_df, days=7):
    """計 N 日內出現幾多次"""
    if history_df.empty:
        return 0
    
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    recent = history_df[
        (history_df['Ticker'] == ticker) &
        (history_df['日期'].astype(str) >= cutoff)
    ]
    return len(recent)


# ==================== 財報日期 ====================

def get_earnings_warning(info):
    """如果 3 日內有財報 → 返回 True"""
    try:
        ts = info.get('earningsTimestamp')
        if not ts:
            return False
        earnings_date = datetime.fromtimestamp(ts).date()
        today = datetime.now().date()
        diff = (earnings_date - today).days
        return 0 <= diff <= 3
    except Exception:
        return False


# ==================== 篩選邏輯 ====================

def screen_stock(ticker, df):
    if df is None or len(df) < 200:
        return None

    current = float(df['Close'].iloc[-1])

    pos = check_52w_position(df)
    if not pos:
        return None

    cons = check_consolidation(df, days=30)
    if not cons:
        return None
    if cons['range_pct'] >= BOTTOM_PARAMS['consolidation_range']:
        return None

    vol = check_volume_breakout(df, days=30, ratio=BOTTOM_PARAMS['volume_ratio'])
    if not vol:
        return None
    if vol['vol_ratio'] < BOTTOM_PARAMS['volume_ratio']:
        return None

    dif, _, _ = calculate_macd(df['Close'])
    dif_now = float(dif.iloc[-1])
    dif_prev = float(dif.iloc[-2])

    result = None

    if (pos['from_high_pct'] <= BOTTOM_PARAMS['from_high_pct']
        and dif_now > dif_prev):
        has_div = has_pivot_divergence(df, 'bottom')
        strength_str, strength_num = get_strength(has_div, vol['vol_ratio'], cons['range_pct'])
        result = {
            'ticker': ticker,
            'price': round(current, 2),
            'type': '底部轉勢',
            'hasDivergence': has_div,
            'strength': strength_str,
            'strengthNum': strength_num,
            'fromHighPct': pos['from_high_pct'],
            'fromLowPct': pos['from_low_pct'],
            'consolidationRange': cons['range_pct'],
            'volRatio': vol['vol_ratio'],
            'macdDif': round(dif_now, 4),
        }

    elif (pos['from_low_pct'] >= TOP_PARAMS['from_low_pct']
        and dif_now < dif_prev):
        has_div = has_pivot_divergence(df, 'top')
        strength_str, strength_num = get_strength(has_div, vol['vol_ratio'], cons['range_pct'])
        result = {
            'ticker': ticker,
            'price': round(current, 2),
            'type': '頂部轉勢',
            'hasDivergence': has_div,
            'strength': strength_str,
            'strengthNum': strength_num,
            'fromHighPct': pos['from_high_pct'],
            'fromLowPct': pos['from_low_pct'],
            'consolidationRange': cons['range_pct'],
            'volRatio': vol['vol_ratio'],
            'macdDif': round(dif_now, 4),
        }

    return result


# ==================== 攞 sector + 財報 ====================

def enrich_with_info(stock):
    ticker = stock['ticker']
    try:
        info = yf.Ticker(ticker).info
        sector = info.get('sector')
        stock['sector'] = sector if sector else None
        stock['earningsWarning'] = get_earnings_warning(info)
    except Exception:
        stock['sector'] = None
        stock['earningsWarning'] = False
    return stock


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


# ==================== 更新歷史 T+1 / T+3 / T+5 ====================

def update_history_prices():
    """更新 history.csv 嘅 T+1 / T+3 / T+5 收盤價"""
    if not os.path.exists('history.csv'):
        return

    df = pd.read_csv('history.csv', encoding='utf-8-sig')
    today = datetime.now(timezone(timedelta(hours=8))).date()
    updated = False

    for idx, row in df.iterrows():
        ticker = row['Ticker']
        entry_date_str = str(row['日期'])

        try:
            entry_date = datetime.strptime(entry_date_str, '%Y-%m-%d').date()
        except Exception:
            continue

        days_since = (today - entry_date).days
        if days_since <= 0:
            continue

        # 攞 ticker 歷史數據
        try:
            ticker_df = yf.download(ticker, period='60d', interval='1d', progress=False)
            if ticker_df is None or len(ticker_df) == 0:
                continue

            # 搵 entry_date 之後嘅數據
            ticker_df = ticker_df.reset_index()
            ticker_df['Date'] = pd.to_datetime(ticker_df['Date']).dt.date

            after = ticker_df[ticker_df['Date'] > entry_date]
            if len(after) == 0:
                continue

            entry_price = float(row['進場價'])

            # T+1
            if pd.isna(row.get('T+1收盤')) or row.get('T+1收盤') == '':
                if len(after) >= 1:
                    t1 = float(after.iloc[0]['Close'])
                    df.at[idx, 'T+1收盤'] = round(t1, 2)
                    df.at[idx, 'T+1升跌%'] = round((t1 - entry_price) / entry_price * 100, 2)
                    updated = True

            # T+3
            if pd.isna(row.get('T+3收盤')) or row.get('T+3收盤') == '':
                if len(after) >= 3:
                    t3 = float(after.iloc[2]['Close'])
                    df.at[idx, 'T+3收盤'] = round(t3, 2)
                    df.at[idx, 'T+3升跌%'] = round((t3 - entry_price) / entry_price * 100, 2)
                    updated = True

            # T+5
            if pd.isna(row.get('T+5收盤')) or row.get('T+5收盤') == '':
                if len(after) >= 5:
                    t5 = float(after.iloc[4]['Close'])
                    df.at[idx, 'T+5收盤'] = round(t5, 2)
                    df.at[idx, 'T+5升跌%'] = round((t5 - entry_price) / entry_price * 100, 2)
                    updated = True

        except Exception as e:
            print(f"  ⚠️ {ticker} 更新失敗: {e}")
            continue

    if updated:
        df.to_csv('history.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 更新 history.csv")
    else:
        print(f"ℹ️ history.csv 冇新數據需要更新")


# ==================== 寫入歷史 ====================

def save_history(results):
    """寫入新訊號到 history.csv"""
    today = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    
    rows = []
    for r in results:
        rows.append({
            '日期': today,
            'Ticker': r['ticker'],
            '類型': r['type'],
            '進場價': r['price'],
            '距52W高': r.get('fromHighPct', ''),
            '距52W低': r.get('fromLowPct', ''),
            '盤整': r['consolidationRange'],
            '量比': r['volRatio'],
            '背離': '⭐' if r.get('hasDivergence') else '',
            '強度': r.get('strength', '⭐'),
            'T+1收盤': '',
            'T+1升跌%': '',
            'T+3收盤': '',
            'T+3升跌%': '',
            'T+5收盤': '',
            'T+5升跌%': '',
        })
    
    if rows:
        new_df = pd.DataFrame(rows)
        if os.path.exists('history.csv'):
            try:
                old_df = pd.read_csv('history.csv', encoding='utf-8-sig')
                old_df = old_df[old_df['日期'].astype(str) != today]
                combined = pd.concat([old_df, new_df], ignore_index=True)
            except Exception:
                combined = new_df
        else:
            combined = new_df
        
        combined.to_csv('history.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 寫入 history.csv ({len(rows)} 行)")


# ==================== 主程式 ====================

def process_stocks():
    tickers = get_all_us_stocks()
    total_scanned = len(tickers)
    success_count = 0
    failed_count = 0

    # 讀歷史
    history_df = load_history()
    print(f"📚 讀 history.csv：{len(history_df)} 行")

    print(f"🚀 [階段 1/3] 下載 {total_scanned} 隻 1y 日線數據...")

    results = []

    for i in range(0, total_scanned, BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
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

                    if df is None or len(df) < 200:
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
                        result['futuUrl'] = f"https://www.futunn.com/hk/stock/{ticker}-US"
                        result['tvUrl'] = f"https://www.tradingview.com/symbols/{ticker}/"
                        result['sector'] = None
                        result['earningsWarning'] = False
                        # 連續訊號
                        result['consecutiveCount'] = get_consecutive_count(ticker, history_df, days=7)
                        results.append(result)

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
            print(f"  進度：{i}/{total_scanned}，候選 {len(results)} 隻")

    print(f"✅ 階段 1 完成！候選 {len(results)} 隻")

    # ===== 階段 2：攞 sector + 財報 =====
    print(f"🚀 [階段 2/3] 用 info 攞 sector + 財報（{len(results)} 隻）...")

    for i, stock in enumerate(results):
        enrich_with_info(stock)
        time.sleep(INFO_DELAY)
        if (i + 1) % INFO_BATCH_REST == 0:
            print(f"      進度：{i+1}/{len(results)}，休息 {INFO_REST_SEC} 秒")
            time.sleep(INFO_REST_SEC)

    # ===== 階段 3：更新歷史 T+1/T+3/T+5 =====
    print(f"🚀 [階段 3/3] 更新歷史紀錄（T+1/T+3/T+5）...")
    update_history_prices()

    # 寫入新訊號
    save_history(results)

    # 排序
    results.sort(key=lambda x: (
        -x.get('strengthNum', 0),
        0 if x.get('hasDivergence') else 1,
        0 if x['type'] == '底部轉勢' else 1,
        -x.get('volRatio', 0)
    ))

    hkt = timezone(timedelta(hours=8))
    now_hkt = datetime.now(hkt).strftime("%Y-%m-%d %H:%M")

    bottom_count = sum(1 for r in results if r['type'] == '底部轉勢')
    top_count = sum(1 for r in results if r['type'] == '頂部轉勢')
    div_count = sum(1 for r in results if r.get('hasDivergence'))
    warn_count = sum(1 for r in results if r.get('earningsWarning'))

    output = {
        "stats": {
            "lastUpdated": now_hkt,
            "totalScanned": total_scanned,
            "successCount": success_count,
            "bottomCount": bottom_count,
            "topCount": top_count,
            "divergenceCount": div_count,
            "earningsWarningCount": warn_count,
            "matchedCount": len(results),
        },
        "stocks": results
    }

    with open("stocks_data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"🎉 完成！底部 {bottom_count} 隻、頂部 {top_count} 隻（有背離 {div_count} 隻，財報警告 {warn_count} 隻）")
    print(f"   總共 {len(results)} 隻，更新時間：{now_hkt}")


if __name__ == "__main__":
    process_stocks()
