"""
Corporate Earnings Intelligence V4
==================================

Research-only historical event study.

Purpose
-------
Analyze the historical relationship between corporate earnings events
and subsequent S&P 500 market reactions.

V4 adds:
- Pre-event market condition
- 1D / 3D / 5D / 20D raw market reactions
- Historical expected market return baseline
- Abnormal returns
- Cumulative abnormal returns (CAR)
- 20-session MFE / MAE
- Daily event-study observations for days 1-20
- Statistical summaries
- EPS-class breakdown
- Sector breakdown

Important
---------
This module is analytical/research-only.

It does NOT:
- generate trade signals
- execute trades
- modify the Decision Engine
- predict future market direction
- claim causal effects from earnings events

Because this V4 dataset uses the S&P 500 index as the market series,
the expected-return baseline is a historical market-return baseline,
NOT a traditional company-level market model.
"""

import math
import warnings

import numpy as np
import pandas as pd
import yfinance as yf


# ============================================================
# CONFIGURATION
# ============================================================

INPUT_FILE = "earnings_breadth_events_v2.csv"

MARKET_TICKER = "^GSPC"

# Extra days before the first event are required for:
# - reference price
# - pre-event returns
# - historical estimation window
MARKET_START_BUFFER_DAYS = 180

# Extra days after the last event are required for all horizons.
MARKET_END_BUFFER_DAYS = 180

# Event reaction horizons measured in trading sessions.
HORIZONS = {
    "1d": 1,
    "3d": 3,
    "5d": 5,
    "20d": 20,
}

# Pre-event market condition.
PRE_EVENT_HORIZONS = {
    "pre_5d": 5,
    "pre_20d": 20,
}

# Estimation window for the historical market-return baseline.
#
# The estimation window ends several trading sessions before
# the earnings event in order to avoid using the immediate
# pre-event market reaction.
ESTIMATION_WINDOW = 60
ESTIMATION_GAP = 5

# MFE / MAE measurement window.
MFE_MAE_WINDOW = 20

# Reaction classification thresholds.
REACTION_STRONG_POSITIVE = 2.0
REACTION_POSITIVE = 0.25
REACTION_NEGATIVE = -0.25
REACTION_STRONG_NEGATIVE = -2.0

# Statistical confidence level.
Z_95 = 1.96


# ============================================================
# GENERAL HELPERS
# ============================================================

def safe_float(value):
    """
    Convert a value to float safely.

    Returns NaN when conversion is impossible.
    """
    if value is None:
        return np.nan

    try:
        if pd.isna(value):
            return np.nan
    except Exception:
        pass

    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def clean_numeric_series(series):
    """
    Convert pandas Series to numeric safely.
    """
    return pd.to_numeric(series, errors="coerce")


def classify_market_reaction(return_pct):
    """
    Classify market reaction based on cumulative percentage return.
    """

    if pd.isna(return_pct):
        return "UNKNOWN"

    if return_pct >= REACTION_STRONG_POSITIVE:
        return "STRONG_POSITIVE"

    if return_pct > REACTION_POSITIVE:
        return "POSITIVE"

    if return_pct >= REACTION_NEGATIVE:
        return "NEUTRAL"

    if return_pct > REACTION_STRONG_NEGATIVE:
        return "NEGATIVE"

    return "STRONG_NEGATIVE"


def normal_approx_p_value(t_stat):
    """
    Approximate two-sided p-value using the normal distribution.

    This is intentionally simple and is suitable for exploratory
    event-study statistics.

    It should NOT be interpreted as definitive inference because
    earnings observations can overlap and are not necessarily
    independent.
    """

    if pd.isna(t_stat):
        return np.nan

    # Standard normal CDF without requiring scipy.
    cdf = 0.5 * (
        1.0 + math.erf(abs(float(t_stat)) / math.sqrt(2.0))
    )

    return 2.0 * (1.0 - cdf)


def normalize_datetime_index(index):
    """
    Normalize a DatetimeIndex:
    - convert to datetime
    - remove timezone if present
    - normalize to midnight
    """

    idx = pd.to_datetime(index, errors="coerce")

    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)

    return idx.normalize()


# ============================================================
# LOAD EARNINGS DATA
# ============================================================

def load_earnings_data():
    """
    Load the V2 earnings event dataset.

    Required V2 columns are validated explicitly.
    """

    print("=" * 60)
    print("LOADING EARNINGS DATA")
    print("=" * 60)

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
            "Missing required columns in V2 dataset: "
            + ", ".join(missing)
        )

    df["reported_date"] = pd.to_datetime(
        df["reported_date"],
        errors="coerce"
    )

    df = df.dropna(subset=["reported_date"]).copy()

    df["ticker"] = df["ticker"].astype(str).str.upper()
    df["sector"] = df["sector"].fillna("UNKNOWN").astype(str)
    df["eps_result_class"] = (
        df["eps_result_class"]
        .fillna("UNKNOWN")
        .astype(str)
    )

    df["historical_analog_eligible"] = (
        df["historical_analog_eligible"]
        .astype(str)
        .str.lower()
        .isin(["true", "1", "yes"])
    )

    df = df.sort_values(
        ["reported_date", "ticker"]
    ).reset_index(drop=True)

    print(f"Earnings events loaded: {len(df)}")

    if len(df) > 0:
        print(
            f"Start: {df['reported_date'].min().date()}"
        )
        print(
            f"End: {df['reported_date'].max().date()}"
        )

    return df


# ============================================================
# DOWNLOAD MARKET DATA
# ============================================================

def download_market_data(earnings_df):
    """
    Download S&P 500 daily OHLC data.

    The market data is intentionally downloaded with a large
    buffer before and after the event range.
    """

    print("=" * 60)
    print("DOWNLOADING MARKET DATA")
    print("=" * 60)

    min_date = earnings_df["reported_date"].min()
    max_date = earnings_df["reported_date"].max()

    start_date = (
        min_date
        - pd.Timedelta(days=MARKET_START_BUFFER_DAYS)
    )

    end_date = (
        max_date
        + pd.Timedelta(days=MARKET_END_BUFFER_DAYS)
    )

    print(f"Market ticker: {MARKET_TICKER}")
    print(f"Download start: {start_date.date()}")
    print(f"Download end: {end_date.date()}")

    warnings.filterwarnings(
        "ignore",
        message=".*auto_adjust.*"
    )

    data = yf.download(
        MARKET_TICKER,
        start=start_date.strftime("%Y-%m-%d"),
        end=end_date.strftime("%Y-%m-%d"),
        auto_adjust=False,
        interval="1d",
        progress=False,
        threads=False,
    )

    if data is None or data.empty:
        raise RuntimeError(
            "No market data was downloaded from yfinance."
        )

    # Handle possible MultiIndex columns.
    if isinstance(data.columns, pd.MultiIndex):
        try:
            if MARKET_TICKER in data.columns.get_level_values(-1):
                data = data.xs(
                    MARKET_TICKER,
                    axis=1,
                    level=-1
                )
            else:
                data.columns = data.columns.get_level_values(0)
        except Exception:
            data.columns = data.columns.get_level_values(0)

    data.index = normalize_datetime_index(data.index)

    # Keep only standard OHLC columns that are available.
    available_columns = [
        col for col in ["Open", "High", "Low", "Close"]
        if col in data.columns
    ]

    if "Close" not in available_columns:
        raise RuntimeError(
            "S&P 500 market data does not contain Close prices."
        )

    data = data[available_columns].copy()

    for col in available_columns:
        data[col] = pd.to_numeric(
            data[col],
            errors="coerce"
        )

    data = data.dropna(subset=["Close"])

    print(
        f"Trading sessions downloaded: {len(data)}"
    )

    return data


# ============================================================
# MARKET SESSION HELPERS
# ============================================================

def get_reference_session(market_data, event_date):
    """
    Get the last available trading session on or before
    the earnings reported date.

    This is the reference close used for event returns.
    """

    eligible = market_data.index[
        market_data.index <= event_date
    ]

    if len(eligible) == 0:
        return None

    return eligible[-1]


def get_future_sessions(market_data, event_date, count=20):
    """
    Get trading sessions strictly after the earnings event date.
    """

    future = market_data.index[
        market_data.index > event_date
    ]

    return future[:count]


def get_prior_sessions(
    market_data,
    event_date,
    count
):
    """
    Get prior trading sessions ending before the event.

    The event date itself is excluded.
    """

    prior = market_data.index[
        market_data.index < event_date
    ]

    return prior[-count:]


# ============================================================
# PRE-EVENT MARKET CONDITION
# ============================================================

def calculate_pre_event_returns(
    market_data,
    event_date
):
    """
    Calculate market returns before the earnings event.

    pre_5d:
        Reference event-day/prior close compared with close
        5 trading sessions earlier.

    pre_20d:
        Same concept over 20 trading sessions.
    """

    reference_session = get_reference_session(
        market_data,
        event_date
    )

    result = {
        "reference_session": reference_session,
        "pre_5d_return_pct": np.nan,
        "pre_20d_return_pct": np.nan,
    }

    if reference_session is None:
        return result

    reference_close = safe_float(
        market_data.loc[
            reference_session,
            "Close"
        ]
    )

    if pd.isna(reference_close) or reference_close == 0:
        return result

    for label, horizon in PRE_EVENT_HORIZONS.items():

        prior_sessions = get_prior_sessions(
            market_data,
            reference_session,
            horizon
        )

        if len(prior_sessions) < horizon:
            continue

        start_session = prior_sessions[0]

        start_close = safe_float(
            market_data.loc[
                start_session,
                "Close"
            ]
        )

        if pd.isna(start_close) or start_close == 0:
            continue

        return_pct = (
            (reference_close / start_close) - 1.0
        ) * 100.0

        result[f"{label}_return_pct"] = return_pct

    return result


# ============================================================
# HISTORICAL EXPECTED MARKET RETURN
# ============================================================

def calculate_historical_baseline(
    market_data,
    event_date
):
    """
    Estimate normal historical S&P 500 daily return.

    Estimation window:
        60 trading sessions

    Gap:
        5 trading sessions before event

    Example:
        event
        <- 5-session gap
        <- 60-session estimation window

    This avoids using the immediate pre-event market behavior
    in the expected-return estimate.
    """

    all_sessions = market_data.index

    prior_sessions = all_sessions[
        all_sessions < event_date
    ]

    required = (
        ESTIMATION_WINDOW
        + ESTIMATION_GAP
        + 1
    )

    if len(prior_sessions) < required:
        return {
            "estimation_n": 0,
            "mean_daily_return": np.nan,
            "std_daily_return": np.nan,
        }

    # Exclude the immediate pre-event gap.
    end_position = (
        len(prior_sessions)
        - ESTIMATION_GAP
    )

    estimation_end_sessions = prior_sessions[
        :end_position
    ]

    if len(estimation_end_sessions) < (
        ESTIMATION_WINDOW + 1
    ):
        return {
            "estimation_n": 0,
            "mean_daily_return": np.nan,
            "std_daily_return": np.nan,
        }

    estimation_sessions = estimation_end_sessions[
        -(ESTIMATION_WINDOW + 1):
    ]

    closes = market_data.loc[
        estimation_sessions,
        "Close"
    ].astype(float)

    daily_returns = closes.pct_change().dropna()

    if len(daily_returns) == 0:
        return {
            "estimation_n": 0,
            "mean_daily_return": np.nan,
            "std_daily_return": np.nan,
        }

    return {
        "estimation_n": int(len(daily_returns)),
        "mean_daily_return": float(
            daily_returns.mean()
        ),
        "std_daily_return": float(
            daily_returns.std(ddof=1)
        ) if len(daily_returns) > 1 else np.nan,
    }


# ============================================================
# EVENT REACTION
# ============================================================

def calculate_event_reaction(
    market_data,
    event_date
):
    """
    Calculate the complete V4 market reaction for one event.

    Outputs:
    - reference session
    - pre-event returns
    - historical baseline
    - raw returns
    - expected returns
    - abnormal returns
    - CAR
    - MFE
    - MAE
    """

    result = calculate_pre_event_returns(
        market_data,
        event_date
    )

    baseline = calculate_historical_baseline(
        market_data,
        event_date
    )

    result.update({
        "estimation_n": baseline["estimation_n"],
        "mean_daily_return": baseline["mean_daily_return"],
        "std_daily_return": baseline["std_daily_return"],
    })

    reference_session = result["reference_session"]

    if reference_session is None:
        for label in HORIZONS:
            result[f"{label}_raw_return_pct"] = np.nan
            result[f"{label}_expected_return_pct"] = np.nan
            result[f"{label}_abnormal_return_pct"] = np.nan
            result[f"{label}_reaction_class"] = "UNKNOWN"

        result["car_1d_pct"] = np.nan
        result["car_3d_pct"] = np.nan
        result["car_5d_pct"] = np.nan
        result["car_20d_pct"] = np.nan
        result["mfe_20d_pct"] = np.nan
        result["mae_20d_pct"] = np.nan
        result["market_reaction_available"] = False

        return result

    reference_close = safe_float(
        market_data.loc[
            reference_session,
            "Close"
        ]
    )

    if pd.isna(reference_close) or reference_close == 0:
        result["market_reaction_available"] = False
        return result

    future_sessions = get_future_sessions(
        market_data,
        event_date,
        MFE_MAE_WINDOW
    )

    if len(future_sessions) == 0:
        result["market_reaction_available"] = False
        return result

    mean_daily_return = safe_float(
        baseline["mean_daily_return"]
    )

    # --------------------------------------------------------
    # Daily event-study calculations
    # --------------------------------------------------------

    daily_rows = []

    cumulative_raw = 1.0
    cumulative_expected = 1.0

    for day_number, session in enumerate(
        future_sessions,
        start=1
    ):

        close = safe_float(
            market_data.loc[
                session,
                "Close"
            ]
        )

        if pd.isna(close) or close == 0:
            continue

        daily_raw = np.nan

        if day_number == 1:
            previous_close = reference_close
        else:
            previous_session = future_sessions[
                day_number - 2
            ]

            previous_close = safe_float(
                market_data.loc[
                    previous_session,
                    "Close"
                ]
            )

        if (
            not pd.isna(previous_close)
            and previous_close != 0
        ):
            daily_raw = (
                close / previous_close - 1.0
            )

        if pd.isna(mean_daily_return):
            daily_expected = np.nan
        else:
            daily_expected = mean_daily_return

        if (
            not pd.isna(daily_raw)
            and not pd.isna(daily_expected)
        ):
            daily_abnormal = (
                daily_raw - daily_expected
            )
        else:
            daily_abnormal = np.nan

        raw_from_event = (
            close / reference_close - 1.0
        )

        if pd.isna(mean_daily_return):
            expected_from_event = np.nan
            abnormal_from_event = np.nan
        else:
            expected_from_event = (
                (1.0 + mean_daily_return)
                ** day_number
                - 1.0
            )

            abnormal_from_event = (
                raw_from_event
                - expected_from_event
            )

        if not pd.isna(daily_raw):
            cumulative_raw *= (
                1.0 + daily_raw
            )

        if not pd.isna(daily_expected):
            cumulative_expected *= (
                1.0 + daily_expected
            )

        if (
            not pd.isna(daily_raw)
            and not pd.isna(daily_expected)
        ):
            # CAR is the cumulative sum of daily abnormal returns.
            #
            # We keep this additive because this is the standard
            # event-study abnormal-return aggregation.
            pass

        daily_rows.append({
            "session": session,
            "event_day": day_number,
            "close": close,
            "daily_raw_return": daily_raw,
            "daily_expected_return": daily_expected,
            "daily_abnormal_return": daily_abnormal,
            "cumulative_raw_return": raw_from_event,
            "cumulative_expected_return": (
                expected_from_event
            ),
            "cumulative_abnormal_return": (
                abnormal_from_event
            ),
        })

    # --------------------------------------------------------
    # Horizon calculations
    # --------------------------------------------------------

    for label, horizon in HORIZONS.items():

        if len(future_sessions) < horizon:
            result[f"{label}_raw_return_pct"] = np.nan
            result[f"{label}_expected_return_pct"] = np.nan
            result[f"{label}_abnormal_return_pct"] = np.nan
            result[f"{label}_reaction_class"] = "UNKNOWN"
            continue

        session = future_sessions[horizon - 1]

        future_close = safe_float(
            market_data.loc[
                session,
                "Close"
            ]
        )

        if pd.isna(future_close):
            result[f"{label}_raw_return_pct"] = np.nan
            result[f"{label}_expected_return_pct"] = np.nan
            result[f"{label}_abnormal_return_pct"] = np.nan
            result[f"{label}_reaction_class"] = "UNKNOWN"
            continue

        raw_return = (
            future_close / reference_close - 1.0
        )

        if pd.isna(mean_daily_return):
            expected_return = np.nan
            abnormal_return = np.nan
        else:
            expected_return = (
                (1.0 + mean_daily_return)
                ** horizon
                - 1.0
            )

            abnormal_return = (
                raw_return - expected_return
            )

        result[f"{label}_raw_return_pct"] = (
            raw_return * 100.0
        )

        if pd.isna(expected_return):
            result[f"{label}_expected_return_pct"] = np.nan
            result[f"{label}_abnormal_return_pct"] = np.nan
        else:
            result[f"{label}_expected_return_pct"] = (
                expected_return * 100.0
            )

            result[f"{label}_abnormal_return_pct"] = (
                abnormal_return * 100.0
            )

        result[f"{label}_reaction_class"] = (
            classify_market_reaction(
                raw_return * 100.0
            )
        )

    # --------------------------------------------------------
    # CAR
    # --------------------------------------------------------

    if daily_rows:
        daily_df = pd.DataFrame(daily_rows)

        for label, horizon in HORIZONS.items():

            subset = daily_df[
                daily_df["event_day"] <= horizon
            ]

            abnormal_values = subset[
                "daily_abnormal_return"
            ].dropna()

            if len(abnormal_values) == 0:
                result[f"car_{label}_pct"] = np.nan
            else:
                result[f"car_{label}_pct"] = (
                    abnormal_values.sum() * 100.0
                )

    # --------------------------------------------------------
    # MFE / MAE
    # --------------------------------------------------------

    window_sessions = future_sessions[
        :MFE_MAE_WINDOW
    ]

    highs = pd.to_numeric(
        market_data.loc[
            window_sessions,
            "High"
        ],
        errors="coerce"
    ).dropna()

    lows = pd.to_numeric(
        market_data.loc[
            window_sessions,
            "Low"
        ],
        errors="coerce"
    ).dropna()

    if len(highs) > 0:
        result["mfe_20d_pct"] = (
            (highs.max() / reference_close - 1.0)
            * 100.0
        )
    else:
        result["mfe_20d_pct"] = np.nan

    if len(lows) > 0:
        result["mae_20d_pct"] = (
            (lows.min() / reference_close - 1.0)
            * 100.0
        )
    else:
        result["mae_20d_pct"] = np.nan

    result["market_reaction_available"] = True

    return result


# ============================================================
# BUILD EVENT DATASET
# ============================================================

def build_reaction_dataset(
    earnings_df,
    market_data
):
    """
    Build one row per earnings event.

    Original V2 event fields are preserved and V4 market-reaction
    fields are appended.
    """

    print("=" * 60)
    print("BUILDING V4 EVENT DATASET")
    print("=" * 60)

    event_rows = []

    total = len(earnings_df)

    for counter, (_, row) in enumerate(
        earnings_df.iterrows(),
        start=1
    ):

        event_date = row["reported_date"]

        reaction = calculate_event_reaction(
            market_data,
            event_date
        )

        output = row.to_dict()

        # Convert datetime for clean CSV export.
        output["reported_date"] = (
            event_date.strftime("%Y-%m-%d")
        )

        if pd.notna(row["fiscal_date_ending"]):
            output["fiscal_date_ending"] = str(
                row["fiscal_date_ending"]
            )

        output.update({
            "reference_session": (
                reaction.get("reference_session")
                .strftime("%Y-%m-%d")
                if reaction.get("reference_session")
                is not None
                else None
            ),

            "pre_5d_return_pct": reaction.get(
                "pre_5d_return_pct",
                np.nan
            ),

            "pre_20d_return_pct": reaction.get(
                "pre_20d_return_pct",
                np.nan
            ),

            "estimation_n": reaction.get(
                "estimation_n",
                0
            ),

            "mean_daily_return": reaction.get(
                "mean_daily_return",
                np.nan
            ),

            "std_daily_return": reaction.get(
                "std_daily_return",
                np.nan
            ),

            "mfe_20d_pct": reaction.get(
                "mfe_20d_pct",
                np.nan
            ),

            "mae_20d_pct": reaction.get(
                "mae_20d_pct",
                np.nan
            ),

            "market_reaction_available": reaction.get(
                "market_reaction_available",
                False
            ),

            "market_reaction_point_in_time_safe": True,

            "historical_reaction_eligible": bool(
                row["historical_analog_eligible"]
            ),
        })

        for label in HORIZONS:

            output[f"{label}_raw_return_pct"] = (
                reaction.get(
                    f"{label}_raw_return_pct",
                    np.nan
                )
            )

            output[f"{label}_expected_return_pct"] = (
                reaction.get(
                    f"{label}_expected_return_pct",
                    np.nan
                )
            )

            output[f"{label}_abnormal_return_pct"] = (
                reaction.get(
                    f"{label}_abnormal_return_pct",
                    np.nan
                )
            )

            output[f"{label}_reaction_class"] = (
                reaction.get(
                    f"{label}_reaction_class",
                    "UNKNOWN"
                )
            )

            car_key = f"car_{label}_pct"

            output[car_key] = reaction.get(
                car_key,
                np.nan
            )

        event_rows.append(output)

        if counter % 100 == 0 or counter == total:
            print(
                f"Processed {counter}/{total} events"
            )

    result = pd.DataFrame(event_rows)

    return result


# ============================================================
# BUILD DAILY EVENT STUDY
# ============================================================

def build_daily_event_study(
    earnings_df,
    market_data
):
    """
    Create a long-format daily event-study dataset.

    One row represents:

        one earnings event
        one event day
        one market session

    Event days:
        +1 through +20
    """

    print("=" * 60)
    print("BUILDING DAILY EVENT STUDY")
    print("=" * 60)

    rows = []

    for event_id, (_, row) in enumerate(
        earnings_df.iterrows(),
        start=1
    ):

        event_date = row["reported_date"]

        reference_session = get_reference_session(
            market_data,
            event_date
        )

        if reference_session is None:
            continue

        reference_close = safe_float(
            market_data.loc[
                reference_session,
                "Close"
            ]
        )

        if pd.isna(reference_close):
            continue

        baseline = calculate_historical_baseline(
            market_data,
            event_date
        )

        mean_daily_return = safe_float(
            baseline["mean_daily_return"]
        )

        future_sessions = get_future_sessions(
            market_data,
            event_date,
            MFE_MAE_WINDOW
        )

        if len(future_sessions) == 0:
            continue

        previous_close = reference_close

        cumulative_raw = 1.0
        cumulative_expected = 1.0
        cumulative_abnormal = 0.0

        for event_day, session in enumerate(
            future_sessions,
            start=1
        ):

            close = safe_float(
                market_data.loc[
                    session,
                    "Close"
                ]
            )

            if pd.isna(close) or close == 0:
                continue

            daily_raw = (
                close / previous_close - 1.0
            )

            if pd.isna(mean_daily_return):
                daily_expected = np.nan
                daily_abnormal = np.nan
            else:
                daily_expected = mean_daily_return
                daily_abnormal = (
                    daily_raw - daily_expected
                )

            cumulative_raw *= (
                1.0 + daily_raw
            )

            if not pd.isna(daily_expected):
                cumulative_expected *= (
                    1.0 + daily_expected
                )

            if not pd.isna(daily_abnormal):
                cumulative_abnormal += (
                    daily_abnormal
                )

            cumulative_raw_return = (
                cumulative_raw - 1.0
            )

            if pd.isna(mean_daily_return):
                cumulative_expected_return = np.nan
            else:
                cumulative_expected_return = (
                    cumulative_expected - 1.0
                )

            rows.append({
                "event_id": event_id,

                "ticker": row["ticker"],
                "sector": row["sector"],
                "fiscal_date_ending": (
                    row["fiscal_date_ending"]
                ),
                "reported_date": (
                    event_date.strftime("%Y-%m-%d")
                ),

                "eps_actual": row["eps_actual"],
                "eps_consensus": row["eps_consensus"],
                "eps_surprise": row["eps_surprise"],
                "eps_surprise_pct": row[
                    "eps_surprise_pct"
                ],
                "eps_result_class": row[
                    "eps_result_class"
                ],

                "point_in_time_safe": row[
                    "point_in_time_safe"
                ],

                "historical_analog_eligible": row[
                    "historical_analog_eligible"
                ],

                "reference_session": (
                    reference_session.strftime(
                        "%Y-%m-%d"
                    )
                ),

                "event_session": (
                    session.strftime(
                        "%Y-%m-%d"
                    )
                ),

                "event_day": event_day,

                "reference_close": reference_close,
                "close": close,

                "daily_raw_return": daily_raw,
                "daily_expected_return": (
                    daily_expected
                ),
                "daily_abnormal_return": (
                    daily_abnormal
                ),

                "cumulative_raw_return": (
                    cumulative_raw_return
                ),

                "cumulative_expected_return": (
                    cumulative_expected_return
                ),

                "cumulative_abnormal_return": (
                    cumulative_abnormal
                ),

                "market_baseline_n": baseline[
                    "estimation_n"
                ],

                "market_baseline_mean_daily_return": (
                    baseline[
                        "mean_daily_return"
                    ]
                ),

                "market_baseline_std_daily_return": (
                    baseline[
                        "std_daily_return"
                    ]
                ),

                "market_reaction_point_in_time_safe": True,
            })

            previous_close = close

    result = pd.DataFrame(rows)

    print(
        f"Daily event-study rows: {len(result)}"
    )

    return result


# ============================================================
# ABNORMAL RETURN DATASET
# ============================================================

def build_abnormal_return_dataset(
    daily_event_study
):
    """
    Build a clean abnormal-return table.

    This is intentionally long-format and is useful for
    later statistical research.
    """

    if daily_event_study.empty:
        return pd.DataFrame()

    columns = [
        "event_id",
        "ticker",
        "sector",
        "reported_date",
        "event_day",
        "eps_result_class",
        "eps_surprise",
        "eps_surprise_pct",
        "daily_raw_return",
        "daily_expected_return",
        "daily_abnormal_return",
        "cumulative_raw_return",
        "cumulative_expected_return",
        "cumulative_abnormal_return",
        "market_baseline_n",
        "market_baseline_mean_daily_return",
        "market_baseline_std_daily_return",
        "market_reaction_point_in_time_safe",
    ]

    available = [
        col for col in columns
        if col in daily_event_study.columns
    ]

    result = daily_event_study[
        available
    ].copy()

    return result


# ============================================================
# STATISTICAL SUMMARY
# ============================================================

def calculate_statistics(series):
    """
    Calculate exploratory descriptive and normal-approximation
    statistics for a numeric return series.
    """

    values = pd.to_numeric(
        series,
        errors="coerce"
    ).dropna()

    n = len(values)

    if n == 0:
        return {
            "n": 0,
            "mean": np.nan,
            "median": np.nan,
            "std": np.nan,
            "p25": np.nan,
            "p75": np.nan,
            "min": np.nan,
            "max": np.nan,
            "positive_pct": np.nan,
            "negative_pct": np.nan,
            "t_stat": np.nan,
            "p_value": np.nan,
            "ci95_low": np.nan,
            "ci95_high": np.nan,
        }

    mean = values.mean()

    median = values.median()

    std = (
        values.std(ddof=1)
        if n > 1
        else np.nan
    )

    p25 = values.quantile(0.25)
    p75 = values.quantile(0.75)

    minimum = values.min()
    maximum = values.max()

    positive_pct = (
        (values > 0).mean() * 100.0
    )

    negative_pct = (
        (values < 0).mean() * 100.0
    )

    if n > 1 and not pd.isna(std) and std > 0:
        standard_error = (
            std / math.sqrt(n)
        )

        t_stat = (
            mean / standard_error
        )

        p_value = normal_approx_p_value(
            t_stat
        )

        ci95_low = (
            mean - Z_95 * standard_error
        )

        ci95_high = (
            mean + Z_95 * standard_error
        )

    else:
        t_stat = np.nan
        p_value = np.nan
        ci95_low = np.nan
        ci95_high = np.nan

    return {
        "n": n,
        "mean": mean,
        "median": median,
        "std": std,
        "p25": p25,
        "p75": p75,
        "min": minimum,
        "max": maximum,
        "positive_pct": positive_pct,
        "negative_pct": negative_pct,
        "t_stat": t_stat,
        "p_value": p_value,
        "ci95_low": ci95_low,
        "ci95_high": ci95_high,
    }


# ============================================================
# OVERALL SUMMARY
# ============================================================

def calculate_overall_summary(
    reaction_df
):
    """
    Calculate overall event-study statistics.

    One row per horizon.
    """

    rows = []

    for label in HORIZONS:

        column = f"{label}_raw_return_pct"

        if column not in reaction_df.columns:
            continue

        stats = calculate_statistics(
            reaction_df[column]
        )

        rows.append({
            "horizon": label,
            "return_type": "RAW_RETURN",
            **stats,
        })

        abnormal_column = (
            f"{label}_abnormal_return_pct"
        )

        if abnormal_column in reaction_df.columns:

            abnormal_stats = calculate_statistics(
                reaction_df[abnormal_column]
            )

            rows.append({
                "horizon": label,
                "return_type": "ABNORMAL_RETURN",
                **abnormal_stats,
            })

        car_column = f"car_{label}_pct"

        if car_column in reaction_df.columns:

            car_stats = calculate_statistics(
                reaction_df[car_column]
            )

            rows.append({
                "horizon": label,
                "return_type": "CAR",
                **car_stats,
            })

    return pd.DataFrame(rows)


# ============================================================
# EPS CLASS SUMMARY
# ============================================================

def calculate_eps_class_summary(
    reaction_df
):
    """
    Compare 5D market reactions by EPS surprise class.

    This is descriptive and does not establish causality.
    """

    rows = []

    column = "5d_raw_return_pct"

    if column not in reaction_df.columns:
        return pd.DataFrame()

    for eps_class, group in reaction_df.groupby(
        "eps_result_class",
        dropna=False
    ):

        stats = calculate_statistics(
            group[column]
        )

        rows.append({
            "eps_result_class": eps_class,
            "horizon": "5d",
            **stats,
        })

    return pd.DataFrame(rows).sort_values(
        "eps_result_class"
    ).reset_index(drop=True)


# ============================================================
# SECTOR SUMMARY
# ============================================================

def calculate_sector_summary(
    reaction_df
):
    """
    Compare 5D market reactions by sector.

    Again, this is descriptive research only.
    """

    rows = []

    column = "5d_raw_return_pct"

    if column not in reaction_df.columns:
        return pd.DataFrame()

    for sector, group in reaction_df.groupby(
        "sector",
        dropna=False
    ):

        stats = calculate_statistics(
            group[column]
        )

        rows.append({
            "sector": sector,
            "horizon": "5d",
            **stats,
        })

    return pd.DataFrame(rows).sort_values(
        "sector"
    ).reset_index(drop=True)


# ============================================================
# SAVE DATASETS
# ============================================================

def save_outputs(
    reaction_df,
    daily_event_study,
    abnormal_df,
    overall_summary,
    eps_summary,
    sector_summary
):
    """
    Save all V4 research outputs.
    """

    print("=" * 60)
    print("SAVING V4 OUTPUTS")
    print("=" * 60)

    reaction_file = (
        "earnings_market_reaction_v4.csv"
    )

    event_study_file = (
        "earnings_event_study_v4.csv"
    )

    abnormal_file = (
        "earnings_abnormal_return_v4.csv"
    )

    summary_file = (
        "earnings_market_reaction_summary_v4.csv"
    )

    eps_file = (
        "earnings_reaction_by_eps_class_v4.csv"
    )

    sector_file = (
        "earnings_reaction_by_sector_v4.csv"
    )

    reaction_df.to_csv(
        reaction_file,
        index=False
    )

    daily_event_study.to_csv(
        event_study_file,
        index=False
    )

    abnormal_df.to_csv(
        abnormal_file,
        index=False
    )

    overall_summary.to_csv(
        summary_file,
        index=False
    )

    eps_summary.to_csv(
        eps_file,
        index=False
    )

    sector_summary.to_csv(
        sector_file,
        index=False
    )

    files = [
        reaction_file,
        event_study_file,
        abnormal_file,
        summary_file,
        eps_file,
        sector_file,
    ]

    for filename in files:
        print(f"Created: {filename}")


# ============================================================
# MAIN
# ============================================================

def main():
    """
    Main V4 execution pipeline.
    """

    print()
    print("=" * 70)
    print("CORPORATE EARNINGS INTELLIGENCE V4")
    print("=" * 70)
    print("Research-only historical event study")
    print("=" * 70)
    print()

    # --------------------------------------------------------
    # 1. Load V2 earnings events
    # --------------------------------------------------------

    earnings_df = load_earnings_data()

    if earnings_df.empty:
        raise RuntimeError(
            "No earnings events available."
        )

    # --------------------------------------------------------
    # 2. Download market data
    # --------------------------------------------------------

    market_data = download_market_data(
        earnings_df
    )

    # --------------------------------------------------------
    # 3. Build event-level reaction dataset
    # --------------------------------------------------------

    reaction_df = build_reaction_dataset(
        earnings_df,
        market_data
    )

    # --------------------------------------------------------
    # 4. Build daily event study
    # --------------------------------------------------------

    daily_event_study = build_daily_event_study(
        earnings_df,
        market_data
    )

    # --------------------------------------------------------
    # 5. Build abnormal-return dataset
    # --------------------------------------------------------

    abnormal_df = build_abnormal_return_dataset(
        daily_event_study
    )

    # --------------------------------------------------------
    # 6. Calculate summaries
    # --------------------------------------------------------

    overall_summary = calculate_overall_summary(
        reaction_df
    )

    eps_summary = calculate_eps_class_summary(
        reaction_df
    )

    sector_summary = calculate_sector_summary(
        reaction_df
    )

    # --------------------------------------------------------
    # 7. Save outputs
    # --------------------------------------------------------

    save_outputs(
        reaction_df,
        daily_event_study,
        abnormal_df,
        overall_summary,
        eps_summary,
        sector_summary
    )

    # --------------------------------------------------------
    # 8. Console summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("V4 SUMMARY")
    print("=" * 70)

    print()
    print("Events:")
    print(len(reaction_df))

    if (
        "market_reaction_available"
        in reaction_df.columns
    ):
        available_count = int(
            reaction_df[
                "market_reaction_available"
            ].sum()
        )

        print(
            f"Market reaction available: "
            f"{available_count}/{len(reaction_df)}"
        )

    print()
    print("Overall reaction summary:")

    if not overall_summary.empty:
        print(
            overall_summary.to_string(
                index=False
            )
        )

    print()
    print("EPS class summary:")

    if not eps_summary.empty:
        print(
            eps_summary.to_string(
                index=False
            )
        )

    print()
    print("Sector summary:")

    if not sector_summary.empty:
        print(
            sector_summary.to_string(
                index=False
            )
        )

    print()
    print("=" * 70)
    print("CORPORATE EARNINGS INTELLIGENCE V4 COMPLETED")
    print("=" * 70)
    print()
    print("Research-only.")
    print("No trading signal generated.")
    print("No Decision Engine integration.")
    print()


if __name__ == "__main__":
    main()
