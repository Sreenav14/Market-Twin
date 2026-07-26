"""Test the health-check endpoint."""

from typing import cast

from fastapi.testclient import TestClient
from httpx import Response
from markettwin_control_api.main import app


def test_health_check() -> None:
    """Confirm that the Control API is running."""

    with TestClient(app) as client:
        response = cast(
            Response,
            client.get("/health"),  # pyright: ignore[reportUnknownMemberType]
        )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "control-api",
        "version": "0.1.0",
        "environment": "local",
    }