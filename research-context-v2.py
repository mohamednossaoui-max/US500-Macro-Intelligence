#!/usr/bin/env python3

"""
US500 Macro Intelligence
Research Context v2

Combines:
    - Macro Context v1
    - Sentiment Engine v1
    - Technical Intelligence v1
    - Cross-Asset Intelligence v1

Purpose:
    Unified research context only.

IMPORTANT:
    - Research-only
    - No trading signals
    - No forecasting
    - No recommendations
    - No execution
    - No Decision Engine integration
    - No unified trading decision
    - Strict point-in-time alignment
    - Anti-lookahead validation

PIT rules:
    Macro:
        macro_availability_date

    Sentiment:
        sentiment_asof_date

    Technical:
        technical_availability_date
        NOT technical_observation_date

    Cross-Asset:
        cross_asset_availability_date
        NOT cross_asset_observation_date

The master cutoff is determined by:
    RESEARCH_CONTEXT_AS_OF_DATE

The cutoff normally comes from the latest Macro Context date.
Future source rows are allowed because all layers are aligned
backward using their PIT availability/as-of dates.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# Configuration
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

MACRO_FILE = Path(
    os.getenv(
        "MACRO_CONTEXT_FILE",
        BASE_DIR / "context_input" / "macro_context_v1.csv",
    )
)

SENTIMENT_FILE = Path(
    os.getenv(
        "SENTIMENT_ENGINE_FILE",
        BASE_DIR / "context_input" / "sentiment_engine_research_v1.csv",
    )
)

TECHNICAL_FILE = Path(
    os.getenv(
        "TECHNICAL_INTELLIGENCE_FILE",
        BASE_DIR / "context_input" / "technical_intelligence_research_v1.csv",
    )
)

CROSS_ASSET_FILE = Path(
    os.getenv(
        "CROSS_ASSET_FILE",
        BASE_DIR / "context_input" / "cross_asset_research_v1.csv",
    )
)

OUTPUT_FILE = BASE_DIR / "research_context_v2.csv"
SUMMARY_FILE = BASE_DIR / "research_context_summary_v2.csv"
EXTREMES_FILE = BASE_DIR / "research_context_extremes_v2.csv"


# ============================================================
# Utility
# ============================================================

def fail(message: str) -> None:
    raise RuntimeError(message)


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        fail(f"{label} not found: {path}")


def ensure_unique_columns(
    df: pd.DataFrame,
    label: str,
) -> pd.DataFrame:

    duplicated = df.columns[
        df.columns.duplicated()
    ].tolist()

    if duplicated:
        fail(
            f"{label} contains duplicate column labels: "
            f"{duplicated}"
        )

    return df


def detect_date_column(
    df: pd.DataFrame,
    candidates: list[str],
    label: str,
) -> str:

    for column in candidates:
        if column in df.columns:
            return column

    fail(
        f"Could not identify date column for {label}. "
        f"Available columns: {list(df.columns)}"
    )


def parse_dates(
    series: pd.Series,
    label: str,
) -> pd.Series:

    result = pd.to_datetime(
        series,
        errors="coerce",
    )

    if result.isna().any():

        count = int(result.isna().sum())

        fail(
            f"{label}: {count} invalid dates detected."
        )

    return result.dt.normalize()


def get_as_of_date() -> pd.Timestamp | None:

    value = os.getenv(
        "RESEARCH_CONTEXT_AS_OF_DATE",
        "",
    ).strip()

    if not value:
        return None

    parsed = pd.to_datetime(
        value,
        errors="coerce",
    )

    if pd.isna(parsed):

        fail(
            "Invalid RESEARCH_CONTEXT_AS_OF_DATE. "
            "Expected YYYY-MM-DD."
        )

    return pd.Timestamp(parsed).normalize()


def first_existing(
    row: pd.Series,
    candidates: list[str],
):

    for column in candidates:

        if column in row.index:

            value = row[column]

            if pd.notna(value):
                return value

    return np.nan


# ============================================================
# Load files
# ============================================================

for path, label in [
    (MACRO_FILE, "Macro Context"),
    (SENTIMENT_FILE, "Sentiment Engine"),
    (TECHNICAL_FILE, "Technical Intelligence"),
    (CROSS_ASSET_FILE, "Cross-Asset Intelligence"),
]:

    require_file(path, label)


macro = pd.read_csv(
    MACRO_FILE,
    low_memory=False,
)

sentiment = pd.read_csv(
    SENTIMENT_FILE,
    low_memory=False,
)

technical = pd.read_csv(
    TECHNICAL_FILE,
    low_memory=False,
)

cross_asset = pd.read_csv(
    CROSS_ASSET_FILE,
    low_memory=False,
)


for df, label in [
    (macro, "Macro Context"),
    (sentiment, "Sentiment Engine"),
    (technical, "Technical Intelligence"),
    (cross_asset, "Cross-Asset Intelligence"),
]:

    ensure_unique_columns(df, label)

    if df.empty:
        fail(
            f"{label} dataset is empty."
        )


# ============================================================
# Detect dates
# ============================================================

macro_date_column = detect_date_column(
    macro,
    [
        "context_date",
        "observation_date",
        "asof_date",
        "date",
    ],
    "Macro Context",
)

sentiment_date_column = detect_date_column(
    sentiment,
    [
        "asof_date",
        "observation_date",
        "context_date",
        "date",
    ],
    "Sentiment Engine",
)

technical_date_column = detect_date_column(
    technical,
    [
        "observation_date",
        "context_date",
        "date",
    ],
    "Technical Intelligence",
)

cross_asset_observation_column = detect_date_column(
    cross_asset,
    [
        "observation_date",
        "date",
    ],
    "Cross-Asset Intelligence observation date",
)


# ============================================================
# Temporary normalized dates
# ============================================================

macro["_source_date"] = parse_dates(
    macro[macro_date_column],
    "Macro Context source date",
)

sentiment["_source_date"] = parse_dates(
    sentiment[sentiment_date_column],
    "Sentiment Engine source date",
)

technical["_source_date"] = parse_dates(
    technical[technical_date_column],
    "Technical Intelligence source date",
)

cross_asset["_source_observation_date"] = parse_dates(
    cross_asset[cross_asset_observation_column],
    "Cross-Asset observation date",
)


# ============================================================
# MACRO PREPARATION
# ============================================================

if "context_date" in macro.columns:

    macro["macro_original_context_date"] = parse_dates(
        macro["context_date"],
        "Macro original context date",
    )

    macro = macro.drop(
        columns=["context_date"]
    )

else:

    macro["macro_original_context_date"] = (
        macro["_source_date"]
    )


if "availability_date" in macro.columns:

    macro["macro_availability_date"] = parse_dates(
        macro["availability_date"],
        "Macro availability date",
    )

else:

    macro["macro_availability_date"] = (
        macro["macro_original_context_date"]
    )


macro = macro.drop(
    columns=[
        "_source_date",
        "availability_date",
    ],
    errors="ignore",
)


macro_rename = {}

for column in macro.columns:

    if column in {
        "macro_availability_date",
        "macro_original_context_date",
    }:
        continue

    new_name = f"macro_{column}"

    if new_name in macro.columns:
        fail(
            f"Macro column collision: {new_name}"
        )

    macro_rename[column] = new_name


macro = macro.rename(
    columns=macro_rename
)


macro = (
    macro
    .sort_values("macro_availability_date")
    .drop_duplicates(
        subset=["macro_availability_date"],
        keep="last",
    )
    .reset_index(drop=True)
)


ensure_unique_columns(
    macro,
    "Prepared Macro Context",
)


# ============================================================
# SENTIMENT PREPARATION
# ============================================================

if "asof_date" in sentiment.columns:

    sentiment["sentiment_asof_date"] = parse_dates(
        sentiment["asof_date"],
        "Sentiment asof date",
    )

elif "observation_date" in sentiment.columns:

    sentiment["sentiment_asof_date"] = parse_dates(
        sentiment["observation_date"],
        "Sentiment observation date",
    )

elif "context_date" in sentiment.columns:

    sentiment["sentiment_asof_date"] = parse_dates(
        sentiment["context_date"],
        "Sentiment context date",
    )

else:

    sentiment["sentiment_asof_date"] = (
        sentiment["_source_date"]
    )


if "availability_date" in sentiment.columns:

    sentiment["sentiment_availability_date"] = parse_dates(
        sentiment["availability_date"],
        "Sentiment availability date",
    )

else:

    sentiment["sentiment_availability_date"] = (
        sentiment["sentiment_asof_date"]
    )


sentiment = sentiment.drop(
    columns=[
        "_source_date",
        "asof_date",
        "observation_date",
        "context_date",
        "date",
        "availability_date",
    ],
    errors="ignore",
)


sentiment_rename = {}

for column in sentiment.columns:

    if column in {
        "sentiment_asof_date",
        "sentiment_availability_date",
    }:
        continue

    new_name = f"sentiment_{column}"

    if new_name in sentiment.columns:
        fail(
            f"Sentiment column collision: {new_name}"
        )

    sentiment_rename[column] = new_name


sentiment = sentiment.rename(
    columns=sentiment_rename
)


sentiment = (
    sentiment
    .sort_values("sentiment_asof_date")
    .drop_duplicates(
        subset=["sentiment_asof_date"],
        keep="last",
    )
    .reset_index(drop=True)
)


ensure_unique_columns(
    sentiment,
    "Prepared Sentiment Engine",
)


# ============================================================
# TECHNICAL PREPARATION
# ============================================================

if "observation_date" in technical.columns:

    technical["technical_observation_date"] = parse_dates(
        technical["observation_date"],
        "Technical observation date",
    )

elif "context_date" in technical.columns:

    technical["technical_observation_date"] = parse_dates(
        technical["context_date"],
        "Technical context date",
    )

else:

    technical["technical_observation_date"] = (
        technical["_source_date"]
    )


if "availability_date" in technical.columns:

    technical["technical_availability_date"] = parse_dates(
        technical["availability_date"],
        "Technical availability date",
    )

else:

    technical["technical_availability_date"] = (
        technical["technical_observation_date"]
        + pd.Timedelta(days=1)
    )


technical_pit_invalid = (
    technical["technical_availability_date"]
    < technical["technical_observation_date"]
)

if technical_pit_invalid.any():

    fail(
        "Technical Intelligence contains rows where "
        "availability_date is earlier than observation_date."
    )


technical = technical.drop(
    columns=[
        "_source_date",
        "observation_date",
        "context_date",
        "date",
        "availability_date",
    ],
    errors="ignore",
)


technical_rename = {}

for column in technical.columns:

    if column in {
        "technical_observation_date",
        "technical_availability_date",
    }:
        continue

    new_name = f"technical_{column}"

    if new_name in technical.columns:
        fail(
            f"Technical column collision: {new_name}"
        )

    technical_rename[column] = new_name


technical = technical.rename(
    columns=technical_rename
)


technical = (
    technical
    .sort_values(
        [
            "technical_observation_date",
            "technical_availability_date",
        ]
    )
    .drop_duplicates(
        subset=["technical_observation_date"],
        keep="last",
    )
    .reset_index(drop=True)
)


ensure_unique_columns(
    technical,
    "Prepared Technical Intelligence",
)


# ============================================================
# CROSS-ASSET PREPARATION
# ============================================================

# ------------------------------------------------------------
# Observation date
# ------------------------------------------------------------

cross_asset["cross_asset_observation_date"] = (
    cross_asset["_source_observation_date"]
)


# ------------------------------------------------------------
# Availability date
# ------------------------------------------------------------

if "availability_date" not in cross_asset.columns:

    fail(
        "Cross-Asset Intelligence is missing "
        "availability_date."
    )


cross_asset["cross_asset_availability_date"] = (
    parse_dates(
        cross_asset["availability_date"],
        "Cross-Asset availability date",
    )
)


# ------------------------------------------------------------
# Cross-Asset PIT validation
# ------------------------------------------------------------

cross_asset_pit_invalid = (
    cross_asset["cross_asset_availability_date"]
    <= cross_asset["cross_asset_observation_date"]
)


if cross_asset_pit_invalid.any():

    count = int(
        cross_asset_pit_invalid.sum()
    )

    fail(
        "Cross-Asset PIT validation failed: "
        f"{count} rows have availability_date "
        "earlier than or equal to observation_date."
    )


# ------------------------------------------------------------
# Existing PIT flag validation
# ------------------------------------------------------------

if "point_in_time_safe" in cross_asset.columns:

    pit_values = (
        cross_asset["point_in_time_safe"]
        .astype(str)
        .str.lower()
    )

    invalid_flag = ~pit_values.isin(
        ["true", "1"]
    )

    if invalid_flag.any():

        fail(
            "Cross-Asset contains rows where "
            "point_in_time_safe is not TRUE."
        )


# ------------------------------------------------------------
# Remove source date columns
# ------------------------------------------------------------

cross_asset = cross_asset.drop(
    columns=[
        "_source_observation_date",
        "observation_date",
        "availability_date",
        "date",
    ],
    errors="ignore",
)


# ------------------------------------------------------------
# Prefix Cross-Asset fields
# ------------------------------------------------------------

cross_asset_rename = {}

for column in cross_asset.columns:

    if column in {
        "cross_asset_observation_date",
        "cross_asset_availability_date",
    }:
        continue

    new_name = f"cross_asset_{column}"

    if new_name in cross_asset.columns:

        fail(
            f"Cross-Asset column collision: {new_name}"
        )

    cross_asset_rename[column] = new_name


cross_asset = cross_asset.rename(
    columns=cross_asset_rename
)


# ------------------------------------------------------------
# One row per availability date
# ------------------------------------------------------------

cross_asset = (
    cross_asset
    .sort_values(
        [
            "cross_asset_availability_date",
            "cross_asset_observation_date",
        ]
    )
    .drop_duplicates(
        subset=["cross_asset_availability_date"],
        keep="last",
    )
    .reset_index(drop=True)
)


ensure_unique_columns(
    cross_asset,
    "Prepared Cross-Asset Intelligence",
)


# ============================================================
# Determine master cutoff
# ============================================================

as_of_date = get_as_of_date()


# ============================================================
# Build unified calendar
# ============================================================

calendar_parts = [
    macro["macro_availability_date"],
    sentiment["sentiment_asof_date"],
    technical["technical_availability_date"],
    cross_asset["cross_asset_availability_date"],
]


calendar = pd.concat(
    calendar_parts,
    ignore_index=True,
)


calendar = (
    pd.to_datetime(
        calendar,
        errors="coerce",
    )
    .dropna()
    .dt.normalize()
    .drop_duplicates()
    .sort_values()
    .reset_index(drop=True)
)


context = pd.DataFrame(
    {
        "context_date": calendar
    }
)


# ============================================================
# Apply master cutoff
# ============================================================

if as_of_date is not None:

    context = context[
        context["context_date"] <= as_of_date
    ].copy()

    if context.empty:

        fail(
            "RESEARCH_CONTEXT_AS_OF_DATE removed "
            "all context dates."
        )


# ============================================================
# MACRO AS-OF MERGE
# ============================================================

context = context.sort_values(
    "context_date"
).reset_index(drop=True)

macro = macro.sort_values(
    "macro_availability_date"
).reset_index(drop=True)


context = pd.merge_asof(
    context,
    macro,
    left_on="context_date",
    right_on="macro_availability_date",
    direction="backward",
    allow_exact_matches=True,
)


# ============================================================
# SENTIMENT AS-OF MERGE
# ============================================================

context = context.sort_values(
    "context_date"
).reset_index(drop=True)

sentiment = sentiment.sort_values(
    "sentiment_asof_date"
).reset_index(drop=True)


context = pd.merge_asof(
    context,
    sentiment,
    left_on="context_date",
    right_on="sentiment_asof_date",
    direction="backward",
    allow_exact_matches=True,
)


# ============================================================
# TECHNICAL AS-OF MERGE
# ============================================================

context = context.sort_values(
    "context_date"
).reset_index(drop=True)

technical = technical.sort_values(
    "technical_availability_date"
).reset_index(drop=True)


context = pd.merge_asof(
    context,
    technical,
    left_on="context_date",
    right_on="technical_availability_date",
    direction="backward",
    allow_exact_matches=True,
)


# ============================================================
# CROSS-ASSET AS-OF MERGE
# ============================================================
#
# CRITICAL PIT RULE:
#
# Use cross_asset_availability_date.
#
# NEVER use cross_asset_observation_date as the
# synchronization key.
# ============================================================

context = context.sort_values(
    "context_date"
).reset_index(drop=True)

cross_asset = cross_asset.sort_values(
    "cross_asset_availability_date"
).reset_index(drop=True)


context = pd.merge_asof(
    context,
    cross_asset,
    left_on="context_date",
    right_on="cross_asset_availability_date",
    direction="backward",
    allow_exact_matches=True,
)


# ============================================================
# Layer availability
# ============================================================

context["macro_available"] = (
    context["macro_availability_date"].notna()
    & (
        context["macro_availability_date"]
        <= context["context_date"]
    )
)


context["sentiment_available"] = (
    context["sentiment_asof_date"].notna()
    & (
        context["sentiment_asof_date"]
        <= context["context_date"]
    )
)


context["technical_available"] = (
    context["technical_availability_date"].notna()
    & (
        context["technical_availability_date"]
        <= context["context_date"]
    )
)


context["cross_asset_available"] = (
    context["cross_asset_availability_date"].notna()
    & (
        context["cross_asset_availability_date"]
        <= context["context_date"]
    )
)


context["available_layer_count"] = (
    context[
        [
            "macro_available",
            "sentiment_available",
            "technical_available",
            "cross_asset_available",
        ]
    ]
    .sum(axis=1)
    .astype(int)
)


# ============================================================
# Canonical research metadata
# ============================================================

context["point_in_time_safe"] = True

context["research_only"] = True

context["decision_engine_ready"] = False

context["trading_signal_generated"] = False

context["forecast_generated"] = False

context["unified_decision_generated"] = False


# ============================================================
# PIT / ANTI-LOOKAHEAD VALIDATION
# ============================================================

pit_failures = []


# ------------------------------------------------------------
# Macro
# ------------------------------------------------------------

macro_mask = (
    context["macro_availability_date"].notna()
    & (
        context["macro_availability_date"]
        > context["context_date"]
    )
)


if macro_mask.any():

    pit_failures.append(
        "Macro availability lookahead detected."
    )


# ------------------------------------------------------------
# Sentiment
# ------------------------------------------------------------

sentiment_mask = (
    context["sentiment_asof_date"].notna()
    & (
        context["sentiment_asof_date"]
        > context["context_date"]
    )
)


if sentiment_mask.any():

    pit_failures.append(
        "Sentiment lookahead detected."
    )


# ------------------------------------------------------------
# Technical
# ------------------------------------------------------------

technical_mask = (
    context["technical_availability_date"].notna()
    & (
        context["technical_availability_date"]
        > context["context_date"]
    )
)


if technical_mask.any():

    pit_failures.append(
        "Technical availability lookahead detected."
    )


# Technical internal PIT
technical_internal_mask = (
    context["technical_observation_date"].notna()
    & context["technical_availability_date"].notna()
    & (
        context["technical_availability_date"]
        < context["technical_observation_date"]
    )
)


if technical_internal_mask.any():

    pit_failures.append(
        "Technical availability earlier than "
        "observation date."
    )


# ------------------------------------------------------------
# Cross-Asset
# ------------------------------------------------------------

cross_asset_mask = (
    context["cross_asset_availability_date"].notna()
    & (
        context["cross_asset_availability_date"]
        > context["context_date"]
    )
)


if cross_asset_mask.any():

    pit_failures.append(
        "Cross-Asset availability lookahead detected."
    )


# Cross-Asset internal PIT
cross_asset_internal_mask = (
    context["cross_asset_observation_date"].notna()
    & context["cross_asset_availability_date"].notna()
    & (
        context["cross_asset_availability_date"]
        <= context["cross_asset_observation_date"]
    )
)


if cross_asset_internal_mask.any():

    pit_failures.append(
        "Cross-Asset availability date is not "
        "strictly after observation date."
    )


if pit_failures:

    fail(
        "Point-in-time / anti-lookahead validation failed:\n"
        + "\n".join(pit_failures)
    )


# ============================================================
# Date integrity
# ============================================================

context["context_date"] = pd.to_datetime(
    context["context_date"],
    errors="coerce",
).dt.normalize()


if context["context_date"].isna().any():

    fail(
        "context_date contains invalid dates."
    )


context = (
    context
    .sort_values("context_date")
    .reset_index(drop=True)
)


duplicate_dates = int(
    context["context_date"].duplicated().sum()
)


if duplicate_dates:

    fail(
        f"Duplicate context dates detected: "
        f"{duplicate_dates}"
    )


# ============================================================
# Future-date validation
# ============================================================

if as_of_date is not None:

    future_rows = context[
        context["context_date"] > as_of_date
    ]

    if not future_rows.empty:

        fail(
            "Future context rows remain after cutoff."
        )

    if context["context_date"].max() != as_of_date:

        fail(
            "Latest context date "
            f"{context['context_date'].max().date()} "
            "does not equal requested cutoff "
            f"{as_of_date.date()}."
        )


# ============================================================
# Layer count consistency
# ============================================================

expected_layer_count = (
    context[
        [
            "macro_available",
            "sentiment_available",
            "technical_available",
            "cross_asset_available",
        ]
    ]
    .sum(axis=1)
    .astype(int)
)


if not context[
    "available_layer_count"
].equals(expected_layer_count):

    fail(
        "available_layer_count is inconsistent "
        "with layer availability flags."
    )


# ============================================================
# Research-only assertions
# ============================================================

if not context[
    "point_in_time_safe"
].eq(True).all():

    fail(
        "point_in_time_safe contains FALSE."
    )


if not context[
    "research_only"
].eq(True).all():

    fail(
        "research_only contains FALSE."
    )


if not context[
    "decision_engine_ready"
].eq(False).all():

    fail(
        "decision_engine_ready must remain FALSE."
    )


if not context[
    "trading_signal_generated"
].eq(False).all():

    fail(
        "Trading signals detected."
    )


if not context[
    "forecast_generated"
].eq(False).all():

    fail(
        "Forecasts detected."
    )


if not context[
    "unified_decision_generated"
].eq(False).all():

    fail(
        "Unified decisions detected."
    )


# ============================================================
# Required canonical columns
# ============================================================

required_columns = [
    "context_date",
    "available_layer_count",

    "macro_available",
    "sentiment_available",
    "technical_available",
    "cross_asset_available",

    "macro_availability_date",
    "sentiment_asof_date",
    "technical_observation_date",
    "technical_availability_date",
    "cross_asset_observation_date",
    "cross_asset_availability_date",

    "point_in_time_safe",
    "research_only",
    "decision_engine_ready",
    "trading_signal_generated",
    "forecast_generated",
    "unified_decision_generated",
]


missing = [
    column
    for column in required_columns
    if column not in context.columns
]


if missing:

    fail(
        f"Missing required canonical columns: {missing}"
    )


# ============================================================
# Latest context
# ============================================================

latest = context.iloc[-1]


# ============================================================
# Build summary
# ============================================================

summary = {
    "context_date": latest["context_date"],

    "available_layer_count": latest[
        "available_layer_count"
    ],

    "macro_available": latest[
        "macro_available"
    ],

    "sentiment_available": latest[
        "sentiment_available"
    ],

    "technical_available": latest[
        "technical_available"
    ],

    "cross_asset_available": latest[
        "cross_asset_available"
    ],

    "point_in_time_safe": latest[
        "point_in_time_safe"
    ],

    "research_only": latest[
        "research_only"
    ],

    "decision_engine_ready": latest[
        "decision_engine_ready"
    ],

    "trading_signal_generated": latest[
        "trading_signal_generated"
    ],

    "forecast_generated": latest[
        "forecast_generated"
    ],

    "unified_decision_generated": latest[
        "unified_decision_generated"
    ],
}


# ============================================================
# Macro summary
# ============================================================

summary["economic_regime"] = first_existing(
    latest,
    [
        "macro_economic_regime",
        "economic_regime",
    ],
)

summary["inflation_score"] = first_existing(
    latest,
    [
        "macro_inflation_score",
        "inflation_score",
    ],
)

summary["labor_score"] = first_existing(
    latest,
    [
        "macro_labor_score",
        "labor_score",
    ],
)

summary["growth_score"] = first_existing(
    latest,
    [
        "macro_growth_score",
        "growth_score",
    ],
)

summary["fed_score"] = first_existing(
    latest,
    [
        "macro_fed_score",
        "fed_score",
    ],
)

summary["financial_stress_regime"] = first_existing(
    latest,
    [
        "macro_financial_stress_regime",
        "financial_stress_regime",
    ],
)

summary["financial_stress_composite"] = first_existing(
    latest,
    [
        "macro_financial_stress_composite",
        "financial_stress_composite",
    ],
)

summary["treasury_2y"] = first_existing(
    latest,
    [
        "macro_treasury_2y",
        "treasury_2y",
    ],
)

summary["treasury_10y"] = first_existing(
    latest,
    [
        "macro_treasury_10y",
        "treasury_10y",
    ],
)

summary["yield_10y_2y_spread"] = first_existing(
    latest,
    [
        "macro_yield_10y_2y_spread",
        "yield_10y_2y_spread",
    ],
)


# ============================================================
# Sentiment summary
# ============================================================

summary["sentiment_regime"] = first_existing(
    latest,
    [
        "sentiment_research_regime",
        "sentiment_unified_sentiment_regime",
        "research_regime",
    ],
)

summary["unified_sentiment_score"] = first_existing(
    latest,
    [
        "sentiment_unified_sentiment_score",
        "unified_sentiment_score",
    ],
)

summary["cot_score"] = first_existing(
    latest,
    [
        "sentiment_cot_sentiment_score",
        "cot_sentiment_score",
        "cot_score",
    ],
)

summary["aaii_score"] = first_existing(
    latest,
    [
        "sentiment_aaii_sentiment_score",
        "aaii_sentiment_score",
        "aaii_score",
    ],
)

summary["vix_score"] = first_existing(
    latest,
    [
        "sentiment_vix_sentiment_score",
        "vix_sentiment_score",
        "vix_score",
    ],
)

summary["VIX"] = first_existing(
    latest,
    [
        "sentiment_VIX",
        "VIX",
    ],
)


# ============================================================
# Technical summary
# ============================================================

summary["technical_regime"] = first_existing(
    latest,
    [
        "technical_technical_regime",
        "technical_regime",
    ],
)

summary["trend_structure"] = first_existing(
    latest,
    [
        "technical_trend_structure",
        "trend_structure",
    ],
)

summary["Close"] = first_existing(
    latest,
    [
        "technical_Close",
        "Close",
    ],
)

summary["RSI14"] = first_existing(
    latest,
    [
        "technical_RSI14",
        "RSI14",
    ],
)

summary["ATR14"] = first_existing(
    latest,
    [
        "technical_ATR14",
        "ATR14",
    ],
)

summary["ATR14_pct"] = first_existing(
    latest,
    [
        "technical_ATR14_pct",
        "ATR14_pct",
    ],
)

summary["ROC20_pct"] = first_existing(
    latest,
    [
        "technical_ROC20_pct",
        "ROC20_pct",
    ],
)

summary["drawdown_pct"] = first_existing(
    latest,
    [
        "technical_drawdown_pct",
        "drawdown_pct",
    ],
)


# ============================================================
# Cross-Asset summary
# ============================================================

summary["cross_asset_asset_count"] = first_existing(
    latest,
    [
        "cross_asset_available_asset_count",
        "cross_asset_asset_count",
    ],
)

summary["cross_asset_SP500"] = first_existing(
    latest,
    [
        "cross_asset_SP500",
    ],
)

summary["cross_asset_NASDAQ"] = first_existing(
    latest,
    [
        "cross_asset_NASDAQ",
    ],
)

summary["cross_asset_GOLD"] = first_existing(
    latest,
    [
        "cross_asset_GOLD",
    ],
)

summary["cross_asset_DXY"] = first_existing(
    latest,
    [
        "cross_asset_DXY",
    ],
)

summary["cross_asset_VIX"] = first_existing(
    latest,
    [
        "cross_asset_VIX",
    ],
)

summary["cross_asset_US10Y"] = first_existing(
    latest,
    [
        "cross_asset_US10Y",
    ],
)

summary["cross_asset_WTI"] = first_existing(
    latest,
    [
        "cross_asset_WTI",
    ],
)

summary["cross_asset_BITCOIN"] = first_existing(
    latest,
    [
        "cross_asset_BITCOIN",
    ],
)

summary["cross_asset_SP500_NASDAQ_corr"] = first_existing(
    latest,
    [
        "cross_asset_SP500_NASDAQ_corr_60d",
    ],
)

summary["cross_asset_SP500_GOLD_corr"] = first_existing(
    latest,
    [
        "cross_asset_SP500_GOLD_corr_60d",
    ],
)

summary["cross_asset_SP500_DXY_corr"] = first_existing(
    latest,
    [
        "cross_asset_SP500_DXY_corr_60d",
    ],
)

summary["cross_asset_SP500_VIX_corr"] = first_existing(
    latest,
    [
        "cross_asset_SP500_VIX_corr_60d",
    ],
)


# ============================================================
# Summary dataframe
# ============================================================

summary_df = pd.DataFrame(
    [summary]
)


# ============================================================
# Research extremes
# ============================================================

extreme_mask = pd.Series(
    False,
    index=context.index,
)


# Sentiment extremes
if "sentiment_research_regime" in context.columns:

    extreme_mask |= context[
        "sentiment_research_regime"
    ].isin(
        [
            "EXTREME_BULLISH",
            "EXTREME_BEARISH",
        ]
    )


# Technical extremes
if "technical_technical_regime" in context.columns:

    extreme_mask |= context[
        "technical_technical_regime"
    ].isin(
        [
            "STRONG_BULLISH",
            "STRONG_BEARISH",
        ]
    )


# Financial stress extremes
if "macro_financial_stress_regime" in context.columns:

    extreme_mask |= context[
        "macro_financial_stress_regime"
    ].isin(
        [
            "EXTREME_RESEARCH_STRESS",
            "HIGH_RESEARCH_STRESS",
        ]
    )


# Cross-Asset correlation extremes
correlation_columns = [
    column
    for column in context.columns
    if (
        column.startswith("cross_asset_")
        and "_corr_60d" in column
    )
]


for column in correlation_columns:

    values = pd.to_numeric(
        context[column],
        errors="coerce",
    )

    extreme_mask |= (
        values.abs() >= 0.80
    )


extremes = context.loc[
    extreme_mask
].copy()


# ============================================================
# Save
# ============================================================

context.to_csv(
    OUTPUT_FILE,
    index=False,
)

summary_df.to_csv(
    SUMMARY_FILE,
    index=False,
)

extremes.to_csv(
    EXTREMES_FILE,
    index=False,
)


# ============================================================
# Final report
# ============================================================

print("=" * 70)
print("RESEARCH CONTEXT v2")
print("=" * 70)

print(
    f"Rows: {len(context):,}"
)

print(
    f"Columns: {len(context.columns):,}"
)

print(
    "Date range:",
    context["context_date"].min().date(),
    "->",
    context["context_date"].max().date(),
)

if as_of_date is not None:

    print(
        "As-of cutoff:",
        as_of_date.date(),
    )

else:

    print(
        "As-of cutoff: NONE"
    )


print(
    "Latest context date:",
    latest["context_date"].date()
)

print(
    "Latest available layers:",
    int(
        latest["available_layer_count"]
    ),
    "/ 4"
)

print(
    "Macro available:",
    bool(
        latest["macro_available"]
    )
)

print(
    "Sentiment available:",
    bool(
        latest["sentiment_available"]
    )
)

print(
    "Technical available:",
    bool(
        latest["technical_available"]
    )
)

print(
    "Cross-Asset available:",
    bool(
        latest["cross_asset_available"]
    )
)

print(
    "Point-in-time safe:",
    bool(
        context["point_in_time_safe"].all()
    )
)

print(
    "Research only:",
    bool(
        context["research_only"].all()
    )
)

print(
    "Decision Engine:",
    bool(
        context["decision_engine_ready"].any()
    )
)

print(
    "Trading signal:",
    bool(
        context["trading_signal_generated"].any()
    )
)

print(
    "Forecast:",
    bool(
        context["forecast_generated"].any()
    )
)

print(
    "Unified decision:",
    bool(
        context["unified_decision_generated"].any()
    )
)

print(
    "Duplicate context dates:",
    duplicate_dates
)

print(
    "PIT failures:",
    len(pit_failures)
)

print(
    "Extreme research rows:",
    len(extremes)
)

print("=" * 70)
print("RESEARCH CONTEXT v2 PASSED")
print("=" * 70)
