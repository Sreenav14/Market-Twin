"""Audit artifacts must be uploaded and linked before claiming screenshot availability."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from markettwin_execution_orchestrator.slop import evidence


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "missing", "upload"])
async def test_state_evidence_links_only_successfully_stored_artifacts(monkeypatch, failure):
    artifact_id, execution_id = uuid4(), uuid4()
    upload = AsyncMock(side_effect=OSError("Unavailable") if failure == "upload" else None)
    storage = Mock(return_value=SimpleNamespace(upload=upload))
    monkeypatch.setattr(evidence.S3ArtifactStorage, "from_environment", storage)
    create = AsyncMock(return_value=artifact_id)
    monkeypatch.setattr(evidence, "ArtifactRepository", lambda _: SimpleNamespace(create=create))
    state = {"url": "https://app.test/", "viewport": "mobile320", "interaction_path": "Menu",
             "screenshot_path": None if failure == "missing" else "screenshot.png",
             "page_signals": []}
    await evidence.save_state_evidence(state, session=Mock(), execution_id=execution_id)
    if failure:
        create.assert_not_awaited()
        assert not state.get("screenshot_artifact_id")
        assert state["page_signals"][0]["rule_id"] == "UI_EVIDENCE_UNAVAILABLE"
    else:
        assert state["screenshot_artifact_id"] == str(artifact_id)
        assert create.await_args.kwargs["metadata"]["interaction_path"] == "Menu"
        assert create.await_args.kwargs["execution_id"] == execution_id
        await evidence.save_state_evidence(state, session=Mock(), execution_id=execution_id)
        upload.assert_awaited_once()
        create.assert_awaited_once()


@pytest.mark.asyncio
async def test_database_failure_does_not_claim_evidence_or_hide_failed_transaction(monkeypatch):
    monkeypatch.setattr(evidence.S3ArtifactStorage, "from_environment",
                        lambda: SimpleNamespace(upload=AsyncMock()))
    monkeypatch.setattr(evidence, "ArtifactRepository", lambda _: SimpleNamespace(
        create=AsyncMock(side_effect=RuntimeError("Database unavailable"))))
    state = {"screenshot_path": "shot.png", "page_signals": []}
    with pytest.raises(RuntimeError, match="Database"):
        await evidence.save_state_evidence(state, session=Mock(), execution_id=uuid4())
    assert not state.get("screenshot_artifact_id")


async def test_upload_leaves_progress_lock_available(monkeypatch):
    lock = asyncio.Lock()

    async def upload(**_):
        assert not lock.locked()

    async def create(**_):
        assert lock.locked()
        return uuid4()

    monkeypatch.setattr(evidence.S3ArtifactStorage, "from_environment",
                        lambda: SimpleNamespace(upload=upload))
    monkeypatch.setattr(evidence, "ArtifactRepository", lambda _: SimpleNamespace(create=create))
    state = {"screenshot_path": "shot.png", "page_signals": []}
    await evidence.save_state_evidence(state, session=Mock(), execution_id=uuid4(), write_lock=lock)
    assert state["screenshot_artifact_id"]

@pytest.mark.asyncio
async def test_visual_finding_retains_only_its_referenced_view():
    states = [
        {"elements": [], "page_signals": [], "viewport": "desktop1280"},
        {"elements": [], "page_signals": [], "viewport": "mobile320"},
    ]
    saved = []

    async def save(state):
        saved.append(state["viewport"])
        state["screenshot_artifact_id"] = "mobile-proof"

    await evidence.retain_finding_evidence(states, [], save)
    assert saved == []
    finding = {"rule_id": "UI_VISUAL_REVIEW", "severity": "review", "evidence_indexes": [1, 1, 9]}
    await evidence.retain_finding_evidence(states, [finding], save)
    assert saved == ["mobile320"]
    assert finding["evidence_artifact_ids"] == ["mobile-proof"]
