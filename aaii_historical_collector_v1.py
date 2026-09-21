"""
AAII Historical Sentiment Collector v1

Purpose
-------
Collect the official AAII Investor Sentiment Survey historical dataset
and transform it into a research-safe, point-in-time dataset.

Research-only:
- No sentiment score
- No trading signal
- No forecast
- No Decision Engine integration

Source
------
AAII Investor Sentiment Survey
Official historical spreadsheet:
https://www.aaii.com/files/surveys/sentiment.xls

Survey methodology:
- Weekly survey
- Bullish / Neutral / Bearish
- Survey period ends Wednesday
- Results published Thursday

PIT methodology
---------------
observation_date:
    AAII reported / survey week-ending date

availability_date:
    observation_date + 1 calendar day

This is a conservative publication-date proxy based on AAII's
documented Thursday publication schedule.

Important:
This is a research-safe proxy, not an exact historical timestamp.

Outputs
-------
aaii_historical_records_input_v1.csv
aaii_historical_collection_summary_v1.csv
"""

from __future__ import annotations

import io
import re
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests


# ============================================================
# Configuration
# ============================================================

SOURCE_URL = (
    "https://www.aaii.com/files/surveys/sentiment.xls"
)

SOURCE_PAGE_URL = (
    "https://www.aaii.com/sentimentsurvey/sent_results"
)

OUTPUT_RECORDS = (
    "aaii_historical_records_input_v1.csv"
)

OUTPUT_SUMMARY = (
    "aaii_historical_collection_summary_v1.csv"
)

MIN_EXPECTED_RECORDS = 1000

RESEARCH_ONLY = True
DECISION_ENGINE_READY = False
SENTIMENT_SCORE_GENERATED = False
POINT_IN_TIME_SAFE = True

AVAILABILITY_SEMANTICS = (
    "conservative_proxy_"
    "publication_thursday_after_survey_week"
)


# ============================================================
# Helpers
# ============================================================

def fail(message: str) -> None:
    print()
    print("=" * 72)
    print("AAII HISTORICAL COLLECTOR V1: FAIL")
    print("=" * 72)
    print(message)
    print("=" * 72)
    sys.exit(1)


def clean_column_name(value) -> str:
    """
    Normalize spreadsheet column names.
    """
    value = str(value).strip().lower()

    value = value.replace("\n", " ")
    value = value.replace("\r", " ")

    value = re.sub(r"\s+", "_", value)

    value = re.sub(
        r"[^a-z0-9_]+",
        "",
        value,
    )

    return value


def parse_percent_series(series: pd.Series) -> pd.Series:
    """
    Convert percentage values such as:
        37.5%
        37.5
        0.375

    into percentage points:
        37.5
    """

    cleaned = (
        series.astype(str)
        .str.strip()
        .str.replace("%", "", regex=False)
        .str.replace(",", "", regex=False)
    )

    numeric = pd.to_numeric(
        cleaned,
        errors="coerce",
    )

    # If values look like fractions, convert them
    # to percentage points.
    fraction_mask = (
        numeric.notna()
        & (numeric >= 0)
        & (numeric <= 1)
    )

    numeric.loc[fraction_mask] = (
        numeric.loc[fraction_mask] * 100.0
    )

    return numeric


def detect_header_row(raw: pd.DataFrame) -> int:
    """
    Detect the header row containing
    Date/Bullish/Neutral/Bearish.
    """

    for i in range(
        min(len(raw), 30)
    ):

        row = raw.iloc[i].astype(str).str.lower()

        joined = " ".join(row.tolist())

        has_bullish = "bullish" in joined
        has_neutral = "neutral" in joined
        has_bearish = "bearish" in joined

        if (
            has_bullish
            and has_neutral
            and has_bearish
        ):
            return i

    fail(
        "Could not detect the AAII spreadsheet header row."
    )


def find_column(
    columns,
    candidates,
    required=True,
):
    """
    Find a column using normalized candidate names.
    """

    normalized = {
        clean_column_name(c): c
        for c in columns
    }

    for candidate in candidates:

        key = clean_column_name(candidate)

        if key in normalized:
            return normalized[key]

    # More flexible matching
    for column in columns:

        normalized_column = clean_column_name(
            column
        )

        for candidate in candidates:

            candidate_key = clean_column_name(
                candidate
            )

            if (
                candidate_key in normalized_column
                or normalized_column in candidate_key
            ):
                return column

    if required:
        fail(
            "Required column not found. "
            f"Candidates={candidates}. "
            f"Available={list(columns)}"
        )

    return None


# ============================================================
# Download official AAII dataset
# ============================================================

def download_source() -> bytes:

    print("=" * 72)
    print("AAII HISTORICAL COLLECTOR V1")
    print("=" * 72)

    print()
    print("Source:")
    print(SOURCE_URL)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(compatible; "
            "US500-Macro-Intelligence/1.0)"
        )
    }

    try:

        response = requests.get(
            SOURCE_URL,
            headers=headers,
            timeout=60,
        )

        response.raise_for_status()

    except requests.RequestException as exc:

        fail(
            "Unable to download official AAII "
            f"historical dataset: {exc}"
        )

    content_type = (
        response.headers
        .get("Content-Type", "")
        .lower()
    )

    print()
    print(
        "HTTP status:",
        response.status_code,
    )

    print(
        "Content-Type:",
        content_type,
    )

    print(
        "Downloaded bytes:",
        len(response.content),
    )

    if len(response.content) < 1000:

        fail(
            "Downloaded file is unexpectedly small."
        )

    return response.content


# ============================================================
# Read AAII spreadsheet
# ============================================================

def read_source(content: bytes) -> pd.DataFrame:

    print()
    print("Reading AAII spreadsheet...")

    try:

        raw = pd.read_excel(
            io.BytesIO(content),
            header=None,
        )

    except Exception as exc:

        fail(
            "Unable to read AAII XLS file. "
            "Make sure xlrd is installed. "
            f"Error={exc}"
        )

    if raw.empty:

        fail(
            "AAII spreadsheet is empty."
        )

    header_row = detect_header_row(
        raw
    )

    print(
        "Detected header row:",
        header_row,
    )

    df = pd.read_excel(
        io.BytesIO(content),
        header=header_row,
    )

    return df


# ============================================================
# Normalize AAII data
# ============================================================

def normalize_source(
    df: pd.DataFrame,
) -> pd.DataFrame:

    print()
    print("Normalizing AAII data...")

    # --------------------------------------------------------
    # Normalize column names
    # --------------------------------------------------------

    original_columns = list(
        df.columns
    )

    normalized_map = {
        column: clean_column_name(column)
        for column in original_columns
    }

    df = df.rename(
        columns=normalized_map
    )

    print(
        "Detected columns:",
        list(df.columns),
    )

    # --------------------------------------------------------
    # Find columns
    # --------------------------------------------------------

    date_column = find_column(
        df.columns,
        [
            "reported_date",
            "report_date",
            "date",
            "week_ending",
            "week_end",
            "reported",
        ],
    )

    bullish_column = find_column(
        df.columns,
        [
            "bullish",
            "bull",
        ],
    )

    neutral_column = find_column(
        df.columns,
        [
            "neutral",
        ],
    )

    bearish_column = find_column(
        df.columns,
        [
            "bearish",
            "bear",
        ],
    )

    # --------------------------------------------------------
    # Select
    # --------------------------------------------------------

    data = df[
        [
            date_column,
            bullish_column,
            neutral_column,
            bearish_column,
        ]
    ].copy()

    data.columns = [
        "observation_date_raw",
        "bullish",
        "neutral",
        "bearish",
    ]

    # --------------------------------------------------------
    # Parse date
    # --------------------------------------------------------

    data["observation_date"] = pd.to_datetime(
        data["observation_date_raw"],
        errors="coerce",
    )

    # --------------------------------------------------------
    # Parse percentages
    # --------------------------------------------------------

    data["bullish"] = parse_percent_series(
        data["bullish"]
    )

    data["neutral"] = parse_percent_series(
        data["neutral"]
    )

    data["bearish"] = parse_percent_series(
        data["bearish"]
    )

    # --------------------------------------------------------
    # Remove invalid rows
    # --------------------------------------------------------

    data = data[
        data["observation_date"].notna()
    ].copy()

    data = data[
        data["bullish"].notna()
        & data["neutral"].notna()
        & data["bearish"].notna()
    ].copy()

    # --------------------------------------------------------
    # Keep realistic AAII percentage values
    # --------------------------------------------------------

    data = data[
        (data["bullish"] >= 0)
        & (data["bullish"] <= 100)
        & (data["neutral"] >= 0)
        & (data["neutral"] <= 100)
        & (data["bearish"] >= 0)
        & (data["bearish"] <= 100)
    ].copy()

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    data = data.sort_values(
        "observation_date"
    ).reset_index(
        drop=True
    )

    return data


# ============================================================
# Build PIT-safe records
# ============================================================

def build_records(
    data: pd.DataFrame,
) -> pd.DataFrame:

    print()
    print("Building PIT-safe records...")

    records = pd.DataFrame()

    records[
        "observation_date"
    ] = data[
        "observation_date"
    ]

    records[
        "availability_date"
    ] = (
        records[
            "observation_date"
        ]
        + pd.Timedelta(days=1)
    )

    records[
        "bullish_pct"
    ] = data["bullish"]

    records[
        "neutral_pct"
    ] = data["neutral"]

    records[
        "bearish_pct"
    ] = data["bearish"]

    # --------------------------------------------------------
    # Derived descriptive fields
    # --------------------------------------------------------

    records[
        "bull_bear_spread_pp"
    ] = (
        records["bullish_pct"]
        - records["bearish_pct"]
    )

    # --------------------------------------------------------
    # Source metadata
    # --------------------------------------------------------

    records[
        "source"
    ] = "AAII Investor Sentiment Survey"

    records[
        "source_url"
    ] = SOURCE_URL

    records[
        "source_page_url"
    ] = SOURCE_PAGE_URL

    records[
        "availability_semantics"
    ] = AVAILABILITY_SEMANTICS

    # --------------------------------------------------------
    # PIT metadata
    # --------------------------------------------------------

    records[
        "point_in_time_safe"
    ] = POINT_IN_TIME_SAFE

    records[
        "research_only"
    ] = RESEARCH_ONLY

    records[
        "decision_engine_ready"
    ] = DECISION_ENGINE_READY

    records[
        "sentiment_score_generated"
    ] = SENTIMENT_SCORE_GENERATED

    return records


# ============================================================
# Schema validation
# ============================================================

def validate_schema(
    records: pd.DataFrame,
) -> None:

    print()
    print("Validating schema...")

    required_columns = [

        "observation_date",
        "availability_date",

        "bullish_pct",
        "neutral_pct",
        "bearish_pct",

        "bull_bear_spread_pp",

        "source",
        "source_url",
        "source_page_url",

        "availability_semantics",

        "point_in_time_safe",
        "research_only",
        "decision_engine_ready",
        "sentiment_score_generated",
    ]

    missing = [
        column
        for column in required_columns
        if column not in records.columns
    ]

    if missing:

        fail(
            "Schema validation failed. "
            f"Missing columns: {missing}"
        )

    if len(records.columns) != len(
        required_columns
    ):

        print(
            "WARNING: Output contains a different "
            "number of columns than the minimum schema."
        )

    print(
        "Schema validation: PASS"
    )


# ============================================================
# PIT validation
# ============================================================

def validate_pit(
    records: pd.DataFrame,
) -> None:

    print()
    print("Validating point-in-time safety...")

    observation = pd.to_datetime(
        records["observation_date"],
        errors="coerce",
    )

    availability = pd.to_datetime(
        records["availability_date"],
        errors="coerce",
    )

    if observation.isna().any():

        fail(
            "Invalid observation_date detected."
        )

    if availability.isna().any():

        fail(
            "Invalid availability_date detected."
        )

    invalid_dates = (
        availability
        <= observation
    )

    if invalid_dates.any():

        count = int(
            invalid_dates.sum()
        )

        fail(
            "PIT validation failed: "
            f"{count} records have "
            "availability_date <= observation_date."
        )

    # --------------------------------------------------------
    # Explicit PIT flag
    # --------------------------------------------------------

    if not records[
        "point_in_time_safe"
    ].astype(bool).all():

        fail(
            "point_in_time_safe is not TRUE "
            "for every record."
        )

    # --------------------------------------------------------
    # Research-only flags
    # --------------------------------------------------------

    if not records[
        "research_only"
    ].astype(bool).all():

        fail(
            "research_only must be TRUE."
        )

    if records[
        "decision_engine_ready"
    ].astype(bool).any():

        fail(
            "Decision Engine must remain disabled."
        )

    if records[
        "sentiment_score_generated"
    ].astype(bool).any():

        fail(
            "Sentiment score must not be generated "
            "by the historical collector."
        )

    print(
        "PIT validation: PASS"
    )


# ============================================================
# Data integrity validation
# ============================================================

def validate_integrity(
    records: pd.DataFrame,
) -> None:

    print()
    print("Validating data integrity...")

    # --------------------------------------------------------
    # Minimum record count
    # --------------------------------------------------------

    if len(records) < MIN_EXPECTED_RECORDS:

        fail(
            "Unexpectedly low AAII record count: "
            f"{len(records)}. "
            f"Expected at least {MIN_EXPECTED_RECORDS}."
        )

    # --------------------------------------------------------
    # Duplicate dates
    # --------------------------------------------------------

    duplicates = records.duplicated(
        subset=[
            "observation_date"
        ]
    ).sum()

    if duplicates:

        fail(
            f"Duplicate observation dates: "
            f"{duplicates}"
        )

    # --------------------------------------------------------
    # Chronological order
    # --------------------------------------------------------

    if not records[
        "observation_date"
    ].is_monotonic_increasing:

        fail(
            "Observation dates are not "
            "monotonically increasing."
        )

    # --------------------------------------------------------
    # Percentage validation
    # --------------------------------------------------------

    percentage_columns = [
        "bullish_pct",
        "neutral_pct",
        "bearish_pct",
    ]

    for column in percentage_columns:

        values = records[
            column
        ]

        invalid = (
            values.isna()
            | (values < 0)
            | (values > 100)
        )

        if invalid.any():

            fail(
                f"Invalid percentage values "
                f"in {column}: "
                f"{int(invalid.sum())}"
            )

    # --------------------------------------------------------
    # Weekly sum validation
    # --------------------------------------------------------

    sentiment_sum = (
        records["bullish_pct"]
        + records["neutral_pct"]
        + records["bearish_pct"]
    )

    # AAII values can have rounding differences.
    # Allow a small tolerance.
    sum_error = (
        sentiment_sum - 100
    ).abs()

    invalid_sum = (
        sum_error > 0.5
    )

    if invalid_sum.any():

        fail(
            "Bullish + Neutral + Bearish "
            "does not approximately equal 100 "
            "for "
            f"{int(invalid_sum.sum())} records."
        )

    # --------------------------------------------------------
    # Spread validation
    # --------------------------------------------------------

    expected_spread = (
        records["bullish_pct"]
        - records["bearish_pct"]
    )

    if not np.allclose(
        records[
            "bull_bear_spread_pp"
        ],
        expected_spread,
        equal_nan=True,
    ):

        fail(
            "Bull-bear spread calculation mismatch."
        )

    print(
        "Data integrity: PASS"
    )


# ============================================================
# Summary
# ============================================================

def create_summary(
    records: pd.DataFrame,
) -> pd.DataFrame:

    first_date = records[
        "observation_date"
    ].min()

    last_date = records[
        "observation_date"
    ].max()

    summary = pd.DataFrame(
        [
            {
                "dataset": (
                    "AAII Investor Sentiment Survey"
                ),

                "records": len(records),

                "first_observation_date": (
                    first_date.date()
                ),

                "last_observation_date": (
                    last_date.date()
                ),

                "source": (
                    "AAII Investor Sentiment Survey"
                ),

                "source_url": SOURCE_URL,

                "availability_semantics": (
                    AVAILABILITY_SEMANTICS
                ),

                "point_in_time_safe": True,

                "research_only": True,

                "decision_engine_ready": False,

                "sentiment_score_generated": False,

                "duplicate_observations": 0,

                "min_expected_records": (
                    MIN_EXPECTED_RECORDS
                ),
            }
        ]
    )

    return summary


# ============================================================
# Main
# ============================================================

def main() -> None:

    content = download_source()

    raw = read_source(
        content
    )

    data = normalize_source(
        raw
    )

    if data.empty:

        fail(
            "No valid AAII observations "
            "were extracted."
        )

    records = build_records(
        data
    )

    validate_schema(
        records
    )

    validate_pit(
        records
    )

    validate_integrity(
        records
    )

    summary = create_summary(
        records
    )

    # ========================================================
    # Save records
    # ========================================================

    records.to_csv(
        OUTPUT_RECORDS,
        index=False,
    )

    summary.to_csv(
        OUTPUT_SUMMARY,
        index=False,
    )

    # ========================================================
    # Final report
    # ========================================================

    print()
    print("=" * 72)
    print("AAII HISTORICAL COLLECTOR V1")
    print("VALIDATION REPORT")
    print("=" * 72)

    print(
        f"Records:                    {len(records):,}"
    )

    print(
        "First observation:          "
        f"{records['observation_date'].min().date()}"
    )

    print(
        "Last observation:           "
        f"{records['observation_date'].max().date()}"
    )

    print(
        "Duplicate observations:     0"
    )

    print(
        "PIT safe:                   TRUE"
    )

    print(
        "Research only:              TRUE"
    )

    print(
        "Decision Engine ready:      FALSE"
    )

    print(
        "Sentiment score generated:  FALSE"
    )

    print(
        "Source:                     AAII"
    )

    print()
    print("Output files:")

    print(
        f"  - {OUTPUT_RECORDS}"
    )

    print(
        f"  - {OUTPUT_SUMMARY}"
    )

    print()
    print("=" * 72)
    print("VALIDATION: PASS")
    print("=" * 72)


if __name__ == "__main__":
    main()
