#!/usr/bin/env python3
"""
Cross-Asset Intelligence v1
Research-only. No trading signals, forecasts, scores, or Decision Engine integration.

Free/public-data implementation using yfinance for:
^GSPC, DX-Y.NYB, ^IRX, ^TNX, GC=F, CL=F, BTC-USD

Notes:
- yfinance is used only for historical market observations.
- Availability is conservatively represented as the observation date + 1 calendar day.
- This is NOT PIT-perfect because vendor history can be revised.
- Cross-asset diagnostics are descriptive, not predictive or causal.
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

TICKERS = {
    "US500": "^GSPC",
    "DXY": "DX-Y.NYB",
    "US2Y_PROXY": "^IRX",
    "US10Y": "^TNX",
    "GOLD": "GC=F",
    "OIL": "CL=F",
    "BITCOIN": "BTC-USD",
}

START_DATE = "2019-01-01"
ROLLING_WINDOW = 60
MIN_VALID_ROLLING = 30
HORIZONS = [1, 5, 20]


def normalize_index(idx):
    d = pd.to_datetime(idx, errors="coerce", utc=True)
    return d.tz_convert(None).normalize()


def download_prices():
    frames = []
    errors = []
    for name, ticker in TICKERS.items():
        try:
            raw = yf.download(
                ticker,
                start=START_DATE,
                auto_adjust=False,
                progress=False,
                actions=False,
                group_by="column",
            )
            if raw.empty:
                errors.append(f"{name}: empty download")
                continue

            if isinstance(raw.columns, pd.MultiIndex):
                if "Close" in raw.columns.get_level_values(0):
                    s = raw["Close"]
                    if isinstance(s, pd.DataFrame):
                        s = s.iloc[:, 0]
                else:
                    errors.append(f"{name}: Close column missing")
                    continue
            else:
                if "Close" not in raw.columns:
                    errors.append(f"{name}: Close column missing")
                    continue
                s = raw["Close"]

            s = pd.to_numeric(s, errors="coerce")
            # Treat infinities from vendor data as missing observations.
            s = s.replace([np.inf, -np.inf], np.nan)
            s.index = normalize_index(s.index)
            s = s[~s.index.duplicated(keep="last")].sort_index()
            s.name = name
            frames.append(s)
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")

    if not frames:
        raise RuntimeError("No cross-asset series were downloaded: " + "; ".join(errors))

    prices = pd.concat(frames, axis=1, sort=False).sort_index()
    prices.index.name = "asof_date"
    return prices, errors


def add_returns(prices):
    out = prices.copy()
    for h in HORIZONS:
        for col in prices.columns:
            out[f"{col}_RET_{h}D_PCT"] = prices[col].pct_change(h) * 100.0
    return out


def add_availability(out):
    out = out.copy()
    out["availability_date"] = out.index + pd.Timedelta(days=1)
    out["point_in_time_reconstructed"] = True
    out["pit_perfect"] = False
    return out


def rolling_correlations(df):
    ret_cols = {c: f"{c}_RET_1D_PCT" for c in TICKERS if f"{c}_RET_1D_PCT" in df}
    rows = []
    us = ret_cols.get("US500")
    if not us:
        return pd.DataFrame(columns=[
            "asof_date", "asset", "window_days", "rolling_corr_with_us500"
        ])

    for asset, col in ret_cols.items():
        if asset == "US500":
            continue
        corr = df[us].rolling(ROLLING_WINDOW, min_periods=MIN_VALID_ROLLING).corr(df[col])
        tmp = pd.DataFrame({
            "asof_date": df.index,
            "asset": asset,
            "window_days": ROLLING_WINDOW,
            "rolling_corr_with_us500": corr.values,
        })
        rows.append(tmp)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def divergence_diagnostics(df):
    # Descriptive divergence: US500 20D return and asset 20D return have opposite signs.
    rows = []
    for asset in TICKERS:
        if asset == "US500":
            continue
        a = f"{asset}_RET_20D_PCT"
        u = "US500_RET_20D_PCT"
        if a not in df or u not in df:
            continue
        x = df[[u, a]].dropna()
        if x.empty:
            continue
        opposite = (np.sign(x[u]) * np.sign(x[a]) < 0)
        rows.append({
            "asset": asset,
            "observations": int(len(x)),
            "opposite_sign_20d_count": int(opposite.sum()),
            "opposite_sign_20d_pct": float(opposite.mean() * 100),
        })
    return pd.DataFrame(rows)


def pairwise_correlations(df):
    cols = [f"{a}_RET_1D_PCT" for a in TICKERS if f"{a}_RET_1D_PCT" in df]
    if len(cols) < 2:
        return pd.DataFrame()
    c = df[cols].corr()
    c.index = [x.replace("_RET_1D_PCT", "") for x in c.index]
    c.columns = [x.replace("_RET_1D_PCT", "") for x in c.columns]
    return c


def validate(prices, research, rolling, divergence, errors):
    checks = []
    def check(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    check("us500_available", "US500" in prices.columns)
    check("minimum_rows", len(prices) >= 250, f"rows={len(prices)}")
    check("unique_dates", not prices.index.duplicated().any())
    check("sorted_dates", prices.index.is_monotonic_increasing)
    # Validate each economic series according to its type.
    # Oil is intentionally allowed to be <= 0 because CL=F contains the
    # documented negative settlement period in April 2020.
    positive_price_cols = [
        c for c in ["US500", "DXY", "GOLD", "BITCOIN"]
        if c in prices.columns
    ]
    oil_values = prices["OIL"].dropna() if "OIL" in prices.columns else pd.Series(dtype=float)
    yield_cols = [c for c in ["US2Y_PROXY", "US10Y"] if c in prices.columns]

    positive_values = prices[positive_price_cols].stack()
    positive_arr = pd.to_numeric(positive_values, errors="coerce").to_numpy(dtype=float)
    positive_nonfinite = int((~np.isfinite(positive_arr)).sum()) if len(positive_arr) else 0
    positive_nonpositive = int((positive_arr <= 0).sum()) if len(positive_arr) else 0
    positive_finite = positive_nonfinite == 0 if len(positive_arr) else False
    positive_prices = positive_nonpositive == 0 if len(positive_arr) else False

    oil_arr = pd.to_numeric(oil_values, errors="coerce").to_numpy(dtype=float)
    oil_nonfinite = int((~np.isfinite(oil_arr)).sum()) if len(oil_arr) else 0
    oil_finite = oil_nonfinite == 0 if len(oil_arr) else False

    yield_values = prices[yield_cols].stack()
    yield_arr = pd.to_numeric(yield_values, errors="coerce").to_numpy(dtype=float)
    yield_nonfinite = int((~np.isfinite(yield_arr)).sum()) if len(yield_arr) else 0
    yield_finite = yield_nonfinite == 0 if len(yield_arr) else False

    market_bad_by_col = {}
    for col in positive_price_cols:
        arr = pd.to_numeric(prices[col], errors="coerce").to_numpy(dtype=float)
        market_bad_by_col[col] = {
            "nonfinite": int((~np.isfinite(arr)).sum()),
            "nonpositive": int((arr <= 0).sum()),
        }

    yield_bad_by_col = {}
    for col in yield_cols:
        arr = pd.to_numeric(prices[col], errors="coerce").to_numpy(dtype=float)
        yield_bad_by_col[col] = {
            "nonfinite": int((~np.isfinite(arr)).sum()),
        }

    check(
        "positive_market_prices",
        positive_finite and positive_prices,
        json.dumps({
            "non_null_values": len(positive_values),
            "nonfinite": positive_nonfinite,
            "nonpositive": positive_nonpositive,
            "by_column": market_bad_by_col,
        }, sort_keys=True)
    )
    check(
        "oil_series_finite",
        oil_finite,
        json.dumps({
            "non_null_values": len(oil_values),
            "nonfinite": oil_nonfinite,
        }, sort_keys=True)
    )
    check(
        "yield_series_finite",
        yield_finite,
        json.dumps({
            "non_null_values": len(yield_values),
            "nonfinite": yield_nonfinite,
            "by_column": yield_bad_by_col,
        }, sort_keys=True)
    )
    check("returns_present", any(c.endswith("_RET_20D_PCT") for c in research.columns))
    check("rolling_output", len(rolling) > 0)
    check("divergence_output", len(divergence) > 0)
    check("research_only", bool(research["research_only"].eq(True).all()))
    check("decision_engine_ready_false", bool(research["decision_engine_ready"].eq(False).all()))
    check("trading_signal_false", bool(research["trading_signal"].eq(False).all()))
    check("forecast_false", bool(research["forecast"].eq(False).all()))
    check("pit_perfect_false", bool(research["pit_perfect"].eq(False).all()))

    # Measure traditional-market coverage against the US500 observation
    # calendar, not the union calendar (which includes weekends/crypto dates).
    if "US500" in prices.columns:
        reference_dates = prices.index[prices["US500"].notna()]
    else:
        reference_dates = prices.index

    coverage = {}
    for col in prices.columns:
        if col == "BITCOIN":
            denom = int(prices[col].notna().sum())
            coverage[col] = 100.0 if denom else 0.0
        else:
            denom = max(len(reference_dates), 1)
            coverage[col] = round(
                float(prices.loc[reference_dates, col].notna().sum() / denom * 100),
                3
            )

    check("coverage_nonzero", all(v > 0 for v in coverage.values()), str(coverage))

    status = "PASS" if all(x["pass"] for x in checks) else "FAIL"
    warnings = [f"download: {e}" for e in errors]
    if any(v < 80 for v in coverage.values()):
        warnings.append("At least one series has <80% coverage versus the US500 observation calendar.")

    return {
        "validator": "Cross-Asset Intelligence v1",
        "status": status,
        "validation_pass": status == "PASS",
        "errors": [x for x in checks if not x["pass"]],
        "warnings": warnings,
        "rows": int(len(prices)),
        "date_start": str(prices.index.min().date()) if len(prices) else None,
        "date_end": str(prices.index.max().date()) if len(prices) else None,
        "coverage_pct": coverage,
        "rolling_window_days": ROLLING_WINDOW,
        "research_only": True,
        "decision_engine_ready": False,
        "trading_signal": False,
        "forecast": False,
        "pit_perfect": False,
        "point_in_time_reconstructed": True,
        "interpretation": (
            "PASS is structural/data-quality validation only. "
            "Correlations and divergences are descriptive and do not establish causality, "
            "predictiveness, trading usefulness, or preference for any asset."
        ),
        "checks": checks,
        "tickers": TICKERS,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="cross_asset_intelligence_v1")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    prices, download_errors = download_prices()
    research = add_returns(prices)
    research = add_availability(research)

    # Explicit research-only metadata on every row.
    research["research_only"] = True
    research["decision_engine_ready"] = False
    research["trading_signal"] = False
    research["forecast"] = False

    research = research.reset_index()
    research["record_id"] = (
        "CROSS_ASSET_" + research["asof_date"].dt.strftime("%Y%m%d")
    )

    rolling = rolling_correlations(research.set_index("asof_date"))
    divergence = divergence_diagnostics(research.set_index("asof_date"))
    corr = pairwise_correlations(research.set_index("asof_date"))

    summary_rows = []
    for asset in TICKERS:
        if asset == "US500":
            continue
        for h in HORIZONS:
            c = f"{asset}_RET_{h}D_PCT"
            u = f"US500_RET_{h}D_PCT"
            if c not in research or u not in research:
                continue
            x = research[[c, u]].dropna()
            summary_rows.append({
                "asset": asset,
                "horizon": f"{h}D",
                "observations": int(len(x)),
                "mean_asset_return_pct": float(x[c].mean()) if len(x) else np.nan,
                "mean_us500_return_pct": float(x[u].mean()) if len(x) else np.nan,
                "pearson_corr_with_us500": float(x[c].corr(x[u])) if len(x) >= 2 else np.nan,
            })
    summary = pd.DataFrame(summary_rows)

    validation = validate(
        prices,
        research,
        rolling,
        divergence,
        download_errors,
    )

    research.to_csv(out / "cross_asset_research_v1.csv", index=False)
    summary.to_csv(out / "cross_asset_summary_v1.csv", index=False)
    rolling.to_csv(out / "cross_asset_rolling_correlation_v1.csv", index=False)
    divergence.to_csv(out / "cross_asset_divergence_v1.csv", index=False)
    corr.to_csv(out / "cross_asset_correlation_matrix_v1.csv")
    with open(out / "cross_asset_validation_v1.json", "w", encoding="utf-8") as f:
        json.dump(validation, f, indent=2)

    print(json.dumps(validation, indent=2))
    if not validation["validation_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
