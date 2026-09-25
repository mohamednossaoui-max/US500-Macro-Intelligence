#!/usr/bin/env python3
"""
US500 MACRO INTELLIGENCE
RESEARCH TERMINAL — EDGE FINDER STYLE

Research-only visualization layer.

This application visualizes research artifacts produced by GitHub Actions.
It does not generate trading signals, forecasts, execution instructions,
position sizing, SL/TP, or directional recommendations.
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

APP_TITLE = "US500 Research Terminal"
APP_VERSION = "4.0"
GITHUB_OWNER = "mohamednossaoui-max"
GITHUB_REPO = "US500-Macro-Intelligence"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
US500_TICKER = os.getenv("US500_TICKER", "^GSPC")
CACHE_TTL = 900
MARKET_CACHE_TTL = 300

# Exact artifact contracts. The loader never chooses an arbitrary CSV.
DATASETS: Dict[str, Dict[str, Any]] = {
    "Research Context": {
        "artifact": "research-context-v1",
        "files": ["research_context_v1.csv"],
    },
    "Macro Context": {
        "artifact": "macro-context-v1",
        "files": ["macro_context_v1.csv", "macro_context_v1.json"],
    },
    "Financial Stress": {
        "artifact": "financial-stress-research-v1",
        "files": ["financial_stress_research_v1.csv"],
    },
    "Sentiment": {
        "artifact": "sentiment-engine-v1",
        "files": ["sentiment_engine_research_v1.csv"],
    },
    "Technical": {
        "artifact": "technical-intelligence-v1",
        "files": ["technical_intelligence_research_v1.csv"],
    },
    "Liquidity": {
        "artifact": "liquidity-intelligence-v1",
        "files": ["liquidity_intelligence_research_v1.csv"],
    },
    "Market Breadth": {
        "artifact": "market-breadth-full-validation-v1",
        "files": ["market_breadth_analysis_v1.csv"],
    },
    "Event News": {
        "artifact": "event-news-intelligence-v2.1",
        "files": ["event_news_research_v2.csv"],
    },
    "Cross Asset": {
        "artifact": "cross-asset-intelligence-v1",
        "files": ["cross_asset_intelligence_v1.csv"],
    },
    "Earnings": {
        "artifact": "earnings-market-reaction-v3-results",
        "files": ["earnings_market_reaction_v3.csv"],
    },
    "Fed Intelligence": {
        "artifact": "fed-intelligence-v1",
        "files": ["fed_intelligence_output_v1.json"],
    },
    "Market Breadth": {
        "artifact": "market-breadth-full-validation-v1",
        "files": ["market_breadth_analysis_v1.csv"],
    },
    "Earnings Detail": {
        "artifact": "earnings-market-reaction-v3-results",
        "files": [
            "earnings_market_reaction_summary_v3.csv",
            "earnings_reaction_by_eps_class_v3.csv",
            "earnings_reaction_by_sector_v3.csv",
        ],
    },
    "Decision Engine": {
        "artifact": "decision-engine-v1",
        "files": ["decision_engine_validation_v1.csv", "decision_engine_validation_v1_summary.csv", "decision_engine_validation_v1_events.csv", "decision_engine_research_v1.csv", "decision_engine_research_v1_summary.csv"],
    },
    "Final Validation": {
        "artifact": "final-end-to-end-validation-v1",
        "files": [
            "final_end_to_end_validation_report.csv",
            "final_end_to_end_validation_summary.csv",
            "final_end_to_end_validation_manifest.csv",
            "final_end_to_end_validation_events.csv",
        ],
    },
    # Historical Event Study is kept flexible across the repo's v1/v2 naming.
    # We only accept exact filenames listed here; no first-CSV heuristic is used.
    "Historical Edge": {
        "artifact_candidates": ["historical-event-study-v2", "historical-event-study-v1"],
        "files": [
            "historical_event_study_summary_v2.csv",
            "historical_event_study_event_overlap_v2.csv",
            "historical_event_study_feature_redundancy_v2.csv",
            "historical_event_study_conditional_events_v2.csv",
            "historical_event_study_controlled_associations_v2.csv",
            "historical_event_study_sample_adequacy_v2.csv",
            "historical_event_study_baseline_v2.csv",
            "historical_event_study_summary_v1.csv",
            "historical_event_study_events_v1.csv",
            "historical_event_study_baseline_v1.csv",
            "historical_event_study_validation_v1.csv",
        ],
    },
}

ARTIFACT_ERRORS: Dict[str, str] = {}
DATASET_ERRORS: Dict[str, str] = {}


st.set_page_config(
    page_title=APP_TITLE,
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
:root{--bg:#070a0f;--panel:#0d121a;--panel2:#101722;--border:#202b39;--text:#e8edf5;--muted:#7e8a9c;--accent:#65d6bd;--blue:#78a9ff;--amber:#d8b36a;--red:#e27d8a}
html,body,[class*="css"]{font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.stApp{background:radial-gradient(circle at 80% -10%,rgba(50,72,105,.22),transparent 34%),linear-gradient(180deg,#070a0f 0%,#080c12 100%);color:var(--text)}
section[data-testid="stSidebar"]{background:#090d13;border-right:1px solid var(--border)}
section[data-testid="stSidebar"] *{color:#dce3ed!important}
.block-container{max-width:1550px;padding-top:1rem;padding-bottom:4rem}
.hero{background:linear-gradient(135deg,rgba(17,24,35,.98),rgba(9,13,20,.98));border:1px solid #202b3b;border-radius:18px;padding:27px 30px;margin-bottom:18px;box-shadow:0 15px 50px rgba(0,0,0,.24)}
.hero-title{font-size:31px;font-weight:780;letter-spacing:-.035em}.hero-subtitle{color:var(--muted);margin-top:5px;font-size:13px}
.badge,.research-badge{display:inline-block;border-radius:999px;padding:6px 12px;font-size:10px;font-weight:750;letter-spacing:.07em;text-transform:uppercase}
.badge{border:1px solid #263446;background:#121a25}.research-badge{border:1px solid #245046;background:#0d1c19;color:#6ed8c1}
.section{background:rgba(13,18,26,.96);border:1px solid var(--border);border-radius:15px;padding:19px;margin-bottom:17px}.section-title{font-size:17px;font-weight:730;margin-bottom:3px}.section-subtitle{color:var(--muted);font-size:11px;margin-bottom:15px}
.metric-card{background:linear-gradient(145deg,#111821,#0d131b);border:1px solid #202b39;border-radius:14px;padding:17px;min-height:106px}.metric-label{color:#778498;text-transform:uppercase;font-size:10px;letter-spacing:.09em}.metric-value{margin-top:8px;font-size:25px;font-weight:760;letter-spacing:-.02em}.metric-sub{color:#697688;margin-top:4px;font-size:11px}
.state-card{border:1px solid #243042;background:#0e151f;border-radius:12px;padding:14px;min-height:90px}.state-label{color:#758296;font-size:10px;text-transform:uppercase;letter-spacing:.08em}.state-value{font-size:16px;font-weight:720;margin-top:7px}.state-source{color:#667386;font-size:10px;margin-top:4px}
.evidence{background:#0b1118;border-left:3px solid #405168;border-radius:7px;padding:12px 14px;margin-bottom:9px}.evidence-title{font-weight:700;font-size:12px}.evidence-text{color:#aab5c4;font-size:11px;line-height:1.55;margin-top:3px}
.warning-box{background:#19150d;border:1px solid #4b3b1e;border-radius:10px;padding:13px;color:#cdbd95;font-size:11px}.info-box{background:#0c141d;border:1px solid #233348;border-radius:10px;padding:13px;color:#9eabbc;font-size:11px}
.footer{color:#586577;text-align:center;font-size:10px;padding-top:30px}div[data-testid="stMetric"]{background:#101720;border:1px solid #202b39;border-radius:13px;padding:10px}
</style>
""",
    unsafe_allow_html=True,
)


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def number(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        x = float(value)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def fmt(value: Any, digits: int = 2) -> str:
    x = number(value)
    if x is None:
        return clean(value) or "Not available"
    return f"{x:,.{digits}f}"


def fmt_pct(value: Any, digits: int = 2) -> str:
    x = number(value)
    return "N/A" if x is None else f"{x:.{digits}f}%"


def date_value(value: Any) -> str:
    if value is None:
        return "N/A"
    try:
        ts = pd.to_datetime(value, errors="coerce")
        return "N/A" if pd.isna(ts) else str(ts.date())
    except Exception:
        return clean(value) or "Not available"


def find_column(df: Optional[pd.DataFrame], candidates: List[str]) -> Optional[str]:
    if df is None or df.empty:
        return None
    normalized = {str(c).strip().lower(): c for c in df.columns}
    for candidate in candidates:
        if candidate.strip().lower() in normalized:
            return normalized[candidate.strip().lower()]
    return None


def row_value(df: Optional[pd.DataFrame], candidates: List[str], default: Any = None) -> Any:
    if df is None or df.empty:
        return default
    col = find_column(df, candidates)
    if col is None:
        return default
    return df.iloc[-1].get(col, default)


def latest_date(df: Optional[pd.DataFrame]) -> Optional[pd.Timestamp]:
    if df is None or df.empty:
        return None
    col = find_column(
        df,
        ["context_date", "asof_date", "study_date", "observation_date", "date", "event_date", "reported_date"],
    )
    if col is None:
        return None
    dates = pd.to_datetime(df[col], errors="coerce")
    return dates.max() if dates.notna().any() else None


def true_value(value: Any) -> bool:
    return clean(value).lower() in {"true", "1", "yes", "y", "pass", "passed"}


def safe_read_csv(raw: bytes) -> Optional[pd.DataFrame]:
    try:
        return pd.read_csv(io.BytesIO(raw), low_memory=False)
    except Exception:
        return None


def secret(name: str) -> Optional[str]:
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    return os.getenv(name)


def github_headers() -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "US500-Research-Terminal",
    }
    token = secret("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def github_artifacts() -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    headers = github_headers()
    for page in range(1, 11):
        response = requests.get(
            f"{GITHUB_API}/actions/artifacts?per_page=100&page={page}",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        items = response.json().get("artifacts", [])
        if not items:
            break
        result.extend(items)
        if len(items) < 100:
            break
    return result


def latest_artifact(name: str) -> Optional[Dict[str, Any]]:
    try:
        items = [x for x in github_artifacts() if x.get("name") == name and not x.get("expired", False)]
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return items[0] if items else None
    except Exception:
        return None


def latest_from_candidates(names: List[str]) -> Optional[Dict[str, Any]]:
    candidates = [latest_artifact(name) for name in names]
    candidates = [x for x in candidates if x]
    candidates.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return candidates[0] if candidates else None


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def download_artifact(artifact_id: int) -> Dict[str, bytes]:
    response = requests.get(
        f"{GITHUB_API}/actions/artifacts/{artifact_id}/zip",
        headers=github_headers(),
        timeout=90,
        allow_redirects=True,
    )
    response.raise_for_status()
    files: Dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        for name in archive.namelist():
            if not name.endswith("/"):
                files[name] = archive.read(name)
    return files


def artifact_files(artifact_name: Optional[str] = None, artifact_names: Optional[List[str]] = None) -> Dict[str, bytes]:
    artifact = latest_artifact(artifact_name) if artifact_name else latest_from_candidates(artifact_names or [])
    label = artifact_name or ", ".join(artifact_names or []) or "unknown artifact"
    if artifact is None:
        ARTIFACT_ERRORS[label] = "No non-expired artifact with the requested name was found."
        return {}
    try:
        return download_artifact(int(artifact["id"]))
    except requests.HTTPError as exc:
        ARTIFACT_ERRORS[label] = f"GitHub artifact download failed: {exc}"
    except Exception as exc:
        ARTIFACT_ERRORS[label] = f"Artifact download failed: {type(exc).__name__}: {exc}"
    return {}


def find_artifact_file(files: Dict[str, bytes], exact_names: List[str]) -> Optional[bytes]:
    for exact_name in exact_names:
        if exact_name in files:
            return files[exact_name]
        for path, content in files.items():
            if Path(path).name == exact_name:
                return content
    return None


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_named_csv(dataset_name: str, file_index: int = 0) -> Optional[pd.DataFrame]:
    config = DATASETS.get(dataset_name, {})
    filenames = config.get("files", [])
    if not filenames or file_index >= len(filenames):
        DATASET_ERRORS[dataset_name] = "No configured CSV filename for this dataset."
        return None
    # Prefer CSV files for this loader.
    csv_names = [x for x in filenames if x.lower().endswith('.csv')]
    if file_index >= len(csv_names):
        DATASET_ERRORS[dataset_name] = "Configured files do not contain the requested CSV index."
        return None
    files = artifact_files(config.get("artifact"), config.get("artifact_candidates"))
    raw = find_artifact_file(files, [csv_names[file_index]])
    if raw is None:
        DATASET_ERRORS[dataset_name] = f"File not found in artifact: {csv_names[file_index]}"
        return None
    df = safe_read_csv(raw)
    if df is None or df.empty:
        DATASET_ERRORS[dataset_name] = f"CSV could not be read or is empty: {csv_names[file_index]}"
        return None
    return df


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_named_csvs(dataset_name: str) -> Dict[str, pd.DataFrame]:
    config = DATASETS.get(dataset_name, {})
    files = artifact_files(config.get("artifact"), config.get("artifact_candidates"))
    result: Dict[str, pd.DataFrame] = {}
    for filename in config.get("files", []):
        if not filename.lower().endswith('.csv'):
            continue
        raw = find_artifact_file(files, [filename])
        if raw is None:
            continue
        df = safe_read_csv(raw)
        if df is not None and not df.empty:
            result[filename] = df
    if not result:
        DATASET_ERRORS[dataset_name] = "No configured CSV files were loaded from the artifact."
    return result


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_named_json(dataset_name: str) -> Optional[Dict[str, Any]]:
    config = DATASETS.get(dataset_name, {})
    json_names = [x for x in config.get("files", []) if x.lower().endswith('.json')]
    if not json_names:
        DATASET_ERRORS[dataset_name] = "No configured JSON filename for this dataset."
        return None
    files = artifact_files(config.get("artifact"), config.get("artifact_candidates"))
    raw = find_artifact_file(files, json_names)
    if raw is None:
        DATASET_ERRORS[dataset_name] = f"JSON file not found in artifact: {json_names[0]}"
        return None
    try:
        import json
        return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        DATASET_ERRORS[dataset_name] = f"JSON parse failed: {exc}"
        return None


def load_historical_files() -> Dict[str, pd.DataFrame]:
    config = DATASETS["Historical Edge"]
    files = artifact_files(None, config.get("artifact_candidates", []))
    result: Dict[str, pd.DataFrame] = {}
    for filename in config.get("files", []):
        raw = find_artifact_file(files, [filename])
        if raw is not None:
            df = safe_read_csv(raw)
            if df is not None and not df.empty:
                result[filename] = df
    return result


def local_file(filename: str) -> Optional[pd.DataFrame]:
    root = Path(__file__).resolve().parent
    for path in (root / filename, root / "artifacts" / filename, root / "data" / filename):
        if path.exists():
            try:
                return pd.read_csv(path, low_memory=False)
            except Exception:
                pass
    return None


def load_dataset(name: str) -> Optional[pd.DataFrame]:
    df = load_named_csv(name)
    if df is not None and not df.empty:
        return df
    config = DATASETS.get(name, {})
    for filename in config.get("files", []):
        df = local_file(filename)
        if df is not None and not df.empty:
            return df
    return None


research_context = load_dataset("Research Context")
macro_context = load_dataset("Macro Context")
financial_stress = load_dataset("Financial Stress")
sentiment = load_dataset("Sentiment")
technical = load_dataset("Technical")
liquidity = load_dataset("Liquidity")
breadth = load_dataset("Market Breadth")
event_news = load_dataset("Event News")
cross_asset = load_dataset("Cross Asset")
earnings = load_dataset("Earnings")
fed_intelligence = load_named_json("Fed Intelligence")
market_breadth = load_dataset("Market Breadth")
earnings_detail_files = load_named_csvs("Earnings Detail")
earnings_summary = earnings_detail_files.get("earnings_market_reaction_summary_v3.csv")
earnings_eps = earnings_detail_files.get("earnings_reaction_by_eps_class_v3.csv")
earnings_sector = earnings_detail_files.get("earnings_reaction_by_sector_v3.csv")
historical_files = load_historical_files()
final_validation_files = load_named_csvs("Final Validation")


@st.cache_data(ttl=MARKET_CACHE_TTL, show_spinner=False)
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
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = [str(col[0]) for col in data.columns]
        data = data.reset_index()
        if "Date" not in data.columns and "Datetime" in data.columns:
            data = data.rename(columns={"Datetime": "Date"})
        data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
        return data
    except Exception:
        return pd.DataFrame()


market = load_market_data()


def market_snapshot() -> Dict[str, Any]:
    if market.empty or "Close" not in market.columns:
        return {}
    close = pd.to_numeric(market["Close"], errors="coerce").dropna()
    if close.empty:
        return {}
    current = float(close.iloc[-1])
    previous = float(close.iloc[-2]) if len(close) > 1 else current
    change = current - previous
    change_pct = change / previous * 100 if previous else np.nan
    ath = float(close.max())
    drawdown = (current / ath - 1) * 100 if ath else np.nan
    return {"price": current, "change": change, "change_pct": change_pct, "ath": ath, "drawdown": drawdown,
            "high_2y": float(close.max()), "low_2y": float(close.min())}


SNAPSHOT = market_snapshot()


def current_context() -> Dict[str, Any]:
    if research_context is None or research_context.empty:
        return {}
    row = research_context.iloc[-1]

    def get(names: List[str], default: Any = None) -> Any:
        col = find_column(research_context, names)
        return row.get(col, default) if col else default

    return {
        "date": get(["context_date", "asof_date", "study_date"]),
        "layers": get(["available_layer_count", "layer_count"]),
        "macro_available": get(["macro_available"]),
        "sentiment_available": get(["sentiment_available"]),
        "technical_available": get(["technical_available"]),
        "pit": get(["point_in_time_safe"]),
        "research_only": get(["research_only"]),
        "economic_regime": get(["macro_economic_regime", "economic_regime"]),
        "inflation_score": get(["macro_inflation_score", "inflation_score"]),
        "labor_score": get(["macro_labor_score", "labor_score"]),
        "growth_score": get(["macro_growth_score", "growth_score"]),
        "fed_score": get(["macro_fed_score", "fed_score"]),
        "financial_stress_regime": get(["macro_financial_stress_regime", "financial_stress_regime"]),
        "financial_stress": get(["macro_financial_stress_composite", "financial_stress_composite"]),
        "vix": get(["macro_vix", "vix"]),
        "yield_spread": get(["macro_yield_10y_2y_spread", "yield_10y_2y_spread"]),
        "sentiment_regime": get(["sentiment_research_regime", "sentiment_unified_sentiment_regime", "research_regime"]),
        "sentiment_score": get(["sentiment_unified_sentiment_score", "unified_sentiment_score"]),
        "cot": get(["sentiment_cot_sentiment_score", "cot_sentiment_score", "cot_score"]),
        "aaii": get(["sentiment_aaii_sentiment_score", "aaii_sentiment_score", "aaii_score"]),
        "vix_sentiment": get(["sentiment_vix_sentiment_score", "vix_sentiment_score", "vix_score"]),
        "technical_regime": get(["technical_technical_regime", "technical_regime"]),
        "trend": get(["technical_trend_structure", "trend_structure"]),
        "rsi": get(["technical_RSI14", "RSI14"]),
        "atr_pct": get(["technical_ATR14_pct", "ATR14_pct"]),
        "roc20": get(["technical_ROC20_pct", "ROC20_pct"]),
        "technical_drawdown": get(["technical_drawdown_pct", "drawdown_pct"]),
    }


CTX = current_context()


def canonical_value(names: List[str], default: Any = None) -> Any:
    """Read the canonical latest Research Context row before falling back to a standalone dataset."""
    if research_context is None or research_context.empty:
        return default
    col = find_column(research_context, names)
    if col is None:
        return default
    value = research_context.iloc[-1].get(col, default)
    if pd.isna(value):
        return default
    return value


def display_value(value: Any, default: str = "Not available") -> str:
    if value is None:
        return default
    if isinstance(value, float) and np.isnan(value):
        return default
    text = clean(value)
    return text if text else default


def render_data_health() -> None:
    if not secret("GITHUB_TOKEN"):
        warning("GITHUB_TOKEN is not configured. The dashboard cannot reliably read GitHub Actions artifacts. The canonical Research Context will still be shown when available locally.")
    if DATASET_ERRORS:
        with st.expander("Data access diagnostics", expanded=False):
            for name, error in DATASET_ERRORS.items():
                st.write(f"**{name}:** {error}")



def hero(title: str, subtitle: str, page: str) -> None:
    st.markdown(
        f'<div class="hero"><div style="margin-bottom:10px"><span class="badge">{page}</span>&nbsp;<span class="research-badge">RESEARCH ONLY</span></div><div class="hero-title">{title}</div><div class="hero-subtitle">{subtitle}</div></div>',
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: Any, subtitle: str = "") -> None:
    st.markdown(
        f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div><div class="metric-sub">{subtitle}</div></div>',
        unsafe_allow_html=True,
    )


def state_card(label: str, value: Any, source: str = "") -> None:
    st.markdown(
        f'<div class="state-card"><div class="state-label">{label}</div><div class="state-value">{value}</div><div class="state-source">{source}</div></div>',
        unsafe_allow_html=True,
    )


def evidence(title: str, text: str) -> None:
    st.markdown(
        f'<div class="evidence"><div class="evidence-title">{title}</div><div class="evidence-text">{text}</div></div>',
        unsafe_allow_html=True,
    )


def info(message: str) -> None:
    st.markdown(f'<div class="info-box">{message}</div>', unsafe_allow_html=True)


def warning(message: str) -> None:
    st.markdown(f'<div class="warning-box">{message}</div>', unsafe_allow_html=True)


def section_title(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="section"><div class="section-title">{title}</div><div class="section-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def section_end() -> None:
    st.markdown('</div>', unsafe_allow_html=True)


def dataset_status(name: str, df: Optional[pd.DataFrame]) -> None:
    if df is None or df.empty:
        warning(f"<strong>{name}</strong><br>Dataset unavailable in this deployment.")
        return
    info(f"<strong>{name}</strong> · {len(df):,} rows · latest: {date_value(latest_date(df))}")


def plot_series(df: Optional[pd.DataFrame], date_candidates: List[str], value_candidates: List[str], title: str) -> None:
    if df is None or df.empty:
        warning(f"No research data available for {title}.")
        return
    dcol = find_column(df, date_candidates)
    vcol = find_column(df, value_candidates)
    if not dcol or not vcol:
        warning(f"The expected fields for {title} were not found in the research artifact.")
        return
    work = df[[dcol, vcol]].copy()
    work[dcol] = pd.to_datetime(work[dcol], errors="coerce")
    work[vcol] = pd.to_numeric(work[vcol], errors="coerce")
    work = work.dropna().sort_values(dcol).tail(500)
    if work.empty:
        warning(f"No usable observations are available for {title}.")
        return
    work = work.set_index(dcol)
    st.line_chart(work[vcol], height=280)


def table_clean(df: Optional[pd.DataFrame], max_rows: int = 30) -> None:
    if df is None or df.empty:
        warning("No data available.")
        return
    st.dataframe(df.tail(max_rows), use_container_width=True, hide_index=True)


def latest_numeric(df: Optional[pd.DataFrame], candidates: List[str]) -> Optional[float]:
    return number(row_value(df, candidates))


def render_overview() -> None:
    hero("US500 Research Intelligence", "A consolidated view of the latest research state, market context and historical evidence.", "Overview")
    if not SNAPSHOT:
        warning("US500 market snapshot is unavailable. Research artifacts remain accessible below.")
    cols = st.columns(5)
    cards = [
        ("US500 proxy", fmt(SNAPSHOT.get("price")), US500_TICKER),
        ("1D change", fmt_pct(SNAPSHOT.get("change_pct")), "public market proxy"),
        ("2Y high", fmt(SNAPSHOT.get("high_2y")), "rolling window"),
        ("2Y drawdown", fmt_pct(SNAPSHOT.get("drawdown")), "from rolling high"),
        ("Research date", date_value(CTX.get("date")), "Research Context"),
    ]
    for col, (label, value, sub) in zip(cols, cards):
        with col:
            metric_card(label, value, sub)

    st.markdown("### Current research state")
    cols = st.columns(4)
    states = [
        ("Macro", canonical_value(["macro_economic_regime", "economic_regime", "research_regime"]) or row_value(macro_context, ["economic_regime", "research_regime"]), "Macro research"),
        ("Financial stress", canonical_value(["macro_financial_stress_regime", "research_regime", "stress_regime"]) or row_value(financial_stress, ["research_regime", "stress_regime"]), "Financial Stress"),
        ("Sentiment", canonical_value(["sentiment_research_regime", "research_regime", "sentiment_regime"]) or row_value(sentiment, ["research_regime", "sentiment_regime"]), "Sentiment research"),
        ("Technical", canonical_value(["technical_technical_regime", "technical_regime", "research_regime"]) or row_value(technical, ["technical_regime", "research_regime"]), "Technical research"),
    ]
    for col, item in zip(cols, states):
        with col:
            state_card(item[0], item[1] or "Not available", item[2])

    section_title("Market research summary", "Evidence-oriented synthesis from the latest available research layers.")
    evidence("Macro", f"Current macro regime: <strong>{clean(states[0][1]) or 'Not available'}</strong>. Inflation, labor, growth and Federal Reserve fields are shown in the Macro page when available.")
    evidence("Financial stress", f"Current stress regime: <strong>{clean(states[1][1]) or 'Not available'}</strong>. The financial-stress dataset combines market stress components and point-in-time observations.")
    evidence("Sentiment", f"Current sentiment research state: <strong>{clean(states[2][1]) or 'Not available'}</strong>. The dashboard reports observed sentiment evidence without converting it into a trading instruction.")
    evidence("Technical", f"Current technical structure: <strong>{clean(states[3][1]) or 'Not available'}</strong>. Trend, RSI, ATR and rate-of-change evidence are displayed where the artifact provides them.")
    section_end()

    section_title("Market history", "Public S&P 500 proxy used only for visual market context.")
    if not market.empty and "Date" in market.columns and "Close" in market.columns:
        chart = market[["Date", "Close"]].dropna().set_index("Date")
        st.line_chart(chart["Close"], height=340)
    else:
        warning("Market-price series is unavailable.")
    section_end()


def render_regime() -> None:
    hero("Market Regime", "Current research state across the major evidence layers.", "Market Regime")
    cols = st.columns(4)
    items = [
        ("Macro regime", canonical_value(["macro_economic_regime", "economic_regime", "research_regime"]) or row_value(macro_context, ["economic_regime", "research_regime"])),
        ("Stress regime", canonical_value(["macro_financial_stress_regime", "research_regime", "stress_regime"]) or row_value(financial_stress, ["research_regime", "stress_regime"])),
        ("Sentiment regime", canonical_value(["sentiment_research_regime", "research_regime", "sentiment_regime"]) or row_value(sentiment, ["research_regime", "sentiment_regime"])),
        ("Technical regime", canonical_value(["technical_technical_regime", "technical_regime", "research_regime"]) or row_value(technical, ["technical_regime", "research_regime"])),
    ]
    for col, (label, value) in zip(cols, items):
        with col:
            state_card(label, value or "Not available")
    section_title("Research integrity", "The dashboard exposes observed research state rather than a unified trading decision.")
    evidence("Point-in-time status", "Research Context declares point-in-time safety as <strong>TRUE</strong> when that field is present and true.")
    evidence("Coverage", f"Research Context reports {fmt(CTX.get('layers'), 0)} available layers on {date_value(CTX.get('date'))} when the fields are present.")
    section_end()


def render_macro() -> None:
    hero("Macro Intelligence", "Economic and Federal Reserve research evidence.", "Macro")
    dataset_status("Macro Context", macro_context)
    cols = st.columns(5)
    values = [
        ("Economic regime", canonical_value(["macro_economic_regime", "economic_regime", "research_regime"]) or row_value(macro_context, ["economic_regime", "research_regime"])),
        ("Inflation", canonical_value(["macro_inflation_score", "inflation_score"]) or row_value(macro_context, ["inflation_score"])),
        ("Labor", canonical_value(["macro_labor_score", "labor_score"]) or row_value(macro_context, ["labor_score"])),
        ("Growth", canonical_value(["macro_growth_score", "growth_score"]) or row_value(macro_context, ["growth_score"])),
        ("Fed", canonical_value(["macro_fed_score", "fed_score"]) or row_value(macro_context, ["fed_score"])),
    ]
    for col, (label, value) in zip(cols, values):
        with col:
            metric_card(label, fmt(value), "latest research field")
    section_title("Macro evidence", "Use the underlying series to inspect the evidence rather than a directional conclusion.")
    candidates = [
        (["inflation_score", "INFLATION_SCORE"], "Inflation research score"),
        (["labor_score", "LABOR_SCORE"], "Labor research score"),
        (["growth_score", "GROWTH_SCORE"], "Growth research score"),
        (["fed_score", "FED_SCORE"], "Federal Reserve research score"),
    ]
    for value_cols, title in candidates:
        plot_series(macro_context, ["date", "asof_date", "study_date", "observation_date"], value_cols, title)
    section_end()


def render_stress() -> None:
    hero("Financial Stress", "Market stress, volatility, rates and financial-condition evidence.", "Financial Stress")
    dataset_status("Financial Stress", financial_stress)
    cols = st.columns(5)
    metrics = [
        ("Stress regime", row_value(financial_stress, ["research_regime", "stress_regime"])),
        ("Composite", row_value(financial_stress, ["composite_stress_score", "FINANCIAL_STRESS_COMPOSITE"])),
        ("VIX", row_value(financial_stress, ["VIX", "vix"])),
        ("10Y–2Y", row_value(financial_stress, ["YIELD_10Y_2Y_SPREAD", "YIELD_CURVE"])),
        ("Stress components", row_value(financial_stress, ["stress_component_count"])),
    ]
    for col, (label, value) in zip(cols, metrics):
        with col:
            metric_card(label, fmt(value), "latest available")
    section_title("Stress evidence", "The research dataset uses VIX, NFCI/ANFCI and the 10Y–2Y spread as stress components.")
    plot_series(financial_stress, ["asof_date", "date"], ["VIX", "vix"], "VIX")
    plot_series(financial_stress, ["asof_date", "date"], ["NFCI", "nfci"], "NFCI")
    plot_series(financial_stress, ["asof_date", "date"], ["ANFCI", "anfci"], "ANFCI")
    plot_series(financial_stress, ["asof_date", "date"], ["YIELD_10Y_2Y_SPREAD", "YIELD_CURVE"], "10Y–2Y spread")
    section_end()


def render_sentiment() -> None:
    hero("Sentiment Intelligence", "Observed sentiment evidence and its research regime.", "Sentiment")
    dataset_status("Sentiment", sentiment)
    cols = st.columns(4)
    metrics = [
        ("Research regime", canonical_value(["sentiment_research_regime", "research_regime", "sentiment_regime"]) or row_value(sentiment, ["research_regime", "sentiment_regime"])),
        ("Unified score", canonical_value(["sentiment_unified_sentiment_score", "unified_sentiment_score", "sentiment_score"]) or row_value(sentiment, ["unified_sentiment_score", "sentiment_score"])),
        ("COT", canonical_value(["sentiment_cot_sentiment_score", "cot_sentiment_score", "cot_score"]) or row_value(sentiment, ["cot_sentiment_score", "cot_score"])),
        ("VIX sentiment", canonical_value(["sentiment_vix_sentiment_score", "vix_sentiment_score", "vix_score"]) or row_value(sentiment, ["vix_sentiment_score", "vix_score"])),
    ]
    for col, (label, value) in zip(cols, metrics):
        with col:
            metric_card(label, fmt(value), "latest research field")
    section_title("Sentiment evidence", "Sentiment is presented as research evidence, not as an instruction.")
    plot_series(sentiment, ["date", "asof_date", "observation_date"], ["unified_sentiment_score", "sentiment_score"], "Unified sentiment score")
    plot_series(sentiment, ["date", "asof_date", "observation_date"], ["cot_sentiment_score", "cot_score"], "COT sentiment")
    section_end()


def render_technical() -> None:
    hero("Technical Intelligence", "Trend structure, momentum and volatility evidence.", "Technical")
    dataset_status("Technical", technical)
    cols = st.columns(5)
    metrics = [
        ("Regime", canonical_value(["technical_technical_regime", "technical_regime", "research_regime"]) or row_value(technical, ["technical_regime", "research_regime"])),
        ("Trend", canonical_value(["technical_trend_structure", "trend_structure"]) or row_value(technical, ["trend_structure", "technical_trend_structure"])),
        ("RSI 14", canonical_value(["technical_RSI14", "RSI14", "rsi14"]) or row_value(technical, ["RSI14", "rsi14"])),
        ("ATR 14 %", canonical_value(["technical_ATR14_pct", "ATR14_pct", "atr14_pct"]) or row_value(technical, ["ATR14_pct", "atr14_pct"])),
        ("ROC 20 %", canonical_value(["technical_ROC20_pct", "ROC20_pct", "roc20_pct"]) or row_value(technical, ["ROC20_pct", "roc20_pct"])),
    ]
    for col, (label, value) in zip(cols, metrics):
        with col:
            metric_card(label, fmt(value), "latest research field")
    section_title("Technical evidence", "Historical structure and momentum measures from the technical research layer.")
    plot_series(technical, ["date", "asof_date", "observation_date"], ["RSI14", "rsi14"], "RSI 14")
    plot_series(technical, ["date", "asof_date", "observation_date"], ["ROC20_pct", "roc20_pct"], "ROC 20")
    section_end()


def render_fed() -> None:
    hero("Fed Intelligence", "FOMC, minutes, press-conference and SEP research evidence.", "Fed Intelligence")
    if not fed_intelligence:
        warning("Fed Intelligence artifact is unavailable.")
        return
    if isinstance(fed_intelligence, dict):
        for key, value in fed_intelligence.items():
            if isinstance(value, (dict, list)):
                with st.expander(str(key).replace("_", " ").title(), expanded=False):
                    st.json(value, expanded=False)
            else:
                evidence(str(key).replace("_", " ").title(), clean(value))


def render_liquidity() -> None:
    hero("Liquidity", "Observed liquidity conditions from the dedicated research layer.", "Liquidity")
    dataset_status("Liquidity", liquidity)
    if liquidity is None or liquidity.empty:
        return
    dcol = find_column(liquidity, ["date", "asof_date", "observation_date"])
    numeric = liquidity.select_dtypes(include=[np.number]).columns.tolist()
    preferred = [c for c in ["liquidity_score", "net_liquidity", "fed_balance_sheet", "reserves"] if c in liquidity.columns]
    values = preferred or numeric[:4]
    if dcol and values:
        for col in values:
            plot_series(liquidity, [dcol], [col], str(col).replace("_", " ").title())
    table_clean(liquidity, 35)


def render_breadth() -> None:
    hero("Market Breadth", "Breadth participation and market-structure evidence.", "Market Breadth")
    dataset_status("Market Breadth", market_breadth)
    if market_breadth is None or market_breadth.empty:
        return
    date_candidates = ["date", "asof_date", "observation_date"]
    for col in ["advance_decline", "breadth_score", "percent_above_200dma", "percent_above_50dma", "ad_line"]:
        if find_column(market_breadth, [col]):
            plot_series(market_breadth, date_candidates, [col], col.replace("_", " ").title())
    table_clean(market_breadth, 40)


def render_earnings() -> None:
    hero("Earnings", "Observed market reactions around corporate earnings events.", "Earnings")
    tabs = st.tabs(["Reaction Data", "Summary / EPS", "Sector"])
    with tabs[0]:
        dataset_status("Earnings", earnings)
        table_clean(earnings, 40)
    with tabs[1]:
        table_clean(earnings_summary, 40)
        table_clean(earnings_eps, 40)
    with tabs[2]:
        table_clean(earnings_sector, 40)


def render_historical_edge() -> None:
    hero("Historical Edge", "Comparable historical environments and observed forward distributions.", "Historical Edge")
    if not historical_files:
        warning("Historical Event Study artifact is not available. No synthetic analogue is created.")
        return
    summary = next((df for name, df in historical_files.items() if "summary" in name.lower()), None)
    if summary is not None and not summary.empty:
        st.markdown("### Historical evidence summary")
        st.dataframe(summary, use_container_width=True, hide_index=True)
    st.markdown("### Supporting study artifacts")
    for name, df in historical_files.items():
        with st.expander(name.replace("_", " ").replace(".csv", "").title(), expanded=False):
            dataset_status(name, df)
            st.dataframe(df.tail(50), use_container_width=True, hide_index=True)


def render_event_studies() -> None:
    hero("Event Studies", "Historical event-response evidence from the dedicated research modules.", "Event Studies")
    tabs = st.tabs(["Event News", "Earnings"])
    with tabs[0]:
        dataset_status("Event News", event_news)
        table_clean(event_news, 40)
    with tabs[1]:
        dataset_status("Earnings", earnings)
        table_clean(earnings, 40)


def render_cross_asset() -> None:
    hero("Cross-Asset Intelligence", "Cross-market relationships and observed context.", "Cross-Asset")
    dataset_status("Cross Asset", cross_asset)
    if cross_asset is not None and not cross_asset.empty:
        st.dataframe(cross_asset.tail(50), use_container_width=True, hide_index=True)
    else:
        warning("Cross-asset research artifact is unavailable.")


def render_evidence() -> None:
    hero("Evidence", "The research terminal keeps current-state evidence, contract checks and validation together.", "Evidence")
    tabs = st.tabs(["Current Evidence", "Research Contract", "Validation"])
    with tabs[0]:
        current_date = date_value(CTX.get("date"))
        evidence("Research date", f"The consolidated Research Context date is <strong>{current_date}</strong> when available.")
        evidence("Macro evidence", f"Macro regime is <strong>{clean(CTX.get('economic_regime')) or 'Not available'}</strong>.")
        evidence("Financial stress", f"Stress regime is <strong>{clean(CTX.get('financial_stress_regime')) or clean(row_value(financial_stress, ['research_regime'])) or 'Not available'}</strong>; VIX is <strong>{fmt(CTX.get('vix') or row_value(financial_stress, ['VIX', 'vix']))}</strong>.")
        evidence("Sentiment evidence", f"Sentiment regime is <strong>{clean(CTX.get('sentiment_regime')) or 'Not available'}</strong>.")
        evidence("Technical evidence", f"Technical regime is <strong>{clean(CTX.get('technical_regime')) or 'Not available'}</strong>; RSI 14 is <strong>{fmt(CTX.get('rsi') or row_value(technical, ['RSI14', 'rsi14']))}</strong>.")
        evidence("Historical support", f"Actual historical-event-study artifacts loaded: <strong>{len(historical_files)}</strong>. No artificial analogue score is created.")
    with tabs[1]:
        info("Research-only boundary: this application visualizes existing research artifacts and does not generate trading signals, forecasts, execution instructions, position sizing, or directional recommendations.")
        evidence("Decision Engine", "The contract-first Decision Engine is treated as a research contract layer; its outputs are not converted into trading instructions here.")
    with tabs[2]:
        validation = load_named_csv("Decision Engine", 0)
        if validation is not None and not validation.empty:
            st.dataframe(validation, use_container_width=True, hide_index=True)
        else:
            info("Decision Engine validation artifact is not available.")
        if final_validation_files:
            st.markdown("### Final End-to-End Validation")
            for name, df in final_validation_files.items():
                st.caption(name)
                st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            info("Final End-to-End Validation artifact is not available.")

def render_data_status() -> None:
    hero("Data Status", "Compact deployment diagnostics for the research artifacts used by the dashboard.", "Data Status")
    rows = []
    for name in DATASETS:
        df = historical_files.get(next(iter(DATASETS[name].get("files", [])), "")) if name == "Historical Edge" else load_dataset(name)
        config = DATASETS[name]
        artifact = config.get("artifact") or ", ".join(config.get("artifact_candidates", []))
        rows.append({"Dataset": name, "Artifact": artifact, "Rows": 0 if df is None else len(df), "Latest": date_value(latest_date(df)) if df is not None else "N/A", "Status": "AVAILABLE" if df is not None and not df.empty else "MISSING"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if not secret("GITHUB_TOKEN"):
        warning("GITHUB_TOKEN is not configured. If the repository is private, Streamlit cannot read GitHub Actions artifacts. Add GITHUB_TOKEN to Streamlit secrets.")
    else:
        info("GITHUB_TOKEN detected. Artifact access is configured for the dashboard.")


PAGES = {
    "Overview": render_overview,
    "Market Regime": render_regime,
    "Macro": render_macro,
    "Fed Intelligence": render_fed,
    "Financial Stress": render_stress,
    "Liquidity": render_liquidity,
    "Sentiment": render_sentiment,
    "Technical": render_technical,
    "Market Breadth": render_breadth,
    "Historical Edge": render_historical_edge,
    "Event Studies": render_event_studies,
    "Cross-Asset": render_cross_asset,
    "Earnings": render_earnings,
    "Evidence": render_evidence,
}

with st.sidebar:
    st.markdown('<div style="font-size:18px;font-weight:780">◈ US500</div><div style="color:#748196;font-size:10px;letter-spacing:.08em;text-transform:uppercase;margin-bottom:18px">Research Intelligence Terminal</div>', unsafe_allow_html=True)
    page = st.radio("Research", list(PAGES.keys()), index=0)
    st.markdown("---")
    st.caption(f"Version {APP_VERSION}")
    st.caption(f"Market proxy: {US500_TICKER}")
    st.caption(f"Research date: {date_value(CTX.get('date'))}")

render_data_health()

try:
    PAGES[page]()
except requests.HTTPError as exc:
    warning(f"GitHub data request failed: <strong>{clean(exc)}</strong>. Check GITHUB_TOKEN and artifact access.")
except Exception as exc:
    warning(f"The selected page could not be rendered: <strong>{type(exc).__name__}: {clean(exc)}</strong>")

st.markdown('<div class="footer">US500 Macro Intelligence · Research-only visualization · Public S&P 500 price proxy may differ from broker US500 pricing.</div>', unsafe_allow_html=True)
