"""Official BLS '-' gaps must not break later releases or permit stale fallback."""
import copy
import json
import pytest
import economic_bls_employment_ingestion_v1 as legacy
from economic_official_sources_v1 import collect_bls, MetadataError, BLS


def point(year, month, value):
    return {'year': str(year), 'period': f'M{month:02d}', 'periodName': 'Month',
            'value': value, 'footnotes': [{'code': '9', 'text': 'Data unavailable due to the 2025 lapse in appropriations.'}] if value == '-' else []}


def payload():
    return {'status': 'REQUEST_SUCCEEDED', 'Results': {'series': [
        {'seriesID': legacy.PAYROLL_SERIES, 'data': [point(2026, 9, '160100'), point(2026, 8, '160000')]},
        {'seriesID': legacy.UNEMPLOYMENT_SERIES, 'data': [point(2026, 9, '4.2'), point(2026, 8, '4.1'), point(2025, 10, '-')]}]}}


def test_historical_gap_diagnostic_staging_only(tmp_path, monkeypatch):
    body = payload(); gaps = []
    parsed = legacy.parse_monthly_observations(body, gaps)
    assert len(gaps) == 1 and gaps[0]['observation_month'] == '2025-10'
    assert gaps[0]['status'] == 'SOURCE_DATA_UNAVAILABLE'
    nfp = legacy.derive_nfp_change(parsed[legacy.PAYROLL_SERIES])
    unemployment = legacy.build_unemployment_record(parsed[legacy.UNEMPLOYMENT_SERIES], nfp['observation_month'])
    legacy.validate_employment_release(nfp, unemployment)
    monkeypatch.setattr(legacy, 'STAGING_DIR', tmp_path)
    monkeypatch.setattr(legacy, 'STAGING_JSON', tmp_path/'out.json')
    monkeypatch.setattr(legacy, 'STAGING_CSV', tmp_path/'out.csv')
    artifact = legacy.write_staging_artifact(nfp, unemployment, gaps)
    assert nfp['actual'] == 100000 and unemployment['actual'] == 4.2
    assert artifact['release_date'] is None and not artifact['pit_safe_for_canonical_merge']
    assert json.loads((tmp_path/'out.json').read_text())['unavailable_observations'] == gaps
    assert body == payload()


@pytest.mark.parametrize('series_index', [0, 1])
def test_latest_missing_cannot_fallback(series_index):
    body = payload(); body['Results']['series'][series_index]['data'].insert(0, point(2026, 10, '-'))
    with pytest.raises(RuntimeError, match='Latest BLS observation unavailable'):
        legacy.parse_monthly_observations(body)


def test_missing_payroll_baseline_cannot_bridge_gap():
    body = payload(); body['Results']['series'][0]['data'] = [point(2026,9,'160100'), point(2026,8,'-'), point(2026,7,'159900')]
    parsed = legacy.parse_monthly_observations(body)
    with pytest.raises(RuntimeError, match='not consecutive'):
        legacy.derive_nfp_change(parsed[legacy.PAYROLL_SERIES])


@pytest.mark.parametrize('bad', ['unexpected', '', 'nan', 'inf'])
def test_invalid_values_still_fail(bad):
    body = payload(); body['Results']['series'][1]['data'][0]['value'] = bad
    with pytest.raises(ValueError, match='Malformed BLS observation'):
        legacy.parse_monthly_observations(body)


@pytest.mark.parametrize('indicator', list(BLS))
def test_production_all_bls_indicators_refuse_missing_latest(indicator):
    class Client:
        def bls_payload(self, series):
            return {'status':'REQUEST_SUCCEEDED','Results':{'series':[{'seriesID':series,'data':[point(2026,9,'-'),point(2026,8,'100'),point(2026,7,'99')]}]}}
        def get(self, url):
            raise AssertionError('Missing latest must be rejected before resolving metadata')
    with pytest.raises(MetadataError,match='Latest BLS value unavailable'):
        collect_bls(Client(), indicator)
