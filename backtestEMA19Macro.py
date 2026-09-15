"""
US500 EMA19 + Macro Regime Backtest
===================================

Phase 2:
EMA19 Pullback baseline + historical macro regime classification.

IMPORTANT:
- No trade execution.
- No position sizing.
- No optimization.
- EMA19 entry logic is unchanged.
- Stop loss and TP are unchanged.
- Macro is used for classification and comparison.
- Macro data is aligned backward using observation dates.
- FRED API key is used when available.
- Public FRED CSV is used only as a fallback.
- Derived macro growth/inflation rates are calculated from raw series.

NOTE:
This is NOT yet a true vintage/release-date backtest.
It avoids future observation dates, but historical revisions
and publication timing are not fully reconstructed.
"""

from __future__ import annotations

import io
import os
import warnings
from typing import Optional

import numpy as np
import pandas as pd
import requests

from data import (
    get_historical_market_data,
    load_all_macro_data,
)

warnings.filterwarnings("ignore")


# ============================================================
# SETTINGS
# ============================================================

START_DATE = "2019-01-01"

EMA_FAST = 19
EMA_TREND = 200

RR = 4.0

ATR_PERIOD = 14
LOOKBACK_LOW = 5
ATR_MULTIPLIER = 0.5

TICKER = "^GSPC"

FRED_START_DATE = START_DATE


# ============================================================
# FRED PUBLIC SERIES
# ============================================================

FRED_PUBLIC_SERIES = {
    "US10Y": "DGS10",
    "US2Y": "DGS2",
    "T10Y2Y": "T10Y2Y",
    "VIX": "VIXCLS",
    "UNRATE": "UNRATE",
    "INITIAL_CLAIMS_4W": "IC4WSA",
    "HY_SPREAD": "BAMLH0A0HYM2",
    "CORP_OAS": "BAMLC0A0CM",
    "NFCI": "NFCI",
    "INDPRO": "INDPRO",
    "RETAIL": "RSAFS",
    "PCE": "PCE",
    "PCEPI": "PCEPI",
    "CORE_PCE": "PCEPILFE",
    "FEDFUNDS": "FEDFUNDS",
}


# ============================================================
# DATE NORMALIZATION
# ============================================================

def normalize_datetime_series(
    values,
) -> pd.Series:

    """
    Normalize all dates to timezone-naive datetime64[ns].

    This prevents merge_asof errors such as:

    dtype('<M8[s]')
    vs
    dtype('<M8[us]')
    """

    result = pd.to_datetime(
        values,
        errors="coerce",
        utc=True,
    )

    # Convert timezone-aware UTC to timezone-naive.
    try:
        result = result.dt.tz_localize(None)
    except AttributeError:
        pass

    return result.astype(
        "datetime64[ns]"
    )


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    df: pd.DataFrame,
    period: int = 14,
) -> pd.Series:

    high = df["high"]
    low = df["low"]
    close = df["close"]

    previous_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - previous_close).abs()
    tr3 = (low - previous_close).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1,
    ).max(axis=1)

    atr = true_range.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    return atr


# ============================================================
# MARKET PREPARATION
# ============================================================

def prepare_market_data(
    df: pd.DataFrame,
) -> pd.DataFrame:

    data = df.copy()

    data.index = pd.to_datetime(
        data.index,
        errors="coerce",
    )

    data = data[
        ~data.index.isna()
    ]

    data = data.sort_index()

    data.columns = [
        str(c)
        .lower()
        .replace(" ", "_")
        for c in data.columns
    ]

    required = [
        "open",
        "high",
        "low",
        "close",
    ]

    for col in required:

        if col not in data.columns:

            raise ValueError(
                f"Required market column missing: {col}"
            )

    data["ema19"] = data[
        "close"
    ].ewm(
        span=EMA_FAST,
        adjust=False,
    ).mean()

    data["ema200"] = data[
        "close"
    ].ewm(
        span=EMA_TREND,
        adjust=False,
    ).mean()

    # Previous completed candle ATR.
    data["atr14"] = calculate_atr(
        data,
        ATR_PERIOD,
    ).shift(1)

    return data


# ============================================================
# EMA19 SIGNAL DETECTION
# ============================================================

def detect_ema19_pullbacks(
    df: pd.DataFrame,
) -> pd.DataFrame:

    signals = []

    start_index = EMA_TREND

    for i in range(
        start_index,
        len(df),
    ):

        row = df.iloc[i]

        close = row["close"]
        low = row["low"]
        ema19 = row["ema19"]
        ema200 = row["ema200"]

        if pd.isna(close):
            continue

        if pd.isna(low):
            continue

        if pd.isna(ema19):
            continue

        if pd.isna(ema200):
            continue

        # ----------------------------------------------------
        # TREND
        # ----------------------------------------------------

        if close <= ema200:
            continue

        if ema19 <= ema200:
            continue

        # ----------------------------------------------------
        # TOUCH EMA19
        # ----------------------------------------------------

        if low > ema19:
            continue

        # ----------------------------------------------------
        # PREVENT IMMEDIATE DUPLICATE SIGNAL
        # ----------------------------------------------------

        if i > 0:

            previous = df.iloc[i - 1]

            previous_close = (
                previous["close"]
            )

            previous_low = (
                previous["low"]
            )

            previous_ema19 = (
                previous["ema19"]
            )

            if (
                not pd.isna(previous_close)
                and not pd.isna(previous_low)
                and not pd.isna(previous_ema19)
            ):

                previous_was_reclaim = (
                    previous_close > previous_ema19
                    and previous_low <= previous_ema19
                )

                if previous_was_reclaim:
                    continue

        distance_ema19 = (
            close / ema19 - 1
        ) * 100

        distance_ema200 = (
            close / ema200 - 1
        ) * 100

        signals.append(
            {
                "signal_date": df.index[i],
                "entry": float(close),
                "ema19": float(ema19),
                "ema200": float(ema200),
                "distance_from_ema19_pct":
                    float(distance_ema19),
                "distance_from_ema200_pct":
                    float(distance_ema200),
            }
        )

    return pd.DataFrame(
        signals
    )


# ============================================================
# STOP LOSS
# ============================================================

def calculate_stop_loss(
    df: pd.DataFrame,
    signal_index: int,
) -> Optional[float]:

    if signal_index < LOOKBACK_LOW:

        return None

    row = df.iloc[
        signal_index
    ]

    atr = row["atr14"]

    if pd.isna(atr):

        return None

    # Only candles BEFORE the signal candle.
    previous_candles = df.iloc[
        signal_index - LOOKBACK_LOW:
        signal_index
    ]

    if len(previous_candles) < LOOKBACK_LOW:

        return None

    lowest_low = (
        previous_candles["low"]
        .min()
    )

    if pd.isna(lowest_low):

        return None

    stop_loss = (
        lowest_low
        - ATR_MULTIPLIER * atr
    )

    return float(stop_loss)


# ============================================================
# TRADE EVALUATION
# ============================================================

def evaluate_trade(
    df: pd.DataFrame,
    signal_index: int,
    entry: float,
    stop_loss: float,
    take_profit: float,
) -> dict:

    result = {
        "status": "OPEN",
        "result": "OPEN",
        "exit_date": pd.NaT,
        "R": np.nan,
    }

    for j in range(
        signal_index + 1,
        len(df),
    ):

        row = df.iloc[j]

        high = row["high"]
        low = row["low"]

        if pd.isna(high) or pd.isna(low):

            continue

        hit_tp = (
            high >= take_profit
        )

        hit_sl = (
            low <= stop_loss
        )

        # ----------------------------------------------------
        # SAME-DAY TP + SL
        # ----------------------------------------------------

        if hit_tp and hit_sl:

            result["status"] = "VALID"
            result["result"] = "AMBIGUOUS"
            result["exit_date"] = df.index[j]

            return result

        # ----------------------------------------------------
        # STOP
        # ----------------------------------------------------

        if hit_sl:

            result["status"] = "VALID"
            result["result"] = "LOSS"
            result["exit_date"] = df.index[j]
            result["R"] = -1.0

            return result

        # ----------------------------------------------------
        # TARGET
        # ----------------------------------------------------

        if hit_tp:

            result["status"] = "VALID"
            result["result"] = "WIN"
            result["exit_date"] = df.index[j]
            result["R"] = RR

            return result

    return result


# ============================================================
# BUILD BACKTEST
# ============================================================

def build_ema19_backtest(
    market: pd.DataFrame,
    signals: pd.DataFrame,
) -> pd.DataFrame:

    trades = []

    for _, signal in signals.iterrows():

        signal_date = pd.Timestamp(
            signal["signal_date"]
        )

        try:

            signal_index = (
                market.index.get_loc(
                    signal_date
                )
            )

        except KeyError:

            continue

        entry = float(
            signal["entry"]
        )

        stop_loss = calculate_stop_loss(
            market,
            signal_index,
        )

        row = signal.to_dict()

        row["stop_loss"] = stop_loss

        # ----------------------------------------------------
        # INVALID STOP
        # ----------------------------------------------------

        if (
            stop_loss is None
            or pd.isna(stop_loss)
            or stop_loss >= entry
        ):

            row["take_profit"] = np.nan
            row["risk_points"] = np.nan
            row["status"] = "INVALID_SL"
            row["result"] = "INVALID_SL"
            row["exit_date"] = pd.NaT
            row["R"] = np.nan

            trades.append(row)

            continue

        risk_points = (
            entry - stop_loss
        )

        take_profit = (
            entry
            + RR * risk_points
        )

        evaluation = evaluate_trade(
            market,
            signal_index,
            entry,
            stop_loss,
            take_profit,
        )

        row["take_profit"] = take_profit
        row["risk_points"] = risk_points

        row.update(
            evaluation
        )

        trades.append(row)

    return pd.DataFrame(
        trades
    )


# ============================================================
# MACRO FRAME NORMALIZATION
# ============================================================

def _prepare_macro_frame(
    value,
    name: str,
) -> pd.DataFrame:

    if value is None:

        return pd.DataFrame(
            columns=[
                "date",
                name,
            ]
        )

    if isinstance(
        value,
        pd.Series,
    ):

        frame = value.to_frame(
            name=name
        ).reset_index()

    elif isinstance(
        value,
        pd.DataFrame,
    ):

        frame = value.copy()

        if isinstance(
            frame.index,
            pd.DatetimeIndex,
        ):

            frame = frame.reset_index()

            frame = frame.rename(
                columns={
                    frame.columns[0]:
                        "date"
                }
            )

        else:

            date_column = None

            for col in frame.columns:

                if str(col).lower() in (
                    "date",
                    "datetime",
                    "time",
                ):

                    date_column = col
                    break

            if date_column is not None:

                frame = frame.rename(
                    columns={
                        date_column:
                            "date"
                    }
                )

    else:

        return pd.DataFrame(
            columns=[
                "date",
                name,
            ]
        )

    if "date" not in frame.columns:

        return pd.DataFrame(
            columns=[
                "date",
                name,
            ]
        )

    value_columns = [
        c for c in frame.columns
        if c != "date"
    ]

    if name not in frame.columns:

        if not value_columns:

            return pd.DataFrame(
                columns=[
                    "date",
                    name,
                ]
            )

        frame = frame.rename(
            columns={
                value_columns[0]:
                    name
            }
        )

    frame["date"] = normalize_datetime_series(
        frame["date"]
    )

    frame[name] = pd.to_numeric(
        frame[name],
        errors="coerce",
    )

    frame = frame[
        [
            "date",
            name,
        ]
    ]

    frame = frame.dropna(
        subset=["date"]
    )

    frame = frame.sort_values(
        "date"
    )

    frame = frame.drop_duplicates(
        subset=["date"],
        keep="last",
    )

    return frame


# ============================================================
# EXTRACT SERIES FROM DATA DICT
# ============================================================

def _extract_macro_series(
    macro_data,
    possible_names,
) -> pd.DataFrame:

    if macro_data is None:

        return pd.DataFrame()

    if isinstance(
        macro_data,
        dict,
    ):

        normalized = {
            str(k).lower(): v
            for k, v
            in macro_data.items()
        }

        for wanted in possible_names:

            if wanted.lower() in normalized:

                return _prepare_macro_frame(
                    normalized[
                        wanted.lower()
                    ],
                    wanted,
                )

    if isinstance(
        macro_data,
        pd.DataFrame,
    ):

        columns_lower = {
            str(c).lower(): c
            for c in macro_data.columns
        }

        for wanted in possible_names:

            if wanted.lower() in columns_lower:

                original = columns_lower[
                    wanted.lower()
                ]

                frame = macro_data[
                    [original]
                ].copy()

                frame = frame.rename(
                    columns={
                        original:
                            wanted
                    }
                )

                return _prepare_macro_frame(
                    frame,
                    wanted,
                )

    return pd.DataFrame()


# ============================================================
# FRED API KEY
# ============================================================

def get_fred_api_key() -> str:

    return os.getenv(
        "FRED_API_KEY",
        "",
    ).strip()


# ============================================================
# FRED API DIRECT FETCH
# ============================================================

def fetch_fred_api_series(
    series_id: str,
    start_date: str = START_DATE,
) -> pd.DataFrame:

    """
    Direct FRED API fetch.

    Used mainly for series that are not present in data.py,
    such as PCEPI in the current configuration.
    """

    api_key = get_fred_api_key()

    if not api_key:

        return pd.DataFrame()

    url = (
        "https://api.stlouisfed.org/fred/series/observations"
    )

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start_date,
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=20,
            headers={
                "User-Agent":
                    "US500-Macro-Backtest/1.0"
            },
        )

        response.raise_for_status()

        payload = response.json()

        observations = payload.get(
            "observations",
            [],
        )

        if not observations:

            return pd.DataFrame()

        frame = pd.DataFrame(
            observations
        )

        if (
            "date" not in frame.columns
            or "value" not in frame.columns
        ):

            return pd.DataFrame()

        frame["date"] = normalize_datetime_series(
            frame["date"]
        )

        frame["value"] = pd.to_numeric(
            frame["value"],
            errors="coerce",
        )

        frame = frame[
            [
                "date",
                "value",
            ]
        ]

        frame = frame.dropna(
            subset=["date"]
        )

        frame = frame.sort_values(
            "date"
        )

        frame = frame.drop_duplicates(
            subset=["date"],
            keep="last",
        )

        return frame

    except Exception as exc:

        print(
            f"  FRED API fetch failed "
            f"{series_id}: {exc}"
        )

        return pd.DataFrame()


# ============================================================
# PUBLIC FRED CSV FALLBACK
# ============================================================

def fetch_fred_public_csv(
    series_id: str,
    start_date: str = START_DATE,
) -> pd.DataFrame:

    """
    Download FRED data without an API key.

    This is only a fallback.
    """

    url = (
        "https://fred.stlouisfed.org/graph/fredgraph.csv"
        f"?id={series_id}"
        f"&cosd={start_date}"
    )

    try:

        response = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent":
                    "US500-Macro-Backtest/1.0"
            },
        )

        response.raise_for_status()

        frame = pd.read_csv(
            io.StringIO(
                response.text
            )
        )

        if frame.empty:

            return pd.DataFrame()

        date_col = frame.columns[0]

        value_col = frame.columns[1]

        frame = frame.rename(
            columns={
                date_col: "date",
                value_col: "value",
            }
        )

        frame["date"] = normalize_datetime_series(
            frame["date"]
        )

        frame["value"] = pd.to_numeric(
            frame["value"],
            errors="coerce",
        )

        frame = frame[
            [
                "date",
                "value",
            ]
        ]

        frame = frame.dropna(
            subset=["date"]
        )

        frame = frame.sort_values(
            "date"
        )

        frame = frame.drop_duplicates(
            subset=["date"],
            keep="last",
        )

        return frame

    except Exception as exc:

        print(
            f"  FRED public fetch failed "
            f"{series_id}: {exc}"
        )

        return pd.DataFrame()


# ============================================================
# LOAD MACRO WITH FALLBACK
# ============================================================

def load_macro_resilient() -> dict:

    """
    Load macro data in three layers:

    1. Existing data.py loader.
    2. Direct FRED API using FRED_API_KEY.
    3. Public FRED CSV fallback.

    This avoids losing an individual series simply because
    it was not included in config.py.
    """

    existing_data = {}

    try:

        loaded = load_all_macro_data(
            start_date=START_DATE
        )

        if isinstance(
            loaded,
            dict,
        ):

            existing_data = loaded

    except Exception as exc:

        print(
            f"Existing macro loader warning: {exc}"
        )

    result = {}

    # --------------------------------------------------------
    # STANDARD SERIES
    # --------------------------------------------------------

    aliases = {

        "US10Y": [
            "US10Y",
            "DGS10",
        ],

        "US2Y": [
            "US2Y",
            "DGS2",
        ],

        "T10Y2Y": [
            "T10Y2Y",
        ],

        "VIX": [
            "VIX",
            "VIXCLS",
        ],

        "UNRATE": [
            "UNRATE",
            "UNEMPLOYMENT",
        ],

        "INITIAL_CLAIMS_4W": [
            "INITIAL_CLAIMS_4W",
            "IC4WSA",
        ],

        "HY_SPREAD": [
            "HY_SPREAD",
            "BAMLH0A0HYM2",
        ],

        "CORP_OAS": [
            "CORP_OAS",
            "BAMLC0A0CM",
        ],

        "NFCI": [
            "NFCI",
        ],

        "INDPRO": [
            "INDPRO",
        ],

        "RETAIL": [
            "RETAIL",
            "RSAFS",
        ],

        "PCE": [
            "PCE",
        ],

        "PCEPI": [
            "PCEPI",
        ],

        "CORE_PCE": [
            "CORE_PCE",
            "PCEPILFE",
        ],

        "FEDFUNDS": [
            "FEDFUNDS",
        ],
    }

    # --------------------------------------------------------
    # FIRST: DATA.PY
    # --------------------------------------------------------

    for standard_name, names in aliases.items():

        frame = _extract_macro_series(
            existing_data,
            names,
        )

        if not frame.empty:

            frame = frame.rename(
                columns={
                    frame.columns[-1]:
                        standard_name
                }
            )

            result[
                standard_name
            ] = frame

    # --------------------------------------------------------
    # SECOND: DIRECT FRED API
    # --------------------------------------------------------

    for standard_name, series_id in (
        FRED_PUBLIC_SERIES.items()
    ):

        if standard_name in result:

            continue

        if get_fred_api_key():

            print(
                f"  Fetching FRED API: "
                f"{standard_name} ({series_id})"
            )

            frame = fetch_fred_api_series(
                series_id=series_id,
                start_date=FRED_START_DATE,
            )

            if not frame.empty:

                frame = frame.rename(
                    columns={
                        "value":
                            standard_name
                    }
                )

                result[
                    standard_name
                ] = frame

    # --------------------------------------------------------
    # THIRD: PUBLIC CSV
    # --------------------------------------------------------

    for standard_name, series_id in (
        FRED_PUBLIC_SERIES.items()
    ):

        if standard_name in result:

            continue

        print(
            f"  Fetching FRED fallback: "
            f"{standard_name} ({series_id})"
        )

        frame = fetch_fred_public_csv(
            series_id=series_id,
            start_date=FRED_START_DATE,
        )

        if frame.empty:

            continue

        frame = frame.rename(
            columns={
                "value":
                    standard_name
            }
        )

        result[
            standard_name
        ] = frame

    return result


# ============================================================
# DERIVED MACRO INDICATORS
# ============================================================

def add_derived_series(
    macro_frames: dict,
) -> dict:

    result = dict(
        macro_frames
    )

    # --------------------------------------------------------
    # INDUSTRIAL PRODUCTION YOY
    # --------------------------------------------------------

    if "INDPRO" in result:

        frame = result[
            "INDPRO"
        ].copy()

        frame = frame.sort_values(
            "date"
        )

        frame[
            "INDPRO_YOY"
        ] = (
            frame["INDPRO"]
            .pct_change(12)
            * 100
        )

        result[
            "INDPRO_DERIVED"
        ] = frame[
            [
                "date",
                "INDPRO_YOY",
            ]
        ]

    # --------------------------------------------------------
    # RETAIL SALES YOY
    # --------------------------------------------------------

    if "RETAIL" in result:

        frame = result[
            "RETAIL"
        ].copy()

        frame = frame.sort_values(
            "date"
        )

        frame[
            "RETAIL_YOY"
        ] = (
            frame["RETAIL"]
            .pct_change(12)
            * 100
        )

        result[
            "RETAIL_DERIVED"
        ] = frame[
            [
                "date",
                "RETAIL_YOY",
            ]
        ]

    # --------------------------------------------------------
    # HEADLINE PCE INFLATION
    # --------------------------------------------------------

    if "PCEPI" in result:

        frame = result[
            "PCEPI"
        ].copy()

        frame = frame.sort_values(
            "date"
        )

        frame[
            "PCE_INFLATION"
        ] = (
            frame["PCEPI"]
            .pct_change(12)
            * 100
        )

        result[
            "PCE_INFLATION_DERIVED"
        ] = frame[
            [
                "date",
                "PCE_INFLATION",
            ]
        ]

    # --------------------------------------------------------
    # CORE PCE INFLATION
    # --------------------------------------------------------

    if "CORE_PCE" in result:

        frame = result[
            "CORE_PCE"
        ].copy()

        frame = frame.sort_values(
            "date"
        )

        frame[
            "CORE_PCE_INFLATION"
        ] = (
            frame["CORE_PCE"]
            .pct_change(12)
            * 100
        )

        result[
            "CORE_PCE_INFLATION_DERIVED"
        ] = frame[
            [
                "date",
                "CORE_PCE_INFLATION",
            ]
        ]

    return result


# ============================================================
# MERGE MACRO FRAMES
# ============================================================

def merge_macro_frames(
    frames: dict,
) -> pd.DataFrame:

    merged = None

    for name, frame in frames.items():

        if frame is None:
            continue

        if frame.empty:
            continue

        temp = frame.copy()

        temp["date"] = normalize_datetime_series(
            temp["date"]
        )

        temp = temp.dropna(
            subset=["date"]
        )

        if temp.empty:
            continue

        temp = temp.sort_values(
            "date"
        )

        temp = temp.drop_duplicates(
            subset=["date"],
            keep="last",
        )

        if merged is None:

            merged = temp

        else:

            duplicate_columns = [
                c
                for c in temp.columns
                if c != "date"
                and c in merged.columns
            ]

            temp = temp.drop(
                columns=duplicate_columns,
                errors="ignore",
            )

            if len(
                temp.columns
            ) > 1:

                merged = pd.merge(
                    merged,
                    temp,
                    on="date",
                    how="outer",
                )

                merged["date"] = (
                    normalize_datetime_series(
                        merged["date"]
                    )
                )

    if merged is None:

        return pd.DataFrame()

    merged["date"] = (
        normalize_datetime_series(
            merged["date"]
        )
    )

    merged = merged.sort_values(
        "date"
    )

    merged = merged.drop_duplicates(
        subset=["date"],
        keep="last",
    )

    return merged


# ============================================================
# MACRO CLASSIFICATION
# ============================================================

def classify_macro_regime(
    row: pd.Series,
) -> str:

    hy = row.get(
        "HY_SPREAD",
        np.nan,
    )

    corp = row.get(
        "CORP_OAS",
        np.nan,
    )

    vix = row.get(
        "VIX",
        np.nan,
    )

    nfci = row.get(
        "NFCI",
        np.nan,
    )

    t10y2y = row.get(
        "T10Y2Y",
        np.nan,
    )

    unrate = row.get(
        "UNRATE",
        np.nan,
    )

    claims = row.get(
        "INITIAL_CLAIMS_4W",
        np.nan,
    )

    pce_inflation = row.get(
        "PCE_INFLATION",
        np.nan,
    )

    core_pce_inflation = row.get(
        "CORE_PCE_INFLATION",
        np.nan,
    )

    indpro_yoy = row.get(
        "INDPRO_YOY",
        np.nan,
    )

    retail_yoy = row.get(
        "RETAIL_YOY",
        np.nan,
    )

    us10y = row.get(
        "US10Y",
        np.nan,
    )

    us2y = row.get(
        "US2Y",
        np.nan,
    )

    fedfunds = row.get(
        "FEDFUNDS",
        np.nan,
    )

    # ========================================================
    # F — LIQUIDITY / FINANCIAL SHOCK
    # ========================================================

    financial_stress = False

    if (
        not pd.isna(vix)
        and vix >= 35
    ):

        financial_stress = True

    if (
        not pd.isna(hy)
        and hy >= 6
    ):

        financial_stress = True

    if (
        not pd.isna(corp)
        and corp >= 3.5
    ):

        financial_stress = True

    if (
        not pd.isna(nfci)
        and nfci >= 1.0
    ):

        financial_stress = True

    if financial_stress:

        return (
            "F — Liquidity / Financial Shock"
        )

    # ========================================================
    # E — RECESSION / BEAR RISK
    # ========================================================

    recession_score = 0

    if (
        not pd.isna(unrate)
        and unrate >= 5.0
    ):

        recession_score += 2

    if (
        not pd.isna(claims)
        and claims >= 300000
    ):

        recession_score += 2

    if (
        not pd.isna(indpro_yoy)
        and indpro_yoy < 0
    ):

        recession_score += 1

    if (
        not pd.isna(retail_yoy)
        and retail_yoy < 0
    ):

        recession_score += 1

    if (
        not pd.isna(t10y2y)
        and t10y2y < -0.50
    ):

        recession_score += 1

    if recession_score >= 3:

        return (
            "E — Recession / Bear Risk"
        )

    # ========================================================
    # C / D — INFLATION / RATES SHOCK
    # ========================================================

    inflation_score = 0

    if (
        not pd.isna(pce_inflation)
        and pce_inflation >= 3.0
    ):

        inflation_score += 1

    if (
        not pd.isna(core_pce_inflation)
        and core_pce_inflation >= 3.0
    ):

        inflation_score += 1

    if (
        not pd.isna(us10y)
        and us10y >= 4.5
    ):

        inflation_score += 1

    if (
        not pd.isna(us2y)
        and us2y >= 4.5
    ):

        inflation_score += 1

    if (
        not pd.isna(fedfunds)
        and fedfunds >= 4.5
    ):

        inflation_score += 1

    growth_weak = False

    if (
        not pd.isna(indpro_yoy)
        and indpro_yoy < 0
    ):

        growth_weak = True

    if (
        not pd.isna(retail_yoy)
        and retail_yoy < 0
    ):

        growth_weak = True

    if (
        not pd.isna(claims)
        and claims >= 260000
    ):

        growth_weak = True

    if inflation_score >= 3:

        if growth_weak:

            return (
                "D — Growth + Inflation / Mixed Stress"
            )

        return (
            "C — Inflation / Rates Shock"
        )

    # ========================================================
    # B — GROWTH SCARE / HEALTHY CORRECTION
    # ========================================================

    growth_weak_count = 0

    if (
        not pd.isna(indpro_yoy)
        and indpro_yoy < 0
    ):

        growth_weak_count += 1

    if (
        not pd.isna(retail_yoy)
        and retail_yoy < 0
    ):

        growth_weak_count += 1

    if (
        not pd.isna(claims)
        and claims >= 260000
    ):

        growth_weak_count += 1

    inflation_not_hot = True

    if (
        not pd.isna(pce_inflation)
        and pce_inflation >= 3.5
    ):

        inflation_not_hot = False

    if (
        not pd.isna(core_pce_inflation)
        and core_pce_inflation >= 3.5
    ):

        inflation_not_hot = False

    if (
        growth_weak_count >= 2
        and inflation_not_hot
    ):

        return (
            "B — Growth Scare / Healthy Correction"
        )

    # ========================================================
    # A — HEALTHY / TECHNICAL PULLBACK
    # ========================================================

    return (
        "A — Healthy / Technical Pullback"
    )


# ============================================================
# PREPARE MACRO DATA
# ============================================================

def prepare_macro_data(
    market: pd.DataFrame,
) -> pd.DataFrame:

    print()
    print(
        "=" * 60
    )

    print(
        "LOADING MACRO DATA"
    )

    print(
        "=" * 60
    )

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    macro_frames = load_macro_resilient()

    if not macro_frames:

        print(
            "No macro series available."
        )

        return pd.DataFrame()

    # --------------------------------------------------------
    # PRINT STATUS
    # --------------------------------------------------------

    print()
    print(
        "MACRO DATA STATUS"
    )

    print(
        "-" * 60
    )

    for name in FRED_PUBLIC_SERIES:

        if name in macro_frames:

            frame = macro_frames[
                name
            ]

            print(
                f"{name:<22}: "
                f"{len(frame):>5} observations"
            )

        else:

            print(
                f"{name:<22}: UNAVAILABLE"
            )

    # --------------------------------------------------------
    # DERIVED SERIES
    # --------------------------------------------------------

    macro_frames = add_derived_series(
        macro_frames
    )

    # --------------------------------------------------------
    # MERGE
    # --------------------------------------------------------

    macro = merge_macro_frames(
        macro_frames
    )

    if macro.empty:

        print(
            "Macro merge produced no data."
        )

        return pd.DataFrame()

    # --------------------------------------------------------
    # MARKET DATES
    # --------------------------------------------------------

    market_reset = (
        market
        .reset_index()
    )

    first_column = (
        market_reset.columns[0]
    )

    market_reset = (
        market_reset
        .rename(
            columns={
                first_column:
                    "date"
            }
        )
    )

    # IMPORTANT:
    # Force exact same datetime dtype on both sides.
    market_reset["date"] = (
        normalize_datetime_series(
            market_reset["date"]
        )
    )

    macro["date"] = (
        normalize_datetime_series(
            macro["date"]
        )
    )

    market_reset = (
        market_reset
        .dropna(
            subset=["date"]
        )
        .sort_values("date")
    )

    macro = (
        macro
        .dropna(
            subset=["date"]
        )
        .sort_values("date")
    )

    # Remove duplicates before merge_asof.
    market_reset = (
        market_reset
        .drop_duplicates(
            subset=["date"],
            keep="last",
        )
    )

    macro = (
        macro
        .drop_duplicates(
            subset=["date"],
            keep="last",
        )
    )

    # Final dtype verification.
    market_reset["date"] = (
        market_reset["date"]
        .astype("datetime64[ns]")
    )

    macro["date"] = (
        macro["date"]
        .astype("datetime64[ns]")
    )

    # --------------------------------------------------------
    # BACKWARD ALIGNMENT
    # --------------------------------------------------------
    #
    # For each market day, use the latest macro observation
    # whose observation date is <= that market day.
    #
    # This prevents future observation dates.
    #
    # It does NOT reconstruct historical release timestamps.
    # --------------------------------------------------------

    merged = pd.merge_asof(
        market_reset,
        macro,
        on="date",
        direction="backward",
    )

    # --------------------------------------------------------
    # CLASSIFY
    # --------------------------------------------------------

    merged["macro_regime"] = (
        merged.apply(
            classify_macro_regime,
            axis=1,
        )
    )

    merged = merged.set_index(
        "date"
    )

    return merged


# ============================================================
# ATTACH MACRO TO TRADES
# ============================================================

def attach_macro_to_trades(
    trades: pd.DataFrame,
    macro_market: pd.DataFrame,
) -> pd.DataFrame:

    if trades.empty:

        return trades

    result = trades.copy()

    result["signal_date"] = (
        normalize_datetime_series(
            result["signal_date"]
        )
    )

    macro_columns = [

        "macro_regime",

        "US10Y",
        "US2Y",
        "T10Y2Y",

        "VIX",

        "UNRATE",

        "INITIAL_CLAIMS_4W",

        "HY_SPREAD",
        "CORP_OAS",
        "NFCI",

        "INDPRO",
        "INDPRO_YOY",

        "RETAIL",
        "RETAIL_YOY",

        "PCE",
        "PCEPI",
        "PCE_INFLATION",

        "CORE_PCE",
        "CORE_PCE_INFLATION",

        "FEDFUNDS",
    ]

    available = [
        c
        for c in macro_columns
        if c in macro_market.columns
    ]

    if not available:

        return result

    macro_for_merge = (
        macro_market[
            available
        ]
        .reset_index()
    )

    first_column = (
        macro_for_merge.columns[0]
    )

    macro_for_merge = (
        macro_for_merge
        .rename(
            columns={
                first_column:
                    "signal_date"
            }
        )
    )

    macro_for_merge["signal_date"] = (
        normalize_datetime_series(
            macro_for_merge[
                "signal_date"
            ]
        )
    )

    result["signal_date"] = (
        normalize_datetime_series(
            result["signal_date"]
        )
    )

    result = result.dropna(
        subset=["signal_date"]
    )

    macro_for_merge = (
        macro_for_merge
        .dropna(
            subset=["signal_date"]
        )
    )

    result = result.sort_values(
        "signal_date"
    )

    macro_for_merge = (
        macro_for_merge
        .sort_values(
            "signal_date"
        )
    )

    # Remove duplicate dates.
    result = result.drop_duplicates(
        subset=["signal_date"],
        keep="last",
    )

    macro_for_merge = (
        macro_for_merge
        .drop_duplicates(
            subset=["signal_date"],
            keep="last",
        )
    )

    # Force identical datetime precision.
    result["signal_date"] = (
        result["signal_date"]
        .astype("datetime64[ns]")
    )

    macro_for_merge["signal_date"] = (
        macro_for_merge["signal_date"]
        .astype("datetime64[ns]")
    )

    result = pd.merge_asof(
        result,
        macro_for_merge,
        on="signal_date",
        direction="backward",
    )

    return result


# ============================================================
# SUMMARY
# ============================================================

def calculate_summary(
    trades: pd.DataFrame,
) -> dict:

    if trades.empty:

        return {
            "total_signals": 0,
            "valid_setups": 0,
            "resolved_trades": 0,
            "wins": 0,
            "losses": 0,
            "ambiguous": 0,
            "open": 0,
            "invalid_sl": 0,
            "win_rate_pct": np.nan,
            "average_R": np.nan,
            "expectancy_R": np.nan,
            "total_R": np.nan,
            "profit_factor": np.nan,
        }

    total = len(trades)

    valid = int(
        (
            trades["status"]
            == "VALID"
        ).sum()
    )

    wins = int(
        (
            trades["result"]
            == "WIN"
        ).sum()
    )

    losses = int(
        (
            trades["result"]
            == "LOSS"
        ).sum()
    )

    ambiguous = int(
        (
            trades["result"]
            == "AMBIGUOUS"
        ).sum()
    )

    open_trades = int(
        (
            trades["result"]
            == "OPEN"
        ).sum()
    )

    invalid = int(
        (
            trades["status"]
            == "INVALID_SL"
        ).sum()
    )

    resolved = (
        wins + losses
    )

    if resolved > 0:

        win_rate = (
            wins / resolved
        ) * 100

    else:

        win_rate = np.nan

    resolved_r = (
        trades.loc[
            trades["result"].isin(
                [
                    "WIN",
                    "LOSS",
                ]
            ),
            "R",
        ]
        .dropna()
    )

    if len(resolved_r) > 0:

        average_r = (
            resolved_r.mean()
        )

        total_r = (
            resolved_r.sum()
        )

        gross_profit = (
            resolved_r[
                resolved_r > 0
            ].sum()
        )

        gross_loss = abs(
            resolved_r[
                resolved_r < 0
            ].sum()
        )

        if gross_loss > 0:

            profit_factor = (
                gross_profit
                / gross_loss
            )

        else:

            profit_factor = np.inf

    else:

        average_r = np.nan
        total_r = np.nan
        profit_factor = np.nan

    return {
        "total_signals": total,
        "valid_setups": valid,
        "resolved_trades": resolved,
        "wins": wins,
        "losses": losses,
        "ambiguous": ambiguous,
        "open": open_trades,
        "invalid_sl": invalid,
        "win_rate_pct": win_rate,
        "average_R": average_r,
        "expectancy_R": average_r,
        "total_R": total_r,
        "profit_factor": profit_factor,
    }


# ============================================================
# MACRO SUMMARY
# ============================================================

def grouped_macro_summary(
    trades: pd.DataFrame,
) -> pd.DataFrame:

    if (
        trades.empty
        or "macro_regime"
        not in trades.columns
    ):

        return pd.DataFrame()

    rows = []

    regime_order = [

        "A — Healthy / Technical Pullback",

        "B — Growth Scare / Healthy Correction",

        "C — Inflation / Rates Shock",

        "D — Growth + Inflation / Mixed Stress",

        "E — Recession / Bear Risk",

        "F — Liquidity / Financial Shock",
    ]

    for regime in regime_order:

        subset = trades[
            trades["macro_regime"]
            == regime
        ]

        if subset.empty:

            continue

        summary = calculate_summary(
            subset
        )

        rows.append(
            {
                "macro_regime": regime,

                "signals":
                    summary[
                        "total_signals"
                    ],

                "valid":
                    summary[
                        "valid_setups"
                    ],

                "resolved":
                    summary[
                        "resolved_trades"
                    ],

                "wins":
                    summary[
                        "wins"
                    ],

                "losses":
                    summary[
                        "losses"
                    ],

                "ambiguous":
                    summary[
                        "ambiguous"
                    ],

                "open":
                    summary[
                        "open"
                    ],

                "win_rate_pct":
                    summary[
                        "win_rate_pct"
                    ],

                "average_R":
                    summary[
                        "average_R"
                    ],

                "total_R":
                    summary[
                        "total_R"
                    ],

                "profit_factor":
                    summary[
                        "profit_factor"
                    ],
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# YEARLY SUMMARY
# ============================================================

def yearly_macro_summary(
    trades: pd.DataFrame,
) -> pd.DataFrame:

    if trades.empty:

        return pd.DataFrame()

    data = trades.copy()

    data["year"] = (
        pd.to_datetime(
            data["signal_date"]
        ).dt.year
    )

    rows = []

    for year, subset in (
        data.groupby("year")
    ):

        summary = calculate_summary(
            subset
        )

        rows.append(
            {
                "year": year,
                **summary,
            }
        )

    return (
        pd.DataFrame(rows)
        .sort_values("year")
    )


# ============================================================
# MACRO DATA QUALITY
# ============================================================

def macro_data_quality(
    macro_market: pd.DataFrame,
) -> pd.DataFrame:

    if macro_market.empty:

        return pd.DataFrame()

    rows = []

    columns = [
        "US10Y",
        "US2Y",
        "T10Y2Y",
        "VIX",
        "UNRATE",
        "INITIAL_CLAIMS_4W",
        "HY_SPREAD",
        "CORP_OAS",
        "NFCI",
        "INDPRO",
        "INDPRO_YOY",
        "RETAIL",
        "RETAIL_YOY",
        "PCE_INFLATION",
        "CORE_PCE_INFLATION",
        "FEDFUNDS",
    ]

    for column in columns:

        if column not in macro_market.columns:

            continue

        available = (
            macro_market[column]
            .notna()
            .sum()
        )

        total = len(
            macro_market
        )

        coverage = (
            available / total * 100
            if total > 0
            else np.nan
        )

        rows.append(
            {
                "series": column,
                "available_rows": int(
                    available
                ),
                "total_market_rows": int(
                    total
                ),
                "coverage_pct": coverage,
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "US500 EMA19 + MACRO BACKTEST"
    )

    print(
        "=" * 60
    )

    print(
        f"Ticker: {TICKER}"
    )

    print(
        f"Start: {START_DATE}"
    )

    print(
        f"EMA: {EMA_FAST}"
    )

    print(
        f"Trend EMA: {EMA_TREND}"
    )

    print(
        f"RR: 1:{RR}"
    )

    # ========================================================
    # MARKET
    # ========================================================

    print()
    print(
        "Loading market data..."
    )

    market_raw = (
        get_historical_market_data(
            ticker=TICKER,
            start_date=START_DATE,
        )
    )

    if market_raw is None:

        raise RuntimeError(
            "Market data returned None."
        )

    if market_raw.empty:

        raise RuntimeError(
            "Market data is empty."
        )

    market = prepare_market_data(
        market_raw
    )

    print(
        "Market data: "
        f"{market.index.min().date()} "
        "→ "
        f"{market.index.max().date()}"
    )

    # ========================================================
    # SIGNALS
    # ========================================================

    signals = detect_ema19_pullbacks(
        market
    )

    print(
        f"EMA19 Pullback signals: "
        f"{len(signals)}"
    )

    # ========================================================
    # BACKTEST
    # ========================================================

    trades = build_ema19_backtest(
        market,
        signals,
    )

    print(
        f"Backtest events: "
        f"{len(trades)}"
    )

    # ========================================================
    # MACRO
    # ========================================================

    macro_market = prepare_macro_data(
        market
    )

    if macro_market.empty:

        print()
        print(
            "WARNING: Macro data unavailable."
        )

        trades[
            "macro_regime"
        ] = "DATA UNAVAILABLE"

    else:

        trades = attach_macro_to_trades(
            trades,
            macro_market,
        )

    # ========================================================
    # OVERALL
    # ========================================================

    summary = calculate_summary(
        trades
    )

    print()
    print(
        "OVERALL"
    )

    print(
        "-" * 60
    )

    print(
        f"Total Signals       : "
        f"{summary['total_signals']}"
    )

    print(
        f"Valid Setups        : "
        f"{summary['valid_setups']}"
    )

    print(
        f"Resolved Trades     : "
        f"{summary['resolved_trades']}"
    )

    print(
        f"Wins                : "
        f"{summary['wins']}"
    )

    print(
        f"Losses              : "
        f"{summary['losses']}"
    )

    print(
        f"Ambiguous           : "
        f"{summary['ambiguous']}"
    )

    print(
        f"Open                : "
        f"{summary['open']}"
    )

    print(
        f"Invalid Sl          : "
        f"{summary['invalid_sl']}"
    )

    if pd.isna(
        summary["win_rate_pct"]
    ):

        print(
            "Win Rate Pct        : N/A"
        )

    else:

        print(
            f"Win Rate Pct        : "
            f"{summary['win_rate_pct']:.3f}"
        )

    if pd.isna(
        summary["average_R"]
    ):

        print(
            "Average R           : N/A"
        )

    else:

        print(
            f"Average R           : "
            f"{summary['average_R']:.3f}"
        )

    if pd.isna(
        summary["expectancy_R"]
    ):

        print(
            "Expectancy R        : N/A"
        )

    else:

        print(
            f"Expectancy R        : "
            f"{summary['expectancy_R']:.3f}"
        )

    if pd.isna(
        summary["total_R"]
    ):

        print(
            "Total R             : N/A"
        )

    else:

        print(
            f"Total R             : "
            f"{summary['total_R']:.1f}"
        )

    if pd.isna(
        summary["profit_factor"]
    ):

        print(
            "Profit Factor       : N/A"
        )

    elif np.isinf(
        summary["profit_factor"]
    ):

        print(
            "Profit Factor       : INF"
        )

    else:

        print(
            f"Profit Factor       : "
            f"{summary['profit_factor']:.3f}"
        )

    # ========================================================
    # MACRO RESULTS
    # ========================================================

    macro_summary = (
        grouped_macro_summary(
            trades
        )
    )

    print()
    print(
        "RESULTS BY MACRO REGIME"
    )

    print(
        "-" * 60
    )

    if macro_summary.empty:

        print(
            "No macro regime results available."
        )

    else:

        print(
            macro_summary.to_string(
                index=False,
                float_format=lambda x:
                    f"{x:.3f}",
            )
        )

    # ========================================================
    # YEARLY
    # ========================================================

    yearly = yearly_macro_summary(
        trades
    )

    print()
    print(
        "YEARLY RESULTS"
    )

    print(
        "-" * 60
    )

    if yearly.empty:

        print(
            "No yearly results."
        )

    else:

        yearly_columns = [
            "year",
            "total_signals",
            "resolved_trades",
            "wins",
            "losses",
            "ambiguous",
            "win_rate_pct",
            "average_R",
            "total_R",
        ]

        print(
            yearly[
                yearly_columns
            ].to_string(
                index=False,
                float_format=lambda x:
                    f"{x:.3f}",
            )
        )

    # ========================================================
    # DATA QUALITY
    # ========================================================

    quality = (
        macro_data_quality(
            macro_market
        )
        if not macro_market.empty
        else pd.DataFrame()
    )

    print()
    print(
        "MACRO DATA QUALITY"
    )

    print(
        "-" * 60
    )

    if quality.empty:

        print(
            "No macro quality information."
        )

    else:

        print(
            quality.to_string(
                index=False,
                float_format=lambda x:
                    f"{x:.2f}",
            )
        )

    # ========================================================
    # SAVE FILES
    # ========================================================

    trades.to_csv(
        "backtestEMA19Macro_trades.csv",
        index=False,
    )

    macro_summary.to_csv(
        "backtestEMA19Macro_regimes.csv",
        index=False,
    )

    yearly.to_csv(
        "backtestEMA19Macro_yearly.csv",
        index=False,
    )

    pd.DataFrame(
        [summary]
    ).to_csv(
        "backtestEMA19Macro_summary.csv",
        index=False,
    )

    if not macro_market.empty:

        macro_market.to_csv(
            "backtestEMA19Macro_macro_data.csv"
        )

    if not quality.empty:

        quality.to_csv(
            "backtestEMA19Macro_data_quality.csv",
            index=False,
        )

    if not signals.empty:

        signals.to_csv(
            "backtestEMA19Macro_signals.csv",
            index=False,
        )

    # ========================================================
    # FILE LIST
    # ========================================================

    print()
    print(
        "FILES CREATED"
    )

    print(
        "-" * 60
    )

    print(
        "backtestEMA19Macro_trades.csv"
    )

    print(
        "backtestEMA19Macro_regimes.csv"
    )

    print(
        "backtestEMA19Macro_yearly.csv"
    )

    print(
        "backtestEMA19Macro_summary.csv"
    )

    if not macro_market.empty:

        print(
            "backtestEMA19Macro_macro_data.csv"
        )

    if not quality.empty:

        print(
            "backtestEMA19Macro_data_quality.csv"
        )

    if not signals.empty:

        print(
            "backtestEMA19Macro_signals.csv"
        )

    print()
    print(
        "EMA19 + MACRO BACKTEST COMPLETE"
    )


if __name__ == "__main__":
    main()
