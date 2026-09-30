from pathlib import Path
import json
import pandas as pd
import importlib
cross_asset = importlib.import_module("evidence_adapters.cross_asset")

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public_data"


def _rows():
    return cross_asset.build(PUBLIC)


def _context_date():
    d = pd.read_csv(PUBLIC / 'research_context_summary_v1.csv', low_memory=False)
    return pd.to_datetime(d.iloc[-1]['context_date']).normalize()


def test_cross_asset_artifact_declares_pit_limited():
    summary = json.loads((PUBLIC / "cross_asset_summary_v1.json").read_text())
    assert summary["pit_status"] == "PIT_LIMITED"
    assert summary["point_in_time_safe"] is False
    assert summary["mechanical_availability_gate_passed"] is True
    assert summary["session_aware_pit_safe"] is False


def test_cross_asset_rows_preserve_mechanical_gate_but_not_overpromote_pit():
    d = pd.read_csv(PUBLIC / "cross_asset_research_v1.csv")
    assert set(d["pit_status"].dropna()) == {"PIT_LIMITED"}
    assert not d["session_aware_pit_safe"].astype(bool).any()
    assert d["point_in_time_safe"].astype(bool).all()


def test_cross_asset_evidence_uses_latest_observation_per_asset():
    rows = {r["indicator"]: r for r in _rows()}
    assert rows["SP500"]["observation_date"] == "2026-09-24"
    assert rows["NASDAQ"]["observation_date"] == "2026-09-24"
    assert rows["GOLD"]["observation_date"] == "2026-09-25"
    assert rows["BITCOIN"]["observation_date"] == "2026-09-25"


def test_cross_asset_does_not_borrow_other_assets_availability_date():
    rows = {r["indicator"]: r for r in _rows()}
    assert rows["SP500"]["available_at"] == "2026-09-25"
    assert rows["NASDAQ"]["available_at"] == "2026-09-25"
    assert rows["GOLD"]["available_at"] == "2026-09-26"
    assert rows["SP500"]["available_at"] != rows["GOLD"]["available_at"]


def test_cross_asset_context_freshness_is_measured_against_research_context():
    rows = _rows()
    context_date = _context_date()
    assert {r["as_of_date"] for r in rows} == {context_date.date().isoformat()}
    for r in rows:
        if r.get("available_at"):
            expected_age = int((context_date - pd.to_datetime(r["available_at"]).normalize()).days)
            assert r["age_days"] == expected_age


def test_cross_asset_never_becomes_decision_eligible_while_pit_limited():
    from research_evidence_quality_v1 import apply_quality
    rows = apply_quality(_rows())
    assert len(rows) == 8
    assert all(r["pit_status"] == "PIT_LIMITED" for r in rows)
    assert all(r["decision_engine_eligible"] is False for r in rows)
    assert all(r["exclusion_reason"] == "PIT_LIMITED_EVIDENCE" for r in rows)
