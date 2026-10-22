
---

## 4. `.github/workflows/daily_scan.yml`（完整替換）

```yaml
name: Daily Stock Scan

on:
  schedule:
    - cron: "0 22 * * 1-5"   # 美股收盤後（UTC）
  workflow_dispatch:

jobs:
  scan:
    runs-on: ubuntu-latest
    permissions:
      contents: write

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run screener
        env:
          FINNHUB_API_KEY: ${{ secrets.FINNHUB_API_KEY }}
          STRICT_STOCK_LIST: "1"
        run: python main.py

      - name: Commit updated data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add history.csv stocks_data.json
          if git diff --cached --quiet; then
            echo "No changes to commit"
          else
            git commit -m "chore: update screener data $(date -u +%Y-%m-%d) [skip ci]"
            git push
          fi
