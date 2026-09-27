import pandas as pd
import numpy as np
import yfinance as yf
import json
import time
from datetime import datetime

# 1. 獲取美股個股清單 (排除 ETF)
def get_us_stock_list():
    print("正在從官方 FTP 獲取全美股上市個股清單 (過濾 ETF)...")
    tickers = set()
    
    try:
        nasdaq_url = "ftp://ftp.nasdaqtrader.com/SymbolDirectory/nasdaqlisted.txt"
        df_nasdaq = pd.read_csv(nasdaq_url, sep="|")
        
        other_url = "ftp://ftp.nasdaqtrader.com/SymbolDirectory/otherlisted.txt"
        df_other = pd.read_csv(other_url, sep="|")
        
        if 'ETF' in df_nasdaq.columns:
            df_nasdaq = df_nasdaq[df_nasdaq['ETF'] != 'Y']
            
        if 'ETF' in df_other.columns:
            df_other = df_other[df_other['ETF'] != 'Y']

        nasdaq_symbols = df_nasdaq['Symbol'].dropna().tolist()
        other_symbols = df_other['ACT Symbol'].dropna().tolist()
        
        all_symbols = nasdaq_symbols + other_symbols
        
        for symbol in all_symbols:
            symbol = str(symbol).strip()
            if (symbol and len(symbol) <= 5 and symbol.isalpha() 
                and not symbol.startswith('File') 
                and not symbol.startswith('Total')):
                tickers.add(symbol)
                
        print(f"✅ 成功獲取 {len(tickers)} 隻全美股上市公司代號 (已排除 ETF)。")
    except Exception as e:
        print(f"❌ 官方 FTP 獲取失敗: {e}，切換至備用清單...")
        fallback = [
            "NVDA", "TSLA", "AMD", "AAPL", "PLTR", "MSFT", "AMZN", "META", "SMCI", 
            "GOOGL", "INTC", "NFLX", "AVGO", "COST", "QCOM", "TXN", "SHOP", "LLY",
            "BABA", "PDD", "BIDU", "JD", "NIO", "XPEV", "COIN", "MSTR", "ARM", "MU"
        ]
        tickers.update(fallback)

    return sorted(list(tickers))

# 2. 計算 MACD DIF 與背離型態
def check_macd_divergence(df_kline):
    if df_kline is None or len(df_kline) < 35:
        return "無"
    
    close = df_kline['Close']
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    
    recent_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-15:-1].min())
    recent_dif = float(dif.iloc[-1])
    prev_dif = float(dif.iloc[-15:-1].min())
    
    if recent_close < prev_close and recent_dif > prev_dif and recent_dif < 0:
        return "底背離"
    elif recent_close > float(close.iloc[-15:-1].max()) and recent_dif < float(dif.iloc[-15:-1].max()) and recent_dif > 0:
        return "頂背離"
    return "無"

# 格式化市值數值 (例如：$1.5T, $250.5B, $800M)
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

# 真·分批獲取市值數據（避免單隻重複請求）
def get_batch_market_caps(batch_tickers):
    market_caps = {}
    try:
        tickers_obj = yf.Tickers(' '.join(batch_tickers))
        for symbol in batch_tickers:
            try:
                # 直接讀取 fast_info 緩存
                mcap = tickers_obj.tickers[symbol].fast_info.get('market_cap', None)
                market_caps[symbol] = mcap
            except Exception:
                market_caps[symbol] = None
    except Exception:
        pass
    return market_caps

# 3. 核心數據處理
def process_stocks():
    tickers = get_us_stock_list()
    results = []
    total_scanned = len(tickers)
    success_count = 0
    failed_count = 0
    
    print(f"🚀 開始全美股個股掃描，共計 {total_scanned} 隻股票...")
    
    # 建議將批次大小適當調小至 100，提升 API 穩定度
    batch_size = 100
    candidates = []

    # 第一階段：全美股日線批次下載 (過濾價格與成交量)
    for i in range(0, total_scanned, batch_size):
        batch_tickers = tickers[i:i + batch_size]
        print(f"階段 1/2: [{min(i + batch_size, total_scanned)}/{total_scanned}] 檢查日線量價與市值...")
        
        try:
            # 1. 批次下載價格數據
            data = yf.download(batch_tickers, period="3mo", interval="1d", group_by='ticker', threads=True, progress=False)
            
            # 2. 批次一次過抓取該 Batch 的市值
            mcap_dict = get_batch_market_caps(batch_tickers)

            for ticker in batch_tickers:
                try:
                    df_day = data[ticker].dropna(how='all') if len(batch_tickers) > 1 else data.dropna(how='all')
                    
                    if df_day is None or len(df_day) < 35:
                        failed_count += 1
                        continue
                        
                    price = round(float(df_day['Close'].iloc[-1]), 2)
                    if price < 2.0:
                        success_count += 1
                        continue

                    vol_today = float(df_day['Volume'].iloc[-1])
                    vol_yesterday = float(df_day['Volume'].iloc[-2])
                    if vol_today < 50000:
                        success_count += 1
                        continue

                    vol_ratio = round(vol_today / vol_yesterday, 2) if vol_yesterday > 0 else 1.0
                    turnover_diff = round(((vol_today - vol_yesterday) / vol_yesterday) * 100, 1) if vol_yesterday > 0 else 0.0
                    
                    # 計算日線 MACD 背離
                    day_div = check_macd_divergence(df_day)

                    # 從批次字典讀取市值，不再發起獨立 HTTP 請求
                    mcap_raw = mcap_dict.get(ticker, None)
                    mcap_str, mcap_num = format_market_cap(mcap_raw)

                    candidates.append({
                        "ticker": ticker,
                        "price": price,
                        "vol_today": vol_today,
                        "vol_ratio": vol_ratio,
                        "turnover_diff": turnover_diff,
                        "marketCapStr": mcap_str,
                        "marketCapNum": mcap_num,
                        "dayDiv": day_div
                    })
                    success_count += 1
                except Exception:
                    failed_count += 1
                    continue
        except Exception:
            failed_count += len(batch_tickers)
            continue
            
        time.sleep(0.5)

    print(f"✅ 第一階段完成！共 {len(candidates)} 隻股票通過初步篩選，開始批次計算周與月 MACD 背離...")

    # 第二階段：批次計算周線與月線 MACD 背離
    cand_tickers = [c["ticker"] for c in candidates]
    
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

                # 黃金策略：成交量暴增 且 在日/周/月中出現任一下影底背離
                has_bottom_div = (day_div == "底背離" or week_div == "底背離" or month_div == "底背離")
                match_strategy = bool((item["turnover_diff"] >= 20.0) and (item["vol_ratio"] >= 2.0) and has_bottom_div)
                
                futu_url = f"https://www.futunn.com/hk/stock/{ticker}-US"

                if match_strategy or day_div != "無" or week_div != "無" or month_div != "無" or (item["turnover_diff"] >= 20.0 and item["vol_ratio"] >= 2.0):
                    results.append({
                        "ticker": ticker,
                        "name": ticker,
                        "price": item["price"],
                        "marketCap": item["marketCapStr"],
                        "marketCapNum": item["marketCapNum"],
                        "dayDiv": day_div,
                        "weekDiv": week_div,
                        "monthDiv": month_div,
                        "turnover": f"{round(item['vol_today']/1000000, 2)}M",
                        "turnoverDiff": item["turnover_diff"],
                        "volumeRatio": item["vol_ratio"],
                        "matchStrategy": match_strategy,
                        "futuUrl": futu_url
                    })
            except Exception:
                continue

    print(f"✅ 全美股掃描完成！總數: {total_scanned}, 成功: {success_count}, 失敗: {failed_count}")

    output_data = {
        "stats": {
            "totalScanned": total_scanned,
            "successCount": success_count,
            "failedCount": failed_count,
            "matchedCount": len(results),
            "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M")
        },
        "stocks": results
    }

    with open("stocks_data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    process_stocks()
