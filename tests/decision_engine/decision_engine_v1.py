#!/usr/bin/env python3
"""
US500 MACRO INTELLIGENCE
DECISION ENGINE V1

Research-only downstream classification.

This engine:
- consumes the point-in-time Research Context CSV
- extracts descriptive evidence from the actual Research Context schema
- never creates a trading signal
- never creates a forecast
- never executes trades
- never performs position sizing
- never creates SL/TP
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


ENGINE_VERSION = "decision-engine-v1"
RESEARCH_ONLY = True
DECISION_ENGINE_ENABLED = True

MIN_EVIDENCE = 2
MAJORITY_RATIO = 0.67
HIGH_CONFIDENCE_EVIDENCE = 4


# ============================================================
# BASIC HELPERS
# ============================================================

def die(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def is_missing(value: Any) -> bool:
    if value is None:
        return True

    try:
        if pd.isna(value):
            return True
    except Exception:
        pass

    return str(value).strip().lower() in {
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
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def normalize_name(value: Any) -> str:
    if is_missing(value):
        return ""

    return re.sub(
        r"[^a-z0-9]+",
        "_",
        str(value).strip().lower(),
    ).strip("_")


def normalized_columns(df: pd.DataFrame) -> Dict[str, str]:
    return {
        normalize_name(column): column
        for column in df.columns
    }


def find_column(
    df: pd.DataFrame,
    candidates: Iterable[str],
) -> Optional[str]:

    normalized = normalized_columns(df)

    for candidate in candidates:
        key = normalize_name(candidate)

        if key in normalized:
            return normalized[key]

    return None


def get_value(
    row: pd.Series,
    candidates: Iterable[str],
) -> Any:

    temp = pd.DataFrame([row])

    column = find_column(temp, candidates)

    if column is None:
        return None

    value = row[column]

    return None if is_missing(value) else value


def get_text(
    row: pd.Series,
    candidates: Iterable[str],
) -> Optional[str]:

    value = get_value(row, candidates)

    if value is None:
        return None

    return str(value).strip()


def get_number(
    row: pd.Series,
    candidates: Iterable[str],
) -> Optional[float]:

    return as_float(
        get_value(row, candidates)
    )


def get_bool(
    row: pd.Series,
    candidates: Iterable[str],
) -> Optional[bool]:

    return as_bool(
        get_value(row, candidates)
    )


def date_column(
    df: pd.DataFrame,
) -> Optional[str]:

    return find_column(
        df,
        [
            "context_date",
            "asof_date",
            "as_of_date",
            "observation_date",
            "availability_date",
            "date",
        ],
    )


def latest_row(
    df: pd.DataFrame,
    column: Optional[str],
) -> pd.Series:

    if df.empty:
        die("Input Research Context CSV is empty.")

    if column is None:
        return df.iloc[-1]

    dates = pd.to_datetime(
        df[column],
        errors="coerce",
    )

    valid = dates.notna()

    if not valid.any():
        return df.iloc[-1]

    latest_index = dates[valid].idxmax()

    return df.loc[latest_index]


# ============================================================
# INPUT VALIDATION
# ============================================================

def validate_input(
    df: pd.DataFrame,
) -> List[str]:

    errors: List[str] = []

    if df.empty:
        errors.append(
            "Research Context CSV is empty."
        )
        return errors

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
            "Research Context: "
            "point_in_time_safe field is missing."
        )

    else:

        values = df[pit_column].map(as_bool)

        if values.isna().any():

            errors.append(
                "Research Context: invalid "
                "point_in_time_safe values."
            )

        elif not bool(values.all()):

            errors.append(
                "Research Context: point_in_time_safe "
                "is not true for every row."
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
                "Research Context: invalid "
                "research_only values."
            )

        elif not bool(values.all()):

            errors.append(
                "Research Context: research_only "
                "is not true for every row."
            )

    dcol = date_column(df)

    if dcol is None:

        errors.append(
            "Research Context: no usable "
            "context date column was found."
        )

    else:

        dates = pd.to_datetime(
            df[dcol],
            errors="coerce",
        )

        if dates.isna().any():

            errors.append(
                "Research Context contains invalid dates."
            )

        valid = dates.dropna()

        if (
            not valid.empty
            and not valid.is_monotonic_increasing
        ):

            errors.append(
                "Research Context dates are not "
                "monotonic increasing."
            )

    return errors


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


def add(
    evidence: List[Evidence],
    source: str,
    category: str,
    stance: str,
    reason: str,
    value: Any = None,
) -> None:

    evidence.append(
        Evidence(
            source=source,
            category=category,
            stance=stance,
            reason=reason,
            value=value,
        )
    )


# ============================================================
# REGIME CLASSIFICATION
# ============================================================

def classify_regime(
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
        "dovish",
        "accommodative",
        "supportive",
        "strong_bullish",
    }

    contradictory = {
        "bearish",
        "negative",
        "contraction",
        "recession",
        "high_research_stress",
        "high_stress",
        "extreme_research_stress",
        "crisis",
        "stagflation",
        "hawkish",
        "restrictive",
        "tight",
        "strong_bearish",
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


# ============================================================
# LAYER AVAILABILITY
# ============================================================

def layer_is_available(
    row: pd.Series,
    names: Iterable[str],
) -> bool:

    value = get_bool(
        row,
        names,
    )

    if value is not None:
        return value

    return False


# ============================================================
# MACRO EVIDENCE
# ============================================================

def collect_macro_evidence(
    row: pd.Series,
    evidence: List[Evidence],
) -> None:

    # --------------------------------------------------------
    # Economic Intelligence
    # --------------------------------------------------------

    economic_regime = get_text(
        row,
        [
            "macro_economic_regime",
            "economic_regime",
            "macro_regime",
        ],
    )

    economic_classification = classify_regime(
        economic_regime
    )

    if economic_classification is not None:

        add(
            evidence,
            "Macro Context",
            "economic",
            economic_classification,
            (
                "Economic regime is "
                f"{economic_regime}."
            ),
            economic_regime,
        )

    # --------------------------------------------------------
    # Financial Stress
    # --------------------------------------------------------

    financial_regime = get_text(
        row,
        [
            "macro_financial_stress_regime",
            "financial_stress_regime",
            "stress_regime",
        ],
    )

    financial_classification = classify_regime(
        financial_regime
    )

    if financial_classification is not None:

        add(
            evidence,
            "Financial Stress",
            "financial_stress",
            financial_classification,
            (
                "Financial stress regime is "
                f"{financial_regime}."
            ),
            financial_regime,
        )

    # --------------------------------------------------------
    # Fed Intelligence
    # --------------------------------------------------------

    fed_regime = get_text(
        row,
        [
            "macro_fed_regime",
            "fed_regime",
            "policy_regime",
        ],
    )

    if fed_regime is not None:

        fed_classification = classify_regime(
            fed_regime
        )

        if fed_classification is not None:

            add(
                evidence,
                "Fed Intelligence",
                "fed",
                fed_classification,
                (
                    "Fed regime is "
                    f"{fed_regime}."
                ),
                fed_regime,
            )

    else:

        fed_score = get_number(
            row,
            [
                "macro_fed_score",
                "fed_score",
                "fed_policy_score",
            ],
        )

        if fed_score is not None:

            if fed_score >= 70:

                add(
                    evidence,
                    "Fed Intelligence",
                    "fed",
                    "SUPPORTIVE",
                    (
                        "Fed research score "
                        "is in the high range."
                    ),
                    fed_score,
                )

            elif fed_score <= 30:

                add(
                    evidence,
                    "Fed Intelligence",
                    "fed",
                    "CONTRADICTORY",
                    (
                        "Fed research score "
                        "is in the low range."
                    ),
                    fed_score,
                )


# ============================================================
# SENTIMENT EVIDENCE
# ============================================================

def collect_sentiment_evidence(
    row: pd.Series,
    evidence: List[Evidence],
) -> None:

    regime = get_text(
        row,
        [
            "sentiment_unified_sentiment_regime",
            "sentiment_research_regime",
            "unified_sentiment_regime",
            "sentiment_regime",
        ],
    )

    classification = classify_regime(
        regime
    )

    if classification is not None:

        add(
            evidence,
            "Sentiment Engine",
            "sentiment",
            classification,
            (
                "Unified sentiment regime is "
                f"{regime}."
            ),
            regime,
        )


# ============================================================
# TECHNICAL EVIDENCE
# ============================================================

def collect_technical_evidence(
    row: pd.Series,
    evidence: List[Evidence],
) -> None:

    regime = get_text(
        row,
        [
            "technical_technical_regime",
            "technical_regime",
            "technical_trend_structure",
            "trend_regime",
        ],
    )

    classification = classify_regime(
        regime
    )

    if classification is not None:

        add(
            evidence,
            "Technical Intelligence",
            "technical",
            classification,
            (
                "Technical research regime is "
                f"{regime}."
            ),
            regime,
        )


# ============================================================
# COLLECT ALL EVIDENCE
# ============================================================

def collect_evidence(
    row: pd.Series,
) -> List[Evidence]:

    evidence: List[Evidence] = []

    macro_available = layer_is_available(
        row,
        [
            "macro_available",
            "has_macro",
            "macro_layer_available",
        ],
    )

    sentiment_available = layer_is_available(
        row,
        [
            "sentiment_available",
            "has_sentiment",
            "sentiment_layer_available",
        ],
    )

    technical_available = layer_is_available(
        row,
        [
            "technical_available",
            "has_technical",
            "technical_layer_available",
        ],
    )

    if macro_available:

        collect_macro_evidence(
            row,
            evidence,
        )

    if sentiment_available:

        collect_sentiment_evidence(
            row,
            evidence,
        )

    if technical_available:

        collect_technical_evidence(
            row,
            evidence,
        )

    return evidence


# ============================================================
# DECISION-ENGINE DESCRIPTIVE CLASSIFICATION
# ============================================================

def classify_evidence(
    evidence: List[Evidence],
) -> Dict[str, Any]:

    supportive = [
        item
        for item in evidence
        if item.stance == "SUPPORTIVE"
    ]

    contradictory = [
        item
        for item in evidence
        if item.stance == "CONTRADICTORY"
    ]

    mixed = [
        item
        for item in evidence
        if item.stance == "MIXED"
    ]

    evidence_count = len(evidence)

    if evidence_count < MIN_EVIDENCE:

        state = "INSUFFICIENT_DATA"

    elif supportive and not contradictory:

        state = "SUPPORTIVE"

    elif contradictory and not supportive:

        state = "CONTRADICTORY"

    else:

        directional = (
            len(supportive)
            + len(contradictory)
        )

        if directional == 0:

            state = "MIXED"

        else:

            supportive_ratio = (
                len(supportive)
                / directional
            )

            contradictory_ratio = (
                len(contradictory)
                / directional
            )

            if supportive_ratio >= MAJORITY_RATIO:

                state = "SUPPORTIVE"

            elif contradictory_ratio >= MAJORITY_RATIO:

                state = "CONTRADICTORY"

            else:

                state = "MIXED"

    # --------------------------------------------------------
    # IMPORTANT:
    # Confidence is evidence coverage only.
    # It is NOT probability and NOT trade confidence.
    # --------------------------------------------------------

    if evidence_count >= HIGH_CONFIDENCE_EVIDENCE:

        confidence = 1.0

    elif evidence_count > 0:

        confidence = round(
            evidence_count
            / HIGH_CONFIDENCE_EVIDENCE,
            4,
        )

    else:

        confidence = 0.0

    return {
        "state": state,
        "confidence": confidence,
        "evidence_count": evidence_count,
        "supportive_count": len(supportive),
        "contradictory_count": len(contradictory),
        "mixed_count": len(mixed),
    }


# ============================================================
# OUTPUT BUILD
# ============================================================

def build_output(
    context_date: Optional[str],
    evidence: List[Evidence],
    classification: Dict[str, Any],
    validation_errors: List[str],
) -> Dict[str, Any]:

    missing: List[str] = []

    if not evidence:

        missing.append(
            "usable research evidence"
        )

    missing.extend(validation_errors)

    return {
        "engine": ENGINE_VERSION,
        "engine_version": ENGINE_VERSION,

        "as_of_date": context_date,

        "state": classification["state"],

        "confidence": classification["confidence"],

        "confidence_type": "evidence_coverage",

        "evidence_count": classification[
            "evidence_count"
        ],

        "supportive_count": classification[
            "supportive_count"
        ],

        "contradictory_count": classification[
            "contradictory_count"
        ],

        "mixed_count": classification[
            "mixed_count"
        ],

        "missing": missing,

        "point_in_time_safe": (
            len(validation_errors) == 0
        ),

        "research_only": True,

        "decision_engine_enabled": True,

        # ----------------------------------------------------
        # Explicit research-only protections
        # ----------------------------------------------------

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


# ============================================================
# WRITE OUTPUT FILES
# ============================================================

def write_outputs(
    output_dir: Path,
    output: Dict[str, Any],
    evidence: List[Evidence],
) -> None:

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # JSON
    # --------------------------------------------------------

    json_path = (
        output_dir
        / "decision_engine_research_v1.json"
    )

    json_path.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Main CSV
    # --------------------------------------------------------

    flat_output = {
        key: value
        for key, value in output.items()
        if key != "evidence"
    }

    pd.DataFrame(
        [flat_output]
    ).to_csv(
        output_dir
        / "decision_engine_research_v1.csv",
        index=False,
    )

    # --------------------------------------------------------
    # Summary CSV
    # --------------------------------------------------------

    pd.DataFrame(
        [
            {
                "as_of_date": output[
                    "as_of_date"
                ],

                "state": output[
                    "state"
                ],

                "confidence": output[
                    "confidence"
                ],

                "evidence_count": output[
                    "evidence_count"
                ],

                "supportive_count": output[
                    "supportive_count"
                ],

                "contradictory_count": output[
                    "contradictory_count"
                ],

                "mixed_count": output[
                    "mixed_count"
                ],

                "point_in_time_safe": output[
                    "point_in_time_safe"
                ],

                "research_only": output[
                    "research_only"
                ],

                "decision_engine_enabled": output[
                    "decision_engine_enabled"
                ],
            }
        ]
    ).to_csv(
        output_dir
        / "decision_engine_research_summary_v1.csv",
        index=False,
    )

    # --------------------------------------------------------
    # Evidence CSV
    # --------------------------------------------------------

    pd.DataFrame(
        [
            item.to_dict()
            for item in evidence
        ]
    ).to_csv(
        output_dir
        / "decision_engine_research_evidence_v1.csv",
        index=False,
    )


# ============================================================
# OUTPUT VALIDATION
# ============================================================

def validate_output(
    output: Dict[str, Any],
) -> List[str]:

    errors: List[str] = []

    if output["research_only"] is not True:

        errors.append(
            "research_only must be true."
        )

    if (
        output["decision_engine_enabled"]
        is not True
    ):

        errors.append(
            "decision_engine_enabled "
            "must be true."
        )

    if output["execution"] is not False:

        errors.append(
            "execution must be false."
        )

    if (
        output["broker_integration"]
        is not False
    ):

        errors.append(
            "broker_integration "
            "must be false."
        )

    if output["position_sizing"] is not False:

        errors.append(
            "position_sizing must be false."
        )

    if output["trading_signal"] is not None:

        errors.append(
            "trading_signal must remain null."
        )

    if output["forecast"] is not None:

        errors.append(
            "forecast must remain null."
        )

    if output["unified_decision"] is not None:

        errors.append(
            "unified_decision must remain null."
        )

    if output["stop_loss"] is not None:

        errors.append(
            "stop_loss must remain null."
        )

    if output["take_profit"] is not None:

        errors.append(
            "take_profit must remain null."
        )

    if output["state"] not in {
        "SUPPORTIVE",
        "CONTRADICTORY",
        "MIXED",
        "INSUFFICIENT_DATA",
    }:

        errors.append(
            "Invalid Decision Engine state."
        )

    confidence = as_float(
        output["confidence"]
    )

    if (
        confidence is None
        or not 0 <= confidence <= 1
    ):

        errors.append(
            "Confidence must be between 0 and 1."
        )

    return errors


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "US500 Macro Intelligence "
            "Decision Engine V1"
        )
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

    input_path = Path(
        args.input
    )

    output_dir = Path(
        args.output_dir
    )

    if not input_path.is_file():

        die(
            f"Input path is not a file: "
            f"{input_path}"
        )

    print("=" * 70)
    print(
        "US500 MACRO INTELLIGENCE "
        "— DECISION ENGINE V1"
    )
    print("=" * 70)

    print(
        "Research-only:",
        RESEARCH_ONLY,
    )

    print(
        "Decision Engine enabled:",
        DECISION_ENGINE_ENABLED,
    )

    print()

    # --------------------------------------------------------
    # READ INPUT
    # --------------------------------------------------------

    try:

        df = pd.read_csv(
            input_path
        )

    except Exception as exc:

        die(
            f"Could not read "
            f"{input_path}: {exc}"
        )

    # --------------------------------------------------------
    # VALIDATE INPUT
    # --------------------------------------------------------

    validation_errors = validate_input(
        df
    )

    dcol = date_column(
        df
    )

    row = latest_row(
        df,
        dcol,
    )

    context_date = None

    if dcol is not None:

        dates = pd.to_datetime(
            df[dcol],
            errors="coerce",
        ).dropna()

        if not dates.empty:

            context_date = (
                dates.max()
                .date()
                .isoformat()
            )

    print(
        "Input rows:",
        len(df),
    )

    print(
        "Input columns:",
        len(df.columns),
    )

    print(
        "Date column:",
        dcol,
    )

    print(
        "Latest context date:",
        context_date,
    )

    # --------------------------------------------------------
    # DISPLAY LAYER AVAILABILITY
    # --------------------------------------------------------

    print()
    print(
        "Research Context layer availability:"
    )

    macro_available = get_bool(
        row,
        ["macro_available"],
    )

    sentiment_available = get_bool(
        row,
        ["sentiment_available"],
    )

    technical_available = get_bool(
        row,
        ["technical_available"],
    )

    print(
        "  macro_available:",
        macro_available,
    )

    print(
        "  sentiment_available:",
        sentiment_available,
    )

    print(
        "  technical_available:",
        technical_available,
    )

    # --------------------------------------------------------
    # COLLECT EVIDENCE
    # --------------------------------------------------------

    evidence = collect_evidence(
        row
    )

    classification = classify_evidence(
        evidence
    )

    # --------------------------------------------------------
    # BUILD OUTPUT
    # --------------------------------------------------------

    output = build_output(
        context_date=context_date,
        evidence=evidence,
        classification=classification,
        validation_errors=validation_errors,
    )

    # --------------------------------------------------------
    # VALIDATE OUTPUT
    # --------------------------------------------------------

    output_errors = validate_output(
        output
    )

    validation_errors.extend(
        output_errors
    )

    if validation_errors:

        output[
            "point_in_time_safe"
        ] = False

        output[
            "state"
        ] = "INSUFFICIENT_DATA"

        output[
            "missing"
        ] = validation_errors

    # --------------------------------------------------------
    # WRITE OUTPUTS
    # --------------------------------------------------------

    write_outputs(
        output_dir=output_dir,
        output=output,
        evidence=evidence,
    )

    # --------------------------------------------------------
    # PRINT RESULT
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("DECISION ENGINE RESULT")
    print("=" * 70)

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

    # --------------------------------------------------------
    # EVIDENCE DISPLAY
    # --------------------------------------------------------

    print()
    print("Evidence:")

    if not evidence:

        print(
            "  No usable evidence found."
        )

    else:

        for item in evidence:

            print(
                f"  [{item.stance}] "
                f"{item.source} / "
                f"{item.category}: "
                f"{item.reason}"
            )

    # --------------------------------------------------------
    # RESEARCH-ONLY SAFETY DISPLAY
    # --------------------------------------------------------

    print()
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

    print(
        "Execution:",
        output["execution"],
    )

    print(
        "Position sizing:",
        output["position_sizing"],
    )

    print(
        "Stop loss:",
        output["stop_loss"],
    )

    print(
        "Take profit:",
        output["take_profit"],
    )

    # --------------------------------------------------------
    # FAIL ONLY ON REAL VALIDATION ERRORS
    # --------------------------------------------------------

    if validation_errors:

        print()
        print("=" * 70)
        print(
            "VALIDATION ERRORS"
        )
        print("=" * 70)

        for error in validation_errors:

            print(
                "-",
                error,
            )

        return 1

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "DECISION ENGINE V1 "
        "VALIDATION PASSED"
    )
    print("=" * 70)

    return 0


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
