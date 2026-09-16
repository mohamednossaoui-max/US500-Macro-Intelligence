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
…
