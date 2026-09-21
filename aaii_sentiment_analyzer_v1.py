"""
AAII Sentiment Analyzer v1

Research-only historical AAII sentiment analysis.

Input:
    aaii_historical_records_input_v1.csv

Outputs:
    aaii_sentiment_research_v1.csv
    aaii_sentiment_research_summary_v1.csv
    aaii_sentiment_extremes_v1.csv

Methodology:
    - 52-observation rolling window
    - Minimum 26 observations
    - Bullish / Neutral / Bearish levels
    - Bull-Bear spread
    - Weekly changes
    - Rolling mean / standard deviation
    - Rolling z-score
    - Rolling percentile
    - Descriptive historical regimes

Research-only:
    - No trading signals
    - No forecast
    - No Decision Engine integration
    - No deterministic prediction
    - No composite sentiment score
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# Configuration
# ============================================================

INPUT_FILE = (
    "aaii_historical_records_input_v1.csv"
)

OUTPUT_FILE = (
    "aaii_sentiment_research_v1.csv"
)

SUMMARY_FILE = (
    "aaii_sentiment_research_summary_v1.csv"
)

EXTREMES_FILE = (
    "aaii_sentiment_extremes_v1.csv"
)

ROLLING_WINDOW = 52

MINIMUM_OBSERVATIONS = 26

RESEARCH_ONLY = True

DECISION_ENGINE_READY = False

SENTIMENT_SCORE_GENERATED = False

POINT_IN_TIME_SAFE = True


# ============================================================
# Error helper
# ============================================================

def fail(message: str) -> None:

    print()
    print("=" * 72)
    print("AAII SENTIMENT ANALYZER V1: FAIL")
    print("=" * 72)
    print(message)
    print("=" * 72)

    sys.exit(1)


# ============================================================
# Load input
# ============================================================

def load_input() -> pd.DataFrame:

    print("=" * 72)
    print("AAII SENTIMENT ANALYZER V1")
    print("=" * 72)

    print()
    print("Input:")
    print(INPUT_FILE)

    if not Path(INPUT_FILE).exists():

        fail(
            f"Input file not found: {INPUT_FILE}"
        )

    try:

        df = pd.read_csv(
            INPUT_FILE
        )

    except Exception as exc:

        fail(
            f"Unable to read input CSV: {exc}"
        )

    if df.empty:

        fail(
            "Input CSV contains zero rows."
        )

    print(
        "Input rows:",
        len(df),
    )

    return df


# ============================================================
# Validate input
# ============================================================

def validate_input(
    df: pd.DataFrame,
) -> None:

    print()
    print("Validating input...")

    required_columns = [

        "observation_date",
        "availability_date",

        "bullish_pct",
        "neutral_pct",
        "bearish_pct",

        "bull_bear_spread_pp",

        "source",

        "point_in_time_safe",
        "research_only",
        "decision_engine_ready",
        "sentiment_score_generated",
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:

        fail(
            "Missing required columns:\n"
            + "\n".join(
                f"  - {column}"
                for column in missing
            )
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

    if df[
        "observation_date"
    ].isna().any():

        fail(
            "Invalid observation_date values."
        )

    if df[
        "availability_date"
    ].isna().any():

        fail(
            "Invalid availability_date values."
        )

    # --------------------------------------------------------
    # PIT
    # --------------------------------------------------------

    invalid_pit = (
        df["availability_date"]
        <=
        df["observation_date"]
    )

    if invalid_pit.any():

        fail(
            "PIT validation failed: "
            f"{int(invalid_pit.sum())} rows."
        )

    # --------------------------------------------------------
    # Research-only flags
    # --------------------------------------------------------

    if not df[
        "point_in_time_safe"
    ].astype(bool).all():

        fail(
            "point_in_time_safe is not TRUE "
            "for all input rows."
        )

    if not df[
        "research_only"
    ].astype(bool).all():

        fail(
            "research_only is not TRUE "
            "for all input rows."
        )

    if df[
        "decision_engine_ready"
    ].astype(bool).any():

        fail(
            "Decision Engine integration detected."
        )

    if df[
        "sentiment_score_generated"
    ].astype(bool).any():

        fail(
            "Input already contains a generated "
            "sentiment score."
        )

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    df.sort_values(
        "observation_date",
        inplace=True,
    )

    df.reset_index(
        drop=True,
        inplace=True,
    )

    # --------------------------------------------------------
    # Duplicate observations
    # --------------------------------------------------------

    duplicates = df.duplicated(
        subset=[
            "observation_date"
        ]
    ).sum()

    if duplicates:

        fail(
            "Duplicate observation dates: "
            f"{duplicates}"
        )

    print(
        "Input validation: PASS"
    )


# ============================================================
# Calculate rolling statistics
# ============================================================

def rolling_statistics(
    series: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series]:

    rolling = series.rolling(
        window=ROLLING_WINDOW,
        min_periods=MINIMUM_OBSERVATIONS,
    )

    mean = rolling.mean()

    std = rolling.std(
        ddof=0
    )

    z_score = (
        (series - mean)
        /
        std.replace(
            0,
            np.nan,
        )
    )

    return mean, std, z_score


# ============================================================
# Rolling percentile
# ============================================================

def rolling_percentile(
    series: pd.Series,
) -> pd.Series:

    def percentile_rank(
        window_values,
    ):

        values = np.asarray(
            window_values,
            dtype=float,
        )

        values = values[
            np.isfinite(values)
        ]

        if len(values) < MINIMUM_OBSERVATIONS:

            return np.nan

        current = values[-1]

        less_equal = (
            np.sum(
                values <= current
            )
        )

        return (
            less_equal
            /
            len(values)
            *
            100.0
        )

    return series.rolling(
        window=ROLLING_WINDOW,
        min_periods=MINIMUM_OBSERVATIONS,
    ).apply(
        percentile_rank,
        raw=True,
    )


# ============================================================
# Analyze
# ============================================================

def analyze(
    df: pd.DataFrame,
) -> pd.DataFrame:

    print()
    print(
        "Calculating AAII historical statistics..."
    )

    result = df.copy()

    # --------------------------------------------------------
    # Weekly changes
    # --------------------------------------------------------

    result[
        "bullish_weekly_change_pp"
    ] = (
        result[
            "bullish_pct"
        ].diff()
    )

    result[
        "neutral_weekly_change_pp"
    ] = (
        result[
            "neutral_pct"
        ].diff()
    )

    result[
        "bearish_weekly_change_pp"
    ] = (
        result[
            "bearish_pct"
        ].diff()
    )

    result[
        "bull_bear_spread_weekly_change_pp"
    ] = (
        result[
            "bull_bear_spread_pp"
        ].diff()
    )

    # --------------------------------------------------------
    # Rolling statistics
    # --------------------------------------------------------

    indicators = {

        "bullish_pct": "bullish",

        "neutral_pct": "neutral",

        "bearish_pct": "bearish",

        "bull_bear_spread_pp": "bull_bear_spread",
    }

    for column, prefix in indicators.items():

        mean, std, z = (
            rolling_statistics(
                result[column]
            )
        )

        percentile = (
            rolling_percentile(
                result[column]
            )
        )

        result[
            f"{prefix}_rolling_mean"
        ] = mean

        result[
            f"{prefix}_rolling_std"
        ] = std

        result[
            f"{prefix}_z"
        ] = z

        result[
            f"{prefix}_percentile"
        ] = percentile

    # --------------------------------------------------------
    # Descriptive regime based on Bull-Bear spread percentile
    # --------------------------------------------------------

    percentile = result[
        "bull_bear_spread_percentile"
    ]

    conditions = [

        percentile >= 95,

        percentile >= 75,

        percentile <= 5,

        percentile <= 25,
    ]

    choices = [

        "EXTREME_BULLISH",

        "BULLISH",

        "EXTREME_BEARISH",

        "BEARISH",
    ]

    result[
        "research_regime"
    ] = np.select(
        conditions,
        choices,
        default="NEUTRAL",
    )

    result.loc[
        percentile.isna(),
        "research_regime",
    ] = "INSUFFICIENT_DATA"

    # --------------------------------------------------------
    # Extreme flags
    # --------------------------------------------------------

    result[
        "bullish_extreme_flag"
    ] = (
        result[
            "bullish_percentile"
        ] >= 95
    ) | (
        result[
            "bullish_percentile"
        ] <= 5
    )

    result[
        "bearish_extreme_flag"
    ] = (
        result[
            "bearish_percentile"
        ] >= 95
    ) | (
        result[
            "bearish_percentile"
        ] <= 5
    )

    result[
        "bull_bear_spread_extreme_flag"
    ] = (
        result[
            "bull_bear_spread_percentile"
        ] >= 95
    ) | (
        result[
            "bull_bear_spread_percentile"
        ] <= 5
    )

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    result[
        "rolling_window_observations"
    ] = ROLLING_WINDOW

    result[
        "minimum_observations"
    ] = MINIMUM_OBSERVATIONS

    result[
        "point_in_time_safe"
    ] = True

    result[
        "research_only"
    ] = True

    result[
        "decision_engine_ready"
    ] = False

    result[
        "sentiment_score_generated"
    ] = False

    return result


# ============================================================
# Validate output
# ============================================================

def validate_output(
    result: pd.DataFrame,
) -> None:

    print()
    print(
        "Validating analyzer output..."
    )

    required_columns = [

        "observation_date",
        "availability_date",

        "bullish_pct",
        "neutral_pct",
        "bearish_pct",

        "bull_bear_spread_pp",

        "bullish_weekly_change_pp",
        "neutral_weekly_change_pp",
        "bearish_weekly_change_pp",

        "bull_bear_spread_weekly_change_pp",

        "bullish_rolling_mean",
        "bullish_rolling_std",
        "bullish_z",
        "bullish_percentile",

        "neutral_rolling_mean",
        "neutral_rolling_std",
        "neutral_z",
        "neutral_percentile",

        "bearish_rolling_mean",
        "bearish_rolling_std",
        "bearish_z",
        "bearish_percentile",

        "bull_bear_spread_rolling_mean",
        "bull_bear_spread_rolling_std",
        "bull_bear_spread_z",
        "bull_bear_spread_percentile",

        "research_regime",

        "bullish_extreme_flag",
        "bearish_extreme_flag",
        "bull_bear_spread_extreme_flag",

        "rolling_window_observations",
        "minimum_observations",

        "point_in_time_safe",
        "research_only",
        "decision_engine_ready",
        "sentiment_score_generated",
    ]

    missing = [
        column
        for column in required_columns
        if column not in result.columns
    ]

    if missing:

        fail(
            "Output schema failed.\n"
            "Missing:\n"
            + "\n".join(
                f"  - {column}"
                for column in missing
            )
        )

    # --------------------------------------------------------
    # PIT
    # --------------------------------------------------------

    invalid_pit = (
        result["availability_date"]
        <=
        result["observation_date"]
    )

    if invalid_pit.any():

        fail(
            "Output PIT validation failed."
        )

    # --------------------------------------------------------
    # Research-only
    # --------------------------------------------------------

    if not result[
        "point_in_time_safe"
    ].astype(bool).all():

        fail(
            "Output point_in_time_safe "
            "contains FALSE."
        )

    if not result[
        "research_only"
    ].astype(bool).all():

        fail(
            "Output research_only "
            "contains FALSE."
        )

    if result[
        "decision_engine_ready"
    ].astype(bool).any():

        fail(
            "Output Decision Engine flag "
            "contains TRUE."
        )

    if result[
        "sentiment_score_generated"
    ].astype(bool).any():

        fail(
            "Output sentiment score flag "
            "contains TRUE."
        )

    # --------------------------------------------------------
    # Spread
    # --------------------------------------------------------

    expected_spread = (
        result[
            "bullish_pct"
        ]
        -
        result[
            "bearish_pct"
        ]
    )

    if not np.allclose(
        result[
            "bull_bear_spread_pp"
        ],
        expected_spread,
        equal_nan=True,
    ):

        fail(
            "Bull-Bear spread mismatch."
        )

    # --------------------------------------------------------
    # Ordering
    # --------------------------------------------------------

    if not result[
        "observation_date"
    ].is_monotonic_increasing:

        fail(
            "Observation dates are not "
            "chronologically sorted."
        )

    # --------------------------------------------------------
    # No duplicates
    # --------------------------------------------------------

    if result.duplicated(
        subset=[
            "observation_date"
        ]
    ).any():

        fail(
            "Duplicate observation dates "
            "detected."
        )

    print(
        "Output validation: PASS"
    )


# ============================================================
# Summary
# ============================================================

def create_summary(
    result: pd.DataFrame,
) -> pd.DataFrame:

    regimes = (
        result[
            "research_regime"
        ]
        .value_counts()
        .to_dict()
    )

    summary = pd.DataFrame(
        [
            {
                "dataset":
                    "AAII Sentiment Research v1",

                "records":
                    len(result),

                "first_observation_date":
                    result[
                        "observation_date"
                    ].min().date(),

                "last_observation_date":
                    result[
                        "observation_date"
                    ].max().date(),

                "rolling_window_observations":
                    ROLLING_WINDOW,

                "minimum_observations":
                    MINIMUM_OBSERVATIONS,

                "insufficient_data_rows":
                    int(
                        (
                            result[
                                "research_regime"
                            ]
                            ==
                            "INSUFFICIENT_DATA"
                        ).sum()
                    ),

                "extreme_bullish_rows":
                    int(
                        (
                            result[
                                "research_regime"
                            ]
                            ==
                            "EXTREME_BULLISH"
                        ).sum()
                    ),

                "bullish_rows":
                    int(
                        (
                            result[
                                "research_regime"
                            ]
                            ==
                            "BULLISH"
                        ).sum()
                    ),

                "neutral_rows":
                    int(
                        (
                            result[
                                "research_regime"
                            ]
                            ==
                            "NEUTRAL"
                        ).sum()
                    ),

                "bearish_rows":
                    int(
                        (
                            result[
                                "research_regime"
                            ]
                            ==
                            "BEARISH"
                        ).sum()
                    ),

                "extreme_bearish_rows":
                    int(
                        (
                            result[
                                "research_regime"
                            ]
                            ==
                            "EXTREME_BEARISH"
                        ).sum()
                    ),

                "extreme_observations":
                    int(
                        result[
                            "bull_bear_spread_extreme_flag"
                        ].sum()
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
        ]
    )

    return summary


# ============================================================
# Extremes
# ============================================================

def create_extremes(
    result: pd.DataFrame,
) -> pd.DataFrame:

    mask = (
        result[
            "bullish_extreme_flag"
        ]
        |
        result[
            "bearish_extreme_flag"
        ]
        |
        result[
            "bull_bear_spread_extreme_flag"
        ]
    )

    columns = [

        "observation_date",
        "availability_date",

        "bullish_pct",
        "neutral_pct",
        "bearish_pct",

        "bull_bear_spread_pp",

        "bullish_z",
        "bullish_percentile",

        "neutral_z",
        "neutral_percentile",

        "bearish_z",
        "bearish_percentile",

        "bull_bear_spread_z",
        "bull_bear_spread_percentile",

        "research_regime",

        "bullish_extreme_flag",
        "bearish_extreme_flag",
        "bull_bear_spread_extreme_flag",

        "point_in_time_safe",
        "research_only",
        "decision_engine_ready",
        "sentiment_score_generated",
    ]

    extremes = (
        result.loc[
            mask,
            columns,
        ]
        .copy()
        .sort_values(
            "observation_date"
        )
        .reset_index(
            drop=True
        )
    )

    return extremes


# ============================================================
# Main
# ============================================================

def main() -> None:

    df = load_input()

    validate_input(
        df
    )

    result = analyze(
        df
    )

    validate_output(
        result
    )

    summary = create_summary(
        result
    )

    extremes = create_extremes(
        result
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    result.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    summary.to_csv(
        SUMMARY_FILE,
        index=False,
    )

    extremes.to_csv(
        EXTREMES_FILE,
        index=False,
    )

    # --------------------------------------------------------
    # Final report
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print(
        "AAII SENTIMENT ANALYZER V1"
    )
    print(
        "FINAL VALIDATION REPORT"
    )
    print("=" * 72)

    print(
        f"Records:                    "
        f"{len(result):,}"
    )

    print(
        "First observation:          "
        f"{result['observation_date'].min().date()}"
    )

    print(
        "Last observation:           "
        f"{result['observation_date'].max().date()}"
    )

    print(
        f"Rolling window:             "
        f"{ROLLING_WINDOW} observations"
    )

    print(
        f"Minimum observations:       "
        f"{MINIMUM_OBSERVATIONS}"
    )

    print(
        "Extreme observations:       "
        f"{len(extremes):,}"
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
        "Output validation:          PASS"
    )

    print()
    print(
        "Output files:"
    )

    print(
        f"  - {OUTPUT_FILE}"
    )

    print(
        f"  - {SUMMARY_FILE}"
    )

    print(
        f"  - {EXTREMES_FILE}"
    )

    print()
    print("=" * 72)
    print(
        "VALIDATION: PASS"
    )
    print("=" * 72)


if __name__ == "__main__":
    main()
