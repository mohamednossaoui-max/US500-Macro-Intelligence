"""
Liquidity Intelligence Analyzer v1

Research-only — No Trading Signal
No Forecast — No Decision Engine — No Liquidity Score

Purpose:
    Transform PIT-safe liquidity historical records into a daily
    descriptive liquidity intelligence dataset.

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


# ============================================================
# Configuration
# ============================================================

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

AS_OF_DATE = os.getenv(
    "LIQUIDITY_AS_OF_DATE",
    "",
).strip()


# ============================================================
# Expected indicators
# ============================================================

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


# ============================================================
# Change windows
# ============================================================

CHANGE_WINDOWS = {
    "7D": 7,
    "30D": 30,
    "90D": 90,
    "1Y": 365,
}


# ============================================================
# Utility
# ============================================================

def fail(message: str) -> None:
    raise RuntimeError(f"ERROR: {message}")


# ============================================================
# Load input
# ============================================================

def load_input(path: str) -> pd.DataFrame:

    if not Path(path).exists():
        fail(f"Input file not found: {path}")

    df = pd.read_csv(path)

    required_columns = {
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

    missing = required_columns - set(df.columns)

    if missing:
        fail(
            f"Missing required columns: {sorted(missing)}"
        )

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
        fail(
            "Invalid observation_date values detected."
        )

    if df["availability_date"].isna().any():
        fail(
            "Invalid availability_date values detected."
        )

    if df["actual"].isna().any():
        fail(
            "Invalid actual values detected."
        )

    return df


# ============================================================
# Validate input
# ============================================================

def validate_input(df: pd.DataFrame) -> None:

    actual_indicators = set(
        df["indicator"]
        .dropna()
        .unique()
    )

    missing = EXPECTED_INDICATORS - actual_indicators

    if missing:
        fail(
            f"Missing indicators: {sorted(missing)}"
        )

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
            "Duplicate indicator/date/vintage rows detected: "
            f"{int(duplicates.sum())}"
        )

    if (~df["point_in_time_safe"].astype(bool)).any():
        fail(
            "Input contains point_in_time_safe=False records."
        )

    if df["revision_flag"].astype(bool).any():
        fail(
            "Input contains revision_flag=True records."
        )

    if (~df["research_only"].astype(bool)).any():
        fail(
            "Input contains research_only=False records."
        )

    if df["decision_engine_ready"].astype(bool).any():
        fail(
            "Input contains decision_engine_ready=True records."
        )

    if df["trading_signal_generated"].astype(bool).any():
        fail(
            "Input contains trading_signal_generated=True records."
        )

    if df["forecast_generated"].astype(bool).any():
        fail(
            "Input contains forecast_generated=True records."
        )

    if df["liquidity_score_generated"].astype(bool).any():
        fail(
            "Input contains liquidity_score_generated=True records."
        )

    invalid_pit = (
        df["availability_date"]
        < df["observation_date"]
    )

    if invalid_pit.any():
        fail(
            "Found records where availability_date "
            "precedes observation_date."
        )


# ============================================================
# Determine as-of date
# ============================================================

def determine_asof(
    df: pd.DataFrame,
) -> pd.Timestamp:

    if AS_OF_DATE:

        asof = pd.Timestamp(
            AS_OF_DATE
        )

    else:

        asof = (
            df["availability_date"]
            .max()
            .normalize()
        )

    if pd.isna(asof):
        fail(
            "Unable to determine as-of date."
        )

    return asof


# ============================================================
# PIT filter
# ============================================================

def apply_pit_filter(
    df: pd.DataFrame,
    asof: pd.Timestamp,
) -> pd.DataFrame:

    """
    Critical PIT rule:

        availability_date <= asof_date

    observation_date alone must NOT be used to determine
    whether information was available.
    """

    result = df[
        df["availability_date"]
        .dt.normalize()
        <= asof
    ].copy()

    if result.empty:
        fail(
            "No PIT-safe records available on or before "
            f"{asof.date()}."
        )

    return result


# ============================================================
# Daily calendar
# ============================================================

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


# ============================================================
# Build PIT daily panel
# ============================================================

def build_indicator_panel(
    pit_df: pd.DataFrame,
    calendar: pd.DataFrame,
) -> pd.DataFrame:

    """
    For each as-of date, select the latest observation that
    was already available by that date.

    This uses availability_date, not observation_date.
    """

    result = calendar.copy()

    for indicator in sorted(
        EXPECTED_INDICATORS
    ):

        sub = pit_df[
            pit_df["indicator"]
            == indicator
        ].copy()

        if sub.empty:
            continue

        sub = sub.sort_values(
            [
                "availability_date",
                "observation_date",
            ]
        )

        sub = (
            sub
            .drop_duplicates(
                subset=[
                    "availability_date"
                ],
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

        result = pd.merge_asof(
            result.sort_values(
                "asof_date"
            ),
            sub.sort_values(
                "availability_date"
            ),
            left_on="asof_date",
            right_on="availability_date",
            direction="backward",
        )

        result = result.drop(
            columns=[
                "availability_date"
            ],
            errors="ignore",
        )

    return result


# ============================================================
# Historical value helper
# ============================================================

def value_at_or_before(
    series: pd.Series,
    dates: pd.Series,
    target_date: pd.Timestamp,
) -> float:

    mask = (
        (dates <= target_date)
        & series.notna()
    )

    if not mask.any():
        return np.nan

    valid_dates = dates[mask]

    idx = valid_dates.idxmax()

    return float(
        series.loc[idx]
    )


# ============================================================
# Add changes
# ============================================================

def add_changes(
    panel: pd.DataFrame,
) -> pd.DataFrame:

    panel = panel.copy()

    for indicator in sorted(
        EXPECTED_INDICATORS
    ):

        if indicator not in panel.columns:
            continue

        current = panel[indicator]

        for label, days in CHANGE_WINDOWS.items():

            absolute_changes = []
            percent_changes = []

            for idx in panel.index:

                current_value = (
                    current.loc[idx]
                )

                if pd.isna(
                    current_value
                ):

                    absolute_changes.append(
                        np.nan
                    )

                    percent_changes.append(
                        np.nan
                    )

                    continue

                target_date = (
                    panel.loc[
                        idx,
                        "asof_date"
                    ]
                    - pd.Timedelta(
                        days=days
                    )
                )

                previous_value = (
                    value_at_or_before(
                        current,
                        panel["asof_date"],
                        target_date,
                    )
                )

                if pd.isna(
                    previous_value
                ):

                    absolute_changes.append(
                        np.nan
                    )

                    percent_changes.append(
                        np.nan
                    )

                    continue

                absolute_change = (
                    float(current_value)
                    - previous_value
                )

                absolute_changes.append(
                    absolute_change
                )

                if previous_value == 0:

                    percent_changes.append(
                        np.nan
                    )

                else:

                    percent_changes.append(
                        (
                            absolute_change
                            / abs(previous_value)
                        )
                        * 100.0
                    )

            panel[
                f"{indicator}_CHANGE_{label}"
            ] = absolute_changes

            panel[
                f"{indicator}_PCT_CHANGE_{label}"
            ] = percent_changes

    return panel


# ============================================================
# Add descriptive directions
# ============================================================

def add_direction_fields(
    panel: pd.DataFrame,
) -> pd.DataFrame:

    panel = panel.copy()

    for indicator in sorted(
        EXPECTED_INDICATORS
    ):

        for label in [
            "30D",
            "90D",
            "1Y",
        ]:

            change_col = (
                f"{indicator}_CHANGE_{label}"
            )

            if change_col not in panel.columns:
                continue

            values = panel[
                change_col
            ]

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


# ============================================================
# Rates and spreads
# ============================================================

def add_rates_and_spreads(
    panel: pd.DataFrame,
) -> pd.DataFrame:

    panel = panel.copy()

    if (
        "SOFR" in panel.columns
        and "EFFR" in panel.columns
    ):

        panel[
            "SOFR_EFFR_SPREAD_BPS"
        ] = (
            panel["SOFR"]
            - panel["EFFR"]
        ) * 100.0

    return panel


# ============================================================
# Net liquidity descriptive proxy
# ============================================================

def add_net_liquidity_proxy(
    panel: pd.DataFrame,
) -> pd.DataFrame:

    panel = panel.copy()

    required = {
        "FED_TOTAL_ASSETS",
        "TREASURY_GENERAL_ACCOUNT",
        "ON_RRP",
    }

    if not required.issubset(
        panel.columns
    ):
        return panel

    # ON_RRP is represented in billions.
    # H.4.1 balance-sheet series are represented
    # in millions.

    panel[
        "ON_RRP_MILLIONS"
    ] = (
        panel["ON_RRP"]
        * 1000.0
    )

    panel[
        "NET_LIQUIDITY_PROXY_MILLIONS"
    ] = (
        panel["FED_TOTAL_ASSETS"]
        - panel["TREASURY_GENERAL_ACCOUNT"]
        - panel["ON_RRP_MILLIONS"]
    )

    return panel


# ============================================================
# Metadata
# ============================================================

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

    panel[
        "analyzer_asof_limit"
    ] = asof.strftime(
        "%Y-%m-%d"
    )

    return panel


# ============================================================
# Summary
# ============================================================

def build_summary(
    panel: pd.DataFrame,
    asof: pd.Timestamp,
) -> pd.DataFrame:

    latest = panel.iloc[-1]

    rows: List[Dict] = []

    for indicator in sorted(
        EXPECTED_INDICATORS
    ):

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
            "asof_date":
                asof.strftime(
                    "%Y-%m-%d"
                ),

            "indicator":
                indicator,

            "latest_value":
                value,

            "latest_observation_date":
                (
                    observation_date.strftime(
                        "%Y-%m-%d"
                    )
                    if pd.notna(
                        observation_date
                    )
                    else None
                ),

            "research_only":
                True,

            "point_in_time_safe":
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

        rows.append(row)

    return pd.DataFrame(rows)


# ============================================================
# Output validation
# ============================================================

def validate_output(
    panel: pd.DataFrame,
    asof: pd.Timestamp,
) -> None:

    if panel.empty:
        fail(
            "Analyzer output is empty."
        )

    if (
        panel["asof_date"].max()
        != asof
    ):
        fail(
            "Output does not end at requested "
            "as-of date."
        )

    if not panel[
        "point_in_time_safe"
    ].all():

        fail(
            "Output contains "
            "point_in_time_safe=False."
        )

    if not panel[
        "research_only"
    ].all():

        fail(
            "Output contains "
            "research_only=False."
        )

    if panel[
        "decision_engine_ready"
    ].any():

        fail(
            "Output contains "
            "decision_engine_ready=True."
        )

    if panel[
        "trading_signal_generated"
    ].any():

        fail(
            "Output contains trading signals."
        )

    if panel[
        "forecast_generated"
    ].any():

        fail(
            "Output contains forecasts."
        )

    if panel[
        "liquidity_score_generated"
    ].any():

        fail(
            "Output contains liquidity scores."
        )

    if panel[
        "asof_date"
    ].duplicated().any():

        fail(
            "Duplicate as-of dates detected."
        )


# ============================================================
# Main
# ============================================================

def main() -> None:

    print("=" * 72)

    print(
        "Liquidity Intelligence Analyzer v1"
    )

    print(
        "Research-only — No Trading Signal"
    )

    print(
        "No Forecast — No Decision Engine"
    )

    print(
        "No Liquidity Score"
    )

    print("=" * 72)

    # --------------------------------------------------------
    # Load
    # --------------------------------------------------------

    df = load_input(
        INPUT_FILE
    )

    print(
        f"Input rows: {len(df):,}"
    )

    # --------------------------------------------------------
    # Validate input
    # --------------------------------------------------------

    validate_input(df)

    print(
        "Input validation: PASS"
    )

    # --------------------------------------------------------
    # Determine as-of
    # --------------------------------------------------------

    asof = determine_asof(
        df
    )

    print(
        "Analyzer as-of date: "
        f"{asof.strftime('%Y-%m-%d')}"
    )

    # --------------------------------------------------------
    # PIT filter
    # --------------------------------------------------------

    pit_df = apply_pit_filter(
        df,
        asof,
    )

    print(
        "PIT-eligible rows: "
        f"{len(pit_df):,}"
    )

    # --------------------------------------------------------
    # Calendar
    # --------------------------------------------------------

    start_date = (
        pit_df[
            "availability_date"
        ]
        .min()
        .normalize()
    )

    calendar = create_daily_calendar(
        start_date,
        asof,
    )

    print(
        "Daily research calendar: "
        f"{len(calendar):,} days"
    )

    # --------------------------------------------------------
    # Build daily PIT panel
    # --------------------------------------------------------

    panel = build_indicator_panel(
        pit_df,
        calendar,
    )

    # --------------------------------------------------------
    # Descriptive calculations
    # --------------------------------------------------------

    panel = add_changes(
        panel
    )

    panel = add_direction_fields(
        panel
    )

    panel = add_rates_and_spreads(
        panel
    )

    panel = add_net_liquidity_proxy(
        panel
    )

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    panel = add_metadata(
        panel,
        asof,
    )

    # --------------------------------------------------------
    # Validate output
    # --------------------------------------------------------

    validate_output(
        panel,
        asof,
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary = build_summary(
        panel,
        asof,
    )

    # --------------------------------------------------------
    # Output columns
    # --------------------------------------------------------

    output_columns = [
        "asof_date",
    ]

    # Levels + observation dates

    for indicator in sorted(
        EXPECTED_INDICATORS
    ):

        output_columns.extend(
            [
                indicator,
                f"{indicator}_observation_date",
            ]
        )

    # Changes

    for indicator in sorted(
        EXPECTED_INDICATORS
    ):

        for label in CHANGE_WINDOWS:

            output_columns.extend(
                [
                    f"{indicator}_CHANGE_{label}",
                    f"{indicator}_PCT_CHANGE_{label}",
                ]
            )

    # Directions

    for indicator in sorted(
        EXPECTED_INDICATORS
    ):

        for label in [
            "30D",
            "90D",
            "1Y",
        ]:

            output_columns.append(
                f"{indicator}_DIRECTION_{label}"
            )

    # Derived fields

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
        column
        for column in output_columns
        if column in panel.columns
    ]

    output = panel[
        output_columns
    ].copy()

    # --------------------------------------------------------
    # Write outputs
    # --------------------------------------------------------

    output.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    summary.to_csv(
        SUMMARY_FILE,
        index=False,
    )

    # --------------------------------------------------------
    # Final status
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("STATUS: PASS")
    print("=" * 72)

    print(
        f"Output: {OUTPUT_FILE}"
    )

    print(
        f"Summary: {SUMMARY_FILE}"
    )

    print(
        f"Output rows: {len(output):,}"
    )

    print(
        "Output date range: "
        f"{output['asof_date'].min().date()} "
        "→ "
        f"{output['asof_date'].max().date()}"
    )

    # --------------------------------------------------------
    # Latest context
    # --------------------------------------------------------

    latest = output.iloc[-1]

    print()
    print(
        "Latest research context:"
    )

    print(
        "  AS_OF_DATE: "
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

    if (
        "SOFR_EFFR_SPREAD_BPS"
        in output.columns
    ):

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

    # --------------------------------------------------------
    # Research-only status
    # --------------------------------------------------------

    print()
    print(
        "Research-only validation:"
    )

    print(
        "  PIT-safe: PASS"
    )

    print(
        "  Research-only: PASS"
    )

    print(
        "  Decision Engine: DISABLED"
    )

    print(
        "  Trading signal: NONE"
    )

    print(
        "  Forecast: NONE"
    )

    print(
        "  Liquidity score: NONE"
    )


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    main()
