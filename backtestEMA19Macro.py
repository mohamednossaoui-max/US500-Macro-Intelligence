import os
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore")

# ============================================================
# CONFIG
# ============================================================
START_DATE = "2019-01-01"
MARKET_TICKER = os.getenv("US500_TICKER", "^GSPC")
EMA_FAST = 19
EMA_TREND = 200
RR = 4.0
ATR_PERIOD = 14
STOP_LOOKBACK = 5
ATR_MULTIPLIER = 0.5
FRED_API_KEY = os.getenv("FRED_API_KEY", "").strip()

OUTPUT_TRADES = "backtestEMA19Macro_trades.csv"
OUTPUT_REGIMES = "backtestEMA19Macro_regimes.csv"
OUTPUT_YEARLY = "backtestEMA19Macro_yearly.csv"
OUTPUT_SUMMARY = "backtestEMA19Macro_summary.csv"
OUTPUT_MACRO = "backtestEMA19Macro_macro_data.csv"
OUTPUT_QUALITY = "backtestEMA19Macro_data_quality.csv"
OUTPUT_SIGNALS = "backtestEMA19Macro_signals.csv"

# We deliberately request extra history so YoY calculations have a full base.
MACRO_FETCH_START = "2000-01-01"

FRED_SERIES = {
    "US10Y": "DGS10",
    "US2Y": "DGS2",
    "T10Y2Y": "T10Y2Y",
    "VIX": "VIXCLS",
    "DXY": "DTWEXBGS",
    "UNRATE": "UNRATE",
    "INITIAL_CLAIMS_4W": "IC4WSA",
    "FEDFUNDS": "FEDFUNDS",
    "HY_SPREAD": "BAMLH0A0HYM2",
    "CORP_OAS": "BAMLC0A0CM",
    "NFCI": "NFCI",
    "INDPRO": "INDPRO",
    "RETAIL": "RSAFS",
    "PCE": "PCE",
    "PCEPI": "PCEPI",
    "CORE_PCE": "PCEPILFE",
}

REGIME_NAMES = {
    "A": "A â Healthy / Technical Pullback",
    "B": "B â Growth Scare / Healthy Correction",
    "C": "C â Inflation / Rates Shock",
    "D": "D â Growth + Inflation / Mixed Stress",
    "E": "E â Recession / Bear Risk",
    "F": "F â Liquidity / Financial Shock",
    "U": "U â Macro Data Insufficient",
}

# ============================================================
# MARKET DATA
# ============================================================
def get_market_data():
    print("Loading market data...")

    end_date = (pd.Timestamp.today() + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    df = yf.download(
        MARKET_TICKER,
        start=START_DATE,
        end=end_date,
        interval="1d",
        auto_adjust=False,
        progress=False,
    )

    if df.empty:
        raise RuntimeError("Market data download returned no data.")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required = ["Open", "High", "Low", "Close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(f"Missing market columns: {missing}")

    df = df[required].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.reset_index().rename(columns={"Date": "date"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce").astype("datetime64[ns]")
    df = df.dropna(subset=["date", "Close", "High", "Low"])
    df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)

    print(
        f"Market data: {df['date'].min().date()} â {df['date'].max().date()}"
    )
    return df


def atr(df, period=14):
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def prepare_market(df):
    df = df.copy()
    df["EMA19"] = df["Close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=EMA_TREND, adjust=False).mean()
    df["ATR14"] = atr(df, ATR_PERIOD)
    return df


# ============================================================
# EMA19 SIGNALS
# ============================================================
def detect_signals(df):
    """
    FINAL / BASELINE EMA19 SIGNAL ENGINE.

    Signal conditions:
      1. Close > EMA200
      2. EMA19 > EMA200
      3. Low <= EMA19
      4. Entry = signal-day Close
      5. Stop = lowest Low of the previous 5 COMPLETED candles
         minus 0.5 * ATR14 from the previous completed candle
      6. RR = 1:4

    IMPORTANT:
      Only ONE signal/trade is allowed at a time.
      After a signal is created, the engine advances to the candle
      where that trade resolves (WIN / LOSS / AMBIGUOUS), or to the
      end of the dataset if it remains OPEN.

    This is intentional: it prevents multiple overlapping EMA19
    signals from changing the original baseline.
    """

    signals = []

    start_i = max(EMA_TREND, ATR_PERIOD, STOP_LOOKBACK) + 1
    i = start_i

    while i < len(df):

        row = df.iloc[i]

        # ----------------------------------------------------
        # Basic data validation
        # ----------------------------------------------------
        if not np.isfinite(row["EMA19"]):
            i += 1
            continue

        if not np.isfinite(row["EMA200"]):
            i += 1
            continue

        if not np.isfinite(row["ATR14"]):
            i += 1
            continue

        # ----------------------------------------------------
        # EMA19 pullback condition
        # ----------------------------------------------------
        condition = (
            row["Close"] > row["EMA200"]
            and row["EMA19"] > row["EMA200"]
            and row["Low"] <= row["EMA19"]
        )

        if not condition:
            i += 1
            continue

        signal_date = row["date"]
        entry = float(row["Close"])

        # ----------------------------------------------------
        # Stop uses ONLY candles completed before signal candle
        # ----------------------------------------------------
        previous_5 = df.iloc[i - STOP_LOOKBACK:i]

        prev_low = float(previous_5["Low"].min())
        previous_atr = float(df.iloc[i - 1]["ATR14"])

        stop = prev_low - ATR_MULTIPLIER * previous_atr

        # ----------------------------------------------------
        # Invalid stop
        # ----------------------------------------------------
        if not np.isfinite(stop) or stop >= entry:

            signals.append(
                {
                    "signal_date": signal_date,
                    "entry": entry,
                    "stop": stop,
                    "risk": entry - stop,
                    "valid_sl": False,
                }
            )

            # Invalid setup is immediately released.
            i += 1
            continue

        # ----------------------------------------------------
        # Valid trade
        # ----------------------------------------------------
        risk = entry - stop
        target = entry + RR * risk

        signals.append(
            {
                "signal_date": signal_date,
                "entry": entry,
                "stop": stop,
                "risk": risk,
                "target": target,
                "valid_sl": True,
            }
        )

        # ----------------------------------------------------
        # ONE TRADE AT A TIME
        #
        # Find the first future candle that resolves the trade.
        # Same-day TP + SL = AMBIGUOUS.
        # ----------------------------------------------------
        exit_index = None

        for j in range(i + 1, len(df)):

            future_row = df.iloc[j]

            hit_tp = future_row["High"] >= target
            hit_sl = future_row["Low"] <= stop

            if hit_tp or hit_sl:
                exit_index = j
                break

        if exit_index is not None:
            # Next eligible signal is AFTER the exit candle.
            i = exit_index + 1
        else:
            # Trade remains open through the end of data.
            break

    out = pd.DataFrame(signals)

    print(f"EMA19 Pullback signals: {len(out)}")

    return out


# ============================================================
# TRADE EVALUATION
# ============================================================
def evaluate_signal(signal, market):
    signal_date = pd.Timestamp(signal["signal_date"])
    entry = float(signal["entry"])
    stop = float(signal["stop"])
    risk = float(signal["risk"])

    if not bool(signal["valid_sl"]):
        return {
            **signal,
            "target": np.nan,
            "result": "INVALID_SL",
            "exit_date": pd.NaT,
            "R": np.nan,
        }

    target = entry + RR * risk
    future = market[market["date"] > signal_date].copy()

    for _, row in future.iterrows():
        hit_tp = row["High"] >= target
        hit_sl = row["Low"] <= stop

        if hit_tp and hit_sl:
            return {
                **signal,
                "target": target,
                "result": "AMBIGUOUS",
                "exit_date": row["date"],
                "R": np.nan,
            }

        if hit_tp:
            return {
                **signal,
                "target": target,
                "result": "WIN",
                "exit_date": row["date"],
                "R": RR,
            }

        if hit_sl:
            return {
                **signal,
                "target": target,
                "result": "LOSS",
                "exit_date": row["date"],
                "R": -1.0,
            }

    return {
        **signal,
        "target": target,
        "result": "OPEN",
        "exit_date": pd.NaT,
        "R": np.nan,
    }


def build_backtest(market, signals):
    rows = []
    for _, signal in signals.iterrows():
        rows.append(evaluate_signal(signal.to_dict(), market))

    trades = pd.DataFrame(rows)
    print(f"Backtest events: {len(trades)}")
    return trades


# ============================================================
# FRED DATA
# ============================================================
def fred_series(series_id, start_date=MACRO_FETCH_START):
    if not FRED_API_KEY:
        raise RuntimeError(
            "FRED_API_KEY is missing. Add it to GitHub Actions Secrets."
        )

    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
        "sort_order": "asc",
    }

    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()

    observations = data.get("observations", [])
    if not observations:
        return pd.DataFrame(columns=["date", "value"])

    out = pd.DataFrame(observations)
    out["date"] = pd.to_datetime(out["date"], errors="coerce").astype("datetime64[ns]")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out[["date", "value"]].dropna(subset=["date", "value"])
    out = out.sort_values("date").drop_duplicates("date", keep="last")
    return out.reset_index(drop=True)


def load_macro_raw():
    print("\n" + "=" * 60)
    print("LOADING MACRO DATA")
    print("=" * 60)

    if not FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY is missing.")

    raw = {}
    for name, series_id in FRED_SERIES.items():
        try:
            print(f"  Fetching FRED API: {name} ({series_id})")
            df = fred_series(series_id)
            raw[name] = df
            print(f"    {len(df)} observations")
        except Exception as exc:
            print(f"    FAILED {name}: {exc}")
            raw[name] = pd.DataFrame(columns=["date", "value"])

    return raw


# ============================================================
# MACRO DERIVATIONS + DAILY ALIGNMENT
# ============================================================
def derive_macro_series(raw):
    """
    Derive YoY/inflation metrics BEFORE daily alignment.
    This is essential: never calculate YoY after forward-fill.
    """
    clean = {k: v.copy() for k, v in raw.items()}

    def yoy(name, output):
        if name not in clean or clean[name].empty:
            clean[output] = pd.DataFrame(columns=["date", "value"])
            return

        s = clean[name].set_index("date")["value"].sort_index()
        # Monthly series: 12 observations back.
        derived = s.pct_change(12) * 100.0
        clean[output] = derived.dropna().rename("value").reset_index()

    yoy("INDPRO", "INDPRO_YOY")
    yoy("RETAIL", "RETAIL_YOY")
    yoy("PCEPI", "PCE_INFLATION")
    yoy("CORE_PCE", "CORE_PCE_INFLATION")

    return clean


def align_one_series(market_dates, series_df):
    """
    Align each macro observation to the latest observation on/before
    each market date. merge_asof is used instead of exact-date reindexing,
    so monthly/weekly series remain available on normal trading days.
    """
    left = pd.DataFrame({"date": pd.to_datetime(market_dates).astype("datetime64[ns]")})
    right = series_df.copy()

    if right.empty:
        return pd.Series(np.nan, index=left.index, dtype=float)

    right["date"] = pd.to_datetime(right["date"], errors="coerce").astype("datetime64[ns]")
    right["value"] = pd.to_numeric(right["value"], errors="coerce")
    right = right.dropna(subset=["date", "value"])
    right = right.sort_values("date").drop_duplicates("date", keep="last")

    merged = pd.merge_asof(
        left.sort_values("date"),
        right[["date", "value"]],
        on="date",
        direction="backward",
    )

    return merged["value"].set_axis(left.sort_values("date").index)


def prepare_macro_data(market):
    print("\n" + "=" * 60)
    print("PREPARING MACRO DATA")
    print("=" * 60)

    raw = load_macro_raw()
    clean = derive_macro_series(raw)

    result = market.copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce").astype("datetime64[ns]")
    result = result.sort_values("date").reset_index(drop=True)

    for name, series_df in clean.items():
        result[name] = align_one_series(result["date"], series_df).to_numpy()

    # Regime classification after all series have been aligned.
    result["macro_regime"] = result.apply(classify_macro_regime, axis=1)

    # Early warning is also calculated daily.
    result = calculate_early_warning(result)

    # Data quality.
    quality = []
    total = len(result)
    for col in list(FRED_SERIES.keys()) + [
        "INDPRO_YOY",
        "RETAIL_YOY",
        "PCE_INFLATION",
        "CORE_PCE_INFLATION",
    ]:
        available = int(result[col].notna().sum()) if col in result.columns else 0
        quality.append(
            {
                "series": col,
                "available_rows": available,
                "total_market_rows": total,
                "coverage_pct": (available / total * 100.0) if total else 0.0,
            }
        )

    quality_df = pd.DataFrame(quality)
    quality_df.to_csv(OUTPUT_QUALITY, index=False)

    print("\nMACRO DATA QUALITY")
    print("-" * 60)
    print(quality_df.to_string(index=False))

    return result, quality_df


# ============================================================
# MACRO REGIME CLASSIFICATION
# ============================================================
def classify_macro_regime(row):
    """
    Mechanical A-F regime classification.

    F = liquidity/financial shock
    E = recession/bear risk
    C/D = inflation/rates pressure
    B = growth scare with contained inflation
    A = healthy/technical pullback
    U = insufficient macro data

    Important: U prevents missing data from silently becoming A.
    """
    required_for_core = [
        "VIX",
        "HY_SPREAD",
        "CORP_OAS",
        "NFCI",
        "UNRATE",
        "INITIAL_CLAIMS_4W",
        "INDPRO_YOY",
        "RETAIL_YOY",
        "PCE_INFLATION",
        "CORE_PCE_INFLATION",
        "T10Y2Y",
        "US10Y",
        "US2Y",
        "FEDFUNDS",
    ]

    available_core = sum(
        pd.notna(row.get(col, np.nan)) for col in required_for_core
    )

    # If too much macro information is missing, do not call it healthy.
    if available_core < 8:
        return REGIME_NAMES["U"]

    vix = row.get("VIX", np.nan)
    hy = row.get("HY_SPREAD", np.nan)
    corp = row.get("CORP_OAS", np.nan)
    nfci = row.get("NFCI", np.nan)

    # ---------------- F: liquidity / financial shock ----------------
    if (
        (pd.notna(vix) and vix >= 35)
        or (pd.notna(hy) and hy >= 6)
        or (pd.notna(corp) and corp >= 3.5)
        or (pd.notna(nfci) and nfci >= 1.0)
    ):
        return REGIME_NAMES["F"]

    unemployment = row.get("UNRATE", np.nan)
    claims = row.get("INITIAL_CLAIMS_4W", np.nan)
    indpro_yoy = row.get("INDPRO_YOY", np.nan)
    retail_yoy = row.get("RETAIL_YOY", np.nan)
    curve = row.get("T10Y2Y", np.nan)

    recession_score = 0
    recession_score += int(pd.notna(unemployment) and unemployment >= 5.0)
    recession_score += int(pd.notna(claims) and claims >= 300000)
    recession_score += int(pd.notna(indpro_yoy) and indpro_yoy < 0)
    recession_score += int(pd.notna(retail_yoy) and retail_yoy < 0)
    recession_score += int(pd.notna(curve) and curve < -0.50)

    # ---------------- E: recession / bear risk ----------------
    if recession_score >= 3:
        return REGIME_NAMES["E"]

    pce = row.get("PCE_INFLATION", np.nan)
    core_pce = row.get("CORE_PCE_INFLATION", np.nan)
    us10y = row.get("US10Y", np.nan)
    us2y = row.get("US2Y", np.nan)
    fedfunds = row.get("FEDFUNDS", np.nan)

    inflation_score = 0
    inflation_score += int(pd.notna(pce) and pce >= 3.0)
    inflation_score += int(pd.notna(core_pce) and core_pce >= 3.0)
    inflation_score += int(pd.notna(us10y) and us10y >= 4.5)
    inflation_score += int(pd.notna(us2y) and us2y >= 4.5)
    inflation_score += int(pd.notna(fedfunds) and fedfunds >= 4.5)

    growth_weak = 0
    growth_weak += int(pd.notna(indpro_yoy) and indpro_yoy < 0)
    growth_weak += int(pd.notna(retail_yoy) and retail_yoy < 0)
    growth_weak += int(pd.notna(unemployment) and unemployment >= 4.5)
    growth_weak += int(pd.notna(claims) and claims >= 275000)

    # ---------------- C / D ----------------
    if inflation_score >= 3:
        if growth_weak >= 2:
            return REGIME_NAMES["D"]
        return REGIME_NAMES["C"]

    # ---------------- B ----------------
    if growth_weak >= 2:
        return REGIME_NAMES["B"]

    # ---------------- A ----------------
    return REGIME_NAMES["A"]


# ============================================================
# EARLY WARNING
# ============================================================
def calculate_early_warning(df):
    """
    Daily leading-risk score 0-100.
    Category maxima:
      Credit 20
      Labor 20
      Yield Curve 15
      Financial Conditions 20
      Market 15
      Macro Momentum 10
    """
    df = df.copy()

    # Changes / pct changes are calculated on the aligned daily data.
    hy_pct_60 = df["HY_SPREAD"].pct_change(60) * 100 if "HY_SPREAD" in df else np.nan
    corp_pct_60 = df["CORP_OAS"].pct_change(60) * 100 if "CORP_OAS" in df else np.nan
    claims_pct_12 = df["INITIAL_CLAIMS_4W"].pct_change(12) * 100 if "INITIAL_CLAIMS_4W" in df else np.nan
    curve_delta_60 = df["T10Y2Y"].diff(60) if "T10Y2Y" in df else np.nan
    nfci_delta_4 = df["NFCI"].diff(4) if "NFCI" in df else np.nan
    vix_pct_20 = df["VIX"].pct_change(20) * 100 if "VIX" in df else np.nan
    dxy_pct_60 = df["DXY"].pct_change(60) * 100 if "DXY" in df else np.nan

    scores = []

    for i in range(len(df)):
        row = df.iloc[i]
        credit = 0
        labor = 0
        curve = 0
        financial = 0
        market = 0
        momentum = 0

        hy = row.get("HY_SPREAD", np.nan)
        corp = row.get("CORP_OAS", np.nan)
        if pd.notna(hy):
            if hy >= 6: credit += 12
            elif hy >= 5: credit += 9
            elif hy >= 4: credit += 5
        if pd.notna(hy_pct_60.iloc[i]):
            x = hy_pct_60.iloc[i]
            if x >= 30: credit += 8
            elif x >= 15: credit += 5
            elif x >= 8: credit += 3
        if pd.notna(corp):
            if corp >= 3: credit += 5
            elif corp >= 2.5: credit += 3
        credit = min(credit, 20)

        claims = row.get("INITIAL_CLAIMS_4W", np.nan)
        unrate = row.get("UNRATE", np.nan)
        if pd.notna(claims_pct_12.iloc[i]):
            x = claims_pct_12.iloc[i]
            if x >= 8: labor += 12
            elif x >= 5: labor += 8
            elif x >= 3: labor += 4
        if pd.notna(unrate) and i >= 3:
            delta = unrate - df.iloc[i - 3].get("UNRATE", np.nan)
            if pd.notna(delta):
                if delta >= 0.2: labor += 8
                elif delta >= 0.1: labor += 4
        labor = min(labor, 20)

        curve_val = row.get("T10Y2Y", np.nan)
        if pd.notna(curve_val):
            if curve_val < -0.50: curve += 10
            elif curve_val < 0: curve += 7
        if pd.notna(curve_delta_60.iloc[i]):
            x = curve_delta_60.iloc[i]
            if x <= -0.50: curve += 5
            elif x <= -0.25: curve += 3
        curve = min(curve, 15)

        nfci = row.get("NFCI", np.nan)
        if pd.notna(nfci):
            if nfci >= 1: financial += 12
            elif nfci >= 0.5: financial += 8
            elif nfci > 0: financial += 4
        if pd.notna(nfci_delta_4.iloc[i]):
            x = nfci_delta_4.iloc[i]
            if x >= 0.30: financial += 8
            elif x >= 0.15: financial += 5
            elif x >= 0.08: financial += 2
        financial = min(financial, 20)

        vix = row.get("VIX", np.nan)
        dxy = row.get("DXY", np.nan)
        if pd.notna(vix):
            if vix >= 35: market += 15
            elif vix >= 30: market += 10
            elif vix >= 25: market += 6
            elif vix >= 20: market += 3
        if pd.notna(vix_pct_20.iloc[i]):
            x = vix_pct_20.iloc[i]
            if x >= 50: market += 5
            elif x >= 25: market += 3
        if pd.notna(dxy_pct_60.iloc[i]):
            x = dxy_pct_60.iloc[i]
            if x >= 8: market += 3
            elif x >= 5: market += 2
        market = min(market, 15)

        indpro = row.get("INDPRO_YOY", np.nan)
        retail = row.get("RETAIL_YOY", np.nan)
        pce = row.get("PCE_INFLATION", np.nan)
        if pd.notna(indpro) and i >= 3:
            if indpro < df.iloc[i - 3].get("INDPRO_YOY", indpro):
                momentum += 3
        if pd.notna(retail) and i >= 3:
            if retail < df.iloc[i - 3].get("RETAIL_YOY", retail):
                momentum += 3
        if pd.notna(pce) and i >= 3:
            if pce > df.iloc[i - 3].get("PCE_INFLATION", pce):
                momentum += 4
        momentum = min(momentum, 10)

        total = credit + labor + curve + financial + market + momentum
        if total <= 24:
            level = "LOW"
        elif total <= 49:
            level = "MODERATE"
        elif total <= 74:
            level = "HIGH"
        else:
            level = "CRITICAL"

        scores.append((total, level, credit, labor, curve, financial, market, momentum))

    cols = [
        "early_warning_score",
        "early_warning_level",
        "ew_credit",
        "ew_labor",
        "ew_yield_curve",
        "ew_financial",
        "ew_market",
        "ew_macro_momentum",
    ]
    score_df = pd.DataFrame(scores, columns=cols, index=df.index)
    return pd.concat([df, score_df], axis=1)


# ============================================================
# ATTACH MACRO TO TRADES
# ============================================================
def attach_macro_to_trades(trades, macro_daily):
    trades = trades.copy()
    macro = macro_daily.copy()

    trades["signal_date"] = pd.to_datetime(trades["signal_date"], errors="coerce").astype("datetime64[ns]")
    macro["date"] = pd.to_datetime(macro["date"], errors="coerce").astype("datetime64[ns]")

    macro_cols = [
        "macro_regime",
        "VIX",
        "US10Y",
        "US2Y",
        "T10Y2Y",
        "DXY",
        "UNRATE",
        "INITIAL_CLAIMS_4W",
        "HY_SPREAD",
        "CORP_OAS",
        "NFCI",
        "INDPRO_YOY",
        "RETAIL_YOY",
        "PCE_INFLATION",
        "CORE_PCE_INFLATION",
        "FEDFUNDS",
        "early_warning_score",
        "early_warning_level",
    ]

    available = [c for c in macro_cols if c in macro.columns]
    right = macro[["date"] + available].sort_values("date")
    left = trades.sort_values("signal_date").copy()

    merged = pd.merge_asof(
        left,
        right,
        left_on="signal_date",
        right_on="date",
        direction="backward",
    )

    merged = merged.drop(columns=["date"], errors="ignore")
    return merged.sort_values("signal_date").reset_index(drop=True)


# ============================================================
# SUMMARIES
# ============================================================
def summarize_trades(trades):
    total = len(trades)
    valid = int((trades["result"] != "INVALID_SL").sum())
    resolved = int(trades["result"].isin(["WIN", "LOSS", "AMBIGUOUS"]).sum())
    wins = int((trades["result"] == "WIN").sum())
    losses = int((trades["result"] == "LOSS").sum())
    ambiguous = int((trades["result"] == "AMBIGUOUS").sum())
    open_trades = int((trades["result"] == "OPEN").sum())
    invalid_sl = int((trades["result"] == "INVALID_SL").sum())

    resolved_non_amb = int(trades["result"].isin(["WIN", "LOSS"]).sum())
    win_rate = wins / resolved_non_amb * 100 if resolved_non_amb else np.nan

    r_values = trades.loc[trades["result"].isin(["WIN", "LOSS"]), "R"].dropna()
    average_r = float(r_values.mean()) if len(r_values) else np.nan
    total_r = float(r_values.sum()) if len(r_values) else np.nan
    expectancy = average_r

    gross_profit = float(r_values[r_values > 0].sum()) if len(r_values) else 0.0
    gross_loss = float(-r_values[r_values < 0].sum()) if len(r_values) else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf

    return {
        "total_signals": total,
        "valid_setups": valid,
        "resolved_trades": resolved,
        "wins": wins,
        "losses": losses,
        "ambiguous": ambiguous,
        "open": open_trades,
        "invalid_sl": invalid_sl,
        "win_rate_pct": win_rate,
        "average_R": average_r,
        "expectancy_R": expectancy,
        "total_R": total_r,
        "profit_factor": profit_factor,
    }


def grouped_summary(trades, group_col):
    rows = []
    for key, g in trades.groupby(group_col, dropna=False):
        s = summarize_trades(g)
        s[group_col] = key
        rows.append(s)

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows)
    return out[[group_col] + [c for c in s.keys()]]


# ============================================================
# MAIN
# ============================================================
def main():
    print("\nUS500 EMA19 + MACRO BACKTEST")
    print("Signal engine: NON-OVERLAPPING / ONE TRADE AT A TIME")
    print("Macro alignment: latest observation on/before each market day")
    print("NOTE: This is NOT yet a release-date/vintage backtest.")
    print("=" * 60)
    print(f"Ticker: {MARKET_TICKER}")
    print(f"Start: {START_DATE}")
    print(f"EMA: {EMA_FAST}")
    print(f"Trend EMA: {EMA_TREND}")
    print(f"RR: 1:{RR}")

    market = get_market_data()
    market = prepare_market(market)

    signals = detect_signals(market)
    signals.to_csv(OUTPUT_SIGNALS, index=False)

    trades = build_backtest(market, signals)

    # Macro data is prepared independently from trade results.
    macro_daily, quality = prepare_macro_data(market)
    macro_daily.to_csv(OUTPUT_MACRO, index=False)

    trades = attach_macro_to_trades(trades, macro_daily)
    trades.to_csv(OUTPUT_TRADES, index=False)

    overall = summarize_trades(trades)
    pd.DataFrame([overall]).to_csv(OUTPUT_SUMMARY, index=False)

    regime = grouped_summary(trades, "macro_regime")
    regime.to_csv(OUTPUT_REGIMES, index=False)

    trades["year"] = pd.to_datetime(trades["signal_date"]).dt.year
    yearly = grouped_summary(trades, "year")
    yearly.to_csv(OUTPUT_YEARLY, index=False)

    print("\n" + "=" * 60)
    print("OVERALL")
    print("=" * 60)
    print(pd.DataFrame([overall]).to_string(index=False))

    print("\nRESULTS BY MACRO REGIME")
    print("=" * 60)
    if regime.empty:
        print("No regime results.")
    else:
        print(regime.to_string(index=False))

    print("\nYEARLY RESULTS")
    print("=" * 60)
    print(yearly.to_string(index=False))

    print("\nMACRO REGIME COUNTS")
    print("=" * 60)
    print(
        trades["macro_regime"]
        .value_counts(dropna=False)
        .rename_axis("macro_regime")
        .reset_index(name="signals")
        .to_string(index=False)
    )

    print("\nFILES CREATED")
    print("=" * 60)
    for f in [
        OUTPUT_TRADES,
        OUTPUT_REGIMES,
        OUTPUT_YEARLY,
        OUTPUT_SUMMARY,
        OUTPUT_MACRO,
        OUTPUT_QUALITY,
        OUTPUT_SIGNALS,
    ]:
        print(f)

    print("\nEMA19 + MACRO BACKTEST COMPLETE")


if __name__ == "__main__":
    main()
