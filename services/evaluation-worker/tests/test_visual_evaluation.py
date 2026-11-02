"""Tests for evidence-backed visual evaluation."""

from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from markettwin_evaluation_worker import visual_evaluation
from markettwin_evaluation_worker.persistence.evaluation_repository import (
    EvaluationRepository,
    VisualArtifactRecord,
    VisualEvidenceSet,
)
from markettwin_evaluation_worker.persistence.visual_cache import VisualResultCache
from markettwin_evaluation_worker.visual_artifact_storage import (
    VisualArtifactStorage,
)
from markettwin_evaluation_worker.visual_verifier import (
    VisualVerificationResult,
)


class FakeRepository:
    def __init__(
        self,
        evidence: tuple[
            VisualEvidenceSet,
            ...
        ],
    ) -> None:
        self.evidence = evidence

        self.calls: list[
            tuple[
                UUID,
                tuple[int, ...],
            ]
        ] = []

    async def list_visual_evidence(
        self,
        *,
        execution_id: UUID,
        step_ids: tuple[int, ...],
    ) -> tuple[VisualEvidenceSet, ...]:
        self.calls.append(
            (
                execution_id,
                step_ids,
            )
        )

        return self.evidence


class FakeStorage:
    def __init__(self) -> None:
        self.downloaded: list[UUID] = []

    async def download(
        self,
        *,
        artifact: VisualArtifactRecord,
        directory: Path,
    ) -> Path:
        self.downloaded.append(
            artifact.artifact_id
        )

        path = (
            directory
            / f"{artifact.artifact_id}.png"
        )

        path.write_bytes(
            artifact.kind.encode()
        )

        return path


async def test_visual_retry_reuses_only_matching_pixels_prompt_model_and_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: dict[tuple[UUID, UUID, str], VisualVerificationResult] = {}
    calls = 0

    class Cache:
        async def get(
            self, *, run_id: UUID, execution_id: UUID, key: str,
        ) -> VisualVerificationResult | None:
            return saved.get((run_id, execution_id, key))

        async def put(
            self, *, run_id: UUID, execution_id: UUID, key: str,
            result: VisualVerificationResult,
        ) -> None:
            saved[run_id, execution_id, key] = result

    class Storage(FakeStorage):
        pixels = b"first"

        async def download(self, *, artifact: VisualArtifactRecord, directory: Path) -> Path:
            path = await super().download(artifact=artifact, directory=directory)
            path.write_bytes(self.pixels)
            return path

    async def verify(**_kwargs: object) -> VisualVerificationResult:
        nonlocal calls
        calls += 1
        return VisualVerificationResult("satisfied", "Visible.", ())

    monkeypatch.setattr(visual_evaluation, "verify_visual_criterion", verify)
    monkeypatch.setenv("VISUAL_MODEL_NAME", "openai/gpt-4o-mini")
    run_id, execution_id = uuid4(), uuid4()
    storage, cache = Storage(), Cache()
    evidence = (VisualEvidenceSet(step_id=1, viewport=VisualArtifactRecord(
        artifact_id=uuid4(), step_id=1, kind="viewport", storage_provider="minio",
        bucket="markettwin", object_key="executions/image.png", content_type="image/png",
    )),)

    async def evaluate(criterion: str, execution: UUID = execution_id) -> None:
        await visual_evaluation.evaluate_visual_criterion_from_evidence(
            test_run_id=run_id, journey_id=uuid4(), execution_id=execution,
            agent_snapshot_id=uuid4(), criterion=criterion, evidence=evidence,
            storage=cast(VisualArtifactStorage, storage), cache=cast(VisualResultCache, cache),
        )

    await evaluate("Heading is visible.")
    await evaluate("Heading is visible.")
    assert calls == 1  # Simulated later report failure/retry reuses the judgment.
    await evaluate("Button is visible.")
    assert calls == 2
    storage.pixels = b"changed"
    await evaluate("Button is visible.")
    assert calls == 3
    monkeypatch.setenv("VISUAL_MODEL_NAME", "openai/gpt-4o")
    await evaluate("Button is visible.")
    assert calls == 4
    await evaluate("Button is visible.", uuid4())
    assert calls == 5


@pytest.mark.parametrize("focused", [False, True])
@pytest.mark.parametrize("status", ["unsatisfied", "satisfied"])
async def test_viewport_only_failure_cannot_confirm_a_product_defect(
    monkeypatch: pytest.MonkeyPatch, focused: bool, status: str,
) -> None:
    viewport = VisualArtifactRecord(
        artifact_id=uuid4(), step_id=7, kind="viewport", storage_provider="minio",
        bucket="markettwin", object_key="viewport.png", content_type="image/png",
    )
    crop = VisualArtifactRecord(
        artifact_id=uuid4(), step_id=7, kind="element_crop", storage_provider="minio",
        bucket="markettwin", object_key="crop.png", content_type="image/png",
    )

    async def verify(**_: object) -> VisualVerificationResult:
        return VisualVerificationResult(
            status=cast(visual_evaluation.VisualVerificationStatus, status),
            rationale="Expected destination heading is absent.", observed_details=(),
        )

    monkeypatch.setattr(visual_evaluation, "verify_visual_criterion", verify)
    result = await visual_evaluation.evaluate_visual_criterion_from_evidence(
        test_run_id=uuid4(), journey_id=uuid4(), execution_id=uuid4(),
        agent_snapshot_id=uuid4(), criterion="Billing settings heading is visible.",
        evidence=(VisualEvidenceSet(
            step_id=7, viewport=viewport, element_crop=crop if focused else None,
        ),), storage=cast(VisualArtifactStorage, FakeStorage()),
    )
    assert result.status == (
        "unverified" if status == "unsatisfied" and not focused else status
    )
    assert result.evidence_step_id == 7
    assert result.artifact_ids == ((viewport.artifact_id, crop.artifact_id)
                                   if focused else (viewport.artifact_id,))


@pytest.mark.asyncio
async def test_visual_evaluation_uses_viewport_and_crop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion evaluation should send exact selected pixels to vision."""

    execution_id = uuid4()

    viewport_id = uuid4()
    crop_id = uuid4()

    viewport = VisualArtifactRecord(
        artifact_id=viewport_id,
        step_id=7,
        kind="viewport",
        storage_provider="minio",
        bucket="markettwin",
        object_key="viewport.png",
        content_type="image/png",
    )

    crop = VisualArtifactRecord(
        artifact_id=crop_id,
        step_id=7,
        kind="element_crop",
        storage_provider="minio",
        bucket="markettwin",
        object_key="crop.png",
        content_type="image/png",
    )

    repository = FakeRepository(
        evidence=(
            VisualEvidenceSet(step_id=8, action_type="click", step_status="completed"),
            VisualEvidenceSet(
                step_id=6, action_type="click", step_status="failed",
                action_summary='Click semantic target {"name": "Continue"}.',
            ),
            VisualEvidenceSet(
                step_id=7,
                action_type="capture_element",
                step_status="completed",
                viewport=viewport,
                element_crop=crop,
            ),
        )
    )

    storage = FakeStorage()

    seen_images: list[
        tuple[bytes, bytes | None]
    ] = []

    async def fake_verify(
        *,
        criterion: str,
        viewport_path: Path,
        focused_path: Path | None = None,
        execution_context: tuple[dict[str, object], ...] = (),
    ) -> VisualVerificationResult:
        assert (
            criterion
            == "Software testing heading is readable."
        )
        assert execution_context == (
            {"step_id": 6, "action_type": "click", "status": "failed",
             "target": 'Click semantic target {"name": "Continue"}.'},
            {"step_id": 7, "action_type": "capture_element", "status": "completed"},
        )

        seen_images.append(
            (
                viewport_path.read_bytes(),  # noqa: ASYNC240
                (
                    focused_path.read_bytes()  # noqa: ASYNC240
                    if focused_path is not None
                    else None
                ),
            )
        )

        return VisualVerificationResult(
            status="satisfied",
            rationale=(
                "The heading is clearly visible "
                "and readable."
            ),
            observed_details=(
                "The heading is unobscured.",
            ),
        )

    monkeypatch.setattr(
        visual_evaluation,
        "verify_visual_criterion",
        fake_verify,
    )

    result = (
        await visual_evaluation
        .evaluate_visual_criterion_from_steps(
            test_run_id=uuid4(),
            journey_id=uuid4(),
            criterion=(
                "Software testing heading is readable."
            ),
            execution_id=execution_id,
            agent_snapshot_id=uuid4(),
            step_ids=(6, 7, 8),
            repository=cast(
                EvaluationRepository,
                repository,
            ),
            storage=cast(
                VisualArtifactStorage,
                storage,
            ),
        )
    )

    assert result.status == "satisfied"

    assert result.evidence_step_id == 7

    assert result.artifact_ids == (
        viewport_id,
        crop_id,
    )

    assert repository.calls == [
        (
            execution_id,
            (6, 7, 8),
        )
    ]

    assert storage.downloaded == [
        viewport_id,
        crop_id,
    ]

    assert seen_images == [
        (
            b"viewport",
            b"element_crop",
        )
    ]


@pytest.mark.asyncio
async def test_visual_evaluation_is_unverified_without_viewport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing screenshot evidence must not trigger a model call."""

    execution_id = uuid4()

    repository = FakeRepository(
        evidence=(
            VisualEvidenceSet(
                step_id=7,
            ),
        )
    )

    storage = FakeStorage()

    async def fail_if_called(
        **_: object,
    ) -> VisualVerificationResult:
        raise AssertionError(
            "Vision model must not be called."
        )

    monkeypatch.setattr(
        visual_evaluation,
        "verify_visual_criterion",
        fail_if_called,
    )

    result = (
        await visual_evaluation
        .evaluate_visual_criterion_from_steps(
            test_run_id=uuid4(),
            journey_id=uuid4(),
            criterion=(
                "Heading is readable."
            ),
            execution_id=execution_id,
            agent_snapshot_id=uuid4(),
            step_ids=(7,),
            repository=cast(
                EvaluationRepository,
                repository,
            ),
            storage=cast(
                VisualArtifactStorage,
                storage,
            ),
        )
    )

    assert result.status == "unverified"

    assert result.evidence_step_id is None

    assert result.artifact_ids == ()

    assert storage.downloaded == []
