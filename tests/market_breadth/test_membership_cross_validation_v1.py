#!/usr/bin/env python3
"""
Market Breadth — S&P 500 Membership Cross-Validation v2.1

Purpose
-------
Research-only validation of reconstructed historical S&P 500 membership.

IMPORTANT
---------
This module does NOT claim PIT-perfect membership.

The membership universe is reconstructed from free public sources and
cross-validated across multiple historical datasets.

Sources
-------
1. fja05680/sp500
   Historical S&P 500 membership reference.

2. hanshof/sp500_constituents
   Independent historical reconstruction.

3. chinobing/historical_sp500_constituents
   Auto-renewed historical reconstruction.

4. pitindex
   Supporting PIT historical evidence only.

IMPORTANT:
pitindex is NOT treated as an independent source because its S&P 500
historical seed is derived from fja05680/sp500.

Research metadata
-----------------
point_in_time_reconstructed = TRUE
membership_source = FREE_PUBLIC_RECONSTRUCTION
membership_quality = RESEARCH_GRADE
cross_validated = TRUE
pit_perfect = FALSE
research_only = TRUE
decision_engine_ready = FALSE
trading_signal = FALSE
forecast = FALSE

Classification
--------------
MATCH
    All three direct sources agree exactly.

EXPLAINABLE
    Direct sources differ slightly and the difference is small enough
    to be treated as a representation/count difference.

PIT_SUPPORTED_DISAGREEMENT
    Direct sources disagree and pitindex provides supporting evidence
    for one side.

UNRESOLVED_CONFLICT
    Direct sources disagree and available PIT evidence does not provide
    sufficient resolution.

Gate
----
The workflow fails only if unresolved conflicts exceed 1%.

<= 1% unresolved:
    PASS_WITH_REVIEW

0 unresolved:
    PASS

> 1% unresolved:
    REVIEW_REQUIRED
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd


# ============================================================================
# OPTIONAL PITINDEX
# ============================================================================

try:
    import pitindex
except ImportError:
    pitindex = None


# ============================================================================
# CONFIGURATION
# ============================================================================

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

# Small membership differences are allowed as explainable.
EXPLAINABLE_DIFFERENCE_THRESHOLD = 10

# PIT sanity range.
# A valid S&P 500 snapshot should be around 500 members, although
# multiple share classes can make the count slightly above/below 500.
PIT_MIN_MEMBERS = 400
PIT_MAX_MEMBERS = 600

# Final quality gate.
MAX_UNRESOLVED_RATIO = 0.01


# ============================================================================
# NORMALIZATION
# ============================================================================

def normalize_ticker(value) -> str:
    """
    Normalize ticker representation.

    Examples:
        BRK.B -> BRK-B
        BF.B  -> BF-B

    This is only a formatting normalization.
    """

    if value is None:
        return ""

    value = str(value).strip().upper()

    if value in {"", "NAN", "NONE", "NULL"}:
        return ""

    # Normalize Yahoo/Wikipedia-style separator differences.
    value = value.replace(".", "-")

    return value


def normalize_ticker_set(values: Iterable) -> Set[str]:
    """
    Convert an iterable of ticker values into a normalized set.
    """

    result: Set[str] = set()

    for value in values:
        ticker = normalize_ticker(value)

        if ticker:
            result.add(ticker)

    return result


def parse_ticker_list(value) -> Set[str]:
    """
    Parse a comma-separated ticker list.
    """

    if pd.isna(value):
        return set()

    text = str(value).strip()

    if not text:
        return set()

    parts = [item.strip() for item in text.split(",")]

    return normalize_ticker_set(parts)


# ============================================================================
# SET COMPARISON
# ============================================================================

def jaccard(a: Set[str], b: Set[str]) -> float:
    """
    Jaccard similarity.
    """

    union = a | b

    if not union:
        return 1.0

    return len(a & b) / len(union)


def overlap_pct(a: Set[str], b: Set[str]) -> float:
    """
    Symmetric overlap percentage using the larger universe
    as denominator.
    """

    denominator = max(len(a), len(b))

    if denominator == 0:
        return 100.0

    return 100.0 * len(a & b) / denominator


def symmetric_difference_count(
    a: Set[str],
    b: Set[str],
) -> int:
    return len(a ^ b)


# ============================================================================
# COLUMN DISCOVERY
# ============================================================================

def find_column(
    df: pd.DataFrame,
    candidates: List[str],
) -> Optional[str]:
    """
    Find a DataFrame column using case-insensitive exact matching.
    """

    normalized = {
        str(column).strip().lower(): column
        for column in df.columns
    }

    for candidate in candidates:

        key = candidate.strip().lower()

        if key in normalized:
            return normalized[key]

    return None


# ============================================================================
# DIRECT SOURCE LOADER
# ============================================================================

def load_generic_snapshot_csv(
    url: str,
    source_name: str,
) -> Dict[pd.Timestamp, Set[str]]:
    """
    Load historical constituent snapshots.

    Supports:
        date + ticker list
        date + ticker
        date + constituents
        date + components
        date + members

    Returns:
        {
            date: {ticker1, ticker2, ...}
        }
    """

    print(f"Loading {source_name}...")
    print(f"URL: {url}")

    df = pd.read_csv(url)

    if df.empty:
        raise RuntimeError(
            f"{source_name}: CSV is empty"
        )

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

    df = df.dropna(
        subset=[date_col]
    )

    ticker_col = find_column(
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

    # -----------------------------------------------------------------
    # FORMAT A
    # date + ticker/constituent list
    # -----------------------------------------------------------------

    if ticker_col is not None:

        for date, group in df.groupby(date_col):

            members: Set[str] = set()

            for value in group[ticker_col]:

                members.update(
                    parse_ticker_list(value)
                )

            if members:

                snapshots[
                    pd.Timestamp(date).normalize()
                ] = members

        if snapshots:
            return snapshots

    # -----------------------------------------------------------------
    # FORMAT B
    # date + multiple ticker-like columns
    # -----------------------------------------------------------------

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
        column
        for column in df.columns
        if column not in excluded_columns
    ]

    for _, row in df.iterrows():

        date = row[date_col]

        if pd.isna(date):
            continue

        members: Set[str] = set()

        for column in candidate_columns:

            value = row[column]

            if pd.isna(value):
                continue

            text = str(value).strip()

            if not text:
                continue

            if text.lower() in {
                "nan",
                "none",
                "date",
                "security",
            }:
                continue

            if "," in text:

                members.update(
                    parse_ticker_list(text)
                )

            else:

                ticker = normalize_ticker(text)

                if ticker:
                    members.add(ticker)

        if members:

            snapshots[
                pd.Timestamp(date).normalize()
            ] = members

    if not snapshots:

        raise RuntimeError(
            f"{source_name}: no membership snapshots could be parsed"
        )

    return snapshots


# ============================================================================
# PITINDEX LOADER
# ============================================================================

def extract_pit_tickers(members) -> Set[str]:
    """
    Extract tickers from pitindex.get_constituents().

    IMPORTANT
    ---------
    pitindex.get_constituents() returns a pandas DataFrame.

    The correct extraction is:
        members["ticker"]

    NOT:
        normalize_ticker_set(members)

    because iterating a DataFrame returns its column names.

    That previous bug produced:
        pit_count = 5

    because the DataFrame had five columns.
    """

    if members is None:
        return set()

    # -------------------------------------------------------------
    # Expected pitindex output: DataFrame
    # -------------------------------------------------------------

    if isinstance(members, pd.DataFrame):

        ticker_col = find_column(
            members,
            [
                "ticker",
                "symbol",
                "symbols",
            ],
        )

        if ticker_col is None:

            warnings.warn(
                "pitindex returned a DataFrame but no ticker column "
                f"was found. Columns={list(members.columns)}"
            )

            return set()

        tickers = normalize_ticker_set(
            members[ticker_col].tolist()
        )

        return tickers

    # -------------------------------------------------------------
    # Series fallback
    # -------------------------------------------------------------

    if isinstance(members, pd.Series):

        return normalize_ticker_set(
            members.tolist()
        )

    # -------------------------------------------------------------
    # Dict fallback
    # -------------------------------------------------------------

    if isinstance(members, dict):

        for key in [
            "ticker",
            "tickers",
            "symbol",
            "symbols",
        ]:

            if key in members:

                value = members[key]

                if isinstance(value, (list, tuple, set)):

                    return normalize_ticker_set(
                        value
                    )

        return set()

    # -------------------------------------------------------------
    # List / tuple / set fallback
    # -------------------------------------------------------------

    if isinstance(
        members,
        (list, tuple, set),
    ):

        return normalize_ticker_set(
            members
        )

    return set()


def load_pitindex_snapshots(
    dates: Iterable[pd.Timestamp],
) -> Dict[pd.Timestamp, Set[str]]:
    """
    Query pitindex for the comparison dates.

    Invalid PIT snapshots outside the sanity range are rejected.
    """

    snapshots: Dict[pd.Timestamp, Set[str]] = {}

    if pitindex is None:

        warnings.warn(
            "pitindex is not installed. "
            "PIT-supported classification will be unavailable."
        )

        return snapshots

    unique_dates = sorted(
        set(
            pd.Timestamp(date).normalize()
            for date in dates
        )
    )

    print("Loading pitindex...")

    with warnings.catch_warnings():

        # Suppress stale-data warning from pitindex.
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

            parsed = extract_pit_tickers(
                members
            )

            # -----------------------------------------------------
            # PIT sanity validation
            # -----------------------------------------------------

            if not parsed:
                continue

            if not (
                PIT_MIN_MEMBERS
                <= len(parsed)
                <= PIT_MAX_MEMBERS
            ):

                warnings.warn(
                    f"pitindex snapshot {date.date()} has "
                    f"{len(parsed)} members; outside sanity range "
                    f"{PIT_MIN_MEMBERS}-{PIT_MAX_MEMBERS}. "
                    "Snapshot skipped."
                )

                continue

            snapshots[date] = parsed

    return snapshots


# ============================================================================
# CLASSIFICATION
# ============================================================================

def classify_snapshot(
    fja: Set[str],
    hans: Set[str],
    chinobing: Set[str],
    pit: Set[str],
) -> Tuple[str, str]:

    direct_sets = {
        "fja": fja,
        "hans": hans,
        "chinobing": chinobing,
    }

    # -----------------------------------------------------------------
    # Exact agreement
    # -----------------------------------------------------------------

    if fja == hans == chinobing:

        return (
            "MATCH",
            "All three direct public reconstructions agree.",
        )

    # -----------------------------------------------------------------
    # Find strongest pair
    # -----------------------------------------------------------------

    pairwise = [
        ("fja", "hans", fja, hans),
        ("fja", "chinobing", fja, chinobing),
        ("hans", "chinobing", hans, chinobing),
    ]

    best_pair = None
    best_jaccard = -1.0

    for (
        name_a,
        name_b,
        set_a,
        set_b,
    ) in pairwise:

        score = jaccard(
            set_a,
            set_b,
        )

        if score > best_jaccard:

            best_jaccard = score

            best_pair = (
                name_a,
                name_b,
                set_a,
                set_b,
            )

    # -----------------------------------------------------------------
    # Two direct sources agree exactly
    # -----------------------------------------------------------------

    if best_pair is not None:

        (
            name_a,
            name_b,
            set_a,
            set_b,
        ) = best_pair

        if set_a == set_b:

            third_name = next(
                name
                for name in direct_sets
                if name not in {
                    name_a,
                    name_b,
                }
            )

            third_set = direct_sets[
                third_name
            ]

            difference = symmetric_difference_count(
                set_a,
                third_set,
            )

            # ---------------------------------------------------------
            # PIT support
            # ---------------------------------------------------------

            if pit:

                pit_score_agree = jaccard(
                    pit,
                    set_a,
                )

                pit_score_third = jaccard(
                    pit,
                    third_set,
                )

                if (
                    pit_score_agree
                    > pit_score_third
                ):

                    return (
                        "PIT_SUPPORTED_DISAGREEMENT",
                        (
                            f"{name_a} and {name_b} agree while "
                            f"{third_name} differs; pitindex supports "
                            f"the {name_a}/{name_b} membership."
                        ),
                    )

            # ---------------------------------------------------------
            # Small explainable difference
            # ---------------------------------------------------------

            if (
                difference
                <= EXPLAINABLE_DIFFERENCE_THRESHOLD
            ):

                return (
                    "EXPLAINABLE",
                    (
                        f"{name_a} and {name_b} agree; "
                        f"{third_name} differs by "
                        f"{difference} members."
                    ),
                )

    # -----------------------------------------------------------------
    # PIT support for one direct source
    # -----------------------------------------------------------------

    if pit:

        direct_scores = {
            name: jaccard(
                members,
                pit,
            )
            for name, members
            in direct_sets.items()
        }

        best_direct_name = max(
            direct_scores,
            key=direct_scores.get,
        )

        worst_direct_name = min(
            direct_scores,
            key=direct_scores.get,
        )

        best_score = direct_scores[
            best_direct_name
        ]

        worst_score = direct_scores[
            worst_direct_name
        ]

        if (
            best_score >= 0.99
            and (
                best_score
                - worst_score
            ) >= 0.005
        ):

            return (
                "PIT_SUPPORTED_DISAGREEMENT",
                (
                    f"pitindex supports {best_direct_name}; "
                    f"best_jaccard={best_score:.6f}, "
                    f"worst_jaccard={worst_score:.6f}."
                ),
            )

    # -----------------------------------------------------------------
    # No sufficient evidence
    # -----------------------------------------------------------------

    return (
        "UNRESOLVED_CONFLICT",
        (
            "Direct sources disagree and no sufficient PIT evidence "
            "resolves the disagreement."
        ),
    )


# ============================================================================
# MAIN
# ============================================================================

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

    start_date = pd.Timestamp(
        args.start
    ).normalize()

    end_date = (
        pd.Timestamp(args.end).normalize()
        if args.end
        else None
    )

    output_dir = Path(
        args.output
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # =================================================================
    # HEADER
    # =================================================================

    print("=" * 72)

    print(
        "Market Breadth — S&P 500 Membership "
        "Cross-Validation v2.1"
    )

    print("=" * 72)

    print(
        f"Start date: {start_date.date()}"
    )

    if end_date:

        print(
            f"End date:   {end_date.date()}"
        )

    print(
        "Research-only: TRUE"
    )

    print(
        "PIT-perfect: FALSE"
    )

    print(
        "Membership source: "
        "FREE_PUBLIC_RECONSTRUCTION"
    )

    print(
        "Membership quality: "
        "RESEARCH_GRADE"
    )

    # =================================================================
    # LOAD DIRECT SOURCES
    # =================================================================

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

    # =================================================================
    # FILTER DATE RANGE
    # =================================================================

    def filter_dates(
        source: Dict[pd.Timestamp, Set[str]],
    ) -> Dict[pd.Timestamp, Set[str]]:

        result = {}

        for date, members in source.items():

            if date < start_date:
                continue

            if (
                end_date is not None
                and date > end_date
            ):
                continue

            result[date] = members

        return result

    fja = filter_dates(fja)
    hans = filter_dates(hans)
    chinobing = filter_dates(chinobing)

    # =================================================================
    # COMMON DATES
    # =================================================================

    common_dates = sorted(
        set(fja)
        & set(hans)
        & set(chinobing)
    )

    if not common_dates:

        print(
            "ERROR: No common dates across "
            "the three direct sources."
        )

        return 1

    # =================================================================
    # DIRECT SOURCE COVERAGE
    # =================================================================

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
        "Common date range:   "
        f"{common_dates[0].date()} → "
        f"{common_dates[-1].date()}"
    )

    # =================================================================
    # PITINDEX
    # =================================================================

    pit = load_pitindex_snapshots(
        common_dates
    )

    print(
        f"pitindex snapshots:   {len(pit):,}"
    )

    # =================================================================
    # PIT DIAGNOSTIC
    # =================================================================

    print()
    print("=" * 72)
    print("PITINDEX DIAGNOSTIC")
    print("=" * 72)

    if pit:

        pit_sizes = [
            len(members)
            for members in pit.values()
        ]

        print(
            f"PIT snapshots loaded: {len(pit):,}"
        )

        print(
            f"PIT membership min:   {min(pit_sizes):,}"
        )

        print(
            f"PIT membership max:   {max(pit_sizes):,}"
        )

        print(
            f"PIT membership mean:  "
            f"{sum(pit_sizes) / len(pit_sizes):.2f}"
        )

        print(
            "PIT sanity range:     "
            f"{PIT_MIN_MEMBERS}-{PIT_MAX_MEMBERS}"
        )

        if min(pit_sizes) < PIT_MIN_MEMBERS:

            print(
                "WARNING: PIT minimum membership "
                "is below sanity threshold."
            )

        if max(pit_sizes) > PIT_MAX_MEMBERS:

            print(
                "WARNING: PIT maximum membership "
                "is above sanity threshold."
            )

    else:

        print(
            "PIT snapshots loaded: 0"
        )

        print(
            "WARNING: No PIT evidence available."
        )

    # =================================================================
    # COMPARE
    # =================================================================

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

            "asof_date":
                date.date().isoformat(),

            "fja_count":
                len(fja_set),

            "hans_count":
                len(hans_set),

            "chinobing_count":
                len(chinobing_set),

            "pit_count":
                len(pit_set),

            "fja_hans_jaccard":
                jaccard(
                    fja_set,
                    hans_set,
                ),

            "fja_chinobing_jaccard":
                jaccard(
                    fja_set,
                    chinobing_set,
                ),

            "hans_chinobing_jaccard":
                jaccard(
                    hans_set,
                    chinobing_set,
                ),

            "fja_hans_overlap_pct":
                overlap_pct(
                    fja_set,
                    hans_set,
                ),

            "fja_chinobing_overlap_pct":
                overlap_pct(
                    fja_set,
                    chinobing_set,
                ),

            "hans_chinobing_overlap_pct":
                overlap_pct(
                    hans_set,
                    chinobing_set,
                ),

            "fja_only_vs_hans":
                len(
                    fja_set - hans_set
                ),

            "hans_only_vs_fja":
                len(
                    hans_set - fja_set
                ),

            "fja_only_vs_chinobing":
                len(
                    fja_set - chinobing_set
                ),

            "chinobing_only_vs_fja":
                len(
                    chinobing_set - fja_set
                ),

            "pit_available":
                bool(pit_set),

            "classification":
                classification,

            "classification_reason":
                reason,

            "point_in_time_reconstructed":
                True,

            "membership_source":
                "FREE_PUBLIC_RECONSTRUCTION",

            "membership_quality":
                "RESEARCH_GRADE",

            "cross_validated":
                True,

            "research_only":
                True,

            "decision_engine_ready":
                False,

        }

        # -------------------------------------------------------------
        # PIT similarity
        # -------------------------------------------------------------

        if pit_set:

            row[
                "fja_pit_jaccard"
            ] = jaccard(
                fja_set,
                pit_set,
            )

            row[
                "hans_pit_jaccard"
            ] = jaccard(
                hans_set,
                pit_set,
            )

            row[
                "chinobing_pit_jaccard"
            ] = jaccard(
                chinobing_set,
                pit_set,
            )

        else:

            row[
                "fja_pit_jaccard"
            ] = None

            row[
                "hans_pit_jaccard"
            ] = None

            row[
                "chinobing_pit_jaccard"
            ] = None

        rows.append(row)

    comparison = pd.DataFrame(
        rows
    )

    # =================================================================
    # STATISTICS
    # =================================================================

    classification_counts = (
        comparison[
            "classification"
        ]
        .value_counts()
        .to_dict()
    )

    total = len(comparison)

    match_count = int(
        (
            comparison[
                "classification"
            ]
            == "MATCH"
        ).sum()
    )

    explainable_count = int(
        (
            comparison[
                "classification"
            ]
            == "EXPLAINABLE"
        ).sum()
    )

    pit_supported_count = int(
        (
            comparison[
                "classification"
            ]
            == "PIT_SUPPORTED_DISAGREEMENT"
        ).sum()
    )

    unresolved_count = int(
        (
            comparison[
                "classification"
            ]
            == "UNRESOLVED_CONFLICT"
        ).sum()
    )

    direct_source_conflict_ratio = (
        unresolved_count / total
        if total
        else 0.0
    )

    pit_supported_ratio = (
        pit_supported_count / total
        if total
        else 0.0
    )

    unresolved_ratio = (
        unresolved_count / total
        if total
        else 0.0
    )

    # =================================================================
    # FINAL STATUS
    # =================================================================

    if unresolved_count == 0:

        final_status = "PASS"

    elif unresolved_ratio <= MAX_UNRESOLVED_RATIO:

        final_status = "PASS_WITH_REVIEW"

    else:

        final_status = "REVIEW_REQUIRED"

    # =================================================================
    # SUMMARY
    # =================================================================

    summary = {

        "validation_version":
            "v2.1",

        "start_date":
            start_date.date().isoformat(),

        "end_date":
            (
                end_date.date().isoformat()
                if end_date is not None
                else None
            ),

        "common_snapshot_count":
            total,

        "common_date_start":
            common_dates[0].date().isoformat(),

        "common_date_end":
            common_dates[-1].date().isoformat(),

        # -------------------------------------------------------------
        # Agreement statistics
        # -------------------------------------------------------------

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

        # -------------------------------------------------------------
        # Classification
        # -------------------------------------------------------------

        "match_count":
            match_count,

        "explainable_count":
            explainable_count,

        "pit_supported_disagreement_count":
            pit_supported_count,

        "unresolved_conflict_count":
            unresolved_count,

        "direct_source_conflict_ratio":
            direct_source_conflict_ratio,

        "pit_supported_disagreement_ratio":
            pit_supported_ratio,

        "unresolved_ratio":
            unresolved_ratio,

        "classification_counts":
            classification_counts,

        # -------------------------------------------------------------
        # Coverage
        # -------------------------------------------------------------

        "fja_snapshot_count":
            len(fja),

        "hans_snapshot_count":
            len(hans),

        "chinobing_snapshot_count":
            len(chinobing),

        "pitindex_snapshot_count":
            len(pit),

        # -------------------------------------------------------------
        # Quality metadata
        # -------------------------------------------------------------

        "point_in_time_reconstructed":
            True,

        "membership_source":
            "FREE_PUBLIC_RECONSTRUCTION",

        "membership_quality":
            "RESEARCH_GRADE",

        "cross_validated":
            True,

        "pit_perfect":
            False,

        "research_only":
            True,

        "decision_engine_ready":
            False,

        "trading_signal":
            False,

        "forecast":
            False,

        # -------------------------------------------------------------
        # Gate
        # -------------------------------------------------------------

        "max_unresolved_ratio":
            MAX_UNRESOLVED_RATIO,

        "final_status":
            final_status,
    }

    # =================================================================
    # SAVE COMPARISON
    # =================================================================

    comparison_path = (
        output_dir
        / "membership_snapshot_comparison_v2.csv"
    )

    comparison.to_csv(
        comparison_path,
        index=False,
    )

    # =================================================================
    # SAVE DISCREPANCIES
    # =================================================================

    discrepancies = comparison[
        comparison[
            "classification"
        ]
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

    # =================================================================
    # SAVE UNRESOLVED
    # =================================================================

    unresolved = comparison[
        comparison[
            "classification"
        ]
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

    # =================================================================
    # SAVE SUMMARY
    # =================================================================

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

    # =================================================================
    # CONSOLE RESULT
    # =================================================================

    print()
    print("=" * 72)
    print("RESULT")
    print("=" * 72)

    print(
        f"Common snapshots: {total:,}"
    )

    print(
        "Date range: "
        f"{common_dates[0].date()} → "
        f"{common_dates[-1].date()}"
    )

    print()

    print(
        "Mean FJA/HANS Jaccard: "
        f"{summary['mean_fja_hans_jaccard']:.6f}"
    )

    print(
        "Median FJA/HANS Jaccard: "
        f"{summary['median_fja_hans_jaccard']:.6f}"
    )

    print(
        "Minimum FJA/HANS Jaccard: "
        f"{summary['minimum_fja_hans_jaccard']:.6f}"
    )

    print()

    print(
        "Mean FJA/Chinobing Jaccard: "
        f"{summary['mean_fja_chinobing_jaccard']:.6f}"
    )

    print(
        "Mean HANS/Chinobing Jaccard: "
        f"{summary['mean_hans_chinobing_jaccard']:.6f}"
    )

    print()

    print("Classification:")

    print(
        f"  MATCH: "
        f"{classification_counts.get('MATCH', 0)}"
    )

    print(
        f"  EXPLAINABLE: "
        f"{classification_counts.get('EXPLAINABLE', 0)}"
    )

    print(
        f"  PIT_SUPPORTED_DISAGREEMENT: "
        f"{classification_counts.get('PIT_SUPPORTED_DISAGREEMENT', 0)}"
    )

    print(
        f"  UNRESOLVED_CONFLICT: "
        f"{classification_counts.get('UNRESOLVED_CONFLICT', 0)}"
    )

    print()

    print(
        "Direct source conflict ratio: "
        f"{direct_source_conflict_ratio:.4%}"
    )

    print(
        "PIT-supported disagreement ratio: "
        f"{pit_supported_ratio:.4%}"
    )

    print(
        "Unresolved ratio: "
        f"{unresolved_ratio:.4%}"
    )

    print()

    print("Coverage:")

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
        [
            display_columns
        ]
        .head(20)
        .to_string(index=False)
    )

    # =================================================================
    # UNRESOLVED DETAILS
    # =================================================================

    print()
    print("=" * 72)
    print("UNRESOLVED CONFLICTS")
    print("=" * 72)

    if unresolved.empty:

        print(
            "No unresolved conflicts."
        )

    else:

        unresolved_columns = [
            "asof_date",
            "fja_count",
            "hans_count",
            "chinobing_count",
            "pit_count",
            "fja_hans_jaccard",
            "fja_pit_jaccard",
            "hans_pit_jaccard",
            "chinobing_pit_jaccard",
            "classification_reason",
        ]

        available_columns = [
            column
            for column in unresolved_columns
            if column in unresolved.columns
        ]

        print(
            unresolved[
                available_columns
            ].to_string(index=False)
        )

    # =================================================================
    # ARTIFACTS
    # =================================================================

    print()
    print("=" * 72)
    print("ARTIFACTS")
    print("=" * 72)

    print(
        comparison_path
    )

    print(
        discrepancies_path
    )

    print(
        unresolved_path
    )

    print(
        summary_path
    )

    # =================================================================
    # FINAL STATUS
    # =================================================================

    print()
    print("=" * 72)
    print(
        f"FINAL STATUS: {final_status}"
    )
    print("=" * 72)

    # Fail only when unresolved conflicts exceed 1%.
    if unresolved_ratio > MAX_UNRESOLVED_RATIO:

        return 1

    return 0


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":

    sys.exit(
        main()
    )
