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

# We test ONE company only to minimize API usage.
TICKER = "MSFT"

# Alpha Vantage asks free users to spread requests.
REQUEST_DELAY = 1.5


# ============================================================
# API REQUEST
# ============================================================

def request_api(function, ticker):
    """
    Request one Alpha Vantage endpoint.

    A delay is applied before every request except the first one.
    """

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

    # --------------------------------------------------------
    # Error / rate-limit responses
    # --------------------------------------------------------

    if "Error Message" in data:
        print("\nAlpha Vantage Error Message:")
        print(data["Error Message"])

    if "Note" in data:
        print("\nAlpha Vantage Note:")
        print(data["Note"])

    if "Information" in data:
        print("\nAlpha Vantage Information:")
        print(data["Information"])

    return data


# ============================================================
# SAVE RAW JSON
# ============================================================

def save_raw_json(filename, data):
    """
    Save the complete API response.
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
            ensure_ascii=False
        )

    print(
        f"\nCreated raw response: {filename}"
    )


# ============================================================
# TEST EARNINGS
# ============================================================

def test_earnings(ticker):

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

    if not quarterly:

        print(
            "\nNo quarterly earnings data returned."
        )

        print(
            "Full response:"
        )

        print(data)

        return []

    print(
        f"\nQuarterly records returned: "
        f"{len(quarterly)}"
    )

    rows = []

    for item in quarterly[:10]:

        rows.append({

            "ticker":
                ticker,

            "fiscalDateEnding":
                item.get(
                    "fiscalDateEnding"
                ),

            "reportedDate":
                item.get(
                    "reportedDate"
                ),

            "reportedEPS":
                item.get(
                    "reportedEPS"
                ),

            "estimatedEPS":
                item.get(
                    "estimatedEPS"
                ),

            "surprise":
                item.get(
                    "surprise"
                ),

            "surprisePercentage":
                item.get(
                    "surprisePercentage"
                ),
        })

    df = pd.DataFrame(rows)

    print("\nParsed earnings data:")

    print(
        df.to_string(
            index=False
        )
    )

    df.to_csv(
        "earnings_source_test.csv",
        index=False
    )

    print(
        "\nCreated: earnings_source_test.csv"
    )

    return rows


# ============================================================
# TEST EARNINGS ESTIMATES
# ============================================================

def test_estimates(ticker):

    print("\n" + "=" * 70)
    print(
        f"{ticker} — EARNINGS ESTIMATES"
    )
    print("=" * 70)

    # Wait before the second API request.
    print(
        f"\nWaiting {REQUEST_DELAY} seconds "
        "before next API request..."
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

    quarterly = data.get(
        "quarterly",
        []
    )

    if not quarterly:

        print(
            "\nNo quarterly estimates data returned."
        )

        print(
            "\nFull response:"
        )

        print(data)

        return []

    print(
        f"\nQuarterly estimate records returned: "
        f"{len(quarterly)}"
    )

    rows = []

    for item in quarterly[:10]:

        rows.append({

            "ticker":
                ticker,

            "fiscalDateEnding":
                item.get(
                    "fiscalDateEnding"
                ),

            "epsEstimate":
                item.get(
                    "epsEstimate"
                ),

            "epsEstimateAnalystCount":
                item.get(
                    "epsEstimateAnalystCount"
                ),

            "revenueEstimate":
                item.get(
                    "revenueEstimate"
                ),

            "revenueEstimateAnalystCount":
                item.get(
                    "revenueEstimateAnalystCount"
                ),
        })

    df = pd.DataFrame(rows)

    print(
        "\nParsed estimates:"
    )

    print(
        df.to_string(
            index=False
        )
    )

    df.to_csv(
        "earnings_estimates_source_test.csv",
        index=False
    )

    print(
        "\nCreated: "
        "earnings_estimates_source_test.csv"
    )

    return rows


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
        "CORPORATE EARNINGS SOURCE TEST V2"
    )

    print(
        "#" * 70
    )

    print(
        f"\nTicker: {TICKER}"
    )

    print(
        f"Request delay: "
        f"{REQUEST_DELAY} seconds"
    )

    # --------------------------------------------------------
    # REQUEST 1
    # --------------------------------------------------------

    earnings_rows = test_earnings(
        TICKER
    )

    # --------------------------------------------------------
    # REQUEST 2
    # --------------------------------------------------------

    estimate_rows = test_estimates(
        TICKER
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
        f"Earnings rows: "
        f"{len(earnings_rows)}"
    )

    print(
        f"Estimate rows: "
        f"{len(estimate_rows)}"
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
        " - msft_earnings_raw.json"
    )

    print(
        " - msft_earnings_estimates_raw.json"
    )

    print(
        "\nEARNINGS SOURCE TEST V2 COMPLETED"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
