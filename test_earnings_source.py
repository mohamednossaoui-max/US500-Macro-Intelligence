import os
import time
import json
import requests
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "ALPHAVANTAGE_API_KEY is not available."
    )

BASE_URL = "https://www.alphavantage.co/query"

# We continue with one ticker only
# to minimize Alpha Vantage API usage.
TICKER = "MSFT"

# Alpha Vantage free request pacing
REQUEST_DELAY = 1.5


# ============================================================
# API REQUEST
# ============================================================

def request_api(function, ticker):

    print(
        f"\nRequesting: {function} / {ticker}"
    )

    params = {
        "function": function,
        "symbol": ticker,
        "apikey": API_KEY,
    }

    response = requests.get(
        BASE_URL,
        params=params,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    print(
        "Response keys:",
        list(data.keys())
    )

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
# SAVE RAW JSON
# ============================================================

def save_raw_json(filename, data):

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False
        )

    print(
        f"Created raw response: {filename}"
    )


# ============================================================
# LOAD / CONVERT NUMERIC VALUE
# ============================================================

def to_float(value):

    if value is None:
        return None

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


# ============================================================
# EARNINGS
# ============================================================

def get_earnings(ticker):

    print("\n" + "=" * 70)
    print(f"{ticker} — EARNINGS")
    print("=" * 70)

    data = request_api(
        "EARNINGS",
        ticker
    )

    save_raw_json(
        "msft_earnings_raw.json",
        data
    )

    quarterly = data.get(
        "quarterlyEarnings",
        []
    )

    print(
        f"\nQuarterly records returned: "
        f"{len(quarterly)}"
    )

    rows = []

    for item in quarterly:

        fiscal_date = item.get(
            "fiscalDateEnding"
        )

        rows.append({

            "ticker":
                ticker,

            "fiscalDateEnding":
                fiscal_date,

            "reportedDate":
                item.get(
                    "reportedDate"
                ),

            "reportedEPS":
                to_float(
                    item.get(
                        "reportedEPS"
                    )
                ),

            "estimatedEPS":
                to_float(
                    item.get(
                        "estimatedEPS"
                    )
                ),

            "surprise":
                to_float(
                    item.get(
                        "surprise"
                    )
                ),

            "surprisePercentage":
                to_float(
                    item.get(
                        "surprisePercentage"
                    )
                ),
        })

    return rows


# ============================================================
# EARNINGS ESTIMATES
# ============================================================

def get_estimates(ticker):

    print("\n" + "=" * 70)
    print(
        f"{ticker} — EARNINGS ESTIMATES"
    )
    print("=" * 70)

    print(
        f"\nWaiting {REQUEST_DELAY} seconds..."
    )

    time.sleep(
        REQUEST_DELAY
    )

    data = request_api(
        "EARNINGS_ESTIMATES",
        ticker
    )

    save_raw_json(
        "msft_earnings_estimates_raw.json",
        data
    )

    estimates = data.get(
        "estimates",
        []
    )

    print(
        f"\nTotal estimate records returned: "
        f"{len(estimates)}"
    )

    rows = []

    for item in estimates:

        horizon = str(
            item.get(
                "horizon",
                ""
            )
        ).lower()

        # ----------------------------------------------------
        # We only want fiscal-quarter estimates.
        # Fiscal-year estimates are kept out of this V1 test.
        # ----------------------------------------------------

        if horizon != "fiscal quarter":
            continue

        rows.append({

            "ticker":
                ticker,

            "fiscalDateEnding":
                item.get(
                    "date"
                ),

            "horizon":
                item.get(
                    "horizon"
                ),

            "epsEstimate":
                to_float(
                    item.get(
                        "eps_estimate_average"
                    )
                ),

            "epsEstimateHigh":
                to_float(
                    item.get(
                        "eps_estimate_high"
                    )
                ),

            "epsEstimateLow":
                to_float(
                    item.get(
                        "eps_estimate_low"
                    )
                ),

            "epsAnalystCount":
                to_float(
                    item.get(
                        "eps_estimate_analyst_count"
                    )
                ),

            "revenueEstimate":
                to_float(
                    item.get(
                        "revenue_estimate_average"
                    )
                ),

            "revenueEstimateHigh":
                to_float(
                    item.get(
                        "revenue_estimate_high"
                    )
                ),

            "revenueEstimateLow":
                to_float(
                    item.get(
                        "revenue_estimate_low"
                    )
                ),

            "revenueAnalystCount":
                to_float(
                    item.get(
                        "revenue_estimate_analyst_count"
                    )
                ),

            # ------------------------------------------------
            # Historical consensus snapshots
            # ------------------------------------------------

            "epsEstimate7DaysAgo":
                to_float(
                    item.get(
                        "eps_estimate_average_7_days_ago"
                    )
                ),

            "epsEstimate30DaysAgo":
                to_float(
                    item.get(
                        "eps_estimate_average_30_days_ago"
                    )
                ),

            "epsEstimate60DaysAgo":
                to_float(
                    item.get(
                        "eps_estimate_average_60_days_ago"
                    )
                ),

            "epsEstimate90DaysAgo":
                to_float(
                    item.get(
                        "eps_estimate_average_90_days_ago"
                    )
                ),

            # ------------------------------------------------
            # Revision counts
            # ------------------------------------------------

            "epsRevisionUp7Days":
                to_float(
                    item.get(
                        "eps_estimate_revision_up_trailing_7_days"
                    )
                ),

            "epsRevisionDown7Days":
                to_float(
                    item.get(
                        "eps_estimate_revision_down_trailing_7_days"
                    )
                ),

            "epsRevisionUp30Days":
                to_float(
                    item.get(
                        "eps_estimate_revision_up_trailing_30_days"
                    )
                ),

            "epsRevisionDown30Days":
                to_float(
                    item.get(
                        "eps_estimate_revision_down_trailing_30_days"
                    )
                ),
        })

    print(
        f"\nFiscal-quarter estimate records: "
        f"{len(rows)}"
    )

    return rows


# ============================================================
# MERGE EARNINGS + ESTIMATES
# ============================================================

def merge_earnings_and_estimates(
    earnings_rows,
    estimate_rows
):

    print("\n" + "=" * 70)
    print(
        "MERGING EARNINGS + ESTIMATES"
    )
    print("=" * 70)

    earnings_df = pd.DataFrame(
        earnings_rows
    )

    estimates_df = pd.DataFrame(
        estimate_rows
    )

    if earnings_df.empty:
        print(
            "No earnings data available."
        )
        return pd.DataFrame()

    if estimates_df.empty:
        print(
            "No estimates data available."
        )
        return earnings_df

    # --------------------------------------------------------
    # Normalize dates
    # --------------------------------------------------------

    earnings_df[
        "fiscalDateEnding"
    ] = pd.to_datetime(
        earnings_df[
            "fiscalDateEnding"
        ],
        errors="coerce"
    )

    estimates_df[
        "fiscalDateEnding"
    ] = pd.to_datetime(
        estimates_df[
            "fiscalDateEnding"
        ],
        errors="coerce"
    )

    # --------------------------------------------------------
    # Merge using ticker + fiscal period
    # --------------------------------------------------------

    merged = pd.merge(
        earnings_df,
        estimates_df,
        on=[
            "ticker",
            "fiscalDateEnding"
        ],
        how="left",
        suffixes=(
            "",
            "_estimate"
        )
    )

    # --------------------------------------------------------
    # Calculate additional metrics
    # --------------------------------------------------------

    merged[
        "epsSurprisePctCalculated"
    ] = None

    valid_eps = (
        merged["reportedEPS"].notna()
        &
        merged["epsEstimate"].notna()
        &
        (merged["epsEstimate"] != 0)
    )

    merged.loc[
        valid_eps,
        "epsSurprisePctCalculated"
    ] = (
        (
            merged.loc[
                valid_eps,
                "reportedEPS"
            ]
            -
            merged.loc[
                valid_eps,
                "epsEstimate"
            ]
        )
        /
        merged.loc[
            valid_eps,
            "epsEstimate"
        ]
        * 100
    )

    # --------------------------------------------------------
    # Estimate revision momentum
    # --------------------------------------------------------

    valid_7d = (
        merged[
            "epsEstimate7DaysAgo"
        ].notna()
        &
        merged[
            "epsEstimate7DaysAgo"
        ].ne(0)
        &
        merged[
            "epsEstimate"
        ].notna()
    )

    merged[
        "epsRevisionPct7Days"
    ] = None

    merged.loc[
        valid_7d,
        "epsRevisionPct7Days"
    ] = (
        (
            merged.loc[
                valid_7d,
                "epsEstimate"
            ]
            -
            merged.loc[
                valid_7d,
                "epsEstimate7DaysAgo"
            ]
        )
        /
        merged.loc[
            valid_7d,
            "epsEstimate7DaysAgo"
        ]
        * 100
    )

    valid_30d = (
        merged[
            "epsEstimate30DaysAgo"
        ].notna()
        &
        merged[
            "epsEstimate30DaysAgo"
        ].ne(0)
        &
        merged[
            "epsEstimate"
        ].notna()
    )

    merged[
        "epsRevisionPct30Days"
    ] = None

    merged.loc[
        valid_30d,
        "epsRevisionPct30Days"
    ] = (
        (
            merged.loc[
                valid_30d,
                "epsEstimate"
            ]
            -
            merged.loc[
                valid_30d,
                "epsEstimate30DaysAgo"
            ]
        )
        /
        merged.loc[
            valid_30d,
            "epsEstimate30DaysAgo"
        ]
        * 100
    )

    # --------------------------------------------------------
    # Sort newest first
    # --------------------------------------------------------

    merged = merged.sort_values(
        "fiscalDateEnding",
        ascending=False
    )

    return merged


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n"
        + "#" * 70
    )

    print(
        "US500 MACRO INTELLIGENCE"
    )

    print(
        "CORPORATE EARNINGS SOURCE TEST V3"
    )

    print(
        "#" * 70
    )

    print(
        f"\nTicker: {TICKER}"
    )

    # --------------------------------------------------------
    # STEP 1 — Earnings
    # --------------------------------------------------------

    earnings_rows = get_earnings(
        TICKER
    )

    # --------------------------------------------------------
    # STEP 2 — Estimates
    # --------------------------------------------------------

    estimate_rows = get_estimates(
        TICKER
    )

    # --------------------------------------------------------
    # STEP 3 — Save individual datasets
    # --------------------------------------------------------

    earnings_df = pd.DataFrame(
        earnings_rows
    )

    estimates_df = pd.DataFrame(
        estimate_rows
    )

    earnings_df.to_csv(
        "earnings_source_test.csv",
        index=False
    )

    estimates_df.to_csv(
        "earnings_estimates_source_test.csv",
        index=False
    )

    # --------------------------------------------------------
    # STEP 4 — Merge
    # --------------------------------------------------------

    merged_df = merge_earnings_and_estimates(
        earnings_rows,
        estimate_rows
    )

    # --------------------------------------------------------
    # STEP 5 — Save merged dataset
    # --------------------------------------------------------

    if not merged_df.empty:

        merged_df.to_csv(
            "earnings_combined_test.csv",
            index=False
        )

        print(
            "\nCreated:"
        )

        print(
            "earnings_combined_test.csv"
        )

    # --------------------------------------------------------
    # STEP 6 — Display latest records
    # --------------------------------------------------------

    print(
        "\n"
        + "=" * 70
    )

    print(
        "LATEST COMBINED EARNINGS RECORDS"
    )

    print(
        "=" * 70
    )

    if not merged_df.empty:

        display_columns = [

            "ticker",

            "fiscalDateEnding",

            "reportedDate",

            "reportedEPS",

            "estimatedEPS",

            "surprise",

            "surprisePercentage",

            "epsEstimate",

            "revenueEstimate",

            "epsAnalystCount",

            "revenueAnalystCount",

            "epsEstimate7DaysAgo",

            "epsEstimate30DaysAgo",

            "epsRevisionUp7Days",

            "epsRevisionDown7Days",

            "epsRevisionUp30Days",

            "epsRevisionDown30Days",

            "epsRevisionPct7Days",

            "epsRevisionPct30Days",
        ]

        available_columns = [
            col
            for col in display_columns
            if col in merged_df.columns
        ]

        print(
            merged_df[
                available_columns
            ].head(10).to_string(
                index=False
            )
        )

    else:

        print(
            "No combined records available."
        )

    # --------------------------------------------------------
    # FINAL SUMMARY
    # --------------------------------------------------------

    print(
        "\n"
        + "=" * 70
    )

    print(
        "TEST SUMMARY"
    )

    print(
        "=" * 70
    )

    print(
        f"Earnings records: "
        f"{len(earnings_rows)}"
    )

    print(
        f"Quarterly estimate records: "
        f"{len(estimate_rows)}"
    )

    if not merged_df.empty:

        matched = (
            merged_df[
                "epsEstimate"
            ].notna()
        ).sum()

        print(
            f"Matched earnings + estimates: "
            f"{matched}"
        )

    print(
        "\nGenerated files:"
    )

    print(
        " - earnings_source_test.csv"
    )

    print(
        " - earnings_estimates_source_test.csv"
    )

    print(
        " - earnings_combined_test.csv"
    )

    print(
        " - msft_earnings_raw.json"
    )

    print(
        " - msft_earnings_estimates_raw.json"
    )

    print(
        "\nCORPORATE EARNINGS SOURCE TEST V3 COMPLETED"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
