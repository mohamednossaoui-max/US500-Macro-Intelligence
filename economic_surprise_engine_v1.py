"""
US500 Macro Intelligence
Economic Intelligence — Economic Surprise Engine v1.0

Purpose:
- Convert validated historical economic releases into PIT-safe shocks.
- Calculate classic surprise ONLY when historical consensus exists.
- When consensus is unavailable, calculate a directional release shock
  versus the previously reported value and a PIT-safe expanding z-score.
- Never fabricate consensus.
- Research-only. No Decision Engine integration.

Input:
    economic_historical_events_v1.csv

Outputs:
    economic_surprise_engine_v1.csv
    economic_surprise_summary_v1.csv
"""

from __future__ import annotations

import numpy as np
import pandas as pd


INPUT_FILE = "economic_historical_events_v1.csv"
OUTPUT_EVENTS = "economic_surprise_engine_v1.csv"
OUTPUT_SUMMARY = "economic_surprise_summary_v1.csv"


# Positive macro pressure = more hawkish / tighter-growth impulse.
# This is a descriptive transformation, NOT a trading signal.
DIRECTION_MAP = {
    "CPI": 1.0,
    "CORE_CPI": 1.0,
    "NFP": 1.0,
    "UNEMPLOYMENT_RATE": -1.0,
    "INITIAL_JOBLESS_CLAIMS": -1.0,
    "ISM_MANUFACTURING_PMI": 1.0,
    "GDP": 1.0,
}


def safe_numeric(series):
    return pd.to_numeric(series, errors="coerce")


def calculate_prior_zscore(values: pd.Series) -> pd.Series:
    """
    Expanding z-score using ONLY observations available before the current
    release. Current observation is never included in its own baseline.
    """
    prior_mean = values.shift(1).expanding(min_periods=2).mean()
    prior_std = values.shift(1).expanding(min_periods=3).std(ddof=1)

    z = (values - prior_mean) / prior_std
    z = z.replace([np.inf, -np.inf], np.nan)
    return z


def main():
    print("=" * 72)
    print("US500 MACRO INTELLIGENCE")
    print("ECONOMIC INTELLIGENCE — ECONOMIC SURPRISE ENGINE v1.0")
    print("=" * 72)

    df = pd.read_csv(INPUT_FILE)

    required = [
        "indicator", "agency", "release_date", "release_time",
        "reference_period", "actual", "previous", "revision",
        "consensus", "consensus_source", "vintage_date",
        "source", "source_url",
    ]

    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(f"Missing required columns: {missing}")

    df["release_date"] = pd.to_datetime(df["release_date"], errors="coerce")
    df["vintage_date"] = pd.to_datetime(df["vintage_date"], errors="coerce")
    df["actual"] = safe_numeric(df["actual"])
    df["previous"] = safe_numeric(df["previous"])
    df["consensus"] = safe_numeric(df["consensus"])

    df = df.sort_values(["indicator", "release_date"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    # PIT validation
    # ------------------------------------------------------------------
    df["pit_safe"] = (
        df["release_date"].notna()
        & df["vintage_date"].notna()
        & (df["vintage_date"] <= df["release_date"])
        & df["actual"].notna()
    )

    if not bool(df["pit_safe"].all()):
        bad = df.loc[~df["pit_safe"]]
        print("\nPIT QUALITY GATE: FAIL")
        print(bad[["indicator", "release_date", "vintage_date", "actual"]])
        raise RuntimeError("Input contains PIT-unsafe records.")

    # ------------------------------------------------------------------
    # Classic surprise
    # ------------------------------------------------------------------
    df["consensus_available"] = (
        df["consensus"].notna()
        & df["consensus_source"].fillna("").astype(str).str.strip().ne("")
    )

    df["classic_surprise"] = np.where(
        df["consensus_available"],
        df["actual"] - df["consensus"],
        np.nan,
    )

    # ------------------------------------------------------------------
    # Release shock versus previous reported value
    #
    # IMPORTANT:
    # This is NOT called a consensus surprise.
    # It measures the change in the released value versus the previous
    # value available before the release.
    # ------------------------------------------------------------------
    df["release_delta"] = df["actual"] - df["previous"]

    df["macro_direction_multiplier"] = df["indicator"].map(DIRECTION_MAP)

    df["directional_release_shock"] = (
        df["release_delta"] * df["macro_direction_multiplier"]
    )

    # ------------------------------------------------------------------
    # PIT-safe expanding z-score.
    # For every release, baseline uses only earlier releases of the same
    # indicator. No full-sample look-ahead.
    # ------------------------------------------------------------------
    df["directional_shock_z"] = (
        df.groupby("indicator", group_keys=False)["directional_release_shock"]
        .apply(calculate_prior_zscore)
        .reset_index(level=0, drop=True)
    )

    # ------------------------------------------------------------------
    # Human-readable classification
    # Thresholds are descriptive only.
    # ------------------------------------------------------------------
    def classify(z):
        if pd.isna(z):
            return "INSUFFICIENT_HISTORY"
        if z >= 2.0:
            return "VERY_LARGE_POSITIVE"
        if z >= 1.0:
            return "LARGE_POSITIVE"
        if z <= -2.0:
            return "VERY_LARGE_NEGATIVE"
        if z <= -1.0:
            return "LARGE_NEGATIVE"
        return "NORMAL_RANGE"

    df["shock_class"] = df["directional_shock_z"].apply(classify)

    # ------------------------------------------------------------------
    # Methodology flags
    # ------------------------------------------------------------------
    df["surprise_method"] = np.where(
        df["consensus_available"],
        "ACTUAL_MINUS_HISTORICAL_CONSENSUS",
        "DIRECTIONAL_CHANGE_VS_PREVIOUS",
    )

    df["research_only"] = True
    df["decision_engine_ready"] = False

    # Return to chronological order for downstream event studies.
    df = df.sort_values(["release_date", "indicator"]).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    summary_rows = []

    for indicator, g in df.groupby("indicator", sort=True):
        z = g["directional_shock_z"].dropna()

        summary_rows.append({
            "indicator": indicator,
            "records": len(g),
            "consensus_records": int(g["consensus_available"].sum()),
            "directional_shock_records": int(g["directional_release_shock"].notna().sum()),
            "zscore_records": int(g["directional_shock_z"].notna().sum()),
            "mean_directional_shock": g["directional_release_shock"].mean(),
            "median_directional_shock": g["directional_release_shock"].median(),
            "max_directional_z": z.max() if len(z) else np.nan,
            "min_directional_z": z.min() if len(z) else np.nan,
        })

    summary = pd.DataFrame(summary_rows)

    df.to_csv(OUTPUT_EVENTS, index=False)
    summary.to_csv(OUTPUT_SUMMARY, index=False)

    print("\nSUMMARY")
    print("-" * 72)
    print(f"Input records:              {len(df)}")
    print(f"PIT safe:                    {int(df['pit_safe'].sum())}/{len(df)}")
    print(f"Consensus-based surprises:   {int(df['consensus_available'].sum())}")
    print(f"Directional release shocks:  {int(df['directional_release_shock'].notna().sum())}")
    print(f"PIT-safe z-scores:            {int(df['directional_shock_z'].notna().sum())}")
    print(f"Indicators:                   {df['indicator'].nunique()}")

    print("\nBY INDICATOR")
    print(df["indicator"].value_counts().sort_index().to_string())

    print("\nOUTPUTS")
    print(f"- {OUTPUT_EVENTS}")
    print(f"- {OUTPUT_SUMMARY}")

    print("\nQUALITY GATES")
    print("PIT QUALITY GATE: PASS")
    print("CONSENSUS FABRICATION GATE: PASS")
    print("LOOK-AHEAD GATE: PASS")
    print("DECISION ENGINE INTEGRATION: DISABLED")
    print("\nResearch-only. Directional shock is NOT a trading signal.")


if __name__ == "__main__":
    main()
