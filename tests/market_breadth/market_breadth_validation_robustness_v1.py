#!/usr/bin/env python3
"""
Market Breadth — Validation & Robustness v1

Research-only validation layer.
No trading signals, forecasts, rankings, or Decision Engine integration.

Input:
    market_breadth_analysis_v1.csv

Outputs:
    market_breadth_robustness_summary_v1.json
    market_breadth_coverage_robustness_v1.csv
    market_breadth_state_robustness_v1.csv
    market_breadth_window_robustness_v1.csv
    market_breadth_lookahead_audit_v1.csv
    market_breadth_robustness_validation_v1.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


REQUIRED = [
    "asof_date", "universe_count", "price_eligible_count", "coverage_pct",
    "advances", "declines", "unchanged", "net_advances",
    "pct_advancing", "pct_declining", "cumulative_ad_line",
    "net_advances_5d", "net_advances_20d", "pct_advancing_20d_avg",
    "pct_declining_20d_avg", "advance_decline_ratio_20d",
    "ad_line_change_20d", "ad_line_change_60d",
    "net_advances_z_252d", "net_advances_20d_z_252d",
    "pct_advancing_20d_z_252d", "ad_line_change_20d_z_252d",
    "breadth_research_state",
    "point_in_time_reconstructed", "membership_source",
    "membership_quality", "cross_validated", "pit_perfect",
    "price_source", "price_quality", "price_pit_perfect",
    "research_only", "decision_engine_ready", "trading_signal", "forecast",
]


def bool_all(s):
    return bool(s.astype(bool).all())


def pct(x):
    return round(float(x) * 100.0, 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    inp = Path(args.input)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(inp)
    df["asof_date"] = pd.to_datetime(df["asof_date"], errors="coerce")
    df = df.sort_values("asof_date").reset_index(drop=True)

    errors = []
    warnings = []

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        errors.append(f"Missing required columns: {missing}")

    if df["asof_date"].isna().any():
        errors.append("Invalid asof_date values found.")

    if df["asof_date"].duplicated().any():
        errors.append("Duplicate asof_date values found.")

    # 1) Core accounting identities
    identity_ok = (
        (df["advances"] + df["declines"] + df["unchanged"]
         == df["price_eligible_count"]).all()
        and (df["net_advances"] == df["advances"] - df["declines"]).all()
    )
    if not identity_ok:
        errors.append("Breadth accounting identities failed.")

    # 2) Coverage robustness
    thresholds = [75.0, 80.0, 85.0, 90.0, 95.0, 100.0]
    coverage_rows = []
    for t in thresholds:
        sub = df[df["coverage_pct"] >= t].copy()
        coverage_rows.append({
            "coverage_threshold_pct": t,
            "rows": int(len(sub)),
            "row_share_pct": pct(len(sub) / len(df)) if len(df) else 0.0,
            "mean_coverage_pct": round(float(sub["coverage_pct"].mean()), 4) if len(sub) else np.nan,
            "positive_state_share_pct": pct((sub["breadth_research_state"] == "POSITIVE_BREADTH").mean()) if len(sub) else np.nan,
            "negative_state_share_pct": pct((sub["breadth_research_state"] == "NEGATIVE_BREADTH").mean()) if len(sub) else np.nan,
            "balanced_state_share_pct": pct((sub["breadth_research_state"] == "BALANCED_BREADTH").mean()) if len(sub) else np.nan,
            "mean_net_advances": round(float(sub["net_advances"].mean()), 6) if len(sub) else np.nan,
            "mean_net_advances_20d": round(float(sub["net_advances_20d"].mean()), 6) if len(sub) else np.nan,
        })

    coverage_df = pd.DataFrame(coverage_rows)
    coverage_df.to_csv(out / "market_breadth_coverage_robustness_v1.csv", index=False)

    # 3) State distribution
    state_counts = df["breadth_research_state"].value_counts(dropna=False)
    state_rows = []
    for state, count in state_counts.items():
        state_rows.append({
            "breadth_research_state": state,
            "count": int(count),
            "share_pct": pct(count / len(df)) if len(df) else 0.0,
        })
    state_df = pd.DataFrame(state_rows)
    state_df.to_csv(out / "market_breadth_state_robustness_v1.csv", index=False)

    allowed_states = {"POSITIVE_BREADTH", "NEGATIVE_BREADTH", "BALANCED_BREADTH"}
    if not set(df["breadth_research_state"].dropna()).issubset(allowed_states):
        errors.append("Unexpected breadth_research_state value found.")

    # 4) Window robustness
    window_specs = [
        ("5D", "net_advances_5d"),
        ("20D", "net_advances_20d"),
        ("60D_AD_LINE", "ad_line_change_60d"),
    ]
    window_rows = []
    for label, col in window_specs:
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        window_rows.append({
            "window": label,
            "column": col,
            "available_rows": int(s.notna().sum()),
            "mean": round(float(s.mean()), 6) if len(s) else np.nan,
            "median": round(float(s.median()), 6) if len(s) else np.nan,
            "std": round(float(s.std(ddof=1)), 6) if len(s) > 1 else np.nan,
            "min": round(float(s.min()), 6) if len(s) else np.nan,
            "max": round(float(s.max()), 6) if len(s) else np.nan,
        })

    # Compare 20D net advances and 20D A/D-line change.
    diff20 = (df["net_advances_20d"] - df["ad_line_change_20d"]).abs()
    window_rows.append({
        "window": "20D_IDENTITY",
        "column": "net_advances_20d_vs_ad_line_change_20d",
        "available_rows": int(diff20.notna().sum()),
        "mean": round(float(diff20.mean()), 10),
        "median": round(float(diff20.median()), 10),
        "std": round(float(diff20.std(ddof=1)), 10) if diff20.notna().sum() > 1 else np.nan,
        "min": round(float(diff20.min()), 10),
        "max": round(float(diff20.max()), 10),
    })
    if (diff20.dropna() > 1e-9).any():
        errors.append("20D net advances and 20D A/D-line change identity failed.")

    window_df = pd.DataFrame(window_rows)
    window_df.to_csv(out / "market_breadth_window_robustness_v1.csv", index=False)

    # 5) A/D line continuity
    ad_diff = df["cumulative_ad_line"].diff()
    ad_identity_error = (ad_diff - df["net_advances"]).abs()
    # First row has no prior A/D value and is intentionally excluded.
    if (ad_identity_error.iloc[1:].dropna() > 1e-9).any():
        errors.append("Cumulative A/D line continuity failed.")

    # 6) Rolling z-score no-lookahead audit.
    # Recompute the analyzer's trailing z-score exactly: 252-observation window,
    # minimum 126 non-null observations, population standard deviation (ddof=0).
    z_cols = [
        ("net_advances", "net_advances_z_252d"),
        ("net_advances_20d", "net_advances_20d_z_252d"),
        ("pct_advancing_20d_avg", "pct_advancing_20d_z_252d"),
        ("ad_line_change_20d", "ad_line_change_20d_z_252d"),
    ]
    audit_rows = []
    for raw_col, z_col in z_cols:
        raw = pd.to_numeric(df[raw_col], errors="coerce")
        recomputed = (
            raw.rolling(window=252, min_periods=126)
               .apply(lambda x: (x.iloc[-1] - x.mean()) / x.std(ddof=0)
                      if x.std(ddof=0) != 0 else np.nan,
                      raw=False)
        )
        supplied = pd.to_numeric(df[z_col], errors="coerce")
        mask = recomputed.notna() & supplied.notna()
        if mask.any():
            max_abs = float((recomputed[mask] - supplied[mask]).abs().max())
            mean_abs = float((recomputed[mask] - supplied[mask]).abs().mean())
        else:
            max_abs = np.nan
            mean_abs = np.nan

        audit_rows.append({
            "raw_column": raw_col,
            "z_column": z_col,
            "recomputed_rows": int(recomputed.notna().sum()),
            "compared_rows": int(mask.sum()),
            "max_abs_difference": max_abs,
            "mean_abs_difference": mean_abs,
            "no_lookahead_check": bool(max_abs <= 1e-8) if not np.isnan(max_abs) else True,
        })
        if not np.isnan(max_abs) and max_abs > 1e-8:
            errors.append(f"Rolling z-score mismatch for {z_col}.")

    audit_df = pd.DataFrame(audit_rows)
    audit_df.to_csv(out / "market_breadth_lookahead_audit_v1.csv", index=False)

    # 7) Metadata / research-only audit
    bool_requirements = {
        "point_in_time_reconstructed": True,
        "cross_validated": True,
        "pit_perfect": False,
        "price_pit_perfect": False,
        "research_only": True,
        "decision_engine_ready": False,
        "trading_signal": False,
        "forecast": False,
    }
    metadata_results = {}
    for col, expected in bool_requirements.items():
        ok = bool((df[col] == expected).all())
        metadata_results[col] = ok
        if not ok:
            errors.append(f"Metadata audit failed: {col} != {expected} for all rows.")

    # 8) Data availability / warm-up checks
    # Each z-score source can have a different warm-up because 20D-derived
    # series contain leading NaNs. Validate against the analyzer's actual rule.
    for raw_col, z_col in z_cols:
        raw = pd.to_numeric(df[raw_col], errors="coerce")
        expected_valid = int(
            raw.rolling(window=252, min_periods=126).count().ge(126).sum()
        )
        actual_valid = int(df[z_col].notna().sum())
        if actual_valid != expected_valid:
            warnings.append(
                f"Unexpected z-score warm-up for {z_col}: "
                f"expected {expected_valid}, got {actual_valid}."
            )

    summary = {
        "validator": "Market Breadth Validation & Robustness v1",
        "research_only": True,
        "decision_engine_ready": False,
        "trading_signal": False,
        "forecast": False,
        "pit_perfect": False,
        "input": {
            "row_count": int(len(df)),
            "date_start": df["asof_date"].min().strftime("%Y-%m-%d"),
            "date_end": df["asof_date"].max().strftime("%Y-%m-%d"),
            "mean_coverage_pct": round(float(df["coverage_pct"].mean()), 6),
            "min_coverage_pct": round(float(df["coverage_pct"].min()), 6),
            "max_coverage_pct": round(float(df["coverage_pct"].max()), 6),
        },
        "coverage_robustness": coverage_rows,
        "state_distribution": state_rows,
        "lookahead_audit": audit_rows,
        "metadata_audit": metadata_results,
        "warnings": warnings,
        "errors": errors,
        "validation_pass": len(errors) == 0,
    }

    with open(out / "market_breadth_robustness_summary_v1.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    validation = {
        "validation_pass": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "duplicate_dates": int(df["asof_date"].duplicated().sum()),
        "accounting_identity_pass": bool(identity_ok),
        "ad_line_continuity_pass": bool((ad_identity_error.iloc[1:].dropna() <= 1e-9).all()),
        "twenty_day_identity_pass": bool((diff20.dropna() <= 1e-9).all()),
        "metadata_audit_pass": all(metadata_results.values()),
        "lookahead_audit_pass": bool(all(a["no_lookahead_check"] for a in audit_rows)),
        "research_only_all_true": bool(df["research_only"].all()),
        "decision_engine_ready_all_false": bool((~df["decision_engine_ready"]).all()),
        "trading_signal_all_false": bool((~df["trading_signal"]).all()),
        "forecast_all_false": bool((~df["forecast"]).all()),
        "pit_perfect_all_false": bool((~df["pit_perfect"]).all()),
    }

    with open(out / "market_breadth_robustness_validation_v1.json", "w", encoding="utf-8") as f:
        json.dump(validation, f, indent=2)

    print("==============================================")
    print("MARKET BREADTH VALIDATION & ROBUSTNESS v1")
    print("==============================================")
    print(f"Rows: {len(df)}")
    print(f"Date range: {df['asof_date'].min().date()} -> {df['asof_date'].max().date()}")
    print(f"Mean coverage: {df['coverage_pct'].mean():.4f}%")
    print(f"Min coverage: {df['coverage_pct'].min():.4f}%")
    print(f"Duplicate dates: {df['asof_date'].duplicated().sum()}")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    print(f"FINAL STATUS: {'PASS' if len(errors) == 0 else 'FAIL'}")

    raise SystemExit(0 if len(errors) == 0 else 1)


if __name__ == "__main__":
    main()
