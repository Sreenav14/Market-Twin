"""Reject browser mutation requests outside the configured frontend origin."""

from fastapi import HTTPException, Request

from markettwin_control_api.config import get_settings


async def require_mutation_origin(request: Request) -> None:
    """Cover cookie sessions, login and multipart forms with one browser policy.

    Requests without browser headers or session cookies may use non-cookie
    authentication. They still pass each endpoint's authentication checks.
    """
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    origin = request.headers.get("origin")
    browser_request = (
        origin is not None
        or "sec-fetch-site" in request.headers
        or "markettwin_session" in request.cookies
    )
    if browser_request and (
        origin != get_settings().web_origin
        or request.headers.get("x-markettwin-request") != "1"
    ):
        raise HTTPException(403, "Request origin was rejected.")
