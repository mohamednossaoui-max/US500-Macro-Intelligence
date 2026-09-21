"""
AAII Historical Sentiment Collector v1

Research-only historical collector.

Source:
    AAII Investor Sentiment Survey

Official historical dataset:
    https://www.aaii.com/files/surveys/sentiment.xls

Design:
    - Historical AAII Bullish / Neutral / Bearish
    - Point-in-time safe research dataset
    - Conservative availability-date proxy
    - No sentiment score
    - No trading signal
    - No forecast
    - No Decision Engine integration

Outputs:
    aaii_historical_records_input_v1.csv
    aaii_historical_collection_summary_v1.csv
"""

from __future__ import annotations

import io
import re
import sys

from pathlib import Path
from datetime import timedelta

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
    "conservative_proxy_publication_thursday_"
    "after_survey_week"
)


# ============================================================
# Error helper
# ============================================================

def fail(message: str) -> None:

    print()
    print("=" * 72)
    print("AAII HISTORICAL COLLECTOR V1: FAIL")
    print("=" * 72)
    print(message)
    print("=" * 72)

    sys.exit(1)


# ============================================================
# Column-name normalization
# ============================================================

def clean_column_name(value) -> str:

    value = str(value).strip().lower()

    value = value.replace("\n", " ")
    value = value.replace("\r", " ")

    value = re.sub(
        r"\s+",
        "_",
        value,
    )

    value = re.sub(
        r"[^a-z0-9_]+",
        "",
        value,
    )

    return value


# ============================================================
# Percentage parser
# ============================================================

def parse_percent_series(
    series: pd.Series,
) -> pd.Series:
    """
    Convert values such as:

        35.4%
        35.4
        0.354

    into percentage points:

        35.4
    """

    cleaned = (
        series
        .astype(str)
        .str.strip()
        .str.replace(
            "%",
            "",
            regex=False,
        )
        .str.replace(
            ",",
            "",
            regex=False,
        )
    )

    numeric = pd.to_numeric(
        cleaned,
        errors="coerce",
    )

    # Convert fractions to percentage points.
    fraction_mask = (
        numeric.notna()
        & (numeric >= 0)
        & (numeric <= 1)
    )

    numeric.loc[fraction_mask] = (
        numeric.loc[fraction_mask] * 100.0
    )

    return numeric


# ============================================================
# Header detection
# ============================================================

def detect_header_row(
    raw: pd.DataFrame,
) -> int:
    """
    Detect the AAII spreadsheet header row.

    The spreadsheet may contain mixed cell types
    including strings, floats and NaN values.

    Therefore every cell is safely converted to
    string before searching.
    """

    for i in range(
        min(len(raw), 50)
    ):

        row = raw.iloc[i]

        values = [
            str(value).strip().lower()
            for value in row.tolist()
            if pd.notna(value)
        ]

        joined = " ".join(values)

        has_bullish = (
            "bullish" in joined
        )

        has_neutral = (
            "neutral" in joined
        )

        has_bearish = (
            "bearish" in joined
        )

        if (
            has_bullish
            and has_neutral
            and has_bearish
        ):
            return i

    fail(
        "Could not detect the AAII spreadsheet "
        "header row."
    )

    return -1


# ============================================================
# Flexible column finder
# ============================================================

def find_column(
    columns,
    candidates,
    required=True,
):

    normalized = {
        clean_column_name(column): column
        for column in columns
    }

    # Exact normalized match
    for candidate in candidates:

        key = clean_column_name(
            candidate
        )

        if key in normalized:

            return normalized[key]

    # Flexible partial match
    for column in columns:

        normalized_column = (
            clean_column_name(column)
        )

        for candidate in candidates:

            candidate_key = (
                clean_column_name(candidate)
            )

            if (
                candidate_key
                in normalized_column
            ):

                return column

            if (
                normalized_column
                in candidate_key
            ):

                return column

    if required:

        fail(
            "Required column not found.\n"
            f"Candidates: {candidates}\n"
            f"Available columns: {list(columns)}"
        )

    return None


# ============================================================
# Download official AAII file
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
        .get(
            "Content-Type",
            "",
        )
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
            "Downloaded AAII file is "
            "unexpectedly small."
        )

    # --------------------------------------------------------
    # Verify XLS signature
    # --------------------------------------------------------

    # Traditional XLS files normally begin with
    # OLE Compound File signature:
    #
    # D0 CF 11 E0 A1 B1 1A E1
    #
    # We don't hard-fail solely on the signature because
    # servers may return a valid spreadsheet through
    # different packaging.

    if response.content[:8] == (
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    ):

        print(
            "XLS file signature: detected"
        )

    else:

        print(
            "WARNING: Traditional XLS signature "
            "not detected."
        )

    return response.content


# ============================================================
# Read XLS
# ============================================================

def read_source(
    content: bytes,
) -> pd.DataFrame:

    print()
    print("Reading AAII spreadsheet...")

    try:

        raw = pd.read_excel(
            io.BytesIO(content),
            header=None,
            engine="xlrd",
        )

    except Exception as exc:

        fail(
            "Unable to read AAII XLS file.\n"
            "Required dependency: xlrd\n"
            f"Error: {exc}"
        )

    if raw.empty:

        fail(
            "AAII spreadsheet is empty."
        )

    print(
        "Spreadsheet rows:",
        len(raw),
    )

    print(
        "Spreadsheet columns:",
        len(raw.columns),
    )

    # --------------------------------------------------------
    # Detect header
    # --------------------------------------------------------

    header_row = detect_header_row(
        raw
    )

    print(
        "Detected header row:",
        header_row,
    )

    try:

        df = pd.read_excel(
            io.BytesIO(content),
            header=header_row,
            engine="xlrd",
        )

    except Exception as exc:

        fail(
            "Unable to reload AAII spreadsheet "
            f"using detected header row: {exc}"
        )

    if df.empty:

        fail(
            "AAII dataset after header parsing "
            "is empty."
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
        column: clean_column_name(
            column
        )
        for column in original_columns
    }

    df = df.rename(
        columns=normalized_map
    )

    print(
        "Normalized columns:"
    )

    print(
        list(df.columns)
    )

    # --------------------------------------------------------
    # Find date column
    # --------------------------------------------------------

    date_column = find_column(
        df.columns,
        [
            "reported_date",
            "report_date",
            "date",
            "week_ending",
            "week_end",
            "survey_date",
            "reported",
        ],
    )

    # --------------------------------------------------------
    # Find sentiment columns
    # --------------------------------------------------------

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

    print()
    print(
        "Date column:",
        date_column,
    )

    print(
        "Bullish column:",
        bullish_column,
    )

    print(
        "Neutral column:",
        neutral_column,
    )

    print(
        "Bearish column:",
        bearish_column,
    )

    # --------------------------------------------------------
    # Select relevant columns
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
    # Parse dates
    # --------------------------------------------------------

    data[
        "observation_date"
    ] = pd.to_datetime(
        data[
            "observation_date_raw"
        ],
        errors="coerce",
    )

    # --------------------------------------------------------
    # Parse percentages
    # --------------------------------------------------------

    data["bullish"] = (
        parse_percent_series(
            data["bullish"]
        )
    )

    data["neutral"] = (
        parse_percent_series(
            data["neutral"]
        )
    )

    data["bearish"] = (
        parse_percent_series(
            data["bearish"]
        )
    )

    # --------------------------------------------------------
    # Remove rows without valid date
    # --------------------------------------------------------

    data = data[
        data[
            "observation_date"
        ].notna()
    ].copy()

    # --------------------------------------------------------
    # Remove rows without sentiment data
    # --------------------------------------------------------

    data = data[
        data["bullish"].notna()
        & data["neutral"].notna()
        & data["bearish"].notna()
    ].copy()

    # --------------------------------------------------------
    # Percentage bounds
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

    data = (
        data
        .sort_values(
            "observation_date"
        )
        .reset_index(
            drop=True
        )
    )

    if data.empty:

        fail(
            "No valid AAII observations "
            "remain after normalization."
        )

    return data


# ============================================================
# Build PIT-safe records
# ============================================================

def build_records(
    data: pd.DataFrame,
) -> pd.DataFrame:

    print()
    print("Building PIT-safe AAII records...")

    records = pd.DataFrame()

    # --------------------------------------------------------
    # Dates
    # --------------------------------------------------------

    records[
        "observation_date"
    ] = data[
        "observation_date"
    ]

    # Conservative publication proxy:
    # AAII publishes results Thursday after
    # Wednesday survey close.
    records[
        "availability_date"
    ] = (
        records[
            "observation_date"
        ]
        + pd.Timedelta(
            days=1
        )
    )

    # --------------------------------------------------------
    # Sentiment
    # --------------------------------------------------------

    records[
        "bullish_pct"
    ] = data[
        "bullish"
    ]

    records[
        "neutral_pct"
    ] = data[
        "neutral"
    ]

    records[
        "bearish_pct"
    ] = data[
        "bearish"
    ]

    # --------------------------------------------------------
    # Descriptive spread
    # --------------------------------------------------------

    records[
        "bull_bear_spread_pp"
    ] = (
        records[
            "bullish_pct"
        ]
        -
        records[
            "bearish_pct"
        ]
    )

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    records[
        "source"
    ] = (
        "AAII Investor Sentiment Survey"
    )

    records[
        "source_url"
    ] = SOURCE_URL

    records[
        "source_page_url"
    ] = SOURCE_PAGE_URL

    records[
        "availability_semantics"
    ] = (
        AVAILABILITY_SEMANTICS
    )

    # --------------------------------------------------------
    # Research controls
    # --------------------------------------------------------

    records[
        "point_in_time_safe"
    ] = True

    records[
        "research_only"
    ] = True

    records[
        "decision_engine_ready"
    ] = False

    records[
        "sentiment_score_generated"
    ] = False

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
            "Schema validation failed.\n"
            "Missing columns:\n"
            + "\n".join(
                f"  - {column}"
                for column in missing
            )
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
    print(
        "Validating point-in-time safety..."
    )

    observation = pd.to_datetime(
        records[
            "observation_date"
        ],
        errors="coerce",
    )

    availability = pd.to_datetime(
        records[
            "availability_date"
        ],
        errors="coerce",
    )

    # --------------------------------------------------------
    # Invalid dates
    # --------------------------------------------------------

    if observation.isna().any():

        fail(
            "PIT validation failed: "
            "invalid observation_date."
        )

    if availability.isna().any():

        fail(
            "PIT validation failed: "
            "invalid availability_date."
        )

    # --------------------------------------------------------
    # Availability must follow observation
    # --------------------------------------------------------

    invalid = (
        availability
        <= observation
    )

    if invalid.any():

        fail(
            "PIT validation failed: "
            f"{int(invalid.sum())} records have "
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
            "for all records."
        )

    # --------------------------------------------------------
    # Research-only
    # --------------------------------------------------------

    if not records[
        "research_only"
    ].astype(bool).all():

        fail(
            "research_only must be TRUE "
            "for all records."
        )

    # --------------------------------------------------------
    # Decision Engine
    # --------------------------------------------------------

    if records[
        "decision_engine_ready"
    ].astype(bool).any():

        fail(
            "Decision Engine integration detected."
        )

    # --------------------------------------------------------
    # Sentiment score
    # --------------------------------------------------------

    if records[
        "sentiment_score_generated"
    ].astype(bool).any():

        fail(
            "Sentiment score must not be generated "
            "by the collector."
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
    print(
        "Validating data integrity..."
    )

    # --------------------------------------------------------
    # Minimum records
    # --------------------------------------------------------

    if len(records) < MIN_EXPECTED_RECORDS:

        fail(
            "Unexpectedly low AAII record count: "
            f"{len(records)}. "
            f"Expected at least "
            f"{MIN_EXPECTED_RECORDS}."
        )

    # --------------------------------------------------------
    # Duplicate observations
    # --------------------------------------------------------

    duplicates = records.duplicated(
        subset=[
            "observation_date"
        ]
    ).sum()

    if duplicates > 0:

        fail(
            "Duplicate observation dates: "
            f"{duplicates}"
        )

    # --------------------------------------------------------
    # Chronological ordering
    # --------------------------------------------------------

    if not records[
        "observation_date"
    ].is_monotonic_increasing:

        fail(
            "Observation dates are not "
            "monotonically increasing."
        )

    # --------------------------------------------------------
    # Percentage ranges
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
            |
            (values < 0)
            |
            (values > 100)
        )

        if invalid.any():

            fail(
                f"Invalid percentage values "
                f"in {column}: "
                f"{int(invalid.sum())}"
            )

    # --------------------------------------------------------
    # Sentiment sum
    # --------------------------------------------------------

    total = (
        records[
            "bullish_pct"
        ]
        +
        records[
            "neutral_pct"
        ]
        +
        records[
            "bearish_pct"
        ]
    )

    error = (
        total - 100
    ).abs()

    # Allow rounding differences.
    invalid_sum = (
        error > 0.5
    )

    if invalid_sum.any():

        fail(
            "Bullish + Neutral + Bearish "
            "does not approximately equal 100 "
            f"for {int(invalid_sum.sum())} rows."
        )

    # --------------------------------------------------------
    # Bull-Bear spread
    # --------------------------------------------------------

    expected_spread = (
        records[
            "bullish_pct"
        ]
        -
        records[
            "bearish_pct"
        ]
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

    # --------------------------------------------------------
    # Source
    # --------------------------------------------------------

    if not (
        records[
            "source"
        ]
        .astype(str)
        .str.contains(
            "AAII",
            case=False,
            na=False,
        )
        .all()
    ):

        fail(
            "Unexpected source metadata."
        )

    print(
        "Data integrity: PASS"
    )


# ============================================================
# Create collection summary
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

    # --------------------------------------------------------
    # Download
    # --------------------------------------------------------

    content = download_source()

    # --------------------------------------------------------
    # Read
    # --------------------------------------------------------

    raw = read_source(
        content
    )

    # --------------------------------------------------------
    # Normalize
    # --------------------------------------------------------

    data = normalize_source(
        raw
    )

    # --------------------------------------------------------
    # Build records
    # --------------------------------------------------------

    records = build_records(
        data
    )

    # --------------------------------------------------------
    # Validate schema
    # --------------------------------------------------------

    validate_schema(
        records
    )

    # --------------------------------------------------------
    # Validate PIT
    # --------------------------------------------------------

    validate_pit(
        records
    )

    # --------------------------------------------------------
    # Validate integrity
    # --------------------------------------------------------

    validate_integrity(
        records
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary = create_summary(
        records
    )

    # --------------------------------------------------------
    # Save records
    # --------------------------------------------------------

    records.to_csv(
        OUTPUT_RECORDS,
        index=False,
    )

    # --------------------------------------------------------
    # Save summary
    # --------------------------------------------------------

    summary.to_csv(
        OUTPUT_SUMMARY,
        index=False,
    )

    # --------------------------------------------------------
    # Final validation report
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print(
        "AAII HISTORICAL COLLECTOR V1"
    )
    print(
        "FINAL VALIDATION REPORT"
    )
    print("=" * 72)

    print(
        f"Records:                    "
        f"{len(records):,}"
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
        "Schema validation:          PASS"
    )

    print(
        "PIT validation:             PASS"
    )

    print(
        "Data integrity:             PASS"
    )

    print()
    print(
        "Output files:"
    )

    print(
        f"  - {OUTPUT_RECORDS}"
    )

    print(
        f"  - {OUTPUT_SUMMARY}"
    )

    print()
    print("=" * 72)
    print(
        "VALIDATION: PASS"
    )
    print("=" * 72)


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    main()
