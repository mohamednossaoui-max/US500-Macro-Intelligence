"""
Liquidity Historical Collector v1

FIXED — Official FRED Series / Initial Release
Research-only — No Decision Engine

Purpose:
    Collect historical liquidity-related observations from official
    FRED series using output_type=4 (Initial Release Only).

Indicators:
    WALCL      - Federal Reserve Total Assets
    WRESBAL    - Reserve Balances
    WTREGEN    - Treasury General Account
    WSHOTSL    - Treasury Securities
    WSHOMCB    - Mortgage-Backed Securities
    RRPONTSYD  - Overnight Reverse Repurchase Agreements
    SOFR       - Secured Overnight Financing Rate
    EFFR       - Effective Federal Funds Rate

Important:
    - No liquidity score
    - No trading signal
    - No forecast
    - No Decision Engine integration
    - Research-only
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests


# ================================================================
# Configuration
# ================================================================

START_DATE = os.getenv(
    "LIQUIDITY_START_DATE",
    "2019-01-01"
)

END_DATE = os.getenv(
    "LIQUIDITY_END_DATE",
    "2026-09-21"
)

FRED_API_KEY = os.getenv("FRED_API_KEY")

FRED_ENDPOINT = (
    "https://api.stlouisfed.org/fred/series/observations"
)

OUTPUT_FILE = Path(
    "liquidity_historical_records_input_v1.csv"
)

SUMMARY_FILE = Path(
    "liquidity_historical_collection_summary_v1.csv"
)


# ================================================================
# Official FRED series
# ================================================================

SERIES = {
    "WALCL": {
        "indicator": "FED_TOTAL_ASSETS",
        "unit": "Millions of U.S. Dollars",
        "frequency": "Weekly",
        "source": "Federal Reserve H.4.1 via FRED",
        "source_url": (
            "https://fred.stlouisfed.org/series/WALCL"
        ),
    },

    "WRESBAL": {
        "indicator": "RESERVE_BALANCES",
        "unit": "Millions of U.S. Dollars",
        "frequency": "Weekly",
        "source": "Federal Reserve H.4.1 via FRED",
        "source_url": (
            "https://fred.stlouisfed.org/series/WRESBAL"
        ),
    },

    "WTREGEN": {
        "indicator": "TREASURY_GENERAL_ACCOUNT",
        "unit": "Millions of U.S. Dollars",
        "frequency": "Weekly",
        "source": "Federal Reserve H.4.1 via FRED",
        "source_url": (
            "https://fred.stlouisfed.org/series/WTREGEN"
        ),
    },

    "WSHOTSL": {
        "indicator": "TREASURY_SECURITIES",
        "unit": "Millions of U.S. Dollars",
        "frequency": "Weekly",
        "source": "Federal Reserve H.4.1 via FRED",
        "source_url": (
            "https://fred.stlouisfed.org/series/WSHOTSL"
        ),
    },

    "WSHOMCB": {
        "indicator": "MBS",
        "unit": "Millions of U.S. Dollars",
        "frequency": "Weekly",
        "source": "Federal Reserve H.4.1 via FRED",
        "source_url": (
            "https://fred.stlouisfed.org/series/WSHOMCB"
        ),
    },

    "RRPONTSYD": {
        "indicator": "ON_RRP",
        "unit": "Billions of U.S. Dollars",
        "frequency": "Daily",
        "source": "Federal Reserve Bank of New York via FRED",
        "source_url": (
            "https://fred.stlouisfed.org/series/RRPONTSYD"
        ),
    },

    "SOFR": {
        "indicator": "SOFR",
        "unit": "Percent",
        "frequency": "Daily",
        "source": "Federal Reserve Bank of New York via FRED",
        "source_url": (
            "https://fred.stlouisfed.org/series/SOFR"
        ),
    },

    "EFFR": {
        "indicator": "EFFR",
        "unit": "Percent",
        "frequency": "Daily",
        "source": "Federal Reserve Bank of New York via FRED",
        "source_url": (
            "https://fred.stlouisfed.org/series/EFFR"
        ),
    },
}


# ================================================================
# Required output schema
# ================================================================

OUTPUT_COLUMNS = [
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


# ================================================================
# Utility
# ================================================================

def validate_date(value: str, name: str) -> datetime:
    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d"
        )
    except ValueError as exc:
        raise RuntimeError(
            f"{name} must use YYYY-MM-DD format. "
            f"Received: {value}"
        ) from exc


def validate_configuration():
    """
    Validate API key and date configuration.
    """

    if not FRED_API_KEY:
        raise RuntimeError(
            "FRED_API_KEY is missing. "
            "Configure it as a GitHub Actions secret."
        )

    if len(FRED_API_KEY) != 32:
        raise RuntimeError(
            "FRED_API_KEY must be exactly 32 characters."
        )

    if FRED_API_KEY != FRED_API_KEY.lower():
        raise RuntimeError(
            "FRED_API_KEY must use lowercase characters."
        )

    if not FRED_API_KEY.isalnum():
        raise RuntimeError(
            "FRED_API_KEY must contain only "
            "letters and numbers."
        )

    start_dt = validate_date(
        START_DATE,
        "LIQUIDITY_START_DATE"
    )

    end_dt = validate_date(
        END_DATE,
        "LIQUIDITY_END_DATE"
    )

    if start_dt > end_dt:
        raise RuntimeError(
            f"Start date {START_DATE} is after "
            f"end date {END_DATE}."
        )

    print("Configuration validation: PASS")


# ================================================================
# FRED API
# ================================================================

def fetch_fred_series(
    series_id: str,
    start_date: str,
    end_date: str,
):
    """
    Fetch FRED observations using output_type=4.

    output_type=4:
        Observations, Initial Release Only
    """

    params = {
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "series_id": series_id,
        "observation_start": start_date,
        "observation_end": end_date,
        "output_type": 4,
        "sort_order": "asc",
    }

    try:
        response = requests.get(
            FRED_ENDPOINT,
            params=params,
            timeout=60,
        )

    except requests.RequestException as exc:
        print("")
        print("=" * 70)
        print("FRED NETWORK ERROR")
        print("=" * 70)
        print(f"Series: {series_id}")
        print(f"Error: {exc}")
        print("=" * 70)
        print("")

        raise RuntimeError(
            f"FRED request failed for {series_id}"
        ) from exc

    # ------------------------------------------------------------
    # Explicit HTTP validation
    # ------------------------------------------------------------

    if response.status_code != 200:

        print("")
        print("=" * 70)
        print("FRED API ERROR")
        print("=" * 70)
        print(f"Series:       {series_id}")
        print(f"HTTP status:  {response.status_code}")
        print("")
        print("Request URL:")
        print(response.url)
        print("")
        print("FRED response:")
        print(response.text)
        print("=" * 70)
        print("")

        raise RuntimeError(
            f"FRED API request failed for {series_id}: "
            f"HTTP {response.status_code}"
        )

    # ------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------

    try:
        data = response.json()

    except ValueError as exc:
        print("")
        print("=" * 70)
        print("FRED RESPONSE ERROR")
        print("=" * 70)
        print(f"Series: {series_id}")
        print("Response was not valid JSON.")
        print(response.text[:2000])
        print("=" * 70)
        print("")

        raise RuntimeError(
            f"Invalid JSON response for {series_id}"
        ) from exc

    # ------------------------------------------------------------
    # FRED API error payload
    # ------------------------------------------------------------

    if "error_code" in data:

        print("")
        print("=" * 70)
        print("FRED API ERROR PAYLOAD")
        print("=" * 70)
        print(f"Series:       {series_id}")
        print(
            f"Error code:   {data.get('error_code')}"
        )
        print(
            f"Error message:{data.get('error_message')}"
        )
        print("=" * 70)
        print("")

        raise RuntimeError(
            f"FRED API error {data.get('error_code')}: "
            f"{data.get('error_message')}"
        )

    # ------------------------------------------------------------
    # Observation validation
    # ------------------------------------------------------------

    if "observations" not in data:
        raise RuntimeError(
            f"FRED response for {series_id} "
            "does not contain 'observations'."
        )

    observations = data["observations"]

    if not isinstance(observations, list):
        raise RuntimeError(
            f"Invalid observations payload for {series_id}."
        )

    print(
        f"Received {len(observations):,} "
        f"observations for {series_id}"
    )

    return observations


# ================================================================
# Convert FRED observations
# ================================================================

def convert_series(
    series_id: str,
    observations: list,
):
    """
    Convert raw FRED observations into the project schema.
    """

    meta = SERIES[series_id]

    rows = []

    for obs in observations:

        observation_date = obs.get("date")
        raw_value = obs.get("value")

        if not observation_date:
            continue

        # FRED can use "." for missing observations.
        if raw_value in (
            None,
            "",
            ".",
        ):
            continue

        try:
            actual = float(raw_value)
        except (TypeError, ValueError):
            continue

        obs_dt = datetime.strptime(
            observation_date,
            "%Y-%m-%d"
        )

        # --------------------------------------------------------
        # Conservative availability proxy
        # --------------------------------------------------------
        #
        # This is intentionally labeled as a proxy.
        # It is NOT claimed to be the exact historical
        # publication timestamp.
        #
        availability_date = (
            obs_dt + timedelta(days=1)
        ).strftime("%Y-%m-%d")

        rows.append(
            {
                "indicator": meta["indicator"],
                "observation_date": (
                    obs_dt.strftime("%Y-%m-%d")
                ),
                "availability_date": availability_date,
                "actual": actual,
                "unit": meta["unit"],
                "frequency": meta["frequency"],
                "source": meta["source"],
                "source_url": meta["source_url"],
                "vintage": "initial_release",
                "revision_flag": False,
                "point_in_time_safe": True,
                "availability_semantics": (
                    "Conservative +1 calendar day "
                    "availability proxy; "
                    "FRED output_type=4 initial release"
                ),
                "research_only": True,
                "decision_engine_ready": False,
                "trading_signal_generated": False,
                "forecast_generated": False,
                "liquidity_score_generated": False,
            }
        )

    return rows


# ================================================================
# Main collection
# ================================================================

def collect_all_series():

    all_rows = []

    print("")
    print("=" * 70)
    print("Liquidity Historical Collector v1")
    print("FIXED — Official FRED Series / Initial Release")
    print("Research-only — No Decision Engine")
    print("=" * 70)
    print(f"Start: {START_DATE}")
    print(f"End:   {END_DATE}")
    print(f"Required indicators: {len(SERIES)}")
    print("")

    for series_id, meta in SERIES.items():

        print("-" * 70)
        print(
            f"Collecting "
            f"{meta['indicator']} [{series_id}]"
        )
        print("-" * 70)

        observations = fetch_fred_series(
            series_id=series_id,
            start_date=START_DATE,
            end_date=END_DATE,
        )

        rows = convert_series(
            series_id,
            observations,
        )

        if not rows:
            raise RuntimeError(
                f"No usable observations returned "
                f"for {series_id}."
            )

        print(
            f"Usable observations: {len(rows):,}"
        )

        all_rows.extend(rows)

    return all_rows


# ================================================================
# Validation
# ================================================================

def validate_output(df: pd.DataFrame):

    print("")
    print("=" * 70)
    print("Collector Output Validation")
    print("=" * 70)

    # ------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------

    missing_columns = [
        col
        for col in OUTPUT_COLUMNS
        if col not in df.columns
    ]

    if missing_columns:
        raise RuntimeError(
            f"Missing required columns: "
            f"{missing_columns}"
        )

    # ------------------------------------------------------------
    # Indicators
    # ------------------------------------------------------------

    expected_series = set(SERIES.keys())

    indicator_to_series = {
        meta["indicator"]: series_id
        for series_id, meta in SERIES.items()
    }

    expected_indicators = set(
        indicator_to_series.keys()
    )

    actual_indicators = set(
        df["indicator"].dropna().unique()
    )

    missing_indicators = (
        expected_indicators - actual_indicators
    )

    if missing_indicators:
        raise RuntimeError(
            f"Missing indicators: "
            f"{sorted(missing_indicators)}"
        )

    unexpected_indicators = (
        actual_indicators - expected_indicators
    )

    if unexpected_indicators:
        raise RuntimeError(
            f"Unexpected indicators: "
            f"{sorted(unexpected_indicators)}"
        )

    # ------------------------------------------------------------
    # Dates
    # ------------------------------------------------------------

    df["observation_date"] = pd.to_datetime(
        df["observation_date"],
        errors="coerce",
    )

    df["availability_date"] = pd.to_datetime(
        df["availability_date"],
        errors="coerce",
    )

    if df["observation_date"].isna().any():
        raise RuntimeError(
            "Invalid observation_date values detected."
        )

    if df["availability_date"].isna().any():
        raise RuntimeError(
            "Invalid availability_date values detected."
        )

    start_dt = pd.Timestamp(START_DATE)
    end_dt = pd.Timestamp(END_DATE)

    if (
        df["observation_date"] < start_dt
    ).any():
        raise RuntimeError(
            "Observation dates earlier than "
            "requested start date detected."
        )

    if (
        df["observation_date"] > end_dt
    ).any():
        raise RuntimeError(
            "Observation dates later than "
            "requested end date detected."
        )

    # ------------------------------------------------------------
    # Availability date
    # ------------------------------------------------------------

    invalid_availability = (
        df["availability_date"]
        < df["observation_date"]
    )

    if invalid_availability.any():
        raise RuntimeError(
            "Availability date earlier than "
            "observation date detected."
        )

    # ------------------------------------------------------------
    # Actual values
    # ------------------------------------------------------------

    df["actual"] = pd.to_numeric(
        df["actual"],
        errors="coerce",
    )

    if df["actual"].isna().any():
        raise RuntimeError(
            "Missing or non-numeric actual values detected."
        )

    if np.isinf(df["actual"]).any():
        raise RuntimeError(
            "Infinite actual values detected."
        )

    # ------------------------------------------------------------
    # Duplicates
    # ------------------------------------------------------------

    duplicate_keys = [
        "indicator",
        "observation_date",
        "availability_date",
        "vintage",
    ]

    duplicate_count = df.duplicated(
        subset=duplicate_keys
    ).sum()

    if duplicate_count > 0:
        raise RuntimeError(
            f"Duplicate records detected: "
            f"{duplicate_count}"
        )

    # ------------------------------------------------------------
    # PIT
    # ------------------------------------------------------------

    pit_values = (
        df["point_in_time_safe"]
        .astype(str)
        .str.lower()
    )

    if not (pit_values == "true").all():
        raise RuntimeError(
            "point_in_time_safe is not True "
            "for all records."
        )

    # ------------------------------------------------------------
    # Revision
    # ------------------------------------------------------------

    revision_values = (
        df["revision_flag"]
        .astype(str)
        .str.lower()
    )

    if not (revision_values == "false").all():
        raise RuntimeError(
            "revision_flag is not False "
            "for all records."
        )

    # ------------------------------------------------------------
    # Research-only
    # ------------------------------------------------------------

    research_values = (
        df["research_only"]
        .astype(str)
        .str.lower()
    )

    if not (research_values == "true").all():
        raise RuntimeError(
            "research_only is not True "
            "for all records."
        )

    # ------------------------------------------------------------
    # Decision Engine
    # ------------------------------------------------------------

    decision_values = (
        df["decision_engine_ready"]
        .astype(str)
        .str.lower()
    )

    if not (decision_values == "false").all():
        raise RuntimeError(
            "decision_engine_ready is not False "
            "for all records."
        )

    # ------------------------------------------------------------
    # Trading signals
    # ------------------------------------------------------------

    signal_values = (
        df["trading_signal_generated"]
        .astype(str)
        .str.lower()
    )

    if not (signal_values == "false").all():
        raise RuntimeError(
            "Trading signals detected."
        )

    # ------------------------------------------------------------
    # Forecast
    # ------------------------------------------------------------

    forecast_values = (
        df["forecast_generated"]
        .astype(str)
        .str.lower()
    )

    if not (forecast_values == "false").all():
        raise RuntimeError(
            "Forecast generation detected."
        )

    # ------------------------------------------------------------
    # Liquidity score
    # ------------------------------------------------------------

    score_values = (
        df["liquidity_score_generated"]
        .astype(str)
        .str.lower()
    )

    if not (score_values == "false").all():
        raise RuntimeError(
            "Liquidity score generation detected."
        )

    # ------------------------------------------------------------
    # Required vintage
    # ------------------------------------------------------------

    if not (
        df["vintage"]
        .astype(str)
        .eq("initial_release")
    ).all():
        raise RuntimeError(
            "Unexpected vintage metadata detected."
        )

    print("Schema: PASS")
    print("Indicators: PASS")
    print("Dates: PASS")
    print("Availability dates: PASS")
    print("Actual values: PASS")
    print("Duplicates: PASS")
    print("Point-in-time safety: PASS")
    print("Revision flags: PASS")
    print("Research-only: PASS")
    print("Decision Engine: FALSE")
    print("Trading signals: FALSE")
    print("Forecast: FALSE")
    print("Liquidity score: FALSE")
    print("Vintage: initial_release")
    print("")
    print("Validation: PASS")


# ================================================================
# Summary
# ================================================================

def build_summary(df: pd.DataFrame):

    summary_rows = []

    for indicator, group in (
        df.groupby("indicator", sort=True)
    ):

        summary_rows.append(
            {
                "indicator": indicator,
                "rows": len(group),
                "first_observation": (
                    group["observation_date"]
                    .min()
                    .strftime("%Y-%m-%d")
                ),
                "last_observation": (
                    group["observation_date"]
                    .max()
                    .strftime("%Y-%m-%d")
                ),
                "latest_actual": (
                    group.sort_values(
                        "observation_date"
                    )
                    .iloc[-1]["actual"]
                ),
                "unit": group["unit"].iloc[0],
                "frequency": group["frequency"].iloc[0],
                "source": group["source"].iloc[0],
                "vintage": group["vintage"].iloc[0],
                "point_in_time_safe": True,
                "research_only": True,
                "decision_engine_ready": False,
                "trading_signal_generated": False,
                "forecast_generated": False,
                "liquidity_score_generated": False,
            }
        )

    return pd.DataFrame(summary_rows)


# ================================================================
# Main
# ================================================================

def main():

    try:

        validate_configuration()

        rows = collect_all_series()

        if not rows:
            raise RuntimeError(
                "Collector returned zero records."
            )

        df = pd.DataFrame(rows)

        # Ensure exact column order
        df = df[OUTPUT_COLUMNS]

        # Sort deterministically
        df = df.sort_values(
            [
                "observation_date",
                "indicator",
            ]
        ).reset_index(drop=True)

        validate_output(df)

        summary = build_summary(df)

        # --------------------------------------------------------
        # Save records
        # --------------------------------------------------------

        df.to_csv(
            OUTPUT_FILE,
            index=False,
        )

        # --------------------------------------------------------
        # Save summary
        # --------------------------------------------------------

        summary.to_csv(
            SUMMARY_FILE,
            index=False,
        )

        # --------------------------------------------------------
        # Final console report
        # --------------------------------------------------------

        print("")
        print("=" * 70)
        print("LIQUIDITY HISTORICAL COLLECTION COMPLETE")
        print("=" * 70)
        print(
            f"Total rows: {len(df):,}"
        )
        print(
            f"Indicators: "
            f"{df['indicator'].nunique()}"
        )
        print(
            f"Observation range: "
            f"{df['observation_date'].min().date()} "
            f"→ "
            f"{df['observation_date'].max().date()}"
        )

        print("")
        print("Rows by indicator:")

        counts = (
            df.groupby("indicator")
            .size()
            .sort_index()
        )

        for indicator, count in counts.items():
            print(
                f"  {indicator:30s} "
                f"{count:>8,}"
            )

        print("")
        print("Output files:")
        print(f"  {OUTPUT_FILE}")
        print(f"  {SUMMARY_FILE}")

        print("")
        print("Research-only: TRUE")
        print("Decision Engine: FALSE")
        print("Trading signal: FALSE")
        print("Forecast: FALSE")
        print("Liquidity score: FALSE")

        print("")
        print("=" * 70)
        print("STATUS: PASS")
        print("=" * 70)

    except Exception as exc:

        print("")
        print("=" * 70)
        print("LIQUIDITY HISTORICAL COLLECTOR FAILED")
        print("=" * 70)
        print(f"Error: {exc}")
        print("=" * 70)
        print("")

        sys.exit(1)


if __name__ == "__main__":
    main()
