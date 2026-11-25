"""Task-skill verification wiring (doc 29 section 6, consults
E1-E2).

``verify_skill`` is reused untouched; what a task draft adds is
everything around it: a contract re-validation against the source
trace's trusted evidence, an approved-data profile with disposable
generators, prerequisite establishment inside each clean-context
pass (consult E1: the replay scope is built WITH safe_test_data and
the authenticated session is established before the steps run --
the production journey executor supplies neither), and the declared
cleanup on a finally path inside each pass (consult E2).

Refusals are outcomes, recorded on the version's usage ledger with
the version left in draft: a missing input, an unavailable
prerequisite, or a missing source trace never opens a browser.
A verification that runs and fails also leaves the draft in draft
(``on_failure="leave_draft"``): a draft was never trusted, so a
failed first verification is evidence, not a quarantine event --
quarantine is the consumption path's answer to divergence.

Two authorization designs, both inherited from the product's
existing policy rather than invented here:

- A state-changing click in a replay is dispatched only under an
  exact owner-declared synthetic-action rule (the same
  ``SensitiveActionRule`` contract the run approval gate matches):
  the executor inspects the click intent first, and only when a
  rule matches the intent exactly AND the session runs under the
  ``local_development`` fixture policy does it dispatch with the
  intent's one-time fingerprint -- the controller re-derives the
  intent live and refuses any drift. No rule, no dispatch: the
  pass fails and the failure is recorded. Hard-denied actions stay
  denied; inspection raises before any rule is consulted.
- An ``authenticated`` prerequisite is established by installing a
  handover auth snapshot into the pass's clean context (the same
  snapshot mechanism run cases consume), never by replaying
  credential fills: agent fills of credential fields are blocked
  by policy everywhere in this product, so a login definition's
  fills cannot carry a verification pass. The login definition
  still gates the entry (its existence plus the approved
  login keys in the profile are checked before any browser
  opens); establishment is the snapshot's job.
"""

import re
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from markettwin_shared.feature_plan import (
    CaseAction,
    FeatureScope,
    SafeTestValue,
    TestCaseSpec,
)
from markettwin_shared.task_skill import validate_task_skill

from markettwin_execution_orchestrator.harvest.harvest_replay import (
    ReplayAttempt,
    verify_skill,
)
from markettwin_execution_orchestrator.workflow.skill_filter import (
    rebind_task_assertions,
    step_safety_class,
)

LOGIN_KEYS = ("login_username", "login_password")


def generate_input_value(entry: dict[str, Any]) -> str:
    """One disposable generator value (doc 29 section 6.1): the
    closed enum, fresh per pass. Generated values are not secrets;
    the caller logs them to the verification record."""
    kind = entry.get("generator")
    if kind not in {"unique_text", "unique_email"} or entry.get("kind") != "text":
        raise ValueError("unsupported_input_generator")
    prefix = str(entry.get("prefix") or entry.get("label") or "Value")
    suffix = uuid4().hex[:8]
    if kind == "unique_email":
        slug = re.sub(r"[^a-z0-9]+", "-", prefix.casefold()).strip("-") or "user"
        return f"{slug}-{suffix}@example.test"
    return f"{prefix} {suffix}"


def assemble_evidence(trace: dict[str, Any]) -> dict[str, Any]:
    """The trusted evidence context for a compiled definition,
    assembled host-side from the source trace: full predicates from
    the executed spec, results from the trace's assertion records
    (a satisfied status already implies artifact-backed evidence --
    the executor marks evidence-less assertions unverified)."""
    spec = trace.get("spec") or {}
    results = {
        entry["assertion_id"]: entry
        for entry in trace.get("assertions") or []
        if isinstance(entry, dict) and isinstance(entry.get("assertion_id"), str)
    }
    assertions = []
    for entry in spec.get("expected") or []:
        if not isinstance(entry, dict):
            continue
        record = results.get(str(entry.get("assertion_id"))) or {}
        assertions.append(
            {
                "assertion_id": entry.get("assertion_id"),
                "after_step_ordinal": (
                    entry["after_step_ordinal"] + 1
                    if isinstance(entry.get("after_step_ordinal"), int)
                    else None
                ),
                "oracle": entry.get("oracle"),
                "target": entry.get("target"),
                "expected_value": entry.get("expected_value"),
                "status": record.get("status"),
                "has_evidence": record.get("status") == "satisfied",
            }
        )
    return {"assertions": assertions, "owner_decisions": []}


class TaskReplayExecutor:
    """One verification pass of a task skill in one clean context:
    prerequisites established first (E1), the rebound steps with
    their assertion checkpoints, the terminal check, and the
    declared cleanup on the finally path (E2)."""

    def __init__(
        self,
        controller: Any,
        *,
        app_map: Any,
        profile: dict[str, str],
        login_definition: dict[str, Any] | None = None,
        network_policy: str = "public_only",
        fixture_action_rules: tuple = (),
        auth_snapshot: Any = None,
    ) -> None:
        self._controller = controller
        self._app_map = app_map
        self._profile = dict(profile)
        self._login_definition = login_definition
        self.network_policy = network_policy
        self.fixture_action_rules = tuple(fixture_action_rules)
        self._auth_snapshot = auth_snapshot
        self.generated_log: list[dict[str, str]] = []

    async def run_once(self, *, definition: dict[str, Any]) -> ReplayAttempt:
        import asyncio

        from markettwin_execution_orchestrator.browser.contracts import (
            AllowedOrigin,
        )
        from markettwin_execution_orchestrator.browser.errors import (
            BrowserActionBlockedError,
        )
        from markettwin_execution_orchestrator.harvest.harvest_capture import (
            capture_state,
        )
        from markettwin_execution_orchestrator.harvest.harvest_inventory import (
            distil_elements,
            distil_forms,
            identity_for,
        )
        from markettwin_execution_orchestrator.workflow.case_execution import (
            perform_case_action,
        )
        from markettwin_execution_orchestrator.workflow.skill_assertions import (
            check_skill_assertions,
        )

        task = definition.get("task") or {}
        values = dict(self._profile)
        generated: dict[str, str] = {}
        for entry in task.get("inputs") or []:
            if not isinstance(entry, dict):
                continue
            key = entry.get("key")
            if key and key not in values and entry.get("generator"):
                values[key] = generated[key] = generate_input_value(entry)
        self.generated_log.append(generated)
        rebound = rebind_task_assertions(definition, values)
        native = {
            key: rebound[key]
            for key in (
                "case_id",
                "feature_key",
                "title",
                "kind",
                "steps",
                "expected",
                "safety",
                "estimated_seconds",
            )
            if key in rebound
        }
        spec = TestCaseSpec.model_validate(native)
        parts = urlsplit(self._app_map.base_url)
        origin = AllowedOrigin(
            scheme=parts.scheme,
            hostname=parts.hostname or "",
            port=parts.port or (443 if parts.scheme == "https" else 80),
        )
        first_url = next(
            (
                step.url
                for step in spec.steps
                if step.action == "navigate" and step.url
            ),
            self._app_map.base_url,
        )
        scope = FeatureScope(
            feature_key=spec.feature_key,
            goal="Verify a compiled task skill.",
            starting_url=first_url,
            allowed_origins=(f"{parts.scheme}://{parts.netloc}",),
            safe_test_data=tuple(
                SafeTestValue(key=key, value=value)
                for key, value in values.items()
            ),
        )
        execution_id = uuid4()
        journey_id = uuid4()
        needs_auth = any(
            isinstance(entry, dict) and entry.get("kind") == "authenticated"
            for entry in task.get("prerequisites") or []
        )
        handle = await self._controller.create_session(
            execution_id=execution_id,
            journey_id=journey_id,
            allowed_origins=[origin],
            network_policy=self.network_policy,
            js_capture=True,
            fixture_action_rules=self.fixture_action_rules,
            auth_snapshot=self._auth_snapshot if needs_auth else None,
        )

        async def perform(
            controller: Any, handle: Any, action: Any, scope: Any
        ) -> Any:
            """Dispatch one action; clicks pass the approval gate
            described in the module docstring (inspect the intent,
            dispatch under an exact owner-declared rule only)."""
            if action.action != "click" or action.target is None:
                return await perform_case_action(
                    controller, handle, action, scope
                )
            target = action.target
            intent = await self._controller.inspect_click_approval(
                session_id=handle.session_id,
                execution_id=handle.execution_id,
                journey_id=handle.journey_id,
                role=target.role,
                name=target.name,
                label=target.label,
                text=target.text,
                scope_role=target.scope_role,
                scope_name=target.scope_name,
            )
            if intent is None:
                return await perform_case_action(
                    controller, handle, action, scope
                )
            rule = next(
                (
                    rule
                    for rule in self.fixture_action_rules
                    if rule.matches(intent.action)
                ),
                None,
            )
            if rule is None or self.network_policy != "local_development":
                raise BrowserActionBlockedError(
                    "Verification replay has no owner-declared approval "
                    "for this sensitive action."
                )
            return await perform_case_action(
                controller,
                handle,
                action,
                scope,
                approval_fingerprint=intent.fingerprint,
            )
        establishment_attempted = False
        ok = False
        failure_step: int | None = None
        failure_site: str | None = None
        final_url: str | None = None
        final_state_id: str | None = None
        superset_used = False
        try:
            establishment_attempted = True
            prereq_failure = await self._establish_prerequisites(
                handle, scope, rebound, perform
            )
            if prereq_failure is not None:
                return ReplayAttempt(ok=False, failure_site=prereq_failure)
            for index, action in enumerate(spec.steps):
                try:
                    failed = await check_skill_assertions(
                        self._controller, handle, spec, checkpoint=index
                    )
                    if failed:
                        failure_site = f"skill_assertion:{failed}"
                        break
                    await perform(
                        self._controller, handle, action, scope
                    )
                except Exception as exc:  # noqa: BLE001 - a failed pass
                    failure_step = index
                    failure_site = f"case_execution:{type(exc).__name__}"
                    break
            else:
                failed = None
                for checkpoint in (len(spec.steps), None):
                    failed = await check_skill_assertions(
                        self._controller, handle, spec, checkpoint=checkpoint
                    )
                    if failed:
                        break
                if failed:
                    failure_site = f"skill_assertion:{failed}"
                else:
                    capture = await capture_state(
                        self._controller,
                        handle,
                        execution_id=execution_id,
                        journey_id=journey_id,
                        # The page index's documented exception: a
                        # session created from a broker snapshot.
                        authenticated_session=bool(
                            needs_auth and self._auth_snapshot is not None
                        ),
                    )
                    elements = distil_elements(capture)
                    forms = distil_forms(capture)
                    live_state_id, _, _ = identity_for(
                        capture.url, elements, forms
                    )
                    assertion = rebound.get("success_assertion") or {}
                    from markettwin_shared.app_map_common import canonical_url

                    url_ok = canonical_url(capture.url) == canonical_url(
                        str(assertion.get("url") or "")
                    )
                    state_ok = live_state_id == assertion.get("state_id")
                    if not state_ok and assertion.get(
                        "signature_superset_fallback"
                    ):
                        harvested = set(assertion.get("element_signature") or [])
                        live = {
                            f"{element['role']}|{element['name']}"
                            for element in elements
                        }
                        if harvested and harvested <= live:
                            state_ok = True
                            superset_used = True
                    final_url = capture.url
                    final_state_id = live_state_id
                    ok = url_ok and state_ok
                    if not ok:
                        failure_step = len(spec.steps)
                        failure_site = "task_verify:terminal_mismatch"
        except Exception as exc:  # noqa: BLE001 - a failed pass, recorded
            if failure_site is None:
                failure_site = f"task_verify:{type(exc).__name__}"
            ok = False
        finally:
            # Prerequisites may mutate before failing; cleanup still owns that partial pass.
            if establishment_attempted:
                cleanup_ok = await self._run_cleanup(
                    handle, scope, rebound, perform
                )
                if not cleanup_ok and ok:
                    ok = False
                    failure_site = "cleanup"
                elif not cleanup_ok and failure_site is None:
                    failure_site = "cleanup"
            try:
                async with asyncio.timeout(30):
                    await self._controller.close_session(
                        session_id=handle.session_id
                    )
            except Exception:
                pass
        return ReplayAttempt(
            ok=ok,
            failure_step=failure_step,
            failure_site=failure_site,
            final_url=final_url,
            final_state_id=final_state_id,
            superset_used=superset_used,
        )

    async def _establish_prerequisites(
        self, handle: Any, scope: FeatureScope, definition: dict[str, Any],
        perform_case_action: Any,
    ) -> str | None:
        """E1: prerequisites are executed, not assumed. Returns a
        failure_site string, or None when all are established."""
        task = definition.get("task") or {}
        for entry in task.get("prerequisites") or []:
            if not isinstance(entry, dict):
                continue
            kind = entry.get("kind")
            if kind == "authenticated":
                if self._auth_snapshot is not None:
                    # Established at session creation: the clean
                    # context was born authenticated from the
                    # handover snapshot (module docstring).
                    continue
                return "prerequisite_unavailable"
            elif kind == "on_page":
                try:
                    await perform_case_action(
                        self._controller,
                        handle,
                        CaseAction(action="navigate", url=entry.get("url")),
                        scope,
                    )
                except Exception:  # noqa: BLE001
                    return "prerequisite_unavailable"
            # input_available was checked before the browser opened;
            # skill_active was checked against the serving query.
        return None

    async def _run_cleanup(
        self, handle: Any, scope: FeatureScope, definition: dict[str, Any],
        perform_case_action: Any,
    ) -> bool:
        task = definition.get("task") or {}
        cleanup = task.get("cleanup") or {}
        kind = cleanup.get("kind")
        if kind in (None, "none_required"):
            return True
        try:
            if kind == "reset_action":
                name = str(cleanup.get("action") or "Reset fixture data")
                target = cleanup.get("target")
                if not isinstance(target, dict):
                    target = {"role": "button", "name": name}
                await perform_case_action(
                    self._controller,
                    handle,
                    CaseAction(action="click", target=target),
                    scope,
                )
                return True
            if kind == "compensating_steps":
                steps = [
                    CaseAction.model_validate(raw)
                    for raw in cleanup.get("steps") or []
                ]
                success = definition.get("success_assertion") or {}
                if steps and steps[0].action != "navigate" and success.get("url"):
                    steps.insert(
                        0,
                        CaseAction(action="navigate", url=str(success["url"])),
                    )
                for action in steps:
                    await perform_case_action(
                        self._controller, handle, action, scope
                    )
                return True
        except Exception:  # noqa: BLE001 - a failed cleanup fails the pass
            return False
        return True


async def _load_run_context(
    session_factory: Any, task: dict[str, Any], app_map: Any, *, verification_key: str | None = None,
) -> dict[str, Any]:
    """Resolve the source run's trace, approved profile and login
    definition (the poller's path; direct callers pass their own)."""
    from markettwin_database.models import RunEvent, TestRun
    from sqlalchemy import select

    context: dict[str, Any] = {
        "trace": None,
        "profile": None,
        "login_definition": None,
        "fixture_action_rules": (),
        "auth_snapshot": None,
    }
    source = task.get("source") or {}
    run_ref = source.get("run_id")
    if not isinstance(run_ref, str):
        return context
    from uuid import UUID

    from markettwin_execution_orchestrator.workflow.run_request import (
        _parse_approved_test_data,
    )

    async with session_factory() as session:
        run = await session.get(TestRun, UUID(run_ref))
        if run is None or any(
            getattr(run, field, None) != getattr(app_map, field, None)
            for field in ("workspace_id", "application_id", "target_id")
        ):
            return context
        snapshot = run.configuration_snapshot or {}
        if verification_key is not None:
            from markettwin_execution_orchestrator.browser.auth_session_broker import (
                AuthSessionReuseRejected,
                task_verification_sessions,
            )

            auth = snapshot.get("auth_verification") or {}
            if not isinstance(auth, dict):
                auth = {}
            parts = urlsplit(app_map.base_url)
            origin = f"{parts.scheme}://{parts.netloc}"
            try:
                context["auth_snapshot"] = task_verification_sessions.take_for_task_verification(
                    run_id=run.id, target_id=app_map.target_id, origin=origin,
                    case_id=f"task:{verification_key}", role=auth.get("role"),
                    account_reference=auth.get("account_reference"),
                )
            except AuthSessionReuseRejected:
                pass
        context["profile"] = {
            entry.key: entry.value
            for entry in _parse_approved_test_data(snapshot)
        }
        from markettwin_shared.action_approval import SensitiveActionRule

        rules = []
        for raw_rule in snapshot.get("sensitive_action_rules", []) or []:
            try:
                rules.append(SensitiveActionRule.model_validate(raw_rule))
            except Exception:  # noqa: BLE001 - a malformed rule never loads
                continue
        context["fixture_action_rules"] = tuple(rules)
        rows = list(
            await session.scalars(
                select(RunEvent).where(
                    RunEvent.test_run_id == run.id,
                    RunEvent.event_type == "test_case.task_trace",
                ).order_by(RunEvent.id.desc())
            )
        )
        for row in rows:
            payload = row.payload if isinstance(row.payload, dict) else {}
            trace_refs = [entry.get("event_id") for entry in task.get("evidence_refs", [])
                          if isinstance(entry, dict) and entry.get("kind") == "task_trace"]
            if (payload.get("case_id") == source.get("case_id")
                    and (not trace_refs or str(row.id) in trace_refs)):
                from markettwin_execution_orchestrator.workflow.task_spec_store import (
                    restore_task_trace,
                )

                try:
                    context["trace"] = await restore_task_trace(
                        session, payload=payload, run_id=run.id, execution_id=row.execution_id,
                    )
                except (ValueError, TypeError, AttributeError):
                    context["trace"] = None
                break
        from markettwin_execution_orchestrator.expectations import login_skill

        version = await login_skill.select_login_version(
            session, app_map_id=app_map.id
        )
        if version is not None:
            context["login_definition"] = version.definition_json
    return context


async def verify_task_draft(
    *,
    repository: Any,
    app_map: Any,
    skill_version: Any,
    controller: Any,
    profile: dict[str, str] | None = None,
    login_definition: dict[str, Any] | None = None,
    trace: dict[str, Any] | None = None,
    session_factory: Any = None,
    network_policy: str = "public_only",
    fixture_action_rules: tuple = (),
    auth_snapshot: Any = None,
) -> dict[str, Any]:
    """The task-draft verification entry (doc 29 section 6).

    Returns {"status": "replay_verified" | "draft" | "refused",
    "reason": <code, when refused>, "verify": VerifyResult | None}.
    Every refusal is recorded on the version's usage ledger and
    leaves the version in draft; no browser opens for a refusal."""
    from markettwin_execution_orchestrator.harvest.skill_library import (
        record_usage,
    )

    definition = skill_version.definition_json or {}
    task = definition.get("task") or {}

    async def refuse(reason: str, **payload: Any) -> dict[str, Any]:
        await record_usage(
            repository,
            skill_version,
            kind="verification_replay",
            result="refused",
            payload={"reason": reason, **payload},
        )
        return {"status": "refused", "reason": reason, "verify": None}

    if skill_version.lifecycle_status != "draft" or not isinstance(definition.get("task"), dict):
        return await refuse("task_draft_required")

    if session_factory is not None and (
        trace is None or profile is None or login_definition is None
    ):
        loaded = await _load_run_context(
            session_factory, task, app_map, verification_key=str(skill_version.id),
        )
        trace = trace if trace is not None else loaded["trace"]
        profile = profile if profile is not None else loaded["profile"]
        login_definition = (
            login_definition
            if login_definition is not None
            else loaded["login_definition"]
        )
        if not fixture_action_rules:
            fixture_action_rules = loaded["fixture_action_rules"]
        if auth_snapshot is None:
            auth_snapshot = loaded["auth_snapshot"]
    if trace is None:
        return await refuse("evidence_unavailable")
    profile = profile or {}

    pages = await repository.work_list(app_map)
    states = await repository.list_states_for_map(app_map.id)
    inventory = []
    for state in states:
        for element in await repository.list_elements_for_state(state.id):
            inventory.append(
                {
                    "role": element.role,
                    "name": element.name,
                    "label": element.label_text,
                }
            )
    codes = validate_task_skill(
        definition,
        inventory=inventory,
        page_urls=[page.canonical_url for page in pages],
        trace=trace,
        step_safety=[
            step_safety_class(step)
            for step in definition.get("steps") or []
            if isinstance(step, dict)
        ],
        evidence=assemble_evidence(trace),
    )
    if codes:
        return await refuse("contract_invalid", codes=codes)

    missing = [
        entry["key"]
        for entry in task.get("inputs") or []
        if isinstance(entry, dict)
        and entry.get("required", True)
        and entry.get("key") not in profile
        and not entry.get("generator")
    ]
    if missing:
        return await refuse("missing_input_binding", missing=missing)
    prerequisites = [
        entry for entry in task.get("prerequisites") or []
        if isinstance(entry, dict)
    ]
    if any(entry.get("kind") == "authenticated" for entry in prerequisites):
        if auth_snapshot is None:
            return await refuse("prerequisite_unavailable")
    for entry in prerequisites:
        if entry.get("kind") == "skill_active":
            wanted = entry.get("skill_name")
            active_names = set()
            for skill in await repository.list_skills_for_scope(
                workspace_id=app_map.workspace_id,
                application_id=app_map.application_id,
                target_id=app_map.target_id,
            ):
                versions = await repository.list_versions_for_skill(skill.id)
                if any(
                    v.lifecycle_status == "active" for v in versions
                ):
                    active_names.add(skill.name)
            if wanted not in active_names:
                return await refuse("prerequisite_unavailable")

    from markettwin_shared.app_map_common import canonical_url

    base_page = next(
        (p for p in pages if canonical_url(p.canonical_url) == canonical_url(app_map.base_url)),
        None,
    )
    start_state_id = None
    if base_page is not None:
        for state in states:
            if (
                state.map_page_id == base_page.id
                and state.state_key == "default"
            ):
                start_state_id = state.state_id
                break
    executor = TaskReplayExecutor(
        controller,
        app_map=app_map,
        profile=profile,
        login_definition=login_definition,
        network_policy=network_policy,
        fixture_action_rules=fixture_action_rules,
        auth_snapshot=auth_snapshot,
    )
    result = await verify_skill(
        repository=repository,
        app_map=app_map,
        skill_version=skill_version,
        definition=definition,
        executor=executor,
        start_state_id=start_state_id,
        on_failure="leave_draft",
        allow_heal=False,
    )
    if any(executor.generated_log):
        await record_usage(
            repository,
            skill_version,
            kind="verification_replay",
            result=(
                "passed"
                if result.lifecycle_status == "replay_verified"
                else "failed"
            ),
            payload={"generated": executor.generated_log},
        )
    return {"status": result.lifecycle_status, "reason": None, "verify": result}
