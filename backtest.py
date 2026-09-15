import pandas as pd
import numpy as np

from config import MARKET_TICKER
from data import load_market_data
from historical_events import detect_correction_cycles


# ============================================================
# SETTINGS
# ============================================================

RR = 4.0
PULLBACKS = [3, 5, 10, 20, 30]

ATR_PERIOD = 14
SL_LOOKBACK = 5
ATR_MULTIPLIER = 0.5


# ============================================================
# ATR
# ============================================================

def calculate_atr(df, period=14):
    """
    Calculate True Range and ATR.

    ATR is shifted by one day later so that the trigger day
    itself is NOT used in the ATR calculation.
    """

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

    atr = true_range.rolling(period).mean()

    # Exclude current trigger day
    atr = atr.shift(1)

    return atr


# ============================================================
# CREATE PULLBACK EVENTS
# ============================================================

def create_pullback_events(df, cycles):
    """
    For every correction cycle create one event for each
    pullback level.

    Levels:
        -3%
        -5%
        -10%
        -20%
        -30%

    If a level was never reached, result = NO_TRIGGER.
    """

    events = []

    for cycle in cycles:

        cycle_id = cycle.get("cycle_id")

        reference_high = cycle.get("reference_high")
        correction_start = cycle.get("start_date")
        correction_end = cycle.get("recovery_date")

        if reference_high is None:
            continue

        # Data inside correction cycle
        cycle_df = df.copy()

        if correction_start is not None:
            cycle_df = cycle_df[
                cycle_df.index >= pd.to_datetime(correction_start)
            ]

        if correction_end is not None:
            cycle_df = cycle_df[
                cycle_df.index <= pd.to_datetime(correction_end)
            ]

        for pullback in PULLBACKS:

            target_price = reference_high * (
                1 - pullback / 100
            )

            trigger_date = None
            trigger_row = None

            # Find first closing price reaching the pullback
            for date, row in cycle_df.iterrows():

                close = row["Close"]

                if close <= target_price:
                    trigger_date = date
                    trigger_row = row
                    break

            # ------------------------------------------------
            # NO TRIGGER
            # ------------------------------------------------

            if trigger_date is None:

                events.append({
                    "cycle_id": cycle_id,
                    "pullback_level": -pullback,
                    "reference_high": reference_high,
                    "target_price": target_price,
                    "trigger_date": None,
                    "entry": None,
                    "previous_5_low": None,
                    "atr14": None,
                    "sl": None,
                    "tp": None,
                    "risk": None,
                    "result": "NO_TRIGGER",
                    "exit_date": None,
                    "R": None,
                    "maximum_drawdown_pct": None,
                })

                continue

            # ------------------------------------------------
            # ENTRY
            # ------------------------------------------------

            entry = float(trigger_row["Close"])

            # Previous 5 completed candles
            previous_data = df.loc[
                df.index < trigger_date
            ].tail(SL_LOOKBACK)

            if len(previous_data) < SL_LOOKBACK:

                events.append({
                    "cycle_id": cycle_id,
                    "pullback_level": -pullback,
                    "reference_high": reference_high,
                    "target_price": target_price,
                    "trigger_date": trigger_date,
                    "entry": entry,
                    "previous_5_low": None,
                    "atr14": None,
                    "sl": None,
                    "tp": None,
                    "risk": None,
                    "result": "INSUFFICIENT_DATA",
                    "exit_date": None,
                    "R": None,
                    "maximum_drawdown_pct": None,
                })

                continue

            previous_5_low = float(
                previous_data["Low"].min()
            )

            # ATR already excludes trigger day
            atr14 = df.loc[trigger_date, "atr14"]

            # ------------------------------------------------
            # INVALID ATR
            # ------------------------------------------------

            if pd.isna(atr14):

                events.append({
                    "cycle_id": cycle_id,
                    "pullback_level": -pullback,
                    "reference_high": reference_high,
                    "target_price": target_price,
                    "trigger_date": trigger_date,
                    "entry": entry,
                    "previous_5_low": previous_5_low,
                    "atr14": None,
                    "sl": None,
                    "tp": None,
                    "risk": None,
                    "result": "INSUFFICIENT_DATA",
                    "exit_date": None,
                    "R": None,
                    "maximum_drawdown_pct": None,
                })

                continue

            atr14 = float(atr14)

            # ------------------------------------------------
            # STOP LOSS
            # ------------------------------------------------

            sl = previous_5_low - (
                ATR_MULTIPLIER * atr14
            )

            risk = entry - sl

            # ------------------------------------------------
            # INVALID SL
            # ------------------------------------------------

            if risk <= 0:

                events.append({
                    "cycle_id": cycle_id,
                    "pullback_level": -pullback,
                    "reference_high": reference_high,
                    "target_price": target_price,
                    "trigger_date": trigger_date,
                    "entry": entry,
                    "previous_5_low": previous_5_low,
                    "atr14": atr14,
                    "sl": sl,
                    "tp": None,
                    "risk": risk,
                    "result": "INVALID_SL",
                    "exit_date": None,
                    "R": None,
                    "maximum_drawdown_pct": None,
                })

                continue

            # ------------------------------------------------
            # TAKE PROFIT
            # ------------------------------------------------

            tp = entry + (
                RR * risk
            )

            # ------------------------------------------------
            # EVALUATE TRADE
            # ------------------------------------------------

            result = evaluate_trade(
                df=df,
                trigger_date=trigger_date,
                entry=entry,
                sl=sl,
                tp=tp,
            )

            result["cycle_id"] = cycle_id
            result["pullback_level"] = -pullback
            result["reference_high"] = reference_high
            result["target_price"] = target_price
            result["trigger_date"] = trigger_date
            result["entry"] = entry
            result["previous_5_low"] = previous_5_low
            result["atr14"] = atr14
            result["sl"] = sl
            result["tp"] = tp
            result["risk"] = risk

            events.append(result)

    return events


# ============================================================
# EVALUATE TRADE
# ============================================================

def evaluate_trade(
    df,
    trigger_date,
    entry,
    sl,
    tp,
):
    """
    Long trade.

    Entry = trigger day's closing price.

    Starting from the following completed Daily candle:

        Low <= SL  -> LOSS
        High >= TP -> WIN

    If both SL and TP are touched during the same candle,
    the result is AMBIGUOUS because Daily OHLC does not reveal
    which level was touched first.
    """

    future_df = df.loc[
        df.index > trigger_date
    ]

    for date, row in future_df.iterrows():

        high = float(row["High"])
        low = float(row["Low"])

        hit_sl = low <= sl
        hit_tp = high >= tp

        # ----------------------------------------------------
        # BOTH LEVELS TOUCHED
        # ----------------------------------------------------

        if hit_sl and hit_tp:

            return {
                "result": "AMBIGUOUS",
                "exit_date": date,
                "R": None,
                "maximum_drawdown_pct": None,
            }

        # ----------------------------------------------------
        # STOP LOSS
        # ----------------------------------------------------

        if hit_sl:

            return {
                "result": "LOSS",
                "exit_date": date,
                "R": -1.0,
                "maximum_drawdown_pct": None,
            }

        # ----------------------------------------------------
        # TAKE PROFIT
        # ----------------------------------------------------

        if hit_tp:

            return {
                "result": "WIN",
                "exit_date": date,
                "R": RR,
                "maximum_drawdown_pct": None,
            }

    # --------------------------------------------------------
    # TRADE STILL OPEN
    # --------------------------------------------------------

    return {
        "result": "OPEN",
        "exit_date": None,
        "R": None,
        "maximum_drawdown_pct": None,
    }


# ============================================================
# SUMMARY
# ============================================================

def calculate_summary(trades):

    rows = []

    for pullback in PULLBACKS:

        level = -pullback

        level_trades = [
            t for t in trades
            if t["pullback_level"] == level
        ]

        total_events = len(level_trades)

        valid = [
            t for t in level_trades
            if t["result"] in [
                "WIN",
                "LOSS",
                "AMBIGUOUS",
                "OPEN"
            ]
        ]

        resolved = [
            t for t in level_trades
            if t["result"] in [
                "WIN",
                "LOSS"
            ]
        ]

        wins = [
            t for t in level_trades
            if t["result"] == "WIN"
        ]

        losses = [
            t for t in level_trades
            if t["result"] == "LOSS"
        ]

        ambiguous = [
            t for t in level_trades
            if t["result"] == "AMBIGUOUS"
        ]

        open_trades = [
            t for t in level_trades
            if t["result"] == "OPEN"
        ]

        invalid_sl = [
            t for t in level_trades
            if t["result"] == "INVALID_SL"
        ]

        no_trigger = [
            t for t in level_trades
            if t["result"] == "NO_TRIGGER"
        ]

        insufficient_data = [
            t for t in level_trades
            if t["result"] == "INSUFFICIENT_DATA"
        ]

        win_rate = (
            len(wins) / len(resolved) * 100
            if resolved
            else np.nan
        )

        loss_rate = (
            len(losses) / len(resolved) * 100
            if resolved
            else np.nan
        )

        r_values = [
            t["R"]
            for t in resolved
            if t["R"] is not None
        ]

        average_r = (
            np.mean(r_values)
            if r_values
            else np.nan
        )

        total_r = (
            np.sum(r_values)
            if r_values
            else 0
        )

        expectancy_r = (
            total_r / len(resolved)
            if resolved
            else np.nan
        )

        gross_profit = sum(
            t["R"]
            for t in wins
            if t["R"] is not None
        )

        gross_loss = abs(
            sum(
                t["R"]
                for t in losses
                if t["R"] is not None
            )
        )

        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else np.nan
        )

        rows.append({

            "pullback": f"-{pullback}%",

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
                len(insufficient_data),

            "win_rate_pct":
                win_rate,

            "loss_rate_pct":
                loss_rate,

            "average_R":
                average_r,

            "expectancy_R":
                expectancy_r,

            "profit_factor":
                profit_factor,
        })

    return pd.DataFrame(rows)


# ============================================================
# DIAGNOSTICS
# ============================================================

def print_diagnostics(trades):

    # ========================================================
    # INVALID SL
    # ========================================================

    print("\n")
    print("=" * 80)
    print("DIAGNOSTICS — INVALID SL")
    print("=" * 80)

    invalid = [
        t for t in trades
        if t["result"] == "INVALID_SL"
    ]

    if not invalid:

        print("No INVALID_SL cases.")

    else:

        for i, t in enumerate(invalid, 1):

            print("\n" + "-" * 80)
            print(f"INVALID CASE #{i}")
            print("-" * 80)

            print(
                f"Cycle ID           : "
                f"{t.get('cycle_id')}"
            )

            print(
                f"Pullback           : "
                f"{t.get('pullback_level')}%"
            )

            print(
                f"Trigger date       : "
                f"{t.get('trigger_date')}"
            )

            print(
                f"Reference high     : "
                f"{t.get('reference_high')}"
            )

            print(
                f"Target price       : "
                f"{t.get('target_price')}"
            )

            print(
                f"Entry              : "
                f"{t.get('entry')}"
            )

            print(
                f"Previous 5 Low     : "
                f"{t.get('previous_5_low')}"
            )

            print(
                f"ATR(14)             : "
                f"{t.get('atr14')}"
            )

            print(
                f"SL                 : "
                f"{t.get('sl')}"
            )

            print(
                f"Risk               : "
                f"{t.get('risk')}"
            )

            print(
                f"Maximum drawdown   : "
                f"{t.get('maximum_drawdown_pct')}%"
            )

    # ========================================================
    # AMBIGUOUS
    # ========================================================

    print("\n")
    print("=" * 80)
    print("DIAGNOSTICS — AMBIGUOUS")
    print("=" * 80)

    ambiguous = [
        t for t in trades
        if t["result"] == "AMBIGUOUS"
    ]

    if not ambiguous:

        print("No AMBIGUOUS cases.")

    else:

        for i, t in enumerate(ambiguous, 1):

            print("\n" + "-" * 80)
            print(f"AMBIGUOUS CASE #{i}")
            print("-" * 80)

            print(
                f"Cycle ID           : "
                f"{t.get('cycle_id')}"
            )

            print(
                f"Pullback           : "
                f"{t.get('pullback_level')}%"
            )

            print(
                f"Trigger date       : "
                f"{t.get('trigger_date')}"
            )

            print(
                f"Reference high     : "
                f"{t.get('reference_high')}"
            )

            print(
                f"Entry              : "
                f"{t.get('entry')}"
            )

            print(
                f"SL                 : "
                f"{t.get('sl')}"
            )

            print(
                f"TP                 : "
                f"{t.get('tp')}"
            )

            print(
                f"Exit date          : "
                f"{t.get('exit_date')}"
            )

    # ========================================================
    # SAVE DIAGNOSTIC FILES
    # ========================================================

    pd.DataFrame(invalid).to_csv(
        "backtest_invalid_sl.csv",
        index=False
    )

    pd.DataFrame(ambiguous).to_csv(
        "backtest_ambiguous.csv",
        index=False
    )

    print("\n")
    print("=" * 80)
    print("DIAGNOSTIC FILES")
    print("=" * 80)

    print("backtest_invalid_sl.csv")
    print("backtest_ambiguous.csv")


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n")
    print("=" * 60)
    print("US500 BACKTEST")
    print("=" * 60)

    print(f"Ticker: {MARKET_TICKER}")
    print(f"Start: 2019-01-01")
    print(f"RR: 1:{RR}")
    print(f"Pullbacks: {PULLBACKS}")

    # --------------------------------------------------------
    # LOAD DATA
    # --------------------------------------------------------

    df = load_market_data()

    if df is None or len(df) == 0:

        print("\nERROR: No market data available.")
        return

    df = df.copy()

    df.index = pd.to_datetime(df.index)

    df = df.sort_index()

    print(
        f"\nMarket data: "
        f"{df.index.min().date()} "
        f"→ "
        f"{df.index.max().date()}"
    )

    # --------------------------------------------------------
    # VALIDATE OHLC
    # --------------------------------------------------------

    required_columns = [
        "Open",
        "High",
        "Low",
        "Close",
    ]

    missing = [
        c for c in required_columns
        if c not in df.columns
    ]

    if missing:

        print(
            "\nERROR: Missing OHLC columns:",
            missing
        )

        return

    # --------------------------------------------------------
    # ATR
    # --------------------------------------------------------

    df["atr14"] = calculate_atr(
        df,
        ATR_PERIOD
    )

    # --------------------------------------------------------
    # CORRECTION CYCLES
    # --------------------------------------------------------

    cycles = detect_correction_cycles(df)

    print(
        f"Correction cycles detected: "
        f"{len(cycles)}"
    )

    # --------------------------------------------------------
    # EVENTS
    # --------------------------------------------------------

    trades = create_pullback_events(
        df,
        cycles
    )

    print(
        f"Total pullback events: "
        f"{len(trades)}"
    )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary = calculate_summary(
        trades
    )

    print("\n")
    print("RESULTS BY PULLBACK")
    print("-" * 80)

    print(
        summary.to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # OVERALL
    # --------------------------------------------------------

    resolved = [
        t for t in trades
        if t["result"] in [
            "WIN",
            "LOSS"
        ]
    ]

    wins = [
        t for t in trades
        if t["result"] == "WIN"
    ]

    losses = [
        t for t in trades
        if t["result"] == "LOSS"
    ]

    ambiguous = [
        t for t in trades
        if t["result"] == "AMBIGUOUS"
    ]

    invalid_sl = [
        t for t in trades
        if t["result"] == "INVALID_SL"
    ]

    open_trades = [
        t for t in trades
        if t["result"] == "OPEN"
    ]

    valid_setups = [
        t for t in trades
        if t["result"] in [
            "WIN",
            "LOSS",
            "AMBIGUOUS",
            "OPEN"
        ]
    ]

    r_values = [
        t["R"]
        for t in resolved
        if t["R"] is not None
    ]

    total_r = (
        sum(r_values)
        if r_values
        else 0
    )

    average_r = (
        np.mean(r_values)
        if r_values
        else np.nan
    )

    win_rate = (
        len(wins) /
        len(resolved) *
        100
        if resolved
        else np.nan
    )

    gross_profit = sum(
        t["R"]
        for t in wins
        if t["R"] is not None
    )

    gross_loss = abs(
        sum(
            t["R"]
            for t in losses
            if t["R"] is not None
        )
    )

    profit_factor = (
        gross_profit / gross_loss
        if gross_loss > 0
        else np.nan
    )

    print("\n")
    print("OVERALL")
    print("-" * 80)

    print(
        f"Total events    : "
        f"{len(trades)}"
    )

    print(
        f"Valid setups    : "
        f"{len(valid_setups)}"
    )

    print(
        f"Resolved trades : "
        f"{len(resolved)}"
    )

    print(
        f"Invalid SL      : "
        f"{len(invalid_sl)}"
    )

    print(
        f"Ambiguous       : "
        f"{len(ambiguous)}"
    )

    print(
        f"Open            : "
        f"{len(open_trades)}"
    )

    print(
        f"Wins            : "
        f"{len(wins)}"
    )

    print(
        f"Losses          : "
        f"{len(losses)}"
    )

    print(
        f"Win rate        : "
        f"{win_rate:.2f}%"
    )

    print(
        f"Average R       : "
        f"{average_r:.3f}"
    )

    print(
        f"Total R         : "
        f"{total_r:.2f}"
    )

    print(
        f"Profit Factor   : "
        f"{profit_factor:.2f}"
    )

    # --------------------------------------------------------
    # SAVE MAIN FILES
    # --------------------------------------------------------

    trades_df = pd.DataFrame(
        trades
    )

    trades_df.to_csv(
        "backtest_trades.csv",
        index=False
    )

    cycles_df = pd.DataFrame(
        cycles
    )

    cycles_df.to_csv(
        "backtest_cycles.csv",
        index=False
    )

    summary.to_csv(
        "backtest_summary.csv",
        index=False
    )

    # --------------------------------------------------------
    # DIAGNOSTICS
    # --------------------------------------------------------

    print_diagnostics(
        trades
    )

    # --------------------------------------------------------
    # FILES
    # --------------------------------------------------------

    print("\n")
    print("=" * 80)
    print("FILES CREATED")
    print("=" * 80)

    print("backtest_trades.csv")
    print("backtest_cycles.csv")
    print("backtest_summary.csv")
    print("backtest_invalid_sl.csv")
    print("backtest_ambiguous.csv")


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
