"""Checked draft creation in the caller's transaction."""

from markettwin_database.models.knowledge import SkillUsageEvent, SkillVersion
from markettwin_shared.app_map_common import check_skill_transition
from sqlalchemy.ext.asyncio import AsyncSession


async def create_draft_version(
    session: AsyncSession, version: SkillVersion, *, source: str,
) -> None:
    evidence = {"creation_record": {"source": source}}
    if version.lifecycle_status != "draft" or not check_skill_transition(None, "draft", evidence):
        raise ValueError("skill_transition_refused: creation -> draft")
    session.add(version)
    await session.flush()
    session.add(SkillUsageEvent(
        workspace_id=version.workspace_id, skill_id=version.skill_id,
        skill_version_id=version.id, app_map_id=version.app_map_id,
        kind="compile", from_status=None, to_status="draft", result="applied",
        payload=evidence,
    ))
    await session.flush()
