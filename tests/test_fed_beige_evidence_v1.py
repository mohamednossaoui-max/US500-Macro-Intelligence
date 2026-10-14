from datetime import date
from pathlib import Path
from types import SimpleNamespace
import json

import pytest
import fed_intelligence as fed
import fed_beige_evidence_v1 as evidence
from fed_snapshot_ui_v1 import display_quality, issue_month, load_snapshot

FIXTURES = Path(__file__).parent / "fixtures" / "fed_beige"
TODAY = date(2026, 10, 14)


def fetch(url):
    if url == evidence.INDEX:
        name = "index.html"
    else:
        name = "202610-summary.html" if "202610" in url else "202608-summary.html"
    return SimpleNamespace(text=(FIXTURES / name).read_text())


def reports():
    return evidence.load_reports(fetch, TODAY)


def test_real_official_release_labels_not_issue_month_or_last_update():
    current, previous = reports()
    assert current["publication_date"] == "2026-10-14"
    assert current["issue_month"] == "2026-10"
    assert current["issue_date"] is None
    assert current["information_cutoff_date"] == "2026-10-05"
    assert previous["publication_date"] == "2026-09-02"
    assert previous["information_cutoff_date"] == "2026-08-24"


def test_official_comparison_values_are_reproduced():
    current, previous = reports()
    out = evidence.comparison(current, previous, fed.build_beige_analysis(current["text"]),
                              fed.build_beige_analysis(previous["text"]))
    assert out["available"]
    expected = {"districts_with_growth": (10, 9), "districts_with_robust_prices": (1, 3),
                "districts_with_accelerating_prices": (1, 4), "employment_modest": (3, 3),
                "employment_slight": (4, 5), "employment_unchanged": (5, 4)}
    for key, (old, new) in expected.items():
        assert out["changes"][key] == {"previous": old, "current": new, "change": new-old}
    assert "grew slightly" in out["previous_facts"]["consumer_spending_evidence"][0]
    assert "little or no change" in out["current_facts"]["consumer_spending_evidence"][0]


def test_future_publication_is_not_used_even_if_url_month_is_current():
    current, previous = evidence.load_reports(fetch, date(2026, 10, 13))
    assert current["issue_month"] == "2026-08"
    assert not previous["available"]


def test_last_update_alone_is_not_a_publication_date():
    html = '<h3>2026</h3><p><a href="beigebook202610-summary.htm">HTML</a></p><p>Last Update: October 14, 2026</p>'
    assert evidence.release_catalog(html) == []


def test_adjacent_release_date_is_not_borrowed():
    html = '<h3>2026</h3><div><p>September 2: <a href="beigebook202608-summary.htm">HTML</a></p><p><a href="beigebook202610-summary.htm">HTML</a></p></div>'
    assert [x["issue_month"] for x in evidence.release_catalog(html)] == ["2026-08"]


def test_missing_latest_content_is_not_replaced_by_stale_content():
    current, previous = evidence.load_reports(lambda u: None if "202610" in u else fetch(u), TODAY)
    assert current["issue_month"] == "2026-10"
    assert current["available"] is False
    assert previous["available"] is True
    assert not evidence.comparison(current, previous, {}, {})["available"]


def test_missing_previous_is_not_broadly_unchanged():
    current, previous = evidence.load_reports(lambda u: None if "202608" in u else fetch(u), TODAY)
    out = evidence.comparison(current, previous, {}, {})
    assert not out["available"]
    assert out["changes"] == {}


def test_navigation_and_district_highlights_do_not_contaminate_score():
    html = (FIXTURES / "202610-summary.html").read_text()
    baseline, _ = evidence.national_sections(html)
    polluted = html.replace('<h3>National Summary</h3>', '<nav>economic activity increased</nav><h3>National Summary</h3>')
    polluted = polluted.replace('<p id="f2">', '<h4>Highlights by Federal Reserve District</h4><p>economic activity increased</p><p id="f2">')
    actual, _ = evidence.national_sections(polluted)
    assert baseline == actual


def test_unrecognized_numbers_are_null_not_zero_or_neutral():
    facts = evidence.report_facts({"prices": "Many districts had price pressures."})
    assert facts["districts_with_accelerating_prices"] is None
    assert facts["districts_with_robust_prices"] is None


def test_nested_keywords_are_counted_once():
    signal = fed.beige_dimension_signal("economic activity increased.", "growth")
    assert signal["positive_hits"] == 1


def test_cutoff_after_publication_is_rejected():
    def bad(url):
        r = fetch(url)
        return SimpleNamespace(text=r.text.replace("October 5, 2026", "October 15, 2026"))
    current, _ = evidence.load_reports(bad, TODAY)
    assert not current["available"]
    assert current["text"] == ""


def test_landing_page_is_not_a_transcript(monkeypatch):
    monkeypatch.setattr(fed, "get", lambda _: SimpleNamespace(text="<h1>Press Conference</h1><p>Video</p>"))
    out = fed.press_page_data("https://www.federalreserve.gov/monetarypolicy/fomcpresconf20260916.htm")
    assert out["text"] == ""
    assert fed.analyze("Conference", out["text"])["available"] is False


def complete_snapshot():
    record = {"available": True, "publication_date": "2026-10-07",
              "publication_date_source": fed.CALENDAR, "meeting_date": "2026-09-16",
              "latest_publication_date": "2026-10-07", "catalog_verified": True}
    data = {"as_of_date": TODAY.isoformat(),
            "evidence_dates": {k: dict(record) for k in ["statement", "minutes", "chair_press", "sep", "beige_book"]}}
    data["evidence_dates"]["beige_book"]["information_cutoff_date"] = "2026-10-05"
    return data


def test_missing_metadata_never_claims_current_or_pit_safe():
    q = display_quality({"as_of_date": TODAY.isoformat(), "quality": {"freshness_status": "CURRENT", "pit_status": "PIT_SAFE"}}, TODAY)
    assert q["freshness_status"] == "UNVERIFIED"
    assert q["pit_status"] == "UNKNOWN"
    assert q["quality_gate"] == "DEGRADED"


def test_complete_metadata_is_only_date_checked_not_intraday_pit_guarantee():
    q = evidence.snapshot_quality(complete_snapshot(), TODAY)
    assert q["freshness_status"] == "CURRENT"
    assert q["pit_status"] == "DATE_CHECKED"
    assert "intraday" in q["pit_scope"]


@pytest.mark.parametrize("field,value", [("publication_date", "2026-10-15"), ("meeting_date", "2026-10-08")])
def test_invalid_date_order_is_exposed(field, value):
    data = complete_snapshot()
    data["evidence_dates"]["minutes"][field] = value
    assert evidence.snapshot_quality(data, TODAY)["pit_status"] == "INVALID_DATES"


def test_old_snapshot_and_superseded_document_are_stale():
    data = complete_snapshot()
    data["as_of_date"] = "2026-10-13"
    assert evidence.snapshot_quality(data, TODAY)["freshness_status"] == "STALE"
    data["as_of_date"] = TODAY.isoformat()
    data["evidence_dates"]["beige_book"]["latest_publication_date"] = "2026-10-14"
    assert evidence.snapshot_quality(data, TODAY)["document_checks"]["beige_book"] == "STALE"


def test_minutes_release_after_as_of_is_not_selected():
    links = {"minutes": {date(2026, 9, 16): "sep", date(2026, 7, 29): "jul"},
             "minutes_publication_dates": {date(2026, 9, 16): "2026-10-07", date(2026, 7, 29): "2026-08-19"}}
    assert fed.latest_document_date(links, "minutes", date(2026, 9, 30)) == date(2026, 7, 29)


def test_ui_rereads_changed_local_snapshot_without_caches(tmp_path):
    path = tmp_path / "fed.json"
    path.write_text(json.dumps({"beige_analysis": {"score": 55}}))
    first, first_source = load_snapshot(path, "unused", None)
    path.write_text(json.dumps({"beige_analysis": {"score": 53}}))
    second, second_source = load_snapshot(path, "unused", None)
    assert first["beige_analysis"]["score"] == 55
    assert second["beige_analysis"]["score"] == 53
    assert first_source != second_source
    assert issue_month({"issue_date": "2026-10-01"}) == "2026-10"


def test_source_correction_changes_content_hash():
    current, _ = reports()
    def corrected(url):
        r = fetch(url)
        return SimpleNamespace(text=r.text.replace("four Districts reported that the pace", "five Districts reported that the pace"))
    revised, _ = evidence.load_reports(corrected, TODAY)
    assert revised["publication_date"] == current["publication_date"]
    assert revised["content_sha256"] != current["content_sha256"]
    assert revised["facts"]["districts_with_accelerating_prices"] == 5


def test_insufficient_keyword_coverage_does_not_manufacture_neutral_score():
    current, _ = reports()
    analysis = fed.build_beige_analysis(current["text"])
    assert analysis["score"] is None
    assert analysis["tone"] == "INSUFFICIENT KEYWORD COVERAGE"
    assert analysis["dimensions"]["growth"]["score_100"] is None
    assert current["facts"]["districts_with_growth"] == 9


def test_missing_cutoff_and_future_snapshot_never_claim_verified_dates():
    data = complete_snapshot()
    data["evidence_dates"]["beige_book"].pop("information_cutoff_date")
    assert evidence.snapshot_quality(data, TODAY)["pit_status"] == "UNKNOWN"
    data = complete_snapshot()
    data["as_of_date"] = "2026-10-15"
    assert evidence.snapshot_quality(data, TODAY)["pit_status"] == "INVALID_DATES"


@pytest.mark.parametrize("text", ["September 16, 2026 Press Conference", "Last Update: October 7, 2026"])
def test_document_title_or_update_date_is_not_used_as_publication(text):
    assert fed.explicit_publication_date(text) is None


@pytest.mark.parametrize("text", ["For release at 2:00 p.m. EDT September 16, 2026", "Published: September 16, 2026"])
def test_document_explicit_publication_date_is_preserved(text):
    assert fed.explicit_publication_date(text) == "2026-09-16"
