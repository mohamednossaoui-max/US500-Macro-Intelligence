#!/usr/bin/env python3
"""
Market Breadth Analyzer v1

Research-only analysis layer for the Market Breadth Historical Collector v1.

Design principles:
- No trading signals
- No forecasts
- No Decision Engine integration
- Preserve research/PIT quality flags
- Use only information available on or before each as-of date
- Avoid arbitrary threshold-based "buy/sell" regimes
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


RESEARCH_ONLY = True
DECISION_ENGINE_READY = False
TRADING_SIGNAL = False
FORECAST = False

MIN_COVERAGE_PCT = 75.0
ROLLING_Z_WINDOW = 252
ROLLING_Z_MIN_PERIODS = 126


def zscore_rolling(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    mean = series.rolling(window=window, min_periods=min_periods).mean()
    std = series.rolling(window=window, min_periods=min_periods).std(ddof=0)
    return (series - mean) / std.replace(0, np.nan)


def load_input(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    required = [
        "asof_date",
        "universe_count",
        "price_eligible_count",
        "missing_price_count",
        "coverage_pct",
        "coverage_quality",
        "advances",
        "declines",
        "unchanged",
        "net_advances",
        "advance_decline_ratio",
        "pct_advancing",
        "pct_declining",
        "cumulative_ad_line",
        "point_in_time_reconstructed",
        "membership_source",
        "membership_quality",
        "cross_validated",
        "pit_perfect",
        "price_source",
        "price_quality",
        "price_pit_perfect",
        "research_only",
        "decision_engine_ready",
        "trading_signal",
        "forecast",
        "record_id",
    ]

    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["asof_date"] = pd.to_datetime(df["asof_date"], errors="coerce")
    if df["asof_date"].isna().any():
        raise ValueError("Invalid asof_date values found.")

    df = df.sort_values("asof_date").reset_index(drop=True)

    if df["asof_date"].duplicated().any():
        raise ValueError("Duplicate asof_date values found.")

    if df["record_id"].duplicated().any():
        raise ValueError("Duplicate record_id values found.")

    return df


def validate_input(df: pd.DataFrame) -> dict:
    checks = {}

    checks["row_count"] = int(len(df))
    checks["date_start"] = df["asof_date"].min().strftime("%Y-%m-%d")
    checks["date_end"] = df["asof_date"].max().strftime("%Y-%m-%d")
    checks["duplicate_dates"] = int(df["asof_date"].duplicated().sum())
    checks["duplicate_record_ids"] = int(df["record_id"].duplicated().sum())

    checks["invalid_net_advances"] = int(
        (df["net_advances"] != (df["advances"] - df["declines"])).sum()
    )

    checks["invalid_participation_count"] = int(
        (
            (df["advances"] + df["declines"] + df["unchanged"])
            != df["price_eligible_count"]
        ).sum()
    )

    checks["coverage_below_minimum"] = int(
        (df["coverage_pct"] < MIN_COVERAGE_PCT).sum()
    )

    checks["coverage_min_pct"] = float(df["coverage_pct"].min())
    checks["coverage_mean_pct"] = float(df["coverage_pct"].mean())
    checks["coverage_max_pct"] = float(df["coverage_pct"].max())

    checks["research_only_all_true"] = bool(df["research_only"].all())
    checks["decision_engine_ready_all_false"] = bool(
        (~df["decision_engine_ready"].astype(bool)).all()
    )
    checks["trading_signal_all_false"] = bool(
        (~df["trading_signal"].astype(bool)).all()
    )
    checks["forecast_all_false"] = bool((~df["forecast"].astype(bool)).all())

    checks["validation_pass"] = all(
        [
            checks["row_count"] > 0,
            checks["duplicate_dates"] == 0,
            checks["duplicate_record_ids"] == 0,
            checks["invalid_net_advances"] == 0,
            checks["invalid_participation_count"] == 0,
            checks["coverage_below_minimum"] == 0,
            checks["research_only_all_true"],
            checks["decision_engine_ready_all_false"],
            checks["trading_signal_all_false"],
            checks["forecast_all_false"],
        ]
    )

    return checks


def analyze(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # Daily normalized breadth measures.
    eligible = out["price_eligible_count"].replace(0, np.nan)

    out["net_advances_pct_eligible"] = (
        out["net_advances"] / eligible * 100.0
    )

    # Rolling breadth aggregates.
    out["advances_5d"] = out["advances"].rolling(5, min_periods=5).sum()
    out["declines_5d"] = out["declines"].rolling(5, min_periods=5).sum()
    out["net_advances_5d"] = (
        out["advances_5d"] - out["declines_5d"]
    )

    out["advances_20d"] = out["advances"].rolling(20, min_periods=20).sum()
    out["declines_20d"] = out["declines"].rolling(20, min_periods=20).sum()
    out["net_advances_20d"] = (
        out["advances_20d"] - out["declines_20d"]
    )

    out["pct_advancing_20d_avg"] = (
        out["pct_advancing"].rolling(20, min_periods=20).mean()
    )
    out["pct_declining_20d_avg"] = (
        out["pct_declining"].rolling(20, min_periods=20).mean()
    )

    # Aggregate 20-day A/D ratio is preferable to averaging daily ratios.
    out["advance_decline_ratio_20d"] = (
        out["advances_20d"] / out["declines_20d"].replace(0, np.nan)
    )

    # A/D line changes.
    out["ad_line_change_20d"] = (
        out["cumulative_ad_line"]
        - out["cumulative_ad_line"].shift(20)
    )
    out["ad_line_change_60d"] = (
        out["cumulative_ad_line"]
        - out["cumulative_ad_line"].shift(60)
    )

    # Rolling z-scores use only trailing observations.
    out["net_advances_z_252d"] = zscore_rolling(
        out["net_advances"],
        ROLLING_Z_WINDOW,
        ROLLING_Z_MIN_PERIODS,
    )
    out["net_advances_20d_z_252d"] = zscore_rolling(
        out["net_advances_20d"],
        ROLLING_Z_WINDOW,
        ROLLING_Z_MIN_PERIODS,
    )
    out["pct_advancing_20d_z_252d"] = zscore_rolling(
        out["pct_advancing_20d_avg"],
        ROLLING_Z_WINDOW,
        ROLLING_Z_MIN_PERIODS,
    )
    out["ad_line_change_20d_z_252d"] = zscore_rolling(
        out["ad_line_change_20d"],
        ROLLING_Z_WINDOW,
        ROLLING_Z_MIN_PERIODS,
    )

    # Descriptive research state only.
    # This is NOT a trading regime or signal.
    out["breadth_research_state"] = np.select(
        [
            out["net_advances_20d"] > 0,
            out["net_advances_20d"] < 0,
        ],
        [
            "POSITIVE_BREADTH",
            "NEGATIVE_BREADTH",
        ],
        default="BALANCED_BREADTH",
    )

    # Explicit quality propagation.
    out["analysis_point_in_time_reconstructed"] = (
        out["point_in_time_reconstructed"]
    )
    out["analysis_pit_perfect"] = False
    out["analysis_research_only"] = True
    out["analysis_decision_engine_ready"] = False
    out["analysis_trading_signal"] = False
    out["analysis_forecast"] = False

    out["analysis_record_id"] = (
        "MBA_" + out["asof_date"].dt.strftime("%Y%m%d")
    )

    return out


def build_summary(
    analyzed: pd.DataFrame,
    input_validation: dict,
) -> dict:
    latest = analyzed.iloc[-1]

    numeric_summary = {}
    for col in [
        "coverage_pct",
        "net_advances",
        "pct_advancing",
        "pct_declining",
        "cumulative_ad_line",
        "net_advances_5d",
        "net_advances_20d",
        "pct_advancing_20d_avg",
        "pct_declining_20d_avg",
        "advance_decline_ratio_20d",
        "ad_line_change_20d",
        "ad_line_change_60d",
        "net_advances_z_252d",
        "net_advances_20d_z_252d",
        "pct_advancing_20d_z_252d",
        "ad_line_change_20d_z_252d",
    ]:
        value = latest[col]
        numeric_summary[col] = None if pd.isna(value) else float(value)

    return {
        "analyzer": "Market Breadth Analyzer v1",
        "research_only": True,
        "decision_engine_ready": False,
        "trading_signal": False,
        "forecast": False,
        "point_in_time_reconstructed": True,
        "pit_perfect": False,
        "membership_source": "FREE_PUBLIC_RECONSTRUCTION",
        "membership_quality": "RESEARCH_GRADE",
        "price_source": "YAHOO_FINANCE_YFINANCE",
        "price_quality": "FREE_PUBLIC_RESEARCH_GRADE",
        "input_validation": input_validation,
        "analysis_row_count": int(len(analyzed)),
        "analysis_date_start": analyzed["asof_date"].min().strftime("%Y-%m-%d"),
        "analysis_date_end": analyzed["asof_date"].max().strftime("%Y-%m-%d"),
        "latest_asof_date": latest["asof_date"].strftime("%Y-%m-%d"),
        "latest_breadth_research_state": latest["breadth_research_state"],
        "latest": numeric_summary,
    }


def validate_output(analyzed: pd.DataFrame) -> dict:
    required_output = [
        "asof_date",
        "net_advances_5d",
        "net_advances_20d",
        "pct_advancing_20d_avg",
        "pct_declining_20d_avg",
        "advance_decline_ratio_20d",
        "ad_line_change_20d",
        "ad_line_change_60d",
        "net_advances_z_252d",
        "net_advances_20d_z_252d",
        "pct_advancing_20d_z_252d",
        "ad_line_change_20d_z_252d",
        "breadth_research_state",
        "analysis_point_in_time_reconstructed",
        "analysis_pit_perfect",
        "analysis_research_only",
        "analysis_decision_engine_ready",
        "analysis_trading_signal",
        "analysis_forecast",
        "analysis_record_id",
    ]

    missing = [c for c in required_output if c not in analyzed.columns]

    return {
        "missing_output_columns": missing,
        "duplicate_analysis_dates": int(analyzed["asof_date"].duplicated().sum()),
        "duplicate_analysis_record_ids": int(
            analyzed["analysis_record_id"].duplicated().sum()
        ),
        "analysis_research_only_all_true": bool(
            analyzed["analysis_research_only"].all()
        ),
        "analysis_decision_engine_ready_all_false": bool(
            (~analyzed["analysis_decision_engine_ready"]).all()
        ),
        "analysis_trading_signal_all_false": bool(
            (~analyzed["analysis_trading_signal"]).all()
        ),
        "analysis_forecast_all_false": bool(
            (~analyzed["analysis_forecast"]).all()
        ),
        "pit_perfect_all_false": bool((~analyzed["analysis_pit_perfect"]).all()),
        "validation_pass": bool(
            len(missing) == 0
            and analyzed["asof_date"].duplicated().sum() == 0
            and analyzed["analysis_record_id"].duplicated().sum() == 0
            and analyzed["analysis_research_only"].all()
            and (~analyzed["analysis_decision_engine_ready"]).all()
            and (~analyzed["analysis_trading_signal"]).all()
            and (~analyzed["analysis_forecast"]).all()
            and (~analyzed["analysis_pit_perfect"]).all()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Market Breadth Analyzer v1"
    )
    parser.add_argument(
        "--input",
        default="market_breadth_historical_v1/market_breadth_records_v1.csv",
    )
    parser.add_argument(
        "--output",
        default="market_breadth_analysis_v1",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = load_input(input_path)
    input_validation = validate_input(df)

    if not input_validation["validation_pass"]:
        raise ValueError(
            "Input validation failed. "
            + json.dumps(input_validation, indent=2)
        )

    analyzed = analyze(df)
    output_validation = validate_output(analyzed)

    output_csv = output_dir / "market_breadth_analysis_v1.csv"
    summary_json = output_dir / "market_breadth_analysis_summary_v1.json"
    validation_json = output_dir / "market_breadth_analysis_validation_v1.json"

    analyzed.to_csv(output_csv, index=False)

    summary = build_summary(analyzed, input_validation)
    summary["output_validation"] = output_validation

    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    with open(validation_json, "w", encoding="utf-8") as f:
        json.dump(output_validation, f, indent=2, ensure_ascii=False)

    print("==============================================")
    print("MARKET BREADTH ANALYZER v1")
    print("==============================================")
    print(f"Rows: {len(analyzed)}")
    print(
        f"Date range: "
        f"{analyzed['asof_date'].min().date()} -> "
        f"{analyzed['asof_date'].max().date()}"
    )
    print(f"Coverage mean: {analyzed['coverage_pct'].mean():.2f}%")
    print(f"Coverage min: {analyzed['coverage_pct'].min():.2f}%")
    print(f"Coverage max: {analyzed['coverage_pct'].max():.2f}%")
    print()
    print("Latest:")
    latest = analyzed.iloc[-1]
    print(f"  asof_date: {latest['asof_date'].date()}")
    print(f"  net_advances: {latest['net_advances']}")
    print(f"  pct_advancing: {latest['pct_advancing']:.2f}%")
    print(f"  pct_declining: {latest['pct_declining']:.2f}%")
    print(f"  cumulative_ad_line: {latest['cumulative_ad_line']}")
    print(f"  net_advances_20d: {latest['net_advances_20d']}")
    print(
        f"  pct_advancing_20d_avg: "
        f"{latest['pct_advancing_20d_avg']:.2f}"
    )
    print(
        f"  ad_line_change_20d: "
        f"{latest['ad_line_change_20d']}"
    )
    print(
        f"  breadth_research_state: "
        f"{latest['breadth_research_state']}"
    )
    print()
    print("Research-only: TRUE")
    print("PIT-perfect: FALSE")
    print("Decision Engine ready: FALSE")
    print("Trading signal: FALSE")
    print("Forecast: FALSE")
    print()
    print(
        "FINAL STATUS: "
        + ("PASS" if output_validation["validation_pass"] else "FAIL")
    )


if __name__ == "__main__":
    main()
