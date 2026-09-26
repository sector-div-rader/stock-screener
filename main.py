import pandas as pd
import numpy as np
import yfinance as yf
import json
import os
import requests
from datetime import datetime

# 1. 取得全美股（NYSE + NASDAQ）上市股票清單（市值 > 2000萬 USD）
def get_us_stock_list():
    url = "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved"
    # 若 API 無法直接拉取，此處提供標準美股主要成分股與熱門股作為基礎清單
    # 實務上也可以從 SEC 或 Financial Modeling Prep 載入完整 5,000+ 隻 Ticker 清單
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
    
    # 簡化版背離判斷邏輯：近期的價格與 DIF 走勢比較
    recent_close = close.iloc[-1]
    prev_close = close.iloc[-15:-1].min()
    recent_dif = dif.iloc[-1]
    prev_dif = dif.iloc[-15:-1].min()
    
    # 價格破新低，但 DIF 沒有破新低 -> 底背離
    if recent_close < prev_close and recent_dif > prev_dif and recent_dif < 0:
        return "底背離"
    # 價格創新高，但 DIF 沒有創新高 -> 頂背離
    elif recent_close > close.iloc[-15:-1].max() and recent_dif < dif.iloc[-15:-1].max() and recent_dif > 0:
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
            # 抓取日 K 線數據 (用來計算成交量與換手率)
            df_day = stock.history(period="1mo", interval="1d")
            if len(df_day) < 2:
                continue
                
            # 抓取週 K 與月 K 線
            df_week = stock.history(period="1y", interval="1wk")
            df_month = stock.history(period="3y", interval="1mo")
            
            # 成交量與換手率計算 (今日 vs 前一日)
            vol_today = df_day['Volume'].iloc[-1]
            vol_yesterday = df_day['Volume'].iloc[-2]
            vol_ratio = round(vol_today / vol_yesterday, 2) if vol_yesterday > 0 else 1.0
            
            # 換手率增幅估算 (Volume 變動比率)
            turnover_diff = round(((vol_today - vol_yesterday) / vol_yesterday) * 100, 1) if vol_yesterday > 0 else 0.0
            
            # MACD 背離判斷
            week_div = check_macd_divergence(df_week)
            month_div = check_macd_divergence(df_month)
            
            price = round(df_day['Close'].iloc[-1], 2)
            match_strategy = (turnover_diff >= 20.0) and (vol_ratio >= 2.0) and (week_div == "底背離" or month_div == "底背離")
            
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
