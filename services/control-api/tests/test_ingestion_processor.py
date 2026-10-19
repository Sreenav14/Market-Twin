"""Job ownership must release its database lock, including on cancellation."""

import asyncio
from io import BytesIO
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from markettwin_control_api.config import Settings
from markettwin_control_api.knowledge import processor as processor_module
from markettwin_control_api.knowledge.client import KnowledgeWorkerError
from markettwin_control_api.knowledge.link_research import encode_link_marker
from markettwin_control_api.knowledge.processor import IngestionProcessor, LinkResearchFailed
from markettwin_shared.knowledge_preview import KnowledgePreviewResponse
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine


@pytest.mark.parametrize("cancelled", [False, True])
async def test_dispatch_releases_ownership_on_completion_or_cancellation(
    monkeypatch: pytest.MonkeyPatch, cancelled: bool,
) -> None:
    connection = AsyncMock(spec=AsyncConnection)
    connection.scalar.return_value = True
    context = AsyncMock()
    context.__aenter__.return_value = connection
    engine = MagicMock(spec=AsyncEngine)
    engine.connect.return_value = context
    processor = IngestionProcessor(cast(AsyncEngine, engine), Settings())
    process = AsyncMock(side_effect=asyncio.CancelledError() if cancelled else None)
    monkeypatch.setattr(processor, "_process", process)
    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            await processor.process_entry(uuid4(), uuid4())
    else:
        assert await processor.process_entry(uuid4(), uuid4())
    connection.rollback.assert_awaited_once()
    assert "pg_advisory_unlock" in str(connection.execute.await_args.args[0])
    assert connection.commit.await_count == 2


async def test_another_owner_prevents_duplicate_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = AsyncMock(spec=AsyncConnection)
    connection.scalar.return_value = False
    context = AsyncMock()
    context.__aenter__.return_value = connection
    engine = MagicMock(spec=AsyncEngine)
    engine.connect.return_value = context
    processor = IngestionProcessor(cast(AsyncEngine, engine), Settings())
    process = AsyncMock()
    monkeypatch.setattr(processor, "_process", process)
    assert not await processor.process_entry(uuid4(), uuid4())
    process.assert_not_awaited()
    connection.execute.assert_not_awaited()


@pytest.mark.parametrize("status", [502, 503, 504])
async def test_transient_failure_recovers_automatically(
    monkeypatch: pytest.MonkeyPatch, status: int,
) -> None:
    result = MagicMock(spec=KnowledgePreviewResponse)
    payloads: list[bytes] = []

    async def preview(**kwargs: object) -> KnowledgePreviewResponse:
        stream = cast(BytesIO, kwargs["stream"])
        payloads.append(stream.read())
        if len(payloads) == 1:
            raise KnowledgeWorkerError(status, "Temporarily unavailable")
        return cast(KnowledgePreviewResponse, result)

    client = MagicMock()
    client.preview = AsyncMock(side_effect=preview)
    def client_factory(settings: Settings) -> MagicMock:
        return client

    monkeypatch.setattr(processor_module, "KnowledgeWorkerClient", client_factory)
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)
    processor = IngestionProcessor(MagicMock(spec=AsyncEngine), Settings())
    response = await processor._preview_with_retry(  # pyright: ignore[reportPrivateUsage]
        filename="source.txt", content_type="text/plain", stream=BytesIO(b"original source"),
    )
    assert response is result
    assert payloads == [b"original source", b"original source"]
    sleep.assert_awaited_once_with(2)


@pytest.mark.parametrize("status,message,attempts", [
    (415, "Unsupported source format.", 1),
    (422, "The source could not be read.", 1),
    (502, "Knowledge generation reached its output limit.", 1),
    (503, "Temporarily unavailable", 3),
    (504, "Timed out", 3),
    (502, "Model temporarily failed", 3),
])
async def test_terminal_errors_and_retry_exhaustion(
    monkeypatch: pytest.MonkeyPatch, status: int, message: str, attempts: int,
) -> None:
    client = MagicMock()
    client.preview = AsyncMock(side_effect=KnowledgeWorkerError(status, message))
    def client_factory(settings: Settings) -> MagicMock:
        return client

    monkeypatch.setattr(processor_module, "KnowledgeWorkerClient", client_factory)
    sleep = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep)
    processor = IngestionProcessor(MagicMock(spec=AsyncEngine), Settings())
    with pytest.raises(KnowledgeWorkerError, match=message):
        await processor._preview_with_retry(  # pyright: ignore[reportPrivateUsage]
            filename="source.txt", content_type="text/plain", stream=BytesIO(b"source"),
        )
    assert client.preview.await_count == attempts
    assert [call.args[0] for call in sleep.await_args_list] == ([2, 4] if attempts == 3 else [])


def _session_double(record: SimpleNamespace) -> tuple[type, type]:
    class Session:
        def __init__(self, connection: object, expire_on_commit: bool = False) -> None:
            del connection, expire_on_commit

        async def __aenter__(self) -> "Session":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def begin(self) -> "Session":
            return self

    class Repository:
        def __init__(self, session: object) -> None:
            del session

        async def get(self, *_args: object, **_kwargs: object) -> SimpleNamespace:
            return record

    return Session, Repository


async def test_preview_replacement_preserves_trusted_original_source(monkeypatch):
    original = KnowledgePreviewResponse.model_validate({
        "source": {"name": "link.txt", "source_item_count": 0, "processed_item_count": 0,
                   "original_url": "https://example.com/docs"},
        "application_knowledge": [], "artifacts": [], "skills": [],
        "evidence": [], "extraction_issues": [],
    })
    generated = original.model_copy(update={
        "source": original.source.model_copy(update={"original_url": "https://other.example/"}),
    })
    entry = SimpleNamespace(preview=original.model_dump(mode="json"))
    asset = SimpleNamespace(status="processing", status_message=None, processed_at=None)
    session, repository = _session_double(SimpleNamespace(entry=entry, asset=asset))
    monkeypatch.setattr(processor_module, "AsyncSession", session)
    monkeypatch.setattr(processor_module, "IngestionRepository", repository)
    await IngestionProcessor._save(AsyncMock(), uuid4(), uuid4(), result=generated)
    assert entry.preview["source"]["original_url"] == "https://example.com/docs"
    assert asset.status == "needs_user_review"


async def test_queued_link_is_researched_before_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    stored: dict[str, object] = {}

    class Storage:
        def __init__(self, settings: Settings) -> None:
            del settings

        async def put(self, *, key: str, stream: BytesIO, content_type: str) -> None:
            stored["key"] = key
            stored["body"] = stream.read()
            stored["type"] = content_type

    def crawl(url: str, progress: object = None) -> tuple[str, bytes]:
        assert url == "https://example.com/"
        assert progress is not None
        return (
            "example.com-research.txt",
            b"SOURCE URL: https://example.com/\nObserved instructions",
        )

    asset = SimpleNamespace(
        status="processing", original_filename="example.com-link.txt",
        declared_content_type="text/x-markettwin-link", size_bytes=1, sha256=None,
        status_message=None,
    )
    session, repository = _session_double(SimpleNamespace(asset=asset))
    monkeypatch.setattr(processor_module, "KnowledgeSourceStorage", Storage)
    monkeypatch.setattr(processor_module, "research_link", crawl)
    monkeypatch.setattr(processor_module, "AsyncSession", session)
    monkeypatch.setattr(processor_module, "IngestionRepository", repository)
    processor = IngestionProcessor(MagicMock(spec=AsyncEngine), Settings())
    filename, content_type, payload = await processor._research_queued_link(  # pyright: ignore[reportPrivateUsage]
        AsyncMock(), uuid4(), uuid4(), "knowledge/key",
        BytesIO(encode_link_marker("https://example.com/")),
    ) or (None, None, None)
    assert filename == "example.com-research.txt"
    assert content_type == "text/plain"
    assert payload == stored["body"] == b"SOURCE URL: https://example.com/\nObserved instructions"
    assert asset.object_key == stored["key"]
    assert str(stored["key"]).startswith("knowledge/key/research/")
    assert asset.declared_content_type == "text/plain"
    assert asset.status_message == "Generating knowledge."


async def test_failed_link_research_keeps_a_specific_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def crawl(url: str, progress: object = None) -> tuple[str, bytes]:
        del url, progress
        raise ValueError("No readable public pages were found. Could not inspect https://example.com/.")

    asset = SimpleNamespace(status="processing", status_message=None)
    session, repository = _session_double(SimpleNamespace(asset=asset))
    monkeypatch.setattr(processor_module, "research_link", crawl)
    monkeypatch.setattr(processor_module, "AsyncSession", session)
    monkeypatch.setattr(processor_module, "IngestionRepository", repository)
    processor = IngestionProcessor(MagicMock(spec=AsyncEngine), Settings())
    with pytest.raises(LinkResearchFailed, match="No readable public pages"):
        await processor._research_queued_link(  # pyright: ignore[reportPrivateUsage]
            AsyncMock(), uuid4(), uuid4(), "knowledge/key",
            BytesIO(encode_link_marker("https://example.com/")),
        )


async def test_dispatch_scans_beyond_twenty_contended_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime

    rows = [(uuid4(), uuid4(), datetime.now(UTC)) for _ in range(21)]
    statements: list[object] = []

    class Session:
        def __init__(self, engine: object) -> None:
            pass

        async def __aenter__(self) -> "Session":
            return self

        async def __aexit__(self, *args: object) -> None:
            pass

        async def execute(self, statement: object) -> SimpleNamespace:
            statements.append(statement)
            return SimpleNamespace(all=lambda: rows[:20] if len(statements) == 1 else rows[20:])

    monkeypatch.setattr(processor_module, "AsyncSession", Session)
    processor = IngestionProcessor(MagicMock(spec=AsyncEngine), Settings())
    process = AsyncMock(side_effect=[False] * 20 + [True])
    monkeypatch.setattr(processor, "process_entry", process)
    assert await processor.process_next()
    assert process.await_count == 21
    assert len(statements) == 2
    assert "(knowledge.asset_versions.created_at, knowledge.ingestion_entries.id) >" in str(
        statements[1]
    )


async def test_link_cancellation_waits_for_crawl_before_releasing_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started, finish = asyncio.Event(), asyncio.Event()

    async def crawl(*args: object) -> tuple[str, bytes]:
        started.set()
        await finish.wait()
        return "source.txt", b"source"

    monkeypatch.setattr(asyncio, "to_thread", crawl)
    processor = IngestionProcessor(MagicMock(spec=AsyncEngine), Settings())
    monkeypatch.setattr(processor, "_note", AsyncMock())
    operation = asyncio.create_task(processor._research_queued_link(  # pyright: ignore[reportPrivateUsage]
        AsyncMock(), uuid4(), uuid4(), "key",
        BytesIO(encode_link_marker("https://example.com/")),
    ))
    await started.wait()
    operation.cancel()
    await asyncio.sleep(0)
    assert not operation.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await operation
