# diag.py - 診斷版
# 用途：睇下邊個條件最多人 fail
# 跑法：python diag.py

import yfinance as yf
import pandas as pd
import numpy as np

yf.set_tz_cache_location("/tmp/yf_cache")

# 攞 200 隻樣本（S&P 500 + NASDAQ 100）
tickers = [
    # 科技
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AMD', 'NFLX', 'INTC',
    'AVGO', 'ORCL', 'CRM', 'ADBE', 'CSCO', 'QCOM', 'TXN', 'AMAT', 'MU', 'LRCX',
    'ARM', 'SMCI', 'PLTR', 'SNOW', 'PANW', 'CRWD', 'DDOG', 'ZS', 'NET', 'OKTA',
    # 消費
    'WMT', 'COST', 'HD', 'NKE', 'MCD', 'SBUX', 'TGT', 'LOW', 'DIS', 'ABNB',
    'UBER', 'LYFT', 'DASH', 'SHOP', 'ETSY', 'EBAY', 'AMZN', 'BABA', 'JD', 'PDD',
    # 金融
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'BLK', 'SCHW', 'AXP', 'V',
    'MA', 'PYPL', 'SQ', 'COIN', 'MSTR', 'HOOD', 'SOFI', 'AFRM', 'UPST', 'LC',
    # 醫療
    'JNJ', 'UNH', 'LLY', 'ABBV', 'MRK', 'PFE', 'TMO', 'ABT', 'DHR', 'BMY',
    'AMGN', 'GILD', 'BIIB', 'REGN', 'VRTX', 'MRNA', 'BNTX', 'NVAX', 'PFE', 'JNJ',
    # 能源
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'PXD', 'OXY', 'PSX', 'VLO', 'MPC',
    # 工業
    'BA', 'CAT', 'DE', 'HON', 'GE', 'MMM', 'LMT', 'RTX', 'NOC', 'GD',
    # 其他
    'BRK-B', 'JPM', 'V', 'MA', 'UNH', 'JNJ', 'WMT', 'PG', 'HD', 'DIS',
    'KO', 'PEP', 'COST', 'MCD', 'NKE', 'SBUX', 'TGT', 'LOW', 'CVS', 'WBA',
    # 中小型
    'PLUG', 'FCEL', 'BLNK', 'CHPT', 'EVGO', 'RIVN', 'LCID', 'NIO', 'XPEV', 'LI',
    'SOFI', 'HOOD', 'AFRM', 'UPST', 'LC', 'OPEN', 'Z', 'RDFN', 'COMP', 'EXPI',
    # 更多
    'AI', 'PATH', 'U', 'RBLX', 'TTWO', 'EA', 'ATVI', 'ZNGA', 'PLTK', 'SKLZ',
    'SPCE', 'ASTR', 'RKLB', 'JOBY', 'ACHR', 'LILM', 'EVTL', 'BLDE', 'MNTS', 'SPIR',
    'NNDM', 'DDD', 'SSYS', 'MTLS', 'PRLB', 'XONE', 'MKFG', 'DM', 'VELO', 'VLD',
    'ARKK', 'ARKG', 'ARKW', 'ARKF', 'ARKQ', 'ARKX', 'PRNT', 'IZRL', 'ARKK', 'ARKG',
    'SOFI', 'HOOD', 'AFRM', 'UPST', 'LC', 'OPEN', 'Z', 'RDFN', 'COMP', 'EXPI',
    'PLTR', 'SNOW', 'DDOG', 'ZS', 'NET', 'OKTA', 'CRWD', 'PANW', 'S', 'CYBR',
    'MDB', 'ESTC', 'CFLT', 'GTLB', 'HCP', 'SUMO', 'PD', 'DT', 'NEWR', 'APPF',
]

# 去重
tickers = list(set(tickers))
print(f"=== 診斷開始，樣本數：{len(tickers)} ===\n")

fail_counts = {
    'no_data': 0,
    'too_cheap': 0,
    'low_volume': 0,
    'not_dropped_20pct': 0,
    'not_dropped_15pct': 0,
    'not_dropped_10pct': 0,
    'not_consolidating_30d_15pct': 0,
    'not_consolidating_20d_20pct': 0,
    'no_volume_1.5x': 0,
    'no_volume_1.3x': 0,
    'no_dif_up': 0,
    'PASS': 0,
}

# 逐層檢查
for t in tickers:
    try:
        df = yf.Ticker(t).history(period='1y', interval='1d')
        if df is None or len(df) < 200:
            fail_counts['no_data'] += 1
            continue

        current = float(df['Close'].iloc[-1])
        if current < 2.0:
            fail_counts['too_cheap'] += 1
            continue

        vol_today = float(df['Volume'].iloc[-1])
        if vol_today < 20000:
            fail_counts['low_volume'] += 1
            continue

        # 52 週位置
        high_52w = float(df['High'].tail(252).max())
        from_high = (current - high_52w) / high_52w * 100

        # 逐層記錄
        if from_high > -10:
            fail_counts['not_dropped_10pct'] += 1
            continue
        if from_high > -15:
            fail_counts['not_dropped_15pct'] += 1
            continue
        if from_high > -20:
            fail_counts['not_dropped_20pct'] += 1
            continue

        # 盤整（30 日）
        recent_30 = df.tail(30)
        range_30 = (recent_30['High'].max() - recent_30['Low'].min()) / recent_30['Low'].min() * 100
        if range_30 >= 15:
            fail_counts['not_consolidating_30d_15pct'] += 1
            continue

        # 盤整（20 日）
        recent_20 = df.tail(20)
        range_20 = (recent_20['High'].max() - recent_20['Low'].min()) / recent_20['Low'].min() * 100
        if range_20 >= 20:
            fail_counts['not_consolidating_20d_20pct'] += 1
            continue

        # 成交量
        vol_avg = df['Volume'].tail(20).mean()
        vol_ratio = vol_today / vol_avg if vol_avg > 0 else 0
        if vol_ratio < 1.3:
            fail_counts['no_volume_1.3x'] += 1
            continue
        if vol_ratio < 1.5:
            fail_counts['no_volume_1.5x'] += 1
            continue

        # MACD
        ema_fast = df['Close'].ewm(span=5).mean()
        ema_slow = df['Close'].ewm(span=26).mean()
        dif = ema_fast - ema_slow
        if dif.iloc[-1] <= dif.iloc[-2]:
            fail_counts['no_dif_up'] += 1
            continue

        # 全部通過
        fail_counts['PASS'] += 1
        print(f"  ✅ {t}: from_high={from_high:.1f}%, range_30d={range_30:.1f}%, vol={vol_ratio:.2f}x")

    except Exception as e:
        fail_counts['no_data'] += 1

# ==================== 結果 ====================
print("\n=== 診斷結果 ===")
total = len(tickers)
for k, v in fail_counts.items():
    pct = v / total * 100
    print(f"  {k}: {v} ({pct:.1f}%)")

print("\n=== 建議 ===")
if fail_counts['PASS'] < 5:
    print("⚠️ PASS 少於 5 隻，建議放寬：")
    if fail_counts['not_dropped_20pct'] > 0:
        print("  → 放寬 from_high_pct：-20% → -15%")
    if fail_counts['not_consolidating_30d_15pct'] > 0:
        print("  → 放寬 consolidation_range：15% → 20%")
    if fail_counts['no_volume_1.5x'] > 0:
        print("  → 放寬 volume_ratio：1.5x → 1.3x")
    if fail_counts['no_dif_up'] > 0:
        print("  → 放寬 DIF：唔要求翹頭，改為「唔跌」")
else:
    print(f"✅ PASS {fail_counts['PASS']} 隻，參數 OK")
