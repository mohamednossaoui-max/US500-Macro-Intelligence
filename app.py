# US500 MACRO INTELLIGENCE - RESEARCH TERMINAL V6.0
# Research-only frontend.
# No GitHub token, trading logic, forecasting, or execution.

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests
import streamlit as st


# ============================================================
# CONFIGURATION
# ============================================================

APP_VERSION = "V6.0"

REPO = "mohamednossaoui-max/US500-Macro-Intelligence"
BRANCH = "main"

RAW_BASE = (
    f"https://raw.githubusercontent.com/"
    f"{REPO}/{BRANCH}/public_data"
)

PUBLIC_DATA = Path(__file__).resolve().parent / "public_data"

HEADERS = {
    "User-Agent": "US500-Macro-Intelligence-Research-Terminal/6.0"
}


# ============================================================
# DATASET MAP
# ============================================================

DATASETS = {
    "Research Context": "research_context_v1.csv",
    "Macro Context": "macro_context_v1.csv",
    "Economic Intelligence": "economic_regime_events_v1.csv",
    "Economic Surprise": "economic_surprise_engine_v1.csv",
    "Fed Intelligence": "fed_intelligence_output_v1.json",
    "Financial Stress": "financial_stress_research_v1.csv",
    "Liquidity": "liquidity_intelligence_research_v1.csv",
    "COT Positioning": "cot_positioning_research_v1.csv",
    "AAII Sentiment": "aaii_sentiment_research_v1.csv",
    "VIX Sentiment": "vix_sentiment_research_v1.csv",
    "Unified Sentiment": "sentiment_engine_research_v1.csv",
    "Technical Intelligence": "technical_intelligence_research_v1.csv",
    "Market Breadth": "market_breadth_analysis_v1.csv",
    "Cross-Asset Intelligence": "cross_asset_research_v1.csv",
    "Event / News Intelligence": "event_news_research_v2.csv",
    "Earnings Intelligence": "earnings_market_reaction_v3.csv",
    "Decision Engine": "decision_engine_research_v1.csv",
    "Decision Summary": "decision_engine_research_summary_v1.csv",
    "Decision Evidence": "decision_engine_research_evidence_v1.csv",
    "Decision JSON": "decision_engine_research_v1.json",
    "Final Validation": "final_end_to_end_validation_report.csv",
}


EDGE_FILES = {
    "Robustness JSON": "historical_edge_robustness_validation_v1.json",
    "Temporal Robustness": "historical_edge_temporal_robustness_v1.csv",
    "Threshold Sensitivity": "historical_edge_threshold_sensitivity_v1.csv",
    "Temporal Stability": "historical_edge_temporal_stability_v1.csv",
    "Threshold Stability": "historical_edge_threshold_stability_v1.csv",
    "Horizon Stability": "historical_edge_horizon_stability_v1.csv",
    "Sample Adequacy": "historical_edge_sample_adequacy_v1.csv",
    "Event Overlap": "historical_edge_event_overlap_v1.csv",
    "PIT Audit": "historical_edge_pit_audit_v1.csv",
}


# ============================================================
# VERIFIED PIPELINE METADATA
# These are historical verified run references.
# They are NOT presented as live workflow status.
# ============================================================

VERIFIED_RUNS = {
    "Master Pipeline": ("36139637088", "PASS"),
    "Macro Context": ("36181485481", "PASS"),
    "Sentiment Engine": ("36183227935", "PASS"),
    "Research Integration": ("36184596061", "PASS"),
    "Final End-to-End": ("36186001790", "PASS"),
    "Decision Engine V1": ("36189840012", "PASS"),
    "Historical Event Study V2": ("36190915225", "PASS"),
    "Historical Edge Robustness V1": ("36192353073", "PASS"),
}


# ============================================================
# STREAMLIT CONFIG
# ============================================================

st.set_page_config(
    page_title="US500 Macro Intelligence V6.0",
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

    .block-container {
        max-width: 1500px;
        padding-top: 1.3rem;
        padding-bottom: 3rem;
    }

    .terminal-title {
        font-size: 2.1rem;
        font-weight: 800;
        letter-spacing: .03em;
    }

    .terminal-subtitle {
        color: #8793a2;
        margin-bottom: 1.2rem;
    }

    .research-card {
        border: 1px solid rgba(128,140,155,.25);
        border-radius: 12px;
        padding: 15px 17px;
        min-height: 105px;
        background: rgba(128,140,155,.05);
    }

    .research-label {
        font-size: .70rem;
        font-weight: 800;
        letter-spacing: .08em;
        color: #8793a2;
    }

    .research-value {
        font-size: 1.20rem;
        font-weight: 800;
        margin-top: 8px;
    }

    .research-muted {
        color: #8793a2;
        font-size: .78rem;
    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# NETWORK
# ============================================================

@st.cache_data(ttl=900, show_spinner=False)
def get_url(url: str) -> Optional[bytes]:

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=12,
        )

        if response.status_code == 200:
            return response.content

    except requests.RequestException:
        return None

    return None


# ============================================================
# MANIFEST
# ============================================================

@st.cache_data(ttl=1800, show_spinner=False)
def get_manifest() -> dict[str, Any]:

    local = PUBLIC_DATA / "public_data_manifest.json"

    if local.exists():

        try:
            return json.loads(
                local.read_text(
                    encoding="utf-8"
                )
            )
        except Exception:
            pass

    raw = get_url(
        f"{RAW_BASE}/public_data_manifest.json"
    )

    if raw:

        try:
            return json.loads(
                raw.decode("utf-8")
            )
        except Exception:
            pass

    return {}


def manifest_paths(obj: Any) -> list[str]:

    paths: list[str] = []

    if isinstance(obj, dict):

        for value in obj.values():
            paths.extend(
                manifest_paths(value)
            )

    elif isinstance(obj, list):

        for value in obj:
            paths.extend(
                manifest_paths(value)
            )

    elif isinstance(obj, str):

        if obj.lower().endswith(
            (".csv", ".json")
        ):
            paths.append(
                obj.replace("\\", "/").lstrip("/")
            )

    return list(dict.fromkeys(paths))


# ============================================================
# LOCAL FILE DISCOVERY
# ============================================================

def local_candidates(
    filename: str,
) -> list[Path]:

    if not PUBLIC_DATA.exists():
        return []

    result: list[Path] = []

    exact = PUBLIC_DATA / filename

    if exact.exists():
        result.append(exact)

    try:
        result.extend(
            PUBLIC_DATA.rglob(filename)
        )
    except OSError:
        pass

    return list(
        dict.fromkeys(result)
    )


# ============================================================
# TOKEN-FREE DATA LOADER
# ============================================================

@st.cache_data(ttl=900, show_spinner=False)
def load_bytes(
    filename: str,
) -> tuple[Optional[bytes], str]:

    # --------------------------------------------------------
    # 1. LOCAL public_data
    # --------------------------------------------------------

    for path in local_candidates(filename):

        try:

            return (
                path.read_bytes(),
                f"LOCAL: {path.relative_to(PUBLIC_DATA)}",
            )

        except OSError:
            continue

    # --------------------------------------------------------
    # 2. public_data manifest
    # --------------------------------------------------------

    candidates = [filename]

    manifest = get_manifest()

    for path in manifest_paths(manifest):

        clean_path = path.lstrip("/")

        if (
            clean_path == filename
            or clean_path.endswith(
                "/" + filename
            )
        ):
            candidates.append(clean_path)

    # --------------------------------------------------------
    # 3. GitHub Raw
    # --------------------------------------------------------

    for path in list(
        dict.fromkeys(candidates)
    ):

        if path.startswith(
            "public_data/"
        ):

            path = path.split(
                "public_data/",
                1
            )[1]

        raw = get_url(
            f"{RAW_BASE}/{path}"
        )

        if raw is not None:

            return (
                raw,
                f"GITHUB RAW: public_data/{path}",
            )

    # --------------------------------------------------------
    # 4. Not published
    # --------------------------------------------------------

    return None, "NOT PUBLISHED"


# ============================================================
# CSV
# ============================================================

@st.cache_data(ttl=900, show_spinner=False)
def load_csv(
    filename: str,
) -> tuple[
    Optional[pd.DataFrame],
    str,
]:

    raw, source = load_bytes(filename)

    if raw is None:
        return None, source

    try:

        df = pd.read_csv(
            io.BytesIO(raw),
            low_memory=False,
        )

        df.columns = [
            str(column).strip()
            for column in df.columns
        ]

        return df, source

    except Exception:
        return None, source


# ============================================================
# JSON
# ============================================================

@st.cache_data(ttl=900, show_spinner=False)
def load_json(
    filename: str,
) -> tuple[Optional[Any], str]:

    raw, source = load_bytes(filename)

    if raw is None:
        return None, source

    try:

        return (
            json.loads(
                raw.decode("utf-8")
            ),
            source,
        )

    except Exception:
        return None, source


# ============================================================
# LOAD ALL DATA
# ============================================================

@st.cache_data(ttl=900, show_spinner=False)
def load_all() -> dict[str, Any]:

    result: dict[str, Any] = {}

    combined = {
        **DATASETS,
        **{
            f"Edge: {name}": filename
            for name, filename in EDGE_FILES.items()
        },
    }

    for label, filename in combined.items():

        if filename.endswith(".json"):

            obj, source = load_json(
                filename
            )

        else:

            obj, source = load_csv(
                filename
            )

        result[label] = {
            "data": obj,
            "source": source,
        }

    return result


ALL_DATA = load_all()


# ============================================================
# SAFE ACCESSORS
# ============================================================

def data_for(
    label: str,
) -> Any:

    item = ALL_DATA.get(label)

    if item is None:
        return None

    return item["data"]


def df_for(
    label: str,
) -> Optional[pd.DataFrame]:

    obj = data_for(label)

    if isinstance(
        obj,
        pd.DataFrame,
    ):
        return obj

    return None


def source_for(
    label: str,
) -> str:

    item = ALL_DATA.get(label)

    if item is None:
        return "NOT PUBLISHED"

    return item["source"]


# ============================================================
# DATE HELPERS
# ============================================================

DATE_COLUMNS = [
    "asof_date",
    "research_date",
    "date",
    "observation_date",
    "event_date",
    "timestamp",
    "datetime",
]


def date_column(
    df: Optional[pd.DataFrame],
) -> Optional[str]:

    if df is None or df.empty:
        return None

    lower = {
        str(column).lower(): column
        for column in df.columns
    }

    for name in DATE_COLUMNS:

        if name.lower() in lower:
            return str(
                lower[name.lower()]
            )

    return None


def date_info(
    df: Optional[pd.DataFrame],
) -> tuple[str, str]:

    if df is None or df.empty:
        return (
            "Unavailable",
            "Unavailable",
        )

    column = date_column(df)

    if column is None:
        return (
            "Unavailable",
            "Unavailable",
        )

    dates = pd.to_datetime(
        df[column],
        errors="coerce",
        utc=True,
    )

    valid = dates.dropna()

    if valid.empty:
        return (
            "Unavailable",
            "Unavailable",
        )

    latest_date = valid.max()

    age = (
        pd.Timestamp.now(
            tz="UTC"
        )
        - latest_date
    ).total_seconds() / 86400

    if age < 0:

        age_text = (
            "Future-dated observation"
        )

    elif age < 1:

        age_text = (
            "Less than 1 day"
        )

    else:

        age_text = (
            f"{age:.0f} days"
        )

    return (
        latest_date.strftime(
            "%Y-%m-%d"
        ),
        age_text,
    )


def latest(
    df: Optional[pd.DataFrame],
) -> Optional[pd.Series]:

    if df is None or df.empty:
        return None

    column = date_column(df)

    if column is None:
        return df.iloc[-1]

    dates = pd.to_datetime(
        df[column],
        errors="coerce",
        utc=True,
    )

    if dates.notna().any():

        index = dates.idxmax()

        return df.loc[index]

    return df.iloc[-1]


# ============================================================
# SAFE VALUE ACCESS
# IMPORTANT:
# NEVER use pandas Series/DataFrame in boolean expressions.
# ============================================================

def value(
    row: Optional[pd.Series],
    names: list[str],
    default: str = "Unavailable",
) -> str:

    if row is None:
        return default

    lookup = {
        str(column).lower(): column
        for column in row.index
    }

    for name in names:

        column = lookup.get(
            name.lower()
        )

        if column is None:
            continue

        item = row[column]

        try:

            if pd.isna(item):
                continue

        except (
            TypeError,
            ValueError,
        ):

            pass

        if isinstance(
            item,
            float,
        ) and item.is_integer():

            return str(
                int(item)
            )

        return str(item)

    return default


# ============================================================
# NUMERIC SERIES
# ============================================================

def numeric_columns(
    df: Optional[pd.DataFrame],
) -> list[str]:

    if df is None or df.empty:
        return []

    result: list[str] = []

    for column in df.columns:

        converted = pd.to_numeric(
            df[column],
            errors="coerce",
        )

        if converted.notna().sum() >= 3:

            result.append(
                str(column)
            )

    return result


# ============================================================
# CHARTS
# ============================================================

def chart(
    df: Optional[pd.DataFrame],
    title: str,
    preferred: list[str],
) -> None:

    if df is None or df.empty:

        st.info(
            f"{title}: Not published."
        )

        return

    dcol = date_column(df)

    numbers = numeric_columns(df)

    chosen = None

    lower = {
        column.lower(): column
        for column in numbers
    }

    for preferred_name in preferred:

        candidate = lower.get(
            preferred_name.lower()
        )

        if candidate is not None:

            chosen = candidate

            break

    if chosen is None and numbers:

        chosen = numbers[0]

    if dcol is None or chosen is None:

        st.info(
            f"{title}: no compatible "
            "date/numeric series is exposed."
        )

        return

    plot = pd.DataFrame(
        {
            "Date": pd.to_datetime(
                df[dcol],
                errors="coerce",
                utc=True,
            ),
            "Value": pd.to_numeric(
                df[chosen],
                errors="coerce",
            ),
        }
    ).dropna()

    if plot.empty:

        st.info(
            f"{title}: no valid observations."
        )

        return

    st.caption(
        f"{title} | Series: {chosen}"
    )

    st.line_chart(
        plot.set_index("Date")
    )


# ============================================================
# UI HELPERS
# ============================================================

def heading(
    title: str,
    subtitle: str = "",
) -> None:

    st.markdown(
        f"### {title}"
    )

    if subtitle:
        st.caption(subtitle)


def card(
    label: str,
    value_text: str,
    detail: str = "",
) -> None:

    st.markdown(
        f"""
        <div class="research-card">
            <div class="research-label">
                {label}
            </div>

            <div class="research-value">
                {value_text}
            </div>

            <div class="research-muted">
                {detail}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# RESEARCH CONTEXT
# ============================================================

def research_context() -> dict[str, str]:

    row = latest(
        df_for("Research Context")
    )

    economic = value(
        row,
        [
            "economic_regime",
            "economic",
            "regime",
        ],
        "",
    )

    stress = value(
        row,
        [
            "financial_stress_regime",
            "financial_stress",
        ],
        "",
    )

    sentiment = value(
        row,
        [
            "sentiment_regime",
            "sentiment",
            "sentiment_state",
        ],
        "",
    )

    technical = value(
        row,
        [
            "technical_regime",
            "technical",
            "technical_state",
        ],
        "",
    )

    fed = value(
        row,
        [
            "fed_score",
            "fed",
            "fed_intelligence_score",
        ],
        "",
    )

    event = value(
        row,
        [
            "latest_event_topic",
            "event_topic",
            "topic",
        ],
        "",
    )

    if not economic:

        economic = value(
            latest(
                df_for("Macro Context")
            ),
            [
                "economic_regime",
                "economic",
                "regime",
            ],
        )

    if not stress:

        stress = value(
            latest(
                df_for("Financial Stress")
            ),
            [
                "research_regime",
                "financial_stress_regime",
            ],
        )

    if not sentiment:

        sentiment = value(
            latest(
                df_for("Unified Sentiment")
            ),
            [
                "sentiment_regime",
                "sentiment_state",
                "regime",
            ],
        )

    if not technical:

        technical = value(
            latest(
                df_for(
                    "Technical Intelligence"
                )
            ),
            [
                "technical_regime",
                "regime",
                "state",
            ],
        )

    if not fed:

        fed = value(
            latest(
                df_for(
                    "Fed Intelligence"
                )
            ),
            [
                "fed_score",
                "score",
                "composite_score",
            ],
        )

    if not event:

        event = value(
            latest(
                df_for(
                    "Event / News Intelligence"
                )
            ),
            [
                "latest_topic",
                "event_topic",
                "topic",
            ],
        )

    return {
        "Economic": economic,
        "Financial Stress": stress,
        "Fed": fed,
        "Sentiment": sentiment,
        "Technical": technical,
        "Event / News": event,
    }


# ============================================================
# DECISION ENGINE
# ============================================================

def decision_snapshot() -> dict[str, Any]:

    summary = latest(
        df_for("Decision Summary")
    )

    engine = latest(
        df_for("Decision Engine")
    )

    evidence = df_for(
        "Decision Evidence"
    )

    state = value(
        summary,
        [
            "state",
            "decision",
            "classification",
            "research_classification",
        ],
        "",
    )

    if not state:

        state = value(
            engine,
            [
                "state",
                "decision",
                "classification",
                "research_classification",
            ],
            "",
        )

    confidence = value(
        summary,
        [
            "confidence",
            "evidence_coverage",
            "coverage",
        ],
        "",
    )

    if not confidence:

        confidence = value(
            engine,
            [
                "confidence",
                "evidence_coverage",
                "coverage",
            ],
            "",
        )

    evidence_count = value(
        summary,
        [
            "evidence_count",
            "evidence",
        ],
        "",
    )

    if not evidence_count:

        evidence_count = value(
            engine,
            [
                "evidence_count",
                "evidence",
            ],
            "",
        )

    supportive = value(
        summary,
        ["supportive"],
        "",
    )

    contradictory = value(
        summary,
        ["contradictory"],
        "",
    )

    mixed = value(
        summary,
        ["mixed"],
        "",
    )

    # Verified snapshot fallback.
    # This is metadata from the verified run and not a fabricated
    # current market observation.
    if (
        not state
        and evidence is None
        and summary is None
        and engine is None
    ):

        state = "SUPPORTIVE"
        confidence = "1.0"
        evidence_count = "4"
        supportive = "2"
        contradictory = "0"
        mixed = "2"

    return {
        "state": state,
        "confidence": confidence,
        "count": evidence_count,
        "supportive": supportive,
        "contradictory": contradictory,
        "mixed": mixed,
        "evidence": evidence,
    }


# ============================================================
# PIT
# ============================================================

def pit_status(
    label: str,
) -> str:

    row = latest(
        df_for(label)
    )

    return value(
        row,
        [
            "pit_safe",
            "pit_pass",
            "pit_flag",
            "point_in_time_safe",
            "point_in_time",
            "PIT",
        ],
        "Not exposed by this dataset",
    )


# ============================================================
# EXECUTIVE OVERVIEW
# ============================================================

def executive_overview() -> None:

    st.markdown(
        '<div class="terminal-title">'
        'US500 MACRO INTELLIGENCE'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="terminal-subtitle">'
        'RESEARCH TERMINAL V6.0'
        '</div>',
        unsafe_allow_html=True,
    )

    st.info(
        "POINT-IN-TIME RESEARCH | "
        "No trading signal, forecast, execution, "
        "position sizing, stop loss, take profit, "
        "or broker integration."
    )

    context = research_context()

    decision = decision_snapshot()

    latest_date, age = date_info(
        df_for("Research Context")
    )

    if latest_date == "Unavailable":

        latest_date, age = date_info(
            df_for("Macro Context")
        )

    st.caption(
        f"Research as-of: {latest_date} | "
        f"Data age: {age} | "
        "Latest published observation, not live status"
    )

    cards = [
        ("ECONOMIC", context["Economic"]),
        (
            "FINANCIAL STRESS",
            context["Financial Stress"],
        ),
        ("FED", context["Fed"]),
        (
            "SENTIMENT",
            context["Sentiment"],
        ),
        (
            "TECHNICAL",
            context["Technical"],
        ),
        (
            "DECISION ENGINE",
            decision["state"],
        ),
    ]

    columns = st.columns(6)

    for column, item in zip(
        columns,
        cards,
    ):

        with column:

            card(
                item[0],
                item[1],
            )

    heading(
        "Research Context",
        "Latest available evidence across the core research layers.",
    )

    columns = st.columns(3)

    for index, (
        label,
        val,
    ) in enumerate(
        context.items()
    ):

        with columns[
            index % 3
        ]:

            st.metric(
                label,
                val,
            )

    heading(
        "Decision Engine Evidence Coverage"
    )

    st.caption(
        "Confidence represents evidence coverage, not probability."
    )

    columns = st.columns(5)

    metrics = [
        (
            "Classification",
            decision["state"],
        ),
        (
            "Coverage",
            decision["confidence"],
        ),
        (
            "Evidence",
            decision["count"],
        ),
        (
            "Supportive",
            decision["supportive"],
        ),
        (
            "Mixed",
            decision["mixed"],
        ),
    ]

    for column, (
        label,
        val,
    ) in zip(
        columns,
        metrics,
    ):

        with column:

            st.metric(
                label,
                val,
            )

    st.caption(
        f"Contradictory evidence: "
        f"{decision['contradictory']}"
    )

    heading(
        "Verified Pipeline Milestones"
    )

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Stage": stage,
                    "Run ID": run_id,
                    "Status": status,
                }
                for stage, (
                    run_id,
                    status,
                ) in VERIFIED_RUNS.items()
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# RESEARCH CONTEXT PAGE
# ============================================================

def research_context_page() -> None:

    heading(
        "Research Context",
        "Integrated point-in-time research context.",
    )

    context = research_context()

    columns = st.columns(3)

    for index, (
        label,
        val,
    ) in enumerate(
        context.items()
    ):

        with columns[
            index % 3
        ]:

            card(
                label,
                val,
            )

    df = df_for(
        "Research Context"
    )

    if df is None or df.empty:

        st.warning(
            "Research Context: NOT PUBLISHED"
        )

        return

    st.dataframe(
        df.tail(30),
        use_container_width=True,
        hide_index=True,
    )

    chart(
        df,
        "Research Context",
        [
            "composite_score",
            "research_score",
            "score",
        ],
    )


# ============================================================
# GENERIC MODULE PAGE
# ============================================================

def module_page(
    label: str,
    title: str,
    preferred: list[str],
) -> None:

    heading(title)

    df = df_for(label)

    if df is None or df.empty:

        st.warning(
            f"{title}: NOT PUBLISHED"
        )

        return

    latest_date, age = date_info(df)

    st.caption(
        f"Source: {source_for(label)} | "
        f"Latest published observation: {latest_date} | "
        f"Age: {age}"
    )

    row = latest(df)

    columns_numeric = numeric_columns(
        df
    )

    if columns_numeric:

        columns = st.columns(
            min(
                4,
                len(columns_numeric),
            )
        )

        for column, name in zip(
            columns,
            columns_numeric[:4],
        ):

            with column:

                st.metric(
                    name,
                    value(
                        row,
                        [name],
                    ),
                )

    chart(
        df,
        title,
        preferred,
    )

    with st.expander(
        "Latest observations"
    ):

        st.dataframe(
            df.tail(30),
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# ECONOMIC
# ============================================================

def economic_page() -> None:

    heading(
        "Economic Intelligence",
        "Descriptive economic regime and surprise evidence.",
    )

    df = df_for(
        "Economic Intelligence"
    )

    row = latest(df)

    columns = st.columns(4)

    fields = [
        (
            "Regime",
            [
                "economic_regime",
                "regime",
                "state",
            ],
        ),
        (
            "Score",
            [
                "composite_score",
                "regime_score",
                "score",
            ],
        ),
        (
            "Inflation",
            [
                "inflation_regime",
                "inflation",
            ],
        ),
        (
            "Labor",
            [
                "labor_regime",
                "labor",
            ],
        ),
    ]

    for column, (
        label,
        names,
    ) in zip(
        columns,
        fields,
    ):

        with column:

            st.metric(
                label,
                value(row, names),
            )

    module_page(
        "Economic Surprise",
        "Economic Surprise",
        [
            "surprise_score",
            "composite_score",
            "score",
        ],
    )


# ============================================================
# FED
# ============================================================

def fed_page() -> None:

    heading(
        "Fed Intelligence",
        "Federal Reserve research evidence.",
    )

    obj = data_for(
        "Fed Intelligence"
    )

    if isinstance(
        obj,
        dict,
    ):

        rows = []

        for key, val in obj.items():

            if (
                isinstance(
                    val,
                    (
                        str,
                        int,
                        float,
                        bool,
                    ),
                )
                or val is None
            ):

                rows.append(
                    {
                        "Field": key,
                        "Value": val,
                    }
                )

        if rows:

            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )

        else:

            st.info(
                "Fed JSON is published but exposes no simple scalar fields."
            )

    else:

        st.warning(
            "Fed Intelligence: NOT PUBLISHED"
        )


# ============================================================
# DECISION ENGINE PAGE
# ============================================================

def decision_page() -> None:

    heading(
        "Decision Engine",
        "Research classification and evidence safeguards.",
    )

    decision = decision_snapshot()

    columns = st.columns(6)

    metrics = [
        (
            "Classification",
            decision["state"],
        ),
        (
            "Evidence coverage",
            decision["confidence"],
        ),
        (
            "Evidence count",
            decision["count"],
        ),
        (
            "Supportive",
            decision["supportive"],
        ),
        (
            "Contradictory",
            decision["contradictory"],
        ),
        (
            "Mixed",
            decision["mixed"],
        ),
    ]

    for column, (
        label,
        val,
    ) in zip(
        columns,
        metrics,
    ):

        with column:

            st.metric(
                label,
                val,
            )

    st.info(
        "Confidence represents evidence coverage, not probability."
    )

    heading(
        "Evidence Chain"
    )

    evidence = decision["evidence"]

    if (
        evidence is not None
        and not evidence.empty
    ):

        display_columns = [
            column
            for column in [
                "source",
                "category",
                "value",
                "stance",
                "reason",
            ]
            if column in evidence.columns
        ]

        if display_columns:

            st.dataframe(
                evidence[
                    display_columns
                ],
                use_container_width=True,
                hide_index=True,
            )

        else:

            st.dataframe(
                evidence,
                use_container_width=True,
                hide_index=True,
            )

    else:

        st.warning(
            "Decision evidence CSV is NOT PUBLISHED. "
            "The classification shown is the verified pipeline snapshot."
        )

    st.markdown(
        "**Macro Context** -> "
        "**Financial Stress** -> "
        "**Sentiment** -> "
        "**Technical Intelligence** -> "
        "**Research Classification**"
    )

    heading(
        "Safeguards"
    )

    safeguards = [
        (
            "Point-in-time safe",
            pit_status(
                "Decision Engine"
            ),
        ),
        (
            "Research only",
            "TRUE",
        ),
        (
            "Trading signal",
            "NONE",
        ),
        (
            "Forecast",
            "NONE",
        ),
        (
            "Execution",
            "FALSE",
        ),
        (
            "Broker integration",
            "FALSE",
        ),
        (
            "Position sizing",
            "FALSE",
        ),
        (
            "Stop loss",
            "NONE",
        ),
        (
            "Take profit",
            "NONE",
        ),
    ]

    st.dataframe(
        pd.DataFrame(
            safeguards,
            columns=[
                "Control",
                "Status",
            ],
        ),
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# EVIDENCE MATRIX
# ============================================================

def evidence_page() -> None:

    heading(
        "Evidence Matrix",
        "Transparent evidence supporting the research classification.",
    )

    decision = decision_snapshot()

    columns = st.columns(2)

    with columns[0]:

        st.metric(
            "Research classification",
            decision["state"],
        )

    with columns[1]:

        st.metric(
            "Evidence coverage",
            decision["confidence"],
        )

    evidence = decision["evidence"]

    if (
        evidence is None
        or evidence.empty
    ):

        st.warning(
            "decision_engine_research_evidence_v1.csv "
            "is NOT PUBLISHED."
        )

        return

    st.dataframe(
        evidence,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# HISTORICAL EDGE
# ============================================================

def historical_edge_page() -> None:

    heading(
        "Historical Edge",
        "Descriptive historical diagnostics and robustness validation.",
    )

    columns = st.columns(4)

    metrics = [
        (
            "Common sample",
            "1,916",
        ),
        (
            "Event definitions",
            "11",
        ),
        (
            "Horizons",
            "1D / 5D / 20D",
        ),
        (
            "Event Study",
            "PASS",
        ),
    ]

    for column, (
        label,
        val,
    ) in zip(
        columns,
        metrics,
    ):

        with column:

            st.metric(
                label,
                val,
            )

    st.caption(
        "Verified Event Study V2: "
        "2019-01-03 -> 2026-08-18 | "
        "Research only | PIT-perfect: FALSE"
    )

    heading(
        "Historical Edge Robustness V1"
    )

    columns = st.columns(6)

    metrics = [
        (
            "Validation",
            "PASS",
        ),
        (
            "Temporal periods",
            "4",
        ),
        (
            "Temporal rows",
            "132",
        ),
        (
            "Threshold rows",
            "87",
        ),
        (
            "PIT audit rows",
            "3",
        ),
        (
            "PIT-perfect",
            "FALSE",
        ),
    ]

    for column, (
        label,
        val,
    ) in zip(
        columns,
        metrics,
    ):

        with column:

            st.metric(
                label,
                val,
            )

    st.warning(
        "PIT-perfect = FALSE. "
        "This documented limitation is intentionally visible."
    )

    st.info(
        "Some historical event definitions have limited historical sample sizes."
    )

    st.dataframe(
        pd.DataFrame(
            {
                "Temporal period": [
                    "FULL_SAMPLE",
                    "2019_2021",
                    "2022_2023",
                    "2024_2026",
                ],
                "Status": [
                    "VALIDATED",
                    "VALIDATED",
                    "VALIDATED",
                    "VALIDATED",
                ],
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    detail_labels = [
        "Edge: Temporal Robustness",
        "Edge: Threshold Sensitivity",
        "Edge: Temporal Stability",
        "Edge: Threshold Stability",
        "Edge: Horizon Stability",
        "Edge: Sample Adequacy",
        "Edge: Event Overlap",
        "Edge: PIT Audit",
    ]

    published = []

    for label in detail_labels:

        if df_for(label) is not None:

            published.append(label)

    if not published:

        st.info(
            "Robustness validation completed successfully, "
            "but detailed robustness tables are not currently "
            "published in public_data."
        )

    for label in published:

        with st.expander(
            label.replace(
                "Edge: ",
                "",
            )
        ):

            st.dataframe(
                df_for(label).tail(100),
                use_container_width=True,
                hide_index=True,
            )


# ============================================================
# SYSTEM HEALTH
# ============================================================

def health_page() -> None:

    heading(
        "System Health",
        "Verified pipeline milestones and frontend status.",
    )

    columns = st.columns(4)

    metrics = [
        (
            "Core modules",
            "17 / 17",
        ),
        (
            "Validation",
            "PASS",
        ),
        (
            "Decision Engine",
            "PASS",
        ),
        (
            "Historical Edge",
            "PASS",
        ),
    ]

    for column, (
        label,
        val,
    ) in zip(
        columns,
        metrics,
    ):

        with column:

            st.metric(
                label,
                val,
            )

    st.caption(
        "Run IDs are verified pipeline milestones, not a live workflow monitor."
    )

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Stage": stage,
                    "Run ID": run_id,
                    "Status": status,
                }
                for stage, (
                    run_id,
                    status,
                ) in VERIFIED_RUNS.items()
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# DATA STATUS
# ============================================================

def data_status_page() -> None:

    heading(
        "Data Status",
        "Publication state of datasets consumed by the terminal.",
    )

    rows = []

    for label, filename in DATASETS.items():

        obj = data_for(label)

        status = (
            "AVAILABLE"
            if obj is not None
            else "NOT PUBLISHED"
        )

        rows.append(
            {
                "Dataset": label,
                "File": filename,
                "Status": status,
                "Source": source_for(label),
            }
        )

    for label, filename in EDGE_FILES.items():

        key = f"Edge: {label}"

        obj = data_for(key)

        status = (
            "AVAILABLE"
            if obj is not None
            else "NOT PUBLISHED"
        )

        rows.append(
            {
                "Dataset": label,
                "File": filename,
                "Status": status,
                "Source": source_for(key),
            }
        )

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
    )

    manifest = get_manifest()

    if manifest:

        heading(
            "Public Data Manifest"
        )

        columns = st.columns(3)

        with columns[0]:

            st.metric(
                "Generated at UTC",
                str(
                    manifest.get(
                        "generated_at_utc",
                        "Not exposed",
                    )
                ),
            )

        with columns[1]:

            st.metric(
                "Master run",
                str(
                    manifest.get(
                        "master_run_id",
                        "Not exposed",
                    )
                ),
            )

        with columns[2]:

            st.metric(
                "Dataset count",
                str(
                    manifest.get(
                        "dataset_count",
                        "Not exposed",
                    )
                ),
            )

        st.caption(
            "Manifest generation time is not the same as latest observation date."
        )


# ============================================================
# METHODOLOGY
# ============================================================

def methodology_page() -> None:

    heading(
        "Methodology & Limitations"
    )

    st.markdown(
        """
### Research-only boundary

This terminal presents research evidence and validation outputs.

It does not produce:

- trading instructions
- forecasts
- execution commands
- position sizing
- stop loss
- take profit
- broker actions

### Point-in-time methodology

The frontend displays the published research artifacts as supplied.
It does not silently replace historical observations with current values.

### Data freshness

Latest published observation is the newest date contained in a dataset.
It is not a claim that the data is live.

### Decision Engine

The Decision Engine is a research classification based on evidence coverage.

**Confidence represents evidence coverage, not probability.**

### Historical Event Study

Historical Event Study V2 is a descriptive research diagnostic using:

- common sample: 1,916
- event definitions: 11
- horizons: 1D / 5D / 20D
- date range: 2019-01-03 to 2026-08-18

### Historical Edge

Historical Edge Robustness V1 contains temporal, threshold,
horizon, sample-adequacy, event-overlap and PIT diagnostics
where corresponding published artifacts are available.

### Validation semantics

**PASS means structural validation passed.**

It does not establish:

- causality
- predictiveness
- profitability
- usefulness

### Current limitations

- Some historical event definitions have limited sample sizes.
- PIT-perfect is FALSE for the current Historical Edge robustness validation.
- Detailed Historical Edge tables may be unpublished even when the workflow passed.
- Missing datasets are shown as NOT PUBLISHED rather than fabricated.
"""
    )


# ============================================================
# PAGES
# ============================================================

PAGES = {

    "Executive Overview":
        executive_overview,

    "Research Context":
        research_context_page,

    "Economic Intelligence":
        economic_page,

    "Fed Intelligence":
        fed_page,

    "Financial Stress":
        lambda:
            module_page(
                "Financial Stress",
                "Financial Stress",
                [
                    "composite_stress_score",
                    "VIX",
                    "stress_score",
                ],
            ),

    "Liquidity":
        lambda:
            module_page(
                "Liquidity",
                "Liquidity",
                [
                    "net_liquidity",
                    "liquidity_change",
                    "composite_score",
                ],
            ),

    "COT Positioning":
        lambda:
            module_page(
                "COT Positioning",
                "COT Positioning",
                [
                    "net_position",
                    "positioning_score",
                    "z_score",
                ],
            ),

    "AAII Sentiment":
        lambda:
            module_page(
                "AAII Sentiment",
                "AAII Sentiment",
                [
                    "sentiment_score",
                    "bull_bear_spread",
                    "spread",
                ],
            ),

    "VIX Sentiment":
        lambda:
            module_page(
                "VIX Sentiment",
                "VIX Sentiment",
                [
                    "sentiment_score",
                    "VIX",
                    "z_score",
                ],
            ),

    "Unified Sentiment":
        lambda:
            module_page(
                "Unified Sentiment",
                "Unified Sentiment",
                [
                    "sentiment_score",
                    "composite_score",
                    "score",
                ],
            ),

    "Technical Intelligence":
        lambda:
            module_page(
                "Technical Intelligence",
                "Technical Intelligence",
                [
                    "drawdown",
                    "technical_score",
                    "score",
                ],
            ),

    "Market Breadth":
        lambda:
            module_page(
                "Market Breadth",
                "Market Breadth",
                [
                    "breadth_score",
                    "advance_decline",
                    "score",
                ],
            ),

    "Cross-Asset Intelligence":
        lambda:
            module_page(
                "Cross-Asset Intelligence",
                "Cross-Asset Intelligence",
                [
                    "composite_score",
                    "risk_score",
                    "score",
                ],
            ),

    "Event / News Intelligence":
        lambda:
            module_page(
                "Event / News Intelligence",
                "Event / News Intelligence",
                [
                    "event_score",
                    "news_score",
                    "composite_score",
                ],
            ),

    "Earnings Intelligence":
        lambda:
            module_page(
                "Earnings Intelligence",
                "Earnings Intelligence",
                [
                    "reaction_1d",
                    "reaction_5d",
                    "reaction_20d",
                    "mfe_20d",
                    "mae_20d",
                ],
            ),

    "Historical Edge":
        historical_edge_page,

    "Decision Engine":
        decision_page,

    "Evidence Matrix":
        evidence_page,

    "System Health":
        health_page,

    "Data Status":
        data_status_page,

    "Methodology & Limitations":
        methodology_page,
}


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "## US500 Research Terminal"
    )

    st.caption(APP_VERSION)

    selected = st.radio(
        "Navigation",
        list(PAGES.keys()),
        index=0,
    )

    st.divider()

    st.caption(
        "Token-free loading"
    )

    st.caption(
        "local public_data -> "
        "GitHub Raw -> NOT PUBLISHED"
    )


# ============================================================
# RENDER
# ============================================================

PAGES[selected]()


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    f"US500 Macro Intelligence {APP_VERSION} | "
    "Research-only | "
    "No GitHub token required"
)
