"""
Corporate Earnings Intelligence V5
Contextual Event Study

Research-only module.
No trade execution.
No buy/sell signal.
No Decision Engine integration.

Purpose:
- Start from the point-in-time-safe Corporate Earnings V2 event dataset.
- Measure S&P 500 reaction around earnings events.
- Add pre-event market trend, volatility, EPS surprise size,
  and earnings-breadth context.
- Preserve V4 timing conventions.
- Avoid look-ahead bias when constructing event context.

Input:
    earnings_breadth_events_v2.csv

Outputs:
    earnings_contextual_event_study_v5.csv
    earnings_context_by_market_regime_v5.csv
    earnings_context_by_surprise_size_v5.csv
    earnings_context_by_volatility_v5.csv
    earnings_context_by_breadth_v5.csv
    earnings_context_summary_v5.csv
"""

import math
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ============================================================
# CONFIGURATION
# ============================================================

INPUT_FILE = "earnings_breadth_events_v2.csv"
MARKET_TICKER = "^GSPC"

# Larger buffer than V4 so the earliest event has enough history
# for the 60-session estimation window plus pre-event context.
MARKET_START_BUFFER_DAYS = 220
MARKET_END_BUFFER_DAYS = 180

# V4 timing convention:
# reference close = last trading session <= reported date
# future reaction starts on first trading session strictly AFTER
# reported date.
HORIZONS = {
    "1d": 1,
    "3d": 3,
    "5d": 5,
    "20d": 20,
}

PRE_EVENT_HORIZONS = {
    "pre_5d": 5,
    "pre_20d": 20,
}

# Historical expected-return estimation:
# 60 trading sessions ending 5 sessions before the event.
ESTIMATION_WINDOW = 60
ESTIMATION_GAP = 5

# Volatility uses the same estimation window.
VOLATILITY_WINDOW = 20

# MFE/MAE after the event.
MFE_MAE_WINDOW = 20

# Reaction classification copied from V3/V4.
STRONG_POSITIVE_THRESHOLD = 2.0
POSITIVE_THRESHOLD = 0.25
NEUTRAL_THRESHOLD = -0.25
NEGATIVE_THRESHOLD = -2.0

# Market-regime thresholds for pre-event returns.
# These are descriptive bins, not trading recommendations.
PRE_5D_UP_THRESHOLD = 1.0
PRE_5D_DOWN_THRESHOLD = -1.0

PRE_20D_UP_THRESHOLD = 3.0
PRE_20D_DOWN_THRESHOLD = -3.0

# EPS surprise-size thresholds.
SURPRISE_LARGE_POSITIVE = 10.0
SURPRISE_MODERATE_POSITIVE = 3.0
SURPRISE_NEAR_CONSENSUS = -3.0
SURPRISE_MODERATE_NEGATIVE = -10.0

# Volatility regime is based on the event's 20-session annualized
# volatility relative to the cross-sectional median of valid events.
VOLATILITY_LOW_PERCENTILE = 33.333333
VOLATILITY_HIGH_PERCENTILE = 66.666667

# Breadth context is calculated from earnings events whose
# reported date is strictly BEFORE the current event.
# This prevents using same-day/future earnings information.
BREADTH_LOOKBACK_EVENTS = 50


# ============================================================
# BASIC HELPERS
# ============================================================

def safe_float(value):
    """Convert a value to float, returning NaN when unavailable."""
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return np.nan
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def classify_reaction(return_pct):
    """Classify S&P 500 reaction using V3/V4 thresholds."""
    if pd.isna(return_pct):
        return "UNAVAILABLE"

    if return_pct >= STRONG_POSITIVE_THRESHOLD:
        return "STRONG_POSITIVE"

    if return_pct > POSITIVE_THRESHOLD:
        return "POSITIVE"

    if return_pct >= NEUTRAL_THRESHOLD:
        return "NEUTRAL"

    if return_pct > NEGATIVE_THRESHOLD:
        return "NEGATIVE"

    return "STRONG_NEGATIVE"


def classify_market_regime(pre_5d, pre_20d):
    """
    Descriptive pre-event market regime.

    Priority is given to the combination of 5D and 20D direction.
    This is not a forecast or signal.
    """
    if pd.isna(pre_5d) or pd.isna(pre_20d):
        return "UNKNOWN"

    if pre_5d >= PRE_5D_UP_THRESHOLD and pre_20d >= PRE_20D_UP_THRESHOLD:
        return "UPTREND_STRONG"

    if pre_5d <= PRE_5D_DOWN_THRESHOLD and pre_20d <= PRE_20D_DOWN_THRESHOLD:
        return "DOWNTREND_STRONG"

    if pre_5d >= PRE_5D_UP_THRESHOLD and pre_20d < PRE_20D_DOWN_THRESHOLD:
        return "SHORT_TERM_UP_LONG_TERM_DOWN"

    if pre_5d < PRE_5D_DOWN_THRESHOLD and pre_20d >= PRE_20D_UP_THRESHOLD:
        return "SHORT_TERM_DOWN_LONG_TERM_UP"

    if pre_5d >= PRE_5D_UP_THRESHOLD:
        return "SHORT_TERM_UP"

    if pre_5d <= PRE_5D_DOWN_THRESHOLD:
        return "SHORT_TERM_DOWN"

    if pre_20d >= PRE_20D_UP_THRESHOLD:
        return "LONG_TERM_UP"

    if pre_20d <= PRE_20D_DOWN_THRESHOLD:
        return "LONG_TERM_DOWN"

    return "RANGE_NEUTRAL"


def classify_surprise_size(surprise_pct):
    """Classify continuous EPS surprise percentage."""
    if pd.isna(surprise_pct):
        return "UNKNOWN"

    if surprise_pct >= SURPRISE_LARGE_POSITIVE:
        return "LARGE_POSITIVE"

    if surprise_pct >= SURPRISE_MODERATE_POSITIVE:
        return "MODERATE_POSITIVE"

    if surprise_pct > SURPRISE_NEAR_CONSENSUS:
        return "NEAR_CONSENSUS"

    if surprise_pct > SURPRISE_MODERATE_NEGATIVE:
        return "MODERATE_NEGATIVE"

    return "LARGE_NEGATIVE"


def annualized_volatility(daily_returns):
    """Annualize standard deviation of daily returns."""
    series = pd.Series(daily_returns).dropna()

    if len(series) < 2:
        return np.nan

    return float(series.std(ddof=1) * math.sqrt(252) * 100.0)


def normal_two_sided_pvalue(t_stat):
    """
    Two-sided normal approximation.

    This is intentionally labelled exploratory. It is not a replacement
    for a clustered/event-study inference framework.
    """
    if pd.isna(t_stat):
        return np.nan

    return float(math.erfc(abs(float(t_stat)) / math.sqrt(2.0)))


def mean_confidence_interval(values):
    """Return mean, standard error and 95% normal-approximation CI."""
    series = pd.Series(values).dropna()
    n = len(series)

    if n == 0:
        return np.nan, np.nan, np.nan, np.nan

    mean = float(series.mean())

    if n < 2:
        return mean, np.nan, np.nan, np.nan

    std = float(series.std(ddof=1))
    se = std / math.sqrt(n)
    margin = 1.96 * se

    return mean, se, mean - margin, mean + margin


# ============================================================
# LOAD EARNINGS EVENTS
# ============================================================

def load_earnings_data():
    """Load and validate the point-in-time-safe V2 event dataset."""
    path = Path(INPUT_FILE)

    if not path.exists():
        raise FileNotFoundError(
            f"Required input file not found: {INPUT_FILE}"
        )

    df = pd.read_csv(path)

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

    missing = [c for c in required_columns if c not in df.columns]

    if missing:
        raise ValueError(
            "Missing required V2 columns: " + ", ".join(missing)
        )

    df["reported_date"] = pd.to_datetime(
        df["reported_date"],
        errors="coerce",
    )

    df = df.dropna(subset=["reported_date"]).copy()

    df["eps_surprise_pct"] = pd.to_numeric(
        df["eps_surprise_pct"],
        errors="coerce",
    )

    df["point_in_time_safe"] = (
        df["point_in_time_safe"]
        .astype(str)
        .str.lower()
        .isin(["true", "1", "yes"])
    )

    df["historical_analog_eligible"] = (
        df["historical_analog_eligible"]
        .astype(str)
        .str.lower()
        .isin(["true", "1", "yes"])
    )

    # Preserve deterministic ordering.
    df = (
        df.sort_values(
            ["reported_date", "ticker"],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )

    print(f"Earnings events loaded: {len(df)}")

    safe_count = int(df["point_in_time_safe"].sum())
    eligible_count = int(df["historical_analog_eligible"].sum())

    print(f"Point-in-time-safe events: {safe_count}/{len(df)}")
    print(f"Historical-analog-eligible: {eligible_count}/{len(df)}")

    return df


# ============================================================
# MARKET DATA
# ============================================================

def download_market_data(events):
    """Download S&P 500 daily OHLC data."""
    min_date = events["reported_date"].min()
    max_date = events["reported_date"].max()

    start = (
        min_date
        - pd.Timedelta(days=MARKET_START_BUFFER_DAYS)
    ).strftime("%Y-%m-%d")

    end = (
        max_date
        + pd.Timedelta(days=MARKET_END_BUFFER_DAYS)
    ).strftime("%Y-%m-%d")

    print(f"Market ticker: {MARKET_TICKER}")
    print(f"Market start: {start}")
    print(f"Market end: {end}")

    data = yf.download(
        MARKET_TICKER,
        start=start,
        end=end,
        auto_adjust=False,
        interval="1d",
        progress=False,
        threads=False,
    )

    if data is None or data.empty:
        raise RuntimeError(
            f"No market data downloaded for {MARKET_TICKER}"
        )

    # yfinance can return MultiIndex columns.
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [
            col[0] if isinstance(col, tuple) else col
            for col in data.columns
        ]

    data = data.copy()

    data.index = pd.to_datetime(data.index)

    # Normalize timezone if present.
    try:
        if data.index.tz is not None:
            data.index = data.index.tz_localize(None)
    except Exception:
        pass

    data = data.sort_index()

    required = ["Close", "High", "Low"]

    for col in required:
        if col not in data.columns:
            raise RuntimeError(
                f"Market data missing required column: {col}"
            )

        data[col] = pd.to_numeric(
            data[col],
            errors="coerce",
        )

    data = data.dropna(subset=["Close"])

    # Daily close-to-close returns.
    data["daily_return_pct"] = (
        data["Close"].pct_change() * 100.0
    )

    print(f"Trading sessions downloaded: {len(data)}")

    return data


# ============================================================
# TRADING SESSION HELPERS
# ============================================================

def get_reference_position(index, event_date):
    """
    Return the position of the last trading session <= event date.
    """
    dates = pd.DatetimeIndex(index)

    pos = dates.searchsorted(event_date, side="right") - 1

    if pos < 0:
        return None

    return int(pos)


def get_future_positions(index, event_date, horizon):
    """
    Return positions for the first N trading sessions strictly after
    the reported date.
    """
    dates = pd.DatetimeIndex(index)

    first = dates.searchsorted(event_date, side="right")

    if first >= len(dates):
        return []

    last = min(first + horizon, len(dates))

    return list(range(first, last))


# ============================================================
# PRE-EVENT CONTEXT
# ============================================================

def calculate_pre_event_context(market, ref_pos):
    """
    Calculate market returns before the event.

    pre_5d:
        Reference close vs close 5 trading sessions before reference.

    pre_20d:
        Reference close vs close 20 trading sessions before reference.

    These are fully known before/at the event reference close.
    """
    result = {
        "pre_5d_return_pct": np.nan,
        "pre_20d_return_pct": np.nan,
    }

    if ref_pos is None:
        return result

    reference_close = safe_float(
        market.iloc[ref_pos]["Close"]
    )

    if pd.isna(reference_close) or reference_close == 0:
        return result

    for key, sessions in PRE_EVENT_HORIZONS.items():
        old_pos = ref_pos - sessions

        if old_pos < 0:
            continue

        old_close = safe_float(
            market.iloc[old_pos]["Close"]
        )

        if pd.isna(old_close) or old_close == 0:
            continue

        result[f"{key}_return_pct"] = (
            (reference_close / old_close - 1.0) * 100.0
        )

    return result


# ============================================================
# HISTORICAL BASELINE + VOLATILITY
# ============================================================

def calculate_estimation_context(market, ref_pos):
    """
    Calculate historical market baseline and volatility.

    Estimation window:
        60 trading sessions
        ending 5 sessions before the event reference session.

    Therefore event information is excluded from the estimation window.
    """
    result = {
        "estimation_n": 0,
        "expected_daily_return_pct": np.nan,
        "expected_1d_return_pct": np.nan,
        "expected_3d_return_pct": np.nan,
        "expected_5d_return_pct": np.nan,
        "expected_20d_return_pct": np.nan,
        "pre_event_volatility_20d_pct": np.nan,
        "pre_event_volatility_regime": "UNKNOWN",
    }

    if ref_pos is None:
        return result

    end_pos = ref_pos - ESTIMATION_GAP

    if end_pos < 0:
        return result

    start_pos = end_pos - ESTIMATION_WINDOW + 1

    if start_pos < 0:
        return result

    window = market.iloc[start_pos : end_pos + 1].copy()

    daily_returns = pd.to_numeric(
        window["daily_return_pct"],
        errors="coerce",
    ).dropna()

    n = len(daily_returns)

    result["estimation_n"] = int(n)

    if n == 0:
        return result

    expected_daily = float(daily_returns.mean())

    result["expected_daily_return_pct"] = expected_daily

    for label, horizon in HORIZONS.items():
        # Compound historical mean daily return.
        expected = (
            (1.0 + expected_daily / 100.0) ** horizon - 1.0
        ) * 100.0

        result[f"expected_{label}_return_pct"] = expected

    recent_vol = daily_returns.tail(VOLATILITY_WINDOW)

    if len(recent_vol) >= 2:
        result["pre_event_volatility_20d_pct"] = (
            annualized_volatility(recent_vol)
        )

    return result


# ============================================================
# EVENT REACTION
# ============================================================

def calculate_event_reaction(market, event_date, ref_pos):
    """
    Calculate raw S&P 500 reaction after an earnings event.

    V4 timing convention:
        reference = last session <= event date
        day +1 = first session strictly > event date
    """
    result = {
        "reference_market_date": pd.NaT,
        "reference_close": np.nan,
        "market_reaction_available": False,
        "mfe_20d_pct": np.nan,
        "mae_20d_pct": np.nan,
    }

    for label in HORIZONS:
        result[f"{label}_market_date"] = pd.NaT
        result[f"{label}_market_return_pct"] = np.nan
        result[f"{label}_reaction_class"] = "UNAVAILABLE"
        result[f"{label}_abnormal_return_pct"] = np.nan

    if ref_pos is None:
        return result

    reference_date = market.index[ref_pos]
    reference_close = safe_float(
        market.iloc[ref_pos]["Close"]
    )

    if pd.isna(reference_close) or reference_close == 0:
        return result

    result["reference_market_date"] = reference_date
    result["reference_close"] = reference_close

    future_positions = get_future_positions(
        market.index,
        event_date,
        MFE_MAE_WINDOW,
    )

    if not future_positions:
        return result

    result["market_reaction_available"] = True

    # MFE/MAE use high/low during the first 20 sessions.
    highs = pd.to_numeric(
        market.iloc[future_positions]["High"],
        errors="coerce",
    )

    lows = pd.to_numeric(
        market.iloc[future_positions]["Low"],
        errors="coerce",
    )

    if highs.notna().any():
        result["mfe_20d_pct"] = (
            (highs.max() / reference_close - 1.0) * 100.0
        )

    if lows.notna().any():
        result["mae_20d_pct"] = (
            (lows.min() / reference_close - 1.0) * 100.0
        )

    for label, horizon in HORIZONS.items():
        positions = get_future_positions(
            market.index,
            event_date,
            horizon,
        )

        if len(positions) < horizon:
            continue

        pos = positions[horizon - 1]

        future_close = safe_float(
            market.iloc[pos]["Close"]
        )

        if pd.isna(future_close):
            continue

        raw_return = (
            (future_close / reference_close - 1.0)
            * 100.0
        )

        result[f"{label}_market_date"] = market.index[pos]
        result[f"{label}_market_return_pct"] = raw_return
        result[f"{label}_reaction_class"] = classify_reaction(
            raw_return
        )

    return result


# ============================================================
# DAILY EVENT STUDY
# ============================================================

def build_daily_event_study(
    market,
    event_row,
    ref_pos,
    estimation_context,
):
    """
    Create long-format event-study rows for days +1 through +20.

    Each row contains:
      - raw daily market return
      - expected daily return
      - abnormal daily return
      - cumulative raw return
      - cumulative expected return
      - cumulative abnormal return

    Expected daily return comes from the pre-event historical window.
    """
    rows = []

    if ref_pos is None:
        return rows

    reference_close = safe_float(
        market.iloc[ref_pos]["Close"]
    )

    if pd.isna(reference_close) or reference_close == 0:
        return rows

    expected_daily = safe_float(
        estimation_context["expected_daily_return_pct"]
    )

    future_positions = get_future_positions(
        market.index,
        event_row["reported_date"],
        MFE_MAE_WINDOW,
    )

    if not future_positions:
        return rows

    cumulative_raw_factor = 1.0
    cumulative_expected_factor = 1.0
    cumulative_abnormal = 0.0

    for day_number, pos in enumerate(
        future_positions,
        start=1,
    ):
        row = market.iloc[pos]

        daily_raw = safe_float(
            row["daily_return_pct"]
        )

        if pd.isna(daily_raw):
            continue

        if pd.isna(expected_daily):
            expected_daily_value = np.nan
            abnormal_daily = np.nan
        else:
            expected_daily_value = expected_daily
            abnormal_daily = daily_raw - expected_daily_value

        cumulative_raw_factor *= (
            1.0 + daily_raw / 100.0
        )

        if not pd.isna(expected_daily_value):
            cumulative_expected_factor *= (
                1.0 + expected_daily_value / 100.0
            )
            cumulative_abnormal += abnormal_daily

        cumulative_raw = (
            cumulative_raw_factor - 1.0
        ) * 100.0

        if pd.isna(expected_daily_value):
            cumulative_expected = np.nan
        else:
            cumulative_expected = (
                cumulative_expected_factor - 1.0
            ) * 100.0

        rows.append(
            {
                "ticker": event_row["ticker"],
                "sector": event_row["sector"],
                "fiscal_date_ending": event_row[
                    "fiscal_date_ending"
                ],
                "reported_date": event_row["reported_date"],
                "eps_result_class": event_row[
                    "eps_result_class"
                ],
                "eps_surprise_pct": event_row[
                    "eps_surprise_pct"
                ],
                "event_market_regime": event_row[
                    "market_regime"
                ],
                "surprise_size_class": event_row[
                    "surprise_size_class"
                ],
                "volatility_regime": event_row[
                    "pre_event_volatility_regime"
                ],
                "breadth_regime": event_row[
                    "pre_event_breadth_regime"
                ],
                "event_day": day_number,
                "market_date": market.index[pos],
                "daily_market_return_pct": daily_raw,
                "expected_daily_return_pct": expected_daily_value,
                "abnormal_daily_return_pct": abnormal_daily,
                "cumulative_market_return_pct": cumulative_raw,
                "cumulative_expected_return_pct": cumulative_expected,
                "cumulative_abnormal_return_pct": (
                    cumulative_abnormal
                    if not pd.isna(expected_daily_value)
                    else np.nan
                ),
            }
        )

    return rows


# ============================================================
# BREADTH CONTEXT
# ============================================================

def calculate_historical_breadth_context(
    events,
    current_index,
):
    """
    Calculate earnings breadth using only events strictly before
    the current event.

    Look-ahead protection:
      - current event is excluded
      - same-day events are excluded
      - future events are excluded

    We use the most recent BREADTH_LOOKBACK_EVENTS events.
    """
    current_date = events.loc[
        current_index,
        "reported_date",
    ]

    history = events.loc[
        events["reported_date"] < current_date
    ].copy()

    if history.empty:
        return {
            "pre_event_breadth_n": 0,
            "pre_event_breadth_beat_pct": np.nan,
            "pre_event_breadth_miss_pct": np.nan,
            "pre_event_breadth_inline_pct": np.nan,
            "pre_event_breadth_score": np.nan,
            "pre_event_breadth_regime": "UNKNOWN",
            "pre_event_breadth_avg_surprise_pct": np.nan,
        }

    history = history.tail(BREADTH_LOOKBACK_EVENTS)

    valid = history[
        history["eps_result_class"].isin(
            [
                "BEAT",
                "LARGE_BEAT",
                "MISS",
                "LARGE_MISS",
                "IN_LINE",
            ]
        )
    ].copy()

    n = len(valid)

    if n == 0:
        return {
            "pre_event_breadth_n": 0,
            "pre_event_breadth_beat_pct": np.nan,
            "pre_event_breadth_miss_pct": np.nan,
            "pre_event_breadth_inline_pct": np.nan,
            "pre_event_breadth_score": np.nan,
            "pre_event_breadth_regime": "UNKNOWN",
            "pre_event_breadth_avg_surprise_pct": np.nan,
        }

    beats = valid["eps_result_class"].isin(
        ["BEAT", "LARGE_BEAT"]
    ).sum()

    misses = valid["eps_result_class"].isin(
        ["MISS", "LARGE_MISS"]
    ).sum()

    inline = (
        valid["eps_result_class"] == "IN_LINE"
    ).sum()

    beat_pct = beats / n * 100.0
    miss_pct = misses / n * 100.0
    inline_pct = inline / n * 100.0

    # Same descriptive breadth formula used by V2.
    score = np.clip(
        50.0 + (beat_pct - miss_pct) / 2.0,
        0.0,
        100.0,
    )

    if score >= 70.0:
        regime = "POSITIVE_BREADTH"
    elif score >= 55.0:
        regime = "MILDLY_POSITIVE"
    elif score > 45.0:
        regime = "BALANCED"
    elif score > 30.0:
        regime = "MILDLY_NEGATIVE"
    else:
        regime = "NEGATIVE_BREADTH"

    avg_surprise = safe_float(
        valid["eps_surprise_pct"].mean()
    )

    return {
        "pre_event_breadth_n": int(n),
        "pre_event_breadth_beat_pct": beat_pct,
        "pre_event_breadth_miss_pct": miss_pct,
        "pre_event_breadth_inline_pct": inline_pct,
        "pre_event_breadth_score": float(score),
        "pre_event_breadth_regime": regime,
        "pre_event_breadth_avg_surprise_pct": avg_surprise,
    }


# ============================================================
# BUILD EVENT DATASET
# ============================================================

def build_contextual_dataset(events, market):
    """Build one contextual V5 row per earnings event."""
    rows = []
    daily_rows = []

    for i, event in events.iterrows():
        event_date = event["reported_date"]

        ref_pos = get_reference_position(
            market.index,
            event_date,
        )

        pre_context = calculate_pre_event_context(
            market,
            ref_pos,
        )

        estimation_context = calculate_estimation_context(
            market,
            ref_pos,
        )

        reaction = calculate_event_reaction(
            market,
            event_date,
            ref_pos,
        )

        market_regime = classify_market_regime(
            pre_context["pre_5d_return_pct"],
            pre_context["pre_20d_return_pct"],
        )

        surprise_size = classify_surprise_size(
            event["eps_surprise_pct"]
        )

        base = event.to_dict()

        base.update(pre_context)
        base.update(estimation_context)
        base.update(reaction)

        base["market_regime"] = market_regime
        base["surprise_size_class"] = surprise_size

        # These will be populated in the second pass so volatility
        # and breadth regimes use information available at event time.
        base["pre_event_breadth_n"] = np.nan
        base["pre_event_breadth_beat_pct"] = np.nan
        base["pre_event_breadth_miss_pct"] = np.nan
        base["pre_event_breadth_inline_pct"] = np.nan
        base["pre_event_breadth_score"] = np.nan
        base["pre_event_breadth_regime"] = "UNKNOWN"
        base["pre_event_breadth_avg_surprise_pct"] = np.nan

        base["pre_event_volatility_regime"] = "UNKNOWN"

        # Point-in-time flags.
        base["context_point_in_time_safe"] = bool(
            event["point_in_time_safe"]
        )

        base["context_historical_analog_eligible"] = bool(
            event["historical_analog_eligible"]
        )

        rows.append(base)

    df = pd.DataFrame(rows)

    if df.empty:
        return df, pd.DataFrame()

    # --------------------------------------------------------
    # Volatility regimes
    # --------------------------------------------------------

    volatility_values = pd.to_numeric(
        df["pre_event_volatility_20d_pct"],
        errors="coerce",
    )

    valid_vol = volatility_values.dropna()

    if len(valid_vol) >= 3:
        low_cut = np.percentile(
            valid_vol,
            VOLATILITY_LOW_PERCENTILE,
        )

        high_cut = np.percentile(
            valid_vol,
            VOLATILITY_HIGH_PERCENTILE,
        )

        def volatility_class(value):
            if pd.isna(value):
                return "UNKNOWN"

            if value <= low_cut:
                return "LOW_VOLATILITY"

            if value >= high_cut:
                return "HIGH_VOLATILITY"

            return "MEDIUM_VOLATILITY"

        df["pre_event_volatility_regime"] = (
            volatility_values.apply(volatility_class)
        )

    # --------------------------------------------------------
    # Historical earnings breadth
    # --------------------------------------------------------

    # Events are already sorted chronologically.
    # Calculate breadth for each event independently using only
    # dates strictly before that event.
    for i in range(len(df)):
        current_date = df.loc[i, "reported_date"]

        history = df.loc[
            df["reported_date"] < current_date
        ].copy()

        if history.empty:
            continue

        history = history.tail(
            BREADTH_LOOKBACK_EVENTS
        )

        valid = history[
            history["eps_result_class"].isin(
                [
                    "BEAT",
                    "LARGE_BEAT",
                    "MISS",
                    "LARGE_MISS",
                    "IN_LINE",
                ]
            )
        ]

        if valid.empty:
            continue

        n = len(valid)

        beats = valid["eps_result_class"].isin(
            ["BEAT", "LARGE_BEAT"]
        ).sum()

        misses = valid["eps_result_class"].isin(
            ["MISS", "LARGE_MISS"]
        ).sum()

        inline = (
            valid["eps_result_class"] == "IN_LINE"
        ).sum()

        beat_pct = beats / n * 100.0
        miss_pct = misses / n * 100.0
        inline_pct = inline / n * 100.0

        score = float(
            np.clip(
                50.0 + (beat_pct - miss_pct) / 2.0,
                0.0,
                100.0,
            )
        )

        if score >= 70.0:
            breadth_regime = "POSITIVE_BREADTH"
        elif score >= 55.0:
            breadth_regime = "MILDLY_POSITIVE"
        elif score > 45.0:
            breadth_regime = "BALANCED"
        elif score > 30.0:
            breadth_regime = "MILDLY_NEGATIVE"
        else:
            breadth_regime = "NEGATIVE_BREADTH"

        avg_surprise = safe_float(
            valid["eps_surprise_pct"].mean()
        )

        df.loc[i, "pre_event_breadth_n"] = n
        df.loc[i, "pre_event_breadth_beat_pct"] = beat_pct
        df.loc[i, "pre_event_breadth_miss_pct"] = miss_pct
        df.loc[i, "pre_event_breadth_inline_pct"] = inline_pct
        df.loc[i, "pre_event_breadth_score"] = score
        df.loc[i, "pre_event_breadth_regime"] = breadth_regime
        df.loc[i, "pre_event_breadth_avg_surprise_pct"] = (
            avg_surprise
        )

    # --------------------------------------------------------
    # Add abnormal-return fields
    # --------------------------------------------------------

    for label in HORIZONS:
        raw_col = f"{label}_market_return_pct"
        expected_col = f"expected_{label}_return_pct"
        abnormal_col = f"{label}_abnormal_return_pct"

        df[abnormal_col] = (
            pd.to_numeric(df[raw_col], errors="coerce")
            - pd.to_numeric(df[expected_col], errors="coerce")
        )

    # --------------------------------------------------------
    # Build daily event-study rows
    # --------------------------------------------------------

    for i, event in df.iterrows():
        event_date = event["reported_date"]

        ref_pos = get_reference_position(
            market.index,
            event_date,
        )

        event_daily_rows = build_daily_event_study(
            market,
            event,
            ref_pos,
            {
                "expected_daily_return_pct": event[
                    "expected_daily_return_pct"
                ],
            },
        )

        daily_rows.extend(event_daily_rows)

    daily_df = pd.DataFrame(daily_rows)

    return df, daily_df


# ============================================================
# SUMMARY STATISTICS
# ============================================================

def summarize_series(series):
    """Return descriptive and exploratory inference statistics."""
    values = pd.to_numeric(
        series,
        errors="coerce",
    ).dropna()

    n = len(values)

    if n == 0:
        return {
            "n": 0,
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
            "ci95_low_pct": np.nan,
            "ci95_high_pct": np.nan,
        }

    mean = float(values.mean())
    median = float(values.median())

    std = (
        float(values.std(ddof=1))
        if n >= 2
        else np.nan
    )

    positive_pct = float(
        (values > 0).mean() * 100.0
    )

    negative_pct = float(
        (values < 0).mean() * 100.0
    )

    if n >= 2 and std > 0:
        t_stat = mean / (std / math.sqrt(n))
        p_value = normal_two_sided_pvalue(t_stat)
        ci_low = mean - 1.96 * std / math.sqrt(n)
        ci_high = mean + 1.96 * std / math.sqrt(n)
    else:
        t_stat = np.nan
        p_value = np.nan
        ci_low = np.nan
        ci_high = np.nan

    return {
        "n": int(n),
        "mean_pct": mean,
        "median_pct": median,
        "std_pct": std,
        "p25_pct": float(values.quantile(0.25)),
        "p75_pct": float(values.quantile(0.75)),
        "min_pct": float(values.min()),
        "max_pct": float(values.max()),
        "positive_pct": positive_pct,
        "negative_pct": negative_pct,
        "t_stat": t_stat,
        "p_value_normal_approx": p_value,
        "ci95_low_pct": ci_low,
        "ci95_high_pct": ci_high,
    }


def grouped_summary(df, group_column, return_column):
    """Create grouped summary for a contextual dimension."""
    records = []

    for group_value, group in df.groupby(
        group_column,
        dropna=False,
    ):
        stats = summarize_series(
            group[return_column]
        )

        record = {
            "group": (
                "UNKNOWN"
                if pd.isna(group_value)
                else group_value
            ),
            "return_measure": return_column,
        }

        record.update(stats)
        records.append(record)

    return pd.DataFrame(records)


# ============================================================
# MAIN SUMMARY
# ============================================================

def build_overall_summary(df):
    """Build overall V5 summary across horizons."""
    records = []

    for label in HORIZONS:
        raw_col = f"{label}_market_return_pct"
        abnormal_col = f"{label}_abnormal_return_pct"

        raw_stats = summarize_series(df[raw_col])
        abnormal_stats = summarize_series(df[abnormal_col])

        records.append(
            {
                "horizon": label,
                "raw_n": raw_stats["n"],
                "raw_mean_pct": raw_stats["mean_pct"],
                "raw_median_pct": raw_stats["median_pct"],
                "raw_std_pct": raw_stats["std_pct"],
                "raw_positive_pct": raw_stats["positive_pct"],
                "raw_negative_pct": raw_stats["negative_pct"],
                "abnormal_n": abnormal_stats["n"],
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
                "abnormal_negative_pct": abnormal_stats[
                    "negative_pct"
                ],
                "abnormal_t_stat": abnormal_stats[
                    "t_stat"
                ],
                "abnormal_p_value_normal_approx": abnormal_stats[
                    "p_value_normal_approx"
                ],
                "abnormal_ci95_low_pct": abnormal_stats[
                    "ci95_low_pct"
                ],
                "abnormal_ci95_high_pct": abnormal_stats[
                    "ci95_high_pct"
                ],
            }
        )

    return pd.DataFrame(records)


# ============================================================
# CONTEXT SUMMARIES
# ============================================================

def build_context_summary(df):
    """
    Combine the main contextual dimensions into one summary table.

    This is descriptive research output, not a ranking.
    """
    frames = []

    dimensions = [
        (
            "MARKET_REGIME",
            "market_regime",
            "5d_market_return_pct",
        ),
        (
            "SURPRISE_SIZE",
            "surprise_size_class",
            "5d_market_return_pct",
        ),
        (
            "VOLATILITY_REGIME",
            "pre_event_volatility_regime",
            "5d_market_return_pct",
        ),
        (
            "BREADTH_REGIME",
            "pre_event_breadth_regime",
            "5d_market_return_pct",
        ),
    ]

    for dimension, group_column, return_column in dimensions:
        summary = grouped_summary(
            df,
            group_column,
            return_column,
        )

        if summary.empty:
            continue

        summary.insert(
            0,
            "context_dimension",
            dimension,
        )

        frames.append(summary)

    if not frames:
        return pd.DataFrame()

    return pd.concat(
        frames,
        ignore_index=True,
    )


# ============================================================
# OUTPUT CLEANING
# ============================================================

def clean_for_csv(df):
    """Make dates and booleans CSV-friendly."""
    out = df.copy()

    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(
            out[col]
        ):
            out[col] = out[col].dt.strftime(
                "%Y-%m-%d"
            )

    return out


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 70)
    print("CORPORATE EARNINGS INTELLIGENCE V5")
    print("CONTEXTUAL EVENT STUDY")
    print("=" * 70)

    events = load_earnings_data()

    if events.empty:
        raise RuntimeError(
            "No valid earnings events available."
        )

    market = download_market_data(events)

    contextual_df, daily_df = build_contextual_dataset(
        events,
        market,
    )

    if contextual_df.empty:
        raise RuntimeError(
            "V5 contextual dataset is empty."
        )

    # --------------------------------------------------------
    # Research eligibility
    # --------------------------------------------------------

    contextual_df["market_reaction_point_in_time_safe"] = (
        contextual_df["market_reaction_available"]
        & contextual_df["context_point_in_time_safe"]
    )

    contextual_df["historical_context_eligible"] = (
        contextual_df["context_historical_analog_eligible"]
        & contextual_df["context_point_in_time_safe"]
    )

    # --------------------------------------------------------
    # Summary tables
    # --------------------------------------------------------

    overall_summary = build_overall_summary(
        contextual_df
    )

    market_regime_summary = grouped_summary(
        contextual_df,
        "market_regime",
        "5d_market_return_pct",
    )

    market_regime_summary["context_dimension"] = (
        "MARKET_REGIME"
    )

    surprise_summary = grouped_summary(
        contextual_df,
        "surprise_size_class",
        "5d_market_return_pct",
    )

    surprise_summary["context_dimension"] = (
        "SURPRISE_SIZE"
    )

    volatility_summary = grouped_summary(
        contextual_df,
        "pre_event_volatility_regime",
        "5d_market_return_pct",
    )

    volatility_summary["context_dimension"] = (
        "VOLATILITY_REGIME"
    )

    breadth_summary = grouped_summary(
        contextual_df,
        "pre_event_breadth_regime",
        "5d_market_return_pct",
    )

    breadth_summary["context_dimension"] = (
        "BREADTH_REGIME"
    )

    context_summary = build_context_summary(
        contextual_df
    )

    # --------------------------------------------------------
    # Add explicit methodological metadata
    # --------------------------------------------------------

    contextual_df["event_study_method"] = (
        "S&P500 raw reaction with pre-event historical-mean baseline"
    )

    contextual_df["causal_interpretation"] = (
        "NOT_ESTABLISHED"
    )

    contextual_df["research_only"] = True
    contextual_df["decision_engine_integrated"] = False

    if not daily_df.empty:
        daily_df["research_only"] = True
        daily_df["decision_engine_integrated"] = False

    # --------------------------------------------------------
    # Save outputs
    # --------------------------------------------------------

    outputs = {
        "earnings_contextual_event_study_v5.csv": contextual_df,
        "earnings_context_by_market_regime_v5.csv": (
            market_regime_summary
        ),
        "earnings_context_by_surprise_size_v5.csv": (
            surprise_summary
        ),
        "earnings_context_by_volatility_v5.csv": (
            volatility_summary
        ),
        "earnings_context_by_breadth_v5.csv": (
            breadth_summary
        ),
        "earnings_context_summary_v5.csv": (
            overall_summary
        ),
    }

    for filename, dataframe in outputs.items():
        clean_for_csv(dataframe).to_csv(
            filename,
            index=False,
        )

        print(
            f"Saved: {filename} "
            f"({len(dataframe)} rows)"
        )

    # --------------------------------------------------------
    # Also save the long-format daily event study.
    # --------------------------------------------------------

    daily_output = (
        "earnings_contextual_daily_event_study_v5.csv"
    )

    if not daily_df.empty:
        clean_for_csv(daily_df).to_csv(
            daily_output,
            index=False,
        )

        print(
            f"Saved: {daily_output} "
            f"({len(daily_df)} rows)"
        )
    else:
        # Create an empty file with no fabricated rows.
        pd.DataFrame().to_csv(
            daily_output,
            index=False,
        )

        print(
            f"Saved: {daily_output} (0 rows)"
        )

    # --------------------------------------------------------
    # Console summary
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("V5 OVERALL SUMMARY")
    print("=" * 70)

    if not overall_summary.empty:
        display_cols = [
            "horizon",
            "raw_n",
            "raw_mean_pct",
            "abnormal_mean_pct",
            "abnormal_t_stat",
            "abnormal_p_value_normal_approx",
        ]

        print(
            overall_summary[
                display_cols
            ].to_string(index=False)
        )

    print()
    print("=" * 70)
    print("MARKET REGIME — 5D REACTION")
    print("=" * 70)

    if not market_regime_summary.empty:
        print(
            market_regime_summary.to_string(
                index=False
            )
        )

    print()
    print("=" * 70)
    print("EPS SURPRISE SIZE — 5D REACTION")
    print("=" * 70)

    if not surprise_summary.empty:
        print(
            surprise_summary.to_string(
                index=False
            )
        )

    print()
    print("=" * 70)
    print("VOLATILITY REGIME — 5D REACTION")
    print("=" * 70)

    if not volatility_summary.empty:
        print(
            volatility_summary.to_string(
                index=False
            )
        )

    print()
    print("=" * 70)
    print("EARNINGS BREADTH REGIME — 5D REACTION")
    print("=" * 70)

    if not breadth_summary.empty:
        print(
            breadth_summary.to_string(
                index=False
            )
        )

    print()
    print("=" * 70)
    print("CORPORATE EARNINGS INTELLIGENCE V5 COMPLETED")
    print("=" * 70)
    print("Research-only: YES")
    print("Decision Engine integration: NO")
    print(
        "Look-ahead protection: "
        "event context uses information available before each event"
    )


if __name__ == "__main__":
    main()
