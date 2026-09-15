import requests
import pandas as pd
import numpy as np
import yfinance as yf

from datetime import datetime, timedelta

from config import (
    MARKET_TICKER,
    FRED_API_KEY,
    FRED_SERIES,
    BLS_SERIES,
)


# ============================================================
# MARKET DATA
# ============================================================

def get_market_data(
    ticker=MARKET_TICKER,
    period="5y",
):
    """
    Download daily OHLCV market data.
    """

    try:

        data = yf.download(
            ticker,
            period=period,
            interval="1d",
            auto_adjust=False,
            progress=False,
        )

        if data is None or data.empty:
            return pd.DataFrame()

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [
                col[0]
                for col in data.columns
            ]

        data = data.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Adj Close": "adj_close",
                "Volume": "volume",
            }
        )

        required = [
            "open",
            "high",
            "low",
            "close",
        ]

        for col in required:
            if col not in data.columns:
                return pd.DataFrame()

        data = data.dropna(
            subset=required
        )

        data.index = pd.to_datetime(
            data.index
        )

        return data

    except Exception as exc:

        print(
            f"Market data error: {exc}"
        )

        return pd.DataFrame()


# ============================================================
# HISTORICAL MARKET DATA
# ============================================================

def get_historical_market_data(
    ticker=MARKET_TICKER,
    start_date="2019-01-01",
):
    """
    Download extended daily US500 / S&P 500 history.
    """

    try:

        data = yf.download(
            ticker,
            start=start_date,
            interval="1d",
            auto_adjust=False,
            progress=False,
        )

        if data is None or data.empty:
            return pd.DataFrame()

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [
                col[0]
                for col in data.columns
            ]

        data = data.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Adj Close": "adj_close",
                "Volume": "volume",
            }
        )

        required = [
            "open",
            "high",
            "low",
            "close",
        ]

        for col in required:
            if col not in data.columns:
                return pd.DataFrame()

        data = data.dropna(
            subset=required
        )

        data.index = pd.to_datetime(
            data.index
        )

        return data.sort_index()

    except Exception as exc:

        print(
            f"Historical market data error: {exc}"
        )

        return pd.DataFrame()


# ============================================================
# FRED
# ============================================================

def fred_series(
    series_id,
    start_date=None,
):
    """
    Retrieve a FRED time series.

    Returns:
        DataFrame with:
            date
            value

    FRED requires a valid API key.
    """

    if not FRED_API_KEY:

        print(
            f"FRED API KEY MISSING -> {series_id}"
        )

        return pd.DataFrame(
            columns=["date", "value"]
        )

    if start_date is None:

        start_date = (
            datetime.utcnow()
            - timedelta(days=3650)
        ).strftime("%Y-%m-%d")

    url = (
        "https://api.stlouisfed.org/"
        "fred/series/observations"
    )

    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=30,
        )

        if response.status_code != 200:

            print(
                f"FRED ERROR {series_id}: "
                f"HTTP {response.status_code}"
            )

            try:
                print(
                    response.text[:500]
                )
            except Exception:
                pass

            return pd.DataFrame(
                columns=["date", "value"]
            )

        payload = response.json()

        if "error_code" in payload:

            print(
                f"FRED API ERROR {series_id}: "
                f"{payload.get('error_code')}"
            )

            print(
                payload.get(
                    "error_message",
                    "",
                )
            )

            return pd.DataFrame(
                columns=["date", "value"]
            )

        observations = payload.get(
            "observations",
            []
        )

        rows = []

        for obs in observations:

            value = obs.get("value")

            if value in (
                None,
                "",
                ".",
            ):
                continue

            try:

                value = float(value)

            except Exception:

                continue

            date = obs.get("date")

            if not date:
                continue

            rows.append(
                {
                    "date": pd.to_datetime(
                        date
                    ),
                    "value": value,
                }
            )

        if not rows:

            print(
                f"FRED NO DATA -> {series_id}"
            )

            return pd.DataFrame(
                columns=["date", "value"]
            )

        df = pd.DataFrame(
            rows
        )

        df = (
            df
            .set_index("date")
            .sort_index()
        )

        return df

    except requests.exceptions.RequestException as exc:

        print(
            f"FRED REQUEST ERROR "
            f"{series_id}: {exc}"
        )

        return pd.DataFrame(
            columns=["date", "value"]
        )

    except Exception as exc:

        print(
            f"FRED ERROR "
            f"{series_id}: {exc}"
        )

        return pd.DataFrame(
            columns=["date", "value"]
        )


# ============================================================
# LOAD ALL FRED DATA
# ============================================================

def load_fred_data(
    start_date=None,
):
    """
    Load all FRED series defined in config.py.
    """

    data = {}

    for name, series_id in FRED_SERIES.items():

        data[name] = fred_series(
            series_id,
            start_date=start_date,
        )

    return data


# ============================================================
# BLS API
# ============================================================

def bls_series(
    series_id,
    start_year=None,
    end_year=None,
):
    """
    Retrieve a BLS public time series.
    """

    current_year = datetime.utcnow().year

    if end_year is None:
        end_year = current_year

    if start_year is None:
        start_year = end_year - 10

    url = (
        "https://api.bls.gov/publicAPI/v2/"
        "timeseries/data/"
    )

    payload = {
        "seriesid": [series_id],
        "startyear": str(start_year),
        "endyear": str(end_year),
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=30,
        )

        response.raise_for_status()

        result = response.json()

        if result.get(
            "status"
        ) != "REQUEST_SUCCEEDED":

            print(
                f"BLS ERROR {series_id}: "
                f"{result}"
            )

            return pd.DataFrame(
                columns=["date", "value"]
            )

        rows = []

        for series in result.get(
            "Results",
            {}
        ).get(
            "series",
            []
        ):

            for item in series.get(
                "data",
                []
            ):

                value = item.get(
                    "value"
                )

                if value in (
                    None,
                    "",
                ):
                    continue

                try:

                    value = float(
                        value.replace(
                            ",",
                            "",
                        )
                    )

                except Exception:

                    continue

                period = item.get(
                    "period",
                    "",
                )

                if not period.startswith(
                    "M"
                ):
                    continue

                try:

                    month = int(
                        period[1:]
                    )

                except Exception:

                    continue

                if month < 1 or month > 12:
                    continue

                date = pd.Timestamp(
                    year=int(
                        item["year"]
                    ),
                    month=month,
                    day=1,
                )

                rows.append(
                    {
                        "date": date,
                        "value": value,
                    }
                )

        if not rows:

            return pd.DataFrame(
                columns=["date", "value"]
            )

        df = pd.DataFrame(
            rows
        )

        df = (
            df
            .drop_duplicates(
                subset=["date"]
            )
            .set_index("date")
            .sort_index()
        )

        return df

    except Exception as exc:

        print(
            f"BLS ERROR {series_id}: {exc}"
        )

        return pd.DataFrame(
            columns=["date", "value"]
        )


# ============================================================
# LOAD BLS DATA
# ============================================================

def load_bls_data():

    data = {}

    for name, series_id in BLS_SERIES.items():

        data[name] = bls_series(
            series_id
        )

    return data


# ============================================================
# COMBINED MACRO DATA
# ============================================================

def load_all_macro_data(
    start_date=None,
):
    """
    Load all macroeconomic data.
    """

    fred = load_fred_data(
        start_date=start_date
    )

    bls = load_bls_data()

    combined = {}

    combined.update(fred)
    combined.update(bls)

    return combined


# ============================================================
# SAFE LATEST VALUE
# ============================================================

def latest_value(
    df,
    default=np.nan,
):

    if df is None:
        return default

    if df.empty:
        return default

    try:

        value = (
            df["value"]
            .dropna()
            .iloc[-1]
        )

        return float(value)

    except Exception:

        return default


# ============================================================
# DATA STATUS
# ============================================================

def data_status(
    macro_data,
):

    status = []

    for name, df in macro_data.items():

        if (
            df is None
            or df.empty
        ):

            status.append(
                {
                    "Indicator": name,
                    "Status": "UNAVAILABLE",
                }
            )

        else:

            status.append(
                {
                    "Indicator": name,
                    "Status": "AVAILABLE",
                }
            )

    return pd.DataFrame(
        status
    )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print()
    print(
        "DATA.PY TEST"
    )
    print(
        "============"
    )

    # --------------------------------------------------------
    # MARKET TEST
    # --------------------------------------------------------

    print()
    print(
        "HISTORICAL MARKET DATA TEST"
    )
    print(
        "---------------------------"
    )

    market = get_historical_market_data(
        start_date="2019-01-01"
    )

    if market.empty:

        print(
            "ERROR: Historical market data unavailable."
        )

    else:

        print(
            "Rows:",
            len(market)
        )

        print(
            "Start:",
            market.index.min().date()
        )

        print(
            "End:",
            market.index.max().date()
        )

        print(
            "Columns:",
            list(market.columns)
        )

        required = [
            "open",
            "high",
            "low",
            "close",
        ]

        missing = [
            col
            for col in required
            if col not in market.columns
        ]

        if missing:

            print(
                "Missing columns:",
                missing
            )

        else:

            print(
                "Required OHLC columns: OK"
            )

    # --------------------------------------------------------
    # FRED TEST
    # --------------------------------------------------------

    print()
    print(
        "FRED TEST"
    )
    print(
        "---------"
    )

    if not FRED_API_KEY:

        print(
            "ERROR: FRED_API_KEY is not configured."
        )

        print(
            "Add FRED_API_KEY to your GitHub Actions secret."
        )

    else:

        print(
            "FRED API key detected."
        )

        fred = load_fred_data(
            start_date="2019-01-01"
        )

        for name, df in fred.items():

            if df.empty:

                print(
                    f"{name:<22}: UNAVAILABLE"
                )

            else:

                latest_date = (
                    df.index.max().date()
                )

                latest = float(
                    df["value"].iloc[-1]
                )

                print(
                    f"{name:<22}: "
                    f"{len(df):>5} observations | "
                    f"{df.index.min().date()} -> "
                    f"{latest_date} | "
                    f"latest={latest}"
                )

    # --------------------------------------------------------
    # BLS TEST
    # --------------------------------------------------------

    print()
    print(
        "BLS TEST"
    )
    print(
        "--------"
    )

    bls = load_bls_data()

    for name, df in bls.items():

        if df.empty:

            print(
                f"{name:<22}: UNAVAILABLE"
            )

        else:

            print(
                f"{name:<22}: "
                f"{len(df):>5} observations | "
                f"{df.index.min().date()} -> "
                f"{df.index.max().date()}"
            )

    print()
    print(
        "DATA.PY TEST COMPLETE"
    )
