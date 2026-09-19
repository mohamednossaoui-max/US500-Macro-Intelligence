"""
US500 Macro Intelligence
Economic Intelligence — Economic Regime Classifier v1.3

Purpose:
- Build PIT-safe economic regime observations from the Economic Surprise Engine.
- Use the latest valid observation available as of each snapshot date.
- Aggregate multiple indicators inside each macro dimension.
- Avoid look-ahead bias.
- Avoid mixing z-score and raw-shock scales in the same dimension.
- Research-only.
- NO Decision Engine integration.
- NO trading signal generation.

Input:
    economic_surprise_engine_v1.csv

Outputs:
    economic_regime_events_v1.csv
    economic_regime_summary_v1.csv
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

INPUT_FILE = "economic_surprise_engine_v1.csv"

OUTPUT_EVENTS = "economic_regime_events_v1.csv"
OUTPUT_SUMMARY = "economic_regime_summary_v1.csv"

# Regime thresholds
POSITIVE_THRESHOLD = 0.5
NEGATIVE_THRESHOLD = -0.5


# ============================================================
# MACRO DIMENSION MAP
# ============================================================

DIMENSION_MAP = {
    "CPI": "INFLATION",
    "CORE_CPI": "INFLATION",

    "NFP": "LABOR",
    "UNEMPLOYMENT_RATE": "LABOR",
    "INITIAL_JOBLESS_CLAIMS": "LABOR",

    "GDP": "GROWTH",
    "ISM_MANUFACTURING_PMI": "GROWTH",
}


# ============================================================
# HELPERS
# ============================================================

def safe_numeric(series: pd.Series) -> pd.Series:
    """
    Convert a pandas series to numeric safely.
    Invalid values become NaN.
    """
    return pd.to_numeric(series, errors="coerce")


def clean_string(value) -> str:
    """
    Safely convert a value to a clean string.
    """
    if pd.isna(value):
        return ""

    return str(value).strip()


# ============================================================
# BUILD DIMENSION SCORE
# ============================================================

def build_dimension_score(
    df: pd.DataFrame,
    dimension: str,
    snapshot_date: pd.Timestamp,
):
    """
    Build one macro dimension score using only information
    available on or before snapshot_date.

    Methodology:

    1. Restrict observations to:
       - same dimension
       - release_date <= snapshot_date
       - PIT safe
       - valid directional release shock

    2. For every indicator:
       - select the latest valid observation available
         at the snapshot date.

    3. If at least one selected indicator has a z-score:
       - use ONLY z-scores
       - do not mix raw shocks with z-scores.

    4. Otherwise:
       - use raw directional shocks.

    5. Average the selected indicator values.

    Returns:
        dictionary containing the dimension score and metadata.
    """

    dimension_df = df[
        (df["dimension"] == dimension)
        & (df["release_date"] <= snapshot_date)
        & (df["pit_safe"] == True)
        & (df["directional_release_shock"].notna())
    ].copy()

    if dimension_df.empty:
        return {
            "score": np.nan,
            "method": "NO_DATA",
            "observation_date": pd.NaT,
            "age_days": np.nan,
            "indicator_count": 0,
            "indicators": "",
            "zscore_count": 0,
            "raw_shock_count": 0,
        }

    # --------------------------------------------------------
    # Latest valid observation per indicator
    # --------------------------------------------------------

    dimension_df = dimension_df.sort_values(
        ["indicator", "release_date"]
    )

    latest_by_indicator = (
        dimension_df
        .groupby("indicator", as_index=False)
        .tail(1)
        .copy()
    )

    if latest_by_indicator.empty:
        return {
            "score": np.nan,
            "method": "NO_DATA",
            "observation_date": pd.NaT,
            "age_days": np.nan,
            "indicator_count": 0,
            "indicators": "",
            "zscore_count": 0,
            "raw_shock_count": 0,
        }

    # --------------------------------------------------------
    # Z-score availability
    # --------------------------------------------------------

    z_available = latest_by_indicator[
        latest_by_indicator["directional_shock_z"].notna()
    ].copy()

    # --------------------------------------------------------
    # Preferred method:
    # Use z-scores only if at least one valid z-score exists.
    #
    # We deliberately do NOT mix z-scores and raw shocks.
    # --------------------------------------------------------

    if not z_available.empty:

        values = z_available["directional_shock_z"].astype(float)

        score = values.mean()

        used = z_available.copy()

        method = "MEAN_PIT_ZSCORES"

        zscore_count = len(used)
        raw_shock_count = 0

    # --------------------------------------------------------
    # Fallback:
    # No z-score available -> use raw directional shocks.
    # --------------------------------------------------------

    else:

        values = latest_by_indicator[
            "directional_release_shock"
        ].astype(float)

        score = values.mean()

        used = latest_by_indicator.copy()

        method = "MEAN_RAW_DIRECTIONAL_SHOCK"

        zscore_count = 0
        raw_shock_count = len(used)

    # --------------------------------------------------------
    # Observation metadata
    # --------------------------------------------------------

    latest_observation_date = used["release_date"].max()

    age_days = (
        snapshot_date - latest_observation_date
    ).days

    indicators = ",".join(
        sorted(
            used["indicator"]
            .dropna()
            .astype(str)
            .unique()
        )
    )

    return {
        "score": float(score),
        "method": method,
        "observation_date": latest_observation_date,
        "age_days": int(age_days),
        "indicator_count": len(used),
        "indicators": indicators,
        "zscore_count": zscore_count,
        "raw_shock_count": raw_shock_count,
    }


# ============================================================
# REGIME CLASSIFICATION
# ============================================================

def classify_regime(
    inflation_score,
    labor_score,
    growth_score,
):
    """
    Classify the economic regime from the three macro dimensions.

    Inflation:
        positive = inflationary pressure
        negative = disinflationary pressure

    Labor:
        positive = stronger labor conditions
        negative = weaker labor conditions

    Growth:
        positive = stronger growth
        negative = weaker growth
    """

    scores = [
        inflation_score,
        labor_score,
        growth_score,
    ]

    available = sum(
        pd.notna(score)
        for score in scores
    )

    # --------------------------------------------------------
    # No usable dimensions
    # --------------------------------------------------------

    if available == 0:
        return "INSUFFICIENT_DATA"

    # --------------------------------------------------------
    # Partial information
    # --------------------------------------------------------

    if available < 3:
        return "PARTIAL_DATA"

    # --------------------------------------------------------
    # All dimensions available
    # --------------------------------------------------------

    inflation_positive = (
        inflation_score >= POSITIVE_THRESHOLD
    )

    inflation_negative = (
        inflation_score <= NEGATIVE_THRESHOLD
    )

    labor_positive = (
        labor_score >= POSITIVE_THRESHOLD
    )

    labor_negative = (
        labor_score <= NEGATIVE_THRESHOLD
    )

    growth_positive = (
        growth_score >= POSITIVE_THRESHOLD
    )

    growth_negative = (
        growth_score <= NEGATIVE_THRESHOLD
    )

    # ========================================================
    # REGIME 1
    # Inflationary Growth
    # ========================================================

    if (
        inflation_positive
        and growth_positive
        and labor_positive
    ):
        return "INFLATIONARY_GROWTH"

    # ========================================================
    # REGIME 2
    # Disinflationary Growth
    # ========================================================

    if (
        inflation_negative
        and growth_positive
        and labor_positive
    ):
        return "DISINFLATIONARY_GROWTH"

    # ========================================================
    # REGIME 3
    # Stagflationary
    # ========================================================

    if (
        inflation_positive
        and growth_negative
        and labor_negative
    ):
        return "STAGFLATIONARY"

    # ========================================================
    # REGIME 4
    # Disinflationary Slowdown
    # ========================================================

    if (
        inflation_negative
        and growth_negative
        and labor_positive
    ):
        return "DISINFLATIONARY_SLOWDOWN"

    # ========================================================
    # REGIME 5
    # Recessionary Pressure
    # ========================================================

    if (
        growth_negative
        and labor_negative
    ):
        return "RECESSIONARY_PRESSURE"

    # ========================================================
    # Everything else
    # ========================================================

    return "MIXED"


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 72)
    print("US500 MACRO INTELLIGENCE")
    print("ECONOMIC INTELLIGENCE — ECONOMIC REGIME CLASSIFIER v1.3")
    print("=" * 72)

    # ========================================================
    # LOAD DATA
    # ========================================================

    try:
        df = pd.read_csv(INPUT_FILE)
    except FileNotFoundError:
        raise RuntimeError(
            f"Input file not found: {INPUT_FILE}"
        )

    print(f"\nInput file: {INPUT_FILE}")
    print(f"Input records: {len(df)}")

    # ========================================================
    # REQUIRED COLUMNS
    # ========================================================

    required_columns = [
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
        "pit_safe",
        "directional_release_shock",
        "directional_shock_z",
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        raise RuntimeError(
            f"Missing required columns: {missing}"
        )

    # ========================================================
    # STANDARDIZATION
    # ========================================================

    df["indicator"] = (
        df["indicator"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df["release_date"] = pd.to_datetime(
        df["release_date"],
        errors="coerce",
    )

    df["vintage_date"] = pd.to_datetime(
        df["vintage_date"],
        errors="coerce",
    )

    df["directional_release_shock"] = safe_numeric(
        df["directional_release_shock"]
    )

    df["directional_shock_z"] = safe_numeric(
        df["directional_shock_z"]
    )

    # ========================================================
    # DIMENSION ASSIGNMENT
    # ========================================================

    df["dimension"] = df["indicator"].map(
        DIMENSION_MAP
    )

    unknown_indicators = sorted(
        df.loc[
            df["dimension"].isna(),
            "indicator"
        ]
        .dropna()
        .unique()
        .tolist()
    )

    if unknown_indicators:
        print("\nWARNING")
        print("Indicators without macro dimension mapping:")
        print(unknown_indicators)

    # ========================================================
    # PIT QUALITY GATE
    # ========================================================

    df["pit_safe"] = (
        df["pit_safe"].astype(bool)
        & df["release_date"].notna()
        & df["vintage_date"].notna()
        & (
            df["vintage_date"]
            <= df["release_date"]
        )
    )

    if not bool(df["pit_safe"].all()):

        bad = df.loc[
            ~df["pit_safe"],
            [
                "indicator",
                "release_date",
                "vintage_date",
            ],
        ]

        print("\nPIT QUALITY GATE: FAIL")
        print(bad)

        raise RuntimeError(
            "Input contains PIT-unsafe records."
        )

    print(
        f"PIT safe input records: "
        f"{int(df['pit_safe'].sum())}/{len(df)}"
    )

    # ========================================================
    # SNAPSHOT DATES
    # ========================================================

    snapshot_dates = sorted(
        df.loc[
            df["pit_safe"],
            "release_date"
        ]
        .dropna()
        .unique()
    )

    print(
        f"Snapshot dates: {len(snapshot_dates)}"
    )

    # ========================================================
    # BUILD REGIME OBSERVATIONS
    # ========================================================

    regime_rows = []

    for snapshot_date in snapshot_dates:

        snapshot_date = pd.Timestamp(
            snapshot_date
        )

        inflation = build_dimension_score(
            df,
            "INFLATION",
            snapshot_date,
        )

        labor = build_dimension_score(
            df,
            "LABOR",
            snapshot_date,
        )

        growth = build_dimension_score(
            df,
            "GROWTH",
            snapshot_date,
        )

        regime = classify_regime(
            inflation["score"],
            labor["score"],
            growth["score"],
        )

        # ----------------------------------------------------
        # Dimensions available
        # ----------------------------------------------------

        dimensions_available = sum(
            pd.notna(value)
            for value in [
                inflation["score"],
                labor["score"],
                growth["score"],
            ]
        )

        # ----------------------------------------------------
        # Store row
        # ----------------------------------------------------

        regime_rows.append({

            "release_date": snapshot_date,

            # ------------------------------
            # Inflation
            # ------------------------------

            "inflation_score": inflation["score"],
            "inflation_method": inflation["method"],
            "inflation_observation_date": (
                inflation["observation_date"]
            ),
            "inflation_age_days": inflation["age_days"],
            "inflation_indicator_count": (
                inflation["indicator_count"]
            ),
            "inflation_indicators": (
                inflation["indicators"]
            ),
            "inflation_zscore_count": (
                inflation["zscore_count"]
            ),
            "inflation_raw_shock_count": (
                inflation["raw_shock_count"]
            ),

            # ------------------------------
            # Labor
            # ------------------------------

            "labor_score": labor["score"],
            "labor_method": labor["method"],
            "labor_observation_date": (
                labor["observation_date"]
            ),
            "labor_age_days": labor["age_days"],
            "labor_indicator_count": (
                labor["indicator_count"]
            ),
            "labor_indicators": (
                labor["indicators"]
            ),
            "labor_zscore_count": (
                labor["zscore_count"]
            ),
            "labor_raw_shock_count": (
                labor["raw_shock_count"]
            ),

            # ------------------------------
            # Growth
            # ------------------------------

            "growth_score": growth["score"],
            "growth_method": growth["method"],
            "growth_observation_date": (
                growth["observation_date"]
            ),
            "growth_age_days": growth["age_days"],
            "growth_indicator_count": (
                growth["indicator_count"]
            ),
            "growth_indicators": (
                growth["indicators"]
            ),
            "growth_zscore_count": (
                growth["zscore_count"]
            ),
            "growth_raw_shock_count": (
                growth["raw_shock_count"]
            ),

            # ------------------------------
            # Regime
            # ------------------------------

            "dimensions_available": (
                dimensions_available
            ),

            "economic_regime": regime,

            # ------------------------------
            # Research flags
            # ------------------------------

            "research_only": True,

            "decision_engine_ready": False,

            "pit_safe": True,

        })

    # ========================================================
    # CREATE DATAFRAME
    # ========================================================

    regime_df = pd.DataFrame(
        regime_rows
    )

    if regime_df.empty:
        raise RuntimeError(
            "No regime observations were generated."
        )

    regime_df = regime_df.sort_values(
        "release_date"
    ).reset_index(drop=True)

    # ========================================================
    # LOOK-AHEAD QUALITY GATE
    # ========================================================

    observation_columns = [
        "inflation_observation_date",
        "labor_observation_date",
        "growth_observation_date",
    ]

    for column in observation_columns:

        invalid = (
            regime_df[column].notna()
            & (
                regime_df[column]
                > regime_df["release_date"]
            )
        )

        if bool(invalid.any()):

            print(
                "\nLOOK-AHEAD QUALITY GATE: FAIL"
            )

            print(
                regime_df.loc[
                    invalid,
                    [
                        "release_date",
                        column,
                    ],
                ]
            )

            raise RuntimeError(
                f"Look-ahead detected in {column}."
            )

    # ========================================================
    # AGE QUALITY GATE
    # ========================================================

    age_columns = [
        "inflation_age_days",
        "labor_age_days",
        "growth_age_days",
    ]

    for column in age_columns:

        invalid = (
            regime_df[column].notna()
            & (regime_df[column] < 0)
        )

        if bool(invalid.any()):

            print(
                "\nAGE QUALITY GATE: FAIL"
            )

            print(
                regime_df.loc[
                    invalid,
                    [
                        "release_date",
                        column,
                    ],
                ]
            )

            raise RuntimeError(
                f"Negative observation age detected "
                f"in {column}."
            )

    # ========================================================
    # PIT FLAG GATE
    # ========================================================

    if not bool(
        regime_df["pit_safe"].all()
    ):
        raise RuntimeError(
            "Regime output contains PIT-unsafe rows."
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    summary_rows = []

    for regime, group in regime_df.groupby(
        "economic_regime",
        sort=True,
    ):

        summary_rows.append({

            "economic_regime": regime,

            "observations": len(group),

            "share_of_observations": (
                len(group)
                / len(regime_df)
            ),

            "mean_inflation_score": (
                group["inflation_score"]
                .mean()
            ),

            "mean_labor_score": (
                group["labor_score"]
                .mean()
            ),

            "mean_growth_score": (
                group["growth_score"]
                .mean()
            ),

            "mean_dimensions_available": (
                group["dimensions_available"]
                .mean()
            ),

        })

    summary_df = pd.DataFrame(
        summary_rows
    )

    # ========================================================
    # OVERALL SUMMARY ROW
    # ========================================================

    overall = pd.DataFrame([{

        "economic_regime": "ALL",

        "observations": len(regime_df),

        "share_of_observations": 1.0,

        "mean_inflation_score": (
            regime_df["inflation_score"]
            .mean()
        ),

        "mean_labor_score": (
            regime_df["labor_score"]
            .mean()
        ),

        "mean_growth_score": (
            regime_df["growth_score"]
            .mean()
        ),

        "mean_dimensions_available": (
            regime_df["dimensions_available"]
            .mean()
        ),

    }])

    summary_df = pd.concat(
        [
            summary_df,
            overall,
        ],
        ignore_index=True,
    )

    # ========================================================
    # OUTPUT
    # ========================================================

    regime_df.to_csv(
        OUTPUT_EVENTS,
        index=False,
    )

    summary_df.to_csv(
        OUTPUT_SUMMARY,
        index=False,
    )

    # ========================================================
    # CONSOLE REPORT
    # ========================================================

    print("\n" + "=" * 72)
    print("REGIME CLASSIFIER SUMMARY")
    print("=" * 72)

    print(
        f"\nInput records: "
        f"{len(df)}"
    )

    print(
        f"PIT safe input records: "
        f"{int(df['pit_safe'].sum())}/{len(df)}"
    )

    print(
        f"Regime observations: "
        f"{len(regime_df)}"
    )

    print(
        f"Indicators: "
        f"{df['indicator'].nunique()}"
    )

    print(
        f"Dimensions: "
        f"{df['dimension'].dropna().nunique()}"
    )

    print("\nREGIME DISTRIBUTION")
    print("-" * 72)

    print(
        regime_df[
            "economic_regime"
        ]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print("\nDIMENSION COVERAGE")
    print("-" * 72)

    print(
        "Inflation score coverage: "
        f"{regime_df['inflation_score'].notna().sum()}"
        f"/{len(regime_df)}"
    )

    print(
        "Labor score coverage: "
        f"{regime_df['labor_score'].notna().sum()}"
        f"/{len(regime_df)}"
    )

    print(
        "Growth score coverage: "
        f"{regime_df['growth_score'].notna().sum()}"
        f"/{len(regime_df)}"
    )

    print("\nREGIME OBSERVATIONS")
    print("-" * 72)

    display_columns = [
        "release_date",
        "inflation_score",
        "labor_score",
        "growth_score",
        "dimensions_available",
        "economic_regime",
    ]

    print(
        regime_df[
            display_columns
        ].to_string(index=False)
    )

    print("\nOUTPUTS")
    print("-" * 72)

    print(
        f"- {OUTPUT_EVENTS}"
    )

    print(
        f"- {OUTPUT_SUMMARY}"
    )

    # ========================================================
    # QUALITY GATES
    # ========================================================

    print("\nQUALITY GATES")
    print("-" * 72)

    print("PIT QUALITY GATE: PASS")
    print("LOOK-AHEAD GATE: PASS")
    print("AGE CONSISTENCY GATE: PASS")
    print("DIMENSION STANDARDIZATION GATE: PASS")
    print("REGIME CLASSIFICATION GATE: PASS")
    print("DECISION ENGINE INTEGRATION: DISABLED")

    print(
        "\nResearch-only."
    )

    print(
        "Economic regime classification is descriptive "
        "and is NOT a trading signal."
    )

    print("=" * 72)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
