"""
backtestEMA19_baseline.py

EMA19 BASELINE VALIDATION

Purpose
-------
Reconstruct the original EMA19 pullback backtest independently from the
Macro layer. This script is intentionally NOT connected to Macro Regimes,
Early Warning, Fed Intelligence, or Technical Confirmation.

Reference rules reconstructed from the previous baseline:
    - Market: ^GSPC
    - Daily timeframe
    - Start: 2019-01-01
    - Fast EMA: 19
    - Trend EMA: 200
    - Pullback: Low <= EMA19
    - Trend filter: Close > EMA200 and EMA19 > EMA200
    - Entry: signal-day Close
    - Stop: lowest Low of the previous 5 COMPLETED candles
             minus 0.5 * ATR(14) from the previous completed candle
    - RR: 1:4
    - Same-day TP and SL: AMBIGUOUS
    - No Macro filtering

IMPORTANT
---------
The exact historical script is no longer available. Therefore this is a
RECONSTRUCTION, not a claim that it is byte-for-byte identical to the old
script.

The script prints detailed diagnostics so we can compare the result with
the old reference:
    119 signals
    117 valid
    109 resolved
    36 wins
    73 losses
    3 ambiguous
    5 open
    2 invalid SL
    +71R
    PF ~1.97
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf


# ============================================================
# CONFIG
# ============================================================

TICKER = "^GSPC"
START_DATE = "2019-01-01"

EMA_FAST = 19
EMA_TREND = 200

ATR_PERIOD = 14
STOP_LOOKBACK = 5
ATR_MULTIPLIER = 0.5

RR = 4.0

OUTPUT_TRADES = "backtestEMA19_baseline_trades.csv"
OUTPUT_YEARLY = "backtestEMA19_baseline_yearly.csv"
OUTPUT_SUMMARY = "backtestEMA19_baseline_summary.csv"
OUTPUT_SIGNALS = "backtestEMA19_baseline_signals.csv"


# ============================================================
# DATA
# ============================================================

def get_market_data():
    print("=" * 60)
    print("LOADING MARKET DATA")
    print("=" * 60)

    df = yf.download(
        TICKER,
        start=START_DATE,
        interval="1d",
        auto_adjust=False,
        progress=False,
    )

    if df is None or df.empty:
        raise RuntimeError("No market data returned by Yahoo Finance.")

    # yfinance can return MultiIndex columns.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required = ["Open", "High", "Low", "Close"]

    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(f"Missing market columns: {missing}")

    df = df[required].copy()

    df.index = pd.to_datetime(df.index, errors="coerce")
    df = df[~df.index.isna()]
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]

    df = df.reset_index()
    df = df.rename(columns={"Date": "date"})

    df["date"] = pd.to_datetime(
        df["date"], errors="coerce"
    ).astype("datetime64[ns]")

    for col in required:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=required).reset_index(drop=True)

    print(
        f"Market data: "
        f"{df['date'].min().date()} -> "
        f"{df['date'].max().date()}"
    )
    print(f"Rows: {len(df)}")

    return df


# ============================================================
# INDICATORS
# ============================================================

def calculate_atr(df, period=14):
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    previous_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - previous_close).abs()
    tr3 = (low - previous_close).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    # Wilder-style ATR via exponential smoothing.
    atr = true_range.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    return atr


def prepare_market(df):
    df = df.copy()

    df["EMA19"] = df["Close"].ewm(
        span=EMA_FAST,
        adjust=False
    ).mean()

    df["EMA200"] = df["Close"].ewm(
        span=EMA_TREND,
        adjust=False
    ).mean()

    df["ATR14"] = calculate_atr(
        df,
        ATR_PERIOD
    )

    return df


# ============================================================
# SIGNAL ENGINE
# ============================================================

def detect_signals(df):
    """
    Reconstructed baseline signal engine.

    IMPORTANT:
    We do NOT add Macro, Early Warning, or Technical Confirmation here.

    A signal is generated whenever:
        Close > EMA200
        EMA19 > EMA200
        Low <= EMA19

    Duplicate avoidance:
        Consecutive qualifying candles are treated as separate signals
        only when the previous signal has already been resolved.

    This is kept deliberately explicit so that the diagnostics show us
    whether the reconstructed engine matches the historical reference.
    """

    signals = []

    i = max(
        EMA_TREND,
        ATR_PERIOD,
        STOP_LOOKBACK
    ) + 1

    while i < len(df):

        row = df.iloc[i]

        if not np.isfinite(row["EMA19"]):
            i += 1
            continue

        if not np.isfinite(row["EMA200"]):
            i += 1
            continue

        if not np.isfinite(row["ATR14"]):
            i += 1
            continue

        # ----------------------------------------------------
        # EMA19 pullback
        # ----------------------------------------------------
        signal = (
            row["Close"] > row["EMA200"]
            and row["EMA19"] > row["EMA200"]
            and row["Low"] <= row["EMA19"]
        )

        if not signal:
            i += 1
            continue

        entry = float(row["Close"])

        # Previous five COMPLETED candles.
        previous = df.iloc[
            i - STOP_LOOKBACK:i
        ]

        previous_low = float(
            previous["Low"].min()
        )

        previous_atr = float(
            df.iloc[i - 1]["ATR14"]
        )

        stop = (
            previous_low
            - ATR_MULTIPLIER * previous_atr
        )

        valid_sl = (
            np.isfinite(stop)
            and stop < entry
        )

        record = {
            "signal_index": i,
            "signal_date": row["date"],
            "entry": entry,
            "stop": stop,
            "valid_sl": valid_sl,
        }

        if valid_sl:
            risk = entry - stop
            target = entry + RR * risk

            record["risk"] = risk
            record["target"] = target
        else:
            record["risk"] = np.nan
            record["target"] = np.nan

        signals.append(record)

        # ----------------------------------------------------
        # One trade at a time.
        #
        # This is the key reconstructed baseline behavior.
        # Search forward until this trade resolves.
        # ----------------------------------------------------
        if valid_sl:

            target = record["target"]
            stop = record["stop"]

            resolved_index = None

            for j in range(i + 1, len(df)):

                future = df.iloc[j]

                hit_tp = (
                    future["High"] >= target
                )

                hit_sl = (
                    future["Low"] <= stop
                )

                if hit_tp or hit_sl:
                    resolved_index = j
                    break

            if resolved_index is not None:
                # Next signal can only occur after exit candle.
                i = resolved_index + 1
            else:
                # Open through end of dataset.
                break

        else:
            i += 1

    out = pd.DataFrame(signals)

    print(
        f"\nReconstructed EMA19 signals: "
        f"{len(out)}"
    )

    return out


# ============================================================
# TRADE EVALUATION
# ============================================================

def evaluate_trades(df, signals):
    trades = []

    if signals.empty:
        return pd.DataFrame()

    for _, signal in signals.iterrows():

        signal_index = int(
            signal["signal_index"]
        )

        signal_date = signal["signal_date"]
        entry = float(signal["entry"])
        stop = float(signal["stop"])
        valid_sl = bool(signal["valid_sl"])

        target = (
            float(signal["target"])
            if valid_sl
            else np.nan
        )

        trade = {
            "signal_date": signal_date,
            "entry": entry,
            "stop": stop,
            "target": target,
            "risk": (
                float(signal["risk"])
                if valid_sl
                else np.nan
            ),
            "valid_sl": valid_sl,
            "result": None,
            "R": np.nan,
            "exit_date": pd.NaT,
            "exit_price": np.nan,
            "holding_days": np.nan,
        }

        if not valid_sl:
            trade["result"] = "INVALID_SL"
            trades.append(trade)
            continue

        resolved = False

        for j in range(
            signal_index + 1,
            len(df)
        ):

            future = df.iloc[j]

            hit_tp = (
                future["High"] >= target
            )

            hit_sl = (
                future["Low"] <= stop
            )

            # Same candle touches both levels.
            if hit_tp and hit_sl:

                trade["result"] = "AMBIGUOUS"
                trade["R"] = np.nan
                trade["exit_date"] = future["date"]
                trade["exit_price"] = np.nan
                trade["holding_days"] = j - signal_index

                resolved = True
                break

            if hit_tp:

                trade["result"] = "WIN"
                trade["R"] = RR
                trade["exit_date"] = future["date"]
                trade["exit_price"] = target
                trade["holding_days"] = j - signal_index

                resolved = True
                break

            if hit_sl:

                trade["result"] = "LOSS"
                trade["R"] = -1.0
                trade["exit_date"] = future["date"]
                trade["exit_price"] = stop
                trade["holding_days"] = j - signal_index

                resolved = True
                break

        if not resolved:

            trade["result"] = "OPEN"
            trade["R"] = np.nan

        trades.append(trade)

    return pd.DataFrame(trades)


# ============================================================
# STATISTICS
# ============================================================

def calculate_stats(trades):

    if trades.empty:
        return {
            "total_signals": 0,
            "valid_setups": 0,
            "resolved_trades": 0,
            "wins": 0,
            "losses": 0,
            "ambiguous": 0,
            "open_trades": 0,
            "invalid_sl": 0,
            "win_rate_pct": np.nan,
            "average_R": np.nan,
            "total_R": np.nan,
            "profit_factor": np.nan,
        }

    valid = trades[
        trades["valid_sl"] == True
    ]

    resolved = trades[
        trades["result"].isin(
            ["WIN", "LOSS", "AMBIGUOUS"]
        )
    ]

    wins = trades[
        trades["result"] == "WIN"
    ]

    losses = trades[
        trades["result"] == "LOSS"
    ]

    ambiguous = trades[
        trades["result"] == "AMBIGUOUS"
    ]

    open_trades = trades[
        trades["result"] == "OPEN"
    ]

    invalid = trades[
        trades["result"] == "INVALID_SL"
    ]

    # Historical baseline win rate excludes ambiguous trades.
    denominator = (
        len(wins) + len(losses)
    )

    win_rate = (
        len(wins) / denominator * 100
        if denominator
        else np.nan
    )

    resolved_r = trades[
        trades["result"].isin(
            ["WIN", "LOSS"]
        )
    ]["R"]

    total_R = (
        resolved_r.sum()
        if not resolved_r.empty
        else np.nan
    )

    average_R = (
        resolved_r.mean()
        if not resolved_r.empty
        else np.nan
    )

    gross_profit = (
        wins["R"].sum()
        if not wins.empty
        else 0
    )

    gross_loss = abs(
        losses["R"].sum()
    ) if not losses.empty else 0

    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else np.nan
    )

    return {
        "total_signals": len(trades),
        "valid_setups": len(valid),
        "resolved_trades": len(resolved),
        "wins": len(wins),
        "losses": len(losses),
        "ambiguous": len(ambiguous),
        "open_trades": len(open_trades),
        "invalid_sl": len(invalid),
        "win_rate_pct": win_rate,
        "average_R": average_R,
        "total_R": total_R,
        "profit_factor": profit_factor,
    }


def yearly_stats(trades):

    if trades.empty:
        return pd.DataFrame()

    x = trades.copy()

    x["year"] = pd.to_datetime(
        x["signal_date"]
    ).dt.year

    rows = []

    for year, group in x.groupby("year"):

        stats = calculate_stats(group)
        stats["year"] = year
        rows.append(stats)

    result = pd.DataFrame(rows)

    if not result.empty:
        result = result.sort_values(
            "year"
        )

    return result


# ============================================================
# DIAGNOSTICS
# ============================================================

def print_comparison(stats):

    reference = {
        "total_signals": 119,
        "valid_setups": 117,
        "resolved_trades": 109,
        "wins": 36,
        "losses": 73,
        "ambiguous": 3,
        "open_trades": 5,
        "invalid_sl": 2,
        "win_rate_pct": 33.028,
        "average_R": 0.651,
        "total_R": 71,
        "profit_factor": 1.973,
    }

    print("\n" + "=" * 60)
    print("BASELINE VALIDATION")
    print("=" * 60)

    print(
        f"{'Metric':25s}"
        f"{'Current':>15s}"
        f"{'Old reference':>18s}"
    )

    print("-" * 60)

    for key in reference:

        current = stats.get(key)
        old = reference[key]

        if isinstance(old, float):
            current_text = (
                f"{current:.3f}"
                if pd.notna(current)
                else "NaN"
            )
            old_text = f"{old:.3f}"
        else:
            current_text = str(current)
            old_text = str(old)

        print(
            f"{key:25s}"
            f"{current_text:>15s}"
            f"{old_text:>18s}"
        )

    print("-" * 60)

    signal_diff = (
        stats["total_signals"]
        - reference["total_signals"]
    )

    print(
        f"\nSignal difference vs old reference: "
        f"{signal_diff:+d}"
    )

    if abs(signal_diff) <= 2:
        print(
            "STATUS: Signal count is very close "
            "to the historical reference."
        )
    else:
        print(
            "STATUS: Signal count does NOT yet "
            "match the historical reference."
        )
        print(
            "Do NOT use this as the final Macro baseline "
            "until the difference is understood."
        )


# ============================================================
# SAVE
# ============================================================

def save_results(trades, signals, yearly, stats):

    trades.to_csv(
        OUTPUT_TRADES,
        index=False
    )

    signals.to_csv(
        OUTPUT_SIGNALS,
        index=False
    )

    yearly.to_csv(
        OUTPUT_YEARLY,
        index=False
    )

    summary = pd.DataFrame(
        [stats]
    )

    summary.to_csv(
        OUTPUT_SUMMARY,
        index=False
    )

    print("\nFILES CREATED")
    print("-" * 60)

    for filename in [
        OUTPUT_TRADES,
        OUTPUT_SIGNALS,
        OUTPUT_YEARLY,
        OUTPUT_SUMMARY,
    ]:
        print(filename)


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n")
    print("=" * 60)
    print("US500 EMA19 BASELINE RECONSTRUCTION")
    print("=" * 60)

    print(f"Ticker: {TICKER}")
    print(f"Start: {START_DATE}")
    print(f"EMA: {EMA_FAST}")
    print(f"Trend EMA: {EMA_TREND}")
    print(f"RR: 1:{RR}")

    market = get_market_data()
    market = prepare_market(market)

    signals = detect_signals(
        market
    )

    trades = evaluate_trades(
        market,
        signals
    )

    stats = calculate_stats(
        trades
    )

    print("\n" + "=" * 60)
    print("BASELINE RESULTS")
    print("=" * 60)

    for key, value in stats.items():
        if isinstance(value, float):
            if pd.isna(value):
                print(f"{key:25s}: NaN")
            else:
                print(f"{key:25s}: {value:.3f}")
        else:
            print(f"{key:25s}: {value}")

    yearly = yearly_stats(
        trades
    )

    if not yearly.empty:

        print("\nYEARLY RESULTS")
        print("-" * 60)

        display_cols = [
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
                display_cols
            ].to_string(
                index=False
            )
        )

    print_comparison(
        stats
    )

    save_results(
        trades,
        signals,
        yearly,
        stats
    )

    print("\n" + "=" * 60)
    print("BASELINE RECONSTRUCTION COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
