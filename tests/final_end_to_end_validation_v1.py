#!/usr/bin/env python3

"""
US500 MACRO INTELLIGENCE
FINAL END-TO-END VALIDATION V1

Artifact-aware / Pagination-safe / Research-only

Important:
- This validator validates the existing research architecture.
- It does NOT implement a Decision Engine.
- It does NOT generate trading signals.
- It does NOT generate forecasts.
- It does NOT execute trades.
- It does NOT modify any research module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


VERSION = "FINAL_END_TO_END_VALIDATION_V1"

ARCHITECTURE_FILE = "FINAL_UNIFIED_DECISION_ARCHITECTURE_V1.md"


# ---------------------------------------------------------------------
# REQUIRED RESEARCH LAYERS
# ---------------------------------------------------------------------

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


# ---------------------------------------------------------------------
# ARTIFACT CLASSIFICATION
# ---------------------------------------------------------------------

PRIMARY_PATTERNS = {
    "Economic Intelligence": [
        r"economic.*surprise",
        r"economic.*regime",
        r"economic.*research",
        r"economic.*intelligence",
    ],

    "Fed Intelligence": [
        r"fed.*intelligence",
        r"fed.*research",
    ],

    "Financial Stress": [
        r"financial[-_ ]stress.*research",
        r"financial[-_ ]stress.*intelligence",
    ],

    "COT Positioning": [
        r"cot.*positioning.*research",
        r"cot.*positioning",
    ],

    "AAII Sentiment": [
        r"aaii.*sentiment.*research",
        r"aaii.*sentiment",
    ],

    "VIX Sentiment": [
        r"vix.*sentiment.*research",
        r"vix.*sentiment",
    ],

    "Unified Sentiment": [
        r"sentiment.*engine.*research",
        r"sentiment[-_ ]engine",
    ],

    "Technical Intelligence": [
        r"technical.*intelligence.*research",
        r"technical[-_ ]intelligence",
    ],

    "Market Breadth": [
        r"market.*breadth.*research",
        r"market[-_ ]breadth.*analysis",
        r"breadth.*research",
    ],

    "Cross-Asset Intelligence": [
        r"cross[-_ ]asset.*research",
        r"cross[-_ ]asset.*intelligence",
    ],

    "Event / News Intelligence": [
        r"event[-_ ]news.*research",
        r"event[-_ ]news.*intelligence",
    ],

    "Earnings Intelligence": [
        r"earnings.*research",
        r"earnings.*intelligence",
        r"earnings.*contextual",
        r"earnings.*reaction",
    ],

    "Macro Context": [
        r"macro[-_ ]context",
        r"macro.*research",
    ],

    "Research Context": [
        r"research[-_ ]context",
    ],
}


DIAGNOSTIC_PATTERNS = [
    r"validation",
    r"robustness",
    r"sensitivity",
    r"discrepanc",
    r"unresolved",
    r"conflict",
    r"extreme",
    r"frequency",
    r"events?",
    r"summary",
    r"membership",
    r"quality",
    r"diagnostic",
    r"manifest",
    r"verdict",
    r"year[_-]by[_-]year",
    r"max[_-]drawdown",
    r"leave[_-]one[_-]year",
    r"crisis[_-]exclusion",
    r"largest[_-]year",
]


SUPPORTING_PATTERNS = [
    r"historical",
    r"collector",
    r"raw",
    r"foundation",
    r"records",
]


# ---------------------------------------------------------------------
# FORBIDDEN FIELDS
# ---------------------------------------------------------------------

FORBIDDEN_EXECUTION_COLUMNS = {
    "order_id",
    "broker_order_id",
    "execution_id",
    "fill_price",
    "filled_quantity",
    "broker",
    "position_id",
    "trade_execution",
    "execution_price",
    "execution_time",
}


FORBIDDEN_FORECAST_COLUMNS = {
    "forecast_price",
    "predicted_price",
    "predicted_return",
    "prediction",
    "prediction_price",
    "future_prediction",
}


# ---------------------------------------------------------------------
# DATA STRUCTURES
# ---------------------------------------------------------------------

@dataclass
class CheckResult:

    check_id: str
    category: str
    layer: str
    status: str
    severity: str
    message: str
    detail: str = ""

    def to_dict(self):
        return {
            "check_id": self.check_id,
            "category": self.category,
            "layer": self.layer,
            "status": self.status,
            "severity": self.severity,
            "message": self.message,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------
# GENERAL HELPERS
# ---------------------------------------------------------------------

def normalize_name(value: str) -> str:

    return re.sub(
        r"[^a-z0-9]+",
        "-",
        str(value).lower()
    ).strip("-")


def add_check(
    results: List[CheckResult],
    check_id: str,
    category: str,
    layer: str,
    status: str,
    severity: str,
    message: str,
    detail: str = "",
):

    results.append(
        CheckResult(
            check_id=check_id,
            category=category,
            layer=layer,
            status=status,
            severity=severity,
            message=message,
            detail=detail,
        )
    )


def file_sha256(path: Path) -> str:

    h = hashlib.sha256()

    with path.open("rb") as f:

        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b""
        ):

            h.update(chunk)

    return h.hexdigest()


def read_csv_safe(
    path: Path,
) -> Tuple[
    Optional[pd.DataFrame],
    Optional[str],
]:

    try:

        df = pd.read_csv(
            path,
            low_memory=False,
        )

        return df, None

    except Exception as exc:

        return None, str(exc)


def parse_dates(
    series: pd.Series,
) -> pd.Series:

    return pd.to_datetime(
        series,
        errors="coerce",
        utc=True,
    )


def bool_series(
    series: pd.Series,
) -> Optional[pd.Series]:

    if series is None:
        return None

    normalized = (
        series.astype(str)
        .str.strip()
        .str.lower()
    )

    mapping = {
        "true": True,
        "false": False,
        "1": True,
        "0": False,
        "yes": True,
        "no": False,
        "y": True,
        "n": False,
    }

    converted = normalized.map(mapping)

    if converted.isna().any():
        return None

    return converted.astype(bool)


def discover_csv_files(
    root: Path,
) -> List[Path]:

    if not root.exists():
        return []

    return sorted(
        [
            p
            for p in root.rglob("*.csv")
            if p.is_file()
        ]
    )


def discover_json_files(
    root: Path,
) -> List[Path]:

    if not root.exists():
        return []

    return sorted(
        [
            p
            for p in root.rglob("*.json")
            if p.is_file()
        ]
    )


# ---------------------------------------------------------------------
# ARTIFACT CLASSIFICATION
# ---------------------------------------------------------------------

def is_diagnostic_name(
    name: str,
) -> bool:

    normalized = normalize_name(name)

    return any(
        re.search(
            pattern,
            normalized
        )
        for pattern in DIAGNOSTIC_PATTERNS
    )


def detect_primary_layer(
    path: Path,
) -> Optional[str]:

    normalized = normalize_name(
        path.name
    )

    for layer, patterns in PRIMARY_PATTERNS.items():

        for pattern in patterns:

            if re.search(
                pattern,
                normalized
            ):

                return layer

    return None


def classify_artifact(
    path: Path,
) -> Tuple[
    str,
    Optional[str],
]:

    """
    Returns:

        (classification, layer)

    classification:

        PRIMARY
        SUPPORTING
        DIAGNOSTIC
        UNKNOWN

    Classification is intentionally conservative.

    A canonical Event / News research artifact must not be
    downgraded simply because its filename contains the generic
    word "event".
    """

    name = normalize_name(
        path.name
    )

    layer = detect_primary_layer(
        path
    )

    # Event / News research files are PRIMARY.
    if (
        layer == "Event / News Intelligence"
        and re.search(
            r"event[-_ ]news[-_ ]research",
            name,
        )
    ):

        return (
            "PRIMARY",
            layer,
        )

    # Diagnostic artifacts are validation evidence.
    if is_diagnostic_name(
        path.name
    ):

        return (
            "DIAGNOSTIC",
            layer,
        )

    if layer:

        return (
            "PRIMARY",
            layer,
        )

    if any(
        re.search(
            pattern,
            name
        )
        for pattern in SUPPORTING_PATTERNS
    ):

        return (
            "SUPPORTING",
            None,
        )

    return (
        "UNKNOWN",
        None,
    )


# ---------------------------------------------------------------------
# PRIMARY ARTIFACT CROSS-CHECK
# ---------------------------------------------------------------------

def layer_has_nonempty_primary(
    target_path: Path,
    csv_files: List[Path],
) -> bool:

    """
    Returns True when another PRIMARY artifact belonging to the
    same research layer contains at least one data row.

    This prevents an older/placeholder empty PRIMARY artifact from
    invalidating an otherwise valid research layer.
    """

    target_classification, target_layer = classify_artifact(
        target_path
    )

    if (
        target_classification != "PRIMARY"
        or target_layer is None
    ):
        return False

    for candidate in csv_files:

        if candidate == target_path:
            continue

        classification, layer = classify_artifact(
            candidate
        )

        if (
            classification != "PRIMARY"
            or layer != target_layer
        ):
            continue

        df, error = read_csv_safe(
            candidate
        )

        if (
            error is None
            and df is not None
            and not df.empty
        ):

            return True

    return False


# ---------------------------------------------------------------------
# BASIC CSV VALIDATION
# ---------------------------------------------------------------------

def validate_basic_dataframe(
    path: Path,
    df: pd.DataFrame,
    results: List[CheckResult],
    strict: bool,
    allow_empty_primary: bool = False,
):

    classification, layer = classify_artifact(
        path
    )

    if layer is None:
        layer = "Unclassified"

    name = path.name

    # Diagnostic files are validation evidence, not canonical
    # research datasets.
    if classification == "DIAGNOSTIC":
        return

    if df.empty:

        if (
            classification == "PRIMARY"
            and strict
            and not allow_empty_primary
        ):

            add_check(
                results,
                "PRIMARY_NONEMPTY",
                "Artifact Integrity",
                layer,
                "FAIL",
                "ERROR",
                (
                    f"{name} is a PRIMARY artifact "
                    f"but contains zero rows."
                ),
            )

        else:

            status_message = (
                f"{name} contains zero rows; "
                f"artifact classification="
                f"{classification}."
            )

            if allow_empty_primary:

                status_message = (
                    f"{name} is an empty PRIMARY artifact, "
                    f"but another non-empty PRIMARY artifact "
                    f"for the same research layer exists; "
                    f"treated as historical/placeholder evidence."
                )

            add_check(
                results,
                "NONEMPTY",
                "Artifact Integrity",
                layer,
                "REVIEW",
                "WARNING",
                status_message,
            )

    else:

        add_check(
            results,
            "NONEMPTY",
            "Artifact Integrity",
            layer,
            "PASS",
            "INFO",
            (
                f"{name} contains "
                f"{len(df)} data rows."
            ),
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
            (
                f"{name} contains "
                f"{len(df.columns)} columns."
            ),
        )

    duplicate_rows = int(
        df.duplicated().sum()
    )

    if duplicate_rows:

        add_check(
            results,
            "DUPLICATE_ROWS",
            "Data Integrity",
            layer,
            (
                "FAIL"
                if classification == "PRIMARY"
                and not allow_empty_primary
                else "REVIEW"
            ),
            (
                "ERROR"
                if classification == "PRIMARY"
                and not allow_empty_primary
                else "WARNING"
            ),
            (
                f"{name} contains "
                f"{duplicate_rows} completely "
                f"duplicated rows."
            ),
        )

    else:

        add_check(
            results,
            "DUPLICATE_ROWS",
            "Data Integrity",
            layer,
            "PASS",
            "INFO",
            (
                f"{name} contains no completely "
                f"duplicated rows."
            ),
        )


# ---------------------------------------------------------------------
# DATE VALIDATION
# ---------------------------------------------------------------------

DATE_COLUMNS = [
    "observation_date",
    "availability_date",
    "asof_date",
    "context_date",
    "source_date",
    "event_date",
    "reported_date",
    "technical_observation_date",
    "technical_availability_date",
    "cross_asset_observation_date",
    "cross_asset_availability_date",
    "macro_availability_date",
    "sentiment_asof_date",
]


def validate_dates(
    path: Path,
    df: pd.DataFrame,
    results: List[CheckResult],
):

    classification, layer = classify_artifact(
        path
    )

    if layer is None:
        layer = "Unclassified"

    for column in DATE_COLUMNS:

        if column not in df.columns:
            continue

        series = df[column]

        # Empty and placeholder values are not invalid dates.
        # They represent unavailable/non-applicable metadata.
        normalized = (
            series.astype(str)
            .str.strip()
            .str.lower()
        )

        empty_or_placeholder = normalized.isin({
            "",
            "nan",
            "nat",
            "none",
            "null",
            "na",
            "n/a",
            "not available",
            "not_available",
            "unknown",
            "-",
        })

        non_empty = (
            series.notna()
            & ~empty_or_placeholder
        )

        if not non_empty.any():

            add_check(
                results,
                "DATE_PARSE",
                "Temporal Integrity",
                layer,
                "REVIEW",
                "WARNING",
                (
                    f"{path.name}:{column} "
                    f"contains no populated values."
                ),
            )

            continue

        parsed = parse_dates(
            series[non_empty]
        )

        invalid = int(
            parsed.isna().sum()
        )

        if invalid:

            add_check(
                results,
                "DATE_PARSE",
                "Temporal Integrity",
                layer,
                (
                    "FAIL"
                    if classification == "PRIMARY"
                    else "REVIEW"
                ),
                (
                    "ERROR"
                    if classification == "PRIMARY"
                    else "WARNING"
                ),
                (
                    f"{path.name}:{column} contains "
                    f"{invalid} populated invalid dates."
                ),
            )

        else:

            add_check(
                results,
                "DATE_PARSE",
                "Temporal Integrity",
                layer,
                "PASS",
                "INFO",
                (
                    f"{path.name}:{column} populated "
                    f"dates parsed successfully."
                ),
            )


# ---------------------------------------------------------------------
# POINT-IN-TIME VALIDATION
# ---------------------------------------------------------------------

def validate_pit(
    path: Path,
    df: pd.DataFrame,
    results: List[CheckResult],
):

    classification, layer = classify_artifact(
        path
    )

    if layer is None:
        layer = "Unclassified"

    name = path.name

    # -------------------------------------------------------------
    # PIT FLAG
    # -------------------------------------------------------------

    if "point_in_time_safe" in df.columns:

        values = bool_series(
            df["point_in_time_safe"]
        )

        if values is None:

            add_check(
                results,
                "PIT_FLAG_PARSE",
                "PIT",
                layer,
                "FAIL",
                "ERROR",
                (
                    f"{name}:point_in_time_safe "
                    f"contains invalid boolean values."
                ),
            )

        elif bool(values.all()):

            add_check(
                results,
                "PIT_FLAG",
                "PIT",
                layer,
                "PASS",
                "INFO",
                (
                    f"{name}:point_in_time_safe "
                    f"is TRUE for all rows."
                ),
            )

        else:

            bad = int(
                (~values).sum()
            )

            add_check(
                results,
                "PIT_FLAG",
                "PIT",
                layer,
                "FAIL",
                "ERROR",
                (
                    f"{name}:point_in_time_safe "
                    f"is FALSE for {bad} rows."
                ),
            )

    # -------------------------------------------------------------
    # MASTER PIT RULE
    #
    # availability_date <= asof_date
    #
    # DO NOT compare availability_date to observation_date.
    #
    # Observation date and release/availability date can legitimately
    # be different. A later release after an observation date is not
    # automatically look-ahead.
    # -------------------------------------------------------------

    asof_candidates = [
        c
        for c in [
            "asof_date",
            "context_date",
            "sentiment_asof_date",
        ]
        if c in df.columns
    ]

    availability_candidates = [
        c
        for c in [
            "availability_date",
            "technical_availability_date",
            "cross_asset_availability_date",
            "macro_availability_date",
        ]
        if c in df.columns
    ]

    if (
        not asof_candidates
        or not availability_candidates
    ):

        return

    asof_col = asof_candidates[0]

    asof = parse_dates(
        df[asof_col]
    )

    for avail_col in availability_candidates:

        avail = parse_dates(
            df[avail_col]
        )

        valid = (
            asof.notna()
            & avail.notna()
        )

        if not valid.any():

            add_check(
                results,
                "PIT_DATE_COMPARISON",
                "PIT",
                layer,
                "REVIEW",
                "WARNING",
                (
                    f"{name}: no populated date pairs "
                    f"available for "
                    f"{avail_col}/{asof_col}."
                ),
            )

            continue

        # Correct point-in-time invariant:
        #
        # The information must have been available by the
        # context/as-of date.
        #
        # Therefore:
        #
        #     availability_date <= asof_date
        #
        bad = int(
            (
                avail[valid]
                > asof[valid]
            ).sum()
        )

        if bad:

            add_check(
                results,
                "PIT_DATE_COMPARISON",
                "PIT",
                layer,
                "FAIL",
                "ERROR",
                (
                    f"{name}:{avail_col} is later than "
                    f"{asof_col} for {bad} rows."
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
                    f"{name}:{avail_col} satisfies "
                    f"{avail_col} <= {asof_col}."
                ),
            )


# ---------------------------------------------------------------------
# RESEARCH-ONLY BOUNDARY
# ---------------------------------------------------------------------

def validate_research_boundaries(
    path: Path,
    df: pd.DataFrame,
    results: List[CheckResult],
):

    classification, layer = classify_artifact(
        path
    )

    if layer is None:
        layer = "Unclassified"

    name = path.name

    if "research_only" in df.columns:

        values = bool_series(
            df["research_only"]
        )

        if (
            values is None
            or not bool(values.all())
        ):

            add_check(
                results,
                "RESEARCH_ONLY",
                "Research Boundary",
                layer,
                "FAIL",
                "ERROR",
                (
                    f"{name}:research_only is not "
                    f"TRUE for every row."
                ),
            )

        else:

            add_check(
                results,
                "RESEARCH_ONLY",
                "Research Boundary",
                layer,
                "PASS",
                "INFO",
                (
                    f"{name}:research_only is TRUE "
                    f"for all rows."
                ),
            )

    for column in [
        "decision_engine_ready",
        "trading_signal_generated",
        "forecast_generated",
        "unified_decision_generated",
        "trade_execution",
    ]:

        if column not in df.columns:
            continue

        values = bool_series(
            df[column]
        )

        if values is None:

            add_check(
                results,
                f"BOUNDARY_{column.upper()}",
                "Research Boundary",
                layer,
                "FAIL",
                "ERROR",
                (
                    f"{name}:{column} contains "
                    f"invalid boolean values."
                ),
            )

        elif bool(values.any()):

            add_check(
                results,
                f"BOUNDARY_{column.upper()}",
                "Research Boundary",
                layer,
                "FAIL",
                "ERROR",
                (
                    f"{name}:{column} is TRUE "
                    f"in some rows."
                ),
            )

        else:

            add_check(
                results,
                f"BOUNDARY_{column.upper()}",
                "Research Boundary",
                layer,
                "PASS",
                "INFO",
                (
                    f"{name}:{column} is FALSE "
                    f"for all rows."
                ),
            )

    forbidden_execution = [
        c
        for c in df.columns
        if c.lower()
        in FORBIDDEN_EXECUTION_COLUMNS
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
                f"{name} contains explicit execution "
                f"fields: "
                + ", ".join(forbidden_execution)
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
            (
                f"{name} contains no explicit "
                f"execution fields."
            ),
        )

    forbidden_forecast = [
        c
        for c in df.columns
        if c.lower()
        in FORBIDDEN_FORECAST_COLUMNS
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
                f"{name} contains explicit forecast "
                f"fields: "
                + ", ".join(forbidden_forecast)
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
            (
                f"{name} contains no explicit "
                f"forecast fields."
            ),
        )


# ---------------------------------------------------------------------
# RECORD ID
# ---------------------------------------------------------------------

def validate_record_identity(
    path: Path,
    df: pd.DataFrame,
    results: List[CheckResult],
):

    classification, layer = classify_artifact(
        path
    )

    if layer is None:
        layer = "Unclassified"

    if classification != "PRIMARY":
        return

    id_candidates = [
        c
        for c in df.columns
        if c.lower()
        in {
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
            (
                f"{path.name} has no recognized "
                f"record identity field."
            ),
        )

        return

    for column in id_candidates:

        nulls = int(
            df[column].isna().sum()
        )

        duplicates = int(
            df[column].duplicated().sum()
        )

        if nulls:

            add_check(
                results,
                "RECORD_ID_NULL",
                "Provenance",
                layer,
                "FAIL",
                "ERROR",
                (
                    f"{path.name}:{column} contains "
                    f"{nulls} null IDs."
                ),
            )

        elif duplicates:

            add_check(
                results,
                "RECORD_ID_DUPLICATE",
                "Provenance",
                layer,
                "FAIL",
                "ERROR",
                (
                    f"{path.name}:{column} contains "
                    f"{duplicates} duplicate IDs."
                ),
            )

        else:

            add_check(
                results,
                "RECORD_ID",
                "Provenance",
                layer,
                "PASS",
                "INFO",
                (
                    f"{path.name}:{column} is non-null "
                    f"and unique."
                ),
            )


# ---------------------------------------------------------------------
# FINAL RESEARCH CONTEXT
# ---------------------------------------------------------------------

def validate_final_context(
    path: Path,
    df: pd.DataFrame,
    results: List[CheckResult],
):

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

    missing = [
        c
        for c in required
        if c not in df.columns
    ]

    if missing:

        add_check(
            results,
            "CANONICAL_CONTEXT_SCHEMA",
            "Unified Architecture",
            layer,
            "FAIL",
            "ERROR",
            (
                "Canonical Research Context is missing "
                "required columns."
            ),
            ", ".join(missing),
        )

        return

    add_check(
        results,
        "CANONICAL_CONTEXT_SCHEMA",
        "Unified Architecture",
        layer,
        "PASS",
        "INFO",
        (
            "Canonical Research Context required "
            "control schema is present."
        ),
    )

    dates = parse_dates(
        df["context_date"]
    )

    if dates.isna().any():

        add_check(
            results,
            "CONTEXT_DATE_VALID",
            "Unified Architecture",
            layer,
            "FAIL",
            "ERROR",
            (
                "Canonical context_date contains "
                "invalid dates."
            ),
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
                (
                    "Canonical context_date is not "
                    "monotonically increasing."
                ),
            )

        else:

            add_check(
                results,
                "CONTEXT_DATE_ORDER",
                "Unified Architecture",
                layer,
                "PASS",
                "INFO",
                (
                    "Canonical context_date is "
                    "monotonically increasing."
                ),
            )

        duplicates = int(
            dates.duplicated().sum()
        )

        if duplicates:

            add_check(
                results,
                "CONTEXT_DATE_UNIQUE",
                "Unified Architecture",
                layer,
                "FAIL",
                "ERROR",
                (
                    f"Canonical context_date has "
                    f"{duplicates} duplicates."
                ),
            )

        else:

            add_check(
                results,
                "CONTEXT_DATE_UNIQUE",
                "Unified Architecture",
                layer,
                "PASS",
                "INFO",
                (
                    "Canonical context_date is unique."
                ),
            )

    for column in [
        "point_in_time_safe",
        "research_only",
    ]:

        values = bool_series(
            df[column]
        )

        if (
            values is None
            or not bool(values.all())
        ):

            add_check(
                results,
                f"CANONICAL_{column.upper()}",
                "Unified Architecture",
                layer,
                "FAIL",
                "ERROR",
                (
                    f"Canonical {column} is not TRUE "
                    f"for all rows."
                ),
            )

        else:

            add_check(
                results,
                f"CANONICAL_{column.upper()}",
                "Unified Architecture",
                layer,
                "PASS",
                "INFO",
                (
                    f"Canonical {column} is TRUE "
                    f"for all rows."
                ),
            )

    for column in [
        "decision_engine_ready",
        "trading_signal_generated",
        "forecast_generated",
        "unified_decision_generated",
    ]:

        values = bool_series(
            df[column]
        )

        if (
            values is None
            or bool(values.any())
        ):

            add_check(
                results,
                f"CANONICAL_{column.upper()}",
                "Unified Architecture",
                layer,
                "FAIL",
                "ERROR",
                (
                    f"Canonical {column} contains "
                    f"TRUE/invalid values."
                ),
            )

        else:

            add_check(
                results,
                f"CANONICAL_{column.upper()}",
                "Unified Architecture",
                layer,
                "PASS",
                "INFO",
                (
                    f"Canonical {column} is FALSE "
                    f"for all rows."
                ),
            )

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
            (
                "available_layer_count contains "
                "non-numeric values."
            ),
        )

    elif (counts < 0).any():

        add_check(
            results,
            "AVAILABLE_LAYER_COUNT",
            "Unified Architecture",
            layer,
            "FAIL",
            "ERROR",
            (
                "available_layer_count contains "
                "negative values."
            ),
        )

    else:

        add_check(
            results,
            "AVAILABLE_LAYER_COUNT",
            "Unified Architecture",
            layer,
            "PASS",
            "INFO",
            (
                "available_layer_count is "
                "numerically valid."
            ),
        )


# ---------------------------------------------------------------------
# ARCHITECTURE DOCUMENT
# ---------------------------------------------------------------------

def validate_architecture_document(
    repo_root: Path,
    results: List[CheckResult],
):

    path = (
        repo_root
        / ARCHITECTURE_FILE
    )

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

    content = path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    required_groups = {

        "research_only": [
            "research_only",
        ],

        "pit": [
            "availability_date",
            "point_in_time_safe",
        ],

        "decision_boundary": [
            "decision_engine_ready",
            "trading_signal_generated",
            "forecast_generated",
            "unified_decision_generated",
        ],

        "conflict_policy": [
            "CONFLICTING_CONTEXT",
            "MIXED_CONTEXT",
            "CROSS_LAYER_DIVERGENCE",
        ],

        "architecture_state": [
            "Research Mode: ACTIVE",
            "Decision Engine: NOT IMPLEMENTED",
            "Trade Execution: NOT IMPLEMENTED",
        ],
    }

    missing = []

    for group, phrases in required_groups.items():

        for phrase in phrases:

            if phrase not in content:

                missing.append(
                    f"{group}:{phrase}"
                )

    if missing:

        add_check(
            results,
            "ARCHITECTURE_CONTRACT",
            "Architecture",
            "Architecture",
            "FAIL",
            "ERROR",
            (
                "Architecture document is missing "
                "required contract elements."
            ),
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
            (
                "Architecture contract contains "
                "required research-only boundaries."
            ),
        )


# ---------------------------------------------------------------------
# LAYER COVERAGE
# ---------------------------------------------------------------------

def classify_layers(
    artifact_files: List[Path],
):

    mapping: Dict[
        str,
        Dict[
            str,
            List[Path]
        ]
    ] = {

        layer: {
            "PRIMARY": [],
            "SUPPORTING": [],
            "DIAGNOSTIC": [],
        }

        for layer in REQUIRED_LAYERS
    }

    for path in artifact_files:

        classification, layer = classify_artifact(
            path
        )

        if (
            layer in mapping
            and classification in mapping[layer]
        ):

            mapping[layer][classification].append(
                path
            )

    return mapping


def validate_layer_coverage(
    mapping,
    results: List[CheckResult],
):

    for layer in REQUIRED_LAYERS:

        primary = mapping[layer]["PRIMARY"]

        supporting = mapping[layer]["SUPPORTING"]

        diagnostic = mapping[layer]["DIAGNOSTIC"]

        if primary:

            add_check(
                results,
                "LAYER_COVERAGE",
                "Layer Coverage",
                layer,
                "PASS",
                "INFO",
                (
                    f"PRIMARY artifact coverage "
                    f"confirmed: {len(primary)} file(s)."
                ),
            )

        elif supporting:

            add_check(
                results,
                "LAYER_COVERAGE",
                "Layer Coverage",
                layer,
                "REVIEW",
                "WARNING",
                (
                    "Supporting artifact(s) were found "
                    "but no canonical primary artifact "
                    "was automatically identified."
                ),
                ", ".join(
                    p.name
                    for p in supporting
                ),
            )

        elif diagnostic:

            add_check(
                results,
                "LAYER_COVERAGE",
                "Layer Coverage",
                layer,
                "REVIEW",
                "WARNING",
                (
                    "Only diagnostic artifacts were "
                    "found for this layer."
                ),
                ", ".join(
                    p.name
                    for p in diagnostic
                ),
            )

        else:

            add_check(
                results,
                "LAYER_COVERAGE",
                "Layer Coverage",
                layer,
                "FAIL",
                "ERROR",
                (
                    "No artifact was found for this "
                    "required research layer."
                ),
            )


# ---------------------------------------------------------------------
# CROSS-LAYER CONTEXT
# ---------------------------------------------------------------------

def find_research_context(
    csv_files: List[Path],
) -> Optional[Path]:

    candidates = []

    for path in csv_files:

        name = normalize_name(
            path.name
        )

        parent_name = normalize_name(
            str(path.parent)
        )

        if (
            "research-context" in name
            or "research-context" in parent_name
        ):

            classification, _ = classify_artifact(
                path
            )

            if classification == "PRIMARY":

                candidates.append(
                    path
                )

    if not candidates:
        return None

    # Prefer a populated canonical artifact.
    populated = []

    for candidate in candidates:

        df, error = read_csv_safe(
            candidate
        )

        if (
            error is None
            and df is not None
            and not df.empty
        ):

            populated.append(candidate)

    if populated:

        return sorted(
            populated,
            key=lambda p: (
                p.stat().st_mtime,
                p.name,
            ),
            reverse=True,
        )[0]

    return candidates[0]


def validate_cross_layer_context(
    csv_files: List[Path],
    results: List[CheckResult],
):

    selected = find_research_context(
        csv_files
    )

    if selected is None:

        add_check(
            results,
            "CANONICAL_CONTEXT_DISCOVERY",
            "Cross-Layer Consistency",
            "Research Context",
            "FAIL",
            "ERROR",
            (
                "No PRIMARY Research Context CSV "
                "was discovered."
            ),
        )

        return

    df, error = read_csv_safe(
        selected
    )

    if (
        error
        or df is None
    ):

        add_check(
            results,
            "CANONICAL_CONTEXT_READ",
            "Cross-Layer Consistency",
            "Research Context",
            "FAIL",
            "ERROR",
            (
                f"Unable to read "
                f"{selected.name}: {error}"
            ),
        )

        return

    validate_final_context(
        selected,
        df,
        results,
    )

    layer_flags = [
        c
        for c in [
            "macro_available",
            "sentiment_available",
            "technical_available",
            "cross_asset_available",
        ]
        if c in df.columns
    ]

    if layer_flags:

        for column in layer_flags:

            values = bool_series(
                df[column]
            )

            if values is None:

                add_check(
                    results,
                    "CONTEXT_LAYER_FLAG",
                    "Cross-Layer Consistency",
                    "Research Context",
                    "FAIL",
                    "ERROR",
                    (
                        f"{selected.name}:{column} "
                        f"contains invalid boolean values."
                    ),
                )

            else:

                add_check(
                    results,
                    "CONTEXT_LAYER_FLAG",
                    "Cross-Layer Consistency",
                    "Research Context",
                    "PASS",
                    "INFO",
                    (
                        f"{selected.name}:{column} "
                        f"is boolean-consistent."
                    ),
                )

    else:

        add_check(
            results,
            "CONTEXT_LAYER_FLAGS",
            "Cross-Layer Consistency",
            "Research Context",
            "REVIEW",
            "WARNING",
            (
                "No recognizable layer availability "
                "flags were found."
            ),
        )


# ---------------------------------------------------------------------
# JSON ARTIFACT VALIDATION
# ---------------------------------------------------------------------

def validate_json_artifact(
    path: Path,
    results: List[CheckResult],
):

    classification, layer = classify_artifact(
        path
    )

    if layer is None:
        layer = "Unclassified"

    try:

        content = path.read_text(
            encoding="utf-8",
            errors="strict",
        )

        data = json.loads(
            content
        )

    except Exception as exc:

        status = (
            "FAIL"
            if classification == "PRIMARY"
            else "REVIEW"
        )

        severity = (
            "ERROR"
            if status == "FAIL"
            else "WARNING"
        )

        add_check(
            results,
            "JSON_READ",
            "Artifact Integrity",
            layer,
            status,
            severity,
            (
                f"Unable to parse "
                f"{path.name}: {exc}"
            ),
        )

        return

    # Diagnostic JSON is not a canonical dataset.
    if classification == "DIAGNOSTIC":
        return

    add_check(
        results,
        "JSON_READ",
        "Artifact Integrity",
        layer,
        "PASS",
        "INFO",
        (
            f"{path.name} is valid JSON."
        ),
    )

    # Validate explicit research-boundary fields when present.
    if isinstance(data, dict):

        expected = {

            "research_only": True,

            "decision_engine_ready": False,

            "trading_signal_generated": False,

            "forecast_generated": False,

            "unified_decision_generated": False,

            "trade_execution": False,
        }

        for field, expected_value in expected.items():

            if field not in data:
                continue

            value = data[field]

            if value != expected_value:

                add_check(
                    results,
                    f"JSON_BOUNDARY_{field.upper()}",
                    "Research Boundary",
                    layer,
                    "FAIL",
                    "ERROR",
                    (
                        f"{path.name}:{field} violates "
                        f"the expected research-only "
                        f"boundary."
                    ),
                )

            else:

                add_check(
                    results,
                    f"JSON_BOUNDARY_{field.upper()}",
                    "Research Boundary",
                    layer,
                    "PASS",
                    "INFO",
                    (
                        f"{path.name}:{field} has the "
                        f"expected value."
                    ),
                )


# ---------------------------------------------------------------------
# MANIFEST
# ---------------------------------------------------------------------

def build_manifest(
    csv_files: List[Path],
    json_files: List[Path],
) -> pd.DataFrame:

    rows = []

    for path in (
        csv_files
        + json_files
    ):

        try:

            stat = path.stat()

            rows.append(
                {
                    "file": str(path),
                    "file_name": path.name,
                    "extension": path.suffix.lower(),
                    "size_bytes": stat.st_size,
                    "sha256": file_sha256(path),
                    "detected_layer":
                        detect_primary_layer(path)
                        or "",
                    "classification":
                        classify_artifact(path)[0],
                }
            )

        except Exception:

            rows.append(
                {
                    "file": str(path),
                    "file_name": path.name,
                    "extension": path.suffix.lower(),
                    "size_bytes": -1,
                    "sha256": "",
                    "detected_layer": "",
                    "classification": "UNKNOWN",
                }
            )

    return pd.DataFrame(
        rows
    )


# ---------------------------------------------------------------------
# OVERALL STATUS
# ---------------------------------------------------------------------

def overall_status(
    results: List[CheckResult],
) -> str:

    statuses = [
        r.status
        for r in results
    ]

    if "FAIL" in statuses:
        return "FAIL"

    if "REVIEW" in statuses:
        return "REVIEW"

    return "PASS"


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

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

    repo_root = Path(
        args.repo_root
    ).resolve()

    artifacts_dir = Path(
        args.artifacts_dir
    ).resolve()

    output_dir = Path(
        args.output_dir
    ).resolve()

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    results: List[CheckResult] = []

    print("=" * 78)
    print(
        "US500 MACRO INTELLIGENCE"
    )
    print(
        "FINAL END-TO-END VALIDATION V1"
    )
    print(
        "ARTIFACT-AWARE / PAGINATION-SAFE"
    )
    print("=" * 78)
    print()

    print(
        f"Repository root : {repo_root}"
    )

    print(
        f"Artifacts dir   : {artifacts_dir}"
    )

    print(
        f"Output dir      : {output_dir}"
    )

    print()

    # -------------------------------------------------------------
    # ARCHITECTURE
    # -------------------------------------------------------------

    validate_architecture_document(
        repo_root,
        results,
    )

    # -------------------------------------------------------------
    # DISCOVER ARTIFACTS
    # -------------------------------------------------------------

    csv_files = discover_csv_files(
        artifacts_dir
    )

    json_files = discover_json_files(
        artifacts_dir
    )

    print(
        f"CSV artifacts discovered : "
        f"{len(csv_files)}"
    )

    print(
        f"JSON artifacts discovered: "
        f"{len(json_files)}"
    )

    print()

    if (
        not csv_files
        and not json_files
    ):

        add_check(
            results,
            "ARTIFACT_DISCOVERY",
            "Artifact Integrity",
            "Global",
            "FAIL",
            "ERROR",
            (
                "No CSV or JSON artifacts "
                "were discovered."
            ),
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
                f"Discovered {len(csv_files)} CSV "
                f"and {len(json_files)} JSON artifacts."
            ),
        )

    # -------------------------------------------------------------
    # LAYER CLASSIFICATION
    # -------------------------------------------------------------

    all_artifact_files = (
        csv_files
        + json_files
    )

    mapping = classify_layers(
        all_artifact_files
    )

    print("=" * 78)
    print(
        "RESEARCH LAYER COVERAGE"
    )
    print("=" * 78)

    for layer in REQUIRED_LAYERS:

        primary = mapping[layer]["PRIMARY"]

        supporting = mapping[layer]["SUPPORTING"]

        diagnostic = mapping[layer]["DIAGNOSTIC"]

        print()

        print(layer)

        print(
            f"  PRIMARY    : "
            f"{len(primary)}"
        )

        print(
            f"  SUPPORTING : "
            f"{len(supporting)}"
        )

        print(
            f"  DIAGNOSTIC : "
            f"{len(diagnostic)}"
        )

        for path in primary:

            print(
                f"    PRIMARY -> "
                f"{path.name}"
            )

    print()

    validate_layer_coverage(
        mapping,
        results,
    )

    # -------------------------------------------------------------
    # VALIDATE CSV ARTIFACTS
    # -------------------------------------------------------------

    for path in csv_files:

        classification, layer = (
            classify_artifact(path)
        )

        print(
            f"Validating "
            f"[{classification}] "
            f"{path}"
        )

        df, error = read_csv_safe(
            path
        )

        if error:

            status = (
                "FAIL"
                if classification == "PRIMARY"
                else "REVIEW"
            )

            severity = (
                "ERROR"
                if status == "FAIL"
                else "WARNING"
            )

            add_check(
                results,
                "CSV_READ",
                "Artifact Integrity",
                layer or "Unclassified",
                status,
                severity,
                (
                    f"Unable to read "
                    f"{path.name}: {error}"
                ),
            )

            continue

        if df is None:
            continue

        strict = (
            classification == "PRIMARY"
        )

        allow_empty_primary = (
            classification == "PRIMARY"
            and layer is not None
            and layer_has_nonempty_primary(
                path,
                csv_files,
            )
        )

        validate_basic_dataframe(
            path,
            df,
            results,
            strict,
            allow_empty_primary,
        )

        # Only PRIMARY and SUPPORTING research data
        # receive temporal / PIT / boundary checks.
        if classification in {
            "PRIMARY",
            "SUPPORTING",
        }:

            validate_dates(
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

        if layer == "Research Context":

            validate_final_context(
                path,
                df,
                results,
            )

    # -------------------------------------------------------------
    # VALIDATE JSON ARTIFACTS
    # -------------------------------------------------------------

    for path in json_files:

        print(
            f"Validating JSON "
            f"[{classify_artifact(path)[0]}] "
            f"{path}"
        )

        validate_json_artifact(
            path,
            results,
        )

    # -------------------------------------------------------------
    # CROSS-LAYER CANONICAL CONTEXT
    # -------------------------------------------------------------

    validate_cross_layer_context(
        csv_files,
        results,
    )

    # -------------------------------------------------------------
    # MANIFEST
    # -------------------------------------------------------------

    manifest = build_manifest(
        csv_files,
        json_files,
    )

    manifest_path = (
        output_dir
        / "final_end_to_end_validation_manifest.csv"
    )

    manifest.to_csv(
        manifest_path,
        index=False,
    )

    # -------------------------------------------------------------
    # REPORT
    # -------------------------------------------------------------

    results_df = pd.DataFrame(
        [
            r.to_dict()
            for r in results
        ]
    )

    report_path = (
        output_dir
        / "final_end_to_end_validation_report.csv"
    )

    results_df.to_csv(
        report_path,
        index=False,
    )

    # -------------------------------------------------------------
    # SUMMARY
    # -------------------------------------------------------------

    summary_rows = []

    for status in [
        "PASS",
        "REVIEW",
        "FAIL",
    ]:

        count = (
            int(
                (
                    results_df["status"]
                    == status
                ).sum()
            )
            if not results_df.empty
            else 0
        )

        summary_rows.append(
            {
                "status": status,
                "count": count,
            }
        )

    final_status = overall_status(
        results
    )

    summary_rows.append(
        {
            "status": "OVERALL",
            "count": final_status,
        }
    )

    summary = pd.DataFrame(
        summary_rows
    )

    summary_path = (
        output_dir
        / "final_end_to_end_validation_summary.csv"
    )

    summary.to_csv(
        summary_path,
        index=False,
    )

    # -------------------------------------------------------------
    # EVENTS
    # -------------------------------------------------------------

    if not results_df.empty:

        events = results_df[
            results_df["status"].isin(
                [
                    "FAIL",
                    "REVIEW",
                ]
            )
        ].copy()

    else:

        events = pd.DataFrame()

    events_path = (
        output_dir
        / "final_end_to_end_validation_events.csv"
    )

    events.to_csv(
        events_path,
        index=False,
    )

    # -------------------------------------------------------------
    # FINAL JSON
    # -------------------------------------------------------------

    json_output = {

        "validation_version":
            VERSION,

        "architecture_version":
            "FINAL_UNIFIED_DECISION_ARCHITECTURE_V1",

        "overall_status":
            final_status,

        "research_only":
            True,

        "decision_engine_implemented":
            False,

        "decision_engine_ready":
            False,

        "trading_signal_generated":
            False,

        "trade_execution":
            False,

        "forecast_generated":
            False,

        "unified_decision_generated":
            False,

        "csv_artifact_count":
            len(csv_files),

        "json_artifact_count":
            len(json_files),

        "checks_total":
            len(results),

        "checks_pass":
            sum(
                r.status == "PASS"
                for r in results
            ),

        "checks_review":
            sum(
                r.status == "REVIEW"
                for r in results
            ),

        "checks_fail":
            sum(
                r.status == "FAIL"
                for r in results
            ),

        "required_layers":
            REQUIRED_LAYERS,
    }

    json_path = (
        output_dir
        / "final_end_to_end_validation.json"
    )

    json_path.write_text(
        json.dumps(
            json_output,
            indent=2,
        ),
        encoding="utf-8",
    )

    # -------------------------------------------------------------
    # FINAL CONSOLE OUTPUT
    # -------------------------------------------------------------

    print()

    print("=" * 78)
    print(
        "FINAL END-TO-END VALIDATION RESULT"
    )
    print("=" * 78)

    print(
        f"OVERALL STATUS : "
        f"{final_status}"
    )

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

    print(
        "Research-only boundary : ACTIVE"
    )

    print(
        "Decision Engine        : NOT IMPLEMENTED"
    )

    print(
        "Trading signals        : FALSE"
    )

    print(
        "Trade execution        : FALSE"
    )

    print(
        "Forecasting            : FALSE"
    )

    print(
        "Unified decision       : FALSE"
    )

    print()

    # REVIEW is informational and does not fail the workflow.
    # Only mandatory FAIL conditions return exit code 1.

    if final_status == "FAIL":

        print(
            "FINAL RESULT: FAILED — "
            "mandatory validation invariant(s) failed."
        )

        return 1

    if final_status == "REVIEW":

        print(
            "FINAL RESULT: PASSED WITH REVIEW — "
            "no mandatory validation invariant failed."
        )

        return 0

    print(
        "FINAL RESULT: PASSED — "
        "all mandatory validation invariants passed."
    )

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
