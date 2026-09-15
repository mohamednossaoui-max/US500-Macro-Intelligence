import pandas as pd
import numpy as np

from data import get_historical_market_data
from historical_events import detect_correction_cycles


# ============================================================
# CONFIGURATION
# ============================================================

START_DATE = "2019-01-01"

PULLBACKS = [3, 5, 10, 20, 30]

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
        axis=1
    ).max(axis=1)

    atr = true_range.rolling(
        period
    ).mean()

    return atr


# ============================================================
# PREPARE MARKET DATA
# ============================================================

def prepare_market_data(df):

    df = df.copy()

    df = df.sort_index()

    # ATR calculated using completed candles.
    # Shift(1) ensures trigger candle is excluded.
    df["atr14"] = (
        calculate_atr(
            df,
            ATR_PERIOD
        )
        .shift(1)
    )

    return df


# ============================================================
# PULLBACK TRIGGER
# ============================================================

def find_pullback_trigger(
    df,
    cycle,
    pullback_pct,
):
    """
    Find the first daily close that reaches
    the requested pullback level.

    Reference high remains frozen during
    the correction cycle.
    """

    reference_high = float(
        cycle["reference_high"]
    )

    target_price = (
        reference_high
        * (1 - pullback_pct / 100)
    )

    start_date = pd.Timestamp(
        cycle["start_date"]
    )

    end_date = pd.Timestamp(
        cycle["end_date"]
    )

    period = df.loc[
        start_date:end_date
    ]

    if period.empty:
        return None

    for date, row in period.iterrows():

        close = float(row["close"])

        if close <= target_price:

            return {
                "trigger_date": date,
                "entry": close,
                "reference_high": reference_high,
                "target_price": target_price,
            }

    return None


# ============================================================
# STOP LOSS
# ============================================================

def calculate_stop_loss(
    df,
    trigger_date,
):
    """
    Mechanical stop:

        lowest Low of previous 5 completed
        Daily candles
        -
        0.5 * ATR(14)

    Trigger day is excluded.
    """

    try:

        position = df.index.get_loc(
            trigger_date
        )

    except KeyError:

        return np.nan

    # Need at least 5 candles BEFORE trigger.
    if position < LOOKBACK_LOW:
        return np.nan

    previous_candles = df.iloc[
        position - LOOKBACK_LOW:
        position
    ]

    if len(previous_candles) < LOOKBACK_LOW:
        return np.nan

    lowest_low = float(
        previous_candles["low"].min()
    )

    atr = float(
        df.iloc[position]["atr14"]
    )

    if not np.isfinite(atr):
        return np.nan

    stop = (
        lowest_low
        - ATR_MULTIPLIER * atr
    )

    return float(stop)


# ============================================================
# TRADE EVALUATION
# ============================================================

def evaluate_trade(
    df,
    entry_date,
    entry,
    stop_loss,
    take_profit,
):
    """
    Evaluate trade after entry.

    Entry occurs at trigger-day close.

    Future candles are examined from the
    following trading day.

    If both TP and SL are touched on the
    same candle, result is AMBIGUOUS because
    daily OHLC cannot determine which was hit first.
    """

    try:

        position = df.index.get_loc(
            entry_date
        )

    except KeyError:

        return {
            "result": "ERROR",
            "exit_date": None,
            "R": np.nan,
        }

    future = df.iloc[
        position + 1:
    ]

    for date, row in future.iterrows():

        high = float(row["high"])
        low = float(row["low"])

        hit_sl = low <= stop_loss
        hit_tp = high >= take_profit

        # Both levels touched on same candle.
        if hit_sl and hit_tp:

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
    df,
    cycles,
):
    """
    Create one event for every combination:

        correction cycle
        x
        pullback level

    This means all 5 levels are preserved,
    even when a level is never triggered.
    """

    events = []

    for cycle_id, cycle in enumerate(
        cycles,
        start=1
    ):

        for pullback in PULLBACKS:

            trigger = find_pullback_trigger(
                df,
                cycle,
                pullback,
            )

            base = {
                "cycle_id": cycle_id,
                "pullback": -pullback,
                "reference_high":
                    cycle["reference_high"],
                "cycle_start":
                    cycle["start_date"],
                "cycle_end":
                    cycle["end_date"],
                "cycle_trough":
                    cycle.get(
                        "trough_date",
                        None
                    ),
                "cycle_drawdown":
                    cycle.get(
                        "drawdown_pct",
                        np.nan
                    ),
            }

            # No trigger.
            if trigger is None:

                events.append({
                    **base,
                    "trigger_date": None,
                    "entry": np.nan,
                    "stop_loss": np.nan,
                    "take_profit": np.nan,
                    "risk_points": np.nan,
                    "status": "NO_TRIGGER",
                    "result": "NO_TRIGGER",
                    "exit_date": None,
                    "R": np.nan,
                })

                continue

            trigger_date = trigger[
                "trigger_date"
            ]

            entry = float(
                trigger["entry"]
            )

            stop_loss = calculate_stop_loss(
                df,
                trigger_date
            )

            # Invalid SL.
            if (
                not np.isfinite(stop_loss)
                or stop_loss >= entry
            ):

                events.append({
                    **base,
                    "trigger_date":
                        trigger_date,
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

            risk = entry - stop_loss

            take_profit = (
                entry
                + RR * risk
            )

            evaluation = evaluate_trade(
                df,
                trigger_date,
                entry,
                stop_loss,
                take_profit,
            )

            events.append({
                **base,
                "trigger_date":
                    trigger_date,
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
                    evaluation["result"],
                "exit_date":
                    evaluation["exit_date"],
                "R":
                    evaluation["R"],
            })

    return pd.DataFrame(events)


# ============================================================
# SUMMARY
# ============================================================

def calculate_summary(
    trades
):
    """
    Produce summary by pullback level.
    """

    rows = []

    for pullback in PULLBACKS:

        level = -pullback

        subset = trades[
            trades["pullback"] == level
        ]

        total_events = len(subset)

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

            average_r = (
                resolved["R"]
                .mean()
            )

            total_r = (
                resolved["R"]
                .sum()
            )

            gross_profit = (
                wins["R"].sum()
                if not wins.empty
                else 0
            )

            gross_loss = abs(
                losses["R"].sum()
            ) if not losses.empty else 0

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
                f"-{pullback}%",

            "total_events":
                total_events,

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

            "insufficient_data":
                0,

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

    return pd.DataFrame(rows)


# ============================================================
# INVALID SL DIAGNOSTICS
# ============================================================

def build_invalid_sl_diagnostics(
    trades
):
    """
    Detailed report of all invalid SL setups.

    This is important before changing the
    stop-loss formula.
    """

    invalid = trades[
        trades["status"] == "INVALID_SL"
    ].copy()

    if invalid.empty:
        return invalid

    invalid = invalid[
        [
            "cycle_id",
            "pullback",
            "cycle_start",
            "cycle_end",
            "cycle_trough",
            "cycle_drawdown",
            "trigger_date",
            "entry",
            "stop_loss",
            "reference_high",
        ]
    ]

    return invalid


# ============================================================
# AMBIGUOUS DIAGNOSTICS
# ============================================================

def build_ambiguous_diagnostics(
    trades
):
    """
    Detailed report where both TP and SL were
    touched on the same daily candle.
    """

    ambiguous = trades[
        trades["result"] == "AMBIGUOUS"
    ].copy()

    if ambiguous.empty:
        return ambiguous

    ambiguous = ambiguous[
        [
            "cycle_id",
            "pullback",
            "trigger_date",
            "entry",
            "stop_loss",
            "take_profit",
            "exit_date",
            "reference_high",
            "cycle_drawdown",
        ]
    ]

    return ambiguous


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

        average_r = (
            resolved["R"].mean()
        )

        total_r = (
            resolved["R"].sum()
        )

        gross_profit = (
            wins["R"].sum()
            if not wins.empty
            else 0
        )

        gross_loss = abs(
            losses["R"].sum()
        ) if not losses.empty else 0

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
        f"Pullbacks: {PULLBACKS}"
    )

    print()

    # --------------------------------------------------------
    # LOAD MARKET DATA
    # --------------------------------------------------------

    df = get_historical_market_data(
        start_date=START_DATE
    )

    if df.empty:

        raise RuntimeError(
            "Historical market data unavailable."
        )

    print(
        "Market data:",
        df.index.min().date(),
        "→",
        df.index.max().date()
    )

    # --------------------------------------------------------
    # PREPARE DATA
    # --------------------------------------------------------

    df = prepare_market_data(
        df
    )

    # --------------------------------------------------------
    # DETECT CORRECTION CYCLES
    # --------------------------------------------------------

    cycles = detect_correction_cycles(
        df
    )

    print(
        "Correction cycles detected:",
        len(cycles)
    )

    # --------------------------------------------------------
    # BUILD EVENTS
    # --------------------------------------------------------

    trades = build_backtest_events(
        df,
        cycles
    )

    print(
        "Total pullback events:",
        len(trades)
    )

    # --------------------------------------------------------
    # RESULTS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # OVERALL
    # --------------------------------------------------------

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
            float
        ):

            if np.isnan(value):

                display_value = "N/A"

            else:

                display_value = round(
                    value,
                    3
                )

        else:

            display_value = value

        print(
            f"{label:<20}: {display_value}"
        )

    # --------------------------------------------------------
    # DIAGNOSTICS
    # --------------------------------------------------------

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

    if not invalid_sl.empty:

        print()
        print(
            "INVALID SL CASES"
        )

        print(
            invalid_sl.to_string(
                index=False
            )
        )

    if not ambiguous.empty:

        print()
        print(
            "AMBIGUOUS CASES"
        )

        print(
            ambiguous.to_string(
                index=False
            )
        )

    # --------------------------------------------------------
    # SAVE FILES
    # --------------------------------------------------------

    trades.to_csv(
        "backtest_trades.csv",
        index=False
    )

    pd.DataFrame(
        cycles
    ).to_csv(
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
