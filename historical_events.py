import pandas as pd
import numpy as np

from data import get_historical_market_data


# ============================================================
# SETTINGS
# ============================================================

PULLBACK_LEVELS = [
    -3,
    -5,
    -10,
    -20,
    -30,
]


# ============================================================
# PREPARE MARKET DATA
# ============================================================

def prepare_market_data(market_data):
    """
    Prepare daily market data and calculate:
        - running high
        - drawdown from running high
    """

    if market_data is None or market_data.empty:
        return pd.DataFrame()

    data = market_data.copy()

    required = [
        "high",
        "low",
        "close",
    ]

    for column in required:
        if column not in data.columns:
            return pd.DataFrame()

    data = data.sort_index()

    data["running_high"] = (
        data["close"].cummax()
    )

    data["drawdown_pct"] = (
        (
            data["close"]
            / data["running_high"]
        ) - 1
    ) * 100

    return data


# ============================================================
# DETECT CORRECTION CYCLES
# ============================================================

def detect_correction_cycles(
    market_data,
    minimum_drawdown=-3,
):
    """
    Detect complete correction cycles.

    A correction cycle starts when price closes at or below
    the minimum drawdown from the previous reference high.

    The cycle ends when price closes back at or above the
    reference high.

    Important:
        The reference high is frozen during the correction.
        Therefore a continuing decline does NOT create
        multiple independent corrections.
    """

    data = prepare_market_data(
        market_data
    )

    if data.empty:
        return pd.DataFrame()

    cycles = []

    in_correction = False

    reference_high = None
    reference_high_date = None
    start_date = None

    cycle_rows = []

    for date, row in data.iterrows():

        close = float(
            row["close"]
        )

        high = float(
            row["high"]
        )

        low = float(
            row["low"]
        )

        if not in_correction:

            current_high = float(
                row["running_high"]
            )

            current_high_date = (
                data.loc[
                    :date,
                    "close"
                ].idxmax()
            )

            drawdown = (
                (
                    close
                    / current_high
                ) - 1
            ) * 100

            if drawdown <= minimum_drawdown:

                in_correction = True

                reference_high = current_high

                reference_high_date = (
                    current_high_date
                )

                start_date = date

                cycle_rows = [
                    {
                        "date": date,
                        "close": close,
                        "high": high,
                        "low": low,
                    }
                ]

        else:

            cycle_rows.append(
                {
                    "date": date,
                    "close": close,
                    "high": high,
                    "low": low,
                }
            )

            # ------------------------------------------------
            # Correction recovered
            # ------------------------------------------------

            if close >= reference_high:

                cycle_df = pd.DataFrame(
                    cycle_rows
                )

                trough_position = (
                    cycle_df["low"]
                    .idxmin()
                )

                trough_row = (
                    cycle_df.loc[
                        trough_position
                    ]
                )

                trough_date = (
                    trough_row["date"]
                )

                trough_price = float(
                    trough_row["low"]
                )

                maximum_drawdown = (
                    (
                        trough_price
                        / reference_high
                    ) - 1
                ) * 100

                recovery_days = (
                    date
                    - start_date
                ).days

                cycles.append(
                    {
                        "reference_high_date":
                            reference_high_date,

                        "reference_high":
                            reference_high,

                        "start_date":
                            start_date,

                        "start_price":
                            float(
                                cycle_rows[0][
                                    "close"
                                ]
                            ),

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
                    }
                )

                in_correction = False

                reference_high = None
                reference_high_date = None
                start_date = None
                cycle_rows = []

    # --------------------------------------------------------
    # Handle an unfinished correction at the end of data
    # --------------------------------------------------------

    if in_correction and cycle_rows:

        cycle_df = pd.DataFrame(
            cycle_rows
        )

        trough_position = (
            cycle_df["low"]
            .idxmin()
        )

        trough_row = (
            cycle_df.loc[
                trough_position
            ]
        )

        trough_date = (
            trough_row["date"]
        )

        trough_price = float(
            trough_row["low"]
        )

        maximum_drawdown = (
            (
                trough_price
                / reference_high
            ) - 1
        ) * 100

        cycles.append(
            {
                "reference_high_date":
                    reference_high_date,

                "reference_high":
                    reference_high,

                "start_date":
                    start_date,

                "start_price":
                    float(
                        cycle_rows[0][
                            "close"
                        ]
                    ),

                "trough_date":
                    trough_date,

                "trough_price":
                    trough_price,

                "maximum_drawdown_pct":
                    maximum_drawdown,

                "recovery_date":
                    None,

                "recovery_days":
                    np.nan,
            }
        )

    if not cycles:
        return pd.DataFrame()

    return pd.DataFrame(
        cycles
    )


# ============================================================
# ADD PULLBACK LEVELS
# ============================================================

def add_pullback_levels(
    market_data,
    cycles,
    levels=PULLBACK_LEVELS,
):
    """
    For every correction cycle, identify the first date
    on which each pullback level was reached.

    Example:

        -3%
        -5%
        -10%
        -20%
        -30%

    These are entry-level observations inside the SAME
    correction cycle.
    """

    if cycles is None or cycles.empty:
        return pd.DataFrame()

    data = prepare_market_data(
        market_data
    )

    results = []

    for cycle_id, cycle in cycles.iterrows():

        start_date = cycle[
            "start_date"
        ]

        recovery_date = cycle[
            "recovery_date"
        ]

        reference_high = float(
            cycle[
                "reference_high"
            ]
        )

        if recovery_date is not None:
            period = data.loc[
                start_date:
                recovery_date
            ]
        else:
            period = data.loc[
                start_date:
            ]

        for level in levels:

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

            for date, row in period.iterrows():

                close = float(
                    row["close"]
                )

                drawdown = (
                    (
                        close
                        / reference_high
                    ) - 1
                ) * 100

                if drawdown <= level:

                    trigger_date = date
                    trigger_price = close
                    trigger_drawdown = drawdown

                    break

            if trigger_date is None:
                continue

            result = cycle.to_dict()

            result[
                "cycle_id"
            ] = int(cycle_id) + 1

            result[
                "level"
            ] = abs(level)

            result[
                "level_price"
            ] = threshold_price

            result[
                "trigger_date"
            ] = trigger_date

            result[
                "trigger_price"
            ] = trigger_price

            result[
                "trigger_drawdown_pct"
            ] = trigger_drawdown

            results.append(
                result
            )

    if not results:
        return pd.DataFrame()

    result_df = pd.DataFrame(
        results
    )

    columns = [
        "cycle_id",
        "level",
        "reference_high_date",
        "reference_high",
        "start_date",
        "start_price",
        "trigger_date",
        "trigger_price",
        "trigger_drawdown_pct",
        "trough_date",
        "trough_price",
        "maximum_drawdown_pct",
        "recovery_date",
        "recovery_days",
    ]

    return result_df[
        columns
    ].sort_values(
        [
            "start_date",
            "level",
        ]
    ).reset_index(
        drop=True
    )


# ============================================================
# BUILD HISTORICAL EVENTS
# ============================================================

def build_historical_events(
    start_date="2019-01-01",
):
    """
    Complete historical correction study.
    """

    market = get_historical_market_data(
        start_date=start_date
    )

    if market.empty:
        return pd.DataFrame()

    cycles = detect_correction_cycles(
        market,
        minimum_drawdown=-3,
    )

    if cycles.empty:
        return pd.DataFrame()

    events = add_pullback_levels(
        market,
        cycles,
        levels=PULLBACK_LEVELS,
    )

    return events


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print()
    print(
        "US500 HISTORICAL CORRECTION STUDY"
    )
    print(
        "================================="
    )

    events = build_historical_events(
        start_date="2019-01-01"
    )

    if events.empty:

        print(
            "ERROR: No historical correction events detected."
        )

    else:

        print()
        print(
            "TOTAL LEVEL EVENTS:",
            len(events)
        )

        print()
        print(
            "UNIQUE CORRECTION CYCLES:",
            events[
                "cycle_id"
            ].nunique()
        )

        print()
        print(
            "EVENTS BY PULLBACK LEVEL"
        )
        print(
            "------------------------"
        )

        counts = (
            events[
                "level"
            ]
            .value_counts()
            .sort_index()
        )

        for level, count in counts.items():

            print(
                f"-{level:.0f}%:",
                count,
                "events"
            )

        print()
        print(
            "CORRECTION CYCLES"
        )
        print(
            "-----------------"
        )

        cycle_columns = [
            "cycle_id",
            "reference_high_date",
            "reference_high",
            "start_date",
            "trough_date",
            "trough_price",
            "maximum_drawdown_pct",
            "recovery_date",
            "recovery_days",
        ]

        cycles_display = (
            events[
                cycle_columns
            ]
            .drop_duplicates(
                subset=[
                    "cycle_id"
                ]
            )
        )

        print(
            cycles_display.to_string(
                index=False
            )
        )

        print()
        print(
            "PULLBACK LEVEL EVENTS"
        )
        print(
            "---------------------"
        )

        event_columns = [
            "cycle_id",
            "level",
            "trigger_date",
            "trigger_price",
            "trigger_drawdown_pct",
            "trough_date",
            "maximum_drawdown_pct",
            "recovery_date",
            "recovery_days",
        ]

        print(
            events[
                event_columns
            ].to_string(
                index=False
            )
        )

        print()
        print(
            "HISTORICAL CORRECTION STUDY COMPLETE"
        )
