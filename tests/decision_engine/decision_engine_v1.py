#!/usr/bin/env python3

"""
US500 MACRO INTELLIGENCE
DECISION ENGINE V1

CONTRACT-FIRST / RESEARCH-ONLY

Purpose:
- Consume ONLY the validated Research Context v1 summary.
- Preserve the frozen architecture contract.
- Produce a descriptive research-context record.
- Do NOT generate trading signals.
- Do NOT generate forecasts.
- Do NOT execute trades.
- Do NOT score market direction.
- Do NOT convert regimes into BUY/SELL decisions.

Frozen invariants:
    research_only = TRUE
    decision_engine_ready = FALSE
    trading_signal_generated = FALSE
    forecast_generated = FALSE
    unified_decision_generated = FALSE
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ARCHITECTURE_VERSION = "1.0"
METHODOLOGY_VERSION = "DECISION_ENGINE_V1_CONTRACT_FIRST"

INPUT_FILENAME = "research_context_summary_v1.csv"

LAYER_NAMES = (
    "macro",
    "sentiment",
    "technical",
)

TOTAL_LAYER_COUNT = len(LAYER_NAMES)

REQUIRED_INPUT_COLUMNS = [
    "context_date",
    "available_layer_count",
    "macro_available",
    "sentiment_available",
    "technical_available",
    "point_in_time_safe",
    "research_only",
    "decision_engine_ready",
    "trading_signal_generated",
    "forecast_generated",
    "unified_decision_generated",
]


TRUE_VALUES = {
    "true",
    "1",
    "yes",
    "y",
    "pass",
    "passed",
}

FALSE_VALUES = {
    "false",
    "0",
    "no",
    "n",
    "fail",
    "failed",
}


# ============================================================
# ARGUMENTS
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "US500 Macro Intelligence — "
            "Decision Engine V1"
        )
    )

    parser.add_argument(
        "--artifacts-dir",
        default="artifacts",
        help="Directory containing Research Context artifact.",
    )

    parser.add_argument(
        "--output",
        default="decision_engine_research_v1.csv",
        help="Decision Engine output CSV.",
    )

    parser.add_argument(
        "--summary-output",
        default="decision_engine_summary_v1.csv",
        help="Decision Engine summary CSV.",
    )

    return parser.parse_args()


# ============================================================
# BASIC HELPERS
# ============================================================

def clean(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def parse_boolean(value: Any) -> bool | None:
    normalized = clean(value).lower()

    if normalized in TRUE_VALUES:
        return True

    if normalized in FALSE_VALUES:
        return False

    return None


def parse_integer(value: Any) -> int | None:
    try:
        return int(clean(value))
    except (TypeError, ValueError):
        return None


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    rows: List[Dict[str, Any]],
) -> None:

    if not rows:
        raise RuntimeError(
            f"Cannot write empty CSV: {path}"
        )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = list(rows[0].keys())

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)


# ============================================================
# INPUT DISCOVERY
# ============================================================

def find_research_context(
    artifacts_dir: Path,
) -> Path:

    candidates = sorted(
        artifacts_dir.rglob(INPUT_FILENAME)
    )

    if not candidates:

        raise RuntimeError(
            f"Required Research Context file not found: "
            f"{INPUT_FILENAME}\n"
            f"Search root: {artifacts_dir}"
        )

    if len(candidates) > 1:

        # Deterministic selection.
        candidates = sorted(
            candidates,
            key=lambda path: str(path),
        )

    return candidates[0]


# ============================================================
# VALIDATE INPUT CONTRACT
# ============================================================

def validate_required_columns(
    row: Dict[str, str],
) -> None:

    missing = [
        column
        for column in REQUIRED_INPUT_COLUMNS
        if column not in row
    ]

    if missing:

        raise RuntimeError(
            "Research Context input is missing required "
            "architecture fields:\n"
            + "\n".join(
                f"  - {column}"
                for column in missing
            )
        )


def validate_control_flags(
    row: Dict[str, str],
) -> None:

    required_true = [
        "point_in_time_safe",
        "research_only",
    ]

    required_false = [
        "decision_engine_ready",
        "trading_signal_generated",
        "forecast_generated",
        "unified_decision_generated",
    ]

    for field in required_true:

        value = parse_boolean(row.get(field))

        if value is not True:

            raise RuntimeError(
                f"Architecture violation: "
                f"{field} must be TRUE."
            )

    for field in required_false:

        value = parse_boolean(row.get(field))

        if value is not False:

            raise RuntimeError(
                f"Architecture violation: "
                f"{field} must be FALSE."
            )


def validate_layer_count(
    row: Dict[str, str],
) -> int:

    declared = parse_integer(
        row.get("available_layer_count")
    )

    if declared is None:

        raise RuntimeError(
            "available_layer_count is not a valid integer."
        )

    actual = 0

    for layer in LAYER_NAMES:

        available = parse_boolean(
            row.get(f"{layer}_available")
        )

        if available is None:

            raise RuntimeError(
                f"{layer}_available must be "
                f"TRUE or FALSE."
            )

        if available:
            actual += 1

    if declared != actual:

        raise RuntimeError(
            "Layer-count mismatch: "
            f"declared={declared}, "
            f"actual={actual}"
        )

    if declared < 0 or declared > TOTAL_LAYER_COUNT:

        raise RuntimeError(
            "available_layer_count is outside "
            "the valid range."
        )

    return actual


# ============================================================
# CONTEXT CLASSIFICATION
# ============================================================

def completeness_status(
    available_count: int,
) -> str:

    if available_count == TOTAL_LAYER_COUNT:
        return "COMPLETE"

    if available_count >= 1:
        return "PARTIAL"

    return "INSUFFICIENT"


def context_state(
    completeness: str,
) -> str:

    mapping = {
        "COMPLETE": "COMPLETE_CONTEXT",
        "PARTIAL": "PARTIAL_CONTEXT",
        "INSUFFICIENT": "INSUFFICIENT_CONTEXT",
    }

    return mapping[completeness]


# ============================================================
# PROVENANCE
# ============================================================

def source_snapshot_id(
    row: Dict[str, str],
) -> str:

    canonical = json.dumps(
        row,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def record_id(
    record: Dict[str, Any],
) -> str:

    deterministic = {
        key: value
        for key, value in record.items()
        if key not in {
            "retrieval_timestamp_utc",
            "record_id",
        }
    }

    canonical = json.dumps(
        deterministic,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()[:16]


# ============================================================
# DATE / AGE
# ============================================================

def calculate_age_days(
    asof_date: str,
    availability_date: str,
) -> str:

    if not asof_date:
        return ""

    if not availability_date:
        return ""

    try:

        from datetime import date

        asof = date.fromisoformat(
            asof_date[:10]
        )

        available = date.fromisoformat(
            availability_date[:10]
        )

        return str(
            (asof - available).days
        )

    except ValueError:

        return ""


# ============================================================
# LAYER FIELD HELPERS
# ============================================================

def layer_observation_date(
    row: Dict[str, str],
    layer: str,
) -> str:

    candidates = [
        f"{layer}_observation_date",
        f"{layer}_context_date",
        f"{layer}_asof_date",
    ]

    for field in candidates:

        value = clean(
            row.get(field)
        )

        if value:
            return value

    return ""


def layer_availability_date(
    row: Dict[str, str],
    layer: str,
) -> str:

    candidates = [
        f"{layer}_availability_date",
        f"{layer}_available_date",
    ]

    for field in candidates:

        value = clean(
            row.get(field)
        )

        if value:
            return value

    return ""


def layer_source(
    row: Dict[str, str],
    layer: str,
) -> str:

    value = clean(
        row.get(f"{layer}_source")
    )

    if value:
        return value

    return "research-context-v1"


def layer_source_url(
    row: Dict[str, str],
    layer: str,
) -> str:

    return clean(
        row.get(
            f"{layer}_source_url"
        )
    )


# ============================================================
# BUILD CANONICAL RECORD
# ============================================================

def build_record(
    row: Dict[str, str],
    source_file: Path,
) -> Dict[str, Any]:

    validate_required_columns(row)
    validate_control_flags(row)

    context_date = clean(
        row.get("context_date")
    )

    if not context_date:

        raise RuntimeError(
            "context_date cannot be empty."
        )

    available_count = validate_layer_count(row)

    completeness = completeness_status(
        available_count
    )

    state = context_state(
        completeness
    )

    snapshot = source_snapshot_id(row)

    record: Dict[str, Any] = {

        # ----------------------------------------------------
        # Canonical dates
        # ----------------------------------------------------

        "context_date": context_date,

        "asof_date": context_date,

        # ----------------------------------------------------
        # Layer architecture
        # ----------------------------------------------------

        "available_layer_count":
            available_count,

        "total_layer_count":
            TOTAL_LAYER_COUNT,

        "completeness_status":
            completeness,

        "context_state":
            state,

        # ----------------------------------------------------
        # Frozen control flags
        # ----------------------------------------------------

        "point_in_time_safe":
            "TRUE",

        "research_only":
            "TRUE",

        "decision_engine_ready":
            "FALSE",

        "trading_signal_generated":
            "FALSE",

        "forecast_generated":
            "FALSE",

        "unified_decision_generated":
            "FALSE",

        # ----------------------------------------------------
        # Architecture / provenance
        # ----------------------------------------------------

        "architecture_version":
            ARCHITECTURE_VERSION,

        "methodology_version":
            METHODOLOGY_VERSION,

        "source_snapshot_id":
            snapshot,

        "source_file":
            source_file.name,

        # ----------------------------------------------------
        # Macro
        # ----------------------------------------------------

        "macro_available":
            "TRUE"
            if parse_boolean(
                row.get("macro_available")
            )
            else "FALSE",

        "macro_observation_date":
            layer_observation_date(
                row,
                "macro",
            ),

        "macro_availability_date":
            layer_availability_date(
                row,
                "macro",
            ),

        "macro_age":
            calculate_age_days(
                context_date,
                layer_availability_date(
                    row,
                    "macro",
                ),
            ),

        "macro_source":
            layer_source(
                row,
                "macro",
            ),

        "macro_source_url":
            layer_source_url(
                row,
                "macro",
            ),

        "macro_point_in_time_safe":
            "TRUE",

        # ----------------------------------------------------
        # Sentiment
        # ----------------------------------------------------

        "sentiment_available":
            "TRUE"
            if parse_boolean(
                row.get("sentiment_available")
            )
            else "FALSE",

        "sentiment_observation_date":
            layer_observation_date(
                row,
                "sentiment",
            ),

        "sentiment_availability_date":
            layer_availability_date(
                row,
                "sentiment",
            ),

        "sentiment_age":
            calculate_age_days(
                context_date,
                layer_availability_date(
                    row,
                    "sentiment",
                ),
            ),

        "sentiment_source":
            layer_source(
                row,
                "sentiment",
            ),

        "sentiment_source_url":
            layer_source_url(
                row,
                "sentiment",
            ),

        "sentiment_point_in_time_safe":
            "TRUE",

        # ----------------------------------------------------
        # Technical
        # ----------------------------------------------------

        "technical_available":
            "TRUE"
            if parse_boolean(
                row.get("technical_available")
            )
            else "FALSE",

        "technical_observation_date":
            layer_observation_date(
                row,
                "technical",
            ),

        "technical_availability_date":
            layer_availability_date(
                row,
                "technical",
            ),

        "technical_age":
            calculate_age_days(
                context_date,
                layer_availability_date(
                    row,
                    "technical",
                ),
            ),

        "technical_source":
            layer_source(
                row,
                "technical",
            ),

        "technical_source_url":
            layer_source_url(
                row,
                "technical",
            ),

        "technical_point_in_time_safe":
            "TRUE",

        # ----------------------------------------------------
        # Existing descriptive context
        #
        # These fields are copied for research traceability.
        # They are NEVER converted into directional scoring.
        # ----------------------------------------------------

        "economic_regime":
            clean(row.get("economic_regime")),

        "fed_score":
            clean(row.get("fed_score")),

        "financial_stress_regime":
            clean(
                row.get(
                    "financial_stress_regime"
                )
            ),

        "sentiment_regime":
            clean(
                row.get("sentiment_regime")
            ),

        "technical_regime":
            clean(
                row.get("technical_regime")
            ),

        "trend_structure":
            clean(
                row.get("trend_structure")
            ),

        # ----------------------------------------------------
        # Runtime provenance
        # ----------------------------------------------------

        "retrieval_timestamp_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),
    }

    record["record_id"] = record_id(
        record
    )

    return record


# ============================================================
# SUMMARY
# ============================================================

def build_summary(
    record: Dict[str, Any],
) -> Dict[str, Any]:

    return {

        "context_date":
            record["context_date"],

        "asof_date":
            record["asof_date"],

        "available_layer_count":
            record["available_layer_count"],

        "total_layer_count":
            record["total_layer_count"],

        "completeness_status":
            record["completeness_status"],

        "context_state":
            record["context_state"],

        "point_in_time_safe":
            record["point_in_time_safe"],

        "research_only":
            record["research_only"],

        "decision_engine_ready":
            record["decision_engine_ready"],

        "trading_signal_generated":
            record["trading_signal_generated"],

        "forecast_generated":
            record["forecast_generated"],

        "unified_decision_generated":
            record["unified_decision_generated"],

        "architecture_version":
            record["architecture_version"],

        "source_snapshot_id":
            record["source_snapshot_id"],

        "record_id":
            record["record_id"],
    }


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    args = parse_args()

    artifacts_dir = Path(
        args.artifacts_dir
    )

    source_file = find_research_context(
        artifacts_dir
    )

    rows = read_csv(
        source_file
    )

    if not rows:

        raise RuntimeError(
            "Research Context summary is empty."
        )

    if len(rows) != 1:

        raise RuntimeError(
            "Decision Engine V1 requires exactly "
            "one canonical Research Context summary row. "
            f"Found {len(rows)} rows."
        )

    record = build_record(
        rows[0],
        source_file,
    )

    summary = build_summary(
        record
    )

    write_csv(
        Path(args.output),
        [record],
    )

    write_csv(
        Path(args.summary_output),
        [summary],
    )

    print()
    print("=" * 70)
    print(
        "US500 MACRO INTELLIGENCE"
    )
    print(
        "DECISION ENGINE V1"
    )
    print(
        "CONTRACT-FIRST / RESEARCH-ONLY"
    )
    print("=" * 70)

    print(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        )
    )

    print()
    print(
        "Decision Engine output is DESCRIPTIVE ONLY."
    )
    print(
        "No trading signal generated."
    )
    print(
        "No forecast generated."
    )
    print(
        "No execution generated."
    )

    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
