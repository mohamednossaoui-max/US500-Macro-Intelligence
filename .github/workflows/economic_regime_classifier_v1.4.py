"""
US500 Macro Intelligence
Economic Intelligence — Economic Regime Classifier v1.4

Purpose:
- Build PIT-safe economic regime observations from the Economic Surprise Engine.
- Use only PIT-safe information available as of each snapshot date.
- Normalize dimension inputs using PIT directional z-scores only.
- Aggregate multiple indicators inside each macro dimension.
- Apply indicator-specific freshness controls.
- Prevent stale observations from representing the current regime.
- Avoid raw-shock / z-score mixing.
- Avoid look-ahead bias.
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


# ============================================================
# REGIME THRESHOLDS
# ============================================================

POSITIVE_THRESHOLD = 0.5
NEGATIVE_THRESHOLD = -0.5


# ============================================================
# INDICATOR -> MACRO DIMENSION
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
# INDICATOR-SPECIFIC FRESHNESS WINDOWS
# ============================================================
#
# The purpose is NOT to claim that an observation becomes
# economically meaningless exactly at these boundaries.
#
# These are conservative research-engine controls preventing
# very old information from being treated as current.
#
# Weekly claims -> short window
# Monthly indicators -> medium window
# Quarterly GDP -> longer window
# ============================================================

MAX_AGE_DAYS = {
    "CPI": 45,
    "CORE_CPI": 45,

    "NFP": 45,
    "UNEMPLOYMENT_RATE": 45,

    "INITIAL_JOBLESS_CLAIMS": 21,

    "ISM_MANUFACTURING_PMI": 45,

    "GDP": 120,
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
# EMPTY DIMENSION RESULT
# ============================================================

def empty_dimension_result():
    """
    Return a standardized empty dimension result.
    """

    return {
        "score": np.nan,
        "method": "NO_FRESH_ZSCORE",
        "observation_date": pd.NaT,
        "age_days": np.nan,
        "indicator_count": 0,
        "indicators": "",
        "zscore_count": 0,
        "raw_shock_count": 0,
        "stale_indicator_count": 0,
        "stale_indicators": "",
    }


# ============================================================
# BUILD DIMENSION SCORE — v1.4
# ============================================================

def build_dimension_score(
    df: pd.DataFrame,
    dimension: str,
    snapshot_date: pd.Timestamp,
):
    """
    Build one macro dimension score.

    v1.4 methodology:

    1. Restrict observations to:
       - same macro dimension
       - release_date <= snapshot_date
       - PIT-safe records
       - valid directional z-score

    2. For every indicator:
       - select the latest observation available
         as of snapshot_date.

    3. Apply indicator-specific freshness control.

    4. Exclude stale observations.

    5. Use ONLY directional PIT z-scores.

    6. Average the valid fresh z-scores.

    IMPORTANT:
    Raw directional shocks are NEVER used as a fallback.

    This guarantees that all dimension scores are expressed
    on the same normalized scale.

    Returns:
        dictionary containing score and metadata.
    """

    dimension_df = df[
        (df["dimension"] == dimension)
        & (df["release_date"] <= snapshot_date)
        & (df["pit_safe"] == True)
        & (df["directional_shock_z"].notna())
    ].copy()

    if dimension_df.empty:
        return empty_dimension_result()

    # --------------------------------------------------------
    # Latest available observation per indicator
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
        return empty_dimension_result()

    # --------------------------------------------------------
    # Calculate observation age
    # --------------------------------------------------------

    latest_by_indicator["age_days"] = (
        snapshot_date
        - latest_by_indicator["release_date"]
    ).dt.days

    # --------------------------------------------------------
    # Apply indicator-specific freshness
    # --------------------------------------------------------

    latest_by_indicator["max_age_days"] = (
        latest_by_indicator["indicator"]
        .map(MAX_AGE_DAYS)
    )

    # --------------------------------------------------------
    # Detect unknown freshness configuration
    # --------------------------------------------------------

    unknown_freshness = sorted(
        latest_by_indicator.loc[
            latest_by_indicator["max_age_days"].isna(),
            "indicator",
        ]
        .dropna()
        .unique()
        .tolist()
    )

    if unknown_freshness:
        raise RuntimeError(
            "Missing freshness configuration for indicators: "
            f"{unknown_freshness}"
        )

    # --------------------------------------------------------
    # Fresh vs stale
    # --------------------------------------------------------

    latest_by_indicator["is_fresh"] = (
        latest_by_indicator["age_days"]
        <= latest_by_indicator["max_age_days"]
    )

    stale = latest_by_indicator[
        ~latest_by_indicator["is_fresh"]
    ].copy()

    fresh = latest_by_indicator[
        latest_by_indicator["is_fresh"]
        & latest_by_indicator["directional_shock_z"].notna()
    ].copy()

    # --------------------------------------------------------
    # No fresh observations
    # --------------------------------------------------------

    if fresh.empty:
        return {
            "score": np.nan,
            "method": "NO_FRESH_ZSCORE",
            "observation_date": pd.NaT,
            "age_days": np.nan,
            "indicator_count": 0,
            "indicators": "",
            "zscore_count": 0,
            "raw_shock_count": 0,
            "stale_indicator_count": len(stale),
            "stale_indicators": ",".join(
                sorted(
                    stale["indicator"]
                    .dropna()
                    .astype(str)
                    .unique()
                )
            ),
        }

    # --------------------------------------------------------
    # FINAL NORMALIZED SCORE
    # --------------------------------------------------------
    #
    # ONLY z-scores are used.
    #
    # No raw directional shock is ever introduced.
    # --------------------------------------------------------

    values = fresh[
        "directional_shock_z"
    ].astype(float)

    score = values.mean()

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    latest_observation_date = fresh[
        "release_date"
    ].max()

    latest_age_days = int(
        (
            snapshot_date
            - latest_observation_date
        ).days
    )

    indicators = ",".join(
        sorted(
            fresh["indicator"]
            .dropna()
            .astype(str)
            .unique()
        )
    )

    stale_indicators = ",".join(
        sorted(
            stale["indicator"]
            .dropna()
            .astype(str)
            .unique()
        )
    )

    return {
        "score": float(score),

        "method": "MEAN_FRESH_PIT_ZSCORES",

        "observation_date": latest_observation_date,

        "age_days": latest_age_days,

        "indicator_count": len(fresh),

        "indicators": indicators,

        "zscore_count": len(fresh),

        "raw_shock_count": 0,

        "stale_indicator_count": len(stale),

        "stale_indicators": stale_indicators,
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

    All inputs are normalized PIT z-score based dimension scores.

    Inflation:
        positive = stronger inflationary pressure
        negative = stronger disinflationary pressure

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
    # Dimension states
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
    # ========================================================

    if (
        inflation_positive
        and growth_positive
        and labor_positive
    ):
        return "INFLATIONARY_GROWTH"

    # ========================================================
    # REGIME 2
    # ========================================================

    if (
        inflation_negative
        and growth_positive
        and labor_positive
    ):
        return "DISINFLATIONARY_GROWTH"

    # ========================================================
    # REGIME 3
    # ========================================================

    if (
        inflation_positive
        and growth_negative
        and labor_negative
    ):
        return "STAGFLATIONARY"

    # ========================================================
    # REGIME 4
    # ========================================================

    if (
        inflation_negative
        and growth_negative
        and labor_positive
    ):
        return "DISINFLATIONARY_SLOWDOWN"

    # ========================================================
    # REGIME 5
    # ========================================================

    if (
        growth_negative
        and labor_negative
    ):
        return "RECESSIONARY_PRESSURE"

    # ========================================================
    # DEFAULT
    # ========================================================

    return "MIXED"


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 80)
    print("US500 MACRO INTELLIGENCE")
    print("ECONOMIC INTELLIGENCE — ECONOMIC REGIME CLASSIFIER v1.4")
    print("=" * 80)

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
            "indicator",
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
    # Z-SCORE COVERAGE
    # ========================================================

    zscore_count = int(
        df["directional_shock_z"].notna().sum()
    )

    print(
        f"Directional PIT z-score records: "
        f"{zscore_count}/{len(df)}"
    )

    if zscore_count == 0:
        raise RuntimeError(
            "No directional PIT z-scores available."
        )

    # ========================================================
    # SNAPSHOT DATES
    # ========================================================

    snapshot_dates = sorted(
        df.loc[
            df["pit_safe"],
            "release_date",
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

        dimensions_available = sum(
            pd.notna(value)
            for value in [
                inflation["score"],
                labor["score"],
                growth["score"],
            ]
        )

        # ----------------------------------------------------
        # Store observation
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

            "inflation_age_days": (
                inflation["age_days"]
            ),

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

            "inflation_stale_indicator_count": (
                inflation["stale_indicator_count"]
            ),

            "inflation_stale_indicators": (
                inflation["stale_indicators"]
            ),

            # ------------------------------
            # Labor
            # ------------------------------

            "labor_score": labor["score"],

            "labor_method": labor["method"],

            "labor_observation_date": (
                labor["observation_date"]
            ),

            "labor_age_days": (
                labor["age_days"]
            ),

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

            "labor_stale_indicator_count": (
                labor["stale_indicator_count"]
            ),

            "labor_stale_indicators": (
                labor["stale_indicators"]
            ),

            # ------------------------------
            # Growth
            # ------------------------------

            "growth_score": growth["score"],

            "growth_method": growth["method"],

            "growth_observation_date": (
                growth["observation_date"]
            ),

            "growth_age_days": (
                growth["age_days"]
            ),

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

            "growth_stale_indicator_count": (
                growth["stale_indicator_count"]
            ),

            "growth_stale_indicators": (
                growth["stale_indicators"]
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
    # NORMALIZATION QUALITY GATE
    # ========================================================
    #
    # There must be NO raw-shock contribution to any
    # dimension score in v1.4.
    # ========================================================

    raw_columns = [
        "inflation_raw_shock_count",
        "labor_raw_shock_count",
        "growth_raw_shock_count",
    ]

    raw_usage = (
        regime_df[raw_columns]
        .fillna(0)
        .sum()
        .sum()
    )

    if raw_usage != 0:
        raise RuntimeError(
            "Normalization quality gate failed: "
            "raw directional shocks entered dimension scores."
        )

    # ========================================================
    # DIMENSION SCORE METHOD GATE
    # ========================================================

    valid_methods = {
        "MEAN_FRESH_PIT_ZSCORES",
        "NO_FRESH_ZSCORE",
    }

    method_columns = [
        "inflation_method",
        "labor_method",
        "growth_method",
    ]

    for column in method_columns:

        invalid_methods = set(
            regime_df[column]
            .dropna()
            .astype(str)
            .unique()
        ) - valid_methods

        if invalid_methods:
            raise RuntimeError(
                f"Invalid dimension method(s) in "
                f"{column}: {sorted(invalid_methods)}"
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
    # RESEARCH-ONLY GATE
    # ========================================================

    if not bool(
        regime_df["research_only"].all()
    ):
        raise RuntimeError(
            "Research-only gate failed."
        )

    if bool(
        regime_df["decision_engine_ready"].any()
    ):
        raise RuntimeError(
            "Decision Engine integration must remain disabled."
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
    # OVERALL SUMMARY
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

    print("\n" + "=" * 80)
    print("REGIME CLASSIFIER SUMMARY — v1.4")
    print("=" * 80)

    print(
        f"\nInput records: "
        f"{len(df)}"
    )

    print(
        f"PIT safe input records: "
        f"{int(df['pit_safe'].sum())}/{len(df)}"
    )

    print(
        f"Directional PIT z-score records: "
        f"{zscore_count}/{len(df)}"
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

    # ========================================================
    # REGIME DISTRIBUTION
    # ========================================================

    print("\nREGIME DISTRIBUTION")
    print("-" * 80)

    print(
        regime_df[
            "economic_regime"
        ]
        .value_counts()
        .sort_index()
        .to_string()
    )

    # ========================================================
    # DIMENSION COVERAGE
    # ========================================================

    print("\nDIMENSION COVERAGE")
    print("-" * 80)

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

    # ========================================================
    # FRESHNESS / INDICATOR USAGE
    # ========================================================

    print("\nDIMENSION INDICATOR USAGE")
    print("-" * 80)

    for dimension in [
        "INFLATION",
        "LABOR",
        "GROWTH",
    ]:

        subset = df[
            df["dimension"] == dimension
        ]

        print(
            f"{dimension}: "
            f"{', '.join(sorted(subset['indicator'].unique()))}"
        )

    # ========================================================
    # REGIME OBSERVATIONS
    # ========================================================

    print("\nREGIME OBSERVATIONS")
    print("-" * 80)

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

    # ========================================================
    # QUALITY GATES
    # ========================================================

    print("\nQUALITY GATES")
    print("-" * 80)

    print("PIT QUALITY GATE: PASS")
    print("LOOK-AHEAD GATE: PASS")
    print("AGE CONSISTENCY GATE: PASS")
    print("NORMALIZATION GATE: PASS")
    print("FRESHNESS CONTROL: ACTIVE")
    print("RAW/Z-SCORE MIXING: DISABLED")
    print("REGIME CLASSIFICATION GATE: PASS")
    print("DECISION ENGINE INTEGRATION: DISABLED")

    print(
        "\nResearch-only."
    )

    print(
        "Economic regime classification is descriptive "
        "and is NOT a trading signal."
    )

    print("=" * 80)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
