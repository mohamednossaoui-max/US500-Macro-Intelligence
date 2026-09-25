"""US500 Macro Intelligence — Research Terminal V6.0.

Read-only research presentation. Public data is loaded from local public_data/
first and GitHub raw second. This application contains no trading functionality.
"""
from __future__ import annotations

import json
import html
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st


st.set_page_config(page_title="US500 Macro Intelligence | Research Terminal V6.0", page_icon="📊", layout="wide")

REPO_RAW = "https://raw.githubusercontent.com/mohamednossaoui-max/US500-Macro-Intelligence/main/public_data"
DATA_DIR = Path(__file__).resolve().parent / "public_data"
TIMEOUT_SECONDS = 5
NOT_PUBLISHED = "Not published"

# Candidate names follow the artifact names produced by repository workflows.
# Manifest entries are added dynamically so newly published data can be found.
DATASETS: dict[str, list[str]] = {
    "Manifest": ["public_data_manifest.json"],
    "Decision Summary": ["decision_engine_summary_v1.csv", "decision_engine_research_summary_v1.csv", "decision_engine_summary_v1.json"],
    "Decision Engine": ["decision_engine_research_v1.csv", "decision_engine_research_v1.json"],
    "Decision Evidence": ["decision_engine_research_evidence_v1.csv"],
    "Research Context": ["research_context_v1.csv", "research_context_v1.json"],
    "Financial Stress": ["financial_stress_research_v1.csv", "financial_stress_analysis_v1.csv", "financial_stress_summary_v1.csv"],
    "Sentiment": ["sentiment_engine_v1.csv", "sentiment_engine_research_v1.csv"],
    "Technical": ["technical_intelligence_v1.csv", "technical_research_v1.csv"],
    "Fed": ["fed_intelligence_v1.csv", "fed_intelligence_output_v1.json"],
    "Economic": ["economic_intelligence_v1.csv", "economic_regime_v1.csv", "economic_regime_classifier_v1.csv"],
    "Event News": ["event_news_intelligence_v1.csv", "event_news_intelligence_v1.json"],
    "Historical Event Study": ["historical_event_study_validation_v2.json", "historical_event_study_summary_v2.csv", "historical_event_study_v2_summary.csv"],
    "Historical Edge": ["historical_edge_robustness_summary_v1.json", "historical_edge_robustness_summary_v1.csv", "historical_edge_summary_v1.json"],
    "Edge Temporal": ["historical_edge_temporal_v1.csv", "historical_edge_temporal_stability_v1.csv"],
    "Edge Threshold": ["historical_edge_threshold_sensitivity_v1.csv", "historical_edge_threshold_stability_v1.csv"],
    "Edge PIT Audit": ["historical_edge_pit_audit_v1.csv"],
}

VERIFIED = {
    "Decision Engine": {"run_id": "36189840012", "status": "PASS", "state": "SUPPORTIVE", "confidence": "1.0", "evidence_count": 4, "supportive_count": 2, "contradictory_count": 0, "mixed_count": 2, "point_in_time_safe": "TRUE", "research_only": "TRUE", "trading_signal": "NONE", "forecast": "NONE", "execution": "FALSE", "position_sizing": "FALSE", "stop_loss": "NONE", "take_profit": "NONE"},
    "Historical Event Study": {"run_id": "36190915225", "status": "PASS", "sample": 1916, "start": "2019-01-03", "end": "2026-08-18", "events": 11, "horizons": "1D / 5D / 20D", "research_only": "TRUE", "decision_engine_ready": "FALSE", "trading_signal": "FALSE", "forecast": "FALSE", "pit_perfect": "FALSE"},
    "Historical Edge": {"run_id": "36192353073", "status": "PASS", "sample": 1916, "base_events": 11, "periods": 4, "temporal_rows": 132, "threshold_rows": 87, "temporal_stability_rows": 33, "threshold_stability_rows": 24, "horizon_stability_rows": 11, "pit_audit_rows": 3, "pit_perfect": "FALSE", "research_only": "TRUE", "decision_engine": "FALSE", "trading_signal": "FALSE", "forecast": "FALSE", "optimization": "FALSE", "causal_claim": "FALSE", "period_names": "FULL_SAMPLE, 2019_2021, 2022_2023, 2024_2026"},
}
PIPELINE_RUNS = [("Master Pipeline", "36139637088"), ("Macro Context", "36181485481"), ("Sentiment Engine", "36183227935"), ("Research Integration Full Validation", "36184596061"), ("Final End-to-End Validation", "36186001790"), ("Decision Engine V1", "36189840012"), ("Historical Event Study V2", "36190915225"), ("Historical Edge Robustness V1", "36192353073")]


@st.cache_data(ttl=300, show_spinner=False)
def load_public_file(name: str) -> tuple[str | None, str | None]:
    """Return raw content and origin; gracefully tolerate missing files/network."""
    path = DATA_DIR / Path(name).name
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8-sig"), "Local public_data"
    except (OSError, UnicodeError):
        pass
    try:
        response = requests.get(f"{REPO_RAW}/{name}", timeout=TIMEOUT_SECONDS)
        if response.status_code == 200:
            return response.content.decode("utf-8-sig"), "GitHub raw"
    except (requests.RequestException, UnicodeError):
        pass
    return None, None


def parse_content(name: str, content: str | None) -> Any:
    if content is None or not content.strip():
        return None
    try:
        if name.lower().endswith(".json"):
            return json.loads(content)
        return pd.read_csv(pd.io.common.StringIO(content))
    except (ValueError, TypeError, pd.errors.ParserError, json.JSONDecodeError):
        return None


@st.cache_data(ttl=300, show_spinner=False)
def load_dataset(label: str, candidates: tuple[str, ...]) -> tuple[Any, str | None, str | None]:
    for filename in candidates:
        content, origin = load_public_file(filename)
        parsed = parse_content(filename, content)
        if parsed is not None and (not isinstance(parsed, pd.DataFrame) or not parsed.empty):
            return parsed, filename, origin
    return None, None, None


def as_frame(data: Any) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
