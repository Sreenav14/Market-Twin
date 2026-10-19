"""Run the opt-in feature tester against an existing, actively authorized target."""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from dotenv import load_dotenv
from markettwin_control_api.knowledge.repository import IngestionRepository
from markettwin_database import create_database_engine, create_session_factory
from markettwin_database.models import (
    ApplicationTarget,
    Report,
    TargetAllowedOrigin,
    TargetAuthorization,
    TestRun,
)
from markettwin_evaluation_worker.worker import process_run
from markettwin_execution_orchestrator.workflow.deep_run import default_scope
from markettwin_execution_orchestrator.workflow.run_executor import execute_markettwin_run
from markettwin_execution_orchestrator.workflow.run_request import build_run_request
from markettwin_execution_orchestrator.workflow.test_case_planner import (
    DeepFeaturePlanningRequest,
    select_feature_cases,
)
from markettwin_shared.feature_plan import (
    CaseAction,
    ExpectedAssertion,
    FeatureCaseCandidates,
    SemanticTarget,
    TestCaseSpec,
)
from sqlalchemy import select
from sqlalchemy.engine import URL


async def run(
    target_id: UUID, goal: str, output: Path, public_navigation_only: bool = False
) -> None:
    load_dotenv(override=True)
    if os.environ.get("POSTGRES_HOST") not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Diagnostic requires the existing local database.")
    engine = create_database_engine(
        URL.create(
            "postgresql+asyncpg",
            username=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            host=os.environ["POSTGRES_HOST"],
            port=int(os.environ["POSTGRES_PORT"]),
            database=os.environ["POSTGRES_DB"],
        ).render_as_string(hide_password=False)
    )
    try:
        async with create_session_factory(engine)() as session:
            target = await session.get(ApplicationTarget, target_id)
            authorization = await session.scalar(
                select(TargetAuthorization)
                .where(
                    TargetAuthorization.target_id == target_id,
                    TargetAuthorization.status == "authorized",
                    TargetAuthorization.revoked_at.is_(None),
                )
                .order_by(TargetAuthorization.created_at.desc())
                .limit(1)
            )
            previous = await session.scalar(
                select(TestRun)
                .where(
                    TestRun.target_id == target_id,
                )
                .order_by(TestRun.created_at.desc())
                .limit(1)
            )
            if (
                target is None
                or target.status != "active"
                or authorization is None
                or previous is None
                or (
                    authorization.expires_at is not None
                    and authorization.expires_at <= datetime.now(UTC)
                )
            ):
                raise ValueError(
                    "An existing active target, authorization and workspace are required."
                )
            origins = (
                await session.scalars(
                    select(TargetAllowedOrigin).where(
                        TargetAllowedOrigin.target_id == target_id,
                    )
                )
            ).all()
            configuration: dict[str, object] = {
                "study_brief": goal,
                "execution_mode": "deep_feature_v1",
                "authorization_id_at_creation": str(authorization.id),
            }
            approved: list[dict[str, object]] = []
            selected_knowledge = cast(
                list[dict[str, object]], previous.configuration_snapshot.get("knowledge", [])
            )
            for selected in selected_knowledge:
                record = await IngestionRepository(session).get(
                    previous.workspace_id,
                    UUID(str(selected["id"])),
                    application_id=target.application_id,
                )
                if record is not None and record.version.status == "approved":
                    approved.append(
                        {
                            "id": str(record.entry.id),
                            "name": record.blueprint.name,
                            "application_knowledge": record.entry.preview["application_knowledge"],
                        }
                    )
            configuration["knowledge"] = approved
            run_id = uuid4()
            test_run = TestRun(
                id=run_id,
                workspace_id=previous.workspace_id,
                application_id=target.application_id,
                target_id=target_id,
                created_by_user_id=previous.created_by_user_id,
                status="draft",
                target_snapshot={
                    "base_url": target.base_url,
                    "name": target.name,
                    "requires_auth": target.requires_auth,
                    "allowed_origins": [
                        {
                            "scheme": origin.scheme,
                            "hostname": origin.hostname,
                            "port": origin.port,
                            "include_subdomains": origin.include_subdomains,
                        }
                        for origin in origins
                    ],
                },
                configuration_snapshot=configuration,
            )
            session.add(test_run)
            if public_navigation_only:
                if target.base_url != "https://supermemory.ai/product/":
                    raise ValueError(
                        'The frozen public checks apply only to the inspected '
                        'Supermemory product page.'
                    )
                scope = default_scope(build_run_request(test_run))
                cases = []
                for name, destination in (
                    ("Home", "https://supermemory.ai/"),
                    ("Blog", "https://supermemory.ai/blog"),
                    ("Changelog", "https://supermemory.ai/changelog"),
                    ("Pricing", "https://supermemory.ai/pricing"),
                    ("Docs (external)", "https://supermemory.ai/docs"),
                    ("Human", "https://supermemory.ai/product/"),
                ):
                    case_id = "nav_" + name.split()[0].lower()
                    cases.append(
                        TestCaseSpec(
                            case_id=case_id,
                            feature_key=scope.feature_key,
                            title=f"Public {name} navigation",
                            kind="state_transition",
                            steps=(
                                CaseAction(
                                    action="click",
                                    target=SemanticTarget(
                                        role="link",
                                        name=name,
                                        scope_role="navigation" if name != "Human" else None,
                                        scope_name="Site" if name != "Human" else None,
                                    ),
                                ),
                            ),
                            expected=(
                                ExpectedAssertion(
                                    assertion_id=case_id, oracle="url", expected_value=destination
                                ),
                            ),
                        )
                    )
                cases.append(
                    TestCaseSpec(
                        case_id="console_policy",
                        feature_key=scope.feature_key,
                        title="Console link respects stored origin policy",
                        kind="state_transition",
                        steps=(
                            CaseAction(
                                action="click",
                                target=SemanticTarget(
                                    role="link",
                                    name="Console (external)",
                                    scope_role="navigation",
                                    scope_name="Site",
                                ),
                            ),
                        ),
                        expected=(
                            ExpectedAssertion(
                                assertion_id="console_state",
                                oracle="title",
                                expected_value="Console",
                            ),
                        ),
                    )
                )
                cases.append(
                    TestCaseSpec(
                        case_id="product_heading",
                        feature_key=scope.feature_key,
                        title="Public product headline is rendered",
                        kind="happy_path",
                        steps=(CaseAction(action="wait", milliseconds=0),),
                        expected=(
                            ExpectedAssertion(
                                assertion_id="headline",
                                oracle="visible",
                                expected_value=True,
                                target=SemanticTarget(
                                    role="heading",
                                    name=(
                                        'Memory that infers, updates and forgets. The engine, '
                                        'in one page.'
                                    ),
                                ),
                            ),
                        ),
                    )
                )
                plan = select_feature_cases(
                    request=DeepFeaturePlanningRequest(test_run_id=run_id, scope=scope),
                    candidates=FeatureCaseCandidates(cases=tuple(cases)),
                )
                test_run.configuration_snapshot = {
                    **configuration,
                    "feature_scope": scope.model_dump(mode="json"),
                    "feature_plan": plan.model_dump(mode="json"),
                    "feature_budget": plan.budget.model_dump(mode="json"),
                    "planner_mode": "operator_public_navigation",
                }
            await session.commit()
            print(
                json.dumps(
                    {
                        "phase": "planning",
                        "run_id": str(run_id),
                        "target_id": str(target_id),
                        "approved_knowledge_sets": len(approved),
                    }
                ),
                flush=True,
            )
            await execute_markettwin_run(build_run_request(test_run), session=session)
        await process_run(engine, run_id)
        async with create_session_factory(engine)() as session:
            report = await session.scalar(select(Report).where(Report.test_run_id == run_id))
            if report is None:
                raise RuntimeError("No completed report exists.")
            payload = {
                "run_id": str(run_id),
                "report_id": str(report.id),
                "report": report.report_payload,
            }
            await asyncio.to_thread(output.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(
                (output / "results.json").write_text,
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "phase": "finished",
                        "run_id": str(run_id),
                        "coverage": report.report_payload.get("coverage"),
                    }
                ),
                flush=True,
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-id", type=UUID, required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--public-navigation-only",
        action="store_true",
        help="Use the inspected public-page navigation checks without a model call.",
    )
    args = parser.parse_args()
    try:
        asyncio.run(run(args.target_id, args.goal, args.output_dir, args.public_navigation_only))
    except Exception as error:
        print(json.dumps({"phase": "failed", "error_type": type(error).__name__}), flush=True)
        raise SystemExit(1) from None
