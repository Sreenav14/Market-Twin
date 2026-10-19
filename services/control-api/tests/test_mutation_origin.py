"""Browser CSRF policy covers JSON, uploads and session mutations alike."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import Depends, FastAPI
from markettwin_control_api.api import mutation_origin


@pytest.mark.parametrize("path", ["/login", "/upload", "/privileged"])
@pytest.mark.parametrize("headers,cookies,expected", [
    ({"origin": "https://evil.test", "x-markettwin-request": "1"}, {}, 403),
    ({"origin": "https://app.test"}, {}, 403),
    ({"origin": "null", "x-markettwin-request": "1"}, {}, 403),
    ({}, {"markettwin_session": "opaque"}, 403),
    ({"sec-fetch-site": "same-site"}, {}, 403),
    ({"origin": "https://app.test", "x-markettwin-request": "1"},
     {"markettwin_session": "opaque"}, 200),
])
async def test_browser_mutations_require_origin_and_header(
    monkeypatch: pytest.MonkeyPatch, path: str, headers: dict[str, str],
    cookies: dict[str, str], expected: int,
) -> None:
    monkeypatch.setattr(mutation_origin, "get_settings", lambda: SimpleNamespace(
        web_origin="https://app.test",
    ))
    app = FastAPI(dependencies=[Depends(mutation_origin.require_mutation_origin)])
    for route in ("/login", "/upload", "/privileged"):
        app.add_api_route(route, lambda: {"ok": True}, methods=["POST"])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", cookies=cookies,
    ) as client:
        assert (await client.post(path, headers=headers)).status_code == expected
