"""
COT Historical Collector v1
Research-only, PIT-safe collection for CFTC TFF Futures-Only
E-mini S&P 500.

Design:
- Source: CFTC Public Reporting Environment / TFF Futures-Only.
- Target: E-mini S&P 500 (CFTC code 13874A).
- Observation date: CFTC report date.
- Availability date: conservative 7-calendar-day proxy.
- No sentiment score.
- No trading signal.
- No Decision Engine integration.

Outputs:
    cot_historical_records_input_v1.csv
    cot_historical_collection_summary_v1.csv
"""

from __future__ import annotations

import io
import os
import sys

import pandas as pd
import requests


# ============================================================
# Configuration
# ============================================================

REPORT_NAME = "TFF Futures Only"

TARGET_CONTRACT = "E-MINI S&P 500"

TARGET_CODE = "13874A"

START_YEAR = int(
    os.getenv("COT_START_YEAR", "2006")
)

END_YEAR = int(
    os.getenv("COT_END_YEAR", "2026")
)

BASE_URL = (
    "https://publicreporting.cftc.gov/"
    "resource/gpe5-46if.csv"
)

SOURCE_URL = (
    "https://publicreporting.cftc.gov/"
    "stories/s/TFF-Futures-Only/98ig-3k9y/"
)

OUTPUT = "cot_historical_records_input_v1.csv"

SUMMARY = "cot_historical_collection_summary_v1.csv"


# ============================================================
# Fetch one year
# ============================================================

def fetch_year(year: int) -> pd.DataFrame:
    """
    Fetch one calendar year of CFTC TFF Futures-Only data
    for the target E-mini S&P 500 contract.
    """

    where = (
        f"report_date_as_yyyy_mm_dd between "
        f"'{year}-01-01T00:00:00' "
        f"and '{year}-12-31T23:59:59' "
        f"and cftc_contract_market_code='{TARGET_CODE}'"
    )

    params = {
        "$where": where,
        "$order": "report_date_as_yyyy_mm_dd ASC",
        "$limit": 5000,
    }

    response = requests.get(
        BASE_URL,
        params=params,
        timeout=60,
    )

    response.raise_for_status()

    text = response.text

    if not text.strip():
        return pd.DataFrame()

    return pd.read_csv(
        io.StringIO(text)
    )


# ============================================================
# Safe numeric conversion
# ============================================================

def numeric_column(
    df: pd.DataFrame,
    column: str,
) -> pd.Series:
    """
    Convert a source column to numeric safely.
    """

    if column not in df.columns:
        return pd.Series(
            [pd.NA] * len(df),
            index=df.index,
            dtype="Float64",
        )

    return pd.to_numeric(
        df[column],
        errors="coerce",
    )


# ============================================================
# Main
# ============================================================

def main() -> int:

    print(
        "Collecting CFTC TFF Futures-Only "
        f"{TARGET_CONTRACT} ({TARGET_CODE})"
    )

    print(
        f"Period: {START_YEAR}-{END_YEAR}"
    )

    frames = []

    # --------------------------------------------------------
    # Download data year by year
    # --------------------------------------------------------

    for year in range(
        START_YEAR,
        END_YEAR + 1,
    ):

        try:

            part = fetch_year(year)

            if not part.empty:
                frames.append(part)

            print(
                f"{year}: {len(part)} rows"
            )

        except Exception as exc:

            print(
                f"{year}: ERROR {exc}",
                file=sys.stderr,
            )

            return 1

    # --------------------------------------------------------
    # Ensure data exists
    # --------------------------------------------------------

    if not frames:

        raise RuntimeError(
            "No CFTC TFF Futures-Only records returned."
        )

    raw = pd.concat(
        frames,
        ignore_index=True,
    )

    # --------------------------------------------------------
    # Required CFTC columns
    #
    # IMPORTANT:
    # Current CFTC API uses:
    #
    # lev_money_positions_long
    # lev_money_positions_short
    # other_rept_positions_long
    # other_rept_positions_short
    #
    # NOT the older *_all variants.
    # --------------------------------------------------------

    required_columns = [

        "report_date_as_yyyy_mm_dd",

        "cftc_contract_market_code",

        "open_interest_all",

        "dealer_positions_long_all",

        "dealer_positions_short_all",

        "asset_mgr_positions_long",

        "asset_mgr_positions_short",

        "lev_money_positions_long",

        "lev_money_positions_short",

        "other_rept_positions_long",

        "other_rept_positions_short",

        "nonrept_positions_long_all",

        "nonrept_positions_short_all",
    ]

    missing = [
        column
        for column in required_columns
        if column not in raw.columns
    ]

    if missing:

        raise RuntimeError(
            "CFTC schema changed. "
            "Missing columns: "
            + ", ".join(missing)
        )

    # --------------------------------------------------------
    # Normalize contract code
    # --------------------------------------------------------

    raw[
        "cftc_contract_market_code"
    ] = (
        raw[
            "cftc_contract_market_code"
        ]
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------------
    # Keep only E-mini S&P 500
    # --------------------------------------------------------

    raw = raw[
        raw[
            "cftc_contract_market_code"
        ] == TARGET_CODE
    ].copy()

    if raw.empty:

        raise RuntimeError(
            "No records found for "
            f"CFTC contract code {TARGET_CODE}."
        )

    # --------------------------------------------------------
    # Observation date
    # --------------------------------------------------------

    raw[
        "observation_date"
    ] = pd.to_datetime(
        raw[
            "report_date_as_yyyy_mm_dd"
        ],
        errors="coerce",
    )

    if raw[
        "observation_date"
    ].isna().any():

        raise RuntimeError(
            "Invalid observation dates found."
        )

    # --------------------------------------------------------
    # Conservative availability date
    # --------------------------------------------------------

    raw[
        "availability_date"
    ] = (
        raw[
            "observation_date"
        ]
        + pd.to_timedelta(
            7,
            unit="D",
        )
    )

    # --------------------------------------------------------
    # Contract name
    # --------------------------------------------------------

    if "contract_market_name" in raw.columns:

        contract_name = (
            raw["contract_market_name"]
        )

    else:

        contract_name = pd.Series(
            [TARGET_CONTRACT] * len(raw),
            index=raw.index,
        )

    # --------------------------------------------------------
    # Build canonical output
    # --------------------------------------------------------

    out = pd.DataFrame({

        "contract_market_code":
            raw[
                "cftc_contract_market_code"
            ],

        "contract_name":
            contract_name.astype(str),

        "observation_date":
            raw[
                "observation_date"
            ].dt.strftime(
                "%Y-%m-%d"
            ),

        "availability_date":
            raw[
                "availability_date"
            ].dt.strftime(
                "%Y-%m-%d"
            ),

        "open_interest":
            numeric_column(
                raw,
                "open_interest_all",
            ),

        "dealer_long":
            numeric_column(
                raw,
                "dealer_positions_long_all",
            ),

        "dealer_short":
            numeric_column(
                raw,
                "dealer_positions_short_all",
            ),

        "asset_manager_long":
            numeric_column(
                raw,
                "asset_mgr_positions_long",
            ),

        "asset_manager_short":
            numeric_column(
                raw,
                "asset_mgr_positions_short",
            ),

        "leveraged_money_long":
            numeric_column(
                raw,
                "lev_money_positions_long",
            ),

        "leveraged_money_short":
            numeric_column(
                raw,
                "lev_money_positions_short",
            ),

        "other_reportables_long":
            numeric_column(
                raw,
                "other_rept_positions_long",
            ),

        "other_reportables_short":
            numeric_column(
                raw,
                "other_rept_positions_short",
            ),

        "nonreportable_long":
            numeric_column(
                raw,
                "nonrept_positions_long_all",
            ),

        "nonreportable_short":
            numeric_column(
                raw,
                "nonrept_positions_short_all",
            ),

        "source":
            "CFTC Public Reporting Environment",

        "source_url":
            SOURCE_URL,

        "availability_semantics":
            "conservative_7_calendar_day_proxy",

        "point_in_time_safe":
            True,
    })

    # ========================================================
    # Derived positioning metrics
    # ========================================================

    out[
        "asset_manager_net"
    ] = (
        out[
            "asset_manager_long"
        ]
        - out[
            "asset_manager_short"
        ]
    )

    out[
        "leveraged_money_net"
    ] = (
        out[
            "leveraged_money_long"
        ]
        - out[
            "leveraged_money_short"
        ]
    )

    out[
        "dealer_net"
    ] = (
        out[
            "dealer_long"
        ]
        - out[
            "dealer_short"
        ]
    )

    # ========================================================
    # Sort
    # ========================================================

    out = (
        out
        .sort_values(
            "observation_date"
        )
        .reset_index(drop=True)
    )

    # ========================================================
    # Duplicate check
    # ========================================================

    duplicate_count = int(
        out.duplicated(
            subset=[
                "contract_market_code",
                "observation_date",
            ]
        ).sum()
    )

    if duplicate_count != 0:

        raise AssertionError(
            "Duplicate contract/observation "
            f"rows detected: {duplicate_count}"
        )

    # ========================================================
    # PIT validation
    # ========================================================

    observation_dates = pd.to_datetime(
        out[
            "observation_date"
        ]
    )

    availability_dates = pd.to_datetime(
        out[
            "availability_date"
        ]
    )

    if not bool(
        (
            availability_dates
            > observation_dates
        ).all()
    ):

        raise AssertionError(
            "PIT validation failed: "
            "availability_date must be "
            "later than observation_date."
        )

    # ========================================================
    # PIT flag validation
    # ========================================================

    if not bool(
        out[
            "point_in_time_safe"
        ].all()
    ):

        raise AssertionError(
            "point_in_time_safe validation failed."
        )

    # ========================================================
    # Target contract validation
    # ========================================================

    if not bool(
        out[
            "contract_market_code"
        ]
        .astype(str)
        .eq(TARGET_CODE)
        .all()
    ):

        raise AssertionError(
            "Unexpected contract code detected."
        )

    # ========================================================
    # Date ordering validation
    # ========================================================

    if not observation_dates.is_monotonic_increasing:

        raise AssertionError(
            "Observation dates are not "
            "monotonically increasing."
        )

    # ========================================================
    # Save historical records
    # ========================================================

    out.to_csv(
        OUTPUT,
        index=False,
    )

    # ========================================================
    # Build summary
    # ========================================================

    summary = pd.DataFrame([{

        "report_name":
            REPORT_NAME,

        "target_contract":
            TARGET_CONTRACT,

        "target_code":
            TARGET_CODE,

        "start_year":
            START_YEAR,

        "end_year":
            END_YEAR,

        "records":
            len(out),

        "first_observation_date":
            out[
                "observation_date"
            ].min(),

        "last_observation_date":
            out[
                "observation_date"
            ].max(),

        "duplicate_contract_observation_rows":
            duplicate_count,

        "missing_open_interest":
            int(
                out[
                    "open_interest"
                ].isna().sum()
            ),

        "point_in_time_safe_all":
            bool(
                out[
                    "point_in_time_safe"
                ].all()
            ),

        "research_only":
            True,

        "decision_engine_ready":
            False,

        "sentiment_score_generated":
            False,
    }])

    # ========================================================
    # Save summary
    # ========================================================

    summary.to_csv(
        SUMMARY,
        index=False,
    )

    # ========================================================
    # Final console output
    # ========================================================

    print()
    print("=" * 70)
    print("COT HISTORICAL COLLECTOR V1")
    print("=" * 70)

    print(
        summary.to_string(
            index=False
        )
    )

    print("=" * 70)

    print(
        f"Output: {OUTPUT}"
    )

    print(
        f"Summary: {SUMMARY}"
    )

    print(
        "PIT validation: PASS"
    )

    print(
        "Duplicate validation: PASS"
    )

    print(
        "Target contract validation: PASS"
    )

    print(
        "Research-only: TRUE"
    )

    print(
        "Decision Engine ready: FALSE"
    )

    return 0


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    raise SystemExit(
        main()
    )
