# US500 Macro Intelligence — PRODUCTION

## What this version adds
- Persistent SQLite history and alert log.
- FRED + BLS official API ingestion.
- Configurable US500 ticker; `^GSPC` is the default public proxy.
- Mechanical SL: lowest low of previous 5 completed Daily candles − 0.5×ATR(14).
- TP fixed at 1:4.
- Pullback ladder: −3%, −5%, −10%, −20%, −30%.
- Six macro regimes A–F and early-warning cluster.
- Official Federal Reserve FOMC page ingestion.
- No fabricated consensus/forecast values.

## Start
1. Install Python 3.11+.
2. `pip install -r requirements.txt`
3. Set `FRED_API_KEY` as an environment variable (recommended) or enter it in the sidebar.
4. `streamlit run app.py`

## Important
This is decision-support, not an execution system. `^GSPC` is not necessarily identical to your broker's US500 CFD/futures feed. For live trading, set `US500_TICKER` to a verified feed available to you.

Consensus forecasts, push notifications, and fully automatic Fed-statement NLP are intentionally not faked; they are separate integrations requiring dependable providers/credentials.
