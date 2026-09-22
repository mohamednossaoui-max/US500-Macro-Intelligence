"""
Market Breadth — S&P 500 Membership Cross-Validation v1

Purpose
-------
Research-only validation of historical S&P 500 membership using
multiple free public sources.

Sources
-------
1. fja05680/sp500
2. hanshof/sp500_constituents
3. pitindex

Scope
-----
2019-01-01 -> latest common available date

Important
---------
This test does NOT claim PIT-perfect historical membership.

It measures:
- source availability
- snapshot size
- constituent overlap
- symmetric differences
- source agreement
- unresolved conflicts

No:
- trading signals
- forecasts
- Decision Engine integration
- paid data
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd


DEFAULT_START = "2019-01-01"

FJA_URL = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes%20%28Updated%29.csv"
)

HANS_URL = (
    "https://raw.githubusercontent.com/hanshof/sp500_constituents/master/"
    "sp_500_historical_components.csv"
)


@dataclass
class SnapshotComparison:
    asof_date: str
    fja_count: int
    hans_count: int
    pit_count: int

    fja_hans_intersection: int
    fja_hans_union: int

    fja_only: int
    hans_only: int

    fja_hans_jaccard: float
    fja_hans_overlap_pct: float

    pit_fja_intersection: int
    pit_hans_intersection: int

    classification: str


def download_csv(url: str) -> pd.DataFrame:
    """
    Download a public CSV without requiring credentials.
    """
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "US500-Macro-Intelligence/"
                "market-breadth-cross-validation-v1"
            )
        },
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()

    return pd.read_csv(io.BytesIO(raw))


def normalize_ticker(value: object) -> str:
    """
    Normalize ticker representation while preserving the actual symbol.

    We intentionally do NOT perform aggressive corporate-action mapping here.
    A ticker rename must remain visible as a research discrepancy.
    """
    if pd.isna(value):
        return ""

    ticker = str(value).strip().upper()

    # Remove accidental surrounding whitespace.
    ticker = ticker.strip()

    # Normalize common Yahoo-style class notation only.
    # Example: BRK.B -> BRK-B
    ticker = ticker.replace(".", "-")

    return ticker


def parse_ticker_list(value: object) -> set[str]:
    if pd.isna(value):
        return set()

    text = str(value).strip()

    if not text:
        return set()

    return {
        normalize_ticker(x)
        for x in text.split(",")
        if normalize_ticker(x)
    }


def find_column(df: pd.DataFrame, candidates: Iterable[str]) -> str:
    normalized = {
        str(c).strip().lower(): c
        for c in df.columns
    }

    for candidate in candidates:
        key = candidate.strip().lower()

        if key in normalized:
            return normalized[key]

    raise ValueError(
        f"Could not find any of columns {list(candidates)} "
        f"in {list(df.columns)}"
    )


def load_fja(start_date: str) -> dict[str, set[str]]:
    print("Loading fja05680/sp500...")

    df = download_csv(FJA_URL)

    date_col = find_column(
        df,
        ["date", "Date"],
    )

    ticker_col = None

    for candidate in [
        "tickers",
        "Ticker",
        "tickers_list",
        "constituents",
    ]:
        if candidate in df.columns:
            ticker_col = candidate
            break

    if ticker_col is None:
        raise ValueError(
            "Could not identify ticker-list column in fja dataset. "
            f"Columns: {list(df.columns)}"
        )

    df[date_col] = pd.to_datetime(
        df[date_col],
        errors="coerce",
    )

    start = pd.Timestamp(start_date)

    df = df[
        df[date_col].notna()
        & (df[date_col] >= start)
    ].copy()

    df = df.sort_values(date_col)

    snapshots: dict[str, set[str]] = {}

    for _, row in df.iterrows():
        d = row[date_col].date().isoformat()

        tickers = parse_ticker_list(
            row[ticker_col]
        )

        if tickers:
            snapshots[d] = tickers

    return snapshots


def load_hanshof(start_date: str) -> dict[str, set[str]]:
    print("Loading hanshof/sp500_constituents...")

    df = download_csv(HANS_URL)

    date_col = find_column(
        df,
        ["date", "Date"],
    )

    ticker_col = None

    for candidate in [
        "tickers",
        "Ticker",
        "tickers_list",
        "constituents",
    ]:
        if candidate in df.columns:
            ticker_col = candidate
            break

    if ticker_col is None:
        raise ValueError(
            "Could not identify ticker-list column in hanshof dataset. "
            f"Columns: {list(df.columns)}"
        )

    df[date_col] = pd.to_datetime(
        df[date_col],
        errors="coerce",
    )

    start = pd.Timestamp(start_date)

    df = df[
        df[date_col].notna()
        & (df[date_col] >= start)
    ].copy()

    df = df.sort_values(date_col)

    snapshots: dict[str, set[str]] = {}

    for _, row in df.iterrows():
        d = row[date_col].date().isoformat()

        tickers = parse_ticker_list(
            row[ticker_col]
        )

        if tickers:
            snapshots[d] = tickers

    return snapshots


def load_pitindex(
    dates: list[str],
) -> dict[str, set[str]]:
    """
    Load PIT snapshots through pitindex.

    pitindex ships its own dataset, so runtime use does not
    require network access after installation.
    """

    print("Loading pitindex...")

    try:
        import pitindex
    except ImportError as exc:
        raise RuntimeError(
            "pitindex is not installed.\n\n"
            "Install with:\n"
            "    pip install pitindex\n"
        ) from exc

    snapshots: dict[str, set[str]] = {}

    for d in dates:
        try:
            df = pitindex.get_constituents(
                d,
                index="sp500",
            )
        except Exception as exc:
            print(
                f"WARNING: pitindex failed for {d}: {exc}",
                file=sys.stderr,
            )
            continue

        if df is None or df.empty:
            continue

        if "ticker" not in df.columns:
            raise ValueError(
                "pitindex output does not contain 'ticker'. "
                f"Columns: {list(df.columns)}"
            )

        tickers = {
            normalize_ticker(x)
            for x in df["ticker"]
            if normalize_ticker(x)
        }

        if tickers:
            snapshots[d] = tickers

    return snapshots


def classify(
    fja: set[str],
    hans: set[str],
    pit: set[str],
) -> str:

    if not fja or not hans:
        return "MISSING_SOURCE"

    fja_hans_union = fja | hans

    if not fja_hans_union:
        return "MISSING_SOURCE"

    jaccard = len(fja & hans) / len(fja_hans_union)

    fja_hans_diff = fja ^ hans

    # Very high agreement.
    if jaccard >= 0.995:
        return "MATCH"

    # Small discrepancy.
    if jaccard >= 0.985:
        return "EXPLAINABLE_OR_MINOR"

    # If PIT agrees strongly with one source, flag the
    # disagreement rather than automatically selecting a winner.
    if pit:
        pit_fja = len(pit & fja) / max(len(pit | fja), 1)
        pit_hans = len(pit & hans) / max(len(pit | hans), 1)

        if max(pit_fja, pit_hans) >= 0.995:
            return "SOURCE_CONFLICT_WITH_PIT_SUPPORT"

    if fja_hans_diff:
        return "CONFLICT"

    return "UNRESOLVED"


def compare_snapshots(
    fja: dict[str, set[str]],
    hans: dict[str, set[str]],
    pit: dict[str, set[str]],
) -> pd.DataFrame:

    common_dates = sorted(
        set(fja)
        & set(hans)
    )

    rows: list[dict] = []

    for d in common_dates:
        f = fja[d]
        h = hans[d]
        p = pit.get(d, set())

        intersection = f & h
        union = f | h

        fja_only = f - h
        hans_only = h - f

        jaccard = (
            len(intersection) / len(union)
            if union
            else 0.0
        )

        overlap = (
            len(intersection)
            / max(min(len(f), len(h)), 1)
        )

        classification = classify(
            f,
            h,
            p,
        )

        rows.append(
            {
                "asof_date": d,

                "fja_count": len(f),
                "hans_count": len(h),
                "pit_count": len(p),

                "fja_hans_intersection": len(intersection),
                "fja_hans_union": len(union),

                "fja_only": len(fja_only),
                "hans_only": len(hans_only),

                "fja_hans_jaccard": jaccard,
                "fja_hans_overlap_pct": overlap * 100.0,

                "pit_fja_intersection": len(p & f),
                "pit_hans_intersection": len(p & h),

                "classification": classification,
            }
        )

    return pd.DataFrame(rows)


def build_discrepancy_table(
    fja: dict[str, set[str]],
    hans: dict[str, set[str]],
) -> pd.DataFrame:

    common_dates = sorted(
        set(fja) & set(hans)
    )

    rows = []

    for d in common_dates:
        f = fja[d]
        h = hans[d]

        fja_only = sorted(f - h)
        hans_only = sorted(h - f)

        if not fja_only and not hans_only:
            continue

        rows.append(
            {
                "asof_date": d,
                "fja_only": ",".join(fja_only),
                "hans_only": ",".join(hans_only),
                "fja_only_count": len(fja_only),
                "hans_only_count": len(hans_only),
            }
        )

    return pd.DataFrame(rows)


def summarize(
    comparison: pd.DataFrame,
) -> dict:

    if comparison.empty:
        return {
            "status": "FAIL",
            "reason": "No common dates available.",
        }

    counts = (
        comparison["classification"]
        .value_counts()
        .to_dict()
    )

    summary = {
        "status": "PASS_WITH_REVIEW",
        "common_snapshot_dates": int(
            len(comparison)
        ),

        "first_common_date": str(
            comparison["asof_date"].min()
        ),

        "last_common_date": str(
            comparison["asof_date"].max()
        ),

        "mean_jaccard": float(
            comparison["fja_hans_jaccard"].mean()
        ),

        "median_jaccard": float(
            comparison["fja_hans_jaccard"].median()
        ),

        "minimum_jaccard": float(
            comparison["fja_hans_jaccard"].min()
        ),

        "mean_overlap_pct": float(
            comparison["fja_hans_overlap_pct"].mean()
        ),

        "classification_counts": counts,

        "research_only": True,

        "point_in_time_perfect": False,

        "decision_engine_ready": False,
    }

    # Hard failure condition:
    # too many genuine conflicts.
    conflict_count = (
        comparison["classification"]
        .isin(
            [
                "CONFLICT",
                "UNRESOLVED",
            ]
        )
        .sum()
    )

    conflict_ratio = (
        conflict_count
        / len(comparison)
    )

    summary["conflict_ratio"] = float(
        conflict_ratio
    )

    if conflict_ratio > 0.05:
        summary["status"] = "FAIL_REVIEW_REQUIRED"

    return summary


def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--start",
        default=DEFAULT_START,
        help="Start date, YYYY-MM-DD",
    )

    parser.add_argument(
        "--output",
        default="market_breadth_cross_validation_v1",
        help="Output directory",
    )

    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 72)
    print(
        "Market Breadth — S&P 500 Membership "
        "Cross-Validation v1"
    )
    print("=" * 72)

    print(f"Start date: {args.start}")
    print("Research-only: TRUE")
    print("PIT-perfect: FALSE")
    print()

    # ---------------------------------------------------------
    # Load sources
    # ---------------------------------------------------------

    fja = load_fja(args.start)

    hans = load_hanshof(args.start)

    common_dates = sorted(
        set(fja) & set(hans)
    )

    if not common_dates:
        print(
            "ERROR: no common dates between fja and hanshof.",
            file=sys.stderr,
        )
        return 1

    # To avoid unnecessary pitindex calls, use only dates
    # where the two primary sources actually provide snapshots.
    pit = load_pitindex(common_dates)

    # ---------------------------------------------------------
    # Compare
    # ---------------------------------------------------------

    comparison = compare_snapshots(
        fja,
        hans,
        pit,
    )

    discrepancies = build_discrepancy_table(
        fja,
        hans,
    )

    summary = summarize(
        comparison,
    )

    # ---------------------------------------------------------
    # Output
    # ---------------------------------------------------------

    comparison_path = (
        output_dir
        / "membership_snapshot_comparison_v1.csv"
    )

    discrepancies_path = (
        output_dir
        / "membership_discrepancies_v1.csv"
    )

    summary_path = (
        output_dir
        / "membership_cross_validation_summary_v1.json"
    )

    comparison.to_csv(
        comparison_path,
        index=False,
    )

    discrepancies.to_csv(
        discrepancies_path,
        index=False,
    )

    with open(
        summary_path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            summary,
            f,
            indent=2,
        )

    # ---------------------------------------------------------
    # Console report
    # ---------------------------------------------------------

    print()
    print("=" * 72)
    print("RESULT")
    print("=" * 72)

    print(
        f"Common snapshots: "
        f"{summary['common_snapshot_dates']}"
    )

    print(
        f"Date range: "
        f"{summary['first_common_date']} "
        f"→ "
        f"{summary['last_common_date']}"
    )

    print(
        f"Mean Jaccard: "
        f"{summary['mean_jaccard']:.6f}"
    )

    print(
        f"Median Jaccard: "
        f"{summary['median_jaccard']:.6f}"
    )

    print(
        f"Minimum Jaccard: "
        f"{summary['minimum_jaccard']:.6f}"
    )

    print(
        f"Mean overlap: "
        f"{summary['mean_overlap_pct']:.4f}%"
    )

    print(
        f"Conflict ratio: "
        f"{summary['conflict_ratio']:.4%}"
    )

    print()
    print("Classification:")
    for key, value in (
        summary["classification_counts"]
        .items()
    ):
        print(
            f"  {key}: {value}"
        )

    print()
    print("Artifacts:")
    print(
        f"  {comparison_path}"
    )
    print(
        f"  {discrepancies_path}"
    )
    print(
        f"  {summary_path}"
    )

    print()
    print(
        f"FINAL STATUS: {summary['status']}"
    )

    # ---------------------------------------------------------
    # Show worst discrepancies
    # ---------------------------------------------------------

    if not comparison.empty:
        worst = (
            comparison
            .sort_values(
                "fja_hans_jaccard",
                ascending=True,
            )
            .head(20)
        )

        print()
        print("=" * 72)
        print("WORST 20 SNAPSHOT AGREEMENTS")
        print("=" * 72)

        print(
            worst[
                [
                    "asof_date",
                    "fja_count",
                    "hans_count",
                    "pit_count",
                    "fja_hans_jaccard",
                    "fja_only",
                    "hans_only",
                    "classification",
                ]
            ].to_string(
                index=False
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
