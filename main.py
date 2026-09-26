import pandas as pd
import numpy as np
import yfinance as yf
import json
import os
import requests
import io
from datetime import datetime

# 1. 自動動態取得全美股（NYSE, NASDAQ, AMEX）上市普通股清單
def get_us_stock_list():
    print("正在獲取全美股上市股票清單...")
    tickers = set()
    
    # 來源 A: 從 NASDAQ 官方 API 獲取上市股票列表
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
        }
        url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25000&exchange=NASDAQ,NYSE,AMEX"
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            data = res.json()
            rows = data.get('data', {}).get('table', {}).get('rows', [])
            for row in rows:
                symbol = row.get('symbol', '')
                # 過濾含有特殊符號(權證/特別股)、無效字元的代號
                if symbol and '^' not in symbol and '/' not in symbol and '.' not in symbol and len(symbol) <= 5:
                    tickers.add(symbol)
            print(f"成功從 NASDAQ 取得 {len(tickers)} 隻股票代號。")
    except Exception as e:
        print(f"從 NASDAQ API 獲取失敗: {e}")

    # 備用來源 B: 如果 API 失敗，載入美股核心龍頭與熱門標的備用清單
    if len(tickers) < 100:
        print("使用備用美股清單...")
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
    
    print(f"🚀 開始全美股掃描，共計 {total} 隻股票...")
    
    count = 0
    for ticker in tickers:
        count += 1
        if count % 100 == 0 or count == total:
            print(f"進度: [{count}/{total}] (已完成 {round(count/total*100, 1)}%)")

        try:
            stock = yf.Ticker(ticker)
            # 抓取日 K 線 (計算成交量與換手率)
            df_day = stock.history(period="1mo", interval="1d")
            if df_day is None or len(df_day) < 2:
                continue
                
            vol_today = float(df_day['Volume'].iloc[-1])
            vol_yesterday = float(df_day['Volume'].iloc[-2])
            
            # 過濾成交量過低（成交不活躍）的仙股，提升掃描效率與資料品質
            if vol_today < 50000:
                continue

            vol_ratio = round(vol_today / vol_yesterday, 2) if vol_yesterday > 0 else 1.0
            turnover_diff = round(((vol_today - vol_yesterday) / vol_yesterday) * 100, 1) if vol_yesterday > 0 else 0.0
            
            # 抓取週 K 與月 K 線
            df_week = stock.history(period="1y", interval="1wk")
            df_month = stock.history(period="3y", interval="1mo")
            
            week_div = check_macd_divergence(df_week)
            month_div = check_macd_divergence(df_month)
            
            price = round(float(df_day['Close'].iloc[-1]), 2)
            
            # 判斷是否符合全部條件
            match_strategy = bool((turnover_diff >= 20.0) and (vol_ratio >= 2.0) and (week_div == "底背離" or month_div == "底背離"))
            
            # 若符合任一背離或爆量條件才寫入，大幅減少數據檔案體積
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
        except Exception as e:
            # 忽略個別資料抓取失敗的股票，繼續執行
            continue
            
    print(f"✅ 全美股掃描完成！共篩選出 {len(results)} 隻符合條件/特徵的標的。")

    # 將結果輸出為 JSON 檔
    with open("stocks_data.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    process_stocks()
