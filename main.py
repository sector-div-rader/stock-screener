import pandas as pd
import numpy as np
import yfinance as yf
import json
import os
import requests
from datetime import datetime

# 1. 取得全美股上市股票清單
def get_us_stock_list():
    default_tickers = [
        "NVDA", "TSLA", "AMD", "AAPL", "PLTR", "MSFT", "AMZN", "META", "SMCI", 
        "GOOGL", "INTC", "NFLX", "AVGO", "COST", "QCOM", "TXN", "SHOP", "LLY"
    ]
    return default_tickers

# 2. 計算 MACD DIF 與背離型態
def check_macd_divergence(df_kline):
    if len(df_kline) < 35:
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
    
    print(f"開始掃描 {len(tickers)} 隻股票...")
    
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            df_day = stock.history(period="1mo", interval="1d")
            if len(df_day) < 2:
                continue
                
            df_week = stock.history(period="1y", interval="1wk")
            df_month = stock.history(period="3y", interval="1mo")
            
            vol_today = float(df_day['Volume'].iloc[-1])
            vol_yesterday = float(df_day['Volume'].iloc[-2])
            vol_ratio = round(vol_today / vol_yesterday, 2) if vol_yesterday > 0 else 1.0
            
            turnover_diff = round(((vol_today - vol_yesterday) / vol_yesterday) * 100, 1) if vol_yesterday > 0 else 0.0
            
            week_div = check_macd_divergence(df_week)
            month_div = check_macd_divergence(df_month)
            
            price = round(float(df_day['Close'].iloc[-1]), 2)
            
            # 使用 bool() 強制轉回 Python 原生布林值，解決 JSON 轉檔報錯問題
            match_strategy = bool((turnover_diff >= 20.0) and (vol_ratio >= 2.0) and (week_div == "底背離" or month_div == "底背離"))
            
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
            print(f"✅ 完成: {ticker}")
        except Exception as e:
            print(f"❌ 失敗 {ticker}: {e}")
            
    # 將結果輸出為 JSON 檔
    with open("stocks_data.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    process_stocks()
