#!/usr/bin/env python3

"""
Research Context v1

Combines:
    - Macro Context v1
    - Sentiment Engine v1
    - Technical Intelligence v1

Research-only.
No:
    - trading signal
    - forecast
    - recommendation
    - Decision Engine integration
    - unified trading decision
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd


# ======================================================================
# Configuration
# ======================================================================

MACRO_INPUT = Path(
    os.getenv(
        "MACRO_CONTEXT_INPUT",
        "context_input/macro_context_v1.csv",
    )
)

SENTIMENT_INPUT = Path(
    os.getenv(
        "SENTIMENT_ENGINE_INPUT",
        "context_input/sentiment_engine_research_v1.csv",
    )
)

TECHNICAL_INPUT = Path(
    os.getenv(
        "TECHNICAL_INTELLIGENCE_INPUT",
        "context_input/technical_intelligence_research_v1.csv",
    )
)

OUTPUT_CONTEXT = Path(
    "research_context_v1.csv"
)

OUTPUT_SUMMARY = Path(
    "research_context_summary_v1.csv"
)

OUTPUT_EXTREMES = Path(
    "research_context_extremes_v1.csv"
)


# ======================================================================
# Helpers
# ======================================================================

def fail(message: str) -> None:
    raise RuntimeError(message)


def require_file(path: Path) -> None:
    if not path.exists():
        fail(f"Required input file not found: {path}")


def require_columns(
    df: pd.DataFrame,
    required: Iterable[str],
    name: str,
) -> None:

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        fail(
            f"{name} is missing required columns: "
            f"{missing}. "
            f"Available columns: {list(df.columns)}"
        )


def first_existing(
    df: pd.DataFrame,
    candidates: Iterable[str],
) -> Optional[str]:

    for column in candidates:
        if column in df.columns:
            return column

    return None


def to_datetime_column(
    df: pd.DataFrame,
    column: str,
    name: str,
) -> pd.DataFrame:

    result = df.copy()

    result[column] = pd.to_datetime(
        result[column],
        errors="coerce",
    )

    if result[column].isna().all():
        fail(
            f"{name}: column `{column}` "
            f"could not be parsed as dates."
        )

    return result


def coerce_bool(value):

    if pd.isna(value):
        return np.nan

    if isinstance(value, bool):
        return value

    text = str(value).strip().lower()

    if text in {
        "true",
        "1",
        "yes",
        "y",
        "t",
    }:
        return True

    if text in {
        "false",
        "0",
        "no",
        "n",
        "f",
    }:
        return False

    return np.nan


def add_boolean_column(
    df: pd.DataFrame,
    column: str,
    default: bool,
) -> pd.DataFrame:

    result = df.copy()

    if column not in result.columns:
        result[column] = default

    else:
        result[column] = (
            result[column]
            .map(coerce_bool)
            .fillna(default)
        )

    return result


def safe_numeric(
    df: pd.DataFrame,
    columns: Iterable[str],
) -> pd.DataFrame:

    result = df.copy()

    for column in columns:

        if column in result.columns:

            result[column] = pd.to_numeric(
                result[column],
                errors="coerce",
            )

    return result


# ======================================================================
# Macro Context
# ======================================================================

def prepare_macro(
    path: Path,
) -> pd.DataFrame:

    require_file(path)

    df = pd.read_csv(path)

    if df.empty:
        fail("Macro Context input is empty.")

    print(
        "Macro Context input columns:",
        list(df.columns),
    )

    date_column = first_existing(
        df,
        [
            "context_date",
            "asof_date",
            "observation_date",
            "availability_date",
            "date",
        ],
    )

    if date_column is None:

        fail(
            "Could not identify Macro Context date column. "
            f"Available columns: {list(df.columns)}"
        )

    df = to_datetime_column(
        df,
        date_column,
        "Macro Context",
    )

    df = df.dropna(
        subset=[date_column]
    ).copy()

    if df.empty:
        fail(
            "Macro Context has no valid dates."
        )

    # Keep the real macro snapshot date.
    df["macro_context_date"] = (
        df[date_column]
    )

    # Explicit availability if available.
    if "availability_date" in df.columns:

        df["macro_availability_date"] = (
            pd.to_datetime(
                df["availability_date"],
                errors="coerce",
            )
        )

        df["macro_availability_date"] = (
            df["macro_availability_date"]
            .fillna(
                df["macro_context_date"]
            )
        )

    else:

        df["macro_availability_date"] = (
            df["macro_context_date"]
        )

    # VERY IMPORTANT:
    #
    # Macro Context already contains `context_date`.
    # Rename it before merge_asof so it can never collide with
    # the unified context calendar.
    if "context_date" in df.columns:

        df = df.rename(
            columns={
                "context_date":
                    "macro_original_context_date"
            }
        )

    df = (
        df.sort_values(
            "macro_availability_date"
        )
        .drop_duplicates(
            subset=[
                "macro_availability_date"
            ],
            keep="last",
        )
        .reset_index(drop=True)
    )

    return df


# ======================================================================
# Sentiment Engine
# ======================================================================

def prepare_sentiment(
    path: Path,
) -> pd.DataFrame:

    require_file(path)

    df = pd.read_csv(path)

    if df.empty:
        fail(
            "Sentiment Engine input is empty."
        )

    print(
        "Sentiment Engine input columns:",
        list(df.columns),
    )

    require_columns(
        df,
        ["asof_date"],
        "Sentiment Engine",
    )

    df = to_datetime_column(
        df,
        "asof_date",
        "Sentiment Engine",
    )

    df = df.dropna(
        subset=["asof_date"]
    ).copy()

    # Actual artifact uses research_regime.
    if "research_regime" in df.columns:

        df["sentiment_regime"] = (
            df["research_regime"]
        )

    else:

        df["sentiment_regime"] = np.nan

    # Normalize actual score names.
    rename_map = {}

    if "cot_sentiment_score" in df.columns:

        rename_map[
            "cot_sentiment_score"
        ] = "cot_score"

    if "aaii_sentiment_score" in df.columns:

        rename_map[
            "aaii_sentiment_score"
        ] = "aaii_score"

    if "vix_sentiment_score" in df.columns:

        rename_map[
            "vix_sentiment_score"
        ] = "vix_score"

    if rename_map:

        df = df.rename(
            columns=rename_map
        )

    if "unified_sentiment_score" not in df.columns:

        df["unified_sentiment_score"] = np.nan

    if "available_component_count" not in df.columns:

        df["available_component_count"] = np.nan

    df = safe_numeric(
        df,
        [
            "cot_score",
            "aaii_score",
            "vix_score",
            "unified_sentiment_score",
            "available_component_count",
        ],
    )

    # Sentiment Engine has already reconstructed its state
    # point-in-time using as-of dates.
    df["sentiment_availability_date"] = (
        df["asof_date"]
    )

    df = add_boolean_column(
        df,
        "point_in_time_safe",
        True,
    )

    df = add_boolean_column(
        df,
        "research_only",
        True,
    )

    df = add_boolean_column(
        df,
        "decision_engine_ready",
        False,
    )

    df = add_boolean_column(
        df,
        "trading_signal_generated",
        False,
    )

    df = add_boolean_column(
        df,
        "forecast_generated",
        False,
    )

    df = (
        df.sort_values(
            "sentiment_availability_date"
        )
        .drop_duplicates(
            subset=[
                "sentiment_availability_date"
            ],
            keep="last",
        )
        .reset_index(drop=True)
    )

    return df


# ======================================================================
# Technical Intelligence
# ======================================================================

def prepare_technical(
    path: Path,
) -> pd.DataFrame:

    require_file(path)

    df = pd.read_csv(path)

    if df.empty:
        fail(
            "Technical Intelligence input is empty."
        )

    print(
        "Technical Intelligence input columns:",
        list(df.columns),
    )

    require_columns(
        df,
        ["observation_date"],
        "Technical Intelligence",
    )

    df = to_datetime_column(
        df,
        "observation_date",
        "Technical Intelligence",
    )

    df = df.dropna(
        subset=["observation_date"]
    ).copy()

    if "availability_date" in df.columns:

        df["technical_availability_date"] = (
            pd.to_datetime(
                df["availability_date"],
                errors="coerce",
            )
        )

        df["technical_availability_date"] = (
            df[
                "technical_availability_date"
            ].fillna(
                df["observation_date"]
            )
        )

    else:

        df["technical_availability_date"] = (
            df["observation_date"]
        )

    df = safe_numeric(
        df,
        [
            "Close",
            "Open",
            "High",
            "Low",
            "Volume",
            "SMA20",
            "SMA50",
            "SMA200",
            "EMA20",
            "EMA50",
            "RSI14",
            "ROC20_pct",
            "ATR14",
            "ATR14_pct",
            "drawdown_pct",
        ],
    )

    if "technical_regime" not in df.columns:

        df["technical_regime"] = np.nan

    if "trend_structure" not in df.columns:

        df["trend_structure"] = np.nan

    df = add_boolean_column(
        df,
        "point_in_time_safe",
        True,
    )

    df = add_boolean_column(
        df,
        "research_only",
        True,
    )

    df = add_boolean_column(
        df,
        "decision_engine_ready",
        False,
    )

    df = add_boolean_column(
        df,
        "trading_signal_generated",
        False,
    )

    df = add_boolean_column(
        df,
        "forecast_generated",
        False,
    )

    df = (
        df.sort_values(
            "technical_availability_date"
        )
        .drop_duplicates(
            subset=[
                "technical_availability_date"
            ],
            keep="last",
        )
        .reset_index(drop=True)
    )

    return df


# ======================================================================
# Build Context
# ======================================================================

def build_context(
    macro: pd.DataFrame,
    sentiment: pd.DataFrame,
    technical: pd.DataFrame,
) -> pd.DataFrame:

    if macro.empty:
        fail(
            "Macro Context contains no rows."
        )

    if sentiment.empty:
        fail(
            "Sentiment Engine contains no rows."
        )

    if technical.empty:
        fail(
            "Technical Intelligence contains no rows."
        )

    # ------------------------------------------------------------------
    # Create independent date series.
    # ------------------------------------------------------------------

    technical_dates = pd.Series(
        technical[
            "observation_date"
        ].dropna().unique(),
        name="context_date",
    )

    sentiment_dates = pd.Series(
        sentiment[
            "asof_date"
        ].dropna().unique(),
        name="context_date",
    )

    macro_dates = pd.Series(
        macro[
            "macro_availability_date"
        ].dropna().unique(),
        name="context_date",
    )

    # ------------------------------------------------------------------
    # UNION calendar.
    # ------------------------------------------------------------------

    calendar = pd.concat(
        [
            technical_dates,
            sentiment_dates,
            macro_dates,
        ],
        ignore_index=True,
    )

    calendar = pd.to_datetime(
        calendar,
        errors="coerce",
    )

    calendar = (
        pd.Series(calendar)
        .dropna()
        .drop_duplicates()
        .sort_values()
        .reset_index(drop=True)
        .to_frame(
            name="context_date"
        )
    )

    # Explicit final guarantee.
    calendar["context_date"] = pd.to_datetime(
        calendar["context_date"],
        errors="coerce",
    )

    if "context_date" not in calendar.columns:

        fail(
            "Internal error: context_date was not created."
        )

    # ------------------------------------------------------------------
    # Technical merge frame.
    # ------------------------------------------------------------------

    technical_merge = (
        technical.copy()
        .rename(
            columns={
                "observation_date":
                    "technical_observation_date"
            }
        )
    )

    technical_merge = (
        technical_merge
        .sort_values(
            "technical_availability_date"
        )
        .reset_index(drop=True)
    )

    # ------------------------------------------------------------------
    # Sentiment merge frame.
    # ------------------------------------------------------------------

    sentiment_merge = (
        sentiment.copy()
        .sort_values(
            "sentiment_availability_date"
        )
        .reset_index(drop=True)
    )

    # ------------------------------------------------------------------
    # Macro merge frame.
    #
    # IMPORTANT:
    # `context_date` was already renamed to
    # `macro_original_context_date` in prepare_macro().
    # Therefore merge_asof cannot overwrite the unified
    # context_date column.
    # ------------------------------------------------------------------

    macro_merge = (
        macro.copy()
        .sort_values(
            "macro_availability_date"
        )
        .reset_index(drop=True)
    )

    # ------------------------------------------------------------------
    # Merge Technical.
    # ------------------------------------------------------------------

    context = pd.merge_asof(
        calendar.sort_values(
            "context_date"
        ),
        technical_merge,
        left_on="context_date",
        right_on="technical_availability_date",
        direction="backward",
        allow_exact_matches=True,
    )

    # ------------------------------------------------------------------
    # Merge Sentiment.
    # ------------------------------------------------------------------

    context = pd.merge_asof(
        context.sort_values(
            "context_date"
        ),
        sentiment_merge,
        left_on="context_date",
        right_on="sentiment_availability_date",
        direction="backward",
        allow_exact_matches=True,
    )

    # ------------------------------------------------------------------
    # Merge Macro.
    # ------------------------------------------------------------------

    context = pd.merge_asof(
        context.sort_values(
            "context_date"
        ),
        macro_merge,
        left_on="context_date",
        right_on="macro_availability_date",
        direction="backward",
        allow_exact_matches=True,
    )

    # ------------------------------------------------------------------
    # Safety check immediately after merges.
    # ------------------------------------------------------------------

    if "context_date" not in context.columns:

        fail(
            "Internal error: context_date disappeared "
            "during merge operations."
        )

    context["context_date"] = pd.to_datetime(
        context["context_date"],
        errors="coerce",
    )

    # ------------------------------------------------------------------
    # Layer availability.
    # ------------------------------------------------------------------

    context["technical_available"] = (
        context[
            "technical_availability_date"
        ].notna()
        &
        (
            context[
                "technical_availability_date"
            ]
            <= context["context_date"]
        )
    )

    context["sentiment_available"] = (
        context[
            "sentiment_availability_date"
        ].notna()
        &
        (
            context[
                "sentiment_availability_date"
            ]
            <= context["context_date"]
        )
    )

    context["macro_available"] = (
        context[
            "macro_availability_date"
        ].notna()
        &
        (
            context[
                "macro_availability_date"
            ]
            <= context["context_date"]
        )
    )

    # ------------------------------------------------------------------
    # Count available layers.
    # ------------------------------------------------------------------

    context["available_layer_count"] = (
        context[
            "macro_available"
        ].astype(int)

        +

        context[
            "sentiment_available"
        ].astype(int)

        +

        context[
            "technical_available"
        ].astype(int)
    )

    # ------------------------------------------------------------------
    # Anti-lookahead.
    # ------------------------------------------------------------------

    context["technical_no_lookahead"] = (
        ~context["technical_available"]
        |
        (
            context[
                "technical_availability_date"
            ]
            <= context["context_date"]
        )
    )

    context["sentiment_no_lookahead"] = (
        ~context["sentiment_available"]
        |
        (
            context[
                "sentiment_availability_date"
            ]
            <= context["context_date"]
        )
    )

    context["macro_no_lookahead"] = (
        ~context["macro_available"]
        |
        (
            context[
                "macro_availability_date"
            ]
            <= context["context_date"]
        )
    )

    context["point_in_time_safe"] = (
        context[
            "technical_no_lookahead"
        ]
        &
        context[
            "sentiment_no_lookahead"
        ]
        &
        context[
            "macro_no_lookahead"
        ]
    )

    # ------------------------------------------------------------------
    # Research-only controls.
    # ------------------------------------------------------------------

    context["research_only"] = True

    context["decision_engine_ready"] = False

    context["trading_signal_generated"] = False

    context["forecast_generated"] = False

    context["unified_decision_generated"] = False

    # ------------------------------------------------------------------
    # Final sort.
    # ------------------------------------------------------------------

    context = (
        context
        .sort_values(
            "context_date"
        )
        .reset_index(drop=True)
    )

    return context


# ======================================================================
# Validation
# ======================================================================

def validate_context(
    context: pd.DataFrame,
) -> None:

    required = [
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

    require_columns(
        context,
        required,
        "Research Context",
    )

    if context.empty:

        fail(
            "Research Context output is empty."
        )

    if context["context_date"].isna().any():

        fail(
            "Research Context contains "
            "null context_date values."
        )

    if not context[
        "context_date"
    ].is_monotonic_increasing:

        fail(
            "Research Context is not sorted "
            "by context_date."
        )

    if context[
        "context_date"
    ].duplicated().any():

        fail(
            "Research Context contains "
            "duplicate context_date values."
        )

    # PIT.
    if not bool(
        context[
            "point_in_time_safe"
        ].all()
    ):

        bad = context.loc[
            ~context[
                "point_in_time_safe"
            ],
            ["context_date"],
        ].head(10)

        fail(
            "PIT validation failed.\n"
            f"{bad.to_string(index=False)}"
        )

    # Research-only.
    if not bool(
        context[
            "research_only"
        ].all()
    ):

        fail(
            "research_only must be True "
            "for every row."
        )

    if bool(
        context[
            "decision_engine_ready"
        ].any()
    ):

        fail(
            "decision_engine_ready must "
            "remain False."
        )

    if bool(
        context[
            "trading_signal_generated"
        ].any()
    ):

        fail(
            "trading_signal_generated must "
            "remain False."
        )

    if bool(
        context[
            "forecast_generated"
        ].any()
    ):

        fail(
            "forecast_generated must "
            "remain False."
        )

    if bool(
        context[
            "unified_decision_generated"
        ].any()
    ):

        fail(
            "unified_decision_generated must "
            "remain False."
        )

    # Layer count.
    if (
        context[
            "available_layer_count"
        ]
        .dropna()
        .lt(0)
        .any()
    ):

        fail(
            "available_layer_count cannot "
            "be negative."
        )

    if (
        context[
            "available_layer_count"
        ]
        .dropna()
        .gt(3)
        .any()
    ):

        fail(
            "available_layer_count cannot "
            "exceed 3."
        )

    # Explicit lookahead validation.
    for column in [
        "macro_availability_date",
        "sentiment_availability_date",
        "technical_availability_date",
    ]:

        if column not in context.columns:
            continue

        available = context[
            column
        ].notna()

        bad = (
            available
            &
            (
                context[column]
                > context["context_date"]
            )
        )

        if bool(bad.any()):

            fail(
                f"Lookahead detected in {column}."
            )


# ======================================================================
# Summary
# ======================================================================

def create_summary(
    context: pd.DataFrame,
) -> pd.DataFrame:

    latest = context.iloc[-1]

    summary = {
        "context_date":
            latest["context_date"],

        "available_layer_count":
            latest["available_layer_count"],

        "macro_available":
            latest["macro_available"],

        "sentiment_available":
            latest["sentiment_available"],

        "technical_available":
            latest["technical_available"],

        "point_in_time_safe":
            latest["point_in_time_safe"],

        "research_only":
            latest["research_only"],

        "decision_engine_ready":
            latest["decision_engine_ready"],

        "trading_signal_generated":
            latest["trading_signal_generated"],

        "forecast_generated":
            latest["forecast_generated"],

        "unified_decision_generated":
            latest["unified_decision_generated"],
    }

    optional = [
        "economic_regime",
        "sentiment_regime",
        "technical_regime",
        "financial_stress_regime",
        "trend_structure",
        "unified_sentiment_score",
        "cot_score",
        "aaii_score",
        "vix_score",
        "vix",
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

    for column in optional:

        if column in context.columns:

            summary[column] = (
                latest[column]
            )

    return pd.DataFrame(
        [summary]
    )


# ======================================================================
# Extremes
# ======================================================================

def create_extremes(
    context: pd.DataFrame,
) -> pd.DataFrame:

    frames = []

    if "sentiment_regime" in context.columns:

        mask = (
            context[
                "sentiment_regime"
            ]
            .astype(str)
            .isin(
                [
                    "EXTREME_BULLISH",
                    "EXTREME_BEARISH",
                ]
            )
        )

        if bool(mask.any()):

            temp = context.loc[
                mask
            ].copy()

            temp[
                "extreme_type"
            ] = "SENTIMENT"

            frames.append(temp)

    if "technical_regime" in context.columns:

        mask = (
            context[
                "technical_regime"
            ]
            .astype(str)
            .isin(
                [
                    "STRONG_BULLISH",
                    "STRONG_BEARISH",
                ]
            )
        )

        if bool(mask.any()):

            temp = context.loc[
                mask
            ].copy()

            temp[
                "extreme_type"
            ] = "TECHNICAL"

            frames.append(temp)

    if not frames:

        return pd.DataFrame(
            columns=[
                "context_date",
                "extreme_type",
            ]
        )

    result = pd.concat(
        frames,
        ignore_index=True,
    )

    return (
        result
        .sort_values(
            "context_date"
        )
        .reset_index(drop=True)
    )


# ======================================================================
# Main
# ======================================================================

def main() -> None:

    print("=" * 70)
    print("Research Context v1")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Load layers.
    # ------------------------------------------------------------------

    macro = prepare_macro(
        MACRO_INPUT
    )

    sentiment = prepare_sentiment(
        SENTIMENT_INPUT
    )

    technical = prepare_technical(
        TECHNICAL_INPUT
    )

    print(
        f"Macro Context: "
        f"{len(macro):,} rows"
    )

    print(
        f"Sentiment Engine: "
        f"{len(sentiment):,} rows"
    )

    print(
        f"Technical Intelligence: "
        f"{len(technical):,} rows"
    )

    # ------------------------------------------------------------------
    # Build.
    # ------------------------------------------------------------------

    context = build_context(
        macro=macro,
        sentiment=sentiment,
        technical=technical,
    )

    print(
        f"Research Context: "
        f"{len(context):,} rows"
    )

    # ------------------------------------------------------------------
    # Validate.
    # ------------------------------------------------------------------

    validate_context(
        context
    )

    # ------------------------------------------------------------------
    # Save.
    # ------------------------------------------------------------------

    context.to_csv(
        OUTPUT_CONTEXT,
        index=False,
    )

    summary = create_summary(
        context
    )

    summary.to_csv(
        OUTPUT_SUMMARY,
        index=False,
    )

    extremes = create_extremes(
        context
    )

    extremes.to_csv(
        OUTPUT_EXTREMES,
        index=False,
    )

    # ------------------------------------------------------------------
    # Latest state.
    # ------------------------------------------------------------------

    latest = context.iloc[-1]

    print()
    print("=" * 70)
    print("Latest Research Context")
    print("=" * 70)

    print(
        "Context date:",
        latest["context_date"].date(),
    )

    print(
        "Available layers:",
        int(
            latest[
                "available_layer_count"
            ]
        ),
        "/3",
    )

    print(
        "Macro available:",
        latest[
            "macro_available"
        ],
    )

    print(
        "Sentiment available:",
        latest[
            "sentiment_available"
        ],
    )

    print(
        "Technical available:",
        latest[
            "technical_available"
        ],
    )

    if "economic_regime" in context.columns:

        print(
            "Economic regime:",
            latest[
                "economic_regime"
            ],
        )

    if "financial_stress_regime" in context.columns:

        print(
            "Financial stress regime:",
            latest[
                "financial_stress_regime"
            ],
        )

    if "sentiment_regime" in context.columns:

        print(
            "Sentiment regime:",
            latest[
                "sentiment_regime"
            ],
        )

    if "technical_regime" in context.columns:

        print(
            "Technical regime:",
            latest[
                "technical_regime"
            ],
        )

    if "unified_sentiment_score" in context.columns:

        value = latest[
            "unified_sentiment_score"
        ]

        if pd.notna(value):

            print(
                "Unified sentiment score:",
                f"{float(value):.4f}",
            )

    if "Close" in context.columns:

        value = latest["Close"]

        if pd.notna(value):

            print(
                "US500 Close:",
                f"{float(value):.2f}",
            )

    if "RSI14" in context.columns:

        value = latest["RSI14"]

        if pd.notna(value):

            print(
                "RSI14:",
                f"{float(value):.2f}",
            )

    if "VIX" in context.columns:

        value = latest["VIX"]

        if pd.notna(value):

            print(
                "VIX:",
                f"{float(value):.2f}",
            )

    elif "vix" in context.columns:

        value = latest["vix"]

        if pd.notna(value):

            print(
                "VIX:",
                f"{float(value):.2f}",
            )

    print(
        "Point-in-time safe:",
        latest[
            "point_in_time_safe"
        ],
    )

    print(
        "Research-only:",
        latest[
            "research_only"
        ],
    )

    print(
        "Decision Engine ready:",
        latest[
            "decision_engine_ready"
        ],
    )

    print(
        "Trading signal generated:",
        latest[
            "trading_signal_generated"
        ],
    )

    print(
        "Forecast generated:",
        latest[
            "forecast_generated"
        ],
    )

    print(
        "Unified decision generated:",
        latest[
            "unified_decision_generated"
        ],
    )

    print()
    print("=" * 70)
    print("Output files")
    print("=" * 70)

    print(
        OUTPUT_CONTEXT
    )

    print(
        OUTPUT_SUMMARY
    )

    print(
        OUTPUT_EXTREMES
    )

    print()
    print(
        "Research Context v1 PASS"
    )


if __name__ == "__main__":

    try:

        main()

    except Exception as exc:

        print(
            f"Error: {exc}",
            file=sys.stderr,
            flush=True,
        )

        raise
