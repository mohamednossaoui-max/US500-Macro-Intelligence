"""
VIX Historical Collector v1

Source:
    Cboe VIX Historical Data

Research-only historical collection layer.

Input:
    Official Cboe VIX historical CSV

Output:
    vix_historical_records_input_v1.csv
    vix_historical_collection_summary_v1.csv

Point-in-time design:
    observation_date = VIX trading/closing date
    availability_date = observation_date + 1 calendar day

IMPORTANT:
    availability_date is a conservative research-safe proxy.
    It is NOT claimed to be the exact historical publication timestamp.

No:
    - sentiment score
    - trading signal
    - forecast
    - Decision Engine integration
"""

from pathlib import Path
from datetime import timedelta
import sys

import numpy as np
import pandas as pd
import requests


# ============================================================
# CONFIGURATION
# ============================================================

SOURCE_URL = (
    "https://cdn.cboe.com/api/global/us_indices/daily_prices/"
    "VIX_History.csv"
)

SOURCE_PAGE_URL = (
    "https://www.cboe.com/tradable_products/vix/"
    "vix_historical_data"
)

OUTPUT_FILE = Path(
    "vix_historical_records_input_v1.csv"
)

SUMMARY_FILE = Path(
    "vix_historical_collection_summary_v1.csv"
)

MIN_EXPECTED_RECORDS = 5000


# ============================================================
# HELPERS
# ============================================================

def fail(message: str):
    print(f"ERROR: {message}")
    sys.exit(1)


def normalize_column_name(column):
    return (
        str(column)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


# ============================================================
# DOWNLOAD
# ============================================================

print("=" * 70)
print("VIX HISTORICAL COLLECTOR v1")
print("=" * 70)

print()
print("Downloading official Cboe VIX historical data...")
print(f"Source: {SOURCE_URL}")

headers = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(compatible; US500-Macro-Intelligence/1.0)"
    )
}

try:

    response = requests.get(
        SOURCE_URL,
        headers=headers,
        timeout=60,
    )

except requests.RequestException as exc:

    fail(
        f"Failed to download Cboe VIX data: {exc}"
    )


print(
    f"HTTP status: {response.status_code}"
)

if response.status_code != 200:

    fail(
        f"Cboe returned HTTP {response.status_code}"
    )


content = response.content

if not content:

    fail("Downloaded Cboe file is empty.")


print(
    f"Downloaded bytes: {len(content):,}"
)


# ============================================================
# READ CSV
# ============================================================

print()
print("Reading Cboe CSV...")

try:

    from io import BytesIO

    raw = pd.read_csv(
        BytesIO(content)
    )

except Exception as exc:

    fail(
        f"Could not parse Cboe CSV: {exc}"
    )


if raw.empty:

    fail(
        "Cboe CSV contains zero rows."
    )


print(
    f"Raw rows: {len(raw):,}"
)

print(
    f"Raw columns: {list(raw.columns)}"
)


# ============================================================
# NORMALIZE COLUMN NAMES
# ============================================================

raw.columns = [
    normalize_column_name(c)
    for c in raw.columns
]

print()
print(
    f"Normalized columns: {list(raw.columns)}"
)


# ============================================================
# IDENTIFY DATE COLUMN
# ============================================================

date_candidates = [
    "date",
    "observation_date",
]

date_column = None

for candidate in date_candidates:

    if candidate in raw.columns:

        date_column = candidate
        break


if date_column is None:

    fail(
        "Could not identify VIX date column."
    )


# ============================================================
# IDENTIFY CLOSE COLUMN
# ============================================================

close_candidates = [
    "close",
    "vix",
    "vix_close",
]

close_column = None

for candidate in close_candidates:

    if candidate in raw.columns:

        close_column = candidate
        break


if close_column is None:

    fail(
        "Could not identify VIX close column."
    )


# ============================================================
# PARSE DATA
# ============================================================

df = raw[
    [
        date_column,
        close_column,
    ]
].copy()

df = df.rename(
    columns={
        date_column: "observation_date",
        close_column: "VIX",
    }
)


df["observation_date"] = pd.to_datetime(
    df["observation_date"],
    errors="coerce",
)


df["VIX"] = pd.to_numeric(
    df["VIX"],
    errors="coerce",
)


# ============================================================
# CLEAN INVALID ROWS
# ============================================================

before_clean = len(df)

df = df.dropna(
    subset=[
        "observation_date",
        "VIX",
    ]
).copy()

removed_rows = (
    before_clean - len(df)
)


# ============================================================
# VALIDATE VIX VALUES
# ============================================================

if (
    df["VIX"] <= 0
).any():

    fail(
        "Invalid VIX values <= 0 detected."
    )


# ============================================================
# SORT
# ============================================================

df = df.sort_values(
    "observation_date"
).reset_index(
    drop=True
)


# ============================================================
# DUPLICATE VALIDATION
# ============================================================

duplicate_count = (
    df["observation_date"]
    .duplicated()
    .sum()
)

if duplicate_count:

    fail(
        "Duplicate observation dates detected: "
        f"{duplicate_count}"
    )


# ============================================================
# AVAILABILITY DATE
# ============================================================

"""
Conservative research-safe availability proxy.

Cboe provides historical daily closing values.
For point-in-time research we avoid assuming that
the observation was available at the exact close.

Therefore:

availability_date =
observation_date + 1 calendar day

This is deliberately conservative and is not
claimed to represent the exact historical publication time.
"""

df["availability_date"] = (
    df["observation_date"]
    + pd.Timedelta(days=1)
)


# ============================================================
# POINT-IN-TIME VALIDATION
# ============================================================

if not (
    df["availability_date"]
    > df["observation_date"]
).all():

    fail(
        "PIT validation failed."
    )


# ============================================================
# BUILD OUTPUT
# ============================================================

result = pd.DataFrame(
    {
        "observation_date":
            df["observation_date"],

        "availability_date":
            df["availability_date"],

        "VIX":
            df["VIX"],

        "source":
            "Cboe Global Markets",

        "source_url":
            SOURCE_URL,

        "source_page_url":
            SOURCE_PAGE_URL,

        "availability_semantics":
            (
                "Conservative +1 calendar-day "
                "availability proxy after VIX "
                "observation date; not exact "
                "historical publication timestamp."
            ),

        "point_in_time_safe":
            True,

        "research_only":
            True,

        "decision_engine_ready":
            False,

        "sentiment_score_generated":
            False,
    }
)


# ============================================================
# EXPECTED RECORD COUNT
# ============================================================

if len(result) < MIN_EXPECTED_RECORDS:

    fail(
        "Unexpectedly low number of VIX observations: "
        f"{len(result):,}. "
        f"Expected at least {MIN_EXPECTED_RECORDS:,}."
    )


# ============================================================
# FINAL VALIDATION
# ============================================================

if result.empty:

    fail(
        "Final VIX output contains zero rows."
    )


if not result[
    "point_in_time_safe"
].all():

    fail(
        "Final output contains non-PIT-safe rows."
    )


if not result[
    "research_only"
].all():

    fail(
        "Final output contains non-research rows."
    )


if result[
    "decision_engine_ready"
].any():

    fail(
        "Decision Engine ready flag detected."
    )


if result[
    "sentiment_score_generated"
].any():

    fail(
        "Sentiment score flag detected."
    )


if result[
    "observation_date"
].duplicated().any():

    fail(
        "Duplicate observation dates detected "
        "in final output."
    )


if not result[
    "observation_date"
].is_monotonic_increasing:

    fail(
        "Observation dates are not sorted."
    )


if not (
    result["availability_date"]
    > result["observation_date"]
).all():

    fail(
        "Final PIT validation failed."
    )


# ============================================================
# SUMMARY
# ============================================================

summary_rows = [

    {
        "metric":
            "total_observations",

        "value":
            len(result),
    },

    {
        "metric":
            "first_observation_date",

        "value":
            result[
                "observation_date"
            ].min().strftime("%Y-%m-%d"),
    },

    {
        "metric":
            "last_observation_date",

        "value":
            result[
                "observation_date"
            ].max().strftime("%Y-%m-%d"),
    },

    {
        "metric":
            "minimum_expected_records",

        "value":
            MIN_EXPECTED_RECORDS,
    },

    {
        "metric":
            "minimum_vix",

        "value":
            result["VIX"].min(),
    },

    {
        "metric":
            "maximum_vix",

        "value":
            result["VIX"].max(),
    },

    {
        "metric":
            "mean_vix",

        "value":
            result["VIX"].mean(),
    },

    {
        "metric":
            "point_in_time_safe",

        "value":
            True,
    },

    {
        "metric":
            "research_only",

        "value":
            True,
    },

    {
        "metric":
            "decision_engine_ready",

        "value":
            False,
    },

    {
        "metric":
            "sentiment_score_generated",

        "value":
            False,
    },

    {
        "metric":
            "sentiment_signal_generated",

        "value":
            False,
    },

    {
        "metric":
            "forecast_generated",

        "value":
            False,
    },

    {
        "metric":
            "rows_removed_during_cleaning",

        "value":
            removed_rows,
    },
]


summary = pd.DataFrame(
    summary_rows
)


# ============================================================
# SAVE
# ============================================================

result.to_csv(
    OUTPUT_FILE,
    index=False,
)


summary.to_csv(
    SUMMARY_FILE,
    index=False,
)


# ============================================================
# REPORT
# ============================================================

latest = result.iloc[-1]

print()
print("=" * 70)
print("VIX HISTORICAL COLLECTOR v1 — RESULT")
print("=" * 70)

print()
print(
    f"Records: {len(result):,}"
)

print(
    "First observation: "
    f"{result['observation_date'].min().date()}"
)

print(
    "Last observation: "
    f"{result['observation_date'].max().date()}"
)

print(
    f"Minimum VIX: "
    f"{result['VIX'].min():.4f}"
)

print(
    f"Maximum VIX: "
    f"{result['VIX'].max():.4f}"
)

print(
    f"Mean VIX: "
    f"{result['VIX'].mean():.4f}"
)

print()
print("Latest observation:")

print(
    f"  Date: "
    f"{latest['observation_date'].date()}"
)

print(
    f"  Availability: "
    f"{latest['availability_date'].date()}"
)

print(
    f"  VIX: "
    f"{latest['VIX']:.4f}"
)

print()
print("Point-in-time safe: TRUE")
print("Research-only: TRUE")
print("Decision Engine ready: FALSE")
print("Sentiment score generated: FALSE")
print("Trading signal: NONE")
print("Forecast: NONE")

print()
print("Output files:")

print(
    f"  {OUTPUT_FILE}"
)

print(
    f"  {SUMMARY_FILE}"
)

print()
print("=" * 70)
print("PASS: VIX Historical Collector v1 completed successfully.")
print("=" * 70)
