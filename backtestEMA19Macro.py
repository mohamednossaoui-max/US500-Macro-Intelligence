# ============================================================
# US500 / S&P 500
# EMA19 Signal Engine Diagnostic
#
# الهدف:
# تحديد أي منطق لتوليد الإشارات يطابق الـ baseline التاريخي
# المعروف لدينا:
#
# Total signals = 119
#
# Yearly reference:
# 2019 = 1
# 2020 = 16
# 2021 = 26
# 2022 = 5
# 2023 = 15
# 2024 = 17
# 2025 = 19
# 2026 = 18
#
# IMPORTANT:
# هذا الملف يشخّص Signal Engine فقط.
# لا نستخدم Macro ولا Early Warning ولا Fed Intelligence.
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
EMA_SLOW = 200

ATR_PERIOD = 14
STOP_LOOKBACK = 5
ATR_MULTIPLIER = 0.5

RR = 4.0


# ============================================================
# KNOWN REFERENCE
# ============================================================

REFERENCE_TOTAL = 119

REFERENCE_YEARLY = {
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
# DOWNLOAD MARKET DATA
# ============================================================

def get_market_data():

    print("=" * 70)
    print("DOWNLOADING MARKET DATA")
    print("=" * 70)

    df = yf.download(
        TICKER,
        start=START_DATE,
        auto_adjust=False,
        progress=False
    )

    if df.empty:
        raise RuntimeError("No market data downloaded.")

    # yfinance may return MultiIndex columns
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required = ["Open", "High", "Low", "Close"]

    missing = [c for c in required if c not in df.columns]

    if missing:
        raise RuntimeError(
            f"Missing columns: {missing}"
        )

    df = df[required].copy()

    df.index = pd.to_datetime(df.index)

    # Remove timezone if present
    try:
        df.index = df.index.tz_localize(None)
    except Exception:
        pass

    df = df.sort_index()

    df = df.dropna()

    print(f"Ticker       : {TICKER}")
    print(f"Start        : {df.index.min().date()}")
    print(f"End          : {df.index.max().date()}")
    print(f"Rows         : {len(df)}")

    return df


# ============================================================
# INDICATORS
# ============================================================

def add_indicators(df):

    df = df.copy()

    # --------------------------------------------------------
    # EMA 19
    # --------------------------------------------------------

    df["EMA19"] = (
        df["Close"]
        .ewm(
            span=EMA_FAST,
            adjust=False
        )
        .mean()
    )

    # --------------------------------------------------------
    # EMA 200
    # --------------------------------------------------------

    df["EMA200"] = (
        df["Close"]
        .ewm(
            span=EMA_SLOW,
            adjust=False
        )
        .mean()
    )

    # --------------------------------------------------------
    # TRUE RANGE
    # --------------------------------------------------------

    previous_close = df["Close"].shift(1)

    tr1 = df["High"] - df["Low"]

    tr2 = (
        df["High"] - previous_close
    ).abs()

    tr3 = (
        df["Low"] - previous_close
    ).abs()

    df["TR"] = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    # --------------------------------------------------------
    # ATR - Wilder
    # --------------------------------------------------------

    df["ATR14_WILDER"] = (
        df["TR"]
        .ewm(
            alpha=1 / ATR_PERIOD,
            adjust=False
        )
        .mean()
    )

    # --------------------------------------------------------
    # ATR - SMA
    # --------------------------------------------------------

    df["ATR14_SMA"] = (
        df["TR"]
        .rolling(ATR_PERIOD)
        .mean()
    )

    # --------------------------------------------------------
    # ATR - pandas span
    # --------------------------------------------------------

    df["ATR14_SPAN"] = (
        df["TR"]
        .ewm(
            span=ATR_PERIOD,
            adjust=False
        )
        .mean()
    )

    # --------------------------------------------------------
    # ATR - Wilder adjust=True
    # --------------------------------------------------------

    df["ATR14_WILDER_ADJUST"] = (
        df["TR"]
        .ewm(
            alpha=1 / ATR_PERIOD,
            adjust=True
        )
        .mean()
    )

    return df


# ============================================================
# BASE TECHNICAL CONDITION
# ============================================================

def base_condition(df):

    return (
        (df["Close"] > df["EMA200"])
        &
        (df["EMA19"] > df["EMA200"])
        &
        (df["Low"] <= df["EMA19"])
    )


# ============================================================
# SIGNAL ENGINE CANDIDATES
# ============================================================

def generate_signals_all(df):
    """
    Candidate A

    Every candle satisfying the original conditions
    becomes a signal.

    Overlapping signals allowed.
    """

    condition = base_condition(df)

    return df.index[condition].tolist()


def generate_signals_first_after_nonqualifying(df):
    """
    Candidate B

    Signal only when current candle qualifies AND
    previous candle did NOT qualify.

    This creates one signal at the beginning of
    each consecutive qualifying sequence.
    """

    condition = base_condition(df)

    previous = condition.shift(1).fillna(False)

    signal = (
        condition
        &
        ~previous
    )

    return df.index[signal].tolist()


def generate_signals_last_in_run(df):
    """
    Candidate C

    Signal only on the LAST qualifying candle
    in a consecutive qualifying sequence.
    """

    condition = base_condition(df)

    next_day = condition.shift(-1).fillna(False)

    signal = (
        condition
        &
        ~next_day
    )

    return df.index[signal].tolist()


def generate_signals_prev_close_above_ema19(df):
    """
    Candidate D

    Current candle must touch EMA19,
    while previous candle closed above EMA19.

    This attempts to capture a NEW pullback.
    """

    condition = (
        (df["Close"] > df["EMA200"])
        &
        (df["EMA19"] > df["EMA200"])
        &
        (df["Low"] <= df["EMA19"])
        &
        (df["Close"].shift(1) > df["EMA19"].shift(1))
    )

    return df.index[condition].tolist()


def generate_signals_prev_close_above_ema19_or_first(df):
    """
    Candidate E

    New pullback condition.

    Signal when:
      - current candle touches EMA19
      - trend conditions valid
      - previous candle was above EMA19

    This is essentially a stricter pullback reset.
    """

    condition = base_condition(df)

    reset = (
        df["Close"].shift(1)
        >
        df["EMA19"].shift(1)
    )

    signal = (
        condition
        &
        reset
    )

    return df.index[signal].tolist()


def generate_signals_cooldown(df, cooldown_days):
    """
    Candidate F

    Every qualifying candle can generate a signal,
    except signals within N calendar/trading rows
    after a previous signal.
    """

    condition = base_condition(df)

    candidate_dates = df.index[condition].tolist()

    selected = []

    last_position = None

    for date in candidate_dates:

        current_position = df.index.get_loc(date)

        if last_position is None:

            selected.append(date)

            last_position = current_position

        else:

            distance = (
                current_position
                -
                last_position
            )

            if distance > cooldown_days:

                selected.append(date)

                last_position = current_position

    return selected


def generate_signals_one_trade_at_time(df):
    """
    Candidate G

    Only one trade can be active at a time.

    IMPORTANT:
    This is the current reconstructed engine that produced
    approximately 75 signals and therefore is unlikely to be
    the old 119-signal baseline.
    """

    condition = base_condition(df)

    candidate_dates = df.index[condition].tolist()

    selected = []

    active_until_position = -1

    for date in candidate_dates:

        position = df.index.get_loc(date)

        if position <= active_until_position:
            continue

        selected.append(date)

        # We need to determine when this trade resolves.
        # For the diagnostic, we use the same stop/TP logic.
        stop = calculate_stop(
            df,
            position,
            atr_column="ATR14_WILDER"
        )

        if stop is None:
            active_until_position = position
            continue

        entry = float(df.iloc[position]["Close"])

        risk = entry - stop

        if risk <= 0:
            active_until_position = position
            continue

        target = entry + RR * risk

        resolution = find_trade_resolution(
            df,
            position,
            stop,
            target
        )

        if resolution is None:
            active_until_position = len(df) - 1
        else:
            active_until_position = resolution

    return selected


# ============================================================
# STOP CALCULATION
# ============================================================

def calculate_stop(
    df,
    signal_position,
    atr_column="ATR14_WILDER"
):
    """
    Original intended stop:

    Lowest Low of previous 5 COMPLETED candles
    minus 0.5 × ATR(14)

    The trigger candle itself is excluded.
    """

    if signal_position < STOP_LOOKBACK:
        return None

    previous_lows = (
        df["Low"]
        .iloc[
            signal_position - STOP_LOOKBACK:
            signal_position
        ]
    )

    lowest_low = previous_lows.min()

    atr = df.iloc[
        signal_position - 1
    ][atr_column]

    if pd.isna(atr):
        return None

    stop = (
        lowest_low
        -
        ATR_MULTIPLIER * atr
    )

    return float(stop)


# ============================================================
# TRADE RESOLUTION
# ============================================================

def find_trade_resolution(
    df,
    entry_position,
    stop,
    target
):
    """
    Evaluates candles AFTER the entry candle.

    Same-day TP/SL is not evaluated because entry happens
    at the close of the signal candle.

    If both TP and SL are touched on the same future candle,
    the result is AMBIGUOUS.
    """

    for i in range(
        entry_position + 1,
        len(df)
    ):

        high = float(df.iloc[i]["High"])
        low = float(df.iloc[i]["Low"])

        hit_stop = low <= stop
        hit_target = high >= target

        if hit_stop and hit_target:
            return i

        if hit_stop:
            return i

        if hit_target:
            return i

    return None


# ============================================================
# YEARLY COUNTS
# ============================================================

def yearly_counts(signal_dates):

    if not signal_dates:

        return {}

    years = pd.Series(
        pd.to_datetime(signal_dates)
    ).dt.year

    counts = (
        years
        .value_counts()
        .sort_index()
        .to_dict()
    )

    return {
        int(k): int(v)
        for k, v in counts.items()
    }


# ============================================================
# SIGNAL TABLE
# ============================================================

def build_signal_table(
    df,
    signal_dates,
    engine_name
):

    rows = []

    for date in signal_dates:

        position = df.index.get_loc(date)

        row = df.iloc[position]

        stop = calculate_stop(
            df,
            position,
            atr_column="ATR14_WILDER"
        )

        entry = float(row["Close"])

        risk = None
        target = None

        if stop is not None:

            risk = entry - stop

            if risk > 0:

                target = (
                    entry
                    +
                    RR * risk
                )

        rows.append({

            "engine": engine_name,

            "date": date.strftime(
                "%Y-%m-%d"
            ),

            "year": date.year,

            "open": float(row["Open"]),

            "high": float(row["High"]),

            "low": float(row["Low"]),

            "close": entry,

            "EMA19": float(row["EMA19"]),

            "EMA200": float(row["EMA200"]),

            "ATR14": (
                float(row["ATR14_WILDER"])
                if not pd.isna(row["ATR14_WILDER"])
                else np.nan
            ),

            "stop": stop,

            "risk": risk,

            "target": target,

        })

    return pd.DataFrame(rows)


# ============================================================
# COMPARE WITH REFERENCE
# ============================================================

def compare_reference(
    engine_name,
    signal_dates
):

    counts = yearly_counts(signal_dates)

    years = sorted(
        set(
            list(REFERENCE_YEARLY.keys())
            +
            list(counts.keys())
        )
    )

    total = len(signal_dates)

    total_difference = (
        total
        -
        REFERENCE_TOTAL
    )

    exact_total = (
        total
        ==
        REFERENCE_TOTAL
    )

    yearly_match_count = 0

    for year in years:

        actual = counts.get(
            year,
            0
        )

        expected = REFERENCE_YEARLY.get(
            year,
            0
        )

        if actual == expected:
            yearly_match_count += 1

    exact_yearly = (
        all(
            counts.get(year, 0)
            ==
            REFERENCE_YEARLY.get(year, 0)
            for year in REFERENCE_YEARLY
        )
    )

    if exact_total and exact_yearly:

        status = "EXACT MATCH"

    elif exact_total:

        status = "TOTAL MATCH / YEARLY MISMATCH"

    else:

        status = "NO MATCH"

    return {

        "engine": engine_name,

        "total_signals": total,

        "reference_total": REFERENCE_TOTAL,

        "difference": total_difference,

        "yearly_matches": yearly_match_count,

        "yearly_reference_count": len(
            REFERENCE_YEARLY
        ),

        "status": status,

    }


# ============================================================
# BUILD YEARLY DIAGNOSTIC TABLE
# ============================================================

def build_yearly_diagnostic(
    engine_name,
    signal_dates
):

    counts = yearly_counts(
        signal_dates
    )

    rows = []

    for year in sorted(
        REFERENCE_YEARLY.keys()
    ):

        expected = REFERENCE_YEARLY[
            year
        ]

        actual = counts.get(
            year,
            0
        )

        rows.append({

            "engine": engine_name,

            "year": year,

            "reference": expected,

            "actual": actual,

            "difference": (
                actual
                -
                expected
            ),

            "match": (
                actual
                ==
                expected
            )

        })

    return pd.DataFrame(rows)


# ============================================================
# PRINT ENGINE RESULT
# ============================================================

def print_engine_result(
    engine_name,
    signal_dates
):

    result = compare_reference(
        engine_name,
        signal_dates
    )

    counts = yearly_counts(
        signal_dates
    )

    print()
    print("-" * 70)
    print(engine_name)
    print("-" * 70)

    print(
        f"Total signals : {result['total_signals']}"
    )

    print(
        f"Reference     : {REFERENCE_TOTAL}"
    )

    print(
        f"Difference    : {result['difference']}"
    )

    print(
        f"Year matches  : "
        f"{result['yearly_matches']}/"
        f"{result['yearly_reference_count']}"
    )

    print(
        f"STATUS        : {result['status']}"
    )

    print()

    print(
        "YEAR | REFERENCE | ACTUAL | DIFF"
    )

    print(
        "-" * 42
    )

    for year in sorted(
        REFERENCE_YEARLY.keys()
    ):

        reference = REFERENCE_YEARLY[
            year
        ]

        actual = counts.get(
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
            else " "
        )

        print(
            f"{year} | "
            f"{reference:9d} | "
            f"{actual:6d} | "
            f"{diff:+4d} {marker}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("US500 EMA19 SIGNAL ENGINE DIAGNOSTIC")
    print("=" * 70)

    print()
    print("REFERENCE BASELINE")
    print("-" * 70)

    print(
        f"Total signals: {REFERENCE_TOTAL}"
    )

    for year, count in (
        REFERENCE_YEARLY.items()
    ):

        print(
            f"{year}: {count}"
        )

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    df = get_market_data()

    df = add_indicators(df)

    # Remove the initial indicator period
    df = df.dropna(
        subset=[
            "EMA19",
            "EMA200"
        ]
    )

    print()
    print("=" * 70)
    print("DATA READY")
    print("=" * 70)

    print(
        f"Rows after indicators: {len(df)}"
    )

    # --------------------------------------------------------
    # CANDIDATE ENGINES
    # --------------------------------------------------------

    engines = {}

    # A
    engines[
        "A_ALL_QUALIFYING"
    ] = generate_signals_all(df)

    # B
    engines[
        "B_FIRST_AFTER_NONQUALIFYING"
    ] = generate_signals_first_after_nonqualifying(df)

    # C
    engines[
        "C_LAST_IN_QUALIFYING_RUN"
    ] = generate_signals_last_in_run(df)

    # D
    engines[
        "D_PREV_CLOSE_ABOVE_EMA19"
    ] = generate_signals_prev_close_above_ema19(df)

    # E
    engines[
        "E_NEW_PULLBACK_RESET"
    ] = generate_signals_prev_close_above_ema19_or_first(df)

    # F1
    engines[
        "F_COOLDOWN_1"
    ] = generate_signals_cooldown(
        df,
        1
    )

    # F2
    engines[
        "F_COOLDOWN_2"
    ] = generate_signals_cooldown(
        df,
        2
    )

    # F3
    engines[
        "F_COOLDOWN_3"
    ] = generate_signals_cooldown(
        df,
        3
    )

    # F5
    engines[
        "F_COOLDOWN_5"
    ] = generate_signals_cooldown(
        df,
        5
    )

    # F10
    engines[
        "F_COOLDOWN_10"
    ] = generate_signals_cooldown(
        df,
        10
    )

    # G
    engines[
        "G_ONE_TRADE_AT_TIME"
    ] = generate_signals_one_trade_at_time(
        df
    )

    # --------------------------------------------------------
    # RESULTS
    # --------------------------------------------------------

    summary_rows = []

    yearly_rows = []

    signal_tables = []

    for engine_name, signal_dates in engines.items():

        print_engine_result(
            engine_name,
            signal_dates
        )

        result = compare_reference(
            engine_name,
            signal_dates
        )

        summary_rows.append(
            result
        )

        yearly_df = build_yearly_diagnostic(
            engine_name,
            signal_dates
        )

        yearly_rows.append(
            yearly_df
        )

        signal_df = build_signal_table(
            df,
            signal_dates,
            engine_name
        )

        signal_tables.append(
            signal_df
        )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary = pd.DataFrame(
        summary_rows
    )

    summary = summary.sort_values(
        by=[
            "yearly_matches",
            "total_signals"
        ],
        ascending=[
            False,
            True
        ]
    )

    yearly = pd.concat(
        yearly_rows,
        ignore_index=True
    )

    signals = pd.concat(
        signal_tables,
        ignore_index=True
    )

    # --------------------------------------------------------
    # SAVE FILES
    # --------------------------------------------------------

    summary.to_csv(
        "signal_diagnostics_summary.csv",
        index=False
    )

    yearly.to_csv(
        "signal_diagnostics_yearly.csv",
        index=False
    )

    signals.to_csv(
        "signal_diagnostics_signals.csv",
        index=False
    )

    # --------------------------------------------------------
    # FINAL REPORT
    # --------------------------------------------------------

    print()
    print()
    print("=" * 70)
    print("FINAL DIAGNOSTIC SUMMARY")
    print("=" * 70)

    print()

    print(
        summary[
            [
                "engine",
                "total_signals",
                "reference_total",
                "difference",
                "yearly_matches",
                "yearly_reference_count",
                "status"
            ]
        ].to_string(
            index=False
        )
    )

    print()
    print("=" * 70)
    print("REFERENCE YEARLY COUNTS")
    print("=" * 70)

    print()

    print(
        "Year | "
        "Reference | "
        +
        " | ".join(
            [
                "Actual"
            ]
        )
    )

    print("-" * 45)

    # Best candidate
    best_engine = (
        summary.iloc[0]["engine"]
        if not summary.empty
        else None
    )

    if best_engine:

        print()
        print(
            f"BEST CANDIDATE: {best_engine}"
        )

        best_row = summary.iloc[0]

        print(
            f"Total signals: "
            f"{best_row['total_signals']}"
        )

        print(
            f"Yearly matches: "
            f"{best_row['yearly_matches']}/"
            f"{best_row['yearly_reference_count']}"
        )

        print(
            f"Status: "
            f"{best_row['status']}"
        )

    # --------------------------------------------------------
    # ATR DIAGNOSTIC
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("ATR DIAGNOSTIC")
    print("=" * 70)

    print()

    print(
        "Signal count is independent of ATR."
    )

    print(
        "ATR only affects stop validity and R results."
    )

    print()

    atr_columns = [
        "ATR14_WILDER",
        "ATR14_SMA",
        "ATR14_SPAN",
        "ATR14_WILDER_ADJUST"
    ]

    # Use all qualifying signals for ATR diagnostic
    all_signals = engines[
        "A_ALL_QUALIFYING"
    ]

    atr_rows = []

    for atr_column in atr_columns:

        invalid = 0
        valid = 0

        for date in all_signals:

            position = df.index.get_loc(
                date
            )

            stop = calculate_stop(
                df,
                position,
                atr_column
            )

            if stop is None:

                invalid += 1

                continue

            entry = float(
                df.iloc[position]["Close"]
            )

            risk = (
                entry
                -
                stop
            )

            if risk <= 0:

                invalid += 1

            else:

                valid += 1

        atr_rows.append({

            "ATR_method": atr_column,

            "signals": len(
                all_signals
            ),

            "valid_SL": valid,

            "invalid_SL": invalid

        })

    atr_df = pd.DataFrame(
        atr_rows
    )

    print(
        atr_df.to_string(
            index=False
        )
    )

    atr_df.to_csv(
        "signal_diagnostics_atr.csv",
        index=False
    )

    # --------------------------------------------------------
    # DONE
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("FILES CREATED")
    print("=" * 70)

    print(
        "signal_diagnostics_summary.csv"
    )

    print(
        "signal_diagnostics_yearly.csv"
    )

    print(
        "signal_diagnostics_signals.csv"
    )

    print(
        "signal_diagnostics_atr.csv"
    )

    print()
    print("=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
