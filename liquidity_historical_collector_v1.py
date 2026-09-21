"""
Liquidity Historical Collector v1

Official FRED Series / Initial Release
Research-only — No Decision Engine

Purpose:
    Collect historical liquidity-related observations from official
    FRED series using output_type=4 (Initial Release Only).

Important historical unit normalization:
    WRESBAL and WTREGEN changed their published H.4.1 units.

    Through the 2025-11-12 release:
        Billions of U.S. Dollars

    Beginning with the 2025-11-13 release:
        Millions of U.S. Dollars

    The project canonical balance-sheet unit is:
        Millions of U.S. Dollars

    Therefore historical WRESBAL and WTREGEN observations released
    before 2025-11-13 are multiplied by 1000.

    This normalization is vintage/release-date aware and does NOT
    use a numeric-value heuristic.

Method:
    1. Retrieve actual FRED vintage dates for each series.
    2. Restrict vintage dates to the requested historical period.
    3. Request observations using vintage_dates in safe batches.
    4. Use output_type=4 so observations represent Initial Release Only.
    5. Normalize historical H.4.1 units where required.
    6. Deduplicate observations.
    7. Validate PIT/research-only metadata.
    8. Write the historical research dataset and summary.

Indicators:
    WALCL      - Federal Reserve Total Assets
    WRESBAL    - Reserve Balances
    WTREGEN    - Treasury General Account
    WSHOTSL    - Treasury Securities
    WSHOMCB    - Mortgage-Backed Securities
    RRPONTSYD  - Overnight Reverse Repurchase Agreements
    SOFR       - Secured Overnight Financing Rate
    EFFR       - Effective Federal Funds Rate

Research-only:
    - No liquidity score
    - No trading signal
    - No forecast
    - No Decision Engine
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests


# ================================================================
# CONFIGURATION
# ================================================================

START_DATE = os.getenv(
    "LIQUIDITY_START_DATE",
    "2019-01-01"
)

END_DATE = os.getenv(
    "LIQUIDITY_END_DATE",
    "2026-09-21"
)

FRED_API_KEY = os.getenv(
    "FRED_API_KEY"
)

FRED_OBSERVATIONS_ENDPOINT = (
    "https://api.stlouisfed.org/fred/series/observations"
)

FRED_VINTAGE_DATES_ENDPOINT = (
    "https://api.stlouisfed.org/fred/series/vintagedates"
)

OUTPUT_FILE = Path(
    "liquidity_historical_records_input_v1.csv"
)

SUMMARY_FILE = Path(
    "liquidity_historical_collection_summary_v1.csv"
)

# Keep comfortably below FRED's vintage-date limit.
VINTAGE_BATCH_SIZE = 500


# ================================================================
# HISTORICAL UNIT TRANSITION
# ================================================================

# Official ALFRED H.4.1 metadata shows:
#
# WRESBAL:
#   Billions of U.S. Dollars through 2025-11-12
#   Millions of U.S. Dollars from 2025-11-13
#
# WTREGEN:
#   Billions of U.S. Dollars through 2025-11-12
#   Millions of U.S. Dollars from 2025-11-13
#
# The comparison is made against the INITIAL RELEASE / VINTAGE DATE,
# not against observation_date.

H41_UNIT_TRANSITION_DATE = pd.Timestamp(
    "2025-11-13"
)

H41_BILLIONS_SERIES = {
    "WRESBAL",
    "WTREGEN",
}


# ================================================================
# OFFICIAL FRED SERIES
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
# OUTPUT SCHEMA
# ================================================================

OUTPUT_COLUMNS = [

    "indicator",

    "observation_date",

    "availability_date",

    "actual",

    "unit",

    "source_unit",

    "unit_conversion_factor",

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
# DATE UTILITIES
# ================================================================

def validate_date(
    value,
    name
):

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


# ================================================================
# CONFIGURATION VALIDATION
# ================================================================

def validate_configuration():

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

    print(
        "Configuration validation: PASS"
    )


# ================================================================
# FRED REQUEST HELPER
# ================================================================

def fred_get(
    endpoint,
    params,
    series_id,
    purpose
):
    """
    Generic FRED API GET helper with diagnostics.
    """

    try:

        response = requests.get(
            endpoint,
            params=params,
            timeout=60,
        )

    except requests.RequestException as exc:

        raise RuntimeError(
            f"FRED network error for {series_id} "
            f"during {purpose}: {exc}"
        ) from exc

    if response.status_code != 200:

        print("")
        print("=" * 80)
        print("FRED API ERROR")
        print("=" * 80)

        print(
            f"Series: {series_id}"
        )

        print(
            f"Purpose: {purpose}"
        )

        print(
            f"HTTP status: "
            f"{response.status_code}"
        )

        print("")
        print("FRED response:")
        print(
            response.text
        )

        print("=" * 80)
        print("")

        raise RuntimeError(
            f"FRED API request failed for "
            f"{series_id}: HTTP "
            f"{response.status_code}"
        )

    try:

        data = response.json()

    except ValueError as exc:

        raise RuntimeError(
            f"Invalid JSON response for "
            f"{series_id} during {purpose}."
        ) from exc

    if "error_code" in data:

        raise RuntimeError(
            f"FRED API error for {series_id}: "
            f"{data.get('error_code')} - "
            f"{data.get('error_message')}"
        )

    return data


# ================================================================
# GET FRED VINTAGE DATES
# ================================================================

def fetch_vintage_dates(
    series_id,
    start_date,
    end_date
):
    """
    Retrieve actual FRED vintage dates for a series.

    These dates are used as the release/vintage dimension for
    output_type=4 Initial Release Only observations.
    """

    print("")
    print(
        f"[{series_id}] Fetching FRED vintage dates..."
    )

    params = {

        "api_key": FRED_API_KEY,

        "file_type": "json",

        "series_id": series_id,

        "realtime_start": start_date,

        "realtime_end": end_date,

        "limit": 10000,

        "offset": 0,

        "sort_order": "asc",
    }

    data = fred_get(
        endpoint=FRED_VINTAGE_DATES_ENDPOINT,
        params=params,
        series_id=series_id,
        purpose="vintage dates",
    )

    vintage_dates = data.get(
        "vintage_dates",
        []
    )

    if not vintage_dates:

        raise RuntimeError(
            f"No FRED vintage dates found "
            f"for {series_id} between "
            f"{start_date} and {end_date}."
        )

    filtered = [
        date
        for date in vintage_dates
        if start_date <= date <= end_date
    ]

    filtered = sorted(
        set(filtered)
    )

    print(
        f"[{series_id}] Vintage dates found: "
        f"{len(filtered):,}"
    )

    if filtered:

        print(
            f"[{series_id}] Vintage range: "
            f"{filtered[0]} -> {filtered[-1]}"
        )

    if not filtered:

        raise RuntimeError(
            f"No usable vintage dates remain "
            f"for {series_id} after filtering."
        )

    return filtered


# ================================================================
# FETCH OBSERVATIONS FOR VINTAGE BATCH
# ================================================================

def fetch_observation_vintage_batch(
    series_id,
    start_date,
    end_date,
    vintage_dates
):
    """
    Fetch observations for a batch of actual FRED vintage dates.

    output_type=4:
        Observations, Initial Release Only.
    """

    vintage_string = ",".join(
        vintage_dates
    )

    params = {

        "api_key": FRED_API_KEY,

        "file_type": "json",

        "series_id": series_id,

        "observation_start": start_date,

        "observation_end": end_date,

        "output_type": 4,

        "vintage_dates": vintage_string,

        "sort_order": "asc",

        "limit": 100000,

        "offset": 0,
    }

    data = fred_get(
        endpoint=FRED_OBSERVATIONS_ENDPOINT,
        params=params,
        series_id=series_id,
        purpose="initial-release observations",
    )

    observations = data.get(
        "observations",
        []
    )

    return observations


# ================================================================
# FETCH COMPLETE SERIES
# ================================================================

def fetch_fred_series(
    series_id,
    start_date,
    end_date
):
    """
    Fetch a complete Initial Release Only series.

    Process:

        1. Get actual vintage dates.
        2. Split them into safe batches.
        3. Request output_type=4 for each batch.
        4. Combine observations.
        5. Normalize and deduplicate later.
    """

    vintage_dates = fetch_vintage_dates(
        series_id=series_id,
        start_date=start_date,
        end_date=end_date,
    )

    batches = [

        vintage_dates[i:i + VINTAGE_BATCH_SIZE]

        for i in range(
            0,
            len(vintage_dates),
            VINTAGE_BATCH_SIZE
        )
    ]

    print(
        f"[{series_id}] Vintage batches: "
        f"{len(batches)}"
    )

    all_observations = []

    for batch_number, batch in enumerate(
        batches,
        start=1
    ):

        print(
            f"[{series_id}] "
            f"Batch {batch_number}/"
            f"{len(batches)}: "
            f"{batch[0]} -> {batch[-1]} "
            f"({len(batch)} vintage dates)"
        )

        observations = (
            fetch_observation_vintage_batch(
                series_id=series_id,
                start_date=start_date,
                end_date=end_date,
                vintage_dates=batch,
            )
        )

        print(
            f"[{series_id}] "
            f"Batch {batch_number} returned: "
            f"{len(observations):,} observations"
        )

        all_observations.extend(
            observations
        )

    print(
        f"[{series_id}] "
        f"Total raw observations: "
        f"{len(all_observations):,}"
    )

    if not all_observations:

        raise RuntimeError(
            f"FRED returned zero observations "
            f"for {series_id}."
        )

    return all_observations


# ================================================================
# VINTAGE-AWARE UNIT NORMALIZATION
# ================================================================

def normalize_h41_value(
    series_id,
    actual,
    fred_release_date
):
    """
    Normalize historical H.4.1 balance-sheet values.

    Canonical project unit:
        Millions of U.S. Dollars

    WRESBAL and WTREGEN:

        release < 2025-11-13
            source unit = Billions of U.S. Dollars
            conversion factor = 1000

        release >= 2025-11-13
            source unit = Millions of U.S. Dollars
            conversion factor = 1

    This intentionally uses the release/vintage date instead of
    a numeric-value heuristic.
    """

    if series_id not in H41_BILLIONS_SERIES:

        return (
            actual,
            SERIES[series_id]["unit"],
            1.0,
        )

    if not fred_release_date:

        raise RuntimeError(
            f"Missing FRED initial-release date "
            f"for {series_id}. "
            f"Cannot perform vintage-aware "
            f"unit normalization."
        )

    try:

        release_dt = pd.Timestamp(
            fred_release_date
        )

    except Exception as exc:

        raise RuntimeError(
            f"Invalid FRED initial-release date "
            f"for {series_id}: "
            f"{fred_release_date}"
        ) from exc

    if release_dt < H41_UNIT_TRANSITION_DATE:

        return (
            actual * 1000.0,
            "Billions of U.S. Dollars",
            1000.0,
        )

    return (
        actual,
        "Millions of U.S. Dollars",
        1.0,
    )


# ================================================================
# CONVERT FRED OBSERVATIONS
# ================================================================

def convert_series(
    series_id,
    observations
):
    """
    Convert raw FRED observations into the project's
    standardized research schema.
    """

    meta = SERIES[
        series_id
    ]

    rows = []

    for obs in observations:

        observation_date = obs.get(
            "date"
        )

        raw_value = obs.get(
            "value"
        )

        if not observation_date:

            continue

        if raw_value in (
            None,
            "",
            ".",
        ):

            continue

        try:

            actual = float(
                raw_value
            )

        except (
            TypeError,
            ValueError
        ):

            continue

        try:

            obs_dt = datetime.strptime(
                observation_date,
                "%Y-%m-%d"
            )

        except ValueError:

            continue

        # --------------------------------------------------------
        # FRED Initial Release / Vintage Date
        # --------------------------------------------------------

        fred_release_date = obs.get(
            "realtime_start"
        )

        if fred_release_date:

            try:

                release_dt = datetime.strptime(
                    fred_release_date,
                    "%Y-%m-%d"
                )

                availability_date = (
                    release_dt.strftime(
                        "%Y-%m-%d"
                    )
                )

                availability_semantics = (
                    "FRED realtime_start release/vintage "
                    "date; output_type=4 Initial Release; "
                    "exact publication timestamp not represented"
                )

            except ValueError:

                availability_date = (
                    obs_dt +
                    pd.Timedelta(days=1)
                ).strftime(
                    "%Y-%m-%d"
                )

                availability_semantics = (
                    "Fallback conservative +1 "
                    "calendar-day availability proxy; "
                    "FRED output_type=4 Initial Release; "
                    "exact publication timestamp not represented"
                )

        else:

            availability_date = (
                obs_dt +
                pd.Timedelta(days=1)
            ).strftime(
                "%Y-%m-%d"
            )

            availability_semantics = (
                "Fallback conservative +1 "
                "calendar-day availability proxy; "
                "FRED output_type=4 Initial Release; "
                "exact publication timestamp not represented"
            )

        # --------------------------------------------------------
        # Vintage-aware unit normalization
        # --------------------------------------------------------

        (
            actual_normalized,
            source_unit,
            unit_conversion_factor,
        ) = normalize_h41_value(
            series_id=series_id,
            actual=actual,
            fred_release_date=fred_release_date,
        )

        # --------------------------------------------------------
        # PIT sanity
        # --------------------------------------------------------

        availability_dt = datetime.strptime(
            availability_date,
            "%Y-%m-%d"
        )

        if availability_dt < obs_dt:

            raise RuntimeError(
                f"PIT violation for {series_id}: "
                f"observation_date="
                f"{observation_date}, "
                f"availability_date="
                f"{availability_date}"
            )

        # --------------------------------------------------------
        # Append normalized record
        # --------------------------------------------------------

        rows.append(
            {
                "indicator":
                    meta["indicator"],

                "observation_date":
                    observation_date,

                "availability_date":
                    availability_date,

                "actual":
                    actual_normalized,

                "unit":
                    (
                        "Millions of U.S. Dollars"
                        if series_id in H41_BILLIONS_SERIES
                        else meta["unit"]
                    ),

                "source_unit":
                    source_unit,

                "unit_conversion_factor":
                    unit_conversion_factor,

                "frequency":
                    meta["frequency"],

                "source":
                    meta["source"],

                "source_url":
                    meta["source_url"],

                "vintage":
                    "initial_release",

                "revision_flag":
                    False,

                "point_in_time_safe":
                    True,

                "availability_semantics":
                    availability_semantics,

                "research_only":
                    True,

                "decision_engine_ready":
                    False,

                "trading_signal_generated":
                    False,

                "forecast_generated":
                    False,

                "liquidity_score_generated":
                    False,
            }
        )

    print(
        f"[{series_id}] "
        f"Usable converted rows: "
        f"{len(rows):,}"
    )

    return rows


# ================================================================
# COLLECT ALL SERIES
# ================================================================

def collect_all_series():

    all_rows = []

    print("")
    print("=" * 80)
    print("Liquidity Historical Collector v1")
    print("Official FRED Series / Initial Release")
    print("Research-only — No Decision Engine")
    print("=" * 80)

    print(
        f"Start: {START_DATE}"
    )

    print(
        f"End:   {END_DATE}"
    )

    print(
        f"Required series: {len(SERIES)}"
    )

    print("")

    for series_id, meta in SERIES.items():

        print("")
        print("-" * 80)

        print(
            f"Collecting: "
            f"{meta['indicator']} "
            f"[{series_id}]"
        )

        print("-" * 80)

        observations = fetch_fred_series(
            series_id=series_id,
            start_date=START_DATE,
            end_date=END_DATE,
        )

        rows = convert_series(
            series_id=series_id,
            observations=observations,
        )

        if not rows:

            raise RuntimeError(
                f"No usable observations returned "
                f"for {series_id}."
            )

        all_rows.extend(
            rows
        )

        print(
            f"[{series_id}] "
            f"Added to collection: "
            f"{len(rows):,}"
        )

    return all_rows


# ================================================================
# OUTPUT VALIDATION
# ================================================================

def validate_output(df):

    print("")
    print("=" * 80)
    print("Collector Output Validation")
    print("=" * 80)

    # ------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------

    missing_columns = [
        column
        for column in OUTPUT_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:

        raise RuntimeError(
            f"Missing required columns: "
            f"{missing_columns}"
        )

    # ------------------------------------------------------------
    # Indicators
    # ------------------------------------------------------------

    expected_indicators = {
        meta["indicator"]
        for meta in SERIES.values()
    }

    actual_indicators = set(
        df["indicator"]
        .dropna()
        .unique()
    )

    missing_indicators = (
        expected_indicators -
        actual_indicators
    )

    if missing_indicators:

        raise RuntimeError(
            f"Missing indicators: "
            f"{sorted(missing_indicators)}"
        )

    unexpected_indicators = (
        actual_indicators -
        expected_indicators
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
        errors="coerce"
    )

    df["availability_date"] = pd.to_datetime(
        df["availability_date"],
        errors="coerce"
    )

    if df["observation_date"].isna().any():

        raise RuntimeError(
            "Invalid observation_date values."
        )

    if df["availability_date"].isna().any():

        raise RuntimeError(
            "Invalid availability_date values."
        )

    start_dt = pd.Timestamp(
        START_DATE
    )

    end_dt = pd.Timestamp(
        END_DATE
    )

    if (
        df["observation_date"] <
        start_dt
    ).any():

        raise RuntimeError(
            "Observation date earlier than "
            "requested start date."
        )

    if (
        df["observation_date"] >
        end_dt
    ).any():

        raise RuntimeError(
            "Observation date later than "
            "requested end date."
        )

    # ------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------

    if (
        df["availability_date"] <
        df["observation_date"]
    ).any():

        raise RuntimeError(
            "Availability date earlier than "
            "observation date."
        )

    # ------------------------------------------------------------
    # Numeric values
    # ------------------------------------------------------------

    df["actual"] = pd.to_numeric(
        df["actual"],
        errors="coerce"
    )

    if df["actual"].isna().any():

        raise RuntimeError(
            "Missing/non-numeric actual values."
        )

    if np.isinf(
        df["actual"]
    ).any():

        raise RuntimeError(
            "Infinite actual values detected."
        )

    # ------------------------------------------------------------
    # Unit metadata
    # ------------------------------------------------------------

    if df["source_unit"].isna().any():

        raise RuntimeError(
            "Missing source_unit metadata."
        )

    df["unit_conversion_factor"] = pd.to_numeric(
        df["unit_conversion_factor"],
        errors="coerce"
    )

    if df["unit_conversion_factor"].isna().any():

        raise RuntimeError(
            "Missing unit_conversion_factor metadata."
        )

    if (
        df["unit_conversion_factor"] <= 0
    ).any():

        raise RuntimeError(
            "Invalid unit_conversion_factor detected."
        )

    # ------------------------------------------------------------
    # Canonical H.4.1 units
    # ------------------------------------------------------------

    h41_indicators = {
        "FED_TOTAL_ASSETS",
        "RESERVE_BALANCES",
        "TREASURY_GENERAL_ACCOUNT",
        "TREASURY_SECURITIES",
        "MBS",
    }

    for indicator in sorted(
        h41_indicators
    ):

        group = df.loc[
            df["indicator"] == indicator
        ]

        if group.empty:

            continue

        if not (
            group["unit"]
            .eq("Millions of U.S. Dollars")
        ).all():

            raise RuntimeError(
                f"{indicator} is not normalized "
                "to Millions of U.S. Dollars."
            )

    # ------------------------------------------------------------
    # WRESBAL / WTREGEN transition validation
    # ------------------------------------------------------------

    for series_id in [
        "WRESBAL",
        "WTREGEN",
    ]:

        indicator = SERIES[
            series_id
        ]["indicator"]

        group = df.loc[
            df["indicator"] == indicator
        ].copy()

        if group.empty:

            raise RuntimeError(
                f"No records found for {indicator}."
            )

        group["availability_date"] = (
            pd.to_datetime(
                group["availability_date"]
            )
        )

        before = group.loc[
            group["availability_date"]
            <
            H41_UNIT_TRANSITION_DATE
        ]

        after = group.loc[
            group["availability_date"]
            >=
            H41_UNIT_TRANSITION_DATE
        ]

        if not before.empty:

            if not (
                before[
                    "unit_conversion_factor"
                ]
                .eq(1000.0)
            ).all():

                raise RuntimeError(
                    f"{indicator}: historical "
                    "pre-transition records "
                    "must use conversion factor 1000."
                )

        if not after.empty:

            if not (
                after[
                    "unit_conversion_factor"
                ]
                .eq(1.0)
            ).all():

                raise RuntimeError(
                    f"{indicator}: post-transition "
                    "records must use conversion factor 1."
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

    duplicates = df.duplicated(
        subset=duplicate_keys
    ).sum()

    if duplicates > 0:

        raise RuntimeError(
            f"Duplicate records detected: "
            f"{duplicates}"
        )

    # ------------------------------------------------------------
    # PIT
    # ------------------------------------------------------------

    if not (
        df["point_in_time_safe"]
        .astype(str)
        .str.lower()
        .eq("true")
    ).all():

        raise RuntimeError(
            "point_in_time_safe is not True "
            "for all records."
        )

    # ------------------------------------------------------------
    # Revision
    # ------------------------------------------------------------

    if not (
        df["revision_flag"]
        .astype(str)
        .str.lower()
        .eq("false")
    ).all():

        raise RuntimeError(
            "revision_flag is not False "
            "for all records."
        )

    # ------------------------------------------------------------
    # Research only
    # ------------------------------------------------------------

    if not (
        df["research_only"]
        .astype(str)
        .str.lower()
        .eq("true")
    ).all():

        raise RuntimeError(
            "research_only is not True "
            "for all records."
        )

    # ------------------------------------------------------------
    # Decision Engine
    # ------------------------------------------------------------

    if not (
        df["decision_engine_ready"]
        .astype(str)
        .str.lower()
        .eq("false")
    ).all():

        raise RuntimeError(
            "decision_engine_ready is not False."
        )

    # ------------------------------------------------------------
    # Trading signals
    # ------------------------------------------------------------

    if not (
        df["trading_signal_generated"]
        .astype(str)
        .str.lower()
        .eq("false")
    ).all():

        raise RuntimeError(
            "Trading signals detected."
        )

    # ------------------------------------------------------------
    # Forecast
    # ------------------------------------------------------------

    if not (
        df["forecast_generated"]
        .astype(str)
        .str.lower()
        .eq("false")
    ).all():

        raise RuntimeError(
            "Forecast generation detected."
        )

    # ------------------------------------------------------------
    # Liquidity score
    # ------------------------------------------------------------

    if not (
        df["liquidity_score_generated"]
        .astype(str)
        .str.lower()
        .eq("false")
    ).all():

        raise RuntimeError(
            "Liquidity score generation detected."
        )

    # ------------------------------------------------------------
    # Vintage
    # ------------------------------------------------------------

    if not (
        df["vintage"]
        .astype(str)
        .eq("initial_release")
    ).all():

        raise RuntimeError(
            "Unexpected vintage metadata."
        )

    print(
        "Schema: PASS"
    )

    print(
        "Indicators: PASS"
    )

    print(
        "Dates: PASS"
    )

    print(
        "Availability dates: PASS"
    )

    print(
        "Actual values: PASS"
    )

    print(
        "Unit normalization: PASS"
    )

    print(
        "Duplicates: PASS"
    )

    print(
        "Point-in-time safety: PASS"
    )

    print(
        "Revision flags: PASS"
    )

    print(
        "Research-only: PASS"
    )

    print(
        "Decision Engine: FALSE"
    )

    print(
        "Trading signals: FALSE"
    )

    print(
        "Forecast: FALSE"
    )

    print(
        "Liquidity score: FALSE"
    )

    print(
        "Vintage: initial_release"
    )

    print("")
    print(
        "Validation: PASS"
    )


# ================================================================
# SUMMARY
# ================================================================

def build_summary(df):

    summary_rows = []

    for indicator, group in (
        df.groupby(
            "indicator",
            sort=True
        )
    ):

        group = group.sort_values(
            "observation_date"
        )

        latest = group.iloc[-1]

        summary_rows.append(
            {
                "indicator":
                    indicator,

                "rows":
                    len(group),

                "first_observation":
                    group[
                        "observation_date"
                    ]
                    .min()
                    .strftime(
                        "%Y-%m-%d"
                    ),

                "last_observation":
                    group[
                        "observation_date"
                    ]
                    .max()
                    .strftime(
                        "%Y-%m-%d"
                    ),

                "latest_actual":
                    latest["actual"],

                "unit":
                    group["unit"].iloc[0],

                "source_unit":
                    latest["source_unit"],

                "unit_conversion_factor":
                    latest[
                        "unit_conversion_factor"
                    ],

                "frequency":
                    group["frequency"].iloc[0],

                "source":
                    group["source"].iloc[0],

                "vintage":
                    group["vintage"].iloc[0],

                "point_in_time_safe":
                    True,

                "research_only":
                    True,

                "decision_engine_ready":
                    False,

                "trading_signal_generated":
                    False,

                "forecast_generated":
                    False,

                "liquidity_score_generated":
                    False,
            }
        )

    return pd.DataFrame(
        summary_rows
    )


# ================================================================
# MAIN
# ================================================================

def main():

    try:

        # --------------------------------------------------------
        # Configuration
        # --------------------------------------------------------

        validate_configuration()

        # --------------------------------------------------------
        # Collection
        # --------------------------------------------------------

        rows = collect_all_series()

        if not rows:

            raise RuntimeError(
                "Collector returned zero records."
            )

        df = pd.DataFrame(
            rows
        )

        # --------------------------------------------------------
        # Exact schema
        # --------------------------------------------------------

        df = df[
            OUTPUT_COLUMNS
        ]

        # --------------------------------------------------------
        # Convert date fields
        # --------------------------------------------------------

        df["observation_date"] = pd.to_datetime(
            df["observation_date"]
        )

        df["availability_date"] = pd.to_datetime(
            df["availability_date"]
        )

        # --------------------------------------------------------
        # Deterministic sorting before deduplication
        # --------------------------------------------------------

        df = (
            df
            .sort_values(
                [
                    "indicator",
                    "observation_date",
                    "availability_date",
                ]
            )
            .reset_index(
                drop=True
            )
        )

        # --------------------------------------------------------
        # Deduplicate initial-release observations
        #
        # The same initial-release observation can appear more
        # than once when the observation request spans multiple
        # vintage batches.
        #
        # Since output_type=4 selects Initial Release Only,
        # preserve the earliest available initial-release metadata.
        # --------------------------------------------------------

        df = (
            df
            .drop_duplicates(
                subset=[
                    "indicator",
                    "observation_date",
                    "vintage",
                ],
                keep="first"
            )
            .reset_index(
                drop=True
            )
        )

        # --------------------------------------------------------
        # Validate
        # --------------------------------------------------------

        validate_output(
            df
        )

        # --------------------------------------------------------
        # Summary
        # --------------------------------------------------------

        summary = build_summary(
            df
        )

        # --------------------------------------------------------
        # Save records
        # --------------------------------------------------------

        df["observation_date"] = (
            df["observation_date"]
            .dt.strftime(
                "%Y-%m-%d"
            )
        )

        df["availability_date"] = (
            df["availability_date"]
            .dt.strftime(
                "%Y-%m-%d"
            )
        )

        # --------------------------------------------------------
        # Final deterministic order
        # --------------------------------------------------------

        df = (
            df
            .sort_values(
                [
                    "observation_date",
                    "indicator",
                ]
            )
            .reset_index(
                drop=True
            )
        )

        summary = (
            summary
            .sort_values(
                "indicator"
            )
            .reset_index(
                drop=True
            )
        )

        # --------------------------------------------------------
        # Write outputs
        # --------------------------------------------------------

        df.to_csv(
            OUTPUT_FILE,
            index=False
        )

        summary.to_csv(
            SUMMARY_FILE,
            index=False
        )

        # --------------------------------------------------------
        # Final report
        # --------------------------------------------------------

        print("")
        print("=" * 80)

        print(
            "LIQUIDITY HISTORICAL "
            "COLLECTION COMPLETE"
        )

        print("=" * 80)

        print(
            f"Total rows: "
            f"{len(df):,}"
        )

        print(
            f"Indicators: "
            f"{df['indicator'].nunique()}"
        )

        print(
            f"Observation range: "
            f"{df['observation_date'].min()} "
            f"-> "
            f"{df['observation_date'].max()}"
        )

        print("")
        print(
            "Rows by indicator:"
        )

        counts = (
            df
            .groupby(
                "indicator"
            )
            .size()
            .sort_index()
        )

        for indicator, count in counts.items():

            print(
                f"  {indicator:30s}"
                f"{count:>8,}"
            )

        print("")
        print(
            "Unit normalization:"
        )

        print(
            "  WRESBAL pre-2025-11-13: "
            "Billions -> Millions x1000"
        )

        print(
            "  WTREGEN pre-2025-11-13: "
            "Billions -> Millions x1000"
        )

        print(
            "  WRESBAL post-2025-11-13: "
            "Millions x1"
        )

        print(
            "  WTREGEN post-2025-11-13: "
            "Millions x1"
        )

        print("")
        print(
            "Required indicators:"
        )

        for series_id, meta in SERIES.items():

            indicator = meta[
                "indicator"
            ]

            count = int(
                (
                    df["indicator"] ==
                    indicator
                ).sum()
            )

            print(
                f"  {series_id:12s}"
                f"{indicator:30s}"
                f"{count:>8,}"
            )

        print("")
        print(
            "Output files:"
        )

        print(
            f"  {OUTPUT_FILE}"
        )

        print(
            f"  {SUMMARY_FILE}"
        )

        print("")
        print(
            "Research-only: TRUE"
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

        print("")
        print("=" * 80)

        print(
            "STATUS: PASS"
        )

        print("=" * 80)

    except Exception as exc:

        print("")
        print("=" * 80)

        print(
            "LIQUIDITY HISTORICAL "
            "COLLECTOR FAILED"
        )

        print("=" * 80)

        print(
            f"Error: {exc}"
        )

        print("=" * 80)
        print("")

        sys.exit(1)


# ================================================================
# ENTRY POINT
# ================================================================

if __name__ == "__main__":

    main()
