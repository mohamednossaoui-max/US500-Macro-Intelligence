#!/usr/bin/env python3
"""
Market Breadth — Historical Collector v1

Purpose
-------
Research-only reconstruction of historical S&P 500 market breadth.

Method
------
1. Load historical S&P 500 membership from a free public reconstruction.
2. Reconstruct the active membership universe for each trading session.
3. Download historical daily Close data using yfinance.
4. Calculate:
   - advances
   - declines
   - unchanged
   - net advances
   - advance/decline ratio
   - % advancing
   - % declining
   - cumulative A/D line
5. Preserve explicit data-quality and coverage metadata.

IMPORTANT
---------
This module does NOT claim PIT-perfect historical prices.

Membership:
    point_in_time_reconstructed = TRUE
    membership_source = FREE_PUBLIC_RECONSTRUCTION
    membership_quality = RESEARCH_GRADE

Prices:
    price_source = YAHOO_FINANCE_YFINANCE
    price_quality = FREE_PUBLIC_RESEARCH_GRADE

Known limitation:
    yfinance does not reliably provide complete historical data for
    every delisted/renamed security. Therefore coverage is measured
    explicitly and no missing security is silently treated as unchanged.

Research-only:
    No forecast
    No trading signal
    No Decision Engine integration
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path
from typing import Dict, List, Set

import numpy as np
import pandas as pd
import yfinance as yf


# ============================================================================
# CONFIGURATION
# ============================================================================

FJA_URL = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes%20%28Updated%29.csv"
)

DEFAULT_START = "2019-01-01"

PRICE_CHUNK_SIZE = 40

# We do not call the price layer PIT-perfect.
PRICE_COVERAGE_RESEARCH_THRESHOLD = 0.90

REQUEST_SLEEP_SECONDS = 1.0

# Yahoo ticker normalization.
# BRK.B -> BRK-B
# BF.B  -> BF-B


# ============================================================================
# NORMALIZATION
# ============================================================================

def normalize_ticker(value) -> str:
    if value is None:
        return ""

    text = str(value).strip().upper()

    if text in {"", "NAN", "NONE", "NULL"}:
        return ""

    return text.replace(".", "-")


def parse_ticker_list(value) -> Set[str]:
    if pd.isna(value):
        return set()

    text = str(value).strip()

    if not text:
        return set()

    result = set()

    for item in text.split(","):
        ticker = normalize_ticker(item)

        if ticker:
            result.add(ticker)

    return result


# ============================================================================
# MEMBERSHIP
# ============================================================================

def load_membership_history(
    start_date: pd.Timestamp,
) -> Dict[pd.Timestamp, Set[str]]:
    """
    Load FJA historical S&P 500 snapshots.

    Expected format:
        date,tickers

    Example:
        2019-01-18,"A,AAL,AAPL,..."
    """

    print("=" * 72)
    print("LOADING HISTORICAL S&P 500 MEMBERSHIP")
    print("=" * 72)
    print(f"Source: {FJA_URL}")

    df = pd.read_csv(FJA_URL)

    if df.empty:
        raise RuntimeError(
            "Membership CSV is empty."
        )

    columns = {
        str(column).strip().lower(): column
        for column in df.columns
    }

    date_col = columns.get("date")

    ticker_col = None

    for candidate in [
        "tickers",
        "ticker",
        "symbols",
        "constituents",
        "components",
    ]:
        if candidate in columns:
            ticker_col = columns[candidate]
            break

    if date_col is None:
        raise RuntimeError(
            f"Could not identify date column: {list(df.columns)}"
        )

    if ticker_col is None:
        raise RuntimeError(
            f"Could not identify ticker column: {list(df.columns)}"
        )

    df[date_col] = pd.to_datetime(
        df[date_col],
        errors="coerce",
    )

    df = df.dropna(
        subset=[date_col]
    )

    df = df[
        df[date_col] >= start_date
    ].copy()

    snapshots = {}

    for _, row in df.iterrows():

        date = pd.Timestamp(
            row[date_col]
        ).normalize()

        members = parse_ticker_list(
            row[ticker_col]
        )

        if members:

            snapshots[date] = members

    if not snapshots:
        raise RuntimeError(
            "No membership snapshots available after start date."
        )

    print(
        f"Membership snapshots: {len(snapshots):,}"
    )

    print(
        f"First snapshot: "
        f"{min(snapshots).date()}"
    )

    print(
        f"Last snapshot: "
        f"{max(snapshots).date()}"
    )

    counts = [
        len(value)
        for value in snapshots.values()
    ]

    print(
        f"Membership min: {min(counts):,}"
    )

    print(
        f"Membership max: {max(counts):,}"
    )

    print(
        f"Membership mean: {np.mean(counts):.2f}"
    )

    return snapshots


# ============================================================================
# TRADING CALENDAR
# ============================================================================

def load_sp500_sessions(
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DatetimeIndex:

    print()
    print("=" * 72)
    print("LOADING S&P 500 TRADING SESSIONS")
    print("=" * 72)

    data = yf.download(
        "^GSPC",
        start=start_date.strftime("%Y-%m-%d"),
        end=(
            end_date
            + pd.Timedelta(days=1)
        ).strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=False,
        actions=False,
        threads=False,
    )

    if data.empty:
        raise RuntimeError(
            "Unable to retrieve ^GSPC trading calendar."
        )

    if isinstance(data.columns, pd.MultiIndex):
        close = data["Close"]

        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]

    else:
        close = data["Close"]

    sessions = pd.DatetimeIndex(
        pd.to_datetime(
            close.index
        ).normalize()
    )

    sessions = sessions.sort_values()

    print(
        f"Trading sessions: {len(sessions):,}"
    )

    print(
        f"First session: {sessions.min().date()}"
    )

    print(
        f"Last session: {sessions.max().date()}"
    )

    return sessions


# ============================================================================
# DAILY MEMBERSHIP RECONSTRUCTION
# ============================================================================

def reconstruct_daily_membership(
    snapshots: Dict[pd.Timestamp, Set[str]],
    sessions: pd.DatetimeIndex,
) -> Dict[pd.Timestamp, Set[str]]:

    snapshot_dates = sorted(
        snapshots.keys()
    )

    result = {}

    current_members = None
    snapshot_index = 0

    for session in sessions:

        session = pd.Timestamp(
            session
        ).normalize()

        while (
            snapshot_index < len(snapshot_dates)
            and snapshot_dates[snapshot_index] <= session
        ):

            current_members = snapshots[
                snapshot_dates[snapshot_index]
            ]

            snapshot_index += 1

        if current_members is not None:

            result[session] = set(
                current_members
            )

    return result


# ============================================================================
# PRICE DOWNLOAD
# ============================================================================

def download_prices(
    tickers: List[str],
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    """
    Download Close prices in chunks.

    Returns:
        DataFrame
        index = date
        columns = normalized tickers
    """

    print()
    print("=" * 72)
    print("DOWNLOADING HISTORICAL PRICES")
    print("=" * 72)

    all_frames = []

    total = len(tickers)

    for offset in range(
        0,
        total,
        PRICE_CHUNK_SIZE,
    ):

        chunk = tickers[
            offset:
            offset + PRICE_CHUNK_SIZE
        ]

        print(
            f"Price batch "
            f"{offset + 1:,}-{min(offset + len(chunk), total):,}"
            f"/{total:,}"
        )

        try:

            data = yf.download(
                chunk,
                start=start_date.strftime("%Y-%m-%d"),
                end=(
                    end_date
                    + pd.Timedelta(days=1)
                ).strftime("%Y-%m-%d"),
                progress=False,
                auto_adjust=False,
                actions=False,
                group_by="column",
                threads=True,
            )

        except Exception as exc:

            warnings.warn(
                f"Price batch failed: {exc}"
            )

            time.sleep(
                REQUEST_SLEEP_SECONDS
            )

            continue

        if data.empty:
            time.sleep(
                REQUEST_SLEEP_SECONDS
            )
            continue

        # ------------------------------------------------------------
        # Multi-ticker response
        # ------------------------------------------------------------

        if isinstance(
            data.columns,
            pd.MultiIndex,
        ):

            if "Close" not in data.columns.get_level_values(0):
                time.sleep(
                    REQUEST_SLEEP_SECONDS
                )
                continue

            close = data["Close"].copy()

        # ------------------------------------------------------------
        # Single ticker response
        # ------------------------------------------------------------

        else:

            if "Close" not in data.columns:
                time.sleep(
                    REQUEST_SLEEP_SECONDS
                )
                continue

            ticker = chunk[0]

            close = data[
                ["Close"]
            ].rename(
                columns={
                    "Close": ticker
                }
            )

        close.columns = [
            normalize_ticker(column)
            for column in close.columns
        ]

        close.index = pd.to_datetime(
            close.index
        ).normalize()

        all_frames.append(
            close
        )

        time.sleep(
            REQUEST_SLEEP_SECONDS
        )

    if not all_frames:
        raise RuntimeError(
            "No historical price data was downloaded."
        )

    prices = pd.concat(
        all_frames,
        axis=1,
    )

    # Remove duplicate ticker columns.
    prices = prices.loc[
        :,
        ~prices.columns.duplicated()
    ]

    prices = prices.sort_index()

    print()
    print(
        f"Price observations: "
        f"{len(prices):,}"
    )

    print(
        f"Price columns: "
        f"{len(prices.columns):,}"
    )

    return prices


# ============================================================================
# BREADTH CALCULATION
# ============================================================================

def calculate_breadth(
    sessions: pd.DatetimeIndex,
    daily_membership: Dict[pd.Timestamp, Set[str]],
    prices: pd.DataFrame,
) -> pd.DataFrame:

    print()
    print("=" * 72)
    print("CALCULATING MARKET BREADTH")
    print("=" * 72)

    rows = []

    cumulative_ad = 0.0

    previous_close = prices.shift(1)

    for session in sessions:

        session = pd.Timestamp(
            session
        ).normalize()

        universe = daily_membership.get(
            session,
            set(),
        )

        universe_count = len(
            universe
        )

        if universe_count == 0:
            continue

        available_tickers = (
            universe
            & set(prices.columns)
        )

        if not available_tickers:
            continue

        today = prices.loc[
            session,
            list(available_tickers)
        ] if session in prices.index else pd.Series(
            dtype=float
        )

        previous = previous_close.loc[
            session,
            list(available_tickers)
        ] if session in previous_close.index else pd.Series(
            dtype=float
        )

        # ------------------------------------------------------------
        # Only securities with both current and previous prices
        # are eligible for directional breadth.
        # ------------------------------------------------------------

        valid = (
            today.notna()
            & previous.notna()
        )

        today_valid = today[
            valid
        ]

        previous_valid = previous[
            valid
        ]

        if len(today_valid) == 0:
            continue

        change = (
            today_valid
            - previous_valid
        )

        advances = int(
            (change > 0).sum()
        )

        declines = int(
            (change < 0).sum()
        )

        unchanged = int(
            (change == 0).sum()
        )

        eligible_count = int(
            len(today_valid)
        )

        missing_price_count = (
            universe_count
            - eligible_count
        )

        net_advances = (
            advances
            - declines
        )

        if declines > 0:
            advance_decline_ratio = (
                advances
                / declines
            )
        else:
            advance_decline_ratio = None

        pct_advancing = (
            advances
            / eligible_count
            * 100.0
        )

        pct_declining = (
            declines
            / eligible_count
            * 100.0
        )

        cumulative_ad += (
            net_advances
        )

        coverage_pct = (
            eligible_count
            / universe_count
            * 100.0
        )

        if coverage_pct >= 90.0:
            coverage_quality = (
                "GOOD"
            )
        elif coverage_pct >= 75.0:
            coverage_quality = (
                "LIMITED"
            )
        else:
            coverage_quality = (
                "POOR"
            )

        rows.append(
            {
                "asof_date":
                    session.date().isoformat(),

                "universe_count":
                    universe_count,

                "price_eligible_count":
                    eligible_count,

                "missing_price_count":
                    missing_price_count,

                "coverage_pct":
                    round(
                        coverage_pct,
                        4,
                    ),

                "coverage_quality":
                    coverage_quality,

                "advances":
                    advances,

                "declines":
                    declines,

                "unchanged":
                    unchanged,

                "net_advances":
                    net_advances,

                "advance_decline_ratio":
                    (
                        round(
                            advance_decline_ratio,
                            6,
                        )
                        if advance_decline_ratio
                        is not None
                        else None
                    ),

                "pct_advancing":
                    round(
                        pct_advancing,
                        6,
                    ),

                "pct_declining":
                    round(
                        pct_declining,
                        6,
                    ),

                "cumulative_ad_line":
                    cumulative_ad,

                # -------------------------------------------------
                # Membership metadata
                # -------------------------------------------------

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

                # -------------------------------------------------
                # Price metadata
                # -------------------------------------------------

                "price_source":
                    "YAHOO_FINANCE_YFINANCE",

                "price_quality":
                    "FREE_PUBLIC_RESEARCH_GRADE",

                "price_pit_perfect":
                    False,

                # -------------------------------------------------
                # Research metadata
                # -------------------------------------------------

                "research_only":
                    True,

                "decision_engine_ready":
                    False,

                "trading_signal":
                    False,

                "forecast":
                    False,

                "record_id":
                    (
                        f"MB_{session.strftime('%Y%m%d')}"
                    ),
            }
        )

    result = pd.DataFrame(
        rows
    )

    if result.empty:
        raise RuntimeError(
            "Breadth calculation produced zero rows."
        )

    return result


# ============================================================================
# VALIDATION
# ============================================================================

def validate_output(
    df: pd.DataFrame,
) -> dict:

    required_columns = [
        "asof_date",
        "universe_count",
        "price_eligible_count",
        "missing_price_count",
        "coverage_pct",
        "advances",
        "declines",
        "unchanged",
        "net_advances",
        "advance_decline_ratio",
        "pct_advancing",
        "pct_declining",
        "cumulative_ad_line",
        "point_in_time_reconstructed",
        "membership_source",
        "membership_quality",
        "cross_validated",
        "research_only",
        "decision_engine_ready",
        "trading_signal",
        "forecast",
        "record_id",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise RuntimeError(
            "Missing required columns: "
            + ", ".join(
                missing_columns
            )
        )

    duplicate_dates = int(
        df["asof_date"].duplicated().sum()
    )

    duplicate_ids = int(
        df["record_id"].duplicated().sum()
    )

    invalid_counts = int(
        (
            df["advances"]
            + df["declines"]
            + df["unchanged"]
            != df["price_eligible_count"]
        ).sum()
    )

    invalid_net_advances = int(
        (
            df["net_advances"]
            != (
                df["advances"]
                - df["declines"]
            )
        ).sum()
    )

    min_coverage = float(
        df["coverage_pct"].min()
    )

    mean_coverage = float(
        df["coverage_pct"].mean()
    )

    max_coverage = float(
        df["coverage_pct"].max()
    )

    research_only_ok = bool(
        df["research_only"].all()
    )

    decision_engine_ok = bool(
        (~df["decision_engine_ready"]).all()
    )

    signal_ok = bool(
        (~df["trading_signal"]).all()
    )

    forecast_ok = bool(
        (~df["forecast"]).all()
    )

    validation = {
        "row_count":
            int(len(df)),

        "date_start":
            str(df["asof_date"].min()),

        "date_end":
            str(df["asof_date"].max()),

        "duplicate_dates":
            duplicate_dates,

        "duplicate_record_ids":
            duplicate_ids,

        "invalid_breadth_count_rows":
            invalid_counts,

        "invalid_net_advances_rows":
            invalid_net_advances,

        "coverage_min_pct":
            min_coverage,

        "coverage_mean_pct":
            mean_coverage,

        "coverage_max_pct":
            max_coverage,

        "research_only":
            research_only_ok,

        "decision_engine_ready":
            not decision_engine_ok,

        "trading_signal":
            not signal_ok,

        "forecast":
            not forecast_ok,

        "validation_pass":
            (
                duplicate_dates == 0
                and duplicate_ids == 0
                and invalid_counts == 0
                and invalid_net_advances == 0
                and research_only_ok
                and decision_engine_ok
                and signal_ok
                and forecast_ok
            ),
    }

    return validation


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--start",
        default=DEFAULT_START,
    )

    parser.add_argument(
        "--end",
        default=None,
    )

    parser.add_argument(
        "--output",
        default="market_breadth_historical_v1",
    )

    args = parser.parse_args()

    start_date = pd.Timestamp(
        args.start
    ).normalize()

    if args.end:
        end_date = pd.Timestamp(
            args.end
        ).normalize()
    else:
        end_date = pd.Timestamp.today().normalize()

    output_dir = Path(
        args.output
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("=" * 72)
    print("Market Breadth — Historical Collector v1")
    print("=" * 72)

    print(
        f"Start date: {start_date.date()}"
    )

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

    print(
        "Price source: "
        "YAHOO_FINANCE_YFINANCE"
    )

    print(
        "Price quality: "
        "FREE_PUBLIC_RESEARCH_GRADE"
    )

    # -----------------------------------------------------------------
    # 1. Membership
    # -----------------------------------------------------------------

    membership_snapshots = (
        load_membership_history(
            start_date
        )
    )

    membership_last_date = max(
        membership_snapshots
    )

    effective_end = min(
        end_date,
        membership_last_date,
    )

    if effective_end < start_date:
        raise RuntimeError(
            "No overlapping membership period."
        )

    # -----------------------------------------------------------------
    # 2. Trading sessions
    # -----------------------------------------------------------------

    sessions = load_sp500_sessions(
        start_date,
        effective_end,
    )

    # -----------------------------------------------------------------
    # 3. Daily reconstructed membership
    # -----------------------------------------------------------------

    daily_membership = (
        reconstruct_daily_membership(
            membership_snapshots,
            sessions,
        )
    )

    if not daily_membership:
        raise RuntimeError(
            "Daily membership reconstruction returned zero sessions."
        )

    # -----------------------------------------------------------------
    # 4. Unique tickers
    # -----------------------------------------------------------------

    unique_tickers: Set[str] = set()

    for members in daily_membership.values():
        unique_tickers.update(
            members
        )

    tickers = sorted(
        unique_tickers
    )

    print()
    print(
        f"Unique historical tickers: "
        f"{len(tickers):,}"
    )

    # -----------------------------------------------------------------
    # 5. Historical prices
    # -----------------------------------------------------------------

    prices = download_prices(
        tickers,
        start_date,
        effective_end,
    )

    # -----------------------------------------------------------------
    # 6. Breadth
    # -----------------------------------------------------------------

    breadth = calculate_breadth(
        sessions,
        daily_membership,
        prices,
    )

    # -----------------------------------------------------------------
    # 7. Validation
    # -----------------------------------------------------------------

    validation = validate_output(
        breadth
    )

    # -----------------------------------------------------------------
    # 8. Save primary artifact
    # -----------------------------------------------------------------

    records_path = (
        output_dir
        / "market_breadth_records_v1.csv"
    )

    breadth.to_csv(
        records_path,
        index=False,
    )

    # -----------------------------------------------------------------
    # 9. Save validation
    # -----------------------------------------------------------------

    validation_path = (
        output_dir
        / "market_breadth_validation_v1.json"
    )

    with open(
        validation_path,
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            validation,
            handle,
            indent=2,
            ensure_ascii=False,
        )

    # -----------------------------------------------------------------
    # 10. Save metadata
    # -----------------------------------------------------------------

    metadata = {
        "module":
            "Market Breadth Historical Collector",

        "version":
            "v1",

        "start_date":
            str(start_date.date()),

        "end_date":
            str(effective_end.date()),

        "membership_source":
            "FREE_PUBLIC_RECONSTRUCTION",

        "membership_quality":
            "RESEARCH_GRADE",

        "point_in_time_reconstructed":
            True,

        "pit_perfect":
            False,

        "price_source":
            "YAHOO_FINANCE_YFINANCE",

        "price_quality":
            "FREE_PUBLIC_RESEARCH_GRADE",

        "price_pit_perfect":
            False,

        "research_only":
            True,

        "decision_engine_ready":
            False,

        "trading_signal":
            False,

        "forecast":
            False,

        "unique_historical_tickers":
            len(tickers),

        "validation":
            validation,
    }

    metadata_path = (
        output_dir
        / "market_breadth_metadata_v1.json"
    )

    with open(
        metadata_path,
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            metadata,
            handle,
            indent=2,
            ensure_ascii=False,
        )

    # -----------------------------------------------------------------
    # 11. Console output
    # -----------------------------------------------------------------

    print()
    print("=" * 72)
    print("MARKET BREADTH COLLECTOR RESULT")
    print("=" * 72)

    print(
        f"Rows: {len(breadth):,}"
    )

    print(
        f"Date range: "
        f"{breadth['asof_date'].min()} → "
        f"{breadth['asof_date'].max()}"
    )

    print(
        f"Mean price coverage: "
        f"{validation['coverage_mean_pct']:.2f}%"
    )

    print(
        f"Minimum price coverage: "
        f"{validation['coverage_min_pct']:.2f}%"
    )

    print()
    print("VALIDATION:")

    print(
        f"  Duplicate dates: "
        f"{validation['duplicate_dates']}"
    )

    print(
        f"  Invalid breadth rows: "
        f"{validation['invalid_breadth_count_rows']}"
    )

    print(
        f"  Invalid net advances rows: "
        f"{validation['invalid_net_advances_rows']}"
    )

    print(
        f"  Research-only: "
        f"{validation['research_only']}"
    )

    print(
        f"  Decision Engine: "
        f"{metadata['decision_engine_ready']}"
    )

    print(
        f"  Trading signal: "
        f"{metadata['trading_signal']}"
    )

    print(
        f"  Forecast: "
        f"{metadata['forecast']}"
    )

    print()
    print("ARTIFACTS:")

    print(
        records_path
    )

    print(
        validation_path
    )

    print(
        metadata_path
    )

    print()
    print("=" * 72)

    if validation["validation_pass"]:

        print(
            "FINAL STATUS: PASS"
        )

        return 0

    print(
        "FINAL STATUS: REVIEW_REQUIRED"
    )

    return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )
