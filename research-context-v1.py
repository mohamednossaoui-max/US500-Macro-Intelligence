import os
from pathlib import Path

import pandas as pd


# ============================================================
# Research Context v1
# Unified research-only context layer
# ============================================================

OUTPUT_FILE = Path(
    "research_context_v1.csv"
)

SUMMARY_FILE = Path(
    "research_context_summary_v1.csv"
)

EXTREMES_FILE = Path(
    "research_context_extremes_v1.csv"
)

MACRO_FILE = Path(
    os.getenv(
        "MACRO_CONTEXT_FILE",
        "context_input/macro_context_v1.csv"
    )
)

SENTIMENT_FILE = Path(
    os.getenv(
        "SENTIMENT_ENGINE_FILE",
        "context_input/sentiment_engine_research_v1.csv"
    )
)

TECHNICAL_FILE = Path(
    os.getenv(
        "TECHNICAL_INTELLIGENCE_FILE",
        "context_input/technical_intelligence_research_v1.csv"
    )
)


# ============================================================
# Helpers
# ============================================================

def fail(message):
    raise RuntimeError(message)


def read_required(path, name):

    if not path.exists():
        fail(
            f"{name} file not found: {path}"
        )

    df = pd.read_csv(path)

    if df.empty:
        fail(
            f"{name} file is empty."
        )

    print(
        f"{name}: {len(df):,} rows"
    )

    return df


def parse_date(df, column):

    df[column] = pd.to_datetime(
        df[column],
        errors="coerce"
    )

    return df


# ============================================================
# Macro Context
# ============================================================

def prepare_macro(df):

    # Macro Context v1 is a current context snapshot.
    #
    # Actual artifact structure:
    # context_date / as_of_date may vary by version.
    #

    date_column = None

    for candidate in [
        "context_date",
        "as_of_date",
        "asof_date",
        "date",
    ]:
        if candidate in df.columns:
            date_column = candidate
            break

    if date_column is None:
        fail(
            "Macro Context date column not found. "
            f"Columns: {list(df.columns)}"
        )

    df = df.copy()

    df["macro_date"] = pd.to_datetime(
        df[date_column],
        errors="coerce"
    )

    df = df.dropna(
        subset=["macro_date"]
    )

    # Macro Context is already a PIT-safe snapshot.
    if "availability_date" in df.columns:

        df["macro_availability_date"] = pd.to_datetime(
            df["availability_date"],
            errors="coerce"
        )

    elif "context_availability_date" in df.columns:

        df["macro_availability_date"] = pd.to_datetime(
            df["context_availability_date"],
            errors="coerce"
        )

    else:

        df["macro_availability_date"] = (
            df["macro_date"]
        )

    return df


# ============================================================
# Sentiment Engine
# ============================================================

def prepare_sentiment(df):

    # --------------------------------------------------------
    # Actual Sentiment Engine v1 structure
    #
    # asof_date
    # cot_observation_date
    # cot_availability_date
    # ...
    # unified_sentiment_score
    # research_regime
    # --------------------------------------------------------

    required = [
        "asof_date",
        "unified_sentiment_score",
        "research_regime",
        "point_in_time_safe",
        "research_only",
        "decision_engine_ready",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        fail(
            "Sentiment Engine missing columns: "
            f"{missing}"
        )

    result = df.copy()

    result["sentiment_date"] = pd.to_datetime(
        result["asof_date"],
        errors="coerce"
    )

    result = result.dropna(
        subset=["sentiment_date"]
    )

    # Sentiment Engine's asof_date is the PIT reconstruction
    # date. Its component availability dates are already
    # reconstructed inside the engine.
    #
    # Therefore the daily sentiment observation is usable
    # on its asof_date.

    result["sentiment_availability_date"] = (
        result["sentiment_date"]
    )

    result = result.rename(
        columns={
            "research_regime":
                "sentiment_regime",
            "cot_sentiment_score":
                "cot_score",
            "aaii_sentiment_score":
                "aaii_score",
            "vix_sentiment_score":
                "vix_score",
        }
    )

    keep = [
        "sentiment_date",
        "sentiment_availability_date",
        "unified_sentiment_score",
        "sentiment_regime",
        "cot_score",
        "aaii_score",
        "vix_score",
        "available_component_count",
        "point_in_time_safe",
        "research_only",
        "decision_engine_ready",
    ]

    keep = [
        column
        for column in keep
        if column in result.columns
    ]

    result = result[keep]

    return result


# ============================================================
# Technical Intelligence
# ============================================================

def prepare_technical(df):

    required = [
        "observation_date",
        "availability_date",
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
        "point_in_time_safe",
        "research_only",
        "decision_engine_ready",
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

    result = df.copy()

    result["technical_date"] = pd.to_datetime(
        result["observation_date"],
        errors="coerce"
    )

    result["technical_availability_date"] = pd.to_datetime(
        result["availability_date"],
        errors="coerce"
    )

    result = result.dropna(
        subset=[
            "technical_date",
            "technical_availability_date",
        ]
    )

    keep = [
        "technical_date",
        "technical_availability_date",
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
        "point_in_time_safe",
        "research_only",
        "decision_engine_ready",
    ]

    result = result[keep]

    return result


# ============================================================
# PIT-safe context construction
# ============================================================

def build_context(
    macro,
    sentiment,
    technical,
):

    # --------------------------------------------------------
    # Context calendar
    #
    # Technical layer supplies the primary daily market
    # calendar. Macro snapshot and sentiment are aligned to it.
    # --------------------------------------------------------

    context_dates = (
        technical[
            "technical_date"
        ]
        .drop_duplicates()
        .sort_values()
        .reset_index(drop=True)
    )

    context = pd.DataFrame(
        {
            "context_date": context_dates
        }
    )

    # --------------------------------------------------------
    # Macro snapshot
    #
    # Macro Context is a current snapshot, so merge the
    # latest available snapshot backward.
    # --------------------------------------------------------

    macro = macro.sort_values(
        "macro_availability_date"
    )

    context = pd.merge_asof(
        context.sort_values("context_date"),
        macro,
        left_on="context_date",
        right_on="macro_availability_date",
        direction="backward",
    )

    # --------------------------------------------------------
    # Sentiment
    # --------------------------------------------------------

    sentiment = sentiment.sort_values(
        "sentiment_availability_date"
    )

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

    technical = technical.sort_values(
        "technical_availability_date"
    )

    context = pd.merge_asof(
        context.sort_values("context_date"),
        technical,
        left_on="context_date",
        right_on="technical_availability_date",
        direction="backward",
    )

    # --------------------------------------------------------
    # Layer availability
    # --------------------------------------------------------

    context["macro_available"] = (
        context[
            "macro_availability_date"
        ].notna()
    )

    context["sentiment_available"] = (
        context[
            "sentiment_availability_date"
        ].notna()
    )

    context["technical_available"] = (
        context[
            "technical_availability_date"
        ].notna()
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
    # PIT validation
    # --------------------------------------------------------

    context["point_in_time_safe"] = (
        (
            ~context["macro_available"]
            |
            (
                context["macro_availability_date"]
                <= context["context_date"]
            )
        )
        &
        (
            ~context["sentiment_available"]
            |
            (
                context["sentiment_availability_date"]
                <= context["context_date"]
            )
        )
        &
        (
            ~context["technical_available"]
            |
            (
                context["technical_availability_date"]
                <= context["context_date"]
            )
        )
    )

    # --------------------------------------------------------
    # Research-only safeguards
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

def validate_context(df):

    print()
    print("=" * 70)
    print("Research Context Validation")
    print("=" * 70)

    if df.empty:
        fail(
            "Research Context output is empty."
        )

    if df[
        "context_date"
    ].duplicated().any():
        fail(
            "Duplicate context dates detected."
        )

    if not df[
        "context_date"
    ].is_monotonic_increasing:
        fail(
            "Context dates are not sorted."
        )

    if not df[
        "point_in_time_safe"
    ].eq(True).all():
        fail(
            "PIT validation failed."
        )

    if not df[
        "research_only"
    ].eq(True).all():
        fail(
            "Research-only validation failed."
        )

    if not df[
        "decision_engine_ready"
    ].eq(False).all():
        fail(
            "Decision Engine must remain disabled."
        )

    if not df[
        "trading_signal_generated"
    ].eq(False).all():
        fail(
            "Trading signal detected."
        )

    if not df[
        "forecast_generated"
    ].eq(False).all():
        fail(
            "Forecast detected."
        )

    if not df[
        "unified_decision_generated"
    ].eq(False).all():
        fail(
            "Unified decision detected."
        )

    print("✓ Dataset non-empty")
    print("✓ Dates unique")
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

def create_summary(df):

    rows = [
        (
            "context_rows",
            len(df)
        ),
        (
            "first_context_date",
            str(
                df[
                    "context_date"
                ].min().date()
            )
        ),
        (
            "last_context_date",
            str(
                df[
                    "context_date"
                ].max().date()
            )
        ),
        (
            "macro_available_rows",
            int(
                df[
                    "macro_available"
                ].sum()
            )
        ),
        (
            "sentiment_available_rows",
            int(
                df[
                    "sentiment_available"
                ].sum()
            )
        ),
        (
            "technical_available_rows",
            int(
                df[
                    "technical_available"
                ].sum()
            )
        ),
        (
            "all_three_layers_available_rows",
            int(
                (
                    df[
                        "available_layer_count"
                    ] == 3
                ).sum()
            )
        ),
        (
            "pit_safe_rows",
            int(
                df[
                    "point_in_time_safe"
                ].sum()
            )
        ),
    ]

    result = pd.DataFrame(
        rows,
        columns=[
            "metric",
            "value"
        ]
    )

    result["research_only"] = True
    result["decision_engine_ready"] = False

    return result


# ============================================================
# Extremes
# ============================================================

def create_extremes(df):

    mask = pd.Series(
        False,
        index=df.index
    )

    if "sentiment_regime" in df.columns:

        mask |= df[
            "sentiment_regime"
        ].isin(
            [
                "EXTREME_BULLISH",
                "EXTREME_BEARISH",
            ]
        )

    if "technical_regime" in df.columns:

        mask |= df[
            "technical_regime"
        ].isin(
            [
                "STRONG_BULLISH",
                "STRONG_BEARISH",
            ]
        )

    return df.loc[
        mask
    ].copy()


# ============================================================
# Main
# ============================================================

def main():

    print("=" * 70)
    print("Research Context v1")
    print("=" * 70)

    # --------------------------------------------------------
    # Load actual artifacts
    # --------------------------------------------------------

    macro_raw = read_required(
        MACRO_FILE,
        "Macro Context"
    )

    sentiment_raw = read_required(
        SENTIMENT_FILE,
        "Sentiment Engine"
    )

    technical_raw = read_required(
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
        technical
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
        "Rows:",
        len(context)
    )

    print(
        "Period:",
        context[
            "context_date"
        ].iloc[0].date(),
        "->",
        context[
            "context_date"
        ].iloc[-1].date()
    )

    print()
    print("Latest context:")
    print(
        "Date:",
        latest[
            "context_date"
        ].date()
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

    for column in [
        "economic_regime",
        "sentiment_regime",
        "technical_regime",
    ]:

        if column in context.columns:

            print(
                f"{column}:",
                latest[column]
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
