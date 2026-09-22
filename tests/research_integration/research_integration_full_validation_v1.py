#!/usr/bin/env python3
"""
US500 Macro Intelligence — Research Integration Full Validation v1

Purpose
-------
One research-only validation that checks whether Market Breadth contains
information not already represented by the existing research layers.

Layers
------
Base:
    Research Context v1
        Economic + Fed + Financial Stress + Sentiment + Technical
    Liquidity Intelligence v1

Additional:
    Market Breadth Analyzer v1

Outcome
-------
Historical forward US500 returns (1D, 5D, 20D) are used ONLY as study
outcomes. This is an association/event-study layer, not a trading signal,
forecast engine, or Decision Engine component.

Tests
-----
1. Input integrity and PIT/research-only safeguards.
2. Date alignment and common-sample coverage.
3. Breadth coverage sensitivity: all rows vs >=90% coverage.
4. Correlation/redundancy audit between Breadth and existing layers.
5. Partial-correlation / residual association:
       future_return ~ base_layers
   versus Breadth residualized on the same base layers.
6. Directional event-study summaries for Breadth states.
7. Final PASS/REVIEW/FAIL classification.

No ranking of layers is produced.
No trading signal, forecast, score, or Decision Engine output is produced.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


OUTCOME_HORIZONS = {"1D": 1, "5D": 5, "20D": 20}

BREADTH_FEATURES = [
    "net_advances_pct_eligible",
    "net_advances_5d",
    "net_advances_20d",
    "pct_advancing_20d_avg",
    "advance_decline_ratio_20d",
    "ad_line_change_20d",
    "ad_line_change_60d",
    "net_advances_z_252d",
    "net_advances_20d_z_252d",
    "pct_advancing_20d_z_252d",
    "ad_line_change_20d_z_252d",
]

BASE_CANDIDATES = [
    # Research Context — Economic / Fed / Financial Stress
    "macro_inflation_score",
    "macro_labor_score",
    "macro_growth_score",
    "macro_fed_score",
    "macro_financial_stress_composite",
    "macro_yield_curve_stress_z",
    "macro_vix",
    "macro_treasury_2y",
    "macro_treasury_10y",
    "macro_yield_10y_2y_spread",
    # Research Context — Sentiment
    "sentiment_unified_sentiment_score",
    "sentiment_cot_sentiment_score",
    "sentiment_aaii_sentiment_score",
    "sentiment_vix_sentiment_score",
    # Research Context — Technical
    "technical_RSI14",
    "technical_ROC20_pct",
    "technical_ATR14_pct",
    "technical_drawdown_pct",
    "technical_close_vs_SMA20_pct",
    "technical_close_vs_SMA50_pct",
    "technical_close_vs_SMA200_pct",
    # Liquidity Intelligence
    "NET_LIQUIDITY_PROXY_MILLIONS",
    "SOFR_EFFR_SPREAD_BPS",
]

DATE_CANDIDATES = ["context_date", "asof_date", "observation_date"]


def find_date_col(df: pd.DataFrame) -> str:
    for c in DATE_CANDIDATES:
        if c in df.columns:
            return c
    raise ValueError("No supported date column found.")


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path, low_memory=False)
    if df.empty:
        raise ValueError(f"Empty input: {path}")
    return df


def bool_column(df, col, expected):
    return col in df.columns and bool(df[col].eq(expected).all())


def prepare_research_context(df: pd.DataFrame) -> pd.DataFrame:
    dcol = find_date_col(df)
    out = df.copy()
    out["study_date"] = pd.to_datetime(out[dcol], errors="coerce")
    if out["study_date"].isna().any():
        raise ValueError("Research Context contains invalid dates.")
    if "research_only" in out and not bool_column(out, "research_only", True):
        raise ValueError("Research Context research_only safeguard failed.")
    if "decision_engine_ready" in out and not bool_column(out, "decision_engine_ready", False):
        raise ValueError("Research Context Decision Engine safeguard failed.")
    if "trading_signal_generated" in out and not bool_column(out, "trading_signal_generated", False):
        raise ValueError("Research Context trading-signal safeguard failed.")
    if "forecast_generated" in out and not bool_column(out, "forecast_generated", False):
        raise ValueError("Research Context forecast safeguard failed.")
    return out


def prepare_liquidity(df: pd.DataFrame) -> pd.DataFrame:
    dcol = find_date_col(df)
    out = df.copy()
    out["study_date"] = pd.to_datetime(out[dcol], errors="coerce")
    if out["study_date"].isna().any():
        raise ValueError("Liquidity contains invalid dates.")
    if "research_only" in out and not bool_column(out, "research_only", True):
        raise ValueError("Liquidity research_only safeguard failed.")
    if "decision_engine_ready" in out and not bool_column(out, "decision_engine_ready", False):
        raise ValueError("Liquidity Decision Engine safeguard failed.")
    if "trading_signal" in out and not bool_column(out, "trading_signal", False):
        raise ValueError("Liquidity trading-signal safeguard failed.")
    if "forecast" in out and not bool_column(out, "forecast", False):
        raise ValueError("Liquidity forecast safeguard failed.")
    return out


def prepare_breadth(df: pd.DataFrame) -> pd.DataFrame:
    dcol = find_date_col(df)
    out = df.copy()
    out["study_date"] = pd.to_datetime(out[dcol], errors="coerce")
    if out["study_date"].isna().any():
        raise ValueError("Breadth contains invalid dates.")
    if "research_only" in out and not bool_column(out, "research_only", True):
        raise ValueError("Breadth research_only safeguard failed.")
    if "decision_engine_ready" in out and not bool_column(out, "decision_engine_ready", False):
        raise ValueError("Breadth Decision Engine safeguard failed.")
    if "trading_signal" in out and not bool_column(out, "trading_signal", False):
        raise ValueError("Breadth trading-signal safeguard failed.")
    if "forecast" in out and not bool_column(out, "forecast", False):
        raise ValueError("Breadth forecast safeguard failed.")
    if "pit_perfect" in out and not bool_column(out, "pit_perfect", False):
        raise ValueError("Breadth PIT-perfect safeguard failed.")
    return out


def download_sp500_close(start, end) -> pd.DataFrame:
    data = yf.download(
        "^GSPC",
        start=(start - pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
        end=(end + pd.Timedelta(days=25)).strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=False,
        actions=False,
        threads=False,
    )
    if data.empty:
        raise ValueError("Unable to download ^GSPC for event-study outcomes.")
    close = data["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close.index = pd.to_datetime(close.index).normalize()
    return pd.DataFrame({"close": pd.to_numeric(close, errors="coerce")}).dropna()


def add_forward_returns(df: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    close = prices["close"]
    price_dates = pd.to_datetime(close.index, errors="coerce")
    if getattr(price_dates, "tz", None) is not None:
        price_dates = price_dates.tz_localize(None)
    price_dates = price_dates.normalize()

    close_series = pd.Series(
        pd.to_numeric(close.to_numpy(), errors="coerce"),
        index=price_dates,
        name="close",
    )

    future = pd.DataFrame({"study_date": price_dates})
    for label, h in OUTCOME_HORIZONS.items():
        future[f"forward_return_{label}"] = (
            close_series.shift(-h) / close_series - 1.0
        ).to_numpy()

    out["study_date"] = pd.to_datetime(
        out["study_date"], errors="coerce"
    ).dt.normalize()

    return out.merge(future, on="study_date", how="left")


def numeric_available(df, candidates, min_valid=30):
    """
    Resolve candidate features robustly.

    A feature is considered available when:
    - its name exists exactly or case-insensitively;
    - values can be converted to numeric;
    - at least min_valid observations are numeric.

    This only improves input-schema compatibility. It does not alter
    the research methodology or create any trading/forecast output.
    """
    normalized = {
        str(c).strip().lower(): c
        for c in df.columns
    }

    available = []

    for candidate in candidates:
        key = str(candidate).strip().lower()
        actual = normalized.get(key)

        # Liquidity columns are prefixed with "liq_" during integration.
        if actual is None:
            actual = normalized.get(f"liq_{key}")

        if actual is None:
            continue

        numeric = pd.to_numeric(df[actual], errors="coerce")

        if numeric.notna().sum() >= min_valid:
            df[actual] = numeric
            # One physical column must be returned only once, even when
            # multiple candidate aliases resolve to the same column.
            if actual not in available:
                available.append(actual)

    return available


def standardized(df, cols):
    x = df[cols].apply(pd.to_numeric, errors="coerce").copy()
    for c in cols:
        s = x[c]
        std = s.std(ddof=0)
        if std and np.isfinite(std):
            x[c] = (s - s.mean()) / std
        else:
            x[c] = np.nan
    return x


def residual_partial_corr(frame, xcol, ycol, controls):
    cols = [xcol, ycol] + controls
    work = frame[cols].apply(pd.to_numeric, errors="coerce").dropna()
    if len(work) < max(100, len(controls) + 30):
        return None, len(work)

    # Standardize controls to avoid numerical scaling issues.
    Xc = work[controls].to_numpy(dtype=float)
    Xc = (Xc - Xc.mean(axis=0)) / np.where(Xc.std(axis=0, ddof=0) == 0, 1, Xc.std(axis=0, ddof=0))
    X = np.column_stack([np.ones(len(Xc)), Xc])

    x = work[xcol].to_numpy(dtype=float)
    y = work[ycol].to_numpy(dtype=float)

    bx = np.linalg.lstsq(X, x, rcond=None)[0]
    by = np.linalg.lstsq(X, y, rcond=None)[0]
    rx = x - X @ bx
    ry = y - X @ by

    sx = rx.std(ddof=0)
    sy = ry.std(ddof=0)
    if sx == 0 or sy == 0:
        return None, len(work)

    corr = float(np.corrcoef(rx, ry)[0, 1])
    return corr, len(work)


def event_state_summary(df, state_col="breadth_research_state"):
    rows = []
    for state, sub in df.groupby(state_col, dropna=False):
        row = {"breadth_state": state, "rows": len(sub)}
        for label in OUTCOME_HORIZONS:
            s = pd.to_numeric(sub[f"forward_return_{label}"], errors="coerce").dropna()
            row[f"mean_forward_return_{label}_pct"] = float(s.mean() * 100) if len(s) else np.nan
            row[f"median_forward_return_{label}_pct"] = float(s.median() * 100) if len(s) else np.nan
            row[f"positive_return_share_{label}_pct"] = float((s > 0).mean() * 100) if len(s) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--research-context", required=True)
    ap.add_argument("--liquidity", required=True)
    ap.add_argument("--breadth", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    context = prepare_research_context(load_csv(Path(args.research_context)))
    liquidity = prepare_liquidity(load_csv(Path(args.liquidity)))
    breadth = prepare_breadth(load_csv(Path(args.breadth)))

    # Keep one row per date before merging.
    context = context.sort_values("study_date").drop_duplicates("study_date", keep="last")
    liquidity = liquidity.sort_values("study_date").drop_duplicates("study_date", keep="last")
    breadth = breadth.sort_values("study_date").drop_duplicates("study_date", keep="last")

    # Prefix liquidity to avoid accidental collisions.
    liq_cols = ["study_date"] + [
        c for c in liquidity.columns
        if c != "study_date" and c not in {"asof_date", "context_date", "observation_date"}
    ]
    liquidity = liquidity[liq_cols].copy()
    liquidity.columns = [
        c if c == "study_date" else f"liq_{c}"
        for c in liquidity.columns
    ]

    merged = context.merge(liquidity, on="study_date", how="inner")
    merged = merged.merge(
        breadth,
        on="study_date",
        how="inner",
        suffixes=("", "_breadth"),
    )

    if merged.empty:
        raise ValueError("No common dates across Research Context, Liquidity, and Breadth.")

    prices = download_sp500_close(
        merged["study_date"].min(),
        merged["study_date"].max(),
    )
    merged = add_forward_returns(merged, prices)

    # Rename/preserve breadth feature names after merge.
    available_breadth = numeric_available(merged, BREADTH_FEATURES)
    available_base = numeric_available(merged, BASE_CANDIDATES)

    # Remove duplicate semantic columns if suffixing occurred and enforce
    # uniqueness after alias resolution.
    available_breadth = list(dict.fromkeys(available_breadth))
    available_base = [
        c for c in dict.fromkeys(available_base)
        if c not in available_breadth
    ]

    if len(available_breadth) < 3:
        raise ValueError(
            f"Too few Breadth features available for integration test: {available_breadth}"
        )
    if len(available_base) < 3:
        available_columns = sorted(
            [str(c) for c in merged.columns if not str(c).startswith("forward_return_")]
        )
        raise ValueError(
            "Too few base features available for integration test: "
            f"{available_base}. Available integration columns: {available_columns}"
        )

    # Coverage sensitivity: all rows and >=90%.
    sample_defs = {
        "ALL_COVERAGE": merged.copy(),
        "BREADTH_COVERAGE_GE_90": merged[
            pd.to_numeric(merged["coverage_pct"], errors="coerce") >= 90.0
        ].copy(),
    }

    corr_rows = []
    partial_rows = []
    for sample_name, sample in sample_defs.items():
        if sample.empty:
            continue

        # Use at most a compact, non-redundant base control set.
        controls = available_base[:]
        # Avoid singular/near-duplicate controls by dropping highly correlated columns.
        if len(controls) > 10:
            corr = sample[controls].apply(pd.to_numeric, errors="coerce").corr().abs()
            keep = []
            for c in controls:
                if not keep or all(
                    pd.isna(corr.loc[c, k]) or corr.loc[c, k] < 0.90
                    for k in keep
                ):
                    keep.append(c)
            controls = keep[:10]

        for b in available_breadth:
            for base in available_base:
                pair = sample[[b, base]].apply(pd.to_numeric, errors="coerce").dropna()
                if len(pair) >= 30:
                    corr_rows.append({
                        "sample": sample_name,
                        "breadth_feature": b,
                        "base_feature": base,
                        "pearson_correlation": float(pair[b].corr(pair[base])),
                        "observations": len(pair),
                    })

            for outcome in [f"forward_return_{x}" for x in OUTCOME_HORIZONS]:
                corr, n = residual_partial_corr(sample, b, outcome, controls)
                partial_rows.append({
                    "sample": sample_name,
                    "breadth_feature": b,
                    "outcome": outcome,
                    "partial_correlation_controlling_base_layers": corr,
                    "observations": n,
                    "controls_used": "|".join(controls),
                })

    corr_df = pd.DataFrame(corr_rows)
    partial_df = pd.DataFrame(partial_rows)
    corr_df.to_csv(out / "research_integration_breadth_redundancy_v1.csv", index=False)
    partial_df.to_csv(out / "research_integration_breadth_partial_association_v1.csv", index=False)

    state_all = event_state_summary(sample_defs["ALL_COVERAGE"])
    state_90 = event_state_summary(sample_defs["BREADTH_COVERAGE_GE_90"])
    state_all.to_csv(out / "research_integration_breadth_states_all_v1.csv", index=False)
    state_90.to_csv(out / "research_integration_breadth_states_ge90_v1.csv", index=False)

    # Integrity / safeguards.
    safeguard_checks = {
        "research_context_rows": len(context),
        "liquidity_rows": len(liquidity),
        "breadth_rows": len(breadth),
        "merged_rows": len(merged),
        "merged_start": merged["study_date"].min().strftime("%Y-%m-%d"),
        "merged_end": merged["study_date"].max().strftime("%Y-%m-%d"),
        "breadth_features_used": available_breadth,
        "base_features_available": available_base,
        "base_feature_count": len(available_base),
        "base_features_unique": len(set(available_base)),
        "common_sample_rows_all_coverage": len(sample_defs["ALL_COVERAGE"]),
        "common_sample_rows_ge90": len(sample_defs["BREADTH_COVERAGE_GE_90"]),
        "forward_return_outcomes": list(OUTCOME_HORIZONS),
        "research_only": True,
        "decision_engine_ready": False,
        "trading_signal": False,
        "forecast": False,
        "pit_perfect": False,
    }

    # Review conditions, not a trading judgment.
    errors = []
    warnings = []

    if len(merged) < 500:
        errors.append("Common integration sample is below 500 observations.")
    if len(sample_defs["BREADTH_COVERAGE_GE_90"]) < 300:
        warnings.append("Coverage >=90% sample is below 300 observations.")

    if "point_in_time_safe" in context and not context["point_in_time_safe"].eq(True).all():
        errors.append("Research Context PIT safeguard failed.")
    if "research_only" in context and not context["research_only"].eq(True).all():
        errors.append("Research Context research-only safeguard failed.")

    # We do NOT declare Breadth useful/valuable from this test.
    # PASS means the integration study itself is structurally valid.
    final_status = "PASS" if not errors else "FAIL"

    summary = {
        "validator": "US500 Research Integration Full Validation v1",
        "purpose": "Historical association and redundancy study of Market Breadth against existing research layers.",
        "status": final_status,
        "safeguards": safeguard_checks,
        "coverage_sensitivity": {
            "all_rows": len(sample_defs["ALL_COVERAGE"]),
            "ge90_rows": len(sample_defs["BREADTH_COVERAGE_GE_90"]),
            "ge90_share_pct": round(
                len(sample_defs["BREADTH_COVERAGE_GE_90"]) / len(sample_defs["ALL_COVERAGE"]) * 100, 4
            ),
        },
        "partial_association_rows": len(partial_df),
        "redundancy_rows": len(corr_df),
        "warnings": warnings,
        "errors": errors,
        "interpretation_rule": (
            "This validation does not select, rank, score, or recommend a layer. "
            "It reports historical association, redundancy, and sample robustness only."
        ),
    }

    (out / "research_integration_full_validation_summary_v1.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False)
    )

    print("=" * 72)
    print("US500 RESEARCH INTEGRATION FULL VALIDATION v1")
    print("=" * 72)
    print(f"Common sample: {len(merged):,}")
    print(f"Date range: {merged['study_date'].min().date()} -> {merged['study_date'].max().date()}")
    print(f"Breadth features: {len(available_breadth)}")
    print(f"Base features available (unique): {len(available_base)}")
    print(f"Coverage >=90% sample: {len(sample_defs['BREADTH_COVERAGE_GE_90']):,}")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    print(f"FINAL STATUS: {final_status}")
    print("Research-only: TRUE")
    print("Decision Engine: FALSE")
    print("Trading signal: FALSE")
    print("Forecast: FALSE")
    print("PIT-perfect: FALSE")
    print("=" * 72)

    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
