"""Save audit screenshots using the same authorized artifact path as other evidence."""

import logging
from contextlib import nullcontext
from pathlib import Path
from typing import AsyncContextManager
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.persistence.artifact_repository import ArtifactRepository
from markettwin_execution_orchestrator.persistence.artifact_storage import S3ArtifactStorage

logger = logging.getLogger(__name__)


async def retain_finding_evidence(states: list[dict], findings: list[dict], save) -> None:
    selected = {
        index for index, state in enumerate(states)
        if any(element.get("verdict") in {"slop_minor", "slop"} for element in state["elements"])
        or any(signal.get("severity") in {"minor", "severe"} for signal in state["page_signals"])
    }
    references = []
    for finding in findings:
        indexes = finding.pop("evidence_indexes", [])
        if finding.get("severity") == "review" or finding.get("rule_id") == "UI_VISUAL_REVIEW":
            valid = list(dict.fromkeys(
                index for index in indexes if type(index) is int and 0 <= index < len(states)
            ))[:2] if isinstance(indexes, list) else []
            if not valid and len(states) == 1:
                valid = [0]
            selected.update(valid)
            references.append((finding, valid))
    for index in sorted(selected):
        await save(states[index])
    for finding, indexes in references:
        finding["evidence_artifact_ids"] = [
            states[index]["screenshot_artifact_id"] for index in dict.fromkeys(indexes)
            if states[index].get("screenshot_artifact_id")
        ]


async def save_state_evidence(
    state: dict, *, session: AsyncSession, execution_id: UUID,
    write_lock: AsyncContextManager[None] | None = None,
) -> None:
    if state.get("screenshot_artifact_id"):
        return
    path = state.get("screenshot_path")
    try:
        if not path:
            raise FileNotFoundError("No screenshot captured")
        local_path = Path(path)
        content_type = (
            "image/jpeg" if local_path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        )
        stored = await S3ArtifactStorage.from_environment().upload(
            local_path=local_path,
            object_key=f"executions/{execution_id}/ui-audit/{uuid4()}{local_path.suffix}",
            content_type=content_type,
        )
    except Exception as error:
        logger.warning("UI screenshot storage unavailable (%s)", type(error).__name__)
        state["page_signals"].append({"rule_id": "UI_EVIDENCE_UNAVAILABLE", "severity": "info",
            "detail": "Saved screenshot unavailable. Recorded measurements remain available; "
                      "visual evidence cannot be opened."})
        return
    # Database failures must propagate; continuing would leave a failed transaction.
    async with write_lock if write_lock is not None else nullcontext():
        artifact_id = await ArtifactRepository(session).create(
            execution_id=execution_id, step_id=None, artifact_type="screenshot", stored=stored,
            metadata={"kind": "ui_audit", "url": state.get("url"), "viewport": state.get("viewport"),
                      "interaction_path": state.get("interaction_path")},
        )
    state["screenshot_artifact_id"] = str(artifact_id)
