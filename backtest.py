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
            raise ValueError(
                f"Missing required column: {col}"
            )

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

    # ATR based on completed candles.
    df["atr14"] = (
        df["tr"]
        .rolling(ATR_PERIOD)
        .mean()
        .shift(1)
    )

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

def detect_correction_cycles(
    df,
    minimum_drawdown=-3.0
):

    cycles = []

    running_high = -np.inf
    reference_high = None
    reference_high_date = None

    in_correction = False
    start_date = None
    start_position = None

    for i, (date, row) in enumerate(
        df.iterrows()
    ):

        close = float(row["close"])

        # ----------------------------------------------------
        # New closing high
        # ----------------------------------------------------

        if close > running_high:

            # Recovery of previous correction
            if (
                in_correction
                and reference_high is not None
                and close >= reference_high
            ):

                cycle_df = df.iloc[
                    start_position:i + 1
                ]

                trough_date = cycle_df[
                    "low"
                ].idxmin()

                trough_price = float(
                    cycle_df.loc[
                        trough_date,
                        "low"
                    ]
                )

                maximum_drawdown = (
                    trough_price /
                    reference_high - 1
                ) * 100

                recovery_days = (
                    date - start_date
                ).days

                cycles.append({
                    "reference_high_date":
                        reference_high_date,

                    "reference_high":
                        reference_high,

                    "start_date":
                        start_date,

                    "trough_date":
                        trough_date,

                    "trough_price":
                        trough_price,

                    "maximum_drawdown_pct":
                        maximum_drawdown,

                    "recovery_date":
                        date,

                    "recovery_days":
                        recovery_days,
                })

                in_correction = False
                start_date = None
                start_position = None

            running_high = close

            if not in_correction:

                reference_high = close
                reference_high_date = date

        # ----------------------------------------------------
        # Drawdown
        # ----------------------------------------------------

        if reference_high is not None:

            drawdown = (
                close /
                reference_high - 1
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

        trough_date = cycle_df[
            "low"
        ].idxmin()

        trough_price = float(
            cycle_df.loc[
                trough_date,
                "low"
            ]
        )

        maximum_drawdown = (
            trough_price /
            reference_high - 1
        ) * 100

        cycles.append({
            "reference_high_date":
                reference_high_date,

            "reference_high":
                reference_high,

            "start_date":
                start_date,

            "trough_date":
                trough_date,

            "trough_price":
                trough_price,

            "maximum_drawdown_pct":
                maximum_drawdown,

            "recovery_date":
                None,

            "recovery_days":
                None,
        })

    return pd.DataFrame(cycles)


# ============================================================
# ADD PULLBACK EVENTS
# ============================================================

def add_pullback_events(df, cycles):

    events = []

    for cycle_id, cycle in enumerate(
        cycles.to_dict("records"),
        start=1
    ):

        reference_high = float(
            cycle["reference_high"]
        )

        start_date = cycle["start_date"]

        cycle_mask = (
            df.index >= start_date
        )

        if cycle["recovery_date"] is not None:

            cycle_mask &= (
                df.index <=
                cycle["recovery_date"]
            )

        cycle_df = df.loc[cycle_mask]

        for pullback in PULLBACKS:

            target_price = (
                reference_high *
                (1 - pullback / 100)
            )

            trigger = cycle_df[
                cycle_df["close"] <=
                target_price
            ]

            # ------------------------------------------------
            # No trigger
            # ------------------------------------------------

            if trigger.empty:

                events.append({
                    "cycle_id": cycle_id,
                    "pullback_level": pullback,
                    "reference_high":
                        reference_high,
                    "reference_high_date":
                        cycle[
                            "reference_high_date"
                        ],
                    "target_price":
                        target_price,
                    "trigger_date":
                        None,
                    "entry":
                        np.nan,
                    "atr14":
                        np.nan,
                    "previous_5_low":
                        np.nan,
                    "sl":
                        np.nan,
                    "tp":
                        np.nan,
                    "risk":
                        np.nan,
                    "setup_status":
                        "NO_TRIGGER",
                    "maximum_drawdown_pct":
                        cycle[
                            "maximum_drawdown_pct"
                        ],
                })

                continue

            # ------------------------------------------------
            # First trigger
            # ------------------------------------------------

            trigger_date = trigger.index[0]

            trigger_row = df.loc[
                trigger_date
            ]

            entry = float(
                trigger_row["close"]
            )

            atr = trigger_row["atr14"]

            previous_5_low = (
                trigger_row["previous_5_low"]
            )

            # ------------------------------------------------
            # Missing historical data
            # ------------------------------------------------

            if (
                pd.isna(atr)
                or pd.isna(previous_5_low)
            ):

                events.append({
                    "cycle_id": cycle_id,
                    "pullback_level": pullback,
                    "reference_high":
                        reference_high,
                    "reference_high_date":
                        cycle[
                            "reference_high_date"
                        ],
                    "target_price":
                        target_price,
                    "trigger_date":
                        trigger_date,
                    "entry":
                        entry,
                    "atr14":
                        atr,
                    "previous_5_low":
                        previous_5_low,
                    "sl":
                        np.nan,
                    "tp":
                        np.nan,
                    "risk":
                        np.nan,
                    "setup_status":
                        "INSUFFICIENT_DATA",
                    "maximum_drawdown_pct":
                        cycle[
                            "maximum_drawdown_pct"
                        ],
                })

                continue

            # ------------------------------------------------
            # Stop Loss
            # ------------------------------------------------

            sl = (
                float(previous_5_low)
                - 0.5 * float(atr)
            )

            risk = entry - sl

            # ------------------------------------------------
            # IMPORTANT:
            # Do NOT silently delete invalid setups.
            # ------------------------------------------------

            if risk <= 0:

                events.append({
                    "cycle_id": cycle_id,
                    "pullback_level": pullback,
                    "reference_high":
                        reference_high,
                    "reference_high_date":
                        cycle[
                            "reference_high_date"
                        ],
                    "target_price":
                        target_price,
                    "trigger_date":
                        trigger_date,
                    "entry":
                        entry,
                    "atr14":
                        float(atr),
                    "previous_5_low":
                        float(previous_5_low),
                    "sl":
                        sl,
                    "tp":
                        np.nan,
                    "risk":
                        risk,
                    "setup_status":
                        "INVALID_SL",
                    "maximum_drawdown_pct":
                        cycle[
                            "maximum_drawdown_pct"
                        ],
                })

                continue

            # ------------------------------------------------
            # Valid setup
            # ------------------------------------------------

            tp = (
                entry +
                RR * risk
            )

            events.append({
                "cycle_id": cycle_id,
                "pullback_level": pullback,
                "reference_high":
                    reference_high,
                "reference_high_date":
                    cycle[
                        "reference_high_date"
                    ],
                "target_price":
                    target_price,
                "trigger_date":
                    trigger_date,
                "entry":
                    entry,
                "atr14":
                    float(atr),
                "previous_5_low":
                    float(previous_5_low),
                "sl":
                    sl,
                "tp":
                    tp,
                "risk":
                    risk,
                "setup_status":
                    "VALID",
                "maximum_drawdown_pct":
                    cycle[
                        "maximum_drawdown_pct"
                    ],
            })

    return pd.DataFrame(events)


# ============================================================
# EVALUATE ONE TRADE
# ============================================================

def evaluate_trade(df, event):

    if event["setup_status"] != "VALID":

        return {
            "result":
                event["setup_status"],

            "exit_date":
                None,

            "exit_price":
                np.nan,

            "R":
                np.nan,
        }

    trigger_date = event["trigger_date"]

    future = df.loc[
        df.index > trigger_date
    ]

    entry = float(event["entry"])
    sl = float(event["sl"])
    tp = float(event["tp"])

    for date, row in future.iterrows():

        high = float(row["high"])
        low = float(row["low"])

        hit_tp = high >= tp
        hit_sl = low <= sl

        # ----------------------------------------------------
        # Same-bar ambiguity
        # ----------------------------------------------------

        if hit_tp and hit_sl:

            return {
                "result":
                    "AMBIGUOUS",

                "exit_date":
                    date,

                "exit_price":
                    np.nan,

                "R":
                    np.nan,
            }

        # ----------------------------------------------------
        # Stop
        # ----------------------------------------------------

        if hit_sl:

            return {
                "result":
                    "LOSS",

                "exit_date":
                    date,

                "exit_price":
                    sl,

                "R":
                    -1.0,
            }

        # ----------------------------------------------------
        # Target
        # ----------------------------------------------------

        if hit_tp:

            return {
                "result":
                    "WIN",

                "exit_date":
                    date,

                "exit_price":
                    tp,

                "R":
                    RR,
            }

    # --------------------------------------------------------
    # End of historical data
    # --------------------------------------------------------

    return {
        "result":
            "OPEN",

        "exit_date":
            None,

        "exit_price":
            np.nan,

        "R":
            np.nan,
    }


# ============================================================
# SUMMARY
# ============================================================

def calculate_summary(trades):

    rows = []

    for level in PULLBACKS:

        subset = trades[
            trades["pullback_level"] == level
        ]

        if subset.empty:
            continue

        valid = subset[
            subset["setup_status"] == "VALID"
        ]

        wins = (
            valid["result"] == "WIN"
        ).sum()

        losses = (
            valid["result"] == "LOSS"
        ).sum()

        ambiguous = (
            valid["result"] == "AMBIGUOUS"
        ).sum()

        open_trades = (
            valid["result"] == "OPEN"
        ).sum()

        invalid_sl = (
            subset["result"] == "INVALID_SL"
        ).sum()

        no_trigger = (
            subset["result"] == "NO_TRIGGER"
        ).sum()

        insufficient = (
            subset["result"] ==
            "INSUFFICIENT_DATA"
        ).sum()

        resolved = wins + losses

        if resolved > 0:

            win_rate = (
                wins /
                resolved *
                100
            )

            loss_rate = (
                losses /
                resolved *
                100
            )

            resolved_r = valid[
                valid["result"].isin(
                    ["WIN", "LOSS"]
                )
            ]["R"]

            average_r = (
                resolved_r.mean()
            )

            gross_profit = resolved_r[
                resolved_r > 0
            ].sum()

            gross_loss = abs(
                resolved_r[
                    resolved_r < 0
                ].sum()
            )

            profit_factor = (
                gross_profit /
                gross_loss
                if gross_loss > 0
                else np.nan
            )

        else:

            win_rate = np.nan
            loss_rate = np.nan
            average_r = np.nan
            profit_factor = np.nan

        rows.append({
            "pullback":
                f"-{level}%",

            "total_events":
                len(subset),

            "valid_setups":
                len(valid),

            "wins":
                wins,

            "losses":
                losses,

            "ambiguous":
                ambiguous,

            "open":
                open_trades,

            "invalid_sl":
                invalid_sl,

            "no_trigger":
                no_trigger,

            "insufficient_data":
                insufficient,

            "win_rate_pct":
                win_rate,

            "loss_rate_pct":
                loss_rate,

            "average_R":
                average_r,

            "expectancy_R":
                average_r,

            "profit_factor":
                profit_factor,
        })

    return pd.DataFrame(rows)


# ============================================================
# MAIN BACKTEST
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
    # Load data
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
        f"Market data: "
        f"{df.index.min().date()} "
        f"→ "
        f"{df.index.max().date()}"
    )

    # --------------------------------------------------------
    # Correction cycles
    # --------------------------------------------------------

    cycles = detect_correction_cycles(df)

    print(
        f"Correction cycles detected: "
        f"{len(cycles)}"
    )

    # --------------------------------------------------------
    # Events
    # --------------------------------------------------------

    events = add_pullback_events(
        df,
        cycles
    )

    print(
        f"Total pullback events: "
        f"{len(events)}"
    )

    # --------------------------------------------------------
    # Evaluate
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
    # Save detailed data
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

    summary = calculate_summary(
        trades
    )

    summary.to_csv(
        "backtest_summary.csv",
        index=False
    )

    print()
    print("RESULTS BY PULLBACK")
    print("-" * 60)

    print(
        summary.to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # Overall
    # --------------------------------------------------------

    valid = trades[
        trades["setup_status"] == "VALID"
    ]

    resolved = valid[
        valid["result"].isin(
            ["WIN", "LOSS"]
        )
    ]

    print()
    print("OVERALL")
    print("-" * 60)

    print(
        f"Total events    : "
        f"{len(trades)}"
    )

    print(
        f"Valid setups    : "
        f"{len(valid)}"
    )

    print(
        f"Resolved trades : "
        f"{len(resolved)}"
    )

    print(
        f"Invalid SL      : "
        f"{(trades['result'] == 'INVALID_SL').sum()}"
    )

    print(
        f"Ambiguous       : "
        f"{(trades['result'] == 'AMBIGUOUS').sum()}"
    )

    print(
        f"Open            : "
        f"{(trades['result'] == 'OPEN').sum()}"
    )

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
            wins /
            len(resolved) *
            100
        )

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
            gross_profit /
            gross_loss
            if gross_loss > 0
            else np.nan
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
            f"Profit Factor   : "
            f"{profit_factor:.2f}"
        )

    print()
    print("FILES CREATED")
    print("-" * 60)
    print("backtest_trades.csv")
    print("backtest_cycles.csv")
    print("backtest_summary.csv")


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    run_backtest()
