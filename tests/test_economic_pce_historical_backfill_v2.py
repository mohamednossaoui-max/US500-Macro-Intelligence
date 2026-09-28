import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pce_backfill', ROOT/'economic_pce_historical_backfill_v2.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

HTML='''<html><body>
EMBARGOED UNTIL RELEASE AT 8:30 a.m. EDT, Thursday, July 30, 2026
<h1>Personal Income and Outlays, June 2026</h1>
<p>From the preceding month, the PCE price index for June decreased 0.1 percent. Excluding food and energy, the PCE price index increased 0.1 percent.</p>
</body></html>'''

def test_parse_original_bea_release():
    rows=m.parse_bea_release(HTML,'https://www.bea.gov/example')
    assert [r['indicator'] for r in rows] == ['PCE_PRICE_INDEX','CORE_PCE']
    assert rows[0]['actual'] == -0.1
    assert rows[1]['actual'] == 0.1
    assert rows[0]['release_date'] == '2026-07-30'
    assert rows[0]['reference_period'] == 'June 2026'
    assert rows[0]['vintage_date'] == rows[0]['release_date']
    assert rows[0]['consensus'] is None

def test_ambiguous_less_than_point_one_fails_closed():
    html=HTML.replace('decreased 0.1 percent','decreased less than 0.1 percent')
    try:
        m.parse_bea_release(html,'x')
    except ValueError as e:
        assert 'ambiguous' in str(e)
    else:
        raise AssertionError('must fail closed')
