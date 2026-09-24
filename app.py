#!/usr/bin/env python3

"""
US500 MACRO INTELLIGENCE
RESEARCH TERMINAL V5.0

Research-only visualization layer.

This application visualizes research artifacts produced by
the US500 Macro Intelligence repository.

It does NOT:
- generate trading signals
- generate forecasts
- execute trades
- recommend positions
- calculate position sizing
- calculate SL/TP
- make directional trading decisions
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf


# ============================================================
# CONFIGURATION
# ============================================================

APP_TITLE = "US500 Research Terminal"
APP_VERSION = "5.0"

GITHUB_OWNER = "mohamednossaoui-max"
GITHUB_REPO = "US500-Macro-Intelligence"

GITHUB_API = (
f"https://api.github.com/repos/"
f"{GITHUB_OWNER}/{GITHUB_REPO}"
)

DEFAULT_TICKER = "^GSPC"

ARTIFACT_CACHE_TTL = 300
DATA_CACHE_TTL = 600
MARKET_CACHE_TTL = 300


# ============================================================
# ARTIFACT CONTRACT
# ============================================================

ARTIFACTS = {

"Research Context": {
"artifact": "research-context-v1",
"files": {
"main": "research_context_v1.csv",
"summary": "research_context_summary_v1.csv",
"extremes": "research_context_extremes_v1.csv",
},
},

"Macro": {
"artifact": "macro-context-v1",
"files": {
"main": "macro_context_v1.csv",
},
},

"Sentiment Engine": {
"artifact": "sentiment-engine-v1",
"files": {
"main": "sentiment_engine_research_v1.csv",
"summary": "sentiment_engine_research_summary_v1.csv",
"extremes": "sentiment_engine_extremes_v1.csv",
},
},

"AAII": {
"artifact": "aaii-sentiment-v1",
"files": {
"main": "aaii_sentiment_research_v1.csv",
"summary": "aaii_sentiment_research_summary_v1.csv",
"extremes": "aaii_sentiment_extremes_v1.csv",
},
},

"COT": {
"artifact": "cot-positioning-v1",
"files": {
"main": "cot_positioning_research_v1.csv",
"summary": "cot_positioning_research_summary_v1.csv",
"extremes": "cot_positioning_extremes_v1.csv",
},
},

"VIX Sentiment": {
"artifact": "vix-sentiment-v1",
"files": {
"main": "vix_sentiment_research_v1.csv",
"summary": "vix_sentiment_research_summary_v1.csv",
"extremes": "vix_sentiment_extremes_v1.csv",
},
},

"Financial Stress": {
"artifact": "financial-stress-research-v1",
"files": {
"main": "financial_stress_research_v1.csv",
"summary": "financial_stress_research_summary_v1.csv",
},
},

"Liquidity": {
"artifact": "liquidity-intelligence-v1",
"files": {
"main": "liquidity_intelligence_research_v1.csv",
"summary": "liquidity_intelligence_summary_v1.csv",
},
},

"Technical": {
"artifact": "technical-intelligence-v1",
"files": {
"main": "technical_intelligence_research_v1.csv",
"summary": "technical_intelligence_research_summary_v1.csv",
"extremes": "technical_intelligence_extremes_v1.csv",
},
},

"Market Breadth": {
"artifact": "market-breadth-full-validation-v1",
"files": {
"main": "market_breadth_analysis_v1.csv",
"historical": "market_breadth_historical_v1.csv",
},
},

"Event News": {
"artifact": "event-news-intelligence-v2.1",
"files": {
"main": "event_news_research_v2.csv",
"summary": "event_news_research_summary_v2.json",
"validation": "event_news_validation_v2.json",
},
},

"Cross-Asset": {
"artifact": "cross-asset-intelligence-v1",
"files": {
"main": "cross_asset_research_v1.csv",
"summary": "cross_asset_summary_v1.json",
},
},

"Earnings": {
"artifact": "earnings-market-reaction-v3-results",
"files": {
"main": "earnings_market_reaction_v3.csv",
"summary": "earnings_market_reaction_summary_v3.csv",
"eps": "earnings_reaction_by_eps_class_v3.csv",
"sector": "earnings_reaction_by_sector_v3.csv",
},
},

"Decision Engine": {
"artifact": "decision-engine-v1",
"files": {
"main": "decision_engine_research_v1.csv",
"summary": "decision_engine_research_v1_summary.csv",
"validation": "decision_engine_validation_v1.csv",
"validation_summary":
"decision_engine_validation_v1_summary.csv",
"events":
"decision_engine_validation_v1_events.csv",
},
},

"Final Validation": {
"artifact": "final-end-to-end-validation-v1",
"files": {},
},
}


# ============================================================
# HISTORICAL EVENT STUDY
# ============================================================

HISTORICAL_ARTIFACT = "historical-event-study-v2"

HISTORICAL_FILES = {
"Summary":
"historical_event_study_summary_v2.csv",

"Event Overlap":
"historical_event_study_event_overlap_v2.csv",

"Feature Redundancy":
"historical_event_study_feature_redundancy_v2.csv",

"Conditional Events":
"historical_event_study_conditional_events_v2.csv",

"Controlled Associations":
"historical_event_study_controlled_associations_v2.csv",

"Sample Adequacy":
"historical_event_study_sample_adequacy_v2.csv",

"Baseline":
"historical_event_study_baseline_v2.csv",
}


# ============================================================
# FED
# ============================================================

FED_ARTIFACT = "fed-intelligence-v1"
FED_FILE = "fed_intelligence_output_v1.json"


# ============================================================
# STREAMLIT
# ============================================================

st.set_page_config(
page_title=APP_TITLE,
page_icon="📊",
layout="wide",
initial_sidebar_state="expanded",
)


# ============================================================
# CSS
# ============================================================

st.markdown(
"""
<style>

.stApp {
background: #0b0f14;
color: #e6edf3;
}

[data-testid="stSidebar"] {
background: #0d131a;
border-right: 1px solid #27313a;
}

.block-container {
max-width: 1550px;
padding-top: 1rem;
padding-bottom: 3rem;
}

.terminal-title {
font-size: 2.15rem;
font-weight: 800;
letter-spacing: .02em;
}

.terminal-subtitle {
color: #8d9aa6;
margin-bottom: 1.2rem;
}

.research-note {
background: #101820;
border: 1px solid #26323d;
border-left: 4px solid #758697;
border-radius: 8px;
padding: 13px 16px;
margin: 10px 0 20px 0;
color: #b8c3cd;
}

.metric-card {
background: #111820;
border: 1px solid #27333d;
border-radius: 12px;
padding: 15px;
min-height: 108px;
}

.metric-label {
color: #7f8c98;
font-size: .73rem;
text-transform: uppercase;
letter-spacing: .09em;
}

.metric-value {
font-size: 1.45rem;
font-weight: 750;
margin-top: 7px;
}

.metric-note {
color: #7d8a96;
font-size: .76rem;
margin-top: 5px;
}

.section-header {
font-size: 1.18rem;
font-weight: 750;
margin-top: 1.4rem;
margin-bottom: .65rem;
}

.good {
color: #a8c8b1;
}

.review {
color: #d6bc82;
}

.bad {
color: #d89494;
}

.small-muted {
color: #71808d;
font-size: .75rem;
}

</style>
""",
unsafe_allow_html=True,
)


# ============================================================
# TOKEN
# ============================================================

def get_github_token() -> Optional[str]:

token = None

try:
token = st.secrets.get(
"GITHUB_TOKEN",
None,
)
except Exception:
pass

if not token:
token = os.getenv(
"GITHUB_TOKEN",
"",
)

if token is None:
return None

token = str(token).strip()

invalid = {
"",
"GITHUB_TOKEN",
"YOUR_GITHUB_TOKEN",
"YOUR_GITHUB_PAT",
"YOUR_TOKEN",
"PASTE_TOKEN_HERE",
"your_github_token",
"your_github_pat",
}

if token in invalid:
return None

return token


# ============================================================
# TICKER
# ============================================================

def get_ticker() -> str:

try:

value = st.secrets.get(
"US500_TICKER",
None,
)

if value:
return str(value)

except Exception:
pass

return os.getenv(
"US500_TICKER",
DEFAULT_TICKER,
)


# ============================================================
# GITHUB HEADERS
# ============================================================

def github_headers() -> Dict[str, str]:

headers = {
"Accept":
"application/vnd.github+json",

"X-GitHub-Api-Version":
"2022-11-28",

"User-Agent":
"US500-Research-Terminal/5.0",
}

token = get_github_token()

if token:
headers["Authorization"] = (
f"Bearer {token}"
)

return headers


# ============================================================
# GITHUB REQUEST
# ============================================================

def github_get(
url: str,
params: Optional[Dict[str, Any]] = None,
timeout: int = 60,
) -> requests.Response:

response = requests.get(
url,
headers=github_headers(),
params=params,
timeout=timeout,
)

if response.status_code == 401:

if get_github_token():

raise RuntimeError(
"GitHub authentication failed "
"(HTTP 401). The GITHUB_TOKEN in "
"Streamlit Secrets is invalid, expired "
"or revoked."
)

raise RuntimeError(
"GitHub returned HTTP 401 because "
"GITHUB_TOKEN is not configured."
)

if response.status_code == 403:

raise RuntimeError(
"GitHub returned HTTP 403. The token may "
"lack permission to read Actions artifacts, "
"or the GitHub API rate limit may have "
"been reached."
)

if response.status_code == 404:

raise RuntimeError(
"GitHub returned HTTP 404. The repository "
"or requested artifact is not accessible "
"with the current credentials."
)

response.raise_for_status()

return response


# ============================================================
# ARTIFACT DISCOVERY
# ============================================================

@st.cache_data(
ttl=ARTIFACT_CACHE_TTL,
show_spinner=False,
)
def get_all_artifacts() -> Dict[str, Dict[str, Any]]:

result = {}

for page in range(1, 11):

response = github_get(
f"{GITHUB_API}/actions/artifacts",
params={
"per_page": 100,
"page": page,
},
timeout=45,
)

payload = response.json()

items = payload.get(
"artifacts",
[],
)

for artifact in items:

if artifact.get(
"expired",
False,
):
continue

name = artifact.get(
"name"
)

if not name:
continue

previous = result.get(
name
)

if previous is None:

result[name] = artifact

continue

old_date = str(
previous.get(
"created_at",
"",
)
)

new_date = str(
artifact.get(
"created_at",
"",
)
)

if new_date > old_date:

result[name] = artifact

if len(items) < 100:

break

return result


def latest_artifact(
artifact_name: str,
) -> Optional[Dict[str, Any]]:

return get_all_artifacts().get(
artifact_name
)


# ============================================================
# ARTIFACT DOWNLOAD
# ============================================================

@st.cache_data(
ttl=DATA_CACHE_TTL,
show_spinner=False,
)
def download_artifact(
artifact_name: str,
) -> bytes:

artifact = latest_artifact(
artifact_name
)

if artifact is None:

raise FileNotFoundError(
f"Artifact not found: {artifact_name}"
)

artifact_id = artifact.get(
"id"
)

if not artifact_id:

raise RuntimeError(
f"Artifact {artifact_name} "
"does not contain an ID."
)

url = (
f"{GITHUB_API}/actions/artifacts/"
f"{artifact_id}/zip"
)

response = github_get(
url,
timeout=120,
)

if not response.content:

raise RuntimeError(
f"Artifact {artifact_name} "
"returned an empty archive."
)

return response.content


# ============================================================
# ZIP FILE
# ============================================================

@st.cache_data(
ttl=DATA_CACHE_TTL,
show_spinner=False,
)
def artifact_file(
artifact_name: str,
filename: str,
) -> Optional[bytes]:

raw = download_artifact(
artifact_name
)

try:

with zipfile.ZipFile(
io.BytesIO(raw)
) as archive:

names = archive.namelist()

for name in names:

normalized = name.replace(
"\\",
"/",
)

if normalized == filename:

return archive.read(
name
)

for name in names:

normalized = name.replace(
"\\",
"/",
)

if normalized.endswith(
"/" + filename
):

return archive.read(
name
)

except zipfile.BadZipFile:

raise RuntimeError(
f"Artifact {artifact_name} "
"did not contain a valid ZIP archive."
)

return None


# ============================================================
# CSV
# ============================================================

@st.cache_data(
ttl=DATA_CACHE_TTL,
show_spinner=False,
)
def read_csv_artifact(
artifact_name: str,
filename: str,
) -> pd.DataFrame:

content = artifact_file(
artifact_name,
filename,
)

if content is None:

return pd.DataFrame()

return pd.read_csv(
io.BytesIO(content)
)


# ============================================================
# JSON
# ============================================================

@st.cache_data(
ttl=DATA_CACHE_TTL,
show_spinner=False,
)
def read_json_artifact(
artifact_name: str,
filename: str,
) -> Any:

content = artifact_file(
artifact_name,
filename,
)

if content is None:

return {}

return json.loads(
content.decode(
"utf-8"
)
)


# ============================================================
# DATASET LOADER
# ============================================================

def load_named_dataset(
name: str,
file_key: str = "main",
) -> pd.DataFrame:

specification = ARTIFACTS.get(
name
)

if not specification:

return pd.DataFrame()

filename = specification[
"files"
].get(
file_key
)

if not filename:

return pd.DataFrame()

try:

return read_csv_artifact(
specification["artifact"],
filename,
)

except Exception as error:

st.warning(
f"{name}: unable to load "
f"{filename}: {error}"
)

return pd.DataFrame()


# ============================================================
# HELPERS
# ============================================================

def find_column(
df: pd.DataFrame,
candidates: List[str],
) -> Optional[str]:

if df.empty:
return None

mapping = {
str(column).strip().lower():
column
for column in df.columns
}

for candidate in candidates:

found = mapping.get(
str(candidate).strip().lower()
)

if found:

return found

return None


def latest_row(
df: pd.DataFrame,
) -> pd.Series:

if df.empty:

return pd.Series(
dtype=object
)

date_column = find_column(
df,
[
"asof_date",
"context_date",
"date",
"observation_date",
"reported_date",
"event_date",
"session_date",
"timestamp",
],
)

if date_column:

dates = pd.to_datetime(
df[date_column],
errors="coerce",
)

valid = dates.notna()

if valid.any():

index = dates.loc[
valid
].idxmax()

return df.loc[
index
]

return df.iloc[-1]


def row_date(
row: pd.Series,
) -> str:

if row is None or row.empty:

return "N/A"

for column in [
"asof_date",
"context_date",
"date",
"observation_date",
"reported_date",
"event_date",
"session_date",
"timestamp",
]:

if column not in row.index:

continue

parsed = pd.to_datetime(
row[column],
errors="coerce",
)

if pd.notna(parsed):

return parsed.strftime(
"%Y-%m-%d"
)

return "N/A"


def value_from_row(
row: pd.Series,
candidates: List[str],
) -> Any:

if row is None or row.empty:

return None

mapping = {
str(column).lower():
column
for column in row.index
}

for candidate in candidates:

actual = mapping.get(
candidate.lower()
)

if actual is None:

continue

value = row[actual]

try:

if pd.isna(value):

continue

except Exception:

pass

return value

return None


def text_value(
row: pd.Series,
candidates: List[str],
) -> str:

value = value_from_row(
row,
candidates,
)

if value is None:

return "N/A"

text = str(
value
).strip()

if text.lower() in {
"",
"nan",
"none",
"nat",
}:

return "N/A"

return text


def number_value(
row: pd.Series,
candidates: List[str],
) -> Optional[float]:

value = value_from_row(
row,
candidates,
)

try:

number = float(value)

if np.isfinite(number):

return number

except Exception:

pass

return None


def fmt(
value: Any,
decimals: int = 2,
) -> str:

try:

number = float(value)

if not np.isfinite(number):

return "N/A"

return f"{number:,.{decimals}f}"

except Exception:

return "N/A"


def safe_record(
row: pd.Series,
) -> Dict[str, Any]:

result = {}

if row is None:

return result

for key, value in row.items():

try:

if pd.isna(value):

continue

except Exception:

pass

result[str(key)] = str(
value
)

return result


# ============================================================
# METRIC
# ============================================================

def metric(
label: str,
value: str,
note: str = "",
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
<div class="metric-note">
{note}
</div>
</div>
""",
unsafe_allow_html=True,
)


# ============================================================
# RESEARCH NOTICE
# ============================================================

def research_notice():

st.markdown(
"""
<div class="research-note">
<strong>Research-only terminal.</strong>
The information shown here consists of current-state
observations, historical distributions, research
classifications, event studies and supporting evidence.
It does not constitute a trading signal, forecast,
execution instruction or directional recommendation.
</div>
""",
unsafe_allow_html=True,
)


# ============================================================
# GENERIC CHART
# ============================================================

def research_chart(
df: pd.DataFrame,
columns: Optional[List[str]] = None,
title: str = "",
):

if df.empty:

return

selected = []

if columns:

for column in columns:

if column not in df.columns:

continue

values = pd.to_numeric(
df[column],
errors="coerce",
)

if values.notna().any():

selected.append(
column
)

if not selected:

for column in df.columns:

values = pd.to_numeric(
df[column],
errors="coerce",
)

if values.notna().any():

selected.append(
column
)

if len(selected) >= 5:

break

if not selected:

return

date_column = find_column(
df,
[
"asof_date",
"context_date",
"date",
"observation_date",
"reported_date",
"event_date",
"session_date",
],
)

chart = df.copy()

if date_column:

dates = pd.to_datetime(
chart[date_column],
errors="coerce",
)

chart = chart.loc[
dates.notna()
].copy()

chart.index = pd.DatetimeIndex(
dates.loc[
chart.index
]
)

for column in selected:

chart[column] = pd.to_numeric(
chart[column],
errors="coerce",
)

chart = chart[
selected
].dropna(
how="all"
).tail(500)

if chart.empty:

return

if title:

st.markdown(
f"""
<div class="section-header">
{title}
</div>
""",
unsafe_allow_html=True,
)

st.line_chart(
chart,
use_container_width=True,
)


# ============================================================
# MARKET DATA
# ============================================================

@st.cache_data(
ttl=MARKET_CACHE_TTL,
show_spinner=False,
)
def market_data() -> pd.DataFrame:

try:

return yf.download(
get_ticker(),
period="1y",
interval="1d",
auto_adjust=False,
progress=False,
)

except Exception:

return pd.DataFrame()


def market_snapshot() -> Tuple[
Optional[float],
Optional[float],
Optional[str],
]:

df = market_data()

if df.empty:

return None, None, None

try:

close = df["Close"]

if isinstance(
close,
pd.DataFrame,
):

close = close.iloc[:, 0]

close = pd.to_numeric(
close,
errors="coerce",
).dropna()

if close.empty:

return None, None, None

current = float(
close.iloc[-1]
)

change = None

if len(close) >= 2:

previous = float(
close.iloc[-2]
)

if previous:

change = (
current / previous - 1
) * 100

date = None

try:

date = pd.Timestamp(
close.index[-1]
).strftime(
"%Y-%m-%d"
)

except Exception:

pass

return current, change, date

except Exception:

return None, None, None


# ============================================================
# OVERVIEW
# ============================================================

def page_overview():

st.markdown(
"""
<div class="terminal-title">
US500 Research Terminal
</div>
<div class="terminal-subtitle">
Current market context, cross-layer research and
historical evidence.
</div>
""",
unsafe_allow_html=True,
)

research_notice()

price, change, market_date = (
market_snapshot()
)

context = load_named_dataset(
"Research Context"
)

stress = load_named_dataset(
"Financial Stress"
)

sentiment = load_named_dataset(
"Sentiment Engine"
)

technical = load_named_dataset(
"Technical"
)

macro = load_named_dataset(
"Macro"
)

context_row = latest_row(
context
)

stress_row = latest_row(
stress
)

sentiment_row = latest_row(
sentiment
)

technical_row = latest_row(
technical
)

macro_row = latest_row(
macro
)

cols = st.columns(6)

with cols[0]:

change_text = (
f"{change:+.2f}%"
if change is not None
else "N/A"
)

metric(
"US500 Proxy",
fmt(price),
f"{get_ticker()} · {change_text}",
)

with cols[1]:

metric(
"Market Date",
market_date or "N/A",
"market reference",
)

with cols[2]:

metric(
"Research Date",
row_date(context_row),
"latest unified context",
)

with cols[3]:

metric(
"Macro",
text_value(
macro_row,
[
"economic_regime",
"macro_economic_regime",
"macro_regime",
],
),
row_date(macro_row),
)

with cols[4]:

metric(
"Stress",
text_value(
stress_row,
[
"research_regime",
"RESEARCH_REGIME",
"stress_regime",
],
),
row_date(stress_row),
)

with cols[5]:

metric(
"Technical",
text_value(
technical_row,
[
"technical_regime",
"trend_regime",
"research_regime",
],
),
row_date(technical_row),
)

st.markdown(
"### Current Research State"
)

left, right = st.columns(
2
)

with left:

if not context_row.empty:

st.dataframe(
context_row.to_frame(
"value"
),
use_container_width=True,
)

else:

st.info(
"Research Context unavailable."
)

with right:

if not sentiment_row.empty:

st.dataframe(
sentiment_row.to_frame(
"value"
),
use_container_width=True,
)

else:

st.info(
"Sentiment Engine unavailable."
)

research_chart(
stress,
[
"composite_stress_score",
"VIX",
"NFCI",
"ANFCI",
],
"Financial Stress Context",
)


# ============================================================
# MARKET REGIME
# ============================================================

def page_market_regime():

st.title(
"Market Regime"
)

research_notice()

context = load_named_dataset(
"Research Context"
)

if context.empty:

st.warning(
"Research Context is unavailable."
)

return

row = latest_row(
context
)

cols = st.columns(5)

fields = [
(
"Context Date",
row_date(row),
),
(
"Macro",
text_value(
row,
[
"economic_regime",
"macro_economic_regime",
"macro_regime",
],
),
),
(
"Sentiment",
text_value(
row,
[
"sentiment_regime",
"sentiment_research_regime",
],
),
),
(
"Technical",
text_value(
row,
[
"technical_regime",
"trend_structure",
],
),
),
(
"Stress",
text_value(
row,
[
"financial_stress_regime",
"stress_regime",
],
),
),
]

for column, (
label,
value,
) in zip(
cols,
fields,
):

with column:

metric(
label,
value,
"research state",
)

st.markdown(
"### Unified Context"
)

st.dataframe(
row.to_frame(
"value"
),
use_container_width=True,
)

research_chart(
context,
title="Research Context History",
)


# ============================================================
# MACRO
# ============================================================

def page_macro():

st.title(
"Macro"
)

research_notice()

df = load_named_dataset(
"Macro"
)

if df.empty:

st.warning(
"Macro Context is unavailable."
)

return

row = latest_row(
df
)

cols = st.columns(4)

with cols[0]:

metric(
"Latest Date",
row_date(row),
)

with cols[1]:

metric(
"Economic Regime",
text_value(
row,
[
"economic_regime",
"macro_economic_regime",
"macro_regime",
],
),
)

with cols[2]:

metric(
"Stress Regime",
text_value(
row,
[
"financial_stress_regime",
"stress_regime",
],
),
)

with cols[3]:

metric(
"Research State",
text_value(
row,
[
"research_regime",
"macro_regime",
],
),
)

research_chart(
df,
title="Macro Research History",
)

with st.expander(
"Latest Macro Record",
expanded=True,
):

st.json(
safe_record(row),
expanded=False,
)


# ============================================================
# FED
# ============================================================

def page_fed():

st.title(
"Fed Intelligence"
)

research_notice()

try:

fed = read_json_artifact(
FED_ARTIFACT,
FED_FILE,
)

except Exception as error:

st.error(
f"Fed Intelligence unavailable: {error}"
)

return

if not fed:

st.warning(
"Fed Intelligence artifact is empty."
)

return

if not isinstance(
fed,
dict,
):

st.json(
fed
)

return

phase = (
fed.get("phase_2b")
or fed.get("phase_2a")
or {}
)

sep = (
fed.get("sep")
or fed.get("sep_current")
or {}
)

shift = (
fed.get("sep_shift")
or {}
)

beige = (
fed.get("beige_book")
or fed.get("beige_book_analysis")
or {}
)

cols = st.columns(5)

with cols[0]:

metric(
"FOMC",
str(
fed.get(
"latest_fomc"
)
or phase.get(
"latest_fomc"
)
or "N/A"
),
)

with cols[1]:

metric(
"Fed Chair",
str(
fed.get(
"fed_chair"
)
or phase.get(
"fed_chair"
)
or "N/A"
),
)

with cols[2]:

score = (
fed.get(
"fed_score"
)
if fed.get(
"fed_score"
) is not None
else phase.get(
"fed_score"
)
)

metric(
"Fed Score",
fmt(score),
"research metric",
)

with cols[3]:

metric(
"Classification",
str(
fed.get(
"fed_classification"
)
or phase.get(
"fed_classification"
)
or "N/A"
),
)

with cols[4]:

metric(
"SEP",
"Available"
if sep
else "N/A",
)

st.markdown(
"### FOMC Statement / Minutes / Press Conference"
)

for key in [
"fomc_statement",
"fomc_minutes",
"press_conference",
"fed_chair_statement",
]:

value = (
fed.get(key)
if key in fed
else phase.get(key)
)

if value is None:

continue

with st.expander(
key.replace(
"_",
" ",
).title()
):

if isinstance(
value,
(dict, list),
):

st.json(
value,
expanded=False,
)

else:

st.write(
value
)

st.markdown(
"### Summary of Economic Projections"
)

left, right = st.columns(
2
)

with left:

st.write(
"Current SEP"
)

st.json(
sep,
expanded=False,
)

with right:

st.write(
"SEP Shift"
)

st.json(
shift,
expanded=False,
)

if beige:

st.markdown(
"### Beige Book"
)

st.json(
beige,
expanded=False,
)

with st.expander(
"Complete Fed Intelligence Record"
):

st.json(
fed,
expanded=False,
)


# ============================================================
# FINANCIAL STRESS
# ============================================================

def page_financial_stress():

st.title(
"Financial Stress"
)

research_notice()

df = load_named_dataset(
"Financial Stress"
)

if df.empty:

st.warning(
"Financial Stress data unavailable."
)

return

row = latest_row(
df
)

cols = st.columns(5)

with cols[0]:

metric(
"Stress Score",
text_value(
row,
[
"composite_stress_score",
"FINANCIAL_STRESS_COMPOSITE",
],
),
)

with cols[1]:

metric(
"VIX",
fmt(
number_value(
row,
["VIX"],
)
),
)

with cols[2]:

metric(
"10Y - 2Y",
fmt(
number_value(
row,
[
"YIELD_10Y_2Y_SPREAD",
"YIELD_CURVE",
],
)
),
)

with cols[3]:

metric(
"NFCI",
fmt(
number_value(
row,
["NFCI
…
