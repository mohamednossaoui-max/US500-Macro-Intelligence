import os
import time
import json
import requests
import pandas as pd


# ============================================================
# US500 MACRO INTELLIGENCE
# CORPORATE EARNINGS INTELLIGENCE V1
# ============================================================
#
# Conservative implementation.
#
# IMPORTANT:
# - No trade execution
# - No Decision Engine integration
# - No modification of Technical Engine
# - No look-ahead assumptions
#
# Alpha Vantage is used as the primary earnings source.
#
# EARNINGS:
#   Safe for event-time:
#       reported EPS
#       estimated EPS used by earnings endpoint
#       EPS surprise
#       reported date
#
# EARNINGS_ESTIMATES:
#   Useful for current/future intelligence and revision context.
#   Historical point-in-time usage is NOT assumed safe in V1.
#
# ============================================================


BASE_URL = "https://www.alphavantage.co/query"

API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()

REQUEST_DELAY = float(
    os.getenv("ALPHAVANTAGE_REQUEST_DELAY", "1.5")
)

REQUEST_TIMEOUT = int(
    os.getenv("ALPHAVANTAGE_TIMEOUT", "30")
)


# ============================================================
# HELPERS
# ============================================================

def to_float(value):
    """
    Safely convert a value to float.
    """
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


def safe_divide(a, b):
    """
    Safe division.
    """
    if a is None or b is None:
        return None

    if b == 0:
        return None

    try:
        return a / b
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def calculate_surprise_pct(actual, estimate):
    """
    Calculate EPS surprise percentage.

    Formula:
        (Actual - Estimate) / abs(Estimate) * 100

    Using abs(Estimate) avoids a misleading sign when
    the consensus estimate is negative.
    """
    actual = to_float(actual)
    estimate = to_float(estimate)

    if actual is None or estimate is None:
        return None

    if estimate == 0:
        return None

    return (
        (actual - estimate)
        / abs(estimate)
        * 100.0
    )


def calculate_revision_pct(current, previous):
    """
    Calculate estimate revision percentage.

    IMPORTANT:
    This is NOT automatically considered Point-in-Time safe.
    """
    current = to_float(current)
    previous = to_float(previous)

    if current is None or previous is None:
        return None

    if previous == 0:
        return None

    return (
        (current - previous)
        / abs(previous)
        * 100.0
    )


# ============================================================
# API
# ============================================================

def request_api(function, ticker):
    """
    Request Alpha Vantage data with conservative error handling.
    """

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
# RAW DATA
# ============================================================

def save_json(filename, data):
    """
    Save raw API response.
    """

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# EARNINGS
# ============================================================

def fetch_earnings(ticker):
    """
    Fetch reported earnings.

    This is the primary Point-in-Time-safe source in V1.

    We use:
        reportedEPS
        estimatedEPS
        surprise
        surprisePercentage
        reportedDate
        fiscalDateEnding
    """

    ticker = str(ticker).upper().strip()

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

        fiscal_date = item.get(
            "fiscalDateEnding"
        )

        reported_date = item.get(
            "reportedDate"
        )

        reported_eps = to_float(
            item.get("reportedEPS")
        )

        estimated_eps = to_float(
            item.get("estimatedEPS")
        )

        surprise = to_float(
            item.get("surprise")
        )

        surprise_pct = to_float(
            item.get("surprisePercentage")
        )

        calculated_surprise_pct = (
            calculate_surprise_pct(
                reported_eps,
                estimated_eps
            )
        )

        record = {

            # ------------------------------------------------
            # Identity
            # ------------------------------------------------

            "ticker": ticker,

            "company": None,

            "sector": None,

            "industry": None,

            "event_type": "CORPORATE_EARNINGS",

            "fiscal_date_ending": fiscal_date,

            "reported_date": reported_date,

            # ------------------------------------------------
            # EPS
            # ------------------------------------------------

            "eps_actual": reported_eps,

            "eps_consensus": estimated_eps,

            "eps_surprise": surprise,

            "eps_surprise_pct": surprise_pct,

            "eps_surprise_pct_calculated":
                calculated_surprise_pct,

            # ------------------------------------------------
            # Revenue
            #
            # Not populated from EARNINGS.
            # ------------------------------------------------

            "revenue_actual": None,

            "revenue_consensus": None,

            "revenue_surprise": None,

            "revenue_surprise_pct": None,

            # ------------------------------------------------
            # Growth / margins
            #
            # Not assumed available in V1.
            # ------------------------------------------------

            "eps_growth_yoy": None,

            "revenue_growth_yoy": None,

            "gross_margin": None,

            "operating_margin": None,

            "net_margin": None,

            "margin_change_yoy": None,

            # ------------------------------------------------
            # Guidance
            # ------------------------------------------------

            "guidance_direction": None,

            "guidance_eps": None,

            "guidance_revenue": None,

            # ------------------------------------------------
            # Revisions
            #
            # These are populated later from
            # EARNINGS_ESTIMATES.
            # ------------------------------------------------

            "forward_eps_revision_7d_pct": None,

            "forward_eps_revision_30d_pct": None,

            "forward_eps_revision_60d_pct": None,

            "forward_eps_revision_90d_pct": None,

            "eps_revision_up_7d": None,

            "eps_revision_down_7d": None,

            "eps_revision_up_30d": None,

            "eps_revision_down_30d": None,

            # ------------------------------------------------
            # Event classification
            # ------------------------------------------------

            "earnings_beat": (
                True
                if (
                    reported_eps is not None
                    and estimated_eps is not None
                    and reported_eps > estimated_eps
                )
                else (
                    False
                    if (
                        reported_eps is not None
                        and estimated_eps is not None
                    )
                    else None
                )
            ),

            # Revenue beat cannot be determined.
            "revenue_beat": None,

            # ------------------------------------------------
            # Market reaction
            #
            # Not populated in V1.
            # Historical market reaction belongs to the
            # future Historical Analog Engine.
            # ------------------------------------------------

            "sp500_reaction_1d": None,

            "sp500_reaction_3d": None,

            "sp500_reaction_5d": None,

            "sp500_reaction_20d": None,

            # ------------------------------------------------
            # Point-in-Time protection
            # ------------------------------------------------

            "point_in_time": True,

            "point_in_time_safe": True,

            "point_in_time_reason":
                "Reported EPS and consensus EPS are tied to the earnings event.",

            "data_as_of": reported_date,

            "source": "Alpha Vantage EARNINGS",

            "source_type": "primary",

            "historical_analog_eligible": True,

            # ------------------------------------------------
            # Data quality
            # ------------------------------------------------

            "data_quality": "PRIMARY_EVENT_DATA",

        }

        records.append(record)

    return records


# ============================================================
# EARNINGS ESTIMATES
# ============================================================

def fetch_estimates(ticker):
    """
    Fetch Alpha Vantage earnings estimates.

    IMPORTANT:
    The revision snapshots returned by this endpoint are NOT
    automatically treated as Point-in-Time historical data.

    Therefore:
        point_in_time_safe = False

    in the estimate records.

    These values may be used for CURRENT earnings intelligence,
    but V1 does not allow them to contaminate historical
    analog calculations.
    """

    ticker = str(ticker).upper().strip()

    data = request_api(
        "EARNINGS_ESTIMATES",
        ticker
    )

    estimates = data.get(
        "estimates",
        []
    )

    records = []

    for item in estimates:

        horizon = str(
            item.get("horizon", "")
        ).strip().lower()

        if horizon != "fiscal quarter":
            continue

        fiscal_date = item.get("date")

        eps_average = to_float(
            item.get(
                "eps_estimate_average"
            )
        )

        eps_7d = to_float(
            item.get(
                "eps_estimate_average_7_days_ago"
            )
        )

        eps_30d = to_float(
            item.get(
                "eps_estimate_average_30_days_ago"
            )
        )

        eps_60d = to_float(
            item.get(
                "eps_estimate_average_60_days_ago"
            )
        )

        eps_90d = to_float(
            item.get(
                "eps_estimate_average_90_days_ago"
            )
        )

        record = {

            "ticker": ticker,

            "fiscal_date_ending":
                fiscal_date,

            "horizon":
                item.get("horizon"),

            # ------------------------------------------------
            # EPS estimates
            # ------------------------------------------------

            "eps_estimate":
                eps_average,

            "eps_estimate_high":
                to_float(
                    item.get(
                        "eps_estimate_high"
                    )
                ),

            "eps_estimate_low":
                to_float(
                    item.get(
                        "eps_estimate_low"
                    )
                ),

            "eps_analyst_count":
                to_float(
                    item.get(
                        "eps_estimate_analyst_count"
                    )
                ),

            # ------------------------------------------------
            # Revenue estimates
            # ------------------------------------------------

            "revenue_estimate":
                to_float(
                    item.get(
                        "revenue_estimate_average"
                    )
                ),

            "revenue_estimate_high":
                to_float(
                    item.get(
                        "revenue_estimate_high"
                    )
                ),

            "revenue_estimate_low":
                to_float(
                    item.get(
                        "revenue_estimate_low"
                    )
                ),

            "revenue_analyst_count":
                to_float(
                    item.get(
                        "revenue_estimate_analyst_count"
                    )
                ),

            # ------------------------------------------------
            # Historical snapshots
            # ------------------------------------------------

            "eps_estimate_7d_ago":
                eps_7d,

            "eps_estimate_30d_ago":
                eps_30d,

            "eps_estimate_60d_ago":
                eps_60d,

            "eps_estimate_90d_ago":
                eps_90d,

            # ------------------------------------------------
            # Revision counts
            # ------------------------------------------------

            "eps_revision_up_7d":
                to_float(
                    item.get(
                        "eps_estimate_revision_up_trailing_7_days"
                    )
                ),

            "eps_revision_down_7d":
                to_float(
                    item.get(
                        "eps_estimate_revision_down_trailing_7_days"
                    )
                ),

            "eps_revision_up_30d":
                to_float(
                    item.get(
                        "eps_estimate_revision_up_trailing_30_days"
                    )
                ),

            "eps_revision_down_30d":
                to_float(
                    item.get(
                        "eps_estimate_revision_down_trailing_30_days"
                    )
                ),

            # ------------------------------------------------
            # Calculated revision percentages
            # ------------------------------------------------

            "eps_revision_7d_pct":
                calculate_revision_pct(
                    eps_average,
                    eps_7d
                ),

            "eps_revision_30d_pct":
                calculate_revision_pct(
                    eps_average,
                    eps_30d
                ),

            "eps_revision_60d_pct":
                calculate_revision_pct(
                    eps_average,
                    eps_60d
                ),

            "eps_revision_90d_pct":
                calculate_revision_pct(
                    eps_average,
                    eps_90d
                ),

            # ------------------------------------------------
            # Point-in-Time protection
            # ------------------------------------------------

            "point_in_time": False,

            "point_in_time_safe": False,

            "point_in_time_reason":
                "Alpha Vantage estimate snapshots are not treated as historical Point-in-Time observations in V1.",

            "historical_analog_eligible":
                False,

            "source":
                "Alpha Vantage EARNINGS_ESTIMATES",

            "source_type":
                "secondary_estimate_context",

            "data_quality":
                "CURRENT_ESTIMATE_CONTEXT",

        }

        records.append(record)

    return records


# ============================================================
# MERGE
# ============================================================

def merge_earnings_data(
    earnings_records,
    estimate_records
):
    """
    Merge event-time earnings with estimate context.

    IMPORTANT:
    Estimate context remains marked as non-PIT-safe.

    The resulting event remains historically eligible only
    when its core event data comes from EARNINGS.
    """

    earnings_df = pd.DataFrame(
        earnings_records
    )

    estimates_df = pd.DataFrame(
        estimate_records
    )

    if earnings_df.empty:
        return pd.DataFrame()

    if estimates_df.empty:
        return earnings_df

    earnings_df[
        "fiscal_date_ending"
    ] = pd.to_datetime(
        earnings_df[
            "fiscal_date_ending"
        ],
        errors="coerce"
    )

    estimates_df[
        "fiscal_date_ending"
    ] = pd.to_datetime(
        estimates_df[
            "fiscal_date_ending"
        ],
        errors="coerce"
    )

    merged = pd.merge(
        earnings_df,
        estimates_df,
        on=[
            "ticker",
            "fiscal_date_ending"
        ],
        how="left",
        suffixes=(
            "",
            "_estimate_context"
        )
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # The estimate context does NOT make the event
    # non-PIT-safe because the core event data remains safe.
    #
    # However, these revision fields must NOT be used in
    # historical analog calculations until independently
    # validated.
    # --------------------------------------------------------

    merged[
        "revision_context_historical_safe"
    ] = False

    merged[
        "historical_analog_revision_safe"
    ] = False

    merged = merged.sort_values(
        "fiscal_date_ending",
        ascending=False
    )

    return merged


# ============================================================
# PUBLIC FUNCTION
# ============================================================

def build_earnings_intelligence(
    ticker,
    include_estimates=True
):
    """
    Main public function.

    Returns a DataFrame containing Corporate Earnings
    Intelligence for one ticker.

    Example:

        df = build_earnings_intelligence("MSFT")

    """

    ticker = str(
        ticker
    ).upper().strip()

    earnings_records = fetch_earnings(
        ticker
    )

    if not include_estimates:

        return pd.DataFrame(
            earnings_records
        )

    # Respect Alpha Vantage free-tier rate limits.
    time.sleep(
        REQUEST_DELAY
    )

    estimate_records = fetch_estimates(
        ticker
    )

    return merge_earnings_data(
        earnings_records,
        estimate_records
    )


# ============================================================
# EVENT FINGERPRINT
# ============================================================

def build_event_fingerprint(row):
    """
    Convert one earnings event into a conservative
    Corporate Earnings Event Fingerprint.

    V1 only uses information that is explicitly available.

    Missing information remains None.

    This function does NOT produce a market forecast.
    """

    eps_surprise_pct = row.get(
        "eps_surprise_pct"
    )

    if eps_surprise_pct is None:
        eps_surprise_pct = row.get(
            "eps_surprise_pct_calculated"
        )

    # --------------------------------------------------------
    # EPS surprise classification
    # --------------------------------------------------------

    if eps_surprise_pct is None:

        eps_surprise_bucket = (
            "UNKNOWN"
        )

    elif eps_surprise_pct >= 10:

        eps_surprise_bucket = (
            "LARGE_POSITIVE"
        )

    elif eps_surprise_pct >= 3:

        eps_surprise_bucket = (
            "POSITIVE"
        )

    elif eps_surprise_pct > -3:

        eps_surprise_bucket = (
            "NEUTRAL"
        )

    elif eps_surprise_pct > -10:

        eps_surprise_bucket = (
            "NEGATIVE"
        )

    else:

        eps_surprise_bucket = (
            "LARGE_NEGATIVE"
        )

    # --------------------------------------------------------
    # Earnings beat
    # --------------------------------------------------------

    earnings_beat = row.get(
        "earnings_beat"
    )

    # --------------------------------------------------------
    # Revision context
    #
    # Explicitly marked as NOT historical-safe.
    # --------------------------------------------------------

    revision_7d = row.get(
        "eps_revision_7d_pct"
    )

    revision_30d = row.get(
        "eps_revision_30d_pct"
    )

    fingerprint = {

        "event_type":
            "CORPORATE_EARNINGS",

        "ticker":
            row.get("ticker"),

        "fiscal_date_ending":
            row.get("fiscal_date_ending"),

        "reported_date":
            row.get("reported_date"),

        # ----------------------------------------------------
        # EPS
        # ----------------------------------------------------

        "eps_actual":
            row.get("eps_actual"),

        "eps_consensus":
            row.get("eps_consensus"),

        "eps_surprise":
            row.get("eps_surprise"),

        "eps_surprise_pct":
            eps_surprise_pct,

        "eps_surprise_bucket":
            eps_surprise_bucket,

        "earnings_beat":
            earnings_beat,

        # ----------------------------------------------------
        # Revenue
        # ----------------------------------------------------

        "revenue_actual":
            row.get("revenue_actual"),

        "revenue_consensus":
            row.get("revenue_consensus"),

        "revenue_surprise_pct":
            row.get("revenue_surprise_pct"),

        # ----------------------------------------------------
        # Growth / margins
        # ----------------------------------------------------

        "eps_growth_yoy":
            row.get("eps_growth_yoy"),

        "revenue_growth_yoy":
            row.get("revenue_growth_yoy"),

        "margin_change_yoy":
            row.get("margin_change_yoy"),

        # ----------------------------------------------------
        # Guidance
        # ----------------------------------------------------

        "guidance_direction":
            row.get("guidance_direction"),

        # ----------------------------------------------------
        # Revision context
        #
        # IMPORTANT:
        # Not historical analog eligible in V1.
        # ----------------------------------------------------

        "eps_revision_7d_pct":
            revision_7d,

        "eps_revision_30d_pct":
            revision_30d,

        "revision_context_historical_safe":
            False,

        # ----------------------------------------------------
        # Point in time
        # ----------------------------------------------------

        "point_in_time":
            True,

        "historical_analog_eligible":
            True,

        "historical_analog_revision_safe":
            False,

        "data_as_of":
            row.get("data_as_of"),

        "source":
            row.get("source"),

        "data_quality":
            row.get("data_quality"),

    }

    return fingerprint


# ============================================================
# BUILD FINGERPRINTS
# ============================================================

def build_earnings_fingerprints(
    earnings_df
):
    """
    Build one fingerprint per earnings event.
    """

    if earnings_df is None:
        return []

    if earnings_df.empty:
        return []

    fingerprints = []

    for _, row in earnings_df.iterrows():

        fingerprints.append(
            build_event_fingerprint(
                row
            )
        )

    return fingerprints


# ============================================================
# EXPORT
# ============================================================

def export_earnings_intelligence(
    ticker,
    output_csv=None
):
    """
    Build and export earnings intelligence.
    """

    ticker = str(
        ticker
    ).upper().strip()

    df = build_earnings_intelligence(
        ticker
    )

    if output_csv is None:

        output_csv = (
            f"{ticker.lower()}_earnings_intelligence_v1.csv"
        )

    df.to_csv(
        output_csv,
        index=False
    )

    return df


# ============================================================
# SELF TEST
# ============================================================

def run_self_test():
    """
    Simple source/integrity test.

    This is intentionally conservative.
    """

    print(
        "\n" + "=" * 70
    )

    print(
        "US500 MACRO INTELLIGENCE"
    )

    print(
        "CORPORATE EARNINGS INTELLIGENCE V1"
    )

    print(
        "=" * 70
    )

    ticker = "MSFT"

    print(
        f"\nTicker: {ticker}"
    )

    df = build_earnings_intelligence(
        ticker
    )

    if df.empty:

        print(
            "\nNo earnings records returned."
        )

        return

    print(
        "\nRecords:",
        len(df)
    )

    print(
        "Point-in-Time-safe:",
        int(
            df[
                "point_in_time_safe"
            ].sum()
        )
    )

    print(
        "Historical Analog eligible:",
        int(
            df[
                "historical_analog_eligible"
            ].sum()
        )
    )

    print(
        "\nLatest earnings events:"
    )

    display_columns = [

        "ticker",

        "fiscal_date_ending",

        "reported_date",

        "eps_actual",

        "eps_consensus",

        "eps_surprise",

        "eps_surprise_pct",

        "earnings_beat",

        "revenue_consensus",

        "eps_revision_7d_pct",

        "eps_revision_30d_pct",

        "point_in_time_safe",

        "historical_analog_eligible",

    ]

    available_columns = [
        col
        for col in display_columns
        if col in df.columns
    ]

    print(
        df[
            available_columns
        ].head(10).to_string(
            index=False
        )
    )

    output_file = (
        "msft_earnings_intelligence_v1.csv"
    )

    df.to_csv(
        output_file,
        index=False
    )

    print(
        f"\nCreated: {output_file}"
    )

    print(
        "\nV1 SELF TEST COMPLETED"
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    run_self_test()
