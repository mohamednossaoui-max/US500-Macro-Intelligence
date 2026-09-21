import os
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


# ============================================================
# Technical Intelligence v1
# Research-only technical market intelligence layer
# ============================================================

TICKER = os.getenv("US500_TICKER", "^GSPC")
START_DATE = os.getenv("TECHNICAL_START_DATE", "2019-01-01")

OUTPUT_DIR = Path(".")

RESEARCH_OUTPUT = OUTPUT_DIR / "technical_intelligence_research_v1.csv"
SUMMARY_OUTPUT = OUTPUT_DIR / "technical_intelligence_research_summary_v1.csv"
EXTREMES_OUTPUT = OUTPUT_DIR / "technical_intelligence_extremes_v1.csv"


# ============================================================
# Helpers
# ============================================================

def fail(message: str):
    raise RuntimeError(message)


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize yfinance columns.
    Handles both normal and MultiIndex responses.
    """
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            str(col[0]).strip()
            if isinstance(col, tuple)
            else str(col).strip()
            for col in df.columns
        ]
    else:
        df.columns = [str(col).strip() for col in df.columns]

    return df


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Wilder-style RSI using exponential smoothing.
    """
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:

    previous_close = close.shift(1)

    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1
    ).max(axis=1)

    atr = true_range.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period
    ).mean()

    return atr


# ============================================================
# Download Market Data
# ============================================================

def download_market_data() -> pd.DataFrame:

    print("=" * 70)
    print("Technical Intelligence v1")
    print("=" * 70)
    print(f"Ticker: {TICKER}")
    print(f"Start date: {START_DATE}")
    print()

    print("Downloading daily market data...")

    df = yf.download(
        TICKER,
        start=START_DATE,
        interval="1d",
        auto_adjust=False,
        progress=False,
    )

    if df is None or df.empty:
        fail("No market data returned by Yahoo Finance.")

    df = flatten_columns(df)

    required_columns = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    missing = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing:
        fail(
            f"Missing required market columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )

    df = df[required_columns].copy()

    # Normalize index
    df.index = pd.to_datetime(df.index)

    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)

    df = df.sort_index()

    # Remove duplicate dates
    df = df[~df.index.duplicated(keep="last")]

    # Numeric conversion
    for column in required_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df = df.dropna(
        subset=["Open", "High", "Low", "Close"]
    )

    if df.empty:
        fail("Market data became empty after cleaning.")

    print(f"Rows downloaded: {len(df):,}")
    print(
        f"First date: {df.index.min().date()}"
    )
    print(
        f"Last date: {df.index.max().date()}"
    )

    return df


# ============================================================
# Technical Calculations
# ============================================================

def build_technical_dataset(df: pd.DataFrame) -> pd.DataFrame:

    data = df.copy()

    close = data["Close"]
    high = data["High"]
    low = data["Low"]

    # --------------------------------------------------------
    # Moving averages
    # --------------------------------------------------------

    data["SMA20"] = close.rolling(20).mean()
    data["SMA50"] = close.rolling(50).mean()
    data["SMA200"] = close.rolling(200).mean()

    data["EMA20"] = close.ewm(
        span=20,
        adjust=False
    ).mean()

    data["EMA50"] = close.ewm(
        span=50,
        adjust=False
    ).mean()

    # Distance from moving averages
    data["close_vs_SMA20_pct"] = (
        (close / data["SMA20"]) - 1
    ) * 100

    data["close_vs_SMA50_pct"] = (
        (close / data["SMA50"]) - 1
    ) * 100

    data["close_vs_SMA200_pct"] = (
        (close / data["SMA200"]) - 1
    ) * 100

    # Moving-average slopes
    data["SMA20_slope_20d_pct"] = (
        (data["SMA20"] / data["SMA20"].shift(20)) - 1
    ) * 100

    data["SMA50_slope_20d_pct"] = (
        (data["SMA50"] / data["SMA50"].shift(20)) - 1
    ) * 100

    # --------------------------------------------------------
    # Momentum
    # --------------------------------------------------------

    data["RSI14"] = calculate_rsi(
        close,
        period=14
    )

    data["ROC20_pct"] = (
        (close / close.shift(20)) - 1
    ) * 100

    # --------------------------------------------------------
    # Volatility
    # --------------------------------------------------------

    data["TR"] = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1
    ).max(axis=1)

    data["ATR14"] = calculate_atr(
        high,
        low,
        close,
        period=14
    )

    data["ATR14_pct"] = (
        data["ATR14"] / close
    ) * 100

    log_returns = np.log(
        close / close.shift(1)
    )

    data["realized_volatility_20d_pct"] = (
        log_returns.rolling(20).std()
        * np.sqrt(252)
        * 100
    )

    # --------------------------------------------------------
    # Drawdown
    # --------------------------------------------------------

    data["running_high"] = close.cummax()

    data["drawdown_pct"] = (
        (close / data["running_high"]) - 1
    ) * 100

    # Prior 252-session high/low
    data["prior_252d_high"] = (
        close.shift(1)
        .rolling(252)
        .max()
    )

    data["prior_252d_low"] = (
        close.shift(1)
        .rolling(252)
        .min()
    )

    data["from_prior_252d_high_pct"] = (
        (close / data["prior_252d_high"]) - 1
    ) * 100

    data["from_prior_252d_low_pct"] = (
        (close / data["prior_252d_low"]) - 1
    ) * 100

    # --------------------------------------------------------
    # Market Structure
    # --------------------------------------------------------

    data["prior_20d_high"] = (
        close.shift(1)
        .rolling(20)
        .max()
    )

    data["prior_20d_low"] = (
        close.shift(1)
        .rolling(20)
        .min()
    )

    data["breakout_above_prior_20d_high"] = (
        close > data["prior_20d_high"]
    )

    data["breakdown_below_prior_20d_low"] = (
        close < data["prior_20d_low"]
    )

    # --------------------------------------------------------
    # Trend Structure
    # --------------------------------------------------------

    bullish_structure = (
        (close > data["SMA50"])
        & (data["SMA50"] > data["SMA200"])
        & (data["SMA50_slope_20d_pct"] > 0)
    )

    bearish_structure = (
        (close < data["SMA50"])
        & (data["SMA50"] < data["SMA200"])
        & (data["SMA50_slope_20d_pct"] < 0)
    )

    data["trend_structure"] = np.select(
        [
            bullish_structure,
            bearish_structure,
        ],
        [
            "BULLISH_STRUCTURE",
            "BEARISH_STRUCTURE",
        ],
        default="NEUTRAL_STRUCTURE"
    )

    # --------------------------------------------------------
    # Technical Regime
    # --------------------------------------------------------

    ready = (
        data["SMA50"].notna()
        & data["SMA200"].notna()
        & data["RSI14"].notna()
        & data["ATR14"].notna()
        & data["ROC20_pct"].notna()
    )

    strong_bullish = (
        ready
        & (close > data["SMA200"])
        & (data["SMA50"] > data["SMA200"])
        & (data["SMA50_slope_20d_pct"] > 0)
        & (data["ROC20_pct"] > 0)
        & (data["RSI14"] >= 55)
    )

    bullish = (
        ready
        & (close > data["SMA200"])
        & (data["SMA50_slope_20d_pct"] >= 0)
        & (data["ROC20_pct"] >= 0)
        & ~strong_bullish
    )

    strong_bearish = (
        ready
        & (close < data["SMA200"])
        & (data["SMA50"] < data["SMA200"])
        & (data["SMA50_slope_20d_pct"] < 0)
        & (data["ROC20_pct"] < 0)
        & (data["RSI14"] <= 45)
    )

    bearish = (
        ready
        & (close < data["SMA200"])
        & (data["SMA50_slope_20d_pct"] <= 0)
        & (data["ROC20_pct"] <= 0)
        & ~strong_bearish
    )

    data["technical_regime"] = np.select(
        [
            strong_bullish,
            bullish,
            strong_bearish,
            bearish,
        ],
        [
            "STRONG_BULLISH",
            "BULLISH",
            "STRONG_BEARISH",
            "BEARISH",
        ],
        default="NEUTRAL"
    )

    data.loc[~ready, "technical_regime"] = (
        "INSUFFICIENT_DATA"
    )

    # --------------------------------------------------------
    # Research Metadata
    # --------------------------------------------------------

    data["observation_date"] = data.index.date

    data["availability_date"] = (
        pd.to_datetime(data.index)
        + pd.Timedelta(days=1)
    ).date

    data["ticker"] = TICKER

    data["source"] = (
        "Yahoo Finance via yfinance"
    )

    data["source_url"] = (
        "https://finance.yahoo.com/quote/"
        + TICKER
    )

    data["availability_semantics"] = (
        "Conservative +1 calendar-day "
        "research-safe availability proxy; "
        "not exact historical publication timestamp"
    )

    data["point_in_time_safe"] = True
    data["research_only"] = True
    data["decision_engine_ready"] = False
    data["trading_signal_generated"] = False
    data["forecast_generated"] = False
    data["technical_score_generated"] = False

    # --------------------------------------------------------
    # Final column order
    # --------------------------------------------------------

    columns = [
        "observation_date",
        "availability_date",
        "ticker",

        "Open",
        "High",
        "Low",
        "Close",
        "Volume",

        "SMA20",
        "SMA50",
        "SMA200",
        "EMA20",
        "EMA50",

        "close_vs_SMA20_pct",
        "close_vs_SMA50_pct",
        "close_vs_SMA200_pct",

        "SMA20_slope_20d_pct",
        "SMA50_slope_20d_pct",

        "RSI14",
        "ROC20_pct",

        "TR",
        "ATR14",
        "ATR14_pct",
        "realized_volatility_20d_pct",

        "running_high",
        "drawdown_pct",
        "prior_252d_high",
        "prior_252d_low",
        "from_prior_252d_high_pct",
        "from_prior_252d_low_pct",

        "prior_20d_high",
        "prior_20d_low",
        "breakout_above_prior_20d_high",
        "breakdown_below_prior_20d_low",

        "trend_structure",
        "technical_regime",

        "source",
        "source_url",
        "availability_semantics",

        "point_in_time_safe",
        "research_only",
        "decision_engine_ready",
        "trading_signal_generated",
        "forecast_generated",
        "technical_score_generated",
    ]

    return data[columns].reset_index(drop=True)


# ============================================================
# Validation
# ============================================================

def validate_output(data: pd.DataFrame):

    print()
    print("=" * 70)
    print("Validation")
    print("=" * 70)

    if data.empty:
        fail("Technical output is empty.")

    if data["observation_date"].duplicated().any():
        fail("Duplicate observation dates detected.")

    observation_dates = pd.to_datetime(
        data["observation_date"]
    )

    availability_dates = pd.to_datetime(
        data["availability_date"]
    )

    if not observation_dates.is_monotonic_increasing:
        fail("Observation dates are not sorted.")

    if not (
        availability_dates > observation_dates
    ).all():
        fail(
            "Availability date must be later "
            "than observation date."
        )

    if not data["point_in_time_safe"].eq(True).all():
        fail("PIT safety validation failed.")

    if not data["research_only"].eq(True).all():
        fail("Research-only validation failed.")

    if not data["decision_engine_ready"].eq(False).all():
        fail("Decision Engine must remain disabled.")

    if not data["trading_signal_generated"].eq(False).all():
        fail("Trading signals must not be generated.")

    if not data["forecast_generated"].eq(False).all():
        fail("Forecasts must not be generated.")

    if not data["technical_score_generated"].eq(False).all():
        fail("Technical score must not be generated.")

    rsi = data["RSI14"].dropna()

    if not rsi.empty:
        if ((rsi < 0) | (rsi > 100)).any():
            fail("RSI outside 0-100 range.")

    atr = data["ATR14"].dropna()

    if not atr.empty:
        if (atr < 0).any():
            fail("Negative ATR detected.")

    allowed_regimes = {
        "STRONG_BULLISH",
        "BULLISH",
        "NEUTRAL",
        "BEARISH",
        "STRONG_BEARISH",
        "INSUFFICIENT_DATA",
    }

    actual_regimes = set(
        data["technical_regime"].dropna().unique()
    )

    unexpected = actual_regimes - allowed_regimes

    if unexpected:
        fail(
            f"Unexpected technical regimes: {unexpected}"
        )

    print("✓ Non-empty dataset")
    print("✓ No duplicate observation dates")
    print("✓ Dates sorted")
    print("✓ Availability > observation")
    print("✓ PIT safe")
    print("✓ Research only")
    print("✓ Decision Engine disabled")
    print("✓ No trading signal")
    print("✓ No forecast")
    print("✓ No technical score")
    print("✓ RSI valid")
    print("✓ ATR valid")
    print("✓ Technical regimes valid")


# ============================================================
# Summary
# ============================================================

def create_summary(data: pd.DataFrame):

    regime_counts = (
        data["technical_regime"]
        .value_counts()
        .rename_axis("technical_regime")
        .reset_index(name="observations")
    )

    regime_counts["ticker"] = TICKER
    regime_counts["point_in_time_safe"] = True
    regime_counts["research_only"] = True
    regime_counts["decision_engine_ready"] = False
    regime_counts["trading_signal_generated"] = False
    regime_counts["forecast_generated"] = False
    regime_counts["technical_score_generated"] = False

    return regime_counts


def create_extremes(data: pd.DataFrame):

    mask = data["technical_regime"].isin(
        [
            "STRONG_BULLISH",
            "STRONG_BEARISH",
        ]
    )

    extremes = data.loc[mask].copy()

    return extremes


# ============================================================
# Main
# ============================================================

def main():

    market_data = download_market_data()

    technical_data = build_technical_dataset(
        market_data
    )

    validate_output(technical_data)

    summary = create_summary(
        technical_data
    )

    extremes = create_extremes(
        technical_data
    )

    technical_data.to_csv(
        RESEARCH_OUTPUT,
        index=False
    )

    summary.to_csv(
        SUMMARY_OUTPUT,
        index=False
    )

    extremes.to_csv(
        EXTREMES_OUTPUT,
        index=False
    )

    latest = technical_data.iloc[-1]

    print()
    print("=" * 70)
    print("Technical Intelligence v1 completed")
    print("=" * 70)

    print(
        f"Ticker: {TICKER}"
    )

    print(
        f"Observations: {len(technical_data):,}"
    )

    print(
        f"Period: "
        f"{technical_data['observation_date'].iloc[0]} "
        f"→ "
        f"{technical_data['observation_date'].iloc[-1]}"
    )

    print()
    print("Latest state:")
    print(
        f"Date: {latest['observation_date']}"
    )
    print(
        f"Close: {latest['Close']:.2f}"
    )
    print(
        f"SMA20: {latest['SMA20']:.2f}"
    )
    print(
        f"SMA50: {latest['SMA50']:.2f}"
    )
    print(
        f"SMA200: {latest['SMA200']:.2f}"
    )
    print(
        f"RSI14: {latest['RSI14']:.2f}"
    )
    print(
        f"ATR14: {latest['ATR14']:.2f}"
    )
    print(
        f"ATR14 %: {latest['ATR14_pct']:.2f}"
    )
    print(
        f"ROC20 %: {latest['ROC20_pct']:.2f}"
    )
    print(
        f"Drawdown %: {latest['drawdown_pct']:.2f}"
    )
    print(
        f"Trend structure: "
        f"{latest['trend_structure']}"
    )
    print(
        f"Technical regime: "
        f"{latest['technical_regime']}"
    )

    print()
    print("Outputs:")
    print(
        f"- {RESEARCH_OUTPUT}"
    )
    print(
        f"- {SUMMARY_OUTPUT}"
    )
    print(
        f"- {EXTREMES_OUTPUT}"
    )

    print()
    print(
        "Research-only: True"
    )
    print(
        "Decision Engine: Disabled"
    )
    print(
        "Trading Signal: False"
    )
    print(
        "Forecast: False"
    )
    print(
        "Technical Score: False"
    )


if __name__ == "__main__":
    main()
