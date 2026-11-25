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


async def test_link_browser_permission_failure_does_not_blame_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def crawl(*args: object) -> tuple[str, bytes]:
        raise PermissionError("Access denied")

    monkeypatch.setattr(asyncio, "to_thread", crawl)
    processor = IngestionProcessor(MagicMock(spec=AsyncEngine), Settings())
    monkeypatch.setattr(processor, "_note", AsyncMock())
    with pytest.raises(LinkResearchFailed, match="server denied browser access"):
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


def _markdown_response():
    from markettwin_shared.knowledge_markdown import KnowledgeMarkdownResponse

    return KnowledgeMarkdownResponse.model_validate({
        "source": {"name": "pricing-fixture.md", "source_item_count": 1,
                   "processed_item_count": 1, "original_url": None},
        "files": [{
            "slug": "pricing", "title": "Pricing",
            "description": "Plan prices and the annual-discount exception.",
            "sections": [
                {"heading": "Plans",
                 "body_md": "The Starter plan costs $19 per month. The Pro plan costs $49 per month.",
                 "evidence_ordinals": [1], "uncertainties": []},
                {"heading": "Annual billing",
                 "body_md": "Annual billing saves 20%. Exception: the discount does not apply to the Starter plan.",
                 "evidence_ordinals": [1],
                 "uncertainties": [{"text": "The guide does not say whether prices include tax.",
                                    "evidence_ordinals": []}]},
            ],
        }],
        "evidence": [{
            "ordinal": 1, "evidence_type": "text",
            "content_text": "Starter $19 per month, Pro $49 per month. Annual billing saves 20%, except the Starter plan.",
            "content_json": None,
            "source_locator": {"item_index": 0},
            "extractor_name": "markdown", "extractor_version": "1",
        }],
        "extraction_issues": [],
        "usage": {"model": "configured-model", "calls": 1, "prompt_tokens": 120,
                  "completion_tokens": 240, "total_tokens": 360},
    })


async def test_markdown_transient_failure_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _markdown_response()
    calls: list[dict[str, object]] = []

    async def markdown(**kwargs: object):
        calls.append(kwargs)
        if len(calls) == 1:
            raise KnowledgeWorkerError(503, "Temporarily unavailable")
        return response

    client = MagicMock()
    client.markdown = AsyncMock(side_effect=markdown)
    monkeypatch.setattr(processor_module, "KnowledgeWorkerClient", lambda settings: client)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    processor = IngestionProcessor(MagicMock(spec=AsyncEngine), Settings())
    entry_id, workspace_id = uuid4(), uuid4()
    result = await processor._markdown_with_retry(  # pyright: ignore[reportPrivateUsage]
        filename="pricing.md", content_type="text/markdown", stream=BytesIO(b"source"),
        workspace_id=workspace_id, entry_id=entry_id,
    )
    assert result is response
    assert [call["entry_id"] for call in calls] == [entry_id, entry_id]
    assert [call["workspace_id"] for call in calls] == [workspace_id, workspace_id]


def _write_doubles(monkeypatch: pytest.MonkeyPatch, record: SimpleNamespace,
                   stored: dict[str, tuple[bytes, str]], captured: dict[str, object]):
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

        async def current_knowledge_file_version(self, entry_id: object) -> int:
            del entry_id
            return 0

        async def record_knowledge_files(self, rec: object, *, version: int, files: object) -> None:
            captured["record"] = rec
            captured["version"] = version
            captured["files"] = files

    class Storage:
        bucket = "knowledge-bucket"

        def __init__(self, settings: object) -> None:
            del settings

        async def download(self, *, bucket: str, key: str, stream: BytesIO) -> None:
            del bucket, key
            stream.write(b"# Pricing\n\nStarter $19, Pro $49.")
            stream.seek(0)

        async def put(self, *, key: str, stream: BytesIO, content_type: str) -> None:
            stored[key] = (stream.read(), content_type)

    monkeypatch.setattr(processor_module, "AsyncSession", Session)
    monkeypatch.setattr(processor_module, "IngestionRepository", Repository)
    monkeypatch.setattr(processor_module, "KnowledgeSourceStorage", Storage)


async def test_write_markdown_files_stores_versioned_files_manifest_and_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hashlib

    from markettwin_shared.knowledge_markdown import (
        KnowledgeEvidenceIndex,
        KnowledgeManifest,
        estimate_tokens,
    )

    stored: dict[str, tuple[bytes, str]] = {}
    _write_doubles(monkeypatch, SimpleNamespace(), stored, {})
    processor = IngestionProcessor(MagicMock(spec=AsyncEngine), Settings())
    workspace_id, entry_id = uuid4(), uuid4()
    version, rows = await processor._write_markdown_files(  # pyright: ignore[reportPrivateUsage]
        AsyncMock(), workspace_id=workspace_id, entry_id=entry_id,
        markdown=_markdown_response(), original_url=None,
    )
    prefix = f"knowledge/{workspace_id}/{entry_id}/files/v1"
    assert version == 1
    assert [row.slug for row in rows] == ["pricing"]
    body, content_type = stored[f"{prefix}/pricing.md"]
    text = body.decode("utf-8")
    assert content_type == "text/markdown"
    assert "file_version: 1" in text
    assert "$19 per month" in text and "$49 per month" in text
    assert "does not apply to the Starter plan" in text
    assert "## Uncertainties" in text and "include tax" in text
    assert rows[0].object_key == f"{prefix}/pricing.md"
    assert rows[0].sha256 == hashlib.sha256(body).hexdigest()
    assert rows[0].token_count == estimate_tokens(text)
    manifest = KnowledgeManifest.model_validate_json(stored[f"{prefix}/manifest.json"][0])
    assert manifest.version == 1 and manifest.usage.total_tokens == 360
    assert manifest.files[0].slug == "pricing"
    assert manifest.files[0].evidence_ordinals == (1,)
    index = KnowledgeEvidenceIndex.model_validate_json(stored[f"{prefix}/evidence.json"][0])
    assert [unit.ordinal for unit in index.units] == [1]


async def test_process_dual_writes_files_and_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    initial = KnowledgePreviewResponse.model_validate({
        "source": {"name": "pricing.md", "source_item_count": 0, "processed_item_count": 0},
        "application_knowledge": [], "artifacts": [], "skills": [],
        "evidence": [], "extraction_issues": [],
    })
    generated = KnowledgePreviewResponse.model_validate({
        "source": {"name": "pricing.md", "source_item_count": 1, "processed_item_count": 1},
        "application_knowledge": [{
            "name": "Pricing", "content": "Starter $19.", "evidence_ordinals": [1],
            "grounding_confidence": "high", "warnings": [],
        }],
        "artifacts": [], "skills": [], "evidence": [], "extraction_issues": [],
    })
    entry = SimpleNamespace(preview=initial.model_dump(mode="json"))
    asset = SimpleNamespace(
        status="uploaded", status_message=None, processed_at=None,
        declared_content_type="text/markdown", original_filename="pricing.md",
        bucket="sources", object_key="knowledge/source",
    )
    record = SimpleNamespace(entry=entry, asset=asset)
    stored: dict[str, tuple[bytes, str]] = {}
    captured: dict[str, object] = {}
    _write_doubles(monkeypatch, record, stored, captured)
    client = MagicMock()
    client.markdown = AsyncMock(return_value=_markdown_response())
    client.preview = AsyncMock(return_value=generated)
    monkeypatch.setattr(processor_module, "KnowledgeWorkerClient", lambda settings: client)
    processor = IngestionProcessor(MagicMock(spec=AsyncEngine), Settings())
    workspace_id, entry_id = uuid4(), uuid4()
    await processor._process(AsyncMock(), workspace_id, entry_id)  # pyright: ignore[reportPrivateUsage]
    prefix = f"knowledge/{workspace_id}/{entry_id}/files/v1"
    assert f"{prefix}/pricing.md" in stored
    assert f"{prefix}/manifest.json" in stored
    assert f"{prefix}/evidence.json" in stored
    assert captured["version"] == 1
    assert [row.slug for row in captured["files"]] == ["pricing"]  # type: ignore[union-attr]
    assert asset.status == "needs_user_review"
    assert entry.preview["application_knowledge"][0]["name"] == "Pricing"


async def test_process_markdown_failure_leaves_entry_failed_without_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = KnowledgePreviewResponse.model_validate({
        "source": {"name": "pricing.md", "source_item_count": 0, "processed_item_count": 0},
        "application_knowledge": [], "artifacts": [], "skills": [],
        "evidence": [], "extraction_issues": [],
    })
    entry = SimpleNamespace(preview=initial.model_dump(mode="json"))
    asset = SimpleNamespace(
        status="uploaded", status_message=None, processed_at=None,
        declared_content_type="text/markdown", original_filename="pricing.md",
        bucket="sources", object_key="knowledge/source",
    )
    record = SimpleNamespace(entry=entry, asset=asset)
    stored: dict[str, tuple[bytes, str]] = {}
    captured: dict[str, object] = {}
    _write_doubles(monkeypatch, record, stored, captured)
    client = MagicMock()
    client.markdown = AsyncMock(
        side_effect=KnowledgeWorkerError(422, "The source could not be read.")
    )
    client.preview = AsyncMock()
    monkeypatch.setattr(processor_module, "KnowledgeWorkerClient", lambda settings: client)
    processor = IngestionProcessor(MagicMock(spec=AsyncEngine), Settings())
    await processor._process(AsyncMock(), uuid4(), uuid4())  # pyright: ignore[reportPrivateUsage]
    assert asset.status == "parsing_failed"
    assert asset.status_message == "The source could not be read."
    assert captured == {}
    assert stored == {}
    client.preview.assert_not_awaited()


def _publish_doubles(monkeypatch: pytest.MonkeyPatch, record: SimpleNamespace,
                     stored: dict[str, tuple[bytes, str]], captured: dict[str, object]):
    """Processor doubles whose publish flip can be made to fail on demand."""
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

        async def current_knowledge_file_version(self, entry_id: object) -> int:
            del entry_id
            return 0

        async def record_knowledge_files(self, rec: object, *, version: int, files: object) -> None:
            if captured.get("fail_publish"):
                raise RuntimeError("Publish transaction failed.")
            captured["record"] = rec
            captured["version"] = version
            captured["files"] = files

    class Storage:
        bucket = "knowledge-bucket"

        def __init__(self, settings: object) -> None:
            del settings

        async def download(self, *, bucket: str, key: str, stream: BytesIO) -> None:
            del bucket, key
            stream.write(b"# Pricing\n\nStarter $19, Pro $49.")
            stream.seek(0)

        async def put(self, *, key: str, stream: BytesIO, content_type: str) -> None:
            stored[key] = (stream.read(), content_type)

    monkeypatch.setattr(processor_module, "AsyncSession", Session)
    monkeypatch.setattr(processor_module, "IngestionRepository", Repository)
    monkeypatch.setattr(processor_module, "KnowledgeSourceStorage", Storage)


def _publish_record() -> tuple[SimpleNamespace, SimpleNamespace, SimpleNamespace]:
    initial = KnowledgePreviewResponse.model_validate({
        "source": {"name": "pricing.md", "source_item_count": 0, "processed_item_count": 0},
        "application_knowledge": [], "artifacts": [], "skills": [],
        "evidence": [], "extraction_issues": [],
    })
    entry = SimpleNamespace(preview=initial.model_dump(mode="json"))
    asset = SimpleNamespace(
        status="uploaded", status_message=None, processed_at=None,
        declared_content_type="text/markdown", original_filename="pricing.md",
        bucket="sources", object_key="knowledge/source",
    )
    return SimpleNamespace(entry=entry, asset=asset), entry, asset


def _generated_preview() -> KnowledgePreviewResponse:
    return KnowledgePreviewResponse.model_validate({
        "source": {"name": "pricing.md", "source_item_count": 1, "processed_item_count": 1},
        "application_knowledge": [{
            "name": "Pricing", "content": "Starter $19.", "evidence_ordinals": [1],
            "grounding_confidence": "high", "warnings": [],
        }],
        "artifacts": [], "skills": [], "evidence": [], "extraction_issues": [],
    })


async def test_process_preview_failure_publishes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, entry, asset = _publish_record()
    stored: dict[str, tuple[bytes, str]] = {}
    captured: dict[str, object] = {}
    _publish_doubles(monkeypatch, record, stored, captured)
    client = MagicMock()
    client.markdown = AsyncMock(return_value=_markdown_response())
    client.preview = AsyncMock(
        side_effect=KnowledgeWorkerError(422, "The source could not be read.")
    )
    monkeypatch.setattr(processor_module, "KnowledgeWorkerClient", lambda settings: client)
    processor = IngestionProcessor(MagicMock(spec=AsyncEngine), Settings())
    await processor._process(AsyncMock(), uuid4(), uuid4())  # pyright: ignore[reportPrivateUsage]
    # Both outputs are generated before anything is written: a preview
    # failure leaves no blobs, no index rows, and a failed entry.
    assert stored == {}
    assert captured == {}
    assert asset.status == "parsing_failed"
    assert asset.status_message == "The source could not be read."


async def test_process_retry_after_preview_failure_publishes_exactly_one_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, entry, asset = _publish_record()
    stored: dict[str, tuple[bytes, str]] = {}
    captured: dict[str, object] = {}
    _publish_doubles(monkeypatch, record, stored, captured)
    attempts = {"count": 0}

    async def preview(**_kwargs: object) -> KnowledgePreviewResponse:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise KnowledgeWorkerError(422, "The source could not be read.")
        return _generated_preview()

    client = MagicMock()
    client.markdown = AsyncMock(return_value=_markdown_response())
    client.preview = AsyncMock(side_effect=preview)
    monkeypatch.setattr(processor_module, "KnowledgeWorkerClient", lambda settings: client)
    processor = IngestionProcessor(MagicMock(spec=AsyncEngine), Settings())
    workspace_id, entry_id = uuid4(), uuid4()
    await processor._process(AsyncMock(), workspace_id, entry_id)  # pyright: ignore[reportPrivateUsage]
    assert asset.status == "parsing_failed"
    assert stored == {}
    asset.status = "uploaded"  # A re-queued attempt sees a pending asset again.
    await processor._process(AsyncMock(), workspace_id, entry_id)  # pyright: ignore[reportPrivateUsage]
    prefix = f"knowledge/{workspace_id}/{entry_id}/files/v1"
    assert asset.status == "needs_user_review"
    assert captured["version"] == 1
    assert sorted(stored) == [
        f"{prefix}/evidence.json", f"{prefix}/manifest.json", f"{prefix}/pricing.md",
    ]
    assert entry.preview["application_knowledge"][0]["name"] == "Pricing"


async def test_process_publish_failure_rewrites_the_same_version_on_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, entry, asset = _publish_record()
    stored: dict[str, tuple[bytes, str]] = {}
    captured: dict[str, object] = {"fail_publish": True}
    _publish_doubles(monkeypatch, record, stored, captured)
    client = MagicMock()
    client.markdown = AsyncMock(return_value=_markdown_response())
    client.preview = AsyncMock(return_value=_generated_preview())
    monkeypatch.setattr(processor_module, "KnowledgeWorkerClient", lambda settings: client)
    processor = IngestionProcessor(MagicMock(spec=AsyncEngine), Settings())
    workspace_id, entry_id = uuid4(), uuid4()
    with pytest.raises(RuntimeError, match="Publish transaction failed."):
        await processor._process(AsyncMock(), workspace_id, entry_id)  # pyright: ignore[reportPrivateUsage]
    prefix = f"knowledge/{workspace_id}/{entry_id}/files/v1"
    first_bytes = stored[f"{prefix}/pricing.md"][0]
    assert "version" not in captured
    captured["fail_publish"] = False
    await processor._process(AsyncMock(), workspace_id, entry_id)  # pyright: ignore[reportPrivateUsage]
    # The unpublished version number is reused, so the retry overwrites the
    # same versioned keys with identical bytes and flips the pointer once.
    assert captured["version"] == 1
    assert stored[f"{prefix}/pricing.md"][0] == first_bytes
    assert not any("/v2/" in key for key in stored)
    assert asset.status == "needs_user_review"
