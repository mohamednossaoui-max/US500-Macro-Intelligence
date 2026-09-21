"""
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
