import pandas as pd
import numpy as np

from data import get_historical_market_data
from historical_events import (
    detect_correction_cycles,
    add_pullback_levels,
)


# ============================================================
# SETTINGS
# ============================================================

START_DATE = "2019-01-01"

PULLBACK_LEVELS = [-3, -5, -10, -20, -30]

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

    # ATR of completed candles only.
    # Shift(1) excludes the trigger candle.
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

    The trigger candle is excluded.
    """

    try:
        position = df.index.get_loc(
            trigger_date
        )
    except KeyError:
        return np.nan

    # Need 5 completed candles before entry.
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
    entry,
    stop_loss,
    take_profit,
):
    """
    Entry occurs at trigger-day close.

    TP/SL evaluation begins on the following
    trading day.

    If both TP and SL are touched on the
    same daily candle, the result is AMBIGUOUS.
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

        # Daily OHLC cannot tell which level
        # was hit first.
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
# BUILD BACKTEST EVENTS
# ============================================================

def build_backtest_events(
    market_data,
    cycles,
):
    """
    Create one event for every:

        correction cycle
        x
        pullback level

    Therefore:

        19 cycles x 5 levels = 95 events

    even when some levels were never reached.
    """

    events = []

    # --------------------------------------------------------
    # IMPORTANT:
    # cycles is a DataFrame.
    # We therefore use iterrows().
    # --------------------------------------------------------

    for cycle_index, cycle in cycles.iterrows():

        cycle_id = int(cycle_index) + 1

        reference_high = float(
            cycle["reference_high"]
        )

        start_date = pd.Timestamp(
            cycle["start_date"]
        )

        recovery_date = cycle[
            "recovery_date"
        ]

        if pd.isna(recovery_date):

            recovery_date = None

        else:

            recovery_date = pd.Timestamp(
                recovery_date
            )

        # ----------------------------------------------------
        # Select correction period
        # ----------------------------------------------------

        if recovery_date is not None:

            period = market_data.loc[
                start_date:
                recovery_date
            ]

        else:

            period = market_data.loc[
                start_date:
            ]

        # ----------------------------------------------------
        # Every pullback level
        # ----------------------------------------------------

        for level in PULLBACK_LEVELS:

            level_abs = abs(level)

            threshold_price = (
                reference_high
                * (
                    1
                    + level / 100
                )
            )

            trigger_date = None
            trigger_price = None
            trigger_drawdown = None

            # ------------------------------------------------
            # Find first trigger
            # ------------------------------------------------

            for date, row in period.iterrows():

                close = float(
                    row["close"]
                )

                drawdown = (
                    close
                    / reference_high
                    - 1
                ) * 100

                if drawdown <= level:

                    trigger_date = date
                    trigger_price = close
                    trigger_drawdown = drawdown

                    break

            # ------------------------------------------------
            # NO TRIGGER
            # ------------------------------------------------

            if trigger_date is None:

                events.append({

                    "cycle_id":
                        cycle_id,

                    "level":
                        level_abs,

                    "reference_high_date":
                        cycle[
                            "reference_high_date"
                        ],

                    "reference_high":
                        reference_high,

                    "cycle_start":
                        cycle[
                            "start_date"
                        ],

                    "start_price":
                        cycle[
                            "start_price"
                        ],

                    "trigger_date":
                        None,

                    "trigger_price":
                        np.nan,

                    "trigger_drawdown_pct":
                        np.nan,

                    "trough_date":
                        cycle[
                            "trough_date"
                        ],

                    "trough_price":
                        cycle[
                            "trough_price"
                        ],

                    "maximum_drawdown_pct":
                        cycle[
                            "maximum_drawdown_pct"
                        ],

                    "recovery_date":
                        cycle[
                            "recovery_date"
                        ],

                    "recovery_days":
                        cycle[
                            "recovery_days"
                        ],

                    "level_price":
                        threshold_price,

                    "entry":
                        np.nan,

                    "stop_loss":
                        np.nan,

                    "take_profit":
                        np.nan,

                    "risk_points":
                        np.nan,

                    "status":
                        "NO_TRIGGER",

                    "result":
                        "NO_TRIGGER",

                    "exit_date":
                        None,

                    "R":
                        np.nan,
                })

                continue

            # ------------------------------------------------
            # ENTRY
            # ------------------------------------------------

            entry = float(
                trigger_price
            )

            stop_loss = calculate_stop_loss(
                market_data,
                trigger_date,
            )

            # ------------------------------------------------
            # INVALID SL
            # ------------------------------------------------

            if (
                not np.isfinite(stop_loss)
                or stop_loss >= entry
            ):

                events.append({

                    "cycle_id":
                        cycle_id,

                    "level":
                        level_abs,

                    "reference_high_date":
                        cycle[
                            "reference_high_date"
                        ],

                    "reference_high":
                        reference_high,

                    "cycle_start":
                        cycle[
                            "start_date"
                        ],

                    "start_price":
                        cycle[
                            "start_price"
                        ],

                    "trigger_date":
                        trigger_date,

                    "trigger_price":
                        entry,

                    "trigger_drawdown_pct":
                        trigger_drawdown,

                    "trough_date":
                        cycle[
                            "trough_date"
                        ],

                    "trough_price":
                        cycle[
                            "trough_price"
                        ],

                    "maximum_drawdown_pct":
                        cycle[
                            "maximum_drawdown_pct"
                        ],

                    "recovery_date":
                        cycle[
                            "recovery_date"
                        ],

                    "recovery_days":
                        cycle[
                            "recovery_days"
                        ],

                    "level_price":
                        threshold_price,

                    "entry":
                        entry,

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

            # ------------------------------------------------
            # VALID TRADE
            # ------------------------------------------------

            risk = entry - stop_loss

            take_profit = (
                entry
                + RR * risk
            )

            evaluation = evaluate_trade(
                market_data,
                trigger_date,
                entry,
                stop_loss,
                take_profit,
            )

            events.append({

                "cycle_id":
                    cycle_id,

                "level":
                    level_abs,

                "reference_high_date":
                    cycle[
                        "reference_high_date"
                    ],

                "reference_high":
                    reference_high,

                "cycle_start":
                    cycle[
                        "start_date"
                    ],

                "start_price":
                    cycle[
                        "start_price"
                    ],

                "trigger_date":
                    trigger_date,

                "trigger_price":
                    entry,

                "trigger_drawdown_pct":
                    trigger_drawdown,

                "trough_date":
                    cycle[
                        "trough_date"
                    ],

                "trough_price":
                    cycle[
                        "trough_price"
                    ],

                "maximum_drawdown_pct":
                    cycle[
                        "maximum_drawdown_pct"
                    ],

                "recovery_date":
                    cycle[
                        "recovery_date"
                    ],

                "recovery_days":
                    cycle[
                        "recovery_days"
                    ],

                "level_price":
                    threshold_price,

                "entry":
                    entry,

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
# SUMMARY BY PULLBACK
# ============================================================

def calculate_summary(
    trades
):

    rows = []

    for level in PULLBACK_LEVELS:

        level_abs = abs(level)

        subset = trades[
            trades["level"] == level_abs
        ]

        valid = subset[
            subset["status"] == "VALID"
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

        invalid_sl = subset[
            subset["status"] == "INVALID_SL"
        ]

        no_trigger = subset[
            subset["status"] == "NO_TRIGGER"
        ]

        resolved = pd.concat(
            [
                wins,
                losses,
            ],
            ignore_index=True
        )

        resolved_count = len(
            resolved
        )

        if resolved_count > 0:

            win_rate = (
                len(wins)
                / resolved_count
                * 100
            )

            loss_rate = (
                len(losses)
                / resolved_count
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

        rows.append({

            "pullback":
                f"-{level_abs}%",

            "total_events":
                len(subset),

            "valid_setups":
                len(valid),

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

            "no_trigger":
                len(no_trigger),

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
        })

    return pd.DataFrame(
        rows
    )


# ============================================================
# INVALID SL DIAGNOSTICS
# ============================================================

def build_invalid_sl_diagnostics(
    trades
):

    invalid = trades[
        trades["status"] == "INVALID_SL"
    ].copy()

    if invalid.empty:
        return invalid

    columns = [

        "cycle_id",
        "level",

        "reference_high_date",
        "reference_high",

        "cycle_start",
        "start_price",

        "trigger_date",
        "trigger_price",
        "trigger_drawdown_pct",

        "trough_date",
        "trough_price",
        "maximum_drawdown_pct",

        "entry",
        "stop_loss",
        "level_price",
    ]

    return invalid[
        columns
    ]


# ============================================================
# AMBIGUOUS DIAGNOSTICS
# ============================================================

def build_ambiguous_diagnostics(
    trades
):

    ambiguous = trades[
        trades["result"] == "AMBIGUOUS"
    ].copy()

    if ambiguous.empty:
        return ambiguous

    columns = [

        "cycle_id",
        "level",

        "trigger_date",
        "trigger_price",

        "entry",
        "stop_loss",
        "take_profit",
        "risk_points",

        "exit_date",

        "reference_high",
        "maximum_drawdown_pct",
    ]

    return ambiguous[
        columns
    ]


# ============================================================
# OVERALL SUMMARY
# ============================================================

def calculate_overall_summary(
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

    no_trigger = trades[
        trades["status"] == "NO_TRIGGER"
    ]

    resolved = pd.concat(
        [
            wins,
            losses,
        ],
        ignore_index=True
    )

    if not resolved.empty:

        win_rate = (
            len(wins)
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
        average_r = np.nan
        total_r = np.nan
        profit_factor = np.nan

    return {

        "total_events":
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

        "no_trigger":
            len(no_trigger),

        "win_rate_pct":
            win_rate,

        "average_R":
            average_r,

        "total_R":
            total_r,

        "profit_factor":
            profit_factor,
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "US500 BACKTEST"
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
        f"RR: 1:{RR}"
    )

    print(
        f"Pullbacks: {PULLBACK_LEVELS}"
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
    # CORRECTION CYCLES
    # ========================================================

    cycles = detect_correction_cycles(
        market,
        minimum_drawdown=-3,
    )

    if cycles.empty:

        raise RuntimeError(
            "No correction cycles detected."
        )

    print(
        "Correction cycles detected:",
        len(cycles)
    )

    # ========================================================
    # IMPORTANT CROSS-CHECK
    # ========================================================

    # This uses the same historical event engine
    # already tested in historical_events.py.

    historical_events = add_pullback_levels(
        market,
        cycles,
        levels=PULLBACK_LEVELS,
    )

    print(
        "Historical triggered levels:",
        len(historical_events)
    )

    # ========================================================
    # BUILD ALL 19 x 5 EVENTS
    # ========================================================

    trades = build_backtest_events(
        market,
        cycles,
    )

    print(
        "Total pullback events:",
        len(trades)
    )

    # ========================================================
    # RESULTS BY LEVEL
    # ========================================================

    summary = calculate_summary(
        trades
    )

    print()
    print(
        "RESULTS BY PULLBACK"
    )

    print(
        "-" * 60
    )

    print(
        summary.to_string(
            index=False
        )
    )

    # ========================================================
    # OVERALL
    # ========================================================

    overall = calculate_overall_summary(
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
    # DIAGNOSTICS
    # ========================================================

    invalid_sl = (
        build_invalid_sl_diagnostics(
            trades
        )
    )

    ambiguous = (
        build_ambiguous_diagnostics(
            trades
        )
    )

    print()
    print(
        "DIAGNOSTICS"
    )

    print(
        "-" * 60
    )

    print(
        "Invalid SL cases:",
        len(invalid_sl)
    )

    print(
        "Ambiguous cases:",
        len(ambiguous)
    )

    # ========================================================
    # INVALID SL DETAILS
    # ========================================================

    if not invalid_sl.empty:

        print()
        print(
            "INVALID SL CASES"
        )

        print(
            "-" * 60
        )

        print(
            invalid_sl.to_string(
                index=False
            )
        )

    # ========================================================
    # AMBIGUOUS DETAILS
    # ========================================================

    if not ambiguous.empty:

        print()
        print(
            "AMBIGUOUS CASES"
        )

        print(
            "-" * 60
        )

        print(
            ambiguous.to_string(
                index=False
            )
        )

    # ========================================================
    # SAVE CSV FILES
    # ========================================================

    trades.to_csv(
        "backtest_trades.csv",
        index=False
    )

    cycles.to_csv(
        "backtest_cycles.csv",
        index=False
    )

    summary.to_csv(
        "backtest_summary.csv",
        index=False
    )

    invalid_sl.to_csv(
        "backtest_invalid_sl.csv",
        index=False
    )

    ambiguous.to_csv(
        "backtest_ambiguous.csv",
        index=False
    )

    # ========================================================
    # FINAL OUTPUT
    # ========================================================

    print()
    print(
        "FILES CREATED"
    )

    print(
        "-" * 60
    )

    print(
        "backtest_trades.csv"
    )

    print(
        "backtest_cycles.csv"
    )

    print(
        "backtest_summary.csv"
    )

    print(
        "backtest_invalid_sl.csv"
    )

    print(
        "backtest_ambiguous.csv"
    )

    print()
    print(
        "BACKTEST COMPLETE"
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
