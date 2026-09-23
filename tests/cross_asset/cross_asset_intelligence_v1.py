#!/usr/bin/env python3
"""
US500 Macro Intelligence
Cross-Asset Intelligence v1

Research-only cross-asset descriptive layer.

IMPORTANT:
- No trading signals
- No forecasting
- No execution
- No Decision Engine integration
- No investment recommendation
- No ranking / winner selection
- Descriptive cross-asset relationships only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import yfinance as yf


VERSION = "1.0"

RESEARCH_ONLY_FLAGS = {
    "research_only": True,
    "decision_engine_ready": False,
    "trading_signal_generated": False,
    "forecast_generated": False,
    "unified_decision_generated": False,
}


# ---------------------------------------------------------------------
# Cross-asset universe
# ---------------------------------------------------------------------

ASSETS: Dict[str, str] = {
    "SP500": "^GSPC",
    "NASDAQ": "^IXIC",
    "GOLD": "GC=F",
    "DXY": "DX-Y.NYB",
    "VIX": "^VIX",
    "US10Y": "^TNX",
    "WTI": "CL=F",
    "BITCOIN": "BTC-USD",
}


# ---------------------------------------------------------------------
# Methodology parameters
# ---------------------------------------------------------------------

START_DATE = "2000-01-01"
DOWNLOAD_BUFFER_DAYS = 40

VOL_WINDOW = 20
CORRELATION_WINDOW = 60

MIN_ASSET_COVERAGE = 0.70


# ---------------------------------------------------------------------
# Stable deterministic identifier
# ---------------------------------------------------------------------

def stable_id(*parts: str, length: int = 24) -> str:
    raw = "|".join(str(x) for x in parts)

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:length]


# ---------------------------------------------------------------------
# Yahoo Finance downloader
# ---------------------------------------------------------------------

def download_asset(
    symbol: str,
    start: str,
    end: str,
) -> pd.Series:
    """
    Download one daily close series from Yahoo Finance.

    The function explicitly normalizes yfinance's possible
    MultiIndex output so downstream code always receives
    a one-dimensional Series.
    """

    frame = yf.download(
        symbol,
        start=start,
        end=end,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
        group_by="column",
        multi_level_index=True,
    )

    if frame is None or frame.empty:
        raise RuntimeError(
            f"No data returned for {symbol}"
        )

    # -------------------------------------------------------------
    # Extract Close robustly from either normal or MultiIndex data
    # -------------------------------------------------------------

    if isinstance(frame.columns, pd.MultiIndex):

        level_zero = frame.columns.get_level_values(0)

        if "Close" not in level_zero:
            raise RuntimeError(
                f"Close column not found for {symbol}"
            )

        close = frame["Close"]

        if isinstance(close, pd.DataFrame):

            # Preferred: exact ticker column
            if symbol in close.columns:
                close = close[symbol]

            # Fallback: if only one column remains
            elif close.shape[1] == 1:
                close = close.iloc[:, 0]

            else:
                # Final deterministic fallback
                close = close.iloc[:, 0]

    else:

        if "Close" not in frame.columns:
            raise RuntimeError(
                f"Close column not found for {symbol}"
            )

        close = frame["Close"]

    # -------------------------------------------------------------
    # Guarantee Series
    # -------------------------------------------------------------

    if isinstance(close, pd.DataFrame):

        if close.shape[1] != 1:
            raise RuntimeError(
                f"Unable to reduce Close data to one Series for {symbol}"
            )

        close = close.iloc[:, 0]

    close = pd.to_numeric(
        close,
        errors="coerce",
    )

    # -------------------------------------------------------------
    # Normalize datetime index
    # -------------------------------------------------------------

    index = pd.to_datetime(
        close.index,
        errors="coerce",
    )

    try:
        if index.tz is not None:
            index = index.tz_convert(None)
    except AttributeError:
        pass

    index = index.normalize()

    close.index = index

    # Remove invalid / duplicate dates
    close = close[
        ~close.index.isna()
    ]

    close = close[
        ~close.index.duplicated(
            keep="last"
        )
    ]

    close = close.dropna()

    # Explicit index name.
    # This prevents reset_index() from creating "Date"
    # or another provider-specific column name.
    close.index.name = "observation_date"

    close.name = symbol

    if close.empty:
        raise RuntimeError(
            f"Close series is empty for {symbol}"
        )

    return close


# ---------------------------------------------------------------------
# Build Cross-Asset dataset
# ---------------------------------------------------------------------

def build_dataset(
    end_date: str,
) -> pd.DataFrame:

    end_ts = pd.Timestamp(
        end_date
    )

    download_end = (
        end_ts
        + pd.Timedelta(days=1)
    )

    download_start = (
        pd.Timestamp(START_DATE)
        - pd.Timedelta(
            days=DOWNLOAD_BUFFER_DAYS
        )
    )

    series: Dict[str, pd.Series] = {}

    collection_errors: Dict[str, str] = {}

    # -------------------------------------------------------------
    # Download requested assets
    # -------------------------------------------------------------

    for asset, symbol in ASSETS.items():

        try:

            series[asset] = download_asset(
                symbol=symbol,
                start=download_start.strftime(
                    "%Y-%m-%d"
                ),
                end=download_end.strftime(
                    "%Y-%m-%d"
                ),
            )

        except Exception as exc:

            collection_errors[asset] = (
                f"{type(exc).__name__}: {exc}"
            )

    # Require a meaningful cross-asset universe
    if len(series) < 5:

        raise RuntimeError(
            "Cross-asset collection failed: "
            "fewer than 5 requested assets were available. "
            f"Errors: {collection_errors}"
        )

    # -------------------------------------------------------------
    # Combine series
    # -------------------------------------------------------------
    #
    # sort=False explicitly avoids the pandas future warning
    # concerning sorting behavior during concatenation.
    # -------------------------------------------------------------

    prices = pd.concat(
        series,
        axis=1,
        join="outer",
        sort=False,
    )

    prices = prices.sort_index()

    # Ensure the index has the canonical name
    prices.index.name = "observation_date"

    # Apply date boundaries
    prices = prices[
        prices.index <= end_ts
    ]

    prices = prices[
        prices.index >= pd.Timestamp(
            START_DATE
        )
    ]

    if prices.empty:

        raise RuntimeError(
            "Cross-asset dataset is empty "
            "after applying date boundaries."
        )

    output = prices.copy()

    # -------------------------------------------------------------
    # Daily returns
    # -------------------------------------------------------------

    for asset in ASSETS:

        if asset not in output.columns:
            continue

        output[
            f"{asset}_RETURN_1D"
        ] = output[asset].pct_change(
            fill_method=None
        )

    # -------------------------------------------------------------
    # 20-day annualized volatility
    # -------------------------------------------------------------

    for asset in ASSETS:

        return_column = (
            f"{asset}_RETURN_1D"
        )

        if return_column not in output.columns:
            continue

        output[
            f"{asset}_VOL_20D"
        ] = (
            output[return_column]
            .rolling(
                VOL_WINDOW,
                min_periods=10,
            )
            .std()
            * np.sqrt(252.0)
        )

    # -------------------------------------------------------------
    # Cross-asset rolling correlations
    # -------------------------------------------------------------

    pairs = [
        ("SP500", "NASDAQ"),
        ("SP500", "GOLD"),
        ("SP500", "DXY"),
        ("SP500", "VIX"),
        ("SP500", "US10Y"),
        ("SP500", "WTI"),
        ("SP500", "BITCOIN"),
        ("GOLD", "DXY"),
        ("GOLD", "US10Y"),
        ("DXY", "US10Y"),
    ]

    for left, right in pairs:

        left_column = (
            f"{left}_RETURN_1D"
        )

        right_column = (
            f"{right}_RETURN_1D"
        )

        if (
            left_column not in output.columns
            or right_column not in output.columns
        ):
            continue

        output[
            f"CORR_{left}_{right}_60D"
        ] = (
            output[left_column]
            .rolling(
                CORRELATION_WINDOW,
                min_periods=30,
            )
            .corr(
                output[right_column]
            )
        )

    # -------------------------------------------------------------
    # Convert index into canonical observation_date column
    # -------------------------------------------------------------

    output.index.name = "observation_date"

    output = output.reset_index()

    # Explicit safety check
    if "observation_date" not in output.columns:

        raise RuntimeError(
            "Internal schema error: "
            "observation_date was not created after reset_index()."
        )

    output["observation_date"] = (
        pd.to_datetime(
            output["observation_date"],
            errors="coerce",
        )
        .dt.strftime("%Y-%m-%d")
    )

    if output["observation_date"].isna().any():

        raise RuntimeError(
            "Invalid observation_date values detected."
        )

    # -------------------------------------------------------------
    # Point-in-time availability convention
    # -------------------------------------------------------------
    #
    # Cross-asset daily observation becomes available to the
    # research layer on the following calendar day.
    #
    # This is deliberately conservative and avoids using the
    # observation date itself as an availability timestamp.
    # -------------------------------------------------------------

    observation_dates = pd.to_datetime(
        output["observation_date"]
    )

    output["availability_date"] = (
        observation_dates
        + pd.Timedelta(days=1)
    ).dt.strftime("%Y-%m-%d")

    # -------------------------------------------------------------
    # PIT validation flag
    # -------------------------------------------------------------

    output["point_in_time_safe"] = (
        pd.to_datetime(
            output["availability_date"]
        )
        > pd.to_datetime(
            output["observation_date"]
        )
    )

    # -------------------------------------------------------------
    # Research-only invariants
    # -------------------------------------------------------------

    output["research_only"] = True

    output["decision_engine_ready"] = False

    output["trading_signal_generated"] = False

    output["forecast_generated"] = False

    output["unified_decision_generated"] = False

    # -------------------------------------------------------------
    # Available asset count
    # -------------------------------------------------------------

    available_asset_columns = [
        asset
        for asset in ASSETS
        if asset in output.columns
    ]

    output["available_asset_count"] = (
        output[
            available_asset_columns
        ]
        .notna()
        .sum(axis=1)
    )

    # -------------------------------------------------------------
    # Stable observation ID
    # -------------------------------------------------------------

    output[
        "cross_asset_observation_id"
    ] = [
        stable_id(
            str(date),
            str(count),
        )
        for date, count in zip(
            output["observation_date"],
            output["available_asset_count"],
        )
    ]

    # Store collection errors in DataFrame metadata
    output.attrs[
        "collection_errors"
    ] = collection_errors

    return output


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------

def validate(
    data: pd.DataFrame,
    output_dir: Path,
    collection_errors: Dict[str, str],
) -> dict:

    required_columns = [
        "observation_date",
        "availability_date",
        "available_asset_count",
        "point_in_time_safe",
        "research_only",
        "decision_engine_ready",
        "trading_signal_generated",
        "forecast_generated",
        "unified_decision_generated",
        "cross_asset_observation_id",
    ]

    # Required asset columns
    for asset in ASSETS:

        required_columns.extend(
            [
                asset,
                f"{asset}_RETURN_1D",
                f"{asset}_VOL_20D",
            ]
        )

    missing_columns = [
        column
        for column in required_columns
        if column not in data.columns
    ]

    checks = {}

    # -------------------------------------------------------------
    # Dataset
    # -------------------------------------------------------------

    checks["dataset_nonempty"] = (
        len(data) > 0
    )

    checks["required_columns_present"] = (
        len(missing_columns) == 0
    )

    # -------------------------------------------------------------
    # Observation dates
    # -------------------------------------------------------------

    if "observation_date" in data.columns:

        observation_dates = pd.to_datetime(
            data["observation_date"],
            errors="coerce",
        )

        checks["observation_dates_valid"] = bool(
            observation_dates.notna().all()
        )

        checks["date_sorted"] = bool(
            data[
                "observation_date"
            ].is_monotonic_increasing
        )

        checks["dates_unique"] = bool(
            data[
                "observation_date"
            ].is_unique
        )

    else:

        checks["observation_dates_valid"] = False

        checks["date_sorted"] = False

        checks["dates_unique"] = False

    # -------------------------------------------------------------
    # Availability dates
    # -------------------------------------------------------------

    if (
        "availability_date" in data.columns
        and "observation_date" in data.columns
    ):

        availability_dates = pd.to_datetime(
            data["availability_date"],
            errors="coerce",
        )

        observation_dates = pd.to_datetime(
            data["observation_date"],
            errors="coerce",
        )

        checks["availability_dates_valid"] = bool(
            availability_dates.notna().all()
        )

        checks[
            "availability_after_observation"
        ] = bool(
            (
                availability_dates
                > observation_dates
            ).all()
        )

    else:

        checks[
            "availability_dates_valid"
        ] = False

        checks[
            "availability_after_observation"
        ] = False

    # -------------------------------------------------------------
    # PIT flag
    # -------------------------------------------------------------

    checks["point_in_time_safe_all"] = (
        bool(
            data[
                "point_in_time_safe"
            ].eq(True).all()
        )
        if "point_in_time_safe"
        in data.columns
        else False
    )

    # -------------------------------------------------------------
    # Research-only invariants
    # -------------------------------------------------------------

    checks["research_only_all"] = (
        bool(
            data[
                "research_only"
            ].eq(True).all()
        )
        if "research_only"
        in data.columns
        else False
    )

    checks["decision_engine_disabled"] = (
        bool(
            data[
                "decision_engine_ready"
            ].eq(False).all()
        )
        if "decision_engine_ready"
        in data.columns
        else False
    )

    checks["trading_signals_disabled"] = (
        bool(
            data[
                "trading_signal_generated"
            ].eq(False).all()
        )
        if "trading_signal_generated"
        in data.columns
        else False
    )

    checks["forecast_disabled"] = (
        bool(
            data[
                "forecast_generated"
            ].eq(False).all()
        )
        if "forecast_generated"
        in data.columns
        else False
    )

    checks["unified_decision_disabled"] = (
        bool(
            data[
                "unified_decision_generated"
            ].eq(False).all()
        )
        if "unified_decision_generated"
        in data.columns
        else False
    )

    # -------------------------------------------------------------
    # Asset coverage
    # -------------------------------------------------------------

    asset_coverage = {}

    for asset in ASSETS:

        if asset in data.columns:

            coverage = float(
                data[asset]
                .notna()
                .mean()
            )

            asset_coverage[asset] = round(
                coverage,
                4,
            )

        else:

            asset_coverage[asset] = 0.0

    checks["minimum_asset_coverage"] = all(
        value >= MIN_ASSET_COVERAGE
        for value in asset_coverage.values()
    )

    # -------------------------------------------------------------
    # Correlation features
    # -------------------------------------------------------------

    correlation_columns = [
        column
        for column in data.columns
        if column.startswith("CORR_")
    ]

    checks[
        "correlation_features_present"
    ] = (
        len(correlation_columns) >= 5
    )

    # -------------------------------------------------------------
    # Warnings
    # -------------------------------------------------------------

    warnings: List[str] = []

    if collection_errors:

        warnings.append(
            "One or more requested Yahoo Finance "
            "symbols were unavailable: "
            + "; ".join(
                f"{key}={value}"
                for key, value
                in collection_errors.items()
            )
        )

    # -------------------------------------------------------------
    # Overall validation
    # -------------------------------------------------------------

    passed = all(
        bool(value)
        for value in checks.values()
    )

    # -------------------------------------------------------------
    # Validation report
    # -------------------------------------------------------------

    validation = {
        "validator":
            "Cross-Asset Intelligence v1",

        "version":
            VERSION,

        "passed":
            bool(passed),

        "rows":
            int(len(data)),

        "columns":
            int(len(data.columns)),

        "date_start":
            (
                str(
                    data[
                        "observation_date"
                    ].min()
                )
                if len(data)
                else None
            ),

        "date_end":
            (
                str(
                    data[
                        "observation_date"
                    ].max()
                )
                if len(data)
                else None
            ),

        "assets_requested":
            ASSETS,

        "assets_available":
            [
                asset
                for asset in ASSETS
                if asset in data.columns
            ],

        "asset_coverage":
            asset_coverage,

        "rolling_correlation_features":
            correlation_columns,

        "missing_required_columns":
            missing_columns,

        "checks":
            checks,

        "warnings":
            warnings,

        "research_only_flags":
            RESEARCH_ONLY_FLAGS,

        "methodology": {
            "price_source":
                "Yahoo Finance via yfinance",

            "frequency":
                "daily",

            "return_definition":
                "1-day close-to-close percentage return",

            "volatility_definition":
                "20-observation rolling standard deviation "
                "annualized by sqrt(252)",

            "correlation_definition":
                "60-observation rolling Pearson correlation "
                "of daily returns",

            "pit_convention":
                "availability_date = observation_date + "
                "1 calendar day",

            "missing_session_policy":
                "No forward-fill across different asset sessions",
        },
    }

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    (
        output_dir
        / "cross_asset_validation_v1.json"
    ).write_text(
        json.dumps(
            validation,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    # -------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------

    summary = {
        "validator":
            "Cross-Asset Intelligence v1",

        "version":
            VERSION,

        "research_only":
            True,

        "decision_engine_ready":
            False,

        "trading_signal_generated":
            False,

        "forecast_generated":
            False,

        "unified_decision_generated":
            False,

        "rows":
            int(len(data)),

        "columns":
            int(len(data.columns)),

        "date_start":
            validation["date_start"],

        "date_end":
            validation["date_end"],

        "available_assets":
            validation["assets_available"],

        "asset_coverage":
            asset_coverage,

        "correlation_feature_count":
            len(correlation_columns),

        "point_in_time_safe":
            bool(
                checks[
                    "point_in_time_safe_all"
                ]
            ),

        "passed":
            bool(passed),
    }

    (
        output_dir
        / "cross_asset_summary_v1.json"
    ).write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    return validation


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> int:

    parser = argparse.ArgumentParser(
        description=
        "Cross-Asset Intelligence v1"
    )

    parser.add_argument(
        "--output",
        default=
        "cross_asset_intelligence_v1",
        help="Output directory",
    )

    parser.add_argument(
        "--as-of-date",
        default=
        pd.Timestamp.now(
            "UTC"
        ).strftime("%Y-%m-%d"),
        help=
        "Inclusive research cutoff date YYYY-MM-DD",
    )

    args = parser.parse_args()

    output_dir = Path(
        args.output
    )

    # -------------------------------------------------------------
    # Build dataset
    # -------------------------------------------------------------

    try:

        data = build_dataset(
            args.as_of_date
        )

    except Exception as exc:

        print(
            f"ERROR: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )

        return 1

    # -------------------------------------------------------------
    # Output directory
    # -------------------------------------------------------------

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # -------------------------------------------------------------
    # Research dataset
    # -------------------------------------------------------------

    data.to_csv(
        output_dir
        / "cross_asset_research_v1.csv",
        index=False,
    )

    # -------------------------------------------------------------
    # Collection errors
    # -------------------------------------------------------------

    collection_errors = (
        data.attrs.get(
            "collection_errors",
            {},
        )
    )

    # -------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------

    validation = validate(
        data=data,
        output_dir=output_dir,
        collection_errors=
            collection_errors,
    )

    # -------------------------------------------------------------
    # Console report
    # -------------------------------------------------------------

    print("=" * 60)

    print(
        "CROSS-ASSET INTELLIGENCE v1"
    )

    print("=" * 60)

    print(
        f"Rows: "
        f"{validation['rows']:,}"
    )

    print(
        f"Columns: "
        f"{validation['columns']:,}"
    )

    print(
        "Date range: "
        f"{validation['date_start']} -> "
        f"{validation['date_end']}"
    )

    print(
        "Assets available: "
        + ", ".join(
            validation[
                "assets_available"
            ]
        )
    )

    print(
        "Rolling correlation features: "
        f"{len(validation['rolling_correlation_features'])}"
    )

    print(
        "PIT safe: "
        f"{validation['checks']['point_in_time_safe_all']}"
    )

    print(
        "Research only: TRUE"
    )

    print(
        "Decision Engine: FALSE"
    )

    print(
        "Trading signal: FALSE"
    )

    print(
        "Forecast: FALSE"
    )

    print(
        "Unified decision: FALSE"
    )

    # -------------------------------------------------------------
    # Warnings
    # -------------------------------------------------------------

    if validation["warnings"]:

        print(
            "WARNINGS:"
        )

        for warning in validation[
            "warnings"
        ]:

            print(
                f"- {warning}"
            )

    # -------------------------------------------------------------
    # Final status
    # -------------------------------------------------------------

    if not validation["passed"]:

        print(
            "CROSS-ASSET INTELLIGENCE "
            "VALIDATION FAILED"
        )

        return 1

    print(
        "CROSS-ASSET INTELLIGENCE "
        "VALIDATION PASSED"
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
