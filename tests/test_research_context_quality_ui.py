from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
SUMMARY = ROOT / "public_data" / "research_context_summary_v1.csv"


def test_quality_ui_contract_is_present():
    for label in ("Evidence Quality", "Overall Quality", "Coverage", "Freshness", "PIT Integrity", "Degraded / Missing"):
        assert label in APP


def test_quality_ui_reads_published_fields():
    for field in (
        "evidence_quality_status", "evidence_coverage_pct",
        "evidence_freshness_status", "evidence_freshness_current_pct",
        "evidence_pit_status", "evidence_pit_safe_pct",
        "evidence_degraded_count", "evidence_excluded_count", "evidence_as_of_date",
    ):
        assert field in APP
        assert field in pd.read_csv(SUMMARY, nrows=1).columns


def test_research_only_boundary_is_explicit():
    assert "not a forecast" in APP
    assert "trading signal" in APP
    assert "execution input" in APP


def test_current_published_quality_is_not_silently_promoted():
    row = pd.read_csv(SUMMARY).iloc[-1]
    assert row["evidence_quality_status"] == "MEDIUM"
    assert row["evidence_pit_status"] == "PIT_LIMITED"
    q = pd.read_csv(ROOT / "public_data/research_evidence_quality_v1.csv")
    expected_coverage = round(100.0 * (q["availability_status"] == "AVAILABLE").sum() / len(q), 1)
    expected_degraded = int(((q["availability_status"] == "AVAILABLE") & ~q["decision_engine_eligible"].astype(bool)).sum())
    assert float(row["evidence_coverage_pct"]) == expected_coverage
    assert int(row["evidence_degraded_count"]) == expected_degraded
    breadth = q[q["module"] == "MARKET_BREADTH"].iloc[-1]
    assert breadth["freshness_status"] == "STALE"
    assert bool(breadth["decision_engine_eligible"]) is False
