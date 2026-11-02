"""Local startup must make disabled dispatch visible without changing defaults."""

import logging
from unittest.mock import AsyncMock, Mock

import pytest
from markettwin_control_api import main
from markettwin_control_api.config import Settings


@pytest.mark.parametrize(
    ("environment", "enabled", "warns"),
    [("local", False, True), ("development", False, True),
     ("local", True, False), ("production", False, False)],
)
async def test_startup_dispatch_guard(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    environment: str,
    enabled: bool,
    warns: bool,
) -> None:
    settings = Settings.model_construct(app_env=environment, outbox_relay_enabled=enabled)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    database = Mock(close=AsyncMock())
    monkeypatch.setattr(main, "DatabaseRuntime", Mock(return_value=database))
    monkeypatch.setattr(main, "run_ingestion_processor", AsyncMock())
    monkeypatch.setattr(main, "run_human_action_reaper", AsyncMock())
    monkeypatch.setattr(main, "run_outbox_relay", AsyncMock())
    monkeypatch.setattr(main, "KafkaProducer", Mock())
    monkeypatch.setattr(main, "OutboxRelay", Mock())
    application = main.create_app()
    with caplog.at_level(logging.ERROR):
        async with application.router.lifespan_context(application):
            pass
    assert ("Outbox relay is DISABLED" in caplog.text) is warns
    database.close.assert_awaited_once()
