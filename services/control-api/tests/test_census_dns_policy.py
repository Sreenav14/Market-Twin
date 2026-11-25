"""Census requests dial only validated public addresses on every redirect."""

from unittest.mock import Mock

import httpx
import pytest
from markettwin_control_api.knowledge import census


@pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "10.0.0.1", "::1"])
async def test_private_dns_answers_never_reach_transport(monkeypatch, address):
    monkeypatch.setattr(census.socket, "getaddrinfo", lambda *_args, **_kwargs:
                        [(2, 1, 6, "", (address, 443))])
    transport = Mock(side_effect=AssertionError("must not connect"))
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        result = await census.HttpxCensusFetcher()._fetch(client, "https://app.example/")
    assert result.blocked_hop
    transport.assert_not_called()


async def test_public_dns_is_pinned_and_redirect_dns_is_rechecked(monkeypatch):
    def resolve(host, *_args, **_kwargs):
        return [(2, 1, 6, "", ("93.184.216.34" if host == "app.example" else "10.0.0.1", 443))]

    monkeypatch.setattr(census.socket, "getaddrinfo", resolve)
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "app.example"
        assert request.extensions["sni_hostname"] == "app.example"
        return httpx.Response(302, headers={"location": "https://private.example/"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await census.HttpxCensusFetcher()._fetch(client, "https://app.example/")
    assert result.blocked_hop
    assert len(requests) == 1
