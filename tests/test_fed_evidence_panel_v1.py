import copy
import json
from pathlib import Path

import pytest

from fed_evidence_panel_v1 import panel_model, _value

ROOT = Path(__file__).resolve().parents[1]


def published():
    return json.loads((ROOT / "public_data/fed_intelligence_output_v1.json").read_text())


def statement():
    return published()["report_comparison"]["statement"]


def test_actual_published_statement_exposes_decision_vote_and_dissent():
    pair = statement()
    model = panel_model(pair, "statement")
    rows = {row["key"]: row for row in model["rows"]}
    assert model["comparable"]
    assert rows["policy_action"]["current"]["value"] == pair["current"]["facts"]["policy_action"]["value"]
    assert rows["vote"]["current"]["value"] == pair["current"]["facts"]["vote"]["value"]
    if pair["current"]["meeting_date"] == "2026-10-28":
        assert rows["dissent_preference"]["current"]["value"] == "RAISE"
        assert "preferred to raise" in rows["dissent_preference"]["current"]["evidence"]


def test_rendering_model_never_changes_snapshot_scores_dates_or_flags():
    snapshot = published()
    before = copy.deepcopy(snapshot)
    for key in ("statement", "chair_press"):
        panel_model(snapshot["report_comparison"][key], key)
    assert snapshot == before


def test_missing_vote_and_preference_are_not_neutral_or_unanimous():
    pair = statement()
    for side in ("previous", "current"):
        pair[side]["facts"].pop("vote", None)
        pair[side]["topics"]["policy"]["evidence"] = []
    pair["metrics"].pop("vote", None)
    row = panel_model(pair, "statement")["rows"][-1]
    assert not row["current"] and not row["previous"]
    assert row["status"] == "NOT COMPARABLE"


def test_unknown_publication_time_is_not_inferred_from_meeting_or_date():
    pair = statement()
    pair["current"]["published_at"] = "2026-10-28"
    pair["current"]["version_status"] = None
    meta = panel_model(pair, "statement")["provenance"]["current"]
    assert meta["publication_time_status"] == "NOT VERIFIED"
    assert meta["version_status"] == "UNKNOWN"
    assert meta["retrieved_at"] == pair["current"]["retrieved_at"]


def test_recorded_aware_timestamp_is_preserved_without_declaring_pit_safe():
    pair = statement()
    pair["current"]["published_at"] = "2026-10-28T14:00:00-04:00"
    pair["current"]["version_status"] = "PRELIMINARY"
    meta = panel_model(pair, "statement")["provenance"]["current"]
    assert meta["publication_time_status"] == "RECORDED"
    assert meta["version_status"] == "PRELIMINARY"
    assert "pit_safe" not in meta


def test_mixed_scopes_do_not_display_a_comparison_or_wording_change():
    pair = statement()
    pair["current"]["scope"] = "OPENING_STATEMENT"
    model = panel_model(pair, "statement")
    assert not model["comparable"]
    assert not model["highlights"]
    assert all(row["status"] == "NOT COMPARABLE" for row in model["rows"])


def test_reporter_preferences_cannot_be_statement_dissents():
    pair = statement()
    for side in ("previous", "current"):
        pair[side]["scope"] = "FULL_TRANSCRIPT_CHAIR_REMARKS"
    model = panel_model(pair, "chair_press")
    assert all(row["key"] != "dissent_preference" for row in model["rows"])


def test_conflicting_dissent_preferences_are_preserved():
    pair = statement()
    pair["current"]["topics"]["policy"]["evidence"] = [
        "One member preferred to raise the target range.",
        "Another member preferred to lower the target range.",
    ]
    assert panel_model(pair, "statement")["rows"][-1]["current"]["value"] == "MULTIPLE PREFERENCES"


@pytest.mark.parametrize("pair", [None, {}, {"current": None}, {"available": True}])
def test_missing_published_documents_render_unknown_not_success(pair):
    model = panel_model(pair, "statement")
    assert not model["comparable"]
    assert all(row["status"] == "NOT COMPARABLE" for row in model["rows"])


def test_missing_side_is_not_an_unchanged_result():
    pair = statement()
    pair["previous"]["available"] = False
    assert all(row["status"] == "NOT COMPARABLE" for row in panel_model(pair, "statement")["rows"])


def test_vote_list_has_no_percent_suffix():
    assert _value({"value": [10, 2]}, "vote") == "10–2"
    assert _value({"value": [3.75, 4]}, "target_range") == "3.75–4.00%"


def test_untrusted_source_urls_are_not_rendered_as_official_links():
    pair = statement()
    pair["current"]["source"] = "https://www.federalreserve.gov.evil.example/foo"
    assert panel_model(pair, "statement")["provenance"]["current"]["source"] is None


def test_real_compact_component_calls_integrated_panel_and_keeps_details():
    from streamlit.testing.v1 import AppTest
    source = "import json\nfrom fed_report_comparison_ui_v2 import compact_comparison\npair=json.loads(" + repr(json.dumps(statement())) + ")\ncompact_comparison(pair, 'FOMC Statement', 'statement')"
    app = AppTest.from_string(source).run(timeout=30)
    assert not app.exception
    rendered = "\n".join(x.value for group in (app.markdown, app.caption) for x in group)
    assert "Fed Evidence — What changed?" in rendered
    assert "Dissent preference" in rendered
    assert "Publication time: NOT VERIFIED" in rendered
    assert any(x.label == "FOMC Statement — Detailed report comparison" for x in app.expander)


def test_actual_fed_page_contains_panel_and_preserves_published_score():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception
    app.radio[0].set_value("Fed Intelligence").run(timeout=30)
    assert not app.exception
    rendered = "\n".join(x.value for group in (app.markdown, app.caption) for x in group)
    assert "Fed Evidence — What changed?" in rendered
    assert "Press Conference — Evidence & timing" in rendered
    score = published()["fed_score"]["score"]
    assert f"{score:.1f}/100" in rendered
    assert "Source text differences only" in rendered


def test_evidence_highlights_are_literal_published_pairs_with_no_new_direction():
    pair = statement()
    model = panel_model(pair, "statement")
    assert len(model["highlights"]) <= 2
    originals = [p for topic in pair["topics"].values() for p in topic.get("pairs", [])]
    for item in model["highlights"]:
        assert any(item["previous"] == old.get("previous") and item["current"] == old.get("current") for old in originals)
        assert item["status"] == "WORDING_CHANGED"
