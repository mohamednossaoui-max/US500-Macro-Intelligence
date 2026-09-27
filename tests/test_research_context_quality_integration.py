from pathlib import Path
import importlib.util
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "research_context_quality_integration_v1.py"
spec = importlib.util.spec_from_file_location("rcq", MOD_PATH)
rcq = importlib.util.module_from_spec(spec); spec.loader.exec_module(rcq)


def test_rollup_does_not_promote_pit_limited():
    df = pd.DataFrame([{
        "availability_status":"AVAILABLE", "decision_engine_eligible":False,
        "pit_status":"PIT_LIMITED", "freshness_status":"CURRENT", "quality_status":"MEDIUM"
    }])
    r = rcq._rollup(df)
    assert r["pit_status"] == "PIT_LIMITED"
    assert r["eligible_count"] == 0


def test_published_summary_has_quality_metadata():
    df = pd.read_csv(ROOT / "public_data/research_context_summary_v1.csv")
    row = df.iloc[-1]
    assert row["evidence_as_of_date"] == "2026-09-26"
    assert int(row["evidence_evidence_count"]) == 40
    assert int(row["evidence_eligible_count"]) == 30
    assert float(row["evidence_pit_safe_pct"]) == 75.0


def test_breadth_and_cross_asset_remain_pit_limited():
    df = pd.read_csv(ROOT / "public_data/research_context_summary_v1.csv")
    row = df.iloc[-1]
    assert row["breadth_evidence_pit_status"] == "PIT_LIMITED"
    assert row["cross_asset_evidence_pit_status"] == "PIT_LIMITED"
    assert int(row["breadth_evidence_eligible_count"]) == 0
    assert int(row["cross_asset_evidence_eligible_count"]) == 0


def test_existing_states_preserved():
    row = pd.read_csv(ROOT / "public_data/research_context_summary_v1.csv").iloc[-1]
    assert row["economic_regime"] == "MIXED"
    assert row["sentiment_regime"] == "NEUTRAL"
    assert row["technical_regime"] == "BULLISH"
    assert row["financial_stress_regime"] == "LOW_RESEARCH_STRESS"
