"""
US500 Macro Intelligence
Economic Intelligence — Phase 1A
Point-in-Time Economic Event Dataset

Research-only. No trade signals. No Decision Engine integration.

Design principles:
- Preserve the original release information set.
- Never replace an original release value with a later revision.
- Consensus is UNKNOWN unless a historically verifiable source is supplied.
- A record is historical_analog_eligible only when the required PIT fields pass validation.
- Official-source metadata is stored explicitly.

This first implementation is an ingestion + quality-gate layer.
It intentionally does NOT fabricate historical consensus estimates.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import math
import pandas as pd


OUTPUT_EVENTS = "economic_events_v1.csv"
OUTPUT_QUALITY = "economic_data_quality_v1.csv"
INPUT_FILE = "economic_release_records_input_v1.csv"

SUPPORTED_INDICATORS = {
    "CPI": {
        "agency": "BLS",
        "unit": "percent",
        "source_type": "official_release",
    },
    "CORE_CPI": {
        "agency": "BLS",
        "unit": "percent",
        "source_type": "official_release",
    },
    "NFP": {
        "agency": "BLS",
        "unit": "thousands_jobs",
        "source_type": "official_release",
    },
    "UNEMPLOYMENT_RATE": {
        "agency": "BLS",
        "unit": "percent",
        "source_type": "official_release",
    },
    "INITIAL_JOBLESS_CLAIMS": {
        "agency": "DOL",
        "unit": "claims",
        "source_type": "official_release",
    },
    "ISM_MANUFACTURING_PMI": {
        "agency": "ISM",
        "unit": "index",
        "source_type": "official_release",
    },
    "GDP": {
        "agency": "BEA",
        "unit": "percent_annualized",
        "source_type": "official_release",
    },
}

REQUIRED_COLUMNS = [
    "event_id",
    "indicator",
    "release_date",
    "release_time",
    "reference_period",
    "actual",
    "previous",
    "revision",
    "consensus",
    "consensus_source",
    "source",
    "source_url",
    "vintage_date",
]


@dataclass
class QualityResult:
    event_id: str
    indicator: str
    point_in_time_safe: bool
    historical_analog_eligible: bool
    data_quality: str
    issues: str


def is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        return bool(pd.isna(value))
    except Exception:
        return False


def parse_date(value) -> Optional[pd.Timestamp]:
    if is_missing(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed


def parse_float(value) -> Optional[float]:
    if is_missing(value):
        return None
    try:
        number = float(str(value).replace(",", "").strip())
        if not math.isfinite(number):
            return None
        return number
    except (ValueError, TypeError):
        return None


def validate_record(row: pd.Series) -> QualityResult:
    event_id = str(row.get("event_id", "")).strip()
    indicator = str(row.get("indicator", "")).strip()

    issues = []

    if indicator not in SUPPORTED_INDICATORS:
        issues.append("unsupported_indicator")

    release_date = parse_date(row.get("release_date"))
    if release_date is None:
        issues.append("invalid_release_date")

    actual = parse_float(row.get("actual"))
    if actual is None:
        issues.append("missing_or_invalid_actual")

    if is_missing(row.get("source")):
        issues.append("missing_source")

    if is_missing(row.get("source_url")):
        issues.append("missing_source_url")

    # Consensus is deliberately NOT required.
    # It becomes safe only when the source is historically verifiable.
    consensus = parse_float(row.get("consensus"))
    consensus_source = str(row.get("consensus_source", "")).strip()

    if consensus is not None and not consensus_source:
        issues.append("consensus_without_source")

    vintage_date = parse_date(row.get("vintage_date"))
    if vintage_date is not None and release_date is not None:
        if vintage_date > release_date:
            issues.append("vintage_after_release")

    # A PIT record must contain the release timestamp and original actual.
    if is_missing(row.get("release_time")):
        issues.append("missing_release_time")

    if is_missing(row.get("reference_period")):
        issues.append("missing_reference_period")

    point_in_time_safe = len(issues) == 0

    # Consensus-based surprise is eligible only when consensus itself
    # has an explicitly documented historical source.
    consensus_safe = consensus is not None and bool(consensus_source)

    historical_analog_eligible = point_in_time_safe

    if actual is not None and consensus_safe:
        data_quality = "PIT_VERIFIED_WITH_HISTORICAL_CONSENSUS"
    elif point_in_time_safe:
        data_quality = "PIT_RELEASE_VERIFIED_CONSENSUS_UNKNOWN"
    else:
        data_quality = "REQUIRES_REVIEW"

    return QualityResult(
        event_id=event_id,
        indicator=indicator,
        point_in_time_safe=point_in_time_safe,
        historical_analog_eligible=historical_analog_eligible,
        data_quality=data_quality,
        issues=";".join(issues),
    )


def calculate_surprise(row: pd.Series):
    actual = parse_float(row.get("actual"))
    consensus = parse_float(row.get("consensus"))
    consensus_source = str(row.get("consensus_source", "")).strip()

    if actual is None or consensus is None or not consensus_source:
        return pd.NA, pd.NA, "UNKNOWN"

    surprise = actual - consensus

    # Percentage surprise is intentionally not calculated for zero
    # consensus because the denominator would be undefined.
    if consensus == 0:
        surprise_pct = pd.NA
    else:
        surprise_pct = (surprise / abs(consensus)) * 100.0

    if surprise > 0:
        direction = "ABOVE_CONSENSUS"
    elif surprise < 0:
        direction = "BELOW_CONSENSUS"
    else:
        direction = "IN_LINE"

    return surprise, surprise_pct, direction


def normalize_input(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            "Input file is missing required columns: " + ", ".join(missing)
        )

    output = df.copy()

    output["release_date"] = pd.to_datetime(
        output["release_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")

    output["vintage_date"] = pd.to_datetime(
        output["vintage_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")

    output["actual"] = output["actual"].apply(parse_float)
    output["previous"] = output["previous"].apply(parse_float)
    output["revision"] = output["revision"].apply(parse_float)
    output["consensus"] = output["consensus"].apply(parse_float)

    surprises = output.apply(calculate_surprise, axis=1, result_type="expand")
    surprises.columns = [
        "surprise",
        "surprise_pct",
        "surprise_direction",
    ]

    output = pd.concat([output, surprises], axis=1)

    quality = output.apply(validate_record, axis=1, result_type="expand")
    quality.columns = [
        "event_id",
        "indicator",
        "point_in_time_safe",
        "historical_analog_eligible",
        "data_quality",
        "quality_issues",
    ]

    output = output.drop(
        columns=[
            "point_in_time_safe",
            "historical_analog_eligible",
            "data_quality",
            "quality_issues",
        ],
        errors="ignore",
    )

    output = pd.concat([output, quality.drop(columns=["event_id", "indicator"])], axis=1)

    output["source_type"] = output["indicator"].map(
        lambda x: SUPPORTED_INDICATORS.get(x, {}).get("source_type", "UNKNOWN")
    )
    output["agency"] = output["indicator"].map(
        lambda x: SUPPORTED_INDICATORS.get(x, {}).get("agency", "UNKNOWN")
    )
    output["unit"] = output["indicator"].map(
        lambda x: SUPPORTED_INDICATORS.get(x, {}).get("unit", "UNKNOWN")
    )

    # Stable event ordering.
    output = output.sort_values(
        ["release_date", "release_time", "indicator", "event_id"],
        na_position="last",
    ).reset_index(drop=True)

    return output


def build_quality_report(events: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for indicator, meta in SUPPORTED_INDICATORS.items():
        subset = events[events["indicator"] == indicator]

        total = len(subset)
        pit_safe = int(subset["point_in_time_safe"].fillna(False).sum())
        eligible = int(subset["historical_analog_eligible"].fillna(False).sum())
        consensus_known = int(
            (
                subset["consensus"].notna()
                & subset["consensus_source"].fillna("").astype(str).str.strip().ne("")
            ).sum()
        )

        rows.append(
            {
                "indicator": indicator,
                "agency": meta["agency"],
                "records": total,
                "point_in_time_safe_records": pit_safe,
                "historical_analog_eligible_records": eligible,
                "historical_consensus_records": consensus_known,
                "pit_safe_pct": round((pit_safe / total) * 100, 2)
                if total else 0.0,
                "eligible_pct": round((eligible / total) * 100, 2)
                if total else 0.0,
            }
        )

    return pd.DataFrame(rows)


def create_template():
    columns = REQUIRED_COLUMNS + [
        "notes",
    ]

    template = pd.DataFrame(columns=columns)
    template.to_csv(INPUT_FILE, index=False)

    print(f"Created empty input template: {INPUT_FILE}")
    print(
        "Populate it only with historically verifiable release records. "
        "Do not backfill historical consensus from today's estimates."
    )


def main():
    print("=" * 72)
    print("US500 MACRO INTELLIGENCE")
    print("ECONOMIC INTELLIGENCE — PHASE 1A")
    print("POINT-IN-TIME DATASET + QUALITY GATE")
    print("=" * 72)

    input_path = Path(INPUT_FILE)

    if not input_path.exists():
        create_template()
        print("\nSTATUS: TEMPLATE_CREATED")
        print("No economic records were fabricated or inferred.")
        return

    df = pd.read_csv(input_path)

    if df.empty:
        pd.DataFrame(columns=REQUIRED_COLUMNS + [
            "surprise", "surprise_pct", "surprise_direction",
            "point_in_time_safe", "historical_analog_eligible",
            "data_quality", "quality_issues", "source_type", "agency", "unit"
        ]).to_csv(OUTPUT_EVENTS, index=False)
        build_quality_report(pd.DataFrame(columns=[
            "indicator", "point_in_time_safe",
            "historical_analog_eligible", "consensus",
            "consensus_source"
        ])).to_csv(OUTPUT_QUALITY, index=False)
        print("\nSTATUS: EMPTY_INPUT")
        print(f"Populate {INPUT_FILE} with verified release records.")
        print(f"Created empty outputs: {OUTPUT_EVENTS}, {OUTPUT_QUALITY}")
        return

    events = normalize_input(df)

    events.to_csv(OUTPUT_EVENTS, index=False)

    quality = build_quality_report(events)
    quality.to_csv(OUTPUT_QUALITY, index=False)

    total = len(events)
    pit_safe = int(events["point_in_time_safe"].sum())
    eligible = int(events["historical_analog_eligible"].sum())
    consensus_known = int(
        (
            events["consensus"].notna()
            & events["consensus_source"].fillna("").astype(str).str.strip().ne("")
        ).sum()
    )

    print("\nQUALITY GATE")
    print("-" * 72)
    print(f"Total events:                 {total}")
    print(f"PIT safe:                     {pit_safe}/{total}")
    print(f"Historical eligible:          {eligible}/{total}")
    print(f"Historically sourced consensus: {consensus_known}/{total}")

    print("\nBY INDICATOR")
    print(quality.to_string(index=False))

    print("\nOUTPUTS")
    print(f"- {OUTPUT_EVENTS}")
    print(f"- {OUTPUT_QUALITY}")

    if pit_safe == total:
        print("\nPIT QUALITY GATE: PASS")
    else:
        print("\nPIT QUALITY GATE: REVIEW REQUIRED")

    print("\nResearch-only. No Decision Engine integration.")


if __name__ == "__main__":
    main()
