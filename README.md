# US500 Macro Intelligence — Research Terminal V6.0

A Streamlit frontend for presenting published US500 macroeconomic and market research context, Decision Engine evidence, historical research diagnostics, data availability, and point-in-time limitations.

## Run locally

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
```

The app is designed to start even when datasets are missing. Missing datasets are shown as **Not published**.

## Token-free data access

The frontend requires no GitHub token, personal access token, OAuth flow, or secret. For each known public dataset, it checks the repository's local `public_data/` folder first, then requests the public GitHub raw URL:

`https://raw.githubusercontent.com/mohamednossaoui-max/US500-Macro-Intelligence/main/public_data/<filename>`

Requests are cached briefly by Streamlit. A missing file or network error produces an unavailable state instead of stopping the app. The public data manifest is used when available and its generation time is kept distinct from dataset observation dates.

## Architecture

- `app.py` contains the single-file Streamlit navigation, graceful CSV/JSON loader, executive overview, evidence matrix, historical research view, data availability page, and methodology page.
- `public_data/` is an optional local data source and fallback for offline deployments.
- The same public datasets may be loaded from GitHub raw when no local copy exists.
- The existing research and validation modules are separate from the frontend and are not run or rewritten by the app.

## Research-only restrictions

This dashboard presents descriptive research evidence. It does not provide buy/sell recommendations, trading signals, forecasts, entry or exit prices, stop loss or take profit values, position sizing, broker connectivity, or trade execution.

Decision Engine confidence represents evidence coverage, not probability. Historical Event Study and Historical Edge are descriptive research diagnostics. A PASS indicates structural validation passed; it does not establish causality, predictiveness, profitability, or usefulness.

## Current limitations

- The app can show only files that are locally present or published under the expected public filenames/manifest entries.
- The currently verified Historical Edge robustness validation is not PIT-perfect (`PIT-perfect: FALSE`).
- Some historical event definitions have limited sample sizes.
- A workflow run status is validation metadata, not a latest market observation.
- Detailed Historical Edge files are shown only if actually published; summary metadata is not expanded into invented rows.
- Latest published observations may be stale and are labeled with observation date and data age where source dates exist.
