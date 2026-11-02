"""Calendar release dates remain midnight across New York clock changes."""
from types import SimpleNamespace
import pandas as pd
import pytest
import economic_official_sources_v1 as sources
from test_official_endpoint_alternates import Response, forbidden


@pytest.mark.parametrize('clock,release', [
    ('2026-11-02T08:48:02Z', '2026-10-29'),
    ('2026-03-09T12:00:00Z', '2026-03-05'),
    ('2026-11-05T13:29:59Z', '2026-10-29'),
    ('2026-11-05T13:30:00Z', '2026-11-05'),
    ('2026-03-12T12:29:59Z', '2026-03-05'),
    ('2026-03-12T12:30:00Z', '2026-03-12'),
])
def test_claims_calendar_date_across_dst(monkeypatch, clock, release):
    class ClockTimestamp(pd.Timestamp):
        @classmethod
        def now(cls, tz=None):
            return pd.Timestamp(clock).tz_convert(tz)
    class PandasClock:
        Timestamp = ClockTimestamp
        def __getattr__(self, name):
            return getattr(pd, name)
    monkeypatch.setattr(sources, 'pd', PandasClock())
    rd = pd.Timestamp(release)
    week = rd - pd.Timedelta(days=5)
    text = (f'EMBARGOED UNTIL 8:30 A.M. (Eastern) {rd.strftime("%A, %B %d, %Y")} '
            f'In the week ending {week.strftime("%B %d, %Y")}, the advance figure for '
            "seasonally adjusted initial claims was 194,000. The previous week's level "
            'was revised up by 1,000 from 193,000 to 194,000.')
    monkeypatch.setattr(sources, 'PdfReader', lambda _: SimpleNamespace(
        pages=[SimpleNamespace(extract_text=lambda: text)]))
    class Client:
        def get(self, url):
            if url == 'https://www.dol.gov/ui/data.pdf':
                raise forbidden(url)
            return Response('published each week on Thursday' if url.endswith('claims_arch.asp') else 'PDF')
        def post_public_form(self, url, data):
            # Include next week's document to check embargo filtering too.
            dates = [rd, rd + pd.Timedelta(days=7)]
            return Response(''.join(f'<a href="/press/{d.year}/{d.strftime("%m%d%y")}.pdf">Report</a>' for d in dates))
    rows = sources.collect_claims(Client())
    assert rows[-1]['release_date'] == release
    assert rows[-1]['actual'] == 194000
    assert rows[-1]['archive_release_date'] == release
    assert rows[0]['publication_status'] == 'REVISED'
