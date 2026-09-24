#!/usr/bin/env python3

"""
US500 MACRO INTELLIGENCE
RESEARCH TERMINAL

Research-only visualization layer.

IMPORTANT
---------
This application:
- does NOT generate trading signals
- does NOT generate market forecasts
- does NOT execute trades
- does NOT provide position sizing
- does NOT provide SL/TP
- does NOT provide directional recommendations

It visualizes existing research artifacts produced by
the US500 Macro Intelligence GitHub repository.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st
import yfinance as yf


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

APP_TITLE = "US500 Research Terminal"
APP_VERSION = "4.1"

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
# EXACT ARTIFACT CONTRACTS
# ============================================================

DATASETS: Dict[str, Dict[str, Any]] = {

    "Research Context": {
        "artifact": "research-context-v1",
        "files": [
            "research_context_v1.csv",
            "research_context_summary_v1.csv",
            "research_context_extremes_v1.csv",
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
            "financial_stress_research_summary_v1.csv",
        ],
    },

    "Liquidity": {
        "artifact": "liquidity-intelligence-v1",
        "files": [
            "liquidity_intelligence_research_v1.csv",
            "liquidity_intelligence_summary_v1.csv",
        ],
    },

    "AAII Sentiment": {
        "artifact": "aaii-sentiment-v1",
        "files": [
            "aaii_sentiment_research_v1.csv",
            "aaii_sentiment_research_summary_v1.csv",
            "aaii_sentiment_extremes_v1.csv",
        ],
    },

    "COT Positioning": {
        "artifact": "cot-positioning-v1",
        "files": [
            "cot_positioning_research_v1.csv",
            "cot_positioning_research_summary_v1.csv",
            "cot_positioning_extremes_v1.csv",
        ],
    },

    "VIX Sentiment": {
        "artifact": "vix-sentiment-v1",
        "files": [
            "vix_sentiment_research_v1.csv",
            "vix_sentiment_research_summary_v1.csv",
            "vix_sentiment_extremes_v1.csv",
        ],
    },

    "Technical": {
        "artifact": "technical-intelligence-v1",
        "files": [
            "technical_intelligence_research_v1.csv",
            "technical_intelligence_research_summary_v1.csv",
            "technical_intelligence_extremes_v1.csv",
        ],
    },

    "Market Breadth": {
        "artifact": "market-breadth-full-validation-v1",
        "files": [
            "market_breadth_analysis_v1.csv",
            "market_breadth_historical_v1.csv",
        ],
    },

    "Event News": {
        "artifact": "event-news-intelligence-v2.1",
        "files": [
            "event_news_research_v2.csv",
            "event_news_research_summary_v2.json",
        ],
    },

    "Cross-Asset": {
        "artifact": "cross-asset-intelligence-v1",
        "files": [
            "cross_asset_research_v1.csv",
            "cross_asset_summary_v1.json",
        ],
    },

    "Earnings": {
        "artifact": "earnings-market-reaction-v3-results",
        "files": [
            "earnings_market_reaction_v3.csv",
            "earnings_market_reaction_summary_v3.csv",
            "earnings_reaction_by_eps_class_v3.csv",
            "earnings_reaction_by_sector_v3.csv",
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
# STREAMLIT CONFIG
# ============================================================

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# STYLE
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

.status-ok {
    color: #9bc5a8;
}

.status-warning {
    color: #d7bd82;
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
# GITHUB TOKEN
# ============================================================

def get_github_token() -> Optional[str]:
    """
    Read GITHUB_TOKEN from Streamlit Secrets first,
    then environment variables.

    Never display the token.
    """

    token = None

    try:
        token = st.secrets.get(
            "GITHUB_TOKEN",
            None,
        )
    except Exception:
        token = None

    if not token:
        token = os.getenv(
            "GITHUB_TOKEN",
            "",
        )

    if token is None:
        return None

    token = str(token).strip()

    invalid_values = {
        "",
        "YOUR_GITHUB_TOKEN",
        "YOUR_GITHUB_PAT",
        "GITHUB_TOKEN",
        "YOUR_TOKEN",
        "your_github_token",
        "your_github_pat",
        "PASTE_TOKEN_HERE",
    }

    if token in invalid_values:
        return None

    return token


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
            "US500-Research-Terminal",
    }

    token = get_github_token()

    if token:
        headers["Authorization"] = (
            f"Bearer {token}"
        )

    return headers


# ============================================================
# GITHUB API GET
# ============================================================

def github_get(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 60,
) -> requests.Response:
    """
    Centralized GitHub API GET.

    Handles authentication failures explicitly.
    """

    token = get_github_token()

    response = requests.get(
        url,
        headers=github_headers(),
        params=params,
        timeout=timeout,
    )

    if response.status_code == 401:

        if token:

            raise RuntimeError(
                "GitHub authentication failed (HTTP 401). "
                "The configured GITHUB_TOKEN is invalid, "
                "expired, revoked, or unavailable to this app."
            )

        raise RuntimeError(
            "GitHub returned HTTP 401 because no valid "
            "GITHUB_TOKEN is configured in Streamlit Secrets."
        )

    if response.status_code == 403:

        raise RuntimeError(
            "GitHub returned HTTP 403 Forbidden. "
            "The token may not have permission to read "
            "GitHub Actions artifacts, or the API rate limit "
            "may have been reached."
        )

    if response.status_code == 404:

        raise RuntimeError(
            "GitHub returned HTTP 404. "
            "The repository or requested artifact is not "
            "accessible with the current credentials."
        )

    response.raise_for_status()

    return response


# ============================================================
# GITHUB AUTH TEST
# ============================================================

@st.cache_data(
    ttl=300,
    show_spinner=False,
)
def test_github_connection() -> Tuple[bool, str]:

    token = get_github_token()

    if not token:

        return (
            False,
            "No GITHUB_TOKEN configured.",
        )

    try:

        response = github_get(
            f"{GITHUB_API}/actions/artifacts",
            params={
                "per_page": 1,
                "page": 1,
            },
            timeout=30,
        )

        if response.ok:

            return (
                True,
                "GitHub API authentication successful.",
            )

    except Exception as error:

        return (
            False,
            str(error),
        )

    return (
        False,
        "Unknown GitHub API error.",
    )


# ============================================================
# ARTIFACT DISCOVERY
# ============================================================

@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False,
)
def get_artifacts() -> Dict[str, Dict[str, Any]]:
    """
    Discover current artifacts dynamically.

    IMPORTANT:
    No hard-coded artifact IDs are used.

    If multiple artifacts have the same name, the newest
    non-expired artifact is selected.
    """

    artifacts: Dict[str, Dict[str, Any]] = {}

    for page in range(1, 11):

        response = github_get(
            f"{GITHUB_API}/actions/artifacts",
            params={
                "per_page": 100,
                "page": page,
            },
            timeout=30,
        )

        payload = response.json()

        page_items = payload.get(
            "artifacts",
            [],
        )

        for artifact in page_items:

            if artifact.get("expired"):
                continue

            name = artifact.get("name")

            if not name:
                continue

            current = artifacts.get(name)

            if current is None:

                artifacts[name] = artifact

            else:

                current_time = str(
                    current.get(
                        "created_at",
                        "",
                    )
                )

                new_time = str(
                    artifact.get(
                        "created_at",
                        "",
                    )
                )

                if new_time > current_time:

                    artifacts[name] = artifact

        if len(page_items) < 100:
            break

    return artifacts


# ============================================================
# FIND LATEST ARTIFACT
# ============================================================

def get_latest_artifact(
    artifact_name: str,
) -> Optional[Dict[str, Any]]:

    artifacts = get_artifacts()

    artifact = artifacts.get(
        artifact_name
    )

    return artifact


# ============================================================
# DOWNLOAD ARTIFACT
# ============================================================

@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False,
)
def download_artifact(
    artifact_name: str,
) -> bytes:
    """
    Download the latest artifact by NAME.

    The artifact ID is obtained dynamically from GitHub.
    """

    artifact = get_latest_artifact(
        artifact_name
    )

    if not artifact:

        raise FileNotFoundError(
            "GitHub Actions artifact not found: "
            f"{artifact_name}"
        )

    artifact_id = artifact.get(
        "id"
    )

    if not artifact_id:

        raise RuntimeError(
            "Artifact was found but GitHub did not "
            "return an artifact ID."
        )

    url = (
        f"{GITHUB_API}/actions/artifacts/"
        f"{artifact_id}/zip"
    )

    response = github_get(
        url,
        timeout=90,
    )

    content_type = (
        response.headers.get(
            "content-type",
            "",
        )
        .lower()
    )

    if not response.content:

        raise RuntimeError(
            "GitHub returned an empty artifact archive."
        )

    return response.content


# ============================================================
# ARTIFACT ZIP FILE
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

    try:

        with zipfile.ZipFile(
            io.BytesIO(raw)
        ) as archive:

            names = archive.namelist()

            # Exact match first.
            for name in names:

                if name == filename:

                    return archive.read(
                        name
                    )

            # Then basename/suffix match.
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

                if normalized.endswith(
                    filename
                ):

                    return archive.read(
                        name
                    )

    except zipfile.BadZipFile:

        raise RuntimeError(
            f"Artifact '{artifact_name}' "
            "did not return a valid ZIP archive."
        )

    return None


# ============================================================
# CSV LOADER
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

    try:

        return pd.read_csv(
            io.BytesIO(content)
        )

    except Exception as error:

        raise RuntimeError(
            f"Unable to read '{filename}' "
            f"from artifact '{artifact_name}': "
            f"{error}"
        )


# ============================================================
# JSON LOADER
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

    try:

        return json.loads(
            content.decode(
                "utf-8"
            )
        )

    except Exception as error:

        raise RuntimeError(
            f"Unable to read JSON file "
            f"'{filename}': {error}"
        )


# ============================================================
# MARKET DATA
# ============================================================

@st.cache_data(
    ttl=MARKET_CACHE_TTL,
    show_spinner=False,
)
def get_market_data() -> pd.DataFrame:

    try:

        return yf.download(
            US500_TICKER,
            period="6mo",
            interval="1d",
            auto_adjust=False,
            progress=False,
        )

    except Exception:

        return pd.DataFrame()


# ============================================================
# NUMERIC HELPERS
# ============================================================

def numeric(
    value: Any,
) -> Optional[float]:

    try:

        result = float(value)

        if np.isfinite(result):

            return result

    except Exception:
        pass

    return None


def format_number(
    value: Any,
    decimals: int = 2,
) -> str:

    number = numeric(
        value
    )

    if number is None:

        return "N/A"

    return f"{number:,.{decimals}f}"


# ============================================================
# COLUMN HELPERS
# ============================================================

def find_column(
    df: pd.DataFrame,
    candidates,
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
            str(candidate)
            .strip()
            .lower()
        )

        if found is not None:

            return found

    return None


# ============================================================
# LATEST ROW
# ============================================================

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
            "date",
            "context_date",
            "reported_date",
            "event_date",
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

            valid_dates = dates.loc[
                valid
            ]

            index = valid_dates.idxmax()

            return df.loc[
                index
            ]

    return df.iloc[-1]


# ============================================================
# ROW DATE
# ============================================================

def row_date(
    row: pd.Series,
) -> str:

    if row is None or row.empty:

        return "N/A"

    for column in [
        "asof_date",
        "date",
        "context_date",
        "reported_date",
        "event_date",
        "timestamp",
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


# ============================================================
# ROW VALUE
# ============================================================

def row_value(
    row: pd.Series,
    candidates,
) -> str:

    if row is None or row.empty:

        return "N/A"

    lower_map = {
        str(column).lower():
            column
        for column in row.index
    }

    for candidate in candidates:

        actual = lower_map.get(
            str(candidate).lower()
        )

        if actual is None:

            continue

        value = row[actual]

        try:

            if pd.isna(value):

                continue

        except Exception:

            pass

        text = str(
            value
        ).strip()

        if text.lower() in {
            "",
            "nan",
            "none",
            "nat",
        }:

            continue

        return text

    return "N/A"


# ============================================================
# SAFE ROW JSON
# ============================================================

def safe_row_dict(
    row: pd.Series,
) -> Dict[str, str]:

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
# METRIC CARD
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


# ============================================================
# RESEARCH BOUNDARY
# ============================================================

def research_boundary():

    st.markdown(
        """
        <div class="research-note">
        <strong>Research-only terminal.</strong><br>
        This interface presents current-state evidence,
        historical distributions, research classifications,
        historical analogues and risk factors.
        It does not generate trading signals, forecasts,
        execution instructions, position sizing or SL/TP.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# DATAFRAME DISPLAY
# ============================================================

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


# ============================================================
# PLOT RESEARCH
# ============================================================

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

                numeric_series = pd.to_numeric(
                    df[column],
                    errors="coerce",
                )

                if numeric_series.notna().any():

                    columns.append(
                        column
                    )

    if not columns:

        numeric_columns = []

        for column in df.columns:

            series = pd.to_numeric(
                df[column],
                errors="coerce",
            )

            if series.notna().any():

                numeric_columns.append(
                    column
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
            "timestamp",
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

    for column in columns:

        plot_df[column] = pd.to_numeric(
            plot_df[column],
            errors="coerce",
        )

    plot_df = plot_df[
        columns
    ].dropna(
        how="all"
    ).tail(500)

    if plot_df.empty:

        return

    st.markdown(
        f"""
        <div class="section-title">
            {title}
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.line_chart(
        plot_df,
        use_container_width=True,
    )


# ============================================================
# LOAD DATASET
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

        try:

            dataframe = load_csv_artifact(
                artifact,
                filename,
            )

            if not dataframe.empty:

                return dataframe

        except Exception:

            continue

    return pd.DataFrame()


# ============================================================
# MARKET SNAPSHOT
# ============================================================

def market_snapshot():

    market = get_market_data()

    price = None
    daily_change = None

    if market.empty:

        return price, daily_change

    try:

        close = market[
            "Close"
        ]

        if isinstance(
            close,
            pd.DataFrame,
        ):

            close = close.iloc[:, 0]

        close = pd.to_numeric(
            close,
            errors="coerce",
        ).dropna()

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
                    current /
                    previous - 1
                ) * 100

    except Exception:

        pass

    return price, daily_change


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

    price, daily_change = market_snapshot()

    context = load_dataset(
        "Research Context"
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

    stress_row = latest_row(
        stress
    )

    sentiment_row = latest_row(
        sentiment
    )

    technical_row = latest_row(
        technical
    )

    columns = st.columns(5)

    with columns[0]:

        note = US500_TICKER

        if daily_change is not None:

            note += (
                f" · {daily_change:+.2f}%"
            )

        metric_card(
            "US500 Proxy",
            format_number(
                price
            ),
            note,
        )

    with columns[1]:

        metric_card(
            "Research Update",
            row_date(
                context_row
            ),
            "latest unified context",
        )

    with columns[2]:

        metric_card(
            "Macro State",
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
            "Financial Stress",
            row_value(
                stress_row,
                [
                    "research_regime",
                    "RESEARCH_REGIME",
                    "financial_stress_regime",
                    "stress_regime",
                ],
            ),
            row_date(
                stress_row
            ),
        )

    with columns[4]:

        metric_card(
            "Technical State",
            row_value(
                technical_row,
                [
                    "technical_regime",
                    "research_regime",
                    "trend_regime",
                ],
            ),
            row_date(
                technical_row
            ),
        )

    st.markdown(
        "### Research Snapshot"
    )

    left, right = st.columns(2)

    with left:

        st.markdown(
            "#### Current Context"
        )

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

        st.markdown(
            "#### Sentiment Context"
        )

        if not sentiment_row.empty:

            st.dataframe(
                sentiment_row.to_frame(
                    "value"
                ),
                use_container_width=True,
            )

        else:

            st.info(
                "Sentiment research unavailable."
            )

    if not stress.empty:

        plot_research(
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

def render_market_regime():

    st.title(
        "Market Regime"
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

    columns = st.columns(4)

    values = [
        (
            "Context Date",
            row_date(row),
        ),
        (
            "Macro",
            row_value(
                row,
                [
                    "macro_economic_regime",
                    "economic_regime",
                    "macro_regime",
                ],
            ),
        ),
        (
            "Sentiment",
            row_value(
                row,
                [
                    "sentiment_regime",
                    "sentiment_research_regime",
                ],
            ),
        ),
        (
            "Technical",
            row_value(
                row,
                [
                    "technical_regime",
                    "technical_technical_regime",
                ],
            ),
        ),
    ]

    for column, (
        label,
        value,
    ) in zip(
        columns,
        values,
    ):

        with column:

            metric_card(
                label,
                value,
                "research state",
            )

    st.markdown(
        "### Current Unified Research Record"
    )

    st.dataframe(
        row.to_frame(
            "value"
        ),
        use_container_width=True,
    )

    st.markdown(
        "### Context History"
    )

    plot_research(
        context,
        title="Unified Research Context",
    )


# ============================================================
# MACRO
# ============================================================

def render_macro():

    st.title(
        "Macro"
    )

    research_boundary()

    df = load_dataset(
        "Macro"
    )

    if df.empty:

        st.warning(
            "Macro Context artifact unavailable."
        )

        return

    row = latest_row(
        df
    )

    columns = st.columns(4)

    with columns[0]:

        metric_card(
            "Date",
            row_date(row),
        )

    with columns[1]:

        metric_card(
            "Economic Regime",
            row_value(
                row,
                [
                    "macro_economic_regime",
                    "economic_regime",
                    "macro_regime",
                ],
            ),
        )

    with columns[2]:

        metric_card(
            "Financial Stress",
            row_value(
                row,
                [
                    "financial_stress_regime",
                    "stress_regime",
                ],
            ),
        )

    with columns[3]:

        metric_card(
            "Research State",
            row_value(
                row,
                [
                    "research_regime",
                    "macro_regime",
                ],
            ),
        )

    plot_research(
        df,
        title="Macro Research History",
    )

    with st.expander(
        "Latest Macro Research Record",
        expanded=True,
    ):

        st.json(
            safe_row_dict(row),
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
            if fed.get("fed_score") is not None
            else phase.get("fed_score")
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
        )

    st.markdown(
        "### FOMC & Fed Communications"
    )

    communication_keys = [
        "fomc_statement",
        "fomc_minutes",
        "press_conference",
        "fed_chair_statement",
    ]

    found = False

    for key in communication_keys:

        value = (
            fed.get(key)
            if key in fed
            else phase.get(key)
        )

        if value is None:

            continue

        found = True

        st.markdown(
            f"#### {key.replace('_', ' ').title()}"
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

    if not found:

        st.info(
            "No separate FOMC communication fields were found."
        )

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
            "SEP data is not available."
        )

    if beige:

        st.markdown(
            "### Beige Book / Analysis"
        )

        st.json(
            beige,
            expanded=False,
        )

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

    row = latest_row(
        df
    )

    columns = st.columns(5)

    with columns[0]:

        value = row_value(
            row,
            [
                "composite_stress_score",
                "FINANCIAL_STRESS_COMPOSITE",
            ],
        )

        metric_card(
            "Composite Stress",
            value,
            row_date(row),
        )

    with columns[1]:

        metric_card(
            "VIX",
            format_number(
                row_value(
                    row,
                    ["VIX"],
                )
            ),
            row_date(row),
        )

    with columns[2]:

        metric_card(
            "10Y - 2Y",
            format_number(
                row_value(
                    row,
                    [
                        "YIELD_10Y_2Y_SPREAD",
                        "YIELD_CURVE",
                    ],
                )
            ),
            row_date(row),
        )

    with columns[3]:

        metric_card(
            "NFCI",
            format_number(
                row_value(
                    row,
                    ["NFCI"],
                )
            ),
            row_date(row),
        )

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

    row = latest_row(
        df
    )

    st.write(
        f"Latest research record: "
        f"**{row_date(row)}**"
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
            safe_row_dict(row),
            expanded=False,
        )

    show_dataframe(
        df,
        100,
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

    for tab, page_name in zip(
        tabs,
        pages,
    ):

        with tab:

            df = load_dataset(
                page_name
            )

            if df.empty:

                st.warning(
                    f"{page_name} artifact unavailable."
                )

                continue

            row = latest_row(
                df
            )

            st.write(
                f"Latest record: "
                f"**{row_date(row)}**"
            )

            plot_research(
                df,
                title=f"{page_name} History",
            )

            with st.expander(
                "Latest Research Record"
            ):

                st.json(
                    safe_row_dict(row),
                    expanded=False,
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
        "Technical"
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

    row = latest_row(
        df
    )

    st.write(
        f"Latest research record: "
        f"**{row_date(row)}**"
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
            safe_row_dict(row),
            expanded=False,
        )

    show_dataframe(
        df,
        100,
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

    row = latest_row(
        df
    )

    st.write(
        f"Latest research record: "
        f"**{row_date(row)}**"
    )

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

    with st.expander(
        "Latest Breadth Record"
    ):

        st.json(
            safe_row_dict(row),
            expanded=False,
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
        "are displayed descriptively. They are not converted "
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

    if not event_news.empty:

        plot_research(
            event_news,
            title="Event News Research History",
        )

        show_dataframe(
            event_news,
            100,
        )

    else:

        st.warning(
            "Event News artifact unavailable."
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

    row = latest_row(
        df
    )

    metric_card(
        "Latest Record",
        row_date(row),
        "cross-asset research",
    )

    plot_research(
        df,
        title="Cross-Asset Research History",
    )

    with st.expander(
        "Latest Cross-Asset Record"
    ):

        st.json(
            safe_row_dict(row),
            expanded=False,
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

    columns = st.columns(4)

    with columns[0]:

        metric_card(
            "Research Events",
            f"{len(df):,}",
        )

    with columns[1]:

        metric_card(
            "Latest Date",
            row_date(
                latest_row(df)
            ),
        )

    with columns[2]:

        symbol_column = find_column(
            df,
            [
                "ticker",
                "symbol",
            ],
        )

        unique_symbols = 0

        if symbol_column:

            unique_symbols = (
                df[symbol_column]
                .dropna()
                .nunique()
            )

        metric_card(
            "Symbols",
            str(unique_symbols),
        )

    with columns[3]:

        metric_card(
            "Research Mode",
            "Descriptive",
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
        row.to_frame(
            "value"
        ),
        use_container_width=True,
    )

    st.markdown(
        "### Historical Support"
    )

    historical = load_csv_artifact(
        HISTORICAL_ARTIFACT,
        HISTORICAL_FILES[
            "Summary"
        ],
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

    token = get_github_token()

    if not token:

        st.error(
            "GITHUB_TOKEN is not configured."
        )

        st.info(
            "Add GITHUB_TOKEN to Streamlit Secrets."
        )

        return

    connected, message = (
        test_github_connection()
    )

    if connected:

        st.success(
            message
        )

    else:

        st.error(
            message
        )

        return

    try:

        artifacts = get_artifacts()

    except Exception as error:

        st.error(
            f"GitHub artifact discovery failed: {error}"
        )

        return

    rows = []

    artifact_names = []

    for page_name, specification in DATASETS.items():

        artifact_names.append(
            (
                page_name,
                specification[
                    "artifact"
                ],
            )
        )

    artifact_names.extend(
        [
            (
                "Fed Intelligence",
                FED_ARTIFACT,
            ),
            (
                "Historical Event Study",
                HISTORICAL_ARTIFACT,
            ),
        ]
    )

    for label, artifact_name in artifact_names:

        artifact = artifacts.get(
            artifact_name
        )

        if artifact:

            rows.append(
                {
                    "Dataset": label,
                    "Artifact": artifact_name,
                    "Available": True,
                    "Artifact ID": artifact.get(
                        "id",
                        "",
                    ),
                    "Created": artifact.get(
                        "created_at",
                        "",
                    ),
                    "Updated": artifact.get(
                        "updated_at",
                        "",
                    ),
                    "Expired": artifact.get(
                        "expired",
                        False,
                    ),
                }
            )

        else:

            rows.append(
                {
                    "Dataset": label,
                    "Artifact": artifact_name,
                    "Available": False,
                    "Artifact ID": "",
                    "Created": "",
                    "Updated": "",
                    "Expired": "",
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

except RuntimeError as error:

    st.error(
        f"GitHub/API error: {error}"
    )

    st.info(
        "Check Streamlit Secrets and make sure "
        "GITHUB_TOKEN is a valid GitHub token with "
        "permission to read Actions artifacts."
    )

except requests.HTTPError as error:

    st.error(
        f"GitHub/API error: {error}"
    )

except Exception as error:

    st.error(
        f"Application error: {error}"
    )
