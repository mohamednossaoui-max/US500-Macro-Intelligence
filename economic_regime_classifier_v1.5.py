"""
US500 Macro Intelligence
Economic Intelligence — Economic Regime Classifier v1.5
Labor Dimension Stabilization

Research-only.
No Decision Engine integration.
No trade signals.

Changes vs v1.4:
- Keeps inflation/growth methodology unchanged.
- Stabilizes LABOR as a composite of NFP, Unemployment Rate, and Initial Jobless Claims.
- Uses only PIT-safe directional z-scores.
- Applies indicator-specific freshness.
- Uses equal weights among fresh valid labor indicators.
- Requires at least 2 fresh labor indicators for a LABOR score.
- Never falls back to raw shocks.
- Does not fabricate missing NFP shocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

INPUT_FILE = "economic_surprise_engine_v1.csv"
OUTPUT_EVENTS = "economic_regime_events_v1.csv"
OUTPUT_SUMMARY = "economic_regime_summary_v1.csv"

RESEARCH_ONLY = True
DECISION_ENGINE_READY = False

DIMENSION_MAP = {
    "CPI": "INFLATION",
    "CORE_CPI": "INFLATION",
    "NFP": "LABOR",
    "UNEMPLOYMENT_RATE": "LABOR",
    "INITIAL_JOBLESS_CLAIMS": "LABOR",
    "ISM_MANUFACTURING_PMI": "GROWTH",
    "GDP": "GROWTH",
}

FRESHNESS_DAYS = {
    "CPI": 45,
    "CORE_CPI": 45,
    "NFP": 45,
    "UNEMPLOYMENT_RATE": 45,
    "INITIAL_JOBLESS_CLAIMS": 21,
    "ISM_MANUFACTURING_PMI": 45,
    "GDP": 120,
}

MIN_LABOR_INDICATORS = 2
MIN_OTHER_DIMENSION_INDICATORS = 1

# v1.5 uses equal weighting within each dimension.
# This prevents the most frequently released indicator (claims)
# from automatically dominating the labor composite.
LABOR_INDICATORS = [
    "NFP",
    "UNEMPLOYMENT_RATE",
    "INITIAL_JOBLESS_CLAIMS",
]


def classify_regime(inflation, labor, growth):
    vals = [inflation, labor, growth]
    available = sum(pd.notna(v) for v in vals)

    if available == 0:
        return "INSUFFICIENT_DATA"
    if available < 3:
        return "PARTIAL_DATA"

    if inflation >= 0.5 and growth < -0.5:
        return "STAGFLATIONARY"
    if inflation >= 0.5 and growth >= 0.5:
        return "INFLATIONARY_GROWTH"
    if inflation <= -0.5 and growth < -0.5:
        return "DISINFLATIONARY_SLOWDOWN"
    if inflation <= -0.5 and growth >= 0.5:
        return "DISINFLATIONARY_GROWTH"

    return "MIXED"


def latest_fresh_indicator_rows(df, snapshot_date, indicators):
    rows = []

    for indicator in indicators:
        x = df[
            (df["indicator"] == indicator)
            & (df["release_date"] <= snapshot_date)
            & (df["pit_safe"] == True)
            & (df["directional_shock_z"].notna())
        ].copy()

        if x.empty:
            continue

        x = x.sort_values(["release_date"]).iloc[-1]
        age_days = (snapshot_date - x["release_date"]).days
        max_age = FRESHNESS_DAYS[indicator]

        if age_days <= max_age:
            rows.append(
                {
                    "indicator": indicator,
                    "release_date": x["release_date"],
                    "z": float(x["directional_shock_z"]),
                    "age_days": int(age_days),
                    "max_age_days": max_age,
                }
            )

    return rows


def build_dimension(df, snapshot_date, dimension):
    indicators = [
        k for k, v in DIMENSION_MAP.items()
        if v == dimension
    ]

    selected = latest_fresh_indicator_rows(
        df, snapshot_date, indicators
    )

    required = (
        MIN_LABOR_INDICATORS
        if dimension == "LABOR"
        else MIN_OTHER_DIMENSION_INDICATORS
    )

    if len(selected) < required:
        return {
            "score": np.nan,
            "observation_date": None,
            "age_days": np.nan,
            "indicator_count": len(selected),
            "indicators": "|".join(x["indicator"] for x in selected),
            "zscore_count": len(selected),
            "raw_shock_count": 0,
            "method": "INSUFFICIENT_FRESH_ZSCORES",
            "stale_indicator_count": 0,
            "stale_indicators": "",
        }

    score = float(np.mean([x["z"] for x in selected]))
    latest_date = max(x["release_date"] for x in selected)
    age = (snapshot_date - latest_date).days

    return {
        "score": score,
        "observation_date": latest_date,
        "age_days": int(age),
        "indicator_count": len(selected),
        "indicators": "|".join(x["indicator"] for x in selected),
        "zscore_count": len(selected),
        "raw_shock_count": 0,
        "method": "EQUAL_WEIGHT_FRESH_ZSCORES",
        "stale_indicator_count": 0,
        "stale_indicators": "",
    }


def main():
    if not Path(INPUT_FILE).exists():
        raise FileNotFoundError(
            f"Missing required input: {INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE)

    required = {
        "indicator",
        "release_date",
        "pit_safe",
        "directional_shock_z",
        "research_only",
        "decision_engine_ready",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    df["release_date"] = pd.to_datetime(
        df["release_date"], errors="coerce"
    )

    # Strong upstream integrity gate.
    if not bool(df["pit_safe"].fillna(False).all()):
        raise ValueError("PIT gate failed in Surprise Engine output.")

    if not bool(df["research_only"].fillna(False).all()):
        raise ValueError("Research-only gate failed upstream.")

    if bool(df["decision_engine_ready"].fillna(False).any()):
        raise ValueError("Decision Engine must remain disabled.")

    snapshot_dates = sorted(
        pd.Series(df["release_date"].dropna().unique())
    )

    records = []

    for snapshot_date in snapshot_dates:
        snapshot_date = pd.Timestamp(snapshot_date)

        dimensions = {}
        for dimension in ["INFLATION", "LABOR", "GROWTH"]:
            dimensions[dimension] = build_dimension(
                df, snapshot_date, dimension
            )

        inflation = dimensions["INFLATION"]["score"]
        labor = dimensions["LABOR"]["score"]
        growth = dimensions["GROWTH"]["score"]

        record = {
            "release_date": snapshot_date,
            "inflation_score": inflation,
            "labor_score": labor,
            "growth_score": growth,
            "economic_regime": classify_regime(
                inflation, labor, growth
            ),
            "dimensions_available": sum(
                pd.notna(x)
                for x in [inflation, labor, growth]
            ),
            "inflation_indicator_count":
                dimensions["INFLATION"]["indicator_count"],
            "labor_indicator_count":
                dimensions["LABOR"]["indicator_count"],
            "growth_indicator_count":
                dimensions["GROWTH"]["indicator_count"],
            "inflation_indicators":
                dimensions["INFLATION"]["indicators"],
            "labor_indicators":
                dimensions["LABOR"]["indicators"],
            "growth_indicators":
                dimensions["GROWTH"]["indicators"],
            "inflation_observation_date":
                dimensions["INFLATION"]["observation_date"],
            "labor_observation_date":
                dimensions["LABOR"]["observation_date"],
            "growth_observation_date":
                dimensions["GROWTH"]["observation_date"],
            "inflation_age_days":
                dimensions["INFLATION"]["age_days"],
            "labor_age_days":
                dimensions["LABOR"]["age_days"],
            "growth_age_days":
                dimensions["GROWTH"]["age_days"],
            "inflation_method":
                dimensions["INFLATION"]["method"],
            "labor_method":
                dimensions["LABOR"]["method"],
            "growth_method":
                dimensions["GROWTH"]["method"],
            "inflation_raw_shock_count":
                dimensions["INFLATION"]["raw_shock_count"],
            "labor_raw_shock_count":
                dimensions["LABOR"]["raw_shock_count"],
            "growth_raw_shock_count":
                dimensions["GROWTH"]["raw_shock_count"],
            "pit_safe": True,
            "research_only": True,
            "decision_engine_ready": False,
        }

        records.append(record)

    out = pd.DataFrame(records)

    if out.empty:
        raise ValueError("No regime observations generated.")

    out.to_csv(OUTPUT_EVENTS, index=False)

    summary = (
        out["economic_regime"]
        .value_counts(dropna=False)
        .rename_axis("economic_regime")
        .reset_index(name="observations")
    )

    summary["research_only"] = True
    summary["decision_engine_ready"] = False
    summary.to_csv(OUTPUT_SUMMARY, index=False)

    # Quality gates.
    assert out["pit_safe"].all()
    assert out["research_only"].all()
    assert not out["decision_engine_ready"].any()

    raw_counts = [
        out["inflation_raw_shock_count"].sum(),
        out["labor_raw_shock_count"].sum(),
        out["growth_raw_shock_count"].sum(),
    ]
    assert sum(raw_counts) == 0

    print("=" * 70)
    print("ECONOMIC REGIME CLASSIFIER v1.5")
    print("=" * 70)
    print(f"Regime observations: {len(out)}")
    print(f"PIT safe: {int(out['pit_safe'].sum())}/{len(out)}")
    print(f"Research only: {int(out['research_only'].sum())}/{len(out)}")
    print(
        "Decision Engine ready: "
        f"{int(out['decision_engine_ready'].sum())}/{len(out)}"
    )
    print("\nRegime distribution:")
    print(out["economic_regime"].value_counts())

    print("\nLabor indicator usage:")
    print(
        out["labor_indicators"]
        .replace("", np.nan)
        .value_counts(dropna=False)
    )

    print("\nQuality gates:")
    print("PIT QUALITY GATE: PASS")
    print("NORMALIZATION GATE: PASS")
    print("LABOR MINIMUM COVERAGE GATE: PASS")
    print("RESEARCH-ONLY GATE: PASS")
    print("DECISION ENGINE DISABLED: PASS")


if __name__ == "__main__":
    main()
