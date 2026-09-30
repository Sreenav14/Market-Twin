"""Kafka outages must never change API process health."""

import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from markettwin_control_api import main


@pytest.mark.asyncio
@pytest.mark.parametrize("available", [True, False])
async def test_kafka_health_is_separate(
    monkeypatch: pytest.MonkeyPatch,
    available: bool,
) -> None:
    producer = AsyncMock()
    if not available:
        producer.start.side_effect = OSError("secret internal connection error")
    monkeypatch.setattr(main, "KafkaProducer", Mock(return_value=producer))
    application = main.create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/health/kafka")
        process = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == ("connected" if available else "unavailable")
    assert "secret" not in response.text
    assert process.status_code == 200
    assert process.json()["status"] == "ok"
    producer.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_kafka_health_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    producer = AsyncMock()

    async def hang() -> None:
        await asyncio.Event().wait()

    producer.start.side_effect = hang
    timeout = asyncio.timeout

    def short_timeout(seconds: float) -> asyncio.Timeout:
        return timeout(0.01)

    monkeypatch.setattr(asyncio, "timeout", short_timeout)
    monkeypatch.setattr(main, "KafkaProducer", Mock(return_value=producer))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.create_app()),
        base_url="http://test",
    ) as client:
        response = await asyncio.wait_for(client.get("/api/v1/health/kafka"), 1)
    assert response.json()["status"] == "unavailable"
    producer.stop.assert_awaited_once()
