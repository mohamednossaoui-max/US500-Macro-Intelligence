"""
VIX Sentiment Analyzer v1

Research-only VIX sentiment analysis.

Input:
    vix_historical_records_input_v1.csv

Outputs:
    vix_sentiment_research_v1.csv
    vix_sentiment_research_summary_v1.csv
    vix_sentiment_extremes_v1.csv

Method:
    - 252-observation rolling window
    - Minimum 126 observations
    - VIX level
    - Weekly change
    - Rolling mean
    - Rolling standard deviation
    - Rolling z-score
    - Rolling percentile
    - Descriptive fear regimes
    - Extreme observations

IMPORTANT:
    No trading signals.
    No forecast.
    No composite sentiment score.
    No Decision Engine integration.
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

INPUT_FILE = Path(
    "vix_historical_records_input_v1.csv"
)

OUTPUT_FILE = Path(
    "vix_sentiment_research_v1.csv"
)

SUMMARY_FILE = Path(
    "vix_sentiment_research_summary_v1.csv"
)

EXTREMES_FILE = Path(
    "vix_sentiment_extremes_v1.csv"
)

ROLLING_WINDOW = 252
MIN_OBSERVATIONS = 126


EXPECTED_COLUMNS = [
    "observation_date",
    "availability_date",
    "VIX",
    "source",
    "source_url",
    "source_page_url",
    "availability_semantics",
    "point_in_time_safe",
    "research_only",
    "decision_engine_ready",
    "sentiment_score_generated",
]


# ============================================================
# HELPERS
# ============================================================

def fail(message: str):
    print(f"ERROR: {message}")
    sys.exit(1)


def rolling_zscore(series: pd.Series) -> pd.Series:

    rolling_mean = series.rolling(
        ROLLING_WINDOW,
        min_periods=MIN_OBSERVATIONS,
    ).mean()

    rolling_std = series.rolling(
        ROLLING_WINDOW,
        min_periods=MIN_OBSERVATIONS,
    ).std(ddof=0)

    return (
        (series - rolling_mean)
        / rolling_std.replace(0, np.nan)
    )


def rolling_percentile(series: pd.Series) -> pd.Series:
    """
    Percentile rank of the current VIX observation
    within its rolling historical window.

    0   = historically very low
    100 = historically very high
    """

    def percentile_last(window):

        values = pd.Series(window).dropna()

        if len(values) < MIN_OBSERVATIONS:
            return np.nan

        current_value = values.iloc[-1]

        return (
            (values <= current_value).sum()
            / len(values)
            * 100.0
        )

    return series.rolling(
        ROLLING_WINDOW,
        min_periods=MIN_OBSERVATIONS,
    ).apply(
        percentile_last,
        raw=False,
    )


def classify_regime(percentile):

    if pd.isna(percentile):
        return "INSUFFICIENT_DATA"

    if percentile >= 95:
        return "EXTREME_FEAR"

    if percentile >= 75:
        return "HIGH_FEAR"

    if percentile <= 5:
        return "EXTREME_LOW_FEAR"

    if percentile <= 25:
        return "LOW_FEAR"

    return "NEUTRAL"


# ============================================================
# LOAD
# ============================================================

print("=" * 70)
print("VIX SENTIMENT ANALYZER v1")
print("=" * 70)

if not INPUT_FILE.exists():

    fail(
        f"Input file not found: {INPUT_FILE}"
    )

print()
print("Loading VIX historical records...")

df = pd.read_csv(
    INPUT_FILE
)

print(
    f"Input rows: {len(df):,}"
)


# ============================================================
# INPUT SCHEMA
# ============================================================

missing = [
    column
    for column in EXPECTED_COLUMNS
    if column not in df.columns
]

if missing:

    fail(
        f"Missing required columns: {missing}"
    )


# ============================================================
# DATE VALIDATION
# ============================================================

df["observation_date"] = pd.to_datetime(
    df["observation_date"],
    errors="coerce",
)

df["availability_date"] = pd.to_datetime(
    df["availability_date"],
    errors="coerce",
)

if df["observation_date"].isna().any():

    fail(
        "Invalid observation_date values."
    )

if df["availability_date"].isna().any():

    fail(
        "Invalid availability_date values."
    )


# ============================================================
# VIX VALIDATION
# ============================================================

df["VIX"] = pd.to_numeric(
    df["VIX"],
    errors="coerce",
)

if df["VIX"].isna().any():

    fail(
        "Invalid VIX values."
    )

if (df["VIX"] <= 0).any():

    fail(
        "VIX contains values <= 0."
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


if not df[
    "point_in_time_safe"
].astype(bool).all():

    fail(
        "Input contains non-PIT-safe records."
    )


# ============================================================
# RESEARCH-ONLY VALIDATION
# ============================================================

if not df[
    "research_only"
].astype(bool).all():

    fail(
        "Input contains non-research records."
    )


if df[
    "decision_engine_ready"
].astype(bool).any():

    fail(
        "Decision Engine ready flag detected."
    )


if df[
    "sentiment_score_generated"
].astype(bool).any():

    fail(
        "Sentiment score already generated."
    )


# ============================================================
# SORT / DUPLICATES
# ============================================================

df = df.sort_values(
    "observation_date"
).reset_index(
    drop=True
)


if df[
    "observation_date"
].duplicated().any():

    fail(
        "Duplicate observation dates detected."
    )


if not df[
    "observation_date"
].is_monotonic_increasing:

    fail(
        "Observation dates are not sorted."
    )


# ============================================================
# BASE OUTPUT
# ============================================================

result = df.copy()


# ============================================================
# DAILY CHANGE
# ============================================================

result["VIX_change"] = (
    result["VIX"].diff()
)

result["VIX_change_pct"] = (
    result["VIX"].pct_change() * 100.0
)


# ============================================================
# ROLLING STATISTICS
# ============================================================

result["VIX_rolling_mean"] = (
    result["VIX"].rolling(
        ROLLING_WINDOW,
        min_periods=MIN_OBSERVATIONS,
    ).mean()
)

result["VIX_rolling_std"] = (
    result["VIX"].rolling(
        ROLLING_WINDOW,
        min_periods=MIN_OBSERVATIONS,
    ).std(ddof=0)
)

result["VIX_z"] = rolling_zscore(
    result["VIX"]
)

result["VIX_percentile"] = rolling_percentile(
    result["VIX"]
)


# ============================================================
# DESCRIPTIVE RESEARCH REGIME
# ============================================================

result["research_regime"] = (
    result["VIX_percentile"]
    .apply(classify_regime)
)


# ============================================================
# EXTREME FLAGS
# ============================================================

result["extreme_fear"] = (
    result["VIX_percentile"] >= 95
)

result["high_fear"] = (
    (result["VIX_percentile"] >= 75)
    & (result["VIX_percentile"] < 95)
)

result["low_fear"] = (
    (result["VIX_percentile"] <= 25)
    & (result["VIX_percentile"] > 5)
)

result["extreme_low_fear"] = (
    result["VIX_percentile"] <= 5
)


# ============================================================
# METADATA
# ============================================================

result["rolling_window_observations"] = (
    ROLLING_WINDOW
)

result["minimum_observations"] = (
    MIN_OBSERVATIONS
)

result["point_in_time_safe"] = True
result["research_only"] = True
result["decision_engine_ready"] = False
result["sentiment_score_generated"] = False


# ============================================================
# COLUMN ORDER
# ============================================================

preferred_columns = [
    "observation_date",
    "availability_date",

    "VIX",
    "VIX_change",
    "VIX_change_pct",

    "VIX_rolling_mean",
    "VIX_rolling_std",
    "VIX_z",
    "VIX_percentile",

    "research_regime",

    "extreme_fear",
    "high_fear",
    "low_fear",
    "extreme_low_fear",

    "rolling_window_observations",
    "minimum_observations",

    "source",
    "source_url",
    "source_page_url",
    "availability_semantics",

    "point_in_time_safe",
    "research_only",
    "decision_engine_ready",
    "sentiment_score_generated",
]


result = result[
    [
        column
        for column in preferred_columns
        if column in result.columns
    ]
]


# ============================================================
# FINAL VALIDATION
# ============================================================

if result.empty:

    fail(
        "Analyzer produced zero rows."
    )


if not result[
    "point_in_time_safe"
].all():

    fail(
        "Final output contains non-PIT-safe records."
    )


if not result[
    "research_only"
].all():

    fail(
        "Final output contains non-research records."
    )


if result[
    "decision_engine_ready"
].any():

    fail(
        "Final output contains Decision Engine flags."
    )


if result[
    "sentiment_score_generated"
].any():

    fail(
        "Final output contains sentiment scores."
    )


# ============================================================
# SUMMARY
# ============================================================

latest = result.iloc[-1]

regime_counts = (
    result[
        "research_regime"
    ]
    .value_counts()
    .rename_axis(
        "research_regime"
    )
    .reset_index(
        name="observations"
    )
)


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
            "rolling_window_observations",

        "value":
            ROLLING_WINDOW,
    },

    {
        "metric":
            "minimum_observations",

        "value":
            MIN_OBSERVATIONS,
    },

    {
        "metric":
            "latest_VIX",

        "value":
            latest["VIX"],
    },

    {
        "metric":
            "latest_VIX_percentile",

        "value":
            latest["VIX_percentile"],
    },

    {
        "metric":
            "latest_VIX_z",

        "value":
            latest["VIX_z"],
    },

    {
        "metric":
            "latest_research_regime",

        "value":
            latest["research_regime"],
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
]


summary = pd.DataFrame(
    summary_rows
)


# ============================================================
# EXTREMES
# ============================================================

extreme_mask = (
    result["extreme_fear"]
    | result["extreme_low_fear"]
)

extremes = result.loc[
    extreme_mask
].copy()


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

extremes.to_csv(
    EXTREMES_FILE,
    index=False,
)


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 70)
print("VIX SENTIMENT ANALYZER v1 — RESULT")
print("=" * 70)

print(
    f"Observations: {len(result):,}"
)

print(
    "Date range: "
    f"{result['observation_date'].min().date()} "
    f"→ "
    f"{result['observation_date'].max().date()}"
)

print()
print("Latest observation:")

print(
    f"  Date: "
    f"{latest['observation_date'].date()}"
)

print(
    f"  VIX: "
    f"{latest['VIX']:.4f}"
)

print(
    f"  VIX percentile: "
    f"{latest['VIX_percentile']:.4f}"
)

print(
    f"  VIX z-score: "
    f"{latest['VIX_z']:.4f}"
)

print(
    f"  Research regime: "
    f"{latest['research_regime']}"
)

print()
print("Research regime counts:")

for _, row in regime_counts.iterrows():

    print(
        f"  {row['research_regime']}: "
        f"{int(row['observations']):,}"
    )

print()
print(
    f"Extreme observations: "
    f"{len(extremes):,}"
)

print()
print("Point-in-time safe: TRUE")
print("Research-only: TRUE")
print("Decision Engine ready: FALSE")
print("Sentiment score generated: FALSE")
print("Trading signal: NONE")
print("Forecast: NONE")

print("=" * 70)

print()
print(
    "PASS: VIX Sentiment Analyzer v1 "
    "completed successfully."
)
