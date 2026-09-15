# ============================================================
# US500 EMA19 SIGNAL ENGINE
# REVERSE ENGINEERING DIAGNOSTIC V3
# ============================================================
#
# الهدف:
# إعادة بناء الـ historical baseline القديم.
#
# REFERENCE:
#
# Total signals : 119
# Valid setups  : 117
# Invalid SL    : 2
#
# Resolved      : 109
# Wins          : 36
# Losses        : 73
# Ambiguous     : 3
# Open          : 5
#
# Total R       : +71R
# Profit Factor : ~1.973
#
# VALID YEARLY:
#
# 2019 = 1
# 2020 = 16
# 2021 = 26
# 2022 = 5
# 2023 = 15
# 2024 = 17
# 2025 = 19
# 2026 = 18
#
# ============================================================

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf


# ============================================================
# CONFIG
# ============================================================

TICKER = "^GSPC"

START_DATE = "2019-01-01"

EMA_FAST = 19
EMA_TREND = 200

ATR_PERIOD = 14

STOP_LOOKBACK = 5
ATR_MULTIPLIER = 0.5

RR = 4.0


# ============================================================
# REFERENCE
# ============================================================

REF_TOTAL = 119
REF_VALID = 117
REF_INVALID = 2

REF_RESOLVED = 109
REF_WINS = 36
REF_LOSSES = 73
REF_AMBIGUOUS = 3
REF_OPEN = 5

REF_TOTAL_R = 71.0
REF_PF = 1.973

REF_YEARLY = {
    2019: 1,
    2020: 16,
    2021: 26,
    2022: 5,
    2023: 15,
    2024: 17,
    2025: 19,
    2026: 18,
}


# ============================================================
# DOWNLOAD DATA
# ============================================================

def download_market():

    print("=" * 72)
    print("DOWNLOADING MARKET DATA")
    print("=" * 72)

    df = yf.download(
        TICKER,
        start=START_DATE,
        interval="1d",
        auto_adjust=False,
        progress=False,
    )

    if df is None or df.empty:
        raise RuntimeError(
            "No market data returned."
        )

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = (
            df.columns
            .get_level_values(0)
        )

    required = [
        "Open",
        "High",
        "Low",
        "Close",
    ]

    for col in required:

        if col not in df.columns:

            raise RuntimeError(
                f"Missing column: {col}"
            )

    df = df[
        required
    ].copy()

    df.index = pd.to_datetime(
        df.index,
        errors="coerce"
    )

    try:
        df.index = (
            df.index
            .tz_localize(None)
        )
    except Exception:
        pass

    df = df[
        ~df.index.isna()
    ]

    df = df.sort_index()

    df = df[
        ~df.index.duplicated(
            keep="last"
        )
    ]

    df = df.reset_index()

    df = df.rename(
        columns={
            "Date": "date"
        }
    )

    for col in required:

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = df.dropna(
        subset=required
    ).reset_index(
        drop=True
    )

    print(
        f"Market data : "
        f"{df['date'].min().date()} "
        f"-> "
        f"{df['date'].max().date()}"
    )

    print(
        f"Rows        : {len(df)}"
    )

    return df


# ============================================================
# TRUE RANGE
# ============================================================

def true_range(df):

    prev_close = (
        df["Close"].shift(1)
    )

    tr1 = (
        df["High"]
        -
        df["Low"]
    )

    tr2 = (
        df["High"]
        -
        prev_close
    ).abs()

    tr3 = (
        df["Low"]
        -
        prev_close
    ).abs()

    return pd.concat(
        [
            tr1,
            tr2,
            tr3
        ],
        axis=1
    ).max(axis=1)


# ============================================================
# ATR METHODS
# ============================================================

def calculate_atr(
    df,
    method
):

    tr = true_range(df)

    if method == "WILDER":

        return (
            tr
            .ewm(
                alpha=1 / ATR_PERIOD,
                adjust=False,
                min_periods=ATR_PERIOD
            )
            .mean()
        )

    if method == "SMA":

        return (
            tr
            .rolling(
                ATR_PERIOD,
                min_periods=ATR_PERIOD
            )
            .mean()
        )

    if method == "SPAN":

        return (
            tr
            .ewm(
                span=ATR_PERIOD,
                adjust=False,
                min_periods=ATR_PERIOD
            )
            .mean()
        )

    if method == "WILDER_ADJUST":

        return (
            tr
            .ewm(
                alpha=1 / ATR_PERIOD,
                adjust=True,
                min_periods=ATR_PERIOD
            )
            .mean()
        )

    raise ValueError(
        f"Unknown ATR method: {method}"
    )


# ============================================================
# PREPARE INDICATORS
# ============================================================

def prepare_market(
    df,
    atr_method
):

    out = df.copy()

    out["EMA19"] = (
        out["Close"]
        .ewm(
            span=EMA_FAST,
            adjust=False
        )
        .mean()
    )

    out["EMA200"] = (
        out["Close"]
        .ewm(
            span=EMA_TREND,
            adjust=False
        )
        .mean()
    )

    out["ATR14"] = calculate_atr(
        out,
        atr_method
    )

    # Previous-day values
    out["PrevClose"] = (
        out["Close"].shift(1)
    )

    out["PrevEMA19"] = (
        out["EMA19"].shift(1)
    )

    out["PrevEMA200"] = (
        out["EMA200"].shift(1)
    )

    # EMA19 slope
    out["EMA19_Slope"] = (
        out["EMA19"]
        -
        out["EMA19"].shift(1)
    )

    # Distance from EMA19
    out["Distance_EMA19"] = (
        (
            out["Close"]
            -
            out["EMA19"]
        )
        /
        out["EMA19"]
        *
        100
    )

    # Candle direction
    out["Bullish"] = (
        out["Close"]
        >
        out["Open"]
    )

    return out


# ============================================================
# BASE TREND FILTER
# ============================================================

def trend_filter(
    row
):

    return (
        row["Close"] > row["EMA200"]
        and
        row["EMA19"] > row["EMA200"]
    )


# ============================================================
# RAW SIGNAL CONDITIONS
# ============================================================

def condition_touch(
    row
):

    return (
        trend_filter(row)
        and
        row["Low"] <= row["EMA19"]
    )


def condition_touch_close_above(
    row
):

    return (
        trend_filter(row)
        and
        row["Low"] <= row["EMA19"]
        and
        row["Close"] > row["EMA19"]
    )


def condition_open_above_touch(
    row
):

    return (
        trend_filter(row)
        and
        row["Open"] > row["EMA19"]
        and
        row["Low"] <= row["EMA19"]
    )


def condition_bullish_touch(
    row
):

    return (
        trend_filter(row)
        and
        row["Low"] <= row["EMA19"]
        and
        row["Close"] > row["Open"]
    )


def condition_previous_close_above(
    row
):

    return (
        trend_filter(row)
        and
        row["Low"] <= row["EMA19"]
        and
        row["PrevClose"] > row["PrevEMA19"]
    )


def condition_previous_close_above_current_close(
    row
):

    return (
        trend_filter(row)
        and
        row["Low"] <= row["EMA19"]
        and
        row["PrevClose"] > row["PrevEMA19"]
        and
        row["Close"] > row["EMA19"]
    )


def condition_slope_positive(
    row
):

    return (
        trend_filter(row)
        and
        row["Low"] <= row["EMA19"]
        and
        row["EMA19_Slope"] > 0
    )


def condition_touch_and_slope_positive_close(
    row
):

    return (
        trend_filter(row)
        and
        row["Low"] <= row["EMA19"]
        and
        row["EMA19_Slope"] > 0
        and
        row["Close"] > row["EMA19"]
    )


# ============================================================
# CONDITION MAP
# ============================================================

CONDITIONS = {

    "TOUCH":
        condition_touch,

    "TOUCH_CLOSE_ABOVE":
        condition_touch_close_above,

    "OPEN_ABOVE_TOUCH":
        condition_open_above_touch,

    "BULLISH_TOUCH":
        condition_bullish_touch,

    "PREVIOUS_CLOSE_ABOVE":
        condition_previous_close_above,

    "PREVIOUS_CLOSE_ABOVE_CURRENT_CLOSE":
        condition_previous_close_above_current_close,

    "SLOPE_POSITIVE":
        condition_slope_positive,

    "SLOPE_POSITIVE_CLOSE_ABOVE":
        condition_touch_and_slope_positive_close,

}


# ============================================================
# RAW CANDIDATE GENERATION
# ============================================================

def generate_raw_candidates(
    df,
    condition_function
):

    candidates = []

    start = max(
        EMA_TREND,
        ATR_PERIOD,
        STOP_LOOKBACK
    ) + 1

    for i in range(
        start,
        len(df)
    ):

        row = df.iloc[i]

        if not np.isfinite(
            row["EMA19"]
        ):
            continue

        if not np.isfinite(
            row["EMA200"]
        ):
            continue

        if not np.isfinite(
            row["ATR14"]
        ):
            continue

        try:

            valid_condition = (
                condition_function(row)
            )

        except Exception:

            valid_condition = False

        if not valid_condition:

            continue

        candidates.append(i)

    return candidates


# ============================================================
# STOP
# ============================================================

def build_signal(
    df,
    i
):

    row = df.iloc[i]

    entry = float(
        row["Close"]
    )

    previous_5 = df.iloc[
        i - STOP_LOOKBACK:i
    ]

    previous_low = float(
        previous_5["Low"].min()
    )

    previous_atr = float(
        df.iloc[i - 1]["ATR14"]
    )

    if not np.isfinite(
        previous_atr
    ):

        return {

            "index": i,

            "date": row["date"],

            "entry": entry,

            "stop": np.nan,

            "risk": np.nan,

            "target": np.nan,

            "valid_sl": False,

        }

    stop = (
        previous_low
        -
        ATR_MULTIPLIER
        *
        previous_atr
    )

    valid_sl = (
        np.isfinite(stop)
        and
        stop < entry
    )

    if valid_sl:

        risk = (
            entry
            -
            stop
        )

        target = (
            entry
            +
            RR * risk
        )

    else:

        risk = np.nan

        target = np.nan

    return {

        "index": i,

        "date": row["date"],

        "entry": entry,

        "stop": stop,

        "risk": risk,

        "target": target,

        "valid_sl": valid_sl,

    }


# ============================================================
# SPACING MODE 1
# EVERY SIGNAL
# ============================================================

def spacing_all(
    indices
):

    return list(indices)


# ============================================================
# SPACING MODE 2
# MINIMUM ROW GAP
# ============================================================

def spacing_row_gap(
    indices,
    gap
):

    if not indices:

        return []

    selected = []

    last = None

    for i in indices:

        if last is None:

            selected.append(i)

            last = i

            continue

        if (
            i - last
            >
            gap
        ):

            selected.append(i)

            last = i

    return selected


# ============================================================
# SPACING MODE 3
# FIRST SIGNAL IN TOUCH EPISODE
# ============================================================

def spacing_first_episode(
    df,
    indices
):

    index_set = set(
        indices
    )

    selected = []

    for i in indices:

        previous = i - 1

        if previous not in index_set:

            selected.append(i)

    return selected


# ============================================================
# SPACING MODE 4
# LAST SIGNAL IN EPISODE
# ============================================================

def spacing_last_episode(
    df,
    indices
):

    index_set = set(
        indices
    )

    selected = []

    for i in indices:

        next_i = i + 1

        if next_i not in index_set:

            selected.append(i)

    return selected


# ============================================================
# SPACING MODE 5
# RESET AFTER CLOSE ABOVE EMA19
# ============================================================

def spacing_reset_close_above(
    df,
    indices
):

    selected = []

    armed = True

    index_set = set(
        indices
    )

    for i in range(
        len(df)
    ):

        row = df.iloc[i]

        # Re-arm only when a candle closes above EMA19
        if (
            np.isfinite(row["EMA19"])
            and
            row["Close"] > row["EMA19"]
        ):

            armed = True

        if i not in index_set:

            continue

        if not armed:

            continue

        selected.append(i)

        armed = False

    return selected


# ============================================================
# SPACING MODE 6
# RESET AFTER LOW ABOVE EMA19
# ============================================================

def spacing_reset_low_above(
    df,
    indices
):

    selected = []

    armed = True

    index_set = set(
        indices
    )

    for i in range(
        len(df)
    ):

        row = df.iloc[i]

        if (
            np.isfinite(row["EMA19"])
            and
            row["Low"] > row["EMA19"]
        ):

            armed = True

        if i not in index_set:

            continue

        if not armed:

            continue

        selected.append(i)

        armed = False

    return selected


# ============================================================
# SPACING MODE 7
# RESET AFTER TWO CLOSES ABOVE EMA19
# ============================================================

def spacing_reset_two_closes(
    df,
    indices
):

    selected = []

    armed = True

    index_set = set(
        indices
    )

    for i in range(
        len(df)
    ):

        if i >= 2:

            r1 = df.iloc[i - 1]

            r2 = df.iloc[i - 2]

            if (
                r1["Close"] > r1["EMA19"]
                and
                r2["Close"] > r2["EMA19"]
            ):

                armed = True

        if i not in index_set:

            continue

        if not armed:

            continue

        selected.append(i)

        armed = False

    return selected


# ============================================================
# POSITION MODE 1
# OVERLAPPING TRADES
# ============================================================

def position_overlap(
    df,
    indices
):

    return list(indices)


# ============================================================
# POSITION MODE 2
# ONE TRADE AT A TIME
# ============================================================

def position_one_at_time(
    df,
    indices
):

    if not indices:

        return []

    selected = []

    cursor = 0

    while cursor < len(indices):

        signal_index = indices[
            cursor
        ]

        selected.append(
            signal_index
        )

        signal = build_signal(
            df,
            signal_index
        )

        # Invalid SL:
        # old engines treated it as an event
        # and move to next candidate.
        if not signal["valid_sl"]:

            cursor += 1

            continue

        stop = signal["stop"]

        target = signal["target"]

        exit_index = None

        for j in range(
            signal_index + 1,
            len(df)
        ):

            row = df.iloc[j]

            hit_tp = (
                row["High"]
                >= target
            )

            hit_sl = (
                row["Low"]
                <= stop
            )

            if hit_tp or hit_sl:

                exit_index = j

                break

        if exit_index is None:

            break

        # Find first candidate AFTER exit candle
        cursor += 1

        while (
            cursor < len(indices)
            and
            indices[cursor]
            <= exit_index
        ):

            cursor += 1

    return selected


# ============================================================
# POSITION MODE 3
# ONE TRADE AT A TIME
# ALLOW SIGNAL ON EXIT CANDLE
# ============================================================

def position_one_trade_exit_day(
    df,
    indices
):

    if not indices:

        return []

    selected = []

    cursor = 0

    while cursor < len(indices):

        signal_index = indices[
            cursor
        ]

        selected.append(
            signal_index
        )

        signal = build_signal(
            df,
            signal_index
        )

        if not signal["valid_sl"]:

            cursor += 1

            continue

        stop = signal["stop"]

        target = signal["target"]

        exit_index = None

        for j in range(
            signal_index + 1,
            len(df)
        ):

            row = df.iloc[j]

            hit_tp = (
                row["High"]
                >= target
            )

            hit_sl = (
                row["Low"]
                <= stop
            )

            if hit_tp or hit_sl:

                exit_index = j

                break

        if exit_index is None:

            break

        cursor += 1

        while (
            cursor < len(indices)
            and
            indices[cursor]
            <
            exit_index
        ):

            cursor += 1

    return selected


# ============================================================
# RESOLVE TRADE
# ============================================================

def resolve_trade(
    df,
    signal
):

    if not signal[
        "valid_sl"
    ]:

        return (
            "INVALID_SL",
            np.nan,
            pd.NaT
        )

    entry_index = signal[
        "index"
    ]

    stop = signal[
        "stop"
    ]

    target = signal[
        "target"
    ]

    for j in range(
        entry_index + 1,
        len(df)
    ):

        row = df.iloc[j]

        hit_tp = (
            row["High"]
            >= target
        )

        hit_sl = (
            row["Low"]
            <= stop
        )

        if hit_tp and hit_sl:

            return (
                "AMBIGUOUS",
                np.nan,
                row["date"]
            )

        if hit_tp:

            return (
                "WIN",
                RR,
                row["date"]
            )

        if hit_sl:

            return (
                "LOSS",
                -1.0,
                row["date"]
            )

    return (
        "OPEN",
        np.nan,
        pd.NaT
    )


# ============================================================
# EVALUATE ENGINE
# ============================================================

def evaluate_engine(
    df,
    indices
):

    rows = []

    for i in indices:

        signal = build_signal(
            df,
            i
        )

        result, R, exit_date = (
            resolve_trade(
                df,
                signal
            )
        )

        rows.append({

            **signal,

            "result":
                result,

            "R":
                R,

            "exit_date":
                exit_date,

        })

    return pd.DataFrame(
        rows
    )


# ============================================================
# STATISTICS
# ============================================================

def calculate_stats(
    trades
):

    if trades.empty:

        return {

            "total_signals": 0,

            "valid_setups": 0,

            "invalid_sl": 0,

            "resolved": 0,

            "wins": 0,

            "losses": 0,

            "ambiguous": 0,

            "open": 0,

            "total_R": 0.0,

            "avg_R": np.nan,

            "profit_factor": np.nan,

        }

    total = len(trades)

    invalid = int(
        (
            trades["result"]
            ==
            "INVALID_SL"
        ).sum()
    )

    valid = (
        total
        -
        invalid
    )

    wins = int(
        (
            trades["result"]
            ==
            "WIN"
        ).sum()
    )

    losses = int(
        (
            trades["result"]
            ==
            "LOSS"
        ).sum()
    )

    ambiguous = int(
        (
            trades["result"]
            ==
            "AMBIGUOUS"
        ).sum()
    )

    open_trades = int(
        (
            trades["result"]
            ==
            "OPEN"
        ).sum()
    )

    resolved = (
        wins
        +
        losses
    )

    valid_R = trades[
        trades["R"].notna()
    ]["R"]

    total_R = (
        float(valid_R.sum())
        if not valid_R.empty
        else 0.0
    )

    avg_R = (
        float(valid_R.mean())
        if not valid_R.empty
        else np.nan
    )

    gross_profit = (
        trades.loc[
            trades["R"] > 0,
            "R"
        ].sum()
    )

    gross_loss = abs(
        trades.loc[
            trades["R"] < 0,
            "R"
        ].sum()
    )

    if gross_loss > 0:

        pf = (
            float(gross_profit)
            /
            float(gross_loss)
        )

    else:

        pf = np.nan

    return {

        "total_signals":
            total,

        "valid_setups":
            valid,

        "invalid_sl":
            invalid,

        "resolved":
            resolved,

        "wins":
            wins,

        "losses":
            losses,

        "ambiguous":
            ambiguous,

        "open":
            open_trades,

        "total_R":
            total_R,

        "avg_R":
            avg_R,

        "profit_factor":
            pf,

    }


# ============================================================
# YEARLY VALID SETUPS
# ============================================================

def yearly_valid(
    trades
):

    if trades.empty:

        return {}

    valid = trades[
        trades["valid_sl"] == True
    ].copy()

    if valid.empty:

        return {}

    valid["year"] = (
        pd.to_datetime(
            valid["date"]
        ).dt.year
    )

    result = (
        valid["year"]
        .value_counts()
        .sort_index()
        .to_dict()
    )

    return {
        int(k): int(v)
        for k, v in result.items()
    }


# ============================================================
# YEARLY MATCH SCORE
# ============================================================

def yearly_match_count(
    trades
):

    actual = yearly_valid(
        trades
    )

    matches = 0

    abs_diff = 0

    for year, expected in (
        REF_YEARLY.items()
    ):

        value = actual.get(
            year,
            0
        )

        if value == expected:

            matches += 1

        abs_diff += abs(
            value
            -
            expected
        )

    return (
        matches,
        abs_diff
    )


# ============================================================
# DISTANCE SCORE
# ============================================================

def score_result(
    stats,
    yearly_matches,
    yearly_abs_diff
):

    score = 0.0

    # --------------------------------------------------------
    # Strongest priority:
    # yearly valid distribution
    # --------------------------------------------------------

    score += (
        yearly_matches
        *
        1000
    )

    score -= (
        yearly_abs_diff
        *
        50
    )

    # --------------------------------------------------------
    # Total signals
    # --------------------------------------------------------

    score -= (
        abs(
            stats["total_signals"]
            -
            REF_TOTAL
        )
        *
        10
    )

    # --------------------------------------------------------
    # Valid setups
    # --------------------------------------------------------

    score -= (
        abs(
            stats["valid_setups"]
            -
            REF_VALID
        )
        *
        20
    )

    # --------------------------------------------------------
    # Invalid SL
    # --------------------------------------------------------

    score -= (
        abs(
            stats["invalid_sl"]
            -
            REF_INVALID
        )
        *
        50
    )

    # --------------------------------------------------------
    # Trade results
    # --------------------------------------------------------

    score -= (
        abs(
            stats["wins"]
            -
            REF_WINS
        )
        *
        10
    )

    score -= (
        abs(
            stats["losses"]
            -
            REF_LOSSES
        )
        *
        5
    )

    score -= (
        abs(
            stats["ambiguous"]
            -
            REF_AMBIGUOUS
        )
        *
        10
    )

    score -= (
        abs(
            stats["open"]
            -
            REF_OPEN
        )
        *
        10
    )

    # --------------------------------------------------------
    # Total R
    # --------------------------------------------------------

    if np.isfinite(
        stats["total_R"]
    ):

        score -= (
            abs(
                stats["total_R"]
                -
                REF_TOTAL_R
            )
            *
            2
        )

    # --------------------------------------------------------
    # Profit Factor
    # --------------------------------------------------------

    if np.isfinite(
        stats["profit_factor"]
    ):

        score -= (
            abs(
                stats["profit_factor"]
                -
                REF_PF
            )
            *
            20
        )

    return score


# ============================================================
# MAIN DIAGNOSTIC
# ============================================================

def main():

    print()
    print("=" * 72)
    print("US500 EMA19 REVERSE ENGINEERING DIAGNOSTIC V3")
    print("=" * 72)

    print()
    print("REFERENCE")
    print("-" * 72)

    print(
        f"Total signals : {REF_TOTAL}"
    )

    print(
        f"Valid setups  : {REF_VALID}"
    )

    print(
        f"Invalid SL    : {REF_INVALID}"
    )

    print(
        f"Resolved      : {REF_RESOLVED}"
    )

    print(
        f"Wins          : {REF_WINS}"
    )

    print(
        f"Losses        : {REF_LOSSES}"
    )

    print(
        f"Ambiguous     : {REF_AMBIGUOUS}"
    )

    print(
        f"Open          : {REF_OPEN}"
    )

    print(
        f"Total R       : {REF_TOTAL_R}"
    )

    print(
        f"Profit Factor : {REF_PF}"
    )

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    raw = download_market()

    # --------------------------------------------------------
    # ALL CONFIGURATIONS
    # --------------------------------------------------------

    atr_methods = [
        "WILDER",
        "SMA",
        "SPAN",
        "WILDER_ADJUST",
    ]

    spacing_modes = {

        "ALL":
            lambda df, idx:
                spacing_all(idx),

        "ROW_GAP_1":
            lambda df, idx:
                spacing_row_gap(
                    idx,
                    1
                ),

        "ROW_GAP_2":
            lambda df, idx:
                spacing_row_gap(
                    idx,
                    2
                ),

        "ROW_GAP_3":
            lambda df, idx:
                spacing_row_gap(
                    idx,
                    3
                ),

        "ROW_GAP_4":
            lambda df, idx:
                spacing_row_gap(
                    idx,
                    4
                ),

        "ROW_GAP_5":
            lambda df, idx:
                spacing_row_gap(
                    idx,
                    5
                ),

        "ROW_GAP_6":
            lambda df, idx:
                spacing_row_gap(
                    idx,
                    6
                ),

        "ROW_GAP_7":
            lambda df, idx:
                spacing_row_gap(
                    idx,
                    7
                ),

        "ROW_GAP_8":
            lambda df, idx:
                spacing_row_gap(
                    idx,
                    8
                ),

        "FIRST_EPISODE":
            lambda df, idx:
                spacing_first_episode(
                    df,
                    idx
                ),

        "LAST_EPISODE":
            lambda df, idx:
                spacing_last_episode(
                    df,
                    idx
                ),

        "RESET_CLOSE_ABOVE":
            lambda df, idx:
                spacing_reset_close_above(
                    df,
                    idx
                ),

        "RESET_LOW_ABOVE":
            lambda df, idx:
                spacing_reset_low_above(
                    df,
                    idx
                ),

        "RESET_TWO_CLOSES":
            lambda df, idx:
                spacing_reset_two_closes(
                    df,
                    idx
                ),

    }

    position_modes = {

        "OVERLAP":
            position_overlap,

        "ONE_TRADE":
            position_one_at_time,

        "ONE_TRADE_EXIT_DAY":
            position_one_trade_exit_day,

    }

    # --------------------------------------------------------
    # RESULTS
    # --------------------------------------------------------

    summary_rows = []

    yearly_rows = []

    signal_rows = []

    configuration_number = 0

    # --------------------------------------------------------
    # LOOP
    # --------------------------------------------------------

    for atr_method in atr_methods:

        print()
        print(
            "=" * 72
        )

        print(
            f"ATR METHOD: {atr_method}"
        )

        print(
            "=" * 72
        )

        df = prepare_market(
            raw,
            atr_method
        )

        for condition_name, condition_function in (
            CONDITIONS.items()
        ):

            raw_indices = (
                generate_raw_candidates(
                    df,
                    condition_function
                )
            )

            if not raw_indices:

                continue

            for spacing_name, spacing_function in (
                spacing_modes.items()
            ):

                spaced_indices = (
                    spacing_function(
                        df,
                        raw_indices
                    )
                )

                if not spaced_indices:

                    continue

                for position_name, position_function in (
                    position_modes.items()
                ):

                    final_indices = (
                        position_function(
                            df,
                            spaced_indices
                        )
                    )

                    if not final_indices:

                        continue

                    trades = evaluate_engine(
                        df,
                        final_indices
                    )

                    stats = calculate_stats(
                        trades
                    )

                    (
                        yearly_matches,
                        yearly_abs_diff
                    ) = yearly_match_count(
                        trades
                    )

                    score = score_result(
                        stats,
                        yearly_matches,
                        yearly_abs_diff
                    )

                    configuration_number += 1

                    engine_name = (
                        f"{condition_name}"
                        f"__"
                        f"{spacing_name}"
                        f"__"
                        f"{position_name}"
                        f"__"
                        f"{atr_method}"
                    )

                    summary_rows.append({

                        "rank":
                            np.nan,

                        "engine":
                            engine_name,

                        "condition":
                            condition_name,

                        "spacing":
                            spacing_name,

                        "position":
                            position_name,

                        "atr":
                            atr_method,

                        "raw_candidates":
                            len(raw_indices),

                        "final_signals":
                            len(final_indices),

                        "total_signals":
                            stats[
                                "total_signals"
                            ],

                        "valid_setups":
                            stats[
                                "valid_setups"
                            ],

                        "invalid_sl":
                            stats[
                                "invalid_sl"
                            ],

                        "resolved":
                            stats[
                                "resolved"
                            ],

                        "wins":
                            stats[
                                "wins"
                            ],

                        "losses":
                            stats[
                                "losses"
                            ],

                        "ambiguous":
                            stats[
                                "ambiguous"
                            ],

                        "open":
                            stats[
                                "open"
                            ],

                        "total_R":
                            stats[
                                "total_R"
                            ],

                        "avg_R":
                            stats[
                                "avg_R"
                            ],

                        "profit_factor":
                            stats[
                                "profit_factor"
                            ],

                        "yearly_matches":
                            yearly_matches,

                        "yearly_abs_diff":
                            yearly_abs_diff,

                        "score":
                            score,

                    })

                    # ----------------------------------------
                    # YEARLY
                    # ----------------------------------------

                    actual_yearly = (
                        yearly_valid(
                            trades
                        )
                    )

                    for year in (
                        sorted(
                            REF_YEARLY.keys()
                        )
                    ):

                        reference = (
                            REF_YEARLY[
                                year
                            ]
                        )

                        actual = (
                            actual_yearly.get(
                                year,
                                0
                            )
                        )

                        yearly_rows.append({

                            "engine":
                                engine_name,

                            "year":
                                year,

                            "reference":
                                reference,

                            "actual":
                                actual,

                            "difference":
                                actual
                                -
                                reference,

                            "match":
                                actual
                                ==
                                reference,

                        })

                    # ----------------------------------------
                    # SIGNAL DETAILS
                    # ----------------------------------------

                    for _, trade in (
                        trades.iterrows()
                    ):

                        signal_rows.append({

                            "engine":
                                engine_name,

                            "atr":
                                atr_method,

                            "condition":
                                condition_name,

                            "spacing":
                                spacing_name,

                            "position":
                                position_name,

                            "date":
                                trade[
                                    "date"
                                ],

                            "entry":
                                trade[
                                    "entry"
                                ],

                            "stop":
                                trade[
                                    "stop"
                                ],

                            "risk":
                                trade[
                                    "risk"
                                ],

                            "target":
                                trade[
                                    "target"
                                ],

                            "valid_sl":
                                trade[
                                    "valid_sl"
                                ],

                            "result":
                                trade[
                                    "result"
                                ],

                            "R":
                                trade[
                                    "R"
                                ],

                            "exit_date":
                                trade[
                                    "exit_date"
                                ],

                        })

    # --------------------------------------------------------
    # DATAFRAME
    # --------------------------------------------------------

    summary = pd.DataFrame(
        summary_rows
    )

    yearly = pd.DataFrame(
        yearly_rows
    )

    signals = pd.DataFrame(
        signal_rows
    )

    if summary.empty:

        raise RuntimeError(
            "No diagnostic configurations produced results."
        )

    # --------------------------------------------------------
    # RANK
    # --------------------------------------------------------

    summary = summary.sort_values(
        by=[
            "yearly_matches",
            "yearly_abs_diff",
            "score",
        ],
        ascending=[
            False,
            True,
            False,
        ]
    ).reset_index(
        drop=True
    )

    summary[
        "rank"
    ] = (
        summary.index + 1
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    summary.to_csv(
        "signal_diagnostics_v3_summary.csv",
        index=False
    )

    yearly.to_csv(
        "signal_diagnostics_v3_yearly.csv",
        index=False
    )

    signals.to_csv(
        "signal_diagnostics_v3_signals.csv",
        index=False
    )

    # --------------------------------------------------------
    # PRINT TOP 20
    # --------------------------------------------------------

    print()
    print()
    print("=" * 72)
    print("TOP 20 V3 CONFIGURATIONS")
    print("=" * 72)

    display_columns = [

        "rank",

        "engine",

        "total_signals",

        "valid_setups",

        "invalid_sl",

        "resolved",

        "wins",

        "losses",

        "ambiguous",

        "open",

        "total_R",

        "profit_factor",

        "yearly_matches",

        "yearly_abs_diff",

        "score",

    ]

    print(
        summary[
            display_columns
        ]
        .head(20)
        .to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # EXACT / NEAR MATCH
    # --------------------------------------------------------

    print()
    print(
        "=" * 72
    )

    print(
        "REFERENCE MATCH ANALYSIS"
    )

    print(
        "=" * 72
    )

    exact_core = summary[
        (
            summary["total_signals"]
            ==
            REF_TOTAL
        )
        &
        (
            summary["valid_setups"]
            ==
            REF_VALID
        )
        &
        (
            summary["invalid_sl"]
            ==
            REF_INVALID
        )
    ]

    if exact_core.empty:

        print(
            "No configuration has exact "
            "119 / 117 / 2 yet."
        )

    else:

        print()
        print(
            "CONFIGURATIONS WITH "
            "EXACT 119 / 117 / 2:"
        )

        print(
            exact_core[
                display_columns
            ].head(20).to_string(
                index=False
            )
        )

    # --------------------------------------------------------
    # BEST YEARLY MATCH
    # --------------------------------------------------------

    best_yearly = summary[
        summary[
            "yearly_matches"
        ]
        ==
        summary[
            "yearly_matches"
        ].max()
    ]

    print()
    print(
        "=" * 72
    )

    print(
        "BEST YEARLY MATCH"
    )

    print(
        "=" * 72
    )

    print(
        best_yearly[
            display_columns
        ].head(10).to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # FILES
    # --------------------------------------------------------

    print()
    print(
        "=" * 72
    )

    print(
        "FILES CREATED"
    )

    print(
        "=" * 72
    )

    print(
        "signal_diagnostics_v3_summary.csv"
    )

    print(
        "signal_diagnostics_v3_yearly.csv"
    )

    print(
        "signal_diagnostics_v3_signals.csv"
    )

    print()
    print(
        "=" * 72
    )

    print(
        "DIAGNOSTIC V3 COMPLETE"
    )

    print(
        "=" * 72
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()# ============================================================
# US500 / S&P 500
# EMA19 SIGNAL ENGINE DIAGNOSTIC V2
#
# الهدف:
# إعادة بناء الـ historical baseline القديم:
#
# TOTAL SIGNALS = 119
# VALID SETUPS  = 117
# INVALID SL    = 2
#
# VALID SETUPS BY YEAR:
# 2019 = 1
# 2020 = 16
# 2021 = 26
# 2022 = 5
# 2023 = 15
# 2024 = 17
# 2025 = 19
# 2026 = 18
#
# V2 لا يغير شروط الـ EMA19 الأساسية.
# الذي يتم اختباره هو Signal Spacing / Duplicate Handling.
#
# ============================================================

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf


# ============================================================
# CONFIG
# ============================================================

TICKER = "^GSPC"

START_DATE = "2019-01-01"

EMA_FAST = 19
EMA_TREND = 200

ATR_PERIOD = 14

STOP_LOOKBACK = 5
ATR_MULTIPLIER = 0.5

RR = 4.0


# ============================================================
# HISTORICAL REFERENCE
# ============================================================

REFERENCE_TOTAL_SIGNALS = 119

REFERENCE_VALID = 117

REFERENCE_INVALID = 2

REFERENCE_YEARLY_VALID = {
    2019: 1,
    2020: 16,
    2021: 26,
    2022: 5,
    2023: 15,
    2024: 17,
    2025: 19,
    2026: 18,
}


# ============================================================
# DOWNLOAD
# ============================================================

def download_market():

    print("=" * 72)
    print("DOWNLOADING MARKET DATA")
    print("=" * 72)

    df = yf.download(
        TICKER,
        start=START_DATE,
        interval="1d",
        auto_adjust=False,
        progress=False,
    )

    if df is None or df.empty:
        raise RuntimeError(
            "No market data returned."
        )

    # Handle yfinance MultiIndex
    if isinstance(
        df.columns,
        pd.MultiIndex
    ):
        df.columns = (
            df.columns
            .get_level_values(0)
        )

    required = [
        "Open",
        "High",
        "Low",
        "Close",
    ]

    missing = [
        c for c in required
        if c not in df.columns
    ]

    if missing:
        raise RuntimeError(
            f"Missing columns: {missing}"
        )

    df = df[
        required
    ].copy()

    df.index = pd.to_datetime(
        df.index,
        errors="coerce"
    )

    df = df[
        ~df.index.isna()
    ]

    try:
        df.index = (
            df.index
            .tz_localize(None)
        )
    except Exception:
        pass

    df = df.sort_index()

    df = df[
        ~df.index.duplicated(
            keep="last"
        )
    ]

    df = df.reset_index()

    df = df.rename(
        columns={
            "Date": "date"
        }
    )

    for col in required:

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = df.dropna(
        subset=required
    ).reset_index(
        drop=True
    )

    print(
        f"Market data : "
        f"{df['date'].min().date()} "
        f"-> "
        f"{df['date'].max().date()}"
    )

    print(
        f"Rows        : {len(df)}"
    )

    return df


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    df,
    period=14
):

    previous_close = (
        df["Close"].shift(1)
    )

    tr1 = (
        df["High"]
        -
        df["Low"]
    )

    tr2 = (
        df["High"]
        -
        previous_close
    ).abs()

    tr3 = (
        df["Low"]
        -
        previous_close
    ).abs()

    true_range = pd.concat(
        [
            tr1,
            tr2,
            tr3
        ],
        axis=1
    ).max(axis=1)

    atr = (
        true_range
        .ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period
        )
        .mean()
    )

    return atr


# ============================================================
# INDICATORS
# ============================================================

def prepare_market(df):

    df = df.copy()

    df["EMA19"] = (
        df["Close"]
        .ewm(
            span=EMA_FAST,
            adjust=False
        )
        .mean()
    )

    df["EMA200"] = (
        df["Close"]
        .ewm(
            span=EMA_TREND,
            adjust=False
        )
        .mean()
    )

    df["ATR14"] = calculate_atr(
        df,
        ATR_PERIOD
    )

    return df


# ============================================================
# BASELINE CONDITION
# ============================================================

def baseline_condition(
    row
):

    return (
        row["Close"] > row["EMA200"]
        and
        row["EMA19"] > row["EMA200"]
        and
        row["Low"] <= row["EMA19"]
    )


# ============================================================
# STOP
# ============================================================

def calculate_stop(
    df,
    index
):

    if index < STOP_LOOKBACK:

        return np.nan

    previous = df.iloc[
        index - STOP_LOOKBACK:index
    ]

    previous_low = float(
        previous["Low"].min()
    )

    previous_atr = float(
        df.iloc[index - 1]["ATR14"]
    )

    if not np.isfinite(
        previous_atr
    ):

        return np.nan

    stop = (
        previous_low
        -
        ATR_MULTIPLIER
        *
        previous_atr
    )

    return stop


# ============================================================
# BUILD ALL RAW QUALIFYING SIGNALS
# ============================================================

def build_raw_candidates(
    df
):

    candidates = []

    start_index = (
        max(
            EMA_TREND,
            ATR_PERIOD,
            STOP_LOOKBACK
        )
        +
        1
    )

    for i in range(
        start_index,
        len(df)
    ):

        row = df.iloc[i]

        if not np.isfinite(
            row["EMA19"]
        ):
            continue

        if not np.isfinite(
            row["EMA200"]
        ):
            continue

        if not np.isfinite(
            row["ATR14"]
        ):
            continue

        if not baseline_condition(
            row
        ):
            continue

        stop = calculate_stop(
            df,
            i
        )

        entry = float(
            row["Close"]
        )

        valid_sl = (
            np.isfinite(stop)
            and
            stop < entry
        )

        if valid_sl:

            risk = (
                entry
                -
                stop
            )

            target = (
                entry
                +
                RR * risk
            )

        else:

            risk = np.nan
            target = np.nan

        candidates.append({

            "index": i,

            "date": row["date"],

            "entry": entry,

            "stop": stop,

            "risk": risk,

            "target": target,

            "valid_sl": valid_sl,

        })

    return candidates


# ============================================================
# SIGNAL SPACING
# ============================================================

def apply_row_spacing(
    candidates,
    minimum_gap
):
    """
    Keep a signal only if it is at least
    minimum_gap trading rows after the
    previously selected signal.

    Examples:

    gap = 0
        every candidate

    gap = 1
        do not allow adjacent signal candles

    gap = 5
        selected signals must be >5
        trading rows apart
    """

    if not candidates:
        return []

    selected = []

    last_index = None

    for candidate in candidates:

        current = candidate[
            "index"
        ]

        if last_index is None:

            selected.append(
                candidate
            )

            last_index = current

            continue

        distance = (
            current
            -
            last_index
        )

        if distance > minimum_gap:

            selected.append(
                candidate
            )

            last_index = current

    return selected


# ============================================================
# SIGNAL SPACING USING CALENDAR DAYS
# ============================================================

def apply_calendar_spacing(
    candidates,
    minimum_days
):

    if not candidates:
        return []

    selected = []

    last_date = None

    for candidate in candidates:

        current_date = (
            candidate["date"]
        )

        if last_date is None:

            selected.append(
                candidate
            )

            last_date = current_date

            continue

        days = (
            current_date
            -
            last_date
        ).days

        if days > minimum_days:

            selected.append(
                candidate
            )

            last_date = current_date

    return selected


# ============================================================
# FIRST SIGNAL AFTER RESET
# ============================================================

def apply_reset_logic(
    df,
    candidates,
    reset_days
):
    """
    A candidate becomes eligible only if
    price has spent at least reset_days
    trading candles WITHOUT touching EMA19.

    This is not assumed to be the original.
    It is tested as a diagnostic hypothesis.
    """

    selected = []

    last_touch_index = None

    candidate_map = {
        c["index"]: c
        for c in candidates
    }

    for i in range(
        len(df)
    ):

        row = df.iloc[i]

        touch = (
            np.isfinite(
                row["EMA19"]
            )
            and
            row["Low"]
            <=
            row["EMA19"]
        )

        if touch:

            last_touch_index = i

        if i not in candidate_map:

            continue

        if last_touch_index is None:

            selected.append(
                candidate_map[i]
            )

            continue

        distance = (
            i
            -
            last_touch_index
        )

        if distance >= reset_days:

            selected.append(
                candidate_map[i]
            )

    return selected


# ============================================================
# PREVIOUS CLOSE ABOVE EMA19
# ============================================================

def apply_previous_close_filter(
    df,
    candidates
):

    selected = []

    for candidate in candidates:

        i = candidate["index"]

        if i < 1:
            continue

        previous = df.iloc[
            i - 1
        ]

        if (
            previous["Close"]
            >
            previous["EMA19"]
        ):

            selected.append(
                candidate
            )

    return selected


# ============================================================
# TRADE RESOLUTION
# ============================================================

def resolve_trade(
    df,
    candidate
):

    if not candidate[
        "valid_sl"
    ]:

        return "INVALID_SL"

    entry_index = candidate[
        "index"
    ]

    stop = candidate[
        "stop"
    ]

    target = candidate[
        "target"
    ]

    for j in range(
        entry_index + 1,
        len(df)
    ):

        future = df.iloc[j]

        hit_tp = (
            future["High"]
            >= target
        )

        hit_sl = (
            future["Low"]
            <= stop
        )

        if hit_tp and hit_sl:

            return "AMBIGUOUS"

        if hit_tp:

            return "WIN"

        if hit_sl:

            return "LOSS"

    return "OPEN"


# ============================================================
# EVALUATE SIGNAL SET
# ============================================================

def evaluate_engine(
    df,
    candidates
):

    records = []

    for candidate in candidates:

        result = resolve_trade(
            df,
            candidate
        )

        record = candidate.copy()

        record[
            "result"
        ] = result

        records.append(
            record
        )

    return pd.DataFrame(
        records
    )


# ============================================================
# STATISTICS
# ============================================================

def calculate_statistics(
    trades
):

    if trades.empty:

        return {

            "total_signals": 0,

            "valid_setups": 0,

            "invalid_sl": 0,

            "wins": 0,

            "losses": 0,

            "ambiguous": 0,

            "open": 0,

        }

    total = len(trades)

    valid = int(
        (
            trades["valid_sl"]
            == True
        ).sum()
    )

    invalid = int(
        (
            trades["result"]
            ==
            "INVALID_SL"
        ).sum()
    )

    wins = int(
        (
            trades["result"]
            ==
            "WIN"
        ).sum()
    )

    losses = int(
        (
            trades["result"]
            ==
            "LOSS"
        ).sum()
    )

    ambiguous = int(
        (
            trades["result"]
            ==
            "AMBIGUOUS"
        ).sum()
    )

    open_trades = int(
        (
            trades["result"]
            ==
            "OPEN"
        ).sum()
    )

    return {

        "total_signals": total,

        "valid_setups": valid,

        "invalid_sl": invalid,

        "wins": wins,

        "losses": losses,

        "ambiguous": ambiguous,

        "open": open_trades,

    }


# ============================================================
# YEARLY VALID SETUPS
# ============================================================

def yearly_valid_counts(
    trades
):

    if trades.empty:

        return {}

    valid = trades[
        trades["valid_sl"] == True
    ].copy()

    if valid.empty:

        return {}

    valid["year"] = (
        pd.to_datetime(
            valid["date"]
        ).dt.year
    )

    counts = (
        valid["year"]
        .value_counts()
        .sort_index()
        .to_dict()
    )

    return {
        int(k): int(v)
        for k, v in counts.items()
    }


# ============================================================
# REFERENCE COMPARISON
# ============================================================

def compare_reference(
    engine_name,
    trades
):

    stats = calculate_statistics(
        trades
    )

    yearly = yearly_valid_counts(
        trades
    )

    total_diff = (
        stats["total_signals"]
        -
        REFERENCE_TOTAL_SIGNALS
    )

    valid_diff = (
        stats["valid_setups"]
        -
        REFERENCE_VALID
    )

    invalid_diff = (
        stats["invalid_sl"]
        -
        REFERENCE_INVALID
    )

    yearly_matches = 0

    for year, expected in (
        REFERENCE_YEARLY_VALID.items()
    ):

        actual = yearly.get(
            year,
            0
        )

        if actual == expected:

            yearly_matches += 1

    exact_yearly = all(

        yearly.get(
            year,
            0
        )
        ==
        expected

        for year, expected
        in REFERENCE_YEARLY_VALID.items()

    )

    exact_total = (
        stats["total_signals"]
        ==
        REFERENCE_TOTAL_SIGNALS
    )

    exact_valid = (
        stats["valid_setups"]
        ==
        REFERENCE_VALID
    )

    exact_invalid = (
        stats["invalid_sl"]
        ==
        REFERENCE_INVALID
    )

    if (
        exact_total
        and
        exact_valid
        and
        exact_invalid
        and
        exact_yearly
    ):

        status = "EXACT MATCH"

    elif (
        exact_valid
        and
        exact_yearly
    ):

        status = (
            "VALID/YEAR MATCH "
            "BUT TOTAL MISMATCH"
        )

    else:

        status = "NO MATCH"

    return {

        "engine": engine_name,

        "total_signals":
            stats["total_signals"],

        "reference_total":
            REFERENCE_TOTAL_SIGNALS,

        "total_difference":
            total_diff,

        "valid_setups":
            stats["valid_setups"],

        "reference_valid":
            REFERENCE_VALID,

        "valid_difference":
            valid_diff,

        "invalid_sl":
            stats["invalid_sl"],

        "reference_invalid":
            REFERENCE_INVALID,

        "invalid_difference":
            invalid_diff,

        "yearly_matches":
            yearly_matches,

        "yearly_total":
            len(
                REFERENCE_YEARLY_VALID
            ),

        "status":
            status,

    }


# ============================================================
# PRINT RESULT
# ============================================================

def print_engine_result(
    engine_name,
    trades
):

    result = compare_reference(
        engine_name,
        trades
    )

    yearly = yearly_valid_counts(
        trades
    )

    print()
    print("-" * 72)
    print(engine_name)
    print("-" * 72)

    print(
        f"Total signals : "
        f"{result['total_signals']}"
    )

    print(
        f"Reference     : "
        f"{result['reference_total']}"
    )

    print(
        f"Difference    : "
        f"{result['total_difference']:+d}"
    )

    print()

    print(
        f"Valid setups  : "
        f"{result['valid_setups']}"
    )

    print(
        f"Reference     : "
        f"{result['reference_valid']}"
    )

    print(
        f"Difference    : "
        f"{result['valid_difference']:+d}"
    )

    print()

    print(
        f"Invalid SL    : "
        f"{result['invalid_sl']}"
    )

    print(
        f"Reference     : "
        f"{result['reference_invalid']}"
    )

    print(
        f"Difference    : "
        f"{result['invalid_difference']:+d}"
    )

    print()

    print(
        f"Year matches  : "
        f"{result['yearly_matches']}/"
        f"{result['yearly_total']}"
    )

    print(
        f"STATUS        : "
        f"{result['status']}"
    )

    print()

    print(
        "YEAR | REF | ACTUAL | DIFF"
    )

    print(
        "-" * 40
    )

    for year in sorted(
        REFERENCE_YEARLY_VALID.keys()
    ):

        reference = (
            REFERENCE_YEARLY_VALID[
                year
            ]
        )

        actual = yearly.get(
            year,
            0
        )

        diff = (
            actual
            -
            reference
        )

        marker = (
            "✓"
            if diff == 0
            else ""
        )

        print(
            f"{year} | "
            f"{reference:3d} | "
            f"{actual:6d} | "
            f"{diff:+4d} {marker}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 72)
    print("US500 EMA19 SIGNAL ENGINE DIAGNOSTIC V2")
    print("=" * 72)

    print()
    print("HISTORICAL REFERENCE")
    print("-" * 72)

    print(
        f"Total signals : "
        f"{REFERENCE_TOTAL_SIGNALS}"
    )

    print(
        f"Valid setups  : "
        f"{REFERENCE_VALID}"
    )

    print(
        f"Invalid SL    : "
        f"{REFERENCE_INVALID}"
    )

    print()

    for year, count in (
        REFERENCE_YEARLY_VALID.items()
    ):

        print(
            f"{year}: {count}"
        )

    # --------------------------------------------------------
    # MARKET
    # --------------------------------------------------------

    df = download_market()

    df = prepare_market(
        df
    )

    print()
    print("=" * 72)
    print("DATA READY")
    print("=" * 72)

    print(
        f"Rows: {len(df)}"
    )

    # --------------------------------------------------------
    # RAW CANDIDATES
    # --------------------------------------------------------

    candidates = (
        build_raw_candidates(
            df
        )
    )

    print()
    print("=" * 72)
    print("RAW BASELINE CANDIDATES")
    print("=" * 72)

    print(
        f"Raw qualifying candles: "
        f"{len(candidates)}"
    )

    # --------------------------------------------------------
    # ENGINES
    # --------------------------------------------------------

    engines = {}

    # --------------------------------------------------------
    # 1. No spacing
    # --------------------------------------------------------

    engines[
        "01_RAW_ALL"
    ] = candidates

    # --------------------------------------------------------
    # 2-12. Trading-row spacing
    # --------------------------------------------------------

    for gap in range(
        1,
        11
    ):

        engines[
            f"ROW_GAP_{gap}"
        ] = apply_row_spacing(
            candidates,
            gap
        )

    # --------------------------------------------------------
    # 13-22. Calendar-day spacing
    # --------------------------------------------------------

    for days in [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        10,
        14,
        20,
    ]:

        engines[
            f"CALENDAR_GAP_{days}"
        ] = apply_calendar_spacing(
            candidates,
            days
        )

    # --------------------------------------------------------
    # 23. Previous close above EMA19
    # --------------------------------------------------------

    engines[
        "PREVIOUS_CLOSE_ABOVE_EMA19"
    ] = apply_previous_close_filter(
        df,
        candidates
    )

    # --------------------------------------------------------
    # 24-28. Reset logic
    # --------------------------------------------------------

    for reset in [
        1,
        2,
        3,
        5,
        10,
    ]:

        engines[
            f"RESET_{reset}"
        ] = apply_reset_logic(
            df,
            candidates,
            reset
        )

    # --------------------------------------------------------
    # EVALUATE
    # --------------------------------------------------------

    summary_rows = []

    yearly_rows = []

    all_signal_rows = []

    for engine_name, engine_candidates in (
        engines.items()
    ):

        trades = evaluate_engine(
            df,
            engine_candidates
        )

        print_engine_result(
            engine_name,
            trades
        )

        comparison = compare_reference(
            engine_name,
            trades
        )

        summary_rows.append(
            comparison
        )

        yearly = yearly_valid_counts(
            trades
        )

        for year in sorted(
            REFERENCE_YEARLY_VALID.keys()
        ):

            yearly_rows.append({

                "engine":
                    engine_name,

                "year":
                    year,

                "reference_valid":
                    REFERENCE_YEARLY_VALID[
                        year
                    ],

                "actual_valid":
                    yearly.get(
                        year,
                        0
                    ),

                "difference":
                    yearly.get(
                        year,
                        0
                    )
                    -
                    REFERENCE_YEARLY_VALID[
                        year
                    ],

                "match":
                    yearly.get(
                        year,
                        0
                    )
                    ==
                    REFERENCE_YEARLY_VALID[
                        year
                    ],

            })

        for _, trade in (
            trades.iterrows()
        ):

            row = trade.to_dict()

            row[
                "engine"
            ] = engine_name

            all_signal_rows.append(
                row
            )

    # --------------------------------------------------------
    # SUMMARY DATAFRAME
    # --------------------------------------------------------

    summary = pd.DataFrame(
        summary_rows
    )

    # Rank primarily by:
    # 1. yearly matches
    # 2. valid difference
    # 3. total difference

    summary[
        "abs_valid_difference"
    ] = summary[
        "valid_difference"
    ].abs()

    summary[
        "abs_total_difference"
    ] = summary[
        "total_difference"
    ].abs()

    summary = summary.sort_values(
        by=[
            "yearly_matches",
            "abs_valid_difference",
            "abs_total_difference",
        ],
        ascending=[
            False,
            True,
            True,
        ]
    )

    yearly_df = pd.DataFrame(
        yearly_rows
    )

    signals_df = pd.DataFrame(
        all_signal_rows
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    summary.to_csv(
        "signal_diagnostics_v2_summary.csv",
        index=False
    )

    yearly_df.to_csv(
        "signal_diagnostics_v2_yearly.csv",
        index=False
    )

    signals_df.to_csv(
        "signal_diagnostics_v2_signals.csv",
        index=False
    )

    # --------------------------------------------------------
    # FINAL SUMMARY
    # --------------------------------------------------------

    print()
    print()
    print("=" * 72)
    print("FINAL V2 SUMMARY")
    print("=" * 72)

    print()

    columns = [

        "engine",

        "total_signals",

        "total_difference",

        "valid_setups",

        "valid_difference",

        "invalid_sl",

        "invalid_difference",

        "yearly_matches",

        "yearly_total",

        "status",

    ]

    print(
        summary[
            columns
        ].to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # BEST CANDIDATE
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("BEST CANDIDATES")
    print("=" * 72)

    print()

    top = summary.head(
        10
    )

    print(
        top[
            columns
        ].to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # EXACT MATCHES
    # --------------------------------------------------------

    exact = summary[
        summary["status"]
        ==
        "EXACT MATCH"
    ]

    print()
    print("=" * 72)
    print("EXACT MATCHES")
    print("=" * 72)

    if exact.empty:

        print(
            "NO EXACT MATCH FOUND."
        )

    else:

        print(
            exact[
                columns
            ].to_string(
                index=False
            )
        )

    # --------------------------------------------------------
    # FILES
    # --------------------------------------------------------

    print()
    print("=" * 72)
    print("FILES CREATED")
    print("=" * 72)

    print(
        "signal_diagnostics_v2_summary.csv"
    )

    print(
        "signal_diagnostics_v2_yearly.csv"
    )

    print(
        "signal_diagnostics_v2_signals.csv"
    )

    print()
    print("=" * 72)
    print("DIAGNOSTIC V2 COMPLETE")
    print("=" * 72)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
