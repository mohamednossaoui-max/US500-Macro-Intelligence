"""
US500 EMA19 + Macro Regime Backtest
===================================

Phase 2:
EMA19 Pullback baseline + historical macro regime classification.

IMPORTANT:
- No trade execution.
- No position sizing.
- No optimization.
- EMA19 entry logic is kept unchanged.
- Stop loss and TP are kept unchanged.
- Macro is used for historical classification and comparison only.
- No future market data is used to classify the signal date.
"""

from __future__ import annotations

import warnings
from typing import Optional

import numpy as np
import pandas as pd

from data import (
    get_historical_market_data,
    load_all_macro_data,
)

warnings.filterwarnings("ignore")


# ============================================================
# SETTINGS
# ============================================================

START_DATE = "2019-01-01"

EMA_FAST = 19
EMA_TREND = 200

RR = 4.0

ATR_PERIOD = 14
LOOKBACK_LOW = 5
ATR_MULTIPLIER = 0.5

TICKER = "^GSPC"


# ============================================================
# BASIC INDICATORS
# ============================================================

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate Wilder-style ATR using pandas ewm.
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    previous_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - previous_close).abs()
    tr3 = (low - previous_close).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    atr = true_range.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    return atr


def prepare_market_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare daily market data and indicators.

    ATR is shifted by one completed candle so the stop
    calculation does not use the trigger candle.
    """

    data = df.copy()

    data.index = pd.to_datetime(data.index)
    data = data.sort_index()

    # Normalize column names
    data.columns = [
        str(c).lower().replace(" ", "_")
        for c in data.columns
    ]

    required = ["open", "high", "low", "close"]

    for col in required:
        if col not in data.columns:
            raise ValueError(
                f"Required market column missing: {col}"
            )

    data["ema19"] = data["close"].ewm(
        span=EMA_FAST,
        adjust=False
    ).mean()

    data["ema200"] = data["close"].ewm(
        span=EMA_TREND,
        adjust=False
    ).mean()

    # IMPORTANT:
    # ATR available to the trade is the ATR from the
    # previous completed candle.
    data["atr14"] = calculate_atr(
        data,
        ATR_PERIOD
    ).shift(1)

    return data


# ============================================================
# EMA19 SIGNAL DETECTION
# ============================================================

def detect_ema19_pullbacks(
    df: pd.DataFrame
) -> pd.DataFrame:
    """
    Detect EMA19 pullback signals.

    Conditions:

    1. Close > EMA200
    2. EMA19 > EMA200
    3. Daily Low touches or crosses EMA19
    4. Daily Close is above EMA19
    5. Avoid duplicate signals immediately after a reclaim.

    Entry = trigger candle close.
    """

    signals = []

    start_index = EMA_TREND

    for i in range(start_index, len(df)):

        row = df.iloc[i]

        close = row["close"]
        low = row["low"]
        ema19 = row["ema19"]
        ema200 = row["ema200"]

        if pd.isna(close):
            continue

        if pd.isna(low):
            continue

        if pd.isna(ema19):
            continue

        if pd.isna(ema200):
            continue

        # Primary trend filter
        if close <= ema200:
            continue

        if ema19 <= ema200:
            continue

        # Pullback must reach EMA19
        if low > ema19:
            continue

        # Avoid immediate duplicate/reclaim signal
        if i > 0:

            previous = df.iloc[i - 1]

            previous_close = previous["close"]
            previous_low = previous["low"]
            previous_ema19 = previous["ema19"]

            if (
                not pd.isna(previous_close)
                and not pd.isna(previous_low)
                and not pd.isna(previous_ema19)
            ):

                previous_was_reclaim = (
                    previous_close > previous_ema19
                    and previous_low <= previous_ema19
                )

                if previous_was_reclaim:
                    continue

        distance_ema19 = (
            (close / ema19) - 1
        ) * 100

        distance_ema200 = (
            (close / ema200) - 1
        ) * 100

        signals.append(
            {
                "signal_date": df.index[i],
                "entry": float(close),
                "ema19": float(ema19),
                "ema200": float(ema200),
                "distance_from_ema19_pct": float(
                    distance_ema19
                ),
                "distance_from_ema200_pct": float(
                    distance_ema200
                ),
            }
        )

    return pd.DataFrame(signals)


# ============================================================
# STOP LOSS
# ============================================================

def calculate_stop_loss(
    df: pd.DataFrame,
    signal_index: int
) -> Optional[float]:

    """
    Stop = lowest Low of previous 5 completed candles
           - 0.5 * previous completed ATR14

    Trigger candle is excluded.
    """

    if signal_index < LOOKBACK_LOW:
        return None

    row = df.iloc[signal_index]

    atr = row["atr14"]

    if pd.isna(atr):
        return None

    previous_candles = df.iloc[
        signal_index - LOOKBACK_LOW:
        signal_index
    ]

    if len(previous_candles) < LOOKBACK_LOW:
        return None

    lowest_low = previous_candles["low"].min()

    if pd.isna(lowest_low):
        return None

    stop_loss = (
        lowest_low
        - ATR_MULTIPLIER * atr
    )

    return float(stop_loss)


# ============================================================
# TRADE EVALUATION
# ============================================================

def evaluate_trade(
    df: pd.DataFrame,
    signal_index: int,
    entry: float,
    stop_loss: float,
    take_profit: float,
) -> dict:

    """
    Evaluate trade from the NEXT completed candle.

    If both TP and SL are touched on the same daily candle,
    result = AMBIGUOUS because OHLC data cannot tell us
    which level was hit first.
    """

    result = {
        "status": "OPEN",
        "result": "OPEN",
        "exit_date": pd.NaT,
        "R": np.nan,
    }

    for j in range(
        signal_index + 1,
        len(df)
    ):

        row = df.iloc[j]

        high = row["high"]
        low = row["low"]

        if pd.isna(high) or pd.isna(low):
            continue

        hit_tp = high >= take_profit
        hit_sl = low <= stop_loss

        # Both levels touched during same daily candle
        if hit_tp and hit_sl:

            result["status"] = "VALID"
            result["result"] = "AMBIGUOUS"
            result["exit_date"] = df.index[j]

            return result

        if hit_sl:

            result["status"] = "VALID"
            result["result"] = "LOSS"
            result["exit_date"] = df.index[j]
            result["R"] = -1.0

            return result

        if hit_tp:

            result["status"] = "VALID"
            result["result"] = "WIN"
            result["exit_date"] = df.index[j]
            result["R"] = RR

            return result

    return result


# ============================================================
# EMA19 BASELINE BACKTEST
# ============================================================

def build_ema19_backtest(
    market: pd.DataFrame,
    signals: pd.DataFrame
) -> pd.DataFrame:

    trades = []

    for _, signal in signals.iterrows():

        signal_date = pd.Timestamp(
            signal["signal_date"]
        )

        try:
            signal_index = market.index.get_loc(
                signal_date
            )
        except KeyError:
            continue

        entry = float(signal["entry"])

        stop_loss = calculate_stop_loss(
            market,
            signal_index
        )

        row = signal.to_dict()

        row["stop_loss"] = stop_loss

        # Invalid stop:
        # Stop must be below entry for a long trade.
        if (
            stop_loss is None
            or pd.isna(stop_loss)
            or stop_loss >= entry
        ):

            row["take_profit"] = np.nan
            row["risk_points"] = np.nan
            row["status"] = "INVALID_SL"
            row["result"] = "INVALID_SL"
            row["exit_date"] = pd.NaT
            row["R"] = np.nan

            trades.append(row)

            continue

        risk_points = (
            entry - stop_loss
        )

        take_profit = (
            entry
            + RR * risk_points
        )

        evaluation = evaluate_trade(
            market,
            signal_index,
            entry,
            stop_loss,
            take_profit,
        )

        row["take_profit"] = take_profit
        row["risk_points"] = risk_points

        row.update(evaluation)

        trades.append(row)

    return pd.DataFrame(trades)


# ============================================================
# MACRO DATA HELPERS
# ============================================================

def _find_date_column(df: pd.DataFrame) -> Optional[str]:

    for col in df.columns:

        name = str(col).lower()

        if name in (
            "date",
            "datetime",
            "time",
        ):
            return col

    return None


def _prepare_macro_frame(
    value,
    name: str
) -> pd.DataFrame:

    """
    Convert several possible data.py return formats
    into:

        date | value
    """

    if value is None:
        return pd.DataFrame(
            columns=["date", name]
        )

    # Series
    if isinstance(value, pd.Series):

        frame = value.to_frame(
            name=name
        ).reset_index()

    # DataFrame
    elif isinstance(value, pd.DataFrame):

        frame = value.copy()

        date_column = _find_date_column(
            frame
        )

        if date_column is not None:

            if date_column != "date":

                frame = frame.rename(
                    columns={
                        date_column: "date"
                    }
                )

            # If there is exactly one value column
            value_columns = [
                c for c in frame.columns
                if c != "date"
            ]

            if name not in frame.columns:

                if len(value_columns) == 1:

                    frame = frame.rename(
                        columns={
                            value_columns[0]: name
                        }
                    )

        else:

            # DatetimeIndex
            if isinstance(
                frame.index,
                pd.DatetimeIndex
            ):

                frame = frame.reset_index()

                frame = frame.rename(
                    columns={
                        frame.columns[0]: "date"
                    }
                )

                value_columns = [
                    c for c in frame.columns
                    if c != "date"
                ]

                if name not in frame.columns:

                    if len(value_columns) == 1:

                        frame = frame.rename(
                            columns={
                                value_columns[0]: name
                            }
                        )

    else:

        return pd.DataFrame(
            columns=["date", name]
        )

    if "date" not in frame.columns:

        return pd.DataFrame(
            columns=["date", name]
        )

    if name not in frame.columns:

        value_columns = [
            c for c in frame.columns
            if c != "date"
        ]

        if not value_columns:

            return pd.DataFrame(
                columns=["date", name]
            )

        frame = frame.rename(
            columns={
                value_columns[0]: name
            }
        )

    frame["date"] = pd.to_datetime(
        frame["date"],
        errors="coerce"
    )

    frame[name] = pd.to_numeric(
        frame[name],
        errors="coerce"
    )

    frame = frame[
        ["date", name]
    ].dropna(
        subset=["date"]
    )

    frame = frame.sort_values(
        "date"
    )

    frame = frame.drop_duplicates(
        subset=["date"],
        keep="last"
    )

    return frame


def _extract_macro_series(
    macro_data,
    possible_names
) -> pd.DataFrame:

    """
    Find a macro series inside the object returned
    by data.load_all_macro_data().
    """

    if macro_data is None:
        return pd.DataFrame()

    # Dictionary
    if isinstance(
        macro_data,
        dict
    ):

        normalized = {
            str(k).lower(): v
            for k, v in macro_data.items()
        }

        for wanted in possible_names:

            key = wanted.lower()

            if key in normalized:

                return _prepare_macro_frame(
                    normalized[key],
                    wanted
                )

        # Fuzzy fallback
        for key, value in normalized.items():

            for wanted in possible_names:

                if wanted.lower() in key:

                    return _prepare_macro_frame(
                        value,
                        wanted
                    )

    # DataFrame containing many series
    if isinstance(
        macro_data,
        pd.DataFrame
    ):

        columns_lower = {
            str(c).lower(): c
            for c in macro_data.columns
        }

        for wanted in possible_names:

            if wanted.lower() in columns_lower:

                original = columns_lower[
                    wanted.lower()
                ]

                frame = macro_data[
                    [original]
                ].copy()

                frame = frame.rename(
                    columns={
                        original: wanted
                    }
                )

                frame = frame.reset_index()

                if "index" in frame.columns:

                    frame = frame.rename(
                        columns={
                            "index": "date"
                        }
                    )

                return _prepare_macro_frame(
                    frame,
                    wanted
                )

    return pd.DataFrame()


# ============================================================
# MACRO REGIME CLASSIFICATION
# ============================================================

def classify_macro_regime(
    row: pd.Series
) -> str:

    """
    Transparent rule-based macro classification.

    A = Healthy / Technical Pullback
    B = Growth Scare
    C = Inflation / Rates Shock
    D = Growth + Inflation / Mixed Stress
    E = Recession / Bear Risk
    F = Liquidity / Financial Shock

    IMPORTANT:
    These rules are deliberately simple for Phase 2.
    They are NOT optimized to maximize backtest returns.
    """

    # --------------------------------------------------------
    # Extract values
    # --------------------------------------------------------

    hy = row.get("HY_SPREAD", np.nan)
    corp = row.get("CORP_OAS", np.nan)
    vix = row.get("VIX", np.nan)

    t10y2y = row.get(
        "T10Y2Y",
        np.nan
    )

    unrate = row.get(
        "UNRATE",
        np.nan
    )

    claims = row.get(
        "INITIAL_CLAIMS_4W",
        np.nan
    )

    pce = row.get(
        "PCE",
        np.nan
    )

    core_pce = row.get(
        "CORE_PCE",
        np.nan
    )

    indpro = row.get(
        "INDPRO",
        np.nan
    )

    retail = row.get(
        "RETAIL",
        np.nan
    )

    us10y = row.get(
        "US10Y",
        np.nan
    )

    us2y = row.get(
        "US2Y",
        np.nan
    )

    fedfunds = row.get(
        "FEDFUNDS",
        np.nan
    )

    # --------------------------------------------------------
    # Financial / liquidity stress
    # --------------------------------------------------------

    financial_stress = False

    if not pd.isna(vix) and vix >= 35:
        financial_stress = True

    if not pd.isna(hy) and hy >= 6:
        financial_stress = True

    if not pd.isna(corp) and corp >= 3.5:
        financial_stress = True

    # --------------------------------------------------------
    # Recession / bear-risk conditions
    # --------------------------------------------------------

    recession_score = 0

    if (
        not pd.isna(unrate)
        and unrate >= 5.0
    ):
        recession_score += 2

    if (
        not pd.isna(claims)
        and claims >= 300000
    ):
        recession_score += 2

    if (
        not pd.isna(indpro)
        and indpro < 0
    ):
        recession_score += 1

    if (
        not pd.isna(retail)
        and retail < 0
    ):
        recession_score += 1

    if (
        not pd.isna(t10y2y)
        and t10y2y < -0.50
    ):
        recession_score += 1

    if recession_score >= 3:
        return "E — Recession / Bear Risk"

    # --------------------------------------------------------
    # Financial shock takes priority
    # --------------------------------------------------------

    if financial_stress:
        return "F — Liquidity / Financial Shock"

    # --------------------------------------------------------
    # Inflation / rates shock
    # --------------------------------------------------------

    inflation_score = 0

    if (
        not pd.isna(pce)
        and pce >= 3.0
    ):
        inflation_score += 1

    if (
        not pd.isna(core_pce)
        and core_pce >= 3.0
    ):
        inflation_score += 1

    if (
        not pd.isna(us10y)
        and us10y >= 4.5
    ):
        inflation_score += 1

    if (
        not pd.isna(us2y)
        and us2y >= 4.5
    ):
        inflation_score += 1

    if (
        not pd.isna(fedfunds)
        and fedfunds >= 4.5
    ):
        inflation_score += 1

    if inflation_score >= 3:

        growth_weak = False

        if (
            not pd.isna(indpro)
            and indpro < 0
        ):
            growth_weak = True

        if (
            not pd.isna(retail)
            and retail < 0
        ):
            growth_weak = True

        if growth_weak:
            return "D — Growth + Inflation / Mixed Stress"

        return "C — Inflation / Rates Shock"

    # --------------------------------------------------------
    # Growth scare
    # --------------------------------------------------------

    growth_weak_count = 0

    if (
        not pd.isna(indpro)
        and indpro < 0
    ):
        growth_weak_count += 1

    if (
        not pd.isna(retail)
        and retail < 0
    ):
        growth_weak_count += 1

    if (
        not pd.isna(claims)
        and claims >= 260000
    ):
        growth_weak_count += 1

    if growth_weak_count >= 2:

        inflation_not_hot = True

        if (
            not pd.isna(pce)
            and pce >= 3.5
        ):
            inflation_not_hot = False

        if (
            not pd.isna(core_pce)
            and core_pce >= 3.5
        ):
            inflation_not_hot = False

        if inflation_not_hot:
            return "B — Growth Scare / Healthy Correction"

    # --------------------------------------------------------
    # Default
    # --------------------------------------------------------

    return "A — Healthy / Technical Pullback"


# ============================================================
# MACRO DATA PREPARATION
# ============================================================

def prepare_macro_data(
    market: pd.DataFrame
) -> pd.DataFrame:

    """
    Load macro data and align it to market dates.

    CRITICAL:
    merge_asof(direction='backward') means a signal only sees
    macro observations already published before/on the signal date.

    This is intentionally conservative.
    """

    print()
    print("=" * 60)
    print("LOADING MACRO DATA")
    print("=" * 60)

    try:

        macro_raw = load_all_macro_data()

    except TypeError:

        # Some versions may require a date argument.
        try:
            macro_raw = load_all_macro_data(
                start_date=START_DATE
            )
        except Exception as exc:
            print(
                f"Macro data loading failed: {exc}"
            )
            return pd.DataFrame()

    except Exception as exc:

        print(
            f"Macro data loading failed: {exc}"
        )

        return pd.DataFrame()

    series_map = {

        "US10Y": [
            "US10Y",
            "DGS10",
        ],

        "US2Y": [
            "US2Y",
            "DGS2",
        ],

        "T10Y2Y": [
            "T10Y2Y",
        ],

        "VIX": [
            "VIX",
            "VIXCLS",
        ],

        "UNRATE": [
            "UNRATE",
            "UNEMPLOYMENT",
        ],

        "INITIAL_CLAIMS_4W": [
            "INITIAL_CLAIMS_4W",
            "IC4WSA",
        ],

        "HY_SPREAD": [
            "HY_SPREAD",
            "BAMLH0A0HYM2",
        ],

        "CORP_OAS": [
            "CORP_OAS",
            "BAMLC0A0CM",
        ],

        "NFCI": [
            "NFCI",
        ],

        "INDPRO": [
            "INDPRO",
        ],

        "RETAIL": [
            "RETAIL",
            "RSAFS",
        ],

        "PCE": [
            "PCE",
        ],

        "CORE_PCE": [
            "CORE_PCE",
            "PCEPILFE",
        ],

        "FEDFUNDS": [
            "FEDFUNDS",
        ],
    }

    macro_frames = []

    for standard_name, aliases in series_map.items():

        frame = _extract_macro_series(
            macro_raw,
            aliases
        )

        if frame.empty:
            print(
                f"{standard_name:<22}: UNAVAILABLE"
            )
            continue

        frame = frame.rename(
            columns={
                frame.columns[-1]:
                    standard_name
            }
        )

        macro_frames.append(frame)

        print(
            f"{standard_name:<22}: "
            f"{len(frame):>5} observations"
        )

    if not macro_frames:

        print(
            "No macro series available."
        )

        return pd.DataFrame()

    macro = macro_frames[0].copy()

    for frame in macro_frames[1:]:

        macro = pd.merge(
            macro,
            frame,
            on="date",
            how="outer"
        )

    macro = macro.sort_values(
        "date"
    )

    macro = macro.drop_duplicates(
        subset=["date"],
        keep="last"
    )

    market_reset = (
        market
        .reset_index()
        .rename(
            columns={
                market.index.name
                if market.index.name
                else "index": "date"
            }
        )
    )

    market_reset["date"] = pd.to_datetime(
        market_reset["date"]
    )

    macro["date"] = pd.to_datetime(
        macro["date"]
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # backward alignment prevents future macro observations
    # from leaking into historical signals.
    # --------------------------------------------------------

    merged = pd.merge_asof(
        market_reset.sort_values("date"),
        macro.sort_values("date"),
        on="date",
        direction="backward"
    )

    merged["macro_regime"] = merged.apply(
        classify_macro_regime,
        axis=1
    )

    merged = merged.set_index(
        "date"
    )

    return merged


# ============================================================
# ATTACH MACRO TO TRADES
# ============================================================

def attach_macro_to_trades(
    trades: pd.DataFrame,
    macro_market: pd.DataFrame
) -> pd.DataFrame:

    if trades.empty:
        return trades

    result = trades.copy()

    result["signal_date"] = pd.to_datetime(
        result["signal_date"]
    )

    macro_columns = [
        "macro_regime",
        "US10Y",
        "US2Y",
        "T10Y2Y",
        "VIX",
        "UNRATE",
        "INITIAL_CLAIMS_4W",
        "HY_SPREAD",
        "CORP_OAS",
        "NFCI",
        "INDPRO",
        "RETAIL",
        "PCE",
        "CORE_PCE",
        "FEDFUNDS",
    ]

    available = [
        c for c in macro_columns
        if c in macro_market.columns
    ]

    macro_for_merge = (
        macro_market[
            available
        ]
        .reset_index()
        .rename(
            columns={
                macro_market.index.name
                if macro_market.index.name
                else "index": "signal_date"
            }
        )
    )

    macro_for_merge["signal_date"] = (
        pd.to_datetime(
            macro_for_merge["signal_date"]
        )
    )

    result = pd.merge_asof(
        result.sort_values(
            "signal_date"
        ),
        macro_for_merge.sort_values(
            "signal_date"
        ),
        on="signal_date",
        direction="backward"
    )

    return result


# ============================================================
# SUMMARY FUNCTIONS
# ============================================================

def calculate_summary(
    trades: pd.DataFrame
) -> dict:

    total = len(trades)

    valid = int(
        (
            trades["status"] == "VALID"
        ).sum()
    )

    wins = int(
        (
            trades["result"] == "WIN"
        ).sum()
    )

    losses = int(
        (
            trades["result"] == "LOSS"
        ).sum()
    )

    ambiguous = int(
        (
            trades["result"] == "AMBIGUOUS"
        ).sum()
    )

    open_trades = int(
        (
            trades["result"] == "OPEN"
        ).sum()
    )

    invalid = int(
        (
            trades["status"] == "INVALID_SL"
        ).sum()
    )

    resolved = wins + losses

    if resolved > 0:

        win_rate = (
            wins / resolved
        ) * 100

    else:

        win_rate = np.nan

    resolved_r = trades.loc[
        trades["result"].isin(
            ["WIN", "LOSS"]
        ),
        "R"
    ].dropna()

    if len(resolved_r) > 0:

        average_r = (
            resolved_r.mean()
        )

        total_r = (
            resolved_r.sum()
        )

        gross_profit = (
            resolved_r[
                resolved_r > 0
            ].sum()
        )

        gross_loss = abs(
            resolved_r[
                resolved_r < 0
            ].sum()
        )

        if gross_loss > 0:

            profit_factor = (
                gross_profit
                / gross_loss
            )

        else:

            profit_factor = np.inf

    else:

        average_r = np.nan
        total_r = np.nan
        profit_factor = np.nan

    return {
        "total_signals": total,
        "valid_setups": valid,
        "resolved_trades": resolved,
        "wins": wins,
        "losses": losses,
        "ambiguous": ambiguous,
        "open": open_trades,
        "invalid_sl": invalid,
        "win_rate_pct": win_rate,
        "average_R": average_r,
        "expectancy_R": average_r,
        "total_R": total_r,
        "profit_factor": profit_factor,
    }


def grouped_macro_summary(
    trades: pd.DataFrame
) -> pd.DataFrame:

    if (
        trades.empty
        or "macro_regime" not in trades.columns
    ):
        return pd.DataFrame()

    rows = []

    regime_order = [
        "A — Healthy / Technical Pullback",
        "B — Growth Scare / Healthy Correction",
        "C — Inflation / Rates Shock",
        "D — Growth + Inflation / Mixed Stress",
        "E — Recession / Bear Risk",
        "F — Liquidity / Financial Shock",
    ]

    for regime in regime_order:

        subset = trades[
            trades["macro_regime"]
            == regime
        ]

        if subset.empty:
            continue

        summary = calculate_summary(
            subset
        )

        rows.append(
            {
                "macro_regime": regime,
                "signals": summary[
                    "total_signals"
                ],
                "valid": summary[
                    "valid_setups"
                ],
                "resolved": summary[
                    "resolved_trades"
                ],
                "wins": summary[
                    "wins"
                ],
                "losses": summary[
                    "losses"
                ],
                "ambiguous": summary[
                    "ambiguous"
                ],
                "open": summary[
                    "open"
                ],
                "win_rate_pct": summary[
                    "win_rate_pct"
                ],
                "average_R": summary[
                    "average_R"
                ],
                "total_R": summary[
                    "total_R"
                ],
                "profit_factor": summary[
                    "profit_factor"
                ],
            }
        )

    return pd.DataFrame(rows)


def yearly_macro_summary(
    trades: pd.DataFrame
) -> pd.DataFrame:

    if trades.empty:
        return pd.DataFrame()

    data = trades.copy()

    data["year"] = pd.to_datetime(
        data["signal_date"]
    ).dt.year

    rows = []

    for year, subset in data.groupby(
        "year"
    ):

        summary = calculate_summary(
            subset
        )

        rows.append(
            {
                "year": year,
                **summary,
            }
        )

    return pd.DataFrame(rows).sort_values(
        "year"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("US500 EMA19 + MACRO BACKTEST")
    print("=" * 60)

    print(
        f"Ticker: {TICKER}"
    )

    print(
        f"Start: {START_DATE}"
    )

    print(
        f"EMA: {EMA_FAST}"
    )

    print(
        f"Trend EMA: {EMA_TREND}"
    )

    print(
        f"RR: 1:{RR}"
    )

    # --------------------------------------------------------
    # MARKET DATA
    # --------------------------------------------------------

    print()
    print("Loading market data...")

    market_raw = (
        get_historical_market_data(
            ticker=TICKER,
            start_date=START_DATE
        )
    )

    if market_raw is None:
        raise RuntimeError(
            "Market data returned None."
        )

    if market_raw.empty:
        raise RuntimeError(
            "Market data is empty."
        )

    market = prepare_market_data(
        market_raw
    )

    print(
        "Market data: "
        f"{market.index.min().date()} "
        "→ "
        f"{market.index.max().date()}"
    )

    # --------------------------------------------------------
    # EMA19 SIGNALS
    # --------------------------------------------------------

    signals = detect_ema19_pullbacks(
        market
    )

    print(
        f"EMA19 Pullback signals: "
        f"{len(signals)}"
    )

    # --------------------------------------------------------
    # BASELINE BACKTEST
    # --------------------------------------------------------

    trades = build_ema19_backtest(
        market,
        signals
    )

    print(
        f"Backtest events: "
        f"{len(trades)}"
    )

    # --------------------------------------------------------
    # MACRO
    # --------------------------------------------------------

    macro_market = prepare_macro_data(
        market
    )

    if macro_market.empty:

        print()
        print(
            "WARNING: Macro data unavailable."
        )

        trades[
            "macro_regime"
        ] = "DATA UNAVAILABLE"

    else:

        trades = attach_macro_to_trades(
            trades,
            macro_market
        )

    # --------------------------------------------------------
    # OVERALL
    # --------------------------------------------------------

    summary = calculate_summary(
        trades
    )

    print()
    print("OVERALL")
    print("-" * 60)

    print(
        f"Total Signals       : "
        f"{summary['total_signals']}"
    )

    print(
        f"Valid Setups        : "
        f"{summary['valid_setups']}"
    )

    print(
        f"Resolved Trades     : "
        f"{summary['resolved_trades']}"
    )

    print(
        f"Wins                : "
        f"{summary['wins']}"
    )

    print(
        f"Losses              : "
        f"{summary['losses']}"
    )

    print(
        f"Ambiguous           : "
        f"{summary['ambiguous']}"
    )

    print(
        f"Open                : "
        f"{summary['open']}"
    )

    print(
        f"Invalid Sl          : "
        f"{summary['invalid_sl']}"
    )

    print(
        f"Win Rate Pct        : "
        f"{summary['win_rate_pct']:.3f}"
    )

    print(
        f"Average R           : "
        f"{summary['average_R']:.3f}"
    )

    print(
        f"Expectancy R        : "
        f"{summary['expectancy_R']:.3f}"
    )

    print(
        f"Total R             : "
        f"{summary['total_R']:.1f}"
    )

    print(
        f"Profit Factor       : "
        f"{summary['profit_factor']:.3f}"
    )

    # --------------------------------------------------------
    # MACRO REGIME RESULTS
    # --------------------------------------------------------

    macro_summary = (
        grouped_macro_summary(
            trades
        )
    )

    print()
    print("RESULTS BY MACRO REGIME")
    print("-" * 60)

    if macro_summary.empty:

        print(
            "No macro regime results available."
        )

    else:

        print(
            macro_summary.to_string(
                index=False,
                float_format=lambda x:
                    f"{x:.3f}"
            )
        )

    # --------------------------------------------------------
    # YEARLY RESULTS
    # --------------------------------------------------------

    yearly = yearly_macro_summary(
        trades
    )

    print()
    print("YEARLY RESULTS")
    print("-" * 60)

    if yearly.empty:

        print(
            "No yearly results."
        )

    else:

        print(
            yearly[
                [
                    "year",
                    "total_signals",
                    "resolved_trades",
                    "wins",
                    "losses",
                    "ambiguous",
                    "win_rate_pct",
                    "average_R",
                    "total_R",
                ]
            ].to_string(
                index=False,
                float_format=lambda x:
                    f"{x:.3f}"
            )
        )

    # --------------------------------------------------------
    # SAVE FILES
    # --------------------------------------------------------

    trades.to_csv(
        "backtestEMA19Macro_trades.csv",
        index=False
    )

    macro_summary.to_csv(
        "backtestEMA19Macro_regimes.csv",
        index=False
    )

    yearly.to_csv(
        "backtestEMA19Macro_yearly.csv",
        index=False
    )

    # Save aligned macro dataset for auditability
    if not macro_market.empty:

        macro_market.to_csv(
            "backtestEMA19Macro_macro_data.csv"
        )

    # Save compact summary
    pd.DataFrame(
        [summary]
    ).to_csv(
        "backtestEMA19Macro_summary.csv",
        index=False
    )

    print()
    print("FILES CREATED")
    print("-" * 60)

    print(
        "backtestEMA19Macro_trades.csv"
    )

    print(
        "backtestEMA19Macro_regimes.csv"
    )

    print(
        "backtestEMA19Macro_yearly.csv"
    )

    print(
        "backtestEMA19Macro_summary.csv"
    )

    if not macro_market.empty:

        print(
            "backtestEMA19Macro_macro_data.csv"
        )

    print()
    print(
        "EMA19 + MACRO BACKTEST COMPLETE"
    )


if __name__ == "__main__":
    main()
