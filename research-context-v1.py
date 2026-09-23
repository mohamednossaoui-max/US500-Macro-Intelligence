#!/usr/bin/env python3

"""
Research Context v1

Combines:
    - Macro Context v1
    - Sentiment Engine v1
    - Technical Intelligence v1

Purpose:
    Unified research context only.

This layer:
    - DOES NOT generate trading signals
    - DOES NOT generate forecasts
    - DOES NOT generate recommendations
    - DOES NOT integrate with the Decision Engine
    - MUST remain point-in-time safe
    - MUST remain anti-lookahead safe

Optional environment variable:

    RESEARCH_CONTEXT_AS_OF_DATE=YYYY-MM-DD

Example:

    RESEARCH_CONTEXT_AS_OF_DATE=2026-09-20

The as-of date limits the final unified research context.

IMPORTANT PIT RULE:

    Technical Intelligence is synchronized using
    technical_availability_date, NOT merely
    technical_observation_date.

This prevents technical observations from being used
before they are considered available to the unified
research layer.
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

OUTPUT_FILE = BASE_DIR / "research_context_v1.csv"
SUMMARY_FILE = BASE_DIR / "research_context_summary_v1.csv"
EXTREMES_FILE = BASE_DIR / "research_context_extremes_v1.csv"


# ============================================================
# Utility functions
# ============================================================

def fail(message: str) -> None:
    raise RuntimeError(message)


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        fail(f"{label} not found: {path}")


def detect_date_column(
    df: pd.DataFrame,
    candidates: list[str],
    label: str,
) -> str:

    for column in candidates:
        if column in df.columns:
            return column

    fail(
        f"Could not identify a date column for {label}. "
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

        bad = int(result.isna().sum())

        fail(
            f"{label}: {bad} invalid dates detected."
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


# ============================================================
# Load source files
# ============================================================

require_file(
    MACRO_FILE,
    "Macro Context input",
)

require_file(
    SENTIMENT_FILE,
    "Sentiment Engine input",
)

require_file(
    TECHNICAL_FILE,
    "Technical Intelligence input",
)


macro = pd.read_csv(
    MACRO_FILE
)

sentiment = pd.read_csv(
    SENTIMENT_FILE
)

technical = pd.read_csv(
    TECHNICAL_FILE
)


ensure_unique_columns(
    macro,
    "Macro Context",
)

ensure_unique_columns(
    sentiment,
    "Sentiment Engine",
)

ensure_unique_columns(
    technical,
    "Technical Intelligence",
)


# ============================================================
# Detect source date columns
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


# ============================================================
# Normalize source dates
# ============================================================

macro["_source_date"] = parse_dates(
    macro[macro_date_column],
    "Macro Context",
)

sentiment["_source_date"] = parse_dates(
    sentiment[sentiment_date_column],
    "Sentiment Engine",
)

technical["_source_date"] = parse_dates(
    technical[technical_date_column],
    "Technical Intelligence",
)


# ============================================================
# MACRO CONTEXT PREPARATION
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


# ------------------------------------------------------------
# Macro availability date
# ------------------------------------------------------------

if "availability_date" in macro.columns:

    macro["macro_availability_date"] = parse_dates(
        macro["availability_date"],
        "Macro availability date",
    )

else:

    macro["macro_availability_date"] = (
        macro["macro_original_context_date"]
    )


# Remove temporary source date.
macro = macro.drop(
    columns=["_source_date"],
    errors="ignore",
)


# Prefix every non-canonical Macro field.
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
            f"Macro column collision: "
            f"{new_name}"
        )

    macro_rename[column] = new_name


macro = macro.rename(
    columns=macro_rename
)


# One row per availability date.
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
# SENTIMENT ENGINE PREPARATION
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


# ------------------------------------------------------------
# Sentiment availability date
# ------------------------------------------------------------

if "availability_date" in sentiment.columns:

    sentiment["sentiment_availability_date"] = parse_dates(
        sentiment["availability_date"],
        "Sentiment availability date",
    )

else:

    sentiment["sentiment_availability_date"] = (
        sentiment["sentiment_asof_date"]
    )


# Remove source date.
sentiment = sentiment.drop(
    columns=["_source_date"],
    errors="ignore",
)


# Remove source date columns that could collide.
for column in [
    "asof_date",
    "observation_date",
    "context_date",
    "availability_date",
]:

    if column in sentiment.columns:

        sentiment = sentiment.drop(
            columns=[column]
        )


# Prefix remaining source-specific columns.
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
            f"Sentiment column collision: "
            f"{new_name}"
        )

    sentiment_rename[column] = new_name


sentiment = sentiment.rename(
    columns=sentiment_rename
)


# One row per as-of date.
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
# TECHNICAL INTELLIGENCE PREPARATION
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


# ------------------------------------------------------------
# Technical availability date
# ------------------------------------------------------------

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


# ------------------------------------------------------------
# Technical PIT validation
# ------------------------------------------------------------

technical_pit_invalid = (
    technical["technical_availability_date"]
    < technical["technical_observation_date"]
)

if technical_pit_invalid.any():

    bad_count = int(
        technical_pit_invalid.sum()
    )

    fail(
        "Technical Intelligence contains "
        f"{bad_count} rows where availability_date "
        "is earlier than observation_date."
    )


# Remove temporary/source date.
technical = technical.drop(
    columns=["_source_date"],
    errors="ignore",
)


# Remove original source date names.
for column in [
    "observation_date",
    "context_date",
    "date",
    "availability_date",
]:

    if column in technical.columns:

        technical = technical.drop(
            columns=[column]
        )


# Prefix remaining technical fields.
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
            f"Technical column collision: "
            f"{new_name}"
        )

    technical_rename[column] = new_name


technical = technical.rename(
    columns=technical_rename
)


# One row per observation date.
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
# Build unified calendar
# ============================================================
#
# IMPORTANT:
#
# Technical dates enter the unified calendar using their
# availability date, not their observation date.
#
# This ensures a technical observation cannot become visible
# to the unified context before its availability date.
# ============================================================

calendar_parts = [
    macro["macro_availability_date"],
    sentiment["sentiment_asof_date"],
    technical["technical_availability_date"],
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
# Apply explicit as-of cutoff
# ============================================================

as_of_date = get_as_of_date()

if as_of_date is not None:

    context = context[
        context["context_date"] <= as_of_date
    ].copy()

    if context.empty:

        fail(
            "RESEARCH_CONTEXT_AS_OF_DATE removed "
            "all available context dates."
        )


# ============================================================
# Point-in-time merge: Macro
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
# Point-in-time merge: Sentiment
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
# Point-in-time merge: Technical
# ============================================================
#
# CRITICAL:
#
# Use technical_availability_date.
#
# Do NOT use technical_observation_date here.
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


context["available_layer_count"] = (
    context[
        [
            "macro_available",
            "sentiment_available",
            "technical_available",
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
# Anti-lookahead validation
# ============================================================

pit_failures = []


# ------------------------------------------------------------
# Macro lookahead
# ------------------------------------------------------------

macro_mask = (
    context["macro_availability_date"].notna()
    & (
        context["macro_availability_date"]
        > context["context_date"]
    )
)


if macro_mask.any():

    bad_dates = context.loc[
        macro_mask,
        "context_date",
    ].dt.strftime("%Y-%m-%d").tolist()

    pit_failures.append(
        f"Macro lookahead rows: {bad_dates[:10]}"
    )


# ------------------------------------------------------------
# Sentiment lookahead
# ------------------------------------------------------------

sentiment_mask = (
    context["sentiment_asof_date"].notna()
    & (
        context["sentiment_asof_date"]
        > context["context_date"]
    )
)


if sentiment_mask.any():

    bad_dates = context.loc[
        sentiment_mask,
        "context_date",
    ].dt.strftime("%Y-%m-%d").tolist()

    pit_failures.append(
        f"Sentiment lookahead rows: {bad_dates[:10]}"
    )


# ------------------------------------------------------------
# Technical lookahead
# ------------------------------------------------------------
#
# IMPORTANT:
#
# Validate availability date, not observation date.
# ------------------------------------------------------------

technical_mask = (
    context["technical_availability_date"].notna()
    & (
        context["technical_availability_date"]
        > context["context_date"]
    )
)


if technical_mask.any():

    bad_dates = context.loc[
        technical_mask,
        "context_date",
    ].dt.strftime("%Y-%m-%d").tolist()

    pit_failures.append(
        f"Technical availability lookahead rows: "
        f"{bad_dates[:10]}"
    )


# ------------------------------------------------------------
# Technical internal PIT validation
# ------------------------------------------------------------

technical_internal_mask = (
    context["technical_observation_date"].notna()
    & context["technical_availability_date"].notna()
    & (
        context["technical_availability_date"]
        < context["technical_observation_date"]
    )
)


if technical_internal_mask.any():

    bad_dates = context.loc[
        technical_internal_mask,
        "context_date",
    ].dt.strftime("%Y-%m-%d").tolist()

    pit_failures.append(
        "Technical availability earlier than observation "
        f"rows: {bad_dates[:10]}"
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
        "context_date contains invalid or missing dates."
    )


context = context.sort_values(
    "context_date"
).reset_index(drop=True)


duplicate_dates = int(
    context["context_date"].duplicated().sum()
)


if duplicate_dates:

    fail(
        f"Duplicate context_date values detected: "
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
            "Future context rows remain after "
            "RESEARCH_CONTEXT_AS_OF_DATE filtering."
        )


# ============================================================
# Research-only assertions
# ============================================================

if not context["point_in_time_safe"].all():

    fail(
        "point_in_time_safe contains False."
    )


if not context["research_only"].all():

    fail(
        "research_only contains False."
    )


if context["decision_engine_ready"].any():

    fail(
        "decision_engine_ready must remain False."
    )


if context["trading_signal_generated"].any():

    fail(
        "Trading signals must not be generated."
    )


if context["forecast_generated"].any():

    fail(
        "Forecasts must not be generated."
    )


if context["unified_decision_generated"].any():

    fail(
        "Unified decisions must not be generated."
    )


# ============================================================
# Required output columns
# ============================================================

required_columns = [
    "context_date",
    "available_layer_count",
    "macro_available",
    "sentiment_available",
    "technical_available",
    "point_in_time_safe",
    "research_only",
    "decision_engine_ready",
    "trading_signal_generated",
    "forecast_generated",
    "unified_decision_generated",
]


missing_columns = [
    column
    for column in required_columns
    if column not in context.columns
]


if missing_columns:

    fail(
        f"Missing required output columns: "
        f"{missing_columns}"
    )


# ============================================================
# Latest row
# ============================================================

latest = context.iloc[-1]


# ============================================================
# Summary helper
# ============================================================

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
# Latest Macro fields
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
# Latest Sentiment fields
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
# Latest Technical fields
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


# ------------------------------------------------------------
# Sentiment extremes
# ------------------------------------------------------------

if "sentiment_research_regime" in context.columns:

    extreme_mask |= context[
        "sentiment_research_regime"
    ].isin(
        [
            "EXTREME_BULLISH",
            "EXTREME_BEARISH",
        ]
    )


# ------------------------------------------------------------
# Technical extremes
# ------------------------------------------------------------

if "technical_technical_regime" in context.columns:

    extreme_mask |= context[
        "technical_technical_regime"
    ].isin(
        [
            "STRONG_BULLISH",
            "STRONG_BEARISH",
        ]
    )


# ------------------------------------------------------------
# Financial stress extremes
# ------------------------------------------------------------

if "macro_financial_stress_regime" in context.columns:

    extreme_mask |= context[
        "macro_financial_stress_regime"
    ].isin(
        [
            "EXTREME_RESEARCH_STRESS",
            "HIGH_RESEARCH_STRESS",
        ]
    )


extremes = context.loc[
    extreme_mask
].copy()


# ============================================================
# Save outputs
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
# Final validation output
# ============================================================

print("=" * 70)
print("Research Context v1")
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
    )
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
    "Decision Engine ready:",
    bool(
        context["decision_engine_ready"].any()
    )
)

print(
    "Trading signal generated:",
    bool(
        context["trading_signal_generated"].any()
    )
)

print(
    "Forecast generated:",
    bool(
        context["forecast_generated"].any()
    )
)

print(
    "Unified decision generated:",
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
print("PASS")
print("=" * 70)
