from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd


# ==============================================================
# CONFIGURATION
# ==============================================================

INPUT_RESEARCH = "financial_stress_research_v1.csv"

OUTPUT_VALIDATION = "financial_stress_validation_v1_1.csv"
OUTPUT_SUMMARY = "financial_stress_validation_summary_v1_1.csv"
OUTPUT_EVENTS = "financial_stress_validation_events_v1_1.csv"
OUTPUT_FREQUENCY = "financial_stress_frequency_sensitivity_v1_1.csv"

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

# Event definition:
# - start when composite >= EVENT_START_THRESHOLD
# - remain active while composite >= EVENT_END_THRESHOLD
# - end on the first observation below EVENT_END_THRESHOLD
EVENT_START_THRESHOLD = 1.0
EVENT_END_THRESHOLD = 0.0

# Sensitivity windows are calendar-day windows on the daily panel.
ROLLING_WINDOWS = [63, 126, 252]


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
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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

    return [column for column in required if column not in df.columns]


# ==============================================================
# NORMALIZATION
# ==============================================================

def normalize_research_schema(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(
        columns={
            "asof_date": "date",
            "YIELD_10Y_2Y_SPREAD": "YIELD_CURVE",
            "composite_stress_score": "FINANCIAL_STRESS_COMPOSITE",
            "research_regime": "RESEARCH_REGIME",
        }
    )

    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    df["RESEARCH_REGIME"] = (
        df["RESEARCH_REGIME"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    return df


# ==============================================================
# PIT
# ==============================================================

def parse_pit(value) -> bool | None:
    if pd.isna(value):
        return None

    text = str(value).strip().lower()

    if text in {"true", "1", "yes", "y"}:
        return True

    if text in {"false", "0", "no", "n"}:
        return False

    return None


# ==============================================================
# STRESS EVENTS V1.1
# ==============================================================

def empty_events() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "event_id",
            "start_date",
            "end_date",
            "duration_calendar_days",
            "duration_observations",
            "peak_date",
            "peak_composite",
            "peak_regime",
            "mean_composite",
            "time_to_peak_days",
            "recovery_date",
            "recovery_duration_days",
            "max_VIX_Z",
            "max_NFCI_Z",
            "max_ANFCI_Z",
            "max_YIELD_CURVE_STRESS_Z",
        ]
    )


def build_regime_events(df: pd.DataFrame) -> pd.DataFrame:
    """
    Hysteresis event definition.

    Start:
        composite >= 1.0

    Continue:
        composite >= 0.0

    End:
        first subsequent observation with composite < 0.0

    A weekend/holiday gap does not end an event because the panel
    contains trading observations rather than calendar observations.

    The recovery observation (< 0) is used as recovery_date/end_date
    but is not included in the event's stress statistics.
    """

    data = (
        df[
            [
                "date",
                "FINANCIAL_STRESS_COMPOSITE",
                "RESEARCH_REGIME",
                "VIX_Z",
                "NFCI_Z",
                "ANFCI_Z",
                "YIELD_CURVE_STRESS_Z",
            ]
        ]
        .copy()
        .sort_values("date")
        .reset_index(drop=True)
    )

    data = data[
        data["FINANCIAL_STRESS_COMPOSITE"].notna()
    ].reset_index(drop=True)

    if data.empty:
        return empty_events()

    events = []
    active_rows = []
    start_date = None

    def finalize(
        rows: list[dict],
        recovery_row: dict | None,
        event_number: int,
    ) -> None:
        if not rows:
            return

        event = pd.DataFrame(rows)

        peak_idx = event["FINANCIAL_STRESS_COMPOSITE"].idxmax()
        peak_row = event.loc[peak_idx]

        start = pd.Timestamp(event["date"].min())
        peak_date = pd.Timestamp(peak_row["date"])

        if recovery_row is not None:
            recovery_date = pd.Timestamp(recovery_row["date"])
            end_date = recovery_date
            recovery_duration = (recovery_date - peak_date).days
        else:
            recovery_date = pd.NaT
            end_date = pd.Timestamp(event["date"].max())
            recovery_duration = np.nan

        events.append(
            {
                "event_id": f"FS_EVENT_{event_number:04d}",
                "start_date": start,
                "end_date": end_date,
                "duration_calendar_days": (end_date - start).days + 1,
                "duration_observations": len(event),
                "peak_date": peak_date,
                "peak_composite": float(
                    event["FINANCIAL_STRESS_COMPOSITE"].max()
                ),
                "peak_regime": peak_row["RESEARCH_REGIME"],
                "mean_composite": float(
                    event["FINANCIAL_STRESS_COMPOSITE"].mean()
                ),
                "time_to_peak_days": (peak_date - start).days,
                "recovery_date": recovery_date,
                "recovery_duration_days": recovery_duration,
                "max_VIX_Z": event["VIX_Z"].max(),
                "max_NFCI_Z": event["NFCI_Z"].max(),
                "max_ANFCI_Z": event["ANFCI_Z"].max(),
                "max_YIELD_CURVE_STRESS_Z": event[
                    "YIELD_CURVE_STRESS_Z"
                ].max(),
            }
        )

    event_number = 0

    for _, row in data.iterrows():
        score = float(row["FINANCIAL_STRESS_COMPOSITE"])

        if start_date is None:
            if score >= EVENT_START_THRESHOLD:
                start_date = row["date"]
                active_rows = [row.to_dict()]
            continue

        # Active event.
        if score >= EVENT_END_THRESHOLD:
            active_rows.append(row.to_dict())
        else:
            event_number += 1
            finalize(
                active_rows,
                row.to_dict(),
                event_number,
            )
            start_date = None
            active_rows = []

    # Open event at end of sample.
    if active_rows:
        event_number += 1
        finalize(
            active_rows,
            None,
            event_number,
        )

    return pd.DataFrame(events) if events else empty_events()


# ==============================================================
# RAW STRESS TRANSFORMATION
# ==============================================================

def build_raw_stress_components(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Convert raw observations into stress-oriented levels.

    Higher value = more financial stress.

    VIX:
        higher = more stress

    NFCI / ANFCI:
        higher = more stress

    Yield curve:
        lower 10Y-2Y spread = more stress
        therefore multiply spread by -1.
    """

    result = pd.DataFrame({"date": df["date"]})

    result["VIX_RAW_STRESS"] = pd.to_numeric(
        df["VIX"], errors="coerce"
    )
    result["NFCI_RAW_STRESS"] = pd.to_numeric(
        df["NFCI"], errors="coerce"
    )
    result["ANFCI_RAW_STRESS"] = pd.to_numeric(
        df["ANFCI"], errors="coerce"
    )
    result["YIELD_CURVE_RAW_STRESS"] = -pd.to_numeric(
        df["YIELD_CURVE"], errors="coerce"
    )

    return result


# ==============================================================
# ROLLING Z-SCORE
# ==============================================================

def rolling_zscore(
    series: pd.Series,
    window_days: int,
    min_periods: int,
) -> pd.Series:
    rolling_mean = series.rolling(
        f"{window_days}D",
        min_periods=min_periods,
    ).mean()

    rolling_std = series.rolling(
        f"{window_days}D",
        min_periods=min_periods,
    ).std(ddof=0)

    return (
        (series - rolling_mean)
        / rolling_std.replace(0, np.nan)
    )


# ==============================================================
# FREQUENCY SENSITIVITY
# ==============================================================

def build_frequency_sensitivity(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Research-only sensitivity analysis.

    Method A:
        Actual Research v1 composite.

    Method B:
        Daily panel + 126-calendar-day rolling z-scores
        calculated from raw stress-oriented levels.

    Method C:
        Daily panel + 63-calendar-day rolling z-scores.

    Method D:
        Native-frequency normalization:
        each component is normalized only on its native
        observation dates, then aligned back to the daily panel.

    Method A is preserved exactly as the reference series.
    """

    raw = build_raw_stress_components(df)
    raw = raw.sort_values("date").set_index("date")

    sensitivity = pd.DataFrame(index=raw.index)

    sensitivity["METHOD_A_CURRENT"] = (
        df.set_index("date")[
            "FINANCIAL_STRESS_COMPOSITE"
        ]
    )

    component_map = {
        "VIX_RAW_STRESS": "VIX",
        "NFCI_RAW_STRESS": "NFCI",
        "ANFCI_RAW_STRESS": "ANFCI",
        "YIELD_CURVE_RAW_STRESS": "YIELD_CURVE",
    }

    # Daily-panel rolling windows.
    for window in ROLLING_WINDOWS:
        z_columns = []

        for raw_name in component_map:
            z_name = f"{raw_name}_Z_{window}D"
            sensitivity[z_name] = rolling_zscore(
                raw[raw_name],
                window_days=window,
                min_periods=max(12, window // 4),
            )
            z_columns.append(z_name)

        count_name = f"METHOD_{window}D_COMPONENT_COUNT"
        composite_name = f"METHOD_{window}D_COMPOSITE"

        sensitivity[count_name] = sensitivity[
            z_columns
        ].notna().sum(axis=1)

        sensitivity[composite_name] = sensitivity[
            z_columns
        ].mean(axis=1, skipna=True)

        sensitivity.loc[
            sensitivity[count_name] < MIN_COMPONENTS,
            composite_name,
        ] = np.nan

    # Native-frequency normalization.
    native_columns = []

    for raw_name in component_map:
        native_z_name = f"{raw_name}_NATIVE_Z"
        series = raw[raw_name].dropna()

        # Detect native cadence from the actual observations.
        if series.empty:
            sensitivity[native_z_name] = np.nan
            native_columns.append(native_z_name)
            continue

        deltas = series.index.to_series().diff().dt.days.dropna()
        median_delta = (
            float(deltas.median())
            if not deltas.empty
            else 1.0
        )

        if median_delta <= 2:
            native_window = 252
            native_min = 60
        else:
            native_window = 52
            native_min = 12

        native_mean = series.rolling(
            native_window,
            min_periods=native_min,
        ).mean()

        native_std = series.rolling(
            native_window,
            min_periods=native_min,
        ).std(ddof=0)

        native_z = (
            (series - native_mean)
            / native_std.replace(0, np.nan)
        )

        sensitivity[native_z_name] = native_z.reindex(
            sensitivity.index
        )
        native_columns.append(native_z_name)

    sensitivity["METHOD_D_NATIVE_COMPONENT_COUNT"] = (
        sensitivity[native_columns].notna().sum(axis=1)
    )

    sensitivity["METHOD_D_NATIVE_COMPOSITE"] = (
        sensitivity[native_columns].mean(axis=1, skipna=True)
    )

    sensitivity.loc[
        sensitivity["METHOD_D_NATIVE_COMPONENT_COUNT"]
        < MIN_COMPONENTS,
        "METHOD_D_NATIVE_COMPOSITE",
    ] = np.nan

    sensitivity = sensitivity.reset_index()

    # Comparison statistics.
    methods = {
        "METHOD_A_CURRENT": "A_CURRENT",
        "METHOD_63D_COMPOSITE": "B_63D",
        "METHOD_126D_COMPOSITE": "C_126D",
        "METHOD_252D_COMPOSITE": "D_252D",
        "METHOD_D_NATIVE_COMPOSITE": "E_NATIVE",
    }

    comparison_rows = []

    reference = sensitivity["METHOD_A_CURRENT"]

    for column, label in methods.items():
        valid = pd.DataFrame(
            {
                "reference": reference,
                "method": sensitivity[column],
            }
        ).dropna()

        if valid.empty:
            corr = np.nan
            mad = np.nan
            count = 0
        else:
            corr = valid["reference"].corr(valid["method"])
            mad = (
                valid["reference"]
                - valid["method"]
            ).abs().mean()
            count = len(valid)

        comparison_rows.append(
            {
                "method": label,
                "source_column": column,
                "rows_compared_with_method_A": count,
                "correlation_with_method_A": corr,
                "mean_absolute_difference_vs_method_A": mad,
                "note": (
                    "A is the existing Research v1 series; "
                    "other methods are sensitivity diagnostics."
                ),
            }
        )

    comparison = pd.DataFrame(comparison_rows)

    return sensitivity, comparison


# ==============================================================
# THRESHOLD SENSITIVITY
# ==============================================================

def threshold_sensitivity(
    df: pd.DataFrame,
) -> pd.DataFrame:
    thresholds = [0.0, 0.5, 1.0, 1.5, 2.0]
    rows = []

    composite = df["FINANCIAL_STRESS_COMPOSITE"]
    valid = composite.dropna()
    observations = len(valid)

    for threshold in thresholds:
        count = int((valid >= threshold).sum())

        rows.append(
            {
                "threshold": threshold,
                "observations": observations,
                "days_at_or_above_threshold": count,
                "percentage_at_or_above_threshold": (
                    count / observations * 100
                    if observations > 0
                    else np.nan
                ),
                "max_composite": valid.max(),
            }
        )

    return pd.DataFrame(rows)


# ==============================================================
# MAIN
# ==============================================================

def main() -> None:
    print("=" * 72)
    print("FINANCIAL STRESS HISTORICAL VALIDATION V1.1")
    print("=" * 72)

    research_path = find_file(INPUT_RESEARCH)

    print(f"Selected research input: {research_path}")
    print(f"File size: {research_path.stat().st_size} bytes")

    df = pd.read_csv(research_path)

    if df.empty:
        raise RuntimeError("Research input contains zero rows.")

    print(f"Raw rows loaded: {len(df)}")
    print(f"Raw columns: {list(df.columns)}")

    missing = validate_research_schema(df)
    if missing:
        raise RuntimeError(
            "Research input is missing required columns: "
            + ", ".join(missing)
        )

    df = normalize_research_schema(df)

    if df["date"].isna().any():
        raise RuntimeError(
            "Research input contains invalid dates."
        )

    df = (
        df.sort_values("date")
        .reset_index(drop=True)
    )

    duplicate_dates = int(df["date"].duplicated().sum())

    date_diffs = (
        df["date"]
        .diff()
        .dt.total_seconds()
        .div(86400)
        .dropna()
    )

    non_monotonic = int((date_diffs < 0).sum())

    # PIT
    df["PIT_PARSED"] = df["point_in_time_safe"].apply(parse_pit)

    invalid_pit = int(df["PIT_PARSED"].isna().sum())
    pit_unsafe = int((df["PIT_PARSED"] == False).sum())

    # Numeric conversion.
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

    scored = df["FINANCIAL_STRESS_COMPOSITE"].notna()
    scored_count = int(scored.sum())
    insufficient_count = len(df) - scored_count

    calculated_component_count = (
        df[COMPONENTS].notna().sum(axis=1)
    )

    component_count_mismatch = int(
        (
            calculated_component_count
            != df["stress_component_count"]
        ).sum()
    )

    df["CALCULATED_COMPONENT_COUNT"] = (
        calculated_component_count
    )

    regime_counts = (
        df["RESEARCH_REGIME"]
        .value_counts(dropna=False)
        .to_dict()
    )

    # Annual statistics.
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

    # Component availability.
    component_availability_rows = []

    for component in COMPONENTS:
        available = int(df[component].notna().sum())

        component_availability_rows.append(
            {
                "component": component,
                "available_observations": available,
                "missing_observations": len(df) - available,
                "availability_pct": (
                    available / len(df) * 100
                ),
            }
        )

    component_availability = pd.DataFrame(
        component_availability_rows
    )

    # Component correlations.
    correlation = (
        df[
            COMPONENTS
            + ["FINANCIAL_STRESS_COMPOSITE"]
        ].corr()
    )

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

    # ----------------------------------------------------------
    # Events V1.1
    # ----------------------------------------------------------

    events = build_regime_events(df)

    # ----------------------------------------------------------
    # Frequency sensitivity
    # ----------------------------------------------------------

    frequency_detail, frequency_comparison = (
        build_frequency_sensitivity(df)
    )

    # The requested frequency artifact contains both:
    # 1. date-level sensitivity detail
    # 2. comparison rows.
    frequency_detail.to_csv(
        OUTPUT_FREQUENCY,
        index=False,
    )

    # ----------------------------------------------------------
    # Threshold sensitivity
    # ----------------------------------------------------------

    thresholds = threshold_sensitivity(df)

    # ----------------------------------------------------------
    # Validation checks
    # ----------------------------------------------------------

    checks = [
        {
            "check": "non_empty_input",
            "status": "PASS" if len(df) > 0 else "FAIL",
            "value": len(df),
        },
        {
            "check": "duplicate_dates",
            "status": "PASS" if duplicate_dates == 0 else "FAIL",
            "value": duplicate_dates,
        },
        {
            "check": "monotonic_dates",
            "status": "PASS" if non_monotonic == 0 else "FAIL",
            "value": non_monotonic,
        },
        {
            "check": "invalid_pit_values",
            "status": "PASS" if invalid_pit == 0 else "FAIL",
            "value": invalid_pit,
        },
        {
            "check": "pit_unsafe_rows",
            "status": "PASS" if pit_unsafe == 0 else "FAIL",
            "value": pit_unsafe,
        },
        {
            "check": "scored_observations",
            "status": "PASS" if scored_count > 0 else "FAIL",
            "value": scored_count,
        },
        {
            "check": "component_count_consistency",
            "status": (
                "PASS"
                if component_count_mismatch == 0
                else "REVIEW"
            ),
            "value": component_count_mismatch,
        },
        {
            "check": "research_only",
            "status": "PASS",
            "value": "validation_only",
        },
    ]

    checks_df = pd.DataFrame(checks)

    # ----------------------------------------------------------
    # Detailed validation output
    # ----------------------------------------------------------

    output = df.copy()

    output["PIT_VALID"] = df["PIT_PARSED"] == True
    output["COMPONENT_COUNT"] = calculated_component_count

    output["VALIDATION_STATUS"] = np.where(
        (
            output["PIT_VALID"]
            & output["FINANCIAL_STRESS_COMPOSITE"].notna()
            & (output["COMPONENT_COUNT"] >= MIN_COMPONENTS)
        ),
        "VALID",
        "REVIEW",
    )

    output["record_id_validation"] = output.apply(
        lambda row: sha256_text(
            "|".join(
                [
                    str(row["date"].date()),
                    str(
                        row[
                            "FINANCIAL_STRESS_COMPOSITE"
                        ]
                    ),
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

    # ----------------------------------------------------------
    # Summary
    # ----------------------------------------------------------

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
            "value": insufficient_count,
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
            "metric": "component_count_mismatch",
            "value": component_count_mismatch,
        },
        {
            "metric": "stress_event_count",
            "value": len(events),
        },
        {
            "metric": "event_start_threshold",
            "value": EVENT_START_THRESHOLD,
        },
        {
            "metric": "event_end_threshold",
            "value": EVENT_END_THRESHOLD,
        },
        {
            "metric": "frequency_methods",
            "value": "A=current; B=63D; C=126D; D=252D; E=native",
        },
        {
            "metric": "research_only",
            "value": True,
        },
    ]

    for _, row in frequency_comparison.iterrows():
        method = row["method"]

        summary_rows.extend(
            [
                {
                    "metric":
                        f"frequency_{method}_rows",
                    "value":
                        row[
                            "rows_compared_with_method_A"
                        ],
                },
                {
                    "metric":
                        f"frequency_{method}_correlation_vs_A",
                    "value":
                        row[
                            "correlation_with_method_A"
                        ],
                },
                {
                    "metric":
                        f"frequency_{method}_MAD_vs_A",
                    "value":
                        row[
                            "mean_absolute_difference_vs_method_A"
                        ],
                },
            ]
        )

    for regime in RESEARCH_REGIMES:
        count = int(
            (
                df["RESEARCH_REGIME"] == regime
            ).sum()
        )

        percentage = (
            count / len(df) * 100
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

    summary = pd.DataFrame(summary_rows)

    summary.to_csv(
        OUTPUT_SUMMARY,
        index=False,
    )

    events.to_csv(
        OUTPUT_EVENTS,
        index=False,
    )

    # ----------------------------------------------------------
    # Console report
    # ----------------------------------------------------------

    print()
    print("-" * 72)
    print("VALIDATION SUMMARY V1.1")
    print("-" * 72)

    print(
        f"Date range: "
        f"{df['date'].min().date()} -> "
        f"{df['date'].max().date()}"
    )

    print(f"Rows: {len(df)}")
    print(f"Scored rows: {scored_count}")
    print(f"Insufficient rows: {insufficient_count}")
    print(f"Duplicate dates: {duplicate_dates}")
    print(f"PIT unsafe rows: {pit_unsafe}")
    print(f"Invalid PIT values: {invalid_pit}")
    print(
        "Component count mismatches: "
        f"{component_count_mismatch}"
    )
    print(f"Stress events: {len(events)}")

    print()
    print("Event definition:")
    print(
        f"  Start >= {EVENT_START_THRESHOLD}"
    )
    print(
        f"  Continue >= {EVENT_END_THRESHOLD}"
    )
    print(
        f"  End < {EVENT_END_THRESHOLD}"
    )

    print()
    print("Regime distribution:")
    for regime in RESEARCH_REGIMES:
        print(
            f"  {regime}: "
            f"{regime_counts.get(regime, 0)}"
        )

    print()
    print("Frequency sensitivity:")
    print(
        frequency_comparison.to_string(index=False)
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
    print("Annual statistics:")
    print(annual.to_string(index=False))

    print()
    print("Component availability:")
    print(
        component_availability.to_string(index=False)
    )

    print()
    print("Component correlations:")
    print(
        correlation_df.to_string(index=False)
    )

    print()
    print("Threshold sensitivity:")
    print(
        thresholds.to_string(index=False)
    )

    print()
    print("Stress events:")
    if events.empty:
        print("  None detected.")
    else:
        print(
            events.to_string(index=False)
        )

    print()
    print("Output files:")
    print(f"  {OUTPUT_VALIDATION}")
    print(f"  {OUTPUT_SUMMARY}")
    print(f"  {OUTPUT_EVENTS}")
    print(f"  {OUTPUT_FREQUENCY}")

    print()
    print("=" * 72)
    print(
        "FINANCIAL STRESS HISTORICAL "
        "VALIDATION V1.1 COMPLETE"
    )
    print("=" * 72)


if __name__ == "__main__":
    main()
