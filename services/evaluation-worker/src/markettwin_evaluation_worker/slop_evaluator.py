"""Slop evaluation (U-P6-05): three family numbers, no verdict.

Reads the executor's slop.state.result verdict rows and aggregates
them with the shared three-family aggregate. The payload carries the
slop percentage (or its suppression headline), the defect counts,
and the effort family's honest empty state — three currencies,
never blended, and no verdict key: readiness comes only from
Explore & Test.
"""

from uuid import UUID

from markettwin_database.models import RunEvent
from markettwin_shared.slop_aggregate import SLOP_EVALUATION_CONTRACT_VERSION, aggregate_run
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from markettwin_evaluation_worker.activity_checkpoints import load_activity_checkpoints
from markettwin_evaluation_worker.errors import InvalidEvaluationInput
from markettwin_evaluation_worker.persistence.report_repository import (
    ReportRepository,
)


async def evaluate_slop_run(
    *, test_run_id: UUID, session: AsyncSession, require_contract: bool = False,
) -> tuple[tuple[UUID, ...], UUID]:
    result = await session.execute(
        select(RunEvent)
        .where(
            RunEvent.test_run_id == test_run_id,
            RunEvent.event_type == "slop.state.result",
        )
        .order_by(RunEvent.occurred_at, RunEvent.id)
    )
    records = [event.payload for event in result.scalars()]
    if not records:
        raise InvalidEvaluationInput("slop_states_missing", "No final Look states were published.")
    collection = await session.scalar(select(RunEvent).where(
        RunEvent.test_run_id == test_run_id, RunEvent.event_type == "run.collection",
    ).order_by(RunEvent.id.desc()).limit(1))
    coverage = collection.payload if collection is not None else None
    if require_contract or (coverage is not None and "evaluation_contract" in coverage):
        contract = coverage.get("evaluation_contract") if coverage is not None else None
        if coverage is None or not isinstance(contract, dict):
            raise InvalidEvaluationInput("slop_contract_missing", "Look completion contract is missing.")
        if (
            type(contract.get("version")) is not int
            or contract["version"] != SLOP_EVALUATION_CONTRACT_VERSION
        ):
            raise InvalidEvaluationInput("slop_contract_version", "Unsupported Look completion contract.")
        if type(contract.get("expected_states")) is not int or contract["expected_states"] != len(records):
            raise InvalidEvaluationInput("slop_state_count_mismatch", "Look state count disagrees with execution.")
        for record in records:
            if not isinstance(record.get("url"), str) or not all(
                isinstance(record.get(key), list)
                and all(isinstance(row, dict) for row in record[key])
                for key in ("elements", "page_signals", "js_errors")
            ):
                raise InvalidEvaluationInput("slop_state_invalid", "Look state has invalid evidence fields.")
        measured = [record for record in records if not any(
            signal.get("rule_id") == "UI_STATE_UNASSESSED" for signal in record["page_signals"]
        )]
        pages = {record["url"] for record in measured}
        unverified = {record["url"] for record in records} - pages
        pending = coverage.get("pending_urls")
        if (
            not pages
            or coverage.get("states_recorded") != len(measured)
            or coverage.get("pages_recorded") != len(pages)
            or coverage.get("pages_unverified") != len(unverified)
            or not isinstance(pending, list)
            or coverage.get("pages_pending") != len(pending)
        ):
            raise InvalidEvaluationInput("slop_coverage_mismatch", "Look coverage disagrees with final states.")
    states = [
        {
            "url": record.get("url"),
            "viewport": record.get("viewport"),
            "interaction_path": record.get("interaction_path"),
            "screenshot_path": record.get("screenshot_path"),
            "screenshot_artifact_id": record.get("screenshot_artifact_id"),
            "measurement_evidence": record.get("measurement_evidence"),
            "catalogue_version": record.get("catalogue_version"),
            "elements": record.get("elements", []),
            "page_signals": record.get("page_signals", []),
            "js_errors": record.get("js_errors", []),
            **{key: record[key] for key in ("title", "lane_id", "policy_code", "failure_site")
               if key in record},
            **({"tier_context": record["tier_context"]}
               if isinstance(record.get("tier_context"), dict) else {}),
        }
        for record in records
    ]
    families = aggregate_run(states)
    families["pages_inspected"] = (
        collection.payload["pages_recorded"]
        if collection is not None and isinstance(collection.payload.get("pages_recorded"), int)
        else len({state["url"] for state in states if state["url"] and not any(
            signal.get("rule_id") == "UI_STATE_UNASSESSED" for signal in state["page_signals"]
        )})
    )
    slop = families["slop"]
    defects = families["defects"]
    summary = (
        f"Checked the look of {families['pages_inspected']} page(s): "
        f"slop {slop['headline']} from {slop['judged']} judged element(s) "
        f"({slop['severe']} severe, {slop['minor']} minor); "
        f"{defects['serious']} serious and {defects['minor']} minor "
        "JavaScript/defect signal(s). These numbers describe the look "
        "and the code health; they do not change any verdict."
    )
    checkpoints = await load_activity_checkpoints(test_run_id=test_run_id, session=session)
    report_id = await ReportRepository(session).create_completed_report(
        test_run_id=test_run_id,
        executive_summary=summary,
        report_payload={
            "run_kind": "slop",
            "families": families,
            "coverage": coverage,
            "states": states,
            **({"activity_checkpoints": checkpoints} if checkpoints else {}),
        },
    )
    return (), report_id
