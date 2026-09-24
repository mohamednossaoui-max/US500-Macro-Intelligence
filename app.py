#!/usr/bin/env python3
"""
US500 MACRO INTELLIGENCE
RESEARCH TERMINAL — EDGE FINDER STYLE

Research-only visualization layer.

IMPORTANT:
- No trading signals.
- No market forecasts.
- No trade execution.
- No position sizing.
- No SL/TP.
- No directional recommendations.
- Historical statistics are presented as research evidence only.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

APP_TITLE = "US500 Research Terminal"
APP_VERSION = "4.0"

GITHUB_OWNER = "mohamednossaoui-max"
GITHUB_REPO = "US500-Macro-Intelligence"

GITHUB_API = (
    f"https://api.github.com/repos/"
    f"{GITHUB_OWNER}/{GITHUB_REPO}"
)

US500_TICKER = os.getenv("US500_TICKER", "^GSPC")

CACHE_TTL = 900
MARKET_CACHE_TTL = 300


# ============================================================
# EXACT RESEARCH ARTIFACT CONTRACTS
# ============================================================

DATASETS: Dict[str, Dict[str, Any]] = {

    "Research Context": {
        "artifact": "research-context-v1",
        "files": [
            "research_context_v1.csv",
        ],
    },

    "Macro": {
        "artifact": "macro-context-v1",
        "files": [
            "macro_context_v1.csv",
        ],
    },

    "Financial Stress": {
        "artifact": "financial-stress-research-v1",
        "files": [
            "financial_stress_research_v1.csv",
        ],
    },

    "Liquidity": {
        "artifact": "liquidity-intelligence-v1",
        "files": [
            "liquidity_intelligence_research_v1.csv",
        ],
    },

    "AAII Sentiment": {
        "artifact": "aaii-sentiment-v1",
        "files": [
            "aaii_sentiment_research_v1.csv",
        ],
    },

    "COT Positioning": {
        "artifact": "cot-positioning-v1",
        "files": [
            "cot_positioning_research_v1.csv",
        ],
    },

    "VIX Sentiment": {
        "artifact": "vix-sentiment-v1",
        "files": [
            "vix_sentiment_research_v1.csv",
        ],
    },

    "Technical": {
        "artifact": "technical-intelligence-v1",
        "files": [
            "technical_intelligence_research_v1.csv",
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

    "Cross-Asset": {
        "artifact": "cross-asset-intelligence-v1",
        "files": [
            "cross_asset_research_v1.csv",
        ],
    },

    "Earnings": {
        "artifact": "earnings-market-reaction-v3-results",
        "files": [
            "earnings_market_reaction_v3.csv",
        ],
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
# FED INTELLIGENCE
# ============================================================

FED_ARTIFACT = "fed-intelligence-v1"
FED_FILE = "fed_intelligence_output_v1.json"


# ============================================================
# STREAMLIT CONFIGURATION
# ============================================================

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# DARK FINANCIAL TERMINAL STYLE
# ============================================================

st.markdown(
    """
<style>

.stApp {
    background-color: #0b0f14;
    color: #e6edf3;
}

[data-testid="stSidebar"] {
    background-color: #0d131a;
    border-right: 1px solid #27313a;
}

.block-container {
    padding-top: 1.2rem;
    padding-bottom: 3rem;
    max-width: 1500px;
}

.terminal-title {
    font-size: 2.05rem;
    font-weight: 750;
    letter-spacing: 0.02em;
}

.terminal-subtitle {
    color: #8b98a5;
    margin-bottom: 1.2rem;
}

.section-title {
    margin-top: 1.3rem;
    margin-bottom: 0.7rem;
    font-size: 1.15rem;
    font-weight: 700;
}

.research-note {
    background: #101820;
    border-left: 3px solid #6b7c8c;
    padding: 11px 14px;
    border-radius: 6px;
    color: #b9c4ce;
    margin-bottom: 18px;
}

.metric-card {
    background: #111820;
    border: 1px solid #26313b;
    border-radius: 12px;
    padding: 16px;
    min-height: 110px;
}

.metric-label {
    color: #8b98a5;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.metric-value {
    font-size: 1.48rem;
    font-weight: 700;
    margin-top: 7px;
}

.metric-note {
    color: #8b98a5;
    font-size: 0.78rem;
    margin-top: 5px;
}

.sidebar-note {
    color: #778591;
    font-size: 0.75rem;
}

</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# GITHUB AUTHENTICATION
# ============================================================

def get_github_token() -> str:
    """
    Read GitHub token from Streamlit secrets first,
    then environment variables.
    """

    try:
        token = st.secrets.get(
            "GITHUB_TOKEN",
            "",
        )

        if token:
            return str(token)

    except Exception:
        pass

    return os.getenv(
        "GITHUB_TOKEN",
        "",
    )


def github_headers() -> Dict[str, str]:

    headers = {
        "Accept":
            "application/vnd.github+json",

        "X-GitHub-Api-Version":
            "2022-11-28",
    }

    token = get_github_token()

    if token:
        headers["Authorization"] = (
            f"Bearer {token}"
        )

    return headers


# ============================================================
# GITHUB ACTIONS ARTIFACT DISCOVERY
# ============================================================

@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False,
)
def get_artifacts() -> Dict[str, Dict[str, Any]]:

    artifacts: Dict[str, Dict[str, Any]] = {}

    for page in range(1, 11):

        response = requests.get(
            f"{GITHUB_API}/actions/artifacts",
            headers=github_headers(),
            params={
                "per_page": 100,
                "page": page,
            },
            timeout=30,
        )

        response.raise_for_status()

        payload = response.json()

        for artifact in payload.get(
            "artifacts",
            [],
        ):

            if artifact.get("expired"):
                continue

            name = artifact.get("name")

            if name:
                artifacts[name] = artifact

        page_items = payload.get(
            "artifacts",
            [],
        )

        if len(page_items) < 100:
            break

    return artifacts


# ============================================================
# ARTIFACT DOWNLOAD
# ============================================================

@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False,
)
def download_artifact(
    artifact_name: str,
) -> bytes:

    artifacts = get_artifacts()

    artifact = artifacts.get(
        artifact_name
    )

    if not artifact:

        raise FileNotFoundError(
            "GitHub Actions artifact not found: "
            f"{artifact_name}"
        )

    response = requests.get(
        artifact[
            "archive_download_url"
        ],
        headers=github_headers(),
        timeout=60,
    )

    response.raise_for_status()

    return response.content


# ============================================================
# FILE EXTRACTION FROM ARTIFACT ZIP
# ============================================================

@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False,
)
def artifact_file(
    artifact_name: str,
    filename: str,
) -> Optional[bytes]:

    raw = download_artifact(
        artifact_name
    )

    with zipfile.ZipFile(
        io.BytesIO(raw)
    ) as archive:

        names = archive.namelist()

        exact = None

        for name in names:

            if name == filename:

                exact = name
                break

        if exact is None:

            for name in names:

                if (
                    name.endswith(
                        "/" + filename
                    )
                    or name.endswith(
                        filename
                    )
                ):

                    exact = name
                    break

        if exact is None:
            return None

        return archive.read(exact)


# ============================================================
# CSV ARTIFACT LOADER
# ============================================================

@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False,
)
def load_csv_artifact(
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
# JSON ARTIFACT LOADER
# ============================================================

@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False,
)
def load_json_artifact(
    artifact_name: str,
    filename: str,
) -> Dict[str, Any]:

    content = artifact_file(
        artifact_name,
        filename,
    )

    if content is None:
        return {}

    return json.loads(
        content.decode("utf-8")
    )


# ============================================================
# MARKET DATA
# ============================================================

@st.cache_data(
    ttl=MARKET_CACHE_TTL,
    show_spinner=False,
)
def get_market_data() -> pd.DataFrame:

    return yf.download(
        US500_TICKER,
        period="6mo",
        interval="1d",
        auto_adjust=False,
        progress=False,
    )


# ============================================================
# GENERIC HELPERS
# ============================================================

def numeric(
    value,
) -> Optional[float]:

    try:

        result = float(value)

        if np.isfinite(result):
            return result

    except Exception:
        pass

    return None


def format_number(
    value,
    decimals: int = 2,
) -> str:

    number = numeric(value)

    if number is None:
        return "N/A"

    return f"{number:,.{decimals}f}"


def find_column(
    df: pd.DataFrame,
    candidates,
) -> Optional[str]:

    if df.empty:
        return None

    mapping = {
        str(column).lower(): column
        for column in df.columns
    }

    for candidate in candidates:

        found = mapping.get(
            str(candidate).lower()
        )

        if found:
            return found

    return None


def latest_row(
    df: pd.DataFrame,
) -> pd.Series:

    if df.empty:
        return pd.Series(dtype=object)

    date_column = find_column(
        df,
        [
            "asof_date",
            "date",
            "context_date",
            "reported_date",
            "event_date",
        ],
    )

    if date_column:

        dates = pd.to_datetime(
            df[date_column],
            errors="coerce",
        )

        if dates.notna().any():

            index = dates.idxmax()

            return df.loc[index]

    return df.iloc[-1]


def row_date(
    row: pd.Series,
) -> str:

    for column in [
        "asof_date",
        "date",
        "context_date",
        "reported_date",
        "event_date",
    ]:

        if column not in row.index:
            continue

        value = pd.to_datetime(
            row[column],
            errors="coerce",
        )

        if pd.notna(value):

            return value.strftime(
                "%Y-%m-%d"
            )

    return "N/A"


def row_value(
    row: pd.Series,
    candidates,
) -> str:

    for candidate in candidates:

        if candidate not in row.index:
            continue

        value = row[candidate]

        try:

            if pd.isna(value):
                continue

        except Exception:
            pass

        text = str(value).strip()

        if text in {
            "",
            "nan",
            "None",
            "NaN",
        }:

            continue

        return text

    return "N/A"


# ============================================================
# UI HELPERS
# ============================================================

def metric_card(
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


def research_boundary():

    st.markdown(
        """
        <div class="research-note">

        <strong>Research-only terminal.</strong>

        The terminal presents current-state evidence,
        historical distributions, research classifications,
        analogues and risk factors.

        It does not generate trading signals,
        forecasts, execution instructions,
        position sizing or SL/TP.

        </div>
        """,
        unsafe_allow_html=True,
    )


def show_dataframe(
    df: pd.DataFrame,
    rows: int = 100,
):

    if df.empty:

        st.info(
            "No research artifact data is currently available."
        )

        return

    st.dataframe(
        df.tail(rows),
        use_container_width=True,
        height=430,
    )


def plot_research(
    df: pd.DataFrame,
    preferred_columns=None,
    title: str = "Research history",
):

    if df.empty:
        return

    columns = []

    if preferred_columns:

        for column in preferred_columns:

            if column in df.columns:
                columns.append(column)

    if not columns:

        numeric_columns = list(
            df.select_dtypes(
                include=np.number
            ).columns
        )

        columns = numeric_columns[:4]

    if not columns:
        return

    date_column = find_column(
        df,
        [
            "asof_date",
            "date",
            "context_date",
            "reported_date",
            "event_date",
        ],
    )

    plot_df = df.copy()

    if date_column:

        dates = pd.to_datetime(
            plot_df[date_column],
            errors="coerce",
        )

        valid = dates.notna()

        plot_df = plot_df.loc[
            valid
        ].copy()

        plot_df.index = pd.DatetimeIndex(
            dates.loc[
                plot_df.index
            ]
        )

    st.markdown(
        f"""
        <div class="section-title">
            {title}
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.line_chart(
        plot_df[
            columns
        ].tail(500)
    )


# ============================================================
# DATASET LOADER
# ============================================================

def load_dataset(
    dataset_name: str,
) -> pd.DataFrame:

    specification = DATASETS[
        dataset_name
    ]

    artifact = specification[
        "artifact"
    ]

    for filename in specification[
        "files"
    ]:

        dataframe = load_csv_artifact(
            artifact,
            filename,
        )

        if not dataframe.empty:
            return dataframe

    return pd.DataFrame()


# ============================================================
# OVERVIEW
# ============================================================

def render_overview():

    st.markdown(
        """
        <div class="terminal-title">
            US500 Research Terminal
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="terminal-subtitle">
            Unified view of the project's existing research evidence.
        </div>
        """,
        unsafe_allow_html=True,
    )

    research_boundary()

    # --------------------------------------------------------
    # MARKET DATA
    # --------------------------------------------------------

    market = get_market_data()

    price = None
    daily_change = None

    if not market.empty:

        close = market["Close"]

        if isinstance(
            close,
            pd.DataFrame,
        ):

            close = close.iloc[:, 0]

        close = close.dropna()

        if len(close) >= 1:

            price = numeric(
                close.iloc[-1]
            )

        if len(close) >= 2:

            previous = numeric(
                close.iloc[-2]
            )

            current = numeric(
                close.iloc[-1]
            )

            if (
                previous is not None
                and current is not None
                and previous != 0
            ):

                daily_change = (
                    current / previous - 1
                ) * 100

    # --------------------------------------------------------
    # RESEARCH DATA
    # --------------------------------------------------------

    context = load_dataset(
        "Research Context"
    )

    macro = load_dataset(
        "Macro"
    )

    stress = load_dataset(
        "Financial Stress"
    )

    sentiment = load_dataset(
        "AAII Sentiment"
    )

    technical = load_dataset(
        "Technical"
    )

    context_row = latest_row(
        context
    )

    macro_row = latest_row(
        macro
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

    # --------------------------------------------------------
    # SNAPSHOT CARDS
    # --------------------------------------------------------

    columns = st.columns(5)

    with columns[0]:

        note = US500_TICKER

        if daily_change is not None:

            note += (
                f" · {daily_change:+.2f}%"
            )

        metric_card(
            "US500 proxy",
            format_number(price),
            note,
        )

    with columns[1]:

        metric_card(
            "Research update",
            row_date(context_row),
            "latest unified context",
        )

    with columns[2]:

        metric_card(
            "Macro state",
            row_value(
                context_row,
                [
                    "macro_economic_regime",
                    "economic_regime",
                    "macro_regime",
                ],
            ),
            "research classification",
        )

    with columns[3]:

        metric_card(
            "Financial stress",
            row_value(
                stress_row,
                [
                    "research_regime",
                    "RESEARCH_REGIME",
                    "financial_stress_regime",
                ],
            ),
            "research classification",
        )

    with columns[4]:

        metric_card(
            "Technical state",
            row_value(
                technical_row,
                [
                    "technical_regime",
                    "technical_technical_regime",
                    "research_regime",
                ],
            ),
            "research classification",
        )

    # --------------------------------------------------------
    # CURRENT RESEARCH SNAPSHOT
    # --------------------------------------------------------

    st.markdown(
        """
        <div class="section-title">
            Current Research Snapshot
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns(2)

    with left:

        st.write("### Macro")

        st.write(
            row_value(
                macro_row,
                [
                    "economic_regime",
                    "macro_economic_regime",
                    "macro_regime",
                    "research_regime",
                ],
            )
        )

        st.write("### Sentiment")

        st.write(
            row_value(
                sentiment_row,
                [
                    "research_regime",
                    "sentiment_regime",
                    "regime",
                ],
            )
        )

    with right:

        if not context.empty:

            st.write(
                "### Latest Unified Context Record"
            )

            st.dataframe(
                context_row.to_frame(
                    "value"
                ),
                use_container_width=True,
            )


# ============================================================
# MARKET REGIME
# ============================================================

def render_market_regime():

    st.title(
        "Market Regime"
    )

    research_boundary()

    df = load_dataset(
        "Research Context"
    )

    if df.empty:

        st.warning(
            "Research Context artifact unavailable."
        )

        return

    row = latest_row(df)

    columns = st.columns(4)

    states = [

        (
            "Macro",
            [
                "macro_economic_regime",
                "economic_regime",
                "macro_regime",
            ],
        ),

        (
            "Financial Stress",
            [
                "financial_stress_regime",
                "macro_financial_stress_regime",
                "stress_regime",
            ],
        ),

        (
            "Sentiment",
            [
                "sentiment_research_regime",
                "sentiment_regime",
            ],
        ),

        (
            "Technical",
            [
                "technical_technical_regime",
                "technical_regime",
            ],
        ),
    ]

    for column, (
        label,
        candidates,
    ) in zip(
        columns,
        states,
    ):

        with column:

            metric_card(
                label,
                row_value(
                    row,
                    candidates,
                ),
                row_date(row),
            )

    st.markdown(
        "### Unified Research Context"
    )

    show_dataframe(
        df,
        100,
    )


# ============================================================
# MACRO
# ============================================================

def render_macro():

    st.title(
        "Macro Research"
    )

    research_boundary()

    df = load_dataset(
        "Macro"
    )

    if df.empty:

        st.warning(
            "Macro artifact unavailable."
        )

        return

    row = latest_row(df)

    st.write(
        f"Latest research record: **{row_date(row)}**"
    )

    plot_research(
        df,
        [
            "macro_score",
            "economic_score",
            "growth_score",
            "inflation_score",
            "labor_score",
        ],
        "Macro Research History",
    )

    with st.expander(
        "Latest Macro Record",
        expanded=True,
    ):

        st.json(
            {
                str(key): str(value)
                for key, value in row.items()
                if pd.notna(value)
            },
            expanded=False,
        )


# ============================================================
# FED INTELLIGENCE
# ============================================================

def render_fed_intelligence():

    st.title(
        "Fed Intelligence"
    )

    research_boundary()

    try:

        fed = load_json_artifact(
            FED_ARTIFACT,
            FED_FILE,
        )

    except Exception as error:

        st.error(
            f"Fed Intelligence artifact unavailable: {error}"
        )

        return

    if not fed:

        st.warning(
            "Fed Intelligence artifact is empty or unavailable."
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

    sep_shift = (
        fed.get("sep_shift")
        or {}
    )

    beige = (
        fed.get("beige_book")
        or fed.get("beige_book_analysis")
        or {}
    )

    # --------------------------------------------------------
    # TOP METRICS
    # --------------------------------------------------------

    columns = st.columns(5)

    with columns[0]:

        metric_card(
            "Latest FOMC",
            str(
                fed.get("latest_fomc")
                or phase.get("latest_fomc")
                or "N/A"
            ),
        )

    with columns[1]:

        metric_card(
            "Fed Chair",
            str(
                fed.get("fed_chair")
                or phase.get("fed_chair")
                or "N/A"
            ),
        )

    with columns[2]:

        score = (
            fed.get("fed_score")
            or phase.get("fed_score")
        )

        metric_card(
            "Fed Score",
            format_number(score),
            "research metric",
        )

    with columns[3]:

        metric_card(
            "Fed Classification",
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

    with columns[4]:

        metric_card(
            "Beige Book",
            "Available"
            if beige
            else "N/A",
            "research artifact",
        )

    # --------------------------------------------------------
    # FOMC COMMUNICATIONS
    # --------------------------------------------------------

    st.markdown(
        "### FOMC & Fed Communications"
    )

    communication_keys = [
        "fomc_statement",
        "fomc_minutes",
        "press_conference",
        "fed_chair_statement",
    ]

    found_communications = False

    for key in communication_keys:

        value = (
            fed.get(key)
            if key in fed
            else phase.get(key)
        )

        if value is None:
            continue

        found_communications = True

        st.write(
            f"**{key.replace('_', ' ').title()}**"
        )

        if isinstance(
            value,
            (dict, list),
        ):

            st.json(
                value,
                expanded=False,
            )

        else:

            st.write(value)

    if not found_communications:

        st.info(
            "No separate FOMC communication fields "
            "were found in the artifact."
        )

    # --------------------------------------------------------
    # SEP
    # --------------------------------------------------------

    st.markdown(
        "### Summary of Economic Projections"
    )

    if sep or sep_shift:

        left, right = st.columns(2)

        with left:

            st.write(
                "**Current SEP**"
            )

            st.json(
                sep,
                expanded=False,
            )

        with right:

            st.write(
                "**SEP Shift**"
            )

            st.json(
                sep_shift,
                expanded=False,
            )

    else:

        st.info(
            "SEP data is not available in the current artifact."
        )

    # --------------------------------------------------------
    # BEIGE BOOK
    # --------------------------------------------------------

    if beige:

        st.markdown(
            "### Beige Book / Analysis"
        )

        st.json(
            beige,
            expanded=False,
        )

    # --------------------------------------------------------
    # FED DIMENSIONS
    # --------------------------------------------------------

    if phase:

        st.markdown(
            "### Fed Intelligence Dimensions"
        )

        st.json(
            phase,
            expanded=False,
        )

    # --------------------------------------------------------
    # FULL ARTIFACT
    # --------------------------------------------------------

    with st.expander(
        "Full Fed Intelligence Artifact"
    ):

        st.json(
            fed,
            expanded=False,
        )


# ============================================================
# FINANCIAL STRESS
# ============================================================

def render_financial_stress():

    st.title(
        "Financial Stress"
    )

    research_boundary()

    df = load_dataset(
        "Financial Stress"
    )

    if df.empty:

        st.warning(
            "Financial Stress artifact unavailable."
        )

        return

    row = latest_row(df)

    columns = st.columns(5)

    # Composite
    with columns[0]:

        value = row.get(
            "composite_stress_score"
        )

        if value is None:

            value = row.get(
                "FINANCIAL_STRESS_COMPOSITE"
            )

        metric_card(
            "Composite Stress",
            format_number(value),
            row_date(row),
        )

    # VIX
    with columns[1]:

        metric_card(
            "VIX",
            format_number(
                row.get("VIX")
            ),
            row_date(row),
        )

    # Yield Curve
    with columns[2]:

        value = row.get(
            "YIELD_10Y_2Y_SPREAD"
        )

        if value is None:

            value = row.get(
                "YIELD_CURVE"
            )

        metric_card(
            "10Y - 2Y",
            format_number(value),
            row_date(row),
        )

    # NFCI
    with columns[3]:

        metric_card(
            "NFCI",
            format_number(
                row.get("NFCI")
            ),
            row_date(row),
        )

    # Regime
    with columns[4]:

        metric_card(
            "Research Regime",
            row_value(
                row,
                [
                    "research_regime",
                    "RESEARCH_REGIME",
                ],
            ),
            row_date(row),
        )

    plot_research(
        df,
        [
            "composite_stress_score",
            "VIX",
            "NFCI",
            "ANFCI",
            "YIELD_10Y_2Y_SPREAD",
        ],
        "Financial Stress History",
    )

    show_dataframe(
        df,
        100,
    )


# ============================================================
# LIQUIDITY
# ============================================================

def render_liquidity():

    st.title(
        "Liquidity"
    )

    research_boundary()

    df = load_dataset(
        "Liquidity"
    )

    if df.empty:

        st.warning(
            "Liquidity artifact unavailable."
        )

        return

    row = latest_row(df)

    st.write(
        f"Latest research record: **{row_date(row)}**"
    )

    plot_research(
        df,
        title="Liquidity Research History",
    )

    with st.expander(
        "Latest Liquidity Record",
        expanded=True,
    ):

        st.json(
            {
                str(key): str(value)
                for key, value in row.items()
                if pd.notna(value)
            },
            expanded=False,
        )


# ============================================================
# SENTIMENT
# ============================================================

def render_sentiment():

    st.title(
        "Sentiment"
    )

    research_boundary()

    tabs = st.tabs(
        [
            "AAII",
            "COT Positioning",
            "VIX Sentiment",
        ]
    )

    pages = [
        "AAII Sentiment",
        "COT Positioning",
        "VIX Sentiment",
    ]

    for tab, page in zip(
        tabs,
        pages,
    ):

        with tab:

            df = load_dataset(
                page
            )

            if df.empty:

                st.warning(
                    f"{page} artifact unavailable."
                )

                continue

            row = latest_row(df)

            st.write(
                f"Latest record: **{row_date(row)}**"
            )

            plot_research(
                df,
                title=f"{page} History",
            )

            show_dataframe(
                df,
                75,
            )


# ============================================================
# TECHNICAL
# ============================================================

def render_technical():

    st.title(
        "Technical Research"
    )

    research_boundary()

    df = load_dataset(
        "Technical"
    )

    if df.empty:

        st.warning(
            "Technical artifact unavailable."
        )

        return

    row = latest_row(df)

    st.write(
        f"Latest research record: **{row_date(row)}**"
    )

    plot_research(
        df,
        [
            "technical_score",
            "trend_score",
            "momentum_score",
            "volatility_score",
        ],
        "Technical Research History",
    )

    with st.expander(
        "Latest Technical Record",
        expanded=True,
    ):

        st.json(
            {
                str(key): str(value)
                for key, value in row.items()
                if pd.notna(value)
            },
            expanded=False,
        )


# ============================================================
# MARKET BREADTH
# ============================================================

def render_market_breadth():

    st.title(
        "Market Breadth"
    )

    research_boundary()

    df = load_dataset(
        "Market Breadth"
    )

    if df.empty:

        st.warning(
            "Market Breadth artifact unavailable."
        )

        return

    plot_research(
        df,
        [
            "breadth_score",
            "advance_decline",
            "pct_above_200dma",
            "pct_above_50dma",
        ],
        "Market Breadth History",
    )

    show_dataframe(
        df,
        100,
    )


# ============================================================
# HISTORICAL EDGE
# ============================================================

def render_historical_edge():

    st.title(
        "Historical Edge"
    )

    research_boundary()

    st.caption(
        "Historical distributions and event-study evidence "
        "are presented descriptively. They are not converted "
        "into forecasts or trading recommendations."
    )

    for label, filename in HISTORICAL_FILES.items():

        dataframe = load_csv_artifact(
            HISTORICAL_ARTIFACT,
            filename,
        )

        expanded = (
            label == "Summary"
        )

        with st.expander(
            label,
            expanded=expanded,
        ):

            if dataframe.empty:

                st.info(
                    f"{filename} unavailable."
                )

            else:

                show_dataframe(
                    dataframe,
                    150,
                )


# ============================================================
# EVENT STUDIES
# ============================================================

def render_event_studies():

    st.title(
        "Event Studies"
    )

    research_boundary()

    event_news = load_dataset(
        "Event News"
    )

    if event_news.empty:

        st.warning(
            "Event News artifact unavailable."
        )

    else:

        plot_research(
            event_news,
            title="Event News Research History",
        )

        show_dataframe(
            event_news,
            100,
        )

    conditional = load_csv_artifact(
        HISTORICAL_ARTIFACT,
        HISTORICAL_FILES[
            "Conditional Events"
        ],
    )

    if not conditional.empty:

        st.markdown(
            "### Conditional Event Evidence"
        )

        show_dataframe(
            conditional,
            150,
        )


# ============================================================
# CROSS-ASSET
# ============================================================

def render_cross_asset():

    st.title(
        "Cross-Asset"
    )

    research_boundary()

    df = load_dataset(
        "Cross-Asset"
    )

    if df.empty:

        st.warning(
            "Cross-Asset artifact unavailable."
        )

        return

    plot_research(
        df,
        title="Cross-Asset Research History",
    )

    show_dataframe(
        df,
        100,
    )


# ============================================================
# EARNINGS
# ============================================================

def render_earnings():

    st.title(
        "Earnings"
    )

    research_boundary()

    df = load_dataset(
        "Earnings"
    )

    if df.empty:

        st.warning(
            "Earnings artifact unavailable."
        )

        return

    st.metric(
        "Research Events",
        f"{len(df):,}",
    )

    plot_research(
        df,
        [
            "return_1d",
            "return_3d",
            "return_5d",
            "return_20d",
        ],
        "Earnings Market Reaction History",
    )

    show_dataframe(
        df,
        100,
    )


# ============================================================
# EVIDENCE
# ============================================================

def render_evidence():

    st.title(
        "Evidence"
    )

    research_boundary()

    context = load_dataset(
        "Research Context"
    )

    if context.empty:

        st.warning(
            "Research Context artifact unavailable."
        )

        return

    row = latest_row(
        context
    )

    st.markdown(
        "### Current-State Evidence"
    )

    columns = st.columns(4)

    evidence = [

        (
            "Macro",
            [
                "macro_economic_regime",
                "economic_regime",
                "macro_regime",
            ],
        ),

        (
            "Financial Stress",
            [
                "financial_stress_regime",
                "macro_financial_stress_regime",
                "stress_regime",
            ],
        ),

        (
            "Sentiment",
            [
                "sentiment_research_regime",
                "sentiment_regime",
            ],
        ),

        (
            "Technical",
            [
                "technical_technical_regime",
                "technical_regime",
            ],
        ),
    ]

    for column, (
        label,
        candidates,
    ) in zip(
        columns,
        evidence,
    ):

        with column:

            metric_card(
                label,
                row_value(
                    row,
                    candidates,
                ),
                row_date(row),
            )

    st.markdown(
        "### Supporting Research Record"
    )

    st.dataframe(
        row.to_frame("value"),
        use_container_width=True,
    )

    st.markdown(
        "### Historical Support"
    )

    historical = load_csv_artifact(
        HISTORICAL_ARTIFACT,
        HISTORICAL_FILES["Summary"],
    )

    show_dataframe(
        historical,
        100,
    )


# ============================================================
# DATA STATUS
# ============================================================

def render_data_status():

    st.title(
        "Data Status"
    )

    st.caption(
        "Diagnostic view of the exact GitHub Actions "
        "artifacts used by this terminal."
    )

    try:

        artifacts = get_artifacts()

    except Exception as error:

        st.error(
            f"GitHub artifact access failed: {error}"
        )

        return

    rows = []

    for page, specification in DATASETS.items():

        artifact_name = specification[
            "artifact"
        ]

        artifact = artifacts.get(
            artifact_name
        )

        rows.append(
            {
                "Dataset": page,
                "Artifact": artifact_name,
                "Available": bool(artifact),
                "Created": (
                    artifact.get(
                        "created_at",
                        "",
                    )
                    if artifact
                    else ""
                ),
                "Expired": (
                    artifact.get(
                        "expired",
                        False,
                    )
                    if artifact
                    else ""
                ),
            }
        )

    additional_artifacts = [

        (
            "Fed Intelligence",
            FED_ARTIFACT,
        ),

        (
            "Historical Event Study",
            HISTORICAL_ARTIFACT,
        ),
    ]

    for label, artifact_name in additional_artifacts:

        artifact = artifacts.get(
            artifact_name
        )

        rows.append(
            {
                "Dataset": label,
                "Artifact": artifact_name,
                "Available": bool(artifact),
                "Created": (
                    artifact.get(
                        "created_at",
                        "",
                    )
                    if artifact
                    else ""
                ),
                "Expired": (
                    artifact.get(
                        "expired",
                        False,
                    )
                    if artifact
                    else ""
                ),
            }
        )

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
    )


# ============================================================
# NAVIGATION
# ============================================================

PAGES = {

    "Overview":
        render_overview,

    "Market Regime":
        render_market_regime,

    "Macro":
        render_macro,

    "Fed Intelligence":
        render_fed_intelligence,

    "Financial Stress":
        render_financial_stress,

    "Liquidity":
        render_liquidity,

    "Sentiment":
        render_sentiment,

    "Technical":
        render_technical,

    "Market Breadth":
        render_market_breadth,

    "Historical Edge":
        render_historical_edge,

    "Event Studies":
        render_event_studies,

    "Cross-Asset":
        render_cross_asset,

    "Earnings":
        render_earnings,

    "Evidence":
        render_evidence,

    "Data Status":
        render_data_status,
}


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.markdown(
    "## US500 Research Terminal"
)

st.sidebar.caption(
    f"Version {APP_VERSION} · Research-only"
)

page = st.sidebar.radio(
    "Research Sections",
    list(PAGES.keys()),
    index=0,
)

st.sidebar.divider()

st.sidebar.caption(
    f"Market proxy: {US500_TICKER}"
)

st.sidebar.caption(
    "No trading signals"
)

st.sidebar.caption(
    "No forecasts"
)

st.sidebar.caption(
    "No execution"
)


# ============================================================
# APPLICATION ENTRY
# ============================================================

try:

    PAGES[page]()

except requests.HTTPError as error:

    st.error(
        f"GitHub/API error: {error}"
    )

except Exception as error:

    st.error(
        f"Application error: {error}"
    )
