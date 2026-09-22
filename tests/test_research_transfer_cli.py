import httpx
import pytest

from scripts import research_transfer


@pytest.mark.parametrize('status', [200, 201, 409])
def test_remote_archive_transfer_status(monkeypatch, status):
    monkeypatch.setenv('BKTSTR_BASE_URL', 'https://research.example')
    monkeypatch.setenv('BKTSTR_API_KEY', 'test-only')
    client_class = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json={'saved': True}))
    monkeypatch.setattr(research_transfer.httpx, 'Client', lambda **kwargs: client_class(transport=transport, **kwargs))
    if status == 409:
        with pytest.raises(ValueError, match='HTTP 409'):
            research_transfer.remote_request('POST', '/api/v1/research/archives', bundle={})
    else:
        assert research_transfer.remote_request('POST', '/api/v1/research/archives', bundle={}) == {'saved': True}
