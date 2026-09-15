import pandas as pd
import numpy as np

from data import get_historical_market_data


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


# ============================================================
# ATR
# ============================================================

def calculate_atr(df, period=14):

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

    return true_range.rolling(
        period
    ).mean()


# ============================================================
# PREPARE MARKET DATA
# ============================================================

def prepare_market_data(df):

    data = df.copy()

    data = data.sort_index()

    # EMA19
    data["ema19"] = data["close"].ewm(
        span=EMA_FAST,
        adjust=False
    ).mean()

    # EMA200
    data["ema200"] = data["close"].ewm(
        span=EMA_TREND,
        adjust=False
    ).mean()

    # ATR
    data["atr14"] = (
        calculate_atr(
            data,
            ATR_PERIOD,
        )
        .shift(1)
    )

    return data


# ============================================================
# STOP LOSS
# ============================================================

def calculate_stop_loss(
    df,
    trigger_date,
):
    """
    Mechanical SL:

        Lowest Low of previous 5 completed
        Daily candles
        -
        0.5 x ATR(14)

    Trigger candle excluded.
    """

    try:
        position = df.index.get_loc(
            trigger_date
        )
    except KeyError:
        return np.nan

    if position < LOOKBACK_LOW:
        return np.nan

    previous_candles = df.iloc[
        position - LOOKBACK_LOW:
        position
    ]

    if len(previous_candles) != LOOKBACK_LOW:
        return np.nan

    lowest_low = float(
        previous_candles["low"].min()
    )

    atr = float(
        df.iloc[position]["atr14"]
    )

    if not np.isfinite(atr):
        return np.nan

    stop_loss = (
        lowest_low
        - ATR_MULTIPLIER * atr
    )

    return float(stop_loss)


# ============================================================
# EVALUATE TRADE
# ============================================================

def evaluate_trade(
    df,
    entry_date,
    stop_loss,
    take_profit,
):
    """
    Entry occurs at trigger-day close.

    TP/SL evaluation begins on the following
    trading day.

    If both TP and SL are touched on the
    same daily candle, result = AMBIGUOUS.
    """

    position = df.index.get_loc(
        entry_date
    )

    future = df.iloc[
        position + 1:
    ]

    for date, row in future.iterrows():

        high = float(row["high"])
        low = float(row["low"])

        hit_tp = high >= take_profit
        hit_sl = low <= stop_loss

        if hit_tp and hit_sl:

            return {
                "result": "AMBIGUOUS",
                "exit_date": date,
                "R": np.nan,
            }

        if hit_sl:

            return {
                "result": "LOSS",
                "exit_date": date,
                "R": -1.0,
            }

        if hit_tp:

            return {
                "result": "WIN",
                "exit_date": date,
                "R": RR,
            }

    return {
        "result": "OPEN",
        "exit_date": None,
        "R": np.nan,
    }


# ============================================================
# DETECT EMA19 PULLBACKS
# ============================================================

def detect_ema19_pullbacks(df):

    events = []

    data = df.copy()

    # --------------------------------------------------------
    # We need a sufficiently developed EMA200.
    # --------------------------------------------------------

    for i in range(
        EMA_TREND,
        len(data)
    ):

        row = data.iloc[i]

        date = data.index[i]

        close = float(row["close"])
        low = float(row["low"])

        ema19 = float(row["ema19"])
        ema200 = float(row["ema200"])

        # ----------------------------------------------------
        # Ignore rows without indicators.
        # ----------------------------------------------------

        if not np.isfinite(ema19):
            continue

        if not np.isfinite(ema200):
            continue

        # ----------------------------------------------------
        # PRIMARY TREND FILTER
        #
        # Price > EMA200
        # EMA19 > EMA200
        # ----------------------------------------------------

        if close <= ema200:
            continue

        if ema19 <= ema200:
            continue

        # ----------------------------------------------------
        # EMA19 PULLBACK
        #
        # Price must touch or penetrate EMA19.
        #
        # Low <= EMA19
        # ----------------------------------------------------

        if low > ema19:
            continue

        # ----------------------------------------------------
        # RECLAIM
        #
        # Close must finish above EMA19.
        # ----------------------------------------------------

        if close <= ema19:
            continue

        # ----------------------------------------------------
        # PREVIOUS DAY
        #
        # Prevent repeated signals while price remains
        # around EMA19.
        #
        # We require the previous close to be above EMA19
        # or the previous candle not to have already been
        # a valid reclaim.
        # ----------------------------------------------------

        previous = data.iloc[i - 1]

        previous_close = float(
            previous["close"]
        )

        previous_ema19 = float(
            previous["ema19"]
        )

        # If previous candle also closed above EMA19
        # and already touched EMA19, this is not a new
        # reclaim event.
        previous_was_reclaim = (
            previous_close > previous_ema19
            and float(previous["low"]) <= previous_ema19
        )

        if previous_was_reclaim:
            continue

        # ----------------------------------------------------
        # SIGNAL
        # ----------------------------------------------------

        events.append({

            "signal_date": date,

            "entry": close,

            "ema19": ema19,

            "ema200": ema200,

            "distance_from_ema19_pct": (
                (close / ema19 - 1) * 100
            ),

            "distance_from_ema200_pct": (
                (close / ema200 - 1) * 100
            ),

        })

    return pd.DataFrame(
        events
    )


# ============================================================
# BUILD BACKTEST
# ============================================================

def build_backtest(
    market_data,
    signals,
):

    events = []

    for _, signal in signals.iterrows():

        trigger_date = pd.Timestamp(
            signal["signal_date"]
        )

        entry = float(
            signal["entry"]
        )

        stop_loss = calculate_stop_loss(
            market_data,
            trigger_date,
        )

        # ----------------------------------------------------
        # INVALID SL
        # ----------------------------------------------------

        if (
            not np.isfinite(stop_loss)
            or stop_loss >= entry
        ):

            events.append({

                "signal_date":
                    trigger_date,

                "entry":
                    entry,

                "ema19":
                    signal["ema19"],

                "ema200":
                    signal["ema200"],

                "distance_from_ema19_pct":
                    signal[
                        "distance_from_ema19_pct"
                    ],

                "distance_from_ema200_pct":
                    signal[
                        "distance_from_ema200_pct"
                    ],

                "stop_loss":
                    stop_loss,

                "take_profit":
                    np.nan,

                "risk_points":
                    np.nan,

                "status":
                    "INVALID_SL",

                "result":
                    "INVALID_SL",

                "exit_date":
                    None,

                "R":
                    np.nan,
            })

            continue

        # ----------------------------------------------------
        # RISK
        # ----------------------------------------------------

        risk = (
            entry
            - stop_loss
        )

        # ----------------------------------------------------
        # TAKE PROFIT
        # ----------------------------------------------------

        take_profit = (
            entry
            + RR * risk
        )

        # ----------------------------------------------------
        # EVALUATE
        # ----------------------------------------------------

        evaluation = evaluate_trade(
            market_data,
            trigger_date,
            stop_loss,
            take_profit,
        )

        events.append({

            "signal_date":
                trigger_date,

            "entry":
                entry,

            "ema19":
                signal["ema19"],

            "ema200":
                signal["ema200"],

            "distance_from_ema19_pct":
                signal[
                    "distance_from_ema19_pct"
                ],

            "distance_from_ema200_pct":
                signal[
                    "distance_from_ema200_pct"
                ],

            "stop_loss":
                stop_loss,

            "take_profit":
                take_profit,

            "risk_points":
                risk,

            "status":
                "VALID",

            "result":
                evaluation[
                    "result"
                ],

            "exit_date":
                evaluation[
                    "exit_date"
                ],

            "R":
                evaluation[
                    "R"
                ],
        })

    return pd.DataFrame(
        events
    )


# ============================================================
# SUMMARY
# ============================================================

def calculate_summary(
    trades
):

    valid = trades[
        trades["status"] == "VALID"
    ]

    wins = valid[
        valid["result"] == "WIN"
    ]

    losses = valid[
        valid["result"] == "LOSS"
    ]

    ambiguous = valid[
        valid["result"] == "AMBIGUOUS"
    ]

    open_trades = valid[
        valid["result"] == "OPEN"
    ]

    invalid_sl = trades[
        trades["status"] == "INVALID_SL"
    ]

    resolved = pd.concat(
        [
            wins,
            losses,
        ],
        ignore_index=True
    )

    if len(resolved) > 0:

        win_rate = (
            len(wins)
            / len(resolved)
            * 100
        )

        loss_rate = (
            len(losses)
            / len(resolved)
            * 100
        )

        average_r = float(
            resolved["R"].mean()
        )

        total_r = float(
            resolved["R"].sum()
        )

        gross_profit = float(
            wins["R"].sum()
        )

        gross_loss = abs(
            float(
                losses["R"].sum()
            )
        )

        if gross_loss > 0:

            profit_factor = (
                gross_profit
                / gross_loss
            )

        else:

            profit_factor = np.nan

    else:

        win_rate = np.nan
        loss_rate = np.nan
        average_r = np.nan
        total_r = np.nan
        profit_factor = np.nan

    return {

        "total_signals":
            len(trades),

        "valid_setups":
            len(valid),

        "resolved_trades":
            len(resolved),

        "wins":
            len(wins),

        "losses":
            len(losses),

        "ambiguous":
            len(ambiguous),

        "open":
            len(open_trades),

        "invalid_sl":
            len(invalid_sl),

        "win_rate_pct":
            win_rate,

        "loss_rate_pct":
            loss_rate,

        "average_R":
            average_r,

        "expectancy_R":
            average_r,

        "total_R":
            total_r,

        "profit_factor":
            profit_factor,
    }


# ============================================================
# YEARLY SUMMARY
# ============================================================

def calculate_yearly_summary(
    trades
):

    valid = trades[
        trades["status"] == "VALID"
    ].copy()

    if valid.empty:

        return pd.DataFrame()

    valid["year"] = pd.to_datetime(
        valid["signal_date"]
    ).dt.year

    rows = []

    for year, group in valid.groupby(
        "year"
    ):

        resolved = group[
            group["result"].isin(
                ["WIN", "LOSS"]
            )
        ]

        wins = group[
            group["result"] == "WIN"
        ]

        losses = group[
            group["result"] == "LOSS"
        ]

        if len(resolved) > 0:

            win_rate = (
                len(wins)
                / len(resolved)
                * 100
            )

            total_r = float(
                resolved["R"].sum()
            )

            average_r = float(
                resolved["R"].mean()
            )

        else:

            win_rate = np.nan
            total_r = np.nan
            average_r = np.nan

        rows.append({

            "year":
                year,

            "signals":
                len(group),

            "resolved":
                len(resolved),

            "wins":
                len(wins),

            "losses":
                len(losses),

            "ambiguous":
                len(
                    group[
                        group["result"]
                        == "AMBIGUOUS"
                    ]
                ),

            "win_rate_pct":
                win_rate,

            "average_R":
                average_r,

            "total_R":
                total_r,
        })

    return pd.DataFrame(
        rows
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "US500 EMA19 PULLBACK BACKTEST"
    )

    print(
        "=" * 60
    )

    print(
        "Ticker: ^GSPC"
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

    print()

    # ========================================================
    # MARKET DATA
    # ========================================================

    market = get_historical_market_data(
        start_date=START_DATE
    )

    if market.empty:

        raise RuntimeError(
            "Historical market data unavailable."
        )

    print(
        "Market data:",
        market.index.min().date(),
        "→",
        market.index.max().date()
    )

    market = prepare_market_data(
        market
    )

    # ========================================================
    # DETECT SIGNALS
    # ========================================================

    signals = detect_ema19_pullbacks(
        market
    )

    print(
        "EMA19 Pullback signals:",
        len(signals)
    )

    # ========================================================
    # BACKTEST
    # ========================================================

    trades = build_backtest(
        market,
        signals,
    )

    print(
        "Backtest events:",
        len(trades)
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    overall = calculate_summary(
        trades
    )

    print()
    print(
        "OVERALL"
    )

    print(
        "-" * 60
    )

    for key, value in overall.items():

        label = key.replace(
            "_",
            " "
        ).title()

        if isinstance(
            value,
            (float, np.floating)
        ):

            if np.isnan(value):

                display_value = "N/A"

            else:

                display_value = round(
                    float(value),
                    3
                )

        else:

            display_value = value

        print(
            f"{label:<20}: {display_value}"
        )

    # ========================================================
    # YEARLY
    # ========================================================

    yearly = calculate_yearly_summary(
        trades
    )

    print()
    print(
        "YEARLY RESULTS"
    )

    print(
        "-" * 60
    )

    if not yearly.empty:

        print(
            yearly.to_string(
                index=False
            )
        )

    # ========================================================
    # SIGNAL DETAILS
    # ========================================================

    print()
    print(
        "SIGNAL DETAILS"
    )

    print(
        "-" * 60
    )

    if not trades.empty:

        print(
            trades.to_string(
                index=False
            )
        )

    # ========================================================
    # SAVE
    # ========================================================

    signals.to_csv(
        "ema19_signals.csv",
        index=False
    )

    trades.to_csv(
        "backtestEMA19_trades.csv",
        index=False
    )

    yearly.to_csv(
        "backtestEMA19_yearly.csv",
        index=False
    )

    print()
    print(
        "FILES CREATED"
    )

    print(
        "-" * 60
    )

    print(
        "ema19_signals.csv"
    )

    print(
        "backtestEMA19_trades.csv"
    )

    print(
        "backtestEMA19_yearly.csv"
    )

    print()
    print(
        "EMA19 BACKTEST COMPLETE"
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
