# ============================================================
# US500 MACRO BACKTEST V1
# FROZEN EMA19 BASELINE + HISTORICAL MACRO REGIME
# ============================================================
#
# IMPORTANT:
# The EMA19 signal engine below is intentionally frozen to the
# configuration that reproduced the historical baseline:
#
# ATR       : Wilder ATR(14)
# Condition : Close > EMA19, Low <= EMA19,
#             Close > EMA200, EMA19 > EMA200
# Spacing   : ROW_GAP_1
# Position  : OVERLAP
# Stop      : lowest Low of previous 5 completed candles
#             - 0.5 * previous completed ATR(14)
# RR        : 1:4
#
# Baseline reference:
# 119 signals / 117 valid / 2 invalid SL
# 109 resolved / 36 wins / 73 losses / 3 ambiguous / 5 open
# +71R / PF ~= 1.973
#
# MACRO V1 PURPOSE:
# Do NOT change the trades.
# Attach a historical macro regime to every baseline signal and
# compare the unchanged baseline performance by regime.
#
# NO LOOK-AHEAD APPROXIMATION:
# - Daily FRED series use observations available on/before signal date.
# - Monthly macro series are lagged by one calendar month before use.
# - No future market prices are used for the macro classification.
#
# FRED_API_KEY must be supplied through the environment/GitHub Secret.
# Never hard-code the key in this file.
# ============================================================

import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore")

TICKER = "^GSPC"
START_DATE = "2019-01-01"
RR = 4.0
EMA19 = 19
EMA200 = 200
ATR14 = 14
LOW_LOOKBACK = 5

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

FRED_SERIES = {
    "US10Y": "DGS10",
    "US2Y": "DGS2",
    "T10Y2Y": "T10Y2Y",
    "VIX": "VIXCLS",
    "DXY": "DTWEXBGS",
    "UNRATE": "UNRATE",
    "INITIAL_CLAIMS_4W": "IC4WSA",
    "HY_SPREAD": "BAMLH0A0HYM2",
    "CORP_OAS": "BAMLC0A0CM",
    "NFCI": "NFCI",
    "INDPRO": "INDPRO",
    "RETAIL": "RSAFS",
    "PCE": "PCE",
    "CORE_PCE": "PCEPILFE",
    "FEDFUNDS": "FEDFUNDS",
}

# Monthly series are deliberately lagged one month for the regime snapshot.
MONTHLY_SERIES = {
    "UNRATE",
    "INDPRO",
    "RETAIL",
    "PCE",
    "CORE_PCE",
    "FEDFUNDS",
}

DAILY_SERIES = set(FRED_SERIES) - MONTHLY_SERIES


# ============================================================
# MARKET DATA â FROZEN BASELINE
# ============================================================

def load_market():
    df = yf.download(
        TICKER,
        start=START_DATE,
        auto_adjust=False,
        progress=False,
    )

    if df.empty:
        raise RuntimeError("Yahoo Finance returned no market data.")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Open", "High", "Low", "Close"]].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.sort_index().dropna()

    for c in ["Open", "High", "Low", "Close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df.dropna(inplace=True)

    df["EMA19"] = df["Close"].ewm(
        span=EMA19,
        adjust=False,
        min_periods=EMA19,
    ).mean()

    df["EMA200"] = df["Close"].ewm(
        span=EMA200,
        adjust=False,
        min_periods=EMA200,
    ).mean()

    previous_close = df["Close"].shift(1)

    tr = pd.concat(
        [
            df["High"] - df["Low"],
            (df["High"] - previous_close).abs(),
            (df["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["TR"] = tr

    # Wilder ATR(14): this is the version that reproduced the
    # historical baseline reference.
    df["ATR14_WILDER"] = tr.ewm(
        alpha=1 / ATR14,
        adjust=False,
        min_periods=ATR14,
    ).mean()

    return df


# ============================================================
# FROZEN SIGNAL ENGINE
# ============================================================

def build_baseline_signals(df):
    raw = []

    for i in range(len(df)):
        row = df.iloc[i]

        if not (
            pd.notna(row["EMA19"])
            and pd.notna(row["EMA200"])
        ):
            continue

        # Exact baseline condition.
        if not (
            row["Close"] > row["EMA200"]
            and row["EMA19"] > row["EMA200"]
            and row["Low"] <= row["EMA19"]
            and row["Close"] > row["EMA19"]
        ):
            continue

        raw.append(i)

    # Exact spacing reproduced by V3.
    # ROW_GAP_1 means the current qualifying candle must be more
    # than one market row after the previous qualifying candle.
    selected = []

    for p, i in enumerate(raw):
        if p == 0 or raw[p] - raw[p - 1] > 1:
            selected.append(i)

    return selected


def baseline_stop(df, i):
    if i < LOW_LOOKBACK + 1:
        return np.nan

    previous_5 = df.iloc[i - LOW_LOOKBACK:i]
    previous_atr = df.iloc[i - 1]["ATR14_WILDER"]

    if pd.isna(previous_atr):
        return np.nan

    return float(
        previous_5["Low"].min() - 0.5 * previous_atr
    )


def resolve_trade(df, entry_i, entry, stop):
    if not np.isfinite(stop) or stop >= entry:
        return "INVALID_SL", np.nan, None

    risk = entry - stop
    target = entry + RR * risk

    for j in range(entry_i + 1, len(df)):
        high = float(df.iloc[j]["High"])
        low = float(df.iloc[j]["Low"])

        hit_tp = high >= target
        hit_sl = low <= stop

        if hit_tp and hit_sl:
            return "AMBIGUOUS", np.nan, j

        if hit_tp:
            return "WIN", RR, j

        if hit_sl:
            return "LOSS", -1.0, j

    return "OPEN", np.nan, None


def build_baseline_trades(df):
    signal_indices = build_baseline_signals(df)
    rows = []

    for i in signal_indices:
        entry = float(df.iloc[i]["Close"])
        stop = baseline_stop(df, i)
        result, r_mult, exit_i = resolve_trade(
            df, i, entry, stop
        )

        rows.append(
            {
                "signal_date": df.index[i],
                "year": int(df.index[i].year),
                "signal_index": i,
                "entry": entry,
                "stop": stop,
                "risk_points": entry - stop
                if np.isfinite(stop)
                else np.nan,
                "target": (
                    entry + RR * (entry - stop)
                    if np.isfinite(stop) and stop < entry
                    else np.nan
                ),
                "result": result,
                "R": r_mult,
                "exit_date": (
                    df.index[exit_i]
                    if exit_i is not None
                    else pd.NaT
                ),
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# FRED DATA
# ============================================================

def get_fred_key():
    key = os.getenv("FRED_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "FRED_API_KEY is missing. Add it as a GitHub Actions "
            "secret/environment variable; do not put the key in code."
        )
    return key


def fred_series(series_id, api_key):
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": START_DATE,
        "observation_end": pd.Timestamp.today().strftime("%Y-%m-%d"),
    }

    response = requests.get(
        FRED_URL,
        params=params,
        timeout=30,
    )
    response.raise_for_status()

    payload = response.json()
    observations = payload.get("observations", [])

    if not observations:
        return pd.Series(dtype=float, name=series_id)

    rows = []

    for obs in observations:
        value = obs.get("value", ".")

        if value in (".", "", None):
            continue

        try:
            value = float(value)
        except (TypeError, ValueError):
            continue

        rows.append(
            (
                pd.to_datetime(obs["date"]),
                value,
            )
        )

    if not rows:
        return pd.Series(dtype=float, name=series_id)

    s = pd.Series(
        data=[v for _, v in rows],
        index=[d for d, _ in rows],
        name=series_id,
    )

    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s.sort_index()


def load_fred():
    key = get_fred_key()
    data = {}

    print()
    print("=" * 72)
    print("LOADING FRED MACRO DATA")
    print("=" * 72)

    for name, series_id in FRED_SERIES.items():
        try:
            s = fred_series(series_id, key)
            data[name] = s

            print(
                f"{name:20s} {series_id:16s} "
                f"{len(s):5d} observations"
            )
        except Exception as exc:
            print(
                f"{name:20s} {series_id:16s} "
                f"ERROR: {exc}"
            )
            data[name] = pd.Series(dtype=float, name=series_id)

    return data


# ============================================================
# MACRO TRANSFORMATIONS
# ============================================================

def value_asof(series, date, monthly=False):
    if series is None or series.empty:
        return np.nan

    d = pd.Timestamp(date)

    if monthly:
        # Only use data through the PREVIOUS calendar month.
        # This avoids treating a current-month monthly observation
        # as known on an arbitrary date inside that month.
        cutoff = d.to_period("M").start_time - pd.Timedelta(days=1)
    else:
        cutoff = d

    s = series.loc[series.index <= cutoff]

    if s.empty:
        return np.nan

    return float(s.iloc[-1])


def pct_change_asof(series, date, periods, monthly=False):
    if series is None or series.empty:
        return np.nan

    d = pd.Timestamp(date)

    if monthly:
        cutoff = d.to_period("M").start_time - pd.Timedelta(days=1)
    else:
        cutoff = d

    s = series.loc[series.index <= cutoff].dropna()

    if len(s) <= periods:
        return np.nan

    current = float(s.iloc[-1])
    previous = float(s.iloc[-1 - periods])

    if previous == 0:
        return np.nan

    return (current / previous - 1.0) * 100.0


def inflation_yoy(series, date):
    # CORE_PCE and PCE are price indexes, not rates.
    return pct_change_asof(
        series, date, periods=12, monthly=True
    )


# ============================================================
# MACRO REGIME
# ============================================================

def classify_macro(fred, date):
    """
    Transparent research classification.

    A = Healthy / Technical Pullback
    B = Growth Scare / Healthy Correction
    C = Inflation / Rates Shock
    D = Growth + Inflation / Mixed Stress
    E = Recession / Bear Risk
    F = Liquidity / Financial Shock

    This is intentionally descriptive and independent from the
    trading decision engine. No trade is added/removed here.
    """

    us10y = value_asof(fred["US10Y"], date)
    us2y = value_asof(fred["US2Y"], date)
    curve = value_asof(fred["T10Y2Y"], date)
    vix = value_asof(fred["VIX"], date)
    dxy = value_asof(fred["DXY"], date)

    unrate = value_asof(
        fred["UNRATE"], date, monthly=True
    )
    claims = value_asof(
        fred["INITIAL_CLAIMS_4W"], date, monthly=False
    )
    hy = value_asof(
        fred["HY_SPREAD"], date, monthly=False
    )
    corp = value_asof(
        fred["CORP_OAS"], date, monthly=False
    )
    nfci = value_asof(
        fred["NFCI"], date, monthly=False
    )

    indpro_yoy = pct_change_asof(
        fred["INDPRO"], date, 12, monthly=True
    )
    retail_yoy = pct_change_asof(
        fred["RETAIL"], date, 12, monthly=True
    )
    pce_yoy = inflation_yoy(fred["PCE"], date)
    core_pce_yoy = inflation_yoy(
        fred["CORE_PCE"], date
    )

    # --------------------------------------------------------
    # Stress flags
    # --------------------------------------------------------

    financial_stress = 0

    if np.isfinite(vix):
        if vix >= 35:
            financial_stress += 3
        elif vix >= 30:
            financial_stress += 2
        elif vix >= 25:
            financial_stress += 1

    if np.isfinite(hy):
        if hy >= 6:
            financial_stress += 2
        elif hy >= 5:
            financial_stress += 1

    if np.isfinite(corp):
        if corp >= 3:
            financial_stress += 1

    if np.isfinite(nfci):
        if nfci >= 1:
            financial_stress += 2
        elif nfci >= 0.5:
            financial_stress += 1

    # F is reserved for clearly elevated financial/liquidity stress.
    if financial_stress >= 5:
        regime = "F"
    else:
        growth_stress = 0
        inflation_stress = 0

        # Growth
        if np.isfinite(indpro_yoy) and indpro_yoy < 0:
            growth_stress += 1

        if np.isfinite(retail_yoy) and retail_yoy < 0:
            growth_stress += 1

        if np.isfinite(unrate) and unrate >= 5:
            growth_stress += 2
        elif np.isfinite(unrate) and unrate >= 4.5:
            growth_stress += 1

        # Claims level is difficult to compare across decades,
        # so use its 12-observation momentum.
        claims_change = pct_change_asof(
            fred["INITIAL_CLAIMS_4W"],
            date,
            12,
            monthly=False,
        )

        if np.isfinite(claims_change):
            if claims_change >= 15:
                growth_stress += 2
            elif claims_change >= 8:
                growth_stress += 1

        # Inflation
        if np.isfinite(core_pce_yoy):
            if core_pce_yoy >= 3.5:
                inflation_stress += 2
            elif core_pce_yoy >= 3:
                inflation_stress += 1

        if np.isfinite(pce_yoy) and pce_yoy >= 4:
            inflation_stress += 1

        # Rates pressure
        rates_stress = 0

        if np.isfinite(us10y):
            if us10y >= 5:
                rates_stress += 2
            elif us10y >= 4.5:
                rates_stress += 1

        if np.isfinite(curve) and curve < -0.5:
            growth_stress += 1

        # Regime mapping
        if growth_stress >= 3 and inflation_stress >= 2:
            regime = "D"
        elif growth_stress >= 3:
            regime = "E"
        elif inflation_stress >= 2 and rates_stress >= 1:
            regime = "C"
        elif growth_stress >= 1 and inflation_stress == 0:
            regime = "B"
        elif inflation_stress >= 1 or rates_stress >= 1:
            regime = "C"
        else:
            regime = "A"

    return {
        "macro_regime": regime,
        "US10Y": us10y,
        "US2Y": us2y,
        "T10Y2Y": curve,
        "VIX": vix,
        "DXY": dxy,
        "UNRATE": unrate,
        "INITIAL_CLAIMS_4W": claims,
        "HY_SPREAD": hy,
        "CORP_OAS": corp,
        "NFCI": nfci,
        "INDPRO_YOY": indpro_yoy,
        "RETAIL_YOY": retail_yoy,
        "PCE_YOY": pce_yoy,
        "CORE_PCE_YOY": core_pce_yoy,
    }


# ============================================================
# MACRO ATTACHMENT
# ============================================================

def attach_macro(trades, fred):
    rows = []

    for _, trade in trades.iterrows():
        snap = classify_macro(
            fred,
            trade["signal_date"],
        )

        row = trade.to_dict()
        row.update(snap)
        rows.append(row)

    return pd.DataFrame(rows)


# ============================================================
# REPORTING
# ============================================================

def summarize_group(g):
    wins = int((g["result"] == "WIN").sum())
    losses = int((g["result"] == "LOSS").sum())
    ambiguous = int(
        (g["result"] == "AMBIGUOUS").sum()
    )
    open_trades = int(
        (g["result"] == "OPEN").sum()
    )
    invalid = int(
        (g["result"] == "INVALID_SL").sum()
    )
    resolved = wins + losses
    total_r = float(g["R"].dropna().sum())

    gross_profit = float(
        g.loc[g["R"] > 0, "R"].sum()
    )
    gross_loss = abs(float(
        g.loc[g["R"] < 0, "R"].sum()
    ))

    pf = (
        gross_profit / gross_loss
        if gross_loss > 0
        else np.nan
    )

    return {
        "signals": len(g),
        "valid": len(g) - invalid,
        "invalid_sl": invalid,
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "ambiguous": ambiguous,
        "open": open_trades,
        "win_rate": (
            100 * wins / resolved
            if resolved else np.nan
        ),
        "avg_R": (
            float(g["R"].dropna().mean())
            if g["R"].notna().any()
            else np.nan
        ),
        "total_R": total_r,
        "profit_factor": pf,
    }


def regime_report(trades):
    rows = []

    for regime, g in trades.groupby(
        "macro_regime", dropna=False
    ):
        s = summarize_group(g)
        s["macro_regime"] = regime
        rows.append(s)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values(
        "macro_regime"
    )


def level_report(trades):
    """
    The baseline signal engine does not use fixed drawdown
    levels for entry. This report calculates the drawdown from
    the running market high on each signal date so the macro
    layer can later be combined with the pullback framework.
    """
    market = trades.copy()

    # Reference high before/including signal date.
    # This is descriptive, not a new entry rule.
    # Reconstructing from signal entry only would not be enough,
    # so the main() function supplies drawdown separately.
    return market


def add_drawdown(trades, market):
    running_high = market["High"].cummax()

    rows = []

    for _, trade in trades.iterrows():
        d = trade["signal_date"]

        if d not in running_high.index:
            dd = np.nan
            ref_high = np.nan
        else:
            ref_high = float(running_high.loc[d])
            dd = (
                (float(trade["entry"]) / ref_high - 1)
                * 100
                if ref_high > 0
                else np.nan
            )

        row = trade.to_dict()
        row["reference_high"] = ref_high
        row["drawdown_pct"] = dd
        rows.append(row)

    return pd.DataFrame(rows)


def print_baseline_check(trades):
    s = summarize_group(trades)

    print()
    print("=" * 72)
    print("FROZEN BASELINE CHECK")
    print("=" * 72)

    for key in [
        "signals", "valid", "invalid_sl", "resolved",
        "wins", "losses", "ambiguous", "open",
        "win_rate", "avg_R", "total_R",
        "profit_factor",
    ]:
        print(f"{key:18s}: {s[key]}")

    print()
    print("Expected:")
    print("signals=119")
    print("valid=117")
    print("invalid_sl=2")
    print("resolved=109")
    print("wins=36")
    print("losses=73")
    print("ambiguous=3")
    print("open=5")
    print("total_R=71")
    print("profit_factor~=1.973")


def main():
    market = load_market()

    print(
        f"Market rows: {len(market)} | "
        f"{market.index.min().date()} -> "
        f"{market.index.max().date()}"
    )

    baseline = build_baseline_trades(market)

    # This must remain unchanged before macro analysis.
    print_baseline_check(baseline)

    fred = load_fred()

    trades = attach_macro(baseline, fred)
    trades = add_drawdown(trades, market)

    # --------------------------------------------------------
    # REGIME REPORT
    # --------------------------------------------------------

    report = regime_report(trades)

    print()
    print("=" * 72)
    print("MACRO REGIME BACKTEST V1")
    print("=" * 72)

    if report.empty:
        print("No regime classifications available.")
    else:
        print(
            report[
                [
                    "macro_regime",
                    "signals",
                    "valid",
                    "invalid_sl",
                    "resolved",
                    "wins",
                    "losses",
                    "ambiguous",
                    "open",
                    "win_rate",
                    "avg_R",
                    "total_R",
                    "profit_factor",
                ]
            ].to_string(index=False)
        )

    # --------------------------------------------------------
    # DRAWDOWN x REGIME
    # --------------------------------------------------------

    trades["drawdown_bucket"] = pd.cut(
        trades["drawdown_pct"],
        bins=[-np.inf, -20, -10, -5, -3, 0, np.inf],
        labels=[
            "<=-20%",
            "-20% to -10%",
            "-10% to -5%",
            "-5% to -3%",
            "-3% to 0%",
            ">0%",
        ],
        right=True,
    )

    dd_report = []

    for (regime, bucket), g in trades.groupby(
        ["macro_regime", "drawdown_bucket"],
        observed=False,
    ):
        if len(g) == 0:
            continue

        s = summarize_group(g)
        s["macro_regime"] = regime
        s["drawdown_bucket"] = str(bucket)
        dd_report.append(s)

    dd_report = (
        pd.DataFrame(dd_report)
        if dd_report
        else pd.DataFrame()
    )

    print()
    print("=" * 72)
    print("DRAWDOWN x MACRO REGIME")
    print("=" * 72)

    if not dd_report.empty:
        print(
            dd_report[
                [
                    "macro_regime",
                    "drawdown_bucket",
                    "signals",
                    "wins",
                    "losses",
                    "ambiguous",
                    "open",
                    "win_rate",
                    "avg_R",
                    "total_R",
                    "profit_factor",
                ]
            ].to_string(index=False)
        )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    trades.to_csv(
        "macro_backtest_v1_trades.csv",
        index=False,
    )

    report.to_csv(
        "macro_backtest_v1_regimes.csv",
        index=False,
    )

    dd_report.to_csv(
        "macro_backtest_v1_drawdown_regime.csv",
        index=False,
    )

    print()
    print("=" * 72)
    print("OUTPUT FILES")
    print("=" * 72)
    print("macro_backtest_v1_trades.csv")
    print("macro_backtest_v1_regimes.csv")
    print("macro_backtest_v1_drawdown_regime.csv")

    print()
    print("=" * 72)
    print("MACRO BACKTEST V1 COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    main()
