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



Nossaoui Mohammed
Formateur Génie Civil OFPPT
+212763324685
   

On Wed, 16 Sep 2026 at 16:55 nossaoui mohamed.gnav <mohamed.nossaoui@gmail.com> wrote:
# ============================================================
# US500 MACRO BACKTEST V2.1
# FROZEN EMA19 BASELINE
# + MACRO V2
# + MACRO CALIBRATION V2.1
# ============================================================
#
# IMPORTANT:
# The EMA19 signal engine is FROZEN.
#
# BASELINE:
# 119 signals / 117 valid / 2 invalid SL
# 109 resolved / 36 wins / 73 losses / 3 ambiguous / 5 open
# +71R / PF ~= 1.973
#
# V2.1 PURPOSE:
#
# This version does NOT modify the trading strategy.
#
# It adds:
#
# 1. Macro Level
# 2. Macro Momentum
# 3. Direction of deterioration
# 4. Leading-stress analysis
# 5. Drawdown x Macro Momentum analysis
#
# Six dimensions:
#
# Growth
# Inflation
# Labor
# Rates
# Credit
# Liquidity
#
# ------------------------------------------------------------
# NO LOOK-AHEAD
# ------------------------------------------------------------
#
# Daily data:
# observations available on/before signal date
#
# Monthly data:
# previous calendar month's observation
#
# ------------------------------------------------------------
# IMPORTANT
#
# V2.1 is a RESEARCH / CALIBRATION layer.
#
# It is NOT connected to the Decision Engine.
#
# ============================================================

import os
import warnings

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore")


# ============================================================
# CONFIGURATION
# ============================================================

TICKER = "^GSPC"
START_DATE = "2019-01-01"

RR = 4.0

EMA19 = 19
EMA200 = 200
ATR14 = 14
LOW_LOOKBACK = 5

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"


# ============================================================
# FRED SERIES
# ============================================================

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


# ============================================================
# MONTHLY SERIES
# ============================================================

MONTHLY_SERIES = {

"UNRATE",
"INDPRO",
"RETAIL",
"PCE",
"CORE_PCE",
"FEDFUNDS",

}


DAILY_SERIES = (
set(FRED_SERIES)
- MONTHLY_SERIES
)


# ============================================================
# MOMENTUM CONFIGURATION
# ============================================================

# Fixed lookbacks.
#
# These are intentionally simple and transparent.
# They are NOT optimized on the historical results.

DAILY_MOMENTUM_LOOKBACK = 20
MEDIUM_DAILY_LOOKBACK = 60

MONTHLY_MOMENTUM_LOOKBACK = 3
MEDIUM_MONTHLY_LOOKBACK = 6


# ============================================================
# MARKET DATA
# FROZEN BASELINE
# ============================================================

def load_market():

df = yf.download(
TICKER,
start=START_DATE,
auto_adjust=False,
progress=False,
)

if df.empty:

raise RuntimeError(
"Yahoo Finance returned no market data."
)

if isinstance(
df.columns,
pd.MultiIndex,
):

df.columns = (
df.columns
.get_level_values(0)
)

df = df[
[
"Open",
"High",
"Low",
"Close",
]
].copy()

df.index = (
pd.to_datetime(
df.index
)
.tz_localize(None)
)

df = (
df
.sort_index()
.dropna()
)

for column in [
"Open",
"High",
"Low",
"Close",
]:

df[column] = pd.to_numeric(
df[column],
errors="coerce",
)

df.dropna(inplace=True)

# --------------------------------------------------------
# EMA19
# --------------------------------------------------------

df["EMA19"] = (
df["Close"]
.ewm(
span=EMA19,
adjust=False,
min_periods=EMA19,
)
.mean()
)

# --------------------------------------------------------
# EMA200
# --------------------------------------------------------

df["EMA200"] = (
df["Close"]
.ewm(
span=EMA200,
adjust=False,
min_periods=EMA200,
)
.mean()
)

# --------------------------------------------------------
# TRUE RANGE
# --------------------------------------------------------

previous_close = (
df["Close"].shift(1)
)

tr = pd.concat(
[
df["High"] - df["Low"],

(
df["High"]
- previous_close
).abs(),

(
df["Low"]
- previous_close
).abs(),
],
axis=1,
).max(axis=1)

df["TR"] = tr

# --------------------------------------------------------
# WILDER ATR(14)
# --------------------------------------------------------

df["ATR14_WILDER"] = (
tr
.ewm(
alpha=1 / ATR14,
adjust=False,
min_periods=ATR14,
)
.mean()
)

return df


# ============================================================
# FROZEN EMA19 SIGNAL ENGINE
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

# ----------------------------------------------------
# EXACT BASELINE CONDITION
# ----------------------------------------------------

if not (
row["Close"] > row["EMA200"]
and row["EMA19"] > row["EMA200"]
and row["Low"] <= row["EMA19"]
and row["Close"] > row["EMA19"]
):

continue

raw.append(i)

# --------------------------------------------------------
# EXACT ROW_GAP_1 SPACING
# --------------------------------------------------------

selected = []

for p, i in enumerate(raw):

if (
p == 0
or raw[p] - raw[p - 1] > 1
):

selected.append(i)

return selected


# ============================================================
# FROZEN STOP
# ============================================================

def baseline_stop(
df,
i,
):

if i < LOW_LOOKBACK + 1:

return np.nan

previous_5 = df.iloc[
i - LOW_LOOKBACK:i
]

previous_atr = (
df.iloc[i - 1][
"ATR14_WILDER"
]
)

if pd.isna(previous_atr):

return np.nan

return float(
previous_5["Low"].min()
- 0.5 * previous_atr
)


# ============================================================
# FROZEN TRADE RESOLUTION
# ============================================================

def resolve_trade(
df,
entry_i,
entry,
stop,
):

if (
not np.isfinite(stop)
or stop >= entry
):

return (
"INVALID_SL",
np.nan,
None,
)

risk = entry - stop

target = (
entry
+ RR * risk
)

for j in range(
entry_i + 1,
len(df),
):

high = float(
df.iloc[j]["High"]
)

low = float(
df.iloc[j]["Low"]
)

hit_tp = (
high >= target
)

hit_sl = (
low <= stop
)

# Same candle:
# preserved as AMBIGUOUS.

if hit_tp and hit_sl:

return (
"AMBIGUOUS",
np.nan,
j,
)

if hit_tp:

return (
"WIN",
RR,
j,
)

if hit_sl:

return (
"LOSS",
-1.0,
j,
)

return (
"OPEN",
np.nan,
None,
)


# ============================================================
# BUILD FROZEN BASELINE TRADES
# ============================================================

def build_baseline_trades(df):

signal_indices = (
build_baseline_signals(df)
)

rows = []

for i in signal_indices:

entry = float(
df.iloc[i]["Close"]
)

stop = baseline_stop(
df,
i,
)

(
result,
r_mult,
exit_i,
) = resolve_trade(
df,
i,
entry,
stop,
)

rows.append(
{

"signal_date":
df.index[i],

"year":
int(
df.index[i].year
),

"signal_index":
i,

"entry":
entry,

"stop":
stop,

"risk_points":
(
entry - stop
if np.isfinite(stop)
else np.nan
),

"target":
(
entry
+ RR * (
entry - stop
)
if (
np.isfinite(stop)
and stop < entry
)
else np.nan
),

"result":
result,

"R":
r_mult,

"exit_date":
(
df.index[exit_i]
if exit_i is not None
else pd.NaT
),
}
)

return pd.DataFrame(rows)


# ============================================================
# FRED API
# ============================================================

def get_fred_key():

key = os.getenv(
"FRED_API_KEY",
"",
).strip()

if not key:

raise RuntimeError(
"FRED_API_KEY is missing. "
"Add it as a GitHub Actions "
"secret/environment variable; "
"do not put the key in code."
)

return key


# ============================================================
# LOAD ONE FRED SERIES
# ============================================================

def fred_series(
series_id,
api_key,
):

params = {

"series_id":
series_id,

"api_key":
api_key,

"file_type":
"json",

"observation_start":
START_DATE,

"observation_end":
pd.Timestamp.today().strftime(
"%Y-%m-%d"
),
}

response = requests.get(
FRED_URL,
params=params,
timeout=30,
)

response.raise_for_status()

payload = response.json()

observations = payload.get(
"observations",
[],
)

if not observations:

return pd.Series(
dtype=float,
name=series_id,
)

rows = []

for obs in observations:

value = obs.get(
"value",
".",
)

if value in (
".",
"",
None,
):

continue

try:

value = float(value)

except (
TypeError,
ValueError,
):

continue

rows.append(
(
pd.to_datetime(
obs["date"]
),
value,
)
)

if not rows:

return pd.Series(
dtype=float,
name=series_id,
)

s = pd.Series(
data=[
value
for _, value in rows
],
index=[
date
for date, _ in rows
],
name=series_id,
)

s.index = (
pd.to_datetime(
s.index
)
.tz_localize(None)
)

return s.sort_index()


# ============================================================
# LOAD ALL FRED DATA
# ============================================================

def load_fred():

key = get_fred_key()

data = {}

print()
print("=" * 72)
print("LOADING FRED MACRO DATA")
print("=" * 72)

for (
name,
series_id,
) in FRED_SERIES.items():

try:

s = fred_series(
series_id,
key,
)

data[name] = s

print(
f"{name:20s} "
f"{series_id:16s} "
f"{len(s):5d} observations"
)

except Exception as exc:

print(
f"{name:20s} "
f"{series_id:16s} "
f"ERROR: {exc}"
)

data[name] = pd.Series(
dtype=float,
name=series_id,
)

return data


# ============================================================
# AS-OF CUTOFF
# ============================================================

def get_asof_cutoff(
date,
monthly=False,
):

d = pd.Timestamp(date)

if monthly:

return (
d.to_period("M")
.start_time
- pd.Timedelta(days=1)
)

return d


# ============================================================
# AS-OF SERIES
# ============================================================

def series_asof(
series,
date,
monthly=False,
):

if (
series is None
or series.empty
):

return pd.Series(
dtype=float
)

cutoff = get_asof_cutoff(
date,
monthly,
)

return (
series
.loc[
series.index <= cutoff
]
.dropna()
)


# ============================================================
# AS-OF VALUE
# ============================================================

def value_asof(
series,
date,
monthly=False,
):

s = series_asof(
series,
date,
monthly,
)

if s.empty:

return np.nan

return float(
s.iloc[-1]
)


# ============================================================
# AS-OF PERCENT CHANGE
# ============================================================

def pct_change_asof(
series,
date,
periods,
monthly=False,
):

s = series_asof(
series,
date,
monthly,
)

if len(s) <= periods:

return np.nan

current = float(
s.iloc[-1]
)

previous = float(
s.iloc[-1 - periods]
)

if previous == 0:

return np.nan

return (
current / previous - 1.0
) * 100.0


# ============================================================
# AS-OF ABSOLUTE CHANGE
# ============================================================

def absolute_change_asof(
series,
date,
periods,
monthly=False,
):

s = series_asof(
series,
date,
monthly,
)

if len(s) <= periods:

return np.nan

return float(
s.iloc[-1]
- s.iloc[-1 - periods]
)


# ============================================================
# INFLATION YOY
# ============================================================

def inflation_yoy(
series,
date,
):

return pct_change_asof(
series,
date,
periods=12,
monthly=True,
)


# ============================================================
# SCORE HELPER
# ============================================================

def clip_score(x):

if not np.isfinite(x):

return np.nan

return float(
max(
0.0,
min(
100.0,
x,
),
)
)


# ============================================================
# MOMENTUM CLASSIFICATION
# ============================================================

def classify_momentum(
current,
short_change,
medium_change,
stress_direction="higher",
):

if not np.isfinite(
current
):

return (
"UNAVAILABLE",
np.nan,
)

if not np.isfinite(
short_change
):

return (
"UNAVAILABLE",
np.nan,
)

# --------------------------------------------------------
# stress_direction = higher
#
# Higher value = more stress.
#
# Example:
# Credit spread rising -> deterioration.
# Unemployment rising -> deterioration.
# VIX rising -> deterioration.
# --------------------------------------------------------

if stress_direction == "higher":

if (
short_change >= 15
or (
np.isfinite(
medium_change
)
and medium_change >= 25
)
):

return (
"STRONGLY DETERIORATING",
100.0,
)

if (
short_change >= 5
or (
np.isfinite(
medium_change
)
and medium_change >= 10
)
):

return (
"DETERIORATING",
75.0,
)

if (
short_change <= -5
or (
np.isfinite(
medium_change
)
and medium_change <= -10
)
):

return (
"IMPROVING",
25.0,
)

return (
"STABLE",
50.0,
)

# --------------------------------------------------------
# stress_direction = lower
#
# Lower value = more stress.
#
# Example:
# Industrial production falling.
# Retail sales falling.
# --------------------------------------------------------

if stress_direction == "lower":

if (
short_change <= -5
or (
np.isfinite(
medium_change
)
and medium_change <= -10
)
):

return (
"STRONGLY DETERIORATING",
100.0,
)

if (
short_change <= -2
or (
np.isfinite(
medium_change
)
and medium_change <= -5
)
):

return (
"DETERIORATING",
75.0,
)

if (
short_change >= 2
or (
np.isfinite(
medium_change
)
and medium_change >= 5
)
):

return (
"IMPROVING",
25.0,
)

return (
"STABLE",
50.0,
)

return (
"UNAVAILABLE",
np.nan,
)


# ============================================================
# GROWTH SCORE
# ============================================================

def score_growth(
fred,
date,
):

score = 50.0

reasons = []

indpro_yoy = pct_change_asof(
fred["INDPRO"],
date,
12,
monthly=True,
)

retail_yoy = pct_change_asof(
fred["RETAIL"],
date,
12,
monthly=True,
)

unrate = value_asof(
fred["UNRATE"],
date,
monthly=True,
)

claims_change = pct_change_asof(
fred["INITIAL_CLAIMS_4W"],
date,
12,
monthly=False,
)

components = []

# Industrial production

if np.isfinite(
indpro_yoy
):

if indpro_yoy >= 3:
components.append(15)

elif indpro_yoy >= 1:
components.append(30)

elif indpro_yoy >= 0:
components.append(45)

elif indpro_yoy >= -2:
components.append(65)

else:
components.append(85)

# Retail

if np.isfinite(
retail_yoy
):

if retail_yoy >= 5:
components.append(15)

elif retail_yoy >= 3:
components.append(30)

elif retail_yoy >= 1:
components.append(45)

elif retail_yoy >= 0:
components.append(60)

else:
components.append(80)

# Unemployment

if np.isfinite(
unrate
):

if unrate < 4:
components.append(15)

elif unrate < 4.5:
components.append(30)

elif unrate < 5:
components.append(50)

elif unrate < 6:
components.append(75)

else:
components.append(95)

# Claims

if np.isfinite(
claims_change
):

if claims_change < 0:
components.append(20)

elif claims_change < 5:
components.append(35)

elif claims_change < 10:
components.append(50)

elif claims_change < 20:
components.append(70)

else:
components.append(90)

if components:

score = float(
np.mean(components)
)

if score >= 70:

reasons.append(
"Growth deterioration is significant."
)

elif score >= 50:

reasons.append(
"Growth indicators show some deterioration."
)

elif score <= 30:

reasons.append(
"Growth conditions remain relatively strong."
)

return (
clip_score(score),
reasons,
)


# ============================================================
# INFLATION SCORE
# ============================================================

def score_inflation(
fred,
date,
):

score = 50.0

reasons = []

pce_yoy = inflation_yoy(
fred["PCE"],
date,
)

core_pce_yoy = inflation_yoy(
fred["CORE_PCE"],
date,
)

components = []

if np.isfinite(
pce_yoy
):

if pce_yoy < 2:
components.append(10)

elif pce_yoy < 2.5:
components.append(25)

elif pce_yoy < 3:
components.append(45)

elif pce_yoy < 4:
components.append(70)

else:
components.append(90)

if np.isfinite(
core_pce_yoy
):

if core_pce_yoy < 2:
components.append(10)

elif core_pce_yoy < 2.5:
components.append(25)

elif core_pce_yoy < 3:
components.append(45)

elif core_pce_yoy < 3.5:
components.append(70)

else:
components.append(95)

if components:

score = float(
np.mean(components)
)

if score >= 70:

reasons.append(
"Inflation pressure is elevated."
)

elif score >= 50:

reasons.append(
"Inflation remains above a comfortable range."
)

elif score <= 30:

reasons.append(
"Inflation pressure is relatively contained."
)

return (
clip_score(score),
reasons,
)


# ============================================================
# LABOR SCORE
# ============================================================

def score_labor(
fred,
date,
):

score = 50.0

reasons = []

unrate = value_asof(
fred["UNRATE"],
date,
monthly=True,
)

claims_change = pct_change_asof(
fred["INITIAL_CLAIMS_4W"],
date,
12,
monthly=False,
)

components = []

if np.isfinite(
unrate
):

if unrate < 4:
components.append(10)

elif unrate < 4.5:
components.append(30)

elif unrate < 5:
components.append(50)

elif unrate < 6:
components.append(75)

else:
components.append(95)

if np.isfinite(
claims_change
):

if claims_change < 0:
components.append(15)

elif claims_change < 5:
components.append(30)

elif claims_change < 10:
components.append(50)

elif claims_change < 20:
components.append(75)

else:
components.append(95)

if components:

score = float(
np.mean(components)
)

if score >= 70:

reasons.append(
"Labor-market deterioration is elevated."
)

elif score >= 50:

reasons.append(
"Labor indicators are showing some stress."
)

elif score <= 30:

reasons.append(
"Labor conditions remain relatively healthy."
)

return (
clip_score(score),
reasons,
)


# ============================================================
# RATES SCORE
# ============================================================

def score_rates(
fred,
date,
):

score = 50.0

reasons = []

us10y = value_asof(
fred["US10Y"],
date,
)

us2y = value_asof(
fred["US2Y"],
date,
)

curve = value_asof(
fred["T10Y2Y"],
date,
)

components = []

if np.isfinite(
us10y
):

if us10y < 2:
components.append(15)

elif us10y < 3:
components.append(30)

elif us10y < 4:
components.append(50)

elif us10y < 5:
components.append(75)

else:
components.append(90)

if np.isfinite(
us2y
):

if us2y < 1:
components.append(15)

elif us2y < 2:
components.append(30)

elif us2y < 3:
components.append(45)

elif us2y < 4:
components.append(65)

else:
components.append(85)

if np.isfinite(
curve
):

if curve < -1:
components.append(70)

elif curve < -0.5:
components.append(60)

elif curve < 0:
components.append(50)

else:
components.append(25)

if components:

score = float(
np.mean(components)
)

if score >= 70:

reasons.append(
"Rates are exerting significant pressure."
)

elif score >= 50:

reasons.append(
"Rates remain restrictive."
)

elif score <= 30:

reasons.append(
"Rates pressure is relatively limited."
)

return (
clip_score(score),
reasons,
)


# ============================================================
# CREDIT SCORE
# ============================================================

def score_credit(
fred,
date,
):

score = 50.0

reasons = []

hy = value_asof(
fred["HY_SPREAD"],
date,
)

corp = value_asof(
fred["CORP_OAS"],
date,
)

hy_change = pct_change_asof(
fred["HY_SPREAD"],
date,
60,
monthly=False,
)

components = []

if np.isfinite(
hy
):

if hy < 3:
components.append(10)

elif hy < 4:
components.append(25)

elif hy < 5:
components.append(50)

elif hy < 6:
components.append(75)

else:
components.append(95)

if np.isfinite(
corp
):

if corp < 1.5:
components.append(15)

elif corp < 2:
components.append(30)

elif corp < 2.5:
components.append(50)

elif corp < 3:
components.append(70)

else:
components.append(90)

if np.isfinite(
hy_change
):

if hy_change < 0:
components.append(15)

elif hy_change < 10:
components.append(30)

elif hy_change < 20:
components.append(50)

elif hy_change < 30:
components.append(75)

else:
components.append(95)

if components:

score = float(
np.mean(components)
)

if score >= 70:

reasons.append(
"Credit conditions are materially stressed."
)

elif score >= 50:

reasons.append(
"Credit conditions show increasing stress."
)

elif score <= 30:

reasons.append(
"Credit conditions remain relatively calm."
)

return (
clip_score(score),
reasons,
)


# ============================================================
# LIQUIDITY SCORE
# ============================================================

def score_liquidity(
fred,
date,
):

score = 50.0

reasons = []

nfci = value_asof(
fred["NFCI"],
date,
)

vix = value_asof(
fred["VIX"],
date,
)

dxy_change = pct_change_asof(
fred["DXY"],
date,
60,
monthly=False,
)

components = []

if np.isfinite(
nfci
):

if nfci < -0.5:
components.append(10)

elif nfci < 0:
components.append(25)

elif nfci < 0.5:
components.append(45)

elif nfci < 1:
components.append(70)

else:
components.append(95)

if np.isfinite(
vix
):

if vix < 15:
components.append(10)

elif vix < 20:
components.append(25)

elif vix < 25:
components.append(50)

elif vix < 30:
components.append(75)

else:
components.append(95)

if np.isfinite(
dxy_change
):

if dxy_change < 0:
components.append(20)

elif dxy_change < 5:
components.append(35)

elif dxy_change < 8:
components.append(55)

elif dxy_change < 12:
components.append(75)

else:
components.append(90)

if components:

score = float(
np.mean(components)
)

if score >= 70:

reasons.append(
"Liquidity / financial conditions are stressed."
)

elif score >= 50:

reasons.append(
"Financial conditions show some tightening."
)

elif score <= 30:

reasons.append(
"Liquidity conditions remain relatively easy."
)

return (
clip_score(score),
reasons,
)


# ============================================================
# GENERIC DIMENSION MOMENTUM
# ============================================================

def dimension_score_asof(
score_function,
fred,
date,
):

try:

score, _ = score_function(
fred,
date,
)

return score

except Exception:

return np.nan


def calculate_score_momentum(
score_function,
fred,
date,
):

current = dimension_score_asof(
score_function,
fred,
date,
)

d = pd.Timestamp(date)

short_date = (
d
- pd.Timedelta(
days=DAILY_MOMENTUM_LOOKBACK
)
)

medium_date = (
d
- pd.Timedelta(
days=MEDIUM_DAILY_LOOKBACK
)
)

short_score = (
dimension_score_asof(
score_function,
fred,
short_date,
)
)

medium_score = (
dimension_score_asof(
score_function,
fred,
medium_date,
)
)

if (
np.isfinite(current)
and np.isfinite(short_score)
):

short_change = (
current
- short_score
)

else:

short_change = np.nan

if (
np.isfinite(current)
and np.isfinite(medium_score)
):

medium_change = (
current
- medium_score
)

else:

medium_change = np.nan

if not np.isfinite(
short_change
):

return (
"UNAVAILABLE",
np.nan,
current,
short_change,
medium_change,
)

if (
short_change >= 15
or (
np.isfinite(
medium_change
)
and medium_change >= 25
)
):

status = (
"STRONGLY DETERIORATING"
)

elif (
short_change >= 5
or (
np.isfinite(
medium_change
)
and medium_change >= 10
)
):

status = "DETERIORATING"

elif (
short_change <= -5
or (
np.isfinite(
medium_change
)
and medium_change <= -10
)
):

status = "IMPROVING"

else:

status = "STABLE"

return (
status,
clip_score(
50
+ short_change
),
current,
short_change,
medium_change,
)


# ============================================================
# MACRO V2 + V2.1
# ============================================================

def classify_macro_v21(
fred,
date,
):

# --------------------------------------------------------
# V2 LEVELS
# --------------------------------------------------------

growth, growth_reasons = (
score_growth(
fred,
date,
)
)

inflation, inflation_reasons = (
score_inflation(
fred,
date,
)
)

labor, labor_reasons = (
score_labor(
fred,
date,
)
)

rates, rates_reasons = (
score_rates(
fred,
date,
)
)

credit, credit_reasons = (
score_credit(
fred,
date,
)
)

liquidity, liquidity_reasons = (
score_liquidity(
fred,
date,
)
)

# --------------------------------------------------------
# MOMENTUM
#
# Momentum is calculated from the historical change
# in the corresponding V2 stress score.
#
# This means:
#
# Positive change = more stress
# Negative change = less stress
# --------------------------------------------------------

(
growth_momentum,
growth_momentum_score,
_,
growth_short_change,
growth_medium_change,
) = calculate_score_momentum(
score_growth,
fred,
date,
)

(
inflation_momentum,
inflation_momentum_score,
_,
inflation_short_change,
inflation_medium_change,
) = calculate_score_momentum(
score_inflation,
fred,
date,
)

(
labor_momentum,
labor_momentum_score,
_,
labor_short_change,
labor_medium_change,
) = calculate_score_momentum(
score_labor,
fred,
date,
)

(
rates_momentum,
rates_momentum_score,
_,
rates_short_change,
rates_medium_change,
) = calculate_score_momentum(
score_rates,
fred,
date,
)

(
credit_momentum,
credit_momentum_score,
_,
credit_short_change,
credit_medium_change,
) = calculate_score_momentum(
score_credit,
fred,
date,
)

(
liquidity_momentum,
liquidity_momentum_score,
_,
liquidity_short_change,
liquidity_medium_change,
) = calculate_score_momentum(
score_liquidity,
fred,
date,
)

# --------------------------------------------------------
# OVERALL STRESS
# --------------------------------------------------------

levels = [
x
for x in [
growth,
inflation,
labor,
rates,
credit,
liquidity,
]
if np.isfinite(x)
]

if levels:

overall_stress = float(
np.mean(levels)
)

else:

overall_stress = np.nan

# --------------------------------------------------------
# OVERALL MOMENTUM
# --------------------------------------------------------

momentum_scores = [
x
for x in [
growth_momentum_score,
inflation_momentum_score,
labor_momentum_score,
rates_momentum_score,
credit_momentum_score,
liquidity_momentum_score,
]
if np.isfinite(x)
]

if momentum_scores:

overall_momentum = float(
np.mean(momentum_scores)
)

else:

overall_momentum = np.nan

# --------------------------------------------------------
# COUNT DETERIORATING DIMENSIONS
# --------------------------------------------------------

momentum_statuses = [

growth_momentum,
inflation_momentum,
labor_momentum,
rates_momentum,
credit_momentum,
liquidity_momentum,

]

deteriorating_count = sum(
x in [
"DETERIORATING",
"STRONGLY DETERIORATING",
]
for x in momentum_statuses
)

strong_deteriorating_count = sum(
x == "STRONGLY DETERIORATING"
for x in momentum_statuses
)

improving_count = sum(
x == "IMPROVING"
for x in momentum_statuses
)

# --------------------------------------------------------
# LEADING WARNING FLAGS
#
# Credit / Labor / Liquidity receive special attention
# because the research objective is to detect deterioration
# before large drawdowns.
# --------------------------------------------------------

leading_warning_count = sum(
x in [
"DETERIORATING",
"STRONGLY DETERIORATING",
]
for x in [
credit_momentum,
labor_momentum,
liquidity_momentum,
]
)

if (
credit_momentum
== "STRONGLY DETERIORATING"
or labor_momentum
== "STRONGLY DETERIORATING"
or liquidity_momentum
== "STRONGLY DETERIORATING"
):

leading_warning = (
"STRONG"
)

elif leading_warning_count >= 2:

leading_warning = (
"ELEVATED"
)

elif leading_warning_count == 1:

leading_warning = (
"WATCH"
)

else:

leading_warning = (
"NONE"
)

# --------------------------------------------------------
# REGIME CLASSIFICATION
#
# EXACT V2 LOGIC PRESERVED.
# --------------------------------------------------------

regime = "A"

regime_reason = ""

# F

if (
np.isfinite(credit)
and np.isfinite(liquidity)
and credit >= 75
and liquidity >= 75
):

regime = "F"

regime_reason = (
"Severe credit and liquidity stress."
)

# E

elif (
np.isfinite(growth)
and np.isfinite(labor)
and growth >= 70
and labor >= 70
):

regime = "E"

regime_reason = (
"Growth and labor conditions indicate "
"significant economic deterioration."
)

# D

elif (
np.isfinite(growth)
and np.isfinite(inflation)
and growth >= 65
and inflation >= 65
):

regime = "D"

regime_reason = (
"Growth deterioration is occurring alongside "
"elevated inflation pressure."
)

# C

elif (
np.isfinite(inflation)
and np.isfinite(rates)
and inflation >= 65
and rates >= 60
):

regime = "C"

regime_reason = (
"Inflation and rates are exerting "
"significant pressure."
)

# B

elif (
np.isfinite(growth)
and growth >= 60
and (
not np.isfinite(inflation)
or inflation < 55
)
):

regime = "B"

regime_reason = (
"Growth conditions are deteriorating while "
"inflation pressure remains relatively contained."
)

# A

else:

regime = "A"

regime_reason = (
"No dominant combination of macro stresses "
"meets the thresholds for B-F."
)

# --------------------------------------------------------
# SNAPSHOT
# --------------------------------------------------------

snapshot = {

"US10Y":
value_asof(
fred["US10Y"],
date,
),

"US2Y":
value_asof(
fred["US2Y"],
date,
),

"T10Y2Y":
value_asof(
fred["T10Y2Y"],
date,
),

"VIX":
value_asof(
fred["VIX"],
date,
),

"DXY":
value_asof(
fred["DXY"],
date,
),

"UNRATE":
value_asof(
fred["UNRATE"],
date,
monthly=True,
),

"INITIAL_CLAIMS_4W":
value_asof(
fred["INITIAL_CLAIMS_4W"],
date,
),

"HY_SPREAD":
value_asof(
fred["HY_SPREAD"],
date,
),

"CORP_OAS":
value_asof(
fred["CORP_OAS"],
date,
),

"NFCI":
value_asof(
fred["NFCI"],
date,
),

"INDPRO_YOY":
pct_change_asof(
fred["INDPRO"],
date,
12,
monthly=True,
),

"RETAIL_YOY":
pct_change_asof(
fred["RETAIL"],
date,
12,
monthly=True,
),

"PCE_YOY":
inflation_yoy(
fred["PCE"],
date,
),

"CORE_PCE_YOY":
inflation_yoy(
fred["CORE_PCE"],
date,
),
}

# --------------------------------------------------------
# REASONS
# --------------------------------------------------------

all_reasons = (
growth_reasons
+ inflation_reasons
+ labor_reasons
+ rates_reasons
+ credit_reasons
+ liquidity_reasons
)

return {

# ----------------------------------------------------
# REGIME
# ----------------------------------------------------

"macro_regime":
regime,

"macro_regime_reason":
regime_reason,

# ----------------------------------------------------
# LEVEL
# ----------------------------------------------------

"macro_stress":
overall_stress,

"growth_stress":
growth,

"inflation_stress":
inflation,

"labor_stress":
labor,

"rates_stress":
rates,

"credit_stress":
credit,

"liquidity_stress":
liquidity,

# ----------------------------------------------------
# MOMENTUM STATUS
# ----------------------------------------------------

"growth_momentum":
growth_momentum,

"inflation_momentum":
inflation_momentum,

"labor_momentum":
labor_momentum,

"rates_momentum":
rates_momentum,

"credit_momentum":
credit_momentum,

"liquidity_momentum":
liquidity_momentum,

# ----------------------------------------------------
# MOMENTUM SCORES
# ----------------------------------------------------

"growth_momentum_score":
growth_momentum_score,

"inflation_momentum_score":
inflation_momentum_score,

"labor_momentum_score":
labor_momentum_score,

"rates_momentum_score":
rates_momentum_score,

"credit_momentum_score":
credit_momentum_score,

"liquidity_momentum_score":
liquidity_momentum_score,

"macro_momentum":
overall_momentum,

# ----------------------------------------------------
# MOMENTUM CHANGES
# ----------------------------------------------------

"growth_short_change":
growth_short_change,

"growth_medium_change":
growth_medium_change,

"inflation_short_change":
inflation_short_change,

"inflation_medium_change":
inflation_medium_change,

"labor_short_change":
labor_short_change,

"labor_medium_change":
labor_medium_change,

"rates_short_change":
rates_short_change,

"rates_medium_change":
rates_medium_change,

"credit_short_change":
credit_short_change,

"credit_medium_change":
credit_medium_change,

"liquidity_short_change":
liquidity_short_change,

"liquidity_medium_change":
liquidity_medium_change,

# ----------------------------------------------------
# WARNING COUNTS
# ----------------------------------------------------

"deteriorating_count":
deteriorating_count,

"strong_deteriorating_count":
strong_deteriorating_count,

"improving_count":
improving_count,

"leading_warning":
leading_warning,

"leading_warning_count":
leading_warning_count,

# ----------------------------------------------------
# REASONS
# ----------------------------------------------------

"macro_reasons":
" | ".join(
all_reasons
),

**snapshot,
}


# ============================================================
# ATTACH MACRO
# ============================================================

def attach_macro(
trades,
fred,
):

rows = []

for _, trade in trades.iterrows():

snap = classify_macro_v21(
fred,
trade["signal_date"],
)

row = trade.to_dict()

row.update(snap)

rows.append(row)

return pd.DataFrame(rows)


# ============================================================
# SUMMARY
# ============================================================

def summarize_group(g):

wins = int(
(
g["result"]
== "WIN"
).sum()
)

losses = int(
(
g["result"]
== "LOSS"
).sum()
)

ambiguous = int(
(
g["result"]
== "AMBIGUOUS"
).sum()
)

open_trades = int(
(
g["result"]
== "OPEN"
).sum()
)

invalid = int(
(
g["result"]
== "INVALID_SL"
).sum()
)

resolved = (
wins
+ losses
)

total_r = float(
g["R"]
.dropna()
.sum()
)

gross_profit = float(
g.loc[
g["R"] > 0,
"R",
].sum()
)

gross_loss = abs(
float(
g.loc[
g["R"] < 0,
"R",
].sum()
)
)

if gross_loss > 0:

pf = (
gross_profit
/ gross_loss
)

else:

pf = np.nan

return {

"signals":
len(g),

"valid":
len(g) - invalid,

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

"win_rate":
(
100 * wins / resolved
if resolved
else np.nan
),

"avg_R":
(
float(
g["R"]
.dropna()
.mean()
)
if g["R"]
.notna()
.any()
else np.nan
),

"total_R":
total_r,

"profit_factor":
pf,
}


# ============================================================
# REGIME REPORT
# ============================================================

def regime_report(
trades,
):

rows = []

for (
regime,
g,
) in trades.groupby(
"macro_regime",
dropna=False,
):

s = summarize_group(g)

s[
"macro_regime"
] = regime

rows.append(s)

if not rows:

return pd.DataFrame()

return (
pd.DataFrame(rows)
.sort_values(
"macro_regime"
)
)


# ============================================================
# MOMENTUM STATUS REPORT
# ============================================================

def momentum_report(
trades,
column,
):

rows = []

for (
status,
g,
) in trades.groupby(
column,
dropna=False,
):

s = summarize_group(g)

s[
"momentum_status"
] = status

rows.append(s)

if not rows:

return pd.DataFrame()

return pd.DataFrame(
rows
).sort_values(
"momentum_status"
)


# ============================================================
# LEADING WARNING REPORT
# ============================================================

def leading_warning_report(
trades,
):

rows = []

for (
warning,
g,
) in trades.groupby(
"leading_warning",
dropna=False,
):

s = summarize_group(g)

s[
"leading_warning"
] = warning

rows.append(s)

if not rows:

return pd.DataFrame()

return pd.DataFrame(
rows
).sort_values(
"leading_warning"
)


# ============================================================
# ADD RUNNING MARKET DRAWDOWN
# ============================================================

def add_drawdown(
trades,
market,
):

running_high = (
market["High"]
.cummax()
)

rows = []

for _, trade in trades.iterrows():

d = trade[
"signal_date"
]

if d not in running_high.index:

dd = np.nan
ref_high = np.nan

else:

ref_high = float(
running_high.loc[d]
)

if ref_high > 0:

dd = (
float(
trade["entry"]
)
/ ref_high
- 1
) * 100

else:

dd = np.nan

row = trade.to_dict()

row[
"reference_high"
] = ref_high

row[
"drawdown_pct"
] = dd

rows.append(row)

return pd.DataFrame(
rows
)


# ============================================================
# DRAWDOWN BUCKET
# ============================================================

def add_drawdown_bucket(
trades,
):

trades = trades.copy()

trades[
"drawdown_bucket"
] = pd.cut(

trades[
"drawdown_pct"
],

bins=[
-np.inf,
-20,
-10,
-5,
-3,
0,
np.inf,
],

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

return trades


# ============================================================
# DRAWDOWN x LEADING WARNING
# ============================================================

def build_drawdown_warning_report(
trades,
):

rows = []

for (
bucket,
warning,
), g in trades.groupby(
[
"drawdown_bucket",
"leading_warning",
],
observed=False,
):

if len(g) == 0:

continue

s = summarize_group(g)

s[
"drawdown_bucket"
] = str(bucket)

s[
"leading_warning"
] = warning

rows.append(s)

if not rows:

return pd.DataFrame()

return pd.DataFrame(rows)


# ============================================================
# DRAWDOWN x MOMENTUM
# ============================================================

def build_drawdown_momentum_report(
trades,
momentum_column,
):

rows = []

for (
bucket,
status,
), g in trades.groupby(
[
"drawdown_bucket",
momentum_column,
],
observed=False,
):

if len(g) == 0:

continue

s = summarize_group(g)

s[
"drawdown_bucket"
] = str(bucket)

s[
"momentum_status"
] = status

rows.append(s)

if not rows:

return pd.DataFrame()

return pd.DataFrame(
rows
)


# ============================================================
# MACRO STRESS ZONE
# ============================================================

def classify_stress_zone(
score,
):

if not np.isfinite(
score
):

return "UNAVAILABLE"

if score < 25:

return "LOW"

if score < 50:

return "MODERATE"

if score < 75:

return "HIGH"

return "EXTREME"


# ============================================================
# ADD STRESS ZONES
# ============================================================

def add_stress_zones(
trades,
):

trades = trades.copy()

trades[
"macro_stress_zone"
] = trades[
"macro_stress"
].apply(
classify_stress_zone
)

trades[
"macro_momentum_zone"
] = trades[
"macro_momentum"
].apply(
classify_stress_zone
)

return trades


# ============================================================
# PRINT BASELINE CHECK
# ============================================================

def print_baseline_check(
trades,
):

s = summarize_group(
trades
)

print()
print("=" * 72)
print("FROZEN BASELINE CHECK")
print("=" * 72)

for key in [

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

]:

print(
f"{key:18s}: "
f"{s[key]}"
)

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


# ============================================================
# PRINT MOMENTUM SUMMARY
# ============================================================

def print_momentum_summary(
trades,
):

dimensions = [

(
"growth_momentum",
"Growth",
),

(
"inflation_momentum",
"Inflation",
),

(
"labor_momentum",
"Labor",
),

(
"rates_momentum",
"Rates",
),

(
"credit_momentum",
"Credit",
),

(
"liquidity_momentum",
"Liquidity",
),

]

print()
print("=" * 72)
print("MACRO MOMENTUM SUMMARY")
print("=" * 72)

for (
column,
label,
) in dimensions:

if column not in trades.columns:

continue

report = momentum_report(
trades,
column,
)

print()
print(
f"--- {label} ---"
)

print(
report[
[
"momentum_status",
"signals",
"resolved",
"wins",
"losses",
"win_rate",
"avg_R",
"total_R",
"profit_factor",
]
].to_string(
index=False
)
)


# ============================================================
# PRINT LEADING WARNING
# ============================================================

def print_leading_warning(
trades,
):

report = leading_warning_report(
trades
)

print()
print("=" * 72)
print("LEADING WARNING BACKTEST")
print("=" * 72)

if report.empty:

print(
"No leading warning data."
)

return

print(
report[
[
"leading_warning",
"signals",
"resolved",
"wins",
"losses",
"win_rate",
"avg_R",
"total_R",
"profit_factor",
]
].to_string(
index=False
)
)


# ============================================================
# PRINT DIMENSIONS
# ============================================================

def print_dimension_report(
trades,
):

print()
print("=" * 72)
print("MACRO V2.1 DIMENSIONS")
print("=" * 72)

columns = [

"signal_date",
"macro_regime",

"macro_stress",
"macro_momentum",

"growth_stress",
"growth_momentum",

"inflation_stress",
"inflation_momentum",

"labor_stress",
"labor_momentum",

"rates_stress",
"rates_momentum",

"credit_stress",
"credit_momentum",

"liquidity_stress",
"liquidity_momentum",

"leading_warning",
"leading_warning_count",

]

available = [
x
for x in columns
if x in trades.columns
]

print(
trades[
available
]
.sort_values(
"signal_date"
)
.to_string(
index=False
)
)


# ============================================================
# MAIN
# ============================================================

def main():

# ========================================================
# MARKET
# ========================================================

market = load_market()

print(
f"Market rows: "
f"{len(market)} | "
f"{market.index.min().date()} "
f"-> "
f"{market.index.max().date()}"
)

# ========================================================
# FROZEN BASELINE
# ========================================================

baseline = (
build_baseline_trades(
market
)
)

print_baseline_check(
baseline
)

# ========================================================
# LOAD FRED
# ========================================================

fred = load_fred()

# ========================================================
# MACRO V2.1
# ========================================================

trades = attach_macro(
baseline,
fred,
)

# ========================================================
# DRAWDOWN
# ========================================================

trades = add_drawdown(
trades,
market,
)

trades = add_drawdown_bucket(
trades
)

trades = add_stress_zones(
trades
)

# ========================================================
# REGIME REPORT
# ========================================================

report = regime_report(
trades
)

print()
print("=" * 72)
print("MACRO REGIME BACKTEST V2.1")
print("=" * 72)

if report.empty:

print(
"No regime classifications available."
)

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
].to_string(
index=False
)
)

# ========================================================
# MOMENTUM
# ========================================================

print_momentum_summary(
trades
)

# ========================================================
# LEADING WARNING
# ========================================================

print_leading_warning(
trades
)

# ========================================================
# DIMENSIONS
# ========================================================

print_dimension_report(
trades
)

# ========================================================
# DRAWDOWN x LEADING WARNING
# ========================================================

warning_dd_report = (
build_drawdown_warning_report(
trades
)
)

print()
print("=" * 72)
print("DRAWDOWN x LEADING WARNING")
print("=" * 72)

if warning_dd_report.empty:

print(
"No data available."
)

else:

print(
warning_dd_report[
[
"drawdown_bucket",
"leading_warning",
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
].to_string(
index=False
)
)

# ========================================================
# DRAWDOWN x CREDIT MOMENTUM
# ========================================================

credit_dd_report = (
build_drawdown_momentum_report(
trades,
"credit_momentum",
)
)

print()
print("=" * 72)
print("DRAWDOWN x CREDIT MOMENTUM")
print("=" * 72)

if credit_dd_report.empty:

print(
"No data available."
)

else:

print(
credit_dd_report[
[
"drawdown_bucket",
"momentum_status",
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
].to_string(
index=False
)
)

# ========================================================
# DRAWDOWN x LABOR MOMENTUM
# ========================================================

labor_dd_report = (
build_drawdown_momentum_report(
trades,
"labor_momentum",
)
)

print()
print("=" * 72)
print("DRAWDOWN x LABOR MOMENTUM")
print("=" * 72)

if labor_dd_report.empty:

print(
"No data available."
)

else:

print(
labor_dd_report[
[
"drawdown_bucket",
"momentum_status",
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
].to_string(
index=False
)
)

# ========================================================
# DRAWDOWN x LIQUIDITY MOMENTUM
# ========================================================

liquidity_dd_report = (
build_drawdown_momentum_report(
trades,
"liquidity_momentum",
)
)

print()
print("=" * 72)
print("DRAWDOWN x LIQUIDITY MOMENTUM")
print("=" * 72)

if liquidity_dd_report.empty:

print(
"No data available."
)

else:

print(
liquidity_dd_report[
[
"drawdown_bucket",
"momentum_status",
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
].to_string(
index=False
)
)

# ========================================================
# SAVE FULL TRADE DATA
# ========================================================

trades.to_csv(
"macro_backtest_v21_trades.csv",
index=False,
)

# ========================================================
# SAVE REGIME REPORT
# ========================================================

report.to_csv(
"macro_backtest_v21_regimes.csv",
index=False,
)

# ========================================================
# SAVE LEADING WARNING
# ========================================================

leading_report = (
leading_warning_report(
trades
)
)

leading_report.to_csv(
"macro_backtest_v21_leading_warning.csv",
index=False,
)

# ========================================================
# SAVE CREDIT DD
# ========================================================

credit_dd_report.to_csv(
"macro_backtest_v21_credit_momentum_dd.csv",
index=False,
)

# ========================================================
# SAVE LABOR DD
# ========================================================

labor_dd_report.to_csv(
"macro_backtest_v21_labor_momentum_dd.csv",
index=False,
)

# ========================================================
# SAVE LIQUIDITY DD
# ========================================================

liquidity_dd_report.to_csv(
"macro_backtest_v21_liquidity_momentum_dd.csv",
index=False,
)

# ========================================================
# SAVE WARNING x DD
# ========================================================

warning_dd_report.to_csv(
"macro_backtest_v21_warning_dd.csv",
index=False,
)

# ========================================================
# SAVE DIMENSIONS
# ========================================================

dimension_columns = [

"signal_date",

"macro_regime",
"macro_regime_reason",

"macro_stress",
"macro_stress_zone",

"macro_momentum",
"macro_momentum_zone",

"growth_stress",
"growth_momentum",

"inflation_stress",
"inflation_momentum",

"labor_stress",
"labor_momentum",

"rates_stress",
"rates_momentum",

"credit_stress",
"credit_momentum",

"liquidity_stress",
"liquidity_momentum",

"growth_short_change",
"growth_medium_change",

"inflation_short_change",
"inflation_medium_change",

"labor_short_change",
"labor_medium_change",

"rates_short_change",
"rates_medium_change",

"credit_short_change",
"credit_medium_change",

"liquidity_short_change",
"liquidity_medium_change",

"deteriorating_count",
"strong_deteriorating_count",
"improving_count",

"leading_warning",
"leading_warning_count",

"macro_reasons",

]

available_columns = [
column
for column in dimension_columns
if column in trades.columns
]

trades[
available_columns
].to_csv(
"macro_backtest_v21_dimensions.csv",
index=False,
)

# ========================================================
# OUTPUT FILES
# ========================================================

print()
print("=" * 72)
print("OUTPUT FILES")
print("=" * 72)

print(
"macro_backtest_v21_trades.csv"
)

print(
"macro_backtest_v21_regimes.csv"
)

print(
"macro_backtest_v21_leading_warning.csv"
)

print(
"macro_backtest_v21_credit_momentum_dd.csv"
)

print(
"macro_backtest_v21_labor_momentum_dd.csv"
)

print(
"macro_backtest_v21_liquidity_momentum_dd.csv"
)

print(
"macro_backtest_v21_warning_dd.csv"
)

print(
"macro_backtest_v21_dimensions.csv"
)

# ========================================================
# COMPLETE
# ========================================================

print()
print("=" * 72)
print("MACRO CALIBRATION V2.1 COMPLETE")
print("=" * 72)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
main()
