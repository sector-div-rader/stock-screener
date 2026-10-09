# diag5.py - 測試 1y（for GitHub Actions）
import yfinance as yf
import time

yf.set_tz_cache_location("/tmp/yf_cache")

tickers = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AMD', 'NFLX', 'INTC',
    'AVGO', 'ORCL', 'CRM', 'ADBE', 'CSCO', 'QCOM', 'TXN', 'AMAT', 'MU', 'LRCX',
    'WMT', 'COST', 'HD', 'NKE', 'MCD', 'SBUX', 'TGT', 'LOW', 'DIS', 'ABNB',
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'SCHW', 'AXP', 'V',
    'JNJ', 'UNH', 'LLY', 'ABBV', 'MRK', 'PFE', 'TMO', 'ABT', 'DHR', 'BMY',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'OXY', 'PSX', 'VLO',
    'BA', 'CAT', 'DE', 'HON', 'GE', 'MMM', 'LMT', 'RTX',
]

print(f"=== 測試 1y，樣本數：{len(tickers)} ===\n")

success = 0
fail = 0

for t in tickers:
    try:
        df = yf.download(t, period='1y', interval='1d', progress=False)
        if df is not None and len(df) >= 200:
            success += 1
            print(f"  OK {t}: {len(df)} rows")
        else:
            fail += 1
            print(f"  FAIL {t}: {len(df) if df is not None else 0} rows")
    except Exception as e:
        fail += 1
        print(f"  FAIL {t}: {e}")
    time.sleep(0.5)

total = len(tickers)
print(f"\n=== 結果 ===")
print(f"  成功: {success}/{total} ({success/total*100:.1f}%)")
print(f"  失敗: {fail}/{total} ({fail/total*100:.1f}%)")

if success / total > 0.8:
    print(f"\n✅ 1y OK！可以改 main.py 用 period='1y'")
else:
    print(f"\n❌ 1y 仍然失敗")
