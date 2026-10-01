from pathlib import Path
import json
import pandas as pd
import importlib
cross_asset = importlib.import_module("evidence_adapters.cross_asset")

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public_data"
ASSETS = tuple(cross_asset.ASSETS)


def _rows():
    return cross_asset.build(PUBLIC)


def _context_date():
    d = pd.read_csv(PUBLIC / "research_context_summary_v1.csv", low_memory=False)
    return pd.to_datetime(d.iloc[-1]["context_date"]).normalize()


def _source():
    return pd.read_csv(PUBLIC / "cross_asset_research_v1.csv", low_memory=False)


def _expected_latest_row(asset):
    d = _source()
    valid = d.loc[d[asset].notna()]
    assert not valid.empty, f"Expected at least one observation for {asset}"
    return valid.iloc[-1]


def _iso_date(value):
    parsed = pd.to_datetime(value, errors="raise")
    return parsed.date().isoformat()


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
    assert set(rows) == set(ASSETS)

    for asset in ASSETS:
        expected = _expected_latest_row(asset)
        assert rows[asset]["observation_date"] == _iso_date(expected["observation_date"])


def test_cross_asset_does_not_borrow_other_assets_availability_date():
    rows = {r["indicator"]: r for r in _rows()}

    for asset in ASSETS:
        expected = _expected_latest_row(asset)
        # Availability must travel with the same source row selected for this
        # asset.  This prevents a sparse asset from borrowing another asset's
        # newer calendar date as the research dataset advances.
        assert rows[asset]["available_at"] == _iso_date(expected["availability_date"])
        assert rows[asset]["observation_date"] == _iso_date(expected["observation_date"])


def test_cross_asset_context_freshness_is_measured_against_research_context():
    rows = _rows()
    context_date = _context_date()
    assert {r["as_of_date"] for r in rows} == {context_date.date().isoformat()}
    for r in rows:
        if r.get("available_at"):
            available_at = pd.to_datetime(r["available_at"]).normalize()
            assert available_at <= context_date, (
                f"Future cross-asset evidence: {r['indicator']} "
                f"available_at={r['available_at']} context_date={context_date.date().isoformat()}"
            )
            expected_age = int((context_date - available_at).days)
            assert r["age_days"] == expected_age


def test_cross_asset_never_becomes_decision_eligible_while_pit_limited():
    from research_evidence_quality_v1 import apply_quality
    rows = apply_quality(_rows())
    assert len(rows) == len(ASSETS)
    assert all(r["pit_status"] == "PIT_LIMITED" for r in rows)
    assert all(r["decision_engine_eligible"] is False for r in rows)
    assert all(r["exclusion_reason"] == "PIT_LIMITED_EVIDENCE" for r in rows)
