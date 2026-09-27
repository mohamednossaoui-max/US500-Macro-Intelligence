from __future__ import annotations

from pathlib import Path

import pytest

import fed_intelligence as fed

ROOT = Path(__file__).resolve().parents[1]


def _texts():
    return {
        "statement_text": "inflation remains elevated. policy remains restrictive.",
        "minutes_text": "inflation remains elevated. higher for longer.",
        "chair_text": "labor market softened. rate cuts may be appropriate.",
    }


def test_missing_minutes_are_excluded_and_weights_are_renormalized():
    t = _texts()
    out = fed.build_deep_fed_analysis(
        statement_text=t["statement_text"],
        minutes_text="",
        chair_text=t["chair_text"],
        sep_shift_data={},
    )
    w = out["document_weights"]
    assert w["minutes"] == 0.0
    assert w["statement"] == pytest.approx(0.35 / 0.60, abs=1e-6)
    assert w["chair"] == pytest.approx(0.25 / 0.60, abs=1e-6)
    assert sum(w.values()) == pytest.approx(1.0, abs=1e-6)


def test_all_documents_keep_35_40_25_weights():
    out = fed.build_deep_fed_analysis(**_texts(), sep_shift_data={})
    assert out["document_weights"] == {
        "statement": 0.35,
        "minutes": 0.4,
        "chair": 0.25,
    }


def test_unavailable_minutes_do_not_act_as_fake_neutral_evidence():
    t = _texts()
    out = fed.build_deep_fed_analysis(
        statement_text=t["statement_text"],
        minutes_text="",
        chair_text=t["chair_text"],
        sep_shift_data={},
    )
    assert out["document_availability"]["minutes"] is False
    for dimension in fed.DIMENSION_WEIGHTS:
        expected = (
            out["statement"][dimension]["score_100"] * (0.35 / 0.60)
            + out["chair"][dimension]["score_100"] * (0.25 / 0.60)
        )
        assert out["combined"][dimension]["score_100"] == pytest.approx(expected, abs=0.11)


def test_no_communication_documents_means_no_fed_score():
    out = fed.build_deep_fed_analysis("", "", "", {})
    assert out["fed_score"]["score"] is None
    assert out["fed_score"]["classification"] == "UNAVAILABLE"
    assert all(weight == 0 for weight in out["document_weights"].values())


def test_sep_shift_remains_directional_adjustment_only():
    out = fed.build_deep_fed_analysis(
        **_texts(),
        sep_shift_data={"classification": "HAWKISH SHIFT"},
    )
    assert out["fed_score"]["sep_adjustment"] == 5.0
    assert "not a probability" in out["method"].lower()


def test_backward_compatible_powell_keys_are_preserved_in_engine_contract():
    source = (ROOT / "fed_intelligence.py").read_text(encoding="utf-8")
    assert '"chair_press"' in source
    assert '"powell"' in source
    assert '"powell_page"' in source
    assert '"powell_pdf"' in source


def test_fed_ui_exposes_required_report_sections():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    required = [
        'st.subheader("Policy Pulse")',
        'st.subheader("What Changed?")',
        'st.subheader("FOMC Communication")',
        'st.subheader("SEP Pulse — Current vs Previous")',
        'st.subheader("Fed Synthesis")',
        'st.subheader("Beige Book Context")',
        "<div class='title'>FED BOTTOM LINE</div>",
        'with st.expander("View detailed data")',
        '"Minutes are pending and are not treated as evidence."',
    ]
    for marker in required:
        assert marker in source


def test_fed_ui_does_not_mislabel_legacy_available_evidence_as_excluded():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "included · weight metadata pending refresh" in source
    assert "excluded until published" in source
    assert "explicit_weight" in source
    assert "explicit_availability" in source



def test_document_comparison_never_invents_missing_previous_evidence():
    current = fed.analyze("Current", "inflation remains elevated. policy remains restrictive.")
    out = fed.compare_document_analysis(current, fed.analyze("Previous", ""))
    assert out["available"] is False
    assert out["classification"] == "UNAVAILABLE"
    assert out["tone_score_change"] is None


def test_document_comparison_reports_directional_change():
    previous = fed.analyze("Previous", "rate cuts. lower rates. easing policy.")
    current = fed.analyze("Current", "higher for longer. restrictive. additional tightening.")
    out = fed.compare_document_analysis(current, previous)
    assert out["available"] is True
    assert out["classification"] == "MORE HAWKISH"


def test_fed_quality_contract_degrades_partial_publication_set():
    data = {
        "document_status": {
            "statement": {"available": True},
            "minutes": {"available": False},
            "chair_press": {"available": True},
        },
        "sep_current": {"available": True},
        "beige_book": {"available": True},
    }
    q = fed.fed_quality_contract(data, fed.date(2026, 9, 27))
    assert q["quality_gate"] == "DEGRADED"
    assert q["quality_reason"] == "PARTIAL_PUBLICATION_SET"
    assert q["research_only"] is True
    assert q["forecast"] is False


def test_fed_ui_exposes_current_previous_and_quality_sections():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'st.subheader("Communication — Current vs Previous")' in source
    assert 'st.subheader("Fed Evidence Quality")' in source
    assert '"Quality Gate"' in source


def test_latest_published_minutes_are_selected_independently_of_latest_fomc():
    links = {
        "statement": {fed.date(2026, 9, 16): "statement-sep"},
        "minutes": {
            fed.date(2026, 7, 29): "minutes-jul",
            fed.date(2026, 6, 18): "minutes-jun",
        },
        "press": {fed.date(2026, 9, 16): "press-sep"},
        "sep": {},
    }
    latest = fed.latest_document_date(links, "minutes", fed.date(2026, 9, 27))
    assert latest == fed.date(2026, 7, 29)
    assert latest != fed.latest_completed_fomc(links, fed.date(2026, 9, 27))
    assert fed.previous_document_date(links, "minutes", latest) == fed.date(2026, 6, 18)


def test_fed_quality_contract_marks_published_prior_meeting_minutes_as_lagged():
    data = {
        "document_status": {
            "statement": {"available": True},
            "minutes": {"available": True, "lagged": True},
            "chair_press": {"available": True},
        },
        "sep_current": {"available": True},
        "beige_book": {"available": True},
    }
    q = fed.fed_quality_contract(data, fed.date(2026, 9, 27))
    assert q["quality_gate"] == "DEGRADED"
    assert q["quality_reason"] == "LATEST_MINUTES_LAG_LATEST_FOMC"
    assert q["pit_status"] == "PIT_SAFE"


def test_fed_ui_labels_lagged_minutes_without_relabeling_them_current():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "Latest published FOMC Minutes cover the" in source
    assert "lagged research evidence" in source
    assert "are not relabeled as current-meeting minutes" in source


def test_lagged_minutes_remain_available_but_are_excluded_from_current_score():
    out = fed.build_deep_fed_analysis(
        **_texts(), sep_shift_data={}, minutes_current_for_score=False
    )
    assert out["document_availability"]["minutes"] is True
    assert out["document_score_eligibility"]["minutes"] is False
    assert out["document_weights"]["minutes"] == 0.0
    assert out["document_weights"]["statement"] == pytest.approx(0.35 / 0.60, abs=1e-6)
    assert out["document_weights"]["chair"] == pytest.approx(0.25 / 0.60, abs=1e-6)
    assert "prior meeting" in out["method"].lower()


def test_fed_ui_explains_lagged_minutes_scoring_boundary():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "lagged evidence · excluded from current-meeting score" in source
    assert "Current-meeting synthesis uses the current Statement and Press Conference" in source
