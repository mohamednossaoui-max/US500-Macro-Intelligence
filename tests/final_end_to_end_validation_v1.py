#!/usr/bin/env python3

"""
US500 MACRO INTELLIGENCE
FINAL END-TO-END VALIDATION V1

Purpose
-------
Final validation of the frozen research architecture before Decision Engine.

This validator:
- validates available research artifacts
- checks schema integrity
- checks point-in-time safety
- checks availability-date logic
- checks research-only invariants
- checks provenance / record identity where available
- checks canonical Research Context
- checks architecture contract
- checks cross-layer consistency
- checks duplicate records
- checks deterministic structure
- explicitly protects against trade execution / forecasting boundaries

Important
---------
Research-only.
No trade signals.
No execution.
No market forecasting.
No Decision Engine integration.
No modification of existing Intelligence modules.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


VERSION = "FINAL_E2E_VALIDATION_V1"

REQUIRED_LAYERS = [
    "Economic Intelligence",
    "Fed Intelligence",
    "Financial Stress",
    "COT Positioning",
    "AAII Sentiment",
    "VIX Sentiment",
    "Unified Sentiment",
    "Technical Intelligence",
    "Market Breadth",
    "Cross-Asset Intelligence",
    "Event / News Intelligence",
    "Earnings Intelligence",
    "Macro Context",
    "Research Context",
]

ARCHITECTURE_FILE = "FINAL_UNIFIED_DECISION_ARCHITECTURE_V1.md"

CONTROL_TRUE = {
    "true",
    "1",
    "yes",
    "y",
    "pass",
}

CONTROL_FALSE = {
    "false",
    "0",
    "no",
    "n",
    "fail",
}

FORBIDDEN_EXECUTION_COLUMNS = {
    "order_id",
    "broker_order_id",
    "execution_id",
    "execution_status",
    "broker_execution",
    "trade_execution",
    "live_order",
    "place_order",
    "submit_order",
}

FORBIDDEN_FORECAST_COLUMNS = {
    "predicted_price",
    "forecast_price",
    "predicted_return",
    "forecast_return",
    "prediction",
    "forecast_value",
}

# These are intentionally NOT forbidden:
# forward_return, future_return, mfe, mae, horizon_return, etc.
# Historical Event Study / Earnings Intelligence legitimately use them
# as realized historical outcomes.


@dataclass
class CheckResult:
    check_id: str
    category: str
    layer: str
    status: str
    severity: str
    message: str
    evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def add_check(
    results: List[CheckResult],
    check_id: str,
    category: str,
    layer: str,
    status: str,
    severity: str,
    message: str,
    evidence: str = "",
) -> None:
    results.append(
        CheckResult(
            check_id=check_id,
            category=category,
            layer=layer,
            status=status,
            severity=severity,
            message=message,
            evidence=evidence,
        )
    )


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def bool_series(series: pd.Series) -> Optional[pd.Series]:
    values = series.astype(str).str.strip().str.lower()

    unknown = ~values.isin(CONTROL_TRUE | CONTROL_FALSE)
    if unknown.any():
        return None

    return values.isin(CONTROL_TRUE)


def discover_csv_files(root: Path) -> List[Path]:
    return sorted(
        p for p in root.rglob("*.csv")
        if p.is_file()
    )


def discover_json_files(root: Path) -> List[Path]:
    return sorted(
        p for p in root.rglob("*.json")
        if p.is_file()
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def read_csv_safe(path: Path) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    try:
        df = pd.read_csv(path, low_memory=False)
        return df, None
    except Exception as exc:
        return None, str(exc)


def detect_layer(path: Path) -> str:
    text = normalize_name(str(path))

    rules = [
        ("Economic Intelligence", ["economic", "inflation", "labor", "growth", "pmi"]),
        ("Fed Intelligence", ["fed-intelligence", "fed_intelligence", "fomc", "sep", "fed"]),
        ("Financial Stress", ["financial-stress", "financial_stress"]),
        ("COT Positioning", ["cot-positioning", "cot_positioning"]),
        ("AAII Sentiment", ["aaii-sentiment", "aaii_sentiment", "aaii"]),
        ("VIX Sentiment", ["vix-sentiment", "vix_sentiment"]),
        ("Unified Sentiment", ["sentiment-engine", "sentiment_engine", "unified-sentiment"]),
        ("Technical Intelligence", ["technical-intelligence", "technical_intelligence"]),
        ("Market Breadth", ["market-breadth", "market_breadth", "breadth"]),
        ("Cross-Asset Intelligence", ["cross-asset", "cross_asset"]),
        ("Event / News Intelligence", ["event-news", "event_news"]),
        ("Earnings Intelligence", ["earnings"]),
        ("Macro Context", ["macro-context", "macro_context"]),
        ("Research Context", ["research-context", "research_context"]),
    ]

    for layer, patterns in rules:
        if any(pattern in text for pattern in patterns):
            return layer

    return "Unclassified"


def date_column_candidates(df: pd.DataFrame) -> List[str]:
    preferred = [
        "context_date",
        "asof_date",
        "observation_date",
        "date",
        "event_date",
        "reported_date",
        "source_date",
    ]

    found = [c for c in preferred if c in df.columns]

    if found:
        return found

    return [
        c for c in df.columns
        if c.lower().endswith("_date")
        and "availability" not in c.lower()
    ]


def availability_columns(df: pd.DataFrame) -> List[str]:
    return [
        c for c in df.columns
        if "availability_date" in c.lower()
    ]


def parse_dates(
    df: pd.DataFrame,
    column: str,
) -> pd.Series:
    return pd.to_datetime(
        df[column],
        errors="coerce",
        utc=True,
    )


def validate_basic_dataframe(
    path: Path,
    df: pd.DataFrame,
    results: List[CheckResult],
) -> None:
    layer = detect_layer(path)
    name = path.name

    if df.empty:
        add_check(
            results,
            "DATA_NONEMPTY",
            "Data Integrity",
            layer,
            "FAIL",
            "ERROR",
            f"{name} contains zero data rows.",
        )
        return

    add_check(
        results,
        "DATA_NONEMPTY",
        "Data Integrity",
        layer,
        "PASS",
        "INFO",
        f"{name} contains {len(df):,} data rows.",
    )

    if len(df.columns) == 0:
        add_check(
            results,
            "SCHEMA_COLUMNS",
            "Schema",
            layer,
            "FAIL",
            "ERROR",
            f"{name} contains no columns.",
        )
    else:
        add_check(
            results,
            "SCHEMA_COLUMNS",
            "Schema",
            layer,
            "PASS",
            "INFO",
            f"{name} contains {len(df.columns)} columns.",
        )

    duplicate_rows = int(df.duplicated().sum())

    if duplicate_rows:
        add_check(
            results,
            "DUPLICATE_ROWS",
            "Data Integrity",
            layer,
            "FAIL",
            "ERROR",
            f"{name} contains {duplicate_rows} completely duplicated rows.",
        )
    else:
        add_check(
            results,
            "DUPLICATE_ROWS",
            "Data Integrity",
            layer,
            "PASS",
            "INFO",
            f"{name} contains no completely duplicated rows.",
        )

    date_candidates = date_column_candidates(df)

    if date_candidates:
        parsed_any = False

        for column in date_candidates:
            parsed = parse_dates(df, column)
            valid = parsed.notna()

            if valid.any():
                parsed_any = True

                invalid_count = int((~valid).sum())

                if invalid_count:
                    add_check(
                        results,
                        "DATE_PARSE",
                        "Temporal Integrity",
                        layer,
                        "FAIL",
                        "ERROR",
                        f"{name}:{column} contains {invalid_count} invalid dates.",
                    )
                else:
                    add_check(
                        results,
                        "DATE_PARSE",
                        "Temporal Integrity",
                        layer,
                        "PASS",
                        "INFO",
                        f"{name}:{column} parsed successfully.",
                    )

        if not parsed_any:
            add_check(
                results,
                "DATE_PARSE",
                "Temporal Integrity",
                layer,
                "FAIL",
                "ERROR",
                f"{name} has date-like columns but none could be parsed.",
            )

    else:
        add_check(
            results,
            "DATE_COLUMN",
            "Temporal Integrity",
            layer,
            "REVIEW",
            "WARNING",
            f"{name} has no obvious canonical date column.",
        )


def validate_pit(
    path: Path,
    df: pd.DataFrame,
    results: List[CheckResult],
) -> None:
    layer = detect_layer(path)
    name = path.name

    observation_candidates = [
        c for c in [
            "observation_date",
            "asof_date",
            "context_date",
            "date",
            "event_date",
            "reported_date",
        ]
        if c in df.columns
    ]

    availability_cols = availability_columns(df)

    if "point_in_time_safe" in df.columns:
        values = bool_series(df["point_in_time_safe"])

        if values is None:
            add_check(
                results,
                "PIT_FLAG_PARSE",
                "PIT",
                layer,
                "FAIL",
                "ERROR",
                f"{name}:point_in_time_safe contains invalid boolean values.",
            )
        elif bool(values.all()):
            add_check(
                results,
                "PIT_FLAG",
                "PIT",
                layer,
                "PASS",
                "INFO",
                f"{name}:point_in_time_safe is TRUE for all rows.",
            )
        else:
            bad = int((~values).sum())
            add_check(
                results,
                "PIT_FLAG",
                "PIT",
                layer,
                "FAIL",
                "ERROR",
                f"{name}:point_in_time_safe is FALSE for {bad} rows.",
            )

    if availability_cols and observation_candidates:
        obs_col = observation_candidates[0]

        obs = parse_dates(df, obs_col)

        for avail_col in availability_cols:
            avail = parse_dates(df, avail_col)

            valid = obs.notna() & avail.notna()

            if not valid.any():
                add_check(
                    results,
                    "PIT_DATE_COMPARISON",
                    "PIT",
                    layer,
                    "REVIEW",
                    "WARNING",
                    f"{name}: insufficient valid dates for {obs_col}/{avail_col}.",
                )
                continue

            bad = int((avail[valid] < obs[valid]).sum())

            if bad:
                add_check(
                    results,
                    "PIT_DATE_COMPARISON",
                    "PIT",
                    layer,
                    "FAIL",
                    "ERROR",
                    (
                        f"{name}:{avail_col} occurs before {obs_col} "
                        f"for {bad} rows."
                    ),
                )
            else:
                add_check(
                    results,
                    "PIT_DATE_COMPARISON",
                    "PIT",
                    layer,
                    "PASS",
                    "INFO",
                    (
                        f"{name}:{avail_col} is not earlier than "
                        f"{obs_col}."
                    ),
                )

    elif availability_cols:
        add_check(
            results,
            "PIT_OBSERVATION_COLUMN",
            "PIT",
            layer,
            "REVIEW",
            "WARNING",
            (
                f"{name} contains availability dates but no obvious "
                "observation/as-of date."
            ),
        )


def validate_research_boundaries(
    path: Path,
    df: pd.DataFrame,
    results: List[CheckResult],
) -> None:
    layer = detect_layer(path)
    name = path.name

    if "research_only" in df.columns:
        values = bool_series(df["research_only"])

        if values is None or not bool(values.all()):
            add_check(
                results,
                "RESEARCH_ONLY",
                "Research Boundary",
                layer,
                "FAIL",
                "ERROR",
                f"{name}:research_only is not TRUE for every row.",
            )
        else:
            add_check(
                results,
                "RESEARCH_ONLY",
                "Research Boundary",
                layer,
                "PASS",
                "INFO",
                f"{name}:research_only is TRUE for all rows.",
            )

    if "decision_engine_ready" in df.columns:
        values = bool_series(df["decision_engine_ready"])

        if values is None:
            add_check(
                results,
                "DECISION_ENGINE_READY",
                "Research Boundary",
                layer,
                "FAIL",
                "ERROR",
                f"{name}:decision_engine_ready is invalid.",
            )
        elif bool(values.any()):
            add_check(
                results,
                "DECISION_ENGINE_READY",
                "Research Boundary",
                layer,
                "FAIL",
                "ERROR",
                f"{name}:decision_engine_ready is TRUE in some rows.",
            )
        else:
            add_check(
                results,
                "DECISION_ENGINE_READY",
                "Research Boundary",
                layer,
                "PASS",
                "INFO",
                f"{name}:decision_engine_ready is FALSE for all rows.",
            )

    for column in [
        "trading_signal_generated",
        "forecast_generated",
        "unified_decision_generated",
    ]:
        if column not in df.columns:
            continue

        values = bool_series(df[column])

        if values is None:
            add_check(
                results,
                f"BOUNDARY_{column.upper()}",
                "Research Boundary",
                layer,
                "FAIL",
                "ERROR",
                f"{name}:{column} contains invalid boolean values.",
            )
        elif bool(values.any()):
            add_check(
                results,
                f"BOUNDARY_{column.upper()}",
                "Research Boundary",
                layer,
                "FAIL",
                "ERROR",
                f"{name}:{column} is TRUE in some rows.",
            )
        else:
            add_check(
                results,
                f"BOUNDARY_{column.upper()}",
                "Research Boundary",
                layer,
                "PASS",
                "INFO",
                f"{name}:{column} is FALSE for all rows.",
            )

    forbidden_execution = [
        c for c in df.columns
        if c.lower() in FORBIDDEN_EXECUTION_COLUMNS
    ]

    if forbidden_execution:
        add_check(
            results,
            "NO_EXECUTION_FIELDS",
            "Research Boundary",
            layer,
            "FAIL",
            "ERROR",
            (
                f"{name} contains explicit execution fields: "
                f"{', '.join(forbidden_execution)}."
            ),
        )
    else:
        add_check(
            results,
            "NO_EXECUTION_FIELDS",
            "Research Boundary",
            layer,
            "PASS",
            "INFO",
            f"{name} contains no explicit execution fields.",
        )

    forbidden_forecast = [
        c for c in df.columns
        if c.lower() in FORBIDDEN_FORECAST_COLUMNS
    ]

    if forbidden_forecast:
        add_check(
            results,
            "NO_FORECAST_FIELDS",
            "Research Boundary",
            layer,
            "FAIL",
            "ERROR",
            (
                f"{name} contains explicit forecast fields: "
                f"{', '.join(forbidden_forecast)}."
            ),
        )
    else:
        add_check(
            results,
            "NO_FORECAST_FIELDS",
            "Research Boundary",
            layer,
            "PASS",
            "INFO",
            f"{name} contains no explicit forecast fields.",
        )


def validate_record_identity(
    path: Path,
    df: pd.DataFrame,
    results: List[CheckResult],
) -> None:
    layer = detect_layer(path)
    name = path.name

    id_candidates = [
        c for c in df.columns
        if c.lower() in {
            "record_id",
            "observation_id",
            "cross_asset_observation_id",
            "event_id",
            "earnings_event_id",
        }
    ]

    if not id_candidates:
        add_check(
            results,
            "RECORD_ID",
            "Provenance",
            layer,
            "REVIEW",
            "WARNING",
            f"{name} has no recognized record identity field.",
        )
        return

    for column in id_candidates:
        nulls = int(df[column].isna().sum())
        duplicates = int(df[column].duplicated().sum())

        if nulls:
            add_check(
                results,
                "RECORD_ID_NULL",
                "Provenance",
                layer,
                "FAIL",
                "ERROR",
                f"{name}:{column} contains {nulls} null IDs.",
            )
        elif duplicates:
            add_check(
                results,
                "RECORD_ID_DUPLICATE",
                "Provenance",
                layer,
                "FAIL",
                "ERROR",
                f"{name}:{column} contains {duplicates} duplicate IDs.",
            )
        else:
            add_check(
                results,
                "RECORD_ID",
                "Provenance",
                layer,
                "PASS",
                "INFO",
                f"{name}:{column} is non-null and unique.",
            )


def validate_final_context(
    path: Path,
    df: pd.DataFrame,
    results: List[CheckResult],
) -> None:
    layer = "Research Context"

    required = [
        "context_date",
        "available_layer_count",
        "point_in_time_safe",
        "research_only",
        "decision_engine_ready",
        "trading_signal_generated",
        "forecast_generated",
        "unified_decision_generated",
    ]

    missing = [c for c in required if c not in df.columns]

    if missing:
        add_check(
            results,
            "CANONICAL_CONTEXT_SCHEMA",
            "Unified Architecture",
            layer,
            "FAIL",
            "ERROR",
            (
                "Canonical Research Context is missing required columns: "
                + ", ".join(missing)
            ),
        )
        return

    add_check(
        results,
        "CANONICAL_CONTEXT_SCHEMA",
        "Unified Architecture",
        layer,
        "PASS",
        "INFO",
        "Canonical Research Context required control schema is present.",
    )

    dates = parse_dates(df, "context_date")

    if dates.isna().any():
        add_check(
            results,
            "CONTEXT_DATE_VALID",
            "Unified Architecture",
            layer,
            "FAIL",
            "ERROR",
            "Canonical context_date contains invalid dates.",
        )
    else:
        if not dates.is_monotonic_increasing:
            add_check(
                results,
                "CONTEXT_DATE_ORDER",
                "Unified Architecture",
                layer,
                "FAIL",
                "ERROR",
                "Canonical context_date is not monotonically increasing.",
            )
        else:
            add_check(
                results,
                "CONTEXT_DATE_ORDER",
                "Unified Architecture",
                layer,
                "PASS",
                "INFO",
                "Canonical context_date is monotonically increasing.",
            )

        duplicates = int(dates.duplicated().sum())

        if duplicates:
            add_check(
                results,
                "CONTEXT_DATE_UNIQUE",
                "Unified Architecture",
                layer,
                "FAIL",
                "ERROR",
                f"Canonical context_date has {duplicates} duplicates.",
            )
        else:
            add_check(
                results,
                "CONTEXT_DATE_UNIQUE",
                "Unified Architecture",
                layer,
                "PASS",
                "INFO",
                "Canonical context_date is unique.",
            )

    for column in [
        "point_in_time_safe",
        "research_only",
    ]:
        values = bool_series(df[column])

        if values is None or not bool(values.all()):
            add_check(
                results,
                f"CANONICAL_{column.upper()}",
                "Unified Architecture",
                layer,
                "FAIL",
                "ERROR",
                f"Canonical {column} is not TRUE for all rows.",
            )
        else:
            add_check(
                results,
                f"CANONICAL_{column.upper()}",
                "Unified Architecture",
                layer,
                "PASS",
                "INFO",
                f"Canonical {column} is TRUE for all rows.",
            )

    for column in [
        "decision_engine_ready",
        "trading_signal_generated",
        "forecast_generated",
        "unified_decision_generated",
    ]:
        values = bool_series(df[column])

        if values is None or bool(values.any()):
            add_check(
                results,
                f"CANONICAL_{column.upper()}",
                "Unified Architecture",
                layer,
                "FAIL",
                "ERROR",
                f"Canonical {column} contains TRUE/invalid values.",
            )
        else:
            add_check(
                results,
                f"CANONICAL_{column.upper()}",
                "Unified Architecture",
                layer,
                "PASS",
                "INFO",
                f"Canonical {column} is FALSE for all rows.",
            )

    if "available_layer_count" in df.columns:
        counts = pd.to_numeric(
            df["available_layer_count"],
            errors="coerce",
        )

        if counts.isna().any():
            add_check(
                results,
                "AVAILABLE_LAYER_COUNT",
                "Unified Architecture",
                layer,
                "FAIL",
                "ERROR",
                "available_layer_count contains non-numeric values.",
            )
        elif (counts < 0).any():
            add_check(
                results,
                "AVAILABLE_LAYER_COUNT",
                "Unified Architecture",
                layer,
                "FAIL",
                "ERROR",
                "available_layer_count contains negative values.",
            )
        else:
            add_check(
                results,
                "AVAILABLE_LAYER_COUNT",
                "Unified Architecture",
                layer,
                "PASS",
                "INFO",
                "available_layer_count is numerically valid.",
            )


def validate_architecture_document(
    repo_root: Path,
    results: List[CheckResult],
) -> None:
    path = repo_root / ARCHITECTURE_FILE

    if not path.exists():
        add_check(
            results,
            "ARCHITECTURE_DOCUMENT",
            "Architecture",
            "Architecture",
            "FAIL",
            "ERROR",
            f"{ARCHITECTURE_FILE} is missing.",
        )
        return

    text = path.read_text(encoding="utf-8", errors="replace")

    required_phrases = [
        "FROZEN ARCHITECTURE CONTRACT",
        "research_only",
        "point_in_time_safe",
        "decision_engine_ready",
        "trading_signal_generated",
        "forecast_generated",
        "unified_decision_generated",
        "availability_date",
        "provenance",
        "CONFLICTING_CONTEXT",
        "MIXED_CONTEXT",
        "CROSS_LAYER_DIVERGENCE",
        "Decision Engine NOT IMPLEMENTED",
        "Research-only boundary ACTIVE",
    ]

    missing = [
        phrase for phrase in required_phrases
        if phrase not in text
    ]

    if missing:
        add_check(
            results,
            "ARCHITECTURE_CONTRACT",
            "Architecture",
            "Architecture",
            "FAIL",
            "ERROR",
            "Architecture document is missing required contract elements.",
            ", ".join(missing),
        )
    else:
        add_check(
            results,
            "ARCHITECTURE_CONTRACT",
            "Architecture",
            "Architecture",
            "PASS",
            "INFO",
            "Frozen architecture contract contains all required boundary elements.",
        )


def classify_artifacts(
    csv_files: List[Path],
) -> Dict[str, List[Path]]:
    mapping: Dict[str, List[Path]] = {
        layer: [] for layer in REQUIRED_LAYERS
    }

    for path in csv_files:
        layer = detect_layer(path)

        if layer in mapping:
            mapping[layer].append(path)

    return mapping


def validate_layer_coverage(
    mapping: Dict[str, List[Path]],
    results: List[CheckResult],
) -> None:
    for layer in REQUIRED_LAYERS:
        files = mapping.get(layer, [])

        if not files:
            add_check(
                results,
                "LAYER_COVERAGE",
                "Layer Coverage",
                layer,
                "REVIEW",
                "WARNING",
                (
                    "No artifact was automatically identified for this "
                    "layer in the downloaded artifact set."
                ),
            )
        else:
            add_check(
                results,
                "LAYER_COVERAGE",
                "Layer Coverage",
                layer,
                "PASS",
                "INFO",
                (
                    f"{len(files)} artifact file(s) identified for this layer."
                ),
            )


def validate_cross_layer_context(
    csv_files: List[Path],
    results: List[CheckResult],
) -> None:
    candidates = []

    for path in csv_files:
        name = normalize_name(path.name)

        if (
            "research-context" in name
            or "research_context" in name
        ):
            candidates.append(path)

    if not candidates:
        add_check(
            results,
            "CANONICAL_CONTEXT_DISCOVERY",
            "Cross-Layer Consistency",
            "Research Context",
            "REVIEW",
            "WARNING",
            "No Research Context CSV was discovered.",
        )
        return

    selected = candidates[0]
    df, error = read_csv_safe(selected)

    if error:
        add_check(
            results,
            "CANONICAL_CONTEXT_READ",
            "Cross-Layer Consistency",
            "Research Context",
            "FAIL",
            "ERROR",
            f"Unable to read {selected.name}: {error}",
        )
        return

    if df is not None:
        validate_final_context(selected, df, results)

        layer_flags = [
            c for c in [
                "macro_available",
                "sentiment_available",
                "technical_available",
                "cross_asset_available",
            ]
            if c in df.columns
        ]

        if layer_flags:
            for column in layer_flags:
                values = bool_series(df[column])

                if values is None:
                    add_check(
                        results,
                        "CONTEXT_LAYER_FLAG",
                        "Cross-Layer Consistency",
                        "Research Context",
                        "FAIL",
                        "ERROR",
                        f"{selected.name}:{column} contains invalid booleans.",
                    )
                else:
                    add_check(
                        results,
                        "CONTEXT_LAYER_FLAG",
                        "Cross-Layer Consistency",
                        "Research Context",
                        "PASS",
                        "INFO",
                        f"{selected.name}:{column} is internally boolean-consistent.",
                    )
        else:
            add_check(
                results,
                "CONTEXT_LAYER_FLAGS",
                "Cross-Layer Consistency",
                "Research Context",
                "REVIEW",
                "WARNING",
                "No recognizable layer availability flags were found.",
            )


def build_manifest(
    csv_files: List[Path],
    json_files: List[Path],
) -> pd.DataFrame:
    rows = []

    for path in csv_files + json_files:
        try:
            stat = path.stat()
            sha = file_sha256(path)
            size = stat.st_size
        except Exception:
            sha = ""
            size = -1

        rows.append(
            {
                "file": str(path),
                "file_name": path.name,
                "extension": path.suffix.lower(),
                "size_bytes": size,
                "sha256": sha,
                "detected_layer": detect_layer(path),
            }
        )

    return pd.DataFrame(rows)


def overall_status(results: List[CheckResult]) -> str:
    statuses = [r.status for r in results]

    if "FAIL" in statuses:
        return "FAIL"

    if "REVIEW" in statuses:
        return "REVIEW"

    return "PASS"


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--repo-root",
        default=".",
    )

    parser.add_argument(
        "--artifacts-dir",
        default="artifacts",
    )

    parser.add_argument(
        "--output-dir",
        default="final_end_to_end_validation_output",
    )

    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    artifacts_dir = Path(args.artifacts_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    output_dir.mkdir(parents=True, exist_ok=True)

    results: List[CheckResult] = []

    print("=" * 78)
    print("US500 MACRO INTELLIGENCE")
    print("FINAL END-TO-END VALIDATION V1")
    print("=" * 78)
    print()
    print(f"Repository root : {repo_root}")
    print(f"Artifacts dir   : {artifacts_dir}")
    print(f"Output dir      : {output_dir}")
    print()

    validate_architecture_document(repo_root, results)

    csv_files = discover_csv_files(artifacts_dir)
    json_files = discover_json_files(artifacts_dir)

    print(f"CSV artifacts discovered : {len(csv_files)}")
    print(f"JSON artifacts discovered: {len(json_files)}")
    print()

    if not csv_files and not json_files:
        add_check(
            results,
            "ARTIFACT_DISCOVERY",
            "Artifact Integrity",
            "Global",
            "FAIL",
            "ERROR",
            "No CSV or JSON artifacts were discovered.",
        )
    else:
        add_check(
            results,
            "ARTIFACT_DISCOVERY",
            "Artifact Integrity",
            "Global",
            "PASS",
            "INFO",
            (
                f"Discovered {len(csv_files)} CSV and "
                f"{len(json_files)} JSON artifacts."
            ),
        )

    mapping = classify_artifacts(csv_files)

    validate_layer_coverage(mapping, results)

    for path in csv_files:
        print(f"Validating: {path}")

        df, error = read_csv_safe(path)

        if error:
            add_check(
                results,
                "CSV_READ",
                "Artifact Integrity",
                detect_layer(path),
                "FAIL",
                "ERROR",
                f"Unable to read {path.name}: {error}",
            )
            continue

        if df is None:
            continue

        validate_basic_dataframe(
            path,
            df,
            results,
        )

        validate_pit(
            path,
            df,
            results,
        )

        validate_research_boundaries(
            path,
            df,
            results,
        )

        validate_record_identity(
            path,
            df,
            results,
        )

        if (
            "research-context" in normalize_name(path.name)
            or "research_context" in normalize_name(path.name)
        ):
            validate_final_context(
                path,
                df,
                results,
            )

    validate_cross_layer_context(
        csv_files,
        results,
    )

    manifest = build_manifest(
        csv_files,
        json_files,
    )

    manifest_path = output_dir / "final_end_to_end_validation_manifest.csv"
    manifest.to_csv(manifest_path, index=False)

    results_df = pd.DataFrame(
        [r.to_dict() for r in results]
    )

    report_path = (
        output_dir /
        "final_end_to_end_validation_report.csv"
    )

    results_df.to_csv(
        report_path,
        index=False,
    )

    summary_rows = []

    for status in ["PASS", "REVIEW", "FAIL"]:
        count = int(
            (results_df["status"] == status).sum()
        ) if not results_df.empty else 0

        summary_rows.append(
            {
                "status": status,
                "count": count,
            }
        )

    summary = pd.DataFrame(summary_rows)

    final_status = overall_status(results)

    summary = pd.concat(
        [
            summary,
            pd.DataFrame(
                [
                    {
                        "status": "OVERALL",
                        "count": final_status,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    summary_path = (
        output_dir /
        "final_end_to_end_validation_summary.csv"
    )

    summary.to_csv(
        summary_path,
        index=False,
    )

    events = results_df[
        results_df["status"].isin(["FAIL", "REVIEW"])
    ].copy()

    events_path = (
        output_dir /
        "final_end_to_end_validation_events.csv"
    )

    events.to_csv(
        events_path,
        index=False,
    )

    json_output = {
        "validation_version": VERSION,
        "architecture_version": "FINAL_UNIFIED_DECISION_ARCHITECTURE_V1",
        "overall_status": final_status,
        "research_only": True,
        "decision_engine_implemented": False,
        "trading_signal_generated": False,
        "trade_execution": False,
        "forecast_generated": False,
        "csv_artifact_count": len(csv_files),
        "json_artifact_count": len(json_files),
        "checks_total": len(results),
        "checks_pass": sum(
            r.status == "PASS" for r in results
        ),
        "checks_review": sum(
            r.status == "REVIEW" for r in results
        ),
        "checks_fail": sum(
            r.status == "FAIL" for r in results
        ),
    }

    json_path = (
        output_dir /
        "final_end_to_end_validation.json"
    )

    json_path.write_text(
        json.dumps(
            json_output,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 78)
    print("FINAL END-TO-END VALIDATION RESULT")
    print("=" * 78)
    print(f"OVERALL STATUS : {final_status}")
    print(
        f"PASS           : "
        f"{json_output['checks_pass']}"
    )
    print(
        f"REVIEW         : "
        f"{json_output['checks_review']}"
    )
    print(
        f"FAIL           : "
        f"{json_output['checks_fail']}"
    )
    print()
    print("Research-only boundary : ACTIVE")
    print("Decision Engine        : NOT IMPLEMENTED")
    print("Trading signals        : FALSE")
    print("Trade execution        : FALSE")
    print("Forecasting            : FALSE")
    print("=" * 78)

    return 0 if final_status != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
