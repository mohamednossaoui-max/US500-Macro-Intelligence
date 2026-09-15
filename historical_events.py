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
# FIND HISTORICAL PULLBACKS
# ============================================================

def detect_pullbacks(
    market_data,
    levels=PULLBACK_LEVELS,
):
    """
    Detect historical US500 pullbacks from running highs.

    A pullback is measured from the highest closing price
    reached before the correction.

    Levels:
        -3%
        -5%
        -10%
        -20%
        -30%
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

    # --------------------------------------------------------
    # Running high
    # --------------------------------------------------------

    data["running_high"] = (
        data["close"].cummax()
    )

    # --------------------------------------------------------
    # Drawdown from running high
    # --------------------------------------------------------

    data["drawdown_pct"] = (
        (
            data["close"]
            / data["running_high"]
        ) - 1
    ) * 100

    events = []

    # --------------------------------------------------------
    # Process each pullback level
    # --------------------------------------------------------

    for level in levels:

        threshold = float(level)

        below = (
            data["drawdown_pct"]
            <= threshold
        )

        if not below.any():
            continue

        # ----------------------------------------------------
        # Detect first day crossing the level
        # ----------------------------------------------------

        previous = below.shift(
            1,
            fill_value=False
        )

        crossings = data[
            below & ~previous
        ]

        for date, row in crossings.iterrows():

            reference_high = float(
                row["running_high"]
            )

            drawdown = float(
                row["drawdown_pct"]
            )

            events.append(
                {
                    "level": abs(threshold),
                    "date": date,
                    "reference_high": reference_high,
                    "entry_price": float(
                        row["close"]
                    ),
                    "drawdown_pct": drawdown,
                }
            )

    if not events:
        return pd.DataFrame()

    events_df = pd.DataFrame(
        events
    )

    events_df = events_df.sort_values(
        [
            "date",
            "level",
        ]
    ).reset_index(
        drop=True
    )

    return events_df


# ============================================================
# EVENT EXTREMES
# ============================================================

def add_event_extremes(
    market_data,
    events,
):
    """
    Add the lowest price reached after
    each pullback level was triggered.
    """

    if events is None or events.empty:
        return pd.DataFrame()

    data = market_data.sort_index()

    results = []

    for _, event in events.iterrows():

        event_date = event["date"]

        future = data.loc[
            event_date:
        ]

        if future.empty:
            continue

        trough_date = future[
            "low"
        ].idxmin()

        trough_price = float(
            future.loc[
                trough_date,
                "low"
            ]
        )

        reference_high = float(
            event["reference_high"]
        )

        trough_drawdown = (
            (
                trough_price
                / reference_high
            ) - 1
        ) * 100

        result = event.to_dict()

        result[
            "trough_date"
        ] = trough_date

        result[
            "trough_price"
        ] = trough_price

        result[
            "trough_drawdown_pct"
        ] = trough_drawdown

        results.append(
            result
        )

    if not results:
        return pd.DataFrame()

    return pd.DataFrame(
        results
    )


# ============================================================
# RECOVERY DATE
# ============================================================

def add_recovery_dates(
    market_data,
    events,
):
    """
    Find the first date after the trough when
    the market recovers back to the reference high.
    """

    if events is None or events.empty:
        return pd.DataFrame()

    data = market_data.sort_index()

    results = []

    for _, event in events.iterrows():

        reference_high = float(
            event["reference_high"]
        )

        trough_date = event[
            "trough_date"
        ]

        future = data.loc[
            trough_date:
        ]

        recovery_date = None

        for date, row in future.iterrows():

            close = float(
                row["close"]
            )

            if close >= reference_high:

                recovery_date = date

                break

        result = event.to_dict()

        result[
            "recovery_date"
        ] = recovery_date

        if recovery_date is not None:

            result[
                "recovery_days"
            ] = (
                recovery_date
                - trough_date
            ).days

        else:

            result[
                "recovery_days"
            ] = np.nan

        results.append(
            result
        )

    if not results:
        return pd.DataFrame()

    return pd.DataFrame(
        results
    )


# ============================================================
# BUILD HISTORICAL EVENTS
# ============================================================

def build_historical_events(
    start_date="2019-01-01",
):
    """
    Complete historical pullback detection pipeline.
    """

    market = get_historical_market_data(
        start_date=start_date
    )

    if market.empty:
        return pd.DataFrame()

    events = detect_pullbacks(
        market
    )

    if events.empty:
        return pd.DataFrame()

    events = add_event_extremes(
        market,
        events
    )

    if events.empty:
        return pd.DataFrame()

    events = add_recovery_dates(
        market,
        events
    )

    if events.empty:
        return pd.DataFrame()

    return events


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print()
    print(
        "US500 HISTORICAL EVENT STUDY"
    )
    print(
        "============================"
    )

    events = build_historical_events(
        start_date="2019-01-01"
    )

    if events.empty:

        print(
            "ERROR: No historical events detected."
        )

    else:

        print()
        print(
            "TOTAL EVENTS:",
            len(events)
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
            "HISTORICAL EVENTS"
        )
        print(
            "-----------------"
        )

        display_columns = [
            "level",
            "date",
            "reference_high",
            "entry_price",
            "drawdown_pct",
            "trough_date",
            "trough_price",
            "trough_drawdown_pct",
            "recovery_date",
            "recovery_days",
        ]

        print(
            events[
                display_columns
            ].to_string(
                index=False
            )
        )

        print()
        print(
            "HISTORICAL EVENT STUDY COMPLETE"
        )
