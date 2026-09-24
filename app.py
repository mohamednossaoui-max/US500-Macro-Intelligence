#!/usr/bin/env python3

"""
US500 MACRO INTELLIGENCE
RESEARCH TERMINAL — EDGE FINDER STYLE

Research-only visualization layer.

IMPORTANT:
- No BUY / SELL signals.
- No trading execution.
- No deterministic forecast.
- No position sizing.
- No SL / TP.
- No directional recommendation.
- No Decision Engine output as a trading decision.

The application visualizes the actual research artifacts produced
by GitHub Actions.

Repository:
mohamednossaoui-max/US500-Macro-Intelligence
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf


# ============================================================
# CONFIG
# ============================================================

APP_TITLE = "US500 Research Terminal"
APP_VERSION = "2.0"

GITHUB_OWNER = "mohamednossaoui-max"
GITHUB_REPO = "US500-Macro-Intelligence"

GITHUB_API = (
f"https://api.github.com/repos/"
f"{GITHUB_OWNER}/{GITHUB_REPO}"
)

US500_TICKER = os.getenv(
"US500_TICKER",
"^GSPC",
)

CACHE_TTL = 900
MARKET_CACHE_TTL = 300


# ============================================================
# EXACT ARTIFACT / FILE CONTRACT
# ============================================================
#
# These mappings are intentionally explicit.
# Do NOT replace them with "first CSV" heuristics.
#

DATASETS = {

"Research Context": {
"artifact": "research-context-v1",
"file": "research_context_v1.csv",
},

"Macro Context": {
"artifact": "macro-context-v1",
"file": "macro_context_v1.csv",
},

"Financial Stress": {
"artifact": "financial-stress-research-v1",
"file": "financial_stress_research_v1.csv",
},

"Sentiment": {
"artifact": "sentiment-engine-v1",
"file": "sentiment_engine_research_v1.csv",
},

"Technical": {
"artifact": "technical-intelligence-v1",
"file": "technical_intelligence_research_v1.csv",
},

"Liquidity": {
"artifact": "liquidity-intelligence-v1",
"file": "liquidity_intelligence_research_v1.csv",
},

"Market Breadth": {
"artifact": "market-breadth-full-validation-v1",
"file": "market_breadth_analysis_v1.csv",
},

"Historical Edge": {
"artifact": "historical-event-study-v2",
"files": [
"historical_event_study_summary_v2.csv",
"historical_event_study_event_overlap_v2.csv",
"historical_event_study_feature_redundancy_v2.csv",
"historical_event_study_conditional_events_v2.csv",
"historical_event_study_controlled_associations_v2.csv",
"historical_event_study_sample_adequacy_v2.csv",
"historical_event_study_baseline_v2.csv",
],
},

"Event News": {
"artifact": "event-news-intelligence-v2.1",
"file": "event_news_research_v2.csv",
},

"Cross Asset": {
"artifact": "cross-asset-intelligence-v1",
"file": "cross_asset_intelligence_v1.csv",
},

"Earnings": {
"artifact": "earnings-market-reaction-v3-results",
"file": "earnings_market_reaction_v3.csv",
},
}


# ============================================================
# PAGE
# ============================================================

st.set_page_config(
page_title=APP_TITLE,
page_icon="◈",
layout="wide",
initial_sidebar_state="expanded",
)


# ============================================================
# CSS
# ============================================================

st.markdown(
"""
<style>

:root {
--bg: #070a0f;
--panel: #0d121a;
--panel2: #101722;
--border: #1d2735;
--text: #e8edf5;
--muted: #7e8a9c;
--accent: #65d6bd;
--blue: #78a9ff;
--amber: #d8b36a;
--red: #e27d8a;
}

html, body, [class*="css"] {
font-family:
Inter,
-apple-system,
BlinkMacSystemFont,
"Segoe UI",
sans-serif;
}

.stApp {
background:
radial-gradient(
circle at 80% -10%,
rgba(50, 72, 105, 0.22),
transparent 34%
),
linear-gradient(
180deg,
#070a0f 0%,
#080c12 100%
);
color: var(--text);
}

section[data-testid="stSidebar"] {
background: #090d13;
border-right: 1px solid var(--border);
}

section[data-testid="stSidebar"] * {
color: #dce3ed !important;
}

.block-container {
max-width: 1550px;
padding-top: 1rem;
padding-bottom: 4rem;
}

.hero {
background:
linear-gradient(
135deg,
rgba(17, 24, 35, 0.98),
rgba(9, 13, 20, 0.98)
);
border: 1px solid #202b3b;
border-radius: 18px;
padding: 27px 30px;
margin-bottom: 18px;
box-shadow:
0 15px 50px rgba(0, 0, 0, 0.24);
}

.hero-title {
font-size: 31px;
font-weight: 780;
letter-spacing: -0.035em;
}

.hero-subtitle {
color: var(--muted);
margin-top: 5px;
font-size: 13px;
}

.badge {
display: inline-block;
border: 1px solid #263446;
background: #121a25;
border-radius: 999px;
padding: 5px 11px;
font-size: 10px;
font-weight: 750;
letter-spacing: 0.07em;
text-transform: uppercase;
}

.research-badge {
display: inline-block;
border: 1px solid #245046;
background: #0d1c19;
color: #6ed8c1;
border-radius: 999px;
padding: 6px 12px;
font-size: 10px;
font-weight: 750;
letter-spacing: 0.07em;
text-transform: uppercase;
}

.section {
background: rgba(13, 18, 26, 0.96);
border: 1px solid var(--border);
border-radius: 15px;
padding: 19px;
margin-bottom: 17px;
}

.section-title {
font-size: 17px;
font-weight: 730;
margin-bottom: 3px;
}

.section-subtitle {
color: var(--muted);
font-size: 11px;
margin-bottom: 15px;
}

.metric-card {
background:
linear-gradient(
145deg,
#111821,
#0d131b
);
border: 1px solid #202b39;
border-radius: 14px;
padding: 17px;
min-height: 106px;
}

.metric-label {
color: #778498;
text-transform: uppercase;
font-size: 10px;
letter-spacing: 0.09em;
}

.metric-value {
margin-top: 8px;
font-size: 25px;
font-weight: 760;
letter-spacing: -0.02em;
}

.metric-sub {
color: #697688;
margin-top: 4px;
font-size: 11px;
}

.state-card {
border: 1px solid #243042;
background: #0e151f;
border-radius: 12px;
padding: 14px;
min-height: 90px;
}

.state-label {
color: #758296;
font-size: 10px;
text-transform: uppercase;
letter-spacing: .08em;
}

.state-value {
font-size: 16px;
font-weight: 720;
margin-top: 7px;
}

.state-source {
color: #667386;
font-size: 10px;
margin-top: 4px;
}

.evidence {
background: #0b1118;
border-left: 3px solid #405168;
border-radius: 7px;
padding: 12px 14px;
margin-bottom: 9px;
}

.evidence-title {
font-weight: 700;
font-size: 12px;
}

.evidence-text {
color: #aab5c4;
font-size: 11px;
line-height: 1.55;
margin-top: 3px;
}

.warning-box {
background: #19150d;
border: 1px solid #4b3b1e;
border-radius: 10px;
padding: 13px;
color: #cdbd95;
font-size: 11px;
}

.info-box {
background: #0c141d;
border: 1px solid #233348;
border-radius: 10px;
padding: 13px;
color: #9eabbc;
font-size: 11px;
}

.footer {
color: #586577;
text-align: center;
font-size: 10px;
padding-top: 30px;
}

div[data-testid="stMetric"] {
background: #101720;
border: 1px solid #202b39;
border-radius: 13px;
padding: 10px;
}

</style>
""",
unsafe_allow_html=True,
)


# ============================================================
# HELPERS
# ============================================================

def clean(value: Any) -> str:
if value is None:
return ""
return str(value).strip()


def number(value: Any) -> Optional[float]:
try:
if value is None:
return None

x = float(value)

if not np.isfinite(x):
return None

return x

except Exception:
return None


def fmt(value: Any, digits: int = 2) -> str:
x = number(value)

if x is None:
text = clean(value)
return text if text else "N/A"

if abs(x) >= 1000:
return f"{x:,.{digits}f}"

return f"{x:.{digits}f}"


def fmt_pct(value: Any, digits: int = 2) -> str:
x = number(value)

if x is None:
return "N/A"

return f"{x:.{digits}f}%"


def date_value(value: Any) -> str:
if value is None:
return "N/A"

try:
return str(
pd.to_datetime(value).date()
)
except Exception:
return clean(value) or "N/A"


def find_column(
df: pd.DataFrame,
candidates: List[str],
) -> Optional[str]:

normalized = {
str(c).strip().lower(): c
for c in df.columns
}

for candidate in candidates:
key = candidate.strip().lower()

if key in normalized:
return normalized[key]

return None


def row_value(
df: Optional[pd.DataFrame],
candidates: List[str],
default: Any = None,
) -> Any:

if df is None or df.empty:
return default

column = find_column(
df,
candidates,
)

if column is None:
return default

return df.iloc[-1].get(
column,
default,
)


def latest_date(
df: Optional[pd.DataFrame],
) -> Optional[pd.Timestamp]:

if df is None or df.empty:
return None

candidates = [
"context_date",
"asof_date",
"study_date",
"observation_date",
"date",
"event_date",
"reported_date",
]

column = find_column(
df,
candidates,
)

if column is None:
return None

dates = pd.to_datetime(
df[column],
errors="coerce",
)

if dates.notna().any():
return dates.max()

return None


def true_value(value: Any) -> bool:
return clean(value).lower() in {
"true",
"1",
"yes",
"y",
"pass",
"passed",
}


def safe_read_csv(
raw: bytes,
) -> Optional[pd.DataFrame]:

try:
return pd.read_csv(
io.BytesIO(raw),
low_memory=False,
)
except Exception:
return None


def safe_read_json(
raw: bytes,
) -> Optional[Dict[str, Any]]:

try:
return json.loads(
raw.decode("utf-8")
)
except Exception:
return None


# ============================================================
# GITHUB
# ============================================================

def github_headers() -> Dict[str, str]:

headers = {
"Accept":
"application/vnd.github+json",

"User-Agent":
"US500-Research-Terminal",
}

token = None

try:
token = st.secrets.get(
"GITHUB_TOKEN",
None,
)
except Exception:
pass

token = token or os.getenv(
"GITHUB_TOKEN"
)

if token:
headers["Authorization"] = (
f"Bearer {token}"
)

return headers


@st.cache_data(
ttl=CACHE_TTL,
show_spinner=False,
)
def github_artifacts() -> List[Dict[str, Any]]:

result = []

headers = github_headers()

for page in range(1, 11):

url = (
f"{GITHUB_API}/actions/artifacts"
f"?per_page=100&page={page}"
)

response = requests.get(
url,
headers=headers,
timeout=30,
)

response.raise_for_status()

payload = response.json()

items = payload.get(
"artifacts",
[],
)

if not items:
break

result.extend(items)

if len(items) < 100:
break

return result


def latest_artifact(
name: str,
) -> Optional[Dict[str, Any]]:

try:
items = [
x
for x in github_artifacts()
if x.get("name") == name
and not x.get(
"expired",
False,
)
]

if not items:
return None

items.sort(
key=lambda x:
x.get(
"created_at",
"",
),
reverse=True,
)

return items[0]

except Exception:
return None


@st.cache_data(
ttl=CACHE_TTL,
show_spinner=False,
)
def download_artifact(
artifact_id: int,
) -> Dict[str, bytes]:

url = (
f"{GITHUB_API}/actions/artifacts/"
f"{artifact_id}/zip"
)

response = requests.get(
url,
headers=github_headers(),
timeout=90,
allow_redirects=True,
)

response.raise_for_status()

files = {}

with zipfile.ZipFile(
io.BytesIO(
response.content
)
) as archive:

for name in archive.namelist():

if name.endswith("/"):
continue

files[name] = archive.read(
name
)

return files


def artifact_files(
artifact_name: str,
) -> Dict[str, bytes]:

artifact = latest_artifact(
artifact_name
)

if artifact is None:
return {}

try:
return download_artifact(
int(artifact["id"])
)
except Exception:
return {}


def find_artifact_file(
files: Dict[str, bytes],
exact_name: str,
) -> Optional[bytes]:

# First exact path/basename match.
for name, content in files.items():

if name == exact_name:
return content

# Then exact basename match.
for name, content in files.items():

if Path(name).name == exact_name:
return content

return None


# ============================================================
# DATA LOADING
# ============================================================

@st.cache_data(
ttl=CACHE_TTL,
show_spinner=False,
)
def load_named_csv(
dataset_name: str,
) -> Optional[pd.DataFrame]:

config = DATASETS.get(
dataset_name
)

if not config:
return None

artifact = config.get(
"artifact"
)

filename = config.get(
"file"
)

if not artifact or not filename:
return None

files = artifact_files(
artifact
)

raw = find_artifact_file(
files,
filename,
)

if raw is None:
return None

return safe_read_csv(
raw
)


@st.cache_data(
ttl=CACHE_TTL,
show_spinner=False,
)
def load_historical_files() -> Dict[
str,
pd.DataFrame,
]:

result = {}

config = DATASETS[
"Historical Edge"
]

files = artifact_files(
config["artifact"]
)

for filename in config["files"]:

raw = find_artifact_file(
files,
filename,
)

if raw is None:
continue

df = safe_read_csv(
raw
)

if df is not None:
result[filename] = df

return result


# ============================================================
# LOCAL FALLBACK
# ============================================================

def local_file(
filename: str,
) -> Optional[pd.DataFrame]:

root = Path(
__file__
).resolve().parent

candidates = [
root / filename,
root / "artifacts" / filename,
root / "data" / filename,
]

for path in candidates:

if not path.exists():
continue

try:
return pd.read_csv(
path,
low_memory=False,
)
except Exception:
continue

return None


def load_dataset(
name: str,
) -> Optional[pd.DataFrame]:

df = load_named_csv(
name
)

if df is not None and not df.empty:
return df

config = DATASETS.get(
name,
{},
)

filename = config.get(
"file"
)

if filename:
return local_file(
filename
)

return None


# ============================================================
# LOAD MAIN DATA
# ============================================================

research_context = load_dataset(
"Research Context"
)

macro_context = load_dataset(
"Macro Context"
)

financial_stress = load_dataset(
"Financial Stress"
)

sentiment = load_dataset(
"Sentiment"
)

technical = load_dataset(
"Technical"
)

liquidity = load_dataset(
"Liquidity"
)

breadth = load_dataset(
"Market Breadth"
)

event_news = load_dataset(
"Event News"
)

cross_asset = load_dataset(
"Cross Asset"
)

earnings = load_dataset(
"Earnings"
)

historical_files = (
load_historical_files()
)


# ============================================================
# MARKET DATA
# ============================================================

@st.cache_data(
ttl=MARKET_CACHE_TTL,
show_spinner=False,
)
def load_market_data() -> pd.DataFrame:

try:

data = yf.download(
US500_TICKER,
period="2y",
interval="1d",
auto_adjust=False,
progress=False,
threads=False,
)

if data is None or data.empty:
return pd.DataFrame()

if isinstance(
data.columns,
pd.MultiIndex,
):

data.columns = [
str(
col[0]
)
for col in data.columns
]

data = data.reset_index()

data["Date"] = pd.to_datetime(
data["Date"],
errors="coerce",
)

return data

except Exception:
return pd.DataFrame()


market = load_market_data()


def market_snapshot() -> Dict[str, Any]:

if market.empty:
return {}

if "Close" not in market.columns:
return {}

close = pd.to_numeric(
market["Close"],
errors="coerce",
).dropna()

if close.empty:
return {}

current = float(
close.iloc[-1]
)

previous = (
float(close.iloc[-2])
if len(close) > 1
else current
)

change = (
current - previous
)

change_pct = (
change / previous * 100
if previous
else np.nan
)

ath = float(
close.max()
)

drawdown = (
(current / ath - 1) * 100
if ath
else np.nan
)

return {
"price": current,
"change": change,
"change_pct": change_pct,
"ath": ath,
"drawdown": drawdown,
"high_2y": float(
close.max()
),
"low_2y": float(
close.min()
),
}


SNAPSHOT = market_snapshot()


# ============================================================
# CONTEXT HELPERS
# ============================================================

def current_context() -> Dict[str, Any]:

if (
research_context is None
or research_context.empty
):
return {}

row = research_context.iloc[-1]

def get(
names: List[str],
default=None,
):
col = find_column(
research_context,
names,
)

if col is None:
return default

return row.get(
col,
default,
)

return {

"date":
get(
["context_date"]
),

"layers":
get(
["available_layer_count"]
),

"macro_available":
get(
["macro_available"]
),

"sentiment_available":
get(
["sentiment_available"]
),

"technical_available":
get(
["technical_available"]
),

"pit":
get(
["point_in_time_safe"]
),

"research_only":
get(
["research_only"]
),

# Macro
"economic_regime":
get(
[
"macro_economic_regime",
"economic_regime",
]
),

"inflation_score":
get(
[
"macro_inflation_score",
"inflation_score",
]
),

"labor_score":
get(
[
"macro_labor_score",
"labor_score",
]
),

"growth_score":
get(
[
"macro_growth_score",
"growth_score",
]
),

"fed_score":
get(
[
"macro_fed_score",
"fed_score",
]
),

"financial_stress_regime":
get(
[
"macro_financial_stress_regime",
"financial_stress_regime",
]
),

"financial_stress":
get(
[
"macro_financial_stress_composite",
"financial_stress_composite",
]
),

"vix":
get(
[
"macro_vix",
"vix",
]
),

"yield_spread":
get(
[
"macro_yield_10y_2y_spread",
"yield_10y_2y_spread",
]
),

# Sentiment
"sentiment_regime":
get(
[
"sentiment_research_regime",
"sentiment_unified_sentiment_regime",
"research_regime",
]
),

"sentiment_score":
get(
[
"sentiment_unified_sentiment_score",
"unified_sentiment_score",
]
),

"cot":
get(
[
"sentiment_cot_sentiment_score",
"cot_sentiment_score",
"cot_score",
]
),

"aaii":
get(
[
"sentiment_aaii_sentiment_score",
"aaii_sentiment_score",
"aaii_score",
]
),

"vix_sentiment":
get(
[
"sentiment_vix_sentiment_score",
"vix_sentiment_score",
"vix_score",
]
),

# Technical
"technical_regime":
get(
[
"technical_technical_regime",
"technical_regime",
]
),

"trend":
get(
[
"technical_trend_structure",
"trend_structure",
]
),

"rsi":
get(
[
"technical_RSI14",
"RSI14",
]
),

"atr_pct":
get(
[
"technical_ATR14_pct",
"ATR14_pct",
]
),

"roc20":
get(
[
"technical_ROC20_pct",
"ROC20_pct",
]
),

"technical_drawdown":
get(
[
"technical_drawdown_pct",
"drawdown_pct",
]
),
}


CTX = current_context()


# ============================================================
# UI HELPERS
# ============================================================

def hero(
title: str,
subtitle: str,
page: str,
):
st.markdown(
f"""
<div class="hero">
<div style="margin-bottom:10px;">
<span class="badge">{page}</span>
&nbsp;
<span class="research-badge">
RESEARCH ONLY
</span>
</div>

<div class="hero-title">
{title}
</div>

<div class="hero-subtitle">
{subtitle}
</div>
</div>
""",
unsafe_allow_html=True,
)


def metric_card(
label: str,
value: Any,
subtitle: str = "",
):
st.markdown(
f"""
<div class="metric-card">
<div class="metric-label">
{label}
</div>

<div class="metric-value">
{value}
</div>

<div class="metric-sub">
{subtitle}
</div>
</div>
""",
unsafe_allow_html=True,
)


def state_card(
label: str,
value: Any,
source: str = "",
):
st.markdown(
f"""
<div class="state-card">
<div class="state-label">
{label}
</div>

<div class="state-value">
{value}
</div>

<div class="state-source">
{source}
</div>
</div>
""",
unsafe_allow_html=True,
)


def section(
title: str,
subtitle: str = "",
):
st.markdown(
f"""
<div class="section">
<div class="section-title">
{title}
</div>

<div class="section-subtitle">
{subtitle}
</div>
""",
unsafe_allow_html=True,
)


def section_end():
st.markdown(
"</div>",
unsafe_allow_html=True,
)


def evidence(
title: str,
text: str,
):
st.markdown(
f"""
<div class="evidence">
<div class="evidence-title">
{title}
</div>

<div class="evidence-text">
{text}
</div>
</div>
""",
unsafe_allow_html=True,
)


def dataset_status(
name: str,
df: Optional[pd.DataFrame],
):

if df is None or df.empty:

st.markdown(
f"""
<div class="warning-box">
<strong>{name}</strong><br>
Dataset unavailable in the current deployment.
</div>
""",
unsafe_allow_html=True,
)

return

latest = latest_date(
df
)

st.markdown(
f"""
<div class="info-box">
<strong>{name}</strong>
&nbsp;·&nbsp;
{len(df):,} rows
&nbsp;·&nbsp;
latest: {date_value(latest)}
</div>
""",
unsafe_allow_html=True,
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

st.markdown(
"""
<div style="
font-size:18px;
font-weight:780;
margin-bottom:2px;
">
◈ US500
</div>

<div style="
color:#748196;
font-size:10px;
letter-spacing:.08em;
text-transform:uppercase;
margin-bottom:18px;
">
Research Intelligence Terminal
</div>
""",
unsafe_allow_html=True,
)

page = st.radio(
"RESEARCH",
[
"Overview",
"Market Regime",
"Macro",
"Financial Stress",
"Sentiment",
"Technical",
"Historical Edge",
"Event Studies",
"Cross-Asset",
"Earnings",
"Evidence",
],
)

st.divider()

st.caption(
f"US500 proxy: {US500_TICKER}"
)

st.caption(
"Research-only visualization"
)

if CTX.get("date"):
st.caption(
"Research Context: "
+ date_value(
CTX["date"]
)
)


# ============================================================
# OVERVIEW
# ============================================================

def page_overview():

hero(
"US500 Market Intelligence",
(
"Unified view of the latest available research state "
"across macro, financial stress, sentiment and technical structure."
),
"OVERVIEW",
)

cols = st.columns(4)

with cols[0]:
metric_card(
"US500",
fmt(
SNAPSHOT.get(
"price"
)
),
"Public ^GSPC proxy",
)

with cols[1]:
metric_card(
"Daily Change",
fmt_pct(
SNAPSHOT.get(
"change_pct"
)
),
"Latest market session",
)

with cols[2]:
metric_card(
"2Y Drawdown",
fmt_pct(
SNAPSHOT.get(
"drawdown"
)
),
"From observed 2Y high",
)

with cols[3]:
metric_card(
"Research Date",
date_value(
CTX.get("date")
),
"Latest Research Context",
)

st.markdown("")

cols = st.columns(5)

with cols[0]:
state_card(
"Economic Regime",
clean(
CTX.get(
"economic_regime"
)
) or "N/A",
"Macro Context",
)

with cols[1]:
state_card(
"Financial Stress",
clean(
CTX.get(
"financial_stress_regime"
)
) or "N/A",
"Financial Stress Research",
)

with cols[2]:
state_card(
"Sentiment",
clean(
CTX.get(
"sentiment_regime"
)
) or "N/A",
"Sentiment Engine",
)

with cols[3]:
state_card(
"Technical",
clean(
CTX.get(
"technical_regime"
)
) or "N/A",
"Technical Intelligence",
)

with cols[4]:
state_card(
"Layer Coverage",
(
f"{fmt(CTX.get('layers'), 0)} / 3"
if number(
CTX.get("layers")
) is not None
else "N/A"
),
"Research Context",
)

st.markdown("")

section(
"Current Research State",
(
"Descriptive synthesis of the latest synchronized "
"research context. This is not a trading decision."
),
)

cols = st.columns(4)

with cols[0]:
metric_card(
"Financial Stress",
fmt(
CTX.get(
"financial_stress"
)
),
"Composite research measure",
)

with cols[1]:
metric_card(
"Sentiment Score",
fmt(
CTX.get(
"sentiment_score"
)
),
"0–100 historical sentiment scale",
)

with cols[2]:
metric_card(
"VIX",
fmt(
CTX.get(
"vix"
)
),
"Latest context observation",
)

with cols[3]:
metric_card(
"10Y–2Y Spread",
fmt(
CTX.get(
"yield_spread"
)
),
"Yield-curve observation",
)

section_end()

section(
"Market Structure",
"Observed technical conditions from the Technical Intelligence layer.",
)

cols = st.columns(5)

with cols[0]:
metric_card(
"Trend",
clean(
CTX.get(
"trend"
)
) or "N/A",
"Technical structure",
)

with cols[1]:
metric_card(
"RSI 14",
fmt(
CTX.get(
"rsi"
)
),
"Technical oscillator",
)

with cols[2]:
metric_card(
"ATR 14 %",
fmt_pct(
CTX.get(
"atr_pct"
)
),
"Observed volatility",
)

with cols[3]:
metric_card(
"ROC 20",
fmt_pct(
CTX.get(
"roc20"
)
),
"20-session rate of change",
)

with cols[4]:
metric_card(
"Drawdown",
fmt_pct(
CTX.get(
"technical_drawdown"
)
),
"Technical layer drawdown",
)

section_end()

section(
"Research Integrity",
"Controls carried through the current Research Context.",
)

cols = st.columns(4)

with cols[0]:
metric_card(
"PIT",
"SAFE"
if true_value(
CTX.get("pit")
)
else "N/A",
"Point-in-time control",
)

with cols[1]:
metric_card(
"Research Only",
"TRUE"
if true_value(
CTX.get(
"research_only"
)
)
else "N/A",
"Architecture boundary",
)

with cols[2]:
metric_card(
"Trading Signal",
"NONE",
"Not generated by the research stack",
)

with cols[3]:
metric_card(
"Forecast",
"NONE",
"Not generated by the research stack",
)

section_end()


# ============================================================
# MARKET REGIME
# ============================================================

def page_market_regime():

hero(
"Market Regime",
(
"Cross-layer description of the current US500 environment "
"using synchronized research outputs."
),
"MARKET REGIME",
)

cols = st.columns(4)

with cols[0]:
state_card(
"Macro",
clean(
CTX.get(
"economic_regime"
)
) or "N/A",
"Economic Intelligence",
)

with cols[1]:
state_card(
"Stress",
clean(
CTX.get(
"financial_stress_regime"
)
) or "N/A",
"Financial Stress",
)

with cols[2]:
state_card(
"Sentiment",
clean(
CTX.get(
"sentiment_regime"
)
) or "N/A",
"Sentiment Engine",
)

with cols[3]:
state_card(
"Technical",
clean(
CTX.get(
"technical_regime"
)
) or "N/A",
"Technical Intelligence",
)

st.markdown("")

section(
"Regime Matrix",
"Each layer is shown independently; no directional score is constructed.",
)

matrix = pd.DataFrame(
{
"Layer": [
"Economic",
"Financial Stress",
"Sentiment",
"Technical",
],
"Current State": [
CTX.get(
"economic_regime"
),
CTX.get(
"financial_stress_regime"
),
CTX.get(
"sentiment_regime"
),
CTX.get(
"technical_regime"
),
],
"Research Date": [
CTX.get("date")
] * 4,
}
)

st.dataframe(
matrix,
use_container_width=True,
hide_index=True,
)

section_end()

if research_context is not None:

section(
"Regime History",
"Historical Research Context states.",
)

cols_available = [
c
for c in [
"context_date",
"macro_economic_regime",
"macro_financial_stress_regime",
"sentiment_research_regime",
"technical_technical_regime",
]
if c in research_context.columns
]

if len(cols_available) > 1:

history = (
research_context[
cols_available
]
.copy()
)

date_col = (
"context_date"
if "context_date"
in history.columns
else None
)

if date_col:
history[date_col] = pd.to_datetime(
history[date_col],
errors="coerce",
)

history = (
history
.dropna(
subset=[date_col]
)
.tail(500)
.set_index(
date_col
)
)

st.dataframe(
history.tail(100),
use_container_width=True,
)

section_end()


# ============================================================
# MACRO
# ============================================================

def page_macro():

hero(
"Macro Intelligence",
(
"Economic and Federal Reserve context preserved "
"through the Macro Context research layer."
),
"MACRO",
