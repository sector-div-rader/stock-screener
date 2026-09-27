import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import io
from datetime import datetime, timezone, timedelta

# 關閉 yfinance 快取以避免 GitHub Actions 出現 database is locked 錯誤
yf.set_tz_cache_location("/tmp/yf_cache")

# 1. 計算 MACD 及檢測背離 (DIF 快線已調整為 5)
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

    # 底背離條件：價格創新低，但 MACD 柱狀圖回升
    if (c0 < c1 or c0 < c2) and (h0 > h1 and h1 < h2) and h0 < 0:
        return "底背離"
    
    # 頂背離條件：價格創新高，但 MACD 柱狀圖回落
    if (c0 > c1 or c0 > c2) and (h0 < h1 and h1 > h2) and h0 > 0:
        return "頂背離"

    return "無"

# 2. 格式化市值數值 (例如：$1.5T, $250.5B, $800M)
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

# 4. 獲取美股熱門標的名單 (相容性最佳化，防止 403 及 FutureWarning)
def get_us_stock_list():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        req1 = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers=headers)
        req2 = requests.get('https://en.wikipedia.org/wiki/NASDAQ-100', headers=headers)
        
        # 使用 StringIO 包裹防止 Pandas 警告
        sp500_df = pd.read_html(io.StringIO(req1.text))[0]
        sp500 = sp500_df['Symbol'].tolist()
        
        nasdaq_tables = pd.read_html(io.StringIO(req2.text))
        nasdaq100 = []
        for df in nasdaq_tables:
            for col in ['Ticker', 'Symbol']:
                if col in df.columns:
                    nasdaq100.extend(df[col].tolist())
                    break

        tickers = list(set(sp500 + nasdaq100))
        tickers = [t.replace('.', '-') for t in tickers if isinstance(t, str)]
        print(f"✅ 成功獲取線上美股名單共 {len(tickers)} 隻")
        return tickers
    except Exception as e:
        print(f"⚠️ 獲取線上名單失敗 ({e})，自動切換至美股核心備用名單")
        return [
            "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B", "UNH", "JNJ",
            "JPM", "V", "PG", "XOM", "MA", "HD", "CVX", "MRK", "ABBV", "LLY",
            "PEP", "KO", "BAC", "COST", "WMT", "TMO", "MCD", "CSCO", "ACN", "ABT",
            "PFE", "ORCL", "DHR", "CMCSA", "AMD", "DIS", "ADBE", "TXN", "PM", "NKE",
            "CRM", "WFC", "UNP", "UPS", "BMY", "VZ", "QCOM", "AMGN", "MS", "RTX",
            "HON", "IBM", "LOW", "INTC", "SPGI", "COP", "CAT", "LMT", "BA", "AXP",
            "GE", "SBUX", "DE", "AMAT", "BLK", "NOW", "PLD", "GILD", "MDLZ", "T",
            "ADI", "TJX", "C", "ISRG", "ELV", "MMC", "LRCX", "SCHW", "SYK", "BKNG",
            "VRTX", "ZTS", "PGR", "REGN", "CI", "PANW", "SLB", "BDX", "BSX", "TMUS",
            "CB", "ADP", "ITW", "NOC", "AON", "FI", "WM", "CSX", "HUM", "CL",
            "FCX", "CME", "SNPS", "MCO", "EW", "CDNS", "MCK", "SHW", "EMR", "NSC",
            "BABA", "PDD", "BIDU", "JD", "NTES", "NIO", "XPEV", "LI", "FUTU", "PLTR",
            "ARM", "SMCI", "COIN", "MSTR", "UBER", "ABNB", "CRWD", "RBLX", "U"
        ]

# 5. 主執行邏輯
def process_stocks():
    tickers = get_us_stock_list()
    
    print("🚀 [階段 1/2] 正在批量下載日線數據並初步篩選...")
    daily_data = yf.download(tickers, period="60d", interval="1d", group_by='ticker', threads=True, progress=False)

    candidates = []

    for ticker in tickers:
        try:
            df = daily_data[ticker].dropna(how='all') if len(tickers) > 1 else daily_data.dropna(how='all')
            if len(df) < 30:
                continue
            
            day_div = check_macd_divergence(df)
            latest_price = float(df['Close'].iloc[-1])
            vol_today = float(df['Volume'].iloc[-1])
            vol_5d_avg = float(df['Volume'].iloc[-6:-1].mean())

            vol_ratio = round(vol_today / vol_5d_avg, 2) if vol_5d_avg > 0 else 1.0
            turnover_diff = round((vol_today - vol_5d_avg) / vol_5d_avg * 100, 2) if vol_5d_avg > 0 else 0.0

            if day_div != "無" or turnover_diff >= 20.0 or vol_ratio >= 2.0:
                candidates.append({
                    "ticker": ticker,
                    "price": round(latest_price, 2),
                    "dayDiv": day_div,
                    "vol_today": vol_today,
                    "vol_ratio": vol_ratio,
                    "turnover_diff": turnover_diff
                })
        except Exception:
            continue

    print(f"✅ 階段 1 完成！共篩選出 {len(candidates)} 隻候選股票。")

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

                has_bottom_div = (day_div == "底背離" or week_div == "底背離" or month_div == "底背離")
                match_strategy = bool((item["turnover_diff"] >= 20.0) and (item["vol_ratio"] >= 2.0) and has_bottom_div)
                
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
                    "turnover": f"{round(item['vol_today']/1000000, 2)}M",
                    "turnoverDiff": item["turnover_diff"],
                    "volumeRatio": item["vol_ratio"],
                    "matchStrategy": match_strategy,
                    "futuUrl": futu_url
                })
            except Exception as e:
                continue

    hkt = timezone(timedelta(hours=8))
    now_hkt = datetime.now(hkt).strftime("%Y-%m-%d %H:%M")

    output_data = {
        "updatedAt": now_hkt,
        "stocks": results
    }

    with open("stocks_data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"🎉 成功寫入 {len(results)} 條數據至 stocks_data.json！更新時間 (HKT): {now_hkt}")

if __name__ == "__main__":
    process_stocks()
