#!/usr/bin/env python3
"""
US500 MACRO INTELLIGENCE
DECISION ENGINE V1
====================

Research-only Decision Engine.

IMPORTANT:
- No broker integration
- No order execution
- No position sizing
- No stop loss
- No take profit
- No trade execution
- No deterministic price forecast
- No future-data leakage
- Point-in-time safe
- Decision Engine is downstream of Research Context

The engine converts already-validated research evidence into a
research classification.

Possible states:
    SUPPORTIVE
    CONTRADICTORY
    MIXED
    INSUFFICIENT_DATA

This is NOT a trading signal.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


# ============================================================
# VERSION
# ============================================================

ENGINE_VERSION = "decision-engine-v1"

RESEARCH_ONLY = True
DECISION_ENGINE_ENABLED = True

# Minimum evidence requirements.
MIN_EVIDENCE = 2
MIN_SUPPORTIVE = 1
MIN_CONTRADICTORY = 1

# Strong majority threshold.
MAJORITY_RATIO = 0.67

# Confidence is descriptive evidence coverage, not a probability
# of future market movement.
HIGH_CONFIDENCE_EVIDENCE = 4


# ============================================================
# HELPERS
# ============================================================

def die(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def is_missing(value: Any) -> bool:
    if value is None:
        return True

    if isinstance(value, float) and math.isnan(value):
        return True

    if pd.isna(value):
        return True

    text = str(value).strip().lower()

    return text in {
        "",
        "nan",
        "none",
        "null",
        "nat",
        "n/a",
        "na",
    }


def as_bool(value: Any) -> Optional[bool]:
    if is_missing(value):
        return None

    if isinstance(value, bool):
        return value

    text = str(value).strip().lower()

    if text in {"true", "1", "yes", "y", "pass"}:
        return True

    if text in {"false", "0", "no", "n", "fail"}:
        return False

    return None


def as_float(value: Any) -> Optional[float]:
    if is_missing(value):
        return None

    try:
        number = float(value)

        if not math.isfinite(number):
            return None

        return number

    except (TypeError, ValueError):
        return None


def normalize_name(value: Any) -> str:
    if is_missing(value):
        return ""

    text = str(value).strip().lower()

    text = re.sub(r"[^a-z0-9]+", "_", text)

    return text.strip("_")


def find_column(
    df: pd.DataFrame,
    candidates: Iterable[str],
) -> Optional[str]:

    normalized = {
        normalize_name(column): column
        for column in df.columns
    }

    for candidate in candidates:

        key = normalize_name(candidate)

        if key in normalized:
            return normalized[key]

    return None


def find_latest_date_column(df: pd.DataFrame) -> Optional[str]:

    candidates = [
        "asof_date",
        "as_of_date",
        "context_date",
        "observation_date",
        "date",
        "availability_date",
        "effective_date",
    ]

    return find_column(df, candidates)


def parse_dates(
    df: pd.DataFrame,
    column: Optional[str],
) -> pd.Series:

    if column is None:
        return pd.Series(
            pd.NaT,
            index=df.index,
        )

    return pd.to_datetime(
        df[column],
        errors="coerce",
        utc=False,
    )


def latest_row(
    df: pd.DataFrame,
    date_column: Optional[str],
) -> pd.Series:

    if df.empty:
        die("Input dataset is empty.")

    if date_column is None:
        return df.iloc[-1]

    dates = parse_dates(df, date_column)

    valid = dates.notna()

    if not valid.any():
        return df.iloc[-1]

    idx = dates[valid].idxmax()

    return df.loc[idx]


def detect_text(
    row: pd.Series,
    candidates: Iterable[str],
) -> Optional[str]:

    column = find_column(
        pd.DataFrame([row]),
        candidates,
    )

    if column is None:
        return None

    value = row[column]

    if is_missing(value):
        return None

    return str(value).strip()


def detect_numeric(
    row: pd.Series,
    candidates: Iterable[str],
) -> Optional[float]:

    column = find_column(
        pd.DataFrame([row]),
        candidates,
    )

    if column is None:
        return None

    return as_float(row[column])


def detect_bool(
    row: pd.Series,
    candidates: Iterable[str],
) -> Optional[bool]:

    column = find_column(
        pd.DataFrame([row]),
        candidates,
    )

    if column is None:
        return None

    return as_bool(row[column])


# ============================================================
# SCHEMA
# ============================================================

def load_csv(path: Path) -> pd.DataFrame:

    if not path.exists():
        die(f"Required input file not found: {path}")

    try:
        df = pd.read_csv(path)
    except Exception as exc:
        die(f"Could not read {path}: {exc}")

    if df.empty:
        die(f"Input CSV is empty: {path}")

    return df


def validate_required_research_flags(
    df: pd.DataFrame,
    source_name: str,
) -> Tuple[bool, List[str]]:

    errors: List[str] = []

    pit_column = find_column(
        df,
        [
            "point_in_time_safe",
            "pit_safe",
            "pit",
        ],
    )

    if pit_column is None:
        errors.append(
            f"{source_name}: missing point-in-time safety field."
        )
    else:
        values = df[pit_column].map(as_bool)

        if values.isna().any():
            errors.append(
                f"{source_name}: invalid PIT values."
            )
        elif not values.all():
            errors.append(
                f"{source_name}: point_in_time_safe is not "
                f"true for every row."
            )

    research_column = find_column(
        df,
        [
            "research_only",
            "research",
        ],
    )

    if research_column is not None:

        values = df[research_column].map(as_bool)

        if values.isna().any():
            errors.append(
                f"{source_name}: invalid research_only values."
            )

        elif not values.all():
            errors.append(
                f"{source_name}: research_only is not true "
                f"for every row."
            )

    return len(errors) == 0, errors


# ============================================================
# EVIDENCE MODEL
# ============================================================

class Evidence:

    def __init__(
        self,
        source: str,
        category: str,
        stance: str,
        reason: str,
        value: Any = None,
    ) -> None:

        self.source = source
        self.category = category
        self.stance = stance
        self.reason = reason
        self.value = value

    def to_dict(self) -> Dict[str, Any]:

        return {
            "source": self.source,
            "category": self.category,
            "stance": self.stance,
            "reason": self.reason,
            "value": self.value,
        }


# ============================================================
# REGIME INTERPRETATION
# ============================================================

def classify_macro_regime(
    value: Optional[str],
) -> Optional[str]:

    if value is None:
        return None

    normalized = normalize_name(value)

    supportive = {
        "bullish",
        "positive",
        "expansion",
        "growth",
        "strong_growth",
        "disinflation",
        "soft_landing",
        "low_research_stress",
        "low_stress",
    }

    contradictory = {
        "bearish",
        "negative",
        "contraction",
        "recession",
        "high_research_stress",
        "high_stress",
        "crisis",
        "stagflation",
    }

    mixed = {
        "mixed",
        "neutral",
        "transition",
        "uncertain",
        "moderate_stress",
    }

    if normalized in supportive:
        return "SUPPORTIVE"

    if normalized in contradictory:
        return "CONTRADICTORY"

    if normalized in mixed:
        return "MIXED"

    return None


def add_macro_evidence(
    evidence: List[Evidence],
    row: pd.Series,
) -> None:

    regime = detect_text(
        row,
        [
            "economic_regime",
            "macro_regime",
            "research_regime",
            "regime",
        ],
    )

    classified = classify_macro_regime(regime)

    if classified == "SUPPORTIVE":

        evidence.append(
            Evidence(
                source="Macro Context",
                category="macro",
                stance="SUPPORTIVE",
                reason=f"Macro regime classified as {regime}.",
                value=regime,
            )
        )

    elif classified == "CONTRADICTORY":

        evidence.append(
            Evidence(
                source="Macro Context",
                category="macro",
                stance="CONTRADICTORY",
                reason=f"Macro regime classified as {regime}.",
                value=regime,
            )
        )

    elif classified == "MIXED":

        evidence.append(
            Evidence(
                source="Macro Context",
                category="macro",
                stance="MIXED",
                reason=f"Macro regime classified as {regime}.",
                value=regime,
            )
        )


def add_sentiment_evidence(
    evidence: List[Evidence],
    row: pd.Series,
) -> None:

    regime = detect_text(
        row,
        [
            "sentiment_regime",
            "regime",
        ],
    )

    score = detect_numeric(
        row,
        [
            "sentiment_score",
            "composite_sentiment_score",
            "score",
        ],
    )

    classified = classify_macro_regime(regime)

    if classified == "SUPPORTIVE":

        evidence.append(
            Evidence(
                source="Sentiment Engine",
                category="sentiment",
                stance="SUPPORTIVE",
                reason=f"Sentiment regime is {regime}.",
                value=score if score is not None else regime,
            )
        )

    elif classified == "CONTRADICTORY":

        evidence.append(
            Evidence(
                source="Sentiment Engine",
                category="sentiment",
                stance="CONTRADICTORY",
                reason=f"Sentiment regime is {regime}.",
                value=score if score is not None else regime,
            )
        )


def add_technical_evidence(
    evidence: List[Evidence],
    row: pd.Series,
) -> None:

    regime = detect_text(
        row,
        [
            "technical_regime",
            "trend_regime",
            "regime",
        ],
    )

    classified = classify_macro_regime(regime)

    if classified == "SUPPORTIVE":

        evidence.append(
            Evidence(
                source="Technical Intelligence",
                category="technical",
                stance="SUPPORTIVE",
                reason=f"Technical regime is {regime}.",
                value=regime,
            )
        )

    elif classified == "CONTRADICTORY":

        evidence.append(
            Evidence(
                source="Technical Intelligence",
                category="technical",
                stance="CONTRADICTORY",
                reason=f"Technical regime is {regime}.",
                value=regime,
            )
        )


def add_financial_stress_evidence(
    evidence: List[Evidence],
    row: pd.Series,
) -> None:

    regime = detect_text(
        row,
        [
            "financial_stress_regime",
            "stress_regime",
            "research_regime",
        ],
    )

    if regime is None:
        return

    normalized = normalize_name(regime)

    if normalized in {
        "low_research_stress",
        "low_stress",
    }:

        evidence.append(
            Evidence(
                source="Financial Stress",
                category="financial_stress",
                stance="SUPPORTIVE",
                reason=f"Financial stress regime is {regime}.",
                value=regime,
            )
        )

    elif normalized in {
        "high_research_stress",
        "high_stress",
        "crisis",
    }:

        evidence.append(
            Evidence(
                source="Financial Stress",
                category="financial_stress",
                stance="CONTRADICTORY",
                reason=f"Financial stress regime is {regime}.",
                value=regime,
            )
        )


def add_fed_evidence(
    evidence: List[Evidence],
    row: pd.Series,
) -> None:

    score = detect_numeric(
        row,
        [
            "fed_score",
            "fed_policy_score",
            "score",
        ],
    )

    regime = detect_text(
        row,
        [
            "fed_regime",
            "policy_regime",
        ],
    )

    if regime is not None:

        normalized = normalize_name(regime)

        if normalized in {
            "dovish",
            "accommodative",
            "supportive",
        }:

            evidence.append(
                Evidence(
                    source="Fed Intelligence",
                    category="fed",
                    stance="SUPPORTIVE",
                    reason=f"Fed regime is {regime}.",
                    value=regime,
                )
            )

        elif normalized in {
            "hawkish",
            "restrictive",
            "tight",
        }:

            evidence.append(
                Evidence(
                    source="Fed Intelligence",
                    category="fed",
                    stance="CONTRADICTORY",
                    reason=f"Fed regime is {regime}.",
                    value=regime,
                )
            )

        return

    # A numerical Fed score is treated only as a research
    # classification if the dataset explicitly provides one.
    if score is not None:

        if score >= 70:

            evidence.append(
                Evidence(
                    source="Fed Intelligence",
                    category="fed",
                    stance="SUPPORTIVE",
                    reason="Fed research score is in the supportive range.",
                    value=score,
                )
            )

        elif score <= 30:

            evidence.append(
                Evidence(
                    source="Fed Intelligence",
                    category="fed",
                    stance="CONTRADICTORY",
                    reason="Fed research score is in the contradictory range.",
                    value=score,
                )
            )


# ============================================================
# RESEARCH CONTEXT EXTRACTION
# ============================================================

def extract_research_context(
    path: Path,
) -> Tuple[pd.DataFrame, List[str]]:

    df = load_csv(path)

    ok, errors = validate_required_research_flags(
        df,
        "Research Context",
    )

    if not ok:
        return df, errors

    date_column = find_latest_date_column(df)

    if date_column is not None:

        dates = parse_dates(
            df,
            date_column,
        )

        if dates.isna().any():

            errors.append(
                "Research Context contains invalid dates."
            )

        valid_dates = dates.dropna()

        if not valid_dates.empty and not valid_dates.is_monotonic_increasing:

            errors.append(
                "Research Context dates are not monotonic increasing."
            )

    return df, errors


# ============================================================
# LAYER PRESENCE
# ============================================================

def layer_available(
    row: pd.Series,
    candidates: Iterable[str],
) -> bool:

    value = detect_bool(
        row,
        candidates,
    )

    if value is not None:
        return value

    # Fall back to numeric layer count.
    return False


def collect_layer_evidence(
    row: pd.Series,
) -> List[Evidence]:

    evidence: List[Evidence] = []

    # --------------------------------------------------------
    # Macro
    # --------------------------------------------------------

    macro_available = layer_available(
        row,
        [
            "macro_available",
            "has_macro",
            "macro_layer_available",
        ],
    )

    if macro_available:
        add_macro_evidence(
            evidence,
            row,
        )

        add_financial_stress_evidence(
            evidence,
            row,
        )

        add_fed_evidence(
            evidence,
            row,
        )

    # --------------------------------------------------------
    # Sentiment
    # --------------------------------------------------------

    sentiment_available = layer_available(
        row,
        [
            "sentiment_available",
            "has_sentiment",
            "sentiment_layer_available",
        ],
    )

    if sentiment_available:
        add_sentiment_evidence(
            evidence,
            row,
        )

    # --------------------------------------------------------
    # Technical
    # --------------------------------------------------------

    technical_available = layer_available(
        row,
        [
            "technical_available",
            "has_technical",
            "technical_layer_available",
        ],
    )

    if technical_available:
        add_technical_evidence(
            evidence,
            row,
        )

    return evidence


# ============================================================
# DECISION CLASSIFICATION
# ============================================================

def classify_evidence(
    evidence: List[Evidence],
) -> Dict[str, Any]:

    supportive = [
        item for item in evidence
        if item.stance == "SUPPORTIVE"
    ]

    contradictory = [
        item for item in evidence
        if item.stance == "CONTRADICTORY"
    ]

    mixed = [
        item for item in evidence
        if item.stance == "MIXED"
    ]

    evidence_count = (
        len(supportive)
        + len(contradictory)
        + len(mixed)
    )

    if evidence_count < MIN_EVIDENCE:

        state = "INSUFFICIENT_DATA"

    elif (
        len(supportive) > 0
        and len(contradictory) == 0
    ):

        state = "SUPPORTIVE"

    elif (
        len(contradictory) > 0
        and len(supportive) == 0
    ):

        state = "CONTRADICTORY"

    else:

        total_directional = (
            len(supportive)
            + len(contradictory)
        )

        if total_directional == 0:

            state = "MIXED"

        else:

            supportive_ratio = (
                len(supportive)
                / total_directional
            )

            contradictory_ratio = (
                len(contradictory)
                / total_directional
            )

            if supportive_ratio >= MAJORITY_RATIO:

                state = "SUPPORTIVE"

            elif contradictory_ratio >= MAJORITY_RATIO:

                state = "CONTRADICTORY"

            else:

                state = "MIXED"

    # --------------------------------------------------------
    # Descriptive evidence coverage.
    # This is NOT probability.
    # --------------------------------------------------------

    if evidence_count == 0:

        confidence = 0.0

    elif evidence_count >= HIGH_CONFIDENCE_EVIDENCE:

        confidence = 1.0

    else:

        confidence = round(
            evidence_count / HIGH_CONFIDENCE_EVIDENCE,
            4,
        )

    return {
        "state": state,
        "confidence": confidence,
        "evidence_count": evidence_count,
        "supportive_count": len(supportive),
        "contradictory_count": len(contradictory),
        "mixed_count": len(mixed),
    }


# ============================================================
# OUTPUT
# ============================================================

def build_output(
    context_date: Optional[str],
    evidence: List[Evidence],
    classification: Dict[str, Any],
    validation_errors: List[str],
) -> Dict[str, Any]:

    missing = []

    if not evidence:
        missing.append("usable research evidence")

    if validation_errors:
        missing.extend(validation_errors)

    output = {
        "engine": ENGINE_VERSION,
        "engine_version": ENGINE_VERSION,

        "as_of_date": context_date,

        "state": classification["state"],

        # This confidence describes evidence coverage only.
        "confidence": classification["confidence"],
        "confidence_type": "evidence_coverage",

        "evidence_count": classification["evidence_count"],
        "supportive_count": classification["supportive_count"],
        "contradictory_count": classification["contradictory_count"],
        "mixed_count": classification["mixed_count"],

        "missing": missing,

        "point_in_time_safe": len(validation_errors) == 0,
        "research_only": True,
        "decision_engine_enabled": True,

        "trading_signal": None,
        "forecast": None,
        "unified_decision": None,

        "execution": False,
        "broker_integration": False,
        "position_sizing": False,
        "stop_loss": None,
        "take_profit": None,

        "evidence": [
            item.to_dict()
            for item in evidence
        ],
    }

    return output


def write_outputs(
    output_dir: Path,
    output: Dict[str, Any],
    evidence: List[Evidence],
) -> None:

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = (
        output_dir
        / "decision_engine_research_v1.json"
    )

    csv_path = (
        output_dir
        / "decision_engine_research_v1.csv"
    )

    summary_path = (
        output_dir
        / "decision_engine_research_summary_v1.csv"
    )

    evidence_path = (
        output_dir
        / "decision_engine_research_evidence_v1.csv"
    )

    with json_path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False,
        )

    row = {
        key: value
        for key, value in output.items()
        if key != "evidence"
    }

    pd.DataFrame([row]).to_csv(
        csv_path,
        index=False,
    )

    pd.DataFrame(
        [
            {
                "as_of_date": output["as_of_date"],
                "state": output["state"],
                "confidence": output["confidence"],
                "evidence_count": output["evidence_count"],
                "supportive_count": output["supportive_count"],
                "contradictory_count": output["contradictory_count"],
                "mixed_count": output["mixed_count"],
                "point_in_time_safe": output["point_in_time_safe"],
                "research_only": output["research_only"],
                "decision_engine_enabled": output[
                    "decision_engine_enabled"
                ],
            }
        ]
    ).to_csv(
        summary_path,
        index=False,
    )

    pd.DataFrame(
        [
            item.to_dict()
            for item in evidence
        ]
    ).to_csv(
        evidence_path,
        index=False,
    )


# ============================================================
# VALIDATION
# ============================================================

def validate_output(
    output: Dict[str, Any],
) -> List[str]:

    errors: List[str] = []

    if output.get("research_only") is not True:
        errors.append(
            "research_only must be true."
        )

    if output.get("decision_engine_enabled") is not True:
        errors.append(
            "decision_engine_enabled must be true."
        )

    if output.get("execution") is not False:
        errors.append(
            "execution must be false."
        )

    if output.get("broker_integration") is not False:
        errors.append(
            "broker_integration must be false."
        )

    if output.get("position_sizing") is not False:
        errors.append(
            "position_sizing must be false."
        )

    if output.get("trading_signal") is not None:
        errors.append(
            "trading_signal must remain null."
        )

    if output.get("forecast") is not None:
        errors.append(
            "forecast must remain null."
        )

    if output.get("unified_decision") is not None:
        errors.append(
            "unified_decision must remain null."
        )

    allowed_states = {
        "SUPPORTIVE",
        "CONTRADICTORY",
        "MIXED",
        "INSUFFICIENT_DATA",
    }

    if output.get("state") not in allowed_states:
        errors.append(
            "Invalid Decision Engine state."
        )

    confidence = as_float(
        output.get("confidence")
    )

    if confidence is None:
        errors.append(
            "Invalid confidence."
        )
    elif not 0 <= confidence <= 1:
        errors.append(
            "Confidence must be between 0 and 1."
        )

    return errors


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description="US500 Macro Intelligence Decision Engine V1"
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Research Context CSV",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory",
    )

    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    print("=" * 68)
    print("US500 MACRO INTELLIGENCE — DECISION ENGINE V1")
    print("=" * 68)
    print("Research-only:", RESEARCH_ONLY)
    print("Decision Engine enabled:", DECISION_ENGINE_ENABLED)
    print()

    df, validation_errors = extract_research_context(
        input_path
    )

    date_column = find_latest_date_column(df)

    row = latest_row(
        df,
        date_column,
    )

    context_date = None

    if date_column is not None:

        dates = parse_dates(
            df,
            date_column,
        )

        valid_dates = dates.dropna()

        if not valid_dates.empty:

            context_date = (
                valid_dates.max()
                .date()
                .isoformat()
            )

    evidence = collect_layer_evidence(
        row
    )

    classification = classify_evidence(
        evidence
    )

    output = build_output(
        context_date=context_date,
        evidence=evidence,
        classification=classification,
        validation_errors=validation_errors,
    )

    output_validation_errors = validate_output(
        output
    )

    validation_errors.extend(
        output_validation_errors
    )

    if validation_errors:

        output["point_in_time_safe"] = False
        output["missing"] = validation_errors

        # A validation failure must never produce a
        # directional classification as if the evidence
        # were safe.
        output["state"] = "INSUFFICIENT_DATA"

    write_outputs(
        output_dir,
        output,
        evidence,
    )

    print()
    print("=" * 68)
    print("DECISION ENGINE RESULT")
    print("=" * 68)

    print(
        "Context date:",
        output["as_of_date"],
    )

    print(
        "State:",
        output["state"],
    )

    print(
        "Confidence:",
        output["confidence"],
    )

    print(
        "Evidence count:",
        output["evidence_count"],
    )

    print(
        "Supportive:",
        output["supportive_count"],
    )

    print(
        "Contradictory:",
        output["contradictory_count"],
    )

    print(
        "Mixed:",
        output["mixed_count"],
    )

    print(
        "PIT safe:",
        output["point_in_time_safe"],
    )

    print(
        "Research only:",
        output["research_only"],
    )

    print(
        "Trading signal:",
        output["trading_signal"],
    )

    print(
        "Forecast:",
        output["forecast"],
    )

    print(
        "Unified decision:",
        output["unified_decision"],
    )

    print()

    if validation_errors:

        print("=" * 68)
        print("VALIDATION ERRORS")
        print("=" * 68)

        for error in validation_errors:
            print("-", error)

        return 1

    print("=" * 68)
    print("DECISION ENGINE V1 VALIDATION PASSED")
    print("=" * 68)

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
