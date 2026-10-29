from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
import liquidity_historical_collector_v1 as c


def freeze(monkeypatch):
    now = datetime(2026, 10, 29, 0, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(c, 'datetime', SimpleNamespace(now=lambda tz: now.astimezone(tz)))


@pytest.mark.parametrize('cutoff,expected', [('2026-10-29','2026-10-28'), ('2025-01-01','2025-01-01')])
def test_vintage_request_caps_day_without_mutating_input(monkeypatch, cutoff, expected):
    freeze(monkeypatch)
    params = {'realtime_start':'2019-01-01','realtime_end':cutoff}
    def get(url, params, **kw):
        assert params['realtime_end'] == expected
        return SimpleNamespace(status_code=200, json=lambda: {'vintage_dates':['2026-10-21']})
    monkeypatch.setattr(c.requests, 'get', get)
    assert c.fred_get('test',params,'WALCL','vintage dates')['vintage_dates']
    assert params['realtime_end'] == cutoff


def test_server_day_error_is_corrected_before_retry(monkeypatch):
    freeze(monkeypatch)
    calls=[]
    def get(url, params, **kw):
        calls.append(dict(params))
        if len(calls)==1:
            return SimpleNamespace(status_code=400,text="Variable realtime_end can not be after today's date (2026-10-27)")
        assert params['realtime_end']=='2026-10-27'
        return SimpleNamespace(status_code=200,json=lambda: {'vintage_dates':[]})
    monkeypatch.setattr(c.requests,'get',get)
    c.fred_get('test',{'realtime_start':'2019-01-01','realtime_end':'2026-10-29'},'WALCL','vintage dates')
    assert len(calls)==2


def test_initial_release_observation_params_are_preserved(monkeypatch):
    params={'output_type':4,'vintage_dates':'2026-10-21'}
    def get(url, params, **kw):
        assert params == {'output_type':4,'vintage_dates':'2026-10-21'}
        return SimpleNamespace(status_code=200,json=lambda: {'observations':[]})
    monkeypatch.setattr(c.requests,'get',get)
    c.fred_get('test',params,'WALCL','observations')
