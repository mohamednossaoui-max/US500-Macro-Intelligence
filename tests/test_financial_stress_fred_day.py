from datetime import datetime, timezone
from types import SimpleNamespace
import financial_stress_historical_collector_v1 as collector


def setup(monkeypatch, cutoff):
    monkeypatch.setattr(collector, 'END', collector.pd.Timestamp(cutoff))
    monkeypatch.setattr(collector, 'get_fred_api_key', lambda: 'test-only')
    frozen = datetime(2026, 10, 29, 0, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(collector, 'datetime', SimpleNamespace(now=lambda tz: frozen.astimezone(tz)))


def test_utc_midnight_uses_fred_day_and_keeps_initial_release(monkeypatch):
    setup(monkeypatch, '2026-10-29')
    def get(url, params, **kwargs):
        assert params['realtime_end'] == '2026-10-28'
        assert params['output_type'] == 4
        return SimpleNamespace(ok=True, json=lambda: {'observations': []})
    assert collector.get_fred_observations(SimpleNamespace(get=get), 'NFCI') == []


def test_historical_cutoff_is_not_extended(monkeypatch):
    setup(monkeypatch, '2025-01-15')
    def get(url, params, **kwargs):
        assert params['realtime_end'] == '2025-01-15'
        return SimpleNamespace(ok=True, json=lambda: {'observations': []})
    collector.get_fred_observations(SimpleNamespace(get=get), 'ANFCI')


def test_server_clock_rejection_changes_request_before_retry(monkeypatch):
    setup(monkeypatch, '2026-10-29')
    calls = []
    def get(url, params, **kwargs):
        calls.append(dict(params))
        if len(calls) == 1:
            return SimpleNamespace(ok=False, status_code=400, json=lambda: {'error_code': 400, 'error_message': "Variable realtime_end can not be after today's date (2026-10-27) unless it's equal to the real-time max date 9999-12-31."})
        assert params['realtime_end'] == '2026-10-27'
        assert params['output_type'] == 4
        return SimpleNamespace(ok=True, json=lambda: {'observations': []})
    collector.get_fred_observations(SimpleNamespace(get=get), 'NFCI')
    assert len(calls) == 2
