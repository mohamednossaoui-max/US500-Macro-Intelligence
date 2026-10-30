import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location("fed_evidence_experiment", ROOT / "fed_evidence.py")
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


def document(text, meeting="2026-10-28", seen="2026-10-28T18:00:00Z", scope="OFFICIAL_STATEMENT"):
    return {"text": text, "sha256": experiment.sha(text), "meeting_date": meeting,
            "first_seen_at": seen, "source": "https://www.federalreserve.gov/example",
            "scope": scope, "version_status": "UNKNOWN"}


def test_disabled_does_not_read_or_mutate_input():
    assert experiment.build(None, None) == {"status": "DISABLED", "research_only": True}


def test_explicit_decision_vote_and_dissent_have_separate_evidence():
    raw = ("The Federal Open Market Committee approved the following statement for release by a 10 – 2 vote:\n"
           "The Committee decided to maintain the target range for the federal funds rate at 3-3/4 to 4 percent.\n"
           "Voting against the monetary policy action were Lisa D. Cook and Beth M. Hammack, who preferred to raise the target range by 1/4 percentage point.")
    found = experiment.facts(raw, "OFFICIAL_STATEMENT")
    assert found["target_range_percent"]["value"] == [3.75, 4]
    assert found["policy_action"]["value"] == "HOLD"
    assert found["vote"]["value"] == [10, 2]
    assert found["dissent_preference"]["value"] == "RAISE"
    assert "Lisa D. Cook and Beth M. Hammack" in found["dissent_preference"]["evidence"]


def test_version_not_visible_one_second_before_capture():
    manifest = {"documents": [document("Inflation remains elevated.")]}
    assert "current" not in experiment.build(manifest, "2026-10-28T17:59:59Z", True)["comparisons"][0]
    assert "current" in experiment.build(manifest, "2026-10-28T18:00:00Z", True)["comparisons"][0]


def test_revised_text_cannot_leak_through_original_publication_time():
    old = document("First version.")
    old["published_at"] = "2026-10-28T18:00:00Z"
    revised = document("Revised version.", seen="2026-10-30T09:00:00Z")
    revised["published_at"] = old["published_at"]
    manifest = {"documents": [revised, old]}
    before = experiment.build(manifest, "2026-10-29T09:00:00Z", True)
    after = experiment.build(manifest, "2026-10-30T09:00:00Z", True)
    assert before["comparisons"][0]["current"]["sha256"] == old["sha256"]
    assert after["comparisons"][0]["current"]["sha256"] == revised["sha256"]


@pytest.mark.parametrize("timestamp", ["2026-10-28", "2026-10-28T18:00:00"])
def test_incomplete_timestamps_are_rejected(timestamp):
    with pytest.raises(ValueError):
        experiment.instant(timestamp)


def test_hash_mismatch_is_blocked():
    doc = document("Original")
    doc["text"] = "Changed"
    with pytest.raises(ValueError, match="hash"):
        experiment.build({"documents": [doc]}, "2026-10-30T09:00:00Z", True)


def test_mixed_scopes_never_form_a_comparison():
    manifest = {"documents": [document("Old", "2026-09-16", scope="OPENING_STATEMENT"), document("New")]}
    assert all(r["status"] == "INSUFFICIENT_AVAILABLE_DOCUMENTS" for r in experiment.build(manifest, "2026-10-30T09:00:00Z", True)["comparisons"])


def test_full_questions_and_answers_are_rejected():
    with pytest.raises(ValueError, match="Q&A"):
        experiment.validate(document("Reporter says raise.", scope="FULL_TRANSCRIPT_CHAIR_REMARKS"))


def test_missing_dissent_is_unknown_not_unanimous_or_neutral():
    assert "dissent_preference" not in experiment.facts("Inflation remains elevated.", "OFFICIAL_STATEMENT")


def test_input_is_unchanged_and_equal_values_ignore_different_evidence():
    old = document("The Committee decided to maintain the target range at 3.75 to 4 percent.", "2026-09-16")
    new = document("The Committee decided to maintain the target range for federal funds at 3.75 to 4 percent.")
    manifest = {"documents": [old, new]}
    original = copy.deepcopy(manifest)
    result = experiment.build(manifest, "2026-10-30T09:00:00Z", True)
    assert manifest == original
    assert result["comparisons"][0]["changes"]["policy_action"] == "UNCHANGED"


def test_conflicting_capture_versions_fail():
    with pytest.raises(ValueError, match="Conflicting"):
        experiment.build({"documents": [document("One"), document("Two")]}, "2026-10-30T09:00:00Z", True)


def test_conference_language_keeps_level_and_change_in_source_text():
    paragraph = "Overall financial conditions are tighter, but I am unwilling to call them tight."
    found = experiment.facts(paragraph, "OPENING_STATEMENT")
    assert found["financial_conditions"]["evidence"] == [paragraph]
    assert "policy_action" not in found


def test_html_escapes_source_text():
    rendered = experiment.render({"message": "<script>alert(1)</script>"})
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_explicit_timezone_offsets_align():
    assert experiment.instant("2026-10-28T14:00:00-04:00") == experiment.instant("2026-10-28T18:00:00Z")


def test_capture_before_declared_publication_is_blocked():
    doc = document("Text")
    doc["published_at"] = "2026-10-29T18:00:00Z"
    with pytest.raises(ValueError, match="precede"):
        experiment.validate(doc)


def test_opposite_dissents_do_not_collapse_to_first_preference():
    raw = "Voting against were A, who preferred to raise rates, and B, who preferred to lower rates."
    assert experiment.facts(raw, "OFFICIAL_STATEMENT")["dissent_preference"]["value"] == "MULTIPLE_PREFERENCES"


def test_separate_dissent_paragraphs_preserve_conflict():
    raw = "Voting against was A, who preferred to raise rates.\nVoting against was B, who preferred to lower rates."
    assert experiment.facts(raw, "OFFICIAL_STATEMENT")["dissent_preference"]["value"] == "MULTIPLE_PREFERENCES"
