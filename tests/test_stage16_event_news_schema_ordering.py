from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / ".github" / "workflows" / "us500-full-research-pipeline.yml"
HARDENING_WF = ROOT / ".github" / "workflows" / "final-remaining-layers-hardening-v1.yml"
HARDENING = ROOT / "final_remaining_layers_hardening_v1.py"


def _assert_quality_before_hardening(text: str):
    quality = text.index("python remaining_layers_quality_v1.py")
    hardening = text.index("python final_remaining_layers_hardening_v1.py")
    assert quality < hardening


def test_master_rebuild_refreshes_quality_contract_before_final_hardening():
    _assert_quality_before_hardening(MASTER.read_text(encoding="utf-8"))


def test_standalone_hardening_workflow_refreshes_quality_contract_first():
    _assert_quality_before_hardening(HARDENING_WF.read_text(encoding="utf-8"))


def test_final_hardening_fails_closed_on_missing_event_news_contract():
    source = HARDENING.read_text(encoding="utf-8")
    assert "required_event_contract" in source
    assert "decision_role" in source
    assert "Run remaining_layers_quality_v1.py" in source
