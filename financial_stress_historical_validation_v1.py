from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd


# ==============================================================
# CONFIGURATION
# ==============================================================

INPUT_RESEARCH = "financial_stress_research_v1.csv"

OUTPUT_VALIDATION = "financial_stress_validation_v1.csv"
OUTPUT_SUMMARY = "financial_stress_validation_summary_v1.csv"
OUTPUT_EVENTS = "financial_stress_validation_events_v1.csv"

COMPONENTS = [
    "VIX_Z",
    "NFCI_Z",
    "ANFCI_Z",
    "YIELD_CURVE_STRESS_Z",
]

RAW_COMPONENTS = [
    "VIX",
    "NFCI",
    "ANFCI",
    "YIELD_CURVE",
]

MIN_COMPONENTS = 2

RESEARCH_REGIMES = [
    "LOW_RESEARCH_STRESS",
    "ELEVATED_RESEARCH_STRESS",
    "HIGH_RESEARCH_STRESS",
    "EXTREME_RESEARCH_STRESS",
    "INSUFFICIENT_DATA",
]


# ==============================================================
# FILE DISCOVERY
# ==============================================================

def find_file(filename: str) -> Path:
    root = Path(".").resolve()

    candidates = []

    preferred_paths = [
        root / filename,
        root / "input" / filename,
        root / "artifacts" / filename,
        root / "data" / filename,
    ]

    for path in preferred_paths:
        if path.exists() and path.is_file():
            try:
                if path.stat().st_size > 0:
                    candidates.append(path)
            except OSError:
                pass

    for path in root.rglob(filename):
        if path.is_file():
            try:
                if path.stat().st_size > 0:
                    candidates.append(path)
            except OSError:
                pass

    unique = []
    seen = set()

    for path in candidates:
        resolved = str(path.resolve())

        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)

    if not unique:
        raise FileNotFoundError(
            f"Could not find non-empty input file: {filename}"
        )

    # Prefer repository root, then input/
    def priority(path: Path) -> tuple[int, int]:
        resolved = path.resolve()

        if resolved == (root / filename).resolve():
            return (0, len(str(path)))

        if resolved == (root / "input" / filename).resolve():
            return (1, len(str(path)))

        return (2, len(str(path)))

    unique.sort(key=priority)

    return unique[0]


# ==============================================================
# HASH
# ==============================================================

def sha256_text(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


# ==============================================================
# SCHEMA
# ==============================================================

def validate_research_schema(df: pd.DataFrame) -> list[str]:

    required = [
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

    return [
        column
        for column in required
        if column not in df.columns
    ]


# ==============================================================
# NORMALIZATION
# ==============================================================

def normalize_research_schema(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.rename(
        columns={
            "asof_date": "date",
            "YIELD_10Y_2Y_SPREAD": "YIELD_CURVE",
            "composite_stress_score":
                "FINANCIAL_STRESS_COMPOSITE",
            "research_regime":
                "RESEARCH_REGIME",
        }
    )

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
    )

    df["RESEARCH_REGIME"] = (
        df["RESEARCH_REGIME"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    return df


# ==============================================================
# PIT VALIDATION
# ==============================================================

def parse_pit(value) -> bool | None:

    if pd.isna(value):
        return None

    text = str(value).strip().lower()

    if text in {
        "true",
        "1",
        "yes",
        "y",
    }:
        return True

    if text in {
        "false",
        "0",
        "no",
        "n",
    }:
        return False

    return None


# ==============================================================
# STRESS EVENTS
# ==============================================================

def build_regime_events(
    df: pd.DataFrame,
) -> pd.DataFrame:

    event_columns = [
        "ELEVATED_RESEARCH_STRESS",
        "HIGH_RESEARCH_STRESS",
        "EXTREME_RESEARCH_STRESS",
    ]

    valid = df[
        df["RESEARCH_REGIME"].isin(event_columns)
        & df["FINANCIAL_STRESS_COMPOSITE"].notna()
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

    valid = valid.sort_values("date").reset_index(
        drop=True
    )

    # IMPORTANT:
    # Do NOT require calendar-day continuity.
    #
    # The Research panel is daily trading observations.
    # Weekends/holidays naturally create >1 day gaps.
    #
    # Therefore an event continues while consecutive
    # observations remain stress observations.

    regime_values = valid[
        "RESEARCH_REGIME"
    ].tolist()

    groups = []

    current_group = 0

    for i in range(len(regime_values)):

        if i > 0:

            previous = regime_values[i - 1]
            current = regime_values[i]

            # Any consecutive stress observation remains
            # part of the same stress episode.
            #
            # LOW/INSUFFICIENT are already excluded.
            #
            # Therefore no group split is required merely
            # because the regime changes between ELEVATED,
            # HIGH and EXTREME.

        groups.append(current_group)

    valid["event_group"] = groups

    rows = []

    for event_number, (
        _,
        event,
    ) in enumerate(
        valid.groupby("event_group"),
        start=1,
    ):

        event = event.sort_values("date")

        peak_idx = event[
            "FINANCIAL_STRESS_COMPOSITE"
        ].idxmax()

        peak_row = event.loc[peak_idx]

        start_date = event["date"].min()
        end_date = event["date"].max()

        rows.append(
            {
                "event_id":
                    f"FS_EVENT_{event_number:04d}",

                "start_date":
                    start_date,

                "end_date":
                    end_date,

                "duration_calendar_days":
                    (
                        end_date - start_date
                    ).days + 1,

                "duration_observations":
                    len(event),

                "peak_composite":
                    event[
                        "FINANCIAL_STRESS_COMPOSITE"
                    ].max(),

                "peak_regime":
                    peak_row["RESEARCH_REGIME"],

                "mean_composite":
                    event[
                        "FINANCIAL_STRESS_COMPOSITE"
                    ].mean(),

                "max_VIX_Z":
                    event["VIX_Z"].max(),

                "max_NFCI_Z":
                    event["NFCI_Z"].max(),

                "max_ANFCI_Z":
                    event["ANFCI_Z"].max(),

                "max_YIELD_CURVE_STRESS_Z":
                    event[
                        "YIELD_CURVE_STRESS_Z"
                    ].max(),
            }
        )

        current_group += 1

    return pd.DataFrame(rows)


# ==============================================================
# NATIVE-FREQUENCY RESEARCH COMPARISON
# ==============================================================

def native_frequency_proxy(
    df: pd.DataFrame,
) -> pd.DataFrame:

    """
    Research-only sensitivity analysis.

    Current Research v1:
        daily panel
        +
        carry-forward of lower-frequency observations
        +
        252-calendar-day rolling z-scores.

    This validation proxy tests a different treatment:
        use the observations on their native update dates
        and calculate a rolling z-score using recent observations.

    This is NOT a replacement model.
    It is a sensitivity diagnostic only.
    """

    result = pd.DataFrame(
        {
            "date": df["date"],
        }
    )

    native_z_columns = []

    for component in COMPONENTS:

        series = (
            df[
                [
                    "date",
                    component,
                ]
            ]
            .dropna()
            .drop_duplicates(
                subset=["date"]
            )
            .sort_values("date")
            .copy()
        )

        if series.empty:

            result[
                f"{component}_NATIVE_Z"
            ] = np.nan

            native_z_columns.append(
                f"{component}_NATIVE_Z"
            )

            continue

        rolling_mean = (
            series[component]
            .rolling(
                window=52,
                min_periods=12,
            )
            .mean()
        )

        rolling_std = (
            series[component]
            .rolling(
                window=52,
                min_periods=12,
            )
            .std(
                ddof=0
            )
        )

        native_z = (
            (
                series[component]
                - rolling_mean
            )
            / rolling_std.replace(
                0,
                np.nan,
            )
        )

        native = pd.DataFrame(
            {
                "date":
                    series["date"],

                f"{component}_NATIVE_Z":
                    native_z,
            }
        )

        result = result.merge(
            native,
            on="date",
            how="left",
        )

        native_z_columns.append(
            f"{component}_NATIVE_Z"
        )

    result[
        "NATIVE_COMPONENT_COUNT"
    ] = result[
        native_z_columns
    ].notna().sum(axis=1)

    result[
        "NATIVE_COMPOSITE"
    ] = result[
        native_z_columns
    ].mean(
        axis=1,
        skipna=True,
    )

    result.loc[
        result["NATIVE_COMPONENT_COUNT"]
        < MIN_COMPONENTS,
        "NATIVE_COMPOSITE",
    ] = np.nan

    return result[
        [
            "date",
            "NATIVE_COMPOSITE",
            "NATIVE_COMPONENT_COUNT",
        ]
    ]


# ==============================================================
# THRESHOLD SENSITIVITY
# ==============================================================

def threshold_sensitivity(
    df: pd.DataFrame,
) -> pd.DataFrame:

    thresholds = [
        0.0,
        0.5,
        1.0,
        1.5,
        2.0,
    ]

    rows = []

    composite = df[
        "FINANCIAL_STRESS_COMPOSITE"
    ]

    valid = composite.dropna()

    observations = len(valid)

    for threshold in thresholds:

        at_or_above = (
            valid >= threshold
        )

        count = int(
            at_or_above.sum()
        )

        percentage = (
            count
            / observations
            * 100
            if observations > 0
            else np.nan
        )

        rows.append(
            {
                "threshold":
                    threshold,

                "observations":
                    observations,

                "days_at_or_above_threshold":
                    count,

                "percentage_at_or_above_threshold":
                    percentage,

                "max_composite":
                    valid.max(),
            }
        )

    return pd.DataFrame(rows)


# ==============================================================
# MAIN
# ==============================================================

def main() -> None:

    print("=" * 72)
    print(
        "FINANCIAL STRESS HISTORICAL VALIDATION V1"
    )
    print("=" * 72)

    # ----------------------------------------------------------
    # Locate input
    # ----------------------------------------------------------

    research_path = find_file(
        INPUT_RESEARCH
    )

    print(
        f"Selected research input: "
        f"{research_path}"
    )

    print(
        f"File size: "
        f"{research_path.stat().st_size} bytes"
    )

    # ----------------------------------------------------------
    # Load
    # ----------------------------------------------------------

    df = pd.read_csv(
        research_path
    )

    if df.empty:

        raise RuntimeError(
            "Research input contains zero rows."
        )

    print(
        f"Raw rows loaded: {len(df)}"
    )

    print(
        f"Raw columns: "
        f"{list(df.columns)}"
    )

    # ----------------------------------------------------------
    # Validate ACTUAL schema
    # ----------------------------------------------------------

    missing = validate_research_schema(
        df
    )

    if missing:

        raise RuntimeError(
            "Research input is missing required "
            "columns: "
            + ", ".join(missing)
        )

    # ----------------------------------------------------------
    # Normalize schema
    # ----------------------------------------------------------

    df = normalize_research_schema(
        df
    )

    # ----------------------------------------------------------
    # Validate dates
    # ----------------------------------------------------------

    if df["date"].isna().any():

        raise RuntimeError(
            "Research input contains invalid dates."
        )

    # ----------------------------------------------------------
    # Sort
    # ----------------------------------------------------------

    df = (
        df
        .sort_values("date")
        .reset_index(drop=True)
    )

    # ----------------------------------------------------------
    # Duplicate dates
    # ----------------------------------------------------------

    duplicate_dates = int(
        df["date"]
        .duplicated()
        .sum()
    )

    # ----------------------------------------------------------
    # Date ordering
    # ----------------------------------------------------------

    date_diffs = (
        df["date"]
        .diff()
        .dt.total_seconds()
        .div(86400)
        .dropna()
    )

    non_monotonic = int(
        (date_diffs < 0).sum()
    )

    # ----------------------------------------------------------
    # PIT
    # ----------------------------------------------------------

    df["PIT_PARSED"] = (
        df["point_in_time_safe"]
        .apply(parse_pit)
    )

    invalid_pit = int(
        df["PIT_PARSED"].isna().sum()
    )

    pit_unsafe = int(
        (
            df["PIT_PARSED"]
            == False
        ).sum()
    )

    # ----------------------------------------------------------
    # Numeric columns
    # ----------------------------------------------------------

    numeric_columns = [
        "VIX",
        "TREASURY_2Y",
        "TREASURY_10Y",
        "YIELD_CURVE",
        "NFCI",
        "ANFCI",
        *COMPONENTS,
        "stress_component_count",
        "FINANCIAL_STRESS_COMPOSITE",
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # ----------------------------------------------------------
    # Composite scoring
    # ----------------------------------------------------------

    scored = df[
        "FINANCIAL_STRESS_COMPOSITE"
    ].notna()

    scored_count = int(
        scored.sum()
    )

    insufficient_count = (
        len(df)
        - scored_count
    )

    # ----------------------------------------------------------
    # Component count consistency
    # ----------------------------------------------------------

    calculated_component_count = (
        df[COMPONENTS]
        .notna()
        .sum(axis=1)
    )

    component_count_mismatch = int(
        (
            calculated_component_count
            != df[
                "stress_component_count"
            ]
        )
        .sum()
    )

    df[
        "CALCULATED_COMPONENT_COUNT"
    ] = calculated_component_count

    # ----------------------------------------------------------
    # Regime distribution
    # ----------------------------------------------------------

    regime_counts = (
        df[
            "RESEARCH_REGIME"
        ]
        .value_counts(
            dropna=False
        )
        .to_dict()
    )

    # ----------------------------------------------------------
    # Annual statistics
    # ----------------------------------------------------------

    df["year"] = (
        df["date"]
        .dt.year
    )

    annual = (
        df.groupby("year")
        .agg(
            observations=(
                "date",
                "size",
            ),

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

    # ----------------------------------------------------------
    # Component availability
    # ----------------------------------------------------------

    component_availability_rows = []

    for component in COMPONENTS:

        available = int(
            df[component]
            .notna()
            .sum()
        )

        missing_count = (
            len(df)
            - available
        )

        component_availability_rows.append(
            {
                "component":
                    component,

                "available_observations":
                    available,

                "missing_observations":
                    missing_count,

                "availability_pct":
                    (
                        available
                        / len(df)
                        * 100
                    ),
            }
        )

    component_availability = (
        pd.DataFrame(
            component_availability_rows
        )
    )

    # ----------------------------------------------------------
    # Component correlations
    # ----------------------------------------------------------

    correlation = (
        df[
            COMPONENTS
            + [
                "FINANCIAL_STRESS_COMPOSITE"
            ]
        ]
        .corr()
    )

    correlation_rows = []

    for column in correlation.columns:

        correlation_rows.append(
            {
                "variable":
                    column,

                "correlation_with_composite":
                    correlation.loc[
                        column,
                        "FINANCIAL_STRESS_COMPOSITE",
                    ],
            }
        )

    correlation_df = (
        pd.DataFrame(
            correlation_rows
        )
    )

    # ----------------------------------------------------------
    # Stress events
    # ----------------------------------------------------------

    events = build_regime_events(
        df
    )

    # ----------------------------------------------------------
    # Native-frequency comparison
    # ----------------------------------------------------------

    native = native_frequency_proxy(
        df
    )

    comparison = (
        df[
            [
                "date",
                "FINANCIAL_STRESS_COMPOSITE",
            ]
        ]
        .merge(
            native,
            on="date",
            how="left",
        )
    )

    comparison[
        "COMPOSITE_DIFFERENCE"
    ] = (
        comparison[
            "FINANCIAL_STRESS_COMPOSITE"
        ]
        - comparison[
            "NATIVE_COMPOSITE"
        ]
    )

    valid_comparison = (
        comparison
        .dropna(
            subset=[
                "FINANCIAL_STRESS_COMPOSITE",
                "NATIVE_COMPOSITE",
            ]
        )
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

    # ----------------------------------------------------------
    # Threshold sensitivity
    # ----------------------------------------------------------

    thresholds = (
        threshold_sensitivity(
            df
        )
    )

    # ----------------------------------------------------------
    # Validation checks
    # ----------------------------------------------------------

    checks = []

    checks.append(
        {
            "check":
                "non_empty_input",

            "status":
                "PASS"
                if len(df) > 0
                else "FAIL",

            "value":
                len(df),
        }
    )

    checks.append(
        {
            "check":
                "duplicate_dates",

            "status":
                "PASS"
                if duplicate_dates == 0
                else "FAIL",

            "value":
                duplicate_dates,
        }
    )

    checks.append(
        {
            "check":
                "monotonic_dates",

            "status":
                "PASS"
                if non_monotonic == 0
                else "FAIL",

            "value":
                non_monotonic,
        }
    )

    checks.append(
        {
            "check":
                "invalid_pit_values",

            "status":
                "PASS"
                if invalid_pit == 0
                else "FAIL",

            "value":
                invalid_pit,
        }
    )

    checks.append(
        {
            "check":
                "pit_unsafe_rows",

            "status":
                "PASS"
                if pit_unsafe == 0
                else "FAIL",

            "value":
                pit_unsafe,
        }
    )

    checks.append(
        {
            "check":
                "scored_observations",

            "status":
                "PASS"
                if scored_count > 0
                else "FAIL",

            "value":
                scored_count,
        }
    )

    checks.append(
        {
            "check":
                "component_count_consistency",

            "status":
                "PASS"
                if component_count_mismatch == 0
                else "REVIEW",

            "value":
                component_count_mismatch,
        }
    )

    checks.append(
        {
            "check":
                "research_only",

            "status":
                "PASS",

            "value":
                "validation_only",
        }
    )

    checks_df = (
        pd.DataFrame(
            checks
        )
    )

    # ----------------------------------------------------------
    # Detailed validation output
    # ----------------------------------------------------------

    output = df.copy()

    output[
        "PIT_VALID"
    ] = (
        df["PIT_PARSED"]
        == True
    )

    output[
        "COMPONENT_COUNT"
    ] = calculated_component_count

    output[
        "VALIDATION_STATUS"
    ] = np.where(
        (
            output["PIT_VALID"]
            & output[
                "FINANCIAL_STRESS_COMPOSITE"
            ].notna()
            & (
                output[
                    "COMPONENT_COUNT"
                ]
                >= MIN_COMPONENTS
            )
        ),
        "VALID",
        "REVIEW",
    )

    output[
        "record_id_validation"
    ] = output.apply(
        lambda row:
            sha256_text(
                "|".join(
                    [
                        str(
                            row["date"]
                            .date()
                        ),
                        str(
                            row[
                                "FINANCIAL_STRESS_COMPOSITE"
                            ]
                        ),
                        str(
                            row[
                                "RESEARCH_REGIME"
                            ]
                        ),
                    ]
                )
            ),
        axis=1,
    )

    # ----------------------------------------------------------
    # Validation output
    # ----------------------------------------------------------

    output.to_csv(
        OUTPUT_VALIDATION,
        index=False,
    )

    # ----------------------------------------------------------
    # Summary
    # ----------------------------------------------------------

    summary_rows = [

        {
            "metric":
                "start_date",

            "value":
                str(
                    df["date"]
                    .min()
                    .date()
                ),
        },

        {
            "metric":
                "end_date",

            "value":
                str(
                    df["date"]
                    .max()
                    .date()
                ),
        },

        {
            "metric":
                "total_rows",

            "value":
                len(df),
        },

        {
            "metric":
                "scored_rows",

            "value":
                scored_count,
        },

        {
            "metric":
                "insufficient_rows",

            "value":
                insufficient_count,
        },

        {
            "metric":
                "duplicate_dates",

            "value":
                duplicate_dates,
        },

        {
            "metric":
                "pit_unsafe_rows",

            "value":
                pit_unsafe,
        },

        {
            "metric":
                "invalid_pit_values",

            "value":
                invalid_pit,
        },

        {
            "metric":
                "component_count_mismatch",

            "value":
                component_count_mismatch,
        },

        {
            "metric":
                "stress_event_count",

            "value":
                len(events),
        },

        {
            "metric":
                "native_frequency_comparison_rows",

            "value":
                len(valid_comparison),
        },

        {
            "metric":
                "native_frequency_composite_correlation",

            "value":
                native_correlation,
        },

        {
            "metric":
                "native_frequency_mean_absolute_difference",

            "value":
                mean_absolute_difference,
        },

        {
            "metric":
                "research_only",

            "value":
                True,
        },
    ]

    for regime in RESEARCH_REGIMES:

        count = int(
            (
                df[
                    "RESEARCH_REGIME"
                ]
                == regime
            ).sum()
        )

        percentage = (
            count
            / len(df)
            * 100
            if len(df)
            else np.nan
        )

        summary_rows.append(
            {
                "metric":
                    f"regime_count_{regime}",

                "value":
                    count,
            }
        )

        summary_rows.append(
            {
                "metric":
                    f"regime_percentage_{regime}",

                "value":
                    percentage,
            }
        )

    summary = (
        pd.DataFrame(
            summary_rows
        )
    )

    summary.to_csv(
        OUTPUT_SUMMARY,
        index=False,
    )

    # ----------------------------------------------------------
    # Events
    # ----------------------------------------------------------

    events.to_csv(
        OUTPUT_EVENTS,
        index=False,
    )

    # ----------------------------------------------------------
    # Console report
    # ----------------------------------------------------------

    print()
    print("-" * 72)
    print(
        "VALIDATION SUMMARY"
    )
    print("-" * 72)

    print(
        f"Date range: "
        f"{df['date'].min().date()} "
        f"-> "
        f"{df['date'].max().date()}"
    )

    print(
        f"Rows: {len(df)}"
    )

    print(
        f"Scored rows: "
        f"{scored_count}"
    )

    print(
        f"Insufficient rows: "
        f"{insufficient_count}"
    )

    print(
        f"Duplicate dates: "
        f"{duplicate_dates}"
    )

    print(
        f"PIT unsafe rows: "
        f"{pit_unsafe}"
    )

    print(
        f"Invalid PIT values: "
        f"{invalid_pit}"
    )

    print(
        f"Component count mismatches: "
        f"{component_count_mismatch}"
    )

    print(
        f"Stress events: "
        f"{len(events)}"
    )

    print()
    print(
        "Regime distribution:"
    )

    for regime in RESEARCH_REGIMES:

        print(
            f"  {regime}: "
            f"{regime_counts.get(regime, 0)}"
        )

    print()
    print(
        "Native-frequency comparison:"
    )

    print(
        f"  Rows compared: "
        f"{len(valid_comparison)}"
    )

    print(
        f"  Correlation: "
        f"{native_correlation}"
    )

    print(
        f"  Mean absolute difference: "
        f"{mean_absolute_difference}"
    )

    print()
    print(
        "Validation checks:"
    )

    for _, row in checks_df.iterrows():

        print(
            f"  {row['check']}: "
            f"{row['status']} "
            f"({row['value']})"
        )

    print()
    print(
        "Annual statistics:"
    )

    print(
        annual.to_string(
            index=False
        )
    )

    print()
    print(
        "Component availability:"
    )

    print(
        component_availability.to_string(
            index=False
        )
    )

    print()
    print(
        "Component correlations:"
    )

    print(
        correlation_df.to_string(
            index=False
        )
    )

    print()
    print(
        "Threshold sensitivity:"
    )

    print(
        thresholds.to_string(
            index=False
        )
    )

    print()
    print(
        "Output files:"
    )

    print(
        f"  {OUTPUT_VALIDATION}"
    )

    print(
        f"  {OUTPUT_SUMMARY}"
    )

    print(
        f"  {OUTPUT_EVENTS}"
    )

    print()
    print("=" * 72)
    print(
        "FINANCIAL STRESS HISTORICAL "
        "VALIDATION V1 COMPLETE"
    )
    print("=" * 72)


if __name__ == "__main__":
    main()
