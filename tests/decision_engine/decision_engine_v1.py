#!/usr/bin/env python3

"""
US500 MACRO INTELLIGENCE — DECISION ENGINE V1

Research-only.
No trade execution.
No BUY/SELL signals.
No forecasting.

Purpose:
    Combine the latest available Research Context layers into
    one descriptive decision-context snapshot.

Important:
    - Point-in-time aware
    - Research-only
    - No execution
    - No trading signal generation
    - No forecasting
    - No forced interpretation of numeric Fed score
"""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


# ============================================================
# CONSTANTS
# ============================================================

STATES = {
    "BULLISH_CONTEXT",
    "BEARISH_CONTEXT",
    "NEUTRAL_CONTEXT",
    "CONFLICTED",
    "INSUFFICIENT_DATA",
}

TRUE_VALUES = {
    "1",
    "true",
    "yes",
    "y",
    "pass",
    "passed",
}

FALSE_VALUES = {
    "0",
    "false",
    "no",
    "n",
    "fail",
    "failed",
}


# ============================================================
# ARGUMENTS
# ============================================================

def parse_args():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--artifacts-dir",
        default="artifacts",
    )

    parser.add_argument(
        "--output",
        default="decision_engine_research_v1.csv",
    )

    parser.add_argument(
        "--summary-output",
        default="decision_engine_summary_v1.csv",
    )

    return parser.parse_args()


# ============================================================
# NORMALIZATION
# ============================================================

def nk(value):

    return (
        str(value or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def truthy(value):

    if value is None:
        return None

    s = str(value).strip().lower()

    if s in TRUE_VALUES:
        return True

    if s in FALSE_VALUES:
        return False

    return None


def safe_float(value):

    if value is None:
        return None

    try:

        value = float(value)

        if value != value:
            return None

        return value

    except (
        TypeError,
        ValueError,
    ):
        return None


# ============================================================
# CSV
# ============================================================

def read_csv(path):

    with open(
        path,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:

        return list(
            csv.DictReader(f)
        )


# ============================================================
# DATE
# ============================================================

def date_field(row):

    for key in (
        "asof_date",
        "date",
        "context_date",
        "event_date",
        "reported_date",
        "observation_date",
    ):

        if row.get(key):
            return row[key]

    return ""


# ============================================================
# DISCOVERY
# ============================================================

def discover(root):

    output = set()

    for path in glob.glob(
        os.path.join(
            root,
            "**",
            "*.csv",
        ),
        recursive=True,
    ):

        real_path = os.path.realpath(path)

        if (
            os.path.basename(real_path)
            .startswith("decision_engine_")
        ):
            continue

        if "/.git/" in real_path:
            continue

        output.add(real_path)

    return sorted(output)


# ============================================================
# EXTRACT RESEARCH CONTEXT
# ============================================================

def extract(row):

    low = {
        nk(key): value
        for key, value in row.items()
    }

    aliases = {

        # ----------------------------------------------------
        # Economic
        # ----------------------------------------------------

        "economic_regime": [
            "economic_regime",
            "growth_regime",
            "economic_context",
        ],

        # ----------------------------------------------------
        # Fed
        #
        # IMPORTANT:
        # fed_score is accepted as evidence.
        # It is NOT converted into a fabricated
        # DOVISH/Hawkish regime.
        # ----------------------------------------------------

        "fed_regime": [
            "fed_regime",
            "fed_context",
            "monetary_regime",
        ],

        # ----------------------------------------------------
        # Financial Stress
        # ----------------------------------------------------

        "financial_stress_regime": [
            "financial_stress_regime",
            "research_regime",
            "stress_regime",
        ],

        # ----------------------------------------------------
        # Sentiment
        # ----------------------------------------------------

        "sentiment_regime": [
            "sentiment_regime",
            "sentiment_context",
        ],

        # ----------------------------------------------------
        # Technical
        # ----------------------------------------------------

        "technical_regime": [
            "technical_regime",
            "technical_context",
        ],
    }

    output = {}

    # ========================================================
    # TEXTUAL REGIMES
    # ========================================================

    for target, keys in aliases.items():

        for key in keys:

            normalized_key = nk(key)

            if (
                normalized_key in low
                and str(
                    low[normalized_key]
                ).strip()
            ):

                output[target] = (
                    low[normalized_key]
                )

                break

    # ========================================================
    # FED SCORE
    # ========================================================

    if "fed_score" in low:

        fed_score = safe_float(
            low["fed_score"]
        )

        if fed_score is not None:

            output["fed_score"] = fed_score

    # ========================================================
    # OTHER CONTROL FIELDS
    # ========================================================

    for key in (
        "point_in_time_safe",
        "data_quality",
        "availability_date",
    ):

        normalized_key = nk(key)

        if normalized_key in low:

            output[key] = (
                low[normalized_key]
            )

    return output


# ============================================================
# LOCATE LATEST EVIDENCE
# ============================================================

def locate(paths):

    keys = [
        "economic_regime",
        "fed_regime",
        "financial_stress_regime",
        "sentiment_regime",
        "technical_regime",
    ]

    candidates = {
        key: []
        for key in keys
    }

    fed_score_candidates = []

    for path in paths:

        try:

            rows = read_csv(path)

        except Exception:

            continue

        for row in rows:

            extracted = extract(row)

            # ------------------------------------------------
            # Textual layers
            # ------------------------------------------------

            for key in keys:

                if key in extracted:

                    candidates[key].append(
                        (
                            date_field(row),
                            path,
                            row,
                            extracted,
                        )
                    )

            # ------------------------------------------------
            # Fed score
            # ------------------------------------------------

            if "fed_score" in extracted:

                fed_score_candidates.append(
                    (
                        date_field(row),
                        path,
                        row,
                        extracted,
                    )
                )

    result = {}

    # ========================================================
    # LATEST TEXTUAL EVIDENCE
    # ========================================================

    for key, items in candidates.items():

        if not items:
            continue

        items.sort(
            key=lambda item: (
                item[0],
                item[1],
            )
        )

        date_value, path, row, extracted = (
            items[-1]
        )

        result[key] = {

            "value":
                extracted.get(
                    key,
                    "",
                ),

            "source_file":
                path,

            "source_date":
                date_value,

            "point_in_time_safe":
                extracted.get(
                    "point_in_time_safe",
                    "",
                ),

            "data_quality":
                extracted.get(
                    "data_quality",
                    "",
                ),
        }

    # ========================================================
    # LATEST FED SCORE
    # ========================================================

    if fed_score_candidates:

        fed_score_candidates.sort(
            key=lambda item: (
                item[0],
                item[1],
            )
        )

        (
            date_value,
            path,
            row,
            extracted,
        ) = fed_score_candidates[-1]

        result["fed_score"] = {

            "value":
                extracted[
                    "fed_score"
                ],

            "source_file":
                path,

            "source_date":
                date_value,

            "point_in_time_safe":
                extracted.get(
                    "point_in_time_safe",
                    "",
                ),

            "data_quality":
                extracted.get(
                    "data_quality",
                    "",
                ),
        }

    return result


# ============================================================
# SCORING
# ============================================================

def score(name, value):

    value_normalized = nk(value)
    name_normalized = nk(name)

    if not value_normalized:

        return None

    # ========================================================
    # ECONOMIC
    # ========================================================

    if "economic" in name_normalized:

        if any(
            item in value_normalized
            for item in (
                "expansion",
                "strong",
                "positive",
                "improving",
            )
        ):

            return 1

        if any(
            item in value_normalized
            for item in (
                "contraction",
                "weak",
                "negative",
                "deteriorating",
                "recession",
            )
        ):

            return -1

    # ========================================================
    # FED
    # ========================================================

    if (
        "fed" in name_normalized
        or "monetary" in name_normalized
    ):

        if any(
            item in value_normalized
            for item in (
                "dovish",
                "accommodative",
                "easing",
            )
        ):

            return 1

        if any(
            item in value_normalized
            for item in (
                "hawkish",
                "restrictive",
                "tightening",
            )
        ):

            return -1

    # ========================================================
    # FINANCIAL STRESS
    # ========================================================

    if (
        "stress" in name_normalized
        or "financial" in name_normalized
    ):

        if any(
            item in value_normalized
            for item in (
                "low",
                "normal",
                "calm",
            )
        ):

            return 1

        if any(
            item in value_normalized
            for item in (
                "elevated",
                "high",
                "extreme",
                "stress",
            )
        ):

            return -1

    # ========================================================
    # SENTIMENT
    # ========================================================

    if "sentiment" in name_normalized:

        if any(
            item in value_normalized
            for item in (
                "positive",
                "bullish",
                "optimistic",
                "risk_on",
            )
        ):

            return 1

        if any(
            item in value_normalized
            for item in (
                "negative",
                "bearish",
                "pessimistic",
                "risk_off",
            )
        ):

            return -1

    # ========================================================
    # TECHNICAL
    # ========================================================

    if "technical" in name_normalized:

        if any(
            item in value_normalized
            for item in (
                "bullish",
                "uptrend",
                "positive",
                "strong",
            )
        ):

            return 1

        if any(
            item in value_normalized
            for item in (
                "bearish",
                "downtrend",
                "negative",
                "weak",
            )
        ):

            return -1

    return 0


# ============================================================
# BUILD DECISION CONTEXT
# ============================================================

def build(layers):

    keys = [
        "economic_regime",
        "fed_regime",
        "financial_stress_regime",
        "sentiment_regime",
        "technical_regime",
    ]

    # ========================================================
    # VALUES
    # ========================================================

    values = {

        key:
            layers.get(
                key,
                {},
            ).get(
                "value",
                "",
            )

        for key in keys
    }

    # ========================================================
    # FED FALLBACK
    #
    # If textual Fed regime is unavailable but fed_score exists,
    # retain Fed as available research evidence without assigning
    # an artificial directional regime.
    # ========================================================

    fed_score_available = (
        "fed_score" in layers
    )

    if (
        not values["fed_regime"]
        and fed_score_available
    ):

        values["fed_regime"] = (
            "FED_SCORE_AVAILABLE"
        )

    # ========================================================
    # EVIDENCE SOURCES
    # ========================================================

    evidence = {}

    for key in keys:

        evidence[
            key.replace(
                "_regime",
                "_evidence",
            )
        ] = layers.get(
            key,
            {},
        ).get(
            "source_file",
            "",
        )

    # ========================================================
    # FED SCORE EVIDENCE
    # ========================================================

    if fed_score_available:

        evidence["fed_score_evidence"] = (
            layers["fed_score"].get(
                "source_file",
                "",
            )
        )

    # ========================================================
    # DATES
    # ========================================================

    dates = []

    for key in keys:

        date_value = (
            layers.get(
                key,
                {},
            ).get(
                "source_date",
                "",
            )
        )

        if date_value:

            dates.append(
                date_value
            )

    if fed_score_available:

        fed_score_date = (
            layers["fed_score"].get(
                "source_date",
                "",
            )
        )

        if fed_score_date:

            dates.append(
                fed_score_date
            )

    # ========================================================
    # SCORES
    # ========================================================

    scores = {}

    for key in keys:

        value = values[key]

        # ----------------------------------------------------
        # Fed score availability is evidence, but without a
        # documented directional mapping it remains neutral.
        # ----------------------------------------------------

        if (
            key == "fed_regime"
            and value == "FED_SCORE_AVAILABLE"
        ):

            scores[key] = 0

            continue

        calculated = score(
            key,
            value,
        )

        if calculated is not None:

            scores[key] = calculated

    # ========================================================
    # COUNTS
    # ========================================================

    positive = sum(
        value > 0
        for value in scores.values()
    )

    negative = sum(
        value < 0
        for value in scores.values()
    )

    neutral = sum(
        value == 0
        for value in scores.values()
    )

    missing = (
        5
        - len(scores)
    )

    # ========================================================
    # DECISION STATE
    #
    # Descriptive context only.
    # ========================================================

    if len(scores) < 2:

        state = (
            "INSUFFICIENT_DATA"
        )

    elif (
        positive >= 3
        and negative == 0
    ):

        state = (
            "BULLISH_CONTEXT"
        )

    elif (
        negative >= 3
        and positive == 0
    ):

        state = (
            "BEARISH_CONTEXT"
        )

    elif (
        positive > 0
        and negative > 0
    ):

        state = (
            "CONFLICTED"
        )

    else:

        state = (
            "NEUTRAL_CONTEXT"
        )

    # ========================================================
    # CONFIDENCE
    # ========================================================

    confidence = (

        round(
            max(
                positive,
                negative,
                neutral,
            )
            / len(scores),
            4,
        )

        if scores

        else 0.0
    )

    # ========================================================
    # PIT SAFETY
    # ========================================================

    pit_values = []

    for key in keys:

        if key in layers:

            value = truthy(
                layers[key].get(
                    "point_in_time_safe",
                    "",
                )
            )

            if value is not None:

                pit_values.append(
                    value
                )

    if fed_score_available:

        fed_pit = truthy(
            layers["fed_score"].get(
                "point_in_time_safe",
                "",
            )
        )

        if fed_pit is not None:

            pit_values.append(
                fed_pit
            )

    if (
        pit_values
        and all(pit_values)
    ):

        pit = "PASS"

    elif not pit_values:

        pit = "REVIEW"

    else:

        pit = "FAIL"

    # ========================================================
    # DATA QUALITY
    # ========================================================

    if missing >= 3:

        quality = (
            "INSUFFICIENT"
        )

    elif missing:

        quality = (
            "REVIEW"
        )

    else:

        quality = (
            "PASS"
        )

    # ========================================================
    # RESULT
    # ========================================================

    record = {

        "asof_date":
            max(dates)
            if dates
            else datetime.now(
                timezone.utc
            ).date().isoformat(),

        **values,

        **evidence,

        "fed_score":
            (
                layers["fed_score"].get(
                    "value",
                    "",
                )
                if fed_score_available
                else ""
            ),

        "fed_score_available":
            "TRUE"
            if fed_score_available
            else "FALSE",

        "evidence_count":
            len(scores),

        "supportive_count":
            positive,

        "contradictory_count":
            negative,

        "neutral_count":
            neutral,

        "missing_count":
            missing,

        "decision_state":
            state,

        "decision_confidence":
            confidence,

        "conflict_flag":
            "YES"
            if state == "CONFLICTED"
            else "NO",

        "data_quality":
            quality,

        "point_in_time_safe":
            pit,

        "research_only":
            "TRUE",
    }

    record["record_id"] = (
        hashlib.sha256(
            json.dumps(
                record,
                sort_keys=True,
            ).encode()
        ).hexdigest()[:16]
    )

    return record


# ============================================================
# WRITE CSV
# ============================================================

def write_csv(
    path,
    rows,
):

    Path(path).parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=list(
                rows[0]
            ),
        )

        writer.writeheader()

        writer.writerows(
            rows
        )


# ============================================================
# MAIN
# ============================================================

def main():

    args = parse_args()

    paths = discover(
        args.artifacts_dir
    )

    layers = locate(
        paths
    )

    record = build(
        layers
    )

    write_csv(
        args.output,
        [record],
    )

    summary = {

        "run_timestamp_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "decision_state":
            record[
                "decision_state"
            ],

        "decision_confidence":
            record[
                "decision_confidence"
            ],

        "evidence_count":
            record[
                "evidence_count"
            ],

        "supportive_count":
            record[
                "supportive_count"
            ],

        "contradictory_count":
            record[
                "contradictory_count"
            ],

        "neutral_count":
            record[
                "neutral_count"
            ],

        "missing_count":
            record[
                "missing_count"
            ],

        "fed_score":
            record[
                "fed_score"
            ],

        "fed_score_available":
            record[
                "fed_score_available"
            ],

        "point_in_time_safe":
            record[
                "point_in_time_safe"
            ],

        "data_quality":
            record[
                "data_quality"
            ],

        "research_only":
            "TRUE",

        "source_csv_count":
            len(paths),
    }

    write_csv(
        args.summary_output,
        [summary],
    )

    print(
        "DECISION ENGINE V1"
    )

    print(
        json.dumps(
            summary,
            indent=2,
        )
    )

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    raise SystemExit(
        main()
    )
