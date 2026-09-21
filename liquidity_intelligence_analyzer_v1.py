"""
Liquidity Intelligence Analyzer v1

Research-only — No Trading Signal
No Forecast — No Decision Engine — No Liquidity Score

Purpose:
    Transform PIT-safe liquidity historical records into a daily
    research context containing:
        - latest available liquidity levels
        - 7D / 30D / 90D changes
        - 1Y changes
        - descriptive direction
        - SOFR/EFFR spread
        - descriptive net-liquidity proxy

PIT rule:
    A record is usable only when:
        availability_date <= asof_date

Important:
    availability_date is a research availability proxy.
    It is NOT an exact publication timestamp.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd


INPUT_FILE = os.getenv(
    "LIQUIDITY_INPUT_FILE",
    "liquidity_historical_records_input_v1.csv",
)

OUTPUT_FILE = os.getenv(
    "LIQUIDITY_OUTPUT_FILE",
    "liquidity_intelligence_research_v1.csv",
)

SUMMARY_FILE = os.getenv(
    "LIQUIDITY_SUMMARY_FILE",
    "liquidity_intelligence_summary_v1.csv",
)

AS_OF_DATE = os.getenv("LIQUIDITY_AS_OF_DATE", "").strip()

EXPECTED_INDICATORS = {
    "FED_TOTAL_ASSETS",
    "RESERVE_BALANCES",
    "TREASURY_GENERAL_ACCOUNT",
    "TREASURY_SECURITIES",
    "MBS",
    "ON_RRP",
    "SOFR",
    "EFFR",
}

MILLION_UNIT_INDICATORS = {
    "FED_TOTAL_ASSETS",
    "RESERVE_BALANCES",
    "TREASURY_GENERAL_ACCOUNT",
    "TREASURY_SECURITIES",
    "MBS",
}

RATE_INDICATORS = {
    "SOFR",
    "EFFR",
}

CHANGE_WINDOWS = {
    "7D": 7,
    "30D": 30,
    "90D": 90,
    "1Y": 365,
}


def fail(message: str) -> None:
    raise RuntimeError(f"ERROR: {message}")


def load_input(path: str) -> pd.DataFrame:
    if not Path(path).exists():
        fail(f"Input file not found: {path}")

    df = pd.read_csv(path)

    required = {
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
    }

    missing = required - set(df.columns)

    if missing:
        fail(f"Missing required columns: {sorted(missing)}")

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

    if df["observation_date"].isna().any():
        fail("Invalid observation_date values detected.")

    if df["availability_date"].isna().any():
        fail("Invalid availability_date values detected.")

    if df["actual"].isna().any():
        fail("Invalid actual values detected.")

    return df


def validate_input(df: pd.DataFrame) -> None:
    actual_indicators = set(df["indicator"].dropna().unique())

    missing = EXPECTED_INDICATORS - actual_indicators

    if missing:
        fail(f"Missing indicators: {sorted(missing)}")

    duplicates = df.duplicated(
        subset=[
            "indicator",
            "observation_date",
            "availability_date",
            "vintage",
        ]
    )

    if duplicates.any():
        fail(
            f"Duplicate indicator/date/vintage rows detected: "
            f"{int(duplicates.sum())}"
        )

    if (~df["point_in_time_safe"].astype(bool)).any():
        fail("Input contains point_in_time_safe=False records.")

    if df["revision_flag"].astype(bool).any():
        fail("Input contains revision_flag=True records.")

    if (~df["research_only"].astype(bool)).any():
        fail("Input contains research_only=False records.")

    if df["decision_engine_ready"].astype(bool).any():
        fail("Input contains decision_engine_ready=True records.")

    if df["trading_signal_generated"].astype(bool).any():
        fail("Input contains trading_signal_generated=True records.")

    if df["forecast_generated"].astype(bool).any():
        fail("Input contains forecast_generated=True records.")

    if df["liquidity_score_generated"].astype(bool).any():
        fail("Input contains liquidity_score_generated=True records.")

    invalid_pit = (
        df["availability_date"] < df["observation_date"]
    )

    if invalid_pit.any():
        fail(
            "Found records where availability_date precedes "
            "observation_date."
        )


def determine_asof(df: pd.DataFrame) -> pd.Timestamp:
    if AS_OF_DATE:
        asof = pd.Timestamp(AS_OF_DATE)
    else:
        asof = df["availability_date"].max().normalize()

    if pd.isna(asof):
        fail("Unable to determine as-of date.")

    return asof


def apply_pit_filter(
    df: pd.DataFrame,
    asof: pd.Timestamp,
) -> pd.DataFrame:
    """
    Critical PIT rule.

    Only information whose research availability date is on or
    before the requested as-of date is allowed.
    """

    result = df[
        df["availability_date"].dt.normalize() <= asof
    ].copy()

    if result.empty:
        fail(
            f"No PIT-safe records available on or before "
            f"{asof.date()}."
        )

    return result


def create_daily_calendar(
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:

    dates = pd.date_range(
        start=start_date,
        end=end_date,
        freq="D",
    )

    return pd.DataFrame(
        {
            "asof_date": dates,
        }
    )


def build_indicator_panel(
    pit_df: pd.DataFrame,
    calendar: pd.DataFrame,
) -> pd.DataFrame:
    """
    For each calendar date, select the latest observation that was
    already available as of that date.

    This is deliberately based on availability_date rather than
    observation_date.
    """

    result = calendar.copy()

    for indicator in sorted(EXPECTED_INDICATORS):

        sub = pit_df[
            pit_df["indicator"] == indicator
        ].copy()

        if sub.empty:
            continue

        sub = sub.sort_values("availability_date")

        # If multiple records have the same availability date,
        # retain the latest observation_date.
        sub = (
            sub.sort_values(
                [
                    "availability_date",
                    "observation_date",
                ]
            )
            .drop_duplicates(
                subset=["availability_date"],
                keep="last",
            )
        )

        sub = sub[
            [
                "availability_date",
                "observation_date",
                "actual",
            ]
        ].rename(
            columns={
                "actual": indicator,
                "observation_date":
                    f"{indicator}_observation_date",
            }
        )

        merged = pd.merge_asof(
            result.sort_values("asof_date"),
            sub.sort_values("availability_date"),
            left_on="asof_date",
            right_on="availability_date",
            direction="backward",
        )

        result = merged.drop(
            columns=["availability_date"],
            errors="ignore",
        )

    return result


def value_at_or_before(
    series: pd.Series,
    dates: pd.Series,
    target_date: pd.Timestamp,
) -> float:
    """
    Return the latest non-null value whose as-of date is <= target.
    """

    mask = (
        dates <= target_date
    ) & series.notna()

    if not mask.any():
        return np.nan

    idx = dates[mask].idxmax()

    return float(series.loc[idx])


def add_changes(
    panel: pd.DataFrame,
) -> pd.DataFrame:

    panel = panel.copy()

    for indicator in EXPECTED_INDICATORS:

        if indicator not in panel.columns:
            continue

        current = panel[indicator]

        for label, days in CHANGE_WINDOWS.items():

            absolute_changes = []
            percent_changes = []

            for idx in panel.index:

                current_value = current.loc[idx]

                if pd.isna(current_value):
                    absolute_changes.append(np.nan)
                    percent_changes.append(np.nan)
                    continue

                target_date = (
                    panel.loc[idx, "asof_date"]
                    - pd.Timedelta(days=days)
                )

                previous_value = value_at_or_before(
                    current,
                    panel["asof_date"],
                    target_date,
                )

                if pd.isna(previous_value):
                    absolute_changes.append(np.nan)
                    percent_changes.append(np.nan)
                    continue

                absolute_change = (
                    float(current_value)
                    - previous_value
                )

                absolute_changes.append(
                    absolute_change
                )

                if previous_value == 0:
                    percent_changes.append(np.nan)
                else:
                    percent_changes.append(
                        (
                            absolute_change
                            / abs(previous_value)
                        ) * 100.0
                    )

            panel[
                f"{indicator}_CHANGE_{label}"
            ] = absolute_changes

            panel[
                f"{indicator}_PCT_CHANGE_{label}"
            ] = percent_changes

    return panel


def add_direction_fields(
    panel: pd.DataFrame,
) -> pd.DataFrame:

    panel = panel.copy()

    direction_windows = {
        "30D": "30D",
        "90D": "90D",
        "1Y": "1Y",
    }

    for indicator in EXPECTED_INDICATORS:

        for label in direction_windows:

            change_col = (
                f"{indicator}_CHANGE_{label}"
            )

            if change_col not in panel.columns:
                continue

            values = panel[change_col]

            panel[
                f"{indicator}_DIRECTION_{label}"
            ] = np.select(
                [
                    values > 0,
                    values < 0,
                    values == 0,
                ],
                [
                    "RISING",
                    "FALLING",
                    "STABLE",
                ],
                default="INSUFFICIENT_DATA",
            )

    return panel


def add_rates_and_spreads(
    panel: pd.DataFrame,
) -> pd.DataFrame:

    panel = panel.copy()

    if (
        "SOFR" in panel.columns
        and "EFFR" in panel.columns
    ):
        panel["SOFR_EFFR_SPREAD_BPS"] = (
            panel["SOFR"] - panel["EFFR"]
        ) * 100.0

    return panel


def add_net_liquidity_proxy(
    panel: pd.DataFrame,
) -> pd.DataFrame:

    panel = panel.copy()

    required = {
        "FED_TOTAL_ASSETS",
        "TREASURY_GENERAL_ACCOUNT",
        "ON_RRP",
    }

    if not required.issubset(panel.columns):
        return panel

    # ON_RRP is in billions of USD.
    # H.4.1 balance-sheet series are in millions of USD.
    on_rrp_millions = panel["ON_RRP"] * 1000.0

    panel["ON_RRP_MILLIONS"] = on_rrp_millions

    panel["NET_LIQUIDITY_PROXY_MILLIONS"] = (
        panel["FED_TOTAL_ASSETS"]
        - panel["TREASURY_GENERAL_ACCOUNT"]
        - panel["ON_RRP_MILLIONS"]
    )

    return panel


def add_metadata(
    panel: pd.DataFrame,
    asof: pd.Timestamp,
) -> pd.DataFrame:

    panel = panel.copy()

    panel["research_only"] = True
    panel["decision_engine_ready"] = False
    panel["trading_signal_generated"] = False
    panel["forecast_generated"] = False
    panel["liquidity_score_generated"] = False

    panel["pit_rule"] = (
        "availability_date <= asof_date"
    )

    panel["availability_semantics"] = (
        "Source-specific research availability proxy; "
        "exact publication timestamp not represented."
    )

    panel["point_in_time_safe"] = True

    panel["analyzer_asof_limit"] = asof.strftime(
        "%Y-%m-%d"
    )

    return panel


def build_summary(
    panel: pd.DataFrame,
    asof: pd.Timestamp,
) -> pd.DataFrame:

    latest = panel.iloc[-1]

    rows: List[Dict] = []

    for indicator in sorted(EXPECTED_INDICATORS):

        observation_col = (
            f"{indicator}_observation_date"
        )

        value = latest.get(
            indicator,
            np.nan,
        )

        observation_date = latest.get(
            observation_col,
            pd.NaT,
        )

        row = {
            "asof_date": asof.strftime("%Y-%m-%d"),
            "indicator": indicator,
            "latest_value": value,
            "latest_observation_date": (
                observation_date.strftime("%Y-%m-%d")
                if pd.notna(observation_date)
                else None
            ),
            "research_only": True,
            "point_in_time_safe": True,
            "decision_engine_ready": False,
            "trading_signal_generated": False,
            "forecast_generated": False,
            "liquidity_score_generated": False,
        }

        rows.append(row)

    return pd.DataFrame(rows)


def validate_output(
    panel: pd.DataFrame,
    asof: pd.Timestamp,
) -> None:

    if panel.empty:
        fail("Analyzer output is empty.")

    if panel["asof_date"].max() != asof:
        fail(
            "Output does not end at requested as-of date."
        )

    if (
        panel["asof_date"].min()
        > asof
    ):
        fail(
            "Output start date is after requested as-of date."
        )

    if not panel["point_in_time_safe"].all():
        fail(
            "Output contains point_in_time_safe=False."
        )

    if not panel["research_only"].all():
        fail(
            "Output contains research_only=False."
        )

    if panel["decision_engine_ready"].any():
        fail(
            "Output contains decision_engine_ready=True."
        )

    if panel["trading_signal_generated"].any():
        fail(
            "Output contains trading signals."
        )

    if panel["forecast_generated"].any():
        fail(
            "Output contains forecasts."
        )

    if panel["liquidity_score_generated"].any():
        fail(
            "Output contains liquidity scores."
        )

    if (
        panel["asof_date"]
        .duplicated()
        .any()
    ):
        fail(
            "Duplicate as-of dates detected."
        )


def main() -> None:

    print("=" * 72)
    print("Liquidity Intelligence Analyzer v1")
    print("Research-only — No Trading Signal")
    print("No Forecast — No Decision Engine")
    print("No Liquidity Score")
    print("=" * 72)

    df = load_input(INPUT_FILE)

    print(f"Input rows: {len(df):,}")

    validate_input(df)

    asof = determine_asof(df)

    print(
        f"Analyzer as-of date: "
        f"{asof.strftime('%Y-%m-%d')}"
    )

    pit_df = apply_pit_filter(
        df,
        asof,
    )

    print(
        f"PIT-eligible rows: "
        f"{len(pit_df):,}"
    )

    start_date = pit_df[
        "availability_date"
    ].min().normalize()

    calendar = create_daily_calendar(
        start_date,
        asof,
    )

    print(
        f"Daily research calendar: "
        f"{len(calendar):,} days"
    )

    panel = build_indicator_panel(
        pit_df,
        calendar,
    )

    panel = add_changes(panel)

    panel = add_direction_fields(panel)

    panel = add_rates_and_spreads(panel)

    panel = add_net_liquidity_proxy(panel)

    panel = add_metadata(
        panel,
        asof,
    )

    validate_output(
        panel,
        asof,
    )

    summary = build_summary(
        panel,
        asof,
    )

    output_columns = [
        "asof_date",
    ]

    # Latest levels and observation dates.
    for indicator in sorted(EXPECTED_INDICATORS):
        output_columns.extend(
            [
                indicator,
                f"{indicator}_observation_date",
            ]
        )

    # Changes.
    for indicator in sorted(EXPECTED_INDICATORS):
        for label in CHANGE_WINDOWS:
            output_columns.extend(
                [
                    f"{indicator}_CHANGE_{label}",
                    f"{indicator}_PCT_CHANGE_{label}",
                ]
            )

    # Direction.
    for indicator in sorted(EXPECTED_INDICATORS):
        for label in [
            "30D",
            "90D",
            "1Y",
        ]:
            output_columns.append(
                f"{indicator}_DIRECTION_{label}"
            )

    # Derived research fields.
    output_columns.extend(
        [
            "ON_RRP_MILLIONS",
            "SOFR_EFFR_SPREAD_BPS",
            "NET_LIQUIDITY_PROXY_MILLIONS",
            "research_only",
            "decision_engine_ready",
            "trading_signal_generated",
            "forecast_generated",
            "liquidity_score_generated",
            "pit_rule",
            "availability_semantics",
            "point_in_time_safe",
            "analyzer_asof_limit",
        ]
    )

    output_columns = [
        c
        for c in output_columns
        if c in panel.columns
    ]

    output = panel[
        output_columns
    ].copy()

    output.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    summary.to_csv(
        SUMMARY_FILE,
        index=False,
    )

    print()
    print("PASS")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Summary: {SUMMARY_FILE}")
    print(
        f"Output rows: {len(output):,}"
    )
    print(
        f"Output date range: "
        f"{output['asof_date'].min().date()} "
        f"→ "
        f"{output['asof_date'].max().date()}"
    )

    latest = output.iloc[-1]

    print()
    print("Latest research context:")
    print(
        f"  AS_OF_DATE: "
        f"{latest['asof_date'].date()}"
    )

    for indicator in [
        "FED_TOTAL_ASSETS",
        "RESERVE_BALANCES",
        "TREASURY_GENERAL_ACCOUNT",
        "TREASURY_SECURITIES",
        "MBS",
        "ON_RRP",
        "SOFR",
        "EFFR",
    ]:
        if indicator in output.columns:
            print(
                f"  {indicator}: "
                f"{latest[indicator]}"
            )

    if "SOFR_EFFR_SPREAD_BPS" in output.columns:
        print(
            "  SOFR-EFFR spread (bps): "
            f"{latest['SOFR_EFFR_SPREAD_BPS']}"
        )

    if (
        "NET_LIQUIDITY_PROXY_MILLIONS"
        in output.columns
    ):
        print(
            "  Net liquidity proxy ($mm): "
            f"{latest['NET_LIQUIDITY_PROXY_MILLIONS']}"
        )

    print()
    print("Research-only validation:")
    print("  PIT-safe: PASS")
    print("  Research-only: PASS")
    print("  Decision Engine: DISABLED")
    print("  Trading signal: NONE")
    print("  Forecast: NONE")
    print("  Liquidity score: NONE")


if __name__ == "__main__":
    main()"""
Liquidity Intelligence Analyzer v1

Research-only — No Decision Engine

Purpose:
    Transform the PIT-safe Liquidity Historical Collector v1
    artifact into a descriptive liquidity intelligence dataset.

Design principles:
    - Point-in-time safe
    - No look-ahead
    - No trading signals
    - No forecasts
    - No Decision Engine integration
    - No composite liquidity score

Inputs:
    liquidity_historical_records_input_v1.csv

Outputs:
    liquidity_intelligence_research_v1.csv
    liquidity_intelligence_summary_v1.csv

Core indicators:
    FED_TOTAL_ASSETS
    RESERVE_BALANCES
    TREASURY_GENERAL_ACCOUNT
    TREASURY_SECURITIES
    MBS
    ON_RRP
    SOFR
    EFFR

Research calculations:
    - Latest PIT-safe levels
    - 7-day changes
    - 30-day changes
    - 90-day changes
    - 1-year changes
    - Percentage changes
    - Directional descriptive states
    - Liquidity balance-sheet proxy:
          FED_TOTAL_ASSETS
          - TGA
          - ON_RRP

Important:
    ON_RRP is originally reported in billions of U.S. dollars.
    H.4.1 balance-sheet series are reported in millions.
    ON_RRP is therefore converted to millions before the
    balance-sheet proxy is calculated.

The balance-sheet proxy is descriptive research data.
It is NOT a liquidity score and NOT a trading signal.
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd


# ================================================================
# CONFIGURATION
# ================================================================

INPUT_FILE = Path(
    "liquidity_historical_records_input_v1.csv"
)

OUTPUT_FILE = Path(
    "liquidity_intelligence_research_v1.csv"
)

SUMMARY_FILE = Path(
    "liquidity_intelligence_summary_v1.csv"
)

AS_OF_DATE = os.getenv(
    "LIQUIDITY_ANALYSIS_AS_OF_DATE",
    "2026-09-21"
)


# ================================================================
# REQUIRED INDICATORS
# ================================================================

REQUIRED_INDICATORS = {
    "FED_TOTAL_ASSETS",
    "RESERVE_BALANCES",
    "TREASURY_GENERAL_ACCOUNT",
    "TREASURY_SECURITIES",
    "MBS",
    "ON_RRP",
    "SOFR",
    "EFFR",
}


# ================================================================
# REQUIRED INPUT COLUMNS
# ================================================================

REQUIRED_COLUMNS = [
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
# OUTPUT COLUMNS
# ================================================================

OUTPUT_COLUMNS = [
    "asof_date",

    # ------------------------------------------------------------
    # Core levels
    # ------------------------------------------------------------

    "FED_TOTAL_ASSETS",
    "RESERVE_BALANCES",
    "TREASURY_GENERAL_ACCOUNT",
    "TREASURY_SECURITIES",
    "MBS",
    "ON_RRP",
    "SOFR",
    "EFFR",

    # ------------------------------------------------------------
    # Liquidity balance-sheet proxy
    # ------------------------------------------------------------

    "ON_RRP_MILLIONS",
    "BALANCE_SHEET_LIQUIDITY_PROXY",

    # ------------------------------------------------------------
    # Changes
    # ------------------------------------------------------------

    "FED_TOTAL_ASSETS_CHANGE_7D",
    "FED_TOTAL_ASSETS_CHANGE_30D",
    "FED_TOTAL_ASSETS_CHANGE_90D",
    "FED_TOTAL_ASSETS_CHANGE_1Y",

    "RESERVE_BALANCES_CHANGE_7D",
    "RESERVE_BALANCES_CHANGE_30D",
    "RESERVE_BALANCES_CHANGE_90D",
    "RESERVE_BALANCES_CHANGE_1Y",

    "TREASURY_GENERAL_ACCOUNT_CHANGE_7D",
    "TREASURY_GENERAL_ACCOUNT_CHANGE_30D",
    "TREASURY_GENERAL_ACCOUNT_CHANGE_90D",
    "TREASURY_GENERAL_ACCOUNT_CHANGE_1Y",

    "ON_RRP_CHANGE_7D",
    "ON_RRP_CHANGE_30D",
    "ON_RRP_CHANGE_90D",
    "ON_RRP_CHANGE_1Y",

    "SOFR_CHANGE_7D",
    "SOFR_CHANGE_30D",
    "SOFR_CHANGE_90D",
    "SOFR_CHANGE_1Y",

    "EFFR_CHANGE_7D",
    "EFFR_CHANGE_30D",
    "EFFR_CHANGE_90D",
    "EFFR_CHANGE_1Y",

    # ------------------------------------------------------------
    # Percentage changes
    # ------------------------------------------------------------

    "FED_TOTAL_ASSETS_PCT_30D",
    "FED_TOTAL_ASSETS_PCT_1Y",

    "RESERVE_BALANCES_PCT_30D",
    "RESERVE_BALANCES_PCT_1Y",

    "TREASURY_GENERAL_ACCOUNT_PCT_30D",
    "TREASURY_GENERAL_ACCOUNT_PCT_1Y",

    "ON_RRP_PCT_30D",
    "ON_RRP_PCT_1Y",

    # ------------------------------------------------------------
    # Descriptive directional states
    # ------------------------------------------------------------

    "FED_TOTAL_ASSETS_DIRECTION",
    "RESERVE_BALANCES_DIRECTION",
    "TREASURY_GENERAL_ACCOUNT_DIRECTION",
    "ON_RRP_DIRECTION",
    "BALANCE_SHEET_LIQUIDITY_PROXY_DIRECTION",

    # ------------------------------------------------------------
    # PIT / metadata
    # ------------------------------------------------------------

    "latest_fed_assets_observation_date",
    "latest_reserves_observation_date",
    "latest_tga_observation_date",
    "latest_treasury_observation_date",
    "latest_mbs_observation_date",
    "latest_rrp_observation_date",
    "latest_sofr_observation_date",
    "latest_effr_observation_date",

    "latest_fed_assets_availability_date",
    "latest_reserves_availability_date",
    "latest_tga_availability_date",
    "latest_treasury_availability_date",
    "latest_mbs_availability_date",
    "latest_rrp_availability_date",
    "latest_sofr_availability_date",
    "latest_effr_availability_date",

    "point_in_time_safe",

    "research_only",
    "decision_engine_ready",
    "trading_signal_generated",
    "forecast_generated",
    "liquidity_score_generated",
]


# ================================================================
# VALIDATION
# ================================================================

def validate_date(value):

    try:

        return pd.Timestamp(
            value
        )

    except Exception as exc:

        raise RuntimeError(
            "AS_OF_DATE must use YYYY-MM-DD format."
        ) from exc


def validate_input(df):

    print("")
    print("=" * 70)
    print("Liquidity Intelligence Input Validation")
    print("=" * 70)

    # ------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------

    missing_columns = [

        column

        for column in REQUIRED_COLUMNS

        if column not in df.columns

    ]

    if missing_columns:

        raise RuntimeError(
            f"Missing required columns: "
            f"{missing_columns}"
        )

    print("Schema: PASS")

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

    if (
        df["availability_date"]
        < df["observation_date"]
    ).any():

        raise RuntimeError(
            "Availability date earlier than "
            "observation date detected."
        )

    print("Dates: PASS")

    # ------------------------------------------------------------
    # Numeric
    # ------------------------------------------------------------

    df["actual"] = pd.to_numeric(
        df["actual"],
        errors="coerce"
    )

    if df["actual"].isna().any():

        raise RuntimeError(
            "Non-numeric or missing actual values detected."
        )

    if np.isinf(
        df["actual"]
    ).any():

        raise RuntimeError(
            "Infinite actual values detected."
        )

    print("Numeric values: PASS")

    # ------------------------------------------------------------
    # Indicators
    # ------------------------------------------------------------

    actual_indicators = set(
        df["indicator"]
        .dropna()
        .unique()
    )

    missing_indicators = (
        REQUIRED_INDICATORS
        -
        actual_indicators
    )

    if missing_indicators:

        raise RuntimeError(
            f"Missing required indicators: "
            f"{sorted(missing_indicators)}"
        )

    unexpected = (
        actual_indicators
        -
        REQUIRED_INDICATORS
    )

    if unexpected:

        raise RuntimeError(
            f"Unexpected indicators: "
            f"{sorted(unexpected)}"
        )

    print("Indicators: PASS — 8/8")

    # ------------------------------------------------------------
    # PIT
    # ------------------------------------------------------------

    pit = (
        df["point_in_time_safe"]
        .astype(str)
        .str.lower()
    )

    if not (
        pit == "true"
    ).all():

        raise RuntimeError(
            "Input contains records that are not PIT-safe."
        )

    print("PIT metadata: PASS")

    # ------------------------------------------------------------
    # Initial release
    # ------------------------------------------------------------

    vintage = (
        df["vintage"]
        .astype(str)
    )

    if not (
        vintage == "initial_release"
    ).all():

        raise RuntimeError(
            "Input contains non-initial-release observations."
        )

    print("Initial release: PASS")

    # ------------------------------------------------------------
    # Research-only
    # ------------------------------------------------------------

    research = (
        df["research_only"]
        .astype(str)
        .str.lower()
    )

    if not (
        research == "true"
    ).all():

        raise RuntimeError(
            "Input contains non-research-only records."
        )

    print("Research-only metadata: PASS")

    # ------------------------------------------------------------
    # Decision Engine
    # ------------------------------------------------------------

    decision = (
        df["decision_engine_ready"]
        .astype(str)
        .str.lower()
    )

    if not (
        decision == "false"
    ).all():

        raise RuntimeError(
            "Decision Engine flag detected."
        )

    print("Decision Engine: FALSE")

    # ------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------

    signal = (
        df["trading_signal_generated"]
        .astype(str)
        .str.lower()
    )

    if not (
        signal == "false"
    ).all():

        raise RuntimeError(
            "Trading signal detected."
        )

    print("Trading signal: FALSE")

    # ------------------------------------------------------------
    # Forecast
    # ------------------------------------------------------------

    forecast = (
        df["forecast_generated"]
        .astype(str)
        .str.lower()
    )

    if not (
        forecast == "false"
    ).all():

        raise RuntimeError(
            "Forecast flag detected."
        )

    print("Forecast: FALSE")

    # ------------------------------------------------------------
    # Liquidity score
    # ------------------------------------------------------------

    score = (
        df["liquidity_score_generated"]
        .astype(str)
        .str.lower()
    )

    if not (
        score == "false"
    ).all():

        raise RuntimeError(
            "Liquidity score detected in input."
        )

    print("Liquidity score: FALSE")

    print("")
    print("Input validation: PASS")


# ================================================================
# PIT FILTER
# ================================================================

def apply_pit_filter(
    df,
    asof_date
):

    """
    Only observations whose availability_date is on or
    before the analysis date may be used.

    This is the primary anti-look-ahead rule.
    """

    pit_df = df[
        df["availability_date"]
        <=
        asof_date
    ].copy()

    if pit_df.empty:

        raise RuntimeError(
            "No PIT-safe observations available "
            f"as of {asof_date.date()}."
        )

    return pit_df


# ================================================================
# LATEST OBSERVATION
# ================================================================

def latest_observation(
    df,
    indicator
):

    subset = df[
        df["indicator"]
        ==
        indicator
    ].copy()

    if subset.empty:

        return None

    subset = subset.sort_values(
        [
            "observation_date",
            "availability_date",
        ]
    )

    return subset.iloc[-1]


# ================================================================
# VALUE AT LOOKBACK
# ================================================================

def value_before_or_at(
    df,
    indicator,
    target_date
):

    subset = df[
        (
            df["indicator"]
            ==
            indicator
        )
        &
        (
            df["observation_date"]
            <=
            target_date
        )
    ].copy()

    if subset.empty:

        return np.nan

    subset = subset.sort_values(
        [
            "observation_date",
            "availability_date",
        ]
    )

    return float(
        subset.iloc[-1]["actual"]
    )


# ================================================================
# CHANGE
# ================================================================

def calculate_change(
    current,
    previous
):

    if (
        pd.isna(current)
        or
        pd.isna(previous)
    ):

        return np.nan

    return float(
        current
        -
        previous
    )


# ================================================================
# PERCENTAGE CHANGE
# ================================================================

def calculate_pct_change(
    current,
    previous
):

    if (
        pd.isna(current)
        or
        pd.isna(previous)
    ):

        return np.nan

    if previous == 0:

        return np.nan

    return float(
        (
            current
            -
            previous
        )
        /
        abs(previous)
        *
        100.0
    )


# ================================================================
# DIRECTION
# ================================================================

def direction_from_change(
    change
):

    if pd.isna(change):

        return "INSUFFICIENT_DATA"

    if change > 0:

        return "RISING"

    if change < 0:

        return "FALLING"

    return "FLAT"


# ================================================================
# BUILD ANALYSIS
# ================================================================

def build_analysis(
    df,
    asof_date
):

    # ------------------------------------------------------------
    # PIT FILTER
    # ------------------------------------------------------------

    pit_df = apply_pit_filter(
        df,
        asof_date
    )

    # ------------------------------------------------------------
    # Latest observations
    # ------------------------------------------------------------

    latest = {}

    for indicator in REQUIRED_INDICATORS:

        row = latest_observation(
            pit_df,
            indicator
        )

        if row is None:

            raise RuntimeError(
                f"No PIT-safe observation for "
                f"{indicator} as of "
                f"{asof_date.date()}."
            )

        latest[indicator] = row

    # ------------------------------------------------------------
    # Current values
    # ------------------------------------------------------------

    current = {

        indicator:
            float(
                latest[indicator]["actual"]
            )

        for indicator in REQUIRED_INDICATORS

    }

    # ------------------------------------------------------------
    # Observation dates
    # ------------------------------------------------------------

    observation_dates = {

        indicator:
            latest[indicator][
                "observation_date"
            ].strftime("%Y-%m-%d")

        for indicator in REQUIRED_INDICATORS

    }

    availability_dates = {

        indicator:
            latest[indicator][
                "availability_date"
            ].strftime("%Y-%m-%d")

        for indicator in REQUIRED_INDICATORS

    }

    # ------------------------------------------------------------
    # ON RRP unit conversion
    #
    # Original:
    # Billions USD
    #
    # Balance-sheet series:
    # Millions USD
    #
    # Therefore:
    # billions * 1000 = millions
    # ------------------------------------------------------------

    on_rrp_millions = (
        current["ON_RRP"]
        *
        1000.0
    )

    # ------------------------------------------------------------
    # Balance-sheet liquidity proxy
    #
    # Descriptive only:
    #
    # Fed assets
    # - TGA
    # - ON RRP
    #
    # No score.
    # No signal.
    # No forecast.
    # ------------------------------------------------------------

    balance_sheet_proxy = (

        current["FED_TOTAL_ASSETS"]

        -

        current["TREASURY_GENERAL_ACCOUNT"]

        -

        on_rrp_millions

    )

    # ------------------------------------------------------------
    # Lookback dates
    # ------------------------------------------------------------

    date_7d = (
        asof_date
        -
        pd.Timedelta(days=7)
    )

    date_30d = (
        asof_date
        -
        pd.Timedelta(days=30)
    )

    date_90d = (
        asof_date
        -
        pd.Timedelta(days=90)
    )

    date_1y = (
        asof_date
        -
        pd.Timedelta(days=365)
    )

    # ------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------

    def changes_for(indicator):

        current_value = current[indicator]

        v7 = value_before_or_at(
            pit_df,
            indicator,
            date_7d
        )

        v30 = value_before_or_at(
            pit_df,
            indicator,
            date_30d
        )

        v90 = value_before_or_at(
            pit_df,
            indicator,
            date_90d
        )

        v1y = value_before_or_at(
            pit_df,
            indicator,
            date_1y
        )

        return {

            "7D":
                calculate_change(
                    current_value,
                    v7
                ),

            "30D":
                calculate_change(
                    current_value,
                    v30
                ),

            "90D":
                calculate_change(
                    current_value,
                    v90
                ),

            "1Y":
                calculate_change(
                    current_value,
                    v1y
                ),

            "PCT_30D":
                calculate_pct_change(
                    current_value,
                    v30
                ),

            "PCT_1Y":
                calculate_pct_change(
                    current_value,
                    v1y
                ),
        }

    # ------------------------------------------------------------
    # Calculate changes
    # ------------------------------------------------------------

    assets = changes_for(
        "FED_TOTAL_ASSETS"
    )

    reserves = changes_for(
        "RESERVE_BALANCES"
    )

    tga = changes_for(
        "TREASURY_GENERAL_ACCOUNT"
    )

    rrp = changes_for(
        "ON_RRP"
    )

    sofr = changes_for(
        "SOFR"
    )

    effr = changes_for(
        "EFFR"
    )

    # ------------------------------------------------------------
    # Balance-sheet proxy historical values
    # ------------------------------------------------------------

    proxy_history = []

    # We calculate the proxy only on dates where all three
    # required components have a PIT-safe observation.

    for date in sorted(
        pit_df["observation_date"]
        .unique()
    ):

        date = pd.Timestamp(date)

        assets_value = value_before_or_at(
            pit_df,
            "FED_TOTAL_ASSETS",
            date
        )

        tga_value = value_before_or_at(
            pit_df,
            "TREASURY_GENERAL_ACCOUNT",
            date
        )

        rrp_value = value_before_or_at(
            pit_df,
            "ON_RRP",
            date
        )

        if (
            pd.isna(assets_value)
            or
            pd.isna(tga_value)
            or
            pd.isna(rrp_value)
        ):

            continue

        proxy_history.append(
            {
                "date": date,
                "value":
                    assets_value
                    -
                    tga_value
                    -
                    rrp_value * 1000.0,
            }
        )

    proxy_history_df = pd.DataFrame(
        proxy_history
    )

    if proxy_history_df.empty:

        proxy_change_30d = np.nan

    else:

        proxy_current = float(
            proxy_history_df.iloc[-1]["value"]
        )

        proxy_previous = proxy_history_df[
            proxy_history_df["date"]
            <=
            date_30d
        ]

        if proxy_previous.empty:

            proxy_change_30d = np.nan

        else:

            proxy_30d = float(
                proxy_previous.iloc[-1]["value"]
            )

            proxy_change_30d = calculate_change(
                proxy_current,
                proxy_30d
            )

    # ------------------------------------------------------------
    # Build output row
    # ------------------------------------------------------------

    row = {

        "asof_date":
            asof_date.strftime(
                "%Y-%m-%d"
            ),

        # --------------------------------------------------------
        # Levels
        # --------------------------------------------------------

        "FED_TOTAL_ASSETS":
            current["FED_TOTAL_ASSETS"],

        "RESERVE_BALANCES":
            current["RESERVE_BALANCES"],

        "TREASURY_GENERAL_ACCOUNT":
            current["TREASURY_GENERAL_ACCOUNT"],

        "TREASURY_SECURITIES":
            current["TREASURY_SECURITIES"],

        "MBS":
            current["MBS"],

        "ON_RRP":
            current["ON_RRP"],

        "SOFR":
            current["SOFR"],

        "EFFR":
            current["EFFR"],

        "ON_RRP_MILLIONS":
            on_rrp_millions,

        "BALANCE_SHEET_LIQUIDITY_PROXY":
            balance_sheet_proxy,

        # --------------------------------------------------------
        # Changes
        # --------------------------------------------------------

        "FED_TOTAL_ASSETS_CHANGE_7D":
            assets["7D"],

        "FED_TOTAL_ASSETS_CHANGE_30D":
            assets["30D"],

        "FED_TOTAL_ASSETS_CHANGE_90D":
            assets["90D"],

        "FED_TOTAL_ASSETS_CHANGE_1Y":
            assets["1Y"],

        "RESERVE_BALANCES_CHANGE_7D":
            reserves["7D"],

        "RESERVE_BALANCES_CHANGE_30D":
            reserves["30D"],

        "RESERVE_BALANCES_CHANGE_90D":
            reserves["90D"],

        "RESERVE_BALANCES_CHANGE_1Y":
            reserves["1Y"],

        "TREASURY_GENERAL_ACCOUNT_CHANGE_7D":
            tga["7D"],

        "TREASURY_GENERAL_ACCOUNT_CHANGE_30D":
            tga["30D"],

        "TREASURY_GENERAL_ACCOUNT_CHANGE_90D":
            tga["90D"],

        "TREASURY_GENERAL_ACCOUNT_CHANGE_1Y":
            tga["1Y"],

        "ON_RRP_CHANGE_7D":
            rrp["7D"],

        "ON_RRP_CHANGE_30D":
            rrp["30D"],

        "ON_RRP_CHANGE_90D":
            rrp["90D"],

        "ON_RRP_CHANGE_1Y":
            rrp["1Y"],

        "SOFR_CHANGE_7D":
            sofr["7D"],

        "SOFR_CHANGE_30D":
            sofr["30D"],

        "SOFR_CHANGE_90D":
            sofr["90D"],

        "SOFR_CHANGE_1Y":
            sofr["1Y"],

        "EFFR_CHANGE_7D":
            effr["7D"],

        "EFFR_CHANGE_30D":
            effr["30D"],

        "EFFR_CHANGE_90D":
            effr["90D"],

        "EFFR_CHANGE_1Y":
            effr["1Y"],

        # --------------------------------------------------------
        # Percent changes
        # --------------------------------------------------------

        "FED_TOTAL_ASSETS_PCT_30D":
            assets["PCT_30D"],

        "FED_TOTAL_ASSETS_PCT_1Y":
            assets["PCT_1Y"],

        "RESERVE_BALANCES_PCT_30D":
            reserves["PCT_30D"],

        "RESERVE_BALANCES_PCT_1Y":
            reserves["PCT_1Y"],

        "TREASURY_GENERAL_ACCOUNT_PCT_30D":
            tga["PCT_30D"],

        "TREASURY_GENERAL_ACCOUNT_PCT_1Y":
            tga["PCT_1Y"],

        "ON_RRP_PCT_30D":
            rrp["PCT_30D"],

        "ON_RRP_PCT_1Y":
            rrp["PCT_1Y"],

        # --------------------------------------------------------
        # Directions
        # --------------------------------------------------------

        "FED_TOTAL_ASSETS_DIRECTION":
            direction_from_change(
                assets["30D"]
            ),

        "RESERVE_BALANCES_DIRECTION":
            direction_from_change(
                reserves["30D"]
            ),

        "TREASURY_GENERAL_ACCOUNT_DIRECTION":
            direction_from_change(
                tga["30D"]
            ),

        "ON_RRP_DIRECTION":
            direction_from_change(
                rrp["30D"]
            ),

        "BALANCE_SHEET_LIQUIDITY_PROXY_DIRECTION":
            direction_from_change(
                proxy_change_30d
            ),

        # --------------------------------------------------------
        # Observation dates
        # --------------------------------------------------------

        "latest_fed_assets_observation_date":
            observation_dates["FED_TOTAL_ASSETS"],

        "latest_reserves_observation_date":
            observation_dates["RESERVE_BALANCES"],

        "latest_tga_observation_date":
            observation_dates["TREASURY_GENERAL_ACCOUNT"],

        "latest_treasury_observation_date":
            observation_dates["TREASURY_SECURITIES"],

        "latest_mbs_observation_date":
            observation_dates["MBS"],

        "latest_rrp_observation_date":
            observation_dates["ON_RRP"],

        "latest_sofr_observation_date":
            observation_dates["SOFR"],

        "latest_effr_observation_date":
            observation_dates["EFFR"],

        # --------------------------------------------------------
        # Availability dates
        # --------------------------------------------------------

        "latest_fed_assets_availability_date":
            availability_dates["FED_TOTAL_ASSETS"],

        "latest_reserves_availability_date":
            availability_dates["RESERVE_BALANCES"],

        "latest_tga_availability_date":
            availability_dates["TREASURY_GENERAL_ACCOUNT"],

        "latest_treasury_availability_date":
            availability_dates["TREASURY_SECURITIES"],

        "latest_mbs_availability_date":
            availability_dates["MBS"],

        "latest_rrp_availability_date":
            availability_dates["ON_RRP"],

        "latest_sofr_availability_date":
            availability_dates["SOFR"],

        "latest_effr_availability_date":
            availability_dates["EFFR"],

        # --------------------------------------------------------
        # Safety flags
        # --------------------------------------------------------

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

    return pd.DataFrame(
        [row]
    )


# ================================================================
# SUMMARY
# ================================================================

def build_summary(
    analysis
):

    row = analysis.iloc[0]

    summary = {

        "asof_date":
            row["asof_date"],

        "fed_total_assets":
            row["FED_TOTAL_ASSETS"],

        "reserve_balances":
            row["RESERVE_BALANCES"],

        "treasury_general_account":
            row["TREASURY_GENERAL_ACCOUNT"],

        "treasury_securities":
            row["TREASURY_SECURITIES"],

        "mbs":
            row["MBS"],

        "on_rrp":
            row["ON_RRP"],

        "sofr":
            row["SOFR"],

        "effr":
            row["EFFR"],

        "balance_sheet_liquidity_proxy":
            row["BALANCE_SHEET_LIQUIDITY_PROXY"],

        "fed_total_assets_change_30d":
            row["FED_TOTAL_ASSETS_CHANGE_30D"],

        "fed_total_assets_change_1y":
            row["FED_TOTAL_ASSETS_CHANGE_1Y"],

        "reserve_balances_change_30d":
            row["RESERVE_BALANCES_CHANGE_30D"],

        "reserve_balances_change_1y":
            row["RESERVE_BALANCES_CHANGE_1Y"],

        "tga_change_30d":
            row["TREASURY_GENERAL_ACCOUNT_CHANGE_30D"],

        "tga_change_1y":
            row["TREASURY_GENERAL_ACCOUNT_CHANGE_1Y"],

        "on_rrp_change_30d":
            row["ON_RRP_CHANGE_30D"],

        "on_rrp_change_1y":
            row["ON_RRP_CHANGE_1Y"],

        "balance_sheet_proxy_direction":
            row[
                "BALANCE_SHEET_LIQUIDITY_PROXY_DIRECTION"
            ],

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

    return pd.DataFrame(
        [summary]
    )


# ================================================================
# OUTPUT VALIDATION
# ================================================================

def validate_output(
    analysis
):

    print("")
    print("=" * 70)
    print("Liquidity Intelligence Output Validation")
    print("=" * 70)

    # ------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------

    missing = [

        column

        for column in OUTPUT_COLUMNS

        if column not in analysis.columns

    ]

    if missing:

        raise RuntimeError(
            f"Missing output columns: {missing}"
        )

    print("Schema: PASS")

    # ------------------------------------------------------------
    # Single as-of row
    # ------------------------------------------------------------

    if len(analysis) != 1:

        raise RuntimeError(
            "Expected exactly one analysis row."
        )

    print("As-of snapshot: PASS")

    # ------------------------------------------------------------
    # PIT
    # ------------------------------------------------------------

    if not bool(
        analysis.iloc[0]["point_in_time_safe"]
    ):

        raise RuntimeError(
            "Output is not PIT-safe."
        )

    print("PIT safety: PASS")

    # ------------------------------------------------------------
    # Research only
    # ------------------------------------------------------------

    if not bool(
        analysis.iloc[0]["research_only"]
    ):

        raise RuntimeError(
            "research_only must be True."
        )

    print("Research-only: PASS")

    # ------------------------------------------------------------
    # No Decision Engine
    # ------------------------------------------------------------

    if bool(
        analysis.iloc[0]["decision_engine_ready"]
    ):

        raise RuntimeError(
            "Decision Engine flag detected."
        )

    print("Decision Engine: FALSE")

    # ------------------------------------------------------------
    # No signals
    # ------------------------------------------------------------

    if bool(
        analysis.iloc[0]["trading_signal_generated"]
    ):

        raise RuntimeError(
            "Trading signal detected."
        )

    print("Trading signal: FALSE")

    # ------------------------------------------------------------
    # No forecast
    # ------------------------------------------------------------

    if bool(
        analysis.iloc[0]["forecast_generated"]
    ):

        raise RuntimeError(
            "Forecast detected."
        )

    print("Forecast: FALSE")

    # ------------------------------------------------------------
    # No score
    # ------------------------------------------------------------

    if bool(
        analysis.iloc[0]["liquidity_score_generated"]
    ):

        raise RuntimeError(
            "Liquidity score detected."
        )

    print("Liquidity score: FALSE")

    print("")
    print("Output validation: PASS")


# ================================================================
# MAIN
# ================================================================

def main():

    try:

        print("")
        print("=" * 70)
        print("Liquidity Intelligence Analyzer v1")
        print("Research-only — No Decision Engine")
        print("=" * 70)

        # --------------------------------------------------------
        # Date
        # --------------------------------------------------------

        asof_date = validate_date(
            AS_OF_DATE
        )

        print(
            f"As-of date: {asof_date.date()}"
        )

        # --------------------------------------------------------
        # Input
        # --------------------------------------------------------

        if not INPUT_FILE.exists():

            raise RuntimeError(
                f"Input file not found: "
                f"{INPUT_FILE}"
            )

        df = pd.read_csv(
            INPUT_FILE
        )

        print(
            f"Input rows: {len(df):,}"
        )

        # --------------------------------------------------------
        # Validation
        # --------------------------------------------------------

        validate_input(
            df
        )

        # --------------------------------------------------------
        # Analysis
        # --------------------------------------------------------

        analysis = build_analysis(
            df,
            asof_date
        )

        # --------------------------------------------------------
        # Exact output schema
        # --------------------------------------------------------

        analysis = analysis[
            OUTPUT_COLUMNS
        ]

        # --------------------------------------------------------
        # Validation
        # --------------------------------------------------------

        validate_output(
            analysis
        )

        # --------------------------------------------------------
        # Summary
        # --------------------------------------------------------

        summary = build_summary(
            analysis
        )

        # --------------------------------------------------------
        # Save
        # --------------------------------------------------------

        analysis.to_csv(
            OUTPUT_FILE,
            index=False
        )

        summary.to_csv(
            SUMMARY_FILE,
            index=False
        )

        # --------------------------------------------------------
        # Report
        # --------------------------------------------------------

        row = analysis.iloc[0]

        print("")
        print("=" * 70)
        print("LIQUIDITY INTELLIGENCE v1 COMPLETE")
        print("=" * 70)

        print(
            f"As-of date: "
            f"{row['asof_date']}"
        )

        print("")
        print("Latest PIT-safe levels:")

        print(
            f"  Fed Total Assets: "
            f"{row['FED_TOTAL_ASSETS']:,.2f}"
        )

        print(
            f"  Reserve Balances: "
            f"{row['RESERVE_BALANCES']:,.2f}"
        )

        print(
            f"  TGA: "
            f"{row['TREASURY_GENERAL_ACCOUNT']:,.2f}"
        )

        print(
            f"  Treasury Securities: "
            f"{row['TREASURY_SECURITIES']:,.2f}"
        )

        print(
            f"  MBS: "
            f"{row['MBS']:,.2f}"
        )

        print(
            f"  ON RRP: "
            f"{row['ON_RRP']:,.2f}"
        )

        print(
            f"  SOFR: "
            f"{row['SOFR']:,.4f}"
        )

        print(
            f"  EFFR: "
            f"{row['EFFR']:,.4f}"
        )

        print("")
        print(
            "Balance-sheet liquidity proxy: "
            f"{row['BALANCE_SHEET_LIQUIDITY_PROXY']:,.2f} "
            "million USD"
        )

        print("")
        print("30-day directional states:")

        print(
            f"  Fed Assets: "
            f"{row['FED_TOTAL_ASSETS_DIRECTION']}"
        )

        print(
            f"  Reserves: "
            f"{row['RESERVE_BALANCES_DIRECTION']}"
        )

        print(
            f"  TGA: "
            f"{row['TREASURY_GENERAL_ACCOUNT_DIRECTION']}"
        )

        print(
            f"  ON RRP: "
            f"{row['ON_RRP_DIRECTION']}"
        )

        print(
            f"  Liquidity Proxy: "
            f"{row['BALANCE_SHEET_LIQUIDITY_PROXY_DIRECTION']}"
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
        print("=" * 70)
        print("STATUS: PASS")
        print("=" * 70)

    except Exception as exc:

        print("")
        print("=" * 70)
        print("LIQUIDITY INTELLIGENCE ANALYZER FAILED")
        print("=" * 70)
        print(
            f"Error: {exc}"
        )
        print("=" * 70)
        print("")

        sys.exit(1)


if __name__ == "__main__":

    main()
