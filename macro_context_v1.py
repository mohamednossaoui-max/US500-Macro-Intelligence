"""
US500 Macro Context Layer v1

Purpose:
    Combine the existing:
        - Economic Intelligence
        - Fed Intelligence
        - Financial Stress Intelligence

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

The script selects the latest available information as of the
Fed Intelligence as_of_date and preserves the age of each source.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd


FED_FILE = Path("fed_intelligence_output_v1.json")
ECONOMIC_FILE = Path("economic_regime_events_v1.csv")
FINANCIAL_STRESS_FILE = Path("financial_stress_research_v1.csv")

OUTPUT_JSON = Path("macro_context_v1.json")
OUTPUT_CSV = Path("macro_context_v1.csv")


def parse_date(value):
    if value is None or pd.isna(value):
        return None

    return pd.to_datetime(value).date()


def days_between(later, earlier):
    if later is None or earlier is None:
        return None

    return (later - earlier).days


def load_fed():
    if not FED_FILE.exists():
        raise FileNotFoundError(
            f"Missing required file: {FED_FILE}"
        )

    return json.loads(
        FED_FILE.read_text(encoding="utf-8")
    )


def load_economic(as_of_date):
    if not ECONOMIC_FILE.exists():
        raise FileNotFoundError(
            f"Missing required file: {ECONOMIC_FILE}"
        )

    df = pd.read_csv(ECONOMIC_FILE)

    if df.empty:
        raise ValueError("Economic regime file is empty.")

    df["release_date"] = pd.to_datetime(
        df["release_date"]
    ).dt.date

    # Anti-lookahead:
    # only observations released on or before the context date.
    df = df[
        df["release_date"] <= as_of_date
    ].copy()

    if df.empty:
        raise ValueError(
            "No economic observations available "
            "on or before the macro context date."
        )

    df = df.sort_values("release_date")

    return df.iloc[-1].to_dict()


def load_financial_stress(as_of_date):
    if not FINANCIAL_STRESS_FILE.exists():
        raise FileNotFoundError(
            f"Missing required file: {FINANCIAL_STRESS_FILE}"
        )

    df = pd.read_csv(FINANCIAL_STRESS_FILE)

    if df.empty:
        raise ValueError(
            "Financial stress research file is empty."
        )

    # Support the actual v1.3/v1.x column names.
    if "asof_date" not in df.columns:
        raise ValueError(
            "Financial stress file does not contain "
            "'asof_date'."
        )

    df["asof_date"] = pd.to_datetime(
        df["asof_date"]
    ).dt.date

    # Anti-lookahead.
    df = df[
        df["asof_date"] <= as_of_date
    ].copy()

    if df.empty:
        raise ValueError(
            "No financial stress observations available "
            "on or before the macro context date."
        )

    df = df.sort_values("asof_date")

    return df.iloc[-1].to_dict()


def safe_float(value):
    if value is None:
        return None

    try:
        value = float(value)

        if pd.isna(value):
            return None

        return value

    except (TypeError, ValueError):
        return None


def build_macro_context():
    print("=" * 70)
    print("US500 MACRO CONTEXT LAYER v1")
    print("=" * 70)

    # ---------------------------------------------------------
    # FED
    # ---------------------------------------------------------
    fed = load_fed()

    context_date = parse_date(
        fed.get("as_of_date")
    )

    if context_date is None:
        raise ValueError(
            "Fed Intelligence does not contain a valid "
            "'as_of_date'."
        )

    print(f"Context date: {context_date}")

    # ---------------------------------------------------------
    # ECONOMIC INTELLIGENCE
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # FINANCIAL STRESS
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # FED COMPONENTS
    # ---------------------------------------------------------
    statement = fed.get("statement") or {}
    phase_2b = fed.get("phase_2b") or {}
    fed_score = fed.get("fed_score")

    if isinstance(fed_score, dict):
        fed_score_value = (
            fed_score.get("score")
        )
    else:
        fed_score_value = fed_score

    sep_shift = fed.get("sep_shift")

    # ---------------------------------------------------------
    # ECONOMIC COMPONENTS
    # ---------------------------------------------------------
    economic_regime = economic.get(
        "economic_regime"
    )

    inflation_score = safe_float(
        economic.get("inflation_score")
    )

    labor_score = safe_float(
        economic.get("labor_score")
    )

    growth_score = safe_float(
        economic.get("growth_score")
    )

    dimensions_available = economic.get(
        "dimensions_available"
    )

    economic_pit_safe = bool(
        economic.get("pit_safe", False)
    )

    # ---------------------------------------------------------
    # FINANCIAL STRESS COMPONENTS
    # ---------------------------------------------------------
    stress_composite = safe_float(
        stress.get("composite_stress_score")
    )

    stress_regime = stress.get(
        "research_regime"
    )

    stress_pit_safe = bool(
        stress.get("point_in_time_safe", False)
    )

    # ---------------------------------------------------------
    # MACRO CONTEXT OBJECT
    # ---------------------------------------------------------
    context = {
        "methodology_version": "macro_context_v1",

        "context_date": context_date.isoformat(),

        "research_only": True,

        "decision_engine_ready": False,

        "trade_signal": None,

        "forecast": None,

        "economic": {
            "source_date": (
                economic_date.isoformat()
                if economic_date
                else None
            ),
            "age_days": economic_age,

            "economic_regime": economic_regime,

            "inflation_score": inflation_score,
            "labor_score": labor_score,
            "growth_score": growth_score,

            "dimensions_available":
                dimensions_available,

            "pit_safe": economic_pit_safe,
        },

        "fed": {
            "as_of_date": fed.get(
                "as_of_date"
            ),

            "latest_fomc": fed.get(
                "latest_fomc"
            ),

            "fed_chair": fed.get(
                "fed_chair"
            ),

            "statement_tone": statement.get(
                "tone"
            ),

            "statement_tone_score":
                statement.get("tone_score"),

            "phase_2b": phase_2b,

            "fed_score": fed_score_value,

            "sep_shift": sep_shift,

            "beige_book_available":
                (fed.get("beige_book") or {}).get(
                    "available"
                ),

            "pit_safe": True,
        },

        "financial_stress": {
            "source_date": (
                stress_date.isoformat()
                if stress_date
                else None
            ),

            "age_days": stress_age,

            "composite_stress_score":
                stress_composite,

            "research_regime":
                stress_regime,

            "vix": safe_float(
                stress.get("VIX")
            ),

            "treasury_2y": safe_float(
                stress.get("TREASURY_2Y")
            ),

            "treasury_10y": safe_float(
                stress.get("TREASURY_10Y")
            ),

            "yield_10y_2y_spread":
                safe_float(
                    stress.get(
                        "YIELD_10Y_2Y_SPREAD"
                    )
                ),

            "pit_safe": stress_pit_safe,
        },

        "temporal_alignment": {
            "economic_age_days":
                economic_age,

            "financial_stress_age_days":
                stress_age,

            "fed_is_current_snapshot": True,

            "anti_lookahead": True,

            "note": (
                "Sources are not forced to be "
                "same-day. Source age is preserved "
                "explicitly."
            ),
        },
    }

    # ---------------------------------------------------------
    # VALIDATION
    # ---------------------------------------------------------
    assert context["research_only"] is True
    assert context["decision_engine_ready"] is False
    assert context["trade_signal"] is None
    assert context["forecast"] is None

    assert economic_pit_safe is True
    assert stress_pit_safe is True

    # ---------------------------------------------------------
    # WRITE JSON
    # ---------------------------------------------------------
    OUTPUT_JSON.write_text(
        json.dumps(
            context,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ---------------------------------------------------------
    # WRITE ONE-ROW CSV
    # ---------------------------------------------------------
    flat = {
        "methodology_version":
            "macro_context_v1",

        "context_date":
            context["context_date"],

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

        "fed_as_of_date":
            fed.get("as_of_date"),

        "latest_fomc":
            fed.get("latest_fomc"),

        "fed_chair":
            fed.get("fed_chair"),

        "statement_tone":
            statement.get("tone"),

        "statement_tone_score":
            statement.get("tone_score"),

        "fed_score":
            fed_score_value,

        "financial_stress_source_date":
            stress_date,

        "financial_stress_age_days":
            stress_age,

        "financial_stress_composite":
            stress_composite,

        "financial_stress_regime":
            stress_regime,

        "vix":
            safe_float(stress.get("VIX")),

        "treasury_2y":
            safe_float(
                stress.get("TREASURY_2Y")
            ),

        "treasury_10y":
            safe_float(
                stress.get("TREASURY_10Y")
            ),

        "yield_10y_2y_spread":
            safe_float(
                stress.get(
                    "YIELD_10Y_2Y_SPREAD"
                )
            ),

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
    }

    pd.DataFrame([flat]).to_csv(
        OUTPUT_CSV,
        index=False
    )

    print()
    print("Macro Context created successfully.")
    print(f"JSON: {OUTPUT_JSON}")
    print(f"CSV:  {OUTPUT_CSV}")

    print()
    print("Economic regime:", economic_regime)
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

    print()
    print("Research-only: TRUE")
    print("Decision Engine: FALSE")
    print("Trade signal: NONE")
    print("Forecast: NONE")


if __name__ == "__main__":
    build_macro_context()
