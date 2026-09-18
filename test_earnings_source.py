import os
import requests
import pandas as pd


# ============================================================
# ALPHA VANTAGE CONFIGURATION
# ============================================================

API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "ALPHAVANTAGE_API_KEY is not available."
    )

BASE_URL = "https://www.alphavantage.co/query"

# Temporary test:
# AAPL already worked, so we test only MSFT and NVDA
# to avoid unnecessary API requests.
TICKERS = ["MSFT", "NVDA"]


# ============================================================
# API REQUEST
# ============================================================

def request_api(function, ticker):
    """
    Send a request to Alpha Vantage and return the JSON response.
    """

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
        f"\n{ticker} {function} response keys:",
        list(data.keys())
    )

    # --------------------------------------------------------
    # Alpha Vantage error messages
    # --------------------------------------------------------

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
# TEST EARNINGS ENDPOINT
# ============================================================

def test_earnings(ticker):
    """
    Test Alpha Vantage EARNINGS endpoint.
    """

    print("\n" + "=" * 70)
    print(f"{ticker} — EARNINGS")
    print("=" * 70)

    data = request_api(
        "EARNINGS",
        ticker
    )

    quarterly = data.get(
        "quarterlyEarnings",
        []
    )

    # --------------------------------------------------------
    # No quarterly data
    # --------------------------------------------------------

    if not quarterly:

        print(
            f"No quarterly earnings data for {ticker}."
        )

        print(
            "Full response keys:",
            list(data.keys())
        )

        print(
            "Full response:"
        )

        print(data)

        return []

    # --------------------------------------------------------
    # Extract data
    # --------------------------------------------------------

    rows = []

    for item in quarterly[:10]:

        rows.append({
            "ticker": ticker,

            "fiscalDateEnding":
                item.get("fiscalDateEnding"),

            "reportedDate":
                item.get("reportedDate"),

            "reportedEPS":
                item.get("reportedEPS"),

            "estimatedEPS":
                item.get("estimatedEPS"),

            "surprise":
                item.get("surprise"),

            "surprisePercentage":
                item.get("surprisePercentage"),
        })

    # --------------------------------------------------------
    # Display dataframe
    # --------------------------------------------------------

    df = pd.DataFrame(rows)

    print(
        df.to_string(index=False)
    )

    return rows


# ============================================================
# TEST EARNINGS ESTIMATES ENDPOINT
# ============================================================

def test_estimates(ticker):
    """
    Test Alpha Vantage EARNINGS_ESTIMATES endpoint.
    """

    print("\n" + "=" * 70)
    print(f"{ticker} — EARNINGS ESTIMATES")
    print("=" * 70)

    data = request_api(
        "EARNINGS_ESTIMATES",
        ticker
    )

    quarterly = data.get(
        "quarterly",
        []
    )

    # --------------------------------------------------------
    # No quarterly estimates
    # --------------------------------------------------------

    if not quarterly:

        print(
            f"No quarterly estimates data for {ticker}."
        )

        print(
            "Full response keys:",
            list(data.keys())
        )

        print(
            "Full response:"
        )

        print(data)

        return []

    # --------------------------------------------------------
    # Extract estimates
    # --------------------------------------------------------

    rows = []

    for item in quarterly[:10]:

        rows.append({
            "ticker": ticker,

            "fiscalDateEnding":
                item.get("fiscalDateEnding"),

            "epsEstimate":
                item.get("epsEstimate"),

            "epsEstimateAnalystCount":
                item.get("epsEstimateAnalystCount"),

            "revenueEstimate":
                item.get("revenueEstimate"),

            "revenueEstimateAnalystCount":
                item.get("revenueEstimateAnalystCount"),
        })

    # --------------------------------------------------------
    # Display dataframe
    # --------------------------------------------------------

    df = pd.DataFrame(rows)

    print(
        df.to_string(index=False)
    )

    return rows


# ============================================================
# MAIN
# ============================================================

def main():

    earnings_rows = []

    estimate_rows = []

    print(
        "\n"
        + "#" * 70
    )

    print(
        "US500 MACRO INTELLIGENCE"
    )

    print(
        "CORPORATE EARNINGS SOURCE TEST"
    )

    print(
        "#" * 70
    )

    # --------------------------------------------------------
    # Test every ticker
    # --------------------------------------------------------

    for ticker in TICKERS:

        # EARNINGS
        try:

            earnings_rows.extend(
                test_earnings(ticker)
            )

        except Exception as e:

            print(
                f"\nERROR testing "
                f"{ticker} EARNINGS:"
            )

            print(e)

        # ----------------------------------------------------
        # EARNINGS ESTIMATES
        # ----------------------------------------------------

        try:

            estimate_rows.extend(
                test_estimates(ticker)
            )

        except Exception as e:

            print(
                f"\nERROR testing "
                f"{ticker} EARNINGS_ESTIMATES:"
            )

            print(e)

    # ========================================================
    # SAVE EARNINGS RESULTS
    # ========================================================

    if earnings_rows:

        earnings_df = pd.DataFrame(
            earnings_rows
        )

        earnings_df.to_csv(
            "earnings_source_test.csv",
            index=False
        )

        print(
            "\nCreated:"
        )

        print(
            "earnings_source_test.csv"
        )

    else:

        print(
            "\nNo earnings rows were created."
        )

    # ========================================================
    # SAVE ESTIMATE RESULTS
    # ========================================================

    if estimate_rows:

        estimates_df = pd.DataFrame(
            estimate_rows
        )

        estimates_df.to_csv(
            "earnings_estimates_source_test.csv",
            index=False
        )

        print(
            "\nCreated:"
        )

        print(
            "earnings_estimates_source_test.csv"
        )

    else:

        print(
            "\nNo earnings estimate rows were created."
        )

    # ========================================================
    # FINAL STATUS
    # ========================================================

    print(
        "\n"
        + "=" * 70
    )

    print(
        "EARNINGS SOURCE TEST COMPLETED"
    )

    print(
        "=" * 70
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
