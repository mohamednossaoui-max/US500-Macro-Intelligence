"""
COT Positioning Analyzer v1

Research-only analysis of CFTC TFF Futures-Only positioning
for E-mini S&P 500.

Input:
    cot_historical_records_input_v1.csv

Outputs:
    cot_positioning_research_v1.csv
    cot_positioning_research_summary_v1.csv
    cot_positioning_extremes_v1.csv

Design:
- No trading signals.
- No market forecast.
- No Decision Engine integration.
- No sentiment score.
- Positioning metrics only.
- Historical normalization uses 52 COT observations
  (~1 year of weekly observations).
- PIT-safe availability_date is preserved.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd


# ============================================================
# Configuration
# ============================================================

INPUT = "cot_historical_records_input_v1.csv"

OUTPUT = "cot_positioning_research_v1.csv"

SUMMARY = "cot_positioning_research_summary_v1.csv"

EXTREMES = "cot_positioning_extremes_v1.csv"

TARGET_CODE = "13874A"

ROLLING_WINDOW = 52

MIN_PERIODS = 26


# ============================================================
# Required columns
# ============================================================

REQUIRED_COLUMNS = [

    "contract_market_code",

    "contract_name",

    "observation_date",

    "availability_date",

    "open_interest",

    "dealer_long",

    "dealer_short",

    "asset_manager_long",

    "asset_manager_short",

    "leveraged_money_long",

    "leveraged_money_short",

    "other_reportables_long",

    "other_reportables_short",

    "nonreportable_long",

    "nonreportable_short",

    "asset_manager_net",

    "leveraged_money_net",

    "dealer_net",

    "point_in_time_safe",
]


# ============================================================
# Helpers
# ============================================================

def rolling_zscore(
    series: pd.Series,
    window: int = ROLLING_WINDOW,
    min_periods: int = MIN_PERIODS,
) -> pd.Series:

    mean = (
        series
        .rolling(
            window=window,
            min_periods=min_periods,
        )
        .mean()
    )

    std = (
        series
        .rolling(
            window=window,
            min_periods=min_periods,
        )
        .std(
            ddof=0
        )
    )

    return (
        (series - mean)
        / std.replace(0, np.nan)
    )


def rolling_percentile(
    series: pd.Series,
    window: int = ROLLING_WINDOW,
    min_periods: int = MIN_PERIODS,
) -> pd.Series:

    def percentile_rank(values):

        values = pd.Series(values)

        if values.empty:
            return np.nan

        current = values.iloc[-1]

        return (
            values
            .rank(
                pct=True,
                method="average",
            )
            .iloc[-1]
            * 100.0
        )

    return (
        series
        .rolling(
            window=window,
            min_periods=min_periods,
        )
        .apply(
            percentile_rank,
            raw=False,
        )
    )


def net_to_oi(
    net: pd.Series,
    open_interest: pd.Series,
) -> pd.Series:

    return (
        net
        / open_interest.replace(0, np.nan)
    )


# ============================================================
# Main
# ============================================================

def main() -> int:

    print("=" * 70)
    print("COT POSITIONING ANALYZER V1")
    print("=" * 70)

    # --------------------------------------------------------
    # Load input
    # --------------------------------------------------------

    try:

        df = pd.read_csv(
            INPUT
        )

    except FileNotFoundError:

        raise RuntimeError(
            f"Input file not found: {INPUT}"
        )

    # --------------------------------------------------------
    # Validate schema
    # --------------------------------------------------------

    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing:

        raise RuntimeError(
            "Missing required columns: "
            + ", ".join(missing)
        )

    # --------------------------------------------------------
    # Target contract validation
    # --------------------------------------------------------

    df[
        "contract_market_code"
    ] = (
        df[
            "contract_market_code"
        ]
        .astype(str)
        .str.strip()
    )

    df = df[
        df[
            "contract_market_code"
        ] == TARGET_CODE
    ].copy()

    if df.empty:

        raise RuntimeError(
            f"No records found for {TARGET_CODE}"
        )

    # --------------------------------------------------------
    # Dates
    # --------------------------------------------------------

    df[
        "observation_date"
    ] = pd.to_datetime(
        df[
            "observation_date"
        ],
        errors="coerce",
    )

    df[
        "availability_date"
    ] = pd.to_datetime(
        df[
            "availability_date"
        ],
        errors="coerce",
    )

    if (
        df["observation_date"].isna().any()
        or
        df["availability_date"].isna().any()
    ):

        raise RuntimeError(
            "Invalid dates detected."
        )

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    df = (
        df
        .sort_values(
            "observation_date"
        )
        .reset_index(drop=True)
    )

    # --------------------------------------------------------
    # PIT validation
    # --------------------------------------------------------

    if not bool(
        (
            df["availability_date"]
            > df["observation_date"]
        ).all()
    ):

        raise AssertionError(
            "PIT validation failed."
        )

    if not bool(
        df["point_in_time_safe"].all()
    ):

        raise AssertionError(
            "Input contains non-PIT-safe records."
        )

    # ========================================================
    # Positioning calculations
    # ========================================================

    # --------------------------------------------------------
    # Net positioning
    # --------------------------------------------------------

    df["asset_manager_net"] = (
        df["asset_manager_long"]
        - df["asset_manager_short"]
    )

    df["leveraged_money_net"] = (
        df["leveraged_money_long"]
        - df["leveraged_money_short"]
    )

    df["dealer_net"] = (
        df["dealer_long"]
        - df["dealer_short"]
    )

    df["other_reportables_net"] = (
        df["other_reportables_long"]
        - df["other_reportables_short"]
    )

    df["nonreportable_net"] = (
        df["nonreportable_long"]
        - df["nonreportable_short"]
    )

    # --------------------------------------------------------
    # Net positioning / Open Interest
    # --------------------------------------------------------

    df["asset_manager_net_oi_pct"] = (
        net_to_oi(
            df["asset_manager_net"],
            df["open_interest"],
        )
        * 100.0
    )

    df["leveraged_money_net_oi_pct"] = (
        net_to_oi(
            df["leveraged_money_net"],
            df["open_interest"],
        )
        * 100.0
    )

    df["dealer_net_oi_pct"] = (
        net_to_oi(
            df["dealer_net"],
            df["open_interest"],
        )
        * 100.0
    )

    df["other_reportables_net_oi_pct"] = (
        net_to_oi(
            df["other_reportables_net"],
            df["open_interest"],
        )
        * 100.0
    )

    df["nonreportable_net_oi_pct"] = (
        net_to_oi(
            df["nonreportable_net"],
            df["open_interest"],
        )
        * 100.0
    )

    # ========================================================
    # Weekly changes
    # ========================================================

    df["asset_manager_net_change"] = (
        df["asset_manager_net"]
        .diff()
    )

    df["leveraged_money_net_change"] = (
        df["leveraged_money_net"]
        .diff()
    )

    df["dealer_net_change"] = (
        df["dealer_net"]
        .diff()
    )

    df["other_reportables_net_change"] = (
        df["other_reportables_net"]
        .diff()
    )

    df["nonreportable_net_change"] = (
        df["nonreportable_net"]
        .diff()
    )

    df["open_interest_change"] = (
        df["open_interest"]
        .diff()
    )

    # ========================================================
    # 52-observation historical normalization
    # ========================================================

    # Asset Manager

    df["asset_manager_net_z"] = rolling_zscore(
        df["asset_manager_net"]
    )

    df["asset_manager_net_oi_pct_z"] = rolling_zscore(
        df["asset_manager_net_oi_pct"]
    )

    df["asset_manager_net_percentile"] = rolling_percentile(
        df["asset_manager_net"]
    )

    # Leveraged Money

    df["leveraged_money_net_z"] = rolling_zscore(
        df["leveraged_money_net"]
    )

    df["leveraged_money_net_oi_pct_z"] = rolling_zscore(
        df["leveraged_money_net_oi_pct"]
    )

    df["leveraged_money_net_percentile"] = rolling_percentile(
        df["leveraged_money_net"]
    )

    # Dealer

    df["dealer_net_z"] = rolling_zscore(
        df["dealer_net"]
    )

    df["dealer_net_oi_pct_z"] = rolling_zscore(
        df["dealer_net_oi_pct"]
    )

    df["dealer_net_percentile"] = rolling_percentile(
        df["dealer_net"]
    )

    # ========================================================
    # Positioning extremes
    # ========================================================

    df["asset_manager_extreme"] = (
        (df["asset_manager_net_percentile"] >= 95)
        |
        (df["asset_manager_net_percentile"] <= 5)
    )

    df["leveraged_money_extreme"] = (
        (df["leveraged_money_net_percentile"] >= 95)
        |
        (df["leveraged_money_net_percentile"] <= 5)
    )

    df["dealer_extreme"] = (
        (df["dealer_net_percentile"] >= 95)
        |
        (df["dealer_net_percentile"] <= 5)
    )

    # ========================================================
    # Positioning direction descriptors
    # ========================================================

    df["asset_manager_position"] = np.where(
        df["asset_manager_net"] > 0,
        "NET_LONG",
        np.where(
            df["asset_manager_net"] < 0,
            "NET_SHORT",
            "FLAT",
        ),
    )

    df["leveraged_money_position"] = np.where(
        df["leveraged_money_net"] > 0,
        "NET_LONG",
        np.where(
            df["leveraged_money_net"] < 0,
            "NET_SHORT",
            "FLAT",
        ),
    )

    df["dealer_position"] = np.where(
        df["dealer_net"] > 0,
        "NET_LONG",
        np.where(
            df["dealer_net"] < 0,
            "NET_SHORT",
            "FLAT",
        ),
    )

    # ========================================================
    # Research classification
    # ========================================================

    def classify_percentile(value):

        if pd.isna(value):
            return "INSUFFICIENT_DATA"

        if value >= 95:
            return "EXTREME_HIGH"

        if value >= 75:
            return "HIGH"

        if value <= 5:
            return "EXTREME_LOW"

        if value <= 25:
            return "LOW"

        return "NEUTRAL"

    df["asset_manager_research_regime"] = (
        df["asset_manager_net_percentile"]
        .apply(classify_percentile)
    )

    df["leveraged_money_research_regime"] = (
        df["leveraged_money_net_percentile"]
        .apply(classify_percentile)
    )

    df["dealer_research_regime"] = (
        df["dealer_net_percentile"]
        .apply(classify_percentile)
    )

    # ========================================================
    # Research metadata
    # ========================================================

    df["rolling_window_observations"] = (
        ROLLING_WINDOW
    )

    df["minimum_observations"] = (
        MIN_PERIODS
    )

    df["point_in_time_safe"] = True

    df["research_only"] = True

    df["decision_engine_ready"] = False

    df["sentiment_score_generated"] = False

    # ========================================================
    # Output column order
    # ========================================================

    output_columns = [

        "contract_market_code",

        "contract_name",

        "observation_date",

        "availability_date",

        "open_interest",

        # Asset Manager
        "asset_manager_long",
        "asset_manager_short",
        "asset_manager_net",
        "asset_manager_net_oi_pct",
        "asset_manager_net_change",
        "asset_manager_net_z",
        "asset_manager_net_oi_pct_z",
        "asset_manager_net_percentile",
        "asset_manager_position",
        "asset_manager_research_regime",
        "asset_manager_extreme",

        # Leveraged Money
        "leveraged_money_long",
        "leveraged_money_short",
        "leveraged_money_net",
        "leveraged_money_net_oi_pct",
        "leveraged_money_net_change",
        "leveraged_money_net_z",
        "leveraged_money_net_oi_pct_z",
        "leveraged_money_net_percentile",
        "leveraged_money_position",
        "leveraged_money_research_regime",
        "leveraged_money_extreme",

        # Dealer
        "dealer_long",
        "dealer_short",
        "dealer_net",
        "dealer_net_oi_pct",
        "dealer_net_change",
        "dealer_net_z",
        "dealer_net_oi_pct_z",
        "dealer_net_percentile",
        "dealer_position",
        "dealer_research_regime",
        "dealer_extreme",

        # Other groups
        "other_reportables_long",
        "other_reportables_short",
        "other_reportables_net",

        "nonreportable_long",
        "nonreportable_short",
        "nonreportable_net",

        # OI
        "open_interest_change",

        # Metadata
        "rolling_window_observations",
        "minimum_observations",
        "point_in_time_safe",
        "research_only",
        "decision_engine_ready",
        "sentiment_score_generated",
    ]

    research = df[
        output_columns
    ].copy()

    # ========================================================
    # Save research dataset
    # ========================================================

    research.to_csv(
        OUTPUT,
        index=False,
    )

    # ========================================================
    # Extreme observations
    # ========================================================

    extreme_mask = (
        research["asset_manager_extreme"]
        |
        research["leveraged_money_extreme"]
        |
        research["dealer_extreme"]
    )

    extremes = research[
        extreme_mask
    ].copy()

    extremes.to_csv(
        EXTREMES,
        index=False,
    )

    # ========================================================
    # Summary
    # ========================================================

    latest = research.iloc[-1]

    summary = pd.DataFrame([{

        "analyzer":
            "COT Positioning Analyzer v1",

        "target_contract":
            "E-MINI S&P 500",

        "target_code":
            TARGET_CODE,

        "records":
            len(research),

        "first_observation_date":
            research[
                "observation_date"
            ].min(),

        "last_observation_date":
            research[
                "observation_date"
            ].max(),

        "rolling_window_observations":
            ROLLING_WINDOW,

        "minimum_observations":
            MIN_PERIODS,

        "extreme_observations":
            len(extremes),

        "latest_observation_date":
            latest[
                "observation_date"
            ],

        "latest_availability_date":
            latest[
                "availability_date"
            ],

        "latest_asset_manager_net":
            latest[
                "asset_manager_net"
            ],

        "latest_asset_manager_percentile":
            latest[
                "asset_manager_net_percentile"
            ],

        "latest_leveraged_money_net":
            latest[
                "leveraged_money_net"
            ],

        "latest_leveraged_money_percentile":
            latest[
                "leveraged_money_net_percentile"
            ],

        "latest_dealer_net":
            latest[
                "dealer_net"
            ],

        "latest_dealer_percentile":
            latest[
                "dealer_net_percentile"
            ],

        "point_in_time_safe_all":
            bool(
                research[
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

    summary.to_csv(
        SUMMARY,
        index=False,
    )

    # ========================================================
    # Final validations
    # ========================================================

    if len(research) != len(df):

        raise AssertionError(
            "Output record count mismatch."
        )

    if not bool(
        research[
            "point_in_time_safe"
        ].all()
    ):

        raise AssertionError(
            "Output PIT validation failed."
        )

    if not bool(
        research[
            "research_only"
        ].all()
    ):

        raise AssertionError(
            "Research-only validation failed."
        )

    if bool(
        research[
            "decision_engine_ready"
        ].any()
    ):

        raise AssertionError(
            "Decision Engine flag must remain False."
        )

    if bool(
        research[
            "sentiment_score_generated"
        ].any()
    ):

        raise AssertionError(
            "Sentiment score must not be generated "
            "by this analyzer."
        )

    # ========================================================
    # Console
    # ========================================================

    print()
    print("=" * 70)
    print("COT POSITIONING ANALYZER V1 - PASS")
    print("=" * 70)

    print(
        summary.to_string(
            index=False
        )
    )

    print("=" * 70)

    print(
        f"Research output: {OUTPUT}"
    )

    print(
        f"Summary: {SUMMARY}"
    )

    print(
        f"Extremes: {EXTREMES}"
    )

    print(
        "Research-only: TRUE"
    )

    print(
        "Decision Engine: DISABLED"
    )

    print(
        "Sentiment Score: NOT GENERATED"
    )

    return 0


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    raise SystemExit(
        main()
    )
