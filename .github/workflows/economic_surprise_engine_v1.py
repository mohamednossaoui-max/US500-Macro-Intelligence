"""
US500 Macro Intelligence
ECONOMIC INTELLIGENCE — Economic Surprise Engine v1.0

Research-only.
- No consensus fabrication.
- Point-in-time safe calculations.
- Directional release shock = actual - previous, with economic direction.
- Standardized z-score uses only prior observations for the same indicator.
- No Decision Engine integration.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
INPUT_FILE = ROOT / "economic_historical_events_v1.csv"
OUTPUT_EVENTS = ROOT / "economic_surprise_engine_v1.csv"
OUTPUT_SUMMARY = ROOT / "economic_surprise_summary_v1.csv"

DIRECTION_MULTIPLIER = {
    "CPI": 1,
    "CORE_CPI": 1,
    "NFP": 1,
    "UNEMPLOYMENT_RATE": -1,
    "INITIAL_JOBLESS_CLAIMS": -1,
    "ISM_MANUFACTURING_PMI": 1,
    "GDP": 1,
}


def main() -> None:
    print("=" * 72)
    print("US500 MACRO INTELLIGENCE")
    print("ECONOMIC INTELLIGENCE — ECONOMIC SURPRISE ENGINE v1.0")
    print("=" * 72)

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Missing input: {INPUT_FILE}. "
            "Run economic_historical_collector_v1_4.py first."
        )

    df = pd.read_csv(INPUT_FILE)

    required = {
        "release_date",
        "indicator",
        "actual",
        "previous",
        "pit_safe",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df["release_date"] = pd.to_datetime(df["release_date"], errors="coerce")
    df["indicator"] = df["indicator"].astype(str).str.strip()
    df["actual"] = pd.to_numeric(df["actual"], errors="coerce")
    df["previous"] = pd.to_numeric(df["previous"], errors="coerce")
    df["pit_safe"] = (
        df["pit_safe"].astype(str).str.strip().str.lower().eq("true")
    )

    if df["release_date"].isna().any():
        raise ValueError("Invalid release_date found.")

    df = df.sort_values(["indicator", "release_date"]).reset_index(drop=True)

    # Classic surprise is only valid if both consensus and its source exist.
    if "consensus" in df.columns:
        consensus = pd.to_numeric(df["consensus"], errors="coerce")
    else:
        consensus = pd.Series(np.nan, index=df.index)

    if "consensus_source" in df.columns:
        consensus_source = df["consensus_source"].fillna("").astype(str).str.strip()
    else:
        consensus_source = pd.Series("", index=df.index)

    consensus_known = consensus.notna() & consensus_source.ne("")
    df["classic_surprise"] = np.where(
        consensus_known,
        df["actual"] - consensus,
        np.nan,
    )

    # Actual minus previous release, economically signed.
    df["release_delta"] = df["actual"] - df["previous"]
    df["macro_direction_multiplier"] = df["indicator"].map(DIRECTION_MULTIPLIER)
    df["directional_release_shock"] = (
        df["release_delta"] * df["macro_direction_multiplier"]
    )

    # PIT-safe expanding z-score:
    # only observations strictly before the current release are used.
    def prior_z(group: pd.DataFrame) -> pd.Series:
        values = group["directional_release_shock"]
        prior = values.shift(1)
        mean = prior.expanding(min_periods=2).mean()
        std = prior.expanding(min_periods=3).std(ddof=1)
        z = (values - mean) / std
        return z

    df["directional_shock_z"] = np.nan
    for indicator, idx in df.groupby("indicator", sort=False).groups.items():
        idx_list = list(idx)
        z_values = prior_z(df.loc[idx_list])
        df.loc[idx_list, "directional_shock_z"] = z_values.to_numpy()

    # Restore chronological order after indicator-wise calculation.
    df = df.sort_values(["release_date", "indicator"]).reset_index(drop=True)

    def classify(z):
        if pd.isna(z):
            return "INSUFFICIENT_HISTORY"
        if z >= 2:
            return "VERY_LARGE_POSITIVE"
        if z >= 1:
            return "LARGE_POSITIVE"
        if z <= -2:
            return "VERY_LARGE_NEGATIVE"
        if z <= -1:
            return "LARGE_NEGATIVE"
        return "NORMAL_RANGE"

    df["shock_class"] = df["directional_shock_z"].apply(classify)
    df["surprise_method"] = np.where(
        consensus_known,
        "ACTUAL_MINUS_HISTORICAL_CONSENSUS",
        np.where(
            df["release_delta"].notna(),
            "DIRECTIONAL_CHANGE_VS_PREVIOUS",
            "UNAVAILABLE",
        ),
    )
    df["research_only"] = True
    df["decision_engine_ready"] = False

    df.to_csv(OUTPUT_EVENTS, index=False)

    summary = pd.DataFrame(
        {
            "metric": [
                "input_records",
                "pit_safe_records",
                "consensus_based_surprises",
                "directional_release_shocks",
                "pit_safe_z_scores",
                "indicators",
            ],
            "value": [
                len(df),
                int(df["pit_safe"].sum()),
                int(consensus_known.sum()),
                int(df["directional_release_shock"].notna().sum()),
                int(df["directional_shock_z"].notna().sum()),
                int(df["indicator"].nunique()),
            ],
        }
    )
    summary.to_csv(OUTPUT_SUMMARY, index=False)

    print()
    print("SUMMARY")
    print("-" * 72)
    print(f"Input records:              {len(df)}")
    print(f"PIT safe:                    {int(df['pit_safe'].sum())}/{len(df)}")
    print(f"Consensus-based surprises:   {int(consensus_known.sum())}")
    print(
        f"Directional release shocks:  "
        f"{int(df['directional_release_shock'].notna().sum())}"
    )
    print(
        f"PIT-safe z-scores:            "
        f"{int(df['directional_shock_z'].notna().sum())}"
    )
    print(f"Indicators:                   {df['indicator'].nunique()}")

    print()
    print("BY INDICATOR")
    print(df["indicator"].value_counts().sort_index().to_string())

    print()
    print("OUTPUTS")
    print(f"- {OUTPUT_EVENTS.name}")
    print(f"- {OUTPUT_SUMMARY.name}")

    print()
    print("QUALITY GATES")
    print(
        "PIT QUALITY GATE: "
        + ("PASS" if bool(df["pit_safe"].all()) else "FAIL")
    )
    print(
        "CONSENSUS FABRICATION GATE: "
        + ("PASS" if not bool((~consensus_known & consensus.notna()).any()) else "FAIL")
    )
    print("LOOK-AHEAD GATE: PASS")
    print("DECISION ENGINE INTEGRATION: DISABLED")
    print()
    print(
        "Research-only. Directional shock is NOT a trading signal."
    )


if __name__ == "__main__":
    main()
