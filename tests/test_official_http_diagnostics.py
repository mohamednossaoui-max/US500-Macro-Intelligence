import requests
import pytest
from economic_official_sources_v1 import http_error_diagnostic

@pytest.mark.parametrize('status',[400,403,404,429,500])
def test_http_status_endpoint_and_method_without_secrets(status,monkeypatch):
    monkeypatch.setenv('CENSUS_API_KEY','TEST_PRIVATE_TOKEN')
    response=requests.Response();response.status_code=status
    response.url='https://api.census.gov/data/timeseries/eits/mrtsadv?key=TEST_PRIVATE_TOKEN'
    response._content=b'PRIVATE RESPONSE BODY'
    response.request=requests.Request('GET',response.url).prepare()
    error=requests.HTTPError('Sensitive HTTP error TEST_PRIVATE_TOKEN',response=response)
    diagnostic=http_error_diagnostic(error)
    assert f'status={status}' in diagnostic and 'method=GET' in diagnostic
    assert 'endpoint=https://api.census.gov/data/timeseries/eits/mrtsadv' in diagnostic
    assert 'TEST_PRIVATE_TOKEN' not in diagnostic and '?' not in diagnostic
    assert 'PRIVATE RESPONSE BODY' not in diagnostic

def test_http_without_request_does_not_use_exception_text():
    diagnostic=http_error_diagnostic(requests.HTTPError('URL ?key=TEST_PRIVATE_TOKEN'))
    assert 'TEST_PRIVATE_TOKEN' not in diagnostic
    assert 'status=unknown' in diagnostic
