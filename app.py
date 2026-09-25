#!/usr/bin/env python3
"""
US500 MACRO INTELLIGENCE
RESEARCH TERMINAL — V4.2

Research-only visualization layer.

V4.2 architecture:
    1. Local public_data files
    2. Raw GitHub repository files
    3. Optional GitHub Actions artifact fallback

GITHUB_TOKEN is NOT required for normal operation.

No trading signals.
No execution.
No position sizing.
No SL/TP.
No market forecasting.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import requests
import streamlit as st


# ============================================================
# APPLICATION
# ============================================================

APP_TITLE = "US500 Research Terminal"
APP_VERSION = "4.2"

GITHUB_OWNER = "mohamednossaoui-max"
GITHUB_REPO = "US500-Macro-Intelligence"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

GITHUB_API = (
    f"https://api.github.com/repos/"
    f"{GITHUB_OWNER}/{GITHUB_REPO}"
)

RAW_BASE = (
    f"https://raw.githubusercontent.com/"
    f"{GITHUB_OWNER}/{GITHUB_REPO}/"
    f"{GITHUB_BRANCH}"
)

US500_TICKER = os.getenv("US500_TICKER", "^GSPC")

CACHE_TTL = 900
REQUEST_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 90


# ============================================================
# PUBLIC DATA DIRECTORY
# ============================================================

PUBLIC_DATA_DIR = (
    Path(__file__).resolve().parent / "public_data"
)


# ============================================================
# DATASET REGISTRY
# ============================================================

DATASETS: Dict[str, Dict[str, Any]] = {

    "Research Context": {
        "artifact": "research-context-v1",
        "files": [
            "research_context_v1.csv",
        ],
    },

    "Macro Context": {
        "artifact": "macro-context-v1",
        "files": [
            "macro_context_v1.csv",
            "macro_context_v1.json",
        ],
    },

    "Financial Stress": {
        "artifact": "financial-stress-research-v1",
        "files": [
            "financial_stress_research_v1.csv",
        ],
    },

    "Sentiment": {
        "artifact": "sentiment-engine-v1",
        "files": [
            "sentiment_engine_research_v1.csv",
        ],
    },

    "Technical": {
        "artifact": "technical-intelligence-v1",
        "files": [
            "technical_intelligence_research_v1.csv",
        ],
    },

    "Liquidity": {
        "artifact": "liquidity-intelligence-v1",
        "files": [
            "liquidity_intelligence_v1.csv",
            "liquidity_intelligence_research_v1.csv",
        ],
    },

    "Market Breadth": {
        "artifact": "market-breadth-full-validation-v1",
        "files": [
            "market_breadth_analysis_v1.csv",
        ],
    },

    "Event News": {
        "artifact": "event-news-intelligence-v2.1",
        "files": [
            "event_news_research_v2.csv",
        ],
    },

    "Cross Asset": {
        "artifact": "cross-asset-intelligence-v1",
        "files": [
            "cross_asset_intelligence_v1.csv",
        ],
    },

    "Earnings": {
        "artifact": "earnings-market-reaction-v3-results",
        "files": [
            "earnings_market_reaction_v3.csv",
        ],
    },

    "Fed Intelligence": {
        "artifact": "fed-intelligence-v1",
        "files": [
            "fed_intelligence_output_v1.json",
        ],
    },

    "Decision Engine": {
        "artifact": "decision-engine-v1",
        "files": [
            "decision_engine_validation_v1.csv",
            "decision_engine_validation_v1_summary.csv",
            "decision_engine_validation_v1_events.csv",
            "decision_engine_research_v1.csv",
            "decision_engine_research_v1_summary.csv",
        ],
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

    "Historical Edge": {
        "artifact_candidates": [
            "historical-event-study-v2",
            "historical-event-study-v1",
        ],
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


# ============================================================
# DIAGNOSTICS
# ============================================================

ARTIFACT_ERRORS: Dict[str, str] = {}
DATASET_ERRORS: Dict[str, str] = {}
RAW_ERRORS: Dict[str, str] = {}


# ============================================================
# STREAMLIT CONFIG
# ============================================================

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# STYLE
# ============================================================

st.markdown(
    """
<style>

.stApp{
    background:#070a0f;
    color:#e8edf5;
}

section[data-testid="stSidebar"]{
    background:#090d13;
}

.block-container{
    max-width:1550px;
    padding-top:1rem;
    padding-bottom:4rem;
}

.hero{
    background:linear-gradient(135deg,#111823,#090d14);
    border:1px solid #202b3b;
    border-radius:18px;
    padding:27px 30px;
    margin-bottom:18px;
}

.hero-title{
    font-size:31px;
    font-weight:780;
    letter-spacing:-.035em;
}

.hero-subtitle{
    color:#7e8a9c;
    margin-top:5px;
    font-size:13px;
}

.badge,
.research-badge{
    display:inline-block;
    border-radius:999px;
    padding:6px 12px;
    font-size:10px;
    font-weight:750;
    letter-spacing:.07em;
    text-transform:uppercase;
}

.badge{
    border:1px solid #263446;
    background:#121a25;
}

.research-badge{
    border:1px solid #245046;
    background:#0d1c19;
    color:#6ed8c1;
}

.section{
    background:#0d121a;
    border:1px solid #202b39;
    border-radius:15px;
    padding:19px;
    margin-bottom:17px;
}

.section-title{
    font-size:17px;
    font-weight:730;
    margin-bottom:3px;
}

.section-subtitle{
    color:#7e8a9c;
    font-size:11px;
    margin-bottom:15px;
}

.metric-card{
    background:linear-gradient(145deg,#111821,#0d131b);
    border:1px solid #202b39;
    border-radius:14px;
    padding:17px;
    min-height:106px;
}

.metric-label{
    color:#778498;
    text-transform:uppercase;
    font-size:10px;
    letter-spacing:.09em;
}

.metric-value{
    margin-top:8px;
    font-size:25px;
    font-weight:760;
}

.metric-sub{
    color:#697688;
    margin-top:4px;
    font-size:11px;
}

.state-card{
    border:1px solid #243042;
    background:#0e151f;
    border-radius:12px;
    padding:14px;
    min-height:90px;
}

.state-label{
    color:#758296;
    font-size:10px;
    text-transform:uppercase;
    letter-spacing:.08em;
}

.state-value{
    font-size:16px;
    font-weight:720;
    margin-top:7px;
}

.state-source{
    color:#667386;
    font-size:10px;
    margin-top:4px;
}

.evidence{
    background:#0b1118;
    border-left:3px solid #405168;
    border-radius:7px;
    padding:12px 14px;
    margin-bottom:9px;
}

.evidence-title{
    font-weight:700;
    font-size:12px;
}

.evidence-text{
    color:#aab5c4;
    font-size:11px;
    line-height:1.55;
    margin-top:3px;
}

.warning-box{
    background:#19150d;
    border:1px solid #4b3b1e;
    border-radius:10px;
    padding:13px;
    color:#cdbd95;
    font-size:11px;
}

.info-box{
    background:#0c141d;
    border:1px solid #233348;
    border-radius:10px;
    padding:13px;
    color:#9eabbc;
    font-size:11px;
}

.success-box{
    background:#0c1915;
    border:1px solid #245046;
    border-radius:10px;
    padding:13px;
    color:#82d8c2;
    font-size:11px;
}

.footer{
    color:#586577;
    text-align:center;
    font-size:10px;
    padding-top:30px;
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

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return str(value).strip()


def number(value: Any) -> Optional[float]:

    try:

        if value is None:
            return None

        if isinstance(value, str) and not value.strip():
            return None

        x = float(value)

        if np.isfinite(x):
            return x

        return None

    except (TypeError, ValueError):

        return None


def fmt(value: Any, digits: int = 2) -> str:

    x = number(value)

    if x is None:
        return clean(value) or "N/A"

    return f"{x:,.{digits}f}"


def fmt_pct(value: Any, digits: int = 2) -> str:

    x = number(value)

    if x is None:
        return "N/A"

    return f"{x:.{digits}f}%"


def date_value(value: Any) -> str:

    if value is None:
        return "N/A"

    try:

        ts = pd.to_datetime(
            value,
            errors="coerce",
        )

        if pd.isna(ts):
            return "N/A"

        return str(ts.date())

    except Exception:

        return clean(value) or "N/A"


def find_column(
    df: Optional[pd.DataFrame],
    candidates: List[str],
) -> Optional[str]:

    if df is None or df.empty:
        return None

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

    col = find_column(df, candidates)

    if col is None:
        return default

    value = df.iloc[-1].get(col, default)

    try:

        if pd.isna(value):
            return default

    except Exception:
        pass

    return value


def latest_date(
    df: Optional[pd.DataFrame],
) -> Optional[pd.Timestamp]:

    if df is None or df.empty:
        return None

    col = find_column(
        df,
        [
            "context_date",
            "asof_date",
            "study_date",
            "observation_date",
            "date",
            "event_date",
            "reported_date",
        ],
    )

    if col is None:
        return None

    dates = pd.to_datetime(
        df[col],
        errors="coerce",
    )

    if not dates.notna().any():
        return None

    return dates.max()


def safe_read_csv(raw: bytes) -> Optional[pd.DataFrame]:

    try:

        df = pd.read_csv(
            io.BytesIO(raw),
            low_memory=False,
        )

        return df

    except Exception:

        return None


def secret(name: str) -> Optional[str]:

    try:

        value = st.secrets.get(name)

        if value:
            return str(value)

    except Exception:
        pass

    value = os.getenv(name)

    if value:
        return str(value)

    return None


# ============================================================
# LOCAL FILE LOADER
# ============================================================

def local_bytes(filename: str) -> Optional[bytes]:

    candidates = [

        PUBLIC_DATA_DIR / filename,

        Path(__file__).resolve().parent / filename,

        Path(__file__).resolve().parent / "artifacts" / filename,

        Path(__file__).resolve().parent / "data" / filename,

    ]

    for path in candidates:

        try:

            if path.exists() and path.is_file():

                return path.read_bytes()

        except Exception:

            continue

    return None


def local_csv(filename: str) -> Optional[pd.DataFrame]:

    raw = local_bytes(filename)

    if raw is None:
        return None

    return safe_read_csv(raw)


def local_json(filename: str) -> Optional[Dict[str, Any]]:

    raw = local_bytes(filename)

    if raw is None:
        return None

    try:

        return json.loads(
            raw.decode("utf-8")
        )

    except Exception:

        return None


# ============================================================
# RAW GITHUB LOADER
# ============================================================

@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False,
)
def download_raw_file(
    filename: str,
) -> Optional[bytes]:

    url = (
        f"{RAW_BASE}/public_data/"
        f"{filename}"
    )

    try:

        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent":
                    "US500-Research-Terminal/4.2",
                "Accept":
                    "application/octet-stream",
            },
        )

        if response.status_code == 404:

            RAW_ERRORS[filename] = (
                "Raw GitHub file not found."
            )

            return None

        response.raise_for_status()

        return response.content

    except requests.RequestException as exc:

        RAW_ERRORS[filename] = (
            f"Raw GitHub request failed: "
            f"{type(exc).__name__}: {exc}"
        )

        return None

    except Exception as exc:

        RAW_ERRORS[filename] = (
            f"Unexpected raw-file error: "
            f"{type(exc).__name__}: {exc}"
        )

        return None


def remote_csv(
    filename: str,
) -> Optional[pd.DataFrame]:

    raw = download_raw_file(filename)

    if raw is None:
        return None

    return safe_read_csv(raw)


def remote_json(
    filename: str,
) -> Optional[Dict[str, Any]]:

    raw = download_raw_file(filename)

    if raw is None:
        return None

    try:

        return json.loads(
            raw.decode("utf-8")
        )

    except Exception as exc:

        RAW_ERRORS[filename] = (
            f"Invalid JSON: {type(exc).__name__}: {exc}"
        )

        return None


# ============================================================
# OPTIONAL GITHUB API / ARTIFACT FALLBACK
# ============================================================

def github_headers() -> Dict[str, str]:

    headers = {
        "Accept":
            "application/vnd.github+json",
        "User-Agent":
            "US500-Research-Terminal/4.2",
        "X-GitHub-Api-Version":
            "2022-11-28",
    }

    token = secret("GITHUB_TOKEN")

    if token:

        headers["Authorization"] = (
            f"Bearer {token}"
        )

    return headers


@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False,
)
def github_artifact_by_name(
    name: str,
) -> Optional[Dict[str, Any]]:

    url = (
        f"{GITHUB_API}/actions/artifacts"
        f"?name={requests.utils.quote(name, safe='')}"
        f"&per_page=100"
    )

    try:

        response = requests.get(
            url,
            headers=github_headers(),
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code == 404:

            ARTIFACT_ERRORS[name] = (
                "GitHub returned 404."
            )

            return None

        if response.status_code == 403:

            ARTIFACT_ERRORS[name] = (
                "GitHub API returned 403. "
                "Public API access may be rate limited."
            )

            return None

        if response.status_code == 429:

            ARTIFACT_ERRORS[name] = (
                "GitHub API rate limit exceeded."
            )

            return None

        response.raise_for_status()

        payload = response.json()

        artifacts = payload.get(
            "artifacts",
            [],
        )

        valid = [
            artifact
            for artifact in artifacts
            if artifact.get("name") == name
            and not artifact.get("expired", False)
        ]

        if not valid:

            ARTIFACT_ERRORS[name] = (
                f"No non-expired artifact found: {name}"
            )

            return None

        valid.sort(
            key=lambda x: (
                x.get("created_at", ""),
                x.get("id", 0),
            ),
            reverse=True,
        )

        return valid[0]

    except Exception as exc:

        ARTIFACT_ERRORS[name] = (
            f"Artifact lookup failed: "
            f"{type(exc).__name__}: {exc}"
        )

        return None


def latest_artifact(
    name: str,
) -> Optional[Dict[str, Any]]:

    return github_artifact_by_name(name)


def latest_from_candidates(
    names: List[str],
) -> Optional[Dict[str, Any]]:

    candidates = []

    for name in names:

        artifact = latest_artifact(name)

        if artifact:
            candidates.append(artifact)

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (
            x.get("created_at", ""),
            x.get("id", 0),
        ),
        reverse=True,
    )

    return candidates[0]


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
        timeout=DOWNLOAD_TIMEOUT,
        allow_redirects=True,
    )

    response.raise_for_status()

    files: Dict[str, bytes] = {}

    with zipfile.ZipFile(
        io.BytesIO(response.content)
    ) as archive:

        for name in archive.namelist():

            if not name.endswith("/"):

                files[name] = archive.read(name)

    return files


def artifact_files(
    artifact_name: Optional[str] = None,
    artifact_names: Optional[List[str]] = None,
) -> Dict[str, bytes]:

    label = (
        artifact_name
        or ", ".join(artifact_names or [])
        or "unknown artifact"
    )

    artifact = (
        latest_artifact(artifact_name)
        if artifact_name
        else latest_from_candidates(
            artifact_names or []
        )
    )

    if artifact is None:

        ARTIFACT_ERRORS.setdefault(
            label,
            "Artifact unavailable.",
        )

        return {}

    try:

        return download_artifact(
            int(artifact["id"])
        )

    except Exception as exc:

        ARTIFACT_ERRORS[label] = (
            f"Artifact download failed: "
            f"{type(exc).__name__}: {exc}"
        )

        return {}


def find_artifact_file(
    files: Dict[str, bytes],
    exact_names: List[str],
) -> Optional[bytes]:

    for exact_name in exact_names:

        if exact_name in files:
            return files[exact_name]

        for path, content in files.items():

            if Path(path).name == exact_name:
                return content

    return None


# ============================================================
# UNIFIED DATA LOADING
# ============================================================

@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False,
)
def load_named_csv(
    dataset_name: str,
    file_index: int = 0,
) -> Optional[pd.DataFrame]:

    config = DATASETS.get(
        dataset_name,
        {},
    )

    filenames = [
        f
        for f in config.get("files", [])
        if f.lower().endswith(".csv")
    ]

    if file_index >= len(filenames):
        return None

    filename = filenames[file_index]

    # --------------------------------------------------------
    # SOURCE 1: LOCAL PUBLIC DATA
    # --------------------------------------------------------

    df = local_csv(filename)

    if df is not None and not df.empty:
        return df

    # --------------------------------------------------------
    # SOURCE 2: RAW GITHUB
    # --------------------------------------------------------

    df = remote_csv(filename)

    if df is not None and not df.empty:
        return df

    # --------------------------------------------------------
    # SOURCE 3: GITHUB ARTIFACT
    # --------------------------------------------------------

    files = artifact_files(
        config.get("artifact"),
        config.get("artifact_candidates"),
    )

    raw = find_artifact_file(
        files,
        [filename],
    )

    if raw is not None:

        df = safe_read_csv(raw)

        if df is not None and not df.empty:
            return df

    DATASET_ERRORS[dataset_name] = (
        f"Data unavailable for {filename}. "
        f"Checked local, raw GitHub and artifact sources."
    )

    return None


@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False,
)
def load_named_csvs(
    dataset_name: str,
) -> Dict[str, pd.DataFrame]:

    config = DATASETS.get(
        dataset_name,
        {},
    )

    result: Dict[str, pd.DataFrame] = {}

    for filename in config.get("files", []):

        if not filename.lower().endswith(".csv"):
            continue

        df = local_csv(filename)

        if df is None:
            df = remote_csv(filename)

        if df is not None and not df.empty:

            result[filename] = df

    # Artifact fallback for files not found above.

    missing = [
        filename
        for filename in config.get("files", [])
        if filename.lower().endswith(".csv")
        and filename not in result
    ]

    if missing:

        files = artifact_files(
            config.get("artifact"),
            config.get("artifact_candidates"),
        )

        for filename in missing:

            raw = find_artifact_file(
                files,
                [filename],
            )

            if raw is None:
                continue

            df = safe_read_csv(raw)

            if df is not None and not df.empty:

                result[filename] = df

    return result


@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False,
)
def load_named_json(
    dataset_name: str,
) -> Optional[Dict[str, Any]]:

    config = DATASETS.get(
        dataset_name,
        {},
    )

    names = [
        f
        for f in config.get("files", [])
        if f.lower().endswith(".json")
    ]

    if not names:
        return None

    filename = names[0]

    # Local
    data = local_json(filename)

    if data:
        return data

    # Raw GitHub
    data = remote_json(filename)

    if data:
        return data

    # Artifact
    files = artifact_files(
        config.get("artifact"),
        config.get("artifact_candidates"),
    )

    raw = find_artifact_file(
        files,
        names,
    )

    if raw is None:
        return None

    try:

        return json.loads(
            raw.decode("utf-8")
        )

    except Exception:

        return None


def load_dataset(
    name: str,
) -> Optional[pd.DataFrame]:

    return load_named_csv(name)


# ============================================================
# LOAD DATASETS
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

event_news = load_dataset(
    "Event News"
)

cross_asset = load_dataset(
    "Cross Asset"
)

earnings = load_dataset(
    "Earnings"
)

fed_intelligence = load_named_json(
    "Fed Intelligence"
)

market_breadth = load_dataset(
    "Market Breadth"
)

earnings_detail_files = load_named_csvs(
    "Earnings"
)

historical_files = load_named_csvs(
    "Historical Edge"
)

final_validation_files = load_named_csvs(
    "Final Validation"
)

decision_engine_files = load_named_csvs(
    "Decision Engine"
)


# ============================================================
# RESEARCH CONTEXT
# ============================================================

def canonical_value(
    names: List[str],
    default: Any = None,
) -> Any:

    return row_value(
        research_context,
        names,
        default,
    )


CTX = {

    "date": canonical_value(
        [
            "context_date",
            "asof_date",
            "study_date",
        ]
    ),

    "layers": canonical_value(
        [
            "available_layer_count",
            "layer_count",
        ]
    ),

    "pit": canonical_value(
        [
            "point_in_time_safe",
        ]
    ),

    "economic_regime": canonical_value(
        [
            "macro_economic_regime",
            "economic_regime",
            "economic_research_regime",
        ]
    ),

    "financial_stress_regime": canonical_value(
        [
            "macro_financial_stress_regime",
            "financial_stress_regime",
            "stress_regime",
            "financial_research_regime",
        ]
    ),

    "sentiment_regime": canonical_value(
        [
            "sentiment_research_regime",
            "sentiment_regime",
        ]
    ),

    "technical_regime": canonical_value(
        [
            "technical_technical_regime",
            "technical_regime",
        ]
    ),
}


# ============================================================
# UI FUNCTIONS
# ============================================================

def hero(
    title: str,
    subtitle: str,
    page: str,
) -> None:

    st.markdown(
        f"""
        <div class="hero">
            <span class="badge">{page}</span>
            &nbsp;
            <span class="research-badge">
                RESEARCH ONLY
            </span>

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
) -> None:

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
) -> None:

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


def info(message: str) -> None:

    st.markdown(
        f'<div class="info-box">{message}</div>',
        unsafe_allow_html=True,
    )


def success(message: str) -> None:

    st.markdown(
        f'<div class="success-box">{message}</div>',
        unsafe_allow_html=True,
    )


def warning(message: str) -> None:

    st.markdown(
        f'<div class="warning-box">{message}</div>',
        unsafe_allow_html=True,
    )


def evidence(
    title: str,
    text: str,
) -> None:

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
) -> None:

    if df is None or df.empty:

        warning(
            f"<strong>{name}</strong><br>"
            "Dataset unavailable."
        )

    else:

        info(
            f"<strong>{name}</strong> · "
            f"{len(df):,} rows · "
            f"latest: "
            f"{date_value(latest_date(df))}"
        )


def table_clean(
    df: Optional[pd.DataFrame],
    max_rows: int = 30,
) -> None:

    if df is None or df.empty:

        warning("No data available.")

        return

    st.dataframe(
        df.tail(max_rows),
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# PAGES
# ============================================================

def render_regime() -> None:

    hero(
        "Market Regime",
        "Current research state across the major evidence layers.",
        "Market Regime",
    )

    cols = st.columns(4)

    items = [

        (
            "Macro regime",
            CTX["economic_regime"],
            "Research Context",
        ),

        (
            "Stress regime",
            CTX["financial_stress_regime"],
            "Research Context",
        ),

        (
            "Sentiment regime",
            CTX["sentiment_regime"],
            "Research Context",
        ),

        (
            "Technical regime",
            CTX["technical_regime"],
            "Research Context",
        ),

    ]

    for col, item in zip(cols, items):

        label, value, source = item

        with col:

            state_card(
                label,
                clean(value) or "Not available",
                source,
            )

    st.markdown(
        "### Research integrity"
    )

    evidence(
        "Research date",
        f"<strong>{date_value(CTX['date'])}</strong>",
    )

    evidence(
        "Available layers",
        f"<strong>{fmt(CTX['layers'], 0)}</strong>",
    )

    evidence(
        "Point-in-time safe",
        f"<strong>{clean(CTX['pit']) or 'N/A'}</strong>",
    )


def render_overview() -> None:

    hero(
        "US500 Research Intelligence",
        "Consolidated view of the latest research state.",
        "Overview",
    )

    cols = st.columns(4)

    items = [

        (
            "Macro",
            CTX["economic_regime"],
            "Macro research",
        ),

        (
            "Financial stress",
            CTX["financial_stress_regime"],
            "Financial Stress",
        ),

        (
            "Sentiment",
            CTX["sentiment_regime"],
            "Sentiment research",
        ),

        (
            "Technical",
            CTX["technical_regime"],
            "Technical research",
        ),

    ]

    for col, item in zip(cols, items):

        label, value, source = item

        with col:

            state_card(
                label,
                clean(value) or "Not available",
                source,
            )

    st.markdown(
        "### Current research context"
    )

    info(
        "The dashboard is research-only. "
        "It does not generate trading signals, "
        "forecasts, execution instructions, "
        "position sizing, or SL/TP."
    )

    evidence(
        "Research date",
        date_value(CTX["date"]),
    )

    evidence(
        "Available layers",
        fmt(CTX["layers"], 0),
    )


def render_macro() -> None:

    hero(
        "Macro Intelligence",
        "Economic and Federal Reserve research evidence.",
        "Macro",
    )

    dataset_status(
        "Macro Context",
        macro_context,
    )

    table_clean(
        macro_context,
        30,
    )


def render_stress() -> None:

    hero(
        "Financial Stress",
        "Market stress, volatility, rates and financial conditions.",
        "Financial Stress",
    )

    dataset_status(
        "Financial Stress",
        financial_stress,
    )

    table_clean(
        financial_stress,
        30,
    )


def render_sentiment() -> None:

    hero(
        "Sentiment Intelligence",
        "Observed sentiment evidence.",
        "Sentiment",
    )

    dataset_status(
        "Sentiment",
        sentiment,
    )

    table_clean(
        sentiment,
        30,
    )


def render_technical() -> None:

    hero(
        "Technical Intelligence",
        "Trend structure, momentum and volatility evidence.",
        "Technical",
    )

    dataset_status(
        "Technical",
        technical,
    )

    table_clean(
        technical,
        30,
    )


def render_fed() -> None:

    hero(
        "Fed Intelligence",
        "FOMC, minutes, press conference and SEP evidence.",
        "Fed Intelligence",
    )

    if not fed_intelligence:

        warning(
            "Fed Intelligence artifact is unavailable."
        )

        return

    st.json(
        fed_intelligence,
        expanded=False,
    )


def render_liquidity() -> None:

    hero(
        "Liquidity",
        "Observed liquidity conditions.",
        "Liquidity",
    )

    dataset_status(
        "Liquidity",
        liquidity,
    )

    table_clean(
        liquidity,
        40,
    )


def render_breadth() -> None:

    hero(
        "Market Breadth",
        "Breadth participation and market structure.",
        "Market Breadth",
    )

    dataset_status(
        "Market Breadth",
        market_breadth,
    )

    table_clean(
        market_breadth,
        40,
    )


def render_earnings() -> None:

    hero(
        "Earnings",
        "Observed market reactions around earnings events.",
        "Earnings",
    )

    dataset_status(
        "Earnings",
        earnings,
    )

    table_clean(
        earnings,
        40,
    )

    for name, df in earnings_detail_files.items():

        with st.expander(
            name,
            expanded=False,
        ):

            table_clean(
                df,
                40,
            )


def render_historical_edge() -> None:

    hero(
        "Historical Edge",
        "Comparable historical environments.",
        "Historical Edge",
    )

    if not historical_files:

        warning(
            "Historical Event Study data is unavailable."
        )

        return

    for name, df in historical_files.items():

        with st.expander(
            name,
            expanded=False,
        ):

            table_clean(
                df,
                50,
            )


def render_event_studies() -> None:

    hero(
        "Event Studies",
        "Historical event-response evidence.",
        "Event Studies",
    )

    dataset_status(
        "Event News",
        event_news,
    )

    table_clean(
        event_news,
        40,
    )

    dataset_status(
        "Earnings",
        earnings,
    )

    table_clean(
        earnings,
        40,
    )


def render_cross_asset() -> None:

    hero(
        "Cross-Asset Intelligence",
        "Cross-market relationships and observed context.",
        "Cross-Asset",
    )

    dataset_status(
        "Cross Asset",
        cross_asset,
    )

    table_clean(
        cross_asset,
        50,
    )


def render_decision_engine() -> None:

    hero(
        "Decision Engine",
        "Research validation artifacts only.",
        "Decision Engine",
    )

    if not decision_engine_files:

        warning(
            "Decision Engine research artifacts are unavailable."
        )

        return

    info(
        "This interface only displays research and "
        "validation artifacts. It does not execute "
        "trades or issue execution instructions."
    )

    for name, df in decision_engine_files.items():

        with st.expander(
            name,
            expanded=False,
        ):

            table_clean(
                df,
                50,
            )


def render_evidence() -> None:

    hero(
        "Evidence",
        "Current-state evidence and validation.",
        "Evidence",
    )

    evidence(
        "Macro",
        clean(
            CTX["economic_regime"]
        ) or "Not available",
    )

    evidence(
        "Financial stress",
        clean(
            CTX["financial_stress_regime"]
        ) or "Not available",
    )

    evidence(
        "Sentiment",
        clean(
            CTX["sentiment_regime"]
        ) or "Not available",
    )

    evidence(
        "Technical",
        clean(
            CTX["technical_regime"]
        ) or "Not available",
    )

    if final_validation_files:

        st.markdown(
            "### Final validation"
        )

        for name, df in final_validation_files.items():

            with st.expander(
                name,
                expanded=False,
            ):

                table_clean(
                    df,
                    50,
                )


def render_data_status() -> None:

    hero(
        "Data Status",
        "Deployment diagnostics for research data.",
        "Data Status",
    )

    local_count = 0

    try:

        if PUBLIC_DATA_DIR.exists():

            local_count = len(
                list(
                    PUBLIC_DATA_DIR.glob("*")
                )
            )

    except Exception:
        pass

    success(
        "V4.2 data architecture: "
        "Local public_data → Raw GitHub → "
        "optional GitHub Actions artifact fallback."
    )

    info(
        f"Public data directory: "
        f"<strong>{PUBLIC_DATA_DIR}</strong><br>"
        f"Local files detected: "
        f"<strong>{local_count}</strong><br>"
        f"GitHub branch: "
        f"<strong>{GITHUB_BRANCH}</strong>"
    )

    rows = []

    for name, config in DATASETS.items():

        df = None

        if name == "Research Context":
            df = research_context

        elif name == "Macro Context":
            df = macro_context

        elif name == "Financial Stress":
            df = financial_stress

        elif name == "Sentiment":
            df = sentiment

        elif name == "Technical":
            df = technical

        elif name == "Liquidity":
            df = liquidity

        elif name == "Market Breadth":
            df = market_breadth

        elif name == "Event News":
            df = event_news

        elif name == "Cross Asset":
            df = cross_asset

        elif name == "Earnings":
            df = earnings

        elif name == "Fed Intelligence":

            if fed_intelligence:
                rows_count = 1
            else:
                rows_count = 0

            rows.append(
                {
                    "Dataset": name,
                    "Artifact":
                        config.get("artifact", ""),
                    "Rows": rows_count,
                    "Latest": "JSON",
                    "Status":
                        "AVAILABLE"
                        if fed_intelligence
                        else "MISSING",
                }
            )

            continue

        rows.append(
            {
                "Dataset": name,
                "Artifact":
                    config.get("artifact")
                    or ", ".join(
                        config.get(
                            "artifact_candidates",
                            [],
                        )
                    ),
                "Rows":
                    0
                    if df is None
                    else len(df),
                "Latest":
                    date_value(
                        latest_date(df)
                    )
                    if df is not None
                    else "N/A",
                "Status":
                    "AVAILABLE"
                    if df is not None
                    and not df.empty
                    else "MISSING",
            }
        )

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
    )

    if RAW_ERRORS:

        st.markdown(
            "### Raw GitHub diagnostics"
        )

        for name, error in RAW_ERRORS.items():

            warning(
                f"<strong>{name}</strong><br>"
                f"{error}"
            )

    if ARTIFACT_ERRORS:

        st.markdown(
            "### Artifact diagnostics"
        )

        for name, error in ARTIFACT_ERRORS.items():

            warning(
                f"<strong>{name}</strong><br>"
                f"{error}"
            )

    if DATASET_ERRORS:

        st.markdown(
            "### Dataset diagnostics"
        )

        for name, error in DATASET_ERRORS.items():

            warning(
                f"<strong>{name}</strong><br>"
                f"{error}"
            )


# ============================================================
# NAVIGATION
# ============================================================

PAGES = {

    "Overview":
        render_overview,

    "Market Regime":
        render_regime,

    "Macro":
        render_macro,

    "Fed Intelligence":
        render_fed,

    "Financial Stress":
        render_stress,

    "Liquidity":
        render_liquidity,

    "Sentiment":
        render_sentiment,

    "Technical":
        render_technical,

    "Market Breadth":
        render_breadth,

    "Historical Edge":
        render_historical_edge,

    "Event Studies":
        render_event_studies,

    "Cross-Asset":
        render_cross_asset,

    "Earnings":
        render_earnings,

    "Decision Engine":
        render_decision_engine,

    "Evidence":
        render_evidence,

    "Data Status":
        render_data_status,
}


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown("## ◈ US500")

    st.caption(
        "Research Intelligence Terminal"
    )

    page = st.radio(
        "Research",
        list(PAGES.keys()),
        index=0,
    )

    st.markdown("---")

    st.caption(
        f"Version {APP_VERSION}"
    )

    st.caption(
        f"Research date: "
        f"{date_value(CTX['date'])}"
    )

    st.caption(
        "Token-free primary data access"
    )


# ============================================================
# RENDER
# ============================================================

try:

    PAGES[page]()

except Exception as exc:

    warning(
        "<strong>"
        "The selected page could not be rendered:"
        "</strong><br>"
        f"{type(exc).__name__}: {exc}"
    )


# ============================================================
# FOOTER
# ============================================================

st.markdown(
    '<div class="footer">'
    'US500 Macro Intelligence · '
    'Research-only visualization · V4.2'
    '</div>',
    unsafe_allow_html=True,
)
