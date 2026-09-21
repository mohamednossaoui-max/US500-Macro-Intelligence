#!/usr/bin/env python3

"""
Research Context v1

Combines:
    - Macro Context v1
    - Sentiment Engine v1
    - Technical Intelligence v1

Research-only aggregation layer.

IMPORTANT:
    - No trading signal
    - No forecast
    - No recommendation
    - No Decision Engine integration
    - Point-in-time safe
    - Anti-lookahead validation

Optional environment variable:
    RESEARCH_CONTEXT_AS_OF_DATE=YYYY-MM-DD

If provided, no context_date after this date is included.
"""

from __future__ import annotations

import os
import sys
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
# Helpers
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


def parse_date_series(
    df: pd.DataFrame,
    column: str,
    label: str,
) -> pd.Series:
    result = pd.to_datetime(df[column], errors="coerce")

    if result.isna().any():
        bad_count = int(result.isna().sum())
        fail(
            f"{label}: {bad_count} invalid dates found "
            f"in column '{column}'."
        )

    return result.dt.normalize()


def env_as_of_date() -> pd.Timestamp | None:
    """
    Optional explicit context cutoff.

    Example:
        RESEARCH_CONTEXT_AS_OF_DATE=2026-09-21
    """

    value = os.getenv("RESEARCH_CONTEXT_AS_OF_DATE", "").strip()

    if not value:
        return None

    parsed = pd.to_datetime(value, errors="coerce")

    if pd.isna(parsed):
        fail(
            "Invalid RESEARCH_CONTEXT_AS_OF_DATE. "
            "Expected YYYY-MM-DD."
        )

    return pd.Timestamp(parsed).normalize()


def ensure_bool(
    df: pd.DataFrame,
    column: str,
    default: bool,
) -> None:
    if column not in df.columns:
        df[column] = default


def add_prefixed_columns(
    df: pd.DataFrame,
    prefix: str,
    exclude: set[str],
) -> pd.DataFrame:
    """
    Prefix source-specific columns to reduce collisions in the
    final unified research context.

    Core availability/date columns are intentionally preserved.
    """

    rename_map = {}

    for column in df.columns:
        if column in exclude:
            continue

        rename_map[column] = f"{prefix}{column}"

    return df.rename(columns=rename_map)


# ============================================================
# Load inputs
# ============================================================

require_file(MACRO_FILE, "Macro Context input")
require_file(SENTIMENT_FILE, "Sentiment Engine input")
require_file(TECHNICAL_FILE, "Technical Intelligence input")

macro = pd.read_csv(MACRO_FILE)
sentiment = pd.read_csv(SENTIMENT_FILE)
technical = pd.read_csv(TECHNICAL_FILE)


# ============================================================
# Identify and normalize dates
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


macro["_source_date"] = parse_date_series(
    macro,
    macro_date_column,
    "Macro Context",
)

sentiment["_source_date"] = parse_date_series(
    sentiment,
    sentiment_date_column,
    "Sentiment Engine",
)

technical["_source_date"] = parse_date_series(
    technical,
    technical_date_column,
    "Technical Intelligence",
)


# ============================================================
# Normalize availability dates
# ============================================================

# ----------------------------
# Macro
# ----------------------------

if "context_date" in macro.columns:
    macro["macro_original_context_date"] = pd.to_datetime(
        macro["context_date"],
        errors="coerce",
    ).dt.normalize()

if "availability_date" in macro.columns:
    macro["macro_availability_date"] = pd.to_datetime(
        macro["availability_date"],
        errors="coerce",
    ).dt.normalize()
else:
    # Macro Context is already an aggregated research layer.
    # Its context_date is used as its conservative availability date.
    macro["macro_availability_date"] = macro["_source_date"]


# ----------------------------
# Sentiment
# ----------------------------

if "asof_date" in sentiment.columns:
    sentiment["sentiment_asof_date"] = pd.to_datetime(
        sentiment["asof_date"],
        errors="coerce",
    ).dt.normalize()
else:
    sentiment["sentiment_asof_date"] = sentiment["_source_date"]

if "availability_date" in sentiment.columns:
    sentiment["sentiment_availability_date"] = pd.to_datetime(
        sentiment["availability_date"],
        errors="coerce",
    ).dt.normalize()
else:
    sentiment["sentiment_availability_date"] = sentiment[
        "sentiment_asof_date"
    ]


# ----------------------------
# Technical
# ----------------------------

if "observation_date" in technical.columns:
    technical["technical_observation_date"] = pd.to_datetime(
        technical["observation_date"],
        errors="coerce",
    ).dt.normalize()
else:
    technical["technical_observation_date"] = technical["_source_date"]

if "availability_date" in technical.columns:
    technical["technical_availability_date"] = pd.to_datetime(
        technical["availability_date"],
        errors="coerce",
    ).dt.normalize()
else:
    # Conservative research-safe fallback.
    technical["technical_availability_date"] = technical[
        "technical_observation_date"
    ] + pd.Timedelta(days=1)


# ============================================================
# Normalize PIT / research metadata
# ============================================================

for frame in [macro, sentiment, technical]:
    ensure_bool(frame, "point_in_time_safe", True)
    ensure_bool(frame, "research_only", True)
    ensure_bool(frame, "decision_engine_ready", False)


# ============================================================
# Build unified calendar
# ============================================================

calendar_parts = [
    macro["macro_availability_date"].dropna(),
    sentiment["sentiment_asof_date"].dropna(),
    technical["technical_observation_date"].dropna(),
]

calendar = pd.concat(calendar_parts, ignore_index=True)

calendar = (
    pd.Series(calendar)
    .dropna()
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
# Apply explicit context cutoff
# ============================================================

as_of_date = env_as_of_date()

if as_of_date is not None:
    context = context[
        context["context_date"] <= as_of_date
    ].copy()

    if context.empty:
        fail(
            "RESEARCH_CONTEXT_AS_OF_DATE removed all context dates."
        )


# ============================================================
# Prepare Macro Context
# ============================================================

macro = macro.sort_values(
    "macro_availability_date"
).reset_index(drop=True)

# Avoid collision with unified context_date.
if "context_date" in macro.columns:
    macro = macro.drop(columns=["context_date"])

macro_keep = [
    "macro_availability_date",
    "macro_original_context_date",
]

macro_keep += [
    column
    for column in macro.columns
    if column not in macro_keep
    and column != "_source_date"
]

macro = macro[macro_keep].copy()

macro = add_prefixed_columns(
    macro,
    "macro_",
    {
        "macro_availability_date",
        "macro_original_context_date",
    },
)


# ============================================================
# Prepare Sentiment Engine
# ============================================================

sentiment = sentiment.sort_values(
    "sentiment_asof_date"
).reset_index(drop=True)

sentiment = add_prefixed_columns(
    sentiment,
    "sentiment_",
    {
        "sentiment_asof_date",
        "sentiment_availability_date",
    },
)


# ============================================================
# Prepare Technical Intelligence
# ============================================================

technical = technical.sort_values(
    "technical_observation_date"
).reset_index(drop=True)

technical = add_prefixed_columns(
    technical,
    "technical_",
    {
        "technical_observation_date",
        "technical_availability_date",
    },
)


# ============================================================
# Point-in-time reconstruction
# ============================================================

# ----------------------------
# Macro
# ----------------------------

macro = macro.sort_values(
    "macro_availability_date"
).reset_index(drop=True)

context = pd.merge_asof(
    context.sort_values("context_date"),
    macro,
    left_on="context_date",
    right_on="macro_availability_date",
    direction="backward",
    allow_exact_matches=True,
)


# ----------------------------
# Sentiment
# ----------------------------

sentiment = sentiment.sort_values(
    "sentiment_asof_date"
).reset_index(drop=True)

context = pd.merge_asof(
    context.sort_values("context_date"),
    sentiment,
    left_on="context_date",
    right_on="sentiment_asof_date",
    direction="backward",
    allow_exact_matches=True,
)


# ----------------------------
# Technical
# ----------------------------

technical = technical.sort_values(
    "technical_observation_date"
).reset_index(drop=True)

context = pd.merge_asof(
    context.sort_values("context_date"),
    technical,
    left_on="context_date",
    right_on="technical_observation_date",
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
    context["technical_observation_date"].notna()
    & (
        context["technical_observation_date"]
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
# Canonical Research Context metadata
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

for idx, row in context.iterrows():

    context_date = row["context_date"]

    # Macro
    if (
        pd.notna(row.get("macro_availability_date"))
        and row["macro_availability_date"] > context_date
    ):
        pit_failures.append(
            f"Macro lookahead at row {idx}"
        )

    # Sentiment
    if (
        pd.notna(row.get("sentiment_asof_date"))
        and row["sentiment_asof_date"] > context_date
    ):
        pit_failures.append(
            f"Sentiment lookahead at row {idx}"
        )

    # Technical
    if (
        pd.notna(row.get("technical_observation_date"))
        and row["technical_observation_date"] > context_date
    ):
        pit_failures.append(
            f"Technical lookahead at row {idx}"
        )


if pit_failures:
    fail(
        "Point-in-time / anti-lookahead validation failed:\n"
        + "\n".join(pit_failures[:20])
    )


# ============================================================
# Required column validation
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

missing = [
    column
    for column in required_columns
    if column not in context.columns
]

if missing:
    fail(
        f"Missing required output columns: {missing}"
    )


# ============================================================
# Date / duplicate validation
# ============================================================

context["context_date"] = pd.to_datetime(
    context["context_date"]
).dt.normalize()

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
# Research-only assertions
# ============================================================

if not context["point_in_time_safe"].all():
    fail("point_in_time_safe contains False.")

if not context["research_only"].all():
    fail("research_only contains False.")

if context["decision_engine_ready"].any():
    fail("decision_engine_ready must remain False.")

if context["trading_signal_generated"].any():
    fail("Trading signals must not be generated.")

if context["forecast_generated"].any():
    fail("Forecasts must not be generated.")

if context["unified_decision_generated"].any():
    fail("Unified decisions must not be generated.")


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
# Summary
# ============================================================

latest = context.iloc[-1]

summary = {
    "context_date": latest["context_date"],
    "available_layer_count": latest["available_layer_count"],
    "macro_available": latest["macro_available"],
    "sentiment_available": latest["sentiment_available"],
    "technical_available": latest["technical_available"],
    "point_in_time_safe": latest["point_in_time_safe"],
    "research_only": latest["research_only"],
    "decision_engine_ready": latest["decision_engine_ready"],
    "trading_signal_generated": latest[
        "trading_signal_generated"
    ],
    "forecast_generated": latest["forecast_generated"],
    "unified_decision_generated": latest[
        "unified_decision_generated"
    ],
}


# ============================================================
# Add useful latest-layer fields to summary
# ============================================================

summary_columns = [
    "economic_regime",
    "sentiment_research_regime",
    "technical_research_regime",
    "financial_stress_regime",
    "trend_structure",
    "unified_sentiment_score",
    "cot_sentiment_score",
    "aaii_sentiment_score",
    "vix_sentiment_score",
    "VIX",
    "Close",
    "RSI14",
    "ATR14",
    "ATR14_pct",
    "ROC20_pct",
    "drawdown_pct",
    "fed_score",
    "inflation_score",
    "labor_score",
    "growth_score",
    "financial_stress_composite",
    "treasury_2y",
    "treasury_10y",
    "yield_10y_2y_spread",
]


for column in summary_columns:

    if column in context.columns:
        summary[column] = latest[column]


summary_df = pd.DataFrame([summary])


# ============================================================
# Extremes / research context subset
# ============================================================

extreme_columns = [
    "context_date",
    "available_layer_count",
    "macro_available",
    "sentiment_available",
    "technical_available",
]

for column in [
    "economic_regime",
    "sentiment_research_regime",
    "technical_research_regime",
    "financial_stress_regime",
    "trend_structure",
]:
    if column in context.columns:
        extreme_columns.append(column)

extremes = context.copy()

extreme_mask = pd.Series(
    False,
    index=extremes.index,
)

# Sentiment extremes
if "sentiment_research_regime" in extremes.columns:
    extreme_mask |= extremes[
        "sentiment_research_regime"
    ].isin(
        [
            "EXTREME_BULLISH",
            "EXTREME_BEARISH",
        ]
    )

# Technical extremes
if "technical_research_regime" in extremes.columns:
    extreme_mask |= extremes[
        "technical_research_regime"
    ].isin(
        [
            "STRONG_BULLISH",
            "STRONG_BEARISH",
        ]
    )

# Financial stress extremes
if "financial_stress_regime" in extremes.columns:
    extreme_mask |= extremes[
        "financial_stress_regime"
    ].isin(
        [
            "EXTREME_RESEARCH_STRESS",
            "HIGH_RESEARCH_STRESS",
        ]
    )

extremes = extremes.loc[
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
# Final console validation
# ============================================================

print("=" * 70)
print("Research Context v1")
print("=" * 70)

print(f"Output: {OUTPUT_FILE}")
print(f"Rows: {len(context):,}")
print(f"Columns: {len(context.columns):,}")

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
    print("As-of cutoff: NONE")

print(
    "Latest context date:",
    latest["context_date"].date(),
)

print(
    "Latest available layers:",
    int(latest["available_layer_count"]),
)

print(
    "Macro available:",
    bool(latest["macro_available"]),
)

print(
    "Sentiment available:",
    bool(latest["sentiment_available"]),
)

print(
    "Technical available:",
    bool(latest["technical_available"]),
)

print(
    "Point-in-time safe:",
    bool(context["point_in_time_safe"].all()),
)

print(
    "Research only:",
    bool(context["research_only"].all()),
)

print(
    "Decision Engine ready:",
    bool(context["decision_engine_ready"].any()),
)

print(
    "Trading signal generated:",
    bool(context["trading_signal_generated"].any()),
)

print(
    "Forecast generated:",
    bool(context["forecast_generated"].any()),
)

print(
    "Unified decision generated:",
    bool(context["unified_decision_generated"].any()),
)

print(
    "Duplicate context dates:",
    duplicate_dates,
)

print(
    "PIT failures:",
    len(pit_failures),
)

print(
    "Extreme research rows:",
    len(extremes),
)

print("=" * 70)
print("PASS")
print("=" * 70)
