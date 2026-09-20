from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
import pandas as pd


INPUT_RESEARCH = "financial_stress_research_v1.csv"
INPUT_RECORDS = "financial_stress_records_input_v1.csv"

OUTPUT_VALIDATION = "financial_stress_validation_v1.csv"
OUTPUT_SUMMARY = "financial_stress_validation_summary_v1.csv"
OUTPUT_EVENTS = "financial_stress_validation_events_v1.csv"

RESEARCH_REGIMES = [
    "LOW_RESEARCH_STRESS",
    "ELEVATED_RESEARCH_STRESS",
    "HIGH_RESEARCH_STRESS",
    "EXTREME_RESEARCH_STRESS",
    "INSUFFICIENT_DATA",
]

COMPONENTS = [
    "VIX_Z",
    "NFCI_Z",
    "ANFCI_Z",
    "YIELD_CURVE_STRESS_Z",
]

MIN_COMPONENTS = 2


def find_file(filename: str) -> Path:
    candidates = []

    root = Path(".").resolve()

    for base in [
        root,
        root / "input",
        root / "artifacts",
        root / "data",
    ]:
        path = base / filename
        if path.exists() and path.is_file():
            candidates.append(path)

    for path in root.rglob(filename):
        if path.is_file():
            candidates.append(path)

    unique = []
    seen = set()

    for path in candidates:
        key = str(path.resolve())

        if key not in seen:
            seen.add(key)

            try:
                if path.stat().st_size > 0:
                    unique.append(path)
            except OSError:
                pass

    if not unique:
        raise FileNotFoundError(
            f"Could not find non-empty input file: {filename}"
        )

    # Prefer root, then input/
    unique.sort(
        key=lambda p: (
            0 if p.resolve() == (root / filename).resolve() else
            1 if p.resolve() == (root / "input" / filename).resolve() else
            2,
            len(str(p)),
        )
    )

    return unique[0]


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_research_schema(df: pd.DataFrame) -> list[str]:
    required = [
        "date",
        "VIX",
        "NFCI",
        "ANFCI",
        "YIELD_CURVE",
        "VIX_Z",
        "NFCI_Z",
        "ANFCI_Z",
        "YIELD_CURVE_STRESS_Z",
        "FINANCIAL_STRESS_COMPOSITE",
        "RESEARCH_REGIME",
        "point_in_time_safe",
    ]

    return [column for column in required if column not in df.columns]


def build_regime_events(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    df = df.sort_values("date").reset_index(drop=True)

    valid = df[
        df["RESEARCH_REGIME"].isin(
            [
                "ELEVATED_RESEARCH_STRESS",
                "HIGH_RESEARCH_STRESS",
                "EXTREME_RESEARCH_STRESS",
            ]
        )
    ].copy()

    if valid.empty:
        return pd.DataFrame(
            columns=[
                "event_id",
                "start_date",
                "end_date",
                "duration_calendar_days",
                "duration_observations",
                "peak_composite",
                "peak_regime",
                "mean_composite",
                "max_VIX_Z",
                "max_NFCI_Z",
                "max_ANFCI_Z",
                "max_YIELD_CURVE_STRESS_Z",
            ]
        )

    valid["group"] = (
        valid["date"].diff().dt.days.ne(1).cumsum()
    )

    for event_number, (_, event) in enumerate(
        valid.groupby("group"), start=1
    ):
        event = event.sort_values("date")

        peak_idx = event["FINANCIAL_STRESS_COMPOSITE"].idxmax()
        peak_row = event.loc[peak_idx]

        start_date = event["date"].min()
        end_date = event["date"].max()

        rows.append(
            {
                "event_id": f"FS_EVENT_{event_number:04d}",
                "start_date": start_date,
                "end_date": end_date,
                "duration_calendar_days": (
                    end_date - start_date
                ).days + 1,
                "duration_observations": len(event),
                "peak_composite": event[
                    "FINANCIAL_STRESS_COMPOSITE"
                ].max(),
                "peak_regime": peak_row["RESEARCH_REGIME"],
                "mean_composite": event[
                    "FINANCIAL_STRESS_COMPOSITE"
                ].mean(),
                "max_VIX_Z": event["VIX_Z"].max(),
                "max_NFCI_Z": event["NFCI_Z"].max(),
                "max_ANFCI_Z": event["ANFCI_Z"].max(),
                "max_YIELD_CURVE_STRESS_Z": event[
                    "YIELD_CURVE_STRESS_Z"
                ].max(),
            }
        )

    return pd.DataFrame(rows)


def native_frequency_proxy(df: pd.DataFrame) -> pd.DataFrame:
    """
    Research-only comparison.

    The current production research method uses daily carry-forward
    observations and a 252-calendar-day rolling z-score.

    This proxy instead calculates rolling statistics on rows where
    each component actually changes. It is NOT a replacement model.
    It is only used to identify sensitivity to the frequency treatment.
    """

    result = df[["date"] + COMPONENTS].copy()

    for component in COMPONENTS:
        series = result[["date", component]].dropna().copy()

        if series.empty:
            result[f"{component}_NATIVE_Z"] = np.nan
            continue

        # Number of observations is deliberately capped at 52 to
        # approximate roughly one year of weekly observations.
        rolling_mean = series[component].rolling(
            window=52,
            min_periods=12,
        ).mean()

        rolling_std = series[component].rolling(
            window=52,
            min_periods=12,
        ).std(ddof=0)

        native_z = (
            (series[component] - rolling_mean)
            / rolling_std.replace(0, np.nan)
        )

        temp = pd.DataFrame(
            {
                "date": series["date"],
                f"{component}_NATIVE_Z": native_z,
            }
        )

        result = result.merge(temp, on="date", how="left")

    native_cols = [
        f"{component}_NATIVE_Z"
        for component in COMPONENTS
    ]

    result["NATIVE_COMPONENT_COUNT"] = result[
        native_cols
    ].notna().sum(axis=1)

    result["NATIVE_COMPOSITE"] = result[native_cols].mean(
        axis=1,
        skipna=True,
    )

    result.loc[
        result["NATIVE_COMPONENT_COUNT"] < MIN_COMPONENTS,
        "NATIVE_COMPOSITE",
    ] = np.nan

    return result[
        ["date", "NATIVE_COMPOSITE", "NATIVE_COMPONENT_COUNT"]
    ]


def threshold_sensitivity(df: pd.DataFrame) -> pd.DataFrame:
    thresholds = [0.0, 0.5, 1.0, 1.5, 2.0]

    rows = []

    composite = df["FINANCIAL_STRESS_COMPOSITE"]

    for threshold in thresholds:
        elevated = composite >= threshold

        rows.append(
            {
                "threshold": threshold,
                "observations": int(composite.notna().sum()),
                "days_at_or_above_threshold": int(
                    elevated.sum()
                ),
                "percentage_at_or_above_threshold": (
                    elevated.sum()
                    / composite.notna().sum()
                    * 100
                    if composite.notna().sum()
                    else np.nan
                ),
                "max_composite": composite.max(),
            }
        )

    return pd.DataFrame(rows)


def main() -> None:
    print("=" * 72)
    print("FINANCIAL STRESS HISTORICAL VALIDATION V1")
    print("=" * 72)

    research_path = find_file(INPUT_RESEARCH)

    print(f"Selected research input: {research_path}")
    print(f"File size: {research_path.stat().st_size} bytes")

    df = pd.read_csv(research_path)

    if df.empty:
        raise RuntimeError("Research input contains zero rows.")

    missing = validate_research_schema(df)

    if missing:
        raise RuntimeError(
            "Research input is missing required columns: "
            + ", ".join(missing)
        )

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
    )

    if df["date"].isna().any():
        raise RuntimeError("Research input contains invalid dates.")

    df = df.sort_values("date").reset_index(drop=True)

    # ------------------------------------------------------------------
    # 1. Basic integrity
    # ------------------------------------------------------------------

    duplicate_dates = int(df["date"].duplicated().sum())

    date_diffs = df["date"].diff().dt.days.dropna()

    non_monotonic = int((date_diffs < 0).sum())

    if non_monotonic:
        raise RuntimeError(
            "Dates are not monotonically increasing."
        )

    # ------------------------------------------------------------------
    # 2. PIT validation
    # ------------------------------------------------------------------

    pit_series = (
        df["point_in_time_safe"]
        .astype(str)
        .str.lower()
        .str.strip()
    )

    pit_true = pit_series.isin(["true", "1", "yes"])
    pit_false = pit_series.isin(["false", "0", "no"])

    invalid_pit = int((~(pit_true | pit_false)).sum())

    pit_unsafe = int((~pit_true).sum())

    # ------------------------------------------------------------------
    # 3. Numeric validation
    # ------------------------------------------------------------------

    numeric_columns = [
        "VIX",
        "NFCI",
        "ANFCI",
        "YIELD_CURVE",
        *COMPONENTS,
        "FINANCIAL_STRESS_COMPOSITE",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    invalid_numeric = int(
        df[numeric_columns].isna().all(axis=1).sum()
    )

    # ------------------------------------------------------------------
    # 4. Research regime distribution
    # ------------------------------------------------------------------

    regime_counts = (
        df["RESEARCH_REGIME"]
        .value_counts(dropna=False)
        .to_dict()
    )

    scored = df[
        df["FINANCIAL_STRESS_COMPOSITE"].notna()
    ].copy()

    scored_count = len(scored)

    # ------------------------------------------------------------------
    # 5. Annual statistics
    # ------------------------------------------------------------------

    df["year"] = df["date"].dt.year

    annual = (
        df.groupby("year")
        .agg(
            observations=("date", "size"),
            scored_observations=(
                "FINANCIAL_STRESS_COMPOSITE",
                "count",
            ),
            mean_composite=(
                "FINANCIAL_STRESS_COMPOSITE",
                "mean",
            ),
            median_composite=(
                "FINANCIAL_STRESS_COMPOSITE",
                "median",
            ),
            max_composite=(
                "FINANCIAL_STRESS_COMPOSITE",
                "max",
            ),
        )
        .reset_index()
    )

    # ------------------------------------------------------------------
    # 6. Component availability
    # ------------------------------------------------------------------

    component_availability = []

    for component in COMPONENTS:
        available = int(df[component].notna().sum())

        component_availability.append(
            {
                "component": component,
                "available_observations": available,
                "missing_observations": len(df) - available,
                "availability_pct": (
                    available / len(df) * 100
                ),
            }
        )

    component_availability_df = pd.DataFrame(
        component_availability
    )

    # ------------------------------------------------------------------
    # 7. Component correlations
    # ------------------------------------------------------------------

    correlation = df[
        COMPONENTS + ["FINANCIAL_STRESS_COMPOSITE"]
    ].corr()

    correlation_rows = []

    for column in correlation.columns:
        correlation_rows.append(
            {
                "variable": column,
                "correlation_with_composite": correlation.loc[
                    column,
                    "FINANCIAL_STRESS_COMPOSITE",
                ],
            }
        )

    correlation_df = pd.DataFrame(correlation_rows)

    # ------------------------------------------------------------------
    # 8. Historical stress events
    # ------------------------------------------------------------------

    events = build_regime_events(df)

    # ------------------------------------------------------------------
    # 9. Native-frequency comparison
    # ------------------------------------------------------------------

    native = native_frequency_proxy(df)

    comparison = df[
        [
            "date",
            "FINANCIAL_STRESS_COMPOSITE",
        ]
    ].merge(
        native,
        on="date",
        how="left",
    )

    comparison["COMPOSITE_DIFFERENCE"] = (
        comparison["FINANCIAL_STRESS_COMPOSITE"]
        - comparison["NATIVE_COMPOSITE"]
    )

    valid_comparison = comparison.dropna(
        subset=[
            "FINANCIAL_STRESS_COMPOSITE",
            "NATIVE_COMPOSITE",
        ]
    )

    if not valid_comparison.empty:
        native_correlation = (
            valid_comparison[
                [
                    "FINANCIAL_STRESS_COMPOSITE",
                    "NATIVE_COMPOSITE",
                ]
            ]
            .corr()
            .iloc[0, 1]
        )

        mean_absolute_difference = (
            valid_comparison[
                "COMPOSITE_DIFFERENCE"
            ]
            .abs()
            .mean()
        )
    else:
        native_correlation = np.nan
        mean_absolute_difference = np.nan

    # ------------------------------------------------------------------
    # 10. Threshold sensitivity
    # ------------------------------------------------------------------

    thresholds = threshold_sensitivity(df)

    # ------------------------------------------------------------------
    # 11. Validation checks
    # ------------------------------------------------------------------

    checks = []

    checks.append(
        {
            "check": "non_empty_input",
            "status": "PASS" if len(df) > 0 else "FAIL",
            "value": len(df),
        }
    )

    checks.append(
        {
            "check": "duplicate_dates",
            "status": "PASS" if duplicate_dates == 0 else "REVIEW",
            "value": duplicate_dates,
        }
    )

    checks.append(
        {
            "check": "monotonic_dates",
            "status": "PASS" if non_monotonic == 0 else "FAIL",
            "value": non_monotonic,
        }
    )

    checks.append(
        {
            "check": "invalid_pit_values",
            "status": "PASS" if invalid_pit == 0 else "FAIL",
            "value": invalid_pit,
        }
    )

    checks.append(
        {
            "check": "pit_unsafe_rows",
            "status": "PASS" if pit_unsafe == 0 else "FAIL",
            "value": pit_unsafe,
        }
    )

    checks.append(
        {
            "check": "scored_observations",
            "status": "PASS" if scored_count > 0 else "FAIL",
            "value": scored_count,
        }
    )

    checks.append(
        {
            "check": "component_minimum_data",
            "status": (
                "PASS"
                if all(
                    df[c].notna().sum() > 0
                    for c in COMPONENTS
                )
                else "REVIEW"
            ),
            "value": sum(
                df[c].notna().sum() > 0
                for c in COMPONENTS
            ),
        }
    )

    checks.append(
        {
            "check": "research_only",
            "status": "PASS",
            "value": "validation_only",
        }
    )

    checks_df = pd.DataFrame(checks)

    # ------------------------------------------------------------------
    # 12. Build detailed validation output
    # ------------------------------------------------------------------

    output = df.copy()

    output["validation_date_start"] = df["date"].min()
    output["validation_date_end"] = df["date"].max()

    output["PIT_VALID"] = pit_true

    output["COMPONENT_COUNT"] = df[
        COMPONENTS
    ].notna().sum(axis=1)

    output["VALIDATION_STATUS"] = np.where(
        (
            output["PIT_VALID"]
            & output["FINANCIAL_STRESS_COMPOSITE"].notna()
            & (output["COMPONENT_COUNT"] >= MIN_COMPONENTS)
        ),
        "VALID",
        "REVIEW",
    )

    output["record_id"] = output.apply(
        lambda row: sha256_text(
            "|".join(
                [
                    str(row["date"].date()),
                    str(row["FINANCIAL_STRESS_COMPOSITE"]),
                    str(row["RESEARCH_REGIME"]),
                ]
            )
        ),
        axis=1,
    )

    output.to_csv(
        OUTPUT_VALIDATION,
        index=False,
    )

    # ------------------------------------------------------------------
    # 13. Summary output
    # ------------------------------------------------------------------

    summary_rows = [
        {
            "metric": "start_date",
            "value": str(df["date"].min().date()),
        },
        {
            "metric": "end_date",
            "value": str(df["date"].max().date()),
        },
        {
            "metric": "total_rows",
            "value": len(df),
        },
        {
            "metric": "scored_rows",
            "value": scored_count,
        },
        {
            "metric": "insufficient_rows",
            "value": len(df) - scored_count,
        },
        {
            "metric": "duplicate_dates",
            "value": duplicate_dates,
        },
        {
            "metric": "pit_unsafe_rows",
            "value": pit_unsafe,
        },
        {
            "metric": "invalid_pit_values",
            "value": invalid_pit,
        },
        {
            "metric": "invalid_numeric_all_nan_rows",
            "value": invalid_numeric,
        },
        {
            "metric": "stress_event_count",
            "value": len(events),
        },
        {
            "metric": "native_frequency_comparison_rows",
            "value": len(valid_comparison),
        },
        {
            "metric": "native_frequency_composite_correlation",
            "value": native_correlation,
        },
        {
            "metric": "native_frequency_mean_absolute_difference",
            "value": mean_absolute_difference,
        },
        {
            "metric": "research_only",
            "value": True,
        },
    ]

    for regime in RESEARCH_REGIMES:
        count = int(
            (df["RESEARCH_REGIME"] == regime).sum()
        )

        percentage = (
            count / len(df) * 100
            if len(df)
            else np.nan
        )

        summary_rows.append(
            {
                "metric": f"regime_count_{regime}",
                "value": count,
            }
        )

        summary_rows.append(
            {
                "metric": f"regime_percentage_{regime}",
                "value": percentage,
            }
        )

    summary = pd.DataFrame(summary_rows)

    summary.to_csv(
        OUTPUT_SUMMARY,
        index=False,
    )

    # ------------------------------------------------------------------
    # 14. Validation events
    # ------------------------------------------------------------------

    events.to_csv(
        OUTPUT_EVENTS,
        index=False,
    )

    # ------------------------------------------------------------------
    # 15. Console report
    # ------------------------------------------------------------------

    print()
    print("-" * 72)
    print("VALIDATION SUMMARY")
    print("-" * 72)

    print(f"Date range: {df['date'].min().date()} -> {df['date'].max().date()}")
    print(f"Rows: {len(df)}")
    print(f"Scored rows: {scored_count}")
    print(f"Duplicate dates: {duplicate_dates}")
    print(f"PIT unsafe rows: {pit_unsafe}")
    print(f"Invalid PIT values: {invalid_pit}")
    print(f"Stress events: {len(events)}")

    print()
    print("Regime distribution:")

    for regime in RESEARCH_REGIMES:
        print(
            f"  {regime}: "
            f"{regime_counts.get(regime, 0)}"
        )

    print()
    print("Native-frequency comparison:")
    print(
        f"  Rows compared: {len(valid_comparison)}"
    )
    print(
        f"  Correlation: {native_correlation}"
    )
    print(
        f"  Mean absolute difference: "
        f"{mean_absolute_difference}"
    )

    print()
    print("Validation checks:")

    for _, row in checks_df.iterrows():
        print(
            f"  {row['check']}: "
            f"{row['status']} "
            f"({row['value']})"
        )

    print()
    print("Output files:")
    print(f"  {OUTPUT_VALIDATION}")
    print(f"  {OUTPUT_SUMMARY}")
    print(f"  {OUTPUT_EVENTS}")

    print()
    print("=" * 72)
    print("FINANCIAL STRESS HISTORICAL VALIDATION V1 COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    main()
