"""
Corporate Earnings Intelligence V2
===================================

Research-only corporate earnings intelligence.

Purpose
-------
Collect historical and recent EPS earnings-event data from
Alpha Vantage and build a point-in-time-safe earnings dataset.

V2 principles
-------------
- Uses Alpha Vantage EARNINGS endpoint.
- Does NOT use EARNINGS_ESTIMATES revisions.
- Preserves event-time EPS actual / consensus / surprise.
- Conservative classification.
- Revenue data is intentionally UNKNOWN because the EARNINGS
  endpoint does not provide reliable event-time revenue
  actual/consensus fields for this module.
- Historical analog eligibility is explicitly tracked.
- No trading signal.
- No Decision Engine integration.

Rate-limit protection
---------------------
Alpha Vantage free API keys have request-rate limitations.

This version therefore:
- waits between requests
- detects rate-limit responses
- retries automatically
- uses progressively longer waits
- continues safely if a company ultimately fails
"""

import os
import time
import warnings

import numpy as np
import pandas as pd
import requests


# ============================================================
# CONFIGURATION
# ============================================================

API_URL = "https://www.alphavantage.co/query"

API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")

# ------------------------------------------------------------
# Rate-limit protection
# ------------------------------------------------------------

# Normal delay between successful company requests.
REQUEST_DELAY_SECONDS = 12.0

# Delay before the first retry after a rate-limit response.
RATE_LIMIT_RETRY_DELAY_SECONDS = 20.0

# Maximum number of retries after rate-limit / temporary errors.
MAX_RETRIES = 4

# HTTP timeout.
REQUEST_TIMEOUT_SECONDS = 30

# Alpha Vantage may occasionally return transient errors.
TRANSIENT_RETRY_DELAY_SECONDS = 10.0

# ------------------------------------------------------------
# Test universe
# ------------------------------------------------------------

COMPANIES = [
    {
        "ticker": "MSFT",
        "sector": "Information Technology",
    },
    {
        "ticker": "AAPL",
        "sector": "Information Technology",
    },
    {
        "ticker": "NVDA",
        "sector": "Information Technology",
    },
    {
        "ticker": "AMZN",
        "sector": "Consumer Discretionary",
    },
    {
        "ticker": "WMT",
        "sector": "Consumer Staples",
    },
    {
        "ticker": "JPM",
        "sector": "Financials",
    },
    {
        "ticker": "JNJ",
        "sector": "Health Care",
    },
    {
        "ticker": "XOM",
        "sector": "Energy",
    },
    {
        "ticker": "CAT",
        "sector": "Industrials",
    },
    {
        "ticker": "PG",
        "sector": "Consumer Staples",
    },
]

# ------------------------------------------------------------
# EPS classification thresholds
# ------------------------------------------------------------

LARGE_BEAT_THRESHOLD = 10.0
BEAT_THRESHOLD = 3.0
IN_LINE_LOWER_THRESHOLD = -3.0
MISS_THRESHOLD = -10.0

# ------------------------------------------------------------
# User-Agent
# ------------------------------------------------------------

USER_AGENT = (
    "US500-Macro-Intelligence/2.0 "
    "(Corporate-Earnings-Intelligence)"
)

# ------------------------------------------------------------
# Output files
# ------------------------------------------------------------

EVENTS_OUTPUT = (
    "earnings_breadth_events_v2.csv"
)

LATEST_COMPANY_OUTPUT = (
    "earnings_latest_company_v2.csv"
)

BREADTH_SUMMARY_OUTPUT = (
    "earnings_breadth_summary_v2.csv"
)

SECTOR_BREADTH_OUTPUT = (
    "earnings_sector_breadth_v2.csv"
)


# ============================================================
# API VALIDATION
# ============================================================

def validate_api_key():
    """
    Validate that the Alpha Vantage API key exists.
    """

    if not API_KEY:
        raise RuntimeError(
            "ALPHAVANTAGE_API_KEY environment variable "
            "is not set."
        )

    print("Alpha Vantage API key detected.")


# ============================================================
# HELPERS
# ============================================================

def safe_float(value):
    """
    Convert value to float safely.
    """

    if value is None:
        return np.nan

    try:
        if pd.isna(value):
            return np.nan
    except Exception:
        pass

    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def normalize_date(value):
    """
    Normalize a date string to YYYY-MM-DD.

    Returns None if invalid.
    """

    if value is None:
        return None

    try:
        parsed = pd.to_datetime(
            value,
            errors="coerce"
        )

        if pd.isna(parsed):
            return None

        return parsed.strftime("%Y-%m-%d")

    except Exception:
        return None


def calculate_surprise_percentage(
    actual,
    consensus
):
    """
    Calculate EPS surprise percentage.

    Formula:

        (actual - consensus)
        / abs(consensus) * 100
    """

    actual = safe_float(actual)
    consensus = safe_float(consensus)

    if pd.isna(actual) or pd.isna(consensus):
        return np.nan

    if consensus == 0:
        return np.nan

    return (
        (actual - consensus)
        / abs(consensus)
        * 100.0
    )


def classify_eps_result(
    surprise_pct
):
    """
    Classify EPS earnings surprise.

    Thresholds:

        >= +10%   LARGE_BEAT
        >= +3%    BEAT
        >  -3%    IN_LINE
        > -10%    MISS
        <= -10%   LARGE_MISS
    """

    surprise_pct = safe_float(
        surprise_pct
    )

    if pd.isna(surprise_pct):
        return "UNKNOWN"

    if surprise_pct >= LARGE_BEAT_THRESHOLD:
        return "LARGE_BEAT"

    if surprise_pct >= BEAT_THRESHOLD:
        return "BEAT"

    if surprise_pct > IN_LINE_LOWER_THRESHOLD:
        return "IN_LINE"

    if surprise_pct > MISS_THRESHOLD:
        return "MISS"

    return "LARGE_MISS"


def is_rate_limit_response(data):
    """
    Detect Alpha Vantage rate-limit responses.
    """

    if not isinstance(data, dict):
        return False

    text_parts = []

    for key in [
        "Note",
        "Information",
        "Error Message",
    ]:
        value = data.get(key)

        if value:
            text_parts.append(
                str(value).lower()
            )

    combined = " ".join(text_parts)

    rate_limit_keywords = [
        "rate limit",
        "api call frequency",
        "requests per second",
        "requests per day",
        "spreading out",
        "premium plans",
        "25 requests per day",
        "1 request per second",
    ]

    return any(
        keyword in combined
        for keyword in rate_limit_keywords
    )


def extract_api_message(data):
    """
    Extract a useful Alpha Vantage API message.
    """

    if not isinstance(data, dict):
        return None

    for key in [
        "Note",
        "Information",
        "Error Message",
    ]:
        value = data.get(key)

        if value:
            return str(value)

    return None


# ============================================================
# RATE-LIMIT SAFE API REQUEST
# ============================================================

def request_earnings(
    ticker
):
    """
    Request Alpha Vantage EARNINGS data with retry logic.

    Returns:
        dict on success
        None on final failure
    """

    params = {
        "function": "EARNINGS",
        "symbol": ticker,
        "apikey": API_KEY,
    }

    headers = {
        "User-Agent": USER_AGENT
    }

    for attempt in range(
        MAX_RETRIES + 1
    ):

        attempt_number = attempt + 1

        try:

            print(
                f"Requesting EARNINGS / {ticker} "
                f"(attempt {attempt_number}/"
                f"{MAX_RETRIES + 1})"
            )

            response = requests.get(
                API_URL,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            response.raise_for_status()

            data = response.json()

            # ------------------------------------------------
            # Rate limit detected
            # ------------------------------------------------

            if is_rate_limit_response(data):

                message = extract_api_message(
                    data
                )

                print(
                    f"RATE LIMIT for {ticker}: "
                    f"{message}"
                )

                if attempt < MAX_RETRIES:

                    # Progressive retry delay:
                    #
                    # retry 1 -> 20 sec
                    # retry 2 -> 40 sec
                    # retry 3 -> 60 sec
                    # retry 4 -> 80 sec
                    #
                    # This is deliberately conservative.

                    retry_delay = (
                        RATE_LIMIT_RETRY_DELAY_SECONDS
                        * (attempt + 1)
                    )

                    print(
                        f"Rate-limit retry wait: "
                        f"{retry_delay:.1f} seconds..."
                    )

                    time.sleep(
                        retry_delay
                    )

                    continue

                print(
                    f"Maximum retries reached "
                    f"for {ticker}."
                )

                return None

            # ------------------------------------------------
            # Other Alpha Vantage error
            # ------------------------------------------------

            api_message = extract_api_message(
                data
            )

            if api_message:

                print(
                    f"Alpha Vantage message "
                    f"for {ticker}: "
                    f"{api_message}"
                )

                # If no earnings data exists but the response
                # is not a rate limit, return safely.
                return data

            # ------------------------------------------------
            # Validate response
            # ------------------------------------------------

            if (
                "quarterlyEarnings"
                not in data
            ):

                print(
                    f"WARNING: No "
                    f"quarterlyEarnings field "
                    f"for {ticker}."
                )

                return data

            return data

        except requests.exceptions.Timeout:

            print(
                f"TIMEOUT for {ticker}"
            )

            if attempt < MAX_RETRIES:

                retry_delay = (
                    TRANSIENT_RETRY_DELAY_SECONDS
                    * (attempt + 1)
                )

                print(
                    f"Retrying in "
                    f"{retry_delay:.1f} seconds..."
                )

                time.sleep(
                    retry_delay
                )

                continue

            print(
                f"Maximum timeout retries "
                f"reached for {ticker}."
            )

            return None

        except requests.exceptions.RequestException as exc:

            print(
                f"REQUEST ERROR for "
                f"{ticker}: {exc}"
            )

            if attempt < MAX_RETRIES:

                retry_delay = (
                    TRANSIENT_RETRY_DELAY_SECONDS
                    * (attempt + 1)
                )

                print(
                    f"Retrying in "
                    f"{retry_delay:.1f} seconds..."
                )

                time.sleep(
                    retry_delay
                )

                continue

            return None

        except ValueError as exc:

            print(
                f"JSON ERROR for "
                f"{ticker}: {exc}"
            )

            return None

        except Exception as exc:

            print(
                f"UNEXPECTED ERROR for "
                f"{ticker}: {exc}"
            )

            return None

    return None


# ============================================================
# COMPANY EARNINGS FETCH
# ============================================================

def fetch_company_earnings(
    ticker,
    sector
):
    """
    Fetch and normalize Alpha Vantage EARNINGS
    data for one company.
    """

    data = request_earnings(
        ticker
    )

    if data is None:

        print(
            f"FAILED: {ticker} "
            f"returned no usable response."
        )

        return []

    quarterly = data.get(
        "quarterlyEarnings",
        []
    )

    if not isinstance(
        quarterly,
        list
    ):

        print(
            f"WARNING: Invalid quarterly "
            f"earnings structure for {ticker}."
        )

        return []

    print(
        f"Records received: {len(quarterly)}"
    )

    rows = []

    for item in quarterly:

        if not isinstance(
            item,
            dict
        ):
            continue

        fiscal_date_ending = normalize_date(
            item.get(
                "fiscalDateEnding"
            )
        )

        reported_date = normalize_date(
            item.get(
                "reportedDate"
            )
        )

        if reported_date is None:
            continue

        # ----------------------------------------------------
        # EPS
        # ----------------------------------------------------

        actual = safe_float(
            item.get(
                "reportedEPS"
            )
        )

        consensus = safe_float(
            item.get(
                "estimatedEPS"
            )
        )

        provider_surprise = safe_float(
            item.get(
                "surprise"
            )
        )

        provider_surprise_pct = safe_float(
            item.get(
                "surprisePercentage"
            )
        )

        calculated_surprise_pct = (
            calculate_surprise_percentage(
                actual,
                consensus
            )
        )

        # ----------------------------------------------------
        # Prefer Alpha Vantage's event-time
        # surprisePercentage when available.
        #
        # Otherwise calculate it ourselves.
        # ----------------------------------------------------

        if not pd.isna(
            provider_surprise_pct
        ):

            effective_surprise_pct = (
                provider_surprise_pct
            )

        else:

            effective_surprise_pct = (
                calculated_surprise_pct
            )

        # ----------------------------------------------------
        # Classification
        # ----------------------------------------------------

        eps_result_class = (
            classify_eps_result(
                effective_surprise_pct
            )
        )

        if (
            not pd.isna(actual)
            and not pd.isna(consensus)
        ):

            earnings_beat = (
                actual > consensus
            )

        else:

            earnings_beat = np.nan

        # ----------------------------------------------------
        # Revenue
        #
        # Intentionally UNKNOWN in V2.
        # Alpha Vantage EARNINGS endpoint does not provide
        # reliable event-time revenue actual/consensus
        # fields for this research module.
        # ----------------------------------------------------

        revenue_actual = np.nan
        revenue_consensus = np.nan
        revenue_surprise = np.nan
        revenue_surprise_pct = np.nan

        revenue_result_class = "UNKNOWN"

        # ----------------------------------------------------
        # Point-in-time metadata
        # ----------------------------------------------------

        point_in_time = True

        point_in_time_safe = True

        historical_analog_eligible = True

        # ----------------------------------------------------
        # Build row
        # ----------------------------------------------------

        rows.append({
            "ticker": ticker,
            "sector": sector,

            "fiscal_date_ending": (
                fiscal_date_ending
            ),

            "reported_date": (
                reported_date
            ),

            "eps_actual": actual,

            "eps_consensus": consensus,

            "eps_surprise": (
                provider_surprise
            ),

            "eps_surprise_pct": (
                effective_surprise_pct
            ),

            "calculated_eps_surprise_pct": (
                calculated_surprise_pct
            ),

            "eps_result_class": (
                eps_result_class
            ),

            "earnings_beat": (
                earnings_beat
            ),

            "revenue_actual": (
                revenue_actual
            ),

            "revenue_consensus": (
                revenue_consensus
            ),

            "revenue_surprise": (
                revenue_surprise
            ),

            "revenue_surprise_pct": (
                revenue_surprise_pct
            ),

            "revenue_result_class": (
                revenue_result_class
            ),

            "point_in_time": (
                point_in_time
            ),

            "point_in_time_safe": (
                point_in_time_safe
            ),

            "historical_analog_eligible": (
                historical_analog_eligible
            ),

            "source": (
                "Alpha Vantage EARNINGS"
            ),

            "source_type": (
                "primary_event_data"
            ),

            "data_quality": (
                "PRIMARY_EVENT_DATA"
            ),

            "revenue_data_available": False,

            "guidance_data_available": False,

            "earnings_estimate_revisions_used": False,

            "research_only": True,
        })

    return rows


# ============================================================
# BUILD COMPANY DATASET
# ============================================================

def build_company_dataset():
    """
    Fetch earnings data for the complete test universe.

    Companies that fail after all retries are preserved in
    a failure log and do not crash the entire pipeline.
    """

    print()
    print("=" * 70)
    print("BUILDING CORPORATE EARNINGS DATASET")
    print(
        f"Companies in test universe: "
        f"{len(COMPANIES)}"
    )
    print("=" * 70)
    print()

    all_rows = []

    failed_companies = []

    total = len(COMPANIES)

    for index, company in enumerate(
        COMPANIES,
        start=1
    ):

        ticker = company["ticker"]
        sector = company["sector"]

        print(
            f"[{index}/{total}] "
            f"{ticker} ({sector})"
        )
        print()

        rows = fetch_company_earnings(
            ticker,
            sector
        )

        if rows:

            all_rows.extend(
                rows
            )

        else:

            failed_companies.append(
                ticker
            )

            print(
                f"WARNING: {ticker} "
                f"produced no usable earnings "
                f"records."
            )

        print()

        # ----------------------------------------------------
        # Conservative delay between companies.
        #
        # We do NOT need to sleep after the last company.
        # ----------------------------------------------------

        if index < total:

            print(
                f"Waiting "
                f"{REQUEST_DELAY_SECONDS:.1f} "
                f"seconds..."
            )

            time.sleep(
                REQUEST_DELAY_SECONDS
            )

    df = pd.DataFrame(
        all_rows
    )

    print()
    print("=" * 70)
    print("DATASET BUILD COMPLETE")
    print("=" * 70)

    print(
        f"Total event records: "
        f"{len(df)}"
    )

    successful_tickers = (
        sorted(
            df["ticker"].unique().tolist()
        )
        if not df.empty
        else []
    )

    print(
        f"Successful companies: "
        f"{len(successful_tickers)}/"
        f"{total}"
    )

    if successful_tickers:

        print(
            "Successful tickers: "
            + ", ".join(
                successful_tickers
            )
        )

    if failed_companies:

        print(
            "Failed companies: "
            + ", ".join(
                failed_companies
            )
        )

    else:

        print(
            "Failed companies: NONE"
        )

    print()

    return df, failed_companies


# ============================================================
# PREPARE LATEST QUARTER
# ============================================================

def prepare_latest_quarter(
    df
):
    """
    Select the latest reported earnings event for each
    company.
    """

    if df.empty:
        return pd.DataFrame()

    working = df.copy()

    working["reported_date"] = pd.to_datetime(
        working["reported_date"],
        errors="coerce"
    )

    working = working.dropna(
        subset=["reported_date"]
    )

    latest = (
        working.sort_values(
            "reported_date"
        )
        .groupby(
            "ticker",
            as_index=False
        )
        .tail(1)
        .sort_values(
            "ticker"
        )
        .reset_index(drop=True)
    )

    latest["reported_date"] = (
        latest["reported_date"]
        .dt.strftime("%Y-%m-%d")
    )

    return latest


# ============================================================
# BREADTH CALCULATION
# ============================================================

def calculate_breadth(
    latest_df
):
    """
    Calculate descriptive earnings breadth.

    Breadth is based on the percentage of valid companies
    classified as BEAT/LARGE_BEAT versus MISS/LARGE_MISS.

    This is NOT a trading signal.
    """

    if latest_df.empty:

        return {
            "companies_total": 0,
            "companies_valid_eps": 0,
            "companies_unknown": 0,
            "eps_beats": 0,
            "eps_misses": 0,
            "eps_in_line": 0,
            "eps_beat_pct": np.nan,
            "eps_miss_pct": np.nan,
            "eps_in_line_pct": np.nan,
            "average_eps_surprise_pct": np.nan,
            "median_eps_surprise_pct": np.nan,
            "breadth_score": np.nan,
            "breadth_label": "UNKNOWN",
            "breadth_reason": (
                "No valid earnings data."
            ),
        }

    classes = (
        latest_df["eps_result_class"]
        .fillna("UNKNOWN")
        .astype(str)
        .str.upper()
    )

    beats = classes.isin(
        ["BEAT", "LARGE_BEAT"]
    )

    misses = classes.isin(
        ["MISS", "LARGE_MISS"]
    )

    in_line = classes.eq(
        "IN_LINE"
    )

    unknown = classes.eq(
        "UNKNOWN"
    )

    valid = ~unknown

    companies_total = len(
        latest_df
    )

    companies_valid_eps = int(
        valid.sum()
    )

    companies_unknown = int(
        unknown.sum()
    )

    eps_beats = int(
        beats.sum()
    )

    eps_misses = int(
        misses.sum()
    )

    eps_in_line = int(
        in_line.sum()
    )

    if companies_valid_eps > 0:

        eps_beat_pct = (
            eps_beats
            / companies_valid_eps
            * 100.0
        )

        eps_miss_pct = (
            eps_misses
            / companies_valid_eps
            * 100.0
        )

        eps_in_line_pct = (
            eps_in_line
            / companies_valid_eps
            * 100.0
        )

    else:

        eps_beat_pct = np.nan
        eps_miss_pct = np.nan
        eps_in_line_pct = np.nan

    surprise_series = pd.to_numeric(
        latest_df["eps_surprise_pct"],
        errors="coerce"
    ).dropna()

    if len(surprise_series) > 0:

        average_surprise = (
            surprise_series.mean()
        )

        median_surprise = (
            surprise_series.median()
        )

    else:

        average_surprise = np.nan
        median_surprise = np.nan

    # --------------------------------------------------------
    # Descriptive breadth score
    #
    # 50 = balanced
    #
    # Difference between beat and miss percentage
    # is scaled by 0.5.
    #
    # Example:
    # 80% beat / 20% miss
    # score = 50 + (80 - 20) / 2 = 80
    #
    # This is descriptive only.
    # --------------------------------------------------------

    if companies_valid_eps > 0:

        breadth_score = (
            50.0
            + (
                eps_beat_pct
                - eps_miss_pct
            )
            / 2.0
        )

        breadth_score = max(
            0.0,
            min(
                100.0,
                breadth_score
            )
        )

    else:

        breadth_score = np.nan

    if pd.isna(breadth_score):

        breadth_label = "UNKNOWN"

    elif breadth_score >= 70:

        breadth_label = (
            "POSITIVE_BREADTH"
        )

    elif breadth_score >= 55:

        breadth_label = (
            "MILDLY_POSITIVE"
        )

    elif breadth_score > 45:

        breadth_label = "BALANCED"

    elif breadth_score > 30:

        breadth_label = (
            "MILDLY_NEGATIVE"
        )

    else:

        breadth_label = (
            "NEGATIVE_BREADTH"
        )

    breadth_reason = (
        "Descriptive EPS beat/miss breadth; "
        "not a trading signal."
    )

    return {
        "companies_total": (
            companies_total
        ),

        "companies_valid_eps": (
            companies_valid_eps
        ),

        "companies_unknown": (
            companies_unknown
        ),

        "eps_beats": (
            eps_beats
        ),

        "eps_misses": (
            eps_misses
        ),

        "eps_in_line": (
            eps_in_line
        ),

        "eps_beat_pct": (
            eps_beat_pct
        ),

        "eps_miss_pct": (
            eps_miss_pct
        ),

        "eps_in_line_pct": (
            eps_in_line_pct
        ),

        "average_eps_surprise_pct": (
            average_surprise
        ),

        "median_eps_surprise_pct": (
            median_surprise
        ),

        "breadth_score": (
            breadth_score
        ),

        "breadth_label": (
            breadth_label
        ),

        "breadth_reason": (
            breadth_reason
        ),
    }


# ============================================================
# SECTOR BREADTH
# ============================================================

def calculate_sector_breadth(
    latest_df
):
    """
    Calculate descriptive earnings breadth by sector.
    """

    if latest_df.empty:
        return pd.DataFrame()

    rows = []

    for sector, group in latest_df.groupby(
        "sector",
        dropna=False
    ):

        breadth = calculate_breadth(
            group
        )

        rows.append({
            "sector": sector,

            "companies_total": breadth[
                "companies_total"
            ],

            "companies_valid_eps": breadth[
                "companies_valid_eps"
            ],

            "companies_unknown": breadth[
                "companies_unknown"
            ],

            "eps_beats": breadth[
                "eps_beats"
            ],

            "eps_misses": breadth[
                "eps_misses"
            ],

            "eps_in_line": breadth[
                "eps_in_line"
            ],

            "eps_beat_pct": breadth[
                "eps_beat_pct"
            ],

            "eps_miss_pct": breadth[
                "eps_miss_pct"
            ],

            "eps_in_line_pct": breadth[
                "eps_in_line_pct"
            ],

            "average_eps_surprise_pct": (
                breadth[
                    "average_eps_surprise_pct"
                ]
            ),

            "median_eps_surprise_pct": (
                breadth[
                    "median_eps_surprise_pct"
                ]
            ),

            "breadth_score": breadth[
                "breadth_score"
            ],

            "breadth_label": breadth[
                "breadth_label"
            ],

            "breadth_reason": breadth[
                "breadth_reason"
            ],
        })

    return (
        pd.DataFrame(rows)
        .sort_values("sector")
        .reset_index(drop=True)
    )


# ============================================================
# SAVE OUTPUTS
# ============================================================

def save_outputs(
    events_df,
    latest_df,
    breadth_summary,
    sector_breadth
):
    """
    Save all V2 CSV outputs.
    """

    print()
    print("=" * 70)
    print("SAVING V2 OUTPUT FILES")
    print("=" * 70)

    events_df.to_csv(
        EVENTS_OUTPUT,
        index=False
    )

    latest_df.to_csv(
        LATEST_COMPANY_OUTPUT,
        index=False
    )

    pd.DataFrame(
        [breadth_summary]
    ).to_csv(
        BREADTH_SUMMARY_OUTPUT,
        index=False
    )

    sector_breadth.to_csv(
        SECTOR_BREADTH_OUTPUT,
        index=False
    )

    print(
        f" - {EVENTS_OUTPUT}"
    )

    print(
        f" - {LATEST_COMPANY_OUTPUT}"
    )

    print(
        f" - {BREADTH_SUMMARY_OUTPUT}"
    )

    print(
        f" - {SECTOR_BREADTH_OUTPUT}"
    )


# ============================================================
# DISPLAY LATEST RESULTS
# ============================================================

def display_latest_results(
    latest_df
):
    """
    Print latest company results.
    """

    print()
    print("=" * 70)
    print("LATEST COMPANY RESULTS")
    print("=" * 70)

    if latest_df.empty:

        print(
            "No latest company results."
        )

        return

    columns = [
        "ticker",
        "sector",
        "reported_date",
        "eps_actual",
        "eps_consensus",
        "eps_surprise",
        "eps_surprise_pct",
        "eps_result_class",
        "point_in_time_safe",
        "historical_analog_eligible",
    ]

    available = [
        col for col in columns
        if col in latest_df.columns
    ]

    display_df = latest_df[
        available
    ].copy()

    print(
        display_df.to_string(
            index=False
        )
    )


# ============================================================
# DISPLAY SECTOR BREADTH
# ============================================================

def display_sector_breadth(
    sector_breadth
):
    """
    Print sector breadth.
    """

    print()
    print("=" * 70)
    print("SECTOR BREADTH")
    print("=" * 70)

    if sector_breadth.empty:

        print(
            "No sector breadth data."
        )

        return

    print(
        sector_breadth.to_string(
            index=False
        )
    )


# ============================================================
# MAIN
# ============================================================

def main():
    """
    Main execution pipeline.
    """

    print()
    print("=" * 70)
    print("CORPORATE EARNINGS INTELLIGENCE V2")
    print("=" * 70)
    print()
    print(
        "Research-only corporate earnings analysis."
    )
    print(
        "No trading signal."
    )
    print(
        "No Decision Engine integration."
    )
    print()

    # --------------------------------------------------------
    # Validate API key
    # --------------------------------------------------------

    validate_api_key()

    # --------------------------------------------------------
    # Build event dataset
    # --------------------------------------------------------

    events_df, failed_companies = (
        build_company_dataset()
    )

    # --------------------------------------------------------
    # Safety check
    # --------------------------------------------------------

    if events_df.empty:

        raise RuntimeError(
            "No earnings data was collected "
            "from Alpha Vantage."
        )

    # --------------------------------------------------------
    # Prepare latest quarter
    # --------------------------------------------------------

    latest_df = prepare_latest_quarter(
        events_df
    )

    # --------------------------------------------------------
    # Calculate overall breadth
    # --------------------------------------------------------

    breadth_summary = calculate_breadth(
        latest_df
    )

    # --------------------------------------------------------
    # Calculate sector breadth
    # --------------------------------------------------------

    sector_breadth = (
        calculate_sector_breadth(
            latest_df
        )
    )

    # --------------------------------------------------------
    # Display results
    # --------------------------------------------------------

    display_latest_results(
        latest_df
    )

    display_sector_breadth(
        sector_breadth
    )

    # --------------------------------------------------------
    # Save outputs
    # --------------------------------------------------------

    save_outputs(
        events_df,
        latest_df,
        breadth_summary,
        sector_breadth
    )

    # --------------------------------------------------------
    # Final status
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("FINAL V2 STATUS")
    print("=" * 70)

    successful_companies = (
        latest_df["ticker"].nunique()
        if not latest_df.empty
        else 0
    )

    total_companies = len(
        COMPANIES
    )

    print(
        f"Companies successfully loaded: "
        f"{successful_companies}/"
        f"{total_companies}"
    )

    if failed_companies:

        print(
            "Companies without usable data: "
            + ", ".join(
                failed_companies
            )
        )

        print()
        print(
            "WARNING: The dataset is incomplete "
            "for the current run."
        )

    else:

        print(
            "Companies without usable data: NONE"
        )

        print(
            "All test-universe companies "
            "loaded successfully."
        )

    print()
    print(
        f"Breadth score: "
        f"{breadth_summary['breadth_score']}"
    )

    print(
        f"Breadth label: "
        f"{breadth_summary['breadth_label']}"
    )

    print(
        f"Breadth reason: "
        f"{breadth_summary['breadth_reason']}"
    )

    print()
    print("=" * 70)
    print(
        "CORPORATE EARNINGS INTELLIGENCE V2 COMPLETED"
    )
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
