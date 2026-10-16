"""Transient source failures must recover without weakening validation."""
from unittest.mock import Mock, patch
import requests
import pytest
from economic_official_sources_v1 import Client, MetadataError

URL = 'https://www.census.gov/retail/marts/www/marts_current.pdf'


def response(status, headers=None, url=URL):
    r = requests.Response()
    r.status_code = status
    r.url = url
    r.request = requests.Request('GET', url).prepare()
    r.headers.update(headers or {})
    r._content = b'official evidence' if status == 200 else b'source unavailable'
    r._content_consumed = True
    return r


def client(tmp_path, effects):
    c = Client(tmp_path / 'evidence')
    c.session.get = Mock(side_effect=effects)
    return c


@pytest.mark.parametrize('status', [429, 500, 502, 503, 504])
def test_transient_failure_recovers_and_only_success_is_cached(tmp_path, status):
    ok = response(200)
    c = client(tmp_path, [response(status), ok])
    with patch('economic_official_sources_v1.time.sleep') as sleep:
        assert c.get(URL) is ok
        assert c.get(URL) is ok
    assert c.session.get.call_count == 2
    sleep.assert_called_once_with(2)
    assert [p.read_bytes() for p in c.directory.iterdir()] == [b'official evidence']


def test_persistent_503_raises_and_writes_no_evidence(tmp_path):
    c = client(tmp_path, [response(503) for _ in range(4)])
    with patch('economic_official_sources_v1.time.sleep') as sleep:
        with pytest.raises(requests.HTTPError) as error:
            c.get(URL)
    assert error.value.response.status_code == 503
    assert c.session.get.call_count == 4
    assert [call.args[0] for call in sleep.call_args_list] == [2, 4, 8]
    assert not c.cache
    assert not c.directory.exists()


@pytest.mark.parametrize('status', [400, 401, 403, 404])
def test_permanent_http_error_is_not_retried(tmp_path, status):
    c = client(tmp_path, [response(status)])
    with patch('economic_official_sources_v1.time.sleep') as sleep:
        with pytest.raises(requests.HTTPError):
            c.get(URL)
    assert c.session.get.call_count == 1
    sleep.assert_not_called()
    assert not c.cache


@pytest.mark.parametrize('error_type', [requests.Timeout, requests.ConnectionError])
def test_transient_network_failure_recovers(tmp_path, error_type):
    c = client(tmp_path, [error_type(), response(200)])
    with patch('economic_official_sources_v1.time.sleep'):
        assert c.get(URL).status_code == 200
    assert c.session.get.call_count == 2


@pytest.mark.parametrize('header, expected', [('12', 12), ('invalid', 2)])
def test_numeric_retry_after_is_bounded(tmp_path, header, expected):
    c = client(tmp_path, [response(503, {'Retry-After': header}), response(200)])
    with patch('economic_official_sources_v1.time.sleep') as sleep:
        c.get(URL)
    sleep.assert_called_once_with(expected)


def test_redirect_validation_still_applies_after_retry(tmp_path):
    c = client(tmp_path, [response(503), response(200, url='https://example.com/report')])
    with patch('economic_official_sources_v1.time.sleep'):
        with pytest.raises(MetadataError, match='Cross-host redirect'):
            c.get(URL)
    assert not c.cache
    assert not c.directory.exists()


def test_long_retry_after_fails_without_retrying_early(tmp_path):
    c=client(tmp_path,[response(429,{'Retry-After':'9999'}),response(200)])
    with patch('economic_official_sources_v1.time.sleep') as sleep:
        with pytest.raises(requests.HTTPError):c.get(URL)
    assert c.session.get.call_count==1 and not c.cache
    sleep.assert_not_called()
