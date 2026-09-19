"""
US500 Macro Intelligence
Economic Intelligence — Economic Surprise Engine v1.1

Purpose:
- Convert validated historical economic releases into PIT-safe shocks.
- Calculate classic surprise ONLY when historical consensus exists.
- Calculate directional release shocks versus the previously reported value.
- Calculate indicator-specific PIT-safe expanding z-scores.
- Require a minimum history before producing a z-score.
- NEVER mix raw shocks with z-scores.
- NEVER use future observations in the z-score baseline.
- Research-only. No Decision Engine integration.

Input:
    economic_historical_events_v1.csv

Outputs:
    economic_surprise_engine_v1.csv
    economic_surprise_summary_v1.csv

v1.1 methodological change:
    The z-score is calculated independently for each indicator
    using ONLY prior observations of that same indicator.

    Minimum prior observations required:
        3

    This prevents:
        - raw/z-score mixing
        - unstable early z-scores
        - cross-indicator contamination
        - look-ahead bias
"""

from __future__ import annotations

import numpy as np
import pandas as pd


INPUT_FILE = "economic_historical_events_v1.csv"

OUTPUT_EVENTS = "economic_surprise_engine_v1.csv"
OUTPUT_SUMMARY = "economic_surprise_summary_v1.csv"

# Minimum number of valid historical observations that must exist
# BEFORE the current release in order to calculate a z-score.
MIN_PRIOR_HISTORY = 3


# ----------------------------------------------------------------------
# Direction map
# ----------------------------------------------------------------------
#
# Positive macro pressure = more hawkish / tighter-growth impulse.
#
# This is a descriptive transformation only.
# It is NOT a trading signal.
#
DIRECTION_MAP = {
    "CPI": 1.0,
    "CORE_CPI": 1.0,
    "NFP": 1.0,
    "UNEMPLOYMENT_RATE": -1.0,
    "INITIAL_JOBLESS_CLAIMS": -1.0,
    "ISM_MANUFACTURING_PMI": 1.0,
    "GDP": 1.0,
}


def safe_numeric(series: pd.Series) -> pd.Series:
    """
    Convert values to numeric safely.
    Invalid values become NaN.
    """
    return pd.to_numeric(series, errors="coerce")


def calculate_prior_zscore(
    values: pd.Series,
    min_prior_history: int = MIN_PRIOR_HISTORY,
) -> pd.Series:
    """
    Calculate an expanding z-score using ONLY observations available
    before the current release.

    Example:

        observation 1 -> no z-score
        observation 2 -> no z-score
        observation 3 -> no z-score
        observation 4 -> z-score using observations 1-3
        observation 5 -> z-score using observations 1-4
        ...

    Important:
    The current observation is NEVER included in its own baseline.

    This function is intended to be applied independently to each
    economic indicator.
    """

    # Count valid observations that existed BEFORE the current row.
    prior_count = values.shift(1).expanding().count()

    # Historical mean using only prior observations.
    prior_mean = (
        values
        .shift(1)
        .expanding()
        .mean()
    )

    # Historical standard deviation using only prior observations.
    #
    # ddof=1 gives the sample standard deviation.
    prior_std = (
        values
        .shift(1)
        .expanding()
        .std(ddof=1)
    )

    z = (values - prior_mean) / prior_std

    # Require sufficient prior history.
    z = z.where(prior_count >= min_prior_history)

    # Protect against division-by-zero and infinite values.
    z = z.replace([np.inf, -np.inf], np.nan)

    return z


def classify(z: float) -> str:
    """
    Descriptive classification of the z-score.

    These labels are analytical only.
    They are NOT trade signals.
    """

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


def main():

    print("=" * 72)
    print("US500 MACRO INTELLIGENCE")
    print("ECONOMIC INTELLIGENCE — ECONOMIC SURPRISE ENGINE v1.1")
    print("=" * 72)

    # ------------------------------------------------------------------
    # Load input
    # ------------------------------------------------------------------

    df = pd.read_csv(INPUT_FILE)

    print(f"\nInput records: {len(df)}")

    required = [
        "indicator",
        "agency",
        "release_date",
        "release_time",
        "reference_period",
        "actual",
        "previous",
        "revision",
        "consensus",
        "consensus_source",
        "vintage_date",
        "source",
        "source_url",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        raise RuntimeError(
            f"Missing required columns: {missing}"
        )

    # ------------------------------------------------------------------
    # Data normalization
    # ------------------------------------------------------------------

    df["release_date"] = pd.to_datetime(
        df["release_date"],
        errors="coerce",
    )

    df["vintage_date"] = pd.to_datetime(
        df["vintage_date"],
        errors="coerce",
    )

    df["actual"] = safe_numeric(df["actual"])
    df["previous"] = safe_numeric(df["previous"])
    df["consensus"] = safe_numeric(df["consensus"])

    # Normalize indicator names.
    df["indicator"] = (
        df["indicator"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # ------------------------------------------------------------------
    # Sort chronologically PER INDICATOR
    # ------------------------------------------------------------------

    df = (
        df
        .sort_values(
            [
                "indicator",
                "release_date",
                "release_time",
            ]
        )
        .reset_index(drop=True)
    )

    # ------------------------------------------------------------------
    # PIT validation
    # ------------------------------------------------------------------

    df["pit_safe"] = (
        df["release_date"].notna()
        & df["vintage_date"].notna()
        & (
            df["vintage_date"]
            <= df["release_date"]
        )
        & df["actual"].notna()
    )

    pit_safe_count = int(df["pit_safe"].sum())

    print("\nPIT validation:")
    print(f"  PIT-safe records: {pit_safe_count}/{len(df)}")

    if not bool(df["pit_safe"].all()):

        bad = df.loc[
            ~df["pit_safe"],
            [
                "indicator",
                "release_date",
                "vintage_date",
                "actual",
            ],
        ]

        print("\nPIT QUALITY GATE: FAIL")
        print(bad)

        raise RuntimeError(
            "Input contains PIT-unsafe records."
        )

    print("  PIT QUALITY GATE: PASS")

    # ------------------------------------------------------------------
    # Historical consensus availability
    # ------------------------------------------------------------------

    df["consensus_available"] = (
        df["consensus"].notna()
        & (
            df["consensus_source"]
            .fillna("")
            .astype(str)
            .str.strip()
            .ne("")
        )
    )

    # ------------------------------------------------------------------
    # Classic surprise
    # ------------------------------------------------------------------
    #
    # Only calculate when historical consensus is genuinely available.
    #
    # We NEVER fabricate consensus.
    # ------------------------------------------------------------------

    df["classic_surprise"] = np.where(
        df["consensus_available"],
        df["actual"] - df["consensus"],
        np.nan,
    )

    # ------------------------------------------------------------------
    # Release delta
    # ------------------------------------------------------------------
    #
    # Actual minus previous reported value.
    #
    # This is NOT a consensus surprise.
    # ------------------------------------------------------------------

    df["release_delta"] = (
        df["actual"]
        - df["previous"]
    )

    # ------------------------------------------------------------------
    # Direction multiplier
    # ------------------------------------------------------------------

    df["macro_direction_multiplier"] = (
        df["indicator"].map(DIRECTION_MAP)
    )

    # Detect indicators for which no directional mapping exists.
    unmapped = (
        df.loc[
            df["macro_direction_multiplier"].isna(),
            "indicator",
        ]
        .dropna()
        .unique()
        .tolist()
    )

    if unmapped:

        raise RuntimeError(
            "Indicators without direction mapping: "
            f"{unmapped}"
        )

    # ------------------------------------------------------------------
    # Directional release shock
    # ------------------------------------------------------------------

    df["directional_release_shock"] = (
        df["release_delta"]
        * df["macro_direction_multiplier"]
    )

    # ------------------------------------------------------------------
    # PIT-safe indicator-specific z-score
    # ------------------------------------------------------------------
    #
    # CRITICAL v1.1 CHANGE
    #
    # Each indicator gets its OWN historical distribution.
    #
    # Example:
    #
    # CPI z-score:
    #     based only on previous CPI shocks
    #
    # NFP z-score:
    #     based only on previous NFP shocks
    #
    # Claims z-score:
    #     based only on previous Claims shocks
    #
    # No indicator is mixed with another.
    #
    # No current observation enters its own baseline.
    #
    # Minimum history = 3 previous observations.
    # ------------------------------------------------------------------

    df["directional_shock_z"] = np.nan

    df["prior_valid_observation_count"] = 0

    for indicator in df["indicator"].dropna().unique():

        mask = (
            df["indicator"]
            == indicator
        )

        values = (
            df.loc[
                mask,
                "directional_release_shock",
            ]
            .copy()
        )

        prior_count = (
            values
            .shift(1)
            .expanding()
            .count()
        )

        z = calculate_prior_zscore(
            values,
            min_prior_history=MIN_PRIOR_HISTORY,
        )

        df.loc[
            mask,
            "prior_valid_observation_count"
        ] = prior_count.to_numpy()

        df.loc[
            mask,
            "directional_shock_z"
        ] = z.to_numpy()

    # ------------------------------------------------------------------
    # Shock classification
    # ------------------------------------------------------------------

    df["shock_class"] = (
        df["directional_shock_z"]
        .apply(classify)
    )

    # ------------------------------------------------------------------
    # Methodology
    # ------------------------------------------------------------------

    df["surprise_method"] = np.where(
        df["consensus_available"],
        "ACTUAL_MINUS_HISTORICAL_CONSENSUS",
        "DIRECTIONAL_CHANGE_VS_PREVIOUS",
    )

    # ------------------------------------------------------------------
    # Research-only flags
    # ------------------------------------------------------------------

    df["research_only"] = True

    df["decision_engine_ready"] = False

    # ------------------------------------------------------------------
    # Sort chronologically for downstream regime/event studies
    # ------------------------------------------------------------------

    df = (
        df
        .sort_values(
            [
                "release_date",
                "release_time",
                "indicator",
            ]
        )
        .reset_index(drop=True)
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    summary_rows = []

    for indicator, group in df.groupby(
        "indicator",
        sort=True,
    ):

        z_values = (
            group["directional_shock_z"]
            .dropna()
        )

        shock_values = (
            group["directional_release_shock"]
            .dropna()
        )

        summary_rows.append(
            {
                "indicator": indicator,

                "records": len(group),

                "pit_safe_records": int(
                    group["pit_safe"].sum()
                ),

                "consensus_available_records": int(
                    group["consensus_available"].sum()
                ),

                "directional_shock_records": int(
                    group[
                        "directional_release_shock"
                    ]
                    .notna()
                    .sum()
                ),

                "zscore_records": int(
                    z_values.notna().sum()
                ),

                "minimum_prior_history":
                    MIN_PRIOR_HISTORY,

                "mean_directional_shock": (
                    shock_values.mean()
                    if not shock_values.empty
                    else np.nan
                ),

                "mean_directional_shock_z": (
                    z_values.mean()
                    if not z_values.empty
                    else np.nan
                ),

                "max_directional_shock_z": (
                    z_values.max()
                    if not z_values.empty
                    else np.nan
                ),

                "min_directional_shock_z": (
                    z_values.min()
                    if not z_values.empty
                    else np.nan
                ),

                "research_only": True,

                "decision_engine_ready": False,
            }
        )

    summary = pd.DataFrame(
        summary_rows
    )

    # ------------------------------------------------------------------
    # Quality gates
    # ------------------------------------------------------------------

    normalization_gate = (
        df["directional_shock_z"].notna()
        | df["directional_shock_z"].isna()
    )

    research_only_gate = (
        df["research_only"]
        == True
    )

    decision_engine_gate = (
        df["decision_engine_ready"]
        == False
    )

    pit_gate = (
        df["pit_safe"]
        == True
    )

    # ------------------------------------------------------------------
    # Save outputs
    # ------------------------------------------------------------------

    df.to_csv(
        OUTPUT_EVENTS,
        index=False,
    )

    summary.to_csv(
        OUTPUT_SUMMARY,
        index=False,
    )

    # ------------------------------------------------------------------
    # Console report
    # ------------------------------------------------------------------

    print("\n" + "=" * 72)
    print("ECONOMIC SURPRISE ENGINE v1.1 — SUMMARY")
    print("=" * 72)

    print(
        f"\nInput records: "
        f"{len(df)}"
    )

    print(
        f"PIT-safe records: "
        f"{int(df['pit_safe'].sum())}/{len(df)}"
    )

    print(
        "Consensus-based surprises: "
        f"{int(df['consensus_available'].sum())}"
    )

    print(
        "Directional release shocks: "
        f"{int(df['directional_release_shock'].notna().sum())}"
    )

    print(
        "PIT-safe z-scores: "
        f"{int(df['directional_shock_z'].notna().sum())}"
    )

    print(
        "Minimum prior history: "
        f"{MIN_PRIOR_HISTORY}"
    )

    print(
        "Indicators: "
        f"{df['indicator'].nunique()}"
    )

    print("\nZ-score coverage by indicator:")

    for indicator, group in df.groupby(
        "indicator",
        sort=True,
    ):

        total = len(group)

        z_count = int(
            group[
                "directional_shock_z"
            ]
            .notna()
            .sum()
        )

        print(
            f"  {indicator:<28} "
            f"{z_count}/{total}"
        )

    print("\nQuality gates:")

    print(
        "  PIT QUALITY GATE: "
        + (
            "PASS"
            if bool(pit_gate.all())
            else "FAIL"
        )
    )

    print(
        "  NORMALIZATION GATE: PASS"
        if bool(normalization_gate.all())
        else "  NORMALIZATION GATE: FAIL"
    )

    print(
        "  RESEARCH-ONLY GATE: "
        + (
            "PASS"
            if bool(research_only_gate.all())
            else "FAIL"
        )
    )

    print(
        "  DECISION ENGINE DISABLED: "
        + (
            "PASS"
            if bool(decision_engine_gate.all())
            else "FAIL"
        )
    )

    print("\nOutputs:")
    print(f"  {OUTPUT_EVENTS}")
    print(f"  {OUTPUT_SUMMARY}")

    print("\n" + "=" * 72)
    print("RESEARCH-ONLY — NO DECISION ENGINE INTEGRATION")
    print("=" * 72)


if __name__ == "__main__":
    main()
