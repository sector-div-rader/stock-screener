import pandas as pd
import numpy as np
import yfinance as yf
import json
import os
import requests
import io
from datetime import datetime

# 1. 從 NASDAQ 官方 FTP 伺服器獲取全美股個股清單 (排除 ETF 與低價股)
def get_us_stock_list():
    print("正在從官方 FTP 獲取全美股上市個股清單 (過濾 ETF)...")
    tickers = set()
    
    try:
        # 下載 NASDAQ 上市股票資料
        nasdaq_url = "ftp://ftp.nasdaqtrader.com/SymbolDirectory/nasdaqlisted.txt"
        df_nasdaq = pd.read_csv(nasdaq_url, sep="|")
        
        # 下載 NYSE / AMEX 等其他交易所上市股票資料
        other_url = "ftp://ftp.nasdaqtrader.com/SymbolDirectory/otherlisted.txt"
        df_other = pd.read_csv(other_url, sep="|")
        
        # 1. 過濾 NASDAQ 清單中的 ETF (ETF 欄位為 'Y' 的排除)
        if 'ETF' in df_nasdaq.columns:
            df_nasdaq = df_nasdaq[df_nasdaq['ETF'] != 'Y']
            
        # 2. 過濾 Other 清單中的 ETF (ETF 欄位為 'Y' 的排除)
        if 'ETF' in df_other.columns:
            df_other = df_other[df_other['ETF'] != 'Y']

        nasdaq_symbols = df_nasdaq['Symbol'].dropna().tolist()
        other_symbols = df_other['ACT Symbol'].dropna().tolist()
        
        all_symbols = nasdaq_symbols + other_symbols
        
        for symbol in all_symbols:
            symbol = str(symbol).strip()
            # 過濾無效符號、權證、特別股與測試代號 (例如帶有 $、.、~、File Creation Time 等)
            if (symbol and len(symbol) <= 5 and symbol.isalpha() 
                and not symbol.startswith('File') 
                and not symbol.startswith('Total')):
                tickers.add(symbol)
                
        print(f"✅ 成功獲取 {len(tickers)} 隻全美股上市公司個股代號 (已排除 ETF)。")
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

# 3. 核心數據處理
def process_stocks():
    tickers = get_us_stock_list()
    results = []
    total = len(tickers)
    
    print(f"🚀 開始全美股個股掃描，共計 {total} 隻股票...")
    
    count = 0
    for ticker in tickers:
        count += 1
        if count % 200 == 0 or count == total:
            print(f"掃描進度: [{count}/{total}] (已完成 {round(count/total*100, 1)}%)")

        try:
            stock = yf.Ticker(ticker)
            # 抓取日 K 線 (計算現價、成交量與換手率)
            df_day = stock.history(period="1mo", interval="1d")
            if df_day is None or len(df_day) < 2:
                continue
                
            price = round(float(df_day['Close'].iloc[-1]), 2)
            
            # 【新加條件 1】：排除現價低於 $2.00 美元的股票
            if price < 2.0:
                continue

            vol_today = float(df_day['Volume'].iloc[-1])
            vol_yesterday = float(df_day['Volume'].iloc[-2])
            
            # 【過濾條件 2】：過濾日成交量過低 (< 50,000 股) 的冷門股/殭屍股
            if vol_today < 50000:
                continue

            vol_ratio = round(vol_today / vol_yesterday, 2) if vol_yesterday > 0 else 1.0
            turnover_diff = round(((vol_today - vol_yesterday) / vol_yesterday) * 100, 1) if vol_yesterday > 0 else 0.0
            
            # 抓取週 K 與月 K 線
            df_week = stock.history(period="1y", interval="1wk")
            df_month = stock.history(period="3y", interval="1mo")
            
            week_div = check_macd_divergence(df_week)
            month_div = check_macd_divergence(df_month)
            
            # 強制轉換為 Python 原生 bool，防止 JSON dump 報錯
            match_strategy = bool((turnover_diff >= 20.0) and (vol_ratio >= 2.0) and (week_div == "底背離" or month_div == "底背離"))
            
            # 只要符合策略或有背離/爆量特徵就寫入
            if match_strategy or week_div != "無" or month_div != "無" or (turnover_diff >= 20.0 and vol_ratio >= 2.0):
                results.append({
                    "ticker": ticker,
                    "name": ticker,
                    "price": price,
                    "weekDiv": week_div,
                    "monthDiv": month_div,
                    "turnover": f"{round(vol_today/1000000, 2)}M",
                    "turnoverDiff": turnover_diff,
                    "volumeRatio": vol_ratio,
                    "matchStrategy": match_strategy
                })
        except Exception:
            # 個別股票查詢失敗時自動跳過，保持程式穩定執行
            continue
            
    print(f"✅ 全美股個股掃描完成！共篩選出 {len(results)} 隻符合條件的標的。")

    # 將結果輸出為 JSON 檔
    with open("stocks_data.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    process_stocks()
