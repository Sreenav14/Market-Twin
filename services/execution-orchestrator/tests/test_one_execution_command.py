"""The diagnostic must share worker processing and acknowledge only afterward."""

import asyncio
from collections.abc import Awaitable, Callable
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from markettwin_shared.messaging import KafkaConsumerSettings, KafkaMessage


def load_script() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "run_one_execution_command.py"
    spec = spec_from_file_location("one_execution_command", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [None, RuntimeError, asyncio.CancelledError])
async def test_diagnostic_commit_order_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    error: type[BaseException] | None,
) -> None:
    script = load_script()
    calls: list[str] = []
    message = KafkaMessage("commands", 0, 1, None, b"{}")
    factory = object()

    async def process(received: KafkaMessage, sessions: object) -> None:
        assert received is message and sessions is factory
        calls.append("process")
        if error is not None:
            raise error()
        calls.append("processed")

    async def commit() -> None:
        calls.append("commit")

    async def stop() -> None:
        calls.append("stop")

    async def dispose() -> None:
        calls.append("dispose")

    consumer = SimpleNamespace(
        start=AsyncMock(),
        receive=AsyncMock(return_value=message),
        commit=AsyncMock(side_effect=commit),
        stop=AsyncMock(side_effect=stop),
    )
    engine = SimpleNamespace(dispose=AsyncMock(side_effect=dispose))
    consumer_constructor = Mock(return_value=consumer)
    monkeypatch.setattr(script, "database_url", Mock(return_value="postgresql+asyncpg://test"))
    monkeypatch.setattr(script, "create_database_engine", Mock(return_value=engine))
    monkeypatch.setattr(script, "create_session_factory", Mock(return_value=factory))
    monkeypatch.setattr(
        script,
        "load_kafka_consumer_settings",
        Mock(
            return_value=KafkaConsumerSettings(
                bootstrap_servers=("localhost:9092",),
                topic="commands",
                group_id="worker",
            )
        ),
    )
    monkeypatch.setattr(script, "KafkaConsumer", consumer_constructor)
    monkeypatch.setattr(script, "process_command", process)
    main = cast(Callable[[], Awaitable[None]], script.main)
    if error is None:
        await main()
        assert calls == ["process", "processed", "commit", "stop", "dispose"]
    else:
        with pytest.raises(error):
            await main()
        assert calls == ["process", "stop", "dispose"]
        consumer.commit.assert_not_awaited()
    settings = cast(KafkaConsumerSettings, consumer_constructor.call_args.args[0])
    assert settings.max_poll_interval_ms == 86_400_000
