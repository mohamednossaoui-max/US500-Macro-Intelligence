import os
import requests
import pandas as pd

API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "ALPHAVANTAGE_API_KEY is not set."
    )

BASE_URL = "https://www.alphavantage.co/query"

TICKERS = ["AAPL", "MSFT", "NVDA"]


def get_earnings(ticker):
    params = {
        "function": "EARNINGS",
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

    if "Error Message" in data:
        raise RuntimeError(
            f"{ticker}: {data['Error Message']}"
        )

    if "Note" in data:
        raise RuntimeError(
            f"{ticker}: API limit reached: {data['Note']}"
        )

    return data


def get_estimates(ticker):
    params = {
        "function": "EARNINGS_ESTIMATES",
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

    if "Error Message" in data:
        raise RuntimeError(
            f"{ticker}: {data['Error Message']}"
        )

    if "Note" in data:
        raise RuntimeError(
            f"{ticker}: API limit reached: {data['Note']}"
        )

    return data


def main():

    for ticker in TICKERS:

        print("\n" + "=" * 70)
        print(f"{ticker} — EARNINGS")
        print("=" * 70)

        data = get_earnings(ticker)

        quarterly = data.get(
            "quarterlyEarnings",
            []
        )

        if not quarterly:
            print("No quarterly earnings returned.")
            continue

        rows = []

        for item in quarterly[:10]:

            rows.append({
                "ticker": ticker,
                "fiscalDateEnding": item.get(
                    "fiscalDateEnding"
                ),
                "reportedDate": item.get(
                    "reportedDate"
                ),
                "reportedEPS": item.get(
                    "reportedEPS"
                ),
                "estimatedEPS": item.get(
                    "estimatedEPS"
                ),
                "surprise": item.get(
                    "surprise"
                ),
                "surprisePercentage": item.get(
                    "surprisePercentage"
                ),
            })

        df = pd.DataFrame(rows)

        print(df.to_string(index=False))

        print("\n" + "-" * 70)
        print(f"{ticker} — EARNINGS ESTIMATES")
        print("-" * 70)

        estimates = get_estimates(ticker)

        quarterly_estimates = estimates.get(
            "quarterly",
            []
        )

        if not quarterly_estimates:
            print("No quarterly estimates returned.")
            continue

        estimate_rows = []

        for item in quarterly_estimates[:10]:

            estimate_rows.append({
                "ticker": ticker,
                "fiscalDateEnding": item.get(
                    "fiscalDateEnding"
                ),
                "epsEstimate": item.get(
                    "epsEstimate"
                ),
                "epsEstimateAnalystCount": item.get(
                    "epsEstimateAnalystCount"
                ),
                "revenueEstimate": item.get(
                    "revenueEstimate"
                ),
                "revenueEstimateAnalystCount": item.get(
                    "revenueEstimateAnalystCount"
                ),
            })

        estimates_df = pd.DataFrame(
            estimate_rows
        )

        print(
            estimates_df.to_string(
                index=False
            )
        )


if __name__ == "__main__":
    main()
