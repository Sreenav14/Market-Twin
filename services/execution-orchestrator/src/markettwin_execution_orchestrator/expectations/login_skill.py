"""Login skill (doc 21 section 13).

Compiled from the knowledge graph after a successful human handoff --
never from a recording of the human -- and replayed at the login seam
before a handoff is requested. The skill stores key REFERENCES only
(``login_username`` / ``login_password``); credential values are
resolved per run through doc 17's approved-data channel and are never
written to the skill, the replay rows, or any event. This module
imports no model surface.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from markettwin_database.models.knowledge import (
    AppMap,
    MapElement,
    MapField,
    MapForm,
    MapPage,
    Skill,
    SkillReplay,
    SkillUsageEvent,
    SkillVersion,
)
from markettwin_shared.app_map_common import check_skill_transition
from markettwin_shared.feature_plan import SafeTestValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_execution_orchestrator.persistence.skill_creation import create_draft_version

LOGIN_USERNAME_KEY = "login_username"
LOGIN_PASSWORD_KEY = "login_password"
LOGIN_SKILL_NAME = "login"
# One heal cycle per failure is the harvest replay precedent; the seam's
# recovery is the human handoff itself, so the seam never heals inline.
LOGIN_SKILL_MAX_HEAL_PER_FAILURE = 1
LOGIN_SKILL_STALE_AFTER_FAILURES = 2
LOGIN_SKILL_VERIFIED_AFTER_REPLAYS = 2

_USERNAME_HINTS = ("email", "user", "login", "account")


def find_login_form(
    pages: list[MapPage],
    forms: list[MapForm],
    fields: list[MapField],
    elements: list[MapElement],
) -> tuple[MapPage, MapForm, MapField, MapField, MapElement | None] | None:
    """The graph's login form: the form holding a password field."""
    fields_by_form: dict[UUID, list[MapField]] = {}
    for field in fields:
        fields_by_form.setdefault(field.form_id, []).append(field)
    pages_by_id = {page.id: page for page in pages}
    elements_by_id = {element.id: element for element in elements}
    for form in forms:
        form_fields = fields_by_form.get(form.id, [])
        password = next(
            (f for f in form_fields if f.field_type == "password"), None
        )
        if password is None:
            continue
        others = [f for f in form_fields if f.id != password.id]
        username = next(
            (
                f
                for f in others
                if f.field_type in ("email", "text")
                and any(
                    hint in f"{f.label} {f.name_attr or ''}".lower()
                    for hint in _USERNAME_HINTS
                )
            ),
            None,
        ) or next((f for f in others if f.field_type in ("email", "text")), None)
        page = pages_by_id.get(form.map_page_id)
        if username is None or page is None:
            continue
        submit = (
            elements_by_id.get(form.submit_element_id)
            if form.submit_element_id
            else None
        )
        return page, form, username, password, submit
    return None


def build_login_definition(
    found: tuple[MapPage, MapForm, MapField, MapField, MapElement | None],
    *,
    landing_url: str,
    landing_signature: str,
) -> dict[str, object]:
    """The compiled skill definition: key references, never values."""
    page, _form, username, password, submit = found
    steps: list[dict[str, object]] = [
        {"action": "navigate", "url": page.canonical_url},
        {
            "action": "fill",
            "target": {"label": username.label},
            "test_value_key": LOGIN_USERNAME_KEY,
        },
        {
            "action": "fill",
            "target": {"label": password.label},
            "test_value_key": LOGIN_PASSWORD_KEY,
        },
    ]
    if submit is not None and submit.name:
        steps.append(
            {
                "action": "click",
                "target": {"role": submit.role, "name": submit.name},
            }
        )
    return {
        "name": "Sign in",
        "start_url": page.canonical_url,
        "steps": steps,
        "success_assertion": {"url": landing_url, "state_id": landing_signature},
        "locator_bindings": {
            "username_field_id": str(username.id),
            "password_field_id": str(password.id),
            "submit_element_id": str(submit.id) if submit is not None else None,
        },
        "provenance": "handoff-proven",
        "login_keys": [LOGIN_USERNAME_KEY, LOGIN_PASSWORD_KEY],
    }


async def compile_login_skill(
    session: AsyncSession,
    *,
    app_map: AppMap,
    landing_url: str,
    landing_signature: str,
) -> SkillVersion | None:
    """Compile (or recompile) the map's login skill from the graph."""
    pages = list(
        await session.scalars(
            select(MapPage).where(MapPage.app_map_id == app_map.id)
        )
    )
    forms = list(
        await session.scalars(
            select(MapForm).where(MapForm.app_map_id == app_map.id)
        )
    )
    fields = list(
        await session.scalars(
            select(MapField).where(MapField.app_map_id == app_map.id)
        )
    )
    elements = list(
        await session.scalars(
            select(MapElement).where(MapElement.app_map_id == app_map.id)
        )
    )
    found = find_login_form(pages, forms, fields, elements)
    if found is None:
        return None
    definition = build_login_definition(
        found, landing_url=landing_url, landing_signature=landing_signature
    )
    skill = await session.scalar(
        select(Skill).where(
            Skill.app_map_id == app_map.id, Skill.name == LOGIN_SKILL_NAME
        )
    )
    if skill is None:
        skill = Skill(
            workspace_id=app_map.workspace_id,
            name=LOGIN_SKILL_NAME,
            status="active",
            application_id=app_map.application_id,
            target_id=app_map.target_id,
            app_map_id=app_map.id,
            skill_kind="platform",
        )
        session.add(skill)
        await session.flush()
    latest = await session.scalar(
        select(SkillVersion.version_number)
        .where(SkillVersion.skill_id == skill.id)
        .order_by(SkillVersion.version_number.desc())
        .limit(1)
    )
    version = SkillVersion(
        workspace_id=app_map.workspace_id,
        skill_id=skill.id,
        version_number=(latest or 0) + 1,
        status="draft",
        lifecycle_status="draft",
        definition_json=definition,
        package={"kind": "login_skill"},
        verified_fingerprint=landing_signature,
        generation_metadata={"provenance": "handoff-proven"},
        app_map_id=app_map.id,
    )
    await create_draft_version(session, version, source="handoff-proven")
    return version


async def select_login_version(
    session: AsyncSession, *, app_map_id: UUID
) -> SkillVersion | None:
    """The login skill version the seam replays (Phase 3 serving
    rule, doc 22 sections 6.3, 11.1): platform skills only, and the
    preference is active > replay_verified > draft — an activated
    login is the served one; a draft is the pre-activation fallback
    the seam has always had. Suspect/quarantined/retired versions
    are never selected."""
    versions = list(
        await session.scalars(
            select(SkillVersion)
            .join(Skill, Skill.id == SkillVersion.skill_id)
            .where(
                Skill.app_map_id == app_map_id,
                Skill.name == LOGIN_SKILL_NAME,
                Skill.skill_kind == "platform",
                SkillVersion.lifecycle_status.in_(
                    ("active", "replay_verified", "draft")
                ),
            )
            .order_by(SkillVersion.version_number.desc())
        )
    )
    for preference in ("active", "replay_verified", "draft"):
        for version in versions:
            if version.lifecycle_status == preference:
                return version
    return None


def login_mode_allowed(
    *, run_mode: str, is_persona_run: bool, approved_keys: set[str]
) -> tuple[bool, str | None]:
    """Doc 17 section 8 mode filter + the F5(B) persona carve-out.

    Returns (allowed, refusal_key): a missing approved-data key refuses
    the skill with that key named; a read-only non-persona run simply
    does not select it.
    """
    for key in (LOGIN_USERNAME_KEY, LOGIN_PASSWORD_KEY):
        if key not in approved_keys:
            return False, key
    if run_mode == "standard" or is_persona_run:
        return True, None
    return False, None


async def _advance_login_lifecycle(
    session: AsyncSession,
    version: SkillVersion,
    *,
    to_status: str,
    kind: str,
    evidence: dict[str, object],
    result: str,
) -> None:
    """One lifecycle step for the login seam, through the shared
    authority (doc 22 section 5.1): the check runs at the write site
    and the usage event lands in the same transaction. A refused
    transition raises before mutation because it is a caller bug."""
    from_status = version.lifecycle_status
    if not check_skill_transition(from_status, to_status, evidence):
        raise ValueError(f"skill_transition_refused: {from_status} -> {to_status}")
    version.lifecycle_status = to_status
    session.add(
        SkillUsageEvent(
            workspace_id=version.workspace_id,
            skill_id=version.skill_id,
            skill_version_id=version.id,
            app_map_id=version.app_map_id,
            kind=kind,
            from_status=from_status,
            to_status=to_status,
            result=result,
            payload=dict(evidence),
        )
    )
    await session.flush()


async def record_login_replay(
    session: AsyncSession,
    *,
    version: SkillVersion,
    app_map_id: UUID,
    result: str,
    failure_step: int | None = None,
    failure_site: str | None = None,
) -> None:
    """Record one clean-context replay and advance the lifecycle
    (Phase 3 spellings, doc 22 section 4.4: 'verified' is now
    replay_verified, 'stale' is now suspect — the seam's rules are
    unchanged: two passed replays verify a draft; two consecutive
    failures suspect the version, from draft, replay_verified, or
    active alike)."""
    now = datetime.now(UTC)
    session.add(
        SkillReplay(
            skill_version_id=version.id,
            app_map_id=app_map_id,
            result=result,
            failure_step=failure_step,
            failure_site=failure_site,
            heal_cycle=0,
            context_kind="clean",
            model_calls=0,
            started_at=now,
            finished_at=now,
        )
    )
    version.last_replay_result = result
    version.last_replay_at = now
    version.replay_count = (version.replay_count or 0) + 1
    await session.flush()
    rows = list(
        await session.scalars(
            select(SkillReplay)
            .where(SkillReplay.skill_version_id == version.id)
            .order_by(SkillReplay.created_at.desc())
        )
    )
    results = [row.result for row in rows]
    passed_ids = [str(row.id) for row in rows if row.result == "passed"]
    if (
        version.lifecycle_status in ("draft", "suspect")
        and len(results) >= LOGIN_SKILL_VERIFIED_AFTER_REPLAYS
        and all(entry == "passed" for entry in results[:LOGIN_SKILL_VERIFIED_AFTER_REPLAYS])
    ):
        await _advance_login_lifecycle(
            session,
            version,
            to_status="replay_verified",
            kind="verification_replay",
            evidence={
                "two_clean_replays": passed_ids[
                    :LOGIN_SKILL_VERIFIED_AFTER_REPLAYS
                ]
            },
            result="passed",
        )
    recent = results[:LOGIN_SKILL_STALE_AFTER_FAILURES]
    if len(recent) == LOGIN_SKILL_STALE_AFTER_FAILURES and all(
        entry == "failed" for entry in recent
    ):
        failed_ids = [
            str(row.id)
            for row in rows[:LOGIN_SKILL_STALE_AFTER_FAILURES]
        ]
        if version.lifecycle_status == "active":
            await _advance_login_lifecycle(
                session,
                version,
                to_status="suspect",
                kind="demotion",
                evidence={
                    "demotion": {
                        "kind": "seam_failures",
                        "replay_ids": failed_ids,
                    }
                },
                result="failed",
            )
        elif version.lifecycle_status in ("draft", "replay_verified"):
            await _advance_login_lifecycle(
                session,
                version,
                to_status="suspect",
                kind="demotion",
                evidence={
                    "seam_failure": {
                        "consecutive_failures": LOGIN_SKILL_STALE_AFTER_FAILURES,
                        "replay_ids": failed_ids,
                    }
                },
                result="failed",
            )
    await session.flush()


async def replay_login_definition(
    controller: object,
    handle: object,
    *,
    definition: dict[str, object],
    values: dict[str, str],
    allowed_origins: tuple[str, ...],
    policy: object | None,
) -> tuple[bool, int | None, str | None]:
    """Replay the compiled steps on the working session, then verify.

    Returns (succeeded, failure_step, failure_site). Credential values
    travel only inside the action scope; nothing here persists them.
    """
    from markettwin_execution_orchestrator.agents.schemas.test_case import (
        CaseAction,
        FeatureScope,
        SemanticTarget,
    )
    from markettwin_execution_orchestrator.workflow.case_execution import (
        perform_case_action,
    )

    scope = FeatureScope(
        feature_key="login",
        goal="Sign in with the approved credentials.",
        starting_url=str(definition.get("start_url", "")),
        allowed_origins=allowed_origins,
        safe_test_data=tuple(
            SafeTestValue(key=key, value=values[key])
            for key in (LOGIN_USERNAME_KEY, LOGIN_PASSWORD_KEY)
        ),
    )
    steps = definition.get("steps")
    if not isinstance(steps, list) or not steps:
        return False, None, "empty_definition"
    for index, raw_step in enumerate(steps):
        step = raw_step if isinstance(raw_step, dict) else {}
        target = step.get("target")
        action = CaseAction(
            action=str(step.get("action", "")),
            target=SemanticTarget(**target) if isinstance(target, dict) else None,
            url=step.get("url") if isinstance(step.get("url"), str) else None,
            test_value_key=(
                step.get("test_value_key")
                if isinstance(step.get("test_value_key"), str)
                else None
            ),
        )
        try:
            await perform_case_action(controller, handle, action, scope)  # type: ignore[arg-type]
        except Exception as error:  # noqa: BLE001 - any failure falls back
            return False, index, type(error).__name__
    if policy is not None:
        principal = await controller.verify_authenticated_role(  # type: ignore[attr-defined]
            handle=handle, policy=policy
        )
        return principal is not None, None, None if principal else "unverified"
    result = await controller.get_page_index(  # type: ignore[attr-defined]
        session_id=handle.session_id,  # type: ignore[attr-defined]
        execution_id=handle.execution_id,  # type: ignore[attr-defined]
        journey_id=handle.journey_id,  # type: ignore[attr-defined]
        cursor=0,
    )
    success = definition.get("success_assertion")
    expected_url = success.get("url") if isinstance(success, dict) else None
    landed = result.observation.url == expected_url
    return landed, None, None if landed else "landing_mismatch"
