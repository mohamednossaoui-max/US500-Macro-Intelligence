# ============================================================
# US500 MACRO BACKTEST V3.1 - FULL DECISION ENGINE CALIBRATION
# FROZEN EMA19 BASELINE + MACRO CONTEXT + TECHNICAL CONFIRMATION
# ============================================================

import os
import warnings

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore")

TICKER = "^GSPC"
START_DATE = "2019-01-01"

# ============================================================
# FROZEN MARKET DATA CUTOFF
# ============================================================
# The authoritative V3.8/V3.9/V3.10 baseline was validated through
# 2026-09-22.
#
# Yahoo Finance is a moving data source. When a new trading session
# becomes available, the baseline must NOT change automatically.
#
# The previously validated authoritative baseline is:
#   119 signals
#   117 valid
#   2 invalid SL
#   109 resolved
#   36 wins
#   73 losses
#   3 ambiguous
#   5 open
#   +71R
#   PF ~= 1.9726027397
#
# The recent 120-signal result was caused by one additional market
# session being included. That additional signal was OPEN and did
# not change any resolved result or total R.
#
# Therefore we freeze the market horizon instead of changing the
# authoritative baseline to 120 signals.
BASELINE_AS_OF_DATE = pd.Timestamp("2026-09-22")

RR = 4.0
EMA19 = 19
EMA200 = 200
ATR14 = 14
LOW_LOOKBACK = 5

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

FRED_SERIES = {
    "US10Y": "DGS10",
    "US2Y": "DGS2",
    "T10Y2Y": "T10Y2Y",
    "VIX": "VIXCLS",
    "DXY": "DTWEXBGS",
    "UNRATE": "UNRATE",
    "INITIAL_CLAIMS_4W": "IC4WSA",
    "HY_SPREAD": "BAMLH0A0HYM2",
    "CORP_OAS": "BAMLC0A0CM",
    "NFCI": "NFCI",
    "INDPRO": "INDPRO",
    "RETAIL": "RSAFS",
    "PCE": "PCE",
    "CORE_PCE": "PCEPILFE",
    "FEDFUNDS": "FEDFUNDS",
}

MONTHLY_SERIES = {
    "UNRATE",
    "INDPRO",
    "RETAIL",
    "PCE",
    "CORE_PCE",
    "FEDFUNDS",
}

DAILY_MOMENTUM_LOOKBACK = 20
MEDIUM_DAILY_LOOKBACK = 60


# ============================================================
# MARKET / FROZEN BASELINE
# ============================================================

def load_market():
    df = yf.download(
        TICKER,
        start=START_DATE,
        auto_adjust=False,
        progress=False,
    )

    if df.empty:
        raise RuntimeError(
            "Yahoo Finance returned no market data."
        )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[
        ["Open", "High", "Low", "Close"]
    ].copy()

    df.index = pd.to_datetime(
        df.index
    ).tz_localize(None)

    df = (
        df
        .sort_index()
        .dropna()
    )

    # ========================================================
    # CRITICAL FROZEN-DATA PROTECTION
    # ========================================================
    # Yahoo Finance keeps moving forward as new sessions appear.
    # The frozen baseline must be calculated only from the
    # historical horizon used to establish the authoritative
    # V3.8/V3.9/V3.10 results.
    #
    # This cutoff is applied BEFORE EMA/ATR calculations.
    # Therefore the new trading session cannot alter:
    #   - EMA19
    #   - EMA200
    #   - ATR14
    #   - baseline signals
    #   - stops
    #   - targets
    #   - results
    #
    # This is a reproducibility guard, not a trading rule.
    df = df.loc[
        df.index <= BASELINE_AS_OF_DATE
    ].copy()

    if df.empty:
        raise RuntimeError(
            "No market data exists at or before "
            f"{BASELINE_AS_OF_DATE.date()}."
        )

    for c in [
        "Open",
        "High",
        "Low",
        "Close",
    ]:
        df[c] = pd.to_numeric(
            df[c],
            errors="coerce",
        )

    df = df.dropna()

    if df.empty:
        raise RuntimeError(
            "No valid market rows remain after "
            "the frozen baseline cutoff."
        )

    # ========================================================
    # FROZEN EMA CALCULATIONS
    # ========================================================

    df["EMA19"] = (
        df["Close"]
        .ewm(
            span=EMA19,
            adjust=False,
            min_periods=EMA19,
        )
        .mean()
    )

    df["EMA200"] = (
        df["Close"]
        .ewm(
            span=EMA200,
            adjust=False,
            min_periods=EMA200,
        )
        .mean()
    )

    # ========================================================
    # V3.1 TECHNICAL CONFIRMATION
    # ========================================================
    # These fields classify existing signals.
    # They do NOT create or remove baseline entries.

    df["SMA20"] = (
        df["Close"]
        .rolling(
            20,
            min_periods=20,
        )
        .mean()
    )

    df["SMA50"] = (
        df["Close"]
        .rolling(
            50,
            min_periods=50,
        )
        .mean()
    )

    # ========================================================
    # WILDER RSI(14)
    # ========================================================

    delta = df["Close"].diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = (
        gain
        .ewm(
            alpha=1 / 14,
            adjust=False,
            min_periods=14,
        )
        .mean()
    )

    avg_loss = (
        loss
        .ewm(
            alpha=1 / 14,
            adjust=False,
            min_periods=14,
        )
        .mean()
    )

    rs = (
        avg_gain
        / avg_loss.replace(
            0,
            np.nan,
        )
    )

    df["RSI14"] = (
        100
        - (
            100
            / (1 + rs)
        )
    )

    df.loc[
        (avg_loss == 0)
        & (avg_gain > 0),
        "RSI14",
    ] = 100.0

    df.loc[
        (avg_loss == 0)
        & (avg_gain == 0),
        "RSI14",
    ] = 50.0

    # ========================================================
    # TRUE RANGE / WILDER ATR
    # ========================================================

    previous_close = df["Close"].shift(1)

    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (
                df["High"]
                - previous_close
            ).abs(),
            (
                df["Low"]
                - previous_close
            ).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["TR"] = tr

    df["ATR14_WILDER"] = (
        tr
        .ewm(
            alpha=1 / ATR14,
            adjust=False,
            min_periods=ATR14,
        )
        .mean()
    )

    return df


# ============================================================
# FROZEN BASELINE SIGNAL CONDITION
# ============================================================

def baseline_condition(df, i):
    r = df.iloc[i]

    return bool(
        pd.notna(r["EMA19"])
        and pd.notna(r["EMA200"])
        and r["Close"] > r["EMA200"]
        and r["EMA19"] > r["EMA200"]
        and r["Low"] <= r["EMA19"]
        and r["Close"] > r["EMA19"]
    )


def build_baseline_signals(df):
    raw = [
        i
        for i in range(len(df))
        if baseline_condition(df, i)
    ]

    return [
        i
        for p, i in enumerate(raw)
        if p == 0
        or raw[p] - raw[p - 1] > 1
    ]


# ============================================================
# FROZEN STOP
# ============================================================

def baseline_stop(df, i):
    if i < LOW_LOOKBACK + 1:
        return np.nan

    lows = df.iloc[
        i - LOW_LOOKBACK:i
    ]["Low"]

    atr = df.iloc[
        i - 1
    ]["ATR14_WILDER"]

    if pd.isna(atr):
        return np.nan

    return float(
        lows.min()
        - 0.5 * atr
    )


# ============================================================
# FROZEN TRADE RESOLUTION
# ============================================================

def resolve_trade(
    df,
    entry_i,
    entry,
    stop,
):
    if (
        not np.isfinite(stop)
        or stop >= entry
    ):
        return (
            "INVALID_SL",
            np.nan,
            None,
        )

    risk = entry - stop
    target = (
        entry
        + RR * risk
    )

    for j in range(
        entry_i + 1,
        len(df),
    ):
        hi = float(
            df.iloc[j]["High"]
        )

        lo = float(
            df.iloc[j]["Low"]
        )

        tp = hi >= target
        sl = lo <= stop

        if tp and sl:
            return (
                "AMBIGUOUS",
                np.nan,
                j,
            )

        if tp:
            return (
                "WIN",
                RR,
                j,
            )

        if sl:
            return (
                "LOSS",
                -1.0,
                j,
            )

    return (
        "OPEN",
        np.nan,
        None,
    )


# ============================================================
# FROZEN BASELINE TRADES
# ============================================================

def build_baseline_trades(df):
    rows = []

    for i in build_baseline_signals(df):

        entry = float(
            df.iloc[i]["Close"]
        )

        stop = baseline_stop(
            df,
            i,
        )

        result, r_mult, exit_i = (
            resolve_trade(
                df,
                i,
                entry,
                stop,
            )
        )

        rows.append(
            {
                "signal_date":
                    df.index[i],

                "year":
                    int(
                        df.index[i].year
                    ),

                "signal_index":
                    i,

                "entry":
                    entry,

                "stop":
                    stop,

                "risk_points":
                    (
                        entry - stop
                        if np.isfinite(stop)
                        else np.nan
                    ),

                "target":
                    (
                        entry
                        + RR * (
                            entry - stop
                        )
                        if (
                            np.isfinite(stop)
                            and stop < entry
                        )
                        else np.nan
                    ),

                "result":
                    result,

                "R":
                    r_mult,

                "exit_date":
                    (
                        df.index[exit_i]
                        if exit_i is not None
                        else pd.NaT
                    ),
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# BASELINE SUMMARY
# ============================================================

def summarize(g):
    wins = int(
        (
            g["result"]
            == "WIN"
        ).sum()
    )

    losses = int(
        (
            g["result"]
            == "LOSS"
        ).sum()
    )

    ambiguous = int(
        (
            g["result"]
            == "AMBIGUOUS"
        ).sum()
    )

    open_trades = int(
        (
            g["result"]
            == "OPEN"
        ).sum()
    )

    invalid = int(
        (
            g["result"]
            == "INVALID_SL"
        ).sum()
    )

    resolved = (
        wins
        + losses
    )

    r = g["R"].dropna()

    gp = float(
        g.loc[
            g["R"] > 0,
            "R",
        ].sum()
    )

    gl = abs(
        float(
            g.loc[
                g["R"] < 0,
                "R",
            ].sum()
        )
    )

    return {
        "signals":
            len(g),

        "valid":
            len(g) - invalid,

        "invalid_sl":
            invalid,

        "resolved":
            resolved,

        "wins":
            wins,

        "losses":
            losses,

        "ambiguous":
            ambiguous,

        "open":
            open_trades,

        "win_rate":
            (
                100 * wins / resolved
                if resolved
                else np.nan
            ),

        "avg_R":
            (
                float(r.mean())
                if len(r)
                else np.nan
            ),

        "total_R":
            (
                float(r.sum())
                if len(r)
                else 0.0
            ),

        "profit_factor":
            (
                gp / gl
                if gl
                else np.nan
            ),
    }


# ============================================================
# FROZEN BASELINE CHECK
# ============================================================

def print_baseline_check(trades):

    s = summarize(trades)

    expected = {
        "signals": 119,
        "valid": 117,
        "invalid_sl": 2,
        "resolved": 109,
        "wins": 36,
        "losses": 73,
        "ambiguous": 3,
        "open": 5,
        "total_R": 71.0,
    }

    print(
        "\n"
        + "=" * 72
    )

    print(
        "FROZEN BASELINE CHECK"
    )

    print(
        "=" * 72
    )

    print(
        f"Market cutoff      : "
        f"{BASELINE_AS_OF_DATE.date()}"
    )

    for k in [
        "signals",
        "valid",
        "invalid_sl",
        "resolved",
        "wins",
        "losses",
        "ambiguous",
        "open",
        "win_rate",
        "avg_R",
        "total_R",
        "profit_factor",
    ]:
        print(
            f"{k:18s}: {s[k]}"
        )

    ok = (
        all(
            s[k] == v
            for k, v in expected.items()
        )
        and abs(
            s["profit_factor"]
            - 1.9726027397260273
        ) < 1e-9
    )

    print(
        "BASELINE STATUS:",
        "PASS" if ok else "FAIL",
    )

    if not ok:
        print(
            "Expected:",
            expected,
            "PF~=1.973",
        )

    return ok
