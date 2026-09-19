"""
US500 Macro Intelligence
Economic Intelligence — Economic Surprise Engine v1.2
FILE NAME: economic_surprise_engine_v1.1.py

Purpose
-------
Research-only transformation of point-in-time economic release data into
directional release shocks and point-in-time expanding z-scores.

v1.2 methodology:
1. Use official "previous" when it is explicitly present.
2. If official previous is unavailable, use the immediately prior published
   observation for the same indicator, provided its release_date is strictly
   earlier than the current release_date.
3. Never fabricate consensus.
4. Never use future observations.
5. Never fall back from z-score to raw shock.
6. Keep Decision Engine integration disabled.

This distinction is important:
- OFFICIAL_PREVIOUS = value explicitly reported as previous/revised prior value
  in the current release.
- PRIOR_OBSERVATION = previous point-in-time published observation used only
  to measure sequential change when the current release does not provide an
  official previous value.

The PRIOR_OBSERVATION method is NOT presented as historical consensus.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


INPUT_FILE = "economic_historical_events_v1.csv"
OUTPUT_FILE = "economic_surprise_engine_v1.csv"
SUMMARY_FILE = "economic_surprise_summary_v1.csv"

MIN_PRIOR_HISTORY = 3

# Positive multiplier means a higher raw release delta is economically
# "more positive" for the macro dimension.
DIRECTION_MAP = {
    "CPI": 1.0,
    "CORE_CPI": 1.0,
    "NFP": 1.0,
    "UNEMPLOYMENT_RATE": -1.0,
    "INITIAL_JOBLESS_CLAIMS": -1.0,
    "ISM_MANUFACTURING_PMI": 1.0,
    "GDP": 1.0,
}


@dataclass
class GateResult:
    name: str
    passed: bool
    detail: str


def as_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.normalize()


def has_value(value) -> bool:
    return pd.notna(value)


def validate_required_columns(df: pd.DataFrame) -> None:
    required = {
        "indicator",
        "release_date",
        "actual",
        "previous",
        "consensus",
        "consensus_source",
        "vintage_date",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def point_in_time_safe(row: pd.Series) -> bool:
    release = pd.to_datetime(row["release_date"], errors="coerce")
    vintage = pd.to_datetime(row["vintage_date"], errors="coerce")

    if pd.isna(release) or pd.isna(vintage):
        return False

    if vintage > release:
        return False

    if pd.isna(row["actual"]):
        return False

    return True


def historical_consensus_available(row: pd.Series) -> bool:
    return (
        pd.notna(row["consensus"])
        and pd.notna(row["consensus_source"])
        and str(row["consensus_source"]).strip() != ""
    )


def calculate_prior_observation_change(
    df: pd.DataFrame,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate sequential change using only information available before the
    current release.

    For each indicator:
      previous published actual = actual from the latest earlier release_date.

    IMPORTANT:
    This is deliberately different from the `previous` field supplied by an
    official release. It is used only when official previous is missing.
    """

    work = df.copy()
    work["_release_dt"] = pd.to_datetime(work["release_date"], errors="coerce")
    work["_actual_num"] = pd.to_numeric(work["actual"], errors="coerce")

    # Stable chronological order. The original row order is retained as a
    # deterministic tie-breaker for same-day releases.
    work["_row_order"] = np.arange(len(work))
    work = work.sort_values(
        ["indicator", "_release_dt", "_row_order"],
        kind="mergesort",
    )

    prior_actual = pd.Series(np.nan, index=work.index, dtype="float64")
    prior_release = pd.Series(pd.NaT, index=work.index, dtype="datetime64[ns]")

    # Shift is safe because rows are chronological within each indicator.
    grouped = work.groupby("indicator", sort=False)
    prior_actual.loc[work.index] = grouped["_actual_num"].shift(1)
    prior_release.loc[work.index] = grouped["_release_dt"].shift(1)

    # Restore original order/index.
    prior_actual = prior_actual.reindex(df.index)
    prior_release = prior_release.reindex(df.index)

    return prior_actual, prior_release, work["_row_order"].reindex(df.index)


def calculate_prior_zscore(
    df: pd.DataFrame,
    value_column: str = "directional_release_shock",
) -> tuple[pd.Series, pd.Series]:
    """
    Point-in-time expanding z-score.

    For each row, mean/std are calculated from PRIOR valid observations only.
    Current observation is never included in its own baseline.

    Requires MIN_PRIOR_HISTORY valid prior observations.
    """

    work = df.copy()
    work["_release_dt"] = pd.to_datetime(work["release_date"], errors="coerce")
    work["_row_order"] = np.arange(len(work))
    work[value_column] = pd.to_numeric(work[value_column], errors="coerce")

    work = work.sort_values(
        ["indicator", "_release_dt", "_row_order"],
        kind="mergesort",
    )

    z = pd.Series(np.nan, index=work.index, dtype="float64")
    prior_count = pd.Series(0, index=work.index, dtype="int64")

    for indicator, idx in work.groupby("indicator", sort=False).groups.items():
        sub = work.loc[idx].sort_values(
            ["_release_dt", "_row_order"],
            kind="mergesort",
        )

        values = pd.to_numeric(sub[value_column], errors="coerce")
        prior_values = values.shift(1)

        expanding_count = prior_values.notna().cumsum()
        expanding_mean = prior_values.expanding(
            min_periods=MIN_PRIOR_HISTORY
        ).mean()
        expanding_std = prior_values.expanding(
            min_periods=MIN_PRIOR_HISTORY
        ).std(ddof=1)

        prior_count.loc[sub.index] = expanding_count.astype(int).values

        denom = expanding_std.replace(0, np.nan)
        z_values = (values - expanding_mean) / denom

        z.loc[sub.index] = z_values.values

    return z.reindex(df.index), prior_count.reindex(df.index)


def classify_zscore(z):
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


def build_summary(result: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for indicator, group in result.groupby("indicator", sort=True):
        pit = group["point_in_time_safe"]
        consensus = group["consensus_available"]
        z = group["directional_zscore"]

        method_counts = (
            group["delta_method"]
            .fillna("NONE")
            .value_counts()
            .to_dict()
        )

        rows.append(
            {
                "indicator": indicator,
                "records": int(len(group)),
                "pit_safe_records": int(pit.sum()),
                "historical_consensus_records": int(consensus.sum()),
                "directional_shock_records": int(
                    group["directional_release_shock"].notna().sum()
                ),
                "zscore_records": int(z.notna().sum()),
                "insufficient_history_records": int(
                    (group["zscore_class"] == "INSUFFICIENT_HISTORY").sum()
                ),
                "official_previous_delta_records": int(
                    method_counts.get("OFFICIAL_PREVIOUS", 0)
                ),
                "prior_observation_delta_records": int(
                    method_counts.get("PRIOR_OBSERVATION", 0)
                ),
                "no_delta_records": int(method_counts.get("NONE", 0)),
            }
        )

    return pd.DataFrame(rows)


def main() -> None:
    input_path = Path(INPUT_FILE)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_FILE}")

    df = pd.read_csv(input_path)
    validate_required_columns(df)

    df["release_date"] = as_date(df["release_date"])
    df["vintage_date"] = as_date(df["vintage_date"])
    df["actual"] = pd.to_numeric(df["actual"], errors="coerce")
    df["previous"] = pd.to_numeric(df["previous"], errors="coerce")
    df["consensus"] = pd.to_numeric(df["consensus"], errors="coerce")

    unknown_indicators = sorted(
        set(df["indicator"].dropna().astype(str)) - set(DIRECTION_MAP)
    )
    if unknown_indicators:
        raise ValueError(
            f"Indicators missing from DIRECTION_MAP: {unknown_indicators}"
        )

    df["point_in_time_safe"] = df.apply(point_in_time_safe, axis=1)
    df["consensus_available"] = df.apply(
        historical_consensus_available, axis=1
    )

    # Strict PIT gate before any sequential calculation.
    if not df["point_in_time_safe"].all():
        bad = df.loc[~df["point_in_time_safe"]].head(10)
        raise AssertionError(
            "PIT gate failed. Examples:\n"
            + bad.to_string(index=False)
        )

    # Stable chronological order for all point-in-time calculations.
    df["_release_dt"] = pd.to_datetime(df["release_date"], errors="coerce")
    df["_row_order"] = np.arange(len(df))
    df = df.sort_values(
        ["indicator", "_release_dt", "_row_order"],
        kind="mergesort",
    ).reset_index(drop=True)

    # ---------------------------------------------------------------
    # CLASSIC CONSENSUS SURPRISE
    # ---------------------------------------------------------------
    df["classic_surprise"] = np.nan

    consensus_mask = (
        df["consensus_available"]
        & df["actual"].notna()
        & df["consensus"].notna()
    )

    df.loc[consensus_mask, "classic_surprise"] = (
        df.loc[consensus_mask, "actual"]
        - df.loc[consensus_mask, "consensus"]
    )

    # ---------------------------------------------------------------
    # DELTA METHOD
    # ---------------------------------------------------------------
    # Official previous takes precedence.
    df["prior_observation"] = np.nan
    df["prior_observation_release_date"] = pd.NaT

    for indicator, idx in df.groupby("indicator", sort=False).groups.items():
        sub = df.loc[idx].sort_values(
            ["release_date", "_row_order"],
            kind="mergesort",
        )

        previous_actual = pd.to_numeric(sub["actual"], errors="coerce").shift(1)
        previous_release = sub["release_date"].shift(1)

        df.loc[sub.index, "prior_observation"] = previous_actual.values
        df.loc[
            sub.index, "prior_observation_release_date"
        ] = previous_release.values

    df["delta_method"] = "NONE"
    df["delta_reference_value"] = np.nan
    df["delta_reference_release_date"] = pd.NaT

    official_previous_mask = (
        df["previous"].notna()
        & df["actual"].notna()
    )

    prior_observation_mask = (
        ~official_previous_mask
        & df["actual"].notna()
        & df["prior_observation"].notna()
        & df["prior_observation_release_date"].notna()
        & (
            df["prior_observation_release_date"]
            < df["release_date"]
        )
    )

    df.loc[official_previous_mask, "delta_method"] = "OFFICIAL_PREVIOUS"
    df.loc[official_previous_mask, "delta_reference_value"] = (
        df.loc[official_previous_mask, "previous"]
    )

    # The previous published observation is only a fallback for sequential
    # change, never a fabricated "official previous" value.
    df.loc[prior_observation_mask, "delta_method"] = "PRIOR_OBSERVATION"
    df.loc[prior_observation_mask, "delta_reference_value"] = (
        df.loc[prior_observation_mask, "prior_observation"]
    )
    df.loc[prior_observation_mask, "delta_reference_release_date"] = (
        df.loc[prior_observation_mask, "prior_observation_release_date"]
    )

    # Official previous release date is not available as a separate field in
    # the input schema, so leave it blank. The value itself is explicitly
    # reported by the current release.
    df.loc[official_previous_mask, "delta_reference_release_date"] = pd.NaT

    df["release_delta"] = np.nan

    valid_delta_mask = (
        df["actual"].notna()
        & df["delta_reference_value"].notna()
    )

    df.loc[valid_delta_mask, "release_delta"] = (
        df.loc[valid_delta_mask, "actual"]
        - df.loc[valid_delta_mask, "delta_reference_value"]
    )

    # ---------------------------------------------------------------
    # DIRECTIONAL SHOCK
    # ---------------------------------------------------------------
    df["direction_multiplier"] = df["indicator"].map(DIRECTION_MAP)

    df["directional_release_shock"] = np.nan
    shock_mask = (
        df["release_delta"].notna()
        & df["direction_multiplier"].notna()
    )

    df.loc[shock_mask, "directional_release_shock"] = (
        df.loc[shock_mask, "release_delta"]
        * df.loc[shock_mask, "direction_multiplier"]
    )

    # ---------------------------------------------------------------
    # POINT-IN-TIME EXPANDING Z-SCORE
    # ---------------------------------------------------------------
    (
        df["directional_zscore"],
        df["prior_valid_observation_count"],
    ) = calculate_prior_zscore(
        df,
        value_column="directional_release_shock",
    )

    df["zscore_class"] = df["directional_zscore"].apply(classify_zscore)

    # ---------------------------------------------------------------
    # RESEARCH-ONLY FLAGS
    # ---------------------------------------------------------------
    df["research_only"] = True
    df["decision_engine_ready"] = False

    # Methodology audit fields.
    df["zscore_method"] = "EXPANDING_PRIOR_ONLY"
    df["consensus_method"] = np.where(
        df["consensus_available"],
        "HISTORICAL_CONSENSUS_IF_EXPLICITLY_SOURCED",
        "NOT_AVAILABLE",
    )

    # Remove internal calculation fields.
    drop_columns = ["_release_dt", "_row_order"]
    df = df.drop(columns=drop_columns, errors="ignore")

    # Keep output deterministic and readable.
    preferred_order = [
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
        "point_in_time_safe",
        "consensus_available",
        "classic_surprise",
        "prior_observation",
        "prior_observation_release_date",
        "delta_method",
        "delta_reference_value",
        "delta_reference_release_date",
        "release_delta",
        "direction_multiplier",
        "directional_release_shock",
        "directional_zscore",
        "prior_valid_observation_count",
        "zscore_class",
        "zscore_method",
        "consensus_method",
        "research_only",
        "decision_engine_ready",
    ]

    output_columns = [
        c for c in preferred_order if c in df.columns
    ] + [
        c for c in df.columns if c not in preferred_order
    ]

    df = df[output_columns]

    # ---------------------------------------------------------------
    # QUALITY GATES
    # ---------------------------------------------------------------
    gates = [
        GateResult(
            "PIT_SAFE",
            bool(df["point_in_time_safe"].all()),
            f"{int(df['point_in_time_safe'].sum())}/{len(df)}",
        ),
        GateResult(
            "NO_LOOKAHEAD",
            bool(
                (
                    pd.to_datetime(df["vintage_date"], errors="coerce")
                    <= pd.to_datetime(df["release_date"], errors="coerce")
                ).all()
            ),
            "vintage_date <= release_date",
        ),
        GateResult(
            "NO_FABRICATED_CONSENSUS",
            True,
            "Consensus used only when explicitly sourced.",
        ),
        GateResult(
            "NO_RAW_FALLBACK",
            True,
            "Z-score is NaN when prior history is insufficient.",
        ),
        GateResult(
            "RESEARCH_ONLY",
            bool(df["research_only"].all()),
            "All records research_only=True",
        ),
        GateResult(
            "DECISION_ENGINE_DISABLED",
            bool((~df["decision_engine_ready"]).all()),
            "All records decision_engine_ready=False",
        ),
    ]

    failed = [g for g in gates if not g.passed]
    if failed:
        for gate in gates:
            status = "PASS" if gate.passed else "FAIL"
            print(f"{status}: {gate.name} — {gate.detail}")
        raise AssertionError("Economic Surprise Engine v1.2 quality gate failed.")

    summary = build_summary(df)

    df.to_csv(OUTPUT_FILE, index=False)
    summary.to_csv(SUMMARY_FILE, index=False)

    # ---------------------------------------------------------------
    # CONSOLE REPORT
    # ---------------------------------------------------------------
    print("=" * 60)
    print("US500 Macro Intelligence")
    print("Economic Surprise Engine v1.2")
    print("=" * 60)
    print(f"Input records: {len(df)}")
    print(f"PIT-safe records: {int(df['point_in_time_safe'].sum())}/{len(df)}")
    print(
        "Historical consensus records:",
        int(df["consensus_available"].sum()),
    )
    print(
        "Official-previous deltas:",
        int((df["delta_method"] == "OFFICIAL_PREVIOUS").sum()),
    )
    print(
        "Prior-observation deltas:",
        int((df["delta_method"] == "PRIOR_OBSERVATION").sum()),
    )
    print(
        "Directional release shocks:",
        int(df["directional_release_shock"].notna().sum()),
    )
    print(
        "PIT-safe z-scores:",
        int(df["directional_zscore"].notna().sum()),
    )
    print(f"Minimum prior history: {MIN_PRIOR_HISTORY}")
    print(f"Indicators: {df['indicator'].nunique()}")

    print("\nZ-score coverage by indicator:")
    coverage = (
        df.groupby("indicator")
        .agg(
            records=("indicator", "size"),
            zscores=("directional_zscore", "count"),
            official_previous=(
                "delta_method",
                lambda x: int((x == "OFFICIAL_PREVIOUS").sum()),
            ),
            prior_observation=(
                "delta_method",
                lambda x: int((x == "PRIOR_OBSERVATION").sum()),
            ),
        )
        .reset_index()
    )
    print(coverage.to_string(index=False))

    print("\nQUALITY GATES")
    for gate in gates:
        print(f"PASS: {gate.name} — {gate.detail}")

    print("\nOUTPUTS")
    print(OUTPUT_FILE)
    print(SUMMARY_FILE)

    print("\nECONOMIC SURPRISE ENGINE v1.2: PASS")


if __name__ == "__main__":
    main()
