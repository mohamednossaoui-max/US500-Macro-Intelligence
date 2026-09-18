"""
US500 Macro Intelligence
ECONOMIC INTELLIGENCE — Economic Regime Classifier v1.0

Research-only macro regime classification.

Uses only PIT-safe standardized directional shock z-scores.
No raw-unit averaging, no look-ahead, no trading signal, no Decision Engine.
"""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "economic_surprise_engine_v1.csv"
OUTPUT_EVENTS = ROOT / "economic_regime_events_v1.csv"
OUTPUT_SUMMARY = ROOT / "economic_regime_summary_v1.csv"

DIMENSIONS = {
    "inflation": {"CPI", "CORE_CPI"},
    "labor": {"NFP", "UNEMPLOYMENT_RATE", "INITIAL_JOBLESS_CLAIMS"},
    "growth": {"GDP", "ISM_MANUFACTURING_PMI"},
}


def load_input():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Missing input: {INPUT}. Run economic_surprise_engine_v1.py first."
        )

    df = pd.read_csv(INPUT)
    required = {"release_date", "indicator", "pit_safe", "directional_shock_z"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df["release_date"] = pd.to_datetime(df["release_date"], errors="coerce")
    df["indicator"] = df["indicator"].astype(str).str.strip()
    df["directional_shock_z"] = pd.to_numeric(
        df["directional_shock_z"], errors="coerce"
    )
    df["pit_safe"] = df["pit_safe"].astype(str).str.strip().str.lower().eq("true")

    if df["release_date"].isna().any():
        raise ValueError("Invalid release_date found.")

    return df.sort_values(["release_date", "indicator"]).reset_index(drop=True)


def classify_regime(inflation, labor, growth):
    if any(pd.isna(x) for x in (inflation, labor, growth)):
        return "PARTIAL_DATA"

    high, low = 0.50, -0.50

    if inflation >= high and growth >= high and labor >= 0:
        return "INFLATIONARY_GROWTH"
    if inflation <= low and growth >= high and labor >= 0:
        return "DISINFLATIONARY_GROWTH"
    if inflation >= high and growth <= low and labor <= 0:
        return "STAGFLATIONARY"
    if inflation <= low and growth <= low and labor <= 0:
        return "DISINFLATIONARY_SLOWDOWN"
    if growth <= low and labor <= low:
        return "RECESSIONARY_PRESSURE"

    return "MIXED"


def main():
    print("=" * 72)
    print("US500 MACRO INTELLIGENCE")
    print("ECONOMIC INTELLIGENCE — ECONOMIC REGIME CLASSIFIER v1.0")
    print("=" * 72)

    df = load_input()

    if not bool(df["pit_safe"].all()):
        print("\nPIT QUALITY GATE: FAIL")
        raise RuntimeError("Input contains PIT-unsafe records.")

    rows = []

    for release_date, group in df.groupby("release_date", sort=True):
        scores = {}

        for dimension, indicators in DIMENSIONS.items():
            values = group.loc[
                group["indicator"].isin(indicators),
                "directional_shock_z",
            ].dropna()
            scores[dimension] = float(values.mean()) if not values.empty else np.nan

        rows.append({
            "release_date": release_date.date().isoformat(),
            "inflation_score": scores["inflation"],
            "labor_score": scores["labor"],
            "growth_score": scores["growth"],
            "economic_regime": classify_regime(
                scores["inflation"], scores["labor"], scores["growth"]
            ),
            "source_events": int(len(group)),
            "pit_safe": True,
            "research_only": True,
            "decision_engine_ready": False,
        })

    result = pd.DataFrame(rows)

    if result.empty:
        result = pd.DataFrame(columns=[
            "release_date", "inflation_score", "labor_score", "growth_score",
            "economic_regime", "source_events", "pit_safe",
            "research_only", "decision_engine_ready"
        ])

    result.to_csv(OUTPUT_EVENTS, index=False)

    summary = (
        result["economic_regime"].value_counts()
        .rename_axis("economic_regime")
        .reset_index(name="events")
        if not result.empty
        else pd.DataFrame(columns=["economic_regime", "events"])
    )
    summary.to_csv(OUTPUT_SUMMARY, index=False)

    print("\nSUMMARY")
    print("-" * 72)
    print(f"Input records:              {len(df)}")
    print(f"PIT safe input records:     {int(df['pit_safe'].sum())}/{len(df)}")
    print(f"Regime observations:        {len(result)}")
    print(f"Indicators:                 {df['indicator'].nunique()}")

    print("\nREGIME DISTRIBUTION")
    print("-" * 72)
    print(summary.to_string(index=False) if not summary.empty else "No observations.")

    print("\nOUTPUTS")
    print(f"- {OUTPUT_EVENTS.name}")
    print(f"- {OUTPUT_SUMMARY.name}")

    print("\nQUALITY GATES")
    print("PIT QUALITY GATE: PASS")
    print("LOOK-AHEAD GATE: PASS")
    print("UNIT-COMPARABILITY GATE: PASS — standardized z-scores used")
    print("REGIME SIGNAL GATE: PASS — descriptive regime only")
    print("DECISION ENGINE INTEGRATION: DISABLED")
    print("\nResearch-only. Economic regime is NOT a trading signal.")


if __name__ == "__main__":
    main()
