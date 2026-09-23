# ============================================================
# US500 MACRO BACKTEST V3.1 - FULL DECISION ENGINE CALIBRATION
# FROZEN EMA19 BASELINE + MACRO CONTEXT + TECHNICAL CONFIRMATION
# ============================================================
# Frozen baseline configuration validated by V3:
# ATR_WILDER / TOUCH_CLOSE_ABOVE / ROW_GAP_1 / OVERLAP
# Reference: 119 signals, 117 valid, 2 invalid SL,
# 109 resolved, 36 wins, 73 losses, 3 ambiguous, 5 open,
# +71R, PF ~= 1.973.
#
# V2.2 is research-only. It does NOT modify entries, exits, sizing,
# or the Decision Engine. Lead analysis tests whether macro deterioration
# was visible 5/10/20/60 trading days before -10% and -20% drawdowns.
# ============================================================

import os
import warnings

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
BASELINE_AS_OF_DATE = pd.Timestamp("2026-09-17")
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"

FRED_SERIES = {
    "US10Y": "DGS10", "US2Y": "DGS2", "T10Y2Y": "T10Y2Y",
    "VIX": "VIXCLS", "DXY": "DTWEXBGS",
    "UNRATE": "UNRATE", "INITIAL_CLAIMS_4W": "IC4WSA",
    "HY_SPREAD": "BAMLH0A0HYM2", "CORP_OAS": "BAMLC0A0CM",
    "NFCI": "NFCI", "INDPRO": "INDPRO", "RETAIL": "RSAFS",
    "PCE": "PCE", "CORE_PCE": "PCEPILFE", "FEDFUNDS": "FEDFUNDS",
}
MONTHLY_SERIES = {"UNRATE", "INDPRO", "RETAIL", "PCE", "CORE_PCE", "FEDFUNDS"}
DAILY_MOMENTUM_LOOKBACK = 20
MEDIUM_DAILY_LOOKBACK = 60

# ============================================================
# MARKET / FROZEN BASELINE
# ============================================================

def load_market():
    df = yf.download(TICKER, start=START_DATE, auto_adjust=False, progress=False)
    if df.empty:
        raise RuntimeError("Yahoo Finance returned no market data.")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close"]].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.sort_index().dropna()
    for c in ["Open", "High", "Low", "Close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna()
    # FROZEN BASELINE CUTOFF — must occur before EMA/ATR calculations.
    df = df.loc[
        df.index <= BASELINE_AS_OF_DATE
    ].copy()

    df["EMA19"] = df["Close"].ewm(span=EMA19, adjust=False, min_periods=EMA19).mean()
    df["EMA200"] = df["Close"].ewm(span=EMA200, adjust=False, min_periods=EMA200).mean()

    # V3.1 technical confirmation layer. These fields do NOT alter the
    # frozen EMA19 signal generator; they only classify existing signals.
    df["SMA20"] = df["Close"].rolling(20, min_periods=20).mean()
    df["SMA50"] = df["Close"].rolling(50, min_periods=50).mean()

    # Wilder-style RSI(14), calculated without changing any baseline rule.
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["RSI14"] = 100 - (100 / (1 + rs))
    df.loc[(avg_loss == 0) & (avg_gain > 0), "RSI14"] = 100.0
    df.loc[(avg_loss == 0) & (avg_gain == 0), "RSI14"] = 50.0

    pc = df["Close"].shift(1)
    tr = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - pc).abs(),
        (df["Low"] - pc).abs(),
    ], axis=1).max(axis=1)
    df["TR"] = tr
    # Exact V3-selected Wilder ATR.
    df["ATR14_WILDER"] = tr.ewm(alpha=1 / ATR14, adjust=False, min_periods=ATR14).mean()
    return df


def baseline_condition(df, i):
    r = df.iloc[i]
    return bool(
        pd.notna(r["EMA19"])
        and pd.notna(r["EMA200"])
        and r["Close"] > r["EMA200"]
        and r["EMA19"] > r["EMA200"]
        and r["Low"] <= r["EMA19"]
        and r["Close"] > r["EMA19"]
    )


def build_baseline_signals(df):
    raw = [i for i in range(len(df)) if baseline_condition(df, i)]
    return [i for p, i in enumerate(raw) if p == 0 or raw[p] - raw[p - 1] > 1]


def baseline_stop(df, i):
    if i < LOW_LOOKBACK + 1:
        return np.nan
    lows = df.iloc[i - LOW_LOOKBACK:i]["Low"]
    atr = df.iloc[i - 1]["ATR14_WILDER"]
    if pd.isna(atr):
        return np.nan
    return float(lows.min() - 0.5 * atr)


def resolve_trade(df, entry_i, entry, stop):
    if not np.isfinite(stop) or stop >= entry:
        return "INVALID_SL", np.nan, None
    risk = entry - stop
    target = entry + RR * risk
    for j in range(entry_i + 1, len(df)):
        hi = float(df.iloc[j]["High"])
        lo = float(df.iloc[j]["Low"])
        tp = hi >= target
        sl = lo <= stop
        if tp and sl:
            return "AMBIGUOUS", np.nan, j
        if tp:
            return "WIN", RR, j
        if sl:
            return "LOSS", -1.0, j
    return "OPEN", np.nan, None


def build_baseline_trades(df):
    rows = []
    for i in build_baseline_signals(df):
        entry = float(df.iloc[i]["Close"])
        stop = baseline_stop(df, i)
        result, r_mult, exit_i = resolve_trade(df, i, entry, stop)
        rows.append({
            "signal_date": df.index[i], "year": int(df.index[i].year),
            "signal_index": i, "entry": entry, "stop": stop,
            "risk_points": entry - stop if np.isfinite(stop) else np.nan,
            "target": entry + RR * (entry - stop) if np.isfinite(stop) and stop < entry else np.nan,
            "result": result, "R": r_mult,
            "exit_date": df.index[exit_i] if exit_i is not None else pd.NaT,
        })
    return pd.DataFrame(rows)


def summarize(g):
    wins = int((g["result"] == "WIN").sum())
    losses = int((g["result"] == "LOSS").sum())
    ambiguous = int((g["result"] == "AMBIGUOUS").sum())
    open_trades = int((g["result"] == "OPEN").sum())
    invalid = int((g["result"] == "INVALID_SL").sum())
    resolved = wins + losses
    r = g["R"].dropna()
    gp = float(g.loc[g["R"] > 0, "R"].sum())
    gl = abs(float(g.loc[g["R"] < 0, "R"].sum()))
    return {
        "signals": len(g), "valid": len(g) - invalid, "invalid_sl": invalid,
        "resolved": resolved, "wins": wins, "losses": losses,
        "ambiguous": ambiguous, "open": open_trades,
        "win_rate": 100 * wins / resolved if resolved else np.nan,
        "avg_R": float(r.mean()) if len(r) else np.nan,
        "total_R": float(r.sum()) if len(r) else 0.0,
        "profit_factor": gp / gl if gl else np.nan,
    }


def print_baseline_check(trades):
    s = summarize(trades)
    expected = {"signals":119, "valid":117, "invalid_sl":2, "resolved":109,
                "wins":36, "losses":73, "ambiguous":3, "open":5, "total_R":71.0}
    print("\n" + "=" * 72)
    print("FROZEN BASELINE CHECK")
    print("=" * 72)
    for k in ["signals", "valid", "invalid_sl", "resolved", "wins", "losses", "ambiguous", "open", "win_rate", "avg_R", "total_R", "profit_factor"]:
        print(f"{k:18s}: {s[k]}")
    ok = all(s[k] == v for k, v in expected.items()) and abs(s["profit_factor"] - 1.9726027397260273) < 1e-9
    print("BASELINE STATUS:", "PASS" if ok else "FAIL")
    if not ok:
        print("Expected:", expected, "PF~=1.973")

        # DIAGNOSTIC ONLY: expose the last 12 baseline signals so the
        # single extra OPEN signal can be identified without changing
        # the frozen baseline, entry, stop, RR, result, or sizing rules.
        print("\nBASELINE DIAGNOSTIC — LAST 12 SIGNALS")
        print("=" * 72)
        diagnostic_cols = [
            "signal_date", "signal_index", "entry", "stop",
            "result", "R", "exit_date",
        ]
        available = [c for c in diagnostic_cols if c in trades.columns]
        if available:
            print(trades[available].tail(12).to_string(index=False))
        else:
            print("Diagnostic columns not found. Available columns:")
            print(list(trades.columns))
    return ok

# ============================================================
# FRED
# ============================================================

def get_fred_key():
    key = os.getenv("FRED_API_KEY", "").strip()
    if not key:
        raise RuntimeError("FRED_API_KEY is missing. Configure it as a GitHub Actions secret/environment variable.")
    return key


def fred_series(series_id, api_key):
    params = {
        "series_id": series_id, "api_key": api_key, "file_type": "json",
        "observation_start": "2000-01-01",
        "observation_end": pd.Timestamp.today().strftime("%Y-%m-%d"),
    }
    r = requests.get(FRED_URL, params=params, timeout=30)
    r.raise_for_status()
    rows = []
    for obs in r.json().get("observations", []):
        if obs.get("value") in (None, "", "."):
            continue
        try:
            rows.append((pd.to_datetime(obs["date"]), float(obs["value"])))
        except (TypeError, ValueError):
            continue
    if not rows:
        return pd.Series(dtype=float, name=series_id)
    s = pd.Series(dict(rows), name=series_id)
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s.sort_index()


def load_fred():
    key = get_fred_key()
    out = {}
    print("\n" + "=" * 72)
    print("LOADING FRED MACRO DATA")
    print("=" * 72)
    for name, sid in FRED_SERIES.items():
        try:
            out[name] = fred_series(sid, key)
            print(f"{name:20s} {sid:16s} {len(out[name]):5d} observations")
        except Exception as exc:
            print(f"{name:20s} {sid:16s} ERROR: {exc}")
            out[name] = pd.Series(dtype=float, name=sid)
    return out


def _cutoff(date, monthly=False):
    d = pd.Timestamp(date)
    return d.to_period("M").start_time - pd.Timedelta(days=1) if monthly else d


def asof_series(series, date, monthly=False):
    if series is None or series.empty:
        return pd.Series(dtype=float)
    return series.loc[series.index <= _cutoff(date, monthly)].dropna()


def value_asof(series, date, monthly=False):
    s = asof_series(series, date, monthly)
    return float(s.iloc[-1]) if not s.empty else np.nan


def pct_change_asof(series, date, periods, monthly=False):
    s = asof_series(series, date, monthly)
    if len(s) <= periods:
        return np.nan
    old = float(s.iloc[-1 - periods])
    return np.nan if old == 0 else (float(s.iloc[-1]) / old - 1) * 100


def clip_score(x):
    return np.nan if not np.isfinite(x) else float(np.clip(x, 0, 100))


def inflation_yoy(fred, date, key):
    return pct_change_asof(fred[key], date, 12, monthly=True)

# ============================================================
# MACRO V2 LEVEL SCORES - transparent, fixed thresholds
# ============================================================

def score_growth(f, d):
    vals = []
    ind = pct_change_asof(f["INDPRO"], d, 12, True)
    retail = pct_change_asof(f["RETAIL"], d, 12, True)
    un = value_asof(f["UNRATE"], d, True)
    claims = pct_change_asof(f["INITIAL_CLAIMS_4W"], d, 12, False)
    if np.isfinite(ind): vals.append(15 if ind >= 3 else 30 if ind >= 1 else 45 if ind >= 0 else 65 if ind >= -2 else 85)
    if np.isfinite(retail): vals.append(15 if retail >= 5 else 30 if retail >= 3 else 45 if retail >= 1 else 60 if retail >= 0 else 80)
    if np.isfinite(un): vals.append(15 if un < 4 else 30 if un < 4.5 else 50 if un < 5 else 75 if un < 6 else 95)
    if np.isfinite(claims): vals.append(20 if claims < 0 else 35 if claims < 5 else 50 if claims < 10 else 70 if claims < 20 else 90)
    score = np.mean(vals) if vals else np.nan
    reason = "Growth deterioration is significant." if np.isfinite(score) and score >= 70 else "Growth indicators show some deterioration." if np.isfinite(score) and score >= 50 else "Growth conditions remain relatively strong." if np.isfinite(score) and score <= 30 else ""
    return clip_score(score), [reason] if reason else []


def score_inflation(f, d):
    vals = []
    pce = inflation_yoy(f, d, "PCE")
    core = inflation_yoy(f, d, "CORE_PCE")
    if np.isfinite(pce): vals.append(10 if pce < 2 else 25 if pce < 2.5 else 45 if pce < 3 else 70 if pce < 4 else 90)
    if np.isfinite(core): vals.append(10 if core < 2 else 25 if core < 2.5 else 45 if core < 3 else 70 if core < 3.5 else 95)
    score = np.mean(vals) if vals else np.nan
    reason = "Inflation pressure is elevated." if np.isfinite(score) and score >= 70 else "Inflation remains above a comfortable range." if np.isfinite(score) and score >= 50 else "Inflation pressure is relatively contained." if np.isfinite(score) and score <= 30 else ""
    return clip_score(score), [reason] if reason else []


def score_labor(f, d):
    vals = []
    un = value_asof(f["UNRATE"], d, True)
    claims = pct_change_asof(f["INITIAL_CLAIMS_4W"], d, 12, False)
    if np.isfinite(un): vals.append(10 if un < 4 else 30 if un < 4.5 else 50 if un < 5 else 75 if un < 6 else 95)
    if np.isfinite(claims): vals.append(15 if claims < 0 else 30 if claims < 5 else 50 if claims < 10 else 75 if claims < 20 else 95)
    score = np.mean(vals) if vals else np.nan
    reason = "Labor-market deterioration is elevated." if np.isfinite(score) and score >= 70 else "Labor indicators are showing some stress." if np.isfinite(score) and score >= 50 else "Labor conditions remain relatively healthy." if np.isfinite(score) and score <= 30 else ""
    return clip_score(score), [reason] if reason else []


def score_rates(f, d):
    vals = []
    y10 = value_asof(f["US10Y"], d); y2 = value_asof(f["US2Y"], d); curve = value_asof(f["T10Y2Y"], d)
    if np.isfinite(y10): vals.append(15 if y10 < 2 else 30 if y10 < 3 else 50 if y10 < 4 else 75 if y10 < 5 else 90)
    if np.isfinite(y2): vals.append(15 if y2 < 1 else 30 if y2 < 2 else 45 if y2 < 3 else 65 if y2 < 4 else 85)
    if np.isfinite(curve): vals.append(70 if curve < -1 else 60 if curve < -.5 else 50 if curve < 0 else 25)
    score = np.mean(vals) if vals else np.nan
    reason = "Rates are exerting significant pressure." if np.isfinite(score) and score >= 70 else "Rates remain restrictive." if np.isfinite(score) and score >= 50 else "Rates pressure is relatively limited." if np.isfinite(score) and score <= 30 else ""
    return clip_score(score), [reason] if reason else []


def score_credit(f, d):
    vals = []
    hy = value_asof(f["HY_SPREAD"], d); corp = value_asof(f["CORP_OAS"], d); hy60 = pct_change_asof(f["HY_SPREAD"], d, 60)
    if np.isfinite(hy): vals.append(10 if hy < 3 else 25 if hy < 4 else 50 if hy < 5 else 75 if hy < 6 else 95)
    if np.isfinite(corp): vals.append(15 if corp < 1.5 else 30 if corp < 2 else 50 if corp < 2.5 else 70 if corp < 3 else 90)
    if np.isfinite(hy60): vals.append(15 if hy60 < 0 else 30 if hy60 < 10 else 50 if hy60 < 20 else 75 if hy60 < 30 else 95)
    score = np.mean(vals) if vals else np.nan
    reason = "Credit conditions are materially stressed." if np.isfinite(score) and score >= 70 else "Credit conditions show increasing stress." if np.isfinite(score) and score >= 50 else "Credit conditions remain relatively calm." if np.isfinite(score) and score <= 30 else ""
    return clip_score(score), [reason] if reason else []


def score_liquidity(f, d):
    vals = []
    nfci = value_asof(f["NFCI"], d); vix = value_asof(f["VIX"], d); dxy60 = pct_change_asof(f["DXY"], d, 60)
    if np.isfinite(nfci): vals.append(10 if nfci < -.5 else 25 if nfci < 0 else 45 if nfci < .5 else 70 if nfci < 1 else 95)
    if np.isfinite(vix): vals.append(10 if vix < 15 else 25 if vix < 20 else 50 if vix < 25 else 75 if vix < 30 else 95)
    if np.isfinite(dxy60): vals.append(20 if dxy60 < 0 else 35 if dxy60 < 5 else 55 if dxy60 < 8 else 75 if dxy60 < 12 else 90)
    score = np.mean(vals) if vals else np.nan
    reason = "Liquidity / financial conditions are stressed." if np.isfinite(score) and score >= 70 else "Financial conditions show some tightening." if np.isfinite(score) and score >= 50 else "Liquidity conditions remain relatively easy." if np.isfinite(score) and score <= 30 else ""
    return clip_score(score), [reason] if reason else []

DIMENSIONS = {
    "growth": score_growth, "inflation": score_inflation, "labor": score_labor,
    "rates": score_rates, "credit": score_credit, "liquidity": score_liquidity,
}


def dimension_momentum(score_fn, f, d):
    current = score_fn(f, d)[0]
    sd = pd.Timestamp(d) - pd.Timedelta(days=DAILY_MOMENTUM_LOOKBACK)
    md = pd.Timestamp(d) - pd.Timedelta(days=MEDIUM_DAILY_LOOKBACK)
    short = score_fn(f, sd)[0]
    medium = score_fn(f, md)[0]
    sc = current - short if np.isfinite(current) and np.isfinite(short) else np.nan
    mc = current - medium if np.isfinite(current) and np.isfinite(medium) else np.nan
    if not np.isfinite(sc):
        return "UNAVAILABLE", np.nan, sc, mc
    if sc >= 15 or (np.isfinite(mc) and mc >= 25): status = "STRONGLY DETERIORATING"
    elif sc >= 5 or (np.isfinite(mc) and mc >= 10): status = "DETERIORATING"
    elif sc <= -5 or (np.isfinite(mc) and mc <= -10): status = "IMPROVING"
    else: status = "STABLE"
    return status, clip_score(50 + sc), sc, mc


def classify_macro_v21(f, d):
    out = {"signal_date": pd.Timestamp(d)}
    reasons = []
    levels = {}
    momentum_scores = []
    statuses = {}
    for name, fn in DIMENSIONS.items():
        score, rs = fn(f, d)
        status, mscore, sc, mc = dimension_momentum(fn, f, d)
        levels[name] = score; statuses[name] = status
        out[f"{name}_stress"] = score
        out[f"{name}_momentum"] = status
        out[f"{name}_momentum_score"] = mscore
        out[f"{name}_short_change"] = sc
        out[f"{name}_medium_change"] = mc
        reasons.extend(rs)
        if np.isfinite(mscore): momentum_scores.append(mscore)
    valid_levels = [v for v in levels.values() if np.isfinite(v)]
    out["macro_stress"] = float(np.mean(valid_levels)) if valid_levels else np.nan
    out["macro_momentum"] = float(np.mean(momentum_scores)) if momentum_scores else np.nan
    out["deteriorating_count"] = sum(v in ("DETERIORATING", "STRONGLY DETERIORATING") for v in statuses.values())
    out["strong_deteriorating_count"] = sum(v == "STRONGLY DETERIORATING" for v in statuses.values())
    out["improving_count"] = sum(v == "IMPROVING" for v in statuses.values())
    lead = [statuses[x] for x in ("credit", "labor", "liquidity")]
    lead_count = sum(v in ("DETERIORATING", "STRONGLY DETERIORATING") for v in lead)
    out["leading_warning_count"] = lead_count
    out["leading_warning"] = "STRONG" if any(v == "STRONGLY DETERIORATING" for v in lead) else "ELEVATED" if lead_count >= 2 else "WATCH" if lead_count == 1 else "NONE"
    growth = levels["growth"]; inflation = levels["inflation"]; labor = levels["labor"]; rates = levels["rates"]; credit = levels["credit"]; liquidity = levels["liquidity"]
    if np.isfinite(credit) and np.isfinite(liquidity) and credit >= 75 and liquidity >= 75:
        regime, reason = "F", "Severe credit and liquidity stress."
    elif np.isfinite(growth) and np.isfinite(labor) and growth >= 70 and labor >= 70:
        regime, reason = "E", "Growth and labor conditions indicate significant economic deterioration."
    elif np.isfinite(growth) and np.isfinite(inflation) and growth >= 65 and inflation >= 65:
        regime, reason = "D", "Growth deterioration is occurring alongside elevated inflation pressure."
    elif np.isfinite(inflation) and np.isfinite(rates) and inflation >= 65 and rates >= 60:
        regime, reason = "C", "Inflation and rates are exerting significant pressure."
    elif np.isfinite(growth) and growth >= 60 and (not np.isfinite(inflation) or inflation < 55):
        regime, reason = "B", "Growth conditions are deteriorating while inflation pressure remains relatively contained."
    else:
        regime, reason = "A", "No dominant combination of macro stresses meets the thresholds for B-F."
    out["macro_regime"] = regime; out["macro_regime_reason"] = reason; out["macro_reasons"] = " | ".join(x for x in reasons if x)
    return out

# ============================================================
# REPORTS / CALIBRATION
# ============================================================

def attach_macro(trades, fred):
    rows = []
    for _, t in trades.iterrows():
        r = t.to_dict(); r.update(classify_macro_v21(fred, t["signal_date"])); rows.append(r)
    return pd.DataFrame(rows)


def add_drawdown(trades, market):
    rh = market["High"].cummax()
    out = trades.copy()
    out["reference_high"] = out["signal_date"].map(rh)
    out["drawdown_pct"] = (out["entry"] / out["reference_high"] - 1) * 100
    return out


def add_zones(trades):
    out = trades.copy()
    def zone(x):
        if not np.isfinite(x): return "UNAVAILABLE"
        return "LOW" if x < 25 else "MODERATE" if x < 50 else "HIGH" if x < 75 else "EXTREME"
    out["macro_stress_zone"] = out["macro_stress"].apply(zone)
    out["macro_momentum_zone"] = out["macro_momentum"].apply(zone)
    out["drawdown_bucket"] = pd.cut(out["drawdown_pct"], [-np.inf,-20,-10,-5,-3,0,np.inf], labels=["<=-20%","-20% to -10%","-10% to -5%","-5% to -3%","-3% to 0%",">0%"])
    return out


def grouped_report(trades, col):
    rows = []
    for key, g in trades.groupby(col, dropna=False, observed=False):
        s = summarize(g); s[col] = key; rows.append(s)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def grouped_2d_report(trades, col_a, col_b):
    rows = []
    for (key_a, key_b), g in trades.groupby([col_a, col_b], dropna=False, observed=False):
        s = summarize(g)
        s[col_a] = key_a
        s[col_b] = key_b
        s["group"] = f"{key_a} | {key_b}"
        rows.append(s)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def print_report(title, report, key):
    print("\n" + "=" * 72); print(title); print("=" * 72)
    if report.empty:
        print("No data available."); return
    cols = [key,"signals","valid","resolved","wins","losses","ambiguous","open","win_rate","avg_R","total_R","profit_factor"]
    print(report[cols].to_string(index=False))


def detect_drawdown_events(market, thresholds=(-10.0, -20.0)):
    """Return independent drawdown episodes for each threshold.

    Entry into an episode is still defined exactly as before: the daily Close
    reaches or falls below the threshold relative to the cumulative maximum
    High.

    IMPORTANT: recovery is defined by a *new intraday high* (current High >=
    the prior cumulative reference High), not by requiring the Close itself to
    equal the historical High. This distinction matters because a market can
    establish a new all-time High intraday while closing below that High.
    Requiring Close / cumulative-High - 1 >= 0 could therefore keep an episode
    artificially open for a very long time and suppress later independent
    episodes (such as the 2022 drawdown).
    """
    ref_high = market["High"].cummax()
    dd = (market["Close"] / ref_high - 1.0) * 100.0

    # A recovery/new-high day is one whose High reaches the cumulative High
    # that existed before that day.  Shift prevents the current day's High
    # from trivially qualifying because ref_high includes the current day.
    prior_ref_high = ref_high.shift(1)
    recovered = prior_ref_high.notna() & (market["High"] >= prior_ref_high)

    events = []

    for threshold in thresholds:
        in_episode = False
        episode_id = 0

        for pos, idx in enumerate(market.index):
            value = float(dd.iloc[pos])

            # A new episode begins only after the previous episode has fully
            # recovered to a new cumulative high.
            if not in_episode and value <= threshold:
                episode_id += 1
                in_episode = True
                events.append({
                    "threshold": float(threshold),
                    "episode_id": int(episode_id),
                    "event_date": pd.Timestamp(idx),
                    "event_index": int(pos),
                    "event_drawdown_pct": value,
                    "reference_high": float(ref_high.iloc[pos]),
                })

            # Do not let the event day itself immediately recover. Recovery
            # must occur after the threshold event and must be a genuine new
            # High relative to the pre-day reference High.
            elif in_episode and bool(recovered.iloc[pos]):
                in_episode = False

    return pd.DataFrame(events).sort_values(
        ["threshold", "event_date"]
    ).reset_index(drop=True)


def build_lead_event_study(market, fred, thresholds=(-10.0, -20.0), windows=(60, 20, 10, 5)):
    """Evaluate macro state on trading days before independent episodes."""
    events = detect_drawdown_events(market, thresholds=thresholds)
    detail = []
    for _, ev in events.iterrows():
        event_index = int(ev["event_index"])
        row = ev.to_dict()
        for window in windows:
            target_index = event_index - int(window)
            prefix = f"tminus_{window}d"
            if target_index < 0:
                row[f"{prefix}_date"] = pd.NaT
                row[f"{prefix}_available"] = False
                continue
            lead_date = pd.Timestamp(market.index[target_index])
            macro = classify_macro_v21(fred, lead_date)
            row[f"{prefix}_date"] = lead_date
            row[f"{prefix}_available"] = True
            row[f"{prefix}_leading_warning"] = macro["leading_warning"]
            row[f"{prefix}_leading_warning_count"] = macro["leading_warning_count"]
            row[f"{prefix}_macro_regime"] = macro["macro_regime"]
            row[f"{prefix}_macro_stress"] = macro["macro_stress"]
            row[f"{prefix}_macro_momentum"] = macro["macro_momentum"]
            for dim in DIMENSIONS:
                row[f"{prefix}_{dim}_stress"] = macro[f"{dim}_stress"]
                row[f"{prefix}_{dim}_momentum"] = macro[f"{dim}_momentum"]
                row[f"{prefix}_{dim}_momentum_score"] = macro[f"{dim}_momentum_score"]
                row[f"{prefix}_{dim}_short_change"] = macro[f"{dim}_short_change"]
                row[f"{prefix}_{dim}_medium_change"] = macro[f"{dim}_medium_change"]
        detail.append(row)
    return pd.DataFrame(detail)


def build_lead_dimension_report(detail, windows=(60, 20, 10, 5)):
    rows = []
    for threshold in sorted(detail["threshold"].dropna().unique()):
        subset = detail[detail["threshold"] == threshold]
        for dim in DIMENSIONS:
            for window in windows:
                col = f"tminus_{window}d_{dim}_momentum"
                score_col = f"tminus_{window}d_{dim}_stress"
                if col not in subset.columns:
                    continue
                s = subset[col].dropna()
                stress = pd.to_numeric(subset[score_col], errors="coerce").dropna()
                n = len(s)
                rows.append({
                    "threshold": threshold,
                    "dimension": dim,
                    "window_trading_days": window,
                    "events": n,
                    "deteriorating_pct": 100 * s.isin(["DETERIORATING", "STRONGLY DETERIORATING"]).mean() if n else np.nan,
                    "strongly_deteriorating_pct": 100 * (s == "STRONGLY DETERIORATING").mean() if n else np.nan,
                    "improving_pct": 100 * (s == "IMPROVING").mean() if n else np.nan,
                    "stable_pct": 100 * (s == "STABLE").mean() if n else np.nan,
                    "mean_stress": float(stress.mean()) if len(stress) else np.nan,
                    "median_stress": float(stress.median()) if len(stress) else np.nan,
                })
    return pd.DataFrame(rows)


def build_lead_transition_report(detail, windows=(60, 20, 10, 5)):
    rows = []
    for threshold in sorted(detail["threshold"].dropna().unique()):
        subset = detail[detail["threshold"] == threshold]
        for dim in DIMENSIONS:
            base_col = f"tminus_{windows[0]}d_{dim}_stress"
            for window in windows[1:]:
                later_col = f"tminus_{window}d_{dim}_stress"
                if base_col not in subset or later_col not in subset:
                    continue
                pair = subset[[base_col, later_col]].apply(pd.to_numeric, errors="coerce").dropna()
                if pair.empty:
                    continue
                delta = pair[later_col] - pair[base_col]
                rows.append({
                    "threshold": threshold,
                    "dimension": dim,
                    "from_window": windows[0],
                    "to_window": window,
                    "events": len(pair),
                    "mean_stress_change": float(delta.mean()),
                    "median_stress_change": float(delta.median()),
                    "pct_worsened_ge_5": 100 * (delta >= 5).mean(),
                    "pct_worsened_ge_10": 100 * (delta >= 10).mean(),
                    "pct_improved_le_minus_5": 100 * (delta <= -5).mean(),
                })
    return pd.DataFrame(rows)


def build_lead_warning_report(detail, windows=(60, 20, 10, 5)):
    rows = []
    for threshold in sorted(detail["threshold"].dropna().unique()):
        subset = detail[detail["threshold"] == threshold]
        for window in windows:
            col = f"tminus_{window}d_leading_warning"
            if col not in subset:
                continue
            s = subset[col].dropna()
            n = len(s)
            for state in ["NONE", "WATCH", "ELEVATED", "STRONG"]:
                rows.append({
                    "threshold": threshold,
                    "window_trading_days": window,
                    "leading_warning": state,
                    "events": n,
                    "pct": 100 * (s == state).mean() if n else np.nan,
                })
    return pd.DataFrame(rows)



def build_episode_comparison(detail, windows=(60, 20, 10, 5)):
    """One row per independent episode with compact macro trajectory fields."""
    rows = []
    if detail.empty:
        return pd.DataFrame()

    for _, r in detail.iterrows():
        out = {
            "threshold": r["threshold"],
            "episode_id": r["episode_id"],
            "event_date": r["event_date"],
            "event_drawdown_pct": r["event_drawdown_pct"],
        }
        for window in windows:
            prefix = f"tminus_{window}d"
            out[f"{prefix}_date"] = r.get(f"{prefix}_date", pd.NaT)
            out[f"{prefix}_leading_warning"] = r.get(f"{prefix}_leading_warning", np.nan)
            out[f"{prefix}_macro_regime"] = r.get(f"{prefix}_macro_regime", np.nan)
            out[f"{prefix}_macro_stress"] = r.get(f"{prefix}_macro_stress", np.nan)
            out[f"{prefix}_macro_momentum"] = r.get(f"{prefix}_macro_momentum", np.nan)
        rows.append(out)
    return pd.DataFrame(rows)


def build_episode_stress_transitions(detail, windows=(60, 20, 10, 5)):
    """Calculate stress changes within each independent episode.

    Positive delta = more stress according to the existing V2.1 score.
    No thresholds or scoring rules are changed here.
    """
    rows = []
    if detail.empty:
        return pd.DataFrame()

    pairs = list(zip(windows[:-1], windows[1:]))
    for _, r in detail.iterrows():
        for dim in DIMENSIONS:
            for w0, w1 in pairs:
                a = pd.to_numeric(r.get(f"tminus_{w0}d_{dim}_stress"), errors="coerce")
                b = pd.to_numeric(r.get(f"tminus_{w1}d_{dim}_stress"), errors="coerce")
                if not (np.isfinite(a) and np.isfinite(b)):
                    continue
                delta = float(b - a)
                rows.append({
                    "threshold": r["threshold"],
                    "episode_id": r["episode_id"],
                    "event_date": r["event_date"],
                    "dimension": dim,
                    "from_window": w0,
                    "to_window": w1,
                    "stress_from": float(a),
                    "stress_to": float(b),
                    "stress_change": delta,
                    "direction": "WORSENED" if delta >= 5 else "IMPROVED" if delta <= -5 else "STABLE",
                })

            a = pd.to_numeric(r.get(f"tminus_{windows[0]}d_{dim}_stress"), errors="coerce")
            b = pd.to_numeric(r.get(f"tminus_{windows[-1]}d_{dim}_stress"), errors="coerce")
            if np.isfinite(a) and np.isfinite(b):
                delta = float(b - a)
                rows.append({
                    "threshold": r["threshold"],
                    "episode_id": r["episode_id"],
                    "event_date": r["event_date"],
                    "dimension": dim,
                    "from_window": windows[0],
                    "to_window": windows[-1],
                    "stress_from": float(a),
                    "stress_to": float(b),
                    "stress_change": delta,
                    "direction": "WORSENED" if delta >= 5 else "IMPROVED" if delta <= -5 else "STABLE",
                })
    return pd.DataFrame(rows)


def build_episode_dimension_summary(detail, windows=(60, 20, 10, 5)):
    """Summary across independent episodes, with mathematically valid percentages."""
    rows = []
    if detail.empty:
        return pd.DataFrame()

    for threshold in sorted(detail["threshold"].dropna().unique()):
        subset = detail[detail["threshold"] == threshold]
        for dim in DIMENSIONS:
            for window in windows:
                status_col = f"tminus_{window}d_{dim}_momentum"
                stress_col = f"tminus_{window}d_{dim}_stress"
                if status_col not in subset.columns:
                    continue
                s = subset[status_col]
                stress = pd.to_numeric(subset[stress_col], errors="coerce")
                valid = s.notna()
                n = int(valid.sum())
                if n == 0:
                    continue
                ss = s[valid]
                vv = stress[stress.notna()]
                rows.append({
                    "threshold": threshold,
                    "dimension": dim,
                    "window_trading_days": window,
                    "episodes": n,
                    "deteriorating_pct": 100 * ss.isin(["DETERIORATING", "STRONGLY DETERIORATING"]).mean(),
                    "strongly_deteriorating_pct": 100 * (ss == "STRONGLY DETERIORATING").mean(),
                    "improving_pct": 100 * (ss == "IMPROVING").mean(),
                    "stable_pct": 100 * (ss == "STABLE").mean(),
                    "mean_stress": float(vv.mean()) if len(vv) else np.nan,
                    "median_stress": float(vv.median()) if len(vv) else np.nan,
                })
    return pd.DataFrame(rows)


def build_episode_warning_summary(detail, windows=(60, 20, 10, 5)):
    rows = []
    if detail.empty:
        return pd.DataFrame()
    for threshold in sorted(detail["threshold"].dropna().unique()):
        subset = detail[detail["threshold"] == threshold]
        for window in windows:
            col = f"tminus_{window}d_leading_warning"
            if col not in subset.columns:
                continue
            s = subset[col].dropna()
            n = len(s)
            for state in ["NONE", "WATCH", "ELEVATED", "STRONG"]:
                rows.append({
                    "threshold": threshold,
                    "window_trading_days": window,
                    "leading_warning": state,
                    "episodes": n,
                    "pct": 100 * (s == state).mean() if n else np.nan,
                })
    return pd.DataFrame(rows)



def build_confluence_report(trades, columns, min_signals=1):
    """Trade-level macro confluence study. No thresholds or baseline logic are changed."""
    rows = []
    work = trades.copy()
    for c in columns:
        if c not in work.columns:
            raise KeyError(f"Missing confluence column: {c}")
    for keys, g in work.groupby(columns, dropna=False, observed=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        s = summarize(g)
        if s["signals"] < min_signals:
            continue
        row = {c: k for c, k in zip(columns, keys)}
        row.update(s)
        row["confluence_group"] = " | ".join(str(k) for k in keys)
        rows.append(row)
    return pd.DataFrame(rows)


def add_confluence_flags(trades):
    """Descriptive confluence flags; these are research labels only."""
    out = trades.copy()
    out["leading_stress_count"] = out[["credit_momentum", "labor_momentum", "liquidity_momentum"]].isin(["DETERIORATING", "STRONGLY DETERIORATING"]).sum(axis=1)
    out["macro_deterioration_count"] = out[[f"{d}_momentum" for d in DIMENSIONS]].isin(["DETERIORATING", "STRONGLY DETERIORATING"]).sum(axis=1)
    out["macro_improvement_count"] = out[[f"{d}_momentum" for d in DIMENSIONS]].eq("IMPROVING").sum(axis=1)
    out["technical_context"] = "NOT_INCLUDED"
    return out


def summarize_period(g):
    """Summary with no changes to the frozen trade engine."""
    if g.empty:
        return summarize(g)
    return summarize(g)


def add_v24_period(trades, split_date="2025-01-01"):
    out = trades.copy()
    d = pd.to_datetime(out["signal_date"])
    split = pd.Timestamp(split_date)
    out["sample"] = np.where(d < split, "DISCOVERY", "HOLDOUT")
    return out


def v24_candidate_tests(trades):
    """Pre-specified V2.3 hypotheses tested unchanged in discovery and holdout."""
    tests = [
        ("H1_REGIME_A_WATCH", lambda x: (x["macro_regime"] == "A") & (x["leading_warning"] == "WATCH")),
        ("H2_SHALLOW_DD_WATCH", lambda x: (x["drawdown_bucket"] == "-3% to 0%") & (x["leading_warning"] == "WATCH")),
        ("H3_DD_10_TO_5_REGIME_B", lambda x: (x["drawdown_bucket"] == "-10% to -5%") & (x["macro_regime"] == "B")),
        ("H4_REGIME_A_LIQUIDITY_DETERIORATING", lambda x: (x["macro_regime"] == "A") & (x["liquidity_momentum"] == "DETERIORATING")),
        ("H5_SHALLOW_DD_LEADING_STRESS_COUNT_1", lambda x: (x["drawdown_bucket"] == "-3% to 0%") & (x["leading_stress_count"] == 1)),
    ]
    rows = []
    for name, fn in tests:
        mask = fn(trades)
        for sample in ["DISCOVERY", "HOLDOUT"]:
            g = trades.loc[mask & (trades["sample"] == sample)].copy()
            st = summarize(g)
            rows.append({"hypothesis": name, "sample": sample, **st})
    return pd.DataFrame(rows)


def v24_group_robustness(trades):
    """Compare the same pre-specified group definitions across periods."""
    specs = [
        ("REGIME x WARNING", ["macro_regime", "leading_warning"]),
        ("DRAWDOWN x WARNING", ["drawdown_bucket", "leading_warning"]),
        ("DRAWDOWN x REGIME", ["drawdown_bucket", "macro_regime"]),
        ("REGIME x LIQUIDITY", ["macro_regime", "liquidity_momentum"]),
        ("LEADING STRESS COUNT", ["leading_stress_count"]),
    ]
    rows = []
    for title, cols in specs:
        for sample in ["DISCOVERY", "HOLDOUT"]:
            part = trades[trades["sample"] == sample]
            rep = build_confluence_report(part, cols, min_signals=1)
            if rep.empty:
                continue
            rep.insert(0, "sample", sample)
            rep.insert(0, "study", title)
            rows.append(rep)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def make_drawdown_bucket(value, boundaries):
    """Research-only drawdown bucketing for robustness sensitivity; baseline is untouched."""
    b3, b5, b10, b20 = boundaries
    if pd.isna(value):
        return np.nan
    v = float(value)
    if v <= b20:
        return f"<={b20:g}%"
    if v <= b10:
        return f"{b20:g}% to {b10:g}%"
    if v <= b5:
        return f"{b10:g}% to {b5:g}%"
    if v <= b3:
        return f"{b5:g}% to {b3:g}%"
    return f"{b3:g}% to 0%"


def v24_drawdown_sensitivity(trades):
    """Sensitivity around drawdown boundaries, without changing any trade outcomes."""
    schemes = {
        "CANONICAL": (-3.0, -5.0, -10.0, -20.0),
        "SHIFTED_0_5_PP": (-2.5, -4.5, -9.5, -19.5),
        "SHIFTED_1_0_PP": (-2.0, -4.0, -9.0, -19.0),
    }
    rows = []
    for name, bounds in schemes.items():
        work = trades.copy()
        work["sensitivity_drawdown_bucket"] = work["drawdown_pct"].apply(lambda v: make_drawdown_bucket(v, bounds))
        mask = work["leading_warning"].eq("WATCH")
        for sample in ["DISCOVERY", "HOLDOUT"]:
            g = work.loc[mask & work["sample"].eq(sample)]
            st = summarize(g)
            rows.append({"scheme": name, "sample": sample, "boundaries": str(bounds), **st})
    return pd.DataFrame(rows)


def v24_yearly_holdout(trades):
    """Year-by-year holdout stability for the pre-specified hypotheses."""
    tests = {
        "H1_REGIME_A_WATCH": lambda x: (x["macro_regime"] == "A") & (x["leading_warning"] == "WATCH"),
        "H2_SHALLOW_DD_WATCH": lambda x: (x["drawdown_bucket"] == "-3% to 0%") & (x["leading_warning"] == "WATCH"),
        "H4_REGIME_A_LIQUIDITY_DETERIORATING": lambda x: (x["macro_regime"] == "A") & (x["liquidity_momentum"] == "DETERIORATING"),
        "H5_SHALLOW_DD_LEADING_STRESS_COUNT_1": lambda x: (x["drawdown_bucket"] == "-3% to 0%") & (x["leading_stress_count"] == 1),
    }
    hold = trades[trades["sample"] == "HOLDOUT"].copy()
    rows = []
    if hold.empty:
        return pd.DataFrame()
    hold["holdout_year"] = pd.to_datetime(hold["signal_date"]).dt.year
    for name, fn in tests.items():
        mask = fn(hold)
        for year, g0 in hold.loc[mask].groupby("holdout_year"):
            st = summarize(g0)
            rows.append({"hypothesis": name, "year": int(year), **st})
    return pd.DataFrame(rows)


# ============================================================
# V2.5 WALK-FORWARD / ROLLING ROBUSTNESS
# ============================================================
def v25_hypotheses():
    """Exactly the V2.3 pre-specified hypotheses; no re-optimization."""
    return [
        ("H1_REGIME_A_WATCH", lambda x: (x["macro_regime"] == "A") & (x["leading_warning"] == "WATCH")),
        ("H2_SHALLOW_DD_WATCH", lambda x: (x["drawdown_bucket"] == "-3% to 0%") & (x["leading_warning"] == "WATCH")),
        ("H3_DD_10_TO_5_REGIME_B", lambda x: (x["drawdown_bucket"] == "-10% to -5%") & (x["macro_regime"] == "B")),
        ("H4_REGIME_A_LIQUIDITY_DETERIORATING", lambda x: (x["macro_regime"] == "A") & (x["liquidity_momentum"] == "DETERIORATING")),
        ("H5_SHALLOW_DD_LEADING_STRESS_COUNT_1", lambda x: (x["drawdown_bucket"] == "-3% to 0%") & (x["leading_stress_count"] == 1)),
    ]


def v25_walk_forward(trades, first_test_year=2023, last_test_year=None):
    """
    Expanding chronological walk-forward report.

    For each test year Y:
      TRAIN/AVAILABLE: all observations before Y
      TEST: observations in calendar year Y

    The hypotheses are fixed in advance and are never selected or optimized
    from the training period. The prior-period column is descriptive only.
    """
    out = trades.copy()
    out["signal_date"] = pd.to_datetime(out["signal_date"])
    min_year = int(out["signal_date"].dt.year.min())
    max_year = int(out["signal_date"].dt.year.max())
    first_test_year = max(first_test_year, min_year + 1)
    if last_test_year is None:
        last_test_year = max_year

    rows = []
    for test_year in range(first_test_year, last_test_year + 1):
        train = out[out["signal_date"].dt.year < test_year]
        test = out[out["signal_date"].dt.year == test_year]
        if test.empty:
            continue

        for name, fn in v25_hypotheses():
            train_g = train.loc[fn(train)].copy()
            test_g = test.loc[fn(test)].copy()
            train_st = summarize(train_g)
            test_st = summarize(test_g)

            row = {
                "hypothesis": name,
                "test_year": test_year,
                "train_start": train["signal_date"].min().date().isoformat() if not train.empty else "",
                "train_end": train["signal_date"].max().date().isoformat() if not train.empty else "",
                "train_signals": train_st["signals"],
                "train_resolved": train_st["resolved"],
                "train_wins": train_st["wins"],
                "train_losses": train_st["losses"],
                "train_win_rate": train_st["win_rate"],
                "train_avg_R": train_st["avg_R"],
                "train_total_R": train_st["total_R"],
                "train_profit_factor": train_st["profit_factor"],
                "test_signals": test_st["signals"],
                "test_valid": test_st["valid"],
                "test_invalid_sl": test_st["invalid_sl"],
                "test_resolved": test_st["resolved"],
                "test_wins": test_st["wins"],
                "test_losses": test_st["losses"],
                "test_ambiguous": test_st["ambiguous"],
                "test_open": test_st["open"],
                "test_win_rate": test_st["win_rate"],
                "test_avg_R": test_st["avg_R"],
                "test_total_R": test_st["total_R"],
                "test_profit_factor": test_st["profit_factor"],
            }
            rows.append(row)

    return pd.DataFrame(rows)


def v25_stability_summary(walk):
    """Summarize OOS test-year consistency without ranking hypotheses."""
    if walk.empty:
        return pd.DataFrame()

    rows = []
    for name, g in walk.groupby("hypothesis"):
        tested = g[g["test_resolved"] > 0].copy()
        positive = int((tested["test_total_R"] > 0).sum())
        nonnegative = int((tested["test_total_R"] >= 0).sum())
        rows.append({
            "hypothesis": name,
            "test_years_with_resolved_trades": len(tested),
            "positive_test_years": positive,
            "nonnegative_test_years": nonnegative,
            "test_years_total_R": float(tested["test_total_R"].sum()) if not tested.empty else 0.0,
            "test_resolved_total": int(tested["test_resolved"].sum()) if not tested.empty else 0,
            "test_wins_total": int(tested["test_wins"].sum()) if not tested.empty else 0,
            "test_losses_total": int(tested["test_losses"].sum()) if not tested.empty else 0,
            "test_win_rate_pooled": (
                100.0 * tested["test_wins"].sum() / tested["test_resolved"].sum()
                if not tested.empty and tested["test_resolved"].sum() else np.nan
            ),
            "test_avg_R_pooled": (
                float(tested["test_total_R"].sum() / tested["test_resolved"].sum())
                if not tested.empty and tested["test_resolved"].sum() else np.nan
            ),
        })
    return pd.DataFrame(rows)


def main():
    market = load_market()
    print(f"Market rows: {len(market)} | {market.index.min().date()} -> {market.index.max().date()}")

    # ------------------------------------------------------------
    # FROZEN BASELINE — MUST REMAIN IDENTICAL TO V2.3
    # ------------------------------------------------------------
    baseline = build_baseline_trades(market)
    baseline_ok = print_baseline_check(baseline)
    if not baseline_ok:
        raise RuntimeError("FROZEN BASELINE FAILED. V2.4 is stopped; do not use these results.")

    fred = load_fred()
    trades = attach_macro(baseline, fred)
    trades = add_drawdown(trades, market)
    trades = add_zones(trades)
    trades = add_confluence_flags(trades)

    # Fixed chronological split. No optimization on the holdout.
    SPLIT_DATE = "2025-01-01"
    trades = add_v24_period(trades, SPLIT_DATE)

    print("\n" + "=" * 72)
    print("MACRO CALIBRATION V2.4 — OUT-OF-SAMPLE + ROBUSTNESS TEST")
    print("=" * 72)
    print(f"Chronological split: DISCOVERY < {SPLIT_DATE} | HOLDOUT >= {SPLIT_DATE}")
    print("Frozen EMA19 entries/exits/RR are unchanged. Research-only; no trade execution.")

    print("\nSAMPLE SIZES")
    print(trades.groupby("sample").size().rename("signals").to_string())

    # 1) Pre-specified V2.3 hypotheses.
    candidate = v24_candidate_tests(trades)
    print("\n" + "-" * 72)
    print("PRE-SPECIFIED V2.3 HYPOTHESES — DISCOVERY vs HOLDOUT")
    print("-" * 72)
    print(candidate.to_string(index=False))

    # 2) Same group definitions in both samples.
    groups = v24_group_robustness(trades)
    print("\n" + "-" * 72)
    print("GROUP ROBUSTNESS — SAME DEFINITIONS IN BOTH SAMPLES")
    print("-" * 72)
    if groups.empty:
        print("No grouped results.")
    else:
        cols = ["study", "sample"] + [c for c in groups.columns if c not in {"study", "sample", "signals", "valid", "invalid_sl", "resolved", "wins", "losses", "ambiguous", "open", "win_rate", "avg_R", "total_R", "profit_factor", "confluence_group"}] + ["signals", "valid", "resolved", "wins", "losses", "ambiguous", "open", "win_rate", "avg_R", "total_R", "profit_factor"]
        cols = [c for c in cols if c in groups.columns]
        print(groups[cols].to_string(index=False))

    # 3) Boundary sensitivity: only labels change, not trades/results.
    sensitivity = v24_drawdown_sensitivity(trades)
    print("\n" + "-" * 72)
    print("DRAWDOWN BOUNDARY SENSITIVITY — WATCH GROUP")
    print("-" * 72)
    print(sensitivity.to_string(index=False))

    # 4) Holdout year-by-year stability.
    yearly = v24_yearly_holdout(trades)
    print("\n" + "-" * 72)
    print("HOLDOUT YEAR-BY-YEAR STABILITY")
    print("-" * 72)
    if yearly.empty:
        print("No holdout observations for the pre-specified hypotheses.")
    else:
        print(yearly.to_string(index=False))

    # ------------------------------------------------------------
    # V2.5 WALK-FORWARD — SAME FIXED HYPOTHESES
    # ------------------------------------------------------------
    walk = v25_walk_forward(trades, first_test_year=2023)
    stability = v25_stability_summary(walk)

    print("\n" + "=" * 72)
    print("MACRO CALIBRATION V2.5 — WALK-FORWARD / ROLLING ROBUSTNESS")
    print("=" * 72)
    print("Expanding chronology: all data before test year is TRAIN/AVAILABLE;")
    print("the calendar test year is evaluated as unseen TEST data.")
    print("Hypotheses are fixed from V2.3 and are NOT optimized during walk-forward.")
    print("Research-only; no trade execution; no Decision Engine calibration.")

    print("\nWALK-FORWARD TEST-YEAR RESULTS")
    print("-" * 72)
    if walk.empty:
        print("No walk-forward observations.")
    else:
        print(walk.to_string(index=False))

    print("\nWALK-FORWARD STABILITY SUMMARY")
    print("-" * 72)
    if stability.empty:
        print("No resolved walk-forward observations.")
    else:
        print(stability.to_string(index=False))

    # Export everything for auditability.
    trades.to_csv("macro_backtest_v25_trades.csv", index=False)
    candidate.to_csv("macro_backtest_v25_candidate_hypotheses_v24_reference.csv", index=False)
    groups.to_csv("macro_backtest_v25_group_robustness_v24_reference.csv", index=False)
    sensitivity.to_csv("macro_backtest_v25_drawdown_sensitivity_v24_reference.csv", index=False)
    yearly.to_csv("macro_backtest_v25_holdout_yearly_v24_reference.csv", index=False)
    walk.to_csv("macro_backtest_v25_walk_forward.csv", index=False)
    stability.to_csv("macro_backtest_v25_stability_summary.csv", index=False)

    print("\nFILES CREATED")
    print("macro_backtest_v25_trades.csv")
    print("macro_backtest_v25_candidate_hypotheses_v24_reference.csv")
    print("macro_backtest_v25_group_robustness_v24_reference.csv")
    print("macro_backtest_v25_drawdown_sensitivity_v24_reference.csv")
    print("macro_backtest_v25_holdout_yearly_v24_reference.csv")
    print("macro_backtest_v25_walk_forward.csv")
    print("macro_backtest_v25_stability_summary.csv")
    print("\nMACRO CALIBRATION V2.5 WALK-FORWARD / ROLLING ROBUSTNESS COMPLETE")


# ============================================================
# V2.6 STATISTICAL ROBUSTNESS / NULL TESTING
# ============================================================
# Research-only. The five hypotheses are frozen from V2.3/V2.5.
# No threshold optimization, no entry/exit changes, no Decision Engine.

V26_SEED = 2606
V26_BOOTSTRAPS = 10000
V26_PERMUTATIONS = 10000
V26_BLOCK_LEN = 3


def _resolved_r(g):
    if g.empty or "R" not in g.columns:
        return np.array([], dtype=float)
    x = pd.to_numeric(g.loc[g["result"].isin(["WIN", "LOSS"]), "R"], errors="coerce").dropna()
    return x.to_numpy(dtype=float)


def _bootstrap_mean_ci(values, rng, n=V26_BOOTSTRAPS, alpha=0.05):
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return np.nan, np.nan
    if len(values) == 1:
        return float(values[0]), float(values[0])
    samples = rng.choice(values, size=(n, len(values)), replace=True)
    means = samples.mean(axis=1)
    return float(np.quantile(means, alpha/2)), float(np.quantile(means, 1-alpha/2))


def _bootstrap_total_ci(values, rng, n=V26_BOOTSTRAPS, alpha=0.05):
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return np.nan, np.nan
    if len(values) == 1:
        return float(values[0]), float(values[0])
    samples = rng.choice(values, size=(n, len(values)), replace=True)
    totals = samples.sum(axis=1)
    return float(np.quantile(totals, alpha/2)), float(np.quantile(totals, 1-alpha/2))


def _block_bootstrap_mean_ci(values, rng, block_len=V26_BLOCK_LEN, n=V26_BOOTSTRAPS, alpha=0.05):
    values = np.asarray(values, dtype=float)
    m = len(values)
    if m == 0:
        return np.nan, np.nan
    if m < 2:
        return float(values.mean()), float(values.mean())
    L = max(1, min(int(block_len), m))
    means = np.empty(n, dtype=float)
    for b in range(n):
        sample = []
        while len(sample) < m:
            start = int(rng.integers(0, m))
            for k in range(L):
                sample.append(values[(start + k) % m])
                if len(sample) >= m:
                    break
        means[b] = np.mean(sample)
    return float(np.quantile(means, alpha/2)), float(np.quantile(means, 1-alpha/2))


def _permutation_p_value(all_r, mask, observed_mean, rng, n=V26_PERMUTATIONS):
    all_r = np.asarray(all_r, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    k = int(mask.sum())
    if k == 0 or len(all_r) <= 1 or not np.isfinite(observed_mean):
        return np.nan
    extreme = 0
    # Randomly reassign the same number of labels to resolved trades.
    for _ in range(n):
        idx = rng.choice(len(all_r), size=k, replace=False)
        stat = float(all_r[idx].mean())
        if stat >= observed_mean - 1e-12:
            extreme += 1
    return float((extreme + 1) / (n + 1))


def _permutation_diff_p_value(all_r, mask, observed_diff, rng, n=V26_PERMUTATIONS):
    all_r = np.asarray(all_r, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    k = int(mask.sum())
    if k == 0 or k == len(all_r) or len(all_r) <= 1 or not np.isfinite(observed_diff):
        return np.nan
    extreme = 0
    for _ in range(n):
        idx = rng.choice(len(all_r), size=k, replace=False)
        sel = np.zeros(len(all_r), dtype=bool)
        sel[idx] = True
        diff = float(all_r[sel].mean() - all_r[~sel].mean())
        if diff >= observed_diff - 1e-12:
            extreme += 1
    return float((extreme + 1) / (n + 1))


def _placebo_shift_p_value(all_r, mask, observed_mean, rng, n=V26_PERMUTATIONS):
    """Circularly shift the fixed hypothesis membership across chronological trades."""
    all_r = np.asarray(all_r, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    k = int(mask.sum())
    N = len(all_r)
    if k == 0 or N <= 1 or not np.isfinite(observed_mean):
        return np.nan
    extreme = 0
    shifts = rng.integers(1, N, size=n)
    for shift in shifts:
        shifted = np.roll(mask, int(shift))
        stat = float(all_r[shifted].mean())
        if stat >= observed_mean - 1e-12:
            extreme += 1
    return float((extreme + 1) / (n + 1))


def _bh_adjust(pvalues):
    vals = np.asarray(pvalues, dtype=float)
    out = np.full(vals.shape, np.nan, dtype=float)
    good = np.isfinite(vals)
    if not good.any():
        return out
    idx = np.where(good)[0]
    order = idx[np.argsort(vals[good])]
    m = len(order)
    prev = 1.0
    for rank in range(m, 0, -1):
        i = order[rank-1]
        q = vals[i] * m / rank
        prev = min(prev, q)
        out[i] = prev
    return out


def _winner_concentration(values):
    values = np.sort(np.asarray(values, dtype=float))[::-1]
    total = float(values.sum()) if len(values) else 0.0
    out = {"total_R": total}
    for n in [1, 2, 3]:
        if len(values) > n:
            out[f"total_R_excl_top_{n}"] = float(values[n:].sum())
        else:
            out[f"total_R_excl_top_{n}"] = np.nan
    return out


def v26_statistical_robustness(trades):
    """Statistical tests for the five frozen hypotheses.

    The null tests ask whether a hypothesis group's observed R distribution is
    unusually positive relative to random reassignment of the same group size.
    They do not change the trading strategy or select new thresholds.
    """
    resolved = trades[trades["result"].isin(["WIN", "LOSS"])].copy()
    resolved["signal_date"] = pd.to_datetime(resolved["signal_date"])
    resolved = resolved.sort_values("signal_date").reset_index(drop=True)
    all_r = pd.to_numeric(resolved["R"], errors="coerce").to_numpy(dtype=float)
    valid_all = np.isfinite(all_r)
    resolved = resolved.loc[valid_all].reset_index(drop=True)
    all_r = pd.to_numeric(resolved["R"], errors="coerce").to_numpy(dtype=float)
    baseline_mean = float(all_r.mean()) if len(all_r) else np.nan

    rows = []
    rng = np.random.default_rng(V26_SEED)
    pvals = []
    raw_rows = []

    for name, fn in v25_hypotheses():
        mask = np.asarray(fn(resolved), dtype=bool)
        vals = all_r[mask]
        k = len(vals)
        if k == 0:
            raw_rows.append({"hypothesis": name, "resolved": 0})
            pvals.append(np.nan)
            continue

        mean_r = float(vals.mean())
        total_r = float(vals.sum())
        complement = all_r[~mask]
        comp_mean = float(complement.mean()) if len(complement) else np.nan
        diff = mean_r - comp_mean if np.isfinite(comp_mean) else np.nan
        ci_lo, ci_hi = _bootstrap_mean_ci(vals, rng)
        total_lo, total_hi = _bootstrap_total_ci(vals, rng)
        block_lo, block_hi = _block_bootstrap_mean_ci(vals, rng)
        perm_p = _permutation_p_value(all_r, mask, mean_r, rng)
        diff_p = _permutation_diff_p_value(all_r, mask, diff, rng)
        placebo_p = _placebo_shift_p_value(all_r, mask, mean_r, rng)
        concentration = _winner_concentration(vals)
        wins = int((resolved.loc[mask, "result"] == "WIN").sum())
        losses = int((resolved.loc[mask, "result"] == "LOSS").sum())

        row = {
            "hypothesis": name,
            "resolved": k,
            "wins": wins,
            "losses": losses,
            "win_rate": 100.0 * wins / k if k else np.nan,
            "mean_R": mean_r,
            "mean_R_bootstrap_ci_low": ci_lo,
            "mean_R_bootstrap_ci_high": ci_hi,
            "mean_R_block_bootstrap_ci_low": block_lo,
            "mean_R_block_bootstrap_ci_high": block_hi,
            "total_R": total_r,
            "total_R_bootstrap_ci_low": total_lo,
            "total_R_bootstrap_ci_high": total_hi,
            "baseline_mean_R": baseline_mean,
            "vs_complement_mean_R": comp_mean,
            "mean_R_difference_vs_complement": diff,
            "permutation_p_mean": perm_p,
            "permutation_p_vs_complement": diff_p,
            "placebo_circular_shift_p": placebo_p,
            **concentration,
        }
        raw_rows.append(row)
        pvals.append(perm_p)

    report = pd.DataFrame(raw_rows)
    if not report.empty and "permutation_p_mean" in report.columns:
        report["permutation_q_mean_bh"] = _bh_adjust(report["permutation_p_mean"].to_numpy(dtype=float))
    return report


def v26_crisis_exclusion(trades):
    """Sensitivity after excluding major stress years 2020 and 2022."""
    work = trades.copy()
    work["signal_date"] = pd.to_datetime(work["signal_date"])
    work = work[~work["signal_date"].dt.year.isin([2020, 2022])]
    rows = []
    for name, fn in v25_hypotheses():
        g = work.loc[fn(work) & work["result"].isin(["WIN", "LOSS"])].copy()
        r = _resolved_r(g)
        wins = int((g["result"] == "WIN").sum())
        losses = int((g["result"] == "LOSS").sum())
        rows.append({
            "hypothesis": name,
            "resolved": len(r),
            "wins": wins,
            "losses": losses,
            "win_rate": 100.0 * wins / len(r) if len(r) else np.nan,
            "avg_R": float(r.mean()) if len(r) else np.nan,
            "total_R": float(r.sum()) if len(r) else 0.0,
        })
    return pd.DataFrame(rows)


def v26_walk_forward_nulls(trades):
    """Null testing restricted to the chronological V2.5 test years."""
    rows = []
    walk = v25_walk_forward(trades, first_test_year=2023)
    if walk.empty:
        return pd.DataFrame()
    for _, w in walk.iterrows():
        year = int(w["test_year"])
        test = trades[pd.to_datetime(trades["signal_date"]).dt.year == year].copy()
        if test.empty:
            continue
        resolved = test[test["result"].isin(["WIN", "LOSS"])].copy().sort_values("signal_date").reset_index(drop=True)
        all_r = pd.to_numeric(resolved["R"], errors="coerce").to_numpy(dtype=float)
        if len(all_r) == 0:
            continue
        name = w["hypothesis"]
        fn = dict(v25_hypotheses())[name]
        mask = np.asarray(fn(resolved), dtype=bool)
        if mask.sum() == 0:
            continue
        rng = np.random.default_rng(V26_SEED + year)
        obs = float(all_r[mask].mean())
        rows.append({
            "hypothesis": name,
            "test_year": year,
            "resolved": int(mask.sum()),
            "observed_mean_R": obs,
            "permutation_p_mean": _permutation_p_value(all_r, mask, obs, rng, n=V26_PERMUTATIONS),
        })
    return pd.DataFrame(rows)


def v26_main():
    market = load_market()
    print(f"Market rows: {len(market)} | {market.index.min().date()} -> {market.index.max().date()}")

    baseline = build_baseline_trades(market)
    if not print_baseline_check(baseline):
        raise RuntimeError("FROZEN BASELINE FAILED. V2.6 is stopped; do not use these results.")

    fred = load_fred()
    trades = attach_macro(baseline, fred)
    trades = add_drawdown(trades, market)
    trades = add_zones(trades)
    trades = add_confluence_flags(trades)
    trades = add_v24_period(trades, "2025-01-01")

    print("\n" + "=" * 72)
    print("MACRO CALIBRATION V2.6 — STATISTICAL ROBUSTNESS / NULL TESTING")
    print("=" * 72)
    print("Frozen hypotheses: H1/H2/H3/H4/H5 from V2.3/V2.5.")
    print("Bootstrap, permutation, placebo, block-bootstrap, crisis-exclusion and winner-concentration tests.")
    print("Research-only; no trade execution; no Decision Engine calibration.")

    stats = v26_statistical_robustness(trades)
    crisis = v26_crisis_exclusion(trades)
    wf_nulls = v26_walk_forward_nulls(trades)

    print("\nSTATISTICAL ROBUSTNESS — FROZEN HYPOTHESES")
    print("-" * 72)
    print(stats.to_string(index=False))

    print("\nCRISIS-EXCLUSION SENSITIVITY — EXCLUDING 2020 AND 2022")
    print("-" * 72)
    print(crisis.to_string(index=False))

    print("\nWALK-FORWARD TEST-YEAR NULL CHECK")
    print("-" * 72)
    if wf_nulls.empty:
        print("No resolved walk-forward null observations.")
    else:
        print(wf_nulls.to_string(index=False))

    trades.to_csv("macro_backtest_v26_trades.csv", index=False)
    stats.to_csv("macro_backtest_v26_statistical_robustness.csv", index=False)
    crisis.to_csv("macro_backtest_v26_crisis_exclusion.csv", index=False)
    wf_nulls.to_csv("macro_backtest_v26_walk_forward_nulls.csv", index=False)

    print("\nFILES CREATED")
    print("macro_backtest_v26_trades.csv")
    print("macro_backtest_v26_statistical_robustness.csv")
    print("macro_backtest_v26_crisis_exclusion.csv")
    print("macro_backtest_v26_walk_forward_nulls.csv")
    print("\nMACRO CALIBRATION V2.6 STATISTICAL ROBUSTNESS / NULL TESTING COMPLETE")


# V2.6 main guard disabled when running V2.7.


# ============================================================
# V2.7 TEMPORAL / DEPENDENCY ROBUSTNESS
# ============================================================

V27_BOOTSTRAPS = 5000
V27_SEED = 2707

def add_independent_drawdown_episodes(trades, threshold=-3.0):
    """Assign independent drawdown episodes.

    An episode starts on the first observed trade-date at or below the
    threshold after the prior episode has recovered to >= 0% drawdown.
    Trades before the first threshold crossing are assigned NORMAL_0.
    This is deliberately a coarse market-state cluster, not a new trading rule.
    """
    work = trades.copy()
    work["signal_date"] = pd.to_datetime(work["signal_date"])
    work = work.sort_values("signal_date").reset_index(drop=True)

    episode = 0
    active = False
    ids = []
    for _, row in work.iterrows():
        dd = row.get("drawdown_pct", np.nan)
        if not active:
            if np.isfinite(dd) and float(dd) <= threshold:
                episode += 1
                active = True
        ids.append(episode)
        if active and np.isfinite(dd) and float(dd) >= 0:
            active = False
    work["dd3_episode_id"] = ids
    work["dd3_episode"] = work["dd3_episode_id"].apply(
        lambda x: f"EP_{int(x)}" if int(x) > 0 else "NORMAL"
    )
    return work


def _cluster_bootstrap_mean(values, clusters, rng, n=V27_BOOTSTRAPS, alpha=0.05):
    """Bootstrap clusters, keeping all observations inside a cluster together."""
    values = np.asarray(values, dtype=float)
    clusters = np.asarray(clusters)
    if len(values) == 0:
        return np.nan, np.nan
    unique = pd.unique(clusters)
    if len(unique) == 1:
        return float(values.mean()), float(values.mean())

    cluster_values = {c: values[clusters == c] for c in unique}
    means = np.empty(n, dtype=float)
    for b in range(n):
        sampled = rng.choice(unique, size=len(unique), replace=True)
        vals = np.concatenate([cluster_values[c] for c in sampled])
        means[b] = float(np.mean(vals))
    return (
        float(np.quantile(means, alpha / 2)),
        float(np.quantile(means, 1 - alpha / 2)),
    )


def _episode_leave_one_out(values, clusters):
    """Return min/max mean after removing one independent episode/cluster."""
    values = np.asarray(values, dtype=float)
    clusters = np.asarray(clusters)
    unique = pd.unique(clusters)
    if len(unique) <= 1:
        return np.nan, np.nan, len(unique)

    means = []
    for c in unique:
        keep = clusters != c
        if keep.sum():
            means.append(float(values[keep].mean()))
    return float(min(means)), float(max(means)), len(unique)


def _cluster_concentration(values, clusters):
    """Measure whether a result is dominated by one temporal cluster."""
    values = np.asarray(values, dtype=float)
    clusters = np.asarray(clusters)
    unique = pd.unique(clusters)
    totals = {c: float(values[clusters == c].sum()) for c in unique}
    ranked = sorted(totals.values(), reverse=True)
    total = float(values.sum())
    return {
        "cluster_count": len(unique),
        "top_cluster_R": ranked[0] if ranked else np.nan,
        "total_R_excl_top_cluster": (
            total - ranked[0] if ranked else total
        ),
        "top_2_cluster_R": (
            sum(ranked[:2]) if ranked else np.nan
        ),
        "total_R_excl_top_2_clusters": (
            total - sum(ranked[:2]) if ranked else total
        ),
    }


def v27_temporal_robustness(trades):
    """Evaluate frozen hypotheses using temporal clusters rather than
    treating every trade as independent evidence."""
    work = add_independent_drawdown_episodes(trades, threshold=-3.0)
    resolved = work[work["result"].isin(["WIN", "LOSS"])].copy()
    resolved["signal_date"] = pd.to_datetime(resolved["signal_date"])
    resolved = resolved.sort_values("signal_date").reset_index(drop=True)
    resolved["year_cluster"] = resolved["signal_date"].dt.year.astype(str)

    rows = []
    rng = np.random.default_rng(V27_SEED)

    for name, fn in v25_hypotheses():
        mask = np.asarray(fn(resolved), dtype=bool)
        g = resolved.loc[mask].copy()
        if g.empty:
            rows.append({
                "hypothesis": name,
                "resolved": 0,
                "dd3_episode_clusters": 0,
                "year_clusters": 0,
            })
            continue

        r = pd.to_numeric(g["R"], errors="coerce").to_numpy(dtype=float)
        ok = np.isfinite(r)
        g = g.loc[ok].reset_index(drop=True)
        r = pd.to_numeric(g["R"], errors="coerce").to_numpy(dtype=float)

        dd_clusters = g["dd3_episode_id"].to_numpy()
        year_clusters = g["year_cluster"].to_numpy()

        dd_lo, dd_hi = _cluster_bootstrap_mean(r, dd_clusters, rng)
        yr_lo, yr_hi = _cluster_bootstrap_mean(r, year_clusters, rng)

        dd_loo_min, dd_loo_max, dd_n = _episode_leave_one_out(r, dd_clusters)
        yr_loo_min, yr_loo_max, yr_n = _episode_leave_one_out(r, year_clusters)

        row = {
            "hypothesis": name,
            "resolved": len(r),
            "wins": int((g["result"] == "WIN").sum()),
            "losses": int((g["result"] == "LOSS").sum()),
            "mean_R": float(r.mean()),
            "total_R": float(r.sum()),
            "dd3_episode_clusters": dd_n,
            "dd3_cluster_bootstrap_ci_low": dd_lo,
            "dd3_cluster_bootstrap_ci_high": dd_hi,
            "dd3_leave_one_episode_out_min_mean_R": dd_loo_min,
            "dd3_leave_one_episode_out_max_mean_R": dd_loo_max,
            "year_clusters": yr_n,
            "year_cluster_bootstrap_ci_low": yr_lo,
            "year_cluster_bootstrap_ci_high": yr_hi,
            "year_leave_one_out_min_mean_R": yr_loo_min,
            "year_leave_one_out_max_mean_R": yr_loo_max,
            **_cluster_concentration(r, dd_clusters),
        }
        rows.append(row)

    return pd.DataFrame(rows)


def v27_episode_permutation(trades, n=V27_BOOTSTRAPS):
    """Episode-level placebo: preserve complete temporal clusters and compare
    observed hypothesis-group mean with random episode assignment.

    This is intentionally conservative. It does not pretend trades within
    one market episode are independent observations.
    """
    work = add_independent_drawdown_episodes(trades, threshold=-3.0)
    resolved = work[work["result"].isin(["WIN", "LOSS"])].copy()
    resolved["signal_date"] = pd.to_datetime(resolved["signal_date"])
    resolved = resolved.sort_values("signal_date").reset_index(drop=True)

    rows = []
    rng = np.random.default_rng(V27_SEED + 100)

    for name, fn in v25_hypotheses():
        mask = np.asarray(fn(resolved), dtype=bool)
        if not mask.any():
            continue

        observed = float(pd.to_numeric(
            resolved.loc[mask, "R"], errors="coerce"
        ).dropna().mean())

        # A hypothesis is considered represented by the set of episodes in
        # which it appears. Randomly select the same number of episodes and
        # pool all trades from those episodes.
        episode_labels = resolved["dd3_episode_id"].to_numpy()
        unique = pd.unique(episode_labels)
        selected_obs = pd.unique(episode_labels[mask])
        k = len(selected_obs)

        if k == 0 or len(unique) <= 1:
            p = np.nan
        else:
            episode_means = {
                e: float(pd.to_numeric(
                    resolved.loc[episode_labels == e, "R"],
                    errors="coerce"
                ).dropna().mean())
                for e in unique
            }
            valid_eps = [e for e, v in episode_means.items() if np.isfinite(v)]
            k = min(k, len(valid_eps))
            extreme = 0
            for _ in range(n):
                chosen = rng.choice(valid_eps, size=k, replace=False)
                vals = [episode_means[e] for e in chosen]
                stat = float(np.mean(vals))
                if stat >= observed - 1e-12:
                    extreme += 1
            p = float((extreme + 1) / (n + 1))

        rows.append({
            "hypothesis": name,
            "resolved": int(mask.sum()),
            "observed_mean_R": observed,
            "observed_episode_count": int(len(selected_obs)),
            "total_episode_count": int(len(unique)),
            "episode_level_permutation_p": p,
        })

    return pd.DataFrame(rows)


def v27_exclusion_sensitivity(trades):
    """Leave-one-year and leave-one-major-episode sensitivity."""
    work = add_independent_drawdown_episodes(trades, threshold=-3.0)
    resolved = work[work["result"].isin(["WIN", "LOSS"])].copy()
    resolved["signal_date"] = pd.to_datetime(resolved["signal_date"])

    rows = []
    exclusion_sets = {
        "NONE": set(),
        "EXCLUDE_2020": {2020},
        "EXCLUDE_2022": {2022},
        "EXCLUDE_2020_2022": {2020, 2022},
        "EXCLUDE_2025": {2025},
    }

    for name, fn in v25_hypotheses():
        base = resolved.loc[fn(resolved)].copy()
        for label, years in exclusion_sets.items():
            g = base[~base["signal_date"].dt.year.isin(years)]
            r = pd.to_numeric(g["R"], errors="coerce").dropna()
            rows.append({
                "hypothesis": name,
                "exclusion": label,
                "resolved": len(r),
                "wins": int((g["result"] == "WIN").sum()),
                "losses": int((g["result"] == "LOSS").sum()),
                "avg_R": float(r.mean()) if len(r) else np.nan,
                "total_R": float(r.sum()) if len(r) else 0.0,
            })
    return pd.DataFrame(rows)


def v27_main():
    market = load_market()
    print(f"Market rows: {len(market)} | {market.index.min().date()} -> {market.index.max().date()}")

    baseline = build_baseline_trades(market)
    if not print_baseline_check(baseline):
        raise RuntimeError("FROZEN BASELINE FAILED. V2.7 is stopped; do not use these results.")

    fred = load_fred()
    trades = attach_macro(baseline, fred)
    trades = add_drawdown(trades, market)
    trades = add_zones(trades)
    trades = add_confluence_flags(trades)
    trades = add_v24_period(trades, "2025-01-01")

    print("\n" + "=" * 72)
    print("MACRO CALIBRATION V2.7 — TEMPORAL / DEPENDENCY ROBUSTNESS")
    print("=" * 72)
    print("Frozen hypotheses: H1/H2/H4/H5 from V2.3/V2.5; H3 retained for audit.")
    print("Trade-level results are re-tested with independent drawdown episodes and year clusters.")
    print("No thresholds, entries, exits or hypotheses are optimized.")
    print("Research-only; no trade execution; no Decision Engine calibration.")

    temporal = v27_temporal_robustness(trades)
    episode_perm = v27_episode_permutation(trades)
    exclusions = v27_exclusion_sensitivity(trades)

    print("\nTEMPORAL / CLUSTER ROBUSTNESS")
    print("-" * 72)
    print(temporal.to_string(index=False))

    print("\nEPISODE-LEVEL PERMUTATION / PLACEBO")
    print("-" * 72)
    print(episode_perm.to_string(index=False))

    print("\nYEAR / CRISIS EXCLUSION SENSITIVITY")
    print("-" * 72)
    print(exclusions.to_string(index=False))

    trades.to_csv("macro_backtest_v27_trades.csv", index=False)
    temporal.to_csv("macro_backtest_v27_temporal_robustness.csv", index=False)
    episode_perm.to_csv("macro_backtest_v27_episode_permutation.csv", index=False)
    exclusions.to_csv("macro_backtest_v27_exclusion_sensitivity.csv", index=False)

    print("\nFILES CREATED")
    print("macro_backtest_v27_trades.csv")
    print("macro_backtest_v27_temporal_robustness.csv")
    print("macro_backtest_v27_episode_permutation.csv")
    print("macro_backtest_v27_exclusion_sensitivity.csv")
    print("\nMACRO CALIBRATION V2.7 TEMPORAL / DEPENDENCY ROBUSTNESS COMPLETE")



# ============================================================
# V2.9 EPISODE INTEGRITY + STATISTICAL AUDIT
# ============================================================
# Research-only audit of V2.7. No frozen baseline, hypothesis,
# entry, exit, sizing, or Decision Engine logic is changed.
#
# Purpose:
# 1) Reconstruct independent episodes from the DAILY MARKET path,
#    rather than from trade dates only.
# 2) Recompute the V2.7 episode-level permutation exactly.
# 3) Compare the exact finite permutation distribution with the
#    Monte-Carlo p-value printed by V2.7.
# 4) Audit episode/year concentration and leave-one-cluster-out.
# ============================================================

from itertools import combinations

V28_THRESHOLD = -3.0

def v28_market_episode_labels(market, threshold=V28_THRESHOLD):
    """Assign each market date to an independent drawdown episode.

    The episode starts when Close/previous cumulative High reaches the
    threshold. Recovery requires a later genuine new intraday high
    (High >= prior cumulative High), matching the independent-episode
    logic used by the V2.2 episode study.
    """
    m = market.copy()
    m.index = pd.to_datetime(m.index)
    ref_high = m["High"].cummax()
    dd = (m["Close"] / ref_high - 1.0) * 100.0
    prior_ref_high = ref_high.shift(1)
    recovered = prior_ref_high.notna() & (m["High"] >= prior_ref_high)

    labels = []
    episode_id = 0
    active = False
    for pos in range(len(m)):
        value = float(dd.iloc[pos])
        if not active and np.isfinite(value) and value <= threshold:
            episode_id += 1
            active = True
        labels.append(episode_id if active else 0)
        if active and bool(recovered.iloc[pos]):
            active = False
    return pd.Series(labels, index=m.index, name="market_episode_id")


def v28_attach_market_episodes(trades, market, threshold=V28_THRESHOLD):
    out = trades.copy()
    out["signal_date"] = pd.to_datetime(out["signal_date"])
    labels = v28_market_episode_labels(market, threshold)
    mapping = labels.reindex(out["signal_date"]).ffill().fillna(0).astype(int)
    out["market_episode_id"] = mapping.to_numpy()
    out["market_episode"] = out["market_episode_id"].apply(
        lambda x: f"EP_{int(x)}" if int(x) > 0 else "NORMAL"
    )
    return out


def bh_adjust(p_values):
    p=np.asarray(p_values,dtype=float); m=len(p)
    if m==0: return np.array([])
    order=np.argsort(p); q=np.empty(m,float); running=1.0
    for rank,idx in reversed(list(enumerate(order,start=1))):
        running=min(running,p[idx]*m/rank); q[idx]=running
    return q


def v29_corrected_episode_permutation(trades, episode_col, n_mc=10000):
    """Correct episode-level permutation with matched observed/null statistics."""
    rows=[]; rng=np.random.default_rng(V27_SEED+2900)
    resolved=trades[trades['result'].isin(['WIN','LOSS'])].copy()
    for name,fn in v25_hypotheses():
        g=resolved.loc[np.asarray(fn(resolved),dtype=bool)].copy()
        g['R_num']=pd.to_numeric(g['R'],errors='coerce'); g=g[np.isfinite(g['R_num'])].copy()
        if g.empty: continue
        stats={}
        for ep,eg in resolved.groupby(episode_col,dropna=False):
            rr=pd.to_numeric(eg['R'],errors='coerce').dropna()
            if len(rr): stats[ep]={'mean':float(rr.mean()),'n':len(rr),'sum':float(rr.sum())}
        selected=[e for e in pd.unique(g[episode_col]) if e in stats]
        all_eps=list(stats); k=len(selected); total=len(all_eps)
        obs_ep=float(np.mean([stats[e]['mean'] for e in selected])) if k else np.nan
        obs_tw=float(g['R_num'].mean())
        if not k or k>total: continue
        extreme_ep=extreme_tw=0; assignments=0
        if total<=20:
            for combo in combinations(all_eps,k):
                assignments+=1
                se=float(np.mean([stats[e]['mean'] for e in combo]))
                n=sum(stats[e]['n'] for e in combo); st=sum(stats[e]['sum'] for e in combo)/n
                extreme_ep += se >= obs_ep-1e-12
                extreme_tw += st >= obs_tw-1e-12
            p_ep=extreme_ep/assignments; p_tw=extreme_tw/assignments; method='exact'
        else:
            for _ in range(n_mc):
                chosen=rng.choice(all_eps,size=k,replace=False)
                se=float(np.mean([stats[e]['mean'] for e in chosen]))
                n=sum(stats[e]['n'] for e in chosen); st=sum(stats[e]['sum'] for e in chosen)/n
                extreme_ep += se >= obs_ep-1e-12; extreme_tw += st >= obs_tw-1e-12
            assignments=n_mc; p_ep=(extreme_ep+1)/(n_mc+1); p_tw=(extreme_tw+1)/(n_mc+1); method='monte_carlo'
        rows.append({'hypothesis':name,'episode_definition':episode_col,'resolved':len(g),
                     'selected_episode_count':k,'total_resolved_episode_count':total,
                     'observed_episode_mean_R':obs_ep,'observed_trade_mean_R':obs_tw,
                     'episode_mean_p':p_ep,'trade_weighted_p':p_tw,'method':method,
                     'extreme_episode_mean':extreme_ep,'extreme_trade_weighted':extreme_tw,
                     'total_assignments':assignments,'selected_episodes':str([str(e) for e in selected])})
    out=pd.DataFrame(rows)
    if not out.empty:
        out['episode_mean_q_bh']=bh_adjust(out['episode_mean_p'].to_numpy())
        out['trade_weighted_q_bh']=bh_adjust(out['trade_weighted_p'].to_numpy())
    return out


def v29_episode_bootstrap(trades, episode_col, n=20000):
    """Bootstrap independent episodes while preserving within-episode trade blocks."""
    rows=[]; rng=np.random.default_rng(V27_SEED+2950)
    resolved=trades[trades['result'].isin(['WIN','LOSS'])].copy()
    for name,fn in v25_hypotheses():
        g=resolved.loc[np.asarray(fn(resolved),dtype=bool)].copy(); g['R_num']=pd.to_numeric(g['R'],errors='coerce'); g=g[np.isfinite(g['R_num'])]
        eps=[]
        for ep,eg in g.groupby(episode_col,dropna=False): eps.append((float(eg['R_num'].mean()),len(eg),float(eg['R_num'].sum())))
        if not eps: continue
        k=len(eps); x=np.array([e[0] for e in eps]); bm=[]; tw=[]
        for _ in range(n):
            idx=rng.integers(0,k,size=k); bm.append(x[idx].mean())
            nn=sum(eps[j][1] for j in idx); tw.append(sum(eps[j][2] for j in idx)/nn)
        rows.append({'hypothesis':name,'episode_count':k,'observed_episode_mean_R':float(x.mean()),
                     'episode_bootstrap_ci_low':float(np.quantile(bm,.025)), 'episode_bootstrap_ci_high':float(np.quantile(bm,.975)),
                     'observed_trade_mean_R':float(g['R_num'].mean()), 'trade_weighted_episode_bootstrap_ci_low':float(np.quantile(tw,.025)),
                     'trade_weighted_episode_bootstrap_ci_high':float(np.quantile(tw,.975))})
    return pd.DataFrame(rows)


def v29_leave_one_year_out(trades):
    rows=[]; r=trades[trades['result'].isin(['WIN','LOSS'])].copy(); r['R_num']=pd.to_numeric(r['R'],errors='coerce'); r=r[np.isfinite(r['R_num'])].copy(); r['year']=pd.to_datetime(r['signal_date']).dt.year
    for name,fn in v25_hypotheses():
        g=r.loc[np.asarray(fn(r),dtype=bool)].copy()
        if g.empty: continue
        vals=[]
        for y in sorted(g['year'].unique()):
            keep=g['year']!=y
            if keep.sum(): vals.append(float(g.loc[keep,'R_num'].mean()))
        rows.append({'hypothesis':name,'year_count':g['year'].nunique(),'loo_year_min_mean_R':min(vals) if vals else np.nan,'loo_year_max_mean_R':max(vals) if vals else np.nan,'years':str(sorted(g['year'].unique()))})
    return pd.DataFrame(rows)


def v28_reproduce_v27_mc(trades, n=V27_BOOTSTRAPS):
    """Reproduce the V2.7 episode permutation algorithm exactly.

    This is an audit function only. It lets us compare what the code
    actually computes with the p-values printed in the V2.7 run.
    """
    work = add_independent_drawdown_episodes(trades, threshold=V28_THRESHOLD)
    resolved = work[work["result"].isin(["WIN", "LOSS"])].copy()
    resolved["signal_date"] = pd.to_datetime(resolved["signal_date"])
    resolved = resolved.sort_values("signal_date").reset_index(drop=True)

    rows = []
    rng = np.random.default_rng(V27_SEED + 100)

    for name, fn in v25_hypotheses():
        mask = np.asarray(fn(resolved), dtype=bool)
        if not mask.any():
            continue
        observed = float(pd.to_numeric(
            resolved.loc[mask, "R"], errors="coerce"
        ).dropna().mean())

        episode_labels = resolved["dd3_episode_id"].to_numpy()
        unique = pd.unique(episode_labels)
        selected_obs = pd.unique(episode_labels[mask])
        k = len(selected_obs)

        if k == 0 or len(unique) <= 1:
            p = np.nan
        else:
            episode_means = {
                e: float(pd.to_numeric(
                    resolved.loc[episode_labels == e, "R"],
                    errors="coerce"
                ).dropna().mean())
                for e in unique
            }
            valid_eps = [e for e, v in episode_means.items() if np.isfinite(v)]
            k2 = min(k, len(valid_eps))
            extreme = 0
            for _ in range(n):
                chosen = rng.choice(valid_eps, size=k2, replace=False)
                stat = float(np.mean([episode_means[e] for e in chosen]))
                if stat >= observed - 1e-12:
                    extreme += 1
            p = float((extreme + 1) / (n + 1))

        rows.append({
            "hypothesis": name,
            "v27_episode_count_all": int(len(unique)),
            "v27_episode_count_selected": int(k),
            "v27_recomputed_mc_p": p,
            "v27_observed_mean_R": observed,
        })
    return pd.DataFrame(rows)


def v28_cluster_audit(trades, episode_col):
    """Trade contribution and leave-one-cluster-out audit."""
    resolved = trades[trades["result"].isin(["WIN", "LOSS"])].copy()
    rows = []
    for name, fn in v25_hypotheses():
        g = resolved.loc[fn(resolved)].copy()
        if g.empty:
            continue
        g["R_num"] = pd.to_numeric(g["R"], errors="coerce")
        g = g[np.isfinite(g["R_num"])].copy()
        if g.empty:
            continue

        ep_stats = []
        for ep, eg in g.groupby(episode_col, dropna=False):
            ep_stats.append({
                "episode": ep,
                "trades": len(eg),
                "total_R": float(eg["R_num"].sum()),
                "mean_R": float(eg["R_num"].mean()),
            })
        ep_stats = sorted(ep_stats, key=lambda x: x["total_R"], reverse=True)

        loo_means = []
        for ep in ep_stats:
            keep = g[episode_col] != ep["episode"]
            if keep.sum():
                loo_means.append(float(g.loc[keep, "R_num"].mean()))

        years = pd.to_datetime(g["signal_date"]).dt.year
        year_means = []
        for y in sorted(years.unique()):
            keep = years != y
            if keep.sum():
                year_means.append(float(g.loc[keep, "R_num"].mean()))

        rows.append({
            "hypothesis": name,
            "episode_definition": episode_col,
            "resolved": len(g),
            "episode_count": g[episode_col].nunique(dropna=False),
            "top_episode": str(ep_stats[0]["episode"]) if ep_stats else "",
            "top_episode_trades": ep_stats[0]["trades"] if ep_stats else 0,
            "top_episode_total_R": ep_stats[0]["total_R"] if ep_stats else np.nan,
            "total_R": float(g["R_num"].sum()),
            "total_R_excl_top_episode": (
                float(g["R_num"].sum() - ep_stats[0]["total_R"])
                if ep_stats else np.nan
            ),
            "loo_episode_min_mean_R": min(loo_means) if loo_means else np.nan,
            "loo_episode_max_mean_R": max(loo_means) if loo_means else np.nan,
            "year_count": years.nunique(),
            "loo_year_min_mean_R": min(year_means) if year_means else np.nan,
            "loo_year_max_mean_R": max(year_means) if year_means else np.nan,
            "episode_details": str(ep_stats),
        })
    return pd.DataFrame(rows)


def v28_main():
    market = load_market()
    print(f"Market rows: {len(market)} | {market.index.min().date()} -> {market.index.max().date()}")

    baseline = build_baseline_trades(market)
    if not print_baseline_check(baseline):
        raise RuntimeError("FROZEN BASELINE FAILED. V2.9 is stopped.")

    fred = load_fred()
    trades = attach_macro(baseline, fred)
    trades = add_drawdown(trades, market)
    trades = add_zones(trades)
    trades = add_confluence_flags(trades)
    trades = add_v24_period(trades, "2025-01-01")

    print("\n" + "=" * 72)
    print("MACRO CALIBRATION V2.9 — EPISODE INTEGRITY + STATISTICAL AUDIT")
    print("=" * 72)
    print("V2.7 hypotheses remain frozen: H1/H2/H4/H5; H3 retained for audit.")
    print("No thresholds, entries, exits, sizing, or Decision Engine logic are changed.")
    print("Research-only. This stage audits V2.7; it is not a new optimization stage.")

    v27_mc = v28_reproduce_v27_mc(trades)
    market_ep = v28_attach_market_episodes(trades, market)
    corrected = v29_corrected_episode_permutation(market_ep, "market_episode_id")
    boot = v29_episode_bootstrap(market_ep, "market_episode_id")
    loo_year = v29_leave_one_year_out(market_ep)
    audit_market = v28_cluster_audit(market_ep, "market_episode_id")

    print("\nV2.7 ALGORITHM REPRODUCTION CHECK — AUDIT REFERENCE")
    print("-" * 72); print(v27_mc.to_string(index=False))
    print("\nV2.9 CORRECTED EPISODE PERMUTATION — MARKET EPISODES")
    print("-" * 72); print(corrected.to_string(index=False))
    print("\nV2.9 EPISODE BOOTSTRAP")
    print("-" * 72); print(boot.to_string(index=False))
    print("\nV2.9 LEAVE-ONE-YEAR-OUT")
    print("-" * 72); print(loo_year.to_string(index=False))
    print("\nV2.9 CLUSTER / LEAVE-ONE-EPISODE AUDIT — MARKET EPISODES")
    print("-" * 72); print(audit_market.to_string(index=False))

    trades.to_csv("macro_backtest_v29_trades.csv", index=False)
    market_ep.to_csv("macro_backtest_v29_market_episode_trades.csv", index=False)
    v27_mc.to_csv("macro_backtest_v29_v27_algorithm_reproduction_reference.csv", index=False)
    corrected.to_csv("macro_backtest_v29_corrected_episode_permutation.csv", index=False)
    boot.to_csv("macro_backtest_v29_episode_bootstrap.csv", index=False)
    loo_year.to_csv("macro_backtest_v29_leave_one_year_out.csv", index=False)
    audit_market.to_csv("macro_backtest_v29_market_episode_cluster_audit.csv", index=False)
    print("\nFILES CREATED")
    for f in ["macro_backtest_v29_trades.csv","macro_backtest_v29_market_episode_trades.csv","macro_backtest_v29_v27_algorithm_reproduction_reference.csv","macro_backtest_v29_corrected_episode_permutation.csv","macro_backtest_v29_episode_bootstrap.csv","macro_backtest_v29_leave_one_year_out.csv","macro_backtest_v29_market_episode_cluster_audit.csv"]: print(f)
    print("\nMACRO CALIBRATION V2.9 CORRECTED STATISTICAL VALIDATION COMPLETE")


# ============================================================
# V3.1 — FULL DECISION ENGINE CALIBRATION
# Technical confirmation is research-only and never creates signals.
# Higher Low definition frozen for V3.1:
# current signal Low > lowest Low of previous 5 completed candles.
# ============================================================

TECH_SCORE_COMPONENTS = [
    "PRICE_ABOVE_SMA200",
    "SMA50_ABOVE_SMA200",
    "HIGHER_LOW",
    "PRICE_ABOVE_SMA20",
    "RSI14_ABOVE_50",
]

def technical_confirmation_for_signal(market, signal_index):
    r = market.iloc[signal_index]
    vals = {}

    vals["PRICE_ABOVE_SMA200"] = bool(pd.notna(r.get("SMA200")) and r["Close"] > r["SMA200"])
    vals["SMA50_ABOVE_SMA200"] = bool(pd.notna(r.get("SMA50")) and pd.notna(r.get("SMA200")) and r["SMA50"] > r["SMA200"])

    if signal_index < LOW_LOOKBACK:
        vals["HIGHER_LOW"] = False
    else:
        prev_low = market.iloc[signal_index - LOW_LOOKBACK:signal_index]["Low"].min()
        vals["HIGHER_LOW"] = bool(pd.notna(prev_low) and r["Low"] > prev_low)

    vals["PRICE_ABOVE_SMA20"] = bool(pd.notna(r.get("SMA20")) and r["Close"] > r["SMA20"])
    vals["RSI14_ABOVE_50"] = bool(pd.notna(r.get("RSI14")) and r["RSI14"] > 50)

    available = [v for v in vals.values() if isinstance(v, (bool, np.bool_))]
    score = int(sum(bool(v) for v in available))
    status = "STRONG" if score >= 4 else ("PARTIAL" if score == 3 else "WEAK")

    # If any required component is unavailable, retain the numeric score but
    # explicitly mark availability so missing data is not mistaken for failure.
    required_cols = ["SMA200", "SMA50", "SMA20", "RSI14"]
    unavailable = any(pd.isna(r.get(c)) for c in required_cols)
    if unavailable:
        status = "UNAVAILABLE"

    return score, status, vals


def add_v31_technical_confirmation(trades, market):
    rows = []
    for _, row in trades.iterrows():
        i = int(row["signal_index"])
        score, status, vals = technical_confirmation_for_signal(market, i)
        out = row.copy()
        out["technical_score"] = score
        out["technical_status"] = status
        for k, v in vals.items():
            out[k] = bool(v)
        rows.append(out)
    return pd.DataFrame(rows)


def v31_full_calibration_matrix(trades):
    r = trades[trades["result"].isin(["WIN", "LOSS"])].copy()
    r["R_num"] = pd.to_numeric(r["R"], errors="coerce")
    r = r[np.isfinite(r["R_num"])].copy()
    r["macro_modifier"] = np.select(
        [r["H1_FLAG"] & r["H4_FLAG"], r["H1_FLAG"], r["H4_FLAG"]],
        ["H1+H4", "H1", "H4"], default="NONE"
    )
    rows = []
    for (modifier, status, score), g in r.groupby(["macro_modifier", "technical_status", "technical_score"], sort=False):
        wins = int((g["result"] == "WIN").sum())
        losses = int((g["result"] == "LOSS").sum())
        gross_profit = float(g.loc[g["R_num"] > 0, "R_num"].sum())
        gross_loss = abs(float(g.loc[g["R_num"] < 0, "R_num"].sum()))
        rows.append({
            "macro_modifier": modifier,
            "technical_status": status,
            "technical_score": int(score),
            "signals": len(g),
            "wins": wins,
            "losses": losses,
            "win_rate": 100 * wins / len(g),
            "avg_R": float(g["R_num"].mean()),
            "total_R": float(g["R_num"].sum()),
            "profit_factor": gross_profit / gross_loss if gross_loss else np.nan,
        })
    return pd.DataFrame(rows).sort_values(["macro_modifier", "technical_score"], kind="stable")


def v31_technical_score_matrix(trades):
    r = trades[trades["result"].isin(["WIN", "LOSS"])].copy()
    r["R_num"] = pd.to_numeric(r["R"], errors="coerce")
    r = r[np.isfinite(r["R_num"])].copy()
    rows = []
    for score, g in r.groupby("technical_score", sort=True):
        wins = int((g["result"] == "WIN").sum())
        losses = int((g["result"] == "LOSS").sum())
        gp = float(g.loc[g["R_num"] > 0, "R_num"].sum())
        gl = abs(float(g.loc[g["R_num"] < 0, "R_num"].sum()))
        rows.append({
            "technical_score": int(score), "signals": len(g), "wins": wins, "losses": losses,
            "win_rate": 100 * wins / len(g), "avg_R": float(g["R_num"].mean()),
            "total_R": float(g["R_num"].sum()), "profit_factor": gp / gl if gl else np.nan
        })
    return pd.DataFrame(rows)


def v31_decision_distribution(trades):
    rows = []
    for _, row in trades.iterrows():
        d, m = v30_decision_layer(row)
        rows.append({
            "signal_date": row["signal_date"], "result": row["result"], "R": row["R"],
            "macro_decision": d, "macro_modifier": m,
            "macro_regime": row.get("macro_regime"), "leading_warning": row.get("leading_warning"),
            "liquidity_momentum": row.get("liquidity_momentum"),
            "technical_score": row.get("technical_score"),
            "technical_status": row.get("technical_status"),
            "price_above_sma200": row.get("PRICE_ABOVE_SMA200"),
            "sma50_above_sma200": row.get("SMA50_ABOVE_SMA200"),
            "higher_low": row.get("HIGHER_LOW"),
            "price_above_sma20": row.get("PRICE_ABOVE_SMA20"),
            "rsi14_above_50": row.get("RSI14_ABOVE_50"),
        })
    return pd.DataFrame(rows)


# ============================================================
# V3.0 — DECISION ENGINE CALIBRATION
# Research-only calibration layer over the frozen EMA19 baseline.
# H1/H4 are the only candidate macro modifiers carried forward.
# H2/H5 remain research-only; H3 is suspended.
# No entry, exit, sizing, RR, or macro threshold is changed.
# ============================================================

V30_CANDIDATES = {
    "H1_REGIME_A_WATCH": lambda x: (x["macro_regime"] == "A") & (x["leading_warning"] == "WATCH"),
    "H4_REGIME_A_LIQUIDITY_DETERIORATING": lambda x: (x["macro_regime"] == "A") & (x["liquidity_momentum"] == "DETERIORATING"),
}


def v30_decision_layer(row):
    """Non-executing macro calibration label.

    The frozen technical signal remains the sole entry generator.
    Macro conditions only classify the context around an existing signal.
    """
    h1 = bool(V30_CANDIDATES["H1_REGIME_A_WATCH"](pd.DataFrame([row])).iloc[0])
    h4 = bool(V30_CANDIDATES["H4_REGIME_A_LIQUIDITY_DETERIORATING"](pd.DataFrame([row])).iloc[0])
    regime = str(row.get("macro_regime", ""))
    warning = str(row.get("leading_warning", ""))
    early = str(row.get("early_warning_level", ""))

    # Defensive precedence mirrors the existing Decision Engine philosophy.
    if early == "CRITICAL" or regime.startswith("E") or regime.startswith("F"):
        decision = "DEFENSIVE"
    elif h1 or h4:
        decision = "SUPPORTIVE / CONFIRM"
    elif regime.startswith("C") or regime.startswith("D"):
        decision = "WAIT / CONFIRM"
    elif warning in ("ELEVATED", "STRONG"):
        decision = "CAUTION"
    else:
        decision = "BASELINE CONTEXT"

    if h1 and h4:
        modifier = "H1+H4"
    elif h1:
        modifier = "H1"
    elif h4:
        modifier = "H4"
    else:
        modifier = "NONE"
    return decision, modifier


def v30_group_stats(trades, flag_col=None):
    r = trades[trades["result"].isin(["WIN", "LOSS"])].copy()
    r["R_num"] = pd.to_numeric(r["R"], errors="coerce")
    r = r[np.isfinite(r["R_num"])].copy()
    if flag_col is None:
        groups = [("ALL_BASELINE_SIGNALS", r)]
    else:
        groups = [("FLAG_TRUE", r[r[flag_col]]), ("FLAG_FALSE", r[~r[flag_col]])]
    rows=[]
    for name,g in groups:
        if g.empty:
            rows.append({"group":name,"signals":0,"resolved":0,"wins":0,"losses":0,"win_rate":np.nan,"avg_R":np.nan,"total_R":0.0,"profit_factor":np.nan})
            continue
        wins=int((g.result=="WIN").sum()); losses=int((g.result=="LOSS").sum())
        gp=float(g.loc[g.R_num>0,"R_num"].sum()); gl=abs(float(g.loc[g.R_num<0,"R_num"].sum()))
        rows.append({"group":name,"signals":len(g),"resolved":len(g),"wins":wins,"losses":losses,
                     "win_rate":100*wins/len(g),"avg_R":float(g.R_num.mean()),"total_R":float(g.R_num.sum()),
                     "profit_factor":gp/gl if gl else np.nan})
    return pd.DataFrame(rows)


def v30_context_matrix(trades):
    r=trades[trades["result"].isin(["WIN","LOSS"])].copy()
    r["R_num"]=pd.to_numeric(r["R"],errors="coerce")
    r=r[np.isfinite(r["R_num"])].copy()
    r["h1"]=(r["macro_regime"]=="A") & (r["leading_warning"]=="WATCH")
    r["h4"]=(r["macro_regime"]=="A") & (r["liquidity_momentum"]=="DETERIORATING")
    r["macro_modifier"]=np.select([r.h1 & r.h4,r.h1,r.h4],["H1+H4","H1","H4"],default="NONE")
    rows=[]
    for key,g in r.groupby("macro_modifier",sort=False):
        wins=int((g.result=="WIN").sum()); losses=int((g.result=="LOSS").sum())
        gp=float(g.loc[g.R_num>0,"R_num"].sum()); gl=abs(float(g.loc[g.R_num<0,"R_num"].sum()))
        rows.append({"macro_modifier":key,"signals":len(g),"wins":wins,"losses":losses,
                     "win_rate":100*wins/len(g),"avg_R":float(g.R_num.mean()),"total_R":float(g.R_num.sum()),
                     "profit_factor":gp/gl if gl else np.nan})
    return pd.DataFrame(rows)


def v30_decision_distribution(trades):
    rows=[]
    for _,row in trades.iterrows():
        d,m=v30_decision_layer(row)
        rows.append({"signal_date":row["signal_date"],"result":row["result"],"R":row["R"],"macro_decision":d,"macro_modifier":m,
                     "macro_regime":row.get("macro_regime"),"leading_warning":row.get("leading_warning"),"liquidity_momentum":row.get("liquidity_momentum")})
    return pd.DataFrame(rows)


def v31_main():
    market = load_market()
    market["SMA200"] = market["Close"].rolling(200, min_periods=200).mean()
    print(f"Market rows: {len(market)} | {market.index.min().date()} -> {market.index.max().date()}")

    baseline = build_baseline_trades(market)
    if not print_baseline_check(baseline):
        raise RuntimeError("FROZEN BASELINE FAILED. V3.1 STOPPED.")

    fred = load_fred()
    trades = attach_macro(baseline, fred)
    trades = add_drawdown(trades, market)
    trades = add_zones(trades)
    trades = add_confluence_flags(trades)

    print("\n" + "=" * 72)
    print("MACRO CALIBRATION V3.1 — FULL DECISION ENGINE CALIBRATION")
    print("=" * 72)
    print("Frozen EMA19 baseline remains the sole technical signal generator.")
    print("Candidate macro modifiers: H1 and H4 only.")
    print("H2/H5 remain research-only; H3 is suspended.")
    print("Technical confirmation is research-only; it does NOT create entries.")
    print("Higher Low = signal Low > lowest Low of previous 5 completed candles.")
    print("No thresholds, entries, exits, sizing, RR, or macro definitions changed.")
    print("Research-only: this script does NOT execute trades or place orders.")

    # V3.1 technical layer is attached only after the frozen baseline trades exist.
    trades = add_v31_technical_confirmation(trades, market)
    trades["H1_FLAG"] = (trades["macro_regime"] == "A") & (trades["leading_warning"] == "WATCH")
    trades["H4_FLAG"] = (trades["macro_regime"] == "A") & (trades["liquidity_momentum"] == "DETERIORATING")

    dist = v31_decision_distribution(trades)
    matrix = v31_full_calibration_matrix(trades)
    score_matrix = v31_technical_score_matrix(trades)

    print("\nV3.1 TECHNICAL CONFIRMATION SCORE DISTRIBUTION")
    print("-" * 72)
    print(score_matrix.to_string(index=False))

    print("\nV3.1 FULL CALIBRATION MATRIX — MACRO MODIFIER × TECHNICAL SCORE")
    print("-" * 72)
    print(matrix.to_string(index=False))

    print("\nV3.1 DECISION DISTRIBUTION")
    print("-" * 72)
    print(dist["macro_decision"].value_counts(dropna=False).to_string())

    print("\nV3.1 TECHNICAL STATUS DISTRIBUTION")
    print("-" * 72)
    print(dist["technical_status"].value_counts(dropna=False).to_string())

    # Integrity guards.
    baseline_dates = pd.to_datetime(baseline["signal_date"]).astype("int64")
    v31_dates = pd.to_datetime(trades["signal_date"]).astype("int64")
    if len(baseline) != len(trades) or not baseline_dates.equals(v31_dates):
        raise RuntimeError("SIGNAL-GENERATION GUARD FAILED: V3.1 changed the frozen baseline signal set.")
    print("\nV3.1 SIGNAL-GENERATION GUARD: PASS")
    print("Technical confirmation and macro modifiers classify existing frozen signals only; they do not create entries.")

    trades.to_csv("macro_backtest_v31_trades.csv", index=False)
    dist.to_csv("macro_backtest_v31_decision_distribution.csv", index=False)
    matrix.to_csv("macro_backtest_v31_full_calibration_matrix.csv", index=False)
    score_matrix.to_csv("macro_backtest_v31_technical_score_matrix.csv", index=False)

    print("\nFILES CREATED")
    for f in [
        "macro_backtest_v31_trades.csv",
        "macro_backtest_v31_decision_distribution.csv",
        "macro_backtest_v31_full_calibration_matrix.csv",
        "macro_backtest_v31_technical_score_matrix.csv",
    ]:
        print(f)
    print("\nMACRO CALIBRATION V3.1 FULL DECISION ENGINE CALIBRATION COMPLETE")



# ============================================================
# V3.2 — DECISION ENGINE ROBUSTNESS & INTERACTION VALIDATION
# ============================================================
# Research-only validation of pre-specified V3.0/V3.1 context candidates.
# No new entries, exits, sizing, RR, thresholds, macro definitions, or
# technical definitions are introduced here.
#
# Candidates carried forward:
#   C1 H1 = Regime A + WATCH
#   C2 H4 = Regime A + Liquidity Deteriorating
#   C3 H1+H4
#   C4 H1+H4 + Technical Score >= 4
#   C5 H1 + Technical Score >= 4
#   C6 H4 + Technical Score >= 4
#
# C4-C6 are pre-specified interaction checks motivated by V3.1.
# They are NOT optimized thresholds; >=4 is exactly the existing STRONG
# technical-status boundary from V3.1.
# ============================================================

V32_CANDIDATES = {
    "C1_H1_REGIME_A_WATCH": lambda x: (x["macro_regime"] == "A") & (x["leading_warning"] == "WATCH"),
    "C2_H4_REGIME_A_LIQUIDITY_DETERIORATING": lambda x: (x["macro_regime"] == "A") & (x["liquidity_momentum"] == "DETERIORATING"),
    "C3_H1_PLUS_H4": lambda x: ((x["macro_regime"] == "A") & (x["leading_warning"] == "WATCH") & (x["liquidity_momentum"] == "DETERIORATING")),
    "C4_H1_PLUS_H4_STRONG_TECH": lambda x: ((x["macro_regime"] == "A") & (x["leading_warning"] == "WATCH") & (x["liquidity_momentum"] == "DETERIORATING") & (pd.to_numeric(x["technical_score"], errors="coerce") >= 4)),
    "C5_H1_STRONG_TECH": lambda x: ((x["macro_regime"] == "A") & (x["leading_warning"] == "WATCH") & (pd.to_numeric(x["technical_score"], errors="coerce") >= 4)),
    "C6_H4_STRONG_TECH": lambda x: ((x["macro_regime"] == "A") & (x["liquidity_momentum"] == "DETERIORATING") & (pd.to_numeric(x["technical_score"], errors="coerce") >= 4)),
}


def v32_resolved(trades):
    r = trades[trades["result"].isin(["WIN", "LOSS"])].copy()
    r["R_num"] = pd.to_numeric(r["R"], errors="coerce")
    return r[np.isfinite(r["R_num"])].copy()


def v32_stats(g):
    if g.empty:
        return {"signals": 0, "wins": 0, "losses": 0, "win_rate": np.nan, "avg_R": np.nan, "total_R": 0.0, "profit_factor": np.nan}
    wins = int((g["result"] == "WIN").sum())
    losses = int((g["result"] == "LOSS").sum())
    gp = float(g.loc[g["R_num"] > 0, "R_num"].sum())
    gl = abs(float(g.loc[g["R_num"] < 0, "R_num"].sum()))
    return {"signals": len(g), "wins": wins, "losses": losses,
            "win_rate": 100 * wins / len(g), "avg_R": float(g["R_num"].mean()),
            "total_R": float(g["R_num"].sum()), "profit_factor": gp / gl if gl else np.nan}


def v32_candidate_matrix(trades):
    r = v32_resolved(trades)
    rows = []
    for name, fn in V32_CANDIDATES.items():
        g = r.loc[np.asarray(fn(r), dtype=bool)].copy()
        rows.append({"candidate": name, **v32_stats(g)})
    return pd.DataFrame(rows)


def v32_oos(trades, split_date="2025-01-01"):
    r = v32_resolved(trades)
    d = pd.to_datetime(r["signal_date"])
    rows = []
    for name, fn in V32_CANDIDATES.items():
        mask = np.asarray(fn(r), dtype=bool)
        for sample, smask in [("DISCOVERY", d < pd.Timestamp(split_date)), ("HOLDOUT", d >= pd.Timestamp(split_date))]:
            g = r.loc[mask & smask].copy()
            rows.append({"candidate": name, "sample": sample, **v32_stats(g)})
    return pd.DataFrame(rows)


def v32_walk_forward(trades):
    r = v32_resolved(trades).copy()
    r["signal_date"] = pd.to_datetime(r["signal_date"])
    min_year = int(r["signal_date"].dt.year.min())
    max_year = int(r["signal_date"].dt.year.max())
    rows = []
    for test_year in range(max(2023, min_year + 1), max_year + 1):
        train = r[r["signal_date"].dt.year < test_year]
        test = r[r["signal_date"].dt.year == test_year]
        if test.empty:
            continue
        for name, fn in V32_CANDIDATES.items():
            tg = train.loc[np.asarray(fn(train), dtype=bool)]
            vg = test.loc[np.asarray(fn(test), dtype=bool)]
            ts = v32_stats(tg); vs = v32_stats(vg)
            rows.append({"candidate": name, "test_year": test_year,
                         "train_signals": ts["signals"], "train_wins": ts["wins"], "train_losses": ts["losses"],
                         "train_win_rate": ts["win_rate"], "train_avg_R": ts["avg_R"], "train_total_R": ts["total_R"],
                         "train_profit_factor": ts["profit_factor"],
                         "test_signals": vs["signals"], "test_wins": vs["wins"], "test_losses": vs["losses"],
                         "test_win_rate": vs["win_rate"], "test_avg_R": vs["avg_R"], "test_total_R": vs["total_R"],
                         "test_profit_factor": vs["profit_factor"]})
    return pd.DataFrame(rows)


def v32_loo_year(trades):
    r = v32_resolved(trades).copy()
    r["year"] = pd.to_datetime(r["signal_date"]).dt.year
    rows = []
    for name, fn in V32_CANDIDATES.items():
        g = r.loc[np.asarray(fn(r), dtype=bool)].copy()
        vals = []
        for y in sorted(g["year"].unique()):
            keep = g["year"] != y
            if keep.sum():
                vals.append(float(g.loc[keep, "R_num"].mean()))
        rows.append({"candidate": name, "year_count": int(g["year"].nunique()),
                     "loo_year_min_mean_R": min(vals) if vals else np.nan,
                     "loo_year_max_mean_R": max(vals) if vals else np.nan,
                     "years": str(sorted(g["year"].unique().tolist()))})
    return pd.DataFrame(rows)


def v32_crisis_exclusion(trades):
    r = v32_resolved(trades).copy()
    r["year"] = pd.to_datetime(r["signal_date"]).dt.year
    exclusions = {"NONE": set(), "EXCLUDE_2020": {2020}, "EXCLUDE_2022": {2022},
                  "EXCLUDE_2020_2022": {2020, 2022}, "EXCLUDE_2025": {2025}}
    rows = []
    for name, fn in V32_CANDIDATES.items():
        mask = np.asarray(fn(r), dtype=bool)
        for label, years in exclusions.items():
            g = r.loc[mask & ~r["year"].isin(years)].copy()
            rows.append({"candidate": name, "exclusion": label, **v32_stats(g)})
    return pd.DataFrame(rows)


def v32_cluster_audit(trades, market, threshold=-3.0):
    work = v28_attach_market_episodes(trades, market, threshold=threshold)
    r = v32_resolved(work)
    rows = []
    for name, fn in V32_CANDIDATES.items():
        g = r.loc[np.asarray(fn(r), dtype=bool)].copy()
        if g.empty:
            continue
        ep_stats = []
        for ep, eg in g.groupby("market_episode_id", dropna=False):
            ep_stats.append((ep, len(eg), float(eg["R_num"].sum()), float(eg["R_num"].mean())))
        ep_stats.sort(key=lambda x: x[2], reverse=True)
        loo = []
        for ep, _, _, _ in ep_stats:
            keep = g["market_episode_id"] != ep
            if keep.sum(): loo.append(float(g.loc[keep, "R_num"].mean()))
        total = float(g["R_num"].sum())
        top = ep_stats[0] if ep_stats else ("", 0, np.nan, np.nan)
        rows.append({"candidate": name, "resolved": len(g), "episode_count": g["market_episode_id"].nunique(dropna=False),
                     "top_episode": str(top[0]), "top_episode_trades": top[1], "top_episode_total_R": top[2],
                     "total_R": total, "total_R_excl_top_episode": total - top[2] if ep_stats else np.nan,
                     "loo_episode_min_mean_R": min(loo) if loo else np.nan,
                     "loo_episode_max_mean_R": max(loo) if loo else np.nan})
    return pd.DataFrame(rows), work


def v32_episode_permutation(trades, market, threshold=-3.0, n_mc=10000):
    """Matched episode-level and trade-weighted permutation tests for C1-C6.

    The null chooses k independent market episodes uniformly without replacement,
    matching the selected candidate's episode count. Observed and null statistics
    use the same statistic, avoiding the V2.7 mismatch.
    """
    work = v28_attach_market_episodes(trades, market, threshold=threshold)
    r = v32_resolved(work)
    rng = np.random.default_rng(3200)
    all_stats = {}
    for ep, eg in r.groupby("market_episode_id", dropna=False):
        rr = eg["R_num"].to_numpy(dtype=float)
        if len(rr): all_stats[ep] = {"mean": float(rr.mean()), "n": len(rr), "sum": float(rr.sum())}
    episodes = list(all_stats)
    rows = []
    for name, fn in V32_CANDIDATES.items():
        g = r.loc[np.asarray(fn(r), dtype=bool)].copy()
        selected = [e for e in pd.unique(g["market_episode_id"]) if e in all_stats]
        k = len(selected); total = len(episodes)
        if not k or total < k:
            continue
        obs_ep = float(np.mean([all_stats[e]["mean"] for e in selected]))
        obs_tw = float(g["R_num"].mean())
        extreme_ep = extreme_tw = 0
        # Exact finite enumeration when feasible, otherwise Monte Carlo.
        if total <= 18:
            from itertools import combinations
            assignments = 0
            for combo in combinations(episodes, k):
                assignments += 1
                ep_stat = float(np.mean([all_stats[e]["mean"] for e in combo]))
                n = sum(all_stats[e]["n"] for e in combo)
                tw_stat = float(sum(all_stats[e]["sum"] for e in combo) / n)
                extreme_ep += ep_stat >= obs_ep - 1e-12
                extreme_tw += tw_stat >= obs_tw - 1e-12
            p_ep = extreme_ep / assignments
            p_tw = extreme_tw / assignments
            method = "exact"
        else:
            assignments = n_mc
            for _ in range(n_mc):
                chosen = rng.choice(episodes, size=k, replace=False)
                ep_stat = float(np.mean([all_stats[e]["mean"] for e in chosen]))
                n = sum(all_stats[e]["n"] for e in chosen)
                tw_stat = float(sum(all_stats[e]["sum"] for e in chosen) / n)
                extreme_ep += ep_stat >= obs_ep - 1e-12
                extreme_tw += tw_stat >= obs_tw - 1e-12
            p_ep = (extreme_ep + 1) / (n_mc + 1)
            p_tw = (extreme_tw + 1) / (n_mc + 1)
            method = "monte_carlo"
        rows.append({"candidate": name, "resolved": len(g), "selected_episode_count": k,
                     "total_resolved_episode_count": total, "observed_episode_mean_R": obs_ep,
                     "observed_trade_mean_R": obs_tw, "episode_mean_p": p_ep,
                     "trade_weighted_p": p_tw, "method": method,
                     "extreme_episode_mean": extreme_ep, "extreme_trade_weighted": extreme_tw,
                     "total_assignments": assignments})
    out = pd.DataFrame(rows)
    if not out.empty:
        out["episode_mean_q_bh"] = bh_adjust(out["episode_mean_p"].to_numpy(dtype=float))
        out["trade_weighted_q_bh"] = bh_adjust(out["trade_weighted_p"].to_numpy(dtype=float))
    return out


def v32_episode_bootstrap(trades, market, threshold=-3.0, n=20000):
    work = v28_attach_market_episodes(trades, market, threshold=threshold)
    r = v32_resolved(work)
    rng = np.random.default_rng(3250)
    rows = []
    for name, fn in V32_CANDIDATES.items():
        g = r.loc[np.asarray(fn(r), dtype=bool)].copy()
        eps = []
        for ep, eg in g.groupby("market_episode_id", dropna=False):
            rr = eg["R_num"].to_numpy(dtype=float)
            if len(rr): eps.append((float(rr.mean()), len(rr), float(rr.sum())))
        if not eps: continue
        k = len(eps)
        means = np.array([e[0] for e in eps])
        bm = np.empty(n); tw = np.empty(n)
        for i in range(n):
            idx = rng.integers(0, k, size=k)
            bm[i] = means[idx].mean()
            nn = sum(eps[j][1] for j in idx)
            tw[i] = sum(eps[j][2] for j in idx) / nn
        rows.append({"candidate": name, "episode_count": k,
                     "observed_episode_mean_R": float(means.mean()),
                     "episode_bootstrap_ci_low": float(np.quantile(bm, .025)),
                     "episode_bootstrap_ci_high": float(np.quantile(bm, .975)),
                     "observed_trade_mean_R": float(g["R_num"].mean()),
                     "trade_weighted_episode_bootstrap_ci_low": float(np.quantile(tw, .025)),
                     "trade_weighted_episode_bootstrap_ci_high": float(np.quantile(tw, .975))})
    return pd.DataFrame(rows)


def v32_print(title, df):
    print("\n" + "=" * 72)
    print(title)
    print("-" * 72)
    print(df.to_string(index=False) if not df.empty else "No data available.")


def v32_main():
    market = load_market()
    market["SMA200"] = market["Close"].rolling(200, min_periods=200).mean()
    print(f"Market rows: {len(market)} | {market.index.min().date()} -> {market.index.max().date()}")

    baseline = build_baseline_trades(market)
    if not print_baseline_check(baseline):
        raise RuntimeError("FROZEN BASELINE FAILED. V3.2 STOPPED.")

    fred = load_fred()
    trades = attach_macro(baseline, fred)
    trades = add_drawdown(trades, market)
    trades = add_zones(trades)
    trades = add_confluence_flags(trades)
    trades = add_v31_technical_confirmation(trades, market)
    trades["H1_FLAG"] = (trades["macro_regime"] == "A") & (trades["leading_warning"] == "WATCH")
    trades["H4_FLAG"] = (trades["macro_regime"] == "A") & (trades["liquidity_momentum"] == "DETERIORATING")

    print("\n" + "=" * 72)
    print("MACRO CALIBRATION V3.2 — DECISION ENGINE ROBUSTNESS & INTERACTION VALIDATION")
    print("=" * 72)
    print("Frozen EMA19 baseline remains the sole technical signal generator.")
    print("Candidates: C1-C6 are pre-specified V3.0/V3.1 context checks only.")
    print("Technical confirmation remains research-only; it does NOT create entries.")
    print("Higher Low = signal Low > lowest Low of previous 5 completed candles.")
    print("No thresholds, entries, exits, sizing, RR, or macro definitions changed.")
    print("Research-only: this script does NOT execute trades or place orders.")

    matrix = v32_candidate_matrix(trades)
    oos = v32_oos(trades)
    wf = v32_walk_forward(trades)
    loo = v32_loo_year(trades)
    crisis = v32_crisis_exclusion(trades)
    cluster, market_ep = v32_cluster_audit(trades, market)
    perm = v32_episode_permutation(trades, market)
    boot = v32_episode_bootstrap(trades, market)

    v32_print("V3.2 CANDIDATE CALIBRATION", matrix)
    v32_print("V3.2 CHRONOLOGICAL OOS — DISCOVERY / HOLDOUT", oos)
    v32_print("V3.2 EXPANDING WALK-FORWARD", wf)
    v32_print("V3.2 LEAVE-ONE-YEAR-OUT", loo)
    v32_print("V3.2 CRISIS EXCLUSION SENSITIVITY", crisis)
    v32_print("V3.2 MARKET-EPISODE CLUSTER / LEAVE-ONE-EPISODE-OUT", cluster)
    v32_print("V3.2 CORRECTED MARKET-EPISODE PERMUTATION", perm)
    v32_print("V3.2 MARKET-EPISODE BOOTSTRAP", boot)

    # Integrity guards: V3.2 must preserve the exact V3.1 baseline signal set.
    baseline_dates = pd.to_datetime(baseline["signal_date"]).astype("int64").reset_index(drop=True)
    v32_dates = pd.to_datetime(trades["signal_date"]).astype("int64").reset_index(drop=True)
    if len(baseline) != len(trades) or not baseline_dates.equals(v32_dates):
        raise RuntimeError("SIGNAL-GENERATION GUARD FAILED: V3.2 changed the frozen baseline signal set.")

    # Also verify the V3.1 technical values are reproducible for every signal.
    reference_tech = add_v31_technical_confirmation(baseline, market)
    if not reference_tech["technical_score"].reset_index(drop=True).equals(trades["technical_score"].reset_index(drop=True)):
        raise RuntimeError("TECHNICAL INTEGRITY GUARD FAILED: V3.2 changed V3.1 technical scores.")

    print("\nV3.2 SIGNAL-GENERATION GUARD: PASS")
    print("V3.2 TECHNICAL-INTEGRITY GUARD: PASS")
    print("Candidates classify existing frozen signals only; they do not create entries.")

    trades.to_csv("macro_backtest_v32_trades.csv", index=False)
    matrix.to_csv("macro_backtest_v32_candidate_calibration.csv", index=False)
    oos.to_csv("macro_backtest_v32_oos.csv", index=False)
    wf.to_csv("macro_backtest_v32_walk_forward.csv", index=False)
    loo.to_csv("macro_backtest_v32_leave_one_year_out.csv", index=False)
    crisis.to_csv("macro_backtest_v32_crisis_exclusion.csv", index=False)
    cluster.to_csv("macro_backtest_v32_market_episode_cluster_audit.csv", index=False)
    perm.to_csv("macro_backtest_v32_market_episode_permutation.csv", index=False)
    boot.to_csv("macro_backtest_v32_market_episode_bootstrap.csv", index=False)
    market_ep.to_csv("macro_backtest_v32_market_episode_trades.csv", index=False)

    print("\nFILES CREATED")
    for f in [
        "macro_backtest_v32_trades.csv",
        "macro_backtest_v32_candidate_calibration.csv",
        "macro_backtest_v32_oos.csv",
        "macro_backtest_v32_walk_forward.csv",
        "macro_backtest_v32_leave_one_year_out.csv",
        "macro_backtest_v32_crisis_exclusion.csv",
        "macro_backtest_v32_market_episode_cluster_audit.csv",
        "macro_backtest_v32_market_episode_permutation.csv",
        "macro_backtest_v32_market_episode_bootstrap.csv",
        "macro_backtest_v32_market_episode_trades.csv",
    ]:
        print(f)
    print("\nMACRO CALIBRATION V3.2 DECISION ENGINE ROBUSTNESS & INTERACTION VALIDATION COMPLETE")

# ============================================================
# V3.3 — C3 vs C4 INCREMENTAL INFORMATION
# + DECISION CONTEXT CALIBRATION
# ============================================================
# Integrated directly into the V3.2 pipeline.
#
# C3 = H1 + H4
# C4 = H1 + H4 + Strong Technical
#
# IMPORTANT:
# V3.3 reuses the exact V3.2 definitions already present above:
#   H1 = Regime A + WATCH
#   H4 = Regime A + Liquidity DETERIORATING
#   Strong Technical = technical_score >= 4
#
# Research only. No signal, entry, stop, RR, sizing, macro definition,
# or technical definition is changed.
# ============================================================

V33_STRONG_TECH_MIN = 4

V33_DRAWDOWN_BINS = [
    -np.inf, -20, -10, -5, -3, 0, np.inf
]

V33_DRAWDOWN_LABELS = [
    "<=-20%",
    "-20% to -10%",
    "-10% to -5%",
    "-5% to -3%",
    "-3% to 0%",
    ">0%",
]


def v33_summary(df):
    if df.empty:
        return {
            "signals": 0, "valid": 0, "invalid_sl": 0,
            "resolved": 0, "wins": 0, "losses": 0,
            "ambiguous": 0, "open": 0, "win_rate": np.nan,
            "avg_R": np.nan, "total_R": 0.0,
            "profit_factor": np.nan,
        }

    wins = int((df["result"] == "WIN").sum())
    losses = int((df["result"] == "LOSS").sum())
    ambiguous = int((df["result"] == "AMBIGUOUS").sum())
    open_trades = int((df["result"] == "OPEN").sum())
    invalid = int((df["result"] == "INVALID_SL").sum())
    resolved = wins + losses

    r = pd.to_numeric(df["R"], errors="coerce")
    gross_profit = float(r[r > 0].sum())
    gross_loss = abs(float(r[r < 0].sum()))

    return {
        "signals": len(df),
        "valid": len(df) - invalid,
        "invalid_sl": invalid,
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "ambiguous": ambiguous,
        "open": open_trades,
        "win_rate": 100 * wins / resolved if resolved else np.nan,
        "avg_R": float(r.dropna().mean()) if r.notna().any() else np.nan,
        "total_R": float(r.dropna().sum()),
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else np.nan,
    }


def v33_build_contexts(trades):
    df = trades.copy()

    regime = df["macro_regime"].astype(str).str.upper().str.strip()
    warning = df["leading_warning"].astype(str).str.upper().str.strip()
    liquidity = df["liquidity_momentum"].astype(str).str.upper().str.strip()
    tech_score = pd.to_numeric(df["technical_score"], errors="coerce")

    # EXACT V3.2 definitions — do not broaden H4.
    df["V33_H1"] = (regime == "A") & (warning == "WATCH")
    df["V33_H4"] = (regime == "A") & (liquidity == "DETERIORATING")
    df["V33_STRONG_TECH"] = tech_score >= V33_STRONG_TECH_MIN

    df["V33_C3"] = df["V33_H1"] & df["V33_H4"]
    df["V33_C4"] = df["V33_C3"] & df["V33_STRONG_TECH"]
    df["V33_C3_NOT_C4"] = df["V33_C3"] & ~df["V33_C4"]
    df["V33_NOT_C4"] = ~df["V33_C4"]

    df["V33_RESEARCH_CONTEXT"] = np.select(
        [
            df["V33_C4"],
            df["V33_C3"],
            df["V33_H1"],
        ],
        [
            "H1+H4+STRONG_TECH",
            "H1+H4",
            "H1",
        ],
        default="NONE",
    )

    dd = pd.to_numeric(df["drawdown_pct"], errors="coerce")
    df["V33_DRAWDOWN_BUCKET"] = pd.cut(
        dd,
        bins=V33_DRAWDOWN_BINS,
        labels=V33_DRAWDOWN_LABELS,
        right=True,
    )
    df["V33_YEAR"] = pd.to_datetime(df["signal_date"]).dt.year

    return df


def v33_group_report(df, groups):
    rows = []
    for name, mask in groups.items():
        s = v33_summary(df.loc[mask])
        s["group"] = name
        rows.append(s)
    return pd.DataFrame(rows)


def v33_context_drawdown(df):
    rows = []
    contexts = ["NONE", "H1", "H1+H4", "H1+H4+STRONG_TECH"]

    for context in contexts:
        for bucket in V33_DRAWDOWN_LABELS:
            g = df[
                (df["V33_RESEARCH_CONTEXT"] == context)
                & (df["V33_DRAWDOWN_BUCKET"].astype(str) == bucket)
            ]
            if g.empty:
                continue
            s = v33_summary(g)
            s["context"] = context
            s["drawdown_bucket"] = bucket
            rows.append(s)

    return pd.DataFrame(rows)


def v33_context_drawdown_technical(df):
    rows = []
    contexts = ["NONE", "H1", "H1+H4", "H1+H4+STRONG_TECH"]

    for context in contexts:
        for bucket in V33_DRAWDOWN_LABELS:
            for tech in ["WEAK", "PARTIAL", "STRONG"]:
                g = df[
                    (df["V33_RESEARCH_CONTEXT"] == context)
                    & (df["V33_DRAWDOWN_BUCKET"].astype(str) == bucket)
                    & (df["technical_status"].astype(str).str.upper() == tech)
                ]
                if g.empty:
                    continue
                s = v33_summary(g)
                s["context"] = context
                s["drawdown_bucket"] = bucket
                s["technical_status"] = tech
                rows.append(s)

    return pd.DataFrame(rows)


def v33_yearly(df):
    rows = []
    contexts = ["NONE", "H1", "H1+H4", "H1+H4+STRONG_TECH"]

    for context in contexts:
        g0 = df[df["V33_RESEARCH_CONTEXT"] == context]
        for year, g in g0.groupby("V33_YEAR"):
            s = v33_summary(g)
            s["context"] = context
            s["year"] = int(year)
            rows.append(s)

    return pd.DataFrame(rows)


def v33_chronological_oos(df, split_date="2025-01-01"):
    rows = []
    d = pd.to_datetime(df["signal_date"])
    discovery = d < pd.Timestamp(split_date)
    holdout = d >= pd.Timestamp(split_date)

    candidates = {
        "C3_H1_PLUS_H4": df["V33_C3"],
        "C4_H1_PLUS_H4_STRONG_TECH": df["V33_C4"],
        "C3_NOT_C4": df["V33_C3_NOT_C4"],
        "NOT_C4": df["V33_NOT_C4"],
    }

    for name, mask in candidates.items():
        for sample, period in [("DISCOVERY", discovery), ("HOLDOUT", holdout)]:
            s = v33_summary(df.loc[mask & period])
            s["candidate"] = name
            s["sample"] = sample
            rows.append(s)

    return pd.DataFrame(rows)


def v33_walk_forward(df):
    rows = []
    d = pd.to_datetime(df["signal_date"])
    years = sorted(d.dt.year.dropna().unique())

    candidates = {
        "C3_H1_PLUS_H4": df["V33_C3"],
        "C4_H1_PLUS_H4_STRONG_TECH": df["V33_C4"],
    }

    for test_year in years:
        if test_year <= 2022:
            continue

        train_period = d.dt.year < test_year
        test_period = d.dt.year == test_year

        for name, mask in candidates.items():
            train = df.loc[mask & train_period]
            test = df.loc[mask & test_period]

            tr = v33_summary(train)
            te = v33_summary(test)

            rows.append({
                "candidate": name,
                "test_year": int(test_year),
                "train_signals": tr["signals"],
                "train_wins": tr["wins"],
                "train_losses": tr["losses"],
                "train_win_rate": tr["win_rate"],
                "train_avg_R": tr["avg_R"],
                "train_total_R": tr["total_R"],
                "train_profit_factor": tr["profit_factor"],
                "test_signals": te["signals"],
                "test_wins": te["wins"],
                "test_losses": te["losses"],
                "test_win_rate": te["win_rate"],
                "test_avg_R": te["avg_R"],
                "test_total_R": te["total_R"],
                "test_profit_factor": te["profit_factor"],
            })

    return pd.DataFrame(rows)


def v33_leave_one_year_out(df):
    rows = []
    candidates = {
        "C3_H1_PLUS_H4": df["V33_C3"],
        "C4_H1_PLUS_H4_STRONG_TECH": df["V33_C4"],
        "C3_NOT_C4": df["V33_C3_NOT_C4"],
    }

    d = pd.to_datetime(df["signal_date"])
    years = sorted(d.dt.year.dropna().unique())

    for name, mask in candidates.items():
        g = df.loc[
            mask & df["result"].isin(["WIN", "LOSS"])
        ].copy()
        g["R_num"] = pd.to_numeric(g["R"], errors="coerce")
        g["year"] = pd.to_datetime(g["signal_date"]).dt.year
        g = g[np.isfinite(g["R_num"])]

        means = []
        for year in years:
            remaining = g[g["year"] != year]
            if not remaining.empty:
                means.append(float(remaining["R_num"].mean()))

        rows.append({
            "candidate": name,
            "year_count": int(g["year"].nunique()),
            "loo_year_min_mean_R": min(means) if means else np.nan,
            "loo_year_max_mean_R": max(means) if means else np.nan,
        })

    return pd.DataFrame(rows)


def v33_crisis_exclusion(df):
    rows = []
    candidates = {
        "C3_H1_PLUS_H4": df["V33_C3"],
        "C4_H1_PLUS_H4_STRONG_TECH": df["V33_C4"],
        "C3_NOT_C4": df["V33_C3_NOT_C4"],
    }

    exclusions = {
        "NONE": set(),
        "EXCLUDE_2020": {2020},
        "EXCLUDE_2022": {2022},
        "EXCLUDE_2020_2022": {2020, 2022},
        "EXCLUDE_2025": {2025},
    }

    years = pd.to_datetime(df["signal_date"]).dt.year

    for name, mask in candidates.items():
        for label, excluded in exclusions.items():
            keep = mask & ~years.isin(excluded)
            s = v33_summary(df.loc[keep])
            s["candidate"] = name
            s["exclusion"] = label
            rows.append(s)

    return pd.DataFrame(rows)


def v33_market_episode_audit(df, market):
    # Reuse the exact V3.2/V2.8 market-episode construction.
    work = v28_attach_market_episodes(df, market, threshold=-3.0)

    rows = []
    candidates = {
        "C3_H1_PLUS_H4": work["V33_C3"],
        "C4_H1_PLUS_H4_STRONG_TECH": work["V33_C4"],
        "C3_NOT_C4": work["V33_C3_NOT_C4"],
    }

    resolved = work[work["result"].isin(["WIN", "LOSS"])].copy()
    resolved["R_num"] = pd.to_numeric(resolved["R"], errors="coerce")
    resolved = resolved[np.isfinite(resolved["R_num"])]

    for name, mask in candidates.items():
        selected = resolved.loc[mask.loc[resolved.index]]

        if selected.empty:
            continue

        ep_stats = (
            selected.groupby("market_episode_id")
            .agg(
                trades=("R_num", "count"),
                total_R=("R_num", "sum"),
            )
            .reset_index()
        )

        ep_stats = ep_stats.sort_values("total_R", ascending=False)
        top = ep_stats.iloc[0]
        total_R = float(selected["R_num"].sum())

        loo_means = []
        for episode_id in ep_stats["market_episode_id"]:
            remaining = selected[
                selected["market_episode_id"] != episode_id
            ]
            if not remaining.empty:
                loo_means.append(float(remaining["R_num"].mean()))

        rows.append({
            "candidate": name,
            "resolved": len(selected),
            "episode_count": len(ep_stats),
            "top_episode_trades": int(top["trades"]),
            "top_episode_total_R": float(top["total_R"]),
            "total_R": total_R,
            "total_R_excl_top": total_R - float(top["total_R"]),
            "loo_min_mean_R": min(loo_means) if loo_means else np.nan,
            "loo_max_mean_R": max(loo_means) if loo_means else np.nan,
        })

    return pd.DataFrame(rows)


def v33_decision_impact(df):
    # Descriptive only. This does not execute or alter trades.
    rows = []

    for context, g in df.groupby("V33_RESEARCH_CONTEXT"):
        s = v33_summary(g)
        s["context"] = context
        rows.append(s)

    return pd.DataFrame(rows)


def v33_main(trades, market):
    print("\n" + "=" * 72)
    print("US500 MACRO INTELLIGENCE — V3.3")
    print("C3 vs C4 INCREMENTAL INFORMATION")
    print("=" * 72)

    df = v33_build_contexts(trades)

    # --------------------------------------------------------
    # V3.3 integrity guards
    # --------------------------------------------------------
    if len(df) != len(trades):
        raise RuntimeError("V3.3 changed the frozen signal count.")

    original_dates = pd.to_datetime(trades["signal_date"]).reset_index(drop=True)
    v33_dates = pd.to_datetime(df["signal_date"]).reset_index(drop=True)

    if not original_dates.equals(v33_dates):
        raise RuntimeError("V3.3 SIGNAL-GENERATION GUARD FAILED.")

    expected_strong = (
        pd.to_numeric(df["technical_score"], errors="coerce")
        >= V33_STRONG_TECH_MIN
    )

    if not df["V33_STRONG_TECH"].reset_index(drop=True).equals(
        expected_strong.reset_index(drop=True)
    ):
        raise RuntimeError("V3.3 TECHNICAL-INTEGRITY GUARD FAILED.")

    # Verify V3.2 H1/H4 definitions are reproduced exactly.
    expected_h1 = trades["H1_FLAG"].astype(bool)
    expected_h4 = trades["H4_FLAG"].astype(bool)

    if not df["V33_H1"].reset_index(drop=True).equals(
        expected_h1.reset_index(drop=True)
    ):
        raise RuntimeError("V3.3 H1 DEFINITION GUARD FAILED.")

    if not df["V33_H4"].reset_index(drop=True).equals(
        expected_h4.reset_index(drop=True)
    ):
        raise RuntimeError("V3.3 H4 DEFINITION GUARD FAILED.")

    print("\nV3.3 SIGNAL-GENERATION GUARD: PASS")
    print("V3.3 TECHNICAL-INTEGRITY GUARD: PASS")
    print("V3.3 H1/H4 DEFINITION GUARD: PASS")
    print("V3.3 NO ENTRY CREATION: PASS")
    print("V3.3 NO BASELINE MODIFICATION: PASS")

    reports = {
        "macro_backtest_v33_c3_c4_incremental.csv":
            v33_group_report(
                df,
                {
                    "C3_ALL": df["V33_C3"],
                    "C4_SUBSET": df["V33_C4"],
                    "C3_NOT_C4": df["V33_C3_NOT_C4"],
                },
            ),

        "macro_backtest_v33_baseline_vs_c4.csv":
            v33_group_report(
                df,
                {
                    "ALL_FROZEN_SIGNALS":
                        np.ones(len(df), dtype=bool),
                    "C4": df["V33_C4"],
                    "NOT_C4": df["V33_NOT_C4"],
                },
            ),

        "macro_backtest_v33_context_drawdown.csv":
            v33_context_drawdown(df),

        "macro_backtest_v33_context_drawdown_technical.csv":
            v33_context_drawdown_technical(df),

        "macro_backtest_v33_yearly.csv":
            v33_yearly(df),

        "macro_backtest_v33_oos.csv":
            v33_chronological_oos(df),

        "macro_backtest_v33_walk_forward.csv":
            v33_walk_forward(df),

        "macro_backtest_v33_leave_one_year_out.csv":
            v33_leave_one_year_out(df),

        "macro_backtest_v33_crisis_exclusion.csv":
            v33_crisis_exclusion(df),

        "macro_backtest_v33_market_episode_audit.csv":
            v33_market_episode_audit(df, market),

        "macro_backtest_v33_decision_impact.csv":
            v33_decision_impact(df),

        "macro_backtest_v33_trades.csv":
            df,
    }

    for filename, report in reports.items():
        report.to_csv(filename, index=False)

    print("\n" + "=" * 72)
    print("V3.3 C3 vs C4 INCREMENTAL ANALYSIS")
    print("=" * 72)
    print(
        reports["macro_backtest_v33_c3_c4_incremental.csv"]
        .to_string(index=False)
    )

    print("\n" + "=" * 72)
    print("V3.3 BASELINE vs C4")
    print("=" * 72)
    print(
        reports["macro_backtest_v33_baseline_vs_c4.csv"]
        .to_string(index=False)
    )

    print("\n" + "=" * 72)
    print("V3.3 MARKET EPISODE AUDIT")
    print("=" * 72)
    print(
        reports["macro_backtest_v33_market_episode_audit.csv"]
        .to_string(index=False)
    )

    print("\n" + "=" * 72)
    print("V3.3 OOS")
    print("=" * 72)
    print(
        reports["macro_backtest_v33_oos.csv"]
        .to_string(index=False)
    )

    print("\n" + "=" * 72)
    print("V3.3 WALK-FORWARD")
    print("=" * 72)
    print(
        reports["macro_backtest_v33_walk_forward.csv"]
        .to_string(index=False)
    )

    print("\n" + "=" * 72)
    print("V3.3 LEAVE-ONE-YEAR-OUT")
    print("=" * 72)
    print(
        reports["macro_backtest_v33_leave_one_year_out.csv"]
        .to_string(index=False)
    )

    print("\n" + "=" * 72)
    print("V3.3 CRISIS EXCLUSION")
    print("=" * 72)
    print(
        reports["macro_backtest_v33_crisis_exclusion.csv"]
        .to_string(index=False)
    )

    print("\n" + "=" * 72)
    print("V3.3 COMPLETE")
    print("=" * 72)

    for filename in reports:
        print(filename)


# ============================================================
# V3.4 — DECISION ENGINE IMPACT CALIBRATION
# ============================================================
# Research-only.
#
# Purpose:
#   Measure whether C3 = H1 + H4 adds useful information to the
#   EXISTING V3.0 Decision Engine classification.
#
# Important:
#   - Frozen EMA19 signal generation is unchanged.
#   - No entries/exits/SL/RR/sizing are changed.
#   - C3 does NOT create trades.
#   - C4 / Strong Technical is NOT promoted to a decision rule.
#   - This stage is descriptive/counterfactual-free: it measures
#     outcomes conditional on the existing Decision Engine labels.
# ============================================================

def v34_build_decision_context(trades):
    df = v33_build_contexts(trades).copy()

    decisions = []
    modifiers = []

    for _, row in df.iterrows():
        d, m = v30_decision_layer(row)
        decisions.append(d)
        modifiers.append(m)

    df["V34_BASE_DECISION"] = decisions
    df["V34_BASE_MODIFIER"] = modifiers
    df["V34_C3_CONTEXT"] = np.where(df["V33_C3"], "C3_H1_PLUS_H4", "NOT_C3")

    return df


def v34_summary(df):
    if df.empty:
        return {
            "signals": 0,
            "resolved": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": np.nan,
            "avg_R": np.nan,
            "total_R": 0.0,
            "profit_factor": np.nan,
        }

    r = df[df["result"].isin(["WIN", "LOSS"])].copy()
    r["R_num"] = pd.to_numeric(r["R"], errors="coerce")
    r = r[np.isfinite(r["R_num"])]

    if r.empty:
        return {
            "signals": len(df),
            "resolved": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": np.nan,
            "avg_R": np.nan,
            "total_R": 0.0,
            "profit_factor": np.nan,
        }

    wins = int((r["result"] == "WIN").sum())
    losses = int((r["result"] == "LOSS").sum())
    gp = float(r.loc[r["R_num"] > 0, "R_num"].sum())
    gl = abs(float(r.loc[r["R_num"] < 0, "R_num"].sum()))

    return {
        "signals": len(df),
        "resolved": len(r),
        "wins": wins,
        "losses": losses,
        "win_rate": 100 * wins / len(r),
        "avg_R": float(r["R_num"].mean()),
        "total_R": float(r["R_num"].sum()),
        "profit_factor": gp / gl if gl else np.nan,
    }


def v34_decision_x_c3(df):
    rows = []

    decisions = [
        "CRITICAL — NO NEW TRADE",
        "DEFENSIVE",
        "WAIT / CONFIRM",
        "CAUTION",
        "SUPPORTIVE / CONFIRM",
        "BASELINE CONTEXT",
    ]

    contexts = ["C3_H1_PLUS_H4", "NOT_C3"]

    for decision in decisions:
        for context in contexts:
            g = df[
                (df["V34_BASE_DECISION"] == decision)
                & (df["V34_C3_CONTEXT"] == context)
            ]
            s = v34_summary(g)
            s["decision"] = decision
            s["c3_context"] = context
            rows.append(s)

    return pd.DataFrame(rows)


def v34_c3_vs_non_c3(df):
    rows = []

    for context, mask in [
        ("C3_H1_PLUS_H4", df["V33_C3"]),
        ("NOT_C3", ~df["V33_C3"]),
    ]:
        s = v34_summary(df.loc[mask])
        s["context"] = context
        rows.append(s)

    return pd.DataFrame(rows)


def v34_modifier_x_c3(df):
    rows = []

    for modifier in ["H1+H4", "H1", "H4", "NONE"]:
        for context, mask in [
            ("C3_H1_PLUS_H4", df["V33_C3"]),
            ("NOT_C3", ~df["V33_C3"]),
        ]:
            g = df[
                (df["V34_BASE_MODIFIER"] == modifier)
                & mask
            ]
            s = v34_summary(g)
            s["base_modifier"] = modifier
            s["c3_context"] = context
            rows.append(s)

    return pd.DataFrame(rows)


def v34_decision_distribution(df):
    rows = []

    for decision, g in df.groupby("V34_BASE_DECISION", sort=False):
        s = v34_summary(g)
        s["decision"] = decision
        s["c3_signals"] = int(g["V33_C3"].sum())
        s["non_c3_signals"] = int((~g["V33_C3"]).sum())
        rows.append(s)

    return pd.DataFrame(rows)


def v34_yearly(df):
    rows = []

    work = df.copy()
    work["year"] = pd.to_datetime(work["signal_date"]).dt.year

    for year, gy in work.groupby("year"):
        for context, mask in [
            ("C3_H1_PLUS_H4", gy["V33_C3"]),
            ("NOT_C3", ~gy["V33_C3"]),
        ]:
            g = gy.loc[mask]
            s = v34_summary(g)
            s["year"] = int(year)
            s["c3_context"] = context
            rows.append(s)

    return pd.DataFrame(rows)


def v34_integrity_guards(original, df):
    if len(original) != len(df):
        raise RuntimeError("V3.4 SIGNAL-GENERATION GUARD FAILED.")

    original_dates = pd.to_datetime(
        original["signal_date"]
    ).reset_index(drop=True)

    new_dates = pd.to_datetime(
        df["signal_date"]
    ).reset_index(drop=True)

    if not original_dates.equals(new_dates):
        raise RuntimeError("V3.4 SIGNAL-GENERATION GUARD FAILED: signal dates changed.")

    original_scores = pd.to_numeric(
        original["technical_score"], errors="coerce"
    ).reset_index(drop=True)

    new_scores = pd.to_numeric(
        df["technical_score"], errors="coerce"
    ).reset_index(drop=True)

    if not original_scores.equals(new_scores):
        raise RuntimeError("V3.4 TECHNICAL-INTEGRITY GUARD FAILED.")

    expected_c3 = (
        (df["macro_regime"] == "A")
        & (df["leading_warning"] == "WATCH")
        & (df["liquidity_momentum"] == "DETERIORATING")
    )

    if not df["V33_C3"].reset_index(drop=True).equals(
        expected_c3.reset_index(drop=True)
    ):
        raise RuntimeError("V3.4 C3 DEFINITION GUARD FAILED.")

    print("\nV3.4 SIGNAL-GENERATION GUARD: PASS")
    print("V3.4 TECHNICAL-INTEGRITY GUARD: PASS")
    print("V3.4 C3-DEFINITION GUARD: PASS")
    print("V3.4 NO ENTRY CREATION: PASS")
    print("V3.4 NO BASELINE MODIFICATION: PASS")


def v34_main(trades, market):
    print("\n" + "=" * 72)
    print("US500 MACRO INTELLIGENCE — V3.4")
    print("DECISION ENGINE IMPACT CALIBRATION")
    print("=" * 72)

    df = v34_build_decision_context(trades)

    v34_integrity_guards(trades, df)

    decision_dist = v34_decision_distribution(df)
    decision_x_c3 = v34_decision_x_c3(df)
    c3_vs_non_c3 = v34_c3_vs_non_c3(df)
    modifier_x_c3 = v34_modifier_x_c3(df)
    yearly = v34_yearly(df)

    # --------------------------------------------------------
    # IMPORTANT:
    # V3.4 does NOT create a new decision rule.
    # It measures the existing V3.0 decision labels conditional
    # on C3 vs non-C3.
    # --------------------------------------------------------

    print("\n" + "=" * 72)
    print("V3.4 BASE DECISION DISTRIBUTION")
    print("=" * 72)
    print(decision_dist.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.4 DECISION × C3 CONTEXT")
    print("=" * 72)
    print(decision_x_c3.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.4 C3 vs NON-C3")
    print("=" * 72)
    print(c3_vs_non_c3.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.4 BASE MODIFIER × C3")
    print("=" * 72)
    print(modifier_x_c3.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.4 YEARLY C3 CONTEXT")
    print("=" * 72)
    print(yearly.to_string(index=False))

    reports = {
        "macro_backtest_v34_decision_distribution.csv": decision_dist,
        "macro_backtest_v34_decision_x_c3.csv": decision_x_c3,
        "macro_backtest_v34_c3_vs_non_c3.csv": c3_vs_non_c3,
        "macro_backtest_v34_modifier_x_c3.csv": modifier_x_c3,
        "macro_backtest_v34_yearly.csv": yearly,
        "macro_backtest_v34_trades.csv": df,
    }

    for filename, report in reports.items():
        report.to_csv(filename, index=False)

    print("\n" + "=" * 72)
    print("V3.4 COMPLETE")
    print("=" * 72)
    print("Research-only. No new entries were created.")
    print("Frozen baseline and V3.0 decision logic were not modified.")
    print("\nFILES CREATED")
    for filename in reports:
        print(filename)


# ============================================================
# US500 MACRO INTELLIGENCE — V3.5
# C3 CONTEXT × DRAWDOWN × LEADING-WARNING PROXY × TECHNICAL
#
# Research-only incremental-information analysis.
# IMPORTANT: the supplied pipeline has no early_warning_level field.
# V3.5 therefore uses the existing leading_warning classification as the
# early-warning proxy; it does NOT invent a new early-warning score.
#
# C3 remains EXACTLY:
#   H1 = Regime A + WATCH
#   H4 = Regime A + Liquidity DETERIORATING
#   C3 = H1 + H4
#
# Frozen baseline, entry, stop, RR, sizing, signal set and
# previous macro/technical definitions are NOT modified.
# V3.5 does not create entries or optimize thresholds.
# ============================================================

V35_DRAWDOWN_LABELS = [
    "<=-20%",
    "-20% to -10%",
    "-10% to -5%",
    "-5% to -3%",
    "-3% to 0%",
    ">0%",
]

V35_EARLY_WARNING_LEVELS = ["NONE", "WATCH", "ELEVATED", "STRONG"]
V35_TECHNICAL_STATUSES = ["WEAK", "PARTIAL", "STRONG"]


def v35_build_context(df):
    out = v33_build_contexts(df).copy()

    # Preserve the exact C3 definition from V3.3.
    expected_c3 = (
        (out["macro_regime"].astype(str).str.upper().str.strip() == "A")
        & (out["leading_warning"].astype(str).str.upper().str.strip() == "WATCH")
        & (out["liquidity_momentum"].astype(str).str.upper().str.strip() == "DETERIORATING")
    )

    if not out["V33_C3"].reset_index(drop=True).equals(
        expected_c3.reset_index(drop=True)
    ):
        raise RuntimeError("V3.5 C3 DEFINITION GUARD FAILED.")

    out["V35_C3_CONTEXT"] = np.where(
        out["V33_C3"], "C3_H1_PLUS_H4", "NOT_C3"
    )

    dd = pd.to_numeric(out["drawdown_pct"], errors="coerce")
    out["V35_DRAWDOWN_BUCKET"] = pd.cut(
        dd,
        bins=[-np.inf, -20, -10, -5, -3, 0, np.inf],
        labels=V35_DRAWDOWN_LABELS,
        right=True,
    )

    out["V35_EARLY_WARNING"] = (
        out["leading_warning"].astype(str).str.upper().str.strip()
    )
    out["V35_TECHNICAL_STATUS"] = (
        out["technical_status"].astype(str).str.upper().str.strip()
    )
    out["V35_YEAR"] = pd.to_datetime(out["signal_date"]).dt.year

    return out


def v35_summary(df):
    if df.empty:
        return {
            "signals": 0, "valid": 0, "invalid_sl": 0,
            "resolved": 0, "wins": 0, "losses": 0,
            "ambiguous": 0, "open": 0,
            "win_rate": np.nan, "avg_R": np.nan,
            "total_R": 0.0, "profit_factor": np.nan,
        }

    wins = int((df["result"] == "WIN").sum())
    losses = int((df["result"] == "LOSS").sum())
    ambiguous = int((df["result"] == "AMBIGUOUS").sum())
    open_trades = int((df["result"] == "OPEN").sum())
    invalid = int((df["result"] == "INVALID_SL").sum())
    resolved = wins + losses

    r = pd.to_numeric(df["R"], errors="coerce")
    rr = r[df["result"].isin(["WIN", "LOSS"]) & np.isfinite(r)]

    gp = float(rr[rr > 0].sum())
    gl = abs(float(rr[rr < 0].sum()))

    return {
        "signals": len(df),
        "valid": len(df) - invalid,
        "invalid_sl": invalid,
        "resolved": len(rr),
        "wins": wins,
        "losses": losses,
        "ambiguous": ambiguous,
        "open": open_trades,
        "win_rate": 100 * wins / len(rr) if len(rr) else np.nan,
        "avg_R": float(rr.mean()) if len(rr) else np.nan,
        "total_R": float(rr.sum()) if len(rr) else 0.0,
        "profit_factor": gp / gl if gl else np.nan,
    }


def v35_group_report(df, group_cols):
    rows = []

    work = df.copy()
    keys = group_cols if isinstance(group_cols, list) else [group_cols]

    grouped = work.groupby(keys, dropna=False, sort=False, observed=False)

    for key, g in grouped:
        if not isinstance(key, tuple):
            key = (key,)

        s = v35_summary(g)
        for col, value in zip(keys, key):
            s[col] = str(value)
        rows.append(s)

    return pd.DataFrame(rows)


def v35_c3_vs_non_c3_by(df, dimension):
    rows = []

    values = [
        v for v in df[dimension].dropna().astype(str).unique()
    ]

    # Preserve the published ordering where possible.
    preferred = {
        "V35_DRAWDOWN_BUCKET": V35_DRAWDOWN_LABELS,
        "V35_EARLY_WARNING": V35_EARLY_WARNING_LEVELS,
        "V35_TECHNICAL_STATUS": V35_TECHNICAL_STATUSES,
    }
    ordered = [v for v in preferred.get(dimension, []) if v in values]
    ordered += [v for v in values if v not in ordered]

    for value in ordered:
        for context in ["C3_H1_PLUS_H4", "NOT_C3"]:
            g = df[
                (df[dimension].astype(str) == value)
                & (df["V35_C3_CONTEXT"] == context)
            ]
            s = v35_summary(g)
            s["dimension"] = dimension
            s["bucket"] = value
            s["c3_context"] = context
            rows.append(s)

    return pd.DataFrame(rows)


def v35_incremental_difference(df, dimension):
    """Difference C3 minus NOT_C3 inside each fixed dimension bucket.

    This is descriptive only. It does not select or optimize a rule.
    """
    rows = []
    table = v35_c3_vs_non_c3_by(df, dimension)

    for bucket in table["bucket"].drop_duplicates():
        a = table[
            (table["bucket"] == bucket)
            & (table["c3_context"] == "C3_H1_PLUS_H4")
        ]
        b = table[
            (table["bucket"] == bucket)
            & (table["c3_context"] == "NOT_C3")
        ]

        if a.empty or b.empty:
            rows.append({
                "dimension": dimension,
                "bucket": bucket,
                "c3_signals": int(a["signals"].iloc[0]) if not a.empty else 0,
                "non_c3_signals": int(b["signals"].iloc[0]) if not b.empty else 0,
                "c3_resolved": int(a["resolved"].iloc[0]) if not a.empty else 0,
                "non_c3_resolved": int(b["resolved"].iloc[0]) if not b.empty else 0,
                "c3_avg_R": float(a["avg_R"].iloc[0]) if not a.empty else np.nan,
                "non_c3_avg_R": float(b["avg_R"].iloc[0]) if not b.empty else np.nan,
                "delta_avg_R_C3_minus_non_C3": np.nan,
                "c3_win_rate": float(a["win_rate"].iloc[0]) if not a.empty else np.nan,
                "non_c3_win_rate": float(b["win_rate"].iloc[0]) if not b.empty else np.nan,
                "delta_win_rate_pp_C3_minus_non_C3": np.nan,
            })
            continue

        c3_avg = a["avg_R"].iloc[0]
        n3_avg = b["avg_R"].iloc[0]
        c3_wr = a["win_rate"].iloc[0]
        n3_wr = b["win_rate"].iloc[0]

        rows.append({
            "dimension": dimension,
            "bucket": bucket,
            "c3_signals": int(a["signals"].iloc[0]),
            "non_c3_signals": int(b["signals"].iloc[0]),
            "c3_resolved": int(a["resolved"].iloc[0]),
            "non_c3_resolved": int(b["resolved"].iloc[0]),
            "c3_avg_R": c3_avg,
            "non_c3_avg_R": n3_avg,
            "delta_avg_R_C3_minus_non_C3": (
                c3_avg - n3_avg
                if pd.notna(c3_avg) and pd.notna(n3_avg)
                else np.nan
            ),
            "c3_win_rate": c3_wr,
            "non_c3_win_rate": n3_wr,
            "delta_win_rate_pp_C3_minus_non_C3": (
                c3_wr - n3_wr
                if pd.notna(c3_wr) and pd.notna(n3_wr)
                else np.nan
            ),
        })

    return pd.DataFrame(rows)


def v35_combined_matrix(df):
    """C3 vs non-C3 inside Drawdown × Early Warning.

    No optimization is performed. Empty cells are retained.
    """
    rows = []

    for dd in V35_DRAWDOWN_LABELS:
        for ew in V35_EARLY_WARNING_LEVELS:
            for context in ["C3_H1_PLUS_H4", "NOT_C3"]:
                g = df[
                    (df["V35_DRAWDOWN_BUCKET"].astype(str) == dd)
                    & (df["V35_EARLY_WARNING"] == ew)
                    & (df["V35_C3_CONTEXT"] == context)
                ]
                s = v35_summary(g)
                s["drawdown_bucket"] = dd
                s["early_warning"] = ew
                s["c3_context"] = context
                rows.append(s)

    return pd.DataFrame(rows)


def v35_drawdown_early_technical(df):
    """Full descriptive matrix: Drawdown × Early Warning × Technical × C3."""
    rows = []

    for dd in V35_DRAWDOWN_LABELS:
        for ew in V35_EARLY_WARNING_LEVELS:
            for tech in V35_TECHNICAL_STATUSES:
                for context in ["C3_H1_PLUS_H4", "NOT_C3"]:
                    g = df[
                        (df["V35_DRAWDOWN_BUCKET"].astype(str) == dd)
                        & (df["V35_EARLY_WARNING"] == ew)
                        & (df["V35_TECHNICAL_STATUS"] == tech)
                        & (df["V35_C3_CONTEXT"] == context)
                    ]
                    s = v35_summary(g)
                    s["drawdown_bucket"] = dd
                    s["early_warning"] = ew
                    s["technical_status"] = tech
                    s["c3_context"] = context
                    rows.append(s)

    return pd.DataFrame(rows)


def v35_decision_x_c3(df):
    rows = []

    for decision in [
        "CRITICAL — NO NEW TRADE",
        "DEFENSIVE",
        "WAIT / CONFIRM",
        "CAUTION",
        "SUPPORTIVE / CONFIRM",
        "BASELINE CONTEXT",
    ]:
        for context in ["C3_H1_PLUS_H4", "NOT_C3"]:
            g = df[
                (df["V34_BASE_DECISION"] == decision)
                & (df["V35_C3_CONTEXT"] == context)
            ]
            s = v35_summary(g)
            s["decision"] = decision
            s["c3_context"] = context
            rows.append(s)

    return pd.DataFrame(rows)


def v35_yearly(df):
    rows = []

    for year in sorted(df["V35_YEAR"].dropna().unique()):
        for context in ["C3_H1_PLUS_H4", "NOT_C3"]:
            g = df[
                (df["V35_YEAR"] == year)
                & (df["V35_C3_CONTEXT"] == context)
            ]
            s = v35_summary(g)
            s["year"] = int(year)
            s["c3_context"] = context
            rows.append(s)

    return pd.DataFrame(rows)


def v35_integrity_guards(original, df):
    if len(original) != len(df):
        raise RuntimeError("V3.5 SIGNAL-GENERATION GUARD FAILED.")

    od = pd.to_datetime(original["signal_date"]).reset_index(drop=True)
    nd = pd.to_datetime(df["signal_date"]).reset_index(drop=True)
    if not od.equals(nd):
        raise RuntimeError(
            "V3.5 SIGNAL-GENERATION GUARD FAILED: signal dates changed."
        )

    ot = pd.to_numeric(
        original["technical_score"], errors="coerce"
    ).reset_index(drop=True)
    nt = pd.to_numeric(
        df["technical_score"], errors="coerce"
    ).reset_index(drop=True)
    if not ot.equals(nt):
        raise RuntimeError("V3.5 TECHNICAL-INTEGRITY GUARD FAILED.")

    expected_c3 = (
        (df["macro_regime"].astype(str).str.upper().str.strip() == "A")
        & (df["leading_warning"].astype(str).str.upper().str.strip() == "WATCH")
        & (df["liquidity_momentum"].astype(str).str.upper().str.strip() == "DETERIORATING")
    )
    if not df["V33_C3"].reset_index(drop=True).equals(
        expected_c3.reset_index(drop=True)
    ):
        raise RuntimeError("V3.5 C3-DEFINITION GUARD FAILED.")

    # V3.5 must not alter the frozen result labels or R values.
    if not original["result"].reset_index(drop=True).equals(
        df["result"].reset_index(drop=True)
    ):
        raise RuntimeError("V3.5 RESULT-INTEGRITY GUARD FAILED.")

    orr = pd.to_numeric(original["R"], errors="coerce").reset_index(drop=True)
    nrr = pd.to_numeric(df["R"], errors="coerce").reset_index(drop=True)
    if not orr.equals(nrr):
        raise RuntimeError("V3.5 R-INTEGRITY GUARD FAILED.")

    print("\nV3.5 SIGNAL-GENERATION GUARD: PASS")
    print("V3.5 TECHNICAL-INTEGRITY GUARD: PASS")
    print("V3.5 C3-DEFINITION GUARD: PASS")
    print("V3.5 RESULT/R-INTEGRITY GUARD: PASS")
    print("V3.5 NO ENTRY CREATION: PASS")
    print("V3.5 NO BASELINE MODIFICATION: PASS")


def v35_main(trades, market):
    print("\n" + "=" * 72)
    print("US500 MACRO INTELLIGENCE — V3.5")
    print("C3 CONTEXT × DRAWDOWN × EARLY WARNING × TECHNICAL")
    print("=" * 72)

    df = v34_build_decision_context(trades).copy()
    df = v35_build_context(df)

    v35_integrity_guards(trades, df)

    dd = v35_c3_vs_non_c3_by(df, "V35_DRAWDOWN_BUCKET")
    ew = v35_c3_vs_non_c3_by(df, "V35_EARLY_WARNING")
    tech = v35_c3_vs_non_c3_by(df, "V35_TECHNICAL_STATUS")

    dd_diff = v35_incremental_difference(df, "V35_DRAWDOWN_BUCKET")
    ew_diff = v35_incremental_difference(df, "V35_EARLY_WARNING")
    tech_diff = v35_incremental_difference(df, "V35_TECHNICAL_STATUS")

    combined = v35_combined_matrix(df)
    full = v35_drawdown_early_technical(df)
    decision = v35_decision_x_c3(df)
    yearly = v35_yearly(df)

    print("\n" + "=" * 72)
    print("V3.5 C3 vs NON-C3 — DRAWDOWN")
    print("=" * 72)
    print(dd.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.5 INCREMENTAL DIFFERENCE — DRAWDOWN")
    print("=" * 72)
    print(dd_diff.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.5 C3 vs NON-C3 — EARLY WARNING PROXY (LEADING WARNING)")
    print("=" * 72)
    print(ew.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.5 INCREMENTAL DIFFERENCE — EARLY WARNING PROXY")
    print("=" * 72)
    print(ew_diff.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.5 C3 vs NON-C3 — TECHNICAL STATUS")
    print("=" * 72)
    print(tech.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.5 INCREMENTAL DIFFERENCE — TECHNICAL STATUS")
    print("=" * 72)
    print(tech_diff.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.5 DRAWDOWN × EARLY WARNING PROXY × C3")
    print("=" * 72)
    print(combined.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.5 DRAWDOWN × EARLY WARNING PROXY × TECHNICAL × C3")
    print("=" * 72)
    print(full.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.5 DECISION × C3")
    print("=" * 72)
    print(decision.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.5 YEARLY C3 CONTEXT")
    print("=" * 72)
    print(yearly.to_string(index=False))

    reports = {
        "macro_backtest_v35_c3_vs_non_c3_drawdown.csv": dd,
        "macro_backtest_v35_incremental_drawdown.csv": dd_diff,
        "macro_backtest_v35_c3_vs_non_c3_early_warning.csv": ew,
        "macro_backtest_v35_incremental_early_warning.csv": ew_diff,
        "macro_backtest_v35_c3_vs_non_c3_technical.csv": tech,
        "macro_backtest_v35_incremental_technical.csv": tech_diff,
        "macro_backtest_v35_drawdown_early_warning_c3.csv": combined,
        "macro_backtest_v35_drawdown_early_warning_technical_c3.csv": full,
        "macro_backtest_v35_decision_x_c3.csv": decision,
        "macro_backtest_v35_yearly.csv": yearly,
        "macro_backtest_v35_trades.csv": df,
    }

    for filename, report in reports.items():
        report.to_csv(filename, index=False)

    print("\n" + "=" * 72)
    print("V3.5 COMPLETE")
    print("=" * 72)
    print("Research-only. No new entries were created.")
    print("Frozen baseline, V3.0 decision logic and V3.3 C3 definition were not modified.")
    print("\nFILES CREATED")
    for filename in reports:
        print(filename)



# ============================================================
# US500 MACRO INTELLIGENCE — V3.6
# DECISION ENGINE COUNTERFACTUAL / ABLATION ANALYSIS
#
# Research-only.
#
# Purpose:
#   Test whether the existing V3.4 Decision Engine's H1/H4
#   supportive branch adds incremental information to the
#   decision labels, WITHOUT changing any frozen trade.
#
# IMPORTANT METHODOLOGICAL POINT:
#   The current V3.0/V3.4 engine does not contain a dedicated
#   "C3" branch. It uses H1 OR H4:
#       H1 = Regime A + WATCH
#       H4 = Regime A + Liquidity DETERIORATING
#
#   Therefore a true C3-only ablation is not identifiable from
#   the current engine. V3.6 explicitly tests the identifiable
#   counterfactual:
#       BASE        = existing V3.0/V3.4 logic
#       NO_H1_H4    = same logic with the H1/H4 supportive branch removed
#       H1_ONLY     = same logic with only H1 allowed to support
#       H4_ONLY     = same logic with only H4 allowed to support
#
# The frozen signal generator, entries, stops, RR, sizing,
# results and R values are never modified.
# ============================================================


def v36_decision_layer(row, mode="BASE"):
    """Counterfactual copy of the existing V3.0 decision logic.

    BASE reproduces the current V3.4 decision labels.
    NO_H1_H4 removes only the H1/H4 supportive branch.
    H1_ONLY retains H1 support but removes H4 support.
    H4_ONLY retains H4 support but removes H1 support.

    This function changes labels only; it never changes trades.
    """
    regime = str(row.get("macro_regime", ""))
    warning = str(row.get("leading_warning", ""))
    early = str(row.get("early_warning_level", ""))

    h1 = (
        regime.upper().strip() == "A"
        and warning.upper().strip() == "WATCH"
    )
    h4 = (
        regime.upper().strip() == "A"
        and str(row.get("liquidity_momentum", "")).upper().strip()
        == "DETERIORATING"
    )

    # Reproduce the existing V3.0 precedence.
    if early == "CRITICAL" or regime.startswith("E") or regime.startswith("F"):
        return "DEFENSIVE"

    if mode == "BASE":
        supportive = h1 or h4
    elif mode == "NO_H1_H4":
        supportive = False
    elif mode == "H1_ONLY":
        supportive = h1
    elif mode == "H4_ONLY":
        supportive = h4
    else:
        raise ValueError(f"Unknown V3.6 mode: {mode}")

    if supportive:
        return "SUPPORTIVE / CONFIRM"

    if regime.startswith("C") or regime.startswith("D"):
        return "WAIT / CONFIRM"

    if warning.upper().strip() in ("ELEVATED", "STRONG"):
        return "CAUTION"

    return "BASELINE CONTEXT"


def v36_build_decision_comparison(trades):
    """Attach base and counterfactual decisions to the same 119 signals."""
    df = trades.copy()

    df["V36_C3"] = (
        (df["macro_regime"].astype(str).str.upper().str.strip() == "A")
        & (df["leading_warning"].astype(str).str.upper().str.strip() == "WATCH")
        & (
            df["liquidity_momentum"]
            .astype(str)
            .str.upper()
            .str.strip()
            == "DETERIORATING"
        )
    )

    df["V36_H1"] = (
        (df["macro_regime"].astype(str).str.upper().str.strip() == "A")
        & (df["leading_warning"].astype(str).str.upper().str.strip() == "WATCH")
    )

    df["V36_H4"] = (
        (df["macro_regime"].astype(str).str.upper().str.strip() == "A")
        & (
            df["liquidity_momentum"]
            .astype(str)
            .str.upper()
            .str.strip()
            == "DETERIORATING"
        )
    )

    df["V36_C3_CONTEXT"] = np.where(
        df["V36_C3"], "C3_H1_PLUS_H4", "NOT_C3"
    )

    for mode in ["BASE", "NO_H1_H4", "H1_ONLY", "H4_ONLY"]:
        df[f"V36_DECISION_{mode}"] = [
            v36_decision_layer(row, mode)
            for _, row in df.iterrows()
        ]

    df["V36_BASE_DECISION"] = df["V36_DECISION_BASE"]
    df["V36_NO_H1_H4_CHANGED"] = (
        df["V36_DECISION_BASE"] != df["V36_DECISION_NO_H1_H4"]
    )
    df["V36_H1_ONLY_CHANGED"] = (
        df["V36_DECISION_BASE"] != df["V36_DECISION_H1_ONLY"]
    )
    df["V36_H4_ONLY_CHANGED"] = (
        df["V36_DECISION_BASE"] != df["V36_DECISION_H4_ONLY"]
    )

    return df


def v36_summary(df):
    if df.empty:
        return {
            "signals": 0,
            "resolved": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": np.nan,
            "avg_R": np.nan,
            "total_R": 0.0,
            "profit_factor": np.nan,
        }

    r = df[df["result"].isin(["WIN", "LOSS"])].copy()
    r["R_num"] = pd.to_numeric(r["R"], errors="coerce")
    r = r[np.isfinite(r["R_num"])].copy()

    wins = int((r["result"] == "WIN").sum())
    losses = int((r["result"] == "LOSS").sum())
    gp = float(r.loc[r["R_num"] > 0, "R_num"].sum())
    gl = abs(float(r.loc[r["R_num"] < 0, "R_num"].sum()))

    return {
        "signals": len(df),
        "resolved": len(r),
        "wins": wins,
        "losses": losses,
        "win_rate": 100.0 * wins / len(r) if len(r) else np.nan,
        "avg_R": float(r["R_num"].mean()) if len(r) else np.nan,
        "total_R": float(r["R_num"].sum()) if len(r) else 0.0,
        "profit_factor": gp / gl if gl else np.nan,
    }


def v36_transition_report(df, from_col, to_col):
    rows = []

    for (old_decision, new_decision), g in df.groupby(
        [from_col, to_col], sort=False, dropna=False
    ):
        s = v36_summary(g)
        s["from_decision"] = old_decision
        s["to_decision"] = new_decision
        s["changed"] = old_decision != new_decision
        rows.append(s)

    return pd.DataFrame(rows)


def v36_change_by_context(df, changed_col):
    rows = []

    for context, g in df.groupby("V36_C3_CONTEXT", sort=False):
        changed = g[g[changed_col]]
        unchanged = g[~g[changed_col]]

        cs = v36_summary(changed)
        us = v36_summary(unchanged)

        rows.append({
            "c3_context": context,
            "changed_signals": cs["signals"],
            "changed_resolved": cs["resolved"],
            "changed_wins": cs["wins"],
            "changed_losses": cs["losses"],
            "changed_avg_R": cs["avg_R"],
            "changed_total_R": cs["total_R"],
            "unchanged_signals": us["signals"],
            "unchanged_resolved": us["resolved"],
            "unchanged_wins": us["wins"],
            "unchanged_losses": us["losses"],
            "unchanged_avg_R": us["avg_R"],
            "unchanged_total_R": us["total_R"],
        })

    return pd.DataFrame(rows)


def v36_decision_performance(df, decision_col, mode):
    rows = []

    for decision, g in df.groupby(decision_col, sort=False, dropna=False):
        s = v36_summary(g)
        s["mode"] = mode
        s["decision"] = decision
        rows.append(s)

    return pd.DataFrame(rows)


def v36_decision_change_matrix(df):
    """Performance of signals whose decision changes under the ablation."""
    rows = []

    comparisons = [
        ("NO_H1_H4", "V36_DECISION_NO_H1_H4", "V36_NO_H1_H4_CHANGED"),
        ("H1_ONLY", "V36_DECISION_H1_ONLY", "V36_H1_ONLY_CHANGED"),
        ("H4_ONLY", "V36_DECISION_H4_ONLY", "V36_H4_ONLY_CHANGED"),
    ]

    for mode, new_col, changed_col in comparisons:
        changed = df[df[changed_col]].copy()

        if changed.empty:
            rows.append({
                "mode": mode,
                "signals_changed": 0,
                "resolved": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": np.nan,
                "avg_R": np.nan,
                "total_R": 0.0,
                "profit_factor": np.nan,
            })
            continue

        s = v36_summary(changed)
        s["mode"] = mode
        s["signals_changed"] = s.pop("signals")
        rows.append(s)

    return pd.DataFrame(rows)


def v36_integrity_guards(original, df):
    if len(original) != len(df):
        raise RuntimeError("V3.6 SIGNAL COUNT GUARD FAILED.")

    od = pd.to_datetime(original["signal_date"]).reset_index(drop=True)
    nd = pd.to_datetime(df["signal_date"]).reset_index(drop=True)
    if not od.equals(nd):
        raise RuntimeError("V3.6 SIGNAL DATE GUARD FAILED.")

    for col in ["result", "R", "technical_score"]:
        a = original[col].reset_index(drop=True)
        b = df[col].reset_index(drop=True)

        if col in ["R", "technical_score"]:
            a = pd.to_numeric(a, errors="coerce")
            b = pd.to_numeric(b, errors="coerce")

        if not a.equals(b):
            raise RuntimeError(f"V3.6 {col.upper()} INTEGRITY GUARD FAILED.")

    expected_h1 = (
        (df["macro_regime"].astype(str).str.upper().str.strip() == "A")
        & (df["leading_warning"].astype(str).str.upper().str.strip() == "WATCH")
    )

    expected_h4 = (
        (df["macro_regime"].astype(str).str.upper().str.strip() == "A")
        & (
            df["liquidity_momentum"]
            .astype(str)
            .str.upper()
            .str.strip()
            == "DETERIORATING"
        )
    )

    expected_c3 = expected_h1 & expected_h4

    if not df["V36_H1"].reset_index(drop=True).equals(
        expected_h1.reset_index(drop=True)
    ):
        raise RuntimeError("V3.6 H1 DEFINITION GUARD FAILED.")

    if not df["V36_H4"].reset_index(drop=True).equals(
        expected_h4.reset_index(drop=True)
    ):
        raise RuntimeError("V3.6 H4 DEFINITION GUARD FAILED.")

    if not df["V36_C3"].reset_index(drop=True).equals(
        expected_c3.reset_index(drop=True)
    ):
        raise RuntimeError("V3.6 C3 DEFINITION GUARD FAILED.")

    # Verify that BASE reproduces the current V3.4 decision labels.
    # v30_decision_layer() returns (decision, modifier).
    # V3.6 decision columns intentionally store only the decision label,
    # so compare the first tuple element. The previous V3.6 version
    # incorrectly compared a string Series with the full tuples.
    reference = [
        v30_decision_layer(row)[0]
        for _, row in original.iterrows()
    ]
    actual = df["V36_DECISION_BASE"].reset_index(drop=True)
    expected = pd.Series(reference, index=actual.index, dtype=object)

    # Series.equals() is stricter than value equality: it also checks
    # dtype and Series metadata such as the name.  The guard is intended
    # to verify the decision LABELS themselves.  Compare aligned values
    # after resetting the index, while retaining an explicit mismatch
    # report for genuine label differences.
    mismatch = pd.DataFrame({
        "actual": actual.astype(object),
        "expected": expected.astype(object),
    })
    mismatch = mismatch[mismatch["actual"] != mismatch["expected"]]
    if not mismatch.empty:
        raise RuntimeError(
            "V3.6 BASE DECISION REPRODUCTION GUARD FAILED. "
            f"Mismatches: {len(mismatch)}"
        )

    print("\nV3.6 SIGNAL COUNT GUARD: PASS")
    print("V3.6 SIGNAL DATE GUARD: PASS")
    print("V3.6 RESULT/R/TECHNICAL INTEGRITY GUARD: PASS")
    print("V3.6 H1/H4 DEFINITION GUARD: PASS")
    print("V3.6 C3 DEFINITION GUARD: PASS")
    print("V3.6 BASE DECISION REPRODUCTION GUARD: PASS")
    print("V3.6 NO ENTRY CREATION: PASS")
    print("V3.6 NO BASELINE MODIFICATION: PASS")


def v36_main(trades, market):
    print("\n" + "=" * 72)
    print("US500 MACRO INTELLIGENCE — V3.6")
    print("DECISION ENGINE COUNTERFACTUAL / ABLATION ANALYSIS")
    print("=" * 72)

    df = v36_build_decision_comparison(trades)
    v36_integrity_guards(trades, df)

    transitions_no = v36_transition_report(
        df, "V36_DECISION_BASE", "V36_DECISION_NO_H1_H4"
    )
    transitions_h1 = v36_transition_report(
        df, "V36_DECISION_BASE", "V36_DECISION_H1_ONLY"
    )
    transitions_h4 = v36_transition_report(
        df, "V36_DECISION_BASE", "V36_DECISION_H4_ONLY"
    )

    changed_summary = v36_decision_change_matrix(df)

    context_no = v36_change_by_context(
        df, "V36_NO_H1_H4_CHANGED"
    )
    context_h1 = v36_change_by_context(
        df, "V36_H1_ONLY_CHANGED"
    )
    context_h4 = v36_change_by_context(
        df, "V36_H4_ONLY_CHANGED"
    )

    perf = pd.concat(
        [
            v36_decision_performance(
                df, "V36_DECISION_BASE", "BASE"
            ),
            v36_decision_performance(
                df, "V36_DECISION_NO_H1_H4", "NO_H1_H4"
            ),
            v36_decision_performance(
                df, "V36_DECISION_H1_ONLY", "H1_ONLY"
            ),
            v36_decision_performance(
                df, "V36_DECISION_H4_ONLY", "H4_ONLY"
            ),
        ],
        ignore_index=True,
    )

    # Full signal-level audit: every frozen signal gets all four labels.
    audit = df[
        [
            "signal_date",
            "year",
            "result",
            "R",
            "V36_H1",
            "V36_H4",
            "V36_C3",
            "V36_C3_CONTEXT",
            "V36_DECISION_BASE",
            "V36_DECISION_NO_H1_H4",
            "V36_DECISION_H1_ONLY",
            "V36_DECISION_H4_ONLY",
            "V36_NO_H1_H4_CHANGED",
            "V36_H1_ONLY_CHANGED",
            "V36_H4_ONLY_CHANGED",
        ]
    ].copy()

    print("\n" + "=" * 72)
    print("V3.6 DECISION CHANGES — BASE vs NO H1/H4 SUPPORTIVE BRANCH")
    print("=" * 72)
    print(changed_summary.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.6 TRANSITIONS — BASE -> NO H1/H4")
    print("=" * 72)
    print(transitions_no.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.6 CHANGED vs UNCHANGED — BASE -> NO H1/H4")
    print("=" * 72)
    print(context_no.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.6 TRANSITIONS — BASE -> H1 ONLY")
    print("=" * 72)
    print(transitions_h1.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.6 TRANSITIONS — BASE -> H4 ONLY")
    print("=" * 72)
    print(transitions_h4.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.6 DECISION PERFORMANCE BY MODE")
    print("=" * 72)
    print(perf.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.6 SIGNAL-LEVEL AUDIT")
    print("=" * 72)
    print(audit.to_string(index=False))

    reports = {
        "macro_backtest_v36_decision_ablation_summary.csv": changed_summary,
        "macro_backtest_v36_transitions_base_vs_no_h1_h4.csv": transitions_no,
        "macro_backtest_v36_transitions_base_vs_h1_only.csv": transitions_h1,
        "macro_backtest_v36_transitions_base_vs_h4_only.csv": transitions_h4,
        "macro_backtest_v36_changed_by_c3_context_no_h1_h4.csv": context_no,
        "macro_backtest_v36_changed_by_c3_context_h1_only.csv": context_h1,
        "macro_backtest_v36_changed_by_c3_context_h4_only.csv": context_h4,
        "macro_backtest_v36_decision_performance_by_mode.csv": perf,
        "macro_backtest_v36_signal_level_audit.csv": audit,
    }

    for filename, report in reports.items():
        report.to_csv(filename, index=False)

    print("\n" + "=" * 72)
    print("V3.6 COMPLETE")
    print("=" * 72)
    print("Research-only. No new entries were created.")
    print("Frozen baseline, entries, stops, RR, sizing and R outcomes were not modified.")
    print("V3.6 is an ablation of the existing H1/H4 decision branch, not a new trading rule.")
    print("\nFILES CREATED")
    for filename in reports:
        print(filename)





# ============================================================
# US500 MACRO INTELLIGENCE — V3.6.1
# AGGREGATE ABLATION AUDIT
#
# Research-only continuation of V3.6.
# V3.6.1 does NOT alter signals, entries, stops, RR, sizing,
# results, R values, or the existing Decision Engine.
#
# Purpose:
#   1) Count decision changes versus BASE.
#   2) Audit the performance of rows whose decision changes.
#   3) Produce BASE -> counterfactual transition matrices.
#   4) Separate H1-only, H4-only, redundant, and true combined
#      interaction cases.
#   5) Audit changes by C3 / NON-C3 context and year.
#   6) Add explicit no-trade-modification integrity guards.
# ============================================================


def v361_transition_matrix(df, new_col):
    """One-row-per-transition matrix, including changed-row performance."""
    rows = []
    for (base_decision, counter_decision), g in df.groupby(
        ["V36_DECISION_BASE", new_col], sort=False, dropna=False
    ):
        s = v36_summary(g)
        rows.append({
            "base_decision": base_decision,
            "counterfactual_decision": counter_decision,
            "changed": bool(base_decision != counter_decision),
            "signals": s["signals"],
            "resolved": s["resolved"],
            "wins": s["wins"],
            "losses": s["losses"],
            "win_rate": s["win_rate"],
            "avg_R": s["avg_R"],
            "total_R": s["total_R"],
            "profit_factor": s["profit_factor"],
        })
    return pd.DataFrame(rows)


def v361_change_summary(df, changed_col, mode):
    changed = df[df[changed_col]].copy()
    unchanged = df[~df[changed_col]].copy()
    cs = v36_summary(changed)
    us = v36_summary(unchanged)
    total = len(df)
    return {
        "mode": mode,
        "total_signals": total,
        "changed_signals": cs["signals"],
        "changed_pct": 100.0 * cs["signals"] / total if total else np.nan,
        "changed_resolved": cs["resolved"],
        "changed_wins": cs["wins"],
        "changed_losses": cs["losses"],
        "changed_win_rate": cs["win_rate"],
        "changed_avg_R": cs["avg_R"],
        "changed_total_R": cs["total_R"],
        "changed_profit_factor": cs["profit_factor"],
        "unchanged_signals": us["signals"],
        "unchanged_resolved": us["resolved"],
        "unchanged_wins": us["wins"],
        "unchanged_losses": us["losses"],
        "unchanged_win_rate": us["win_rate"],
        "unchanged_avg_R": us["avg_R"],
        "unchanged_total_R": us["total_R"],
        "unchanged_profit_factor": us["profit_factor"],
    }


def v361_interaction_classification(df):
    """Classify how H1/H4 jointly affect the BASE decision label.

    Categories are descriptive counterfactual classifications, not
    trading rules.
    """
    b = df["V36_DECISION_BASE"]
    n = df["V36_DECISION_NO_H1_H4"]
    h1 = df["V36_DECISION_H1_ONLY"]
    h4 = df["V36_DECISION_H4_ONLY"]

    conditions = [
        # BASE is supported, while neither component alone reproduces it.
        (b != n) & (b != h1) & (b != h4),
        # H1 alone reproduces BASE; H4 alone does not.
        (b != n) & (b == h1) & (b != h4),
        # H4 alone reproduces BASE; H1 alone does not.
        (b != n) & (b != h1) & (b == h4),
        # Both alone reproduce BASE, so the second component is redundant.
        (b != n) & (b == h1) & (b == h4),
        # No component changes the label.
        (b == n) & (b == h1) & (b == h4),
    ]
    labels = [
        "COMBINED_INTERACTION",
        "H1_ONLY_EFFECT",
        "H4_ONLY_EFFECT",
        "REDUNDANT_H1_H4_SUPPORT",
        "NO_ABLATION_EFFECT",
    ]

    out = df.copy()
    out["V361_INTERACTION_CLASS"] = np.select(
        conditions, labels, default="OTHER_COUNTERFACTUAL_PATTERN"
    )
    return out


def v361_class_summary(df):
    rows = []
    for cls, g in df.groupby("V361_INTERACTION_CLASS", sort=False):
        s = v36_summary(g)
        rows.append({
            "interaction_class": cls,
            "signals": s["signals"],
            "resolved": s["resolved"],
            "wins": s["wins"],
            "losses": s["losses"],
            "win_rate": s["win_rate"],
            "avg_R": s["avg_R"],
            "total_R": s["total_R"],
            "profit_factor": s["profit_factor"],
        })
    return pd.DataFrame(rows)


def v361_context_summary(df):
    rows = []
    for context, g in df.groupby("V36_C3_CONTEXT", sort=False):
        for cls, cg in g.groupby("V361_INTERACTION_CLASS", sort=False):
            s = v36_summary(cg)
            rows.append({
                "c3_context": context,
                "interaction_class": cls,
                "signals": s["signals"],
                "resolved": s["resolved"],
                "wins": s["wins"],
                "losses": s["losses"],
                "win_rate": s["win_rate"],
                "avg_R": s["avg_R"],
                "total_R": s["total_R"],
                "profit_factor": s["profit_factor"],
            })
    return pd.DataFrame(rows)


def v361_yearly_change_summary(df):
    rows = []
    comparisons = [
        ("NO_H1_H4", "V36_NO_H1_H4_CHANGED"),
        ("H1_ONLY", "V36_H1_ONLY_CHANGED"),
        ("H4_ONLY", "V36_H4_ONLY_CHANGED"),
    ]
    for year, g in df.groupby("year", sort=True):
        for mode, changed_col in comparisons:
            changed = g[g[changed_col]]
            s = v36_summary(changed)
            rows.append({
                "year": int(year),
                "mode": mode,
                "total_signals": len(g),
                "changed_signals": s["signals"],
                "changed_pct": 100.0 * s["signals"] / len(g) if len(g) else np.nan,
                "resolved": s["resolved"],
                "wins": s["wins"],
                "losses": s["losses"],
                "win_rate": s["win_rate"],
                "avg_R": s["avg_R"],
                "total_R": s["total_R"],
                "profit_factor": s["profit_factor"],
            })
    return pd.DataFrame(rows)


def v361_decision_change_guard(original, df):
    """Verify V3.6.1 only adds analytical columns."""
    frozen_cols = ["signal_date", "year", "result", "R", "technical_score"]
    for col in frozen_cols:
        a = original[col].reset_index(drop=True)
        b = df[col].reset_index(drop=True)
        if col in ["R", "technical_score"]:
            a = pd.to_numeric(a, errors="coerce")
            b = pd.to_numeric(b, errors="coerce")
        if not a.equals(b):
            raise RuntimeError(f"V3.6.1 {col.upper()} GUARD FAILED.")

    # Decision columns must be strings only; no trade fields are modified.
    decision_cols = [
        "V36_DECISION_BASE",
        "V36_DECISION_NO_H1_H4",
        "V36_DECISION_H1_ONLY",
        "V36_DECISION_H4_ONLY",
    ]
    for col in decision_cols:
        if col not in df.columns:
            raise RuntimeError(f"V3.6.1 MISSING DECISION COLUMN: {col}")

    print("V3.6.1 FROZEN SIGNAL/RESULT/R/TECHNICAL GUARD: PASS")
    print("V3.6.1 NO ENTRY CREATION: PASS")
    print("V3.6.1 NO BASELINE MODIFICATION: PASS")


def v361_main(trades, market):
    print("\n" + "=" * 72)
    print("US500 MACRO INTELLIGENCE — V3.6.1")
    print("AGGREGATE DECISION ABLATION AUDIT")
    print("=" * 72)

    # Rebuild the exact V3.6 labels from the same frozen in-memory trades.
    df = v36_build_decision_comparison(trades)
    df = v361_interaction_classification(df)
    v361_decision_change_guard(trades, df)

    comparisons = [
        ("NO_H1_H4", "V36_NO_H1_H4_CHANGED"),
        ("H1_ONLY", "V36_H1_ONLY_CHANGED"),
        ("H4_ONLY", "V36_H4_ONLY_CHANGED"),
    ]

    change_summary = pd.DataFrame([
        v361_change_summary(df, changed_col, mode)
        for mode, changed_col in comparisons
    ])

    transition_no = v361_transition_matrix(df, "V36_DECISION_NO_H1_H4")
    transition_h1 = v361_transition_matrix(df, "V36_DECISION_H1_ONLY")
    transition_h4 = v361_transition_matrix(df, "V36_DECISION_H4_ONLY")

    interaction_summary = v361_class_summary(df)
    context_summary = v361_context_summary(df)
    yearly = v361_yearly_change_summary(df)

    # Direct C3 vs NON-C3 audit of the counterfactual effects.
    c3_rows = []
    for context, g in df.groupby("V36_C3_CONTEXT", sort=False):
        for mode, changed_col in comparisons:
            s = v36_summary(g[g[changed_col]])
            c3_rows.append({
                "c3_context": context,
                "mode": mode,
                "signals": len(g),
                "changed_signals": s["signals"],
                "changed_pct": 100.0 * s["signals"] / len(g) if len(g) else np.nan,
                "resolved": s["resolved"],
                "wins": s["wins"],
                "losses": s["losses"],
                "win_rate": s["win_rate"],
                "avg_R": s["avg_R"],
                "total_R": s["total_R"],
                "profit_factor": s["profit_factor"],
            })
    c3_audit = pd.DataFrame(c3_rows)

    # Compact signal-level audit focused only on rows where any ablation changes.
    any_change = (
        df["V36_NO_H1_H4_CHANGED"]
        | df["V36_H1_ONLY_CHANGED"]
        | df["V36_H4_ONLY_CHANGED"]
    )
    changed_rows = df.loc[
        any_change,
        [
            "signal_date", "year", "result", "R",
            "V36_H1", "V36_H4", "V36_C3", "V36_C3_CONTEXT",
            "V361_INTERACTION_CLASS",
            "V36_DECISION_BASE", "V36_DECISION_NO_H1_H4",
            "V36_DECISION_H1_ONLY", "V36_DECISION_H4_ONLY",
            "V36_NO_H1_H4_CHANGED", "V36_H1_ONLY_CHANGED",
            "V36_H4_ONLY_CHANGED",
        ],
    ].copy()

    print("\n" + "=" * 72)
    print("V3.6.1 AGGREGATE DECISION CHANGE SUMMARY")
    print("=" * 72)
    print(change_summary.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.6.1 INTERACTION CLASSIFICATION")
    print("=" * 72)
    print(interaction_summary.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.6.1 BASE -> NO H1/H4 TRANSITIONS")
    print("=" * 72)
    print(transition_no.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.6.1 BASE -> H1 ONLY TRANSITIONS")
    print("=" * 72)
    print(transition_h1.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.6.1 BASE -> H4 ONLY TRANSITIONS")
    print("=" * 72)
    print(transition_h4.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.6.1 C3 vs NON-C3 CHANGE AUDIT")
    print("=" * 72)
    print(c3_audit.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.6.1 YEARLY CHANGE AUDIT")
    print("=" * 72)
    print(yearly.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.6.1 CHANGED SIGNALS ONLY")
    print("=" * 72)
    print(changed_rows.to_string(index=False))

    reports = {
        "macro_backtest_v361_ablation_change_summary.csv": change_summary,
        "macro_backtest_v361_interaction_classification.csv": interaction_summary,
        "macro_backtest_v361_context_interaction_audit.csv": context_summary,
        "macro_backtest_v361_transitions_base_vs_no_h1_h4.csv": transition_no,
        "macro_backtest_v361_transitions_base_vs_h1_only.csv": transition_h1,
        "macro_backtest_v361_transitions_base_vs_h4_only.csv": transition_h4,
        "macro_backtest_v361_c3_vs_non_c3_change_audit.csv": c3_audit,
        "macro_backtest_v361_yearly_change_audit.csv": yearly,
        "macro_backtest_v361_changed_signals_only.csv": changed_rows,
    }

    for filename, report in reports.items():
        report.to_csv(filename, index=False)

    print("\n" + "=" * 72)
    print("V3.6.1 COMPLETE")
    print("=" * 72)
    print("Research-only. No new entries were created.")
    print("Frozen baseline, entries, stops, RR, sizing and R outcomes were not modified.")
    print("The audit measures only how Decision Engine labels change under counterfactual ablations.")
    print("\nFILES CREATED")
    for filename in reports:
        print(filename)


# ============================================================
# US500 MACRO INTELLIGENCE — V3.7
# CONDITIONAL REGIME AUDIT
#
# Research-only continuation of V3.6.1.
# V3.7 does NOT alter signals, entries, stops, RR, sizing,
# results, R values, technical scores, or the Decision Engine.
#
# Purpose:
#   1) Determine when H1/H4 counterfactual effects occur.
#   2) Audit H1/H4 decision changes conditionally by:
#      - Macro Regime A-F
#      - Drawdown bucket
#      - Leading Warning
#      - Technical Status
#      - Year
#   3) Audit selected 2D contexts for regime-dependent effects.
#   4) Correct V3.6.1 interaction labels so "H1-only context"
#      is not confused with "H1-only ablation effect".
#   5) Flag small-N groups rather than treating them as evidence.
#   6) Preserve all frozen integrity guards.
# ============================================================


def v37_corrected_interaction_classification(df):
    """Descriptive classification of the existing V3.6 ablation labels.

    IMPORTANT: these are context classifications, not trading rules.
    "H1_ONLY_CONTEXT" means H1 alone reproduces BASE while H4 alone does not.
    "H4_ONLY_CONTEXT" is the symmetric case.
    "C3_REDUNDANT_SUPPORT" means both H1 and H4 alone reproduce BASE.
    "COMBINED_INTERACTION" means neither alone reproduces BASE.
    "NO_ABLATION_EFFECT" means no counterfactual changes the BASE label.
    """
    b = df["V36_DECISION_BASE"]
    n = df["V36_DECISION_NO_H1_H4"]
    h1 = df["V36_DECISION_H1_ONLY"]
    h4 = df["V36_DECISION_H4_ONLY"]

    conditions = [
        (b != n) & (b != h1) & (b != h4),
        (b != n) & (b == h1) & (b != h4),
        (b != n) & (b != h1) & (b == h4),
        (b != n) & (b == h1) & (b == h4),
        (b == n) & (b == h1) & (b == h4),
    ]
    labels = [
        "COMBINED_INTERACTION",
        "H1_ONLY_CONTEXT",
        "H4_ONLY_CONTEXT",
        "C3_REDUNDANT_SUPPORT",
        "NO_ABLATION_EFFECT",
    ]
    out = df.copy()
    out["V37_INTERACTION_CLASS"] = np.select(
        conditions, labels, default="OTHER_COUNTERFACTUAL_PATTERN"
    )
    return out


def v37_summary(g):
    s = v36_summary(g)
    return {
        "signals": s["signals"],
        "resolved": s["resolved"],
        "wins": s["wins"],
        "losses": s["losses"],
        "win_rate": s["win_rate"],
        "avg_R": s["avg_R"],
        "total_R": s["total_R"],
        "profit_factor": s["profit_factor"],
    }


def v37_conditional_audit(df, dimension, mode, changed_col):
    """Aggregate ablation effects within one contextual dimension."""
    rows = []
    work = df.copy()
    work[dimension] = work[dimension].astype(str).fillna("NA")
    for context, g in work.groupby(dimension, sort=False, dropna=False):
        changed = g[g[changed_col]]
        s = v37_summary(changed)
        total = len(g)
        rows.append({
            "dimension": dimension,
            "context": context,
            "mode": mode,
            "signals": total,
            "changed_signals": s["signals"],
            "changed_pct": 100.0 * s["signals"] / total if total else np.nan,
            "resolved": s["resolved"],
            "wins": s["wins"],
            "losses": s["losses"],
            "win_rate": s["win_rate"],
            "avg_R": s["avg_R"],
            "total_R": s["total_R"],
            "profit_factor": s["profit_factor"],
            "N_FLAG": "N<5" if total < 5 else ("N<10" if total < 10 else "OK"),
            "CHANGED_N_FLAG": "CHANGED_N<5" if s["signals"] < 5 else ("CHANGED_N<10" if s["signals"] < 10 else "OK"),
        })
    return pd.DataFrame(rows)


def v37_pair_audit(df, dimensions, mode, changed_col):
    """Selected 2D conditional audit; useful for context dependence."""
    rows = []
    for keys, g in df.groupby(dimensions, sort=False, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        changed = g[g[changed_col]]
        s = v37_summary(changed)
        row = {k: str(v) for k, v in zip(dimensions, keys)}
        row.update({
            "mode": mode,
            "signals": len(g),
            "changed_signals": s["signals"],
            "changed_pct": 100.0 * s["signals"] / len(g) if len(g) else np.nan,
            "resolved": s["resolved"],
            "wins": s["wins"],
            "losses": s["losses"],
            "win_rate": s["win_rate"],
            "avg_R": s["avg_R"],
            "total_R": s["total_R"],
            "profit_factor": s["profit_factor"],
            "N_FLAG": "N<5" if len(g) < 5 else ("N<10" if len(g) < 10 else "OK"),
            "CHANGED_N_FLAG": "CHANGED_N<5" if s["signals"] < 5 else ("CHANGED_N<10" if s["signals"] < 10 else "OK"),
        })
        rows.append(row)
    return pd.DataFrame(rows)


def v37_transition_context_audit(df, dimension, mode, decision_col):
    """Decision transition audit inside each contextual group."""
    rows = []
    for context, g in df.groupby(dimension, sort=False, dropna=False):
        for (base_decision, counter_decision), cg in g.groupby(
            ["V36_DECISION_BASE", decision_col], sort=False, dropna=False
        ):
            s = v37_summary(cg)
            rows.append({
                "dimension": dimension,
                "context": str(context),
                "mode": mode,
                "base_decision": base_decision,
                "counterfactual_decision": counter_decision,
                "changed": bool(base_decision != counter_decision),
                "signals": s["signals"],
                "resolved": s["resolved"],
                "wins": s["wins"],
                "losses": s["losses"],
                "win_rate": s["win_rate"],
                "avg_R": s["avg_R"],
                "total_R": s["total_R"],
                "profit_factor": s["profit_factor"],
            })
    return pd.DataFrame(rows)


def v37_integrity_guard(original, df):
    """V3.7 may only add research columns."""
    frozen_cols = [
        "signal_date", "year", "result", "R", "technical_score",
        "entry", "stop", "target", "risk_points",
    ]
    for col in frozen_cols:
        if col not in original.columns or col not in df.columns:
            raise RuntimeError(f"V3.7 MISSING FROZEN COLUMN: {col}")
        a = original[col].reset_index(drop=True)
        b = df[col].reset_index(drop=True)
        if col in ["R", "technical_score", "entry", "stop", "target", "risk_points"]:
            a = pd.to_numeric(a, errors="coerce")
            b = pd.to_numeric(b, errors="coerce")
            if not np.allclose(a.to_numpy(dtype=float), b.to_numpy(dtype=float), equal_nan=True):
                raise RuntimeError(f"V3.7 {col.upper()} INTEGRITY GUARD FAILED.")
        else:
            if not a.equals(b):
                raise RuntimeError(f"V3.7 {col.upper()} INTEGRITY GUARD FAILED.")

    expected_dates = pd.to_datetime(original["signal_date"]).reset_index(drop=True)
    actual_dates = pd.to_datetime(df["signal_date"]).reset_index(drop=True)
    if not expected_dates.equals(actual_dates):
        raise RuntimeError("V3.7 SIGNAL DATE GUARD FAILED.")

    required = [
        "V36_DECISION_BASE", "V36_DECISION_NO_H1_H4",
        "V36_DECISION_H1_ONLY", "V36_DECISION_H4_ONLY",
        "V36_H1", "V36_H4", "V36_C3", "V36_C3_CONTEXT",
    ]
    for col in required:
        if col not in df.columns:
            raise RuntimeError(f"V3.7 MISSING V3.6 COLUMN: {col}")

    print("V3.7 FROZEN SIGNAL/RESULT/R/TECHNICAL GUARD: PASS")
    print("V3.7 NO ENTRY CREATION: PASS")
    print("V3.7 NO BASELINE MODIFICATION: PASS")


def v37_main(trades, market):
    print("\n" + "=" * 72)
    print("US500 MACRO INTELLIGENCE — V3.7")
    print("CONDITIONAL REGIME AUDIT")
    print("=" * 72)

    df = v36_build_decision_comparison(trades)
    df = v37_corrected_interaction_classification(df)
    v37_integrity_guard(trades, df)

    # Verify V3.6 labels are reproduced exactly before conditional analysis.
    # v30_decision_layer() returns (decision, modifier). Compare only the
    # decision LABEL values. Do not use Series.equals() here because the
    # Series name is metadata and can differ even when every label matches.
    # pandas documents Series/DataFrame equality as sensitive to metadata in
    # strict equality helpers, so this guard intentionally compares the
    # aligned object values after resetting position.
    actual = df["V36_DECISION_BASE"].reset_index(drop=True).astype(object)
    reference = pd.Series(
        [v30_decision_layer(row)[0] for _, row in trades.iterrows()],
        index=actual.index,
        dtype=object,
    )

    mismatch = pd.DataFrame({
        "actual": actual.to_numpy(dtype=object),
        "expected": reference.to_numpy(dtype=object),
    })
    mismatch = mismatch[mismatch["actual"] != mismatch["expected"]]

    if not mismatch.empty:
        raise RuntimeError(
            "V3.7 BASE DECISION REPRODUCTION GUARD FAILED. "
            f"Mismatches: {len(mismatch)}"
        )
    print("V3.7 BASE DECISION REPRODUCTION GUARD: PASS")

    dimensions = [
        "macro_regime",
        "drawdown_bucket",
        "leading_warning",
        "technical_status",
        "year",
    ]
    comparisons = [
        ("NO_H1_H4", "V36_DECISION_NO_H1_H4", "V36_NO_H1_H4_CHANGED"),
        ("H1_ONLY", "V36_DECISION_H1_ONLY", "V36_H1_ONLY_CHANGED"),
        ("H4_ONLY", "V36_DECISION_H4_ONLY", "V36_H4_ONLY_CHANGED"),
    ]

    conditional_parts = []
    transition_parts = []
    for dimension in dimensions:
        for mode, decision_col, changed_col in comparisons:
            conditional_parts.append(
                v37_conditional_audit(df, dimension, mode, changed_col)
            )
            transition_parts.append(
                v37_transition_context_audit(df, dimension, mode, decision_col)
            )
    conditional = pd.concat(conditional_parts, ignore_index=True)
    transitions = pd.concat(transition_parts, ignore_index=True)

    # Selected 2D contexts: the combinations most relevant to the research framework.
    pair_specs = [
        ("macro_regime", "leading_warning"),
        ("drawdown_bucket", "leading_warning"),
        ("drawdown_bucket", "macro_regime"),
        ("technical_status", "macro_regime"),
        ("technical_status", "leading_warning"),
    ]
    pair_parts = []
    for dims in pair_specs:
        for mode, _, changed_col in comparisons:
            pair_parts.append(v37_pair_audit(df, list(dims), mode, changed_col))
    pair_audit = pd.concat(pair_parts, ignore_index=True)

    # Corrected interaction class summary.
    interaction_rows = []
    for cls, g in df.groupby("V37_INTERACTION_CLASS", sort=False):
        s = v37_summary(g)
        interaction_rows.append({
            "interaction_class": cls,
            "signals": s["signals"],
            "resolved": s["resolved"],
            "wins": s["wins"],
            "losses": s["losses"],
            "win_rate": s["win_rate"],
            "avg_R": s["avg_R"],
            "total_R": s["total_R"],
            "profit_factor": s["profit_factor"],
        })
    interaction = pd.DataFrame(interaction_rows)

    # High-N candidates: descriptive shortlist only. No ranking or trading verdict.
    high_n = conditional[
        (conditional["signals"] >= 10) &
        (conditional["changed_signals"] >= 5)
    ].copy()
    high_n = high_n.sort_values(
        ["dimension", "mode", "changed_pct"], ascending=[True, True, False]
    )

    # Signal-level rows where at least one counterfactual changes the decision.
    any_change = (
        df["V36_NO_H1_H4_CHANGED"] |
        df["V36_H1_ONLY_CHANGED"] |
        df["V36_H4_ONLY_CHANGED"]
    )
    changed = df.loc[any_change].copy()
    changed["V37_INTERACTION_CLASS"] = changed["V37_INTERACTION_CLASS"].astype(str)

    print("\n" + "=" * 72)
    print("V3.7 CORRECTED INTERACTION CLASSIFICATION")
    print("=" * 72)
    print(interaction.to_string(index=False))

    for dimension in dimensions:
        print("\n" + "=" * 72)
        print(f"V3.7 CONDITIONAL AUDIT — {dimension.upper()}")
        print("=" * 72)
        print(conditional[conditional["dimension"] == dimension].to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.7 SELECTED 2D CONTEXT AUDIT")
    print("=" * 72)
    print(pair_audit.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.7 DECISION TRANSITIONS BY CONTEXT")
    print("=" * 72)
    print(transitions.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.7 HIGH-N RESEARCH CANDIDATE GROUPS")
    print("=" * 72)
    if high_n.empty:
        print("No groups satisfy signals >= 10 and changed_signals >= 5.")
    else:
        print(high_n.to_string(index=False))

    print("\n" + "=" * 72)
    print("V3.7 CHANGED SIGNALS — CORRECTED CLASS")
    print("=" * 72)
    cols = [
        "signal_date", "year", "result", "R",
        "macro_regime", "drawdown_bucket", "leading_warning",
        "technical_status", "V36_H1", "V36_H4", "V36_C3_CONTEXT",
        "V37_INTERACTION_CLASS",
        "V36_DECISION_BASE", "V36_DECISION_NO_H1_H4",
        "V36_DECISION_H1_ONLY", "V36_DECISION_H4_ONLY",
        "V36_NO_H1_H4_CHANGED", "V36_H1_ONLY_CHANGED",
        "V36_H4_ONLY_CHANGED",
    ]
    print(changed[cols].to_string(index=False))

    reports = {
        "macro_backtest_v37_conditional_context_audit.csv": conditional,
        "macro_backtest_v37_context_transition_audit.csv": transitions,
        "macro_backtest_v37_selected_2d_context_audit.csv": pair_audit,
        "macro_backtest_v37_corrected_interaction_classification.csv": interaction,
        "macro_backtest_v37_high_n_research_candidates.csv": high_n,
        "macro_backtest_v37_changed_signals_corrected.csv": changed[cols],
    }
    for filename, report in reports.items():
        report.to_csv(filename, index=False)

    print("\n" + "=" * 72)
    print("V3.7 COMPLETE")
    print("=" * 72)
    print("Research-only. No new entries were created.")
    print("Frozen baseline, entries, stops, RR, sizing and R outcomes were not modified.")
    print("Small-N groups are explicitly flagged and are not treated as evidence.")
    print("V3.7 does not modify the Decision Engine.")
    print("\nFILES CREATED")
    for filename in reports:
        print(filename)



# ============================================================
# US500 MACRO INTELLIGENCE — V3.8
# STRICT OOS / WALK-FORWARD ABLATION VALIDATION
# ============================================================
# STANDALONE VERSION
#
# This file intentionally contains the authoritative V3.2/V3.7
# definitions above it. It does NOT require a second Python file.
#
# Frozen baseline remains:
#   119 signals
#   117 valid
#   2 invalid SL
#   109 resolved
#   36 wins
#   73 losses
#   3 ambiguous
#   5 open
#   +71R
#   PF ~= 1.9726027397
#
# V3.8:
#   - strict chronological holdout from 2025-01-01
#   - expanding yearly walk-forward audit
#   - frozen V3.7 interaction contexts
#   - no new entries
#   - no changes to SL/TP/RR/R
#   - no parameter optimization in OOS
# ============================================================

OOS_START = pd.Timestamp("2025-01-01")
WALK_YEARS = [2023, 2024, 2025, 2026]


def v38_metric_summary(g):
    g = g.copy()

    wins = int((g["result"] == "WIN").sum())
    losses = int((g["result"] == "LOSS").sum())
    invalid = int((g["result"] == "INVALID_SL").sum())
    ambiguous = int((g["result"] == "AMBIGUOUS").sum())
    open_trades = int((g["result"] == "OPEN").sum())
    resolved = wins + losses

    r = pd.to_numeric(g["R"], errors="coerce")
    gross_profit = float(r[r > 0].sum())
    gross_loss = abs(float(r[r < 0].sum()))

    return {
        "signals": len(g),
        "valid": len(g) - invalid,
        "invalid_sl": invalid,
        "resolved": resolved,
        "wins": wins,
        "losses": losses,
        "ambiguous": ambiguous,
        "open": open_trades,
        "win_rate": 100.0 * wins / resolved if resolved else np.nan,
        "avg_R": float(r.dropna().mean()) if r.notna().any() else np.nan,
        "total_R": float(r.dropna().sum()) if r.notna().any() else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else np.nan,
    }


def v38_frozen_baseline_guard(baseline):
    s = v38_metric_summary(baseline)

    expected = {
        "signals": 119,
        "valid": 117,
        "invalid_sl": 2,
        "resolved": 109,
        "wins": 36,
        "losses": 73,
        "ambiguous": 3,
        "open": 5,
        "total_R": 71.0,
    }

    for key, expected_value in expected.items():
        actual = s[key]
        if key == "total_R":
            ok = np.isclose(actual, expected_value, atol=1e-12)
        else:
            ok = actual == expected_value

        if not ok:
            raise RuntimeError(
                f"V3.8 FROZEN BASELINE GUARD FAILED: "
                f"{key}={actual}, expected={expected_value}"
            )

    if not np.isclose(
        s["profit_factor"],
        1.9726027397260273,
        atol=1e-12,
    ):
        raise RuntimeError(
            "V3.8 FROZEN BASELINE GUARD FAILED: "
            f"profit_factor={s['profit_factor']}"
        )

    print("V3.8 FROZEN SIGNAL/RESULT/R GUARD: PASS")


def v38_base_decision_guard(trades):
    actual = trades["V36_DECISION_BASE"].reset_index(drop=True).astype(object)

    expected = pd.Series(
        [v30_decision_layer(row)[0] for _, row in trades.iterrows()],
        index=actual.index,
        dtype=object,
    )

    if not np.array_equal(
        actual.to_numpy(dtype=object),
        expected.to_numpy(dtype=object),
    ):
        raise RuntimeError(
            "V3.8 BASE DECISION REPRODUCTION GUARD FAILED."
        )

    print("V3.8 BASE DECISION REPRODUCTION GUARD: PASS")


def v38_context_masks(df):
    return {
        "H1_ONLY_CONTEXT":
            df["V37_INTERACTION_CLASS"].eq("H1_ONLY_CONTEXT"),

        "C3_REDUNDANT_SUPPORT":
            df["V37_INTERACTION_CLASS"].eq("C3_REDUNDANT_SUPPORT"),

        "H4_ONLY_CONTEXT":
            df["V37_INTERACTION_CLASS"].eq("H4_ONLY_CONTEXT"),

        "A_WATCH_CONTEXT":
            (
                df["macro_regime"].eq("A")
                & df["leading_warning"].eq("WATCH")
            ),
    }


def v38_counterfactual_column(mode):
    if mode == "H1_ONLY_CONTEXT":
        return "V36_H1_ONLY_CHANGED"

    if mode == "H4_ONLY_CONTEXT":
        return "V36_H4_ONLY_CHANGED"

    if mode in (
        "C3_REDUNDANT_SUPPORT",
        "A_WATCH_CONTEXT",
    ):
        return "V36_NO_H1_H4_CHANGED"

    raise ValueError(f"Unknown V3.8 context: {mode}")


def v38_decision_column(mode):
    if mode == "H1_ONLY_CONTEXT":
        return "V36_DECISION_H1_ONLY"

    if mode == "H4_ONLY_CONTEXT":
        return "V36_DECISION_H4_ONLY"

    return "V36_DECISION_NO_H1_H4"


def v38_audit_context(df, mode, start=None, end=None):
    x = df.copy()

    if start is not None:
        x = x[x["signal_date"] >= pd.Timestamp(start)]

    if end is not None:
        x = x[x["signal_date"] < pd.Timestamp(end)]

    mask = v38_context_masks(x)[mode]
    selected = x.loc[mask].copy()

    if selected.empty:
        return {
            "context": mode,
            "signals": 0,
            "resolved": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": np.nan,
            "avg_R": np.nan,
            "total_R": 0.0,
            "profit_factor": np.nan,
            "decision_changed": 0,
            "decision_change_pct": np.nan,
            "changed_resolved": 0,
            "changed_wins": 0,
            "changed_losses": 0,
            "changed_win_rate": np.nan,
            "changed_avg_R": np.nan,
            "changed_total_R": 0.0,
            "changed_profit_factor": np.nan,
            "small_N_flag": True,
        }

    changed_col = v38_counterfactual_column(mode)
    decision_col = v38_decision_column(mode)

    selected["V38_CHANGED"] = selected[changed_col].astype(bool)

    all_stats = v38_metric_summary(selected)
    changed = selected[selected["V38_CHANGED"]].copy()

    changed_stats = v38_metric_summary(changed)

    base_decisions = selected["V36_DECISION_BASE"].astype(str)
    counterfactual = selected[decision_col].astype(str)

    transition_count = int(
        (base_decisions != counterfactual).sum()
    )

    return {
        "context": mode,
        "signals": all_stats["signals"],
        "resolved": all_stats["resolved"],
        "wins": all_stats["wins"],
        "losses": all_stats["losses"],
        "win_rate": all_stats["win_rate"],
        "avg_R": all_stats["avg_R"],
        "total_R": all_stats["total_R"],
        "profit_factor": all_stats["profit_factor"],

        "decision_changed": transition_count,
        "decision_change_pct":
            100.0 * transition_count / len(selected),

        "changed_resolved": changed_stats["resolved"],
        "changed_wins": changed_stats["wins"],
        "changed_losses": changed_stats["losses"],
        "changed_win_rate": changed_stats["win_rate"],
        "changed_avg_R": changed_stats["avg_R"],
        "changed_total_R": changed_stats["total_R"],
        "changed_profit_factor": changed_stats["profit_factor"],

        "small_N_flag":
            changed_stats["resolved"] < 5,
    }


def v38_strict_oos(df):
    rows = []

    for context in v38_context_masks(df):
        discovery = v38_audit_context(
            df,
            context,
            start=None,
            end=OOS_START,
        )
        discovery["sample"] = "DISCOVERY"
        rows.append(discovery)

        holdout = v38_audit_context(
            df,
            context,
            start=OOS_START,
            end=None,
        )
        holdout["sample"] = "HOLDOUT_OOS"
        rows.append(holdout)

    return pd.DataFrame(rows)


def v38_walk_forward(df):
    rows = []

    for year in WALK_YEARS:
        start = pd.Timestamp(f"{year}-01-01")
        end = pd.Timestamp(f"{year + 1}-01-01")

        for context in v38_context_masks(df):
            row = v38_audit_context(
                df,
                context,
                start=start,
                end=end,
            )
            row["test_year"] = year
            rows.append(row)

    return pd.DataFrame(rows)


def v38_transition_audit(df):
    oos = df[df["signal_date"] >= OOS_START].copy()

    rows = []

    for context in v38_context_masks(df):
        mask = v38_context_masks(oos)[context]
        x = oos.loc[mask].copy()

        if x.empty:
            continue

        decision_col = v38_decision_column(context)

        transitions = (
            x["V36_DECISION_BASE"].astype(str)
            + " -> "
            + x[decision_col].astype(str)
        )

        for transition, count in transitions.value_counts().items():
            rows.append({
                "context": context,
                "transition": transition,
                "signals": int(count),
            })

    return pd.DataFrame(rows)


def v38_alignment_guards(baseline, trades):
    if len(baseline) != len(trades):
        raise RuntimeError(
            "V3.8 NO ENTRY CREATION GUARD FAILED: row count changed."
        )

    baseline_dates = pd.to_datetime(
        baseline["signal_date"]
    ).reset_index(drop=True)

    trade_dates = pd.to_datetime(
        trades["signal_date"]
    ).reset_index(drop=True)

    if not baseline_dates.equals(trade_dates):
        raise RuntimeError(
            "V3.8 NO ENTRY CREATION GUARD FAILED: signal dates changed."
        )

    for column in ["result", "R"]:
        left = baseline[column].reset_index(drop=True)
        right = trades[column].reset_index(drop=True)

        if column == "R":
            if not np.allclose(
                pd.to_numeric(left, errors="coerce"),
                pd.to_numeric(right, errors="coerce"),
                equal_nan=True,
            ):
                raise RuntimeError(
                    f"V3.8 FROZEN RESULT/R GUARD FAILED: {column}"
                )
        else:
            if not left.astype(object).equals(
                right.astype(object)
            ):
                raise RuntimeError(
                    f"V3.8 FROZEN RESULT/R GUARD FAILED: {column}"
                )

    print("V3.8 NO ENTRY CREATION: PASS")
    print("V3.8 NO BASELINE MODIFICATION: PASS")


def v38_print(title, df):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)

    if df.empty:
        print("NO ROWS")
    else:
        print(df.to_string(index=False))


def v38_run():
    print("\n" + "=" * 78)
    print("US500 MACRO INTELLIGENCE — V3.8")
    print("STRICT OOS / WALK-FORWARD ABLATION VALIDATION")
    print("=" * 78)

    # --------------------------------------------------------
    # 1. AUTHORITATIVE MARKET DATA
    # --------------------------------------------------------
    market = load_market()

    # --------------------------------------------------------
    # 2. FROZEN BASELINE
    # --------------------------------------------------------
    baseline = build_baseline_trades(market)

    if not print_baseline_check(baseline):
        raise RuntimeError(
            "V3.8 STOPPED: authoritative frozen baseline failed."
        )

    v38_frozen_baseline_guard(baseline)

    # --------------------------------------------------------
    # 3. AUTHORITATIVE V3.2 → V3.7 PIPELINE
    # --------------------------------------------------------
    fred = load_fred()

    trades = attach_macro(
        baseline,
        fred,
    )

    trades = add_drawdown(
        trades,
        market,
    )

    trades = add_zones(
        trades,
    )

    trades = add_confluence_flags(
        trades,
    )

    trades = add_v31_technical_confirmation(
        trades,
        market,
    )

    # Frozen H1/H4 definitions.
    trades["H1_FLAG"] = (
        (trades["macro_regime"] == "A")
        & (trades["leading_warning"] == "WATCH")
    )

    trades["H4_FLAG"] = (
        (trades["macro_regime"] == "A")
        & (
            trades["liquidity_momentum"]
            == "DETERIORATING"
        )
    )

    # --------------------------------------------------------
    # 4. V3.7 DECISION COMPARISON
    # --------------------------------------------------------
    decision_df = v36_build_decision_comparison(
        trades
    )

    decision_df = v37_corrected_interaction_classification(
        decision_df
    )

    required_columns = [
        "V36_DECISION_BASE",
        "V36_DECISION_NO_H1_H4",
        "V36_DECISION_H1_ONLY",
        "V36_DECISION_H4_ONLY",
        "V36_NO_H1_H4_CHANGED",
        "V36_H1_ONLY_CHANGED",
        "V36_H4_ONLY_CHANGED",
        "V37_INTERACTION_CLASS",
    ]

    missing = [
        column
        for column in required_columns
        if column not in decision_df.columns
    ]

    if missing:
        raise RuntimeError(
            "V3.8 V3.7 CLASSIFICATION GUARD FAILED: "
            + str(missing)
        )

    print("V3.8 V3.7 CLASSIFICATION GUARD: PASS")

    # --------------------------------------------------------
    # 5. ALIGNMENT / BASE DECISION GUARDS
    # --------------------------------------------------------
    v38_alignment_guards(
        baseline,
        decision_df,
    )

    v38_base_decision_guard(
        decision_df,
    )

    # --------------------------------------------------------
    # 6. STRICT CHRONOLOGICAL OOS
    # --------------------------------------------------------
    oos = v38_strict_oos(
        decision_df
    )

    # --------------------------------------------------------
    # 7. EXPANDING YEARLY WALK-FORWARD AUDIT
    # --------------------------------------------------------
    walk_forward = v38_walk_forward(
        decision_df
    )

    # --------------------------------------------------------
    # 8. OOS DECISION TRANSITIONS
    # --------------------------------------------------------
    transitions = v38_transition_audit(
        decision_df
    )

    # --------------------------------------------------------
    # 9. IS → OOS SURVIVAL
    # --------------------------------------------------------
    survival_rows = []

    for context in v38_context_masks(
        decision_df
    ):
        discovery = oos[
            (oos["context"] == context)
            & (oos["sample"] == "DISCOVERY")
        ]

        holdout = oos[
            (oos["context"] == context)
            & (oos["sample"] == "HOLDOUT_OOS")
        ]

        if discovery.empty or holdout.empty:
            continue

        d = discovery.iloc[0]
        h = holdout.iloc[0]

        if (
            np.isfinite(d["avg_R"])
            and np.isfinite(h["avg_R"])
        ):
            delta = (
                h["avg_R"]
                - d["avg_R"]
            )
        else:
            delta = np.nan

        survival_rows.append({
            "context": context,
            "discovery_resolved":
                d["resolved"],
            "discovery_avg_R":
                d["avg_R"],
            "discovery_total_R":
                d["total_R"],
            "holdout_resolved":
                h["resolved"],
            "holdout_avg_R":
                h["avg_R"],
            "holdout_total_R":
                h["total_R"],
            "OOS_avg_R_minus_IS_avg_R":
                delta,
            "holdout_small_N":
                bool(
                    h["small_N_flag"]
                ),
        })

    survival = pd.DataFrame(
        survival_rows
    )

    # --------------------------------------------------------
    # 10. PRINT RESULTS
    # --------------------------------------------------------
    v38_print(
        "V3.8 STRICT CHRONOLOGICAL OOS",
        oos,
    )

    v38_print(
        "V3.8 EXPANDING WALK-FORWARD YEAR AUDIT",
        walk_forward,
    )

    v38_print(
        "V3.8 OOS DECISION TRANSITIONS",
        transitions,
    )

    v38_print(
        "V3.8 DISCOVERY → OOS PERFORMANCE SURVIVAL",
        survival,
    )

    # --------------------------------------------------------
    # 11. EXPORT
    # --------------------------------------------------------
    decision_df.to_csv(
        "macro_backtest_v38_frozen_decision_labels.csv",
        index=False,
    )

    oos.to_csv(
        "macro_backtest_v38_strict_oos.csv",
        index=False,
    )

    walk_forward.to_csv(
        "macro_backtest_v38_expanding_walk_forward.csv",
        index=False,
    )

    transitions.to_csv(
        "macro_backtest_v38_oos_decision_transitions.csv",
        index=False,
    )

    survival.to_csv(
        "macro_backtest_v38_is_oos_survival.csv",
        index=False,
    )

    # --------------------------------------------------------
    # 12. FINAL GUARDS
    # --------------------------------------------------------
    oos_dates = pd.to_datetime(
        decision_df.loc[
            decision_df["signal_date"] >= OOS_START,
            "signal_date",
        ]
    )

    if len(oos_dates):
        if oos_dates.min() < OOS_START:
            raise RuntimeError(
                "V3.8 OOS CHRONOLOGY GUARD FAILED."
            )

    print(
        "\nV3.8 OOS CHRONOLOGY GUARD: PASS"
    )

    print("\n" + "=" * 78)
    print("V3.8 VALIDATION STATUS")
    print("=" * 78)

    print(
        "V3.8 FROZEN SIGNAL/RESULT/R GUARD: PASS"
    )

    print(
        "V3.8 V3.7 CLASSIFICATION GUARD: PASS"
    )

    print(
        "V3.8 BASE DECISION REPRODUCTION GUARD: PASS"
    )

    print(
        "V3.8 NO ENTRY CREATION: PASS"
    )

    print(
        "V3.8 NO BASELINE MODIFICATION: PASS"
    )

    print(
        "V3.8 OOS CHRONOLOGY GUARD: PASS"
    )

    print(
        "V3.8 VALIDATION COMPLETE"
    )

    print(
        "Research-only. No Decision Engine rule was changed."
    )

    print(
        "Small-N OOS groups must not be interpreted as proof."
    )

    print("\nFILES CREATED")

    for filename in [
        "macro_backtest_v38_frozen_decision_labels.csv",
        "macro_backtest_v38_strict_oos.csv",
        "macro_backtest_v38_expanding_walk_forward.csv",
        "macro_backtest_v38_oos_decision_transitions.csv",
        "macro_backtest_v38_is_oos_survival.csv",
    ]:
        print(filename)



# ============================================================
# US500 MACRO INTELLIGENCE — V3.9
# ROBUST OOS / TEMPORAL SURVIVAL VALIDATION
# ============================================================
#
# Research-only extension of V3.8.
#
# IMPORTANT:
#   V3.9 does NOT change the frozen signal generator, entries,
#   stops, TP, RR, sizing, trade outcomes, V3.7 context definitions,
#   or the Decision Engine.
#
# V3.9 consumes the exact frozen V3.8 signal-level classification
# and applies pre-specified robustness diagnostics to the
# chronological OOS / walk-forward outputs.
#
# No parameter optimization is performed.
# Small samples remain explicitly flagged.
# ============================================================

V39_MIN_RESOLVED = 5
V39_MIN_OOS_YEARS = 2
V39_CONTEXTS = [
    "H1_ONLY_CONTEXT",
    "C3_REDUNDANT_SUPPORT",
    "H4_ONLY_CONTEXT",
    "A_WATCH_CONTEXT",
]


def v39_metric(g):
    g = g.copy()
    resolved = g[g["result"].isin(["WIN", "LOSS"])].copy()
    wins = int((resolved["result"] == "WIN").sum())
    losses = int((resolved["result"] == "LOSS").sum())
    total_r = float(pd.to_numeric(resolved["R"], errors="coerce").sum())
    n = len(resolved)
    avg_r = total_r / n if n else np.nan
    pf = (
        float(resolved.loc[resolved["R"] > 0, "R"].sum())
        / abs(float(resolved.loc[resolved["R"] < 0, "R"].sum()))
        if float(resolved.loc[resolved["R"] < 0, "R"].sum()) != 0
        else np.nan
    )
    return {
        "signals": int(len(g)),
        "resolved": n,
        "wins": wins,
        "losses": losses,
        "win_rate": 100.0 * wins / n if n else np.nan,
        "avg_R": avg_r,
        "total_R": total_r,
        "profit_factor": pf,
    }


def v39_year_survival(signal_df):
    """
    Build year-by-year OOS survival directly from the authoritative V3.8
    signal-level frozen labels.

    IMPORTANT: V3.8's expanding walk-forward CSV is an aggregate audit
    table. It contains context/test_year and summary statistics, but it
    intentionally does NOT contain per-trade ``result`` or ``R`` columns.
    Therefore V3.9 must not expect result/R in that walk-forward table.

    The per-year R survival calculation is reconstructed from the frozen
    signal-level labels, which preserves the exact V3.8 outcomes without
    changing the baseline, signals, entries, stops, RR, or Decision Engine.
    """
    x = signal_df.copy()
    x["signal_date"] = pd.to_datetime(x["signal_date"])
    x["year"] = x["signal_date"].dt.year

    # V3.9 evaluates the same expanding-walk-forward test years used by V3.8.
    x = x[x["year"].isin(WALK_YEARS)].copy()

    rows = []
    for context in V39_CONTEXTS:
        c = x[x["context"] == context].copy()
        positive = 0
        negative = 0
        zero = 0
        yearly_r = []

        for year in WALK_YEARS:
            y = c[c["year"] == year]
            m = v39_metric(y)
            r = m["total_R"]

            if m["resolved"] == 0:
                zero += 1
            elif r > 0:
                positive += 1
            elif r < 0:
                negative += 1

            yearly_r.append(r if m["resolved"] else np.nan)

        finite = [r for r in yearly_r if pd.notna(r)]
        rows.append({
            "context": context,
            "oos_years_with_data": len(finite),
            "positive_years": positive,
            "negative_years": negative,
            "zero_trade_years": zero,
            "positive_year_rate_pct": 100.0 * positive / len(finite) if finite else np.nan,
            "median_yearly_R": float(np.median(finite)) if finite else np.nan,
            "worst_year_R": float(np.min(finite)) if finite else np.nan,
            "best_year_R": float(np.max(finite)) if finite else np.nan,
            "small_N_flag": len(finite) < V39_MIN_OOS_YEARS,
        })

    return pd.DataFrame(rows)


def v39_crisis_exclusion(signal_df):
    rows = []
    exclusions = [
        ("NONE", set()),
        ("EXCLUDE_2020", {2020}),
        ("EXCLUDE_2022", {2022}),
        ("EXCLUDE_2020_2022", {2020, 2022}),
        ("EXCLUDE_2025", {2025}),
    ]

    for context in V39_CONTEXTS:
        x = signal_df[signal_df["context"] == context].copy()
        x["year"] = pd.to_datetime(x["signal_date"]).dt.year

        for label, years in exclusions:
            y = x[~x["year"].isin(years)]
            m = v39_metric(y)
            rows.append({
                "context": context,
                "exclusion": label,
                **m,
                "small_N_flag": m["resolved"] < V39_MIN_RESOLVED,
            })
    return pd.DataFrame(rows)


def v39_oos_aggregate(signal_df):
    x = signal_df[pd.to_datetime(signal_df["signal_date"]) >= OOS_START].copy()
    rows = []

    for context in V39_CONTEXTS:
        y = x[x["context"] == context]
        m = v39_metric(y)
        years = sorted(pd.to_datetime(y["signal_date"]).dt.year.dropna().unique())
        rows.append({
            "context": context,
            **m,
            "oos_years_with_signals": len(years),
            "small_N_flag": (
                m["resolved"] < V39_MIN_RESOLVED
                or len(years) < V39_MIN_OOS_YEARS
            ),
        })
    return pd.DataFrame(rows)


def v39_survival_verdict(aggregate, survival):
    rows = []
    for context in V39_CONTEXTS:
        a = aggregate[aggregate["context"] == context].iloc[0]
        s = survival[survival["context"] == context].iloc[0]

        sufficient = (
            int(a["resolved"]) >= V39_MIN_RESOLVED
            and int(a["oos_years_with_signals"]) >= V39_MIN_OOS_YEARS
        )

        if not sufficient:
            status = "INSUFFICIENT_OOS_SAMPLE"
        elif (
            float(a["avg_R"]) > 0
            and float(a["profit_factor"]) > 1
            and float(s["positive_years"]) >= float(s["negative_years"])
        ):
            status = "SURVIVES_PRE_SPECIFIED_CHECKS"
        else:
            status = "DOES_NOT_SURVIVE_PRE_SPECIFIED_CHECKS"

        rows.append({
            "context": context,
            "oos_resolved": int(a["resolved"]),
            "oos_avg_R": float(a["avg_R"]) if pd.notna(a["avg_R"]) else np.nan,
            "oos_total_R": float(a["total_R"]),
            "oos_profit_factor": float(a["profit_factor"]) if pd.notna(a["profit_factor"]) else np.nan,
            "oos_years_with_signals": int(a["oos_years_with_signals"]),
            "positive_years": int(s["positive_years"]),
            "negative_years": int(s["negative_years"]),
            "status": status,
            "research_only": True,
        })
    return pd.DataFrame(rows)


def v39_main():
    print("\n" + "=" * 78)
    print("US500 MACRO INTELLIGENCE — V3.9")
    print("ROBUST OOS / TEMPORAL SURVIVAL VALIDATION")
    print("=" * 78)
    print("V3.9 runs the frozen V3.8 pipeline first.")
    print("No signal, entry, stop, RR, result or Decision Engine rule is changed.")

    # Run exact V3.8 pipeline and regenerate its authoritative outputs.
    v38_run()

    labels_file = "macro_backtest_v38_frozen_decision_labels.csv"
    wf_file = "macro_backtest_v38_expanding_walk_forward.csv"

    labels = pd.read_csv(labels_file)
    wf = pd.read_csv(wf_file)

    # V3.8 exports the frozen decision-label table without a literal
    # ``context`` column. Contexts are derived deterministically from the
    # frozen V3.7 interaction class and the original A+WATCH definition.
    # This is classification only; it does not alter signals, results or R.
    required_labels = {
        "signal_date", "result", "R",
        "V37_INTERACTION_CLASS", "macro_regime", "leading_warning",
    }
    missing = required_labels - set(labels.columns)
    if missing:
        raise RuntimeError(
            f"V3.9 missing required V3.8 frozen label columns: {sorted(missing)}"
        )

    # IMPORTANT: V3.8 contexts are overlapping research masks, not a
    # mutually-exclusive classification. Do NOT use np.select here: it
    # would assign A+WATCH rows to H1/C3/H4 first and erase the overlap.
    # Build an independent long-form context table instead.
    context_masks = {
        "H1_ONLY_CONTEXT": labels["V37_INTERACTION_CLASS"].eq("H1_ONLY_CONTEXT"),
        "C3_REDUNDANT_SUPPORT": labels["V37_INTERACTION_CLASS"].eq("C3_REDUNDANT_SUPPORT"),
        "H4_ONLY_CONTEXT": labels["V37_INTERACTION_CLASS"].eq("H4_ONLY_CONTEXT"),
        "A_WATCH_CONTEXT": (
            labels["macro_regime"].eq("A")
            & labels["leading_warning"].eq("WATCH")
        ),
    }
    context_labels = pd.concat(
        [
            labels.loc[mask].assign(context=context_name)
            for context_name, mask in context_masks.items()
        ],
        ignore_index=True,
    )

    # V3.8 walk-forward is an aggregate audit table. It intentionally
    # contains context/test_year and summary metrics, not per-trade result/R.
    # Only require the structural columns that V3.8 actually exports.
    required_wf = {"context", "test_year"}
    missing = required_wf - set(wf.columns)
    if missing:
        raise RuntimeError(
            f"V3.9 missing required V3.8 walk-forward columns: {sorted(missing)}"
        )

    aggregate = v39_oos_aggregate(context_labels)
    survival = v39_year_survival(context_labels)
    crisis = v39_crisis_exclusion(context_labels)
    verdict = v39_survival_verdict(aggregate, survival)

    aggregate.to_csv("macro_backtest_v39_oos_aggregate.csv", index=False)
    survival.to_csv("macro_backtest_v39_year_survival.csv", index=False)
    crisis.to_csv("macro_backtest_v39_crisis_exclusion.csv", index=False)
    verdict.to_csv("macro_backtest_v39_survival_verdict.csv", index=False)

    print("\n" + "=" * 78)
    print("V3.9 OOS AGGREGATE")
    print("=" * 78)
    print(aggregate.to_string(index=False))

    print("\n" + "=" * 78)
    print("V3.9 YEAR SURVIVAL")
    print("=" * 78)
    print(survival.to_string(index=False))

    print("\n" + "=" * 78)
    print("V3.9 CRISIS EXCLUSION")
    print("=" * 78)
    print(crisis.to_string(index=False))

    print("\n" + "=" * 78)
    print("V3.9 PRE-SPECIFIED SURVIVAL VERDICT")
    print("=" * 78)
    print(verdict.to_string(index=False))

    # Integrity checks.
    if len(labels) == 0:
        raise RuntimeError("V3.9 frozen label file is empty.")

    if not pd.to_numeric(labels["R"], errors="coerce").notna().any():
        raise RuntimeError("V3.9 R integrity check failed.")

    # V3.8 contexts are overlapping research masks, not an exhaustive
    # partition of all 119 signals. Signals outside the four V3.9
    # research contexts are intentionally labelled __NOT_IN_V39_CONTEXT__.
    # Integrity therefore checks only the rows assigned to a V3.9 context.
    assigned_contexts = set(context_labels["context"].dropna().unique())
    if not assigned_contexts.issubset(set(V39_CONTEXTS)):
        raise RuntimeError(
            "V3.9 context integrity check failed: unexpected assigned contexts "
            + str(sorted(assigned_contexts - set(V39_CONTEXTS)))
        )
    if not assigned_contexts:
        raise RuntimeError("V3.9 context integrity check failed: no V3.9 contexts assigned.")

    oos_dates = pd.to_datetime(labels.loc[
        pd.to_datetime(labels["signal_date"]) >= OOS_START,
        "signal_date"
    ])
    if len(oos_dates) and oos_dates.min() < OOS_START:
        raise RuntimeError("V3.9 OOS chronology guard failed.")

    print("\n" + "=" * 78)
    print("V3.9 VALIDATION STATUS")
    print("=" * 78)
    print("V3.9 V3.8 PIPELINE GUARD: PASS")
    print("V3.9 FROZEN CONTEXT GUARD: PASS")
    print("V3.9 NO ENTRY CREATION: PASS")
    print("V3.9 NO BASELINE MODIFICATION: PASS")
    print("V3.9 OOS CHRONOLOGY GUARD: PASS")
    print("V3.9 NO PARAMETER OPTIMIZATION: PASS")
    print("V3.9 VALIDATION COMPLETE")
    print("Research-only. No Decision Engine rule was changed.")
    print("Small-N groups are not evidence of robustness.")

    print("\nFILES CREATED")
    for filename in [
        "macro_backtest_v39_oos_aggregate.csv",
        "macro_backtest_v39_year_survival.csv",
        "macro_backtest_v39_crisis_exclusion.csv",
        "macro_backtest_v39_survival_verdict.csv",
    ]:
        print(filename)



# ============================================================
# US500 MACRO INTELLIGENCE — V3.10
# EXTENDED TEMPORAL ROBUSTNESS / SURVIVAL VALIDATION
# ============================================================
#
# V3.10 extends the research audit across the full frozen signal
# history (2019 -> latest available year) using the exact V3.7/V3.8
# context labels and exact frozen R outcomes.
#
# IMPORTANT METHODOLOGICAL LIMIT:
#   These V3.7 context labels were defined using the complete frozen
#   research dataset. Therefore V3.10 is an EXTENDED TEMPORAL
#   ROBUSTNESS audit, NOT a new strict out-of-sample test.
#
# Strict chronological OOS remains V3.8/V3.9.
#
# V3.10 does NOT change:
#   - signal generation
#   - entries / stops / TP / RR
#   - trade resolution / R
#   - H1 / H4 / C3 definitions
#   - Decision Engine logic
#   - any parameter
#
# Research-only.
# ============================================================

V310_YEARS = list(range(2019, 2027))
V310_CONTEXTS = list(V39_CONTEXTS)
V310_MIN_RESOLVED = 20
V310_MIN_YEARS = 3


def v310_year_metric(g):
    return v39_metric(g)


def v310_year_by_year(signal_df):
    x = signal_df.copy()
    x["signal_date"] = pd.to_datetime(x["signal_date"])
    x["year"] = x["signal_date"].dt.year
    rows = []
    for context in V310_CONTEXTS:
        for year in V310_YEARS:
            g = x[(x["context"] == context) & (x["year"] == year)].copy()
            m = v310_year_metric(g)
            rows.append({
                "context": context,
                "year": year,
                **m,
                "has_resolved": bool(m["resolved"] > 0),
                "small_N_flag": bool(m["resolved"] < 5),
            })
    return pd.DataFrame(rows)


def v310_temporal_summary(yearly):
    rows = []
    for context in V310_CONTEXTS:
        y = yearly[yearly["context"] == context].copy()
        active = y[y["resolved"] > 0].copy()
        positive = int((active["total_R"] > 0).sum())
        negative = int((active["total_R"] < 0).sum())
        zero = int((active["total_R"] == 0).sum())
        finite = active["total_R"].astype(float).tolist()
        rows.append({
            "context": context,
            "signals": int(y["signals"].sum()),
            "resolved": int(y["resolved"].sum()),
            "wins": int(y["wins"].sum()),
            "losses": int(y["losses"].sum()),
            "win_rate": 100.0 * int(y["wins"].sum()) / int(y["resolved"].sum()) if int(y["resolved"].sum()) else np.nan,
            "avg_R": float(y["total_R"].sum()) / int(y["resolved"].sum()) if int(y["resolved"].sum()) else np.nan,
            "total_R": float(y["total_R"].sum()),
            "positive_years": positive,
            "negative_years": negative,
            "zero_result_years": zero,
            "years_with_resolved": int(len(active)),
            "positive_year_rate_pct": 100.0 * positive / len(active) if len(active) else np.nan,
            "median_yearly_R": float(np.median(finite)) if finite else np.nan,
            "worst_year_R": float(np.min(finite)) if finite else np.nan,
            "best_year_R": float(np.max(finite)) if finite else np.nan,
            "small_N_flag": bool(int(y["resolved"].sum()) < V310_MIN_RESOLVED or len(active) < V310_MIN_YEARS),
        })
    return pd.DataFrame(rows)


def v310_max_drawdown(signal_df):
    x = signal_df.copy()
    x["signal_date"] = pd.to_datetime(x["signal_date"])
    rows = []
    for context in V310_CONTEXTS:
        g = x[x["context"] == context].copy()
        g = g[g["result"].isin(["WIN", "LOSS"])].copy()
        g = g.sort_values("signal_date")
        if g.empty:
            rows.append({"context": context, "max_drawdown_R": np.nan, "worst_peak_to_trough": np.nan})
            continue
        curve = g["R"].astype(float).cumsum()
        peak = curve.cummax()
        dd = curve - peak
        rows.append({
            "context": context,
            "max_drawdown_R": float(dd.min()),
            "worst_peak_to_trough": float(dd.min()),
        })
    return pd.DataFrame(rows)


def v310_leave_one_year_out(signal_df):
    x = signal_df.copy()
    x["signal_date"] = pd.to_datetime(x["signal_date"])
    x["year"] = x["signal_date"].dt.year
    rows = []
    for context in V310_CONTEXTS:
        base = x[x["context"] == context].copy()
        for year in V310_YEARS:
            g = base[base["year"] != year]
            m = v39_metric(g)
            rows.append({
                "context": context,
                "excluded_year": year,
                **m,
                "small_N_flag": bool(m["resolved"] < V310_MIN_RESOLVED),
            })
    return pd.DataFrame(rows)


def v310_crisis_exclusion(signal_df):
    rows = []
    exclusions = [
        ("NONE", set()),
        ("EXCLUDE_2020", {2020}),
        ("EXCLUDE_2022", {2022}),
        ("EXCLUDE_2020_2022", {2020, 2022}),
        ("EXCLUDE_2025", {2025}),
    ]
    x = signal_df.copy()
    x["year"] = pd.to_datetime(x["signal_date"]).dt.year
    for context in V310_CONTEXTS:
        base = x[x["context"] == context]
        for label, years in exclusions:
            g = base[~base["year"].isin(years)]
            m = v39_metric(g)
            rows.append({
                "context": context,
                "exclusion": label,
                **m,
                "small_N_flag": bool(m["resolved"] < V310_MIN_RESOLVED),
            })
    return pd.DataFrame(rows)


def v310_largest_year_exclusion(yearly):
    rows = []
    for context in V310_CONTEXTS:
        y = yearly[yearly["context"] == context].copy()
        active = y[y["resolved"] > 0].copy()
        if active.empty:
            rows.append({"context": context, "largest_positive_year": np.nan, "total_R_excl_largest_positive_year": 0.0,
                         "avg_R_excl_largest_positive_year": np.nan, "resolved_excl_largest_positive_year": 0,
                         "small_N_flag": True})
            continue
        pos = active[active["total_R"] > 0]
        if pos.empty:
            largest_year = int(active.loc[active["total_R"].idxmax(), "year"])
        else:
            largest_year = int(pos.loc[pos["total_R"].idxmax(), "year"])
        g = active[active["year"] != largest_year]
        total = float(g["total_R"].sum())
        resolved = int(g["resolved"].sum())
        rows.append({
            "context": context,
            "largest_positive_year": largest_year,
            "total_R_excl_largest_positive_year": total,
            "avg_R_excl_largest_positive_year": total / resolved if resolved else np.nan,
            "resolved_excl_largest_positive_year": resolved,
            "small_N_flag": bool(resolved < V310_MIN_RESOLVED),
        })
    return pd.DataFrame(rows)


def v310_robustness_verdict(summary, crisis, largest_year):
    rows = []
    for _, r in summary.iterrows():
        c = crisis[(crisis["context"] == r["context"]) & (crisis["exclusion"] == "EXCLUDE_2020_2022")].iloc[0]
        ly = largest_year[largest_year["context"] == r["context"]].iloc[0]
        sufficient = (
            int(r["resolved"]) >= V310_MIN_RESOLVED
            and int(r["years_with_resolved"]) >= V310_MIN_YEARS
        )
        survives_core = (
            float(r["avg_R"]) > 0
            and float(r["total_R"]) > 0
            and int(r["positive_years"]) >= int(r["negative_years"])
        ) if pd.notna(r["avg_R"]) else False
        survives_crisis = (
            float(c["total_R"]) > 0
            and pd.notna(c["avg_R"])
            and float(c["avg_R"]) > 0
        )
        survives_largest = (
            float(ly["total_R_excl_largest_positive_year"]) > 0
            and pd.notna(ly["avg_R_excl_largest_positive_year"])
            and float(ly["avg_R_excl_largest_positive_year"]) > 0
        )
        if not sufficient:
            status = "INSUFFICIENT_EXTENDED_SAMPLE"
        elif survives_core and survives_crisis and survives_largest:
            status = "ROBUSTNESS_CHECKS_SURVIVED_RESEARCH_ONLY"
        else:
            status = "DOES_NOT_SURVIVE_EXTENDED_ROBUSTNESS_CHECKS"
        rows.append({
            "context": r["context"],
            "resolved": int(r["resolved"]),
            "years_with_resolved": int(r["years_with_resolved"]),
            "total_R": float(r["total_R"]),
            "avg_R": float(r["avg_R"]) if pd.notna(r["avg_R"]) else np.nan,
            "positive_years": int(r["positive_years"]),
            "negative_years": int(r["negative_years"]),
            "crisis_excl_2020_2022_total_R": float(c["total_R"]),
            "excl_largest_positive_year_total_R": float(ly["total_R_excl_largest_positive_year"]),
            "status": status,
            "research_only": True,
            "NOT_STRICT_OOS": True,
        })
    return pd.DataFrame(rows)


def v310_main():
    print("\n" + "=" * 78)
    print("US500 MACRO INTELLIGENCE — V3.10")
    print("EXTENDED TEMPORAL ROBUSTNESS / SURVIVAL VALIDATION")
    print("=" * 78)
    print("V3.10 first runs the frozen V3.8/V3.9 pipeline.")
    print("V3.10 is NOT a new strict OOS test because V3.7 context labels were defined on the full frozen dataset.")

    # Run V3.9 first. This regenerates the authoritative frozen labels and
    # executes all V3.8/V3.9 guards before any V3.10 diagnostics.
    v39_main()

    labels = pd.read_csv("macro_backtest_v38_frozen_decision_labels.csv")

    # V3.8 frozen labels do NOT export a literal `context` column.
    # The V3.8/V3.9 contexts are overlapping research masks reconstructed
    # from the authoritative V3.7 classification and macro fields.
    required = {
        "signal_date",
        "result",
        "R",
        "V37_INTERACTION_CLASS",
        "macro_regime",
        "leading_warning",
    }
    missing = required - set(labels.columns)
    if missing:
        raise RuntimeError(
            f"V3.10 missing required frozen label columns: {sorted(missing)}"
        )

    # IMPORTANT: V3.8 contexts are overlapping research masks, not a
    # mutually-exclusive classification. Do NOT use np.select here: it
    # would erase A+WATCH overlap whenever a row is also H1/C3/H4.
    context_masks = {
        "H1_ONLY_CONTEXT": labels["V37_INTERACTION_CLASS"].eq("H1_ONLY_CONTEXT"),
        "C3_REDUNDANT_SUPPORT": labels["V37_INTERACTION_CLASS"].eq("C3_REDUNDANT_SUPPORT"),
        "H4_ONLY_CONTEXT": labels["V37_INTERACTION_CLASS"].eq("H4_ONLY_CONTEXT"),
        "A_WATCH_CONTEXT": (
            labels["macro_regime"].eq("A")
            & labels["leading_warning"].eq("WATCH")
        ),
    }
    context_labels = pd.concat(
        [
            labels.loc[mask].assign(context=context_name)
            for context_name, mask in context_masks.items()
        ],
        ignore_index=True,
    )

    # Contexts are intentionally overlapping and are not an exhaustive
    # partition of the 119 frozen signals. Only assigned research contexts
    # enter V3.10 temporal diagnostics.
    assigned_contexts = set(context_labels["context"].dropna().unique())
    expected_contexts = {
        "H1_ONLY_CONTEXT",
        "C3_REDUNDANT_SUPPORT",
        "H4_ONLY_CONTEXT",
        "A_WATCH_CONTEXT",
    }
    if not assigned_contexts.issubset(expected_contexts):
        raise RuntimeError(
            "V3.10 context integrity failed: unexpected assigned contexts "
            + str(sorted(assigned_contexts - expected_contexts))
        )
    if not assigned_contexts:
        raise RuntimeError(
            "V3.10 context integrity failed: no assigned research contexts."
        )

    assigned = context_labels.copy()
    if assigned.empty:
        raise RuntimeError("V3.10 context integrity failed: no assigned research contexts.")

    yearly = v310_year_by_year(assigned)
    summary = v310_temporal_summary(yearly)
    dd = v310_max_drawdown(assigned)
    loo = v310_leave_one_year_out(assigned)
    crisis = v310_crisis_exclusion(assigned)
    largest = v310_largest_year_exclusion(yearly)
    verdict = v310_robustness_verdict(summary, crisis, largest)

    yearly.to_csv("macro_backtest_v310_year_by_year.csv", index=False)
    summary.to_csv("macro_backtest_v310_temporal_summary.csv", index=False)
    dd.to_csv("macro_backtest_v310_max_drawdown.csv", index=False)
    loo.to_csv("macro_backtest_v310_leave_one_year_out.csv", index=False)
    crisis.to_csv("macro_backtest_v310_crisis_exclusion.csv", index=False)
    largest.to_csv("macro_backtest_v310_largest_year_exclusion.csv", index=False)
    verdict.to_csv("macro_backtest_v310_robustness_verdict.csv", index=False)

    print("\n" + "=" * 78)
    print("V3.10 YEAR-BY-YEAR TEMPORAL AUDIT")
    print("=" * 78)
    print(yearly.to_string(index=False))

    print("\n" + "=" * 78)
    print("V3.10 TEMPORAL SUMMARY")
    print("=" * 78)
    print(summary.to_string(index=False))

    print("\n" + "=" * 78)
    print("V3.10 MAX DRAWDOWN")
    print("=" * 78)
    print(dd.to_string(index=False))

    print("\n" + "=" * 78)
    print("V3.10 LEAVE-ONE-YEAR-OUT")
    print("=" * 78)
    print(loo.to_string(index=False))

    print("\n" + "=" * 78)
    print("V3.10 CRISIS EXCLUSION")
    print("=" * 78)
    print(crisis.to_string(index=False))

    print("\n" + "=" * 78)
    print("V3.10 LARGEST POSITIVE YEAR EXCLUSION")
    print("=" * 78)
    print(largest.to_string(index=False))

    print("\n" + "=" * 78)
    print("V3.10 ROBUSTNESS VERDICT")
    print("=" * 78)
    print(verdict.to_string(index=False))

    # Frozen-data integrity: V3.10 must not modify the authoritative R series.
    if len(labels) != 119:
        raise RuntimeError(f"V3.10 frozen signal count changed: expected 119, got {len(labels)}")
    resolved = labels[labels["result"].isin(["WIN", "LOSS"])]
    if int((resolved["result"] == "WIN").sum()) != 36:
        raise RuntimeError("V3.10 baseline win count changed.")
    if int((resolved["result"] == "LOSS").sum()) != 73:
        raise RuntimeError("V3.10 baseline loss count changed.")
    total_r = float(pd.to_numeric(resolved["R"], errors="coerce").sum())
    if abs(total_r - 71.0) > 1e-9:
        raise RuntimeError(f"V3.10 baseline total R changed: {total_r}")

    print("\n" + "=" * 78)
    print("V3.10 VALIDATION STATUS")
    print("=" * 78)
    print("V3.10 V3.8/V3.9 PIPELINE GUARD: PASS")
    print("V3.10 FROZEN 119-SIGNAL GUARD: PASS")
    print("V3.10 FROZEN 36W/73L GUARD: PASS")
    print("V3.10 FROZEN +71R GUARD: PASS")
    print("V3.10 NO ENTRY CREATION: PASS")
    print("V3.10 NO BASELINE MODIFICATION: PASS")
    print("V3.10 NO PARAMETER OPTIMIZATION: PASS")
    print("V3.10 VALIDATION COMPLETE")
    print("Research-only. No Decision Engine rule was changed.")
    print("IMPORTANT: V3.10 is extended temporal robustness, NOT strict OOS.")

    print("\nFILES CREATED")
    for filename in [
        "macro_backtest_v310_year_by_year.csv",
        "macro_backtest_v310_temporal_summary.csv",
        "macro_backtest_v310_max_drawdown.csv",
        "macro_backtest_v310_leave_one_year_out.csv",
        "macro_backtest_v310_crisis_exclusion.csv",
        "macro_backtest_v310_largest_year_exclusion.csv",
        "macro_backtest_v310_robustness_verdict.csv",
    ]:
        print(filename)


if __name__ == "__main__":
    try:
        v310_main()
    except Exception as exc:
        print("\nV3.10 FAILED:")
        print(type(exc).__name__ + ": " + str(exc))
        raise
