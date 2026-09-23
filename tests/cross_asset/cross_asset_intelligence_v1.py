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


# ============================================================
# CROSS-ASSET UNIVERSE
# ============================================================

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


# ============================================================
# METHODOLOGY PARAMETERS
# ============================================================

START_DATE = "2000-01-01"

DOWNLOAD_BUFFER_DAYS = 40

VOL_WINDOW = 20

CORRELATION_WINDOW = 60

MIN_ASSET_COVERAGE = 0.70


# ============================================================
# STABLE ID
# ============================================================

def stable_id(
    *parts: str,
    length: int = 24,
) -> str:

    raw = "|".join(
        str(x)
        for x in parts
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:length]


# ============================================================
# DOWNLOAD ONE ASSET
# ============================================================

def download_asset(
    symbol: str,
    start: str,
    end: str,
) -> pd.Series:
    """
    Download one daily close series from Yahoo Finance.

    Handles both normal and MultiIndex yfinance output.
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

    # --------------------------------------------------------
    # Extract Close
    # --------------------------------------------------------

    if isinstance(
        frame.columns,
        pd.MultiIndex,
    ):

        level_zero = (
            frame.columns
            .get_level_values(0)
        )

        if "Close" not in level_zero:

            raise RuntimeError(
                f"Close column not found for {symbol}"
            )

        close = frame["Close"]

        if isinstance(
            close,
            pd.DataFrame,
        ):

            if symbol in close.columns:

                close = close[symbol]

            elif close.shape[1] == 1:

                close = close.iloc[:, 0]

            else:

                close = close.iloc[:, 0]

    else:

        if "Close" not in frame.columns:

            raise RuntimeError(
                f"Close column not found for {symbol}"
            )

        close = frame["Close"]

    # --------------------------------------------------------
    # Guarantee one-dimensional Series
    # --------------------------------------------------------

    if isinstance(
        close,
        pd.DataFrame,
    ):

        if close.shape[1] != 1:

            raise RuntimeError(
                f"Unable to reduce Close data "
                f"to one Series for {symbol}"
            )

        close = close.iloc[:, 0]

    close = pd.to_numeric(
        close,
        errors="coerce",
    )

    # --------------------------------------------------------
    # Normalize datetime index
    # --------------------------------------------------------

    index = pd.to_datetime(
        close.index,
        errors="coerce",
    )

    try:

        if index.tz is not None:

            index = index.tz_convert(
                None
            )

    except AttributeError:

        pass

    index = index.normalize()

    close.index = index

    # --------------------------------------------------------
    # Remove invalid / duplicate dates
    # --------------------------------------------------------

    close = close[
        ~close.index.isna()
    ]

    close = close[
        ~close.index.duplicated(
            keep="last"
        )
    ]

    close = close.dropna()

    # Canonical index name
    close.index.name = (
        "observation_date"
    )

    close.name = symbol

    if close.empty:

        raise RuntimeError(
            f"Close series is empty for {symbol}"
        )

    return close


# ============================================================
# BUILD DATASET
# ============================================================

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

    series: Dict[
        str,
        pd.Series
    ] = {}

    collection_errors: Dict[
        str,
        str
    ] = {}

    # --------------------------------------------------------
    # Download all assets
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Require meaningful universe
    # --------------------------------------------------------

    if len(series) < 5:

        raise RuntimeError(
            "Cross-asset collection failed: "
            "fewer than 5 requested assets "
            "were available. "
            f"Errors: {collection_errors}"
        )

    # --------------------------------------------------------
    # Combine price series
    # --------------------------------------------------------

    prices = pd.concat(
        series,
        axis=1,
        join="outer",
        sort=False,
    )

    prices = prices.sort_index()

    prices.index.name = (
        "observation_date"
    )

    # --------------------------------------------------------
    # Date boundaries
    # --------------------------------------------------------

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

    # ========================================================
    # DAILY RETURNS
    # ========================================================

    for asset in ASSETS:

        if asset not in output.columns:

            continue

        output[
            f"{asset}_RETURN_1D"
        ] = output[
            asset
        ].pct_change(
            fill_method=None
        )

    # ========================================================
    # 20-DAY ANNUALIZED VOLATILITY
    # ========================================================

    for asset in ASSETS:

        return_column = (
            f"{asset}_RETURN_1D"
        )

        if return_column not in output.columns:

            continue

        output[
            f"{asset}_VOL_20D"
        ] = (
            output[
                return_column
            ]
            .rolling(
                VOL_WINDOW,
                min_periods=10,
            )
            .std()
            * np.sqrt(252.0)
        )

    # ========================================================
    # CROSS-ASSET CORRELATIONS
    # ========================================================

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
            output[
                left_column
            ]
            .rolling(
                CORRELATION_WINDOW,
                min_periods=30,
            )
            .corr(
                output[
                    right_column
                ]
            )
        )

    # ========================================================
    # CANONICAL OBSERVATION DATE
    # ========================================================

    output.index.name = (
        "observation_date"
    )

    output = output.reset_index()

    if (
        "observation_date"
        not in output.columns
    ):

        raise RuntimeError(
            "Internal schema error: "
            "observation_date was not created "
            "after reset_index()."
        )

    output[
        "observation_date"
    ] = (
        pd.to_datetime(
            output[
                "observation_date"
            ],
            errors="coerce",
        )
        .dt.strftime(
            "%Y-%m-%d"
        )
    )

    if (
        output[
            "observation_date"
        ].isna().any()
    ):

        raise RuntimeError(
            "Invalid observation_date "
            "values detected."
        )

    # ========================================================
    # POINT-IN-TIME AVAILABILITY
    # ========================================================

    observation_dates = pd.to_datetime(
        output[
            "observation_date"
        ]
    )

    output[
        "availability_date"
    ] = (
        observation_dates
        + pd.Timedelta(days=1)
    ).dt.strftime(
        "%Y-%m-%d"
    )

    output[
        "point_in_time_safe"
    ] = (
        pd.to_datetime(
            output[
                "availability_date"
            ]
        )
        >
        pd.to_datetime(
            output[
                "observation_date"
            ]
        )
    )

    # ========================================================
    # RESEARCH-ONLY FLAGS
    # ========================================================

    output[
        "research_only"
    ] = True

    output[
        "decision_engine_ready"
    ] = False

    output[
        "trading_signal_generated"
    ] = False

    output[
        "forecast_generated"
    ] = False

    output[
        "unified_decision_generated"
    ] = False

    # ========================================================
    # AVAILABLE ASSET COUNT
    # ========================================================

    available_asset_columns = [
        asset
        for asset in ASSETS
        if asset in output.columns
    ]

    output[
        "available_asset_count"
    ] = (
        output[
            available_asset_columns
        ]
        .notna()
        .sum(axis=1)
    )

    # ========================================================
    # STABLE OBSERVATION ID
    # ========================================================

    output[
        "cross_asset_observation_id"
    ] = [

        stable_id(
            str(date),
            str(count),
        )

        for date, count in zip(
            output[
                "observation_date"
            ],
            output[
                "available_asset_count"
            ],
        )
    ]

    # Preserve collection errors
    output.attrs[
        "collection_errors"
    ] = collection_errors

    return output


# ============================================================
# VALIDATION
# ============================================================

def validate(
    data: pd.DataFrame,
    output_dir: Path,
    collection_errors: Dict[str, str],
) -> dict:

    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

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

    # ========================================================
    # DATASET
    # ========================================================

    checks[
        "dataset_nonempty"
    ] = len(data) > 0

    checks[
        "required_columns_present"
    ] = (
        len(missing_columns) == 0
    )

    # ========================================================
    # OBSERVATION DATES
    # ========================================================

    if (
        "observation_date"
        in data.columns
    ):

        observation_dates = pd.to_datetime(
            data[
                "observation_date"
            ],
            errors="coerce",
        )

        checks[
            "observation_dates_valid"
        ] = bool(
            observation_dates.notna().all()
        )

        checks[
            "date_sorted"
        ] = bool(
            data[
                "observation_date"
            ].is_monotonic_increasing
        )

        checks[
            "dates_unique"
        ] = bool(
            data[
                "observation_date"
            ].is_unique
        )

    else:

        checks[
            "observation_dates_valid"
        ] = False

        checks[
            "date_sorted"
        ] = False

        checks[
            "dates_unique"
        ] = False

    # ========================================================
    # AVAILABILITY DATES
    # ========================================================

    if (
        "availability_date"
        in data.columns
        and
        "observation_date"
        in data.columns
    ):

        availability_dates = pd.to_datetime(
            data[
                "availability_date"
            ],
            errors="coerce",
        )

        observation_dates = pd.to_datetime(
            data[
                "observation_date"
            ],
            errors="coerce",
        )

        checks[
            "availability_dates_valid"
        ] = bool(
            availability_dates.notna().all()
        )

        checks[
            "availability_after_observation"
        ] = bool(
            (
                availability_dates
                >
                observation_dates
            ).all()
        )

    else:

        checks[
            "availability_dates_valid"
        ] = False

        checks[
            "availability_after_observation"
        ] = False

    # ========================================================
    # PIT
    # ========================================================

    checks[
        "point_in_time_safe_all"
    ] = (

        bool(
            data[
                "point_in_time_safe"
            ].eq(True).all()
        )

        if
        "point_in_time_safe"
        in data.columns

        else False
    )

    # ========================================================
    # RESEARCH-ONLY INVARIANTS
    # ========================================================

    checks[
        "research_only_all"
    ] = (

        bool(
            data[
                "research_only"
            ].eq(True).all()
        )

        if
        "research_only"
        in data.columns

        else False
    )

    checks[
        "decision_engine_disabled"
    ] = (

        bool(
            data[
                "decision_engine_ready"
            ].eq(False).all()
        )

        if
        "decision_engine_ready"
        in data.columns

        else False
    )

    checks[
        "trading_signals_disabled"
    ] = (

        bool(
            data[
                "trading_signal_generated"
            ].eq(False).all()
        )

        if
        "trading_signal_generated"
        in data.columns

        else False
    )

    checks[
        "forecast_disabled"
    ] = (

        bool(
            data[
                "forecast_generated"
            ].eq(False).all()
        )

        if
        "forecast_generated"
        in data.columns

        else False
    )

    checks[
        "unified_decision_disabled"
    ] = (

        bool(
            data[
                "unified_decision_generated"
            ].eq(False).all()
        )

        if
        "unified_decision_generated"
        in data.columns

        else False
    )

    # ========================================================
    # ASSET COVERAGE
    # ========================================================
    #
    # IMPORTANT:
    #
    # Different instruments have different inception dates.
    #
    # We therefore DO NOT measure coverage against the
    # complete 2000 -> present calendar.
    #
    # Instead, each asset is evaluated only between its
    # first and last actual observation.
    #
    # This prevents Bitcoin, for example, from being
    # incorrectly penalized for not existing in 2000.
    # ========================================================

    asset_coverage = {}

    asset_first_dates = {}

    asset_last_dates = {}

    asset_observation_counts = {}

    for asset in ASSETS:

        if asset not in data.columns:

            asset_coverage[
                asset
            ] = 0.0

            asset_first_dates[
                asset
            ] = None

            asset_last_dates[
                asset
            ] = None

            asset_observation_counts[
                asset
            ] = 0

            continue

        asset_series = data[
            asset
        ]

        valid_mask = (
            asset_series.notna()
        )

        if not valid_mask.any():

            asset_coverage[
                asset
            ] = 0.0

            asset_first_dates[
                asset
            ] = None

            asset_last_dates[
                asset
            ] = None

            asset_observation_counts[
                asset
            ] = 0

            continue

        valid_dates = pd.to_datetime(
            data.loc[
                valid_mask,
                "observation_date",
            ],
            errors="coerce",
        )

        first_date = (
            valid_dates.min()
        )

        last_date = (
            valid_dates.max()
        )

        asset_first_dates[
            asset
        ] = (

            first_date.strftime(
                "%Y-%m-%d"
            )

            if pd.notna(first_date)

            else None
        )

        asset_last_dates[
            asset
        ] = (

            last_date.strftime(
                "%Y-%m-%d"
            )

            if pd.notna(last_date)

            else None
        )

        # ----------------------------------------------------
        # Asset-specific historical window
        # ----------------------------------------------------

        all_observation_dates = pd.to_datetime(
            data[
                "observation_date"
            ]
        )

        asset_window = data[
            (
                all_observation_dates
                >= first_date
            )
            &
            (
                all_observation_dates
                <= last_date
            )
        ]

        total_window_rows = len(
            asset_window
        )

        valid_asset_rows = int(
            asset_window[
                asset
            ]
            .notna()
            .sum()
        )

        if total_window_rows > 0:

            coverage = (
                valid_asset_rows
                / total_window_rows
            )

        else:

            coverage = 0.0

        asset_coverage[
            asset
        ] = round(
            float(coverage),
            4,
        )

        asset_observation_counts[
            asset
        ] = valid_asset_rows

    # --------------------------------------------------------
    # Asset availability
    # --------------------------------------------------------

    checks[
        "all_requested_assets_available"
    ] = all(
        asset in data.columns
        for asset in ASSETS
    )

    # --------------------------------------------------------
    # Coverage requirement
    # --------------------------------------------------------

    checks[
        "minimum_asset_coverage"
    ] = all(
        value >= MIN_ASSET_COVERAGE
        for value in asset_coverage.values()
    )

    # ========================================================
    # CORRELATION FEATURES
    # ========================================================

    correlation_columns = [
        column
        for column in data.columns
        if column.startswith(
            "CORR_"
        )
    ]

    checks[
        "correlation_features_present"
    ] = (
        len(
            correlation_columns
        ) >= 5
    )

    # ========================================================
    # WARNINGS
    # ========================================================

    warnings: List[str] = []

    if collection_errors:

        warnings.append(
            "One or more requested Yahoo Finance "
            "symbols were unavailable: "
            +
            "; ".join(
                f"{key}={value}"
                for key, value
                in collection_errors.items()
            )
        )

    # ========================================================
    # OVERALL RESULT
    # ========================================================

    passed = all(
        bool(value)
        for value in checks.values()
    )

    # ========================================================
    # VALIDATION REPORT
    # ========================================================

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

        "asset_first_dates":
            asset_first_dates,

        "asset_last_dates":
            asset_last_dates,

        "asset_observation_counts":
            asset_observation_counts,

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

            "asset_coverage_policy":
                "Coverage is measured within each asset's "
                "own first-to-last available observation window",

            "historical_union_start":
                START_DATE,
        },
    }

    # ========================================================
    # WRITE VALIDATION JSON
    # ========================================================

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

    # ========================================================
    # SUMMARY
    # ========================================================

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
            validation[
                "date_start"
            ],

        "date_end":
            validation[
                "date_end"
            ],

        "available_assets":
            validation[
                "assets_available"
            ],

        "asset_coverage":
            asset_coverage,

        "asset_first_dates":
            asset_first_dates,

        "asset_last_dates":
            asset_last_dates,

        "asset_observation_counts":
            asset_observation_counts,

        "correlation_feature_count":
            len(
                correlation_columns
            ),

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


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description=
        "Cross-Asset Intelligence v1"
    )

    parser.add_argument(
        "--output",
        default=
        "cross_asset_intelligence_v1",
        help=
        "Output directory",
    )

    parser.add_argument(
        "--as-of-date",
        default=
        pd.Timestamp.now(
            "UTC"
        ).strftime(
            "%Y-%m-%d"
        ),
        help=
        "Inclusive research cutoff date YYYY-MM-DD",
    )

    args = parser.parse_args()

    output_dir = Path(
        args.output
    )

    # ========================================================
    # BUILD
    # ========================================================

    try:

        data = build_dataset(
            args.as_of_date
        )

    except Exception as exc:

        print(
            f"ERROR: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )

        return 1

    # ========================================================
    # OUTPUT DIRECTORY
    # ========================================================

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ========================================================
    # RESEARCH DATASET
    # ========================================================

    data.to_csv(
        output_dir
        / "cross_asset_research_v1.csv",
        index=False,
    )

    # ========================================================
    # COLLECTION ERRORS
    # ========================================================

    collection_errors = (
        data.attrs.get(
            "collection_errors",
            {},
        )
    )

    # ========================================================
    # VALIDATION
    # ========================================================

    validation = validate(
        data=data,
        output_dir=output_dir,
        collection_errors=
            collection_errors,
    )

    # ========================================================
    # CONSOLE REPORT
    # ========================================================

    print(
        "=" * 60
    )

    print(
        "CROSS-ASSET INTELLIGENCE v1"
    )

    print(
        "=" * 60
    )

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
        +
        ", ".join(
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

    # ========================================================
    # ASSET COVERAGE REPORT
    # ========================================================

    print(
        "Asset coverage:"
    )

    for asset in ASSETS:

        coverage = validation[
            "asset_coverage"
        ].get(
            asset,
            0.0,
        )

        first_date = validation[
            "asset_first_dates"
        ].get(
            asset
        )

        last_date = validation[
            "asset_last_dates"
        ].get(
            asset
        )

        print(
            f"  {asset}: "
            f"{coverage:.2%} "
            f"({first_date} -> {last_date})"
        )

    # ========================================================
    # WARNINGS
    # ========================================================

    if validation[
        "warnings"
    ]:

        print(
            "WARNINGS:"
        )

        for warning in validation[
            "warnings"
        ]:

            print(
                f"- {warning}"
            )

    # ========================================================
    # FINAL STATUS
    # ========================================================

    if not validation[
        "passed"
    ]:

        print(
            "CROSS-ASSET INTELLIGENCE "
            "VALIDATION FAILED"
        )

        # Print failed checks explicitly
        print(
            "FAILED CHECKS:"
        )

        for name, value in validation[
            "checks"
        ].items():

            if not value:

                print(
                    f"- {name}"
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
