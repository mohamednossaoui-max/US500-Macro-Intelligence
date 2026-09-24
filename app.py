#!/usr/bin/env python3

"""
US500 MACRO INTELLIGENCE
RESEARCH TERMINAL / EDGE FINDER STYLE

Purpose
-------
Professional visualization layer for the completed research stack.

IMPORTANT ARCHITECTURE RULES
----------------------------
- Research-only.
- No BUY / SELL signals.
- No trade execution.
- No deterministic market forecast.
- No directional Decision Engine.
- No position sizing.
- No SL / TP.
- No trading recommendation.

The application visualizes existing research artifacts produced by
GitHub Actions and committed research files.

Primary data sources
--------------------
1. Latest GitHub Actions artifacts.
2. Repository CSV fallback files.
3. Public Yahoo Finance US500 proxy for current market visualization.

Repository
----------
mohamednossaoui-max/US500-Macro-Intelligence
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf


# ============================================================
# CONFIGURATION
# ============================================================

APP_TITLE = "US500 Research Terminal"
APP_VERSION = "1.0"

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


ARTIFACT_MAP = {
    "Research Context": "research-context-v1",
    "Macro Context": "macro-context-v1",
    "Financial Stress": "financial-stress-research-v1",
    "Technical": "technical-intelligence-v1",
    "Liquidity": "liquidity-intelligence-v1",
    "Market Breadth": "market-breadth-analysis-v1",
    "Cross Asset": "cross-asset-intelligence-v1",
    "Historical Edge": "historical-event-study-v2",
    "Historical Edge v1": "historical-event-study-v1",
    "Event News": "event-news-intelligence-v2.1",
    "Earnings": "earnings-market-reaction-v3-results",
    "Decision Context": "decision-engine-v1",
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
# GLOBAL CSS
# ============================================================

st.markdown(
    """
<style>

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
            circle at top right,
            rgba(35, 47, 72, 0.35),
            transparent 38%
        ),
        #080b11;
    color: #e8edf5;
}

section[data-testid="stSidebar"] {
    background: #0b0f16;
    border-right: 1px solid #1c2533;
}

section[data-testid="stSidebar"] * {
    color: #d8dee9 !important;
}

.block-container {
    max-width: 1500px;
    padding-top: 1.2rem;
    padding-bottom: 3rem;
}

h1, h2, h3 {
    letter-spacing: -0.025em;
}

.hero {
    background:
        linear-gradient(
            135deg,
            rgba(20, 27, 40, 0.98),
            rgba(11, 15, 23, 0.98)
        );
    border: 1px solid #202b3a;
    border-radius: 18px;
    padding: 26px 30px;
    margin-bottom: 18px;
    box-shadow: 0 12px 45px rgba(0,0,0,0.25);
}

.hero-title {
    font-size: 31px;
    font-weight: 750;
    margin-bottom: 4px;
}

.hero-subtitle {
    color: #8d99aa;
    font-size: 14px;
}

.metric-card {
    background: #10151e;
    border: 1px solid #202a38;
    border-radius: 14px;
    padding: 18px;
    min-height: 110px;
}

.metric-label {
    color: #8490a2;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.metric-value {
    font-size: 26px;
    font-weight: 720;
    margin-top: 8px;
}

.metric-sub {
    color: #7f8b9d;
    font-size: 12px;
    margin-top: 4px;
}

.section-card {
    background: #0f141d;
    border: 1px solid #1e2937;
    border-radius: 15px;
    padding: 20px;
    margin-bottom: 18px;
}

.badge {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 999px;
    background: #17202d;
    border: 1px solid #293547;
    color: #aeb9c9;
    font-size: 11px;
    font-weight: 650;
    letter-spacing: 0.05em;
}

.research-badge {
    display: inline-block;
    padding: 6px 12px;
    border-radius: 999px;
    background: #101f1c;
    border: 1px solid #23463f;
    color: #7bd8c2;
    font-size: 11px;
    font-weight: 700;
}

.small-muted {
    color: #768295;
    font-size: 12px;
}

.evidence {
    background: #0c1118;
    border-left: 3px solid #43536a;
    border-radius: 8px;
    padding: 13px 16px;
    margin-bottom: 10px;
    color: #b7c1cf;
}

.footer {
    text-align: center;
    color: #5f6b7c;
    font-size: 11px;
    padding-top: 25px;
}

div[data-testid="stMetric"] {
    background: #10151e;
    border: 1px solid #202a38;
    border-radius: 13px;
    padding: 12px;
}

button[kind="secondary"] {
    border-color: #273344;
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


def safe_number(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None

        text = str(value).strip()

        if text == "":
            return None

        value = float(text)

        if not np.isfinite(value):
            return None

        return value

    except Exception:
        return None


def format_value(value: Any) -> str:
    number = safe_number(value)

    if number is not None:
        if abs(number) >= 1000:
            return f"{number:,.2f}"

        if abs(number) >= 100:
            return f"{number:,.1f}"

        return f"{number:.3f}"

    text = clean(value)

    if len(text) > 60:
        return text[:57] + "..."

    return text


def friendly_name(name: str) -> str:
    text = str(name)

    replacements = {
        "_": " ",
        "-": " ",
    }

    for a, b in replacements.items():
        text = text.replace(a, b)

    return text.strip().title()


def is_true(value: Any) -> bool:
    return clean(value).lower() in {
        "true",
        "1",
        "yes",
        "y",
        "pass",
        "passed",
    }


def latest_date(df: pd.DataFrame) -> str:
    candidates = [
        "asof_date",
        "context_date",
        "date",
        "event_date",
        "reported_date",
        "observation_date",
    ]

    for column in candidates:
        if column in df.columns:
            parsed = pd.to_datetime(
                df[column],
                errors="coerce",
            )

            if parsed.notna().any():
                return str(
                    parsed.dropna().max().date()
                )

    return "N/A"


def find_column(
    df: pd.DataFrame,
    candidates: List[str],
) -> Optional[str]:

    normalized = {
        str(c).lower(): c
        for c in df.columns
    }

    for candidate in candidates:

        if candidate.lower() in normalized:
            return normalized[candidate.lower()]

    return None


# ============================================================
# GITHUB API
# ============================================================

def github_headers() -> Dict[str, str]:

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "US500-Research-Terminal",
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
def list_artifacts() -> List[Dict[str, Any]]:

    artifacts = []

    for page in range(1, 6):

        url = (
            f"{GITHUB_API}/actions/artifacts"
            f"?per_page=100&page={page}"
        )

        response = requests.get(
            url,
            headers=github_headers(),
            timeout=30,
        )

        response.raise_for_status()

        payload = response.json()

        page_items = payload.get(
            "artifacts",
            [],
        )

        if not page_items:
            break

        artifacts.extend(
            page_items
        )

        if len(page_items) < 100:
            break

    return artifacts


def latest_artifact(
    artifact_name: str,
) -> Optional[Dict[str, Any]]:

    try:

        artifacts = list_artifacts()

        candidates = [
            a
            for a in artifacts
            if a.get("name")
            == artifact_name
            and not a.get(
                "expired",
                False,
            )
        ]

        if not candidates:
            return None

        candidates.sort(
            key=lambda x: x.get(
                "created_at",
                "",
            ),
            reverse=True,
        )

        return candidates[0]

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

            files[
                Path(name).name
            ] = archive.read(name)

    return files


def artifact_dataframe(
    artifact_name: str,
) -> Optional[pd.DataFrame]:

    artifact = latest_artifact(
        artifact_name
    )

    if not artifact:
        return None

    try:

        files = download_artifact(
            int(artifact["id"])
        )

        csv_files = [
            name
            for name in files
            if name.lower().endswith(
                ".csv"
            )
        ]

        if not csv_files:
            return None

        preferred = sorted(
            csv_files,
            key=lambda x: (
                0
                if "summary" in x.lower()
                else 1,
                x,
            ),
        )

        raw = files[
            preferred[0]
        ]

        return pd.read_csv(
            io.BytesIO(raw)
        )

    except Exception:
        return None


# ============================================================
# LOCAL FALLBACK
# ============================================================

def local_csv_candidates(
    artifact_name: str,
) -> List[Path]:

    root = Path(
        __file__
    ).resolve().parent

    mapping = {
        "financial-stress-research-v1": [
            "financial_stress_research_v1.csv",
            "financial_stress_validation_v1_2.csv",
        ],
        "macro-context-v1": [
            "macro_context_v1.csv",
        ],
        "technical-intelligence-v1": [
            "technical_intelligence_research_v1.csv",
            "technical_intelligence_research_summary_v1.csv",
        ],
        "liquidity-intelligence-v1": [
            "liquidity_intelligence_research_v1.csv",
            "liquidity_intelligence_summary_v1.csv",
        ],
        "market-breadth-analysis-v1": [
            "market_breadth_analysis_v1.csv",
        ],
        "cross-asset-intelligence-v1": [
            "cross_asset_intelligence_v1.csv",
        ],
    }

    names = mapping.get(
        artifact_name,
        [],
    )

    return [
        root / name
        for name in names
        if (root / name).exists()
    ]


@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False,
)
def load_dataset(
    artifact_name: str,
) -> Optional[pd.DataFrame]:

    # --------------------------------------------------------
    # GitHub artifact
    # --------------------------------------------------------

    df = artifact_dataframe(
        artifact_name
    )

    if df is not None and not df.empty:
        return df

    # --------------------------------------------------------
    # Local fallback
    # --------------------------------------------------------

    for path in local_csv_candidates(
        artifact_name
    ):

        try:

            df = pd.read_csv(
                path
            )

            if not df.empty:
                return df

        except Exception:
            continue

    return None


# ============================================================
# MARKET DATA
# ============================================================

@st.cache_data(
    ttl=300,
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
        )

        if isinstance(
            data.columns,
            pd.MultiIndex,
        ):
            data.columns = [
                col[0]
                for col in data.columns
            ]

        data = data.reset_index()

        return data

    except Exception:

        return pd.DataFrame()


market = load_market_data()


def market_snapshot() -> Dict[str, Any]:

    if market.empty:
        return {
            "price": None,
            "change": None,
            "change_pct": None,
            "high": None,
            "low": None,
            "ath": None,
            "drawdown": None,
        }

    close = pd.to_numeric(
        market["Close"],
        errors="coerce",
    ).dropna()

    if close.empty:
        return {}

    price = float(
        close.iloc[-1]
    )

    previous = (
        float(close.iloc[-2])
        if len(close) >= 2
        else price
    )

    change = price - previous

    change_pct = (
        change / previous * 100
        if previous
        else None
    )

    ath = float(
        close.max()
    )

    drawdown = (
        (price / ath - 1) * 100
        if ath
        else None
    )

    return {
        "price": price,
        "change": change,
        "change_pct": change_pct,
        "high": float(close.max()),
        "low": float(close.min()),
        "ath": ath,
        "drawdown": drawdown,
    }


SNAPSHOT = market_snapshot()


# ============================================================
# DATASET LOADING
# ============================================================

@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False,
)
def load_all_research() -> Dict[str, pd.DataFrame]:

    result = {}

    for label, artifact_name in (
        ARTIFACT_MAP.items()
    ):

        df = load_dataset(
            artifact_name
        )

        if df is not None and not df.empty:
            result[label] = df

    return result


RESEARCH = load_all_research()


# ============================================================
# RESEARCH CONTEXT
# ============================================================

context = RESEARCH.get(
    "Research Context"
)

if context is None:
    context = RESEARCH.get(
        "Decision Context"
    )


# ============================================================
# CONTEXT EXTRACTION
# ============================================================

def context_value(
    names: List[str],
    default: Any = "N/A",
) -> Any:

    if context is None or context.empty:
        return default

    row = context.iloc[-1]

    column = find_column(
        context,
        names,
    )

    if column is None:
        return default

    return row.get(
        column,
        default,
    )


def layer_status(
    layer: str,
) -> str:

    value = context_value(
        [
            f"{layer}_available",
            f"{layer}_status",
            f"{layer}_completeness",
        ],
        "N/A",
    )

    if is_true(value):
        return "AVAILABLE"

    if clean(value).upper() in {
        "COMPLETE",
        "AVAILABLE",
        "PASS",
        "PASSED",
    }:
        return "AVAILABLE"

    if clean(value).upper() in {
        "FALSE",
        "MISSING",
        "UNAVAILABLE",
    }:
        return "UNAVAILABLE"

    return clean(value) or "N/A"


# ============================================================
# UI COMPONENTS
# ============================================================

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
                {format_value(value)}
            </div>
            <div class="metric-sub">
                {subtitle}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def evidence_card(
    title: str,
    text: str,
):

    st.markdown(
        f"""
        <div class="evidence">
            <strong>{title}</strong><br>
            <span>{text}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(
    title: str,
    subtitle: str = "",
):

    st.markdown(
        f"""
        <div class="section-card">
            <h3 style="margin-bottom:4px;">
                {title}
            </h3>
            <div class="small-muted">
                {subtitle}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def numeric_columns(
    df: pd.DataFrame,
) -> List[str]:

    result = []

    for column in df.columns:

        converted = pd.to_numeric(
            df[column],
            errors="coerce",
        )

        if (
            converted.notna().sum()
            >= max(
                1,
                int(
                    len(df) * 0.30
                ),
            )
        ):
            result.append(column)

    return result


def display_research_dataset(
    df: Optional[pd.DataFrame],
    title: str,
):

    if df is None or df.empty:

        st.info(
            f"No current artifact available for {title}."
        )

        return

    st.caption(
        f"{len(df):,} observations • "
        f"latest date: {latest_date(df)}"
    )

    numeric = numeric_columns(
        df
    )

    if numeric:

        latest = df.iloc[-1]

        selected = numeric[:8]

        cols = st.columns(
            min(
                len(selected),
                4,
            )
        )

        for index, column in enumerate(
            selected
        ):

            with cols[
                index % len(cols)
            ]:

                metric_card(
                    friendly_name(column),
                    latest.get(
                        column,
                        "N/A",
                    ),
                    title,
                )

    with st.expander(
        "Inspect latest research record"
    ):

        latest_row = (
            df.tail(1)
            .T
            .reset_index()
        )

        latest_row.columns = [
            "Field",
            "Value",
        ]

        st.dataframe(
            latest_row,
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "## ◈ US500 RESEARCH"
    )

    st.markdown(
        '<span class="research-badge">'
        'RESEARCH ONLY'
        '</span>',
        unsafe_allow_html=True,
    )

    st.write("")

    page = st.radio(
        "Research Desk",
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
        f"Ticker: {US500_TICKER}"
    )

    st.caption(
        f"App: {APP_VERSION}"
    )

    if st.button(
        "Refresh Research",
        use_container_width=True,
    ):

        st.cache_data.clear()

        st.rerun()


# ============================================================
# HERO
# ============================================================

st.markdown(
    f"""
    <div class="hero">
        <div class="hero-title">
            US500 Research Terminal
        </div>

        <div class="hero-subtitle">
            Evidence-driven market intelligence —
            Macro · Stress · Sentiment · Technical ·
            Historical Edge · Cross-Asset · Earnings
        </div>

        <div style="margin-top:14px;">
            <span class="research-badge">
                NO TRADING SIGNALS
            </span>
            &nbsp;
            <span class="badge">
                FULL RESEARCH OUTPUT
            </span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# OVERVIEW
# ============================================================

if page == "Overview":

    st.subheader(
        "Market Research Overview"
    )

    date_text = latest_date(
        context
    ) if context is not None else "N/A"

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        metric_card(
            "US500",
            SNAPSHOT.get(
                "price",
                "N/A",
            ),
            "Public S&P 500 proxy",
        )

    with c2:
        metric_card(
            "Daily Change",
            (
                f"{SNAPSHOT['change_pct']:+.2f}%"
                if SNAPSHOT.get(
                    "change_pct"
                )
                is not None
                else "N/A"
            ),
            "Latest completed session",
        )

    with c3:
        metric_card(
            "All-Time Drawdown",
            (
                f"{SNAPSHOT['drawdown']:.2f}%"
                if SNAPSHOT.get(
                    "drawdown"
                )
                is not None
                else "N/A"
            ),
            "Against available price history",
        )

    with c4:
        metric_card(
            "Research Date",
            date_text,
            "Latest synchronized context",
        )

    st.markdown("###")

    cols = st.columns(4)

    layers = [
        (
            "Macro",
            layer_status("macro"),
        ),
        (
            "Sentiment",
            layer_status("sentiment"),
        ),
        (
            "Technical",
            layer_status("technical"),
        ),
        (
            "Research Context",
            (
                "AVAILABLE"
                if context is not None
                else "N/A"
            ),
        ),
    ]

    for col, (
        name,
        status,
    ) in zip(
        cols,
        layers,
    ):

        with col:

            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">
                        {name}
                    </div>

                    <div class="metric-value"
                         style="font-size:20px;">
                        {status}
                    </div>

                    <div class="metric-sub">
                        Research layer
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("###")

    st.subheader(
        "Research State"
    )

    if context is not None:

        context_row = context.iloc[-1]

        important_fields = [
            "context_date",
            "asof_date",
            "available_layer_count",
            "completeness_status",
            "context_state",
            "point_in_time_safe",
            "research_only",
        ]

        rows = []

        for field in important_fields:

            column = find_column(
                context,
                [field],
            )

            if column:

                rows.append(
                    [
                        friendly_name(
                            field
                        ),
                        context_row.get(
                            column,
                            "",
                        ),
                    ]
                )

        if rows:

            st.dataframe(
                pd.DataFrame(
                    rows,
                    columns=[
                        "Research Field",
                        "Current Value",
                    ],
                ),
                use_container_width=True,
                hide_index=True,
            )

    st.subheader(
        "Research Coverage"
    )

    coverage = []

    for label in [
        "Macro Context",
        "Financial Stress",
        "Technical",
        "Liquidity",
        "Market Breadth",
        "Cross Asset",
        "Historical Edge",
        "Event News",
        "Earnings",
    ]:

        coverage.append(
            [
                label,
                (
                    "Available"
                    if label in RESEARCH
                    else "Not available"
                ),
            ]
        )

    st.dataframe(
        pd.DataFrame(
            coverage,
            columns=[
                "Research Module",
                "Current Availability",
            ],
        ),
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# MARKET REGIME
# ============================================================

elif page == "Market Regime":

    st.subheader(
        "Current Market Research State"
    )

    st.caption(
        "This page describes the current research environment. "
        "It does not convert the state into a trade direction."
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        metric_card(
            "Macro",
            layer_status("macro"),
            "Current research availability",
        )

    with c2:
        metric_card(
            "Financial Stress",
            (
                "AVAILABLE"
                if "Financial Stress"
                in RESEARCH
                else "N/A"
            ),
            "Stress research",
        )

    with c3:
        metric_card(
            "Technical",
            layer_status("technical"),
            "Technical research",
        )

    st.markdown("###")

    for label in [
        "Macro Context",
        "Financial Stress",
        "Sentiment",
        "Technical",
        "Liquidity",
        "Market Breadth",
        "Cross Asset",
    ]:

        df = RESEARCH.get(
            label
        )

        if df is None:
            continue

        st.markdown(
            f"### {label}"
        )

        display_research_dataset(
            df,
            label,
        )


# ============================================================
# MACRO
# ============================================================

elif page == "Macro":

    st.subheader(
        "Macro Intelligence"
    )

    df = RESEARCH.get(
        "Macro Context"
    )

    if df is None:
        df = context

    display_research_dataset(
        df,
        "Macro Intelligence",
    )

    if df is not None:

        st.markdown(
            "### Macro Evidence"
        )

        numeric = numeric_columns(
            df
        )

        if numeric:

            latest = df.iloc[-1]

            for column in numeric[:8]:

                value = latest.get(
                    column
                )

                evidence_card(
                    friendly_name(
                        column
                    ),
                    (
                        "Latest research observation: "
                        f"{format_value(value)}"
                    ),
                )


# ============================================================
# FINANCIAL STRESS
# ============================================================

elif page == "Financial Stress":

    st.subheader(
        "Financial Stress Intelligence"
    )

    df = RESEARCH.get(
        "Financial Stress"
    )

    display_research_dataset(
        df,
        "Financial Stress",
    )

    if df is not None:

        st.markdown(
            "### Stress Structure"
        )

        preferred = [
            "VIX",
            "NFCI",
            "ANFCI",
            "YIELD_10Y_2Y_SPREAD",
            "VIX_Z",
            "NFCI_Z",
            "ANFCI_Z",
            "YIELD_CURVE_STRESS_Z",
            "composite_stress_score",
            "research_regime",
        ]

        available = [
            x
            for x in preferred
            if x in df.columns
        ]

        if available:

            latest = df.iloc[-1]

            rows = [
                [
                    friendly_name(
                        column
                    ),
                    format_value(
                        latest.get(
                            column
                        )
                    ),
                ]
                for column in available
            ]

            st.dataframe(
                pd.DataFrame(
                    rows,
                    columns=[
                        "Stress Component",
                        "Latest Observation",
                    ],
                ),
                use_container_width=True,
                hide_index=True,
            )

        numeric = [
            c
            for c in numeric_columns(df)
            if c not in {
                "record_id"
            }
        ]

        if numeric:

            chart_columns = [
                c
                for c in [
                    "VIX",
                    "NFCI",
                    "ANFCI",
                    "composite_stress_score",
                ]
                if c in df.columns
            ]

            if chart_columns:

                chart = (
                    df.copy()
                    .tail(500)
                )

                chart[
                    chart_columns
                ] = chart[
                    chart_columns
                ].apply(
                    pd.to_numeric,
                    errors="coerce",
                )

                st.line_chart(
                    chart[
                        chart_columns
                    ],
                    use_container_width=True,
                )


# ============================================================
# SENTIMENT
# ============================================================

elif page == "Sentiment":

    st.subheader(
        "Sentiment Intelligence"
    )

    sentiment_datasets = [
        (
            "Research Context",
            RESEARCH.get(
                "Research Context"
            ),
        ),
        (
            "AAII",
            None,
        ),
        (
            "VIX",
            None,
        ),
    ]

    for label, df in sentiment_datasets:

        if label == "Research Context":

            if df is not None:

                sentiment_columns = [
                    c
                    for c in df.columns
                    if any(
                        word in c.lower()
                        for word in [
                            "sentiment",
                            "vix",
                            "aaii",
                            "fear",
                            "greed",
                        ]
                    )
                ]

                if sentiment_columns:

                    st.markdown(
                        "### Sentiment fields"
                    )

                    latest = df.iloc[-1]

                    rows = [
                        [
                            friendly_name(c),
                            format_value(
                                latest.get(c)
                            ),
                        ]
                        for c in sentiment_columns
                    ]

                    st.dataframe(
                        pd.DataFrame(
                            rows,
                            columns=[
                                "Indicator",
                                "Latest",
                            ],
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

        elif label in RESEARCH:

            display_research_dataset(
                df,
                label,
            )

    st.info(
        "Sentiment observations are displayed as research evidence. "
        "They are not transformed into a directional signal."
    )


# ============================================================
# TECHNICAL
# ============================================================

elif page == "Technical":

    st.subheader(
        "Technical Intelligence"
    )

    df = RESEARCH.get(
        "Technical"
    )

    display_research_dataset(
        df,
        "Technical Intelligence",
    )

    if df is not None:

        date_col = find_column(
            df,
            [
                "date",
                "asof_date",
                "context_date",
            ],
        )

        numeric = numeric_columns(
            df
        )

        if date_col and numeric:

            chart_df = df.copy()

            chart_df[date_col] = pd.to_datetime(
                chart_df[date_col],
                errors="coerce",
            )

            chart_df = (
                chart_df
                .dropna(
                    subset=[
                        date_col
                    ]
                )
                .tail(500)
                .set_index(
                    date_col
                )
            )

            selected = numeric[:6]

            chart_df[
                selected
            ] = chart_df[
                selected
            ].apply(
                pd.to_numeric,
                errors="coerce",
            )

            st.markdown(
                "### Technical Research History"
            )

            st.line_chart(
                chart_df[
                    selected
                ],
                use_container_width=True,
            )


# ============================================================
# HISTORICAL EDGE
# ============================================================

elif page == "Historical Edge":

    st.subheader(
        "Historical Edge Finder"
    )

    st.caption(
        "Historical analogues and observed outcomes from completed "
        "research. This is a distributional research view, not a forecast."
    )

    df = RESEARCH.get(
        "Historical Edge"
    )

    if df is None:

        df = RESEARCH.get(
            "Historical Edge v1"
        )

    if df is None:

        st.warning(
            "Historical Event Study artifact is not currently available."
        )

    else:

        st.metric(
            "Historical Observations",
            f"{len(df):,}",
        )

        st.write("")

        columns = df.columns.tolist()

        outcome_columns = [
            c
            for c in columns
            if any(
                word in c.lower()
                for word in [
                    "return",
                    "mfe",
                    "mae",
                    "recovery",
                    "drawdown",
                    "horizon",
                    "forward",
                    "outcome",
                ]
            )
        ]

        if outcome_columns:

            st.markdown(
                "### Historical Outcome Fields"
            )

            latest = df.iloc[-1]

            rows = [
                [
                    friendly_name(c),
                    format_value(
                        latest.get(c)
                    ),
                ]
                for c in outcome_columns[:20]
            ]

            st.dataframe(
                pd.DataFrame(
                    rows,
                    columns=[
                        "Historical Field",
                        "Observed Value",
                    ],
                ),
                use_container_width=True,
                hide_index=True,
            )

        st.markdown(
            "### Historical Distribution"
        )

        numeric = numeric_columns(
            df
        )

        selected = [
            c
            for c in numeric
            if any(
                word in c.lower()
                for word in [
                    "return",
                    "mfe",
                    "mae",
                ]
            )
        ][:6]

        if selected:

            plot_df = df[
                selected
            ].copy()

            plot_df = plot_df.apply(
                pd.to_numeric,
                errors="coerce",
            )

            st.line_chart(
                plot_df.tail(300),
                use_container_width=True,
            )

        with st.expander(
            "Inspect historical research sample"
        ):

            st.dataframe(
                df.tail(100),
                use_container_width=True,
                hide_index=True,
            )


# ============================================================
# EVENT STUDIES
# ============================================================

elif page == "Event Studies":

    st.subheader(
        "Event Study Research"
    )

    datasets = [
        (
            "Historical Edge",
            RESEARCH.get(
                "Historical Edge"
            ),
        ),
        (
            "Event News",
            RESEARCH.get(
                "Event News"
            ),
        ),
        (
            "Earnings",
            RESEARCH.get(
                "Earnings"
            ),
        ),
    ]

    for label, df in datasets:

        st.markdown(
            f"### {label}"
        )

        display_research_dataset(
            df,
            label,
        )

    st.info(
        "Event-study results describe historical observations "
        "and distributions. They do not establish a deterministic "
        "future outcome."
    )


# ============================================================
# CROSS ASSET
# ============================================================

elif page == "Cross-Asset":

    st.subheader(
        "Cross-Asset Intelligence"
    )

    df = RESEARCH.get(
        "Cross Asset"
    )

    display_research_dataset(
        df,
        "Cross-Asset Intelligence",
    )

    if df is not None:

        numeric = numeric_columns(
            df
        )

        if numeric:

            selected = numeric[:8]

            chart_df = df[
                selected
            ].copy()

            chart_df = chart_df.apply(
                pd.to_numeric,
                errors="coerce",
            )

            st.markdown(
                "### Cross-Asset Research History"
            )

            st.line_chart(
                chart_df.tail(300),
                use_container_width=True,
            )


# ============================================================
# EARNINGS
# ============================================================

elif page == "Earnings":

    st.subheader(
        "Corporate Earnings Intelligence"
    )

    df = RESEARCH.get(
        "Earnings"
    )

    display_research_dataset(
        df,
        "Earnings Market Reaction V3",
    )

    if df is not None:

        horizon_columns = [
            c
            for c in df.columns
            if any(
                word in c.lower()
                for word in [
                    "1d",
                    "3d",
                    "5d",
                    "20d",
                    "1m",
                    "3m",
                    "mfe",
                    "mae",
                ]
            )
        ]

        if horizon_columns:

            st.markdown(
                "### Earnings Reaction Fields"
            )

            latest = df.iloc[-1]

            rows = [
                [
                    friendly_name(
                        column
                    ),
                    format_value(
                        latest.get(column)
                    ),
                ]
                for column in horizon_columns[:25]
            ]

            st.dataframe(
                pd.DataFrame(
                    rows,
                    columns=[
                        "Field",
                        "Observed Result",
                    ],
                ),
                use_container_width=True,
                hide_index=True,
            )

    st.info(
        "Earnings research summarizes historical market reactions "
        "around corporate reporting events."
    )


# ============================================================
# EVIDENCE
# ============================================================

elif page == "Evidence":

    st.subheader(
        "Evidence Desk"
    )

    st.caption(
        "A compact explanation of what the research stack currently contains."
    )

    evidence_sources = [
        (
            "Macro",
            "Economic Intelligence and Macro Context research.",
            "Macro Context" in RESEARCH,
        ),
        (
            "Financial Stress",
            "VIX, NFCI/ANFCI and yield-curve stress research.",
            "Financial Stress" in RESEARCH,
        ),
        (
            "Sentiment",
            "Sentiment observations incorporated into the unified research context.",
            context is not None,
        ),
        (
            "Technical",
            "Technical structure and market-state observations.",
            "Technical" in RESEARCH,
        ),
        (
            "Historical",
            "Historical event-study distributions and observed outcomes.",
            (
                "Historical Edge" in RESEARCH
                or "Historical Edge v1" in RESEARCH
            ),
        ),
        (
            "Cross-Asset",
            "Relationships across relevant market assets.",
            "Cross Asset" in RESEARCH,
        ),
        (
            "Earnings",
            "Historical corporate earnings reaction research.",
            "Earnings" in RESEARCH,
        ),
    ]

    for (
        name,
        description,
        available,
    ) in evidence_sources:

        status = (
            "AVAILABLE"
            if available
            else "NOT CURRENTLY AVAILABLE"
        )

        evidence_card(
            name,
            f"{description}  Status: {status}.",
        )

    st.markdown(
        "### Research Interpretation"
    )

    evidence_card(
        "Current State",
        "The dashboard displays the latest available research observations "
        "without converting them into an executable market decision.",
    )

    evidence_card(
        "Historical Evidence",
        "Historical event studies are shown as observed distributions, "
        "including forward outcomes, MFE/MAE and recovery characteristics "
        "where those fields exist.",
    )

    evidence_card(
        "Point-in-Time Discipline",
        "The application preserves the point-in-time fields supplied by "
        "the research artifacts instead of reconstructing unavailable "
        "information inside the dashboard.",
    )

    evidence_card(
        "Architecture Boundary",
        "The visualization layer does not create trading signals, "
        "forecasts, position sizing or execution instructions.",
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.markdown(
    """
    <div class="footer">
        US500 Macro Intelligence · Research Terminal<br>
        Research-only visualization layer ·
        No trading signals · No forecasting · No execution
    </div>
    """,
    unsafe_allow_html=True,
)
