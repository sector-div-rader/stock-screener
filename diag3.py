# diag3.py - 測試 yf.Ticker().info 攞 52 週高位
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

print(f"=== 測試 yf.Ticker().info，樣本數：{len(tickers)} ===\n")

success = 0
fail = 0
no_52w = 0

for t in tickers:
    try:
        ticker = yf.Ticker(t)
        info = ticker.info
        high_52w = info.get('fiftyTwoWeekHigh', None)
        low_52w = info.get('fiftyTwoWeekLow', None)
        current = info.get('currentPrice', None)
        market_cap = info.get('marketCap', None)

        if high_52w and low_52w:
            success += 1
            from_high = (current - high_52w) / high_52w * 100 if current else 0
            print(f"  ✅ {t}: 52W High={high_52w}, 52W Low={low_52w}, 現價={current}, 距高={from_high:.1f}%, 市值={market_cap}")
        else:
            no_52w += 1
            print(f"  ⚠️ {t}: 冇 52W 數據 (keys: {list(info.keys())[:10]}...)")

    except Exception as e:
        fail += 1
        print(f"  ❌ {t}: {e}")

    time.sleep(0.1)   # 每隻等 0.1 秒，避免封鎖

total = len(tickers)
print(f"\n=== 結果 ===")
print(f"  成功: {success}/{total} ({success/total*100:.1f}%)")
print(f"  冇 52W 數據: {no_52w}/{total} ({no_52w/total*100:.1f}%)")
print(f"  失敗: {fail}/{total} ({fail/total*100:.1f}%)")

if success / total > 0.8:
    print(f"\n✅ info OK，可以混合用（info + 180d）")
elif success / total > 0.5:
    print(f"\n⚠️ info 部分 OK，建議 fallback（info 失敗時用 180d）")
else:
    print(f"\n❌ info 失敗率太高，建議只用 180d")
