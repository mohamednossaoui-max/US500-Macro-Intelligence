# US500 MACRO INTELLIGENCE - RESEARCH TERMINAL V6.1
# Research-only frontend. Token-free. No trading/execution/forecasting.

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests
import streamlit as st

APP_VERSION = "V6.2"
REPO = "mohamednossaoui-max/US500-Macro-Intelligence"
BRANCH = "main"
PUBLIC_DATA = Path(__file__).resolve().parent / "public_data"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/public_data"
HEADERS = {"User-Agent": "US500-Macro-Intelligence-Research-Terminal/6.2"}

st.set_page_config(
    page_title=f"US500 Macro Intelligence {APP_VERSION}",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
.block-container{max-width:1550px;padding-top:1rem;padding-bottom:3rem}
.hero{padding:20px 22px;border:1px solid rgba(128,140,155,.25);
border-radius:16px;background:rgba(128,140,155,.05);margin-bottom:18px}
.hero h1{margin:0;font-size:2rem}.hero p{margin:.35rem 0;color:#8b96a5}
.badge{display:inline-block;padding:4px 9px;border-radius:999px;
border:1px solid rgba(128,140,155,.35);font-size:.72rem;font-weight:700;margin-right:5px}
.card{border:1px solid rgba(128,140,155,.25);border-radius:12px;padding:14px 16px;
background:rgba(128,140,155,.04);min-height:88px}
.label{font-size:.68rem;font-weight:800;letter-spacing:.08em;color:#8b96a5}
.value{font-size:1.18rem;font-weight:800;margin-top:7px}
.small{color:#8b96a5;font-size:.76rem}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------
# Verified current public_data artifacts
# ---------------------------------------------------------------------

DATASETS = {
    "Research Context": "research_context_v1.csv",
    "Research Context Summary": "research_context_summary_v1.csv",
    "Research Context Extremes": "research_context_extremes_v1.csv",
    "Macro Context": "macro_context_v1.csv",
    "Macro Context JSON": "macro_context_v1.json",
    "Economic Regime": "economic_regime_events_v1.csv",
    "Economic Historical Events": "economic_historical_events_v1.csv",
    "Economic Quality": "economic_historical_quality_v1.csv",
    "Economic Surprise": "economic_surprise_engine_v1.csv",
    "Fed Intelligence": "fed_intelligence_output_v1.json",
    "Financial Stress": "financial_stress_research_v1.csv",
    "Financial Stress Summary": "financial_stress_research_summary_v1.csv",
    "Liquidity": "liquidity_intelligence_research_v1.csv",
    "Liquidity Summary": "liquidity_intelligence_summary_v1.csv",
    "COT": "cot_positioning_research_v1.csv",
    "COT Summary": "cot_positioning_research_summary_v1.csv",
    "COT Extremes": "cot_positioning_extremes_v1.csv",
    "AAII": "aaii_sentiment_research_v1.csv",
    "AAII Summary": "aaii_sentiment_research_summary_v1.csv",
    "AAII Extremes": "aaii_sentiment_extremes_v1.csv",
    "VIX": "vix_sentiment_research_v1.csv",
    "VIX Summary": "vix_sentiment_research_summary_v1.csv",
    "VIX Extremes": "vix_sentiment_extremes_v1.csv",
    "Technical": "technical_intelligence_research_v1.csv",
    "Technical Summary": "technical_intelligence_research_summary_v1.csv",
    "Technical Extremes": "technical_intelligence_extremes_v1.csv",
    "Breadth": "market_breadth_analysis_v1.csv",
    "Breadth Summary": "market_breadth_analysis_summary_v1.json",
    "Breadth Validation": "market_breadth_analysis_validation_v1.json",
    "Cross Asset": "cross_asset_research_v1.csv",
    "Cross Asset Summary": "cross_asset_summary_v1.json",
    "Cross Asset Validation": "cross_asset_validation_v1.json",
    "Event News": "event_news_research_v2.csv",
    "Event News Summary": "event_news_research_summary_v2.json",
    "Event News Validation": "event_news_validation_v2.json",
    "Earnings": "earnings_market_reaction_v3.csv",
    "Earnings Summary": "earnings_market_reaction_summary_v3.csv",
    "Earnings EPS": "earnings_reaction_by_eps_class_v3.csv",
    "Earnings Sectors": "earnings_reaction_by_sector_v3.csv",
    "Decision": "decision_engine_research_v1.csv",
    "Decision Summary": "decision_engine_research_summary_v1.csv",
    "Decision Evidence": "decision_engine_research_evidence_v1.csv",
    "Decision JSON": "decision_engine_research_v1.json",
    "Final Validation": "final_end_to_end_validation_report.csv",
    "Final Validation Summary": "final_end_to_end_validation_summary.csv",
    "Final Validation JSON": "final_end_to_end_validation.json",
    "Final Validation Manifest": "final_end_to_end_validation_manifest.csv",
    "Final Validation Events": "final_end_to_end_validation_events.csv",
    "Event Study Summary": "historical_event_study_summary_v2.csv",
    "Event Study Baseline": "historical_event_study_baseline_v2.csv",
    "Event Study Conditional": "historical_event_study_conditional_events_v2.csv",
    "Event Study Controlled": "historical_event_study_controlled_associations_v2.csv",
    "Event Study Overlap": "historical_event_study_event_overlap_v2.csv",
    "Event Study Redundancy": "historical_event_study_feature_redundancy_v2.csv",
    "Event Study Adequacy": "historical_event_study_sample_adequacy_v2.csv",
    "Event Study Validation": "historical_event_study_validation_v2.json",
}

DATE_COLUMNS = [
    "context_date", "asof_date", "research_date", "observation_date",
    "event_date", "reported_date", "date", "timestamp", "datetime",
]


@st.cache_data(ttl=1800, show_spinner=False)
def get_manifest() -> dict[str, Any]:
    """Load the single canonical publication manifest: manifest.json."""
    filename = "manifest.json"
    local = PUBLIC_DATA / filename
    if local.exists() and local.is_file():
        try:
            manifest = json.loads(local.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = None
        if isinstance(manifest, dict):
            return manifest

    raw = fetch_raw(filename)
    if raw is not None:
        try:
            manifest = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            manifest = None
        if isinstance(manifest, dict):
            return manifest

    return {}


@st.cache_data(ttl=900, show_spinner=False)
def fetch_raw(filename: str) -> Optional[bytes]:
    clean = filename.replace("\\", "/").lstrip("/")
    if clean.startswith("public_data/"):
        clean = clean.split("public_data/", 1)[1]
    try:
        response = requests.get(
            f"{RAW_BASE}/{clean}",
            headers=HEADERS,
            timeout=15,
        )
        if response.status_code == 200:
            return response.content
    except requests.RequestException:
        pass
    return None


def manifest_files() -> list[str]:
    manifest = get_manifest()
    result = []
    datasets = manifest.get("datasets")
    if isinstance(datasets, list):
        for item in datasets:
            if isinstance(item, dict) and isinstance(item.get("file"), str):
                result.append(item["file"])
    return sorted(set(result))


@st.cache_data(ttl=900, show_spinner=False)
def load_bytes(filename: str) -> tuple[Optional[bytes], str]:
    clean = filename.replace("\\", "/").lstrip("/")
    if clean.startswith("public_data/"):
        clean = clean.split("public_data/", 1)[1]

    local = PUBLIC_DATA / clean
    if local.exists() and local.is_file():
        try:
            return local.read_bytes(), f"LOCAL: public_data/{clean}"
        except OSError:
            pass

    raw = fetch_raw(clean)
    if raw is not None:
        return raw, f"GITHUB RAW: public_data/{clean}"

    return None, "NOT PUBLISHED"


@st.cache_data(ttl=900, show_spinner=False)
def load_csv(filename: str) -> tuple[Optional[pd.DataFrame], str]:
    raw, source = load_bytes(filename)
    if raw is None:
        return None, source
    try:
        df = pd.read_csv(io.BytesIO(raw), low_memory=False)
        df.columns = [str(c).strip() for c in df.columns]
        return df, source
    except (ValueError, TypeError, pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError):
        return None, f"UNREADABLE: {source}"


@st.cache_data(ttl=900, show_spinner=False)
def load_json(filename: str) -> tuple[Optional[Any], str]:
    raw, source = load_bytes(filename)
    if raw is None:
        return None, source
    try:
        return json.loads(raw.decode("utf-8")), source
    except (UnicodeDecodeError, ValueError):
        return None, f"UNREADABLE: {source}"


def load_named(name: str) -> tuple[Any, str]:
    filename = DATASETS[name]
    if filename.endswith(".json"):
        return load_json(filename)
    return load_csv(filename)


def date_column(df: Optional[pd.DataFrame]) -> Optional[str]:
    if df is None or df.empty:
        return None
    lookup = {str(c).lower(): c for c in df.columns}
    for name in DATE_COLUMNS:
        if name.lower() in lookup:
            return str(lookup[name.lower()])
    return None


def latest_row(df: Optional[pd.DataFrame]) -> Optional[pd.Series]:
    if df is None or df.empty:
        return None
    column = date_column(df)
    if column is None:
        return df.iloc[-1]
    dates = pd.to_datetime(df[column], errors="coerce", utc=True)
    if dates.notna().any():
        return df.loc[dates.idxmax()]
    return df.iloc[-1]


def latest_date(df: Optional[pd.DataFrame]) -> str:
    if df is None or df.empty:
        return "—"
    column = date_column(df)
    if column is None:
        return "—"
    dates = pd.to_datetime(df[column], errors="coerce", utc=True).dropna()
    if dates.empty:
        return "—"
    return dates.max().strftime("%Y-%m-%d")


def safe_value(
    row: Optional[pd.Series],
    names: list[str],
    default: Any = "Not available",
) -> Any:
    if row is None:
        return default
    lookup = {str(c).lower(): c for c in row.index}
    for name in names:
        column = lookup.get(name.lower())
        if column is None:
            continue
        item = row[column]
        try:
            if pd.isna(item):
                continue
        except (TypeError, ValueError):
            pass
        return item
    return default


def fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    try:
        if pd.isna(value):
            return "—"
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.{digits}f}"
    return str(value)


def card(label: str, value: Any, note: str = "") -> None:
    st.markdown(
        f'<div class="card"><div class="label">{label}</div>'
        f'<div class="value">{fmt(value)}</div>'
        f'<div class="small">{note}</div></div>',
        unsafe_allow_html=True,
    )


def table(df: Optional[pd.DataFrame], height: int = 380) -> None:
    if df is None:
        st.info("Artifact is not published or could not be loaded.")
        return
    if df.empty:
        st.info("Artifact is published but contains no rows.")
        return
    st.dataframe(df, use_container_width=True, height=height, hide_index=True)


def source_status(text: str) -> str:
    if text.startswith("LOCAL:"):
        return "LOCAL"
    if text.startswith("GITHUB RAW:"):
        return "GITHUB RAW"
    if text.startswith("UNREADABLE:"):
        return "UNREADABLE"
    return "NOT PUBLISHED"


def source(name: str, text: str) -> None:
    st.caption(f"{name} • {text}")


def chart(df: Optional[pd.DataFrame], preferred: list[str]) -> None:
    if df is None or df.empty:
        st.info("No observations available for this chart.")
        return
    dcol = date_column(df)
    if dcol is None:
        st.info("No date column is exposed by this artifact.")
        return

    numeric = []
    for column in df.columns:
        converted = pd.to_numeric(df[column], errors="coerce")
        if int(converted.notna().sum()) >= 3:
            numeric.append(str(column))

    if not numeric:
        st.info("No numeric series is exposed by this artifact.")
        return

    lower = {c.lower(): c for c in numeric}
    selected = None
    for candidate in preferred:
        if candidate.lower() in lower:
            selected = lower[candidate.lower()]
            break
    if selected is None:
        selected = numeric[0]

    plot = pd.DataFrame(
        {
            "Date": pd.to_datetime(df[dcol], errors="coerce", utc=True),
            selected: pd.to_numeric(df[selected], errors="coerce"),
        }
    ).dropna()

    if plot.empty:
        st.info("No valid observations for this chart.")
        return

    st.caption(f"Series: {selected}")
    st.line_chart(plot.set_index("Date"))


def module_page(
    title: str,
    data_name: str,
    chart_columns: list[str],
    summary_name: Optional[str] = None,
    json_names: Optional[list[str]] = None,
) -> None:
    st.header(title)
    df, src = load_named(data_name)
    row = latest_row(df)

    cols = st.columns(5)
    metrics = [
        ("Latest Date", latest_date(df)),
        ("Rows", len(df) if isinstance(df, pd.DataFrame) else "—"),
        ("Regime", safe_value(
            row,
            ["research_regime", "regime", "state", "technical_regime",
             "sentiment_regime", "breadth_research_state"],
        )),
        ("PIT", safe_value(row, ["point_in_time_safe", "pit_safe"])),
        ("Source", source_status(src)),
    ]
    for col, (label, value) in zip(cols, metrics):
        with col:
            card(label, value)

    chart(df, chart_columns)

    st.subheader("Latest Published Data")
    table(df.tail(250) if isinstance(df, pd.DataFrame) else None, 520)
    source(data_name, src)

    if summary_name is not None:
        summary, summary_src = load_named(summary_name)
        st.subheader("Summary")
        table(summary, 280)
        source(summary_name, summary_src)

    if json_names:
        for name in json_names:
            obj, json_src = load_named(name)
            if isinstance(obj, dict):
                with st.expander(name):
                    st.json(obj)
                source(name, json_src)


def executive() -> None:
    st.header("Executive Research Dashboard")

    rc, rc_src = load_named("Research Context Summary")
    mc, mc_src = load_named("Macro Context")
    dec, dec_src = load_named("Decision Summary")
    evidence, evidence_src = load_named("Decision Evidence")

    rc_row = latest_row(rc)
    mc_row = latest_row(mc)
    dec_row = latest_row(dec)

    cols = st.columns(6)
    metrics = [
        ("Context Date", safe_value(rc_row, ["context_date"])),
        ("Economic", safe_value(rc_row, ["economic_regime"])),
        ("Financial Stress", safe_value(rc_row, ["financial_stress_regime"])),
        ("Sentiment", safe_value(rc_row, ["sentiment_regime"])),
        ("Technical", safe_value(rc_row, ["technical_regime"])),
        ("PIT Safe", safe_value(rc_row, ["point_in_time_safe"])),
    ]
    for col, (label, value) in zip(cols, metrics):
        with col:
            card(label, value)

    st.subheader("Publication & Freshness")
    coverage = st.columns(4)
    coverage_metrics = [
        ("Research Context", latest_date(rc)),
        ("Macro Context", latest_date(mc)),
        ("Decision Engine", latest_date(dec)),
        ("Final Validation", latest_date(load_named("Final Validation Summary")[0])),
    ]
    for col, (label, value) in zip(coverage, coverage_metrics):
        with col:
            card(label, value)
    st.caption(
        f"Sources: Research Context={source_status(rc_src)} • "
        f"Macro Context={source_status(mc_src)} • Decision={source_status(dec_src)}"
    )

    st.subheader("Research Scores")
    cols = st.columns(6)
    metrics = [
        ("Inflation", safe_value(rc_row, ["inflation_score"])),
        ("Labor", safe_value(rc_row, ["labor_score"])),
        ("Growth", safe_value(rc_row, ["growth_score"])),
        ("Fed", safe_value(rc_row, ["fed_score"])),
        ("Stress Composite", safe_value(rc_row, ["financial_stress_composite"])),
        ("Unified Sentiment", safe_value(rc_row, ["unified_sentiment_score"])),
    ]
    for col, (label, value) in zip(cols, metrics):
        with col:
            card(label, value)

    st.subheader("Decision Engine")
    cols = st.columns(8)
    metrics = [
        ("State", safe_value(dec_row, ["state"])),
        ("Confidence", safe_value(dec_row, ["confidence"])),
        ("Evidence", safe_value(dec_row, ["evidence_count"])),
        ("Supportive", safe_value(dec_row, ["supportive_count"])),
        ("Contradictory", safe_value(dec_row, ["contradictory_count"])),
        ("Mixed", safe_value(dec_row, ["mixed_count"])),
        ("PIT", safe_value(dec_row, ["point_in_time_safe"])),
        ("Research Only", safe_value(dec_row, ["research_only"])),
    ]
    for col, (label, value) in zip(cols, metrics):
        with col:
            card(label, value)

    st.info("Confidence is evidence coverage, not probability.")

    st.subheader("Decision Evidence")
    table(evidence, 300)
    source("Decision Evidence", evidence_src)

    st.subheader("Research Context Trend")
    chart(
        rc,
        ["unified_sentiment_score", "fed_score", "inflation_score", "growth_score"],
    )

    st.caption(
        f"Research Context: {rc_src} • Macro Context: {mc_src} • Decision: {dec_src}"
    )


def research_context() -> None:
    st.header("Research Context")
    df, src = load_named("Research Context Summary")
    extremes, extremes_src = load_named("Research Context Extremes")
    row = latest_row(df)

    cols = st.columns(7)
    metrics = [
        ("Date", safe_value(row, ["context_date"])),
        ("Layers", safe_value(row, ["available_layer_count"])),
        ("Economic", safe_value(row, ["economic_regime"])),
        ("Stress", safe_value(row, ["financial_stress_regime"])),
        ("Sentiment", safe_value(row, ["sentiment_regime"])),
        ("Technical", safe_value(row, ["technical_regime"])),
        ("Decision Ready", safe_value(row, ["decision_engine_ready"])),
    ]
    for col, (label, value) in zip(cols, metrics):
        with col:
            card(label, value)

    table(df, 300)
    source("Research Context Summary", src)

    st.subheader("Research Context Extremes")
    table(extremes, 420)
    source("Research Context Extremes", extremes_src)


def macro_context() -> None:
    st.header("Macro Context")
    df, src = load_named("Macro Context")
    obj, json_src = load_named("Macro Context JSON")
    row = latest_row(df)

    cols = st.columns(7)
    metrics = [
        ("Date", safe_value(row, ["context_date"])),
        ("Economic", safe_value(row, ["economic_regime"])),
        ("Fed Score", safe_value(row, ["fed_score"])),
        ("Stress", safe_value(row, ["financial_stress_regime"])),
        ("Event Topic", safe_value(row, ["event_news_latest_topic"])),
        ("Events", safe_value(row, ["event_news_events_available"])),
        ("Anti-Lookahead", safe_value(row, ["anti_lookahead"])),
    ]
    for col, (label, value) in zip(cols, metrics):
        with col:
            card(label, value)

    table(df, 280)
    source("Macro Context", src)

    if isinstance(obj, dict):
        with st.expander("Macro Context JSON"):
            st.json(obj)
    source("Macro Context JSON", json_src)


def economic() -> None:
    st.header("Economic Intelligence")
    tabs = st.tabs(["Regime", "Surprise", "Historical Events", "Quality"])

    with tabs[0]:
        df, src = load_named("Economic Regime")
        table(df, 420)
        source("Economic Regime", src)

    with tabs[1]:
        df, src = load_named("Economic Surprise")
        table(df.tail(300) if isinstance(df, pd.DataFrame) else None, 500)
        source("Economic Surprise", src)

    with tabs[2]:
        df, src = load_named("Economic Historical Events")
        table(df.tail(300) if isinstance(df, pd.DataFrame) else None, 500)
        source("Economic Historical Events", src)

    with tabs[3]:
        df, src = load_named("Economic Quality")
        table(df, 420)
        source("Economic Quality", src)


def fed() -> None:
    st.header("Fed Intelligence")
    obj, src = load_named("Fed Intelligence")

    if not isinstance(obj, dict):
        st.warning("Fed Intelligence is not published.")
        return

    rows = []
    for key, value in obj.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            rows.append({"Field": key, "Value": fmt(value)})

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("Complete Fed JSON"):
        st.json(obj)
    source("Fed Intelligence", src)


def sentiment() -> None:
    st.header("Sentiment Intelligence")
    tabs = st.tabs(["Unified Context", "AAII", "VIX", "COT"])

    with tabs[0]:
        df, src = load_named("Research Context Summary")
        row = latest_row(df)
        cols = st.columns(6)
        metrics = [
            ("Date", safe_value(row, ["context_date"])),
            ("Regime", safe_value(row, ["sentiment_regime"])),
            ("Unified Score", safe_value(row, ["unified_sentiment_score"])),
            ("AAII Score", safe_value(row, ["aaii_score"])),
            ("VIX Score", safe_value(row, ["vix_score"])),
            ("COT Score", safe_value(row, ["cot_score"])),
        ]
        for col, (label, value) in zip(cols, metrics):
            with col:
                card(label, value)
        st.caption(
            "Unified sentiment is published inside Research Context Summary. "
            "The current manifest does not contain a standalone sentiment engine CSV."
        )
        table(df, 300)
        source("Research Context Summary", src)

    with tabs[1]:
        module_page("AAII Sentiment", "AAII",
                    ["sentiment_score", "bull_bear_spread", "spread", "bullish"],
                    "AAII Summary")

    with tabs[2]:
        module_page("VIX Sentiment", "VIX",
                    ["VIX", "sentiment_score", "z_score", "vix_score"],
                    "VIX Summary")

    with tabs[3]:
        module_page("COT Positioning", "COT",
                    ["net_position", "positioning_score", "z_score", "cot_score"],
                    "COT Summary")


def technical() -> None:
    module_page(
        "Technical Intelligence",
        "Technical",
        ["Close", "RSI14", "ATR14_pct", "ROC20_pct", "drawdown_pct"],
        "Technical Summary",
    )


def breadth() -> None:
    module_page(
        "Market Breadth",
        "Breadth",
        ["breadth_score", "score", "advance_decline"],
        json_names=["Breadth Summary", "Breadth Validation"],
    )


def cross_asset() -> None:
    module_page(
        "Cross-Asset Intelligence",
        "Cross Asset",
        ["composite_score", "risk_score", "score"],
        json_names=["Cross Asset Summary", "Cross Asset Validation"],
    )


def event_news() -> None:
    module_page(
        "Event / News Intelligence V2",
        "Event News",
        ["event_score", "news_score", "composite_score"],
        json_names=["Event News Summary", "Event News Validation"],
    )


def earnings() -> None:
    st.header("Corporate Earnings Intelligence V3")
    tabs = st.tabs(["Events", "Summary", "EPS Classes", "Sectors"])

    with tabs[0]:
        df, src = load_named("Earnings")
        table(df.tail(300) if isinstance(df, pd.DataFrame) else None, 560)
        source("Earnings", src)

    with tabs[1]:
        df, src = load_named("Earnings Summary")
        table(df)
        source("Earnings Summary", src)

    with tabs[2]:
        df, src = load_named("Earnings EPS")
        table(df)
        source("Earnings EPS", src)

    with tabs[3]:
        df, src = load_named("Earnings Sectors")
        table(df)
        source("Earnings Sectors", src)


def decision() -> None:
    st.header("Decision Engine V1 - Research Gate")
    df, src = load_named("Decision Summary")
    evidence, evidence_src = load_named("Decision Evidence")
    obj, json_src = load_named("Decision JSON")
    row = latest_row(df)

    cols = st.columns(8)
    metrics = [
        ("State", safe_value(row, ["state"])),
        ("Confidence", safe_value(row, ["confidence"])),
        ("Evidence", safe_value(row, ["evidence_count"])),
        ("Supportive", safe_value(row, ["supportive_count"])),
        ("Contradictory", safe_value(row, ["contradictory_count"])),
        ("Mixed", safe_value(row, ["mixed_count"])),
        ("PIT", safe_value(row, ["point_in_time_safe"])),
        ("Research Only", safe_value(row, ["research_only"])),
    ]
    for col, (label, value) in zip(cols, metrics):
        with col:
            card(label, value)

    st.subheader("Evidence Matrix")
    table(evidence, 350)
    source("Decision Evidence", evidence_src)

    st.subheader("Decision Summary")
    table(df, 240)
    source("Decision Summary", src)

    if isinstance(obj, dict):
        with st.expander("Complete Decision JSON"):
            st.json(obj)
    source("Decision JSON", json_src)

    st.info(
        "Research gate only. No trading signal, forecast, order, execution, "
        "broker integration, position sizing, stop loss, or take profit."
    )


def event_study() -> None:
    st.header("Historical Event Study V2")

    validation, validation_src = load_named("Event Study Validation")
    summary, summary_src = load_named("Event Study Summary")
    baseline, baseline_src = load_named("Event Study Baseline")
    conditional, conditional_src = load_named("Event Study Conditional")
    controlled, controlled_src = load_named("Event Study Controlled")
    overlap, overlap_src = load_named("Event Study Overlap")
    redundancy, redundancy_src = load_named("Event Study Redundancy")
    adequacy, adequacy_src = load_named("Event Study Adequacy")

    if isinstance(validation, dict):
        cols = st.columns(7)
        metrics = [
            ("Status", validation.get("status", "—")),
            ("Common Sample", validation.get("common_sample_rows", "—")),
            ("Definitions", validation.get("event_definition_count", "—")),
            ("Start", validation.get("date_start", "—")),
            ("End", validation.get("date_end", "—")),
            ("Horizons", ", ".join(validation.get("outcome_horizons", []))),
            ("PIT Perfect", validation.get("pit_perfect", "—")),
        ]
        for col, (label, value) in zip(cols, metrics):
            with col:
                card(label, value)

        warnings = validation.get("warnings")
        if isinstance(warnings, list) and warnings:
            st.warning("Validation warnings: " + " | ".join(str(x) for x in warnings))

        with st.expander("Validation JSON"):
            st.json(validation)
        source("Event Study Validation", validation_src)

    for title, df, src in [
        ("Baseline", baseline, baseline_src),
        ("Event x Horizon Summary", summary, summary_src),
        ("Conditional Events", conditional, conditional_src),
        ("Controlled Associations", controlled, controlled_src),
        ("Event Overlap", overlap, overlap_src),
        ("Feature Redundancy", redundancy, redundancy_src),
        ("Sample Adequacy", adequacy, adequacy_src),
    ]:
        st.subheader(title)
        table(df, 560 if title == "Event x Horizon Summary" else 360)
        source(title, src)


def historical_edge() -> None:
    st.header("Historical Edge / Robustness")

    st.info(
        "The current public_data manifest does not publish separate historical_edge_* "
        "artifacts. The currently published robustness evidence is Historical Event Study V2."
    )

    validation, src = load_named("Event Study Validation")
    if isinstance(validation, dict):
        cols = st.columns(5)
        metrics = [
            ("Status", validation.get("status", "—")),
            ("Common Sample", validation.get("common_sample_rows", "—")),
            ("Definitions", validation.get("event_definition_count", "—")),
            ("PIT Perfect", validation.get("pit_perfect", "—")),
            ("Research Only", validation.get("research_only", "—")),
        ]
        for col, (label, value) in zip(cols, metrics):
            with col:
                card(label, value)
    source("Historical Edge reference", src)

    summary, summary_src = load_named("Event Study Summary")
    adequacy, adequacy_src = load_named("Event Study Adequacy")
    overlap, overlap_src = load_named("Event Study Overlap")

    st.subheader("Published Event Study Evidence")
    table(summary, 560)
    source("Event Study Summary", summary_src)
    table(adequacy, 360)
    source("Event Study Adequacy", adequacy_src)
    table(overlap, 360)
    source("Event Study Overlap", overlap_src)


def final_validation() -> None:
    st.header("Final End-to-End Validation")

    summary, summary_src = load_named("Final Validation Summary")
    report, report_src = load_named("Final Validation")
    obj, json_src = load_named("Final Validation JSON")

    st.subheader("Validation Summary")
    table(summary, 220)
    source("Final Validation Summary", summary_src)

    if isinstance(summary, pd.DataFrame) and "status" in summary.columns:
        counts = summary["status"].astype(str).str.upper().value_counts()
        cols = st.columns(4)
        for col, status in zip(cols, ["PASS", "REVIEW", "FAIL", "OVERALL"]):
            with col:
                card(status, int(counts.get(status, 0)))

    st.subheader("Validation Report")
    table(report, 650)
    source("Final Validation Report", report_src)

    if isinstance(obj, dict):
        with st.expander("Final Validation JSON"):
            st.json(obj)
    source("Final Validation JSON", json_src)


def data_status() -> None:
    st.header("Data Status & Freshness")

    published = set(manifest_files())
    rows = []

    for name, filename in DATASETS.items():
        local = (PUBLIC_DATA / filename).exists()
        if local:
            status = "LOCAL + PUBLISHED"
        elif filename in published:
            status = "PUBLISHED"
        else:
            status = "NOT IN CURRENT MANIFEST"

        rows.append({
            "Dataset": name,
            "File": filename,
            "Status": status,
        })

    table(pd.DataFrame(rows), 650)

    configured_files = set(DATASETS.values())
    extra_published = sorted(published - configured_files)
    if extra_published:
        st.subheader("Published Artifacts Not Yet Mapped to a Named Module")
        st.dataframe(
            pd.DataFrame({"File": extra_published}),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("All artifacts in the current manifest are mapped to the terminal configuration.")

    manifest = get_manifest()
    cols = st.columns(4)
    metrics = [
        ("Manifest Datasets", manifest.get("dataset_count", "—")),
        ("Generated UTC", manifest.get("generated_at_utc", "—")),
        ("Master Run", manifest.get("master_run_id", "—")),
        ("Repository", manifest.get("repository", REPO)),
    ]
    for col, (label, value) in zip(cols, metrics):
        with col:
            card(label, value)

    st.caption(
        "Availability is determined from the actual public_data manifest. "
        "No fabricated fallback values are used."
    )


def explorer() -> None:
    st.header("Published Data Explorer")
    files = manifest_files()

    if not files:
        st.warning("public_data manifest was not found.")
        return

    selected = st.selectbox("Artifact", files)
    obj, src = load_csv(selected) if selected.endswith(".csv") else load_json(selected)
    source(selected, src)

    if isinstance(obj, pd.DataFrame):
        st.write(
            f"Rows: {len(obj):,} • Columns: {len(obj.columns):,} • "
            f"Latest date: {latest_date(obj)}"
        )
        table(obj, 700)
        st.download_button(
            "Download CSV",
            obj.to_csv(index=False).encode("utf-8"),
            file_name=Path(selected).name,
            mime="text/csv",
        )
    elif isinstance(obj, dict):
        st.json(obj)
    else:
        st.info("Artifact is unavailable or unreadable.")


def methodology() -> None:
    st.header("Methodology & Boundaries")
    st.markdown(
        """
### Research-only boundary

This terminal displays published research artifacts only.

It does not generate trading signals, forecasts, orders, broker actions,
position sizing, stop loss, or take profit.

### Loading architecture

1. local public_data
2. public GitHub Raw
3. explicit NOT PUBLISHED

No GitHub token or GitHub API authentication is required.

### Point-in-time

The terminal displays PIT fields supplied by the research pipeline and does not
silently replace historical observations with current values.

### Decision Engine

The published Decision Engine exposes state, confidence/evidence coverage,
evidence counts, PIT status and research-only controls.

### Historical Event Study V2

The currently published validation reports:

- common sample: 1,916
- event definitions: 11
- horizons: 1D / 5D / 20D
- date range: 2019-01-03 to 2026-08-18
- PIT perfect: FALSE

PASS is structural validation only. It does not establish causality,
predictiveness, profitability, usefulness, or preference.

### Publication boundary

The current manifest does not contain separate historical_edge_* artifacts.
The dashboard therefore shows the published Historical Event Study V2 evidence
instead of inventing Historical Edge tables.
"""
    )


PAGES = {
    "Executive Dashboard": executive,
    "Research Context": research_context,
    "Macro Context": macro_context,
    "Economic Intelligence": economic,
    "Fed Intelligence": fed,
    "Financial Stress": lambda: module_page(
        "Financial Stress", "Financial Stress",
        ["composite_stress_score", "VIX", "NFCI", "ANFCI"],
        "Financial Stress Summary",
    ),
    "Liquidity": lambda: module_page(
        "Liquidity Intelligence", "Liquidity",
        ["net_liquidity", "liquidity_change", "composite_score"],
        "Liquidity Summary",
    ),
    "Sentiment": sentiment,
    "Technical Intelligence": technical,
    "Market Breadth": breadth,
    "Cross-Asset": cross_asset,
    "Event / News": event_news,
    "Earnings": earnings,
    "Decision Engine": decision,
    "Historical Event Study": event_study,
    "Historical Edge": historical_edge,
    "Final Validation": final_validation,
    "Data Status": data_status,
    "Data Explorer": explorer,
    "Methodology": methodology,
}

with st.sidebar:
    st.markdown("## US500 Research Terminal")
    st.caption(APP_VERSION)
    selected = st.radio("Navigation", list(PAGES.keys()), index=0)
    st.divider()
    st.caption("Token-free")
    st.caption("local public_data → GitHub Raw → NOT PUBLISHED")
    st.caption(f"Manifest datasets: {get_manifest().get('dataset_count', '—')}")

st.markdown(
    '<div class="hero"><h1>US500 Macro Intelligence — Research Terminal V6.2</h1>'
    '<p>Published research artifacts • point-in-time fields • transparent evidence</p>'
    '<span class="badge">RESEARCH ONLY</span>'
    '<span class="badge">TOKEN FREE</span>'
    '<span class="badge">NO FORECAST</span>'
    '<span class="badge">NO EXECUTION</span></div>',
    unsafe_allow_html=True,
)

PAGES[selected]()

st.divider()
st.caption(
    f"US500 Macro Intelligence {APP_VERSION} • Research-only • No GitHub token required"
)
