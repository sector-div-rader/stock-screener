# Stock Screener

美股技術面篩選器：抓取股票列表、下載歷史價格、計算 MACD / 52 週位置等指標，找出「底部轉勢」同「頂部轉弱」候選股，並透過 GitHub Actions 每日自動更新。

## 功能

- 從公開來源取得美股股票列表（失敗時回退到小型硬編碼列表）
- 下載/更新歷史日線價格至 `history.csv`
- 計算 MACD、52 週高低位置等技術指標
- 輸出底部轉勢（bottom reversal）與頂部轉弱（top reversal）篩選結果
- GitHub Actions 每日自動執行並提交更新

## 安裝

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
