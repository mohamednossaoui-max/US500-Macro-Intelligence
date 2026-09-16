# ============================================================
# US500 MACRO BACKTEST V2.1 - CLEAN
# FROZEN EMA19 BASELINE + MACRO V2.1 CALIBRATION
# ============================================================
# Frozen baseline configuration validated by V3:
# ATR_WILDER / TOUCH_CLOSE_ABOVE / ROW_GAP_1 / OVERLAP
# Reference: 119 signals, 117 valid, 2 invalid SL,
# 109 resolved, 36 wins, 73 losses, 3 ambiguous, 5 open,
# +71R, PF ~= 1.973.
#
# V2.1 is research/calibration only. It does NOT modify entries,
# exits, sizing, or the Decision Engine.
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
    df["EMA19"] = df["Close"].ewm(span=EMA19, adjust=False, min_periods=EMA19).mean()
    df["EMA200"] = df["Close"].ewm(span=EMA200, adjust=False, min_periods=EMA200).mean()
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


def print_report(title, report, key):
    print("\n" + "=" * 72); print(title); print("=" * 72)
    if report.empty:
        print("No data available."); return
    cols = [key,"signals","valid","resolved","wins","losses","ambiguous","open","win_rate","avg_R","total_R","profit_factor"]
    print(report[cols].to_string(index=False))


def main():
    market = load_market()
    print(f"Market rows: {len(market)} | {market.index.min().date()} -> {market.index.max().date()}")
    baseline = build_baseline_trades(market)
    baseline_ok = print_baseline_check(baseline)
    if not baseline_ok:
        raise RuntimeError("FROZEN BASELINE FAILED. V2.1 calibration is stopped; do not use these results.")

    fred = load_fred()
    trades = attach_macro(baseline, fred)
    trades = add_drawdown(trades, market)
    trades = add_zones(trades)

    print_report("MACRO REGIME BACKTEST V2.1", grouped_report(trades, "macro_regime"), "macro_regime")
    print_report("LEADING WARNING BACKTEST", grouped_report(trades, "leading_warning"), "leading_warning")
    for dim in DIMENSIONS:
        print_report(f"{dim.upper()} MOMENTUM", grouped_report(trades, f"{dim}_momentum"), f"{dim}_momentum")
    for dim in ("credit", "labor", "liquidity"):
        print_report(f"DRAWDOWN x {dim.upper()} MOMENTUM", grouped_report(trades, "drawdown_bucket"), "drawdown_bucket")

    trades.to_csv("macro_backtest_v21_trades.csv", index=False)
    grouped_report(trades, "macro_regime").to_csv("macro_backtest_v21_regimes.csv", index=False)
    grouped_report(trades, "leading_warning").to_csv("macro_backtest_v21_leading_warning.csv", index=False)
    grouped_report(trades, "macro_stress_zone").to_csv("macro_backtest_v21_stress_zones.csv", index=False)
    grouped_report(trades, "macro_momentum_zone").to_csv("macro_backtest_v21_momentum_zones.csv", index=False)
    print("\nMACRO CALIBRATION V2.1 COMPLETE")

if __name__ == "__main__":
    main()
