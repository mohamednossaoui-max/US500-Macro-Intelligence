import pandas as pd
import numpy as np

from data import get_historical_market_data


# ============================================================
# CONFIGURATION
# ============================================================

TICKER = "^GSPC"
START_DATE = "2019-01-01"

PULLBACKS = [3, 5, 10, 20, 30]

RR = 4.0
ATR_PERIOD = 14
SL_LOOKBACK = 5

# Entry convention:
# The entry is the CLOSE of the first day that reaches
# the selected pullback level.
ENTRY_MODE = "trigger_close"


# ============================================================
# PREPARE DATA
# ============================================================

def prepare_data(df):
    df = df.copy()

    df.columns = [str(c).lower() for c in df.columns]

    required = ["open", "high", "low", "close"]

    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    df = df.sort_index()
    df = df[~df.index.duplicated(keep="first")]

    # --------------------------------------------------------
    # True Range
    # --------------------------------------------------------

    previous_close = df["close"].shift(1)

    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - previous_close).abs()
    tr3 = (df["low"] - previous_close).abs()

    df["tr"] = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    # ATR uses only information available before the trigger day.
    df["atr14"] = df["tr"].rolling(ATR_PERIOD).mean()

    # --------------------------------------------------------
    # Previous 5 completed candles
    # --------------------------------------------------------

    df["previous_5_low"] = (
        df["low"]
        .shift(1)
        .rolling(SL_LOOKBACK)
        .min()
    )

    return df


# ============================================================
# DETECT CORRECTION CYCLES
# ============================================================

def detect_correction_cycles(df, minimum_drawdown=-3.0):

    cycles = []

    running_high = -np.inf
    reference_high = None
    reference_high_date = None

    in_correction = False
    start_date = None
    start_position = None

    for i, (date, row) in enumerate(df.iterrows()):

        close = float(row["close"])
        low = float(row["low"])

        # ----------------------------------------------------
        # New all-time / running closing high
        # ----------------------------------------------------

        if close > running_high:

            # If we are in a correction and price recovered
            # above the previous reference high, close cycle.
            if in_correction and reference_high is not None:

                if close >= reference_high:

                    cycle_df = df.iloc[start_position:i + 1]

                    trough_position = cycle_df["low"].idxmin()
                    trough_price = float(
                        cycle_df.loc[trough_position, "low"]
                    )

                    maximum_drawdown = (
                        (trough_price / reference_high) - 1
                    ) * 100

                    recovery_days = (
                        date - start_date
                    ).days

                    cycles.append({
                        "reference_high_date": reference_high_date,
                        "reference_high": reference_high,
                        "start_date": start_date,
                        "trough_date": trough_position,
                        "trough_price": trough_price,
                        "maximum_drawdown_pct": maximum_drawdown,
                        "recovery_date": date,
                        "recovery_days": recovery_days,
                    })

                    in_correction = False
                    start_date = None
                    start_position = None

            running_high = close

            if not in_correction:
                reference_high = close
                reference_high_date = date

        # ----------------------------------------------------
        # Check drawdown from reference high
        # ----------------------------------------------------

        if reference_high is not None:

            drawdown = (
                (close / reference_high) - 1
            ) * 100

            if (
                not in_correction
                and drawdown <= minimum_drawdown
            ):
                in_correction = True
                start_date = date
                start_position = i

    # --------------------------------------------------------
    # Unfinished final correction
    # --------------------------------------------------------

    if in_correction:

        cycle_df = df.iloc[start_position:]

        trough_position = cycle_df["low"].idxmin()
        trough_price = float(
            cycle_df.loc[trough_position, "low"]
        )

        maximum_drawdown = (
            (trough_price / reference_high) - 1
        ) * 100

        cycles.append({
            "reference_high_date": reference_high_date,
            "reference_high": reference_high,
            "start_date": start_date,
            "trough_date": trough_position,
            "trough_price": trough_price,
            "maximum_drawdown_pct": maximum_drawdown,
            "recovery_date": None,
            "recovery_days": None,
        })

    return pd.DataFrame(cycles)


# ============================================================
# ADD PULLBACK LEVEL EVENTS
# ============================================================

def add_pullback_events(df, cycles):

    events = []

    for cycle_id, cycle in enumerate(
        cycles.to_dict("records"),
        start=1
    ):

        reference_high = cycle["reference_high"]
        start_date = cycle["start_date"]

        cycle_mask = df.index >= start_date

        if cycle["recovery_date"] is not None:
            cycle_mask &= (
                df.index <= cycle["recovery_date"]
            )

        cycle_df = df.loc[cycle_mask]

        for pullback in PULLBACKS:

            target_price = (
                reference_high *
                (1 - pullback / 100)
            )

            trigger = cycle_df[
                cycle_df["close"] <= target_price
            ]

            if trigger.empty:
                continue

            trigger_date = trigger.index[0]
            trigger_row = df.loc[trigger_date]

            entry = float(trigger_row["close"])

            atr = trigger_row["atr14"]
            previous_5_low = trigger_row["previous_5_low"]

            # We need enough completed candles
            # before the entry day.
            if pd.isna(atr) or pd.isna(previous_5_low):
                continue

            sl = (
                float(previous_5_low)
                - 0.5 * float(atr)
            )

            risk = entry - sl

            # Invalid setup
            if risk <= 0:
                continue

            tp = entry + RR * risk

            events.append({
                "cycle_id": cycle_id,
                "reference_high_date": cycle[
                    "reference_high_date"
                ],
                "reference_high": reference_high,
                "pullback_level": pullback,
                "target_price": target_price,
                "trigger_date": trigger_date,
                "entry": entry,
                "atr14": float(atr),
                "previous_5_low": float(previous_5_low),
                "sl": sl,
                "tp": tp,
                "risk": risk,
                "maximum_drawdown_pct": cycle[
                    "maximum_drawdown_pct"
                ],
            })

    return pd.DataFrame(events)


# ============================================================
# TEST ONE TRADE
# ============================================================

def evaluate_trade(df, event):

    trigger_date = event["trigger_date"]

    future = df.loc[df.index > trigger_date]

    entry = event["entry"]
    sl = event["sl"]
    tp = event["tp"]

    for date, row in future.iterrows():

        high = float(row["high"])
        low = float(row["low"])

        hit_tp = high >= tp
        hit_sl = low <= sl

        # ----------------------------------------------------
        # Both TP and SL reached during same daily candle.
        # We cannot know which came first.
        # ----------------------------------------------------

        if hit_tp and hit_sl:

            return {
                "result": "AMBIGUOUS",
                "exit_date": date,
                "exit_price": np.nan,
                "R": np.nan,
            }

        # ----------------------------------------------------
        # Stop Loss
        # ----------------------------------------------------

        if hit_sl:

            return {
                "result": "LOSS",
                "exit_date": date,
                "exit_price": sl,
                "R": -1.0,
            }

        # ----------------------------------------------------
        # Take Profit
        # ----------------------------------------------------

        if hit_tp:

            return {
                "result": "WIN",
                "exit_date": date,
                "exit_price": tp,
                "R": RR,
            }

    # --------------------------------------------------------
    # Still open at end of dataset
    # --------------------------------------------------------

    return {
        "result": "OPEN",
        "exit_date": None,
        "exit_price": np.nan,
        "R": np.nan,
    }


# ============================================================
# RUN BACKTEST
# ============================================================

def run_backtest():

    print("US500 BACKTEST")
    print("=" * 60)

    print(f"Ticker: {TICKER}")
    print(f"Start: {START_DATE}")
    print(f"RR: 1:{RR}")
    print(f"Pullbacks: {PULLBACKS}")
    print()

    # --------------------------------------------------------
    # Load market data
    # --------------------------------------------------------

    df = get_historical_market_data(
        ticker=TICKER,
        start_date=START_DATE
    )

    if df is None or df.empty:
        raise ValueError(
            "No historical market data available."
        )

    df = prepare_data(df)

    print(
        f"Market data: {df.index.min().date()} "
        f"→ {df.index.max().date()}"
    )

    # --------------------------------------------------------
    # Correction cycles
    # --------------------------------------------------------

    cycles = detect_correction_cycles(df)

    print(
        f"Correction cycles detected: {len(cycles)}"
    )

    # --------------------------------------------------------
    # Pullback events
    # --------------------------------------------------------

    events = add_pullback_events(
        df,
        cycles
    )

    if events.empty:
        print("No valid pullback events found.")
        return

    print(
        f"Trade setups detected: {len(events)}"
    )

    # --------------------------------------------------------
    # Evaluate every trade independently
    # --------------------------------------------------------

    results = []

    for _, event in events.iterrows():

        outcome = evaluate_trade(
            df,
            event
        )

        result = event.to_dict()
        result.update(outcome)

        results.append(result)

    trades = pd.DataFrame(results)

    # --------------------------------------------------------
    # Save detailed results
    # --------------------------------------------------------

    trades.to_csv(
        "backtest_trades.csv",
        index=False
    )

    cycles.to_csv(
        "backtest_cycles.csv",
        index=False
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("RESULTS BY PULLBACK")
    print("-" * 60)

    summary_rows = []

    for level in PULLBACKS:

        subset = trades[
            trades["pullback_level"] == level
        ]

        if subset.empty:
            continue

        wins = (
            subset["result"] == "WIN"
        ).sum()

        losses = (
            subset["result"] == "LOSS"
        ).sum()

        ambiguous = (
            subset["result"] == "AMBIGUOUS"
        ).sum()

        open_trades = (
            subset["result"] == "OPEN"
        ).sum()

        resolved = wins + losses

        win_rate = (
            wins / resolved * 100
            if resolved > 0
            else np.nan
        )

        loss_rate = (
            losses / resolved * 100
            if resolved > 0
            else np.nan
        )

        resolved_r = subset[
            subset["result"].isin(
                ["WIN", "LOSS"]
            )
        ]["R"]

        average_r = (
            resolved_r.mean()
            if not resolved_r.empty
            else np.nan
        )

        expectancy = average_r

        gross_profit = resolved_r[
            resolved_r > 0
        ].sum()

        gross_loss = abs(
            resolved_r[
                resolved_r < 0
            ].sum()
        )

        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else np.nan
        )

        summary_rows.append({
            "pullback": f"-{level}%",
            "trades": len(subset),
            "wins": wins,
            "losses": losses,
            "ambiguous": ambiguous,
            "open": open_trades,
            "win_rate_pct": win_rate,
            "loss_rate_pct": loss_rate,
            "average_R": average_r,
            "expectancy_R": expectancy,
            "profit_factor": profit_factor,
        })

    summary = pd.DataFrame(summary_rows)

    print(
        summary.to_string(
            index=False
        )
    )

    summary.to_csv(
        "backtest_summary.csv",
        index=False
    )

    # --------------------------------------------------------
    # Overall results
    # --------------------------------------------------------

    resolved = trades[
        trades["result"].isin(
            ["WIN", "LOSS"]
        )
    ]

    if not resolved.empty:

        wins = (
            resolved["result"] == "WIN"
        ).sum()

        losses = (
            resolved["result"] == "LOSS"
        ).sum()

        total_r = resolved["R"].sum()

        average_r = resolved["R"].mean()

        win_rate = (
            wins / len(resolved)
        ) * 100

        gross_profit = resolved.loc[
            resolved["R"] > 0,
            "R"
        ].sum()

        gross_loss = abs(
            resolved.loc[
                resolved["R"] < 0,
                "R"
            ].sum()
        )

        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else np.nan
        )

        print()
        print("OVERALL")
        print("-" * 60)
        print(
            f"Resolved trades : {len(resolved)}"
        )
        print(
            f"Wins            : {wins}"
        )
        print(
            f"Losses          : {losses}"
        )
        print(
            f"Win rate        : {win_rate:.2f}%"
        )
        print(
            f"Average R       : {average_r:.3f}"
        )
        print(
            f"Total R         : {total_r:.2f}"
        )
        print(
            f"Profit Factor   : {profit_factor:.2f}"
        )

    print()
    print("FILES CREATED")
    print("-" * 60)
    print("backtest_trades.csv")
    print("backtest_cycles.csv")
    print("backtest_summary.csv")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    run_backtest()
