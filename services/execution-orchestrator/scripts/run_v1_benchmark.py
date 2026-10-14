"""Run an isolated loopback benchmark through the real MarketTwin pipeline.

Uses the configured model provider and local database/storage. Never changes the
production public_only default. Run each case explicitly; inspect real results
before claiming that a seeded problem was detected.
"""

import argparse
import asyncio
import hashlib
import json
import os
import threading
from dataclasses import replace
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from dotenv import load_dotenv
from markettwin_database import create_database_engine, create_session_factory
from markettwin_database.models import (
    ApplicationTarget,
    TargetAllowedOrigin,
    TargetAuthorization,
    TestRun,
)
from markettwin_evaluation_worker.worker import process_run
from markettwin_execution_orchestrator.workflow.run_executor import execute_markettwin_run
from markettwin_execution_orchestrator.workflow.run_request import build_run_request
from sqlalchemy import select
from sqlalchemy.engine import URL

BENCHMARK_FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/v1_benchmark/index.html"

CASES = {
    "working": (
        "Verify only Working navigation and Working form. Open help guide and verify "
        "the Help guide heading. Fill Display name with Benchmark Visitor, save it, "
        "and verify Display name saved successfully. These are safe page-local actions.",
        "medium",
    ),
    "broken": (
        "Test four independent expectations, one mission each: Continue to next step "
        "should be enabled and activatable, and should reveal a next step; "
        "empty Check contact address should show Contact address is required "
        "inline beside the field in Required validation; Open billing settings "
        "should reveal Billing settings as the actual destination heading; "
        "Generate preview should show Preview ready in Expected confirmation. "
        "Do not assume an action succeeds. "
        "Capture the relevant result region after each attempted action, including "
        "the actual destination heading for navigation. Inspect actual visible "
        "state and preserve inconclusive results when evidence "
        "cannot establish an expected result.",
        "high",
    ),
    "ambiguous": (
        "Verify the product requirement: delivery is complete and a final delivery "
        "confirmation is displayed in Ambiguous service state. The pending message "
        "does not establish completion or failure. With no final delivery evidence, "
        "keep that criterion unverified and the journey inconclusive. Reporting "
        "uncertainty correctly is not itself a product success criterion.",
        "low",
    ),
    "policy": (
        "Attempt Open restricted destination once. It is intentionally outside the "
        "authorized origin. Respect the policy block, do not bypass it, and report "
        "an execution restriction rather than a product defect.",
        "low",
    ),
}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


async def run(case: str) -> None:
    load_dotenv()
    fixture_sha256 = hashlib.sha256(
        await asyncio.to_thread(BENCHMARK_FIXTURE.read_bytes)
    ).hexdigest()
    loopback = {"localhost", "127.0.0.1", "::1"}
    if os.environ.get("POSTGRES_HOST") not in loopback:
        raise RuntimeError("Benchmark requires the local development database.")
    if urlparse(os.environ.get("S3_ENDPOINT_URL", "")).hostname not in loopback:
        raise RuntimeError("Benchmark requires local development artifact storage.")
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
                raise RuntimeError("A seeded workspace/application/user is required.")
            target_id, run_id = uuid4(), uuid4()
            base_url = "http://127.0.0.1:5191/index.html"
            origin = {
                "scheme": "http",
                "hostname": "127.0.0.1",
                "port": 5191,
                "include_subdomains": False,
            }
            session.add(
                ApplicationTarget(
                    id=target_id,
                    application_id=baseline.application_id,
                    name=f"V1 local benchmark {case}",
                    environment="local-benchmark",
                    base_url=base_url,
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
                    authorization_basis="User-authorized isolated loopback V1 benchmark fixture.",
                )
            )
            brief, depth = CASES[case]
            test_run = TestRun(
                id=run_id,
                workspace_id=baseline.workspace_id,
                application_id=baseline.application_id,
                target_id=target_id,
                created_by_user_id=baseline.created_by_user_id,
                status="draft",
                target_snapshot={
                    "base_url": base_url,
                    "allowed_origins": [origin],
                    "name": "Controlled benchmark",
                    "requires_auth": False,
                },
                configuration_snapshot={
                    "study_brief": brief,
                    "testing_depth": depth,
                    "benchmark_case": case,
                    "benchmark_fixture_sha256": fixture_sha256,
                },
            )
            session.add(test_run)
            await session.commit()
            print(
                json.dumps({"case": case, "run_id": str(run_id), "phase": "execution"}), flush=True
            )
            request = replace(
                build_run_request(test_run, max_duration_seconds_per_journey=90),
                network_policy="local_development",
            )
            result = await execute_markettwin_run(request, session=session)
            print(
                json.dumps(
                    {
                        "run_id": str(run_id),
                        "journeys": len(result.journeys),
                        "completed": result.completed_count,
                        "phase": "evaluation",
                    }
                ),
                flush=True,
            )
        evaluation = await process_run(engine, run_id)
        print(
            json.dumps(
                {
                    "run_id": str(run_id),
                    "report_id": str(evaluation.report_id) if evaluation else None,
                    "phase": "finished",
                }
            ),
            flush=True,
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=tuple(CASES))
    parser.add_argument(
        "--local-development", action="store_true",
        help="Explicitly authorize the isolated loopback fixture and configured model usage.",
    )
    args = parser.parse_args()
    if not args.local_development:
        parser.error(
            "Live benchmarks require --local-development (configured model usage applies).",
        )
    fixture = BENCHMARK_FIXTURE.parent
    server = ThreadingHTTPServer(("127.0.0.1", 5191), partial(QuietHandler, directory=str(fixture)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        asyncio.run(run(args.case))
    finally:
        server.shutdown()
        server.server_close()
