from pathlib import Path
import importlib.util
import json
import shutil
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
    q = pd.read_csv(ROOT / "public_data/research_evidence_quality_v1.csv")
    contract = pd.read_csv(ROOT / "public_data/research_evidence_contract_v1.csv")
    assert row["evidence_as_of_date"] == contract["as_of_date"].max()
    assert int(row["evidence_evidence_count"]) == len(q)
    assert int(row["evidence_eligible_count"]) == int(q["decision_engine_eligible"].astype(bool).sum())
    expected_pit = round(100.0 * (q["pit_status"] == "PIT_SAFE").sum() / len(q), 1)
    assert float(row["evidence_pit_safe_pct"]) == expected_pit


def test_breadth_and_cross_asset_remain_pit_limited():
    df = pd.read_csv(ROOT / "public_data/research_context_summary_v1.csv")
    row = df.iloc[-1]
    assert row["breadth_evidence_pit_status"] == "PIT_LIMITED"
    assert row["cross_asset_evidence_pit_status"] == "PIT_LIMITED"
    assert int(row["breadth_evidence_eligible_count"]) == 0
    assert int(row["cross_asset_evidence_eligible_count"]) == 0


def test_existing_states_preserved(tmp_path, monkeypatch):
    public = ROOT / "public_data"
    summary_file = tmp_path / "research_context_summary_v1.csv"
    quality_file = tmp_path / "research_evidence_quality_v1.csv"
    quality_summary_file = tmp_path / "research_evidence_quality_summary_v1.json"
    contract_file = tmp_path / "research_evidence_contract_v1.csv"
    for src, dst in [
        (public / "research_context_summary_v1.csv", summary_file),
        (public / "research_evidence_quality_v1.csv", quality_file),
        (public / "research_evidence_quality_summary_v1.json", quality_summary_file),
        (public / "research_evidence_contract_v1.csv", contract_file),
    ]:
        shutil.copy2(src, dst)

    before = pd.read_csv(summary_file, low_memory=False).iloc[-1].copy()
    monkeypatch.setattr(rcq, "CONTEXT_SUMMARY_FILE", summary_file)
    monkeypatch.setattr(rcq, "QUALITY_FILE", quality_file)
    monkeypatch.setattr(rcq, "QUALITY_SUMMARY_FILE", quality_summary_file)
    monkeypatch.setattr(rcq, "CONTRACT_FILE", contract_file)
    after = rcq.integrate().iloc[-1]

    protected = [c for c in before.index if not c.startswith("evidence_") and "_evidence_" not in c]
    assert {c: str(after[c]) for c in protected} == {c: str(before[c]) for c in protected}


def test_published_chronology_gate_remains_strict():
    validation = json.loads((ROOT / "public_data/research_evidence_validation_v1.json").read_text())
    assert validation["chronology_valid"] is True
    assert int(validation["future_evidence_count"]) == 0
