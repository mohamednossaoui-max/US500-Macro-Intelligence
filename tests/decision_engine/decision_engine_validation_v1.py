#!/usr/bin/env python3

"""
US500 MACRO INTELLIGENCE
DECISION ENGINE V1
CONTRACT-FIRST VALIDATOR

Research-only / No Trading / No Forecasting

Purpose:
- Validate the canonical Decision Engine V1 output.
- Validate the frozen architecture contract.
- Validate PIT safety fields.
- Validate layer availability and completeness.
- Validate provenance.
- Validate research-only invariants.
- Reject executable trading semantics.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


# ============================================================
# CONTRACT
# ============================================================

ARCHITECTURE_VERSION = "1.0"
METHODOLOGY_VERSION = "DECISION_ENGINE_V1_CONTRACT_FIRST"

TOTAL_LAYER_COUNT = 3

LAYER_NAMES = (
    "macro",
    "sentiment",
    "technical",
)


REQUIRED_COLUMNS = [
    "context_date",
    "asof_date",
    "available_layer_count",
    "total_layer_count",
    "completeness_status",
    "context_state",
    "point_in_time_safe",
    "research_only",
    "decision_engine_ready",
    "trading_signal_generated",
    "forecast_generated",
    "unified_decision_generated",
    "architecture_version",
    "methodology_version",
    "source_snapshot_id",
    "source_file",
    "record_id",
]


REQUIRED_LAYER_COLUMNS = []

for _layer in LAYER_NAMES:
    REQUIRED_LAYER_COLUMNS.extend(
        [
            f"{_layer}_available",
            f"{_layer}_observation_date",
            f"{_layer}_availability_date",
            f"{_layer}_age",
            f"{_layer}_source",
            f"{_layer}_source_url",
            f"{_layer}_point_in_time_safe",
        ]
    )


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


FORBIDDEN_TOKENS = {
    "BUY",
    "SELL",
    "OPEN_LONG",
    "OPEN_SHORT",
    "CLOSE_LONG",
    "CLOSE_SHORT",
    "LONG_ENTRY",
    "SHORT_ENTRY",
    "TRADE_ENTRY",
    "TRADE_EXIT",
    "PREDICTED_PRICE",
    "PREDICTED_RETURN",
    "EXPECTED_RETURN",
    "PROBABILITY_OF_RISE",
    "PROBABILITY_OF_FALL",
    "PRICE_TARGET",
    "TRADE_TARGET",
}


# ============================================================
# ARGUMENTS
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "US500 Macro Intelligence — "
            "Decision Engine V1 Contract-First Validator"
        )
    )

    parser.add_argument(
        "--input",
        default="decision_engine_research_v1.csv",
        help="Decision Engine output CSV.",
    )

    parser.add_argument(
        "--output",
        default="decision_engine_validation_v1.csv",
        help="Validation checks CSV.",
    )

    parser.add_argument(
        "--summary-output",
        "--summary",
        dest="summary_output",
        default="decision_engine_validation_v1_summary.csv",
        help="Validation summary CSV.",
    )

    parser.add_argument(
        "--events-output",
        "--events",
        dest="events_output",
        default="decision_engine_validation_v1_events.csv",
        help="Validation events CSV.",
    )

    return parser.parse_args()


# ============================================================
# HELPERS
# ============================================================

def clean(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def parse_bool(value: Any) -> bool | None:
    value = clean(value).lower()

    if value in TRUE_VALUES:
        return True

    if value in FALSE_VALUES:
        return False

    return None


def parse_int(value: Any) -> int | None:
    try:
        return int(clean(value))
    except (TypeError, ValueError):
        return None


def parse_date(value: Any) -> str | None:
    value = clean(value)

    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value[:10]
        ).date().isoformat()

    except ValueError:
        return None


def check(
    check_id: str,
    status: str,
    detail: str,
) -> Dict[str, str]:

    return {
        "check_id": check_id,
        "status": status,
        "detail": detail,
    }


def contains_forbidden_token(
    row: Dict[str, str],
) -> str | None:

    for value in row.values():

        text = clean(value).upper()

        for token in FORBIDDEN_TOKENS:

            if re.search(
                rf"(?<![A-Z0-9_]){re.escape(token)}(?![A-Z0-9_])",
                text,
            ):
                return token

    return None


# ============================================================
# RECORD ID RECONSTRUCTION
# ============================================================

def calculate_record_id(
    row: Dict[str, str],
) -> str:

    deterministic = {
        key: value
        for key, value in row.items()
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
# INPUT
# ============================================================

def load_rows(
    path: Path,
) -> List[Dict[str, str]]:

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        return list(
            csv.DictReader(handle)
        )


# ============================================================
# MAIN VALIDATION
# ============================================================

def main() -> int:

    args = parse_args()

    checks: List[Dict[str, str]] = []

    input_path = Path(args.input)

    # --------------------------------------------------------
    # 1. INPUT EXISTS
    # --------------------------------------------------------

    exists = input_path.is_file()

    checks.append(
        check(
            "INPUT_EXISTS",
            "PASS" if exists else "FAIL",
            str(input_path),
        )
    )

    if not exists:

        rows: List[Dict[str, str]] = []

    else:

        try:

            rows = load_rows(
                input_path
            )

        except Exception as exc:

            rows = []

            checks.append(
                check(
                    "INPUT_READABLE",
                    "FAIL",
                    str(exc),
                )
            )

    # --------------------------------------------------------
    # 2. NON EMPTY
    # --------------------------------------------------------

    checks.append(
        check(
            "NON_EMPTY",
            "PASS" if rows else "FAIL",
            f"rows={len(rows)}",
        )
    )

    if not rows:

        return write_results(
            args,
            checks,
        )

    # --------------------------------------------------------
    # 3. EXACTLY ONE RECORD
    # --------------------------------------------------------

    checks.append(
        check(
            "SINGLE_CANONICAL_RECORD",
            "PASS" if len(rows) == 1 else "FAIL",
            f"rows={len(rows)}",
        )
    )

    row = rows[0]

    # --------------------------------------------------------
    # 4. REQUIRED SCHEMA
    # --------------------------------------------------------

    fields = list(row.keys())

    required = (
        REQUIRED_COLUMNS
        + REQUIRED_LAYER_COLUMNS
    )

    missing = [
        column
        for column in required
        if column not in fields
    ]

    checks.append(
        check(
            "REQUIRED_COLUMNS",
            "PASS" if not missing else "FAIL",
            (
                "All Contract-First columns present."
                if not missing
                else "Missing: " + ", ".join(missing)
            ),
        )
    )

    # --------------------------------------------------------
    # 5. ARCHITECTURE VERSION
    # --------------------------------------------------------

    checks.append(
        check(
            "ARCHITECTURE_VERSION",
            (
                "PASS"
                if clean(
                    row.get("architecture_version")
                ) == ARCHITECTURE_VERSION
                else "FAIL"
            ),
            clean(
                row.get("architecture_version")
            ),
        )
    )

    # --------------------------------------------------------
    # 6. METHODOLOGY VERSION
    # --------------------------------------------------------

    checks.append(
        check(
            "METHODOLOGY_VERSION",
            (
                "PASS"
                if clean(
                    row.get("methodology_version")
                ) == METHODOLOGY_VERSION
                else "FAIL"
            ),
            clean(
                row.get("methodology_version")
            ),
        )
    )

    # --------------------------------------------------------
    # 7. CONTEXT / ASOF DATE
    # --------------------------------------------------------

    context_date = parse_date(
        row.get("context_date")
    )

    asof_date = parse_date(
        row.get("asof_date")
    )

    checks.append(
        check(
            "CONTEXT_DATE_VALID",
            "PASS" if context_date else "FAIL",
            clean(row.get("context_date")),
        )
    )

    checks.append(
        check(
            "ASOF_DATE_VALID",
            "PASS" if asof_date else "FAIL",
            clean(row.get("asof_date")),
        )
    )

    checks.append(
        check(
            "CONTEXT_ASOF_ALIGNMENT",
            (
                "PASS"
                if context_date
                and asof_date
                and context_date == asof_date
                else "FAIL"
            ),
            (
                f"context_date={context_date}; "
                f"asof_date={asof_date}"
            ),
        )
    )

    # --------------------------------------------------------
    # 8. LAYER COUNTS
    # --------------------------------------------------------

    declared_count = parse_int(
        row.get("available_layer_count")
    )

    total_count = parse_int(
        row.get("total_layer_count")
    )

    actual_count = 0

    layer_errors = []

    for layer in LAYER_NAMES:

        value = parse_bool(
            row.get(
                f"{layer}_available"
            )
        )

        if value is None:

            layer_errors.append(
                f"{layer}_available invalid"
            )

        elif value:

            actual_count += 1

    checks.append(
        check(
            "TOTAL_LAYER_COUNT",
            (
                "PASS"
                if total_count == TOTAL_LAYER_COUNT
                else "FAIL"
            ),
            (
                f"declared_total={total_count}; "
                f"expected={TOTAL_LAYER_COUNT}"
            ),
        )
    )

    checks.append(
        check(
            "AVAILABLE_LAYER_COUNT",
            (
                "PASS"
                if declared_count is not None
                and 0 <= declared_count <= TOTAL_LAYER_COUNT
                and not layer_errors
                and declared_count == actual_count
                else "FAIL"
            ),
            (
                f"declared={declared_count}; "
                f"actual={actual_count}; "
                f"errors={layer_errors}"
            ),
        )
    )

    # --------------------------------------------------------
    # 9. COMPLETENESS
    # --------------------------------------------------------

    expected_completeness = None

    if declared_count == TOTAL_LAYER_COUNT:

        expected_completeness = "COMPLETE"

    elif declared_count is not None and declared_count >= 1:

        expected_completeness = "PARTIAL"

    elif declared_count == 0:

        expected_completeness = "INSUFFICIENT"

    checks.append(
        check(
            "COMPLETENESS_STATUS",
            (
                "PASS"
                if expected_completeness
                and clean(
                    row.get("completeness_status")
                ) == expected_completeness
                else "FAIL"
            ),
            (
                f"actual={row.get('completeness_status')}; "
                f"expected={expected_completeness}"
            ),
        )
    )

    expected_state = {
        "COMPLETE": "COMPLETE_CONTEXT",
        "PARTIAL": "PARTIAL_CONTEXT",
        "INSUFFICIENT": "INSUFFICIENT_CONTEXT",
    }.get(
        expected_completeness
    )

    checks.append(
        check(
            "CONTEXT_STATE",
            (
                "PASS"
                if expected_state
                and clean(
                    row.get("context_state")
                ) == expected_state
                else "FAIL"
            ),
            (
                f"actual={row.get('context_state')}; "
                f"expected={expected_state}"
            ),
        )
    )

    # --------------------------------------------------------
    # 10. FROZEN RESEARCH-ONLY FLAGS
    # --------------------------------------------------------

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

        value = parse_bool(
            row.get(field)
        )

        checks.append(
            check(
                f"FLAG_TRUE_{field.upper()}",
                "PASS" if value is True else "FAIL",
                clean(row.get(field)),
            )
        )

    for field in required_false:

        value = parse_bool(
            row.get(field)
        )

        checks.append(
            check(
                f"FLAG_FALSE_{field.upper()}",
                "PASS" if value is False else "FAIL",
                clean(row.get(field)),
            )
        )

    # --------------------------------------------------------
    # 11. LAYER PIT FLAGS
    # --------------------------------------------------------

    for layer in LAYER_NAMES:

        field = f"{layer}_point_in_time_safe"

        value = parse_bool(
            row.get(field)
        )

        checks.append(
            check(
                f"PIT_FLAG_{layer.upper()}",
                "PASS" if value is True else "FAIL",
                clean(row.get(field)),
            )
        )

    # --------------------------------------------------------
    # 12. PIT DATE RELATIONSHIP
    #
    # Empty availability dates are accepted here because the
    # current Research Context artifact does not expose them.
    # The engine still explicitly carries point_in_time_safe=TRUE.
    # If dates exist, they must not be after asof_date.
    # --------------------------------------------------------

    if asof_date:

        for layer in LAYER_NAMES:

            availability = parse_date(
                row.get(
                    f"{layer}_availability_date"
                )
            )

            if availability is None:

                checks.append(
                    check(
                        f"PIT_DATE_{layer.upper()}",
                        "REVIEW",
                        (
                            "availability_date is empty; "
                            "layer explicitly declares "
                            "point_in_time_safe=TRUE"
                        ),
                    )
                )

            else:

                checks.append(
                    check(
                        f"PIT_DATE_{layer.upper()}",
                        (
                            "PASS"
                            if availability <= asof_date
                            else "FAIL"
                        ),
                        (
                            f"availability={availability}; "
                            f"asof={asof_date}"
                        ),
                    )
                )

    # --------------------------------------------------------
    # 13. LAYER SOURCES
    # --------------------------------------------------------

    for layer in LAYER_NAMES:

        source = clean(
            row.get(
                f"{layer}_source"
            )
        )

        checks.append(
            check(
                f"SOURCE_{layer.upper()}",
                "PASS" if source else "FAIL",
                source,
            )
        )

    # --------------------------------------------------------
    # 14. SOURCE FILE
    # --------------------------------------------------------

    checks.append(
        check(
            "SOURCE_FILE",
            (
                "PASS"
                if clean(
                    row.get("source_file")
                )
                else "FAIL"
            ),
            clean(
                row.get("source_file")
            ),
        )
    )

    # --------------------------------------------------------
    # 15. SOURCE SNAPSHOT
    # --------------------------------------------------------

    snapshot = clean(
        row.get("source_snapshot_id")
    )

    snapshot_valid = bool(
        re.fullmatch(
            r"[0-9a-fA-F]{64}",
            snapshot,
        )
    )

    checks.append(
        check(
            "SOURCE_SNAPSHOT_ID",
            "PASS" if snapshot_valid else "FAIL",
            snapshot,
        )
    )

    # --------------------------------------------------------
    # 16. RECORD ID
    # --------------------------------------------------------

    supplied_record_id = clean(
        row.get("record_id")
    )

    expected_record_id = calculate_record_id(
        row
    )

    checks.append(
        check(
            "RECORD_ID",
            (
                "PASS"
                if supplied_record_id
                and supplied_record_id == expected_record_id
                else "FAIL"
            ),
            (
                f"supplied={supplied_record_id}; "
                f"expected={expected_record_id}"
            ),
        )
    )

    # --------------------------------------------------------
    # 17. FORBIDDEN TRADING SEMANTICS
    # --------------------------------------------------------

    forbidden = contains_forbidden_token(
        row
    )

    checks.append(
        check(
            "NO_EXECUTABLE_TRADING_SEMANTICS",
            "FAIL" if forbidden else "PASS",
            (
                f"forbidden_token={forbidden}"
                if forbidden
                else "No executable trading token detected."
            ),
        )
    )

    # --------------------------------------------------------
    # 18. NO DIRECTIONAL DECISION FIELD
    # --------------------------------------------------------

    prohibited_fields = {
        "decision",
        "decision_state",
        "decision_confidence",
        "trade_signal",
        "signal",
        "price_target",
        "predicted_price",
        "expected_return",
    }

    present_prohibited = sorted(
        prohibited_fields.intersection(
            set(row.keys())
        )
    )

    checks.append(
        check(
            "NO_DIRECTIONAL_DECISION_FIELDS",
            (
                "PASS"
                if not present_prohibited
                else "FAIL"
            ),
            (
                "No prohibited decision fields."
                if not present_prohibited
                else "Present: "
                + ", ".join(present_prohibited)
            ),
        )
    )

    # --------------------------------------------------------
    # 19. DETERMINISTIC OUTPUT
    # --------------------------------------------------------

    checks.append(
        check(
            "DETERMINISTIC_RECORD",
            (
                "PASS"
                if supplied_record_id == expected_record_id
                else "FAIL"
            ),
            "record_id reproducibility check",
        )
    )

    # --------------------------------------------------------
    # WRITE RESULTS
    # --------------------------------------------------------

    return write_results(
        args,
        checks,
    )


# ============================================================
# WRITE RESULTS
# ============================================================

def write_results(
    args: argparse.Namespace,
    checks: List[Dict[str, str]],
) -> int:

    output_path = Path(
        args.output
    )

    summary_path = Path(
        args.summary_output
    )

    events_path = Path(
        args.events_output
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    events_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Validation results
    # --------------------------------------------------------

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "check_id",
                "status",
                "detail",
            ],
        )

        writer.writeheader()
        writer.writerows(checks)

    # --------------------------------------------------------
    # Events = REVIEW + FAIL
    # --------------------------------------------------------

    events = [
        item
        for item in checks
        if item["status"] != "PASS"
    ]

    with events_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "check_id",
                "status",
                "detail",
            ],
        )

        writer.writeheader()
        writer.writerows(events)

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    passed = sum(
        item["status"] == "PASS"
        for item in checks
    )

    review = sum(
        item["status"] == "REVIEW"
        for item in checks
    )

    failed = sum(
        item["status"] == "FAIL"
        for item in checks
    )

    status = (
        "PASSED"
        if failed == 0
        else "FAILED"
    )

    summary = {
        "run_timestamp_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "total_checks":
            len(checks),

        "pass":
            passed,

        "review":
            review,

        "fail":
            failed,

        "status":
            status,

        "research_only":
            "TRUE",

        "architecture_version":
            ARCHITECTURE_VERSION,

        "methodology_version":
            METHODOLOGY_VERSION,
    }

    with summary_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=list(
                summary.keys()
            ),
        )

        writer.writeheader()
        writer.writerow(summary)

    # --------------------------------------------------------
    # Console
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "US500 MACRO INTELLIGENCE"
    )
    print(
        "DECISION ENGINE V1 VALIDATION"
    )
    print(
        "CONTRACT-FIRST / RESEARCH-ONLY"
    )
    print("=" * 70)

    print(
        f"PASS={passed} "
        f"REVIEW={review} "
        f"FAIL={failed}"
    )

    print(
        f"STATUS={status}"
    )

    print(
        "Research-only = TRUE"
    )

    print(
        "Trading signal generated = FALSE"
    )

    print(
        "Forecast generated = FALSE"
    )

    print(
        "Unified decision generated = FALSE"
    )

    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
