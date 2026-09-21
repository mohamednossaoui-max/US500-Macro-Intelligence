#!/usr/bin/env python3
"""
Research Context v1
===================

Purpose
-------
Combine the following research-only layers into one point-in-time-safe
US500 research context:

    1. Macro Context v1
    2. Sentiment Engine v1
    3. Technical Intelligence v1

Important
---------
This layer is RESEARCH-ONLY.

It does NOT:
    - generate trading signals
    - generate forecasts
    - generate recommendations
    - generate a unified trading decision
    - integrate with the Decision Engine

Point-in-time principles
------------------------
- Macro Context is treated as a dated snapshot.
- Sentiment Engine uses its actual `asof_date` field.
- Technical Intelligence uses its explicit `availability_date`.
- Historical context never receives information before its availability date.
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

OUTPUT_CONTEXT = Path("research_context_v1.csv")
OUTPUT_SUMMARY = Path("research_context_summary_v1.csv")
OUTPUT_EXTREMES = Path("research_context_extremes_v1.csv")


# ======================================================================
# Helpers
# ======================================================================

def fail(message: str) -> None:
    raise RuntimeError(message)


def log(message: str) -> None:
    print(message, flush=True)


def require_file(path: Path) -> None:
    if not path.exists():
        fail(f"Required input file not found: {path}")


def require_columns(
    df: pd.DataFrame,
    required: Iterable[str],
    name: str,
) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        fail(
            f"{name} is missing required columns: {missing}. "
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
            f"{name}: column `{column}` could not be parsed "
            f"as dates."
        )

    return result


def coerce_bool(value):
    if pd.isna(value):
        return np.nan

    if isinstance(value, bool):
        return value

    text = str(value).strip().lower()

    if text in {"true", "1", "yes", "y", "t"}:
        return True

    if text in {"false", "0", "no", "n", "f"}:
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
        result[column] = result[column].map(coerce_bool)
        result[column] = result[column].fillna(default)

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
    """
    Macro Context v1 is a current snapshot rather than a daily time series.

    The actual artifact has one row.

    The macro context date is treated as the date on which the snapshot
    becomes available for this research layer.
    """

    require_file(path)

    df = pd.read_csv(path)

    if df.empty:
        fail("Macro Context input is empty.")

    log(f"Macro Context input columns: {list(df.columns)}")

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

    df = df.dropna(subset=[date_column]).copy()

    if df.empty:
        fail("Macro Context has no valid dates.")

    # Rename the date used by this layer.
    df["macro_context_date"] = df[date_column]

    # For a current snapshot, availability is the snapshot date unless
    # an explicit availability date exists.
    if "availability_date" in df.columns:
        df["macro_availability_date"] = pd.to_datetime(
            df["availability_date"],
            errors="coerce",
        )
        df["macro_availability_date"] = (
            df["macro_availability_date"]
            .fillna(df["macro_context_date"])
        )
    else:
        df["macro_availability_date"] = df["macro_context_date"]

    # If there are multiple rows, keep the latest snapshot.
    df = (
        df.sort_values("macro_availability_date")
        .drop_duplicates(
            subset=["macro_availability_date"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    # The current Macro Context artifact is expected to contain one row.
    # We deliberately do not fabricate historical macro snapshots.
    return df


# ======================================================================
# Sentiment Engine
# ======================================================================

def prepare_sentiment(
    path: Path,
) -> pd.DataFrame:
    """
    Prepare the actual Sentiment Engine v1 schema.

    Actual schema observed in the artifact:

        asof_date
        cot_observation_date
        cot_availability_date
        cot_asset_manager_score
        cot_leveraged_money_score
        cot_sentiment_score
        aaii_observation_date
        aaii_availability_date
        aaii_sentiment_score
        vix_observation_date
        vix_availability_date
        vix_sentiment_score
        cot_available
        aaii_available
        vix_available
        available_component_count
        unified_sentiment_score
        research_regime
        ...
    """

    require_file(path)

    df = pd.read_csv(path)

    if df.empty:
        fail("Sentiment Engine input is empty.")

    log(f"Sentiment Engine input columns: {list(df.columns)}")

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

    df = df.dropna(subset=["asof_date"]).copy()

    # Actual field is `research_regime`.
    if "research_regime" in df.columns:
        df["sentiment_regime"] = df["research_regime"]
    else:
        df["sentiment_regime"] = np.nan

    # Preserve actual component score names while also exposing
    # normalized aliases for the unified research context.
    rename_map = {}

    if "cot_sentiment_score" in df.columns:
        rename_map["cot_sentiment_score"] = "cot_score"

    if "aaii_sentiment_score" in df.columns:
        rename_map["aaii_sentiment_score"] = "aaii_score"

    if "vix_sentiment_score" in df.columns:
        rename_map["vix_sentiment_score"] = "vix_score"

    if rename_map:
        df = df.rename(columns=rename_map)

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

    # Sentiment Engine's as-of date represents the PIT reconstructed
    # research state. It is therefore the effective availability date
    # of the already reconstructed daily state.
    df["sentiment_availability_date"] = df["asof_date"]

    # Preserve actual PIT metadata.
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
        df.sort_values("sentiment_availability_date")
        .drop_duplicates(
            subset=["sentiment_availability_date"],
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
    """
    Prepare Technical Intelligence v1.

    Actual schema includes:

        observation_date
        availability_date
        Close
        SMA20
        SMA50
        SMA200
        RSI14
        ATR14
        ATR14_pct
        ROC20_pct
        drawdown_pct
        trend_structure
        technical_regime
        ...
    """

    require_file(path)

    df = pd.read_csv(path)

    if df.empty:
        fail("Technical Intelligence input is empty.")

    log(f"Technical Intelligence input columns: {list(df.columns)}")

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

    df = df.dropna(subset=["observation_date"]).copy()

    # Explicit availability date is preferred.
    if "availability_date" in df.columns:
        df["technical_availability_date"] = pd.to_datetime(
            df["availability_date"],
            errors="coerce",
        )

        df["technical_availability_date"] = (
            df["technical_availability_date"]
            .fillna(df["observation_date"])
        )
    else:
        # Fallback only if the source does not provide availability.
        # The actual Technical artifact does provide it.
        df["technical_availability_date"] = (
            df["observation_date"]
        )

    numeric_columns = [
        "Close",
        "close",
        "SMA20",
        "SMA50",
        "SMA200",
        "EMA20",
        "EMA50",
        "RSI14",
        "ATR14",
        "ATR14_pct",
        "ROC20_pct",
        "drawdown_pct",
    ]

    df = safe_numeric(df, numeric_columns)

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
        df.sort_values("technical_availability_date")
        .drop_duplicates(
            subset=["technical_availability_date"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    return df


# ======================================================================
# Build Unified Research Context
# ======================================================================

def build_context(
    macro: pd.DataFrame,
    sentiment: pd.DataFrame,
    technical: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build a PIT-safe unified research context.

    Calendar
    --------
    We use the UNION of:
        - Technical observation dates
        - Macro snapshot availability dates
        - Sentiment as-of dates

    This is important because Macro Context is a current snapshot.
    If we used only Technical dates, the 2026-09-20 Macro snapshot would
    disappear because Technical currently ends at 2026-09-18.

    Every layer is merged using its availability date.
    """

    if technical.empty:
        fail("Technical Intelligence contains no rows.")

    if sentiment.empty:
        fail("Sentiment Engine contains no rows.")

    if macro.empty:
        fail("Macro Context contains no rows.")

    # ------------------------------------------------------------------
    # Build calendar explicitly.
    # ------------------------------------------------------------------

    technical_dates = pd.Series(
        technical["observation_date"]
        .dropna()
        .unique(),
        name="context_date",
    )

    sentiment_dates = pd.Series(
        sentiment["asof_date"]
        .dropna()
        .unique(),
        name="context_date",
    )

    macro_dates = pd.Series(
        macro["macro_availability_date"]
        .dropna()
        .unique(),
        name="context_date",
    )

    calendar = pd.concat(
        [
            technical_dates,
            sentiment_dates,
            macro_dates,
        ],
        ignore_index=True,
    )

    calendar = (
        pd.to_datetime(calendar, errors="coerce")
        .dropna()
        .drop_duplicates()
        .sort_values()
        .reset_index(drop=True)
        .to_frame()
    )

    # IMPORTANT:
    # This explicitly guarantees that `context_date` exists.
    calendar.columns = ["context_date"]

    # ------------------------------------------------------------------
    # Prepare Technical side.
    # ------------------------------------------------------------------

    technical_merge = technical.copy()

    technical_merge = technical_merge.rename(
        columns={
            "observation_date": "technical_observation_date",
        }
    )

    technical_merge = technical_merge.sort_values(
        "technical_availability_date"
    ).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Prepare Sentiment side.
    # ------------------------------------------------------------------

    sentiment_merge = sentiment.copy()

    sentiment_merge = sentiment_merge.sort_values(
        "sentiment_availability_date"
    ).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Prepare Macro side.
    # ------------------------------------------------------------------

    macro_merge = macro.copy()

    macro_merge = macro_merge.sort_values(
        "macro_availability_date"
    ).reset_index(drop=True)

    # ------------------------------------------------------------------
    # PIT merge: Technical
    # ------------------------------------------------------------------

    context = pd.merge_asof(
        calendar.sort_values("context_date"),
        technical_merge,
        left_on="context_date",
        right_on="technical_availability_date",
        direction="backward",
        allow_exact_matches=True,
    )

    # ------------------------------------------------------------------
    # PIT merge: Sentiment
    # ------------------------------------------------------------------

    context = pd.merge_asof(
        context.sort_values("context_date"),
        sentiment_merge,
        left_on="context_date",
        right_on="sentiment_availability_date",
        direction="backward",
        allow_exact_matches=True,
    )

    # ------------------------------------------------------------------
    # PIT merge: Macro
    # ------------------------------------------------------------------

    context = pd.merge_asof(
        context.sort_values("context_date"),
        macro_merge,
        left_on="context_date",
        right_on="macro_availability_date",
        direction="backward",
        allow_exact_matches=True,
    )

    # ------------------------------------------------------------------
    # Layer availability
    # ------------------------------------------------------------------

    context["technical_available"] = (
        context["technical_availability_date"].notna()
        & (
            context["technical_availability_date"]
            <= context["context_date"]
        )
    )

    context["sentiment_available"] = (
        context["sentiment_availability_date"].notna()
        & (
            context["sentiment_availability_date"]
            <= context["context_date"]
        )
    )

    context["macro_available"] = (
        context["macro_availability_date"].notna()
        & (
            context["macro_availability_date"]
            <= context["context_date"]
        )
    )

    context["available_layer_count"] = (
        context["macro_available"].astype(int)
        + context["sentiment_available"].astype(int)
        + context["technical_available"].astype(int)
    )

    # ------------------------------------------------------------------
    # PIT / anti-lookahead validation flags
    # ------------------------------------------------------------------

    context["technical_no_lookahead"] = (
        ~context["technical_available"]
        | (
            context["technical_availability_date"]
            <= context["context_date"]
        )
    )

    context["sentiment_no_lookahead"] = (
        ~context["sentiment_available"]
        | (
            context["sentiment_availability_date"]
            <= context["context_date"]
        )
    )

    context["macro_no_lookahead"] = (
        ~context["macro_available"]
        | (
            context["macro_availability_date"]
            <= context["context_date"]
        )
    )

    context["point_in_time_safe"] = (
        context["technical_no_lookahead"]
        & context["sentiment_no_lookahead"]
        & context["macro_no_lookahead"]
    )

    # ------------------------------------------------------------------
    # Research-only controls
    # ------------------------------------------------------------------

    context["research_only"] = True
    context["decision_engine_ready"] = False
    context["trading_signal_generated"] = False
    context["forecast_generated"] = False
    context["unified_decision_generated"] = False

    # ------------------------------------------------------------------
    # Sort explicitly by context_date.
    #
    # This is the line that previously failed. We now guarantee the
    # column exists from the calendar construction above.
    # ------------------------------------------------------------------

    context = context.sort_values(
        "context_date"
    ).reset_index(drop=True)

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
        fail("Research Context output is empty.")

    if context["context_date"].isna().any():
        fail("Research Context contains null context_date values.")

    if not context["context_date"].is_monotonic_increasing:
        fail("Research Context is not sorted by context_date.")

    if context["context_date"].duplicated().any():
        fail("Research Context contains duplicate context_date values.")

    # No lookahead.
    if not bool(context["point_in_time_safe"].all()):
        bad = context.loc[
            ~context["point_in_time_safe"],
            ["context_date"],
        ].head(10)

        fail(
            "PIT validation failed. Example rows:\n"
            f"{bad.to_string(index=False)}"
        )

    # Research-only controls.
    if not bool(context["research_only"].all()):
        fail("research_only must be True for every row.")

    if bool(context["decision_engine_ready"].any()):
        fail("decision_engine_ready must remain False.")

    if bool(context["trading_signal_generated"].any()):
        fail("trading_signal_generated must remain False.")

    if bool(context["forecast_generated"].any()):
        fail("forecast_generated must remain False.")

    if bool(context["unified_decision_generated"].any()):
        fail("unified_decision_generated must remain False.")

    # Layer count sanity.
    if (
        context["available_layer_count"]
        .dropna()
        .lt(0)
        .any()
    ):
        fail("available_layer_count cannot be negative.")

    if (
        context["available_layer_count"]
        .dropna()
        .gt(3)
        .any()
    ):
        fail("available_layer_count cannot exceed 3.")

    # Explicit anti-lookahead checks where availability dates exist.
    for availability_column in [
        "macro_availability_date",
        "sentiment_availability_date",
        "technical_availability_date",
    ]:
        if availability_column in context.columns:
            available_rows = context[availability_column].notna()

            bad = (
                available_rows
                & (
                    context[availability_column]
                    > context["context_date"]
                )
            )

            if bool(bad.any()):
                fail(
                    f"Lookahead detected in {availability_column}."
                )


# ======================================================================
# Summary
# ======================================================================

def create_summary(
    context: pd.DataFrame,
) -> pd.DataFrame:
    """
    Create a compact summary artifact.

    This remains descriptive only.
    """

    latest = context.iloc[-1]

    summary = {
        "context_date": latest.get("context_date"),
        "available_layer_count": latest.get(
            "available_layer_count"
        ),
        "macro_available": latest.get(
            "macro_available"
        ),
        "sentiment_available": latest.get(
            "sentiment_available"
        ),
        "technical_available": latest.get(
            "technical_available"
        ),
        "point_in_time_safe": latest.get(
            "point_in_time_safe"
        ),
        "research_only": latest.get(
            "research_only"
        ),
        "decision_engine_ready": latest.get(
            "decision_engine_ready"
        ),
        "trading_signal_generated": latest.get(
            "trading_signal_generated"
        ),
        "forecast_generated": latest.get(
            "forecast_generated"
        ),
        "unified_decision_generated": latest.get(
            "unified_decision_generated"
        ),
    }

    # Add latest research regimes when available.
    optional_latest_fields = [
        "economic_regime",
        "sentiment_regime",
        "technical_regime",
        "trend_structure",
        "unified_sentiment_score",
        "cot_score",
        "aaii_score",
        "vix_score",
        "VIX",
        "Close",
        "RSI14",
        "ATR14",
        "ATR14_pct",
        "ROC20_pct",
        "drawdown_pct",
    ]

    for field in optional_latest_fields:
        if field in context.columns:
            summary[field] = latest.get(field)

    return pd.DataFrame([summary])


# ======================================================================
# Extremes / Research States
# ======================================================================

def create_extremes(
    context: pd.DataFrame,
) -> pd.DataFrame:
    """
    Create descriptive extreme/research-state rows.

    No trading interpretation is assigned here.
    """

    frames = []

    # Sentiment extreme states.
    if "sentiment_regime" in context.columns:
        mask = context["sentiment_regime"].astype(str).isin(
            [
                "EXTREME_BULLISH",
                "EXTREME_BEARISH",
            ]
        )

        if bool(mask.any()):
            temp = context.loc[
                mask
            ].copy()

            temp["extreme_type"] = "SENTIMENT"

            frames.append(temp)

    # Technical extreme states.
    if "technical_regime" in context.columns:
        mask = context["technical_regime"].astype(str).isin(
            [
                "STRONG_BULLISH",
                "STRONG_BEARISH",
            ]
        )

        if bool(mask.any()):
            temp = context.loc[
                mask
            ].copy()

            temp["extreme_type"] = "TECHNICAL"

            frames.append(temp)

    # If nothing qualifies, create an empty artifact with a stable schema.
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

    return result.sort_values(
        "context_date"
    ).reset_index(drop=True)


# ======================================================================
# Main
# ======================================================================

def main() -> None:

    print("=" * 70)
    print("Research Context v1")
    print("=" * 70)

    # --------------------------------------------------------------
    # Load
    # --------------------------------------------------------------

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
        f"Macro Context: {len(macro):,} rows"
    )

    print(
        f"Sentiment Engine: {len(sentiment):,} rows"
    )

    print(
        f"Technical Intelligence: {len(technical):,} rows"
    )

    # --------------------------------------------------------------
    # Build
    # --------------------------------------------------------------

    context = build_context(
        macro=macro,
        sentiment=sentiment,
        technical=technical,
    )

    print(
        f"Research Context rows: {len(context):,}"
    )

    # --------------------------------------------------------------
    # Validate
    # --------------------------------------------------------------

    validate_context(
        context
    )

    # --------------------------------------------------------------
    # Save main artifact
    # --------------------------------------------------------------

    context.to_csv(
        OUTPUT_CONTEXT,
        index=False,
    )

    # --------------------------------------------------------------
    # Save summary
    # --------------------------------------------------------------

    summary = create_summary(
        context
    )

    summary.to_csv(
        OUTPUT_SUMMARY,
        index=False,
    )

    # --------------------------------------------------------------
    # Save extremes
    # --------------------------------------------------------------

    extremes = create_extremes(
        context
    )

    extremes.to_csv(
        OUTPUT_EXTREMES,
        index=False,
    )

    # --------------------------------------------------------------
    # Latest state
    # --------------------------------------------------------------

    latest = context.iloc[-1]

    print()
    print("=" * 70)
    print("Latest Research Context")
    print("=" * 70)

    print(
        f"Context date: "
        f"{latest['context_date'].date()}"
    )

    print(
        f"Available layers: "
        f"{int(latest['available_layer_count'])}/3"
    )

    print(
        f"Macro available: "
        f"{latest['macro_available']}"
    )

    print(
        f"Sentiment available: "
        f"{latest['sentiment_available']}"
    )

    print(
        f"Technical available: "
        f"{latest['technical_available']}"
    )

    if "economic_regime" in context.columns:
        print(
            f"Economic regime: "
            f"{latest['economic_regime']}"
        )

    if "sentiment_regime" in context.columns:
        print(
            f"Sentiment regime: "
            f"{latest['sentiment_regime']}"
        )

    if "technical_regime" in context.columns:
        print(
            f"Technical regime: "
            f"{latest['technical_regime']}"
        )

    if "unified_sentiment_score" in context.columns:
        value = latest["unified_sentiment_score"]

        if pd.notna(value):
            print(
                f"Unified sentiment score: "
                f"{float(value):.4f}"
            )

    print(
        f"Point-in-time safe: "
        f"{latest['point_in_time_safe']}"
    )

    print(
        f"Research-only: "
        f"{latest['research_only']}"
    )

    print(
        f"Decision Engine ready: "
        f"{latest['decision_engine_ready']}"
    )

    print(
        f"Trading signal generated: "
        f"{latest['trading_signal_generated']}"
    )

    print(
        f"Forecast generated: "
        f"{latest['forecast_generated']}"
    )

    print(
        f"Unified decision generated: "
        f"{latest['unified_decision_generated']}"
    )

    print()
    print("=" * 70)
    print("Output files")
    print("=" * 70)

    print(OUTPUT_CONTEXT)
    print(OUTPUT_SUMMARY)
    print(OUTPUT_EXTREMES)

    print()
    print("Research Context v1 PASS")


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
