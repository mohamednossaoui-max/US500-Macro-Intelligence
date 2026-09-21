"""
Liquidity Historical Collector v1
=================================

Research-only historical liquidity collector.

Official data sources:
- Federal Reserve H.4.1 via FRED
- Federal Reserve Bank of New York via FRED

Indicators:
    FED_TOTAL_ASSETS
    RESERVE_BALANCES
    TREASURY_GENERAL_ACCOUNT
    TREASURY_SECURITIES
    MORTGAGE_BACKED_SECURITIES
    ON_RRP
    SOFR
    EFFR

Research principles:
    - Point-in-time safe
    - Conservative availability-date proxy
    - Initial-release vintage requested where supported
    - No trading signals
    - No forecasts
    - No liquidity score
    - No Decision Engine integration
"""

from __future__ import annotations

import os
import sys
from typing import Dict

import numpy as np
import pandas as pd
import requests


# ============================================================
# Configuration
# ============================================================

START_DATE = pd.Timestamp(
    os.getenv(
        "LIQUIDITY_START_DATE",
        "2019-01-01",
    )
)

END_DATE = pd.Timestamp(
    os.getenv(
        "LIQUIDITY_END_DATE",
        "2026-09-21",
    )
)

FRED_API_KEY = os.getenv(
    "FRED_API_KEY"
)

OUTPUT_FILE = (
    "liquidity_historical_records_input_v1.csv"
)

SUMMARY_FILE = (
    "liquidity_historical_collection_summary_v1.csv"
)


# ============================================================
# Constants
# ============================================================

FRED_API_URL = (
    "https://api.stlouisfed.org/"
    "fred/series/observations"
)


SOURCE_H41 = (
    "Federal Reserve H.4.1 via FRED"
)

SOURCE_NYFED = (
    "Federal Reserve Bank of New York via FRED"
)


# ============================================================
# Official FRED series
# ============================================================

SERIES: Dict[str, Dict[str, str]] = {

    "FED_TOTAL_ASSETS": {
        "series_id": "WALCL",
        "source": SOURCE_H41,
        "frequency": "weekly",
        "unit": "millions_usd",
        "availability_semantics": (
            "H.4.1 Wednesday observation; "
            "conservative Thursday release-date proxy."
        ),
    },

    "RESERVE_BALANCES": {
        "series_id": "WRESBAL",
        "source": SOURCE_H41,
        "frequency": "weekly",
        "unit": "millions_usd",
        "availability_semantics": (
            "H.4.1 Wednesday observation; "
            "conservative Thursday release-date proxy."
        ),
    },

    "TREASURY_GENERAL_ACCOUNT": {
        "series_id": "WTREGEN",
        "source": SOURCE_H41,
        "frequency": "weekly",
        "unit": "millions_usd",
        "availability_semantics": (
            "H.4.1 weekly average ending Wednesday; "
            "conservative Thursday release-date proxy."
        ),
    },

    "TREASURY_SECURITIES": {
        "series_id": "WSHOTSL",
        "source": SOURCE_H41,
        "frequency": "weekly",
        "unit": "millions_usd",
        "availability_semantics": (
            "H.4.1 Wednesday observation; "
            "conservative Thursday release-date proxy."
        ),
    },

    "MORTGAGE_BACKED_SECURITIES": {
        "series_id": "WSHOMCB",
        "source": SOURCE_H41,
        "frequency": "weekly",
        "unit": "millions_usd",
        "availability_semantics": (
            "H.4.1 Wednesday observation; "
            "conservative Thursday release-date proxy."
        ),
    },

    "ON_RRP": {
        "series_id": "RRPONTSYD",
        "source": SOURCE_NYFED,
        "frequency": "daily",
        "unit": "billions_usd",
        "availability_semantics": (
            "New York Fed daily observation; "
            "next-calendar-day conservative availability proxy."
        ),
    },

    "SOFR": {
        "series_id": "SOFR",
        "source": SOURCE_NYFED,
        "frequency": "daily",
        "unit": "percent",
        "availability_semantics": (
            "New York Fed daily rate; "
            "next-calendar-day conservative availability proxy."
        ),
    },

    "EFFR": {
        "series_id": "EFFR",
        "source": SOURCE_NYFED,
        "frequency": "daily",
        "unit": "percent",
        "availability_semantics": (
            "New York Fed daily rate; "
            "next-calendar-day conservative availability proxy."
        ),
    },
}


# ============================================================
# Validation
# ============================================================

REQUIRED_INDICATORS = set(
    SERIES.keys()
)


# ============================================================
# Helpers
# ============================================================

def require_api_key() -> None:

    if not FRED_API_KEY:

        raise RuntimeError(
            "FRED_API_KEY environment variable "
            "is not configured."
        )


def clean_numeric(value):

    if value is None:
        return np.nan

    text = str(value).strip()

    if text in {
        "",
        ".",
        "NA",
        "N/A",
        "nan",
        "None",
    }:
        return np.nan

    try:
        return float(text)
    except ValueError:
        return np.nan


def fred_source_url(series_id: str) -> str:

    return (
        "https://fred.stlouisfed.org/series/"
        + series_id
    )


# ============================================================
# FRED collector
# ============================================================

def collect_series(
    indicator: str,
    metadata: Dict[str, str],
) -> pd.DataFrame:

    series_id = metadata["series_id"]

    print()
    print("-" * 70)
    print(
        f"Collecting {indicator} [{series_id}]"
    )
    print("-" * 70)

    params = {
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "series_id": series_id,

        "observation_start": (
            START_DATE.strftime("%Y-%m-%d")
        ),

        "observation_end": (
            END_DATE.strftime("%Y-%m-%d")
        ),

        # FRED output_type=4 requests
        # initial-release observations.
        "output_type": "4",

        "sort_order": "asc",
    }

    response = requests.get(
        FRED_API_URL,
        params=params,
        timeout=120,
        headers={
            "User-Agent": (
                "US500-Macro-Intelligence/"
                "Liquidity-Historical-Collector-v1"
            )
        },
    )

    response.raise_for_status()

    payload = response.json()

    observations = payload.get(
        "observations",
        [],
    )

    if not observations:

        raise RuntimeError(
            f"{indicator} [{series_id}] "
            "returned zero observations."
        )

    rows = []

    for observation in observations:

        observation_date = pd.to_datetime(
            observation.get("date"),
            errors="coerce",
        )

        actual = clean_numeric(
            observation.get("value")
        )

        if pd.isna(observation_date):
            continue

        if pd.isna(actual):
            continue

        # ----------------------------------------------------
        # Conservative PIT availability
        # ----------------------------------------------------

        availability_date = (
            observation_date
            + pd.Timedelta(days=1)
        )

        rows.append(
            {
                "indicator": indicator,

                "observation_date": (
                    observation_date
                ),

                "availability_date": (
                    availability_date
                ),

                "actual": actual,

                "unit": metadata["unit"],

                "frequency": metadata["frequency"],

                "source": metadata["source"],

                "source_url": fred_source_url(
                    series_id
                ),

                "vintage": (
                    "initial_release"
                ),

                "revision_flag": False,

                "point_in_time_safe": True,

                "availability_semantics": (
                    metadata[
                        "availability_semantics"
                    ]
                ),
            }
        )

    df = pd.DataFrame(rows)

    if df.empty:

        raise RuntimeError(
            f"{indicator} produced no valid rows."
        )

    # --------------------------------------------------------
    # Date boundaries
    # --------------------------------------------------------

    df = df[
        (df["observation_date"] >= START_DATE)
        &
        (df["observation_date"] <= END_DATE)
    ].copy()

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    df = df.sort_values(
        [
            "observation_date",
            "availability_date",
        ]
    ).reset_index(
        drop=True
    )

    print(
        "Rows:",
        len(df),
    )

    print(
        "Date range:",
        df["observation_date"].min().date(),
        "->",
        df["observation_date"].max().date(),
    )

    print(
        "Latest value:",
        df.iloc[-1]["actual"],
    )

    return df


# ============================================================
# Main
# ============================================================

def main():

    print()
    print("=" * 70)
    print(
        "Liquidity Historical Collector v1"
    )
    print(
        "FIXED — Official FRED Series / Initial Release"
    )
    print(
        "Research-only — No Decision Engine"
    )
    print("=" * 70)

    print(
        "Start:",
        START_DATE.date(),
    )

    print(
        "End:",
        END_DATE.date(),
    )

    print(
        "Required indicators:",
        len(REQUIRED_INDICATORS),
    )

    require_api_key()

    collected = []

    # --------------------------------------------------------
    # Collect all official series
    # --------------------------------------------------------

    for indicator, metadata in SERIES.items():

        df = collect_series(
            indicator,
            metadata,
        )

        collected.append(df)

    # --------------------------------------------------------
    # Combine
    # --------------------------------------------------------

    df = pd.concat(
        collected,
        ignore_index=True,
    )

    # --------------------------------------------------------
    # Normalize types
    # --------------------------------------------------------

    df["observation_date"] = pd.to_datetime(
        df["observation_date"],
        errors="coerce",
    )

    df["availability_date"] = pd.to_datetime(
        df["availability_date"],
        errors="coerce",
    )

    df["actual"] = pd.to_numeric(
        df["actual"],
        errors="coerce",
    )

    # --------------------------------------------------------
    # Remove invalid rows
    # --------------------------------------------------------

    df = df.dropna(
        subset=[
            "indicator",
            "observation_date",
            "availability_date",
            "actual",
        ]
    )

    # --------------------------------------------------------
    # Required indicator check
    # --------------------------------------------------------

    available = set(
        df["indicator"]
        .unique()
        .tolist()
    )

    missing = (
        REQUIRED_INDICATORS
        - available
    )

    if missing:

        raise RuntimeError(
            "Missing required indicators: "
            + str(sorted(missing))
        )

    # --------------------------------------------------------
    # Duplicate check
    # --------------------------------------------------------

    duplicate_mask = df.duplicated(
        subset=[
            "indicator",
            "observation_date",
            "availability_date",
            "vintage",
        ],
        keep=False,
    )

    duplicate_count = int(
        duplicate_mask.sum()
    )

    if duplicate_count > 0:

        raise RuntimeError(
            "Duplicate records detected: "
            f"{duplicate_count}"
        )

    # --------------------------------------------------------
    # PIT validation
    # --------------------------------------------------------

    pit_failures = df[
        df["availability_date"]
        < df["observation_date"]
    ]

    if not pit_failures.empty:

        raise RuntimeError(
            "PIT validation failed: "
            "availability_date < "
            "observation_date."
        )

    if not df[
        "point_in_time_safe"
    ].eq(True).all():

        raise RuntimeError(
            "PIT flag validation failed."
        )

    # --------------------------------------------------------
    # Research metadata
    # --------------------------------------------------------

    df["research_only"] = True

    df["decision_engine_ready"] = False

    df["trading_signal_generated"] = False

    df["forecast_generated"] = False

    df["liquidity_score_generated"] = False

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    df = df.sort_values(
        [
            "indicator",
            "observation_date",
            "availability_date",
        ]
    ).reset_index(
        drop=True
    )

    # --------------------------------------------------------
    # Column order
    # --------------------------------------------------------

    columns = [
        "indicator",
        "observation_date",
        "availability_date",
        "actual",
        "unit",
        "frequency",
        "source",
        "source_url",
        "vintage",
        "revision_flag",
        "point_in_time_safe",
        "availability_semantics",
        "research_only",
        "decision_engine_ready",
        "trading_signal_generated",
        "forecast_generated",
        "liquidity_score_generated",
    ]

    df = df[columns]

    # --------------------------------------------------------
    # Save main output
    # --------------------------------------------------------

    df.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary_rows = []

    for indicator, group in df.groupby(
        "indicator",
        sort=True,
    ):

        group = group.sort_values(
            "observation_date"
        )

        latest = group.iloc[-1]

        summary_rows.append(
            {
                "indicator": indicator,

                "series_id": (
                    SERIES[indicator][
                        "series_id"
                    ]
                ),

                "rows": len(group),

                "first_observation": (
                    group[
                        "observation_date"
                    ].min()
                ),

                "last_observation": (
                    group[
                        "observation_date"
                    ].max()
                ),

                "latest_availability": (
                    latest[
                        "availability_date"
                    ]
                ),

                "latest_actual": (
                    latest["actual"]
                ),

                "point_in_time_safe": True,

                "research_only": True,

                "decision_engine_ready": False,

                "trading_signal_generated": False,

                "forecast_generated": False,

                "liquidity_score_generated": False,
            }
        )

    summary = pd.DataFrame(
        summary_rows
    )

    summary.to_csv(
        SUMMARY_FILE,
        index=False,
    )

    # --------------------------------------------------------
    # Final validation
    # --------------------------------------------------------

    if not df["research_only"].eq(
        True
    ).all():

        raise RuntimeError(
            "research_only validation failed."
        )

    if not df[
        "decision_engine_ready"
    ].eq(False).all():

        raise RuntimeError(
            "Decision Engine validation failed."
        )

    if not df[
        "trading_signal_generated"
    ].eq(False).all():

        raise RuntimeError(
            "Trading signal validation failed."
        )

    if not df[
        "forecast_generated"
    ].eq(False).all():

        raise RuntimeError(
            "Forecast validation failed."
        )

    if not df[
        "liquidity_score_generated"
    ].eq(False).all():

        raise RuntimeError(
            "Liquidity score validation failed."
        )

    # --------------------------------------------------------
    # Final report
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "LIQUIDITY HISTORICAL COLLECTION PASSED"
    )
    print("=" * 70)

    print(
        "Total rows:",
        len(df),
    )

    print(
        "Indicators:",
        df["indicator"].nunique(),
    )

    print(
        "Date range:",
        df["observation_date"].min().date(),
        "->",
        df["observation_date"].max().date(),
    )

    print()
    print(
        "Rows per indicator:"
    )

    print(
        df.groupby("indicator")
        .size()
        .to_string()
    )

    print()
    print(
        "PIT safe: TRUE"
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
        "Liquidity score: FALSE"
    )

    print()
    print(
        "Output:",
        OUTPUT_FILE,
    )

    print(
        "Summary:",
        SUMMARY_FILE,
    )

    print("=" * 70)


if __name__ == "__main__":

    try:

        main()

    except Exception as exc:

        print()
        print(
            "ERROR:",
            str(exc),
        )

        sys.exit(1)
