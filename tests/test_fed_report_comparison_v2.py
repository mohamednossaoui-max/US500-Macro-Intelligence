import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import fed_intelligence as fed
import fed_report_comparison_v2 as reports
from fed_beige_evidence_v1 import snapshot_quality

FIXTURES = Path(__file__).parent / "fixtures" / "fed_communication"
PAGE = "https://www.federalreserve.gov/monetarypolicy/fomcpresconf20260916.htm"
PDF = "https://www.federalreserve.gov/mediacenter/files/FOMCpresconf20260916.pdf"


def text(when):
    return (FIXTURES / f"{when}-transcript.txt").read_text()


def pair():
    old = reports.document(reports.chair_remarks(text("20260729")),
                           {"meeting_date": "2026-07-29", "source": PDF.replace("20260916", "20260729")},
                           "FULL_TRANSCRIPT_CHAIR_REMARKS")
    new = reports.document(reports.chair_remarks(text("20260916")),
                           {"meeting_date": "2026-09-16", "source": PDF}, "FULL_TRANSCRIPT_CHAIR_REMARKS")
    return reports.compare(old, new)


def mock_pdf(monkeypatch, full_text):
    monkeypatch.setattr(reports, "PdfReader", lambda _: SimpleNamespace(
        pages=[SimpleNamespace(extract_text=lambda: full_text)]))


def test_verified_canonical_pdf_is_found_without_an_anchor(monkeypatch):
    mock_pdf(monkeypatch, text("20260916"))
    calls = []
    def get(url):
        calls.append(url)
        return SimpleNamespace(text="<h1>Video player</h1>", content=b"%PDF-test") if url == PDF else SimpleNamespace(text="<h1>Video player</h1>", content=b"html")
    result = reports.load_press(PAGE, get, date(2026, 10, 14))
    assert result["available"]
    assert result["source_status"] == "VERIFIED_TRANSCRIPT"
    assert result["pdf_url"] == PDF
    assert result["publication_date"] is None
    assert PDF in calls


def test_canonical_pdf_can_be_recovered_when_landing_page_fetch_fails(monkeypatch):
    mock_pdf(monkeypatch, text("20260916"))
    out = reports.load_press(PAGE, lambda u: SimpleNamespace(content=b"%PDF-test") if u == PDF else None)
    assert out["available"]


def test_wrong_meeting_pdf_is_rejected(monkeypatch):
    mock_pdf(monkeypatch, text("20260729"))
    out = reports.load_press(PAGE, lambda u: SimpleNamespace(text="", content=b"%PDF-test"))
    assert not out["available"]
    assert out["source_status"] == "TRANSCRIPT_DATE_OR_TYPE_MISMATCH"


def test_html_error_page_is_never_a_transcript():
    out = reports.load_press(PAGE, lambda u: SimpleNamespace(text="Video", content=b"<html>Video</html>"))
    assert not out["available"]
    assert out["text"] == ""


def test_pdf_parse_error_remains_distinct_from_publication_status(monkeypatch):
    def fail(_):
        raise ValueError("corrupt PDF")
    monkeypatch.setattr(reports, "PdfReader", fail)
    out = reports.load_press(PAGE, lambda u: SimpleNamespace(text="", content=b"%PDF-corrupt"))
    assert not out["available"]
    assert out["source_status"] == "PDF_EXTRACTION_FAILED"


def test_future_meeting_is_never_requested():
    out = reports.load_press(PAGE, lambda u: pytest.fail("Network must not be called"), date(2026, 9, 15))
    assert not out["available"]


def test_reporter_assertions_are_not_attributed_to_chair():
    raw = "CHAIRMAN WARSH. Inflation remains elevated.\nJANE REPORTER. GDP will crash by 10 percent.\nCHAIRMAN WARSH. We have not made that forecast."
    remarks = reports.chair_remarks(raw)
    assert "GDP will crash" not in remarks
    assert "not made that forecast" in remarks


def test_real_policy_range_decision_and_voting_comparisons():
    out = pair()
    assert out["available"]
    rate = out["metrics"]["target_range"]
    assert rate["previous"]["value"] == [3.5, 3.75]
    assert rate["current"]["value"] == [3.75, 4.0]
    assert rate["change"] == [25, 25]
    assert out["metrics"]["policy_action"]["previous"]["value"] == "HOLD"
    assert out["metrics"]["policy_action"]["current"]["value"] == "RAISE"
    assert out["metrics"]["vote"]["previous"]["value"] == "9–3"
    assert out["metrics"]["vote"]["current"]["value"] == "UNANIMOUS"


def test_fractional_statement_rates_and_vote_are_not_misread():
    body = reports.report_body((FIXTURES / "20260916-statement.html").read_text())
    facts = reports.policy_facts(body)
    assert facts["target_range"]["value"] == [3.75, 4.0]
    assert facts["vote"]["value"] == "12–0"
    assert "For release at" not in body
    assert "Share" not in body


def test_estimated_data_and_reference_period_are_preserved_as_source_text():
    evidence = pair()["current"]["topics"]["inflation"]["evidence"]
    assert any("likely was around 3.6 percent in August" in s for s in evidence)
    # Do not turn a contemporaneous estimate into a later realized PCE release.
    assert "pce" not in pair()["metrics"]


def test_missing_previous_does_not_become_unchanged_or_neutral():
    old = reports.document("", {}, "OFFICIAL_STATEMENT")
    current = reports.document("Inflation remains elevated.", {}, "OFFICIAL_STATEMENT")
    out = reports.compare(old, current)
    assert not out["available"]
    assert out["metrics"] == {}
    assert "UNCHANGED" not in out["status"]


def test_opening_only_and_full_transcript_do_not_silently_compare_different_scope():
    out = pair()
    out["current"]["scope"] = "OPENING_STATEMENT"
    assert reports.compare(out["previous"], out["current"])["status"] == "SCOPE_MISMATCH"


def test_wording_alignment_does_not_declare_a_hawkish_or_dovish_shift():
    old = reports.document("Inflation remains elevated.", {}, "OFFICIAL_STATEMENT")
    new = reports.document("Inflation is still elevated.", {}, "OFFICIAL_STATEMENT")
    out = reports.compare(old, new)
    assert out["topics"]["inflation"]["pairs"][0]["status"] == "WORDING_CHANGED"
    assert "classification" not in out


def test_same_words_and_one_sided_messages_are_distinguished():
    pairs = reports.pair_evidence(["Inflation remains elevated."], ["Inflation remains elevated.", "Credit flows are robust."])
    assert pairs[0]["status"] == "SAME_WORDING"
    assert pairs[1]["status"] == "CURRENT_ONLY_EVIDENCE"


def test_explicit_related_publication_dates_are_preserved():
    dates = reports.release_dates((FIXTURES / "20260916-press-page.html").read_text())
    assert dates == {"statement": "2026-09-16", "sep": "2026-09-16", "minutes": "2026-10-07"}
    assert "chair_press" not in dates


def test_adjacent_multiple_release_labels_are_not_borrowed():
    html = '<div><a href="/monetarypolicy/fomcprojtabl20260916.htm">HTML</a> Released September 16, 2026 <a href="/monetarypolicy/fomcminutes20260916.htm">HTML</a> Released October 7, 2026</div>'
    assert reports.release_dates(html) == {}


def test_current_transcript_and_unknown_publication_date_are_distinct():
    data = {"as_of_date": "2026-10-14", "evidence_dates": {"chair_press": {
        "available": True, "meeting_date": "2026-09-16", "publication_date": None,
        "source": PDF, "meeting_verified": True, "latest_meeting_date": "2026-09-16", "catalog_verified": True}}}
    q = snapshot_quality(data, date(2026, 10, 14))
    assert q["document_checks"]["chair_press"] == "CURRENT_PUBLICATION_DATE_UNKNOWN"
    assert q["pit_status"] == "UNKNOWN"


def test_streamlit_report_comparison_shows_facts_and_sources_not_keyword_coverage():
    testing = pytest.importorskip("streamlit.testing.v1")
    source = "import json\nfrom fed_report_comparison_ui_v2 import render_comparison\npair=json.loads(" + repr(json.dumps(pair())) + ")\nrender_comparison(pair,'Press Conference','chair_press')"
    app = testing.AppTest.from_string(source, default_timeout=30).run()
    assert not app.exception
    rendered = "\n".join(x.value for group in (app.markdown, app.caption) for x in group)
    assert "3.50–3.75% → 3.75–4.00%" in rendered
    assert "Range shift: +25 basis points" in rendered
    assert "HOLD → RAISE" in rendered
    assert "UNANIMOUS" in rendered
    assert "official source" in rendered
    assert "keyword coverage" not in rendered.lower()


def test_press_wrapper_uses_utc_date_not_host_local_day(monkeypatch):
    from datetime import datetime, timezone
    frozen = datetime(2026, 10, 14, 23, 50, tzinfo=timezone.utc)
    monkeypatch.setattr(fed, "datetime", SimpleNamespace(now=lambda tz: frozen))
    seen = {}
    def loader(url, get, as_of):
        seen["as_of"] = as_of
        return {"text": ""}
    monkeypatch.setattr(fed, "load_press", loader)
    fed.press_page_data(PAGE)
    assert seen["as_of"] == date(2026, 10, 14)


def test_opening_transcript_is_explicitly_scoped_even_at_canonical_url(monkeypatch):
    opening = text("20260916").replace("Transcript of Chairman", "Opening Statement Transcript of Chairman", 1)
    mock_pdf(monkeypatch, opening)
    out = reports.load_press(PAGE, lambda u: SimpleNamespace(text="", content=b"%PDF-test"))
    assert out["scope"] == "OPENING_STATEMENT"


def test_mixed_press_scopes_compare_only_verified_opening_turns():
    raw = text("20260916")
    opening = reports.opening_remarks(raw)
    assert opening
    assert len(opening) < len(reports.chair_remarks(raw))
    old = {"available": True, "scope": "FULL_TRANSCRIPT_CHAIR_REMARKS", "text": reports.chair_remarks(raw), "opening_text": opening}
    new = {"available": True, "scope": "OPENING_STATEMENT", "text": opening, "opening_text": opening}
    a, b = reports.align_press_scope(old, new)
    assert a["scope"] == b["scope"] == "OPENING_STATEMENT"
    assert a["text"] == b["text"] == opening
    assert old["scope"] == "FULL_TRANSCRIPT_CHAIR_REMARKS"
    assert reports.compare(reports.document(a["text"], {}, a["scope"]), reports.document(b["text"], {}, b["scope"]))["available"]


def test_scope_alignment_does_not_invent_missing_opening():
    old = {"available": True, "scope": "FULL_TRANSCRIPT_CHAIR_REMARKS", "text": "old"}
    new = {"available": True, "scope": "OPENING_STATEMENT", "text": "new", "opening_text": "new"}
    assert reports.align_press_scope(old, new) == (old, new)


def test_preliminary_page_headers_are_removed_from_chair_evidence():
    raw = "CHAIR WARSH. Inflation is elevated.\nOctober 28, 2026 Chairman Warsh’s Press Conference PRELIMINARY\nPage 2 of 4\nGrowth is strong."
    assert "PRELIMINARY" not in reports.chair_remarks(raw)
    assert "Growth is strong" in reports.chair_remarks(raw)


def test_hold_decision_without_rate_does_not_invent_previous_range():
    out = reports.policy_facts('The Committee decided to maintain the target range for the federal funds rate. Economic activity is strong.')
    assert out['policy_action']['value'] == 'HOLD'
    assert 'target_range' not in out


def test_has_decided_and_unchanged_range_are_supported():
    out = reports.policy_facts('The Committee has decided to leave the target range unchanged at 3¾ to 4 percent.')
    assert out['policy_action']['value'] == 'HOLD'
    assert out['target_range']['value'] == [3.75, 4.0]


def test_forward_guidance_is_not_a_current_decision():
    assert not reports.policy_facts('The Committee may decide to lower the target range to 3 to 3.25 percent next year.')


def test_compact_card_uses_text_status_for_one_sided_numeric_facts():
    testing = pytest.importorskip('streamlit.testing.v1')
    data = pair()
    data['metrics']['target_range']['current'] = None
    data['metrics']['policy_action']['current'] = None
    source = 'import json\nfrom fed_report_comparison_ui_v2 import compact_comparison\ncompact_comparison(json.loads(' + repr(json.dumps(data)) + "),'Press Conference','chair_press')"
    app = testing.AppTest.from_string(source, default_timeout=30).run()
    assert not app.exception
    card = next(x.value for x in app.markdown if "comm-shift-flow" in x.value)
    assert card.count('Text retrieved') == 2
    assert 'Not reported' not in card


def test_october_official_pdf_target_rate_wording():
    raw = text('20261028-opening')
    facts = reports.policy_facts(reports.opening_remarks(raw))
    assert facts['policy_action']['value'] == 'HOLD'
    assert facts['target_range']['value'] == [3.75, 4.0]
    assert 'vote' not in facts
    assert 'target rate for the federal funds rate' in facts['target_range']['evidence']
