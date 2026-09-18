"""
CORPORATE EARNINGS INTELLIGENCE
Market Reaction & Event Study - Phase V4

Research-only module.

Purpose:
    Analyze how S&P 500 historically reacted after corporate earnings
    announcements and compare the reaction with a pre-event normal-return
    baseline.

Input:
    earnings_breadth_events_v2.csv

Outputs:
    earnings_market_reaction_v4.csv
    earnings_event_study_v4.csv
    earnings_abnormal_return_v4.csv
    earnings_market_reaction_summary_v4.csv
    earnings_reaction_by_eps_class_v4.csv
    earnings_reaction_by_sector_v4.csv

IMPORTANT:
    - No BUY / SELL signals.
    - No Decision Engine integration.
    - No trade execution.
    - No future information is used for the event classification.
    - Historical statistics are descriptive/research outputs.
"""

import os
import math
import time
import warnings

import pandas as pd
import numpy as np
import yfinance as yf

warnings.filterwarnings("ignore")


# ============================================================
# CONFIGURATION
# ============================================================

INPUT_FILE = "earnings_breadth_events_v2.csv"

MARKET_TICKER = "^GSPC"

MARKET_ESTIMATION_BUFFER_DAYS = 180
MARKET_FORWARD_BUFFER_DAYS = 150

# Number of trading sessions used to estimate normal market return.
ESTIMATION_WINDOW_SESSIONS = 60

# Gap between estimation window and event date.
# This prevents the days immediately before the event from
# contaminating the normal-return estimate.
ESTIMATION_GAP_SESSIONS = 5

HORIZONS = {
    "1d": 1,
    "3d": 3,
    "5d": 5,
    "20d": 20,
}

EVENT_STUDY_DAYS = 20

OUTPUT_MARKET_REACTION = "earnings_market_reaction_v4.csv"
OUTPUT_EVENT_STUDY = "earnings_event_study_v4.csv"
OUTPUT_ABNORMAL = "earnings_abnormal_return_v4.csv"
OUTPUT_SUMMARY = "earnings_market_reaction_summary_v4.csv"
OUTPUT_EPS = "earnings_reaction_by_eps_class_v4.csv"
OUTPUT_SECTOR = "earnings_reaction_by_sector_v4.csv"


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(message, flush=True)


# ============================================================
# LOAD EARNINGS DATA
# ============================================================

def load_earnings_data():
    log("Loading V2 earnings events...")

    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(
            f"Required input file not found: {INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE)

    required_columns = [
        "ticker",
        "sector",
        "fiscal_date_ending",
        "reported_date",
        "eps_actual",
        "eps_consensus",
        "eps_surprise",
        "eps_surprise_pct",
        "eps_result_class",
        "point_in_time_safe",
        "historical_analog_eligible",
    ]

    missing = [
        col for col in required_columns
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing required V2 columns: {missing}"
        )

    df["reported_date"] = pd.to_datetime(
        df["reported_date"],
        errors="coerce"
    )

    df = df.dropna(
        subset=["reported_date"]
    ).copy()

    df = df.sort_values(
        ["reported_date", "ticker"]
    ).reset_index(drop=True)

    log(f"Earnings events loaded: {len(df)}")

    return df


# ============================================================
# DOWNLOAD MARKET DATA
# ============================================================

def download_market_data(df):
    min_date = df["reported_date"].min()
    max_date = df["reported_date"].max()

    start_date = (
        min_date -
        pd.Timedelta(days=MARKET_ESTIMATION_BUFFER_DAYS)
    )

    end_date = (
        max_date +
        pd.Timedelta(days=MARKET_FORWARD_BUFFER_DAYS)
    )

    log(f"S&P 500 market data: {MARKET_TICKER}")
    log(f"Start: {start_date.date()}")
    log(f"End: {end_date.date()}")

    market = yf.download(
        MARKET_TICKER,
        start=start_date.strftime("%Y-%m-%d"),
        end=(end_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=False,
        interval="1d",
        progress=False,
        threads=False,
    )

    if market.empty:
        raise RuntimeError(
            "No S&P 500 market data downloaded."
        )

    # Handle yfinance MultiIndex columns.
    if isinstance(market.columns, pd.MultiIndex):
        market.columns = [
            col[0] if isinstance(col, tuple) else col
            for col in market.columns
        ]

    required_market_columns = [
        "Open",
        "High",
        "Low",
        "Close",
    ]

    missing = [
        col
        for col in required_market_columns
        if col not in market.columns
    ]

    if missing:
        raise ValueError(
            f"Missing market columns: {missing}"
        )

    market = market[
        required_market_columns
    ].copy()

    market.index = pd.to_datetime(
        market.index
    )

    # Remove timezone if present.
    try:
        market.index = market.index.tz_localize(None)
    except TypeError:
        pass

    market = market.dropna(
        subset=["Close"]
    )

    market = market.sort_index()

    # Daily simple return.
    market["daily_return"] = (
        market["Close"]
        .pct_change()
    )

    # Daily log return.
    market["daily_log_return"] = (
        np.log(
            market["Close"] /
            market["Close"].shift(1)
        )
    )

    log(
        f"Trading sessions downloaded: {len(market)}"
    )

    return market


# ============================================================
# MARKET SESSION HELPERS
# ============================================================

def get_reference_position(market_index, reported_date):
    """
    Reference session = last trading session on or before
    the reported date.

    This preserves the timing convention used by V3.
    """

    positions = market_index.searchsorted(
        reported_date,
        side="right"
    )

    position = positions - 1

    if position < 0:
        return None

    return int(position)


def get_future_close(
    market,
    reference_position,
    offset
):
    """
    offset=1 means first trading session after the
    reference/reporting date.
    """

    position = (
        reference_position +
        offset
    )

    if position >= len(market):
        return None

    return market.iloc[position]["Close"]


# ============================================================
# PRE-EVENT RETURNS
# ============================================================

def calculate_pre_event_returns(
    market,
    reference_position
):
    result = {
        "pre_event_5d_return_pct": np.nan,
        "pre_event_20d_return_pct": np.nan,
    }

    if reference_position >= 5:
        close_now = market.iloc[
            reference_position
        ]["Close"]

        close_5 = market.iloc[
            reference_position - 5
        ]["Close"]

        if pd.notna(close_now) and pd.notna(close_5):
            result["pre_event_5d_return_pct"] = (
                (close_now / close_5) - 1
            ) * 100

    if reference_position >= 20:
        close_now = market.iloc[
            reference_position
        ]["Close"]

        close_20 = market.iloc[
            reference_position - 20
        ]["Close"]

        if pd.notna(close_now) and pd.notna(close_20):
            result["pre_event_20d_return_pct"] = (
                (close_now / close_20) - 1
            ) * 100

    return result


# ============================================================
# ESTIMATION WINDOW
# ============================================================

def calculate_estimation_window(
    market,
    reference_position
):
    """
    Estimate normal market return using:

        60 trading sessions

    ending:

        5 trading sessions before the event reference.

    Example:

        [estimation window]
        ------------------
        60 sessions

                     5-session gap
                              |
                              v
        ----------------------| event
                              E
    """

    result = {
        "estimation_window_available": False,
        "estimation_sessions": 0,
        "estimation_mean_daily_return_pct": np.nan,
        "estimation_std_daily_return_pct": np.nan,
        "estimation_mean_daily_log_return_pct": np.nan,
    }

    estimation_end = (
        reference_position -
        ESTIMATION_GAP_SESSIONS
    )

    estimation_start = (
        estimation_end -
        ESTIMATION_WINDOW_SESSIONS +
        1
    )

    if estimation_start < 1:
        return result

    window = market.iloc[
        estimation_start:
        estimation_end + 1
    ]

    returns = window[
        "daily_return"
    ].dropna()

    log_returns = window[
        "daily_log_return"
    ].dropna()

    if len(returns) < ESTIMATION_WINDOW_SESSIONS:
        return result

    result[
        "estimation_window_available"
    ] = True

    result[
        "estimation_sessions"
    ] = len(returns)

    result[
        "estimation_mean_daily_return_pct"
    ] = returns.mean() * 100

    result[
        "estimation_std_daily_return_pct"
    ] = returns.std(ddof=1) * 100

    result[
        "estimation_mean_daily_log_return_pct"
    ] = log_returns.mean() * 100

    return result


# ============================================================
# EXPECTED RETURNS
# ============================================================

def calculate_expected_return(
    mean_daily_return,
    horizon
):
    """
    Historical-mean expected return baseline.

    This is deliberately NOT described as a full market model.
    """

    if pd.isna(mean_daily_return):
        return np.nan

    return (
        ((1 + mean_daily_return) ** horizon) - 1
    ) * 100


# ============================================================
# EVENT REACTION
# ============================================================

def calculate_event_reaction(
    market,
    reference_position
):
    result = {}

    reference_close = market.iloc[
        reference_position
    ]["Close"]

    reference_date = market.index[
        reference_position
    ]

    result[
        "market_reference_date"
    ] = reference_date

    result[
        "market_reference_close"
    ] = reference_close

    # --------------------------------------------------------
    # Pre-event behavior
    # --------------------------------------------------------

    result.update(
        calculate_pre_event_returns(
            market,
            reference_position
        )
    )

    # --------------------------------------------------------
    # Estimation window
    # --------------------------------------------------------

    estimation = calculate_estimation_window(
        market,
        reference_position
    )

    result.update(estimation)

    mean_daily_return = (
        estimation[
            "estimation_mean_daily_return_pct"
        ] / 100
        if estimation[
            "estimation_mean_daily_return_pct"
        ] is not np.nan
        and pd.notna(
            estimation[
                "estimation_mean_daily_return_pct"
            ]
        )
        else np.nan
    )

    # --------------------------------------------------------
    # Event horizons
    # --------------------------------------------------------

    for name, horizon in HORIZONS.items():

        future_position = (
            reference_position +
            horizon
        )

        if future_position >= len(market):
            result[
                f"market_reaction_{name}_pct"
            ] = np.nan

            result[
                f"expected_return_{name}_pct"
            ] = np.nan

            result[
                f"abnormal_return_{name}_pct"
            ] = np.nan

            result[
                f"car_{name}_pct"
            ] = np.nan

            result[
                f"future_date_{name}"
            ] = pd.NaT

            result[
                f"future_close_{name}"
            ] = np.nan

            continue

        future_close = market.iloc[
            future_position
        ]["Close"]

        future_date = market.index[
            future_position
        ]

        raw_return = (
            future_close /
            reference_close -
            1
        ) * 100

        expected_return = (
            calculate_expected_return(
                mean_daily_return,
                horizon
            )
        )

        # ----------------------------------------------------
        # Abnormal cumulative return
        # ----------------------------------------------------

        if pd.notna(expected_return):
            abnormal_return = (
                raw_return -
                expected_return
            )
        else:
            abnormal_return = np.nan

        # ----------------------------------------------------
        # CAR
        # ----------------------------------------------------

        car = calculate_car(
            market,
            reference_position,
            horizon,
            mean_daily_return
        )

        result[
            f"market_reaction_{name}_pct"
        ] = raw_return

        result[
            f"expected_return_{name}_pct"
        ] = expected_return

        result[
            f"abnormal_return_{name}_pct"
        ] = abnormal_return

        result[
            f"car_{name}_pct"
        ] = car

        result[
            f"future_date_{name}"
        ] = future_date

        result[
            f"future_close_{name}"
        ] = future_close

    # --------------------------------------------------------
    # MFE / MAE
    # --------------------------------------------------------

    max_position = min(
        reference_position +
        EVENT_STUDY_DAYS,
        len(market) - 1
    )

    if max_position > reference_position:

        future_window = market.iloc[
            reference_position + 1:
            max_position + 1
        ]

        highest_high = future_window[
            "High"
        ].max()

        lowest_low = future_window[
            "Low"
        ].min()

        result[
            "mfe_20d_pct"
        ] = (
            highest_high /
            reference_close -
            1
        ) * 100

        result[
            "mae_20d_pct"
        ] = (
            lowest_low /
            reference_close -
            1
        ) * 100

    else:
        result["mfe_20d_pct"] = np.nan
        result["mae_20d_pct"] = np.nan

    return result


# ============================================================
# CAR CALCULATION
# ============================================================

def calculate_car(
    market,
    reference_position,
    horizon,
    expected_daily_return
):
    """
    CAR = sum of daily abnormal returns.

    Daily abnormal return:

        actual daily return
        -
        expected daily return
    """

    end_position = (
        reference_position +
        horizon
    )

    if end_position >= len(market):
        return np.nan

    daily_returns = market.iloc[
        reference_position + 1:
        end_position + 1
    ]["daily_return"]

    daily_returns = daily_returns.dropna()

    if len(daily_returns) < horizon:
        return np.nan

    if pd.isna(expected_daily_return):
        return np.nan

    abnormal_daily_returns = (
        daily_returns -
        expected_daily_return
    )

    return (
        abnormal_daily_returns.sum()
    ) * 100


# ============================================================
# DAILY EVENT STUDY
# ============================================================

def build_daily_event_study(
    event_rows,
    market
):
    records = []

    log(
        "Building daily event-study dataset..."
    )

    for counter, row in enumerate(
        event_rows,
        start=1
    ):

        if counter % 250 == 0:
            log(
                f"Event-study progress: "
                f"{counter}/{len(event_rows)}"
            )

        reported_date = row[
            "reported_date"
        ]

        reference_position = get_reference_position(
            market.index,
            reported_date
        )

        if reference_position is None:
            continue

        estimation = calculate_estimation_window(
            market,
            reference_position
        )

        mean_daily_return = (
            estimation[
                "estimation_mean_daily_return_pct"
            ] / 100
            if pd.notna(
                estimation[
                    "estimation_mean_daily_return_pct"
                ]
            )
            else np.nan
        )

        reference_close = market.iloc[
            reference_position
        ]["Close"]

        reference_date = market.index[
            reference_position
        ]

        for day in range(
            1,
            EVENT_STUDY_DAYS + 1
        ):

            position = (
                reference_position +
                day
            )

            if position >= len(market):
                break

            session = market.iloc[
                position
            ]

            daily_return = session[
                "daily_return"
            ]

            if pd.isna(daily_return):
                continue

            expected_daily_return = (
                mean_daily_return
            )

            abnormal_daily_return = (
                daily_return -
                expected_daily_return
                if pd.notna(
                    expected_daily_return
                )
                else np.nan
            )

            cumulative_raw_return = (
                session["Close"] /
                reference_close -
                1
            ) * 100

            expected_cumulative_return = (
                calculate_expected_return(
                    mean_daily_return,
                    day
                )
            )

            cumulative_abnormal_return = (
                cumulative_raw_return -
                expected_cumulative_return
                if pd.notna(
                    expected_cumulative_return
                )
                else np.nan
            )

            records.append({
                "ticker": row["ticker"],
                "sector": row["sector"],
                "reported_date": reported_date,
                "market_reference_date": reference_date,
                "eps_result_class": row[
                    "eps_result_class"
                ],
                "eps_surprise_pct": row[
                    "eps_surprise_pct"
                ],
                "historical_analog_eligible": row[
                    "historical_analog_eligible"
                ],
                "point_in_time_safe": row[
                    "point_in_time_safe"
                ],
                "event_day": day,
                "session_date": market.index[
                    position
                ],
                "daily_return_pct": (
                    daily_return * 100
                ),
                "expected_daily_return_pct": (
                    expected_daily_return * 100
                    if pd.notna(
                        expected_daily_return
                    )
                    else np.nan
                ),
                "abnormal_daily_return_pct": (
                    abnormal_daily_return * 100
                    if pd.notna(
                        abnormal_daily_return
                    )
                    else np.nan
                ),
                "cumulative_raw_return_pct": (
                    cumulative_raw_return
                ),
                "expected_cumulative_return_pct": (
                    expected_cumulative_return
                ),
                "cumulative_abnormal_return_pct": (
                    cumulative_abnormal_return
                ),
            })

    return pd.DataFrame(records)


# ============================================================
# BUILD EVENT DATASET
# ============================================================

def build_reaction_dataset(
    earnings,
    market
):
    records = []

    total = len(earnings)

    log(
        "CALCULATING EARNINGS → "
        "S&P 500 V4 EVENT STUDY"
    )

    for index, row in earnings.iterrows():

        if (
            index + 1
        ) % 100 == 0:
            log(
                f"[{index + 1}/{total}] "
                f"{row['ticker']} "
                f"{row['reported_date'].date()}"
            )

        reference_position = get_reference_position(
            market.index,
            row["reported_date"]
        )

        output = row.to_dict()

        if reference_position is None:
            output[
                "market_reaction_available"
            ] = False

            output[
                "historical_reaction_eligible"
            ] = False

            records.append(output)
            continue

        reaction = calculate_event_reaction(
            market,
            reference_position
        )

        output.update(reaction)

        output[
            "market_reaction_available"
        ] = True

        output[
            "market_reaction_point_in_time_safe"
        ] = True

        output[
            "historical_reaction_eligible"
        ] = bool(
            row[
                "historical_analog_eligible"
            ]
        )

        # ----------------------------------------------------
        # Descriptive reaction classes
        # ----------------------------------------------------

        for name in HORIZONS:

            value = output.get(
                f"market_reaction_{name}_pct"
            )

            if pd.isna(value):
                reaction_class = "UNKNOWN"

            elif value >= 2:
                reaction_class = "STRONG_POSITIVE"

            elif value > 0.25:
                reaction_class = "POSITIVE"

            elif value >= -0.25:
                reaction_class = "NEUTRAL"

            elif value > -2:
                reaction_class = "NEGATIVE"

            else:
                reaction_class = "STRONG_NEGATIVE"

            output[
                f"market_reaction_{name}_class"
            ] = reaction_class

        records.append(output)

    return pd.DataFrame(records)


# ============================================================
# STATISTICS
# ============================================================

def normal_approx_p_value(t_stat):
    """
    Two-sided normal approximation.

    Used intentionally without introducing scipy as a
    mandatory dependency.

    For large samples this is a useful descriptive approximation,
    but it is NOT a replacement for cluster-robust inference.
    """

    if pd.isna(t_stat):
        return np.nan

    z = abs(t_stat)

    return math.erfc(
        z / math.sqrt(2)
    )


def calculate_statistics(series):
    values = pd.to_numeric(
        series,
        errors="coerce"
    ).dropna()

    n = len(values)

    if n == 0:
        return {
            "events": 0,
            "mean_pct": np.nan,
            "median_pct": np.nan,
            "std_pct": np.nan,
            "p25_pct": np.nan,
            "p75_pct": np.nan,
            "min_pct": np.nan,
            "max_pct": np.nan,
            "positive_pct": np.nan,
            "negative_pct": np.nan,
            "t_stat": np.nan,
            "p_value_normal_approx": np.nan,
            "ci95_lower_pct": np.nan,
            "ci95_upper_pct": np.nan,
        }

    mean = values.mean()
    median = values.median()

    std = (
        values.std(ddof=1)
        if n > 1
        else np.nan
    )

    if n > 1 and pd.notna(std) and std > 0:

        standard_error = (
            std / math.sqrt(n)
        )

        t_stat = (
            mean /
            standard_error
        )

        p_value = normal_approx_p_value(
            t_stat
        )

        ci_margin = (
            1.96 *
            standard_error
        )

        ci_lower = (
            mean -
            ci_margin
        )

        ci_upper = (
            mean +
            ci_margin
        )

    else:
        t_stat = np.nan
        p_value = np.nan
        ci_lower = np.nan
        ci_upper = np.nan

    return {
        "events": n,
        "mean_pct": mean,
        "median_pct": median,
        "std_pct": std,
        "p25_pct": values.quantile(0.25),
        "p75_pct": values.quantile(0.75),
        "min_pct": values.min(),
        "max_pct": values.max(),
        "positive_pct": (
            (values > 0).mean() * 100
        ),
        "negative_pct": (
            (values < 0).mean() * 100
        ),
        "t_stat": t_stat,
        "p_value_normal_approx": p_value,
        "ci95_lower_pct": ci_lower,
        "ci95_upper_pct": ci_upper,
    }


# ============================================================
# OVERALL SUMMARY
# ============================================================

def build_overall_summary(df):
    records = []

    for name in HORIZONS:

        raw_stats = calculate_statistics(
            df[
                f"market_reaction_{name}_pct"
            ]
        )

        abnormal_stats = calculate_statistics(
            df[
                f"abnormal_return_{name}_pct"
            ]
        )

        car_stats = calculate_statistics(
            df[
                f"car_{name}_pct"
            ]
        )

        records.append({
            "metric_type": "RAW_RETURN",
            "horizon": name,
            **raw_stats,
        })

        records.append({
            "metric_type": "ABNORMAL_RETURN",
            "horizon": name,
            **abnormal_stats,
        })

        records.append({
            "metric_type": "CAR",
            "horizon": name,
            **car_stats,
        })

    return pd.DataFrame(records)


# ============================================================
# EPS CLASS ANALYSIS
# ============================================================

def build_eps_summary(df):
    records = []

    classes = sorted(
        df[
            "eps_result_class"
        ]
        .dropna()
        .astype(str)
        .unique()
    )

    for eps_class in classes:

        subset = df[
            df[
                "eps_result_class"
            ].astype(str) == eps_class
        ]

        for name in HORIZONS:

            raw_stats = calculate_statistics(
                subset[
                    f"market_reaction_{name}_pct"
                ]
            )

            abnormal_stats = calculate_statistics(
                subset[
                    f"abnormal_return_{name}_pct"
                ]
            )

            car_stats = calculate_statistics(
                subset[
                    f"car_{name}_pct"
                ]
            )

            records.append({
                "eps_result_class": eps_class,
                "horizon": name,

                "raw_events": raw_stats[
                    "events"
                ],
                "raw_mean_pct": raw_stats[
                    "mean_pct"
                ],
                "raw_median_pct": raw_stats[
                    "median_pct"
                ],
                "raw_std_pct": raw_stats[
                    "std_pct"
                ],
                "raw_positive_pct": raw_stats[
                    "positive_pct"
                ],

                "abnormal_events": abnormal_stats[
                    "events"
                ],
                "abnormal_mean_pct": abnormal_stats[
                    "mean_pct"
                ],
                "abnormal_median_pct": abnormal_stats[
                    "median_pct"
                ],
                "abnormal_std_pct": abnormal_stats[
                    "std_pct"
                ],
                "abnormal_positive_pct": abnormal_stats[
                    "positive_pct"
                ],
                "abnormal_t_stat": abnormal_stats[
                    "t_stat"
                ],
                "abnormal_p_value_normal_approx": (
                    abnormal_stats[
                        "p_value_normal_approx"
                    ]
                ),
                "abnormal_ci95_lower_pct": (
                    abnormal_stats[
                        "ci95_lower_pct"
                    ]
                ),
                "abnormal_ci95_upper_pct": (
                    abnormal_stats[
                        "ci95_upper_pct"
                    ]
                ),

                "car_events": car_stats[
                    "events"
                ],
                "car_mean_pct": car_stats[
                    "mean_pct"
                ],
                "car_median_pct": car_stats[
                    "median_pct"
                ],
                "car_t_stat": car_stats[
                    "t_stat"
                ],
                "car_p_value_normal_approx": (
                    car_stats[
                        "p_value_normal_approx"
                    ]
                ),
            })

    return pd.DataFrame(records)


# ============================================================
# SECTOR ANALYSIS
# ============================================================

def build_sector_summary(df):
    records = []

    sectors = sorted(
        df[
            "sector"
        ]
        .dropna()
        .astype(str)
        .unique()
    )

    for sector in sectors:

        subset = df[
            df[
                "sector"
            ].astype(str) == sector
        ]

        for name in HORIZONS:

            raw_stats = calculate_statistics(
                subset[
                    f"market_reaction_{name}_pct"
                ]
            )

            abnormal_stats = calculate_statistics(
                subset[
                    f"abnormal_return_{name}_pct"
                ]
            )

            car_stats = calculate_statistics(
                subset[
                    f"car_{name}_pct"
                ]
            )

            records.append({
                "sector": sector,
                "horizon": name,

                "raw_events": raw_stats[
                    "events"
                ],
                "raw_mean_pct": raw_stats[
                    "mean_pct"
                ],
                "raw_median_pct": raw_stats[
                    "median_pct"
                ],
                "raw_positive_pct": raw_stats[
                    "positive_pct"
                ],

                "abnormal_events": abnormal_stats[
                    "events"
                ],
                "abnormal_mean_pct": abnormal_stats[
                    "mean_pct"
                ],
                "abnormal_median_pct": abnormal_stats[
                    "median_pct"
                ],
                "abnormal_positive_pct": abnormal_stats[
                    "positive_pct"
                ],
                "abnormal_t_stat": abnormal_stats[
                    "t_stat"
                ],
                "abnormal_p_value_normal_approx": (
                    abnormal_stats[
                        "p_value_normal_approx"
                    ]
                ),

                "car_events": car_stats[
                    "events"
                ],
                "car_mean_pct": car_stats[
                    "mean_pct"
                ],
                "car_median_pct": car_stats[
                    "median_pct"
                ],
                "car_t_stat": car_stats[
                    "t_stat"
                ],
                "car_p_value_normal_approx": (
                    car_stats[
                        "p_value_normal_approx"
                    ]
                ),
            })

    return pd.DataFrame(records)


# ============================================================
# LONG ABNORMAL RETURN DATASET
# ============================================================

def build_abnormal_return_dataset(df):
    records = []

    for _, row in df.iterrows():

        for name, horizon in HORIZONS.items():

            records.append({
                "ticker": row["ticker"],
                "sector": row["sector"],
                "reported_date": row["reported_date"],
                "eps_result_class": row[
                    "eps_result_class"
                ],
                "eps_surprise_pct": row[
                    "eps_surprise_pct"
                ],
                "horizon": name,
                "sessions": horizon,

                "pre_event_5d_return_pct": row[
                    "pre_event_5d_return_pct"
                ],
                "pre_event_20d_return_pct": row[
                    "pre_event_20d_return_pct"
                ],

                "estimation_window_available": row[
                    "estimation_window_available"
                ],
                "estimation_sessions": row[
                    "estimation_sessions"
                ],
                "estimation_mean_daily_return_pct": row[
                    "estimation_mean_daily_return_pct"
                ],
                "estimation_std_daily_return_pct": row[
                    "estimation_std_daily_return_pct"
                ],

                "raw_return_pct": row[
                    f"market_reaction_{name}_pct"
                ],
                "expected_return_pct": row[
                    f"expected_return_{name}_pct"
                ],
                "abnormal_return_pct": row[
                    f"abnormal_return_{name}_pct"
                ],
                "car_pct": row[
                    f"car_{name}_pct"
                ],
            })

    return pd.DataFrame(records)


# ============================================================
# DATA QUALITY
# ============================================================

def print_data_quality(df):
    total = len(df)

    available = int(
        df[
            "market_reaction_available"
        ].sum()
    )

    historical_eligible = int(
        df[
            "historical_reaction_eligible"
        ].sum()
    )

    estimation_available = int(
        df[
            "estimation_window_available"
        ].fillna(False).sum()
    )

    log("")
    log("DATA QUALITY")
    log("=" * 60)
    log(
        f"Total earnings events: {total}"
    )
    log(
        f"Events with market reaction: "
        f"{available}"
    )

    if total:
        log(
            f"Market coverage: "
            f"{available / total * 100:.2f}%"
        )

    log(
        f"Events with valid estimation window: "
        f"{estimation_available}"
    )

    if total:
        log(
            f"Estimation coverage: "
            f"{estimation_available / total * 100:.2f}%"
        )

    log(
        f"Historical analog eligible: "
        f"{historical_eligible}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    start_time = time.time()

    log("=" * 70)
    log("CORPORATE EARNINGS INTELLIGENCE V4")
    log("S&P 500 EVENT STUDY")
    log("RESEARCH ONLY")
    log("=" * 70)

    # --------------------------------------------------------
    # 1. Load V2
    # --------------------------------------------------------

    earnings = load_earnings_data()

    # --------------------------------------------------------
    # 2. Download market data
    # --------------------------------------------------------

    market = download_market_data(
        earnings
    )

    # --------------------------------------------------------
    # 3. Build event-level dataset
    # --------------------------------------------------------

    reaction_df = build_reaction_dataset(
        earnings,
        market
    )

    # --------------------------------------------------------
    # 4. Daily event study
    # --------------------------------------------------------

    event_study_df = build_daily_event_study(
        earnings.to_dict("records"),
        market
    )

    # --------------------------------------------------------
    # 5. Abnormal return long dataset
    # --------------------------------------------------------

    abnormal_df = build_abnormal_return_dataset(
        reaction_df
    )

    # --------------------------------------------------------
    # 6. Overall summary
    # --------------------------------------------------------

    summary_df = build_overall_summary(
        reaction_df
    )

    # --------------------------------------------------------
    # 7. EPS class analysis
    # --------------------------------------------------------

    eps_df = build_eps_summary(
        reaction_df
    )

    # --------------------------------------------------------
    # 8. Sector analysis
    # --------------------------------------------------------

    sector_df = build_sector_summary(
        reaction_df
    )

    # --------------------------------------------------------
    # 9. Save files
    # --------------------------------------------------------

    reaction_df.to_csv(
        OUTPUT_MARKET_REACTION,
        index=False
    )

    event_study_df.to_csv(
        OUTPUT_EVENT_STUDY,
        index=False
    )

    abnormal_df.to_csv(
        OUTPUT_ABNORMAL,
        index=False
    )

    summary_df.to_csv(
        OUTPUT_SUMMARY,
        index=False
    )

    eps_df.to_csv(
        OUTPUT_EPS,
        index=False
    )

    sector_df.to_csv(
        OUTPUT_SECTOR,
        index=False
    )

    # --------------------------------------------------------
    # 10. Data quality
    # --------------------------------------------------------

    print_data_quality(
        reaction_df
    )

    # --------------------------------------------------------
    # 11. Display overall results
    # --------------------------------------------------------

    log("")
    log("=" * 70)
    log("OVERALL V4 RESULTS")
    log("=" * 70)

    display_columns = [
        "metric_type",
        "horizon",
        "events",
        "mean_pct",
        "median_pct",
        "positive_pct",
        "t_stat",
        "p_value_normal_approx",
        "ci95_lower_pct",
        "ci95_upper_pct",
    ]

    print(
        summary_df[
            display_columns
        ].to_string(index=False)
    )

    # --------------------------------------------------------
    # 12. EPS results
    # --------------------------------------------------------

    log("")
    log("=" * 70)
    log("EPS CLASS — 5D ABNORMAL RETURN")
    log("=" * 70)

    eps_5d = eps_df[
        eps_df["horizon"] == "5d"
    ].copy()

    if not eps_5d.empty:
        print(
            eps_5d[
                [
                    "eps_result_class",
                    "abnormal_events",
                    "abnormal_mean_pct",
                    "abnormal_median_pct",
                    "abnormal_positive_pct",
                    "abnormal_t_stat",
                    "abnormal_p_value_normal_approx",
                ]
            ].to_string(index=False)
        )

    # --------------------------------------------------------
    # 13. Sector results
    # --------------------------------------------------------

    log("")
    log("=" * 70)
    log("SECTOR — 5D ABNORMAL RETURN")
    log("=" * 70)

    sector_5d = sector_df[
        sector_df["horizon"] == "5d"
    ].copy()

    if not sector_5d.empty:
        print(
            sector_5d[
                [
                    "sector",
                    "abnormal_events",
                    "abnormal_mean_pct",
                    "abnormal_median_pct",
                    "abnormal_positive_pct",
                    "abnormal_t_stat",
                    "abnormal_p_value_normal_approx",
                ]
            ].to_string(index=False)
        )

    # --------------------------------------------------------
    # 14. Completion
    # --------------------------------------------------------

    elapsed = (
        time.time() -
        start_time
    )

    log("")
    log("=" * 70)
    log("OUTPUT FILES")
    log("=" * 70)

    log(
        f"- {OUTPUT_MARKET_REACTION}"
    )

    log(
        f"- {OUTPUT_EVENT_STUDY}"
    )

    log(
        f"- {OUTPUT_ABNORMAL}"
    )

    log(
        f"- {OUTPUT_SUMMARY}"
    )

    log(
        f"- {OUTPUT_EPS}"
    )

    log(
        f"- {OUTPUT_SECTOR}"
    )

    log("")
    log(
        f"Execution time: {elapsed:.2f} seconds"
    )

    log("")
    log("=" * 70)
    log("CORPORATE EARNINGS INTELLIGENCE V4 COMPLETED")
    log("RESEARCH ONLY — NO TRADING SIGNALS")
    log("=" * 70)


if __name__ == "__main__":
    main()
