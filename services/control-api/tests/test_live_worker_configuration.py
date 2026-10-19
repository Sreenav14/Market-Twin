"""Passive observation must enforce the same internal secret boundary as control."""

import pytest
from fastapi import HTTPException
from markettwin_control_api.api import live_browser
from markettwin_control_api.config import Settings
from pydantic import SecretStr


@pytest.mark.parametrize("secret", [None, "short", " " * 40])
def test_observation_rejects_weak_internal_secret(
    monkeypatch: pytest.MonkeyPatch, secret: str | None,
) -> None:
    settings = Settings.model_construct(
        hitl_internal_secret=SecretStr(secret) if secret is not None else None,
    )
    monkeypatch.setattr(live_browser, "get_settings", lambda: settings)
    with pytest.raises(HTTPException) as error:
        live_browser.worker_client()
    assert error.value.status_code == 503
