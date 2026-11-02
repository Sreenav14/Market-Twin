"""Live discovery/approval/Kafka/execution/evaluation benchmark on the retained fixture.

The local API test client acts as the seeded workspace owner. Browser execution
and model calls use production implementations. No scripted agent driver is used.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from dotenv import load_dotenv
from markettwin_control_api.config import Settings, get_settings
from markettwin_control_api.database import DatabaseRuntime
from markettwin_control_api.main import create_app
from markettwin_control_api.services import OutboxRelay, run_outbox_relay
from markettwin_database.models import (
    AgentExecution,
    ApplicationTarget,
    Artifact,
    ExecutionStep,
    HumanActionRequest,
    PersonaJourney,
    Report,
    RunEvent,
    TestRun,
)
from markettwin_evaluation_worker.worker import main as evaluation_main
from markettwin_execution_orchestrator.worker import main as execution_main
from markettwin_shared.action_approval import SensitiveActionRule
from markettwin_shared.discovery_contract import DiscoveryMap, TestContract
from markettwin_shared.messaging import KafkaProducer
from sqlalchemy import select, text

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/v1_benchmark/index.html"
STALL_EVENT_SILENCE_SECONDS = 300
MAX_STALL_DIAGNOSTICS = 3
MAX_DIAGNOSTIC_TASKS = 16
MAX_DIAGNOSTIC_FRAMES = 12
RUN_PREFLIGHT_TIMEOUT_SECONDS = 60
RUN_PREFLIGHT_POLL_SECONDS = 2
FIXTURE_ACTION_RULES = (
    ("form_submit", "button", "Continue to next step", "fixture-continue"),
    ("form_submit", "button", "Check contact address", "fixture-contact"),
    ("save", "button", "Save display name", "fixture-display"),
)
APPROVED_ACTION_SUMMARIES = {
    "fixture-continue": "Submit a form on the authorized target",
    "fixture-contact": "Submit a form on the authorized target",
    "fixture-display": "Save a change on the authorized target",
}


def normalized_fixture_rules(raw_rules: object) -> list[dict[str, object]]:
    """Validate saved policy and include model defaults in its canonical representation."""
    if not isinstance(raw_rules, list):
        raise ValueError("Source run lacks the exact previously authorized fixture policy.")
    try:
        rules = [SensitiveActionRule.model_validate(rule) for rule in raw_rules]
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Source run lacks the exact previously authorized fixture policy."
        ) from error
    return [rule.model_dump(mode="json", exclude_none=True) for rule in rules]


def response_payload(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return {"body": response.text[:1000]}


class OpaqueActionApprovalRequired(RuntimeError):
    """A fixture run requested an action that requires explicit human takeover."""

    def __init__(self, approvals: list[dict[str, object]]) -> None:
        self.approvals = approvals
        super().__init__("Opaque action approval requires human browser takeover.")


class RunPreflightFailed(RuntimeError):
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"Run preflight did not become ready (HTTP {status_code}).")


async def wait_for_run_preflight(
    client: httpx.AsyncClient, run_id: UUID, *, timeout_seconds: float = (
        RUN_PREFLIGHT_TIMEOUT_SECONDS
    ), poll_interval_seconds: float = RUN_PREFLIGHT_POLL_SECONDS,
) -> dict[str, object]:
    """Wait for all existing readiness checks before asking to freeze and dispatch."""
    path = f"/api/v1/test-runs/{run_id}/preflight"
    deadline = time.monotonic() + timeout_seconds
    last_status = 0
    last_payload: object = None
    while True:
        response = await client.get(path)
        last_status = response.status_code
        last_payload = response_payload(response)
        if last_status >= 400:
            raise RunPreflightFailed(last_status, last_payload)
        if isinstance(last_payload, dict) and last_payload.get("ready") is True:
            return last_payload
        if time.monotonic() >= deadline:
            raise RunPreflightFailed(last_status, last_payload)
        await asyncio.sleep(poll_interval_seconds)


class EventSilenceMonitor:
    """Bound no-progress diagnostics to one snapshot every five minutes."""

    def __init__(self, *, started_at: float | None = None) -> None:
        self.last_event_id: int | None = None
        self.last_event_at = time.monotonic() if started_at is None else started_at
        self.last_capture_at: float | None = None
        self.capture_count = 0

    def observe(self, event_id: int | None, now: float) -> None:
        if event_id != self.last_event_id:
            self.last_event_id = event_id
            self.last_event_at = now
            self.last_capture_at = None
            self.capture_count = 0

    def due(self, now: float) -> bool:
        if self.capture_count >= MAX_STALL_DIAGNOSTICS:
            return False
        if now - self.last_event_at <= STALL_EVENT_SILENCE_SECONDS:
            return False
        if (self.last_capture_at is not None
                and now - self.last_capture_at <= STALL_EVENT_SILENCE_SECONDS):
            return False
        self.last_capture_at = now
        self.capture_count += 1
        return True


def _coroutine_frame_metadata(coroutine: object) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    visited: set[int] = set()
    current = coroutine
    while current is not None and len(frames) < MAX_DIAGNOSTIC_FRAMES:
        if id(current) in visited:
            break
        visited.add(id(current))
        frame = getattr(current, "cr_frame", None) or getattr(current, "gi_frame", None)
        if frame is not None:
            frames.append({
                "function": frame.f_code.co_name,
                "file": frame.f_code.co_filename,
                "line": frame.f_lineno,
            })
        current = (getattr(current, "cr_await", None)
                   or getattr(current, "gi_yieldfrom", None))
    return frames


def _task_frame_metadata(task: asyncio.Task[object]) -> list[dict[str, object]]:
    frames = _coroutine_frame_metadata(task.get_coro())
    for frame in task.get_stack(limit=MAX_DIAGNOSTIC_FRAMES):
        item = {
            "function": frame.f_code.co_name,
            "file": frame.f_code.co_filename,
            "line": frame.f_lineno,
        }
        if item not in frames:
            frames.append(item)
    return frames[:MAX_DIAGNOSTIC_FRAMES]


def task_stack_metadata(tasks: list[asyncio.Task[object]]) -> list[dict[str, object]]:
    """Return bounded pending task/coroutine frames, never locals or source text."""
    roots = tasks[:4]
    try:
        current = asyncio.current_task()
        pending = [task for task in asyncio.all_tasks()
                   if task is not current and not task.done() and task not in roots]
    except RuntimeError:
        pending = []
    pending_frames = {task: _task_frame_metadata(task) for task in pending}
    pending.sort(key=lambda task: (
        0 if any("markettwin_" in str(frame["file"])
                 for frame in pending_frames[task]) else 1,
        tuple((str(frame["file"]), str(frame["function"]))
              for frame in pending_frames[task]),
    ))
    snapshots: list[dict[str, object]] = []
    selected = [(task, True) for task in roots]
    selected.extend((task, False) for task in pending[:max(0, MAX_DIAGNOSTIC_TASKS - len(roots))])
    for index, (task, root) in enumerate(selected):
        snapshots.append({
            "task_index": index,
            "task_name": task.get_name() if root else "pending_task",
            "done": task.done(),
            "cancelled": task.cancelled(),
            "frames": _task_frame_metadata(task) if root else pending_frames[task],
        })
    return snapshots


class FixtureHandler(BaseHTTPRequestHandler):
    good = True

    def log_message(self, *_args):
        pass

    def do_GET(self):
        source = FIXTURE.read_text(encoding="utf-8")
        if self.good:
            # The retained fixture contains only the broken variant. Supply its
            # four declared correct behaviors without editing that broken source.
            source = source.replace("<h1>Profile settings</h1>", "<h1>Billing settings</h1>")
            source += """<script>
const primary = Array.from(document.querySelectorAll('button')).find(
    button => button.textContent === 'Continue to next step');
function show(text, role) {
    const node = document.createElement('p'); node.setAttribute('role', role);
    node.textContent = text; document.body.append(node); node.scrollIntoView();
}
if (primary) { primary.disabled = false;
    primary.onclick = () => show('Next step', 'status'); }
const form = document.getElementById('validation-form');
if (form) form.addEventListener('submit', event => {
    event.preventDefault();
    if (!document.getElementById('contact-address').value)
        show('Contact address is required', 'alert');
});
const preview = document.getElementById('preview');
if (preview) preview.onclick = () => show('Preview ready', 'status');
</script>"""
        data = source.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


async def saved_evidence(factory, run_id):
    run_id = UUID(str(run_id))
    async with factory() as session:
        run = await session.get(TestRun, run_id)
        report = await session.scalar(select(Report).where(
            Report.test_run_id == run_id, Report.status == "completed",
        ))
        events = (await session.scalars(select(RunEvent).where(
            RunEvent.test_run_id == run_id,
        ))).all()
        execution_ids = tuple((await session.scalars(select(AgentExecution.id).join(
            PersonaJourney, PersonaJourney.id == AgentExecution.journey_id,
        ).where(PersonaJourney.test_run_id == run_id))).all())
        steps = (await session.scalars(select(ExecutionStep).where(
            ExecutionStep.execution_id.in_(execution_ids),
        ))).all()
        artifacts = (await session.scalars(select(Artifact).where(
            Artifact.execution_id.in_(execution_ids),
        ))).all()
        discovery = DiscoveryMap.model_validate(run.configuration_snapshot.get("discovery_map"))
        discovery_source_id = UUID(str(
            run.configuration_snapshot.get("discovery_map_source_run_id") or run_id
        ))
        discovery_step_ids = {
            step.execution_step_id for journey in discovery.journeys for step in journey.steps
        }
        source_execution_ids = tuple((await session.scalars(select(AgentExecution.id).join(
            PersonaJourney, PersonaJourney.id == AgentExecution.journey_id,
        ).where(PersonaJourney.test_run_id == discovery_source_id))).all())
        source_steps = []
        if discovery_step_ids and source_execution_ids:
            source_steps = (await session.scalars(select(ExecutionStep).where(
                ExecutionStep.execution_id.in_(source_execution_ids),
                ExecutionStep.id.in_(discovery_step_ids),
            ))).all()
        source_discovery_execution_ids = {step.execution_id for step in source_steps}
        discovery_executions = []
        if source_discovery_execution_ids:
            discovery_executions = (await session.scalars(select(AgentExecution).where(
                AgentExecution.id.in_(source_discovery_execution_ids),
            ))).all()
        plans = [e.payload for e in events if e.event_type == "contract.execution_plan"]
        discovery_event_counts = {
            event_type: sum(e.event_type == event_type for e in events)
            for event_type in ("discovery.started", "discovery.completed")
        }
        run_duration = (
            (run.completed_at - run.started_at).total_seconds()
            if run.started_at is not None and run.completed_at is not None else None
        )
        discovery_start = min(
            (item.created_at for item in discovery_executions), default=None,
        )
        discovery_end = max(
            (item.completed_at for item in discovery_executions if item.completed_at),
            default=None,
        )
        discovery_duration = (
            (discovery_end - discovery_start).total_seconds()
            if discovery_start is not None and discovery_end is not None else None
        )
        report_generation_duration = (
            (report.generated_at - run.completed_at).total_seconds()
            if (report is not None and report.generated_at is not None
                and run.completed_at is not None)
            else None
        )
        return {
            "target_id": str(run.target_id),
            "target_snapshot": run.target_snapshot,
            "run_created_at": run.created_at.isoformat(),
            "run_started_at": run.started_at.isoformat() if run.started_at else None,
            "run_completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "report_generated_at": report.generated_at.isoformat() if report else None,
            "execution_duration_seconds": run_duration,
            "database_total_seconds": (
                (report.generated_at - run.created_at).total_seconds()
                if report and report.generated_at else None
            ),
            "report_generation_seconds": report_generation_duration,
            "source_discovery_execution_duration_seconds": discovery_duration,
            "synthetic_fixture_approval_enabled": bool(
                run.synthetic_fixture_approval_enabled
            ),
            "human_action_approvals_enabled": bool(run.human_action_approvals_enabled),
            "fixture_action_policy": {
                "synthetic_fixture_approval": bool(run.synthetic_fixture_approval_enabled),
                "human_action_approvals": bool(run.human_action_approvals_enabled),
                "sensitive_action_rules": normalized_fixture_rules(
                    run.configuration_snapshot.get("sensitive_action_rules", [])
                ),
            },
            "frozen_contract": run.configuration_snapshot.get("frozen_contract"),
            "discovery_map": run.configuration_snapshot.get("discovery_map"),
            "frozen_contract_source_run_id": run.configuration_snapshot.get(
                "frozen_contract_source_run_id"
            ),
            "frozen_contract_source_hash": run.configuration_snapshot.get(
                "frozen_contract_source_hash"
            ),
            "discovery_map_source_run_id": run.configuration_snapshot.get(
                "discovery_map_source_run_id"
            ),
            "source_discovery_step_source_run_id": str(discovery_source_id),
            "discovery_event_counts": discovery_event_counts,
            "source_discovery_steps": [{
                "id": s.id, "execution_id": str(s.execution_id),
                "step_number": s.step_number, "action_type": s.action_type,
                "status": s.status, "observation_summary": s.observation_summary,
            } for s in source_steps],
            "execution_plan": plans[0] if len(plans) == 1 else None,
            "case_results": [{"execution_id": str(e.execution_id),
                              "journey_id": str(e.journey_id), **e.payload}
                             for e in events if e.event_type == "contract.case.completed"],
            "replay_links": [{"execution_id": str(e.execution_id),
                              "journey_id": str(e.journey_id), **e.payload}
                             for e in events if e.event_type == "test_case.replay"],
            "execution_steps": [{"id": s.id, "execution_id": str(s.execution_id),
                                 "step_number": s.step_number, "action_type": s.action_type,
                                 "status": s.status, "observation_summary": s.observation_summary}
                                for s in steps],
            "artifacts": [{"id": str(a.id), "execution_id": str(a.execution_id),
                           "step_id": a.step_id, "artifact_type": a.artifact_type,
                           "metadata_json": a.metadata_json} for a in artifacts],
        }


async def source_baseline(factory, run_id):
    """Load and validate the completed discovery run reused by this campaign."""
    run_id = UUID(str(run_id))
    async with factory() as session:
        run = await session.get(TestRun, run_id)
        if run is None or run.status != "completed":
            raise ValueError("Frozen-contract source must be a completed run.")
        if run.configuration_snapshot.get("execution_mode") != "discovery_contract_v1":
            raise ValueError("Frozen-contract source must use discovery_contract_v1.")
        try:
            contract = TestContract.model_validate(
                run.configuration_snapshot.get("frozen_contract")
            )
            discovery = DiscoveryMap.model_validate(
                run.configuration_snapshot.get("discovery_map")
            )
        except ValueError as error:
            raise ValueError(
                "Frozen-contract source has invalid saved discovery or contract."
            ) from error
        content_hash = contract.content_hash()
        if (
            contract.test_run_id != run_id or contract.status != "frozen"
            or contract.approved_by_user_id != run.created_by_user_id
            or contract.approved_at is None
            or run.configuration_snapshot.get("frozen_contract_hash") != content_hash
        ):
            raise ValueError("Frozen-contract source failed approval or hash validation.")
        target = await session.get(ApplicationTarget, run.target_id)
        report = await session.scalar(select(Report).where(
            Report.test_run_id == run_id, Report.status == "completed",
        ))
        rules = normalized_fixture_rules(
            run.configuration_snapshot.get("sensitive_action_rules", [])
        )
        expected_rules = normalized_fixture_rules([{
            "category": category,
            "role": role,
            "name": name,
            "resource_reference": resource,
            "test_data_reset_confirmed": True,
        } for category, role, name, resource in FIXTURE_ACTION_RULES])
        if rules != expected_rules or not run.synthetic_fixture_approval_enabled:
            raise ValueError("Source run lacks the exact previously authorized fixture policy.")
        if target is None or report is None:
            raise ValueError("Frozen-contract source target or completed report is missing.")
        target_url = urlsplit(target.base_url)
        if target_url.hostname not in {"localhost", "127.0.0.1"} or not target_url.port:
            raise ValueError("Frozen-contract source target must be loopback with a fixed port.")
        if discovery.target_origin != f"{target_url.scheme}://{target_url.netloc}":
            raise ValueError("Frozen-contract source discovery does not match its target origin.")
        return {
            "run_id": str(run_id),
            "workspace_id": str(run.workspace_id),
            "application_id": str(run.application_id),
            "target_id": str(run.target_id),
            "target_base_url": target.base_url,
            "target_host": target_url.hostname,
            "target_port": target_url.port,
            "contract": contract,
            "discovery": discovery,
            "contract_hash": content_hash,
            "report": report.report_payload,
            "source_synthetic_fixture_approval_enabled": bool(
                run.synthetic_fixture_approval_enabled
            ),
            "source_human_action_approvals_enabled": bool(run.human_action_approvals_enabled),
            "sensitive_action_rules": rules,
            "testing_depth": run.configuration_snapshot.get("testing_depth", "medium"),
            "study_brief": run.configuration_snapshot.get("study_brief", ""),
            "created_by_user_id": str(run.created_by_user_id),
            "full_run_total_seconds": (
                (report.generated_at - run.created_at).total_seconds()
                if report.generated_at else None
            ),
        }


async def wait_for(
    factory, run_id, desired, tasks, deadline_seconds=1200, approval_client=None,
    on_stall: Callable[[dict[str, object]], Awaitable[None]] | None = None,
    approved_action_host: str | None = None,
):
    run_id = UUID(str(run_id))
    silence = EventSilenceMonitor()
    async with asyncio.timeout(deadline_seconds):
        while True:
            for task in tasks:
                if task.done():
                    task.result()
                    raise RuntimeError("A required benchmark service stopped.")
            async with factory() as policy_session:
                blocked = await policy_session.scalars(select(ExecutionStep).where(
                    ExecutionStep.execution_id.in_(select(AgentExecution.id).join(
                        PersonaJourney, PersonaJourney.id == AgentExecution.journey_id,
                    ).where(PersonaJourney.test_run_id == run_id)),
                    ExecutionStep.status == "policy_blocked",
                ).order_by(ExecutionStep.step_number))
                blocked_step = blocked.first()
                if blocked_step is not None:
                    raise OpaqueActionApprovalRequired([{
                        "kind": "policy_blocked_action",
                        "step_id": blocked_step.id,
                        "step_number": blocked_step.step_number,
                        "action_summary": blocked_step.action_summary,
                        "reason": (blocked_step.observation_summary or "Policy blocked.")[:300],
                    }])
                takeover = await policy_session.scalar(
                    select(HumanActionRequest).join(
                        AgentExecution, AgentExecution.id == HumanActionRequest.execution_id,
                    ).join(PersonaJourney, PersonaJourney.id == AgentExecution.journey_id).where(
                        PersonaJourney.test_run_id == run_id,
                        HumanActionRequest.status.in_(("pending", "leased")),
                    ).order_by(HumanActionRequest.created_at.desc()).limit(1)
                )
                if takeover is not None:
                    action = None
                    if takeover.requested_by_step_id is not None:
                        action = await policy_session.get(
                            ExecutionStep, takeover.requested_by_step_id,
                        )
                    raise OpaqueActionApprovalRequired([{
                        "kind": "human_browser_takeover",
                        "request_id": str(takeover.id),
                        "request_type": takeover.request_type,
                        "action_summary": action.action_summary if action else None,
                        "instructions": takeover.instructions,
                    }])
            if approval_client is not None:
                response = await approval_client.get(f"/api/v1/test-runs/{run_id}/action-approvals")
                response.raise_for_status()
                pending = [approval for approval in response.json()
                           if approval["status"] == "pending"]
                for approval in pending:
                    summary = str(approval.get("action_summary", ""))
                    allowed = (
                        approval.get("environment") == "local"
                        and approved_action_host is not None
                        and any(summary == (
                            f"{label} ({approved_action_host}; {resource})"
                        ) for resource, label in APPROVED_ACTION_SUMMARIES.items())
                    )
                    if not allowed:
                        raise OpaqueActionApprovalRequired([{
                            "kind": "undeclared_or_opaque_approval",
                            "approval_id": approval.get("id"),
                            "action_summary": summary,
                            "environment": approval.get("environment"),
                        }])
                    decision = await approval_client.post(
                        f"/api/v1/action-approvals/{approval['id']}/decision",
                        json={"approved": True},
                    )
                    decision.raise_for_status()
            async with factory() as session:
                run = await session.get(TestRun, run_id)
                latest_event_id = None
                if on_stall is not None:
                    latest_event_id = await session.scalar(
                        select(RunEvent.id).where(
                            RunEvent.test_run_id == run_id,
                        ).order_by(RunEvent.id.desc()).limit(1)
                    )
                if run.status in {"failed", "cancelled"}:
                    raise RuntimeError("Fixture run failed before its required checkpoint.")
                if run.configuration_snapshot.get("discovery_stage") == desired:
                    return
                if desired == "report":
                    report = await session.scalar(select(Report).where(
                        Report.test_run_id == run_id, Report.status == "completed",
                    ))
                    if report is not None:
                        return report.report_payload
            if on_stall is not None:
                now = time.monotonic()
                silence.observe(latest_event_id, now)
                if silence.due(now):
                    await on_stall({
                        "kind": "no_run_events",
                        "silence_seconds": int(now - silence.last_event_at),
                        "last_event_id": silence.last_event_id,
                        "tasks": task_stack_metadata(tasks),
                    })
            await asyncio.sleep(2)


async def run(output: Path, source_run_id: UUID, local_kafka: bool):
    load_dotenv()
    if local_kafka:
        os.environ["KAFKA_BOOTSTRAP_SERVERS"] = "127.0.0.1:9092"
        os.environ["KAFKA_SECURITY_PROTOCOL"] = "PLAINTEXT"
        for key in (
            "KAFKA_USERNAME", "KAFKA_PASSWORD", "KAFKA_SASL_MECHANISM", "KAFKA_SSL_CA_FILE",
        ):
            os.environ.pop(key, None)
        # Settings reads .env too; explicitly clear credentials for this process profile.
        os.environ["KAFKA_USERNAME"] = ""
    os.environ["OUTBOX_RELAY_ENABLED"] = "true"
    get_settings.cache_clear()
    settings = Settings()
    loopback = {"localhost", "127.0.0.1", "::1"}
    if (settings.postgres_host not in loopback
            or urlsplit(settings.s3_endpoint_url).hostname not in loopback):
        raise ValueError("Live fixture benchmarks require loopback database and artifact storage.")
    runtime = DatabaseRuntime(settings)
    engine = runtime.engine
    factory = runtime.session_factory
    source = await source_baseline(factory, source_run_id)
    owner = UUID(source["created_by_user_id"])
    workspace = source["workspace_id"]
    application = source["application_id"]
    target_id = source["target_id"]
    try:
        server = ThreadingHTTPServer(
            (str(source["target_host"]), int(source["target_port"])), FixtureHandler,
        )
    except OSError as error:
        raise RuntimeError(
            "Frozen-contract source target port is unavailable; refusing to change its origin."
        ) from error
    threading.Thread(target=server.serve_forever, daemon=True).start()
    tasks = []
    source_contract = source["contract"]
    source_hash = str(source["contract_hash"])
    campaign = {
        "protocol": "single_frozen_contract_replay_v1",
        "source_run_id": str(source_run_id),
        "source_contract_id": str(source_contract.contract_id),
        "source_contract_version": source_contract.version,
        "source_contract_hash": source_hash,
        "discovery_count": 1,
        "reused_target_id": target_id,
        "automatic_opaque_action_approval": False,
        "source_fixture_action_policy": {
            "synthetic_fixture_approval": bool(
                source["source_synthetic_fixture_approval_enabled"]
            ),
            "human_action_approvals": bool(source["source_human_action_approvals_enabled"]),
            "sensitive_action_rules": source["sensitive_action_rules"],
        },
        "approved_fixture_action_rules": source["sensitive_action_rules"],
            "duration_definitions": {
            "replay_total_seconds": (
                "Wall time from the replay create-run request to report availability; "
                "excludes the source discovery run."
            ),
            "execution_duration_seconds": "Persisted run started_at to completed_at.",
            "report_generation_seconds": "Persisted run completed_at to report generated_at.",
            "comparison_to_full_run": (
                "For each replay, add the measured one-time source discovery execution "
                "duration to replay_total_seconds to estimate a full-run elapsed total. "
                "The source full_run_total_seconds includes its discovery, execution, and report."
            ),
        },
        "source_used_synthetic_fixture_approval": bool(
            source["source_synthetic_fixture_approval_enabled"]
        ),
        "source_action_policy_note": (
            "Replay runs preserve the source's three exact declared fixture rules. "
            "Undeclared approvals and policy-blocked actions stop the run."
        ),
    }
    outcomes = []
    output.parent.mkdir(parents=True, exist_ok=True)

    def write_checkpoint():
        output.write_text(json.dumps({
            "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            "mode": "discovery_contract_v1",
            "campaign": campaign,
            "runs": outcomes,
        }, indent=2), encoding="utf-8")

    try:
        async with factory() as session:
            active = await session.scalar(text(
                "SELECT count(*) FROM testing.test_runs WHERE status IN "
                "('queued', 'planning', 'running', 'awaiting_human')"
            ))
            if active:
                raise RuntimeError("Benchmark requires an idle local run queue.")
            source_run = await session.get(TestRun, source_run_id)
            source_report = await session.scalar(select(Report).where(
                Report.test_run_id == source_run_id, Report.status == "completed",
            ))
            if source_run is None or source_report is None:
                raise RuntimeError("Completed frozen-contract source disappeared before replay.")
            source_outcome = {
                "run_id": str(source_run_id), "broken": True, "repeat": 1,
                "operational_run_number": 1, "campaign_run_number": 1,
                "status": "reported", "report": source_report.report_payload,
                "report_integrity_passed": False,
                "manual_interventions": 0,
                "full_run_total_seconds": source["full_run_total_seconds"],
                "campaign_source_run_id": str(source_run_id),
                "campaign_source_contract_hash": source_hash,
                "reused_target_id": target_id,
                **await saved_evidence(factory, source_run_id),
                "frozen_contract_source_run_id": str(source_run_id),
                "frozen_contract_source_hash": source_hash,
                "discovery_map_source_run_id": str(source_run_id),
            }
            campaign["discovery_count"] = source_outcome["discovery_event_counts"][
                "discovery.completed"
            ]
            campaign["source_full_run_total_seconds"] = source_outcome[
                "full_run_total_seconds"
            ]
            campaign["source_discovery_execution_duration_seconds"] = source_outcome[
                "source_discovery_execution_duration_seconds"
            ]
            campaign["source_execution_duration_seconds"] = source_outcome[
                "execution_duration_seconds"
            ]
            campaign["source_report_generation_seconds"] = source_outcome[
                "report_generation_seconds"
            ]
            campaign["included_operational_run_numbers"] = [1, 4, 5, 6, 7, 8]
            campaign["excluded_operational_runs"] = [
                {
                    "operational_run_number": 2,
                    "run_id": "44674ee0-9e8f-4af3-bbf9-cdffeb35120e",
                    "classification": "discovery_reliability_protocol_deviation",
                    "counts_as_replay": False,
                },
                {
                    "operational_run_number": 3,
                    "run_id": "5e39c03e-8a6d-4d9a-aa9b-012f7e82e74e",
                    "classification": "interrupted_before_report",
                    "counts_as_replay": False,
                },
            ]
            outcomes.append(source_outcome)
        app = create_app()
        app.state.database = runtime
        producer = KafkaProducer(settings.kafka_producer_settings)
        tasks = [asyncio.create_task(execution_main(), name="execution_worker"),
                 asyncio.create_task(evaluation_main(), name="evaluation_worker"),
                 asyncio.create_task(run_outbox_relay(
                     relay=OutboxRelay(session_factory=factory, producer=producer),
                     producer=producer,
                 ), name="outbox_relay")]
        async with AsyncExitStack() as stack:
            for module in (
                "test_run", "test_contracts", "human_actions", "test_run_results", "run_readiness",
            ):
                stack.enter_context(patch(
                    f"markettwin_control_api.api.{module}.get_authenticated_user_id",
                    AsyncMock(return_value=owner),
                ))
            client = await stack.enter_async_context(httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test",
                headers={"Origin": settings.web_origin, "x-markettwin-request": "1"},
            ))
            source_results = await client.get(f"/api/v1/test-runs/{source_run_id}/results")
            source_results.raise_for_status()
            source_outcome["report_integrity_passed"] = True
            await asyncio.to_thread(write_checkpoint)
            variants = (
                (True, 2, 4, 2), (True, 3, 5, 3), (False, 1, 6, 4),
                (False, 2, 7, 5), (False, 3, 8, 6),
            )
            for broken, repeat, operational_number, campaign_number in variants:
                run_payload = {
                    "target_id": target_id,
                    "testing_depth": source["testing_depth"],
                    "execution_mode": "discovery_contract_v1",
                    "runtime_human_assistance": False,
                    "synthetic_fixture_approval": source[
                        "source_synthetic_fixture_approval_enabled"
                    ],
                    "human_action_approvals": source[
                        "source_human_action_approvals_enabled"
                    ],
                    "sensitive_action_rules": source["sensitive_action_rules"],
                    "frozen_contract_source_run_id": str(source_run_id),
                    "study_brief": source["study_brief"],
                }
                created_at = time.time()
                response = await client.post(
                    f"/api/v1/applications/{application}/test-runs", json=run_payload,
                )
                response.raise_for_status()
                created = response.json()
                run_id = created["id"]
                run_record = {
                    "run_id": run_id, "broken": broken, "repeat": repeat,
                    "operational_run_number": operational_number,
                    "campaign_run_number": campaign_number,
                    "status": "contract_reused", "campaign_source_run_id": str(source_run_id),
                    "campaign_source_contract_hash": source_hash,
                    "reused_target_id": target_id,
                    "frozen_contract_source_run_id": str(source_run_id),
                    "frozen_contract_source_hash": source_hash,
                    "manual_interventions": 0,
                    "replay_created_at": created_at,
                }
                outcomes.append(run_record)
                await asyncio.to_thread(write_checkpoint)
                snapshot = created.get("configuration_snapshot", {})
                copied_contract = TestContract.model_validate(snapshot.get("test_contract"))
                copied_discovery = DiscoveryMap.model_validate(snapshot.get("discovery_map"))
                if (
                    copied_contract.contract_id != source_contract.contract_id
                    or copied_contract.version != source_contract.version
                    or copied_contract.status != "approved"
                    or copied_contract.content_hash() != source_hash
                    or copied_contract.journeys != source_contract.journeys
                    or copied_discovery != source["discovery"]
                    or snapshot.get("frozen_contract_source_run_id") != str(source_run_id)
                    or snapshot.get("frozen_contract_source_hash") != source_hash
                ):
                    raise ValueError("Replay run did not copy the exact source contract and map.")
                contract_path = (
                    f"/api/v1/workspaces/{workspace}/test-runs/{run_id}/contract"
                )
                response = await client.get(contract_path)
                response.raise_for_status()
                fetched_contract = TestContract.model_validate(response.json())
                if fetched_contract.content_hash() != source_hash:
                    raise ValueError("Replay contract changed before freeze.")
                try:
                    preflight = await wait_for_run_preflight(client, UUID(run_id))
                except RunPreflightFailed as error:
                    run_record.update({
                        "status": "blocked_preflight_not_ready",
                        "preflight_status_code": error.status_code,
                        "preflight_response": error.payload,
                    })
                    await asyncio.to_thread(write_checkpoint)
                    print(json.dumps({
                        "run_id": run_id, "phase": "blocked_preflight_not_ready",
                        "status_code": error.status_code,
                        "preflight": error.payload,
                    }), flush=True)
                    break
                run_record["preflight_status_code"] = 200
                run_record["preflight_response"] = preflight
                FixtureHandler.good = not broken
                frozen = await client.post(contract_path + "/start", json={})
                if frozen.status_code >= 400:
                    start_error = response_payload(frozen)
                    run_record.update({
                        "status": "contract_start_rejected",
                        "contract_start_status_code": frozen.status_code,
                        "contract_start_response": start_error,
                    })
                    await asyncio.to_thread(write_checkpoint)
                    print(json.dumps({
                        "run_id": run_id, "phase": "contract_start_rejected",
                        "status_code": frozen.status_code, "response": start_error,
                    }), flush=True)
                    break
                frozen.raise_for_status()
                frozen_contract = TestContract.model_validate(frozen.json())
                if (
                    frozen_contract.status != "frozen"
                    or frozen_contract.content_hash() != source_hash
                    or frozen_contract.journeys != source_contract.journeys
                ):
                    raise ValueError("Replay start did not preserve the frozen source oracle.")
                run_record["status"] = "executing"
                await asyncio.to_thread(write_checkpoint)
                print(json.dumps({"run_id": run_id, "variant": "broken" if broken else "good",
                                  "repeat": repeat, "phase": "executing_reused_contract"}),
                      flush=True)

                async def record_stall_diagnostic(
                    diagnostic: dict[str, object], run_record=run_record,
                ) -> None:
                    run_record.setdefault("stall_diagnostics", []).append(diagnostic)
                    await asyncio.to_thread(write_checkpoint)

                try:
                    payload = await wait_for(
                        factory, run_id, "report", tasks, deadline_seconds=7200,
                        approval_client=client, on_stall=record_stall_diagnostic,
                        approved_action_host=str(source["target_host"]),
                    )
                except OpaqueActionApprovalRequired as error:
                    run_record.update({
                        "status": "blocked_opaque_action",
                        "blocked_actions": error.approvals,
                        "protocol_deviation": (
                            "Stopped at pending action approval; no automatic decision or "
                            "browser takeover was attempted."
                        ),
                    })
                    await asyncio.to_thread(write_checkpoint)
                    print(json.dumps({
                        "run_id": run_id, "phase": "blocked_opaque_action",
                        "actions": error.approvals,
                    }), flush=True)
                    break
                report_api = await client.get(f"/api/v1/test-runs/{run_id}/results")
                report_api.raise_for_status()
                run_record.update({
                    "status": "reported", "report": payload, "report_integrity_passed": True,
                    "replay_total_seconds": time.time() - run_record["replay_created_at"],
                    **await saved_evidence(factory, run_id),
                })
                run_record["discovery_adjusted_full_run_seconds"] = (
                    run_record["replay_total_seconds"]
                    + float(source_outcome["source_discovery_execution_duration_seconds"] or 0)
                )
                await asyncio.to_thread(write_checkpoint)
                print(json.dumps({"run_id": run_id, "phase": "reported"}), flush=True)
    finally:
        await asyncio.to_thread(write_checkpoint)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        server.shutdown()
        server.server_close()
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-development", action="store_true", required=True)
    parser.add_argument("--frozen-contract-source-run-id", type=UUID, required=True)
    parser.add_argument("--local-kafka", action="store_true")
    parser.add_argument("--output", type=Path, default=Path(".local/contract-benchmark.json"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.CRITICAL)
    asyncio.run(run(args.output, args.frozen_contract_source_run_id, args.local_kafka))
