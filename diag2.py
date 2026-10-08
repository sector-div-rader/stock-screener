# diag2.py - 用 yf.download() 同 main.py 一樣
import yfinance as yf
import pandas as pd
import numpy as np

yf.set_tz_cache_location("/tmp/yf_cache")

tickers = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AMD', 'NFLX', 'INTC',
    'AVGO', 'ORCL', 'CRM', 'ADBE', 'CSCO', 'QCOM', 'TXN', 'AMAT', 'MU', 'LRCX',
    'ARM', 'SMCI', 'PLTR', 'SNOW', 'PANW', 'CRWD', 'DDOG', 'ZS', 'NET', 'OKTA',
    'WMT', 'COST', 'HD', 'NKE', 'MCD', 'SBUX', 'TGT', 'LOW', 'DIS', 'ABNB',
    'UBER', 'LYFT', 'DASH', 'SHOP', 'ETSY', 'EBAY', 'BABA', 'JD', 'PDD', 'BIDU',
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'SCHW', 'AXP', 'V',
    'MA', 'PYPL', 'COIN', 'MSTR', 'HOOD', 'SOFI', 'AFRM', 'UPST',
    'JNJ', 'UNH', 'LLY', 'ABBV', 'MRK', 'PFE', 'TMO', 'ABT', 'DHR', 'BMY',
    'AMGN', 'GILD', 'BIIB', 'REGN', 'VRTX', 'MRNA',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'PSX', 'VLO',
    'BA', 'CAT', 'DE', 'HON', 'GE', 'MMM', 'LMT', 'RTX',
    'KO', 'PEP', 'PG', 'WBA', 'CVS',
]
tickers = list(set(tickers))

print(f"=== 診斷開始，樣本數：{len(tickers)} ===\n")

no_data = 0
fail_52w = 0
fail_range = 0
fail_vol = 0
fail_dif = 0
PASS = 0

# ★ 用 batch download（同 main.py 一樣）
batch_size = 50
for i in range(0, len(tickers), batch_size):
    batch = tickers[i:i+batch_size]
    try:
        data = yf.download(batch, period='1y', interval='1d',
                            group_by='ticker', threads=True, progress=False)

        for t in batch:
            try:
                if len(batch) > 1:
                    if t not in data.columns.levels[0]:
                        no_data += 1
                        continue
                    df = data[t].dropna(how='all')
                else:
                    df = data.dropna(how='all')

                if df is None or len(df) < 252:
                    no_data += 1
                    continue

                current = float(df['Close'].iloc[-1])
                if current < 2.0:
                    continue
                if float(df['Volume'].iloc[-1]) < 20000:
                    continue

                # 52W
                high_52w = float(df['High'].tail(252).max())
                from_high = (current - high_52w) / high_52w * 100
                if from_high > -10:
                    fail_52w += 1
                    continue

                # 盤整
                recent = df.tail(30)
                range_30 = (recent['High'].max() - recent['Low'].min()) / recent['Low'].min() * 100
                if range_30 >= 25:
                    fail_range += 1
                    continue

                # 量比
                vol_today = float(df['Volume'].iloc[-1])
                vol_avg = float(df['Volume'].tail(30).mean())
                vol_ratio = vol_today / vol_avg if vol_avg > 0 else 0
                if vol_ratio < 1.5:
                    fail_vol += 1
                    continue

                # DIF
                ema_fast = df['Close'].ewm(span=5).mean()
                ema_slow = df['Close'].ewm(span=26).mean()
                dif = ema_fast - ema_slow
                if dif.iloc[-1] <= dif.iloc[-2]:
                    fail_dif += 1
                    continue

                PASS += 1
                print(f"  ✅ {t}: from_high={from_high:.1f}%, range={range_30:.1f}%, vol={vol_ratio:.2f}x")
            except Exception as e:
                no_data += 1
    except Exception as e:
        print(f"  ⚠️ Batch {i} error: {e}")
        no_data += len(batch)

print(f"\n=== 結果 ===")
print(f"  no_data: {no_data}")
print(f"  fail_52w: {fail_52w}")
print(f"  fail_range: {fail_range}")
print(f"  fail_vol: {fail_vol}")
print(f"  fail_dif: {fail_dif}")
print(f"  PASS: {PASS}")
