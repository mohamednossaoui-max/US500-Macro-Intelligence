# ============================================================
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
