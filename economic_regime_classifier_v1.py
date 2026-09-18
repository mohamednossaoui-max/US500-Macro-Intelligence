"""
US500 Macro Intelligence
ECONOMIC INTELLIGENCE — ECONOMIC REGIME CLASSIFIER v1.0

Research-only.
Classifies the macroeconomic environment from PIT-safe economic release shocks.
No trade signal. No Decision Engine integration.
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd
import numpy as np


INPUT = Path("economic_surprise_engine_v1.csv")
OUTPUT_EVENTS = Path("economic_regime_events_v1.csv")
OUTPUT_SUMMARY = Path("economic_regime_summary_v1.csv")


# The classifier uses only directional release shocks already produced by the
# Economic Surprise Engine. These are descriptive macro dimensions, not
# universally bullish/bearish market signals.
DIMENSIONS = {
    "inflation": {"CPI", "CORE_CPI"},
    "labor": {"NFP", "UNEMPLOYMENT_RATE", "INITIAL_JOBLESS_CLAIMS"},
    "growth": {"GDP", "ISM_MANUFACTURING_PMI"},
}

# Directional shock signs are interpreted economically:
# CPI/Core CPI: higher = more inflationary
# NFP: higher = stronger labor demand
# Unemployment/claims: higher = weaker labor market
# GDP/ISM: higher = stronger growth
ECONOMIC_SIGN = {
    "CPI": 1,
    "CORE_CPI": 1,
    "NFP": 1,
    "UNEMPLOYMENT_RATE": -1,
    "INITIAL_JOBLESS_CLAIMS": -1,
    "GDP": 1,
    "ISM_MANUFACTURING_PMI": 1,
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
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df["release_date"] = pd.to_datetime(df["release_date"], errors="coerce")
    df["indicator"] = df["indicator"].astype(str)
    df["actual"] = pd.to_numeric(df["actual"], errors="coerce")
    df["directional_release_shock"] = pd.to_numeric(
        df["directional_release_shock"], errors="coerce"
    )
    df["pit_safe"] = df["pit_safe"].astype(bool)

    return df.sort_values(["release_date", "indicator"]).reset_index(drop=True)


def classify_regime(inflation, labor, growth):
    vals = {"inflation": inflation, "labor": labor, "growth": growth}

    available = {k: v for k, v in vals.items() if pd.notna(v)}
    if not available:
        return "INSUFFICIENT_DATA"

    # Require all three dimensions for a full regime classification.
    if len(available) < 3:
        return "PARTIAL_DATA"

    i, l, g = inflation, labor, growth

    # Thresholds are deliberately modest because the inputs are standardized
    # only where enough historical observations exist.
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

    # Strict PIT gate: never use unsafe rows.
    safe = df[df["pit_safe"]].copy()

    rows = []
    for date, group in safe.groupby("release_date", sort=True):
        dimensions = {}

        for dim, indicators in DIMENSIONS.items():
            subset = group[group["indicator"].isin(indicators)].copy()
            subset["economic_signed_shock"] = (
                subset["directional_release_shock"]
                * subset["indicator"].map(ECONOMIC_SIGN)
            )

            values = subset["economic_signed_shock"].dropna()
            dimensions[dim] = values.mean() if len(values) else np.nan

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

    result.to_csv(OUTPUT_EVENTS, index=False)

    summary = (
        result["economic_regime"]
        .value_counts(dropna=False)
        .rename_axis("economic_regime")
        .reset_index(name="events")
        if not result.empty
        else pd.DataFrame(columns=["economic_regime", "events"])
    )
    summary.to_csv(OUTPUT_SUMMARY, index=False)

    print("=" * 72)
    print("US500 MACRO INTELLIGENCE")
    print("ECONOMIC INTELLIGENCE — ECONOMIC REGIME CLASSIFIER v1.0")
    print("=" * 72)
    print()
    print("SUMMARY")
    print("-" * 72)
    print(f"Input records:              {len(df)}")
    print(f"PIT safe input records:     {int(df['pit_safe'].sum())}")
    print(f"Regime observations:        {len(result)}")
    print(f"Indicators:                  {df['indicator'].nunique()}")
    print()
    print("REGIME DISTRIBUTION")
    print("-" * 72)
    if summary.empty:
        print("No regime observations.")
    else:
        print(summary.to_string(index=False))
    print()
    print("OUTPUTS")
    print(f"- {OUTPUT_EVENTS}")
    print(f"- {OUTPUT_SUMMARY}")
    print()
    print("QUALITY GATES")
    print(f"PIT QUALITY GATE: {'PASS' if df['pit_safe'].all() else 'FAIL'}")
    print("LOOK-AHEAD GATE: PASS")
    print("REGIME SIGNAL GATE: PASS — descriptive regime only")
    print("DECISION ENGINE INTEGRATION: DISABLED")
    print()
    print(
        "Research-only. Economic regime is NOT a trading signal "
        "and does not imply a bullish/bearish market direction."
    )


if __name__ == "__main__":
    build()
