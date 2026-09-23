"""
US500 Macro Context Layer v1

Purpose:
    Combine the existing:
        - Economic Intelligence
        - Fed Intelligence
        - Financial Stress Intelligence
        - Event / News Intelligence

into one research-only macro context snapshot.

Important:
    - Point-in-time aware
    - Explicit data-age tracking
    - No trading signals
    - No trade execution
    - No Decision Engine integration
    - No forecasting

Expected inputs:

    fed_intelligence_output_v1.json

    economic_regime_events_v1.csv

    financial_stress_research_v1.csv

    event_news_research_v2.csv

The script selects the latest available information as of the
Fed Intelligence as_of_date and preserves the age of each source.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


# ============================================================
# INPUT FILES
# ============================================================

FED_FILE = Path("fed_intelligence_output_v1.json")

ECONOMIC_FILE = Path(
    "economic_regime_events_v1.csv"
)

FINANCIAL_STRESS_FILE = Path(
    "financial_stress_research_v1.csv"
)

EVENT_NEWS_FILE = Path(
    "event_news_research_v2.csv"
)


# ============================================================
# OUTPUT FILES
# ============================================================

OUTPUT_JSON = Path(
    "macro_context_v1.json"
)

OUTPUT_CSV = Path(
    "macro_context_v1.csv"
)


# ============================================================
# DATE HELPERS
# ============================================================

def parse_date(value):
    if value is None or pd.isna(value):
        return None

    return pd.to_datetime(value).date()


def days_between(later, earlier):
    if later is None or earlier is None:
        return None

    return (later - earlier).days


# ============================================================
# FED INTELLIGENCE
# ============================================================

def load_fed():

    if not FED_FILE.exists():
        raise FileNotFoundError(
            f"Missing required file: {FED_FILE}"
        )

    data = json.loads(
        FED_FILE.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(data, dict):
        raise ValueError(
            "Fed Intelligence file must contain a JSON object."
        )

    return data


# ============================================================
# ECONOMIC INTELLIGENCE
# ============================================================

def load_economic(as_of_date):

    if not ECONOMIC_FILE.exists():
        raise FileNotFoundError(
            f"Missing required file: {ECONOMIC_FILE}"
        )

    df = pd.read_csv(
        ECONOMIC_FILE
    )

    if df.empty:
        raise ValueError(
            "Economic regime file is empty."
        )

    required_columns = {
        "release_date",
    }

    missing = (
        required_columns
        - set(df.columns)
    )

    if missing:
        raise ValueError(
            "Economic regime file is missing "
            "required columns: "
            + ", ".join(
                sorted(missing)
            )
        )

    df["release_date"] = pd.to_datetime(
        df["release_date"],
        errors="coerce"
    ).dt.date

    df = df[
        df["release_date"].notna()
    ].copy()

    # --------------------------------------------------------
    # Anti-lookahead:
    # only observations released on or before
    # the macro context date.
    # --------------------------------------------------------

    df = df[
        df["release_date"] <= as_of_date
    ].copy()

    if df.empty:
        raise ValueError(
            "No economic observations available "
            "on or before the macro context date."
        )

    df = df.sort_values(
        "release_date"
    )

    return df.iloc[-1].to_dict()


# ============================================================
# FINANCIAL STRESS
# ============================================================

def load_financial_stress(as_of_date):

    if not FINANCIAL_STRESS_FILE.exists():
        raise FileNotFoundError(
            f"Missing required file: "
            f"{FINANCIAL_STRESS_FILE}"
        )

    df = pd.read_csv(
        FINANCIAL_STRESS_FILE
    )

    if df.empty:
        raise ValueError(
            "Financial stress research file is empty."
        )

    required_columns = {
        "asof_date",
        "composite_stress_score",
        "research_regime",
        "point_in_time_safe",
    }

    missing = (
        required_columns
        - set(df.columns)
    )

    if missing:
        raise ValueError(
            "Financial stress file is missing "
            "required columns: "
            + ", ".join(
                sorted(missing)
            )
        )

    df["asof_date"] = pd.to_datetime(
        df["asof_date"],
        errors="coerce"
    ).dt.date

    df = df[
        df["asof_date"].notna()
    ].copy()

    # --------------------------------------------------------
    # Anti-lookahead
    # --------------------------------------------------------

    df = df[
        df["asof_date"] <= as_of_date
    ].copy()

    if df.empty:
        raise ValueError(
            "No financial stress observations available "
            "on or before the macro context date."
        )

    # --------------------------------------------------------
    # PIT safety
    # --------------------------------------------------------

    df = df[
        df["point_in_time_safe"] == True
    ].copy()

    if df.empty:
        raise ValueError(
            "No point-in-time-safe Financial Stress "
            "observations available."
        )

    df = df.sort_values(
        "asof_date"
    )

    return df.iloc[-1].to_dict()


# ============================================================
# EVENT / NEWS INTELLIGENCE
# ============================================================

def load_event_news(as_of_date):

    if not EVENT_NEWS_FILE.exists():
        raise FileNotFoundError(
            f"Missing required file: "
            f"{EVENT_NEWS_FILE}"
        )

    df = pd.read_csv(
        EVENT_NEWS_FILE
    )

    if df.empty:
        raise ValueError(
            "Event / News research file is empty."
        )

    required_columns = {
        "published_at",
        "availability_date",
        "topic",
        "title",
        "source",
        "point_in_time_safe",
    }

    missing = (
        required_columns
        - set(df.columns)
    )

    if missing:
        raise ValueError(
            "Event / News file is missing "
            "required columns: "
            + ", ".join(
                sorted(missing)
            )
        )

    # --------------------------------------------------------
    # Normalize dates
    # --------------------------------------------------------

    df["availability_date"] = pd.to_datetime(
        df["availability_date"],
        errors="coerce"
    ).dt.date

    df["published_at"] = pd.to_datetime(
        df["published_at"],
        errors="coerce",
        utc=True
    )

    # --------------------------------------------------------
    # Remove invalid availability dates
    # --------------------------------------------------------

    df = df[
        df["availability_date"].notna()
    ].copy()

    if df.empty:
        raise ValueError(
            "Event / News file contains no valid "
            "availability dates."
        )

    # --------------------------------------------------------
    # Anti-lookahead:
    #
    # Only information that was available on or
    # before the macro context date can enter the
    # Macro Context.
    # --------------------------------------------------------

    df = df[
        df["availability_date"] <= as_of_date
    ].copy()

    # --------------------------------------------------------
    # PIT safety
    # --------------------------------------------------------

    df = df[
        df["point_in_time_safe"] == True
    ].copy()

    if df.empty:
        raise ValueError(
            "No point-in-time-safe Event / News "
            "observations available on or before "
            "the macro context date."
        )

    # --------------------------------------------------------
    # Deterministic ordering
    # --------------------------------------------------------

    df = df.sort_values(
        [
            "availability_date",
            "published_at",
        ],
        na_position="first"
    )

    latest = df.iloc[-1].to_dict()

    topic_counts = (
        df["topic"]
        .astype(str)
        .value_counts()
        .to_dict()
    )

    return {
        "source_date":
            latest["availability_date"],

        "published_at":
            (
                latest["published_at"].isoformat()
                if pd.notna(
                    latest["published_at"]
                )
                else None
            ),

        "latest_title":
            latest.get("title"),

        "latest_source":
            latest.get("source"),

        "latest_topic":
            latest.get("topic"),

        "events_available":
            int(len(df)),

        "topic_counts": {
            str(key): int(value)
            for key, value
            in topic_counts.items()
        },

        "pit_safe": True,
    }


# ============================================================
# SAFE FLOAT
# ============================================================

def safe_float(value):

    if value is None:
        return None

    try:

        value = float(value)

        if pd.isna(value):
            return None

        return value

    except (
        TypeError,
        ValueError,
    ):
        return None


# ============================================================
# BUILD MACRO CONTEXT
# ============================================================

def build_macro_context():

    print("=" * 70)
    print(
        "US500 MACRO CONTEXT LAYER v1"
    )
    print("=" * 70)

    # ========================================================
    # FED
    # ========================================================

    fed = load_fed()

    context_date = parse_date(
        fed.get("as_of_date")
    )

    if context_date is None:
        raise ValueError(
            "Fed Intelligence does not contain "
            "a valid 'as_of_date'."
        )

    print(
        f"Context date: {context_date}"
    )

    # ========================================================
    # ECONOMIC INTELLIGENCE
    # ========================================================

    economic = load_economic(
        context_date
    )

    economic_date = parse_date(
        economic.get("release_date")
    )

    economic_age = days_between(
        context_date,
        economic_date
    )

    # ========================================================
    # FINANCIAL STRESS
    # ========================================================

    stress = load_financial_stress(
        context_date
    )

    stress_date = parse_date(
        stress.get("asof_date")
    )

    stress_age = days_between(
        context_date,
        stress_date
    )

    # ========================================================
    # EVENT / NEWS INTELLIGENCE
    # ========================================================

    event_news = load_event_news(
        context_date
    )

    event_news_date = parse_date(
        event_news.get("source_date")
    )

    event_news_age = days_between(
        context_date,
        event_news_date
    )

    # ========================================================
    # FED COMPONENTS
    # ========================================================

    statement = (
        fed.get("statement")
        or {}
    )

    phase_2b = (
        fed.get("phase_2b")
        or {}
    )

    fed_score = fed.get(
        "fed_score"
    )

    if isinstance(
        fed_score,
        dict
    ):

        fed_score_value = (
            fed_score.get("score")
        )

    else:

        fed_score_value = fed_score

    sep_shift = fed.get(
        "sep_shift"
    )

    # ========================================================
    # ECONOMIC COMPONENTS
    # ========================================================

    economic_regime = (
        economic.get(
            "economic_regime"
        )
    )

    inflation_score = safe_float(
        economic.get(
            "inflation_score"
        )
    )

    labor_score = safe_float(
        economic.get(
            "labor_score"
        )
    )

    growth_score = safe_float(
        economic.get(
            "growth_score"
        )
    )

    dimensions_available = (
        economic.get(
            "dimensions_available"
        )
    )

    economic_pit_safe = bool(
        economic.get(
            "pit_safe",
            False
        )
    )

    # ========================================================
    # FINANCIAL STRESS COMPONENTS
    # ========================================================

    stress_composite = safe_float(
        stress.get(
            "composite_stress_score"
        )
    )

    stress_regime = (
        stress.get(
            "research_regime"
        )
    )

    stress_pit_safe = bool(
        stress.get(
            "point_in_time_safe",
            False
        )
    )

    # ========================================================
    # MACRO CONTEXT OBJECT
    # ========================================================

    context = {

        "methodology_version":
            "macro_context_v1",

        "context_date":
            context_date.isoformat(),

        "research_only":
            True,

        "decision_engine_ready":
            False,

        "trade_signal":
            None,

        "forecast":
            None,

        # ----------------------------------------------------
        # ECONOMIC
        # ----------------------------------------------------

        "economic": {

            "source_date":
                (
                    economic_date.isoformat()
                    if economic_date
                    else None
                ),

            "age_days":
                economic_age,

            "economic_regime":
                economic_regime,

            "inflation_score":
                inflation_score,

            "labor_score":
                labor_score,

            "growth_score":
                growth_score,

            "dimensions_available":
                dimensions_available,

            "pit_safe":
                economic_pit_safe,
        },

        # ----------------------------------------------------
        # FED
        # ----------------------------------------------------

        "fed": {

            "as_of_date":
                fed.get(
                    "as_of_date"
                ),

            "latest_fomc":
                fed.get(
                    "latest_fomc"
                ),

            "fed_chair":
                fed.get(
                    "fed_chair"
                ),

            "statement_tone":
                statement.get(
                    "tone"
                ),

            "statement_tone_score":
                statement.get(
                    "tone_score"
                ),

            "phase_2b":
                phase_2b,

            "fed_score":
                fed_score_value,

            "sep_shift":
                sep_shift,

            "beige_book_available":
                (
                    fed.get(
                        "beige_book"
                    )
                    or {}
                ).get(
                    "available"
                ),

            "pit_safe":
                True,
        },

        # ----------------------------------------------------
        # FINANCIAL STRESS
        # ----------------------------------------------------

        "financial_stress": {

            "source_date":
                (
                    stress_date.isoformat()
                    if stress_date
                    else None
                ),

            "age_days":
                stress_age,

            "composite_stress_score":
                stress_composite,

            "research_regime":
                stress_regime,

            "vix":
                safe_float(
                    stress.get(
                        "VIX"
                    )
                ),

            "treasury_2y":
                safe_float(
                    stress.get(
                        "TREASURY_2Y"
                    )
                ),

            "treasury_10y":
                safe_float(
                    stress.get(
                        "TREASURY_10Y"
                    )
                ),

            "yield_10y_2y_spread":
                safe_float(
                    stress.get(
                        "YIELD_10Y_2Y_SPREAD"
                    )
                ),

            "pit_safe":
                stress_pit_safe,
        },

        # ----------------------------------------------------
        # EVENT / NEWS
        # ----------------------------------------------------

        "event_news": {

            "source_date":
                (
                    event_news_date.isoformat()
                    if event_news_date
                    else None
                ),

            "age_days":
                event_news_age,

            "latest_published_at":
                event_news.get(
                    "published_at"
                ),

            "latest_title":
                event_news.get(
                    "latest_title"
                ),

            "latest_source":
                event_news.get(
                    "latest_source"
                ),

            "latest_topic":
                event_news.get(
                    "latest_topic"
                ),

            "events_available":
                event_news.get(
                    "events_available"
                ),

            "topic_counts":
                event_news.get(
                    "topic_counts",
                    {}
                ),

            "pit_safe":
                event_news.get(
                    "pit_safe",
                    False
                ),
        },

        # ----------------------------------------------------
        # TEMPORAL ALIGNMENT
        # ----------------------------------------------------

        "temporal_alignment": {

            "economic_age_days":
                economic_age,

            "financial_stress_age_days":
                stress_age,

            "event_news_age_days":
                event_news_age,

            "fed_is_current_snapshot":
                True,

            "anti_lookahead":
                True,

            "note":
                (
                    "Sources are not forced to be "
                    "same-day. Source age is preserved "
                    "explicitly. Event / News is filtered "
                    "by availability_date before entering "
                    "the Macro Context."
                ),
        },
    }

    # ========================================================
    # VALIDATION
    # ========================================================

    assert (
        context["research_only"]
        is True
    )

    assert (
        context["decision_engine_ready"]
        is False
    )

    assert (
        context["trade_signal"]
        is None
    )

    assert (
        context["forecast"]
        is None
    )

    assert (
        economic_pit_safe
        is True
    )

    assert (
        stress_pit_safe
        is True
    )

    assert (
        event_news.get("pit_safe")
        is True
    )

    assert (
        event_news_date
        is not None
    )

    # ========================================================
    # WRITE JSON
    # ========================================================

    OUTPUT_JSON.write_text(
        json.dumps(
            context,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ========================================================
    # WRITE ONE-ROW CSV
    # ========================================================

    flat = {

        "methodology_version":
            "macro_context_v1",

        "context_date":
            context[
                "context_date"
            ],

        # Economic
        "economic_source_date":
            economic_date,

        "economic_age_days":
            economic_age,

        "economic_regime":
            economic_regime,

        "inflation_score":
            inflation_score,

        "labor_score":
            labor_score,

        "growth_score":
            growth_score,

        # Fed
        "fed_as_of_date":
            fed.get(
                "as_of_date"
            ),

        "latest_fomc":
            fed.get(
                "latest_fomc"
            ),

        "fed_chair":
            fed.get(
                "fed_chair"
            ),

        "statement_tone":
            statement.get(
                "tone"
            ),

        "statement_tone_score":
            statement.get(
                "tone_score"
            ),

        "fed_score":
            fed_score_value,

        # Financial Stress
        "financial_stress_source_date":
            stress_date,

        "financial_stress_age_days":
            stress_age,

        "financial_stress_composite":
            stress_composite,

        "financial_stress_regime":
            stress_regime,

        "vix":
            safe_float(
                stress.get(
                    "VIX"
                )
            ),

        "treasury_2y":
            safe_float(
                stress.get(
                    "TREASURY_2Y"
                )
            ),

        "treasury_10y":
            safe_float(
                stress.get(
                    "TREASURY_10Y"
                )
            ),

        "yield_10y_2y_spread":
            safe_float(
                stress.get(
                    "YIELD_10Y_2Y_SPREAD"
                )
            ),

        # Event / News
        "event_news_source_date":
            event_news_date,

        "event_news_age_days":
            event_news_age,

        "event_news_latest_topic":
            event_news.get(
                "latest_topic"
            ),

        "event_news_latest_source":
            event_news.get(
                "latest_source"
            ),

        "event_news_events_available":
            event_news.get(
                "events_available"
            ),

        # Research controls
        "research_only":
            True,

        "decision_engine_ready":
            False,

        "anti_lookahead":
            True,

        "economic_pit_safe":
            economic_pit_safe,

        "financial_stress_pit_safe":
            stress_pit_safe,

        "event_news_pit_safe":
            event_news.get(
                "pit_safe"
            ),
    }

    pd.DataFrame(
        [flat]
    ).to_csv(
        OUTPUT_CSV,
        index=False
    )

    # ========================================================
    # TERMINAL OUTPUT
    # ========================================================

    print()
    print(
        "Macro Context created successfully."
    )

    print(
        f"JSON: {OUTPUT_JSON}"
    )

    print(
        f"CSV:  {OUTPUT_CSV}"
    )

    print()

    print(
        "Economic regime:",
        economic_regime
    )

    print(
        "Economic age:",
        economic_age,
        "days"
    )

    print(
        "Financial stress regime:",
        stress_regime
    )

    print(
        "Financial stress age:",
        stress_age,
        "days"
    )

    print(
        "Fed score:",
        fed_score_value
    )

    print(
        "Event / News latest topic:",
        event_news.get(
            "latest_topic"
        )
    )

    print(
        "Event / News latest source:",
        event_news.get(
            "latest_source"
        )
    )

    print(
        "Event / News age:",
        event_news_age,
        "days"
    )

    print(
        "Event / News events available:",
        event_news.get(
            "events_available"
        )
    )

    print()
    print(
        "Research-only: TRUE"
    )

    print(
        "Decision Engine: FALSE"
    )

    print(
        "Trade signal: NONE"
    )

    print(
        "Forecast: NONE"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    build_macro_context()
