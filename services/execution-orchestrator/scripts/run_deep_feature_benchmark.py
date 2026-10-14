"""Persist and evaluate real bounded cases on the isolated local fixture."""

import argparse
import asyncio
import json
import os
import threading
from dataclasses import replace
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from dotenv import load_dotenv
from markettwin_database import create_database_engine, create_session_factory
from markettwin_database.models import (
    ApplicationTarget,
    Report,
    TargetAllowedOrigin,
    TargetAuthorization,
    TestRun,
)
from markettwin_evaluation_worker.worker import process_run
from markettwin_execution_orchestrator.workflow.run_executor import execute_markettwin_run
from markettwin_execution_orchestrator.workflow.run_request import build_run_request
from markettwin_execution_orchestrator.workflow.test_case_planner import (
    DeepFeaturePlanningRequest,
    fixture_case_candidates,
    fixture_feature_scope,
    select_feature_cases,
)
from sqlalchemy import select
from sqlalchemy.engine import URL

FIXTURE = Path(__file__).parents[1] / "tests/fixtures/deep_testing_app"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


async def run(variant: str, output: Path, port: int, planner: str) -> None:
    load_dotenv(override=True)
    if os.environ.get("POSTGRES_HOST") not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Benchmark requires the existing local development database.")
    if urlsplit(os.environ.get("S3_ENDPOINT_URL", "")).hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("Benchmark requires the existing local development object storage.")
    url = URL.create(
        "postgresql+asyncpg",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        database=os.environ["POSTGRES_DB"],
    )
    engine = create_database_engine(url.render_as_string(hide_password=False))
    try:
        async with create_session_factory(engine)() as session:
            baseline = await session.scalar(select(TestRun).order_by(TestRun.created_at).limit(1))
            if baseline is None:
                raise RuntimeError("An existing seeded workspace/application/user is required.")
            target_id, run_id = uuid4(), uuid4()
            starting_url = f"http://127.0.0.1:{port}/index.html?variant={variant}"
            origin = {
                "scheme": "http",
                "hostname": "127.0.0.1",
                "port": port,
                "include_subdomains": False,
            }
            session.add(
                ApplicationTarget(
                    id=target_id,
                    application_id=baseline.application_id,
                    name=f"Deep fixture {variant}",
                    environment="local-benchmark",
                    base_url=starting_url,
                    requires_auth=False,
                )
            )
            await session.flush()
            session.add(TargetAllowedOrigin(target_id=target_id, **origin))
            session.add(
                TargetAuthorization(
                    target_id=target_id,
                    created_by_user_id=baseline.created_by_user_id,
                    authorized_by_user_id=baseline.created_by_user_id,
                    status="authorized",
                    authorization_basis="User-authorized isolated loopback feature benchmark.",
                )
            )
            scope = fixture_feature_scope(starting_url)
            planning = DeepFeaturePlanningRequest(
                test_run_id=run_id,
                scope=scope,
                allow_fixture_truth=True,
            )
            plan = select_feature_cases(request=planning, candidates=fixture_case_candidates(scope))
            configuration: dict[str, object] = {
                "study_brief": scope.goal,
                "execution_mode": "deep_feature_v1",
                "feature_scope": scope.model_dump(mode="json"),
                "feature_budget": plan.budget.model_dump(mode="json"),
                "benchmark_fixture_version": "deep-fixture-v1",
                "benchmark_variant": variant,
                "planner_mode": planner,
            }
            if planner == "frozen":
                configuration["feature_plan"] = plan.model_dump(mode="json")
            test_run = TestRun(
                id=run_id,
                workspace_id=baseline.workspace_id,
                application_id=baseline.application_id,
                target_id=target_id,
                created_by_user_id=baseline.created_by_user_id,
                status="draft",
                target_snapshot={
                    "base_url": starting_url,
                    "allowed_origins": [origin],
                    "name": "Controlled deep fixture",
                    "requires_auth": False,
                },
                configuration_snapshot=configuration,
            )
            session.add(test_run)
            await session.commit()
            print(
                json.dumps({"phase": "execution", "run_id": str(run_id), "planner": planner}),
                flush=True,
            )
            await execute_markettwin_run(
                replace(
                    build_run_request(test_run),
                    network_policy="local_development",
                    fixture_truth=True,
                ),
                session=session,
            )
        await process_run(engine, run_id)
        async with create_session_factory(engine)() as session:
            report = await session.scalar(select(Report).where(Report.test_run_id == run_id))
            if report is None:
                raise RuntimeError("The completed run did not produce a report.")
            payload = {
                "schema_version": 1,
                "mode": "persisted_deep_feature_v1",
                "planner": planner,
                "variant": variant,
                "run_id": str(run_id),
                "report_id": str(report.id),
                "report": report.report_payload,
                "limits": [
                    "Frozen planning runs do not measure model planning quality.",
                    "No autonomous model budget winner is claimed.",
                ],
            }
            await asyncio.to_thread(output.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(
                (output / "results.json").write_text,
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )
            await asyncio.to_thread(
                (output / "results.md").write_text,
                f"# Persisted deep feature benchmark\n\n{report.executive_summary}\n\n"
                f"Run: {run_id}\nPlanner: {planner}\n",
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
    parser.add_argument("--local-development", action="store_true", required=True)
    parser.add_argument("--variant", choices=("good", "bad"), required=True)
    parser.add_argument(
        "--planner",
        choices=("frozen", "model"),
        default="frozen",
        help="model uses the existing configured provider; frozen uses trusted cases.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(FIXTURE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        asyncio.run(run(args.variant, args.output_dir, server.server_port, args.planner))
    except Exception as error:
        print(json.dumps({"phase": "failed", "error_type": type(error).__name__}), flush=True)
        raise SystemExit(1) from None
    finally:
        server.shutdown()
        server.server_close()
