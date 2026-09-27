import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import time
from datetime import datetime, timezone, timedelta

# 關閉 yfinance 快取以避免 GitHub Actions 出現 database is locked 錯誤
yf.set_tz_cache_location("/tmp/yf_cache")

# 1. 計算 MACD 及檢測背離 (DIF 快線設定為 5)
def check_macd_divergence(df):
    if df is None or len(df) < 35:
        return "無"
    
    close = df['Close'].squeeze()
    
    # 計算 MACD (5, 26, 9)
    exp1 = close.ewm(span=5, adjust=False).mean()
    exp2 = close.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal

    # 取得最新 3 根 K 線數據
    h0, h1, h2 = hist.iloc[-1], hist.iloc[-2], hist.iloc[-3]
    c0, c1, c2 = close.iloc[-1], close.iloc[-2], close.iloc[-3]

    # 底背離條件
    if (c0 < c1 or c0 < c2) and (h0 > h1 and h1 < h2) and h0 < 0:
        return "底背離"
    
    # 頂背離條件
    if (c0 > c1 or c0 > c2) and (h0 < h1 and h1 > h2) and h0 > 0:
        return "頂背離"

    return "無"

# 2. 格式化市值數值
def format_market_cap(market_cap):
    if market_cap is None or np.isnan(market_cap) or market_cap <= 0:
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

# 3. 穩健獲取單隻股市值 (帶三重備援)
def get_single_market_cap(ticker_symbol, latest_price):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    # 嘗試 1: Yahoo Quote v6 API
    try:
        url = f"https://query2.finance.yahoo.com/v6/finance/quoteSummary/{ticker_symbol}?modules=price"
        res = requests.get(url, headers=headers, timeout=3)
        if res.status_code == 200:
            mcap = res.json()['quoteSummary']['result'][0]['price'].get('marketCap', {}).get('raw')
            if mcap and mcap > 0:
                return mcap
    except Exception:
        pass

    # 嘗試 2: yfinance fast_info
    try:
        t = yf.Ticker(ticker_symbol)
        mcap = t.fast_info.get('market_cap', None)
        if mcap and not np.isnan(mcap) and mcap > 0:
            return mcap
    except Exception:
        pass

    # 嘗試 3: 用總股本 * 最新價格計算估算市值
    try:
        t = yf.Ticker(ticker_symbol)
        shares = t.fast_info.get('shares', None)
        if shares and shares > 0 and latest_price > 0:
            return shares * latest_price
    except Exception:
        pass

    return None

# 4. 獲取全美股上市股票名單 (自動過濾 ETF / 優先股 / 權證)
def get_all_us_stocks():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    tickers = set()

    try:
        url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/all/all_tickers.txt"
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            lines = res.text.splitlines()
            for line in lines:
                sym = line.strip().upper()
                if sym and sym.isalpha() and len(sym) <= 5:
                    tickers.add(sym)
            print(f"✅ 成功獲取 {len(tickers)} 隻全美股股票標的")
    except Exception:
        pass

    if not tickers:
        try:
            url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=15000&download=true"
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 200:
                rows = res.json().get('data', {}).get('rows', [])
                for r in rows:
                    sym = str(r.get('symbol', '')).strip().upper()
                    asset_type = str(r.get('assetClass', '')).lower()
                    if 'etf' not in asset_type and sym and sym.isalpha() and len(sym) <= 5:
                        tickers.add(sym)
        except Exception:
            pass

    if not tickers:
        tickers = {
            "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX", "INTC",
            "BABA", "PDD", "AVGO", "ORCL", "CRM", "COST", "PEP", "TMUS", "CSCO", "PLTR",
            "ARM", "SMCI", "COIN", "MSTR", "UBER", "ABNB", "DIS", "NKE", "JPM", "BAC"
        }

    return sorted(list(tickers))

# 5. 主執行邏輯
def process_stocks():
    tickers = get_all_us_stocks()
    total_scanned = len(tickers)
    success_count = 0
    failed_count = 0
    
    print(f"🚀 [階段 1/2] 開始分批下載 {total_scanned} 隻全美股日線數據 (篩選條件：股價 ≥ $2.0、單日成交量 ≥ 20k、成交量放大 ≥ 2 倍 或 具 MACD 背離)...")
    
    candidates = []
    batch_size = 200

    for i in range(0, total_scanned, batch_size):
        batch = tickers[i:i + batch_size]
        try:
            daily_data = yf.download(batch, period="60d", interval="1d", group_by='ticker', threads=True, progress=False)

            for ticker in batch:
                try:
                    df = daily_data[ticker].dropna(how='all') if len(batch) > 1 else daily_data.dropna(how='all')
                    if df is None or len(df) < 30:
                        failed_count += 1
                        continue
                    
                    latest_price = float(df['Close'].iloc[-1])
                    # 條件 1：剔除股價低於 $2.0 的股票
                    if latest_price < 2.0:
                        success_count += 1
                        continue

                    vol_today = float(df['Volume'].iloc[-1])
                    vol_5d_avg = float(df['Volume'].iloc[-6:-1].mean())

                    # 條件 2：剔除單日成交量少於 20,000 股的股票
                    if vol_today < 20000:
                        success_count += 1
                        continue

                    day_div = check_macd_divergence(df)
                    
                    # 計算成交量（換手倍率）放大倍數：今日成交量 / 5日平均成交量
                    vol_ratio = round(vol_today / vol_5d_avg, 2) if vol_5d_avg > 0 else 1.0

                    # 條件 3：只要有 MACD 背離，或者換手/成交量放大 2 倍以上 (vol_ratio >= 2.0)
                    if day_div != "無" or vol_ratio >= 2.0:
                        candidates.append({
                            "ticker": ticker,
                            "price": round(latest_price, 2),
                            "dayDiv": day_div,
                            "vol_today": vol_today,
                            "vol_ratio": vol_ratio
                        })
                    success_count += 1
                except Exception:
                    failed_count += 1
                    continue
        except Exception:
            failed_count += len(batch)
            continue

        time.sleep(0.2)

    print(f"✅ 階段 1 完成！篩選出 {len(candidates)} 隻候選股票。")

    print("🚀 [階段 2/2] 正在下載周線/月線數據並計算市值...")
    cand_tickers = [c["ticker"] for c in candidates]
    results = []

    if cand_tickers:
        week_data = yf.download(cand_tickers, period="1y", interval="1wk", group_by='ticker', threads=True, progress=False)
        month_data = yf.download(cand_tickers, period="3y", interval="1mo", group_by='ticker', threads=True, progress=False)

        for item in candidates:
            ticker = item["ticker"]
            try:
                df_week = week_data[ticker].dropna(how='all') if len(cand_tickers) > 1 else week_data.dropna(how='all')
                df_month = month_data[ticker].dropna(how='all') if len(cand_tickers) > 1 else month_data.dropna(how='all')

                day_div = item["dayDiv"]
                week_div = check_macd_divergence(df_week)
                month_div = check_macd_divergence(df_month)

                mcap_raw = get_single_market_cap(ticker, item["price"])
                mcap_str, mcap_num = format_market_cap(mcap_raw)

                # 黃金策略標籤：任一週期底背離 + 換手/成交量放大 2 倍以上 (vol_ratio >= 2.0)
                has_bottom_div = (day_div == "底背離" or week_div == "底背離" or month_div == "底背離")
                match_strategy = bool((item["vol_ratio"] >= 2.0) and has_bottom_div)
                
                futu_url = f"https://www.futunn.com/hk/stock/{ticker}-US"

                results.append({
                    "ticker": ticker,
                    "name": ticker,
                    "price": item["price"],
                    "marketCap": mcap_str,
                    "marketCapNum": mcap_num,
                    "dayDiv": day_div,
                    "weekDiv": week_div,
                    "monthDiv": month_div,
                    "turnover": f"{round(item['vol_today']/1000, 1)}K",  # 顯示今日成交量 (千股)
                    "turnoverDiff": 0.0,
                    "volumeRatio": item["vol_ratio"],                   # 換手/成交量放大倍數 (比平時大 X 倍)
                    "matchStrategy": match_strategy,
                    "futuUrl": futu_url
                })
            except Exception:
                continue

    hkt = timezone(timedelta(hours=8))
    now_hkt = datetime.now(hkt).strftime("%Y-%m-%d %H:%M")

    output_data = {
        "stats": {
            "totalScanned": total_scanned,
            "successCount": success_count,
            "failedCount": failed_count,
            "matchedCount": len(results),
            "lastUpdated": now_hkt
        },
        "stocks": results
    }

    with open("stocks_data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"🎉 成功寫入 {len(results)} 條數據至 stocks_data.json！更新時間 (HKT): {now_hkt}")

if __name__ == "__main__":
    process_stocks()
