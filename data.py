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

    Default market proxy:
        ^GSPC = S&P 500 Index

    Important:
        This may differ slightly from the US500 CFD/futures
        feed used by a broker.
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

        # ----------------------------------------------------
        # Handle MultiIndex columns
        # ----------------------------------------------------

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

    except Exception:

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

    If no API key is available, returns an empty DataFrame.
    """

    if not FRED_API_KEY:

        return pd.DataFrame(
            columns=["value"]
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
            timeout=20,
        )

        response.raise_for_status()

        payload = response.json()

        observations = payload.get(
            "observations",
            []
        )

        rows = []

        for obs in observations:

            value = obs.get(
                "value"
            )

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

            rows.append(
                {
                    "date": pd.to_datetime(
                        obs["date"]
                    ),
                    "value": value,
                }
            )

        if not rows:

            return pd.DataFrame(
                columns=["value"]
            )

        df = pd.DataFrame(rows)

        df = df.set_index(
            "date"
        ).sort_index()

        return df

    except Exception:

        return pd.DataFrame(
            columns=["value"]
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

    BLS allows a limited historical range
    per API request.
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

        if result.get("status") != "REQUEST_SUCCEEDED":

            return pd.DataFrame(
                columns=["value"]
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
                            ""
                        )
                    )

                except Exception:

                    continue

                period = item.get(
                    "period",
                    ""
                )

                # ------------------------------------------------
                # Only monthly observations
                # ------------------------------------------------

                if not period.startswith("M"):

                    continue

                month = int(
                    period[1:]
                )

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
                columns=["value"]
            )

        df = pd.DataFrame(rows)

        df = (
            df
            .drop_duplicates(
                subset=["date"]
            )
            .set_index("date")
            .sort_index()
        )

        return df

    except Exception:

        return pd.DataFrame(
            columns=["value"]
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

def load_all_macro_data():

    fred = load_fred_data()

    bls = load_bls_data()

    combined = {}

    combined.update(
        fred
    )

    combined.update(
        bls
    )

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

        value = df["value"].dropna().iloc[-1]

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

        if df is None or df.empty:

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
