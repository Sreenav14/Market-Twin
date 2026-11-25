"""Graph-backed application map reads and build triggers (Phase 1a).

This router serves the observed app graph and its owner-supplied expectations
(doc 14, section 9). No model calls are made anywhere in this module.
"""

import logging
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Body, HTTPException, Query, Request, Response
from markettwin_database.models.testing import Application, ApplicationTarget
from markettwin_shared.app_map_common import canonical_url
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_control_api.api.auth import get_database_runtime
from markettwin_control_api.api.dependencies import get_authenticated_user_id
from markettwin_control_api.api.permissions import WORKSPACE_WRITE_ROLES
from markettwin_control_api.config import get_settings
from markettwin_control_api.evidence.artifact_url_signer import ArtifactUrlSigner
from markettwin_control_api.knowledge.census import default_census_config
from markettwin_control_api.knowledge.link_research import validate_link_target
from markettwin_control_api.knowledge.map_repository import (
    MapRepository,
    freshness_summary,
)
from markettwin_control_api.persistence.repositories import WorkspaceRepository
from markettwin_control_api.persistence.repositories.authorization_repository import TargetAuthorizationRepository

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix=(
        "/api/v1/workspaces/{workspace_id}"
        "/applications/{application_id}/targets/{target_id}"
    ),
    tags=["App Maps"],
)


class AppMapBuildResponse(BaseModel):
    map_id: UUID
    version_number: int
    status: str


class AppMapResearchRequest(BaseModel):
    research_url: str = Field(min_length=1, max_length=2048)


class AppMapCounts(BaseModel):
    expected: int
    reachable: int
    by_status: dict[str, int]


class AppMapSpend(BaseModel):
    calls: int
    tokens: int
    seconds: float


class AppMapHarvestSpend(BaseModel):
    calls: int
    tokens: int


class AppMapHarvestBlock(BaseModel):
    status: str
    visited: int
    reachable: int
    blocked: int
    failed: int
    unprobed_budget: int
    enriched_groups: int
    template_groups: int
    spend: AppMapHarvestSpend


class AppMapSkillLineOut(BaseModel):
    name: str
    lifecycle_status: str | None
    last_replay_result: str | None
    last_replay_at: datetime | None


class AppMapFreshnessBlock(BaseModel):
    state: str
    last_preflight_at: datetime | None
    last_preflight_id: str | None
    outcome_counts: dict[str, int]
    deferred_count: int


class AppMapPreflightResponse(BaseModel):
    preflight_id: UUID
    map_id: UUID
    status: str


class AppMapPreflightDetail(BaseModel):
    preflight_id: UUID
    map_id: UUID
    status: str
    resulting_map_id: UUID | None
    trigger: str
    outcome: dict | None
    deferred: list | None
    tier_counts: dict | None
    spend_seconds: float | None
    failure_code: str | None
    failure_message: str | None
    failure_site: str | None
    started_at: datetime
    completed_at: datetime | None


class AppMapSummary(BaseModel):
    map_id: UUID
    version_number: int
    status: str
    research_queued: bool = False
    release_state: str | None
    release_scope: str | None
    base_url: str
    builder_version: str
    started_at: datetime
    completed_at: datetime | None
    counts: AppMapCounts
    gate_metrics: dict[str, object]
    spend: AppMapSpend
    harvest: AppMapHarvestBlock
    freshness: AppMapFreshnessBlock
    skills: list[AppMapSkillLineOut]


class AppMapHarvestRequest(BaseModel):
    journey_terminal_url: str | None = Field(default=None, max_length=2048)


class AppMapHarvestResponse(BaseModel):
    map_id: UUID
    harvest_status: str


class AppMapInventoryPage(BaseModel):
    id: UUID
    canonical_url: str
    route_pattern: str
    crawl_status: str
    harvest_status: str | None
    title: str | None


class AppMapInventoryState(BaseModel):
    state_key: str
    state_kind: str
    state_id: str | None
    signatures_present: bool
    element_count: int
    form_count: int


class AppMapInventoryElement(BaseModel):
    state_key: str
    role: str
    name: str
    actionability: str
    safety_class: str
    locators: list[dict[str, object]]
    navigates_to_url: str | None


class AppMapInventoryField(BaseModel):
    label: str
    field_type: str
    required: bool
    validation_source: str


class AppMapInventoryForm(BaseModel):
    state_key: str
    form_key: str
    method: str | None
    probe_status: str
    fields: list[AppMapInventoryField]


class AppMapPageInventory(BaseModel):
    page: AppMapInventoryPage
    states: list[AppMapInventoryState]
    elements: list[AppMapInventoryElement]
    forms: list[AppMapInventoryForm]


class AppMapJourneyStepOut(BaseModel):
    page_url: str | None
    role: str | None
    name: str | None


class AppMapJourneySkillOut(BaseModel):
    name: str
    lifecycle_status: str | None


class AppMapJourneyOut(BaseModel):
    name: str
    intent: str | None
    selection: str
    skill: AppMapJourneySkillOut | None
    steps: list[AppMapJourneyStepOut]


class AppMapJourneyList(BaseModel):
    items: list[AppMapJourneyOut]


class AppMapEvidenceOut(BaseModel):
    url: str
    kind: str
    sha256: str
    byte_size: int
    redaction_status: str


class AppMapPageOut(BaseModel):
    canonical_url: str
    route_pattern: str
    crawl_status: str
    http_status: int | None
    redirect_target: str | None
    requires_auth: bool
    title: str | None
    source_kinds: list[str]
    confidence: str
    last_verified_at: datetime | None


class AppMapPageList(BaseModel):
    map_id: UUID
    version_number: int
    total: int
    items: list[AppMapPageOut]


async def require_app_map_access(
    request: Request, workspace_id: UUID, *, write: bool
) -> UUID:
    user_id = await get_authenticated_user_id(request=request)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        workspace = await WorkspaceRepository(session).get_for_user(
            workspace_id=workspace_id, user_id=user_id
        )
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if write and workspace.role not in WORKSPACE_WRITE_ROLES:
        raise HTTPException(status_code=403, detail="Workspace write access is required.")
    return user_id


async def _resolve_scope(
    session: AsyncSession, workspace_id: UUID, application_id: UUID, target_id: UUID
) -> tuple[Application, ApplicationTarget]:
    application = await session.get(Application, application_id)
    if (
        application is None
        or application.workspace_id != workspace_id
        or application.status != "active"
        or application.deleted_at is not None
    ):
        raise HTTPException(status_code=404, detail="Application not found.")
    target = await session.get(ApplicationTarget, target_id)
    if (
        target is None
        or target.application_id != application_id
        or target.status != "active"
        or target.deleted_at is not None
    ):
        raise HTTPException(status_code=404, detail="Target not found.")
    return application, target


def _repository(request: Request) -> MapRepository:
    return MapRepository(get_database_runtime(request).session_factory)


async def _select_map(
    repository: MapRepository, application_id: UUID, target_id: UUID
):
    """The map the read endpoints serve: latest ready, else latest of any status."""
    app_map = await repository.latest_ready_map(application_id, target_id)
    if app_map is None:
        app_map = await repository.latest_map(application_id, target_id)
    return app_map


@router.post("/map-builds", response_model=AppMapBuildResponse, status_code=202)
async def create_map_build(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    request: Request,
    response: Response,
    payload: AppMapResearchRequest | None = Body(default=None),
) -> AppMapBuildResponse:
    await require_app_map_access(request, workspace_id, write=True)
    database = get_database_runtime(request)
    config = default_census_config()
    async with database.session_factory() as session:
        _, target = await _resolve_scope(
            session, workspace_id, application_id, target_id
        )
        base_url = target.base_url
        if isinstance(payload, AppMapResearchRequest):
            try:
                url = canonical_url(validate_link_target(payload.research_url))
                page, base = urlsplit(url), urlsplit(canonical_url(base_url))
            except ValueError as exc:
                raise HTTPException(422, "Enter a public URL on the selected target.") from exc
            if (page.scheme, page.netloc) != (base.scheme, base.netloc):
                raise HTTPException(422, "The research link must be on the selected target.")
            authorization = await TargetAuthorizationRepository(session).get_active(target_id=target_id)
            if authorization is None:
                raise HTTPException(409, "Authorize the selected target before researching workflows.")
            config["skill_research_url"] = url
    app_map, created = await _repository(request).create_build(
        workspace_id=workspace_id,
        application_id=application_id,
        target_id=target_id,
        base_url=base_url,
        census_config=config,
    )
    if "skill_research_url" in config and app_map.census_config.get("skill_research_url") != config["skill_research_url"]:
        raise HTTPException(409, "This target already has a different map build in progress.")
    response.status_code = 202 if created else 200
    return AppMapBuildResponse(
        map_id=app_map.id,
        version_number=app_map.version_number,
        status=app_map.status,
    )


async def build_map_summary(
    repository: MapRepository, app_map
) -> AppMapSummary:
    """Assemble the graph-backed summary for one map (doc 16 section 10.1)."""
    by_status = await repository.count_pages_by_status(app_map.id)
    counts = AppMapCounts(
        expected=sum(by_status.values()),
        reachable=by_status.get("fetch_ok", 0) + by_status.get("redirect", 0),
        by_status=by_status,
    )
    extras = await repository.harvest_extras(app_map)
    skill_lines = await repository.list_map_skills(app_map.id)
    return AppMapSummary(
        map_id=app_map.id,
        version_number=app_map.version_number,
        status=app_map.status,
        research_queued=(
            app_map.status == "ready" and app_map.harvest_status == "not_started"
            and bool((app_map.census_config or {}).get("skill_research_url"))
        ),
        release_state=app_map.release_state,
        release_scope=app_map.release_scope,
        base_url=app_map.base_url,
        builder_version=app_map.builder_version,
        started_at=app_map.started_at,
        completed_at=app_map.completed_at,
        counts=counts,
        gate_metrics=app_map.gate_metrics,
        spend=AppMapSpend(
            calls=app_map.mapping_spend_calls,
            tokens=app_map.mapping_spend_tokens,
            seconds=app_map.mapping_spend_seconds,
        ),
        freshness=AppMapFreshnessBlock(**freshness_summary(app_map)),
        harvest=AppMapHarvestBlock(
            status=app_map.harvest_status or "not_started",
            visited=extras.visited,
            reachable=extras.reachable,
            blocked=extras.blocked,
            failed=extras.failed,
            unprobed_budget=extras.unprobed_budget,
            enriched_groups=extras.enriched_groups,
            template_groups=extras.template_groups,
            spend=AppMapHarvestSpend(
                calls=extras.spend_calls, tokens=extras.spend_tokens
            ),
        ),
        skills=[
            AppMapSkillLineOut(
                name=line.name,
                lifecycle_status=line.lifecycle_status,
                last_replay_result=line.last_replay_result,
                last_replay_at=line.last_replay_at,
            )
            for line in skill_lines
        ],
    )


@router.get("/app-map", response_model=AppMapSummary)
async def get_app_map_summary(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    request: Request,
) -> AppMapSummary:
    await require_app_map_access(request, workspace_id, write=False)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        await _resolve_scope(session, workspace_id, application_id, target_id)
    repository = _repository(request)
    # This is build progress UI; serving an older ready version hides a rebuild.
    # Run snapshots and graph readers keep their separate latest-ready selection.
    app_map = await repository.latest_map(application_id, target_id)
    if app_map is None:
        raise HTTPException(status_code=404, detail="no app map")
    return await build_map_summary(repository, app_map)


@router.get("/app-map/pages", response_model=AppMapPageList)
async def list_app_map_pages(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    request: Request,
    status: str | None = Query(default=None),
    pattern: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> AppMapPageList:
    await require_app_map_access(request, workspace_id, write=False)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        await _resolve_scope(session, workspace_id, application_id, target_id)
    repository = _repository(request)
    app_map = await _select_map(repository, application_id, target_id)
    if app_map is None:
        raise HTTPException(status_code=404, detail="no app map")
    total, pages = await repository.list_pages(
        app_map.id,
        crawl_status=status,
        route_pattern=pattern,
        limit=limit,
        offset=offset,
    )
    return AppMapPageList(
        map_id=app_map.id,
        version_number=app_map.version_number,
        total=total,
        items=[
            AppMapPageOut(
                canonical_url=page.canonical_url,
                route_pattern=page.route_pattern,
                crawl_status=page.crawl_status,
                http_status=page.http_status,
                redirect_target=page.redirect_target,
                requires_auth=page.requires_auth,
                title=page.title,
                source_kinds=list(page.source_kinds),
                confidence=page.confidence,
                last_verified_at=page.last_verified_at,
            )
            for page in pages
        ],
    )


@router.post(
    "/app-maps/{map_id}/harvest",
    response_model=AppMapHarvestResponse,
    status_code=202,
)
async def trigger_app_map_harvest(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    map_id: UUID,
    request: Request,
    response: Response,
    payload: AppMapHarvestRequest | None = Body(default=None),
) -> AppMapHarvestResponse:
    """Start the deep harvest for a census-ready map (doc 16 sections
    6.1, 10.1): 202 when this call starts it, 200 when a harvest is
    already in flight, 409 when the map is not census-ready."""
    await require_app_map_access(request, workspace_id, write=True)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        await _resolve_scope(session, workspace_id, application_id, target_id)
    repository = _repository(request)
    app_map = await repository.get_map_in_scope(
        map_id, application_id=application_id, target_id=target_id
    )
    if app_map is None:
        raise HTTPException(status_code=404, detail="App map not found.")
    if app_map.status != "ready":
        raise HTTPException(status_code=409, detail="Map is not census-ready.")
    _, started = await repository.start_harvest(
        map_id,
        journey_terminal_url=(
            payload.journey_terminal_url if payload is not None else None
        ),
    )
    response.status_code = 202 if started else 200
    return AppMapHarvestResponse(map_id=map_id, harvest_status="building")


@router.post(
    "/app-maps/{map_id}/preflights",
    response_model=AppMapPreflightResponse,
    status_code=202,
)
async def trigger_app_map_preflight(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    map_id: UUID,
    request: Request,
    response: Response,
) -> AppMapPreflightResponse:
    """Start a freshness preflight for a map (doc 23 section 9.3):
    202 when this call starts it, 200 when one is already in flight
    (the join answer), 409 when the map cannot be swept — not ready,
    or a harvest is building on it."""
    await require_app_map_access(request, workspace_id, write=True)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        await _resolve_scope(session, workspace_id, application_id, target_id)
    repository = _repository(request)
    app_map = await repository.get_map_in_scope(
        map_id, application_id=application_id, target_id=target_id
    )
    if app_map is None:
        raise HTTPException(status_code=404, detail="App map not found.")
    if app_map.status != "ready" or app_map.harvest_status == "building":
        raise HTTPException(
            status_code=409, detail="Map cannot be preflighted now."
        )
    preflight, created = await repository.create_preflight_for_map(
        map_id, trigger="manual"
    )
    if preflight is None:
        raise HTTPException(status_code=404, detail="App map not found.")
    response.status_code = 202 if created else 200
    return AppMapPreflightResponse(
        preflight_id=preflight.id, map_id=map_id, status=preflight.status
    )


@router.get(
    "/app-maps/{map_id}/preflights/{preflight_id}",
    response_model=AppMapPreflightDetail,
)
async def get_app_map_preflight(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    map_id: UUID,
    preflight_id: UUID,
    request: Request,
) -> AppMapPreflightDetail:
    """One preflight's record (doc 23 section 9.3)."""
    await require_app_map_access(request, workspace_id, write=False)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        await _resolve_scope(session, workspace_id, application_id, target_id)
    repository = _repository(request)
    app_map = await repository.get_map_in_scope(
        map_id, application_id=application_id, target_id=target_id
    )
    if app_map is None:
        raise HTTPException(status_code=404, detail="App map not found.")
    preflight = await repository.get_preflight_in_scope(
        preflight_id,
        map_id=map_id,
        application_id=application_id,
        target_id=target_id,
    )
    if preflight is None:
        raise HTTPException(status_code=404, detail="Preflight not found.")
    return AppMapPreflightDetail(
        preflight_id=preflight.id,
        map_id=map_id,
        status=preflight.status,
        resulting_map_id=preflight.resulting_map_id,
        trigger=preflight.trigger,
        outcome=preflight.outcome,
        deferred=preflight.deferred,
        tier_counts=preflight.tier_counts,
        spend_seconds=preflight.spend_seconds,
        failure_code=preflight.failure_code,
        failure_message=preflight.failure_message,
        failure_site=preflight.failure_site,
        started_at=preflight.started_at,
        completed_at=preflight.completed_at,
    )


@router.get("/app-map/pages/{page_id}/inventory", response_model=AppMapPageInventory)
async def get_app_map_page_inventory(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    page_id: UUID,
    request: Request,
) -> AppMapPageInventory:
    """One page's harvested inventory (doc 16 section 10.2)."""
    await require_app_map_access(request, workspace_id, write=False)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        await _resolve_scope(session, workspace_id, application_id, target_id)
    repository = _repository(request)
    app_map = await _select_map(repository, application_id, target_id)
    if app_map is None:
        raise HTTPException(status_code=404, detail="no app map")
    page = await repository.get_page_in_map(app_map.id, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    states = await repository.list_states_for_page(page.id)
    state_ids = [state.id for state in states]
    elements = await repository.list_elements_for_states(state_ids)
    forms = await repository.list_forms_for_states(state_ids)
    fields = await repository.list_fields_for_forms([form.id for form in forms])
    state_keys = {state.id: state.state_key for state in states}
    elements_by_state: dict[UUID, int] = {}
    for element in elements:
        elements_by_state[element.map_page_state_id] = (
            elements_by_state.get(element.map_page_state_id, 0) + 1
        )
    forms_by_state: dict[UUID, int] = {}
    for form in forms:
        forms_by_state[form.map_page_state_id] = (
            forms_by_state.get(form.map_page_state_id, 0) + 1
        )
    fields_by_form: dict[UUID, list[AppMapInventoryField]] = {}
    for field in fields:
        fields_by_form.setdefault(field.form_id, []).append(
            AppMapInventoryField(
                label=field.label,
                field_type=field.field_type,
                required=field.required,
                validation_source=field.validation_source,
            )
        )
    return AppMapPageInventory(
        page=AppMapInventoryPage(
            id=page.id,
            canonical_url=page.canonical_url,
            route_pattern=page.route_pattern,
            crawl_status=page.crawl_status,
            harvest_status=page.harvest_status,
            title=page.title,
        ),
        states=[
            AppMapInventoryState(
                state_key=state.state_key,
                state_kind=state.state_kind,
                state_id=state.state_id,
                signatures_present=state.element_signature is not None,
                element_count=elements_by_state.get(state.id, 0),
                form_count=forms_by_state.get(state.id, 0),
            )
            for state in states
        ],
        elements=[
            AppMapInventoryElement(
                state_key=state_keys.get(element.map_page_state_id, ""),
                role=element.role,
                name=element.name,
                actionability=element.actionability,
                safety_class=element.safety_class,
                locators=list(element.locators or []),
                navigates_to_url=element.navigates_to_url,
            )
            for element in elements
        ],
        forms=[
            AppMapInventoryForm(
                state_key=state_keys.get(form.map_page_state_id, ""),
                form_key=form.form_key,
                method=form.method,
                probe_status=form.probe_status,
                fields=fields_by_form.get(form.id, []),
            )
            for form in forms
        ],
    )


@router.get("/app-map/journeys", response_model=AppMapJourneyList)
async def list_app_map_journeys(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    request: Request,
) -> AppMapJourneyList:
    """The map's journeys with their compiled skills (doc 16 section 10.2)."""
    await require_app_map_access(request, workspace_id, write=False)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        await _resolve_scope(session, workspace_id, application_id, target_id)
    repository = _repository(request)
    app_map = await _select_map(repository, application_id, target_id)
    if app_map is None:
        raise HTTPException(status_code=404, detail="no app map")
    journeys = await repository.list_journeys(app_map.id)
    state_ids: list[UUID] = []
    element_ids: list[UUID] = []
    skill_ids: list[UUID] = []
    for journey in journeys:
        for step in journey.steps or []:
            if isinstance(step, dict):
                if step.get("map_page_state_id"):
                    state_ids.append(UUID(str(step["map_page_state_id"])))
                if step.get("element_id"):
                    element_ids.append(UUID(str(step["element_id"])))
        if journey.skill_id is not None:
            skill_ids.append(journey.skill_id)
    states = await repository.get_states_by_ids(state_ids)
    pages = await repository.get_pages_by_ids(
        [state.map_page_id for state in states.values()]
    )
    elements = await repository.get_elements_by_ids(element_ids)
    skill_lines = await repository.skill_lines_by_ids(skill_ids)
    items: list[AppMapJourneyOut] = []
    for journey in journeys:
        steps_out: list[AppMapJourneyStepOut] = []
        for step in journey.steps or []:
            if not isinstance(step, dict):
                continue
            state = states.get(UUID(str(step["map_page_state_id"]))) if step.get(
                "map_page_state_id"
            ) else None
            page = pages.get(state.map_page_id) if state is not None else None
            element = elements.get(UUID(str(step["element_id"]))) if step.get(
                "element_id"
            ) else None
            steps_out.append(
                AppMapJourneyStepOut(
                    page_url=page.canonical_url if page is not None else None,
                    role=element.role if element is not None else None,
                    name=element.name if element is not None else None,
                )
            )
        line = (
            skill_lines.get(journey.skill_id)
            if journey.skill_id is not None
            else None
        )
        items.append(
            AppMapJourneyOut(
                name=journey.name,
                intent=journey.intent,
                selection=journey.selection,
                skill=(
                    AppMapJourneySkillOut(
                        name=line.name, lifecycle_status=line.lifecycle_status
                    )
                    if line is not None
                    else None
                ),
                steps=steps_out,
            )
        )
    return AppMapJourneyList(items=items)


@router.get("/app-map/evidence/{evidence_id}", response_model=AppMapEvidenceOut)
async def get_app_map_evidence(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    evidence_id: UUID,
    request: Request,
) -> AppMapEvidenceOut:
    """A signed download URL for one stored evidence object (doc 16
    section 10.2). The object must belong to the served map."""
    await require_app_map_access(request, workspace_id, write=False)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        await _resolve_scope(session, workspace_id, application_id, target_id)
    repository = _repository(request)
    app_map = await _select_map(repository, application_id, target_id)
    if app_map is None:
        raise HTTPException(status_code=404, detail="no app map")
    evidence = await repository.get_evidence(evidence_id)
    if evidence is None or evidence.app_map_id != app_map.id:
        raise HTTPException(status_code=404, detail="Evidence not found.")
    settings = get_settings()
    signer = ArtifactUrlSigner(
        region=settings.s3_region,
        endpoint_url=settings.s3_endpoint_url,
        access_key_id=settings.aws_access_key_id,
        secret_access_key=(
            settings.aws_secret_access_key.get_secret_value()
            if settings.aws_secret_access_key
            else None
        ),
        session_token=(
            settings.aws_session_token.get_secret_value()
            if settings.aws_session_token
            else None
        ),
    )
    return AppMapEvidenceOut(
        url=signer.create_download_url(
            bucket=settings.s3_bucket,
            object_key=evidence.object_key,
            download_filename=evidence.object_key.rsplit("/", 1)[-1],
        ),
        kind=evidence.kind,
        sha256=evidence.sha256,
        byte_size=evidence.byte_size,
        redaction_status=evidence.redaction_status,
    )


# --- Phase 2: expectations, conflicts, grounding (doc 21 section 14.2) ---


class AppMapExpectationOut(BaseModel):
    id: UUID
    subject_kind: str
    subject_id: UUID
    page_url: str | None
    statement: str
    oracle_source: str
    source_ref: str | None
    status: str
    confidence: str
    assertion: dict[str, object] | None
    assertion_kind: str | None
    assertion_origin: str | None
    promoted_by: str | None
    conflicted: bool
    has_open_conflict: bool
    verdict_eligible: bool
    last_checked_at: str | None
    last_check_result: str | None


class AppMapExpectationList(BaseModel):
    items: list[AppMapExpectationOut]
    gate: dict[str, object]


class AppMapConflictOut(BaseModel):
    id: UUID
    expectation_id: UUID
    conflict_kind: str | None
    detection_source: str | None
    observed_behaviour: str
    evidence_refs: list[object]
    status: str
    resolution: str | None
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime | None


class AppMapConflictList(BaseModel):
    items: list[AppMapConflictOut]


class AppMapPromoteRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class AppMapRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class AppMapResolveConflictRequest(BaseModel):
    resolution: str = Field(pattern="^(docs-win|app-win|owner-decided)$")
    owner_text: str | None = Field(default=None, max_length=4000)


class AppMapGroundingRequest(BaseModel):
    probe: bool = False
    approved_test_data: dict[str, str] | None = None


class AppMapGroundingResponse(BaseModel):
    map_id: UUID
    grounding_status: str


class AppMapAuditOut(BaseModel):
    audit_kind: str
    checks: dict[str, object]
    findings: list[object]
    graph_fingerprint: str
    created_at: datetime | None


def _expectation_out(record: dict[str, object]) -> AppMapExpectationOut:
    return AppMapExpectationOut(
        id=UUID(str(record["id"])),
        subject_kind=str(record["subject_kind"]),
        subject_id=UUID(str(record["subject_id"])),
        page_url=record["page_url"],  # type: ignore[arg-type]
        statement=str(record["statement"]),
        oracle_source=str(record["oracle_source"]),
        source_ref=record["source_ref"],  # type: ignore[arg-type]
        status=str(record["status"]),
        confidence=str(record["confidence"]),
        assertion=record["assertion"],  # type: ignore[arg-type]
        assertion_kind=record["assertion_kind"],  # type: ignore[arg-type]
        assertion_origin=record["assertion_origin"],  # type: ignore[arg-type]
        promoted_by=record["promoted_by"],  # type: ignore[arg-type]
        conflicted=bool(record["conflicted"]),
        has_open_conflict=bool(record["has_open_conflict"]),
        verdict_eligible=bool(record["verdict_eligible"]),
        last_checked_at=record["last_checked_at"],  # type: ignore[arg-type]
        last_check_result=record["last_check_result"],  # type: ignore[arg-type]
    )


async def _scoped_map(
    request: Request,
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    map_id: UUID,
):  # noqa: ANN202
    """Resolve scope + the map in scope, or raise the incumbent 404s."""
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        await _resolve_scope(session, workspace_id, application_id, target_id)
    repository = _repository(request)
    app_map = await repository.get_map_in_scope(
        map_id, application_id=application_id, target_id=target_id
    )
    if app_map is None:
        raise HTTPException(status_code=404, detail="App map not found.")
    return repository, app_map


@router.get(
    "/app-maps/{map_id}/expectations", response_model=AppMapExpectationList
)
async def list_app_map_expectations(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    map_id: UUID,
    request: Request,
) -> AppMapExpectationList:
    """All expectations on the map with verdict stamps + the gate (§14.2)."""
    await require_app_map_access(request, workspace_id, write=False)
    repository, _app_map = await _scoped_map(
        request, workspace_id, application_id, target_id, map_id
    )
    records = await repository.list_expectation_records(map_id)
    summary = await repository.expectation_summary(map_id)
    gate = {
        key: summary[key]
        for key in (
            "expectations_total",
            "expectations_by_source",
            "verdict_eligible",
            "conflicted_open",
            "doc_sourced_share",
            "journeys_total",
            "journeys_with_expectations",
            "journeys_without_expectations",
            "expectation_gate",
            "grounding_status",
            "release_state",
            "release_scope",
        )
    }
    return AppMapExpectationList(
        items=[_expectation_out(record) for record in records], gate=gate
    )


@router.get(
    "/app-maps/{map_id}/expectations/suggestions",
    response_model=AppMapExpectationList,
)
async def list_app_map_suggestions(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    map_id: UUID,
    request: Request,
) -> AppMapExpectationList:
    """The promotion queue (doc 21 section 5.5): per-record only."""
    await require_app_map_access(request, workspace_id, write=False)
    repository, _app_map = await _scoped_map(
        request, workspace_id, application_id, target_id, map_id
    )
    records = await repository.list_suggestions(map_id)
    return AppMapExpectationList(
        items=[_expectation_out(record) for record in records], gate={}
    )


@router.post(
    "/app-maps/{map_id}/expectations/{expectation_id}/promote",
    response_model=AppMapExpectationOut,
)
async def promote_app_map_expectation(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    map_id: UUID,
    expectation_id: UUID,
    request: Request,
    payload: AppMapPromoteRequest | None = Body(default=None),
) -> AppMapExpectationOut:
    """Promote ONE record (doc 21 section 5.5). No bulk approve exists."""
    user_id = await require_app_map_access(request, workspace_id, write=True)
    repository, _app_map = await _scoped_map(
        request, workspace_id, application_id, target_id, map_id
    )
    try:
        await repository.record_promotion(
            expectation_id,
            app_map_id=map_id,
            actor=str(user_id),
            note=payload.note if payload is not None else None,
        )
    except ValueError as error:
        detail = str(error)
        raise HTTPException(
            status_code=404 if detail == "expectation_not_found" else 409,
            detail=detail,
        ) from error
    records = await repository.list_expectation_records(map_id)
    for record in records:
        if record["id"] == str(expectation_id):
            return _expectation_out(record)
    raise HTTPException(status_code=404, detail="expectation_not_found")


@router.post(
    "/app-maps/{map_id}/expectations/{expectation_id}/reject",
    response_model=AppMapExpectationOut,
)
async def reject_app_map_expectation(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    map_id: UUID,
    expectation_id: UUID,
    request: Request,
    payload: AppMapRejectRequest = Body(...),
) -> AppMapExpectationOut:
    """Reject ONE record: it leaves the queue until re-promoted (§5.5)."""
    user_id = await require_app_map_access(request, workspace_id, write=True)
    repository, _app_map = await _scoped_map(
        request, workspace_id, application_id, target_id, map_id
    )
    try:
        await repository.record_rejection(
            expectation_id, app_map_id=map_id, actor=str(user_id), reason=payload.reason
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    records = await repository.list_expectation_records(map_id)
    for record in records:
        if record["id"] == str(expectation_id):
            return _expectation_out(record)
    raise HTTPException(status_code=404, detail="expectation_not_found")


@router.get("/app-maps/{map_id}/conflicts", response_model=AppMapConflictList)
async def list_app_map_conflicts(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    map_id: UUID,
    request: Request,
) -> AppMapConflictList:
    """Open + resolved conflicts; the split rule keeps both sides (§9)."""
    await require_app_map_access(request, workspace_id, write=False)
    repository, _app_map = await _scoped_map(
        request, workspace_id, application_id, target_id, map_id
    )
    rows = await repository.list_conflicts(map_id)
    return AppMapConflictList(
        items=[
            AppMapConflictOut(
                id=row.id,
                expectation_id=row.expectation_id,
                conflict_kind=row.conflict_kind,
                detection_source=row.detection_source,
                observed_behaviour=row.observed_behaviour,
                evidence_refs=list(row.evidence_refs or []),
                status=row.status,
                resolution=row.resolution,
                decided_by=row.decided_by,
                decided_at=row.decided_at,
                created_at=row.created_at,
            )
            for row in rows
        ]
    )


@router.post(
    "/app-maps/{map_id}/conflicts/{conflict_id}/resolve",
    response_model=AppMapConflictOut,
)
async def resolve_app_map_conflict(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    map_id: UUID,
    conflict_id: UUID,
    request: Request,
    payload: AppMapResolveConflictRequest = Body(...),
) -> AppMapConflictOut:
    """Resolve one conflict (doc 21 sections 9.3/9.4). app-win and
    owner-decided resolutions require the owner's restated statement
    text (422 without it); the write-role check above is the
    non-owner 403."""
    user_id = await require_app_map_access(request, workspace_id, write=True)
    if payload.resolution in ("app-win", "owner-decided") and not (
        payload.owner_text and payload.owner_text.strip()
    ):
        raise HTTPException(
            status_code=422,
            detail="this resolution requires the owner's restated statement text",
        )
    repository, _app_map = await _scoped_map(
        request, workspace_id, application_id, target_id, map_id
    )
    try:
        conflict = await repository.resolve_conflict(
            conflict_id,
            app_map_id=map_id,
            resolution=payload.resolution,
            actor=str(user_id),
            owner_text=payload.owner_text,
        )
    except ValueError as error:
        detail = str(error)
        raise HTTPException(
            status_code=404 if detail.endswith("_not_found") else 409,
            detail=detail,
        ) from error
    return AppMapConflictOut(
        id=conflict.id,
        expectation_id=conflict.expectation_id,
        conflict_kind=conflict.conflict_kind,
        detection_source=conflict.detection_source,
        observed_behaviour=conflict.observed_behaviour,
        evidence_refs=list(conflict.evidence_refs or []),
        status=conflict.status,
        resolution=conflict.resolution,
        decided_by=conflict.decided_by,
        decided_at=conflict.decided_at,
        created_at=conflict.created_at,
    )


@router.post(
    "/app-maps/{map_id}/grounding",
    response_model=AppMapGroundingResponse,
    status_code=202,
)
async def trigger_app_map_grounding(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    map_id: UUID,
    request: Request,
    response: Response,
    payload: AppMapGroundingRequest | None = Body(default=None),
) -> AppMapGroundingResponse:
    """Start expectation grounding for a harvest-ready map (§14.2):
    202 when this call starts it, 200 when already in flight, 409 when
    the map is not harvest-ready (both statuses named)."""
    await require_app_map_access(request, workspace_id, write=True)
    repository, app_map = await _scoped_map(
        request, workspace_id, application_id, target_id, map_id
    )
    if app_map.status != "ready" or app_map.harvest_status not in (
        "ready",
        "partial",
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Map is not ready for grounding: "
                f"census_status={app_map.status!r}, "
                f"harvest_status={app_map.harvest_status!r}, "
                f"grounding_status={app_map.grounding_status!r}."
            ),
        )
    _, started = await repository.start_grounding(
        map_id,
        probe=payload.probe if payload is not None else False,
        approved_test_data=(
            payload.approved_test_data if payload is not None else None
        ),
    )
    response.status_code = 202 if started else 200
    return AppMapGroundingResponse(map_id=map_id, grounding_status="building")


@router.get("/app-map/audits/latest", response_model=AppMapAuditOut)
async def get_latest_app_map_audit(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    request: Request,
) -> AppMapAuditOut:
    """The newest read-only graph audit for the served map (§11/§14.2)."""
    await require_app_map_access(request, workspace_id, write=False)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        await _resolve_scope(session, workspace_id, application_id, target_id)
    repository = _repository(request)
    app_map = await _select_map(repository, application_id, target_id)
    if app_map is None:
        raise HTTPException(status_code=404, detail="no app map")
    report = await repository.latest_audit_report(app_map.id)
    if report is None:
        raise HTTPException(status_code=404, detail="no audit report")
    return AppMapAuditOut(
        audit_kind=report.audit_kind,
        checks=dict(report.checks or {}),
        findings=list(report.findings or []),
        graph_fingerprint=report.graph_fingerprint,
        created_at=report.created_at,
    )


# --- Phase 3: skill library (doc 22 section 12.2) ---------------------------
# The library is scope-served (the target's skills, whatever map
# compiled them); lifecycle writes pass the shared transition
# authority in the repository. No model calls in this section either.


class AppMapSkillOut(BaseModel):
    skill_id: UUID
    name: str
    skill_kind: str
    task_source_kind: str | None = None
    lifecycle_status: str | None
    version_id: UUID | None
    version_number: int | None
    last_replay_result: str | None
    last_replay_at: datetime | None
    replay_count: int
    heal_count: int
    retired_reason: str | None
    diagnosis_model_calls: int
    status_reason: str | None


class AppMapSkillList(BaseModel):
    items: list[AppMapSkillOut]


class AppMapSkillUsageOut(BaseModel):
    skill_id: str
    total_model_calls: int
    total_model_tokens: int
    diagnosis_model_calls: int
    events_by_kind: dict[str, int]
    latest_version: dict[str, object] | None


class AppMapSkillRetireRequest(BaseModel):
    reason: str = Field(default="owner", max_length=32)


class AppMapSkillActionOut(BaseModel):
    skill_id: UUID
    status: str


class AppMapJourneyCompileOut(BaseModel):
    journey_id: UUID
    status: str


async def _scoped_skill_line(
    repository: MapRepository,
    *,
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    skill_id: UUID,
) -> dict[str, object]:
    lines = await repository.skill_library_lines(
        workspace_id=workspace_id,
        application_id=application_id,
        target_id=target_id,
    )
    for line in lines:
        if line["skill_id"] == skill_id:
            return line
    raise HTTPException(status_code=404, detail="skill not found")


@router.get("/app-map/skills", response_model=AppMapSkillList)
async def list_app_map_skills(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    request: Request,
) -> AppMapSkillList:
    """Every skill in the target's scope with its latest version's
    lifecycle and rollups (doc 22 section 12.2)."""
    await require_app_map_access(request, workspace_id, write=False)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        await _resolve_scope(session, workspace_id, application_id, target_id)
    repository = _repository(request)
    lines = await repository.skill_library_lines(
        workspace_id=workspace_id,
        application_id=application_id,
        target_id=target_id,
    )
    return AppMapSkillList(
        items=[AppMapSkillOut(**line) for line in lines]
    )


@router.get(
    "/app-map/skills/{skill_id}/usage", response_model=AppMapSkillUsageOut
)
async def get_app_map_skill_usage(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    skill_id: UUID,
    request: Request,
) -> AppMapSkillUsageOut:
    """The per-skill usage ledger summary (doc 22 sections 12.1-12.2)."""
    await require_app_map_access(request, workspace_id, write=False)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        await _resolve_scope(session, workspace_id, application_id, target_id)
    repository = _repository(request)
    await _scoped_skill_line(
        repository,
        workspace_id=workspace_id,
        application_id=application_id,
        target_id=target_id,
        skill_id=skill_id,
    )
    summary = await repository.skill_usage_summary(skill_id)
    return AppMapSkillUsageOut(**summary)


@router.post(
    "/app-map/skills/{skill_id}/retire",
    response_model=AppMapSkillActionOut,
)
async def retire_app_map_skill(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    skill_id: UUID,
    request: Request,
    payload: AppMapSkillRetireRequest | None = Body(default=None),
) -> AppMapSkillActionOut:
    """Owner retirement of the skill's latest version (doc 22
    section 12.2): the transition and its ledger row commit together
    in the repository; a refused transition is a 409."""
    user_id = await require_app_map_access(request, workspace_id, write=True)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        await _resolve_scope(session, workspace_id, application_id, target_id)
    repository = _repository(request)
    line = await _scoped_skill_line(
        repository,
        workspace_id=workspace_id,
        application_id=application_id,
        target_id=target_id,
        skill_id=skill_id,
    )
    if line["version_id"] is None:
        raise HTTPException(status_code=409, detail="skill has no versions")
    reason = payload.reason if payload is not None else "owner"
    if reason not in ("superseded", "journey_absent", "owner", "scope_removed"):
        raise HTTPException(status_code=422, detail="unknown retired_reason")
    try:
        version = await repository.transition_skill_version(
            version_id=line["version_id"],  # type: ignore[arg-type]
            to_status="retired",
            kind="retirement",
            evidence={
                "retirement": {
                    "retired_reason": reason,
                    "actor_user_id": str(user_id),
                }
            },
            result="applied",
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return AppMapSkillActionOut(
        skill_id=skill_id, status=version.lifecycle_status
    )


@router.post(
    "/app-map/skills/{skill_id}/reverify",
    response_model=AppMapSkillActionOut,
)
async def reverify_app_map_skill(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    skill_id: UUID,
    request: Request,
) -> AppMapSkillActionOut:
    """Re-verify one skill against the served map (doc 22 section
    12.2): the currency check runs now — 'current', 'demoted' (the
    active version failed currency and is suspect, heal cycle
    engaged), or 'queued' (the poller owns this version's state)."""
    await require_app_map_access(request, workspace_id, write=True)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        await _resolve_scope(session, workspace_id, application_id, target_id)
    repository = _repository(request)
    await _scoped_skill_line(
        repository,
        workspace_id=workspace_id,
        application_id=application_id,
        target_id=target_id,
        skill_id=skill_id,
    )
    app_map = await _select_map(repository, application_id, target_id)
    if app_map is None:
        raise HTTPException(status_code=404, detail="no app map")
    outcome = await repository.reverify_skill(
        skill_id, current_map_id=app_map.id
    )
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="skill not found")
    return AppMapSkillActionOut(skill_id=skill_id, status=outcome)


@router.post(
    "/app-map/journeys/{journey_id}/compile",
    response_model=AppMapJourneyCompileOut,
    status_code=202,
)
async def compile_app_map_journey(
    workspace_id: UUID,
    application_id: UUID,
    target_id: UUID,
    journey_id: UUID,
    request: Request,
) -> AppMapJourneyCompileOut:
    """Queue one journey's compilation into the skill library (doc
    22 section 12.2): the request lands on the map row and the
    re-verification poller compiles on its next pass."""
    await require_app_map_access(request, workspace_id, write=True)
    database = get_database_runtime(request)
    async with database.session_factory() as session:
        await _resolve_scope(session, workspace_id, application_id, target_id)
    repository = _repository(request)
    app_map = await _select_map(repository, application_id, target_id)
    if app_map is None:
        raise HTTPException(status_code=404, detail="no app map")
    queued = await repository.request_journey_compile(app_map.id, journey_id)
    if not queued:
        raise HTTPException(status_code=404, detail="journey not found")
    return AppMapJourneyCompileOut(journey_id=journey_id, status="queued")
