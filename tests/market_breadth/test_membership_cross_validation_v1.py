#!/usr/bin/env python3
"""
Market Breadth — S&P 500 Membership Cross-Validation v2

Purpose
-------
Research-only validation of reconstructed historical S&P 500 membership.

Sources
-------
1. fja05680/sp500
   Primary historical reference.

2. hanshof/sp500_constituents
   Independent historical reconstruction.

3. chinobing/historical_sp500_constituents
   Current/auto-renewed reconstruction.

4. pitindex
   Historical validation support only.
   IMPORTANT: pitindex uses fja05680 as a primary historical seed,
   therefore it is NOT treated as an independent source.

Classification
--------------
MATCH
    All direct sources agree.

EXPLAINABLE
    Small difference that is explainable by constituent-count/ticker
    representation differences.

PIT_SUPPORTED_DISAGREEMENT
    Direct sources disagree, but pitindex supports one of them.

UNRESOLVED_CONFLICT
    Direct sources disagree and pitindex does not support either
    side sufficiently.

Research status
---------------
This test does NOT claim PIT-perfect membership.

point_in_time_reconstructed = TRUE
membership_source = FREE_PUBLIC_RECONSTRUCTION
membership_quality = RESEARCH_GRADE
research_only = TRUE
decision_engine_ready = FALSE
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd

# ---------------------------------------------------------------------
# Optional pitindex import
# ---------------------------------------------------------------------

try:
    import pitindex
except ImportError:
    pitindex = None


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

FJA_URL = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes%20%28Updated%29.csv"
)

HANS_URL = (
    "https://raw.githubusercontent.com/hanshof/sp500_constituents/master/"
    "sp_500_historical_components.csv"
)

CHINOBING_URL = (
    "https://raw.githubusercontent.com/chinobing/"
    "historical_sp500_constituents/main/"
    "sp_500_historical_components.csv"
)

DEFAULT_START = "2019-01-01"


# ---------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------

def normalize_ticker(value: str) -> str:
    """
    Normalize ticker representation only where the difference is clearly
    a formatting convention.

    Examples:
        BRK.B -> BRK-B
        BF.B  -> BF-B
    """

    value = str(value).strip().upper()

    if value in {"NAN", "NONE", ""}:
        return ""

    # Normalize common Yahoo/Wikipedia separator differences.
    value = value.replace(".", "-")

    return value


def normalize_ticker_set(values: Iterable[str]) -> Set[str]:
    result = set()

    for value in values:
        ticker = normalize_ticker(value)

        if ticker:
            result.add(ticker)

    return result


def parse_ticker_list(value) -> Set[str]:
    """
    Parse a cell containing a comma-separated ticker list.
    """

    if pd.isna(value):
        return set()

    text = str(value).strip()

    if not text:
        return set()

    # Some files may use comma-separated values.
    parts = [x.strip() for x in text.split(",")]

    return normalize_ticker_set(parts)


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0

    union = a | b

    if not union:
        return 1.0

    return len(a & b) / len(union)


def overlap_pct(a: Set[str], b: Set[str]) -> float:
    """
    Symmetric overlap percentage based on the larger universe.
    """

    denominator = max(len(a), len(b))

    if denominator == 0:
        return 100.0

    return 100.0 * len(a & b) / denominator


def symmetric_difference_count(a: Set[str], b: Set[str]) -> int:
    return len(a ^ b)


# ---------------------------------------------------------------------
# Generic source loaders
# ---------------------------------------------------------------------

def find_column(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    normalized = {
        str(column).strip().lower(): column
        for column in df.columns
    }

    for candidate in candidates:
        key = candidate.strip().lower()

        if key in normalized:
            return normalized[key]

    return None


def load_generic_snapshot_csv(
    url: str,
    source_name: str,
) -> Dict[pd.Timestamp, Set[str]]:
    """
    Load a historical constituent CSV.

    Supports common formats:
        date,tickers
        date,components
        date,constituents

    Also supports wide-ish formats where each row has date + ticker.
    """

    print(f"Loading {source_name}...")
    print(f"URL: {url}")

    df = pd.read_csv(url)

    if df.empty:
        raise RuntimeError(f"{source_name}: CSV is empty")

    date_col = find_column(
        df,
        [
            "date",
            "asof_date",
            "effective_date",
            "as_of_date",
        ],
    )

    if date_col is None:
        raise RuntimeError(
            f"{source_name}: unable to identify date column. "
            f"Columns={list(df.columns)}"
        )

    df[date_col] = pd.to_datetime(
        df[date_col],
        errors="coerce",
    )

    df = df.dropna(subset=[date_col])

    ticker_list_col = find_column(
        df,
        [
            "tickers",
            "ticker",
            "symbols",
            "constituents",
            "components",
            "members",
        ],
    )

    snapshots: Dict[pd.Timestamp, Set[str]] = {}

    # -------------------------------------------------------------
    # Format A: date + comma-separated ticker list
    # -------------------------------------------------------------

    if ticker_list_col is not None:

        for date, group in df.groupby(date_col):

            members = set()

            for value in group[ticker_list_col]:
                members.update(parse_ticker_list(value))

            if members:
                snapshots[date.normalize()] = members

        if snapshots:
            return snapshots

    # -------------------------------------------------------------
    # Format B: date + many ticker columns
    # -------------------------------------------------------------

    excluded_columns = {
        date_col,
        "security",
        "gics sector",
        "gics sub-industry",
        "headquarters location",
        "date added",
        "cik",
        "founded",
    }

    candidate_columns = [
        c for c in df.columns
        if c not in excluded_columns
    ]

    for _, row in df.iterrows():

        date = row[date_col]

        if pd.isna(date):
            continue

        members = set()

        for column in candidate_columns:

            value = row[column]

            if pd.isna(value):
                continue

            text = str(value).strip()

            if not text:
                continue

            # Ignore obvious non-ticker metadata.
            if text.lower() in {
                "nan",
                "none",
                "date",
                "security",
            }:
                continue

            # If comma-separated, split.
            if "," in text:
                members.update(parse_ticker_list(text))
            else:
                ticker = normalize_ticker(text)

                if ticker:
                    members.add(ticker)

        if members:
            snapshots[pd.Timestamp(date).normalize()] = members

    if not snapshots:
        raise RuntimeError(
            f"{source_name}: no membership snapshots could be parsed"
        )

    return snapshots


# ---------------------------------------------------------------------
# pitindex loader
# ---------------------------------------------------------------------

def load_pitindex_snapshots(
    dates: Iterable[pd.Timestamp],
) -> Dict[pd.Timestamp, Set[str]]:
    """
    Query pitindex for the exact comparison dates.

    pitindex is treated only as historical supporting evidence.
    """

    snapshots: Dict[pd.Timestamp, Set[str]] = {}

    if pitindex is None:
        warnings.warn(
            "pitindex is not installed. "
            "PIT-supported classification will be unavailable."
        )
        return snapshots

    unique_dates = sorted(
        set(pd.Timestamp(d).normalize() for d in dates)
    )

    print("Loading pitindex...")

    # Suppress noisy stale-data warning in the test output.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            for date in unique_dates:

                try:
                    members = pitindex.get_constituents(
                        date.strftime("%Y-%m-%d")
                    )

                except TypeError:

                    try:
                        members = pitindex.get_constituents(
                            date
                        )

                    except Exception:
                        continue

                except Exception:
                    continue

                if members is None:
                    continue

                parsed = normalize_ticker_set(members)

                if parsed:
                    snapshots[date] = parsed

    except Exception as exc:
        warnings.warn(
            f"pitindex loading failed: {exc}"
        )

    return snapshots


# ---------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------

def classify_snapshot(
    fja: Set[str],
    hans: Set[str],
    chinobing: Set[str],
    pit: Set[str],
) -> Tuple[str, str]:
    """
    Return:
        classification, reason
    """

    # -------------------------------------------------------------
    # All direct sources agree
    # -------------------------------------------------------------

    if fja == hans == chinobing:

        return (
            "MATCH",
            "All three direct public reconstructions agree."
        )

    # -------------------------------------------------------------
    # Determine direct-source pair agreement
    # -------------------------------------------------------------

    direct_sets = {
        "fja": fja,
        "hans": hans,
        "chinobing": chinobing,
    }

    pairwise = [
        ("fja", "hans", fja, hans),
        ("fja", "chinobing", fja, chinobing),
        ("hans", "chinobing", hans, chinobing),
    ]

    best_pair = None
    best_jaccard = -1.0

    for name_a, name_b, set_a, set_b in pairwise:

        score = jaccard(set_a, set_b)

        if score > best_jaccard:
            best_jaccard = score
            best_pair = (
                name_a,
                name_b,
                set_a,
                set_b,
            )

    # -------------------------------------------------------------
    # Direct source agreement on two of three sources
    # -------------------------------------------------------------

    if best_pair is not None:

        name_a, name_b, set_a, set_b = best_pair

        if set_a == set_b:

            third_name = next(
                name
                for name in direct_sets
                if name not in {name_a, name_b}
            )

            third_set = direct_sets[third_name]

            # Check whether PIT supports the two agreeing sources.
            if pit and third_set != set_a:

                pit_score_agree = jaccard(pit, set_a)
                pit_score_third = jaccard(pit, third_set)

                if pit_score_agree > pit_score_third:
                    return (
                        "PIT_SUPPORTED_DISAGREEMENT",
                        (
                            f"{name_a} and {name_b} agree while "
                            f"{third_name} differs; pitindex supports "
                            f"the {name_a}/{name_b} membership."
                        ),
                    )

            # Difference may simply reflect ticker representation/count.
            if (
                symmetric_difference_count(
                    set_a,
                    third_set
                ) <= 10
            ):
                return (
                    "EXPLAINABLE",
                    (
                        f"{name_a} and {name_b} agree; "
                        f"{third_name} differs by "
                        f"{symmetric_difference_count(set_a, third_set)} "
                        f"members."
                    ),
                )

    # -------------------------------------------------------------
    # PIT support
    # -------------------------------------------------------------

    if pit:

        direct_scores = {
            name: jaccard(members, pit)
            for name, members in direct_sets.items()
        }

        best_direct_name = max(
            direct_scores,
            key=direct_scores.get,
        )

        worst_direct_name = min(
            direct_scores,
            key=direct_scores.get,
        )

        best_score = direct_scores[best_direct_name]
        worst_score = direct_scores[worst_direct_name]

        # PIT clearly supports one direct source.
        if best_score >= 0.99 and best_score - worst_score >= 0.005:

            return (
                "PIT_SUPPORTED_DISAGREEMENT",
                (
                    f"pitindex supports {best_direct_name}; "
                    f"best_jaccard={best_score:.6f}, "
                    f"worst_jaccard={worst_score:.6f}."
                ),
            )

    # -------------------------------------------------------------
    # No sufficient evidence
    # -------------------------------------------------------------

    return (
        "UNRESOLVED_CONFLICT",
        (
            "Direct sources disagree and no sufficient PIT evidence "
            "resolves the disagreement."
        ),
    )


# ---------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------

def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--start",
        default=DEFAULT_START,
        help="Start date, e.g. 2019-01-01",
    )

    parser.add_argument(
        "--end",
        default=None,
        help="Optional end date",
    )

    parser.add_argument(
        "--output",
        default="market_breadth_cross_validation_v2",
        help="Output directory",
    )

    args = parser.parse_args()

    start_date = pd.Timestamp(args.start).normalize()

    end_date = (
        pd.Timestamp(args.end).normalize()
        if args.end
        else None
    )

    output_dir = Path(args.output)
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 72)
    print(
        "Market Breadth — S&P 500 Membership "
        "Cross-Validation v2"
    )
    print("=" * 72)

    print(f"Start date: {start_date.date()}")

    if end_date:
        print(f"End date:   {end_date.date()}")

    print("Research-only: TRUE")
    print("PIT-perfect: FALSE")
    print(
        "Membership source: FREE_PUBLIC_RECONSTRUCTION"
    )
    print(
        "Membership quality: RESEARCH_GRADE"
    )

    # -------------------------------------------------------------
    # Load direct sources
    # -------------------------------------------------------------

    fja = load_generic_snapshot_csv(
        FJA_URL,
        "fja05680/sp500",
    )

    hans = load_generic_snapshot_csv(
        HANS_URL,
        "hanshof/sp500_constituents",
    )

    chinobing = load_generic_snapshot_csv(
        CHINOBING_URL,
        "chinobing/historical_sp500_constituents",
    )

    # -------------------------------------------------------------
    # Restrict dates
    # -------------------------------------------------------------

    def filter_dates(
        source: Dict[pd.Timestamp, Set[str]]
    ) -> Dict[pd.Timestamp, Set[str]]:

        result = {}

        for date, members in source.items():

            if date < start_date:
                continue

            if end_date is not None and date > end_date:
                continue

            result[date] = members

        return result

    fja = filter_dates(fja)
    hans = filter_dates(hans)
    chinobing = filter_dates(chinobing)

    # -------------------------------------------------------------
    # Only dates shared by all direct sources
    # -------------------------------------------------------------

    common_dates = sorted(
        set(fja)
        & set(hans)
        & set(chinobing)
    )

    if not common_dates:
        print(
            "ERROR: No common dates across the three "
            "direct sources."
        )
        return 1

    print()
    print("=" * 72)
    print("DIRECT SOURCE COVERAGE")
    print("=" * 72)

    print(
        f"fja snapshots:       {len(fja):,}"
    )
    print(
        f"hans snapshots:      {len(hans):,}"
    )
    print(
        f"chinobing snapshots: {len(chinobing):,}"
    )

    print(
        f"Common snapshots:    {len(common_dates):,}"
    )

    print(
        f"Common date range:   "
        f"{common_dates[0].date()} → "
        f"{common_dates[-1].date()}"
    )

    # -------------------------------------------------------------
    # PIT validation
    # -------------------------------------------------------------

    pit = load_pitindex_snapshots(
        common_dates
    )

    print(
        f"pitindex snapshots:   {len(pit):,}"
    )

    # -------------------------------------------------------------
    # Compare
    # -------------------------------------------------------------

    rows = []

    for date in common_dates:

        fja_set = fja[date]
        hans_set = hans[date]
        chinobing_set = chinobing[date]

        pit_set = pit.get(
            date,
            set(),
        )

        classification, reason = classify_snapshot(
            fja_set,
            hans_set,
            chinobing_set,
            pit_set,
        )

        row = {
            "asof_date": date.date().isoformat(),

            "fja_count": len(fja_set),
            "hans_count": len(hans_set),
            "chinobing_count": len(chinobing_set),
            "pit_count": len(pit_set),

            "fja_hans_jaccard": jaccard(
                fja_set,
                hans_set,
            ),

            "fja_chinobing_jaccard": jaccard(
                fja_set,
                chinobing_set,
            ),

            "hans_chinobing_jaccard": jaccard(
                hans_set,
                chinobing_set,
            ),

            "fja_hans_overlap_pct": overlap_pct(
                fja_set,
                hans_set,
            ),

            "fja_chinobing_overlap_pct": overlap_pct(
                fja_set,
                chinobing_set,
            ),

            "hans_chinobing_overlap_pct": overlap_pct(
                hans_set,
                chinobing_set,
            ),

            "fja_only_vs_hans": len(
                fja_set - hans_set
            ),

            "hans_only_vs_fja": len(
                hans_set - fja_set
            ),

            "fja_only_vs_chinobing": len(
                fja_set - chinobing_set
            ),

            "chinobing_only_vs_fja": len(
                chinobing_set - fja_set
            ),

            "pit_available": bool(pit_set),

            "classification": classification,
            "classification_reason": reason,

            "point_in_time_reconstructed": True,
            "membership_source":
                "FREE_PUBLIC_RECONSTRUCTION",
            "membership_quality": "RESEARCH_GRADE",
            "cross_validated": True,
            "research_only": True,
            "decision_engine_ready": False,
        }

        # ---------------------------------------------------------
        # PIT scores
        # ---------------------------------------------------------

        if pit_set:

            row["fja_pit_jaccard"] = jaccard(
                fja_set,
                pit_set,
            )

            row["hans_pit_jaccard"] = jaccard(
                hans_set,
                pit_set,
            )

            row["chinobing_pit_jaccard"] = jaccard(
                chinobing_set,
                pit_set,
            )

        else:

            row["fja_pit_jaccard"] = None
            row["hans_pit_jaccard"] = None
            row["chinobing_pit_jaccard"] = None

        rows.append(row)

    comparison = pd.DataFrame(rows)

    # -------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------

    classification_counts = (
        comparison["classification"]
        .value_counts()
        .to_dict()
    )

    total = len(comparison)

    direct_conflict_count = int(
        (
            comparison["classification"]
            == "UNRESOLVED_CONFLICT"
        ).sum()
    )

    pit_supported_count = int(
        (
            comparison["classification"]
            == "PIT_SUPPORTED_DISAGREEMENT"
        ).sum()
    )

    explainable_count = int(
        (
            comparison["classification"]
            == "EXPLAINABLE"
        ).sum()
    )

    match_count = int(
        (
            comparison["classification"]
            == "MATCH"
        ).sum()
    )

    direct_source_conflict_ratio = (
        direct_conflict_count / total
        if total
        else 0.0
    )

    pit_supported_disagreement_ratio = (
        pit_supported_count / total
        if total
        else 0.0
    )

    unresolved_ratio = (
        direct_conflict_count / total
        if total
        else 0.0
    )

    summary = {

        "validation_version": "v2",

        "start_date":
            start_date.date().isoformat(),

        "end_date":
            (
                end_date.date().isoformat()
                if end_date is not None
                else None
            ),

        "common_snapshot_count": total,

        "common_date_start":
            common_dates[0].date().isoformat(),

        "common_date_end":
            common_dates[-1].date().isoformat(),

        # ---------------------------------------------------------
        # Agreement statistics
        # ---------------------------------------------------------

        "mean_fja_hans_jaccard":
            float(
                comparison[
                    "fja_hans_jaccard"
                ].mean()
            ),

        "median_fja_hans_jaccard":
            float(
                comparison[
                    "fja_hans_jaccard"
                ].median()
            ),

        "minimum_fja_hans_jaccard":
            float(
                comparison[
                    "fja_hans_jaccard"
                ].min()
            ),

        "mean_fja_chinobing_jaccard":
            float(
                comparison[
                    "fja_chinobing_jaccard"
                ].mean()
            ),

        "mean_hans_chinobing_jaccard":
            float(
                comparison[
                    "hans_chinobing_jaccard"
                ].mean()
            ),

        "mean_fja_hans_overlap_pct":
            float(
                comparison[
                    "fja_hans_overlap_pct"
                ].mean()
            ),

        "mean_fja_chinobing_overlap_pct":
            float(
                comparison[
                    "fja_chinobing_overlap_pct"
                ].mean()
            ),

        "mean_hans_chinobing_overlap_pct":
            float(
                comparison[
                    "hans_chinobing_overlap_pct"
                ].mean()
            ),

        # ---------------------------------------------------------
        # Corrected classification statistics
        # ---------------------------------------------------------

        "match_count": match_count,

        "explainable_count":
            explainable_count,

        "pit_supported_disagreement_count":
            pit_supported_count,

        "unresolved_conflict_count":
            direct_conflict_count,

        "direct_source_conflict_ratio":
            direct_source_conflict_ratio,

        "pit_supported_disagreement_ratio":
            pit_supported_disagreement_ratio,

        "unresolved_ratio":
            unresolved_ratio,

        "classification_counts":
            classification_counts,

        # ---------------------------------------------------------
        # Data-quality metadata
        # ---------------------------------------------------------

        "fja_snapshot_count":
            len(fja),

        "hans_snapshot_count":
            len(hans),

        "chinobing_snapshot_count":
            len(chinobing),

        "pitindex_snapshot_count":
            len(pit),

        "point_in_time_reconstructed": True,

        "membership_source":
            "FREE_PUBLIC_RECONSTRUCTION",

        "membership_quality":
            "RESEARCH_GRADE",

        "cross_validated": True,

        "pit_perfect": False,

        "research_only": True,

        "decision_engine_ready": False,

        "trading_signal": False,

        "forecast": False,

        # ---------------------------------------------------------
        # Gate status
        # ---------------------------------------------------------

        "final_status": (
            "PASS"
            if direct_conflict_count == 0
            else "PASS_WITH_REVIEW"
            if unresolved_ratio <= 0.01
            else "REVIEW_REQUIRED"
        ),
    }

    # -------------------------------------------------------------
    # Save comparison
    # -------------------------------------------------------------

    comparison_path = (
        output_dir
        / "membership_snapshot_comparison_v2.csv"
    )

    comparison.to_csv(
        comparison_path,
        index=False,
    )

    # -------------------------------------------------------------
    # Save discrepancies
    # -------------------------------------------------------------

    discrepancies = comparison[
        comparison["classification"]
        != "MATCH"
    ].copy()

    discrepancies_path = (
        output_dir
        / "membership_discrepancies_v2.csv"
    )

    discrepancies.to_csv(
        discrepancies_path,
        index=False,
    )

    # -------------------------------------------------------------
    # Save unresolved only
    # -------------------------------------------------------------

    unresolved = comparison[
        comparison["classification"]
        == "UNRESOLVED_CONFLICT"
    ].copy()

    unresolved_path = (
        output_dir
        / "membership_unresolved_conflicts_v2.csv"
    )

    unresolved.to_csv(
        unresolved_path,
        index=False,
    )

    # -------------------------------------------------------------
    # Save summary
    # -------------------------------------------------------------

    summary_path = (
        output_dir
        / "membership_cross_validation_summary_v2.json"
    )

    with open(
        summary_path,
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            summary,
            handle,
            indent=2,
            ensure_ascii=False,
        )

    # -------------------------------------------------------------
    # Console output
    # -------------------------------------------------------------

    print()
    print("=" * 72)
    print("RESULT")
    print("=" * 72)

    print(
        f"Common snapshots: "
        f"{total:,}"
    )

    print(
        f"Date range: "
        f"{common_dates[0].date()} → "
        f"{common_dates[-1].date()}"
    )

    print()

    print(
        f"Mean FJA/HANS Jaccard: "
        f"{summary['mean_fja_hans_jaccard']:.6f}"
    )

    print(
        f"Median FJA/HANS Jaccard: "
        f"{summary['median_fja_hans_jaccard']:.6f}"
    )

    print(
        f"Minimum FJA/HANS Jaccard: "
        f"{summary['minimum_fja_hans_jaccard']:.6f}"
    )

    print()

    print(
        f"Mean FJA/Chinobing Jaccard: "
        f"{summary['mean_fja_chinobing_jaccard']:.6f}"
    )

    print(
        f"Mean HANS/Chinobing Jaccard: "
        f"{summary['mean_hans_chinobing_jaccard']:.6f}"
    )

    print()

    print(
        "Classification:"
    )

    for key in [
        "MATCH",
        "EXPLAINABLE",
        "PIT_SUPPORTED_DISAGREEMENT",
        "UNRESOLVED_CONFLICT",
    ]:

        print(
            f"  {key}: "
            f"{classification_counts.get(key, 0)}"
        )

    print()

    print(
        f"Direct source conflict ratio: "
        f"{direct_source_conflict_ratio:.4%}"
    )

    print(
        f"PIT-supported disagreement ratio: "
        f"{pit_supported_disagreement_ratio:.4%}"
    )

    print(
        f"Unresolved ratio: "
        f"{unresolved_ratio:.4%}"
    )

    print()

    print(
        "Coverage:"
    )

    print(
        f"  FJA:       {len(fja):,}"
    )

    print(
        f"  HANS:      {len(hans):,}"
    )

    print(
        f"  Chinobing: {len(chinobing):,}"
    )

    print(
        f"  PIT:       {len(pit):,}"
    )

    print()

    print(
        "Classification:"
    )

    print(
        f"  FINAL STATUS: "
        f"{summary['final_status']}"
    )

    print()

    print(
        "Artifacts:"
    )

    print(
        f"  {comparison_path}"
    )

    print(
        f"  {discrepancies_path}"
    )

    print(
        f"  {unresolved_path}"
    )

    print(
        f"  {summary_path}"
    )

    print()
    print("=" * 72)
    print("WORST SNAPSHOT AGREEMENTS")
    print("=" * 72)

    display_columns = [
        "asof_date",
        "fja_count",
        "hans_count",
        "chinobing_count",
        "pit_count",
        "fja_hans_jaccard",
        "fja_chinobing_jaccard",
        "hans_chinobing_jaccard",
        "classification",
    ]

    print(
        comparison
        .sort_values(
            "fja_hans_jaccard",
            ascending=True,
        )
        [display_columns]
        .head(20)
        .to_string(index=False)
    )

    # -------------------------------------------------------------
    # Exit code
    # -------------------------------------------------------------

    # We do NOT fail merely because PIT-supported disagreements exist.
    # We fail only when unresolved conflicts exceed 1%.
    if unresolved_ratio > 0.01:
        print()
        print(
            "FINAL STATUS: REVIEW_REQUIRED"
        )
        return 1

    print()
    print(
        "FINAL STATUS: "
        f"{summary['final_status']}"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
