# US500 Research Terminal — Streamlit deployment

## Files
- `app.py` — complete dashboard
- `requirements.txt` — runtime dependencies

## Streamlit secrets
For a private GitHub repository, add:

```toml
GITHUB_TOKEN = "YOUR_GITHUB_TOKEN"
US500_TICKER = "^GSPC"
```

`^GSPC` is a public S&P 500 market-price proxy and may differ from a broker's US500 CFD/futures price.

The app is research-only. It does not generate trading signals, deterministic forecasts, execution instructions, position sizing, or SL/TP instructions.
