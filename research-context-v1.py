import os
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# Research Context v1
# Unified research-only context layer
# ============================================================

OUTPUT_DIR = Path(".")

MACRO_FILE = Path(
    os.getenv(
        "MACRO_CONTEXT_FILE",
        "macro_context_v1.csv"
    )
)

SENTIMENT_FILE = Path(
    os.getenv(
        "SENTIMENT_ENGINE_FILE",
        "sentiment_engine_research_v1.csv"
    )
)

TECHNICAL_FILE = Path(
    os.getenv(
        "TECHNICAL_INTELLIGENCE_FILE",
        "technical_intelligence_research_v1.csv"
    )
)

OUTPUT_FILE = (
    OUTPUT_DIR /
    "research_context_v1.csv"
)

SUMMARY_FILE = (
    OUTPUT_DIR /
    "research_context_summary_v1.csv"
)

EXTREMES_FILE = (
    OUTPUT_DIR /
    "research_context_extremes_v1.csv"
)


# ============================================================
# Helpers
# ============================================================

def fail(message: str):
    raise RuntimeError(message)


def read_csv_required(path: Path, name: str) -> pd.DataFrame:

    if not path.exists():
        fail(
            f"{name} file not found: {path}"
        )

    df = pd.read_csv(path)

    if df.empty:
        fail(
            f"{name} file is empty: {path}"
        )

    print(
        f"{name}: {len(df):,} rows"
    )

    return df


def find_date_column(
    df: pd.DataFrame,
    preferred=None
) -> str:

    if preferred:
        for column in preferred:
            if column in df.columns:
                return column

    candidates = [
        "observation_date",
        "context_date",
        "as_of_date",
        "date",
    ]

    for column in candidates:
        if column in df.columns:
            return column

    fail(
        "Could not identify a date column. "
        f"Available columns: {list(df.columns)}"
    )


def prepare_dates(
    df: pd.DataFrame,
    name: str
) -> pd.DataFrame:

    result = df.copy()

    observation_column = find_date_column(
        result,
        [
            "observation_date",
            "context_date",
            "as_of_date",
            "date",
        ],
    )

    result["_observation_date"] = pd.to_datetime(
        result[observation_column],
        errors="coerce"
    )

    if result["_observation_date"].isna().all():
        fail(
            f"{name}: no valid dates found."
        )

    result = result.dropna(
        subset=["_observation_date"]
    )

    result = (
        result
        .sort_values("_observation_date")
        .drop_duplicates(
            "_observation_date",
            keep="last"
        )
        .reset_index(drop=True)
    )

    return result


def find_availability_column(
    df: pd.DataFrame
) -> str | None:

    candidates = [
        "availability_date",
        "context_availability_date",
    ]

    for column in candidates:
        if column in df.columns:
            return column

    return None


# ============================================================
# Macro preparation
# ============================================================

def prepare_macro(df: pd.DataFrame) -> pd.DataFrame:

    df = prepare_dates(
        df,
        "Macro Context"
    )

    availability_column = find_availability_column(
        df
    )

    if availability_column:
        df["_availability_date"] = pd.to_datetime(
            df[availability_column],
            errors="coerce"
        )
    else:
        # Macro Context v1 is already a PIT-safe context
        # snapshot. Use its observation/context date as the
        # conservative alignment date.
        df["_availability_date"] = (
            df["_observation_date"]
        )

    rename_map = {}

    possible_columns = {
        "economic_regime": [
            "economic_regime",
        ],
        "inflation_score": [
            "inflation_score",
        ],
        "labor_score": [
            "labor_score",
        ],
        "growth_score": [
            "growth_score",
        ],
        "financial_stress_regime": [
            "financial_stress_regime",
            "stress_regime",
            "research_stress_regime",
        ],
        "financial_stress_composite": [
            "financial_stress_composite",
            "stress_composite",
            "composite",
        ],
        "vix": [
            "VIX",
            "vix",
        ],
        "yield_curve_10y_2y": [
            "yield_curve_10y_2y",
            "10y_2y_spread",
            "yield_curve_spread",
        ],
        "fed_score": [
            "fed_score",
        ],
        "sep_shift": [
            "sep_shift",
        ],
        "fed_latest_fomc": [
            "fed_latest_fomc",
            "latest_fomc",
        ],
    }

    for target, candidates in possible_columns.items():

        for candidate in candidates:

            if candidate in df.columns:
                rename_map[candidate] = target
                break

    df = df.rename(
        columns=rename_map
    )

    selected = [
        "_observation_date",
        "_availability_date",
    ]

    for column in possible_columns:

        if column in df.columns:
            selected.append(column)

    result = df[selected].copy()

    result = result.rename(
        columns={
            "_observation_date": "macro_date",
            "_availability_date": "macro_availability_date",
        }
    )

    return result


# ============================================================
# Sentiment preparation
# ============================================================

def prepare_sentiment(df: pd.DataFrame) -> pd.DataFrame:

    df = prepare_dates(
        df,
        "Sentiment Engine"
    )

    availability_column = find_availability_column(
        df
    )

    if availability_column:
        df["_availability_date"] = pd.to_datetime(
            df[availability_column],
            errors="coerce"
        )
    else:
        df["_availability_date"] = (
            df["_observation_date"]
        )

    rename_map = {}

    possible_columns = {
        "unified_sentiment_score": [
            "unified_sentiment_score",
            "sentiment_score",
        ],
        "sentiment_regime": [
            "sentiment_regime",
        ],
        "cot_score": [
            "cot_score",
        ],
        "aaii_score": [
            "aaii_score",
        ],
        "vix_score": [
            "vix_score",
        ],
        "available_component_count": [
            "available_component_count",
        ],
    }

    for target, candidates in possible_columns.items():

        for candidate in candidates:

            if candidate in df.columns:
                rename_map[candidate] = target
                break

    df = df.rename(
        columns=rename_map
    )

    selected = [
        "_observation_date",
        "_availability_date",
    ]

    for column in possible_columns:

        if column in df.columns:
            selected.append(column)

    result = df[selected].copy()

    result = result.rename(
        columns={
            "_observation_date": "sentiment_date",
            "_availability_date": "sentiment_availability_date",
        }
    )

    return result


# ============================================================
# Technical preparation
# ============================================================

def prepare_technical(df: pd.DataFrame) -> pd.DataFrame:

    df = prepare_dates(
        df,
        "Technical Intelligence"
    )

    availability_column = find_availability_column(
        df
    )

    if availability_column:
        df["_availability_date"] = pd.to_datetime(
            df[availability_column],
            errors="coerce"
        )
    else:
        df["_availability_date"] = (
            df["_observation_date"]
        )

    required = [
        "Close",
        "SMA20",
        "SMA50",
        "SMA200",
        "RSI14",
        "ATR14",
        "ATR14_pct",
        "ROC20_pct",
        "drawdown_pct",
        "trend_structure",
        "technical_regime",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        fail(
            "Technical Intelligence missing columns: "
            f"{missing}"
        )

    selected = [
        "_observation_date",
        "_availability_date",
    ] + required

    result = df[selected].copy()

    result = result.rename(
        columns={
            "_observation_date": "technical_date",
            "_availability_date": "technical_availability_date",
        }
    )

    return result


# ============================================================
# PIT-safe merge
# ============================================================

def build_context(
    macro: pd.DataFrame,
    sentiment: pd.DataFrame,
    technical: pd.DataFrame,
) -> pd.DataFrame:

    # --------------------------------------------------------
    # Use the union of all observation dates.
    # --------------------------------------------------------

    all_dates = pd.concat(
        [
            macro["macro_date"],
            sentiment["sentiment_date"],
            technical["technical_date"],
        ],
        ignore_index=True,
    )

    all_dates = (
        pd.Series(all_dates)
        .dropna()
        .drop_duplicates()
        .sort_values()
        .reset_index(drop=True)
    )

    context = pd.DataFrame(
        {
            "context_date": all_dates
        }
    )

    # --------------------------------------------------------
    # PIT-safe availability filtering
    #
    # A source observation is usable only when:
    #
    # source_availability_date <= context_date
    #
    # --------------------------------------------------------

    macro = macro.sort_values(
        "macro_availability_date"
    )

    sentiment = sentiment.sort_values(
        "sentiment_availability_date"
    )

    technical = technical.sort_values(
        "technical_availability_date"
    )

    context = context.sort_values(
        "context_date"
    )

    # --------------------------------------------------------
    # Macro
    # --------------------------------------------------------

    context = pd.merge_asof(
        context,
        macro,
        left_on="context_date",
        right_on="macro_availability_date",
        direction="backward",
    )

    # --------------------------------------------------------
    # Sentiment
    # --------------------------------------------------------

    context = pd.merge_asof(
        context.sort_values("context_date"),
        sentiment,
        left_on="context_date",
        right_on="sentiment_availability_date",
        direction="backward",
    )

    # --------------------------------------------------------
    # Technical
    # --------------------------------------------------------

    context = pd.merge_asof(
        context.sort_values("context_date"),
        technical,
        left_on="context_date",
        right_on="technical_availability_date",
        direction="backward",
    )

    # --------------------------------------------------------
    # Availability age
    # --------------------------------------------------------

    context["macro_age_days"] = (
        context["context_date"]
        - context["macro_availability_date"]
    ).dt.days

    context["sentiment_age_days"] = (
        context["context_date"]
        - context["sentiment_availability_date"]
    ).dt.days

    context["technical_age_days"] = (
        context["context_date"]
        - context["technical_availability_date"]
    ).dt.days

    # --------------------------------------------------------
    # Component availability
    # --------------------------------------------------------

    context["macro_available"] = (
        context["macro_availability_date"]
        .notna()
    )

    context["sentiment_available"] = (
        context["sentiment_availability_date"]
        .notna()
    )

    context["technical_available"] = (
        context["technical_availability_date"]
        .notna()
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
    )

    # --------------------------------------------------------
    # PIT validation flag
    # --------------------------------------------------------

    context["point_in_time_safe"] = (
        (
            ~context["macro_available"]
            | (
                context["macro_availability_date"]
                <= context["context_date"]
            )
        )
        &
        (
            ~context["sentiment_available"]
            | (
                context["sentiment_availability_date"]
                <= context["context_date"]
            )
        )
        &
        (
            ~context["technical_available"]
            | (
                context["technical_availability_date"]
                <= context["context_date"]
            )
        )
    )

    # --------------------------------------------------------
    # Research-only metadata
    # --------------------------------------------------------

    context["research_only"] = True
    context["decision_engine_ready"] = False
    context["trading_signal_generated"] = False
    context["forecast_generated"] = False
    context["unified_decision_generated"] = False

    return context


# ============================================================
# Validation
# ============================================================

def validate_context(
    context: pd.DataFrame
):

    print()
    print("=" * 70)
    print("Research Context Validation")
    print("=" * 70)

    if context.empty:
        fail(
            "Research Context output is empty."
        )

    if context[
        "context_date"
    ].duplicated().any():
        fail(
            "Duplicate context dates detected."
        )

    if not context[
        "context_date"
    ].is_monotonic_increasing:
        fail(
            "Context dates are not sorted."
        )

    if not context[
        "point_in_time_safe"
    ].eq(True).all():
        fail(
            "PIT validation failed."
        )

    if not context[
        "research_only"
    ].eq(True).all():
        fail(
            "Research-only validation failed."
        )

    if not context[
        "decision_engine_ready"
    ].eq(False).all():
        fail(
            "Decision Engine must remain disabled."
        )

    if not context[
        "trading_signal_generated"
    ].eq(False).all():
        fail(
            "Trading signal generation detected."
        )

    if not context[
        "forecast_generated"
    ].eq(False).all():
        fail(
            "Forecast generation detected."
        )

    if not context[
        "unified_decision_generated"
    ].eq(False).all():
        fail(
            "Unified decision generation detected."
        )

    # --------------------------------------------------------
    # Check availability ages
    # --------------------------------------------------------

    for column in [
        "macro_age_days",
        "sentiment_age_days",
        "technical_age_days",
    ]:

        available_mask = context[column].notna()

        if (
            context.loc[
                available_mask,
                column
            ] < 0
        ).any():

            fail(
                f"Negative availability age detected: {column}"
            )

    print("✓ Non-empty context")
    print("✓ No duplicate dates")
    print("✓ Dates sorted")
    print("✓ PIT safe")
    print("✓ Research only")
    print("✓ Decision Engine disabled")
    print("✓ No trading signal")
    print("✓ No forecast")
    print("✓ No unified decision")


# ============================================================
# Summary
# ============================================================

def create_summary(
    context: pd.DataFrame
) -> pd.DataFrame:

    summary = pd.DataFrame(
        {
            "metric": [
                "context_rows",
                "first_context_date",
                "last_context_date",
                "macro_available_rows",
                "sentiment_available_rows",
                "technical_available_rows",
                "all_three_layers_available_rows",
                "pit_safe_rows",
            ],
            "value": [
                len(context),
                str(
                    context[
                        "context_date"
                    ].min().date()
                ),
                str(
                    context[
                        "context_date"
                    ].max().date()
                ),
                int(
                    context[
                        "macro_available"
                    ].sum()
                ),
                int(
                    context[
                        "sentiment_available"
                    ].sum()
                ),
                int(
                    context[
                        "technical_available"
                    ].sum()
                ),
                int(
                    (
                        context[
                            "available_layer_count"
                        ] == 3
                    ).sum()
                ),
                int(
                    context[
                        "point_in_time_safe"
                    ].sum()
                ),
            ],
        }
    )

    summary["research_only"] = True
    summary["decision_engine_ready"] = False

    return summary


# ============================================================
# Extremes
# ============================================================

def create_extremes(
    context: pd.DataFrame
) -> pd.DataFrame:

    masks = []

    if "sentiment_regime" in context.columns:

        masks.append(
            context[
                "sentiment_regime"
            ].isin(
                [
                    "EXTREME_BULLISH",
                    "EXTREME_BEARISH",
                ]
            )
        )

    if "technical_regime" in context.columns:

        masks.append(
            context[
                "technical_regime"
            ].isin(
                [
                    "STRONG_BULLISH",
                    "STRONG_BEARISH",
                ]
            )
        )

    if "economic_regime" in context.columns:

        masks.append(
            context[
                "economic_regime"
            ].isin(
                [
                    "STRONG_GROWTH",
                    "WEAK_GROWTH",
                    "RECESSION",
                ]
            )
        )

    if not masks:
        return context.iloc[0:0].copy()

    combined = masks[0]

    for mask in masks[1:]:
        combined = combined | mask

    return context.loc[
        combined
    ].copy()


# ============================================================
# Main
# ============================================================

def main():

    print("=" * 70)
    print("Research Context v1")
    print("=" * 70)

    # --------------------------------------------------------
    # Load
    # --------------------------------------------------------

    macro_raw = read_csv_required(
        MACRO_FILE,
        "Macro Context"
    )

    sentiment_raw = read_csv_required(
        SENTIMENT_FILE,
        "Sentiment Engine"
    )

    technical_raw = read_csv_required(
        TECHNICAL_FILE,
        "Technical Intelligence"
    )

    # --------------------------------------------------------
    # Prepare
    # --------------------------------------------------------

    macro = prepare_macro(
        macro_raw
    )

    sentiment = prepare_sentiment(
        sentiment_raw
    )

    technical = prepare_technical(
        technical_raw
    )

    # --------------------------------------------------------
    # Build
    # --------------------------------------------------------

    context = build_context(
        macro,
        sentiment,
        technical,
    )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    validate_context(
        context
    )

    # --------------------------------------------------------
    # Outputs
    # --------------------------------------------------------

    summary = create_summary(
        context
    )

    extremes = create_extremes(
        context
    )

    context.to_csv(
        OUTPUT_FILE,
        index=False
    )

    summary.to_csv(
        SUMMARY_FILE,
        index=False
    )

    extremes.to_csv(
        EXTREMES_FILE,
        index=False
    )

    # --------------------------------------------------------
    # Latest
    # --------------------------------------------------------

    latest = context.iloc[-1]

    print()
    print("=" * 70)
    print("Research Context v1 completed")
    print("=" * 70)

    print(
        f"Rows: {len(context):,}"
    )

    print(
        f"Period: "
        f"{context['context_date'].iloc[0].date()} "
        f"→ "
        f"{context['context_date'].iloc[-1].date()}"
    )

    print()
    print("Latest context:")
    print(
        "Date:",
        latest["context_date"].date()
    )

    print(
        "Available layers:",
        int(
            latest[
                "available_layer_count"
            ]
        ),
        "/ 3"
    )

    if "economic_regime" in context.columns:
        print(
            "Economic regime:",
            latest["economic_regime"]
        )

    if "sentiment_regime" in context.columns:
        print(
            "Sentiment regime:",
            latest["sentiment_regime"]
        )

    if "technical_regime" in context.columns:
        print(
            "Technical regime:",
            latest["technical_regime"]
        )

    print()
    print(
        "PIT safe: TRUE"
    )

    print(
        "Research only: TRUE"
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
        "Unified decision: FALSE"
    )

    print()
    print("Outputs:")
    print(
        f"- {OUTPUT_FILE}"
    )
    print(
        f"- {SUMMARY_FILE}"
    )
    print(
        f"- {EXTREMES_FILE}"
    )


if __name__ == "__main__":
    main()
