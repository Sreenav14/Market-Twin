"""Doc 33 section 3.6: the internal knowledge-file read seam —
content by pinned id (sha-verified against the index row), the
collection manifest (index rows, headings merged from the stored
manifest when readable), and the internal-secret check."""

import json
from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from markettwin_control_api.api import internal_knowledge_files as internal_api
from markettwin_control_api.knowledge.files import KnowledgeFileRecord
from pydantic import SecretStr
from starlette.requests import Request

ENTRY_ID = uuid4()
WORKSPACE_ID = uuid4()
FILE_ID = uuid4()
TEXT = "# Pricing\n\nThe Team plan costs $40 per month.\n"


class AsyncContext:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *_args):
        return None


class FakeRepository:
    def __init__(self, *, by_id=None, rows=None):
        self._by_id = by_id
        self._rows = rows or []

    async def get_by_id(self, file_id):
        return self._by_id

    async def list_entry_version(self, *, entry_id, version):
        return self._rows


class FakeStorage:
    """key -> bytes; a missing key raises, like S3."""

    def __init__(self, objects):
        self._objects = objects

    async def download(self, *, bucket, key, stream):
        if key not in self._objects:
            raise RuntimeError("NoSuchKey")
        stream.write(self._objects[key])


def record(*, slug="pricing", version=1, text=TEXT):
    return KnowledgeFileRecord(
        id=FILE_ID, workspace_id=WORKSPACE_ID, ingestion_entry_id=ENTRY_ID,
        slug=slug, title="Pricing", description="Plan prices.",
        object_key=f"knowledge/{WORKSPACE_ID}/{ENTRY_ID}/files/v{version}/{slug}.md",
        sha256=sha256(text.encode("utf-8")).hexdigest(),
        token_count=42, version=version, status="approved",
    )


def wire(monkeypatch, *, repository, objects, secret=None):
    runtime = SimpleNamespace(
        session_factory=lambda: AsyncContext(SimpleNamespace()),
    )
    monkeypatch.setattr(
        internal_api, "get_database_runtime", lambda request: runtime,
    )
    monkeypatch.setattr(
        internal_api, "KnowledgeFileRepository", lambda session: repository,
    )
    storage = FakeStorage(objects)
    monkeypatch.setattr(
        internal_api, "KnowledgeSourceStorage", lambda settings: storage,
    )
    settings = SimpleNamespace(
        knowledge_internal_secret=secret, s3_bucket="bucket",
    )
    monkeypatch.setattr(internal_api, "get_settings", lambda: settings)


def make_request(headers=()):
    return Request({
        "type": "http", "method": "GET", "path": "/", "headers": list(headers),
    })


@pytest.mark.asyncio
async def test_content_returns_text_and_index_metadata(monkeypatch):
    row = record()
    wire(
        monkeypatch,
        repository=FakeRepository(by_id=row),
        objects={row.object_key: TEXT.encode("utf-8")},
    )
    body = await internal_api.knowledge_file_content(FILE_ID, make_request())
    assert body["text"] == TEXT
    assert body["slug"] == "pricing"
    assert body["token_count"] == 42
    assert body["sha256"] == row.sha256


@pytest.mark.asyncio
async def test_content_rejects_bytes_that_fail_the_index_sha(monkeypatch):
    row = record()
    wire(
        monkeypatch,
        repository=FakeRepository(by_id=row),
        objects={row.object_key: b"tampered bytes"},
    )
    with pytest.raises(HTTPException) as exc_info:
        await internal_api.knowledge_file_content(FILE_ID, make_request())
    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_content_unknown_file_is_404(monkeypatch):
    wire(monkeypatch, repository=FakeRepository(by_id=None), objects={})
    with pytest.raises(HTTPException) as exc_info:
        await internal_api.knowledge_file_content(FILE_ID, make_request())
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_internal_secret_is_enforced_when_configured(monkeypatch):
    row = record()
    wire(
        monkeypatch,
        repository=FakeRepository(by_id=row),
        objects={row.object_key: TEXT.encode("utf-8")},
        secret=SecretStr("s" * 32),
    )
    with pytest.raises(HTTPException) as exc_info:
        await internal_api.knowledge_file_content(FILE_ID, make_request())
    assert exc_info.value.status_code == 401
    body = await internal_api.knowledge_file_content(
        FILE_ID,
        make_request(headers=[(b"authorization", b"Bearer " + b"s" * 32)]),
    )
    assert body["text"] == TEXT


@pytest.mark.asyncio
async def test_manifest_merges_headings_from_the_stored_manifest(monkeypatch):
    pricing = record()
    refunds = KnowledgeFileRecord(
        **{**record(slug="refunds").__dict__, "id": uuid4(), "title": "Refunds",
           "object_key": f"knowledge/{WORKSPACE_ID}/{ENTRY_ID}/files/v1/refunds.md"}
    )
    manifest_key = (
        f"knowledge/{WORKSPACE_ID}/{ENTRY_ID}/files/v1/manifest.json"
    )
    manifest = json.dumps({"files": [
        {"slug": "pricing", "section_headings": ["Plans", "Exceptions"]},
        {"slug": "refunds", "section_headings": ["Windows"]},
    ]}).encode("utf-8")
    wire(
        monkeypatch,
        repository=FakeRepository(rows=[pricing, refunds]),
        objects={manifest_key: manifest},
    )
    body = await internal_api.knowledge_collection_manifest(
        ENTRY_ID, make_request(), version=1,
    )
    assert body["version"] == 1
    by_slug = {entry["slug"]: entry for entry in body["files"]}
    assert by_slug["pricing"]["section_headings"] == ["Plans", "Exceptions"]
    assert by_slug["refunds"]["file_id"] == str(refunds.id)
    assert "text" not in by_slug["pricing"]


@pytest.mark.asyncio
async def test_manifest_falls_back_to_index_rows_without_headings(monkeypatch):
    pricing = record()
    wire(
        monkeypatch,
        repository=FakeRepository(rows=[pricing]),
        objects={},  # the stored manifest cannot be read
    )
    body = await internal_api.knowledge_collection_manifest(
        ENTRY_ID, make_request(), version=1,
    )
    assert body["files"][0]["slug"] == "pricing"
    assert body["files"][0]["section_headings"] == []


@pytest.mark.asyncio
async def test_manifest_unknown_version_is_404(monkeypatch):
    wire(monkeypatch, repository=FakeRepository(rows=[]), objects={})
    with pytest.raises(HTTPException) as exc_info:
        await internal_api.knowledge_collection_manifest(
            ENTRY_ID, make_request(), version=9,
        )
    assert exc_info.value.status_code == 404
