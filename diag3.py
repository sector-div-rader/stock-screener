# diag3.py - 測試 180d 可否攞到數據
import yfinance as yf
import pandas as pd

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

print(f"=== 測試 180d，樣本數：{len(tickers)} ===\n")

success_180 = 0
success_120 = 0
success_90 = 0
fail_all = 0

for t in tickers:
    try:
        df_180 = yf.download(t, period='180d', interval='1d', progress=False)
        df_120 = yf.download(t, period='120d', interval='1d', progress=False)
        df_90 = yf.download(t, period='90d', interval='1d', progress=False)

        len_180 = len(df_180) if df_180 is not None else 0
        len_120 = len(df_120) if df_120 is not None else 0
        len_90 = len(df_90) if df_90 is not None else 0

        if len_180 >= 100:
            success_180 += 1
        if len_120 >= 60:
            success_120 += 1
        if len_90 >= 40:
            success_90 += 1

        if len_180 == 0 and len_120 == 0 and len_90 == 0:
            fail_all += 1
            print(f"  ❌ {t}: 全部失敗")
        else:
            print(f"  {t}: 180d={len_180}, 120d={len_120}, 90d={len_90}")

    except Exception as e:
        fail_all += 1
        print(f"  ❌ {t}: {e}")

total = len(tickers)
print(f"\n=== 結果 ===")
print(f"  180d 成功: {success_180}/{total} ({success_180/total*100:.1f}%)")
print(f"  120d 成功: {success_120}/{total} ({success_120/total*100:.1f}%)")
print(f"  90d 成功: {success_90}/{total} ({success_90/total*100:.1f}%)")
print(f"  全部失敗: {fail_all}/{total} ({fail_all/total*100:.1f}%)")

if success_180 / total > 0.8:
    print(f"\n✅ 180d OK，可以改 main.py 用 period='180d'")
elif success_120 / total > 0.8:
    print(f"\n⚠️ 180d 唔夠穩，建議用 period='120d'")
elif success_90 / total > 0.8:
    print(f"\n⚠️ 120d 唔夠穩，建議用 period='90d'")
else:
    print(f"\n❌ 全部 period 都失敗，Yahoo 完全封鎖 GitHub Actions IP")
