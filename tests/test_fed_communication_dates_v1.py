from datetime import date
from types import SimpleNamespace
from bs4 import BeautifulSoup
import fed_intelligence as fed
from fed_communication_ui_v1 import communication_dates


def anchor(html):
    return BeautifulSoup(html, 'html.parser').find('a')


def test_explicit_release_is_separate_from_meeting():
    a=anchor('<div><a href="/monetarypolicy/fomcminutes20260916.htm">HTML</a> (Released October 7, 2026)</div>')
    assert fed.minutes_publication_date(a,date(2026,9,16))=='2026-10-07'


def test_no_release_is_never_inferred():
    a=anchor('<div><a href="fomcminutes20260916.htm">HTML</a> Last Update: October 7, 2026</div>')
    assert fed.minutes_publication_date(a,date(2026,9,16)) is None


def test_neighbor_meeting_release_is_not_borrowed():
    a=anchor('<div><div><a href="fomcminutes20260916.htm">HTML</a></div><div><a href="fomcminutes20260729.htm">HTML</a> (Released August 19, 2026)</div></div>')
    assert fed.minutes_publication_date(a,date(2026,9,16)) is None


def test_release_before_meeting_is_rejected():
    a=anchor('<div><a href="fomcminutes20260916.htm">HTML</a> (Released August 19, 2026)</div>')
    assert fed.minutes_publication_date(a,date(2026,9,16)) is None


def test_discovery_preserves_document_links_and_adds_metadata(monkeypatch):
    html='<div><a href="/monetarypolicy/fomcminutes20260916.htm">HTML</a> (Released October 7, 2026)</div>'
    monkeypatch.setattr(fed,'get',lambda url:SimpleNamespace(text=html))
    links=fed.discover_links()
    assert links['minutes'][date(2026,9,16)].endswith('fomcminutes20260916.htm')
    assert links['minutes_publication_dates'][date(2026,9,16)]=='2026-10-07'


def test_ui_distinguishes_both_dates_and_legacy_is_unavailable():
    item={'current_date':'2026-09-16','previous_date':'2026-07-29','current_publication_date':'2026-10-07'}
    text=communication_dates('minutes',item)
    assert 'Meeting dates: 2026-07-29 → 2026-09-16' in text
    assert 'Current release: 2026-10-07' in text
    assert 'Previous release: Unavailable' in text
    assert 'Current release: Unavailable' in communication_dates('minutes',{'current_date':'2026-09-16'})
    assert '<script>' not in communication_dates('minutes',{'current_publication_date':'<script>'})
    assert communication_dates('statement',item)=='2026-07-29 → 2026-09-16'
