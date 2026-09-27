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

APP_VERSION = "V6.3"
REPO = "mohamednossaoui-max/US500-Macro-Intelligence"
BRANCH = "main"
PUBLIC_DATA = Path(__file__).resolve().parent / "public_data"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/public_data"
HEADERS = {"User-Agent": "US500-Macro-Intelligence-Research-Terminal/6.3"}

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

.fed-strip{border:1px solid rgba(128,140,155,.25);border-radius:14px;padding:14px 16px;margin:.35rem 0 .9rem 0;background:rgba(128,140,155,.035)}
.fed-strip .kicker{font-size:.68rem;font-weight:800;letter-spacing:.08em;color:#8b96a5}
.fed-strip .headline{font-size:1.08rem;font-weight:800;margin:.2rem 0}
.fed-strip .detail{font-size:.8rem;color:#8b96a5}
.pulse{display:flex;justify-content:space-between;gap:8px;align-items:center;padding:9px 0;border-bottom:1px solid rgba(128,140,155,.16)}
.pulse:last-child{border-bottom:0}.pulse-name{font-weight:750}.pulse-value{font-variant-numeric:tabular-nums;font-weight:800}.pulse-note{font-size:.76rem;color:#8b96a5}
.timeline{font-weight:800;letter-spacing:.01em;padding:10px 0 4px 0}
.econ-pulse{border:1px solid rgba(128,140,155,.28);border-radius:14px;padding:15px 16px;background:rgba(128,140,155,.045);margin:.35rem 0 .9rem}
.econ-regime{font-size:1.45rem;font-weight:900;letter-spacing:.03em}.econ-sub{font-size:.8rem;color:#8b96a5;line-height:1.45}
.econ-dim{border:1px solid rgba(128,140,155,.22);border-radius:12px;padding:12px 14px;background:rgba(128,140,155,.03);min-height:112px}
.econ-dim .score{font-size:1.25rem;font-weight:850;margin:.2rem 0}.econ-release{border:1px solid rgba(128,140,155,.22);border-radius:11px;padding:10px 12px;margin:7px 0;background:rgba(128,140,155,.025)}.econ-release .name{font-weight:850}.econ-release .meta{font-size:.75rem;color:#8b96a5}.econ-bottom{border:1px solid rgba(128,140,155,.28);border-radius:14px;padding:14px 16px;background:rgba(128,140,155,.055);margin:.3rem 0 1rem}.econ-group{border:1px solid rgba(128,140,155,.22);border-radius:12px;padding:9px 12px;background:rgba(128,140,155,.025);min-height:96px}.econ-group-title{font-size:.72rem;font-weight:850;letter-spacing:.07em;color:#8b96a5;margin-bottom:5px}.econ-indicator{padding:4px 0;border-bottom:1px solid rgba(128,140,155,.12)}.econ-indicator:last-child{border-bottom:0}.econ-indicator b{font-size:.86rem}.econ-reading{font-size:.8rem;font-variant-numeric:tabular-nums}.econ-context{font-size:.71rem;color:#8b96a5}
.fed-gauge{position:relative;height:16px;border-radius:999px;background:linear-gradient(90deg,rgba(74,144,226,.55),rgba(128,140,155,.18) 50%,rgba(231,111,81,.55));margin:18px 2px 8px}
.fed-marker{position:absolute;top:-7px;width:4px;height:30px;border-radius:4px;background:currentColor;box-shadow:0 0 0 3px rgba(128,140,155,.18)}
.fed-scale{display:flex;justify-content:space-between;font-size:.67rem;font-weight:800;letter-spacing:.07em;color:#8b96a5}
.signal-card{border:1px solid rgba(128,140,155,.25);border-radius:12px;padding:12px 14px;background:rgba(128,140,155,.035);min-height:105px}
.signal-title{font-size:.72rem;font-weight:800;letter-spacing:.06em;color:#8b96a5}
.signal-main{font-size:1.05rem;font-weight:850;margin:.25rem 0}.signal-why{font-size:.76rem;color:#8b96a5;line-height:1.35}
.comm-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 2px;border-bottom:1px solid rgba(128,140,155,.16)}
.comm-row:last-child{border-bottom:0}.comm-name{font-weight:800}.comm-state{font-size:.76rem;font-weight:800}.comm-note{font-size:.73rem;color:#8b96a5}
.bottom-line{border:1px solid rgba(128,140,155,.28);border-radius:14px;padding:15px 16px;background:rgba(128,140,155,.055);margin:.25rem 0 1rem}
.bottom-line .title{font-size:.68rem;font-weight:850;letter-spacing:.09em;color:#8b96a5}.bottom-line .read{font-size:1.12rem;font-weight:850;margin:.25rem 0}.bottom-line .body{font-size:.84rem;line-height:1.5;color:#8b96a5}
@media (max-width: 700px){.block-container{padding-left:.75rem;padding-right:.75rem}.hero{padding:14px 14px}.hero h1{font-size:1.45rem}.card{min-height:76px;padding:11px 12px}.value{font-size:1.02rem}.pulse{display:grid;grid-template-columns:1fr auto;gap:2px 10px}.pulse-note{grid-column:2;text-align:right}.timeline{font-size:.8rem;white-space:normal}.signal-card{min-height:0}.fed-strip,.bottom-line{padding:12px 13px}}
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
    "Earnings Quality": "earnings_quality_summary_v3.json",
    "Decision": "decision_engine_research_v1.csv",
    "Decision Summary": "decision_engine_research_summary_v1.csv",
    "Decision Evidence": "decision_engine_research_evidence_v1.csv",
    "Decision Evidence Registry": "decision_engine_evidence_registry_v2.csv",
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
    "Remaining Layers Quality": "remaining_layers_quality_v1.csv",
    "Remaining Layers Validation": "remaining_layers_quality_validation_v1.json",
    "Final Hardening Validation": "final_remaining_layers_hardening_v1.json",
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
    """Return published artifact paths from either supported manifest shape.

    The canonical publication manifest stores artifacts under ``files`` as a
    mapping keyed by repository-relative paths. Older manifests used a
    ``datasets`` list with a ``file`` field. Keep both shapes readable, but
    never treat the manifest itself as an artifact.
    """
    manifest = get_manifest()
    result: list[str] = []

    files = manifest.get("files")
    if isinstance(files, dict):
        result.extend(str(name) for name in files if isinstance(name, str))

    datasets = manifest.get("datasets")
    if isinstance(datasets, list):
        for item in datasets:
            if isinstance(item, dict) and isinstance(item.get("file"), str):
                result.append(item["file"])

    return sorted({name.replace("\\", "/").lstrip("/") for name in result})


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

    # PR-08D.1 — expose the already-published evidence-quality metadata.
    # Presentation only: no quality value is recomputed in the UI.
    st.subheader("Evidence Quality")
    qcols = st.columns(5)
    qmetrics = [
        ("Overall Quality", safe_value(row, ["evidence_quality_status"]),
         f"As of {safe_value(row, ['evidence_as_of_date'], 'NOT AVAILABLE')}"),
        ("Coverage", safe_value(row, ["evidence_coverage_pct"]), "% available evidence"),
        ("Freshness", safe_value(row, ["evidence_freshness_status"]),
         f"{fmt(safe_value(row, ['evidence_freshness_current_pct'], None))}% current"),
        ("PIT Integrity", safe_value(row, ["evidence_pit_status"]),
         f"{fmt(safe_value(row, ['evidence_pit_safe_pct'], None))}% PIT-safe"),
        ("Degraded / Missing", safe_value(row, ["evidence_degraded_count"]),
         f"{fmt(safe_value(row, ['evidence_excluded_count'], None), 0)} excluded"),
    ]
    for col, (label, value, note) in zip(qcols, qmetrics):
        with col:
            card(label, value, note)

    q_quality = safe_value(row, ["evidence_quality_status"], "NOT AVAILABLE")
    q_pit = safe_value(row, ["evidence_pit_status"], "NOT AVAILABLE")
    q_fresh = safe_value(row, ["evidence_freshness_status"], "NOT AVAILABLE")
    q_cov = safe_value(row, ["evidence_coverage_pct"], "NOT AVAILABLE")
    q_deg = safe_value(row, ["evidence_degraded_count"], "NOT AVAILABLE")
    st.caption(
        f"Evidence quality is published research metadata: quality={q_quality}, "
        f"coverage={q_cov}%, freshness={q_fresh}, PIT={q_pit}, degraded={q_deg}. "
        "It describes evidence fitness and exclusions only; it is not a forecast, "
        "trading signal, recommendation, or execution input."
    )

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
    regime_df, regime_src = load_named("Economic Regime")
    surprise_df, surprise_src = load_named("Economic Surprise")
    events_df, events_src = load_named("Economic Historical Events")
    quality_df, quality_src = load_named("Economic Quality")

    if not isinstance(regime_df, pd.DataFrame) or regime_df.empty:
        st.warning("Economic Regime is not published or is currently unavailable.")
        source("Economic Regime", regime_src)
        return

    st.caption(
        "Point-in-time research view of inflation, labor and growth evidence. "
        "YoY describes the broader price trend; MoM describes latest momentum. "
        "Release shocks are not consensus surprises unless a published consensus is explicitly available."
    )

    row = latest_row(regime_df)
    as_of = safe_value(row, ["release_date"])
    regime = safe_value(row, ["economic_regime"])
    pit_safe = safe_value(row, ["pit_safe"])
    research_only = safe_value(row, ["research_only"])

    dims = {
        "Inflation": {"score": safe_value(row, ["inflation_score"], None), "indicators": safe_value(row, ["inflation_indicators"], "—"), "age": safe_value(row, ["inflation_age_days"], None)},
        "Labor": {"score": safe_value(row, ["labor_score"], None), "indicators": safe_value(row, ["labor_indicators"], "—"), "age": safe_value(row, ["labor_age_days"], None)},
        "Growth": {"score": safe_value(row, ["growth_score"], None), "indicators": safe_value(row, ["growth_indicators"], "—"), "age": safe_value(row, ["growth_age_days"], None)},
    }

    def _direction(value: Any) -> tuple[str, str]:
        if not isinstance(value, (int, float)):
            return "—", "Unavailable"
        if value >= 0.15:
            return "↑", "Positive directional pressure"
        if value <= -0.15:
            return "↓", "Negative directional pressure"
        return "→", "Near neutral"

    def _latest_release(indicator: str) -> Optional[pd.Series]:
        if not isinstance(surprise_df, pd.DataFrame) or surprise_df.empty or "indicator" not in surprise_df.columns:
            return None
        subset = surprise_df[surprise_df["indicator"].astype(str).eq(indicator)].copy()
        if subset.empty:
            return None
        subset["_date"] = pd.to_datetime(subset.get("release_date"), errors="coerce")
        return subset.sort_values("_date").iloc[-1]

    def _release_interpretation(indicator: str, shock: Any) -> str:
        if not isinstance(shock, (int, float)) or pd.isna(shock) or abs(float(shock)) < 1e-12:
            return "Little directional change versus the prior reference."
        positive = float(shock) > 0
        if indicator in {"CPI", "CORE_CPI", "PPI_FINAL_DEMAND", "CORE_PPI", "PCE_PRICE_INDEX", "CORE_PCE"}:
            return "Inflation pressure stronger." if positive else "Inflation pressure softer."
        if indicator in {"NFP", "AVERAGE_HOURLY_EARNINGS"}:
            return "Labor evidence firmer." if positive else "Labor evidence softer."
        if indicator in {"INITIAL_JOBLESS_CLAIMS", "UNEMPLOYMENT_RATE"}:
            return "Labor evidence firmer." if positive else "Labor evidence softer."
        if indicator in {"GDP", "ISM_MANUFACTURING_PMI", "ISM_SERVICES_PMI", "RETAIL_SALES", "RETAIL_SALES_EX_AUTOS"}:
            return "Growth / demand momentum firmer." if positive else "Growth / demand momentum softer."
        return "Positive directional release shock." if positive else "Negative directional release shock."

    # Economic Pulse ----------------------------------------------------
    st.subheader("Economic Pulse")
    headline_parts = []
    for name, data in dims.items():
        arrow, _ = _direction(data["score"])
        score_text = f"{data['score']:+.2f}" if isinstance(data["score"], (int, float)) else "—"
        headline_parts.append(f"{name} {arrow} {score_text}")
    st.markdown(
        f"<div class='econ-pulse'><div class='label'>CURRENT ECONOMIC REGIME</div>"
        f"<div class='econ-regime'>{fmt(regime)}</div>"
        f"<div class='econ-sub'>As of {fmt(as_of)} · {' · '.join(headline_parts)} · PIT {fmt(pit_safe)}</div></div>",
        unsafe_allow_html=True,
    )

    # What changed: use z-score when mature, otherwise release-shock magnitude.
    st.subheader("What Changed?")
    recent = None
    if isinstance(surprise_df, pd.DataFrame) and not surprise_df.empty:
        recent = surprise_df.copy()
        recent["_date"] = pd.to_datetime(recent.get("release_date"), errors="coerce")
        recent["_z"] = pd.to_numeric(recent.get("directional_zscore"), errors="coerce")
        recent["_shock"] = pd.to_numeric(recent.get("directional_release_shock"), errors="coerce")
        newest = recent["_date"].max()
        if pd.notna(newest):
            recent = recent[recent["_date"] >= newest - pd.Timedelta(days=14)]
        recent["_materiality"] = recent["_z"].abs().where(recent["_z"].notna(), recent["_shock"].abs())
        recent = recent.sort_values(["_materiality", "_date"], ascending=[False, False]).head(3)

    if isinstance(recent, pd.DataFrame) and not recent.empty:
        cols = st.columns(len(recent))
        for col, (_, release) in zip(cols, recent.iterrows()):
            indicator = str(release.get("indicator", "—"))
            actual = release.get("actual")
            previous = release.get("delta_reference_value")
            if pd.isna(previous):
                previous = release.get("previous")
            delta = release.get("release_delta")
            shock = release.get("directional_release_shock")
            arrow = "▲" if isinstance(shock, (int, float)) and not pd.isna(shock) and shock > 0 else "▼" if isinstance(shock, (int, float)) and not pd.isna(shock) and shock < 0 else "→"
            delta_text = f"{delta:+.1f}" if isinstance(delta, (int, float)) and not pd.isna(delta) else "—"
            with col:
                st.markdown(
                    f"<div class='signal-card'><div class='signal-title'>{indicator.replace('_', ' ')}</div>"
                    f"<div class='signal-main'>{fmt(previous, 1)} → {fmt(actual, 1)} &nbsp; {arrow} {delta_text}</div>"
                    f"<div class='signal-why'>{_release_interpretation(indicator, shock)}<br>"
                    f"{fmt(release.get('release_date'))} · {fmt(release.get('zscore_class'))}</div></div>",
                    unsafe_allow_html=True,
                )
    else:
        st.info("No recent release-shock evidence is available.")

    # Bottom line -------------------------------------------------------
    inflation, labor, growth = dims["Inflation"]["score"], dims["Labor"]["score"], dims["Growth"]["score"]
    statements = []
    if isinstance(inflation, (int, float)):
        statements.append("inflation pressure is relatively firm" if inflation >= .15 else "inflation pressure is relatively soft" if inflation <= -.15 else "inflation is near neutral")
    if isinstance(labor, (int, float)):
        statements.append("labor evidence is firm" if labor >= .15 else "labor evidence is soft" if labor <= -.15 else "labor remains close to neutral")
    if isinstance(growth, (int, float)):
        statements.append("growth evidence is firm" if growth >= .15 else "growth evidence is softer" if growth <= -.15 else "growth remains close to neutral")
    bottom = "; ".join(statements) + "." if statements else "Dimension evidence is unavailable."
    st.subheader("Economic Bottom Line")
    st.markdown(
        f"<div class='econ-bottom'><div class='label'>CURRENT READ</div><div class='value'>{fmt(regime)}</div>"
        f"<div class='small'>{bottom.capitalize()} This is a research classification, not a market forecast.</div></div>",
        unsafe_allow_html=True,
    )

    # Detailed live indicator groups -----------------------------------
    st.subheader("Economic Indicator Pulse")
    st.caption("Price indicators show YoY trend and MoM momentum when both are published. ISM is a diffusion-index level; Retail Sales uses MoM as the primary momentum reading.")
    groups = [
        ("INFLATION", ["CPI", "CORE_CPI", "PPI_FINAL_DEMAND", "CORE_PPI", "PCE_PRICE_INDEX", "CORE_PCE"]),
        ("LABOR", ["NFP", "UNEMPLOYMENT_RATE", "INITIAL_JOBLESS_CLAIMS", "AVERAGE_HOURLY_EARNINGS"]),
        ("GROWTH & DEMAND", ["RETAIL_SALES", "RETAIL_SALES_EX_AUTOS", "ISM_MANUFACTURING_PMI", "ISM_SERVICES_PMI", "GDP"]),
    ]
    group_cols = st.columns(3)
    for col, (group_name, indicators) in zip(group_cols, groups):
        lines = []
        for indicator in indicators:
            release = _latest_release(indicator)
            if release is None:
                continue
            label = indicator.replace("_", " ")
            mom, yoy, level = release.get("mom"), release.get("yoy"), release.get("level")
            parts = []
            if isinstance(yoy, (int, float)) and not pd.isna(yoy):
                parts.append(f"<b>{yoy:.1f}% YoY</b>")
            if isinstance(mom, (int, float)) and not pd.isna(mom):
                parts.append(f"{mom:+.1f}% MoM")
            if indicator.startswith("ISM_"):
                val = level if isinstance(level, (int, float)) and not pd.isna(level) else release.get("actual")
                if isinstance(val, (int, float)) and not pd.isna(val):
                    parts = [f"<b>{val:.1f}</b> · {'Expansion' if val >= 50 else 'Contraction'}"]
            if not parts:
                actual = release.get("actual")
                parts = [f"<b>{fmt(actual, 1)}</b>"]
            zclass = str(release.get('zscore_class') or '').strip().upper()
            context = fmt(release.get('release_date'))
            if zclass and zclass not in {'INSUFFICIENT_HISTORY', 'NOT_AVAILABLE', 'NONE', 'NAN'}:
                context += f" · {zclass}"
            if indicator == "RETAIL_SALES" and str(release.get("price_adjusted")).lower() in {"false", "0", "no"}:
                context += " · nominal / not price-adjusted"
            lines.append(f"<div class='econ-indicator'><b>{label}</b><div class='econ-reading'>{' · '.join(parts)}</div><div class='econ-context'>{context}</div></div>")
        if not lines:
            lines = ["<div class='econ-context'>No published evidence.</div>"]
        with col:
            st.markdown(f"<div class='econ-group'><div class='econ-group-title'>{group_name}</div>{''.join(lines)}</div>", unsafe_allow_html=True)
    st.caption("Newly integrated series are shown from published releases. Historical normalization activates only after sufficient point-in-time history is available.")

    # Dimension pulse ---------------------------------------------------
    st.subheader("Dimension Pulse")
    cols = st.columns(3)
    for col, (name, data) in zip(cols, dims.items()):
        arrow, direction = _direction(data["score"])
        score_text = f"{data['score']:+.2f}" if isinstance(data["score"], (int, float)) else "—"
        age_text = f"{int(data['age'])} days" if isinstance(data["age"], (int, float)) else "Unavailable"
        indicators = str(data["indicators"]).replace("|", " · ")
        with col:
            st.markdown(
                f"<div class='econ-dim'><div class='label'>{name.upper()}</div>"
                f"<div class='score'>{arrow} {score_text}</div>"
                f"<div class='small'>{direction}<br>{indicators}<br>Freshness: {age_text}</div></div>",
                unsafe_allow_html=True,
            )

    # Latest releases ---------------------------------------------------
    st.subheader("Latest Economic Releases")
    if isinstance(surprise_df, pd.DataFrame) and not surprise_df.empty:
        releases = surprise_df.copy()
        releases["_date"] = pd.to_datetime(releases.get("release_date"), errors="coerce")
        releases = releases.sort_values("_date", ascending=False).head(8)
        for _, release in releases.iterrows():
            indicator = str(release.get("indicator", "—"))
            shock, z = release.get("directional_release_shock"), release.get("directional_zscore")
            actual = release.get("actual")
            previous = release.get("delta_reference_value")
            if pd.isna(previous):
                previous = release.get("previous")
            extra = []
            if isinstance(release.get("yoy"), (int, float)) and not pd.isna(release.get("yoy")):
                extra.append(f"YoY {release.get('yoy'):.1f}%")
            if isinstance(release.get("mom"), (int, float)) and not pd.isna(release.get("mom")):
                extra.append(f"MoM {release.get('mom'):+.1f}%")
            extra_text = " · " + " · ".join(extra) if extra else ""
            st.markdown(
                f"<div class='econ-release'><div class='name'>{indicator.replace('_', ' ')}</div>"
                f"<div>{fmt(previous, 1)} → <b>{fmt(actual, 1)}</b> · Release Δ {fmt(release.get('release_delta'), 1)}{extra_text}</div>"
                f"<div class='meta'>{fmt(release.get('release_date'))} · Directional shock {fmt(shock, 2)} · z {fmt(z, 2)} · {fmt(release.get('zscore_class'))}</div></div>",
                unsafe_allow_html=True,
            )
            url = release.get("source_url")
            if isinstance(url, str) and url.startswith("http"):
                st.markdown(f"[Official source]({url})")
        if surprise_df.get("consensus_method") is not None and surprise_df["consensus_method"].astype(str).eq("NOT_AVAILABLE").any():
            st.caption("Consensus comparison is unavailable for releases whose published evidence set reports consensus_method = NOT_AVAILABLE. No beat/miss claim is inferred.")
    else:
        st.info("Economic release data is unavailable.")

    st.caption(
        f"Economic Regime: {source_status(regime_src)} · Release Engine: {source_status(surprise_src)} · "
        f"PIT Safe: {fmt(pit_safe)} · Research Only: {fmt(research_only)}"
    )

    st.subheader("Research Detail")
    with st.expander("Regime history"):
        table(regime_df.tail(250), 480)
        source("Economic Regime", regime_src)
    with st.expander("Release Shock / Surprise Engine data"):
        st.caption("Consensus fields are displayed as published. NOT_AVAILABLE is never converted into a beat/miss claim.")
        table(surprise_df.tail(300) if isinstance(surprise_df, pd.DataFrame) else None, 520)
        source("Economic Surprise", surprise_src)
    with st.expander("Historical events"):
        table(events_df.tail(300) if isinstance(events_df, pd.DataFrame) else None, 520)
        source("Economic Historical Events", events_src)
    with st.expander("Data quality"):
        table(quality_df, 420)
        source("Economic Quality", quality_src)

def fed() -> None:
    st.header("Fed Intelligence")
    obj, src = load_named("Fed Intelligence")

    if not isinstance(obj, dict) or not obj.get("available", False):
        st.warning("Fed Intelligence is not published or is currently unavailable.")
        source("Fed Intelligence", src)
        return

    st.caption(
        "Research-only interpretation of official Federal Reserve communications. "
        "Scores are analytical indicators, not probabilities or trading signals."
    )

    fed_score = obj.get("fed_score") if isinstance(obj.get("fed_score"), dict) else {}
    sep_shift = obj.get("sep_shift") if isinstance(obj.get("sep_shift"), dict) else {}
    phase = obj.get("phase_2b") if isinstance(obj.get("phase_2b"), dict) else {}
    score = fed_score.get("score")
    classification = fed_score.get("classification", "UNAVAILABLE")
    sep_direction = sep_shift.get("classification", "Not available")

    header_cols = st.columns(3)
    for col, (label, value) in zip(header_cols, [
        ("As of", obj.get("as_of_date")),
        ("Latest FOMC", obj.get("latest_fomc")),
        ("Fed Chair", obj.get("fed_chair")),
    ]):
        with col:
            card(label, value)

    # --- Policy pulse: visual first ------------------------------------
    st.subheader("Policy Pulse")
    if isinstance(score, (int, float)):
        marker = max(0.0, min(100.0, float(score)))
        st.markdown(
            f"<div class='fed-strip'><div class='kicker'>FED POLICY SCORE</div>"
            f"<div class='headline'>{score:.1f}/100 · {fmt(classification)} · {fmt(sep_direction)}</div>"
            f"<div class='fed-gauge'><span class='fed-marker' style='left:calc({marker:.1f}% - 2px)'></span></div>"
            "<div class='fed-scale'><span>DOVISH</span><span>NEUTRAL · 50</span><span>HAWKISH</span></div>"
            "<div class='detail' style='margin-top:8px'>Descriptive research gauge — not a policy probability or trading signal.</div></div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("A policy score is not available for the current evidence set.")

    # --- SEP changes ----------------------------------------------------
    fields = sep_shift.get("fields") if isinstance(sep_shift.get("fields"), dict) else {}
    labels = {
        "gdp": "GDP", "unemployment": "Unemployment", "pce": "PCE",
        "core_pce": "Core PCE", "fed_funds": "Fed Funds",
    }
    explanations = {
        "gdp": ("growth outlook stronger", "growth outlook softer"),
        "unemployment": ("labor outlook softer", "labor outlook stronger"),
        "pce": ("inflation path higher", "inflation path lower"),
        "core_pce": ("core inflation path higher", "core inflation path lower"),
        "fed_funds": ("higher policy-rate path", "lower policy-rate path"),
    }
    changes = []
    for key, label in labels.items():
        detail = fields.get(key) if isinstance(fields.get(key), dict) else {}
        change = detail.get("change")
        if isinstance(change, (int, float)):
            changes.append((abs(change), key, label, detail))
    changes.sort(reverse=True, key=lambda x: x[0])

    st.subheader("What Changed?")
    if changes:
        change_cols = st.columns(min(3, len(changes)))
        for col, (_, key, label, detail) in zip(change_cols, changes[:3]):
            delta = detail.get("change")
            prev = detail.get("previous")
            cur = detail.get("current")
            arrow = "▲" if delta > 0 else "▼" if delta < 0 else "→"
            if key == "unemployment":
                implication = "Hawkish" if delta < 0 else "Dovish" if delta > 0 else "Neutral"
                why = explanations[key][1] if delta < 0 else explanations[key][0]
            else:
                implication = "Hawkish" if delta > 0 else "Dovish" if delta < 0 else "Neutral"
                why = explanations[key][0] if delta > 0 else explanations[key][1]
            with col:
                st.markdown(
                    f"<div class='signal-card'><div class='signal-title'>{label}</div>"
                    f"<div class='signal-main'>{fmt(prev,1)} → {fmt(cur,1)} &nbsp; {arrow} {delta:+.1f}</div>"
                    f"<div class='signal-why'><b>{implication.upper()}</b> · {why}</div></div>",
                    unsafe_allow_html=True,
                )
    else:
        st.info("No comparable SEP changes are available for this snapshot.")

    # --- Bottom line: move decision read near the top ------------------
    top_change = changes[0] if changes else None
    if top_change:
        _, top_key, top_label, top_detail = top_change
        top_delta = top_detail.get("change")
        top_reason = explanations[top_key][0] if top_delta > 0 else explanations[top_key][1]
        change_text = f"Largest SEP move: {top_label} {top_delta:+.1f} ({top_reason})."
    else:
        change_text = "No comparable SEP shift is available."
    minutes_payload = obj.get("minutes") if isinstance(obj.get("minutes"), dict) else {}
    minutes_status = (obj.get("document_status") or {}).get("minutes", {}) if isinstance(obj.get("document_status"), dict) else {}
    if minutes_payload.get("available"):
        minutes_date = obj.get("minutes_meeting_date") or minutes_status.get("meeting_date")
        if minutes_status.get("lagged"):
            minutes_text = f"Latest published Minutes ({fmt(minutes_date)}) are incorporated as lagged evidence for the prior meeting."
        else:
            minutes_text = f"Minutes ({fmt(minutes_date)}) are incorporated."
    else:
        minutes_text = "Minutes are pending and are not treated as evidence."
    st.markdown(
        f"<div class='bottom-line'><div class='title'>FED BOTTOM LINE</div>"
        f"<div class='read'>{fmt(classification)} · {fmt(sep_direction)}</div>"
        f"<div class='body'>Fed Policy Score: {fmt(score,1)}. {change_text} {minutes_text} "
        "Beige Book remains contextual rather than a direct score input.</div></div>",
        unsafe_allow_html=True,
    )

    # --- Compact communication evidence --------------------------------
    weights = phase.get("document_weights") if isinstance(phase.get("document_weights"), dict) else {}
    availability_meta = phase.get("document_availability") if isinstance(phase.get("document_availability"), dict) else {}
    score_eligibility = phase.get("document_score_eligibility") if isinstance(phase.get("document_score_eligibility"), dict) else {}
    communication = [
        ("Statement", "statement", obj.get("statement"), obj.get("statement_source")),
        ("Press Conference", "chair", obj.get("chair_press"), obj.get("chair_page") or obj.get("chair_pdf")),
        ("Minutes", "minutes", obj.get("minutes"), obj.get("minutes_source")),
    ]
    st.subheader("FOMC Communication")
    minutes_status = (obj.get("document_status") or {}).get("minutes", {}) if isinstance(obj.get("document_status"), dict) else {}
    if minutes_status.get("available") and minutes_status.get("lagged"):
        st.caption(
            f"Latest published FOMC Minutes cover the {fmt(minutes_status.get('meeting_date'))} meeting; "
            f"the latest FOMC meeting is {fmt(minutes_status.get('latest_fomc_date'))}. "
            "They are retained as lagged research evidence and are not relabeled as current-meeting minutes."
        )
    timeline_bits = []
    for label, _, payload, _ in communication:
        payload = payload if isinstance(payload, dict) else {}
        timeline_bits.append(f"{label} {'✓' if payload.get('available') else '⏳'}")
    st.markdown(f"<div class='timeline'>{' &nbsp; ─── &nbsp; '.join(timeline_bits)}</div>", unsafe_allow_html=True)
    for label, key, payload, url in communication:
        payload = payload if isinstance(payload, dict) else {}
        available = bool(payload.get("available"))
        tone = fmt(payload.get("tone")) if available else "PENDING"
        explicit_weight = weights.get(key)
        explicit_availability = availability_meta.get(key)
        scoring_key = "chair" if key == "chair" else key
        explicit_score_eligible = score_eligibility.get(scoring_key)
        if explicit_score_eligible is False and available:
            note = "lagged evidence · excluded from current-meeting score"
        elif isinstance(explicit_weight, (int, float)):
            note = f"score weight {explicit_weight * 100:.1f}%" if explicit_weight > 0 else "excluded from score"
        elif explicit_availability is False or not available:
            note = "excluded until published"
        else:
            note = "included · weight metadata pending refresh"
        link = f" · <a href='{url}' target='_blank'>official source</a>" if url else ""
        st.markdown(
            f"<div class='comm-row'><span><span class='comm-name'>{label}</span> "
            f"<span class='comm-note'>{link}</span></span>"
            f"<span><span class='comm-state'>{tone}</span><br><span class='comm-note'>{note}</span></span></div>",
            unsafe_allow_html=True,
        )

    # --- SEP pulse ------------------------------------------------------
    st.subheader("SEP Pulse — Current vs Previous")
    current = obj.get("sep_current") if isinstance(obj.get("sep_current"), dict) else {}
    previous = obj.get("sep_previous") if isinstance(obj.get("sep_previous"), dict) else {}
    for key, label in labels.items():
        detail = fields.get(key) if isinstance(fields.get(key), dict) else {}
        cur = detail.get("current", current.get(key))
        prev = detail.get("previous", previous.get(key))
        delta = detail.get("change")
        arrow = "▲" if isinstance(delta, (int, float)) and delta > 0 else "▼" if isinstance(delta, (int, float)) and delta < 0 else "→"
        delta_text = f"{delta:+.1f}" if isinstance(delta, (int, float)) else "—"
        st.markdown(
            f"<div class='pulse'><span class='pulse-name'>{label}</span>"
            f"<span class='pulse-value'>{fmt(prev,1)} → {fmt(cur,1)} &nbsp; {arrow}</span>"
            f"<span class='pulse-note'>Δ {delta_text}</span></div>",
            unsafe_allow_html=True,
        )
    st.caption(
        f"Current SEP: {fmt(obj.get('latest_sep_date'))} • Previous SEP: {fmt(obj.get('previous_sep_date'))} • "
        f"Directional shift: {fmt(sep_direction)}. SEP is a directional comparison, not a policy probability."
    )

    # --- Communication current vs previous -----------------------------
    comparison = obj.get("communication_comparison") if isinstance(obj.get("communication_comparison"), dict) else {}
    st.subheader("Communication — Current vs Previous")
    comparison_rows = []
    for key, label in (("statement", "FOMC Statement"), ("minutes", "FOMC Minutes"), ("chair_press", "Press Conference")):
        item = comparison.get(key) if isinstance(comparison.get(key), dict) else {}
        comp = item.get("comparison") if isinstance(item.get("comparison"), dict) else {}
        previous_doc = item.get("previous") if isinstance(item.get("previous"), dict) else {}
        current_doc = obj.get("chair_press" if key == "chair_press" else key)
        current_doc = current_doc if isinstance(current_doc, dict) else {}
        comparison_rows.append({
            "Report": label, "Current": item.get("current_date"), "Previous": item.get("previous_date"),
            "Current tone": current_doc.get("tone", "UNAVAILABLE"), "Previous tone": previous_doc.get("tone", "UNAVAILABLE"),
            "Change": comp.get("classification", "UNAVAILABLE"),
        })
    st.dataframe(pd.DataFrame(comparison_rows), use_container_width=True, hide_index=True)
    st.caption("Unavailable or not-yet-published reports remain unavailable; they are never converted into neutral evidence.")

    # --- Synthesis ------------------------------------------------------
    combined = phase.get("combined") if isinstance(phase.get("combined"), dict) else {}
    st.subheader("Fed Synthesis")
    if minutes_status.get("available") and minutes_status.get("lagged"):
        st.caption(
            "Current-meeting synthesis uses the current Statement and Press Conference plus the current SEP. "
            "The latest published Minutes remain visible for research comparison but are excluded from the current-meeting score because they cover the prior meeting."
        )
    if combined:
        for name, data in combined.items():
            if not isinstance(data, dict):
                continue
            dim_score = data.get("score_100")
            dim_label = str(name).replace("_", " ").title()
            if isinstance(dim_score, (int, float)):
                direction = "Hawkish tilt" if dim_score > 52 else "Dovish tilt" if dim_score < 48 else "Balanced"
                c1, c2 = st.columns([1, 3])
                with c1:
                    st.markdown(f"**{dim_label}**")
                    st.caption(f"{dim_score:.1f} · {direction}")
                with c2:
                    st.progress(max(0, min(100, int(round(dim_score)))))
        reasons = phase.get("reasons")
        if isinstance(reasons, list) and reasons:
            with st.expander("Evidence behind the synthesis"):
                for reason in reasons:
                    st.write(reason)
    else:
        st.info("Dimension-level synthesis is not available in the current artifact.")

    # --- Beige Book -----------------------------------------------------
    st.subheader("Beige Book Context")
    beige = obj.get("beige_book") if isinstance(obj.get("beige_book"), dict) else {}
    beige_analysis = obj.get("beige_analysis") if isinstance(obj.get("beige_analysis"), dict) else {}
    if not beige.get("available"):
        st.info("Beige Book is not available for the current as-of date.")
    else:
        beige_cols = st.columns(4)
        for col, (label, value) in zip(beige_cols, [
            ("Issue", beige.get("issue_date")), ("Published", beige.get("publication_date")),
            ("Tone", beige_analysis.get("tone")), ("Context Score", beige_analysis.get("score")),
        ]):
            with col:
                card(label, value)
        dimensions = beige_analysis.get("dimensions")
        if isinstance(dimensions, dict) and dimensions:
            with st.expander("Beige Book dimension detail"):
                for name, data in dimensions.items():
                    if not isinstance(data, dict):
                        continue
                    dscore = data.get("score_100")
                    st.write(f"**{str(name).replace('_', ' ').title()}** — {fmt(dscore)}")
                    if isinstance(dscore, (int, float)):
                        st.progress(max(0, min(100, int(round(dscore)))))
        if beige.get("url"):
            st.markdown(f"[Official Beige Book source]({beige.get('url')})")
        st.caption("Beige Book is contextual evidence and is not included directly in the Fed Policy Score.")

    quality = obj.get("quality") if isinstance(obj.get("quality"), dict) else {}
    st.subheader("Fed Evidence Quality")
    qcols = st.columns(4)
    for col, (label, value) in zip(qcols, [
        ("Quality Gate", quality.get("quality_gate", "UNKNOWN")),
        ("PIT", quality.get("pit_status", "UNKNOWN")),
        ("Freshness", quality.get("freshness_status", "UNKNOWN")),
        ("Role", quality.get("decision_role", "CONTEXTUAL")),
    ]):
        with col:
            card(label, value)
    if quality.get("quality_reason"):
        st.caption(f"Quality note: {quality.get('quality_reason')}. Quality metadata does not alter the Fed analytical score.")

    with st.expander("View detailed data"):
        sep_rows = []
        for key, label in labels.items():
            detail = fields.get(key) if isinstance(fields.get(key), dict) else {}
            sep_rows.append({
                "Projection": label, "Previous": detail.get("previous", previous.get(key)),
                "Current": detail.get("current", current.get(key)), "Change": detail.get("change"),
            })
        st.dataframe(pd.DataFrame(sep_rows), use_container_width=True, hide_index=True)

    with st.expander("Complete Fed JSON"):
        st.json(obj)
    source("Fed Intelligence", src)

def _delta_text(value: Any, suffix: str = "") -> str:
    if not isinstance(value, (int, float)) or pd.isna(value):
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}{suffix}"


def _research_footer(df: Optional[pd.DataFrame], pit_field: str = "point_in_time_safe") -> None:
    row = latest_row(df)
    pit = safe_value(row, [pit_field], "—")
    st.caption(f"Research-only • PIT status: {fmt(pit)} • No forecast, trading signal, or execution is generated by this view.")


def financial_stress() -> None:
    st.header("Financial Stress Intelligence")
    df, src = load_named("Financial Stress")
    row = latest_row(df)
    if row is None:
        st.info("Financial-stress research is unavailable."); return
    score = safe_value(row, ["composite_stress_score"], None)
    regime = safe_value(row, ["research_regime"], "UNAVAILABLE")
    cols = st.columns(4)
    for col, item in zip(cols, [("Current State", regime), ("Composite Stress", score), ("VIX", safe_value(row,["VIX"])), ("Yield 10Y−2Y", safe_value(row,["YIELD_10Y_2Y_SPREAD"]))]):
        with col: card(*item)
    st.subheader("Stress Drivers")
    drivers=[("VIX",safe_value(row,["VIX_Z"],None)),("NFCI",safe_value(row,["NFCI_Z"],None)),("ANFCI",safe_value(row,["ANFCI_Z"],None)),("Yield Curve",safe_value(row,["YIELD_CURVE_STRESS_Z"],None))]
    cols=st.columns(4)
    for col,(name,z) in zip(cols,drivers):
        note="Above normal stress" if isinstance(z,(int,float)) and z>0.5 else "Below normal stress" if isinstance(z,(int,float)) and z<-0.5 else "Near normal"
        with col: card(name, f"z {z:.2f}" if isinstance(z,(int,float)) else "—", note)
    st.subheader("Stress Trend")
    chart(df,["composite_stress_score"])
    st.markdown(f"<div class='fed-strip'><div class='kicker'>BOTTOM LINE</div><div class='headline'>{fmt(regime)}</div><div class='detail'>Composite stress is {fmt(score)}. Component z-scores show where current pressure is concentrated; this is descriptive research, not a market signal.</div></div>",unsafe_allow_html=True)
    with st.expander("View detailed data"): table(df.tail(250),420)
    source("Financial Stress",src); _research_footer(df)


def liquidity() -> None:
    st.header("Liquidity Intelligence")
    df, src = load_named("Liquidity"); row=latest_row(df)
    if row is None: st.info("Liquidity research is unavailable."); return
    st.caption("Research view of balance-sheet liquidity and money-market conditions. No liquidity score is invented where the published artifact does not provide one.")
    cols=st.columns(4)
    items=[("Net Liquidity Proxy",safe_value(row,["NET_LIQUIDITY_PROXY_MILLIONS"]),"USD millions"),("Fed Assets",safe_value(row,["FED_TOTAL_ASSETS"]),safe_value(row,["FED_TOTAL_ASSETS_DIRECTION_30D"])),("Reserve Balances",safe_value(row,["RESERVE_BALANCES"]),safe_value(row,["RESERVE_BALANCES_DIRECTION_30D"])),("TGA",safe_value(row,["TREASURY_GENERAL_ACCOUNT"]),safe_value(row,["TREASURY_GENERAL_ACCOUNT_DIRECTION_30D"]))]
    for col,(a,b,c) in zip(cols,items):
        with col: card(a,b,c)
    st.subheader("30-Day Liquidity Pulse")
    pulse=[("Fed Assets",safe_value(row,["FED_TOTAL_ASSETS_PCT_CHANGE_30D"],None),safe_value(row,["FED_TOTAL_ASSETS_DIRECTION_30D"])),("Reserves",safe_value(row,["RESERVE_BALANCES_PCT_CHANGE_30D"],None),safe_value(row,["RESERVE_BALANCES_DIRECTION_30D"])),("TGA",safe_value(row,["TREASURY_GENERAL_ACCOUNT_PCT_CHANGE_30D"],None),safe_value(row,["TREASURY_GENERAL_ACCOUNT_DIRECTION_30D"])),("ON RRP",safe_value(row,["ON_RRP_PCT_CHANGE_30D"],None),safe_value(row,["ON_RRP_DIRECTION_30D"]))]
    cols=st.columns(4)
    for col,(name,val,direction) in zip(cols,pulse):
        with col: card(name,_delta_text(val,"%"),str(direction))
    st.subheader("Money-Market Conditions")
    cols=st.columns(3)
    for col,item in zip(cols,[("EFFR",safe_value(row,["EFFR"]),safe_value(row,["EFFR_DIRECTION_30D"])),("SOFR",safe_value(row,["SOFR"]),safe_value(row,["SOFR_DIRECTION_30D"])),("SOFR−EFFR",safe_value(row,["SOFR_EFFR_SPREAD_BPS"]),"basis points")]):
        with col: card(*item)
    st.markdown("<div class='fed-strip'><div class='kicker'>BOTTOM LINE</div><div class='headline'>DESCRIPTIVE LIQUIDITY VIEW</div><div class='detail'>The published artifact explicitly disables a liquidity score and Decision Engine readiness. The view therefore surfaces levels and changes without converting them into a synthetic signal.</div></div>",unsafe_allow_html=True)
    with st.expander("View detailed data"): table(df.tail(180),420)
    source("Liquidity",src); _research_footer(df)


def sentiment() -> None:
    st.header("Sentiment Intelligence")
    rc, rc_src=load_named("Research Context Summary"); rr=latest_row(rc)
    aaii,a_src=load_named("AAII"); ar=latest_row(aaii)
    vix,v_src=load_named("VIX"); vr=latest_row(vix)
    cot,c_src=load_named("COT"); cr=latest_row(cot)
    cols=st.columns(4)
    for col,item in zip(cols,[("Unified Context",safe_value(rr,["sentiment_regime"]),safe_value(rr,["unified_sentiment_score"])),("AAII",safe_value(ar,["research_regime"]),f"Spread {fmt(safe_value(ar,['bull_bear_spread_pp']))} pp"),("VIX",safe_value(vr,["research_regime"]),f"{fmt(safe_value(vr,['VIX']))} · pctile {fmt(safe_value(vr,['VIX_percentile']))}"),("COT Asset Managers",safe_value(cr,["asset_manager_research_regime"]),f"Net {fmt(safe_value(cr,['asset_manager_net']))}")]):
        with col: card(*item)
    st.subheader("Sentiment Cross-Check")
    cols=st.columns(3)
    with cols[0]: card("AAII Bulls / Bears",f"{fmt(safe_value(ar,['bullish_pct']))}% / {fmt(safe_value(ar,['bearish_pct']))}%",f"Weekly spread Δ {fmt(safe_value(ar,['bull_bear_spread_weekly_change_pp']))} pp")
    with cols[1]: card("VIX",safe_value(vr,["VIX"]),f"z {fmt(safe_value(vr,['VIX_z']))} · percentile {fmt(safe_value(vr,['VIX_percentile']))}")
    with cols[2]: card("Leveraged Money",safe_value(cr,["leveraged_money_research_regime"]),f"Net {fmt(safe_value(cr,['leveraged_money_net']))} · pctile {fmt(safe_value(cr,['leveraged_money_net_percentile']))}")
    st.markdown(f"<div class='fed-strip'><div class='kicker'>BOTTOM LINE</div><div class='headline'>{fmt(safe_value(rr,['sentiment_regime']))}</div><div class='detail'>AAII, VIX and COT are shown as independent research lenses. Divergence between them is preserved rather than forced into a new score.</div></div>",unsafe_allow_html=True)
    with st.expander("AAII detail"): table(aaii.tail(100),360)
    with st.expander("VIX detail"): table(vix.tail(180),360)
    with st.expander("COT detail"): table(cot.tail(100),360)
    st.caption(f"Sources: AAII={source_status(a_src)} • VIX={source_status(v_src)} • COT={source_status(c_src)} • Context={source_status(rc_src)}")


def technical() -> None:
    st.header("Technical Intelligence")
    df,src=load_named("Technical"); row=latest_row(df)
    if row is None: st.info("Technical research is unavailable."); return
    cols=st.columns(4)
    for col,item in zip(cols,[("Regime",safe_value(row,["technical_regime"]),safe_value(row,["trend_structure"])),("S&P 500",safe_value(row,["Close"]),latest_date(df)),("RSI 14",safe_value(row,["RSI14"]),"momentum"),("Drawdown",safe_value(row,["drawdown_pct"]),"from running high")]):
        with col: card(*item)
    st.subheader("Trend Structure")
    cols=st.columns(3)
    for col,item in zip(cols,[("vs SMA20",safe_value(row,["close_vs_SMA20_pct"]),f"SMA20 slope {fmt(safe_value(row,['SMA20_slope_20d_pct']))}%"),("vs SMA50",safe_value(row,["close_vs_SMA50_pct"]),f"SMA50 slope {fmt(safe_value(row,['SMA50_slope_20d_pct']))}%"),("vs SMA200",safe_value(row,["close_vs_SMA200_pct"]),"long-term distance")]):
        with col: card(item[0],f"{fmt(item[1])}%",item[2])
    st.subheader("Momentum & Risk")
    cols=st.columns(4)
    for col,item in zip(cols,[("ROC 20D",safe_value(row,["ROC20_pct"]),"%"),("ATR 14",safe_value(row,["ATR14_pct"]),"% of index"),("Realized Vol 20D",safe_value(row,["realized_volatility_20d_pct"]),"annualized %"),("20D Breakout",safe_value(row,["breakout_above_prior_20d_high"]),f"Breakdown {fmt(safe_value(row,['breakdown_below_prior_20d_low']))}")]):
        with col: card(item[0],item[1],item[2])
    st.markdown(f"<div class='fed-strip'><div class='kicker'>BOTTOM LINE</div><div class='headline'>{fmt(safe_value(row,['technical_regime']))} · {fmt(safe_value(row,['trend_structure']))}</div><div class='detail'>Technical state is descriptive. The published artifact explicitly generates no technical score, forecast, or trading signal.</div></div>",unsafe_allow_html=True)
    chart(df,["Close"])
    with st.expander("View detailed data"): table(df.tail(180),420)
    source("Technical",src); _research_footer(df)


def breadth() -> None:
    st.header("Market Breadth Intelligence")
    df,src=load_named("Breadth"); row=latest_row(df); summary,ss=load_named("Breadth Summary")
    if row is None: st.info("Breadth research is unavailable."); return
    cols=st.columns(4)
    for col,item in zip(cols,[("Breadth State",safe_value(row,["breadth_research_state"]),latest_date(df)),("Coverage",f"{fmt(safe_value(row,['coverage_pct']))}%",safe_value(row,["coverage_quality"])),("Advancing",f"{fmt(safe_value(row,['pct_advancing']))}%",f"{fmt(safe_value(row,['advances']))} names"),("Declining",f"{fmt(safe_value(row,['pct_declining']))}%",f"{fmt(safe_value(row,['declines']))} names")]):
        with col: card(*item)
    st.subheader("Participation Pulse")
    cols=st.columns(4)
    for col,item in zip(cols,[("Net Advances 1D",safe_value(row,["net_advances"]),f"z {fmt(safe_value(row,['net_advances_z_252d']))}"),("Net Advances 5D",safe_value(row,["net_advances_5d"]),"rolling sum"),("Net Advances 20D",safe_value(row,["net_advances_20d"]),f"z {fmt(safe_value(row,['net_advances_20d_z_252d']))}"),("A/D Line Δ20D",safe_value(row,["ad_line_change_20d"]),f"Δ60D {fmt(safe_value(row,['ad_line_change_60d']))}")]):
        with col: card(*item)
    st.warning("PIT limitation: membership is a free-public historical reconstruction. The published artifact explicitly reports pit_perfect = FALSE; this limitation is preserved in the UI.")
    st.markdown(f"<div class='fed-strip'><div class='kicker'>BOTTOM LINE</div><div class='headline'>{fmt(safe_value(row,['breadth_research_state']))}</div><div class='detail'>Current participation is summarized from the published breadth reconstruction. Structural validation does not make the membership history PIT-perfect.</div></div>",unsafe_allow_html=True)
    chart(df,["cumulative_ad_line","net_advances_20d"])
    with st.expander("View detailed data"): table(df.tail(180),420)
    with st.expander("Breadth validation metadata"):
        if isinstance(summary,dict): st.json(summary)
    source("Breadth",src); source("Breadth Summary",ss)


def cross_asset() -> None:
    st.header("Cross-Asset Intelligence")
    df,src=load_named("Cross Asset"); row=latest_row(df); summary,ss=load_named("Cross Asset Summary")
    if row is None: st.info("Cross-asset research is unavailable."); return
    st.caption("Cross-market confirmation and divergence. No composite risk score is fabricated because the published artifact does not provide one.")
    cols=st.columns(4)
    for col,item in zip(cols,[("Available Assets",safe_value(row,["available_asset_count"]),latest_date(df)),("VIX",safe_value(row,["VIX"]),f"1D {_delta_text(safe_value(row,['VIX_RETURN_1D'],None)*100 if isinstance(safe_value(row,['VIX_RETURN_1D'],None),(int,float)) else None,'%')}"),("US 10Y",safe_value(row,["US10Y"]),f"1D {_delta_text(safe_value(row,['US10Y_RETURN_1D'],None)*100 if isinstance(safe_value(row,['US10Y_RETURN_1D'],None),(int,float)) else None,'%')}"),("DXY",safe_value(row,["DXY"]),f"1D {_delta_text(safe_value(row,['DXY_RETURN_1D'],None)*100 if isinstance(safe_value(row,['DXY_RETURN_1D'],None),(int,float)) else None,'%')}")]):
        with col: card(*item)
    st.subheader("Cross-Market Pulse")
    assets=[("Gold","GOLD"),("WTI","WTI"),("Bitcoin","BITCOIN"),("S&P 500","SP500")]
    cols=st.columns(4)
    for col,(label,key) in zip(cols,assets):
        val=safe_value(row,[key]); ret=safe_value(row,[key+"_RETURN_1D"],None)
        note="Latest session unavailable" if not isinstance(val,(int,float)) or pd.isna(val) else f"1D {_delta_text(ret*100 if isinstance(ret,(int,float)) else None,'%')}"
        with col: card(label,val,note)
    st.subheader("60-Day Correlation Map")
    corrs=[("S&P / Nasdaq","CORR_SP500_NASDAQ_60D"),("S&P / Gold","CORR_SP500_GOLD_60D"),("S&P / DXY","CORR_SP500_DXY_60D"),("S&P / VIX","CORR_SP500_VIX_60D"),("S&P / 10Y","CORR_SP500_US10Y_60D"),("S&P / WTI","CORR_SP500_WTI_60D")]
    cols=st.columns(3)
    for i,(label,key) in enumerate(corrs):
        with cols[i%3]: card(label,safe_value(row,[key]),"rolling Pearson correlation")
    st.markdown("<div class='fed-strip'><div class='kicker'>BOTTOM LINE</div><div class='headline'>CONFIRMATION / DIVERGENCE VIEW</div><div class='detail'>Cross-asset relationships are presented directly from prices, returns, volatility and correlations. Missing same-session equity values are shown as unavailable rather than forward-filled.</div></div>",unsafe_allow_html=True)
    with st.expander("View detailed data"): table(df.tail(180),420)
    with st.expander("Validation metadata"):
        if isinstance(summary,dict): st.json(summary)
    source("Cross Asset",src); source("Cross Asset Summary",ss); _research_footer(df)

def event_news() -> None:
    st.header("Event / News Intelligence V2 — Quality Aware")
    df, src = load_named("Event News")
    summary, ss = load_named("Event News Summary")
    validation, vs = load_named("Event News Validation")
    row = latest_row(df)
    cols=st.columns(5)
    metrics=[("Rows", len(df) if isinstance(df,pd.DataFrame) else "—"),("PIT", safe_value(row,["pit_status","point_in_time_safe"])),("Quality Gate",safe_value(row,["quality_gate"])),("Role",safe_value(row,["decision_role"])),("Research Only",safe_value(row,["research_only"]))]
    for col,(label,value) in zip(cols,metrics):
        with col: card(label,value)
    st.caption("News is structured contextual evidence. Publication chronology, deterministic event class, research relevance and duplicate flags are visible; none is automatically promoted into Decision Engine state scoring.")
    if isinstance(df, pd.DataFrame) and not df.empty:
        rel = df.get("research_relevance", pd.Series(dtype=str)).astype(str).value_counts()
        classes = df.get("event_class", pd.Series(dtype=str)).astype(str).value_counts()
        dups = df.get("is_duplicate", pd.Series(dtype=bool)).astype(str).str.lower().eq("true").sum()
        qcols = st.columns(4)
        for col, item in zip(qcols, [("High relevance", int(rel.get("HIGH",0))), ("Macro releases", int(classes.get("MACRO_RELEASE",0))), ("Policy events", int(classes.get("POLICY_EVENT",0))), ("Duplicates flagged", int(dups))]):
            with col: card(*item)
    table(df.tail(300) if isinstance(df,pd.DataFrame) else None,560); source("Event News",src)
    if isinstance(summary,dict):
        with st.expander("Published summary"): st.json(summary)
    source("Event News Summary",ss)
    if isinstance(validation,dict):
        with st.expander("Validation metadata"): st.json(validation)
    source("Event News Validation",vs)


def earnings() -> None:
    st.header("Corporate Earnings Intelligence V3 — Quality Aware")
    st.caption("Post-event market reactions are contextual historical evidence. They are PIT_LIMITED for a contemporaneous decision snapshot unless their reaction horizon has elapsed.")
    tabs = st.tabs(["Events", "Summary", "EPS Classes", "Sectors"])

    quality, quality_src = load_named("Earnings Quality")
    if isinstance(quality, dict):
        cols = st.columns(5)
        for col, item in zip(cols, [("Rows", quality.get("rows","—")), ("Tickers", quality.get("ticker_count","—")), ("Coverage start", quality.get("date_start","—")), ("Coverage end", quality.get("date_end","—")), ("Decision role", quality.get("decision_role","—"))]):
            with col: card(*item)
        st.warning(quality.get("pit_limitation", "Post-event reactions are contextual only."))
    source("Earnings Quality", quality_src)

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
    st.header("Decision Engine V1 — Research Gate")
    st.caption("Decision semantics are preserved. Quality/PIT metadata is shown separately and never converted into a trading signal or forecast.")
    df, src = load_named("Decision Summary")
    evidence, evidence_src = load_named("Decision Evidence")
    registry, registry_src = load_named("Decision Evidence Registry")
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
    st.caption("CORE evidence may determine the published V1 research state. CONTEXTUAL evidence is integrated for visibility but has included_in_state = FALSE and cannot change the state.")
    table(registry if isinstance(registry, pd.DataFrame) else evidence, 420)
    source("Decision Evidence Registry", registry_src)
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
        if title == "Sample Adequacy":
            st.caption("Reliability is definition-specific: <5 observations = INSUFFICIENT; 5–9 = LIMITED; 10–24 = MODERATE; ≥25 = ADEQUATE. Even ADEQUATE remains descriptive only and is never treated as causal/predictive evidence.")
        table(df, 560 if title == "Event x Horizon Summary" else 360)
        source(title, src)


def historical_edge() -> None:
    st.header("Historical Edge / Robustness")

    st.warning(
        "Historical Edge is EXCLUDED/UNAVAILABLE in the current publication because no dedicated historical_edge_* artifacts are published. Historical Event Study V2 is shown only as contextual reference; it is not relabeled as Historical Edge."
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

    if isinstance(summary, pd.DataFrame) and {"status","count"}.issubset(summary.columns):
        sm = {str(r["status"]).upper(): r["count"] for _, r in summary.iterrows()}
        cols = st.columns(4)
        for col, status in zip(cols, ["PASS", "REVIEW", "FAIL", "OVERALL"]):
            with col:
                card(status, sm.get(status, 0 if status != "OVERALL" else "—"))

    st.subheader("Validation Report")
    table(report, 650)
    source("Final Validation Report", report_src)

    if isinstance(obj, dict):
        with st.expander("Final Validation JSON"):
            st.json(obj)
    source("Final Validation JSON", json_src)


def data_status() -> None:
    st.header("Data Status & Freshness")
    quality, qsrc = load_named("Remaining Layers Quality")
    if isinstance(quality,pd.DataFrame):
        st.subheader("Remaining-Layer Quality Contract")
        table(quality,420); source("Remaining Layers Quality",qsrc)

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
    suffix = Path(selected).suffix.lower()

    if suffix == ".csv":
        obj, src = load_csv(selected)
    elif suffix == ".json":
        obj, src = load_json(selected)
    else:
        raw, src = load_bytes(selected)
        obj = raw

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
    elif isinstance(obj, (dict, list)):
        st.json(obj)
    elif isinstance(obj, (bytes, bytearray)):
        try:
            text = bytes(obj).decode("utf-8")
        except UnicodeDecodeError:
            st.download_button(
                "Download artifact",
                bytes(obj),
                file_name=Path(selected).name,
                mime="application/octet-stream",
            )
        else:
            st.code(text, language=None)
            st.download_button(
                "Download artifact",
                bytes(obj),
                file_name=Path(selected).name,
                mime="text/plain",
            )
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

### Point-in-time and evidence quality

The terminal displays PIT fields supplied by the research pipeline and does not
silently replace historical observations with current values. Remaining layers
use an explicit quality contract: ELIGIBLE / DEGRADED / EXCLUDED. Missing or
excluded evidence is never silently converted to neutral or zero.

### Decision Engine

The published Decision Engine exposes state, confidence/evidence coverage,
evidence counts, PIT status and research-only controls. Quality status is
metadata and does not redefine supportive/contradictory/mixed semantics.
Event/News and Earnings are integrated into the unified evidence registry as CONTEXTUAL evidence with `included_in_state = FALSE`. They are visible to the research gate but cannot silently alter Decision Engine V1 state semantics. Any future promotion requires a dedicated PIT-safe adapter and explicit validation.

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
    "Financial Stress": financial_stress,
    "Liquidity": liquidity,
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
