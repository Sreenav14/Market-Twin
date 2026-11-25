"""Test Run HTTP endpoints."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from ipaddress import ip_address
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid5

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Query,
    status,
)
from markettwin_database.repositories import (
    OutboxRepository,
)
from markettwin_database.models.knowledge import AppMap, MapPage, MapPageState
from markettwin_shared.action_approval import SensitiveActionRule
from markettwin_shared.auth_verification import AuthVerificationPolicy
from markettwin_shared.feature_plan import CaseAction, ExpectedAssertion, SemanticTarget, TestCaseSpec
from markettwin_shared.run_kind import UI_AUDIT_OBJECTIVE, resolve_run_kind
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.api.auth import (
    get_database_runtime,
)
from markettwin_control_api.api.dependencies import (
    get_authenticated_user_id,
)
from markettwin_control_api.api.permissions import (
    WORKSPACE_WRITE_ROLES,
)
from markettwin_control_api.config import get_settings
from markettwin_control_api.knowledge import map_repository
from markettwin_control_api.knowledge.files import (
    KnowledgeFileRepository,
    manifest_object_key,
)
from markettwin_control_api.knowledge.repository import IngestionRepository
from markettwin_control_api.persistence.repositories import (
    ApplicationRepository,
    TargetAuthorizationRepository,
    TargetRecord,
    TargetRepository,
    TestRunRecord,
    TestRunRepository,
    WorkspaceRepository,
)
from markettwin_control_api.services import (
    RunDispatchService,
    RunNotQueueableError,
)
from markettwin_control_api.services.run_readiness import (
    draft_map_readiness, require_run_ready, stalled_run_reason, stalled_run_reasons,
)

router = APIRouter(
    tags=["Test Runs"],
)


class ApprovedTestValue(BaseModel):
    """One owner-declared test-data entry (doc 17, section 5.2).

    A key names a value slot a form fill may use; the value is the
    literal text the owner approves for that slot. Only keys may ever
    appear in run evidence; values travel in the snapshot alone.
    """

    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$", max_length=32)
    value: str = Field(max_length=256)


class BrandTokens(BaseModel):
    palette_hexes: list[str] = Field(default_factory=list, max_length=16)
    font_families: list[str] = Field(default_factory=list, max_length=8)


class LearnTaskRequest(BaseModel):
    page_url: str = Field(min_length=1, max_length=2048)
    expected_text: str = Field(min_length=1, max_length=160, pattern=r"\S")


class KnowledgeFileAttachment(BaseModel):
    """One individually attached knowledge file (doc 33, section 3.6).

    The slug alphabet is the shared contract's: [a-z0-9-], at most 64
    characters. Validation against the approved file index happens at
    creation, on the mutation path."""

    entry_id: UUID
    slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")


class CreateTestRunRequest(BaseModel):
    """Request for creating a MarketTwin test run."""

    target_id: UUID
    creation_request_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=80)
    testing_depth: Literal["low", "medium", "high"] = "medium"
    execution_mode: Literal[
        "legacy_persona", "deep_feature_v1", "discovery_contract_v1", "harness_v1",
    ] = "discovery_contract_v1"
    # Unified run kind (U-P0-05): the only way to choose what a new
    # run does. The execution_mode field above survives only as a
    # rejection sentinel — sending it is a 422 (validator below, U-P8).
    run_kind: Literal["explore_test", "persona", "slop"] | None = None
    frozen_contract_source_run_id: UUID | None = None
    auth_verification: AuthVerificationPolicy | None = None
    auth_mode: Literal["required", "optional"] | None = None
    runtime_human_assistance: bool = True
    allow_offsite_navigation: bool = False
    synthetic_fixture_approval: bool = False
    human_action_approvals: bool = False
    sensitive_action_rules: list[SensitiveActionRule] = Field(
        default_factory=list[SensitiveActionRule], max_length=16,
    )
    harness_run_mode: Literal["read_only", "standard"] = "read_only"
    learn_task: LearnTaskRequest | None = None
    approved_test_data: list[ApprovedTestValue] = Field(
        default_factory=list[ApprovedTestValue], max_length=32,
    )
    brand_tokens: BrandTokens | None = None
    slop_classes_enabled: list[str] | None = Field(
        default=None, max_length=43,
    )
    # Doc 33 section 3.6: source-knowledge attachments. Individual
    # files load whole at plan time; a collection is selected from
    # its manifest. Both are validated and pinned by hash below.
    knowledge_files: list[KnowledgeFileAttachment] = Field(
        default_factory=list[KnowledgeFileAttachment], max_length=64,
    )
    knowledge_collections: list[UUID] = Field(
        default_factory=list[UUID], max_length=16,
    )

    @model_validator(mode="after")
    def retired_fields_are_rejected(self) -> "CreateTestRunRequest":
        # U-P8: the execution_mode alias and frozen-contract replay
        # were retired with the legacy engines. Sending either is a
        # 422 — new runs are created with run_kind only.
        if "execution_mode" in self.model_fields_set:
            raise ValueError(
                "execution_mode was retired; create runs with run_kind instead."
            )
        if self.frozen_contract_source_run_id is not None:
            raise ValueError(
                "Frozen contract replay was retired with the legacy engines."
            )
        return self

    @model_validator(mode="after")
    def authentication_mode_requires_policy(self) -> "CreateTestRunRequest":
        if self.auth_mode is not None and self.auth_verification is None:
            raise ValueError(
                "Authentication mode requires an approved identity verification policy."
            )
        return self

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Test name cannot be blank.")
        return value

    @field_validator("approved_test_data")
    @classmethod
    def unique_approved_test_data_keys(
        cls, value: list[ApprovedTestValue],
    ) -> list[ApprovedTestValue]:
        keys = [entry.key for entry in value]
        if len(set(keys)) != len(keys):
            raise ValueError("Approved test data keys must be unique.")
        return value

    study_brief: str = Field(
        default="",
        max_length=4000,
    )

    @field_validator("study_brief")
    @classmethod
    def clean_study_brief(
        cls,
        value: str,
    ) -> str:
        """Normalize the study brief."""

        return value.strip()

    @model_validator(mode="after")
    def require_goal_for_task_runs(self) -> "CreateTestRunRequest":
        if self.run_kind == "slop":
            self.study_brief = UI_AUDIT_OBJECTIVE
        elif len(self.study_brief) < 10:
            raise ValueError("Study brief must contain at least 10 characters.")
        return self

    @model_validator(mode="after")
    def run_mode_applies_to_explore_test(self) -> "CreateTestRunRequest":
        if self.harness_run_mode == "standard" and self.run_kind in {
            "persona", "slop",
        }:
            raise ValueError("harness_run_mode applies to explore_test runs.")
        if self.approved_test_data and self.harness_run_mode != "standard":
            raise ValueError(
                "Approved test data requires the standard run mode."
            )
        return self


class TestRunResponse(BaseModel):
    """Test run returned by the Control API."""

    id: UUID
    created_at: datetime
    test_number: int | None
    workspace_id: UUID
    application_id: UUID
    target_id: UUID
    created_by_user_id: UUID
    status: str
    target_snapshot: dict[str, object]
    configuration_snapshot: dict[str, object]
    synthetic_fixture_approval_enabled: bool = False
    human_action_approvals_enabled: bool = False
    status_reason: str | None = None
    # The run's unified kind, always resolved (column first, legacy
    # snapshot translation as fallback) so clients never guess.
    run_kind: str = "explore_test"
    # The run's creation-time safety mode (doc 17), read fail-closed
    # from the snapshot: legacy runs report read_only.
    harness_run_mode: Literal["read_only", "standard"] = "read_only"


def build_target_snapshot(
    target: TargetRecord,
) -> dict[str, object]:
    """Freeze the target configuration used by this run."""

    return {
        "target_id": str(target.target_id),
        "application_id": str(target.application_id),
        "name": target.name,
        "environment": target.environment,
        "base_url": target.base_url,
        "requires_auth": target.requires_auth,
        "allowed_origins": [
            {
                "scheme": origin.scheme,
                "hostname": origin.hostname,
                "port": origin.port,
                "include_subdomains": (
                    origin.include_subdomains
                ),
            }
            for origin in target.allowed_origins
        ],
    }


async def _source_knowledge_snapshot_block(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    files: list[KnowledgeFileAttachment],
    collections: list[UUID],
) -> dict[str, object]:
    """Validate and pin the run's source-knowledge attachments.

    Doc 33 section 3.6: every attachment is checked here, on the
    mutation path — the entry is approved, the file exists among the
    entry's approved files, and both live in the run's workspace
    (the A-36 rule). The pin is by hash, like the map block, so a
    later re-upload cannot change what a run used. A collection pins
    its manifest's versioned location (arbitration A-2)."""

    ingestion = IngestionRepository(session)
    file_repository = KnowledgeFileRepository(session)
    entry_ids = {attachment.entry_id for attachment in files} | set(collections)
    for entry_id in entry_ids:
        record = await ingestion.get(workspace_id, entry_id)
        if record is None or record.version.status != "approved":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Attached knowledge must be an approved source in this workspace.",
            )
    pinned_files: list[dict[str, object]] = []
    seen: set[tuple[UUID, str]] = set()
    for attachment in files:
        key = (attachment.entry_id, attachment.slug)
        if key in seen:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Knowledge file '{attachment.slug}' is attached more than once.",
            )
        seen.add(key)
        row = await file_repository.get_approved_file(
            workspace_id=workspace_id,
            entry_id=attachment.entry_id,
            slug=attachment.slug,
        )
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Knowledge file '{attachment.slug}' was not found "
                    "among the source's approved files."
                ),
            )
        pinned_files.append({
            "file_id": str(row.id),
            "entry_id": str(attachment.entry_id),
            "slug": row.slug,
            "title": row.title,
            "object_key": row.object_key,
            "sha256": row.sha256,
        })
    pinned_collections: list[dict[str, object]] = []
    for entry_id in collections:
        version = await file_repository.latest_approved_version(
            workspace_id=workspace_id, entry_id=entry_id,
        )
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="An attached knowledge collection has no approved files.",
            )
        pinned_collections.append({
            "entry_id": str(entry_id),
            "manifest_object_key": manifest_object_key(
                workspace_id, entry_id, version
            ),
            "version": version,
        })
    return {"files": pinned_files, "collections": pinned_collections}


async def _app_map_snapshot_block(
    session: AsyncSession, app_map: AppMap, *, freshness_context: dict | None = None,
) -> dict[str, object]:
    """Freeze the latest ready app map into the run snapshot (Phase 1a, section 9.3)."""

    count_rows = (await session.execute(
        select(MapPage.crawl_status, func.count())
        .where(MapPage.app_map_id == app_map.id)
        .group_by(MapPage.crawl_status)
    )).all()
    by_status = {crawl_status: count for crawl_status, count in count_rows}
    counts: dict[str, object] = {
        "expected": sum(by_status.values()),
        "reachable": by_status.get("fetch_ok", 0) + by_status.get("redirect", 0),
        "blocked_auth": by_status.get("blocked_auth", 0),
        "blocked_wall": by_status.get("blocked_wall", 0),
        "gone": by_status.get("gone", 0),
    }
    cap = map_repository.SNAPSHOT_MAP_PAGE_CAP
    reachable_pages = (await session.scalars(
        select(MapPage)
        .where(
            MapPage.app_map_id == app_map.id,
            MapPage.crawl_status.in_(("fetch_ok", "redirect")),
        )
        .order_by(MapPage.canonical_url)
        .limit(cap + 1)
    )).all()
    routes_truncated = len(reachable_pages) > cap
    reachable_pages = reachable_pages[:cap]
    states_by_page: dict[UUID, list[dict[str, object]]] = {}
    state_rows: list[MapPageState] = []
    if reachable_pages:
        state_rows = (await session.scalars(
            select(MapPageState)
            .where(MapPageState.map_page_id.in_([page.id for page in reachable_pages]))
            .order_by(MapPageState.state_key)
        )).all()
        for state in state_rows:
            states_by_page.setdefault(state.map_page_id, []).append(
                {
                    "state_key": state.state_key,
                    "state_id": state.state_id,
                    "element_signature": state.element_signature,
                    "form_signature": state.form_signature,
                }
            )
    pages: list[dict[str, object]] = []
    routes: list[str] = []
    for page in reachable_pages:
        effective_url = map_repository.page_effective_url(page)
        pages.append(
            {
                "url": page.canonical_url,
                "effective_url": effective_url,
                "pattern": page.route_pattern,
                "status": page.crawl_status,
                "requires_auth": page.requires_auth,
                "states": states_by_page.get(page.id, []),
            }
        )
        routes.append(effective_url)
    block: dict[str, object] = {
        "map_id": str(app_map.id),
        "version_number": app_map.version_number,
        "release_state": app_map.release_state,
        "release_scope": app_map.release_scope,
        "built_at": (app_map.completed_at or app_map.started_at).isoformat(),
        "base_url": app_map.base_url,
        "routes": sorted(set(routes)),
        "routes_truncated": routes_truncated,
        "pages": pages,
        "counts": counts,
    }
    if app_map.harvest_status not in (None, "not_started"):
        await _extend_snapshot_block_with_harvest(
            session, app_map, block, reachable_pages, state_rows
        )
    if app_map.grounding_status not in (None, "not_started"):
        await _extend_snapshot_block_with_expectations(
            session, app_map, block
        )
    # Phase 4 (doc 23 section 8.1): every snapshot block carries the
    # freshness block — the pinned map's own freshness summary plus
    # what creation did about it (the section 6.2 step's context for
    # verdict runs; the not-required default for the other kinds).
    context = freshness_context or {}
    block["freshness"] = map_repository.freshness_snapshot_block(
        app_map,
        preflight_status=context.get("preflight_status", "not_run"),
        pinned_via_preflight=bool(context.get("pinned_via_preflight")),
    )
    if counts["expected"] > cap:
        # The sweep covers the full version even when the snapshot's
        # page set is truncated (doc 23 section 6.1).
        block["freshness"]["sweep_scope"] = "full_map"
    if context.get("last_preflight_id"):
        block["freshness"]["last_preflight_id"] = context["last_preflight_id"]
        last_at = context.get("last_preflight_at")
        block["freshness"]["last_preflight_at"] = (
            last_at.isoformat() if last_at is not None else None
        )
    return block


async def _extend_snapshot_block_with_harvest(
    session: AsyncSession,
    app_map: AppMap,
    block: dict[str, object],
    reachable_pages: list[MapPage],
    state_rows: list[MapPageState],
) -> None:
    """Phase 1b extension (doc 16 section 11.1): harvested pages carry
    their elements, the block carries journeys and verified skills, and
    counts gain the harvest keys. Runs ONLY for maps whose harvest has
    started; an unharvested map's block stays byte-identical to Phase
    1a (test T-N8). Query order is pinned — harvest counts, expectation
    count, elements, journeys, skills, skill versions — and the
    snapshot tests program their fakes in exactly that order."""
    repository = map_repository.MapRepository(
        map_repository.session_factory_for(session)
    )
    harvest = await repository.harvest_counts(app_map.id)
    template_groups, enriched_groups = map_repository.harvest_metric_counts(
        app_map.harvest_metrics
    )
    counts = block["counts"]
    assert isinstance(counts, dict)
    counts.update(
        {
            "visited_harvest": harvest["visited"],
            "template_groups": template_groups,
            "enriched_groups": enriched_groups,
            "expectations": await repository.count_expectations(app_map.id),
        }
    )
    elements = await repository.snapshot_page_elements(
        [state.id for state in state_rows]
    )
    state_by_id = {state.id: state for state in state_rows}
    elements_by_page: dict[UUID, list[dict[str, object]]] = {}
    for element in elements:
        state = state_by_id.get(element.map_page_state_id)
        if state is None:
            continue
        elements_by_page.setdefault(state.map_page_id, []).append(
            {
                "state_key": state.state_key,
                "role": element.role,
                "name": element.name,
                "actionability": element.actionability,
                "safety_class": element.safety_class,
                "locators": list(element.locators or []),
                "navigates_to_url": element.navigates_to_url,
            }
        )
    pages_block = block["pages"]
    assert isinstance(pages_block, list)
    for page, page_block in zip(reachable_pages, pages_block, strict=True):
        page_block["harvest_status"] = page.harvest_status
        page_block["elements"] = elements_by_page.get(page.id, [])
    block["elements_truncated"] = False
    pages_by_id = {page.id: page for page in reachable_pages}
    journeys = await repository.snapshot_journeys(app_map.id)
    journey_blocks: list[dict[str, object]] = []
    for journey in journeys:
        terminal_url: str | None = None
        success_state = (
            state_by_id.get(journey.success_state_id)
            if journey.success_state_id is not None
            else None
        )
        if success_state is not None:
            terminal_page = pages_by_id.get(success_state.map_page_id)
            if terminal_page is not None:
                terminal_url = map_repository.page_effective_url(terminal_page)
        journey_blocks.append(
            {
                "name": journey.name,
                "skill_id": (
                    str(journey.skill_id) if journey.skill_id else None
                ),
                "intent": journey.intent,
                "selection": journey.selection,
                "terminal_url": terminal_url,
                "steps": list(journey.steps or []),
            }
        )
    block["journeys"] = journey_blocks
    served, withheld_count = await repository.latest_active_skills(
        workspace_id=app_map.workspace_id,
        application_id=app_map.application_id,
        target_id=app_map.target_id,
    )
    skill_blocks: list[dict[str, object]] = []
    for skill, version in served:
        package = version.package if isinstance(version.package, dict) else {}
        skill_blocks.append(
            {
                "name": skill.name,
                "skill_id": str(skill.id),
                "skill_version_id": str(version.id),
                "version_number": version.version_number,
                "skill_kind": skill.skill_kind,
                "lifecycle_status": "active",
                "catalogue": {
                    "name": package.get("name") or skill.name,
                    "description": package.get("description") or "",
                },
                "definition": version.definition_json,
                "package": version.package,
            }
        )
    block["skills"] = skill_blocks
    block["skills_withheld"] = withheld_count
    # Byte cap (section 11.1): drop elements in reverse reachability
    # order — fewest provenance kinds first, then canonical URL
    # descending — until the serialised block fits.
    if (
        len(json.dumps(block).encode("utf-8"))
        > map_repository.SNAPSHOT_MAP_MAX_BYTES
    ):
        drop_order = sorted(
            range(len(reachable_pages)),
            key=lambda index: reachable_pages[index].canonical_url,
            reverse=True,
        )
        drop_order.sort(
            key=lambda index: len(reachable_pages[index].source_kinds or [])
        )
        for index in drop_order:
            if (
                len(json.dumps(block).encode("utf-8"))
                <= map_repository.SNAPSHOT_MAP_MAX_BYTES
            ):
                break
            page_block = pages_block[index]
            if page_block.get("elements"):
                page_block["elements"] = []
                block["elements_truncated"] = True

async def _extend_snapshot_block_with_expectations(
    session: AsyncSession,
    app_map: AppMap,
    block: dict[str, object],
) -> None:
    """Phase 2 extension (doc 21 section 14.1): a grounded map's block
    carries its expectations (eligible first, then source grade, capped),
    the expectation coverage block, and its open conflicts. Runs ONLY
    for maps whose grounding has started; an ungrounded map's block
    stays byte-identical to the Phase 1b shape. The byte cap's drop
    order is pinned: pages/routes slimming, elements, non-eligible
    expectation entries, eligible entries, skills last -- a verdict's
    inputs are the last thing a snapshot ever loses.
    """
    from markettwin_shared.app_map_common import expectation_coverage

    repository = map_repository.MapRepository(
        map_repository.session_factory_for(session)
    )
    records = await repository.list_expectation_records(app_map.id)
    source_grade = {
        "documentation": 0,
        "owner-rule": 1,
        "observation": 2,
        "model-draft": 3,
    }
    ordered = sorted(
        records,
        key=lambda record: (
            0 if record["verdict_eligible"] else 1,
            source_grade.get(str(record["oracle_source"]), 4),
        ),
    )
    cap = map_repository.EXPECTATIONS_SNAPSHOT_CAP
    block["expectations_truncated"] = len(ordered) > cap
    entries: list[dict[str, object]] = []
    for record in ordered[:cap]:
        entry: dict[str, object] = {
            "id": record["id"],
            "subject_kind": record["subject_kind"],
            "subject_id": record["subject_id"],
            "page_url": record["page_url"],
            "statement": record["statement"],
            "oracle_source": record["oracle_source"],
            "source_ref": record["source_ref"],
            "status": record["status"],
            "verdict_eligible": record["verdict_eligible"],
            "conflicted": record["conflicted"],
            "has_open_conflict": record["has_open_conflict"],
        }
        if record["assertion"] is not None:
            entry["assertion"] = record["assertion"]
            entry["assertion_kind"] = record["assertion_kind"]
            entry["assertion_origin"] = record["assertion_origin"]
        entry["promoted"] = record["promoted_by"] is not None
        entries.append(entry)
    block["expectations"] = entries
    journey_rows = block.get("journeys")
    coverage_journeys: list[dict[str, object]] = []
    if isinstance(journey_rows, list):
        for journey in journey_rows:
            if not isinstance(journey, dict):
                continue
            step_subjects = [
                str(step["element_id"])
                for step in journey.get("steps") or []
                if isinstance(step, dict) and step.get("element_id")
            ]
            coverage_journeys.append(
                {
                    "id": str(journey.get("name")),
                    "intent": journey.get("intent"),
                    "subject_ids": step_subjects,
                }
            )
    block["coverage"] = expectation_coverage(records, coverage_journeys)
    open_conflicts = await repository.list_open_conflicts(app_map.id)
    block["open_conflicts"] = [
        {
            "id": str(conflict.id),
            "expectation_id": str(conflict.expectation_id),
            "conflict_kind": conflict.conflict_kind,
            "observed_behaviour": conflict.observed_behaviour,
        }
        for conflict in open_conflicts
    ]
    _enforce_snapshot_byte_cap(block)


def _enforce_snapshot_byte_cap(block: dict[str, object]) -> None:
    """The section 14.1 byte cap, applied after the expectations
    extension (the harvest extension enforces it for its own payload
    first). Drop order: pages/routes, elements, non-eligible
    expectation summaries, eligible entries, skills last."""

    def size() -> int:
        return len(json.dumps(block).encode("utf-8"))

    if size() <= map_repository.SNAPSHOT_MAP_MAX_BYTES:
        return
    pages_block = block.get("pages")
    if isinstance(pages_block, list):
        for page_block in pages_block:
            if isinstance(page_block, dict) and page_block.get("states"):
                page_block["states"] = []
                block["pages_states_truncated"] = True
    if size() <= map_repository.SNAPSHOT_MAP_MAX_BYTES:
        return
    if isinstance(pages_block, list) and pages_block:
        block["pages"] = []
        block["routes"] = []
        block["pages_truncated"] = True
    if size() <= map_repository.SNAPSHOT_MAP_MAX_BYTES:
        return
    expectations = block.get("expectations")
    if size() > map_repository.SNAPSHOT_MAP_MAX_BYTES and isinstance(
        expectations, list
    ):
        kept = [
            entry
            for entry in expectations
            if isinstance(entry, dict) and entry.get("verdict_eligible")
        ]
        if len(kept) != len(expectations):
            block["expectations"] = kept
            block["expectations_truncated"] = True
            expectations = kept
    if size() > map_repository.SNAPSHOT_MAP_MAX_BYTES and isinstance(
        expectations, list
    ):
        while expectations and size() > map_repository.SNAPSHOT_MAP_MAX_BYTES:
            expectations.pop()
            block["expectations_truncated"] = True
    if size() > map_repository.SNAPSHOT_MAP_MAX_BYTES:
        skills = block.get("skills")
        if isinstance(skills, list) and skills:
            # Phase 3 (doc 22 section 7.2): strip the level-2/3
            # package payloads before dropping any entry.
            for skill in skills:
                if isinstance(skill, dict):
                    skill.pop("package", None)
            block["skills_truncated"] = True
    if size() > map_repository.SNAPSHOT_MAP_MAX_BYTES:
        skills = block.get("skills")
        if isinstance(skills, list) and skills:
            withheld = block.get("skills_withheld")
            block["skills_withheld"] = (
                withheld if isinstance(withheld, int) else 0
            ) + len(skills)
            block["skills"] = []
            block["skills_truncated"] = True


def test_run_response(
    test_run: TestRunRecord,
    status_reason: str | None = None,
) -> TestRunResponse:
    """Convert repository data into an HTTP response."""

    return TestRunResponse(
        id=test_run.test_run_id,
        created_at=test_run.created_at,
        test_number=test_run.test_number,
        workspace_id=test_run.workspace_id,
        application_id=test_run.application_id,
        target_id=test_run.target_id,
        created_by_user_id=test_run.created_by_user_id,
        status=test_run.status,
        status_reason=status_reason,
        target_snapshot=test_run.target_snapshot,
        configuration_snapshot=(
            test_run.configuration_snapshot
        ),
        synthetic_fixture_approval_enabled=test_run.synthetic_fixture_approval_enabled,
        human_action_approvals_enabled=test_run.human_action_approvals_enabled,
        run_kind=resolve_run_kind(
            run_kind_column=test_run.run_kind,
            configuration_snapshot=test_run.configuration_snapshot,
        ),
        harness_run_mode=(
            "standard"
            if (test_run.configuration_snapshot or {}).get(
                "harness_run_mode"
            ) == "standard"
            else "read_only"
        ),
    )


async def _preflight_creation_step(
    *, database, app_map: AppMap, settings
) -> tuple[UUID, dict[str, object]]:
    """Reuse a recent receipt or enqueue one durable freshness check for the draft."""

    now = datetime.now(UTC)
    session_factory = database.session_factory
    metrics = app_map.freshness_metrics or {}
    recorded_id = metrics.get("preflight_id")
    if (
        app_map.last_preflight_at is not None
        and isinstance(recorded_id, str)
        and now - app_map.last_preflight_at
        <= timedelta(hours=settings.preflight_reuse_hours)
    ):
        try:
            recorded_preflight_id = UUID(recorded_id)
        except ValueError:
            recorded_preflight_id = None
        if recorded_preflight_id is not None:
            async with session_factory() as session:
                receipt = await map_repository.get_preflight(session, recorded_preflight_id)
            if (
                receipt is not None
                and receipt.status in ("ready", "partial")
                and app_map.id in (receipt.app_map_id, receipt.resulting_map_id)
            ):
                return app_map.id, {
                    "preflight_status": "reused",
                    "pinned_via_preflight": False,
                    "last_preflight_id": recorded_id,
                    "last_preflight_at": app_map.last_preflight_at,
                }

    try:
        async with session_factory() as session:
            async with session.begin():
                preflight = await map_repository.create_preflight(
                    session, app_map=app_map, trigger="run_creation"
                )
                preflight_id = preflight.id
    except IntegrityError:
        # The single-flight index fired: join the in-flight row.
        async with session_factory() as session:
            in_flight = await map_repository.latest_preflight_for_map(
                session, app_map.id
            )
        if in_flight is None:
            raise
        preflight_id = in_flight.id

    async with session_factory() as session:
        row = await map_repository.get_preflight(session, preflight_id)
    if row is None:
        raise RuntimeError("Preflight row missing during draft creation.")
    return _preflight_result(app_map.id, row)


def _preflight_result(original_id, row):
    completed = row.status in ("ready", "partial")
    status = "completed" if completed else "failed" if row.status == "failed" else "preparing"
    return (row.resulting_map_id or original_id) if completed else original_id, {
        "preflight_status": status,
        "pinned_via_preflight": completed,
        "last_preflight_id": str(row.id),
        "last_preflight_at": row.completed_at,
    }


async def _finish_draft_preflight(session, run, repository):
    row, check = await draft_map_readiness(session, run, get_settings())
    if check is None:
        return
    if not check.ready or row is None:
        raise HTTPException(status_code=409, detail=check.reason)
    block = run.configuration_snapshot["app_map"]
    freshness = block["freshness"]
    map_id, context = _preflight_result(row.app_map_id, row)
    if context["preflight_status"] == "preparing":
        context["preflight_status"] = "timed_out"
    candidate = await session.get(AppMap, map_id)
    if (candidate is not None and candidate.application_id == run.application_id
        and candidate.target_id == run.target_id and candidate.status == "ready"
        and candidate.release_state in ("partial", "trusted") and context["pinned_via_preflight"]):
        block = await _app_map_snapshot_block(session, candidate, freshness_context=context)
    else:
        if context["pinned_via_preflight"]:
            context.update(preflight_status="failed", pinned_via_preflight=False)
        completed_at = context["last_preflight_at"]
        block = {**block, "freshness": {**freshness, **context,
                 "last_preflight_at": completed_at.isoformat() if completed_at else None}}
    await repository.update_configuration_snapshot(
        test_run_id=run.test_run_id, configuration_snapshot={**run.configuration_snapshot, "app_map": block}
    )


@router.post(
    "/api/v1/applications/{application_id}/test-runs",
    response_model=TestRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_test_run(
    application_id: UUID,
    payload: CreateTestRunRequest,
    request: Request,
) -> TestRunResponse:
    """Create a draft run against an authorized target."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            application_repository = ApplicationRepository(
                database_session
            )

            application = await application_repository.get_for_user(
                application_id=application_id,
                user_id=user_id,
            )

            if application is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Application not found.",
                )

            workspace_repository = WorkspaceRepository(
                database_session
            )

            workspace = await workspace_repository.get_for_user(
                workspace_id=application.workspace_id,
                user_id=user_id,
            )

            if workspace is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Application not found.",
                )

            if workspace.role not in WORKSPACE_WRITE_ROLES:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Your workspace role cannot "
                        "create test runs."
                    ),
                )

            repository = TestRunRepository(database_session)
            draft_id = None
            if payload.creation_request_id is not None:
                # Scope retries to the same user, application and normalized form values.
                body = json.dumps(payload.model_dump(mode="json"), sort_keys=True)
                draft_id = uuid5(application_id, f"{user_id}:{body}")
                previous = await repository.lock_creation_request(draft_id, user_id)
                if previous is not None:
                    return test_run_response(previous)

            target_repository = TargetRepository(
                database_session
            )

            target = await target_repository.get_for_user(
                target_id=payload.target_id,
                user_id=user_id,
            )

            if (
                target is None
                or target.application_id != application_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Target not found for application.",
                )

            authorization_repository = (
                TargetAuthorizationRepository(
                    database_session
                )
            )

            authorization = (
                await authorization_repository.get_active(
                    target_id=target.target_id
                )
            )

            if authorization is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Target is not currently authorized "
                        "for testing."
                    ),
                )

            target_snapshot = build_target_snapshot(
                target
            )

            if (
                target.requires_auth and payload.auth_verification is None
                and not payload.runtime_human_assistance
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Authenticated targets require an approved identity verification policy."
                    ),
                )

            if payload.auth_verification is not None:
                if target.requires_auth and payload.auth_mode == "optional":
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Protected targets require authentication before execution.",
                    )
                if not all(_auth_origin_is_allowed(origin, target) for origin in (
                    payload.auth_verification.origin, *payload.auth_verification.auth_only_origins,
                )):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=(
                            "Authentication and SSO origins must be authorized "
                            "for this target."
                        ),
                    )

            # The unified kind for this run (U-P8: run_kind only; the
            # legacy alias is rejected at validation above).
            effective_run_kind = payload.run_kind or "explore_test"

            if payload.synthetic_fixture_approval:
                loopback_origins = _all_origins_loopback(target)
                if (
                    effective_run_kind != "explore_test"
                    or target.environment not in {"local", "test"}
                    or not loopback_origins
                ):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=(
                            "Synthetic fixture approval requires a deep run on an all-loopback "
                            "local/test target."
                        ),
                    )

            if payload.human_action_approvals and (
                effective_run_kind not in {"explore_test", "persona"}
                or target.environment not in {"local", "development", "test", "staging"}
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        "Sensitive action approvals require an authorized local, test, "
                        "development, or staging target and deep feature execution."
                    ),
                )

            configuration_snapshot: dict[str, object] = {
                "runtime_human_assistance": payload.runtime_human_assistance,
                "allow_offsite_navigation": payload.allow_offsite_navigation,
                "study_brief": payload.study_brief,
                "testing_depth": payload.testing_depth,
                "harness_run_mode": payload.harness_run_mode,
                "authorization_id_at_creation": str(
                    authorization.authorization_id
                ),
            }
            if payload.name is not None:
                configuration_snapshot["test_name"] = payload.name
            if payload.auth_verification is not None:
                configuration_snapshot["auth_mode"] = payload.auth_mode or "required"
                configuration_snapshot["auth_verification"] = payload.auth_verification.model_dump(
                    mode="json"
                )
            if payload.sensitive_action_rules:
                configuration_snapshot["sensitive_action_rules"] = [
                    rule.model_dump(mode="json") for rule in payload.sensitive_action_rules
                ]
            if payload.approved_test_data:
                configuration_snapshot["approved_test_data"] = [
                    entry.model_dump(mode="json") for entry in payload.approved_test_data
                ]
            if payload.brand_tokens is not None:
                configuration_snapshot["brand_tokens"] = (
                    payload.brand_tokens.model_dump(mode="json")
                )
            if payload.slop_classes_enabled is not None:
                configuration_snapshot["slop_classes_enabled"] = list(
                    payload.slop_classes_enabled
                )
            app_map = await map_repository.latest_ready_map(
                database_session, application_id, target.target_id
            )
            if payload.learn_task is not None:
                if (
                    effective_run_kind != "explore_test" or payload.harness_run_mode != "read_only"
                    or payload.allow_offsite_navigation or app_map is None
                ):
                    raise HTTPException(
                        status_code=422,
                        detail="Learning a task requires a ready app map and a read-only test on its target.",
                    )
                learning = payload.learn_task
                page_url = learning.page_url.strip()
                page = None
                try:
                    page = urlsplit(page_url)
                    base = urlsplit(target.base_url)
                    same_origin = (
                        page.scheme == base.scheme and page.hostname == base.hostname
                        and (page.port or (443 if page.scheme == "https" else 80))
                        == (base.port or (443 if base.scheme == "https" else 80))
                    )
                except ValueError:
                    same_origin = False
                if not same_origin or page is None or page.username is not None or page.password is not None:
                    raise HTTPException(status_code=422, detail="Enter a page on the selected target.")
                expected_text = learning.expected_text.strip()
                task_key = sha256(json.dumps([page_url, expected_text]).encode()).hexdigest()[:32]
                case = TestCaseSpec(
                    case_id=f"learn_{task_key}", feature_key=f"learn_{task_key}",
                    title=payload.name or "Learn task", kind="happy_path",
                    steps=(CaseAction(action="navigate", url=page_url),),
                    expected=(ExpectedAssertion(
                        assertion_id="task_outcome", oracle="visible_text",
                        target=SemanticTarget(text=expected_text), expected_value=expected_text,
                        origin="user_approved",
                    ),),
                )
                configuration_snapshot["learn_task"] = True
                configuration_snapshot["harness_work_list"] = [{
                    "case": case.model_dump(mode="json"),
                    "role_name": ["page", case.title, 0],
                }]
            freshness_context = None
            if app_map is not None and effective_run_kind != "explore_test":
                # Decision 5: the other kinds never preflight; their
                # block records TTL trust instead (section 8.1).
                freshness_context = {
                    "preflight_status": "not_required",
                    "pinned_via_preflight": False,
                }
            if app_map is not None and effective_run_kind == "explore_test":
                # Record the durable receipt so Start can resolve a pending sweep.
                pinned_map_id, freshness_context = (
                    await _preflight_creation_step(
                        database=database,
                        app_map=app_map,
                        settings=get_settings(),
                    )
                )
                pinned_map = await database_session.get(AppMap, pinned_map_id)
                if pinned_map is not None:
                    # The worker's writes are committed outside this
                    # transaction; refresh so the snapshot freezes the
                    # map as the preflight left it.
                    await database_session.refresh(pinned_map)
                if (
                    pinned_map is not None
                    and pinned_map.application_id == app_map.application_id
                    and pinned_map.target_id == app_map.target_id
                    and pinned_map.status == "ready"
                    and pinned_map.release_state in ("partial", "trusted")
                ):
                    app_map = pinned_map
                elif pinned_map_id != app_map.id:
                    freshness_context.update(
                        preflight_status="failed", pinned_via_preflight=False,
                    )
            if app_map is not None:
                configuration_snapshot["app_map"] = await _app_map_snapshot_block(
                    database_session, app_map,
                    freshness_context=freshness_context,
                )

            if payload.knowledge_files or payload.knowledge_collections:
                configuration_snapshot["source_knowledge"] = (
                    await _source_knowledge_snapshot_block(
                        database_session,
                        workspace_id=application.workspace_id,
                        files=payload.knowledge_files,
                        collections=payload.knowledge_collections,
                    )
                )

            test_run = await repository.create(
                **({"draft_id": draft_id} if draft_id is not None else {}),
                workspace_id=application.workspace_id,
                application_id=application_id,
                target_id=target.target_id,
                created_by_user_id=user_id,
                target_snapshot=target_snapshot,
                configuration_snapshot=(
                    configuration_snapshot
                ),
                synthetic_fixture_approval_enabled=payload.synthetic_fixture_approval,
                human_action_approvals_enabled=(
                    payload.human_action_approvals or payload.synthetic_fixture_approval
                ),
                run_kind=effective_run_kind,
            )
    return test_run_response(test_run)


def _auth_origin_is_allowed(origin: str, target: TargetRecord) -> bool:
    """Require exact origin membership, honoring only explicit subdomain grants."""
    from urllib.parse import urlsplit

    parsed = urlsplit(origin)
    try:
        port = parsed.port
    except ValueError:
        return False
    for allowed in target.allowed_origins:
        if parsed.scheme != allowed.scheme or port != allowed.port:
            continue
        if parsed.hostname == allowed.hostname:
            return True
        if (
            allowed.include_subdomains
            and parsed.hostname is not None
            and parsed.hostname.endswith("." + allowed.hostname)
        ):
            return True
    return False


def _all_origins_loopback(target: TargetRecord) -> bool:
    if not target.allowed_origins:
        return False
    try:
        base_host = urlsplit(target.base_url).hostname
        if base_host != "localhost" and not ip_address(base_host or "").is_loopback:
            return False
    except ValueError:
        return False
    for origin in target.allowed_origins:
        if origin.scheme != "http" or origin.include_subdomains:
            return False
        if origin.hostname == "localhost":
            continue
        try:
            if ip_address(origin.hostname).is_loopback:
                continue
        except ValueError:
            pass
        return False
    return True


@router.get(
    "/api/v1/applications/{application_id}/test-runs",
    response_model=list[TestRunResponse],
)
async def list_test_runs(
    application_id: UUID,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TestRunResponse]:
    """List runs belonging to an accessible application."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            application_repository = ApplicationRepository(
                database_session
            )

            application = await application_repository.get_for_user(
                application_id=application_id,
                user_id=user_id,
            )

            if application is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Application not found.",
                )

            repository = TestRunRepository(
                database_session
            )

            test_runs = await repository.list_for_application(
                application_id=application_id, limit=limit, offset=offset,
            )
            reasons = await stalled_run_reasons(database_session, test_runs)
            responses = [test_run_response(run, reasons[run.test_run_id]) for run in test_runs]

    return responses


@router.get(
    "/api/v1/test-runs/{test_run_id}",
    response_model=TestRunResponse,
)
async def get_test_run(
    test_run_id: UUID,
    request: Request,
) -> TestRunResponse:
    """Return a test run available to the current user."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            repository = TestRunRepository(
                database_session
            )

            test_run = await repository.get_for_user(
                test_run_id=test_run_id,
                user_id=user_id,
            )
            reason = await stalled_run_reason(
                database_session, run_id=test_run.test_run_id, status=test_run.status,
                created_at=test_run.created_at,
            ) if test_run is not None else None

    if test_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found.",
        )

    return test_run_response(test_run, reason)


class BoardItemResponse(BaseModel):
    """One item on a run's Board (U-P1-07)."""

    item_id: str
    state_id: str
    case_id: str
    role: str
    name: str
    status: str
    blocker: str | None = None
    attempts: int = 0
    page_url: str = ""


class BoardResponse(BaseModel):
    """A run's Board: counts plus every item, in Board order."""

    run_id: UUID
    run_status: str
    run_kind: str
    total: int
    counts: dict[str, int]
    items: list[BoardItemResponse]


def _board_response(test_run: TestRunRecord) -> BoardResponse:
    board = test_run.configuration_snapshot.get("harness_state")
    if not isinstance(board, dict):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This run has no board.",
        )
    states = board.get("states")
    state_urls: dict[str, str] = {}
    if isinstance(states, dict):
        for state_id, state_doc in states.items():
            if isinstance(state_doc, dict):
                state_urls[str(state_id)] = str(state_doc.get("url", ""))
    raw_items = board.get("items")
    item_docs: list[dict[str, object]] = []
    if isinstance(raw_items, dict):
        item_docs = [v for v in raw_items.values() if isinstance(v, dict)]
    elif isinstance(raw_items, list):
        item_docs = [v for v in raw_items if isinstance(v, dict)]
    counts: dict[str, int] = {}
    items: list[BoardItemResponse] = []
    for doc in item_docs:
        item_status = str(doc.get("status", "pending"))
        counts[item_status] = counts.get(item_status, 0) + 1
        items.append(BoardItemResponse(
            item_id=str(doc.get("item_id", "")),
            state_id=str(doc.get("state_id", "")),
            case_id=str(doc.get("case_id", "")),
            role=str(doc.get("role", "")),
            name=str(doc.get("name", "")),
            status=item_status,
            blocker=(str(doc["blocker"]) if doc.get("blocker") else None),
            attempts=int(doc.get("attempts", 0) or 0),
            page_url=state_urls.get(str(doc.get("state_id", "")), ""),
        ))
    return BoardResponse(
        run_id=test_run.test_run_id,
        run_status=test_run.status,
        run_kind=resolve_run_kind(
            run_kind_column=test_run.run_kind,
            configuration_snapshot=test_run.configuration_snapshot,
        ),
        total=len(items),
        counts=counts,
        items=items,
    )


async def _get_run_for_board(test_run_id: UUID, request: Request) -> TestRunRecord:
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as database_session:
        async with database_session.begin():
            repository = TestRunRepository(database_session)
            test_run = await repository.get_for_user(
                test_run_id=test_run_id, user_id=user_id,
            )
    if test_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test run not found.",
        )
    return test_run


@router.get(
    "/api/v1/test-runs/{test_run_id}/board",
    response_model=BoardResponse,
)
async def get_test_run_board(
    test_run_id: UUID,
    request: Request,
) -> BoardResponse:
    """Return the run's Board (the live work list of the unified engine)."""

    test_run = await _get_run_for_board(test_run_id, request)
    return _board_response(test_run)


@router.post(
    "/api/v1/test-runs/{test_run_id}/board/items/{item_id}/disable",
    response_model=BoardResponse,
)
async def disable_board_item(
    test_run_id: UUID,
    item_id: str,
    request: Request,
) -> BoardResponse:
    """Turn off one pending Board item (owner_disabled).

    Only while the run is not testing: the engine owns Board writes
    during a run, and a mid-run edit here would be overwritten by the
    engine's next Board persist.
    """

    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as database_session:
        async with database_session.begin():
            repository = TestRunRepository(database_session)
            test_run = await repository.get_for_user(
                test_run_id=test_run_id, user_id=user_id,
            )
            if test_run is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Test run not found.",
                )
            if test_run.status in {"planning", "running", "awaiting_human"}:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Items can be turned off only while the run "
                        "is not testing."
                    ),
                )
            snapshot = test_run.configuration_snapshot
            board = snapshot.get("harness_state")
            if not isinstance(board, dict):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="This run has no board.",
                )
            # The GET path serves both stored shapes (dict keyed by
            # item id, or a plain list); disabling must accept the
            # same shapes and write back in the shape it found.
            raw_items = board.get("items")
            list_shaped = isinstance(raw_items, list)
            if isinstance(raw_items, dict):
                items = dict(raw_items)
            elif list_shaped:
                items = {
                    str(doc.get("item_id", "")): doc
                    for doc in raw_items
                    if isinstance(doc, dict)
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="This run has no board.",
                )
            item_doc = items.get(item_id)
            if not isinstance(item_doc, dict):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Board item not found.",
                )
            if item_doc.get("status") != "pending":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Only a pending item can be turned off.",
                )
            updated_item = {**item_doc, "status": "owner_disabled"}
            if list_shaped:
                new_items: object = [
                    updated_item
                    if isinstance(doc, dict)
                    and str(doc.get("item_id", "")) == item_id
                    else doc
                    for doc in raw_items
                ]
            else:
                items[item_id] = updated_item
                new_items = items
            updated_snapshot = {
                **snapshot, "harness_state": {**board, "items": new_items},
            }
            await repository.update_configuration_snapshot(
                test_run_id=test_run_id,
                configuration_snapshot=updated_snapshot,
            )
            test_run = replace(
                test_run, configuration_snapshot=updated_snapshot,
            )
    return _board_response(test_run)


class ParkResponse(BaseModel):
    """A parked run's live-park window (U-P4)."""

    parked_at: str
    deadline_at: str


@router.post(
    "/api/v1/test-runs/{test_run_id}/park/extend",
    response_model=ParkResponse,
)
async def extend_park(
    test_run_id: UUID,
    request: Request,
) -> ParkResponse:
    """Extend a parked run's deadline, up to 30 minutes from the park.

    The window is owner time, not agent time: extending never resumes
    the run and never changes any item — it only moves the deadline
    the countdown shows.
    """

    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as database_session:
        async with database_session.begin():
            repository = TestRunRepository(database_session)
            test_run = await repository.get_for_user(
                test_run_id=test_run_id, user_id=user_id,
            )
            if test_run is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Test run not found.",
                )
            park = test_run.configuration_snapshot.get("harness_park")
            if test_run.status != "awaiting_human" or not isinstance(park, dict):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This run is not parked.",
                )
            try:
                parked_at = datetime.fromisoformat(str(park["parked_at"]))
            except (KeyError, ValueError):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This run is not parked.",
                ) from None
            cap = parked_at + timedelta(minutes=30)
            now = datetime.now(UTC)
            if now >= cap:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The park window is exhausted; resume or end the run.",
                )
            new_deadline = min(now + timedelta(minutes=15), cap)
            updated_park = {**park, "deadline_at": new_deadline.isoformat()}
            updated_snapshot = {
                **test_run.configuration_snapshot, "harness_park": updated_park,
            }
            await repository.update_configuration_snapshot(
                test_run_id=test_run_id,
                configuration_snapshot=updated_snapshot,
            )
    return ParkResponse(
        parked_at=str(park["parked_at"]), deadline_at=new_deadline.isoformat(),
    )


class StopRunResponse(BaseModel):
    """An owner stop request recorded on a run (the Stop run button)."""

    test_run_id: UUID
    run_status: str
    stop_requested_at: str


@router.post(
    "/api/v1/test-runs/{test_run_id}/stop",
    response_model=StopRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def stop_test_run(
    test_run_id: UUID,
    request: Request,
) -> StopRunResponse:
    """Record the owner's stop request on a live run.

    The request is durable — an ``owner_stop`` flag in the run's
    configuration snapshot — and the execution engine honours it at
    the next item boundary: the current check finishes, the
    remaining Board items close as not checked ("stopped by
    owner"), partial results publish, and the run closes
    cancelled. Recording is idempotent; a run that already reached
    a terminal state refuses with 409.
    """

    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as database_session:
        async with database_session.begin():
            repository = TestRunRepository(database_session)
            test_run = await repository.get_for_user(
                test_run_id=test_run_id, user_id=user_id,
            )
            if test_run is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Test run not found.",
                )
            if test_run.status in {"completed", "failed", "cancelled"}:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This run has already finished.",
                )
            existing = test_run.configuration_snapshot.get("owner_stop")
            if isinstance(existing, dict):
                requested_at = str(existing.get("requested_at", ""))
            else:
                requested_at = datetime.now(UTC).isoformat()
                updated_snapshot = {
                    **test_run.configuration_snapshot,
                    "owner_stop": {
                        "requested_at": requested_at,
                        "requested_by": str(user_id),
                    },
                }
                await repository.update_configuration_snapshot(
                    test_run_id=test_run_id,
                    configuration_snapshot=updated_snapshot,
                )
    return StopRunResponse(
        test_run_id=test_run_id,
        run_status=test_run.status,
        stop_requested_at=requested_at,
    )


@router.post(
    "/api/v1/test-runs/{test_run_id}/start",
    response_model=TestRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_test_run(
      test_run_id: UUID,
    request: Request,
) -> TestRunResponse:
    """Queue one authorized draft TestRun for execution."""

    user_id = await get_authenticated_user_id(
        request=request
    )

    database = get_database_runtime(request)

    async with database.session_factory() as database_session:
        async with database_session.begin():
            test_run_repository = TestRunRepository(
                database_session
            )

            test_run = await test_run_repository.get_for_user(
                test_run_id=test_run_id,
                user_id=user_id,
            )

            if test_run is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Test run not found.",
                )

            if test_run.status != "draft":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Test run has already been started.",
                )

            if test_run.configuration_snapshot.get("frozen_contract_source_run_id"):
                # The contract start endpoint this check once pointed
                # to was retired with the legacy engines (U-P8); the
                # honest answer now is that such a run can never be
                # started, not a direction to a missing endpoint.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "This run was created by the retired contract "
                        "replay flow and can no longer be started. "
                        "Create a new run instead."
                    ),
                )

            workspace_repository = WorkspaceRepository(
                database_session
            )

            workspace = await workspace_repository.get_for_user(
                workspace_id=test_run.workspace_id,
                user_id=user_id,
            )

            if workspace is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Test run not found.",
                )

            if workspace.role not in WORKSPACE_WRITE_ROLES:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "Your workspace role cannot "
                        "start test runs."
                    ),
                )

            target_repository = TargetRepository(
                database_session
            )

            target = await target_repository.get_for_user(
                target_id=test_run.target_id,
                user_id=user_id,
            )

            if target is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Target is not currently "
                        "available for testing."
                    ),
                )

            authorization_repository = (
                TargetAuthorizationRepository(
                    database_session
                )
            )

            authorization = (
                await authorization_repository.get_active(
                    target_id=target.target_id
                )
            )

            if authorization is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Target is not currently authorized "
                        "for testing."
                    ),
                )

            await require_run_ready(database_session, get_settings())
            await _finish_draft_preflight(database_session, test_run, test_run_repository)
            dispatch_service = RunDispatchService(
                test_run_repository=test_run_repository,
                outbox_repository=OutboxRepository(
                    database_session
                ),
            )

            try:
                queued_run = await dispatch_service.queue(
                    test_run_id=test_run_id
                )
            except RunNotQueueableError as error:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Test run has already been started."
                    ),
                ) from error

    return test_run_response(queued_run)
