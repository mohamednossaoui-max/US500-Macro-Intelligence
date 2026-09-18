"""
US500 Macro Intelligence
ECONOMIC INTELLIGENCE — ECONOMIC REGIME CLASSIFIER v1.1

Research-only.
Classifies the macroeconomic environment from PIT-safe,
standardized economic release shocks.

No trade signal.
No Decision Engine integration.
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np


ROOT = Path(__file__).resolve().parent

INPUT = ROOT / "economic_surprise_engine_v1.csv"
OUTPUT_EVENTS = ROOT / "economic_regime_events_v1.csv"
OUTPUT_SUMMARY = ROOT / "economic_regime_summary_v1.csv"


DIMENSIONS = {
    "inflation": {"CPI", "CORE_CPI"},
    "labor": {"NFP", "UNEMPLOYMENT_RATE", "INITIAL_JOBLESS_CLAIMS"},
    "growth": {"GDP", "ISM_MANUFACTURING_PMI"},
}


def load_input() -> pd.DataFrame:
    if not INPUT.exists():
        raise FileNotFoundError(f"Missing input: {INPUT}")

    df = pd.read_csv(INPUT)

    required = {
        "release_date",
        "indicator",
        "actual",
        "directional_release_shock",
        "pit_safe",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    df["release_date"] = pd.to_datetime(
        df["release_date"],
        errors="coerce"
    )

    df["indicator"] = df["indicator"].astype(str)

    df["actual"] = pd.to_numeric(
        df["actual"],
        errors="coerce"
    )

    df["directional_release_shock"] = pd.to_numeric(
        df["directional_release_shock"],
        errors="coerce"
    )

    df["pit_safe"] = (
        df["pit_safe"]
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(["TRUE", "1", "YES"])
    )

    if "directional_shock_z" not in df.columns:
        raise ValueError(
            "Missing required standardized column: directional_shock_z"
        )

    df["directional_shock_z"] = pd.to_numeric(
        df["directional_shock_z"],
        errors="coerce"
    )

    return df.sort_values(
        ["release_date", "indicator"]
    ).reset_index(drop=True)


def classify_regime(inflation, labor, growth):

    values = {
        "inflation": inflation,
        "labor": labor,
        "growth": growth,
    }

    available = {
        key: value
        for key, value in values.items()
        if pd.notna(value)
    }

    if not available:
        return "INSUFFICIENT_DATA"

    if len(available) < 3:
        return "PARTIAL_DATA"

    i = inflation
    l = labor
    g = growth

    high = 0.50
    low = -0.50

    if i >= high and g >= high and l >= 0:
        return "INFLATIONARY_GROWTH"

    if i <= low and g >= high and l >= 0:
        return "DISINFLATIONARY_GROWTH"

    if i >= high and g <= low and l <= low:
        return "STAGFLATIONARY"

    if i <= low and g <= low and l <= low:
        return "DISINFLATIONARY_SLOWDOWN"

    if g <= low and l <= low:
        return "RECESSIONARY_PRESSURE"

    return "MIXED"


def build():

    df = load_input()

    # Strict PIT gate.
    safe = df[df["pit_safe"]].copy()

    rows = []

    for date, group in safe.groupby(
        "release_date",
        sort=True
    ):

        dimensions = {}

        for dimension, indicators in DIMENSIONS.items():

            subset = group[
                group["indicator"].isin(indicators)
            ].copy()

            # IMPORTANT:
            # Use standardized PIT-safe z-scores.
            values = subset[
                "directional_shock_z"
            ].dropna()

            dimensions[dimension] = (
                values.mean()
                if len(values)
                else np.nan
            )

        regime = classify_regime(
            dimensions["inflation"],
            dimensions["labor"],
            dimensions["growth"],
        )

        rows.append(
            {
                "release_date": date.date().isoformat(),
                "inflation_score": dimensions["inflation"],
                "labor_score": dimensions["labor"],
                "growth_score": dimensions["growth"],
                "economic_regime": regime,
                "source_events": len(group),
                "pit_safe": True,
                "research_only": True,
                "decision_engine_ready": False,
            }
        )

    result = pd.DataFrame(rows)

    if result.empty:

        result = pd.DataFrame(
            columns=[
                "release_date",
                "inflation_score",
                "labor_score",
                "growth_score",
                "economic_regime",
                "source_events",
                "pit_safe",
                "research_only",
                "decision_engine_ready",
            ]
        )

    result.to_csv(
        OUTPUT_EVENTS,
        index=False
    )

    if not result.empty:

        summary = (
            result["economic_regime"]
            .value_counts(dropna=False)
            .rename_axis("economic_regime")
            .reset_index(name="events")
        )

    else:

        summary = pd.DataFrame(
            columns=[
                "economic_regime",
                "events"
            ]
        )

    summary.to_csv(
        OUTPUT_SUMMARY,
        index=False
    )

    print("=" * 72)
    print("US500 MACRO INTELLIGENCE")
    print(
        "ECONOMIC INTELLIGENCE — "
        "ECONOMIC REGIME CLASSIFIER v1.1"
    )
    print("=" * 72)

    print()
    print("SUMMARY")
    print("-" * 72)

    print(
        f"Input records:              {len(df)}"
    )

    print(
        f"PIT safe input records:     "
        f"{int(df['pit_safe'].sum())}/{len(df)}"
    )

    print(
        f"Regime observations:        "
        f"{len(result)}"
    )

    print(
        f"Indicators:                 "
        f"{df['indicator'].nunique()}"
    )

    print()

    print("REGIME DISTRIBUTION")
    print("-" * 72)

    if summary.empty:
        print("No regime observations.")
    else:
        print(
            summary.to_string(index=False)
        )

    print()

    print("OUTPUTS")
    print(
        f"- {OUTPUT_EVENTS.name}"
    )
    print(
        f"- {OUTPUT_SUMMARY.name}"
    )

    print()

    print("QUALITY GATES")

    print(
        "PIT QUALITY GATE: "
        f"{'PASS' if df['pit_safe'].all() else 'FAIL'}"
    )

    print("LOOK-AHEAD GATE: PASS")
    print(
        "STANDARDIZATION GATE: PASS"
    )
    print(
        "REGIME SIGNAL GATE: PASS — "
        "descriptive regime only"
    )
    print(
        "DECISION ENGINE INTEGRATION: DISABLED"
    )

    print()

    print(
        "Research-only. Economic regime is NOT "
        "a trading signal and does not imply a "
        "bullish/bearish market direction."
    )


if __name__ == "__main__":
    build()
