"""
US500 Macro Intelligence
Financial Stress Intelligence — Research Analyzer v1

Research-only.
No Decision Engine integration.
No trade signals.
No execution.

Input:
- financial_stress_records_input_v1.csv

Method:
- Point-in-time as-of reconstruction using availability_date.
- VIX: higher values contribute positively to stress.
- NFCI/ANFCI: higher values contribute positively to stress.
- 10Y-2Y spread: lower values contribute positively to stress.
- Rolling 252-calendar-day z-scores are used for the research composite.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd


INPUT = "financial_stress_records_input_v1.csv"
OUTPUT = "financial_stress_research_v1.csv"
SUMMARY_OUTPUT = "financial_stress_research_summary_v1.csv"

REQUIRED_COLUMNS = {
    "indicator",
    "observation_date",
    "availability_date",
    "actual",
    "unit",
    "frequency",
    "source",
    "source_url",
    "vintage",
    "revision_flag",
    "point_in_time_safe",
    "availability_semantics",
}

INDICATORS = [
    "VIX",
    "TREASURY_2Y",
    "TREASURY_10Y",
    "NFCI",
    "ANFCI",
]

ROLLING_WINDOW = 252
MIN_PERIODS = 60


def zscore(series: pd.Series) -> pd.Series:

    mean = series.rolling(
        ROLLING_WINDOW,
        min_periods=MIN_PERIODS,
    ).mean()

    std = series.rolling(
        ROLLING_WINDOW,
        min_periods=MIN_PERIODS,
    ).std(ddof=0)

    return (
        series - mean
    ) / std.replace(0, np.nan)


def asof_series(
    source: pd.DataFrame,
    dates: pd.DatetimeIndex,
    indicator: str,
) -> pd.Series:

    sub = source[
        source["indicator"] == indicator
    ].copy()

    if sub.empty:
        raise RuntimeError(
            f"Missing required indicator: {indicator}"
        )

    sub = sub.sort_values(
        [
            "availability_date",
            "observation_date",
        ]
    )

    right = sub[
        [
            "availability_date",
            "observation_date",
            "actual",
        ]
    ].copy()

    result = pd.merge_asof(
        pd.DataFrame({
            "asof_date": dates
        }),
        right.sort_values(
            "availability_date"
        ),
        left_on="asof_date",
        right_on="availability_date",
        direction="backward",
        allow_exact_matches=True,
    )

    # Anti-lookahead gate.
    result.loc[
        result["observation_date"]
        > result["asof_date"],
        "actual",
    ] = np.nan

    return pd.Series(
        result["actual"].to_numpy(
            dtype=float
        ),
        index=dates,
        name=indicator,
    )


def record_id(
    row: pd.Series
) -> str:

    key = "|".join(
        [
            str(row["asof_date"]),
            str(row["VIX"]),
            str(row["TREASURY_2Y"]),
            str(row["TREASURY_10Y"]),
            str(row["NFCI"]),
            str(row["ANFCI"]),
        ]
    )

    return hashlib.sha256(
        key.encode()
    ).hexdigest()


def classify(score):

    if pd.isna(score):
        return "INSUFFICIENT_DATA"

    if score >= 2.0:
        return "EXTREME_RESEARCH_STRESS"

    if score >= 1.0:
        return "HIGH_RESEARCH_STRESS"

    if score >= 0.0:
        return "ELEVATED_RESEARCH_STRESS"

    return "LOW_RESEARCH_STRESS"


def main():

    print("=" * 60)
    print(
        "US500 Macro Intelligence"
    )
    print(
        "Financial Stress Intelligence — Research Analyzer v1"
    )
    print(
        "Research-only — No Decision Engine"
    )
    print("=" * 60)

    df = pd.read_csv(INPUT)

    missing = (
        REQUIRED_COLUMNS
        - set(df.columns)
    )

    if missing:
        raise AssertionError(
            f"Missing required input columns: "
            f"{sorted(missing)}"
        )

    if df.empty:
        raise RuntimeError(
            "Input CSV contains zero rows."
        )

    df["observation_date"] = pd.to_datetime(
        df["observation_date"],
        errors="coerce",
    )

    df["availability_date"] = pd.to_datetime(
        df["availability_date"],
        errors="coerce",
    )

    df["actual"] = pd.to_numeric(
        df["actual"],
        errors="coerce",
    )

    if df[
        [
            "observation_date",
            "availability_date",
            "actual",
        ]
    ].isna().any().any():

        raise AssertionError(
            "Input contains invalid dates "
            "or actual values."
        )

    if not df[
        "point_in_time_safe"
    ].astype(bool).all():

        raise AssertionError(
            "Input contains non-PIT-safe records."
        )

    if (
        df["availability_date"]
        < df["observation_date"]
    ).any():

        raise AssertionError(
            "Input contains availability dates "
            "earlier than observation dates."
        )

    actual_indicators = set(
        df["indicator"].unique()
    )

    missing_indicators = (
        set(INDICATORS)
        - actual_indicators
    )

    if missing_indicators:

        raise AssertionError(
            "Missing indicators: "
            f"{sorted(missing_indicators)}"
        )

    start = (
        df["availability_date"]
        .min()
        .normalize()
    )

    end = (
        df["availability_date"]
        .max()
        .normalize()
    )

    dates = pd.date_range(
        start=start,
        end=end,
        freq="D",
    )

    panel = pd.DataFrame(
        index=dates
    )

    for indicator in INDICATORS:

        panel[indicator] = asof_series(
            df,
            dates,
            indicator,
        )

    panel.index.name = "asof_date"

    # ======================================================
    # Yield curve
    # ======================================================

    panel[
        "YIELD_10Y_2Y_SPREAD"
    ] = (
        panel["TREASURY_10Y"]
        - panel["TREASURY_2Y"]
    )

    # ======================================================
    # Stress-oriented Z-scores
    # ======================================================

    panel["VIX_Z"] = zscore(
        panel["VIX"]
    )

    panel["NFCI_Z"] = zscore(
        panel["NFCI"]
    )

    panel["ANFCI_Z"] = zscore(
        panel["ANFCI"]
    )

    spread_z = zscore(
        panel[
            "YIELD_10Y_2Y_SPREAD"
        ]
    )

    # Lower yield spread = more stress.
    panel[
        "YIELD_CURVE_STRESS_Z"
    ] = -spread_z

    components = [
        "VIX_Z",
        "NFCI_Z",
        "ANFCI_Z",
        "YIELD_CURVE_STRESS_Z",
    ]

    panel[
        "stress_component_count"
    ] = (
        panel[components]
        .notna()
        .sum(axis=1)
    )

    panel[
        "composite_stress_score"
    ] = (
        panel[components]
        .mean(axis=1)
    )

    # At least two components are
    # required for a composite score.
    panel.loc[
        panel[
            "stress_component_count"
        ] < 2,
        "composite_stress_score",
    ] = np.nan

    panel[
        "research_regime"
    ] = (
        panel[
            "composite_stress_score"
        ]
        .apply(classify)
    )

    panel[
        "point_in_time_safe"
    ] = True

    out = panel.reset_index()

    out["record_id"] = out.apply(
        record_id,
        axis=1,
    )

    columns = [
        "asof_date",
        "VIX",
        "TREASURY_2Y",
        "TREASURY_10Y",
        "YIELD_10Y_2Y_SPREAD",
        "NFCI",
        "ANFCI",
        "VIX_Z",
        "NFCI_Z",
        "ANFCI_Z",
        "YIELD_CURVE_STRESS_Z",
        "stress_component_count",
        "composite_stress_score",
        "research_regime",
        "point_in_time_safe",
        "record_id",
    ]

    out = out[columns]

    if out.empty:
        raise RuntimeError(
            "Research analyzer produced zero rows."
        )

    if not out[
        "point_in_time_safe"
    ].all():

        raise AssertionError(
            "Research output contains "
            "a non-PIT-safe row."
        )

    out.to_csv(
        OUTPUT,
        index=False,
    )

    # ======================================================
    # Annual summary
    # ======================================================

    summary_base = out.copy()

    summary_base["year"] = (
        summary_base[
            "asof_date"
        ].dt.year
    )

    summary = (
        summary_base
        .groupby(
            "year",
            as_index=False
        )
        .agg(
            days=(
                "asof_date",
                "count",
            ),

            scored_days=(
                "composite_stress_score",
                lambda x:
                    int(x.notna().sum()),
            ),

            average_composite_stress=(
                "composite_stress_score",
                "mean",
            ),

            max_composite_stress=(
                "composite_stress_score",
                "max",
            ),

            high_or_extreme_days=(
                "research_regime",
                lambda x:
                    int(
                        x.isin(
                            [
                                "HIGH_RESEARCH_STRESS",
                                "EXTREME_RESEARCH_STRESS",
                            ]
                        ).sum()
                    ),
            ),
        )
    )

    summary.to_csv(
        SUMMARY_OUTPUT,
        index=False,
    )

    print("=" * 60)
    print(
        "RESEARCH ANALYSIS COMPLETE"
    )
    print("=" * 60)

    print(
        f"Input rows: {len(df)}"
    )

    print(
        f"Output rows: {len(out)}"
    )

    print(
        f"Research output: {OUTPUT}"
    )

    print(
        f"Summary output: {SUMMARY_OUTPUT}"
    )

    print(
        "Scored rows:",
        int(
            out[
                "composite_stress_score"
            ].notna().sum()
        ),
    )

    print(
        "PIT:",
        int(
            out[
                "point_in_time_safe"
            ].sum()
        ),
        "/",
        len(out),
    )

    print(
        "Research-only guard: PASS"
    )

    print(
        "Decision Engine integration: NONE"
    )

    print("=" * 60)


if __name__ == "__main__":
    main()
