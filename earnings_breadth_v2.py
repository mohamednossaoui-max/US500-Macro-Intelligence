import os
import time
import json
import requests
import pandas as pd


# ============================================================
# US500 MACRO INTELLIGENCE
# CORPORATE EARNINGS INTELLIGENCE V2
# S&P 500 EARNINGS BREADTH
# ============================================================
#
# Conservative research-only implementation.
#
# IMPORTANT:
# - No trade execution
# - No Decision Engine integration
# - No Technical Engine modification
# - No historical market forecast
# - No look-ahead assumption
#
# V2 objective:
#   Build a cross-company earnings breadth dataset.
#
# Alpha Vantage:
#   EARNINGS is used for event-time EPS results.
#
# We intentionally do NOT treat EARNINGS_ESTIMATES
# revisions as historical Point-in-Time data.
#
# ============================================================


BASE_URL = "https://www.alphavantage.co/query"

API_KEY = os.getenv(
    "ALPHAVANTAGE_API_KEY",
    ""
).strip()

REQUEST_DELAY = float(
    os.getenv(
        "ALPHAVANTAGE_REQUEST_DELAY",
        "1.5"
    )
)

REQUEST_TIMEOUT = int(
    os.getenv(
        "ALPHAVANTAGE_TIMEOUT",
        "30"
    )
)


# ============================================================
# V2 TEST UNIVERSE
# ============================================================
#
# This is NOT the complete S&P 500.
#
# It is a validation universe covering multiple sectors.
#
# Once the pipeline is validated, we can expand the universe.
#
# ============================================================

UNIVERSE = [
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


# ============================================================
# HELPERS
# ============================================================

def to_float(value):
    if value is None:
        return None

    try:

        if isinstance(value, str):
            value = value.strip()

        if value == "":
            return None

        return float(value)

    except (TypeError, ValueError):

        return None


def calculate_surprise_pct(
    actual,
    estimate
):
    actual = to_float(actual)
    estimate = to_float(estimate)

    if actual is None:
        return None

    if estimate is None:
        return None

    if estimate == 0:
        return None

    return (
        (actual - estimate)
        / abs(estimate)
        * 100.0
    )


def classify_eps_result(
    surprise_pct
):

    if surprise_pct is None:
        return "UNKNOWN"

    if surprise_pct >= 10:
        return "LARGE_BEAT"

    if surprise_pct >= 3:
        return "BEAT"

    if surprise_pct > -3:
        return "IN_LINE"

    if surprise_pct > -10:
        return "MISS"

    return "LARGE_MISS"


# ============================================================
# API
# ============================================================

def request_api(
    function,
    ticker
):

    if not API_KEY:

        raise RuntimeError(
            "ALPHAVANTAGE_API_KEY is not available."
        )

    params = {
        "function": function,
        "symbol": ticker,
        "apikey": API_KEY,
    }

    response = requests.get(
        BASE_URL,
        params=params,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    data = response.json()

    if "Error Message" in data:

        raise RuntimeError(
            f"{ticker} {function}: "
            f"{data['Error Message']}"
        )

    if "Note" in data:

        raise RuntimeError(
            f"{ticker} {function}: "
            f"{data['Note']}"
        )

    if "Information" in data:

        raise RuntimeError(
            f"{ticker} {function}: "
            f"{data['Information']}"
        )

    return data


# ============================================================
# FETCH COMPANY EARNINGS
# ============================================================

def fetch_company_earnings(
    ticker,
    sector
):

    print(
        f"\nRequesting EARNINGS / {ticker}"
    )

    data = request_api(
        "EARNINGS",
        ticker
    )

    quarterly = data.get(
        "quarterlyEarnings",
        []
    )

    records = []

    for item in quarterly:

        actual = to_float(
            item.get("reportedEPS")
        )

        consensus = to_float(
            item.get("estimatedEPS")
        )

        surprise = to_float(
            item.get("surprise")
        )

        surprise_pct = to_float(
            item.get(
                "surprisePercentage"
            )
        )

        calculated_pct = (
            calculate_surprise_pct(
                actual,
                consensus
            )
        )

        # Prefer the provider's event-time
        # surprise percentage when available.
        effective_surprise_pct = (
            surprise_pct
            if surprise_pct is not None
            else calculated_pct
        )

        result_class = (
            classify_eps_result(
                effective_surprise_pct
            )
        )

        if (
            actual is not None
            and consensus is not None
        ):

            earnings_beat = (
                actual > consensus
            )

        else:

            earnings_beat = None

        record = {

            # ------------------------------------------------
            # Identity
            # ------------------------------------------------

            "ticker":
                ticker,

            "sector":
                sector,

            "event_type":
                "CORPORATE_EARNINGS",

            "fiscal_date_ending":
                item.get(
                    "fiscalDateEnding"
                ),

            "reported_date":
                item.get(
                    "reportedDate"
                ),

            # ------------------------------------------------
            # EPS
            # ------------------------------------------------

            "eps_actual":
                actual,

            "eps_consensus":
                consensus,

            "eps_surprise":
                surprise,

            "eps_surprise_pct":
                effective_surprise_pct,

            "eps_surprise_pct_calculated":
                calculated_pct,

            # ------------------------------------------------
            # Classification
            # ------------------------------------------------

            "earnings_beat":
                earnings_beat,

            "eps_result_class":
                result_class,

            # ------------------------------------------------
            # Revenue
            #
            # Not populated here because EARNINGS does not
            # provide event-time revenue actual/consensus.
            # ------------------------------------------------

            "revenue_actual":
                None,

            "revenue_consensus":
                None,

            "revenue_surprise_pct":
                None,

            "revenue_result_class":
                "UNKNOWN",

            # ------------------------------------------------
            # Historical safety
            # ------------------------------------------------

            "point_in_time":
                True,

            "point_in_time_safe":
                True,

            "historical_analog_eligible":
                True,

            "source":
                "Alpha Vantage EARNINGS",

            "source_type":
                "primary_event_data",

            "data_quality":
                "PRIMARY_EVENT_DATA",

        }

        records.append(
            record
        )

    return records


# ============================================================
# BUILD COMPANY DATASET
# ============================================================

def build_company_dataset():

    all_records = []

    total_companies = len(
        UNIVERSE
    )

    print(
        "\n" + "=" * 70
    )

    print(
        "BUILDING CORPORATE EARNINGS DATASET"
    )

    print(
        f"Companies in test universe: "
        f"{total_companies}"
    )

    print(
        "=" * 70
    )

    for index, company in enumerate(
        UNIVERSE,
        start=1
    ):

        ticker = company[
            "ticker"
        ]

        sector = company[
            "sector"
        ]

        print(
            f"\n[{index}/{total_companies}] "
            f"{ticker} "
            f"({sector})"
        )

        try:

            records = (
                fetch_company_earnings(
                    ticker,
                    sector
                )
            )

            all_records.extend(
                records
            )

            print(
                f"Records received: "
                f"{len(records)}"
            )

        except Exception as exc:

            print(
                f"ERROR for {ticker}: "
                f"{exc}"
            )

        # Avoid bursting the free API.
        if index < total_companies:

            print(
                f"Waiting "
                f"{REQUEST_DELAY} seconds..."
            )

            time.sleep(
                REQUEST_DELAY
            )

    return pd.DataFrame(
        all_records
    )


# ============================================================
# LATEST QUARTER
# ============================================================

def prepare_latest_quarter(
    df
):

    if df.empty:

        return df

    df = df.copy()

    df[
        "reported_date"
    ] = pd.to_datetime(
        df[
            "reported_date"
        ],
        errors="coerce"
    )

    df[
        "fiscal_date_ending"
    ] = pd.to_datetime(
        df[
            "fiscal_date_ending"
        ],
        errors="coerce"
    )

    # For each company, select its latest
    # available reported earnings event.

    latest = (
        df.sort_values(
            [
                "ticker",
                "reported_date"
            ],
            ascending=[
                True,
                False
            ]
        )
        .groupby(
            "ticker",
            as_index=False
        )
        .first()
    )

    return latest


# ============================================================
# BREADTH CALCULATION
# ============================================================

def calculate_breadth(
    latest_df
):

    if latest_df.empty:

        return {}

    total = len(
        latest_df
    )

    beat_count = int(
        (
            latest_df[
                "eps_result_class"
            ].isin(
                [
                    "BEAT",
                    "LARGE_BEAT"
                ]
            )
        ).sum()
    )

    miss_count = int(
        (
            latest_df[
                "eps_result_class"
            ].isin(
                [
                    "MISS",
                    "LARGE_MISS"
                ]
            )
        ).sum()
    )

    in_line_count = int(
        (
            latest_df[
                "eps_result_class"
            ] == "IN_LINE"
        ).sum()
    )

    unknown_count = int(
        (
            latest_df[
                "eps_result_class"
            ] == "UNKNOWN"
        ).sum()
    )

    valid_count = (
        beat_count
        + miss_count
        + in_line_count
    )

    if valid_count > 0:

        beat_pct = (
            beat_count
            / valid_count
            * 100.0
        )

        miss_pct = (
            miss_count
            / valid_count
            * 100.0
        )

        in_line_pct = (
            in_line_count
            / valid_count
            * 100.0
        )

    else:

        beat_pct = None
        miss_pct = None
        in_line_pct = None

    valid_surprises = (
        latest_df[
            "eps_surprise_pct"
        ]
        .dropna()
    )

    if len(
        valid_surprises
    ) > 0:

        average_surprise = (
            valid_surprises.mean()
        )

        median_surprise = (
            valid_surprises.median()
        )

    else:

        average_surprise = None
        median_surprise = None

    return {

        "companies_total":
            total,

        "companies_valid_eps":
            valid_count,

        "companies_unknown":
            unknown_count,

        "eps_beats":
            beat_count,

        "eps_misses":
            miss_count,

        "eps_in_line":
            in_line_count,

        "eps_beat_pct":
            beat_pct,

        "eps_miss_pct":
            miss_pct,

        "eps_in_line_pct":
            in_line_pct,

        "average_eps_surprise_pct":
            average_surprise,

        "median_eps_surprise_pct":
            median_surprise,

    }


# ============================================================
# SECTOR BREADTH
# ============================================================

def calculate_sector_breadth(
    latest_df
):

    if latest_df.empty:

        return pd.DataFrame()

    rows = []

    for sector, group in (
        latest_df.groupby(
            "sector"
        )
    ):

        result = calculate_breadth(
            group
        )

        result[
            "sector"
        ] = sector

        rows.append(
            result
        )

    sector_df = pd.DataFrame(
        rows
    )

    if not sector_df.empty:

        sector_df = sector_df[
            [
                "sector",
                "companies_total",
                "companies_valid_eps",
                "companies_unknown",
                "eps_beats",
                "eps_misses",
                "eps_in_line",
                "eps_beat_pct",
                "eps_miss_pct",
                "eps_in_line_pct",
                "average_eps_surprise_pct",
                "median_eps_surprise_pct",
            ]
        ]

        sector_df = (
            sector_df.sort_values(
                "eps_beat_pct",
                ascending=False
            )
        )

    return sector_df


# ============================================================
# BREADTH THERMOMETER INPUT
# ============================================================

def calculate_breadth_context(
    breadth
):

    if not breadth:

        return {
            "breadth_status":
                "UNAVAILABLE",
            "breadth_score":
                None,
            "breadth_reason":
                "No valid earnings breadth data."
        }

    valid = breadth[
        "companies_valid_eps"
    ]

    if valid < 3:

        return {
            "breadth_status":
                "INSUFFICIENT_DATA",
            "breadth_score":
                None,
            "breadth_reason":
                "Too few valid companies."
        }

    beat_pct = breadth[
        "eps_beat_pct"
    ]

    miss_pct = breadth[
        "eps_miss_pct"
    ]

    if (
        beat_pct is None
        or miss_pct is None
    ):

        return {
            "breadth_status":
                "UNAVAILABLE",
            "breadth_score":
                None,
            "breadth_reason":
                "Beat/miss percentages unavailable."
        }

    # --------------------------------------------------------
    # This is NOT a trading score.
    #
    # It is a descriptive breadth context score:
    #
    # 50 = balanced
    # >50 = more beats than misses
    # <50 = more misses than beats
    #
    # It is deliberately NOT connected to Decision Engine.
    # --------------------------------------------------------

    score = (
        50.0
        + (
            beat_pct
            - miss_pct
        ) / 2.0
    )

    score = max(
        0.0,
        min(
            100.0,
            score
        )
    )

    if score >= 70:

        status = "POSITIVE_BREADTH"

    elif score >= 55:

        status = "MILDLY_POSITIVE"

    elif score > 45:

        status = "BALANCED"

    elif score > 30:

        status = "MILDLY_NEGATIVE"

    else:

        status = "NEGATIVE_BREADTH"

    return {

        "breadth_status":
            status,

        "breadth_score":
            score,

        "breadth_reason":
            "Descriptive EPS beat/miss breadth; not a trading signal."

    }


# ============================================================
# EXPORT
# ============================================================

def export_v2():

    df = build_company_dataset()

    if df.empty:

        print(
            "\nNo earnings data collected."
        )

        return

    # --------------------------------------------------------
    # Full event dataset
    # --------------------------------------------------------

    df.to_csv(
        "earnings_breadth_events_v2.csv",
        index=False
    )

    # --------------------------------------------------------
    # Latest event per company
    # --------------------------------------------------------

    latest_df = (
        prepare_latest_quarter(
            df
        )
    )

    latest_df.to_csv(
        "earnings_latest_company_v2.csv",
        index=False
    )

    # --------------------------------------------------------
    # Overall breadth
    # --------------------------------------------------------

    breadth = calculate_breadth(
        latest_df
    )

    breadth_context = (
        calculate_breadth_context(
            breadth
        )
    )

    breadth_output = {
        **breadth,
        **breadth_context,
    }

    breadth_df = pd.DataFrame(
        [breadth_output]
    )

    breadth_df.to_csv(
        "earnings_breadth_summary_v2.csv",
        index=False
    )

    # --------------------------------------------------------
    # Sector breadth
    # --------------------------------------------------------

    sector_df = (
        calculate_sector_breadth(
            latest_df
        )
    )

    sector_df.to_csv(
        "earnings_sector_breadth_v2.csv",
        index=False
    )

    # --------------------------------------------------------
    # Display
    # --------------------------------------------------------

    print(
        "\n" + "=" * 70
    )

    print(
        "EARNINGS BREADTH V2 SUMMARY"
    )

    print(
        "=" * 70
    )

    for key, value in (
        breadth_output.items()
    ):

        if isinstance(
            value,
            float
        ):

            print(
                f"{key}: "
                f"{value:.4f}"
            )

        else:

            print(
                f"{key}: "
                f"{value}"
            )

    print(
        "\n" + "=" * 70
    )

    print(
        "LATEST COMPANY RESULTS"
    )

    print(
        "=" * 70
    )

    display_columns = [

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

    available_columns = [
        col
        for col in display_columns
        if col in latest_df.columns
    ]

    print(
        latest_df[
            available_columns
        ].to_string(
            index=False
        )
    )

    print(
        "\n" + "=" * 70
    )

    print(
        "SECTOR BREADTH"
    )

    print(
        "=" * 70
    )

    if not sector_df.empty:

        print(
            sector_df.to_string(
                index=False
            )
        )

    print(
        "\nCreated files:"
    )

    print(
        " - earnings_breadth_events_v2.csv"
    )

    print(
        " - earnings_latest_company_v2.csv"
    )

    print(
        " - earnings_breadth_summary_v2.csv"
    )

    print(
        " - earnings_sector_breadth_v2.csv"
    )

    print(
        "\nCORPORATE EARNINGS INTELLIGENCE V2 COMPLETED"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    export_v2()
