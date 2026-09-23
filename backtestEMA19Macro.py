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
# that existed before that day. Shift prevents the current day's High
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


def v26_statis
