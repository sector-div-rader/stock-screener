# diag2.py - 直接測 main.py 嘅 pipeline
import yfinance as yf
import pandas as pd
import numpy as np

yf.set_tz_cache_location("/tmp/yf_cache")

# 用同樣 178 隻
tickers = [...]  # 同 diag.py 一樣

print(f"=== 診斷開始，樣本數：{len(tickers)} ===")

fail_52w = 0
fail_range = 0
fail_vol = 0
fail_dif = 0
PASS = 0
no_data = 0

for t in tickers:
    try:
        df = yf.Ticker(t).history(period='1y', interval='1d')
        if df is None or len(df) < 252:
            no_data += 1
            continue

        current = float(df['Close'].iloc[-1])
        if current < 2.0:
            continue
        if float(df['Volume'].iloc[-1]) < 20000:
            continue

        # 1. 52W
        high_52w = float(df['High'].tail(252).max())
        from_high = (current - high_52w) / high_52w * 100
        if from_high > -10:
            fail_52w += 1
            continue

        # 2. 盤整
        recent = df.tail(30)
        range_30 = (recent['High'].max() - recent['Low'].min()) / recent['Low'].min() * 100
        if range_30 >= 25:
            fail_range += 1
            continue

        # 3. 量比
        vol_today = float(df['Volume'].iloc[-1])
        vol_avg = float(df['Volume'].tail(30).mean())
        vol_ratio = vol_today / vol_avg if vol_avg > 0 else 0
        if vol_ratio < 1.5:
            fail_vol += 1
            continue

        # 4. DIF
        ema_fast = df['Close'].ewm(span=5).mean()
        ema_slow = df['Close'].ewm(span=26).mean()
        dif = ema_fast - ema_slow
        if dif.iloc[-1] <= dif.iloc[-2]:
            fail_dif += 1
            continue

        PASS += 1
        print(f"  ✅ {t}: from_high={from_high:.1f}%, range={range_30:.1f}%, vol={vol_ratio:.2f}x")

    except Exception:
        no_data += 1

print(f"\n=== 結果 ===")
print(f"  no_data: {no_data}")
print(f"  fail_52w: {fail_52w}")
print(f"  fail_range: {fail_range}")
print(f"  fail_vol: {fail_vol}")
print(f"  fail_dif: {fail_dif}")
print(f"  PASS: {PASS}")
