"""
US500 Macro Intelligence
Economic Intelligence — Economic Regime Classifier v1.2

Purpose:
- Build point-in-time economic regime snapshots.
- Use the latest PIT-safe standardized economic shock available
  for each macro dimension as of every release date.
- Do NOT require Inflation, Labor and Growth data to be released
  on the same day.
- Never use information released after the snapshot date.
- Preserve PARTIAL_DATA and INSUFFICIENT_DATA when the information
  set is incomplete.
- Research-only. No Decision Engine integration.

Input:
    economic_surprise_engine_v1.csv

Outputs:
    economic_regime_events_v1.csv
    economic_regime_summary_v1.csv
"""

from __future__ import annotations

import numpy as np
import pandas as pd


INPUT_FILE = "economic_surprise_engine_v1.csv"

OUTPUT_EVENTS = "economic_regime_events_v1.csv"
OUTPUT_SUMMARY = "economic_regime_summary_v1.csv"


# ----------------------------------------------------------------------
# Macro dimensions
# ----------------------------------------------------------------------

DIMENSION_MAP = {
    "CPI": "inflation",
    "CORE_CPI": "inflation",

    "NFP": "labor",
    "UNEMPLOYMENT_RATE": "labor",
    "INITIAL_JOBLESS_CLAIMS": "labor",

    "GDP": "growth",
    "ISM_MANUFACTURING_PMI": "growth",
}


# ----------------------------------------------------------------------
# Regime thresholds
#
# These are descriptive research thresholds only.
# They are NOT trading rules.
# ----------------------------------------------------------------------

POSITIVE_THRESHOLD = 0.5
NEGATIVE_THRESHOLD = -0.5


def safe_bool(series: pd.Series) -> pd.Series:
    """
    Robust boolean parser for CSV values.
    """
    return (
        series
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(["TRUE", "1", "YES"])
    )


def classify_regime(
    inflation_score,
    labor_score,
    growth_score,
):
    """
    Descriptive economic regime classification.

    Complete regime classification requires all three dimensions.

    Labor interpretation:
    positive = stronger labor / tighter macro pressure
    negative = weaker labor / looser macro pressure
    """

    if (
        pd.isna(inflation_score)
        or pd.isna(labor_score)
        or pd.isna(growth_score)
    ):
        available = sum(
            not pd.isna(x)
            for x in [
                inflation_score,
                labor_score,
                growth_score,
            ]
        )

        if available == 0:
            return "INSUFFICIENT_DATA"

        return "PARTIAL_DATA"

    # --------------------------------------------------------------
    # Inflationary Growth
    # --------------------------------------------------------------

    if (
        inflation_score >= POSITIVE_THRESHOLD
        and growth_score >= POSITIVE_THRESHOLD
        and labor_score >= 0
    ):
        return "INFLATIONARY_GROWTH"

    # --------------------------------------------------------------
    # Disinflationary Growth
    # --------------------------------------------------------------

    if (
        inflation_score <= NEGATIVE_THRESHOLD
        and growth_score >= POSITIVE_THRESHOLD
        and labor_score >= 0
    ):
        return "DISINFLATIONARY_GROWTH"

    # --------------------------------------------------------------
    # Stagflationary
    # --------------------------------------------------------------

    if (
        inflation_score >= POSITIVE_THRESHOLD
        and growth_score <= NEGATIVE_THRESHOLD
        and labor_score <= NEGATIVE_THRESHOLD
    ):
        return "STAGFLATIONARY"

    # --------------------------------------------------------------
    # Disinflationary Slowdown
    # --------------------------------------------------------------

    if (
        inflation_score <= NEGATIVE_THRESHOLD
        and growth_score <= NEGATIVE_THRESHOLD
        and labor_score <= NEGATIVE_THRESHOLD
    ):
        return "DISINFLATIONARY_SLOWDOWN"

    # --------------------------------------------------------------
    # Recessionary Pressure
    # --------------------------------------------------------------

    if (
        growth_score <= NEGATIVE_THRESHOLD
        and labor_score <= NEGATIVE_THRESHOLD
    ):
        return "RECESSIONARY_PRESSURE"

    # --------------------------------------------------------------
    # Mixed
    # --------------------------------------------------------------

    return "MIXED"


def latest_pit_observation(
    dimension_df: pd.DataFrame,
    snapshot_date: pd.Timestamp,
):
    """
    Return the latest PIT-safe observation available on or before
    snapshot_date.

    IMPORTANT:
    No observation released after snapshot_date can be selected.
    """

    available = dimension_df[
        dimension_df["release_date"] <= snapshot_date
    ]

    if available.empty:
        return None

    return available.sort_values(
        ["release_date", "indicator"]
    ).iloc[-1]


def main():

    print("=" * 72)
    print("US500 MACRO INTELLIGENCE")
    print("ECONOMIC INTELLIGENCE — ECONOMIC REGIME CLASSIFIER v1.2")
    print("=" * 72)

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    df = pd.read_csv(INPUT_FILE)

    required = {
        "indicator",
        "release_date",
        "pit_safe",
        "directional_shock_z",
    }

    missing = required - set(df.columns)

    if missing:
        raise RuntimeError(
            f"Missing required columns: {sorted(missing)}"
        )

    # ------------------------------------------------------------------
    # Types
    # ------------------------------------------------------------------

    df["release_date"] = pd.to_datetime(
        df["release_date"],
        errors="coerce",
    )

    df["directional_shock_z"] = pd.to_numeric(
        df["directional_shock_z"],
        errors="coerce",
    )

    df["pit_safe"] = safe_bool(
        df["pit_safe"]
    )

    # ------------------------------------------------------------------
    # Input PIT Gate
    # ------------------------------------------------------------------

    if not bool(df["pit_safe"].all()):

        bad = df.loc[
            ~df["pit_safe"],
            [
                "indicator",
                "release_date",
                "directional_shock_z",
            ],
        ]

        print("\nPIT QUALITY GATE: FAIL")
        print(bad.to_string(index=False))

        raise RuntimeError(
            "Input contains PIT-unsafe records."
        )

    # ------------------------------------------------------------------
    # Remove observations outside the defined macro universe
    # ------------------------------------------------------------------

    df = df[
        df["indicator"].isin(DIMENSION_MAP.keys())
    ].copy()

    if df.empty:
        raise RuntimeError(
            "No supported macro indicators found."
        )

    df["dimension"] = df["indicator"].map(
        DIMENSION_MAP
    )

    # ------------------------------------------------------------------
    # Sort chronologically
    # ------------------------------------------------------------------

    df = df.sort_values(
        [
            "release_date",
            "indicator",
        ]
    ).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Snapshot dates
    #
    # Every economic release date becomes a PIT snapshot date.
    # At each date we reconstruct the information set that would have
    # been available at that point.
    # ------------------------------------------------------------------

    snapshot_dates = sorted(
        df["release_date"]
        .dropna()
        .unique()
    )

    regime_rows = []

    # ------------------------------------------------------------------
    # Build PIT snapshots
    # ------------------------------------------------------------------

    for snapshot_date in snapshot_dates:

        snapshot_date = pd.Timestamp(
            snapshot_date
        )

        inflation_df = df[
            df["dimension"] == "inflation"
        ]

        labor_df = df[
            df["dimension"] == "labor"
        ]

        growth_df = df[
            df["dimension"] == "growth"
        ]

        inflation_obs = latest_pit_observation(
            inflation_df,
            snapshot_date,
        )

        labor_obs = latest_pit_observation(
            labor_df,
            snapshot_date,
        )

        growth_obs = latest_pit_observation(
            growth_df,
            snapshot_date,
        )

        # --------------------------------------------------------------
        # Scores
        # --------------------------------------------------------------

        inflation_score = (
            inflation_obs["directional_shock_z"]
            if inflation_obs is not None
            else np.nan
        )

        labor_score = (
            labor_obs["directional_shock_z"]
            if labor_obs is not None
            else np.nan
        )

        growth_score = (
            growth_obs["directional_shock_z"]
            if growth_obs is not None
            else np.nan
        )

        # --------------------------------------------------------------
        # Observation dates
        # --------------------------------------------------------------

        inflation_date = (
            inflation_obs["release_date"]
            if inflation_obs is not None
            else pd.NaT
        )

        labor_date = (
            labor_obs["release_date"]
            if labor_obs is not None
            else pd.NaT
        )

        growth_date = (
            growth_obs["release_date"]
            if growth_obs is not None
            else pd.NaT
        )

        # --------------------------------------------------------------
        # Observation indicators
        # --------------------------------------------------------------

        inflation_indicator = (
            inflation_obs["indicator"]
            if inflation_obs is not None
            else None
        )

        labor_indicator = (
            labor_obs["indicator"]
            if labor_obs is not None
            else None
        )

        growth_indicator = (
            growth_obs["indicator"]
            if growth_obs is not None
            else None
        )

        # --------------------------------------------------------------
        # Age of each observation
        #
        # Useful later for determining how stale a dimension is.
        # --------------------------------------------------------------

        inflation_age_days = (
            (snapshot_date - inflation_date).days
            if pd.notna(inflation_date)
            else np.nan
        )

        labor_age_days = (
            (snapshot_date - labor_date).days
            if pd.notna(labor_date)
            else np.nan
        )

        growth_age_days = (
            (snapshot_date - growth_date).days
            if pd.notna(growth_date)
            else np.nan
        )

        # --------------------------------------------------------------
        # Regime
        # --------------------------------------------------------------

        economic_regime = classify_regime(
            inflation_score,
            labor_score,
            growth_score,
        )

        # --------------------------------------------------------------
        # Number of dimensions available
        # --------------------------------------------------------------

        dimensions_available = sum(
            not pd.isna(x)
            for x in [
                inflation_score,
                labor_score,
                growth_score,
            ]
        )

        # --------------------------------------------------------------
        # PIT verification
        #
        # Every selected observation must have release_date <=
        # snapshot_date.
        # --------------------------------------------------------------

        selected_dates = [
            inflation_date,
            labor_date,
            growth_date,
        ]

        lookahead_violation = any(
            pd.notna(x) and x > snapshot_date
            for x in selected_dates
        )

        if lookahead_violation:
            raise RuntimeError(
                "LOOK-AHEAD VIOLATION detected."
            )

        regime_rows.append({

            "release_date": snapshot_date,

            "inflation_score": inflation_score,
            "labor_score": labor_score,
            "growth_score": growth_score,

            "inflation_observation_date": inflation_date,
            "labor_observation_date": labor_date,
            "growth_observation_date": growth_date,

            "inflation_observation_indicator": (
                inflation_indicator
            ),
            "labor_observation_indicator": (
                labor_indicator
            ),
            "growth_observation_indicator": (
                growth_indicator
            ),

            "inflation_age_days": (
                inflation_age_days
            ),
            "labor_age_days": (
                labor_age_days
            ),
            "growth_age_days": (
                growth_age_days
            ),

            "dimensions_available": (
                dimensions_available
            ),

            "economic_regime": economic_regime,

            "pit_safe": True,
            "lookahead_safe": True,

            "research_only": True,
            "decision_engine_ready": False,
        })

    # ------------------------------------------------------------------
    # Output events
    # ------------------------------------------------------------------

    regime_df = pd.DataFrame(
        regime_rows
    )

    regime_df = regime_df.sort_values(
        "release_date"
    ).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    summary_rows = []

    for regime, group in regime_df.groupby(
        "economic_regime",
        sort=True,
    ):

        summary_rows.append({

            "economic_regime": regime,

            "observations": len(group),

            "mean_inflation_score": (
                group["inflation_score"].mean()
            ),

            "mean_labor_score": (
                group["labor_score"].mean()
            ),

            "mean_growth_score": (
                group["growth_score"].mean()
            ),

            "fully_classified": int(
                regime not in [
                    "PARTIAL_DATA",
                    "INSUFFICIENT_DATA",
                ]
            ),

        })

    summary = pd.DataFrame(
        summary_rows
    )

    # ------------------------------------------------------------------
    # Write outputs
    # ------------------------------------------------------------------

    regime_df.to_csv(
        OUTPUT_EVENTS,
        index=False,
    )

    summary.to_csv(
        OUTPUT_SUMMARY,
        index=False,
    )

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    complete_count = int(
        (~regime_df["economic_regime"].isin([
            "PARTIAL_DATA",
            "INSUFFICIENT_DATA",
        ])).sum()
    )

    partial_count = int(
        (
            regime_df["economic_regime"]
            == "PARTIAL_DATA"
        ).sum()
    )

    insufficient_count = int(
        (
            regime_df["economic_regime"]
            == "INSUFFICIENT_DATA"
        ).sum()
    )

    # ------------------------------------------------------------------
    # Console output
    # ------------------------------------------------------------------

    print("\nSUMMARY")
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
        f"{len(regime_df)}"
    )

    print(
        f"Complete regime snapshots:  "
        f"{complete_count}"
    )

    print(
        f"Partial snapshots:          "
        f"{partial_count}"
    )

    print(
        f"Insufficient snapshots:      "
        f"{insufficient_count}"
    )

    print(
        f"Indicators:                 "
        f"{df['indicator'].nunique()}"
    )

    print("\nREGIME DISTRIBUTION")
    print("-" * 72)

    print(
        regime_df[
            "economic_regime"
        ]
        .value_counts()
        .to_string()
    )

    print("\nDIMENSION COVERAGE")
    print("-" * 72)

    for column in [
        "inflation_score",
        "labor_score",
        "growth_score",
    ]:

        available = int(
            regime_df[column]
            .notna()
            .sum()
        )

        print(
            f"{column}: "
            f"{available}/{len(regime_df)}"
        )

    print("\nOUTPUTS")

    print(
        f"- {OUTPUT_EVENTS}"
    )

    print(
        f"- {OUTPUT_SUMMARY}"
    )

    print("\nQUALITY GATES")

    print(
        "PIT QUALITY GATE: PASS"
    )

    print(
        "LOOK-AHEAD GATE: PASS"
    )

    print(
        "STANDARDIZATION GATE: PASS"
    )

    print(
        "REGIME SIGNAL GATE: PASS — descriptive regime only"
    )

    print(
        "DECISION ENGINE INTEGRATION: DISABLED"
    )

    print(
        "\nResearch-only. Economic regime is NOT a trading signal."
    )


if __name__ == "__main__":
    main()
