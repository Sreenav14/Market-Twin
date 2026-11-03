# MarketTwin

MarketTwin tests authorized web applications with bounded agents and real browser
execution, then links results to recorded steps, artifacts and findings. A completed
action or agent narrative is not independent proof of a product defect.

Branch: `feat/batch-1-aws-observability`.

## Project documents

1. [README](README.md): orientation and local commands.
2. [Current status](docs/CURRENT_STATE.md): implemented work, verification and open limits.
3. [Implementation handoff](docs/SESSION_HANDOFF.md): architecture/contracts, active
   requirements, T00-T13 gates, design/Figma inventory, operations and recovery.
4. [Product contract](docs/V1_PRODUCT_CONTRACT.md): testing behavior and evidence rules.
5. [Benchmark results](docs/V1_BENCHMARK_RESULTS.md): measured acceptance results.

`AGENTS.md` is retained as repository instructions. Other project documentation was
consolidated into these files at the user's request. Licenses, source/configuration,
regression tests, screenshots/manifests, benchmark data and backups are unchanged.

## Application and services

| Component | Source | Responsibility |
| --- | --- | --- |
| React/TypeScript web | [apps/web](apps/web) | Application-first Tests, knowledge, execution and evidence/report review |
| FastAPI Control API | [services/control-api](services/control-api) | Identity/workspace permissions, targets, run/review/report APIs |
| Execution Orchestrator | [services/execution-orchestrator](services/execution-orchestrator) | ADK planning, controlled Playwright execution and protected takeover |
| Evaluation Worker | [services/evaluation-worker](services/evaluation-worker) | Evidence checks, optional models and atomic reports |
| Knowledge Worker | [services/knowledge-worker](services/knowledge-worker) | Bounded extraction, grounded drafts and reviewed knowledge |

PostgreSQL stores domain/outbox/events, Kafka transports run commands, and configured
S3/MinIO stores artifacts. Browser registry ownership is process-local and protected;
source implementation does not establish production deployment or autonomous quality.

## Local development

Use Node 22+/npm 10+ and Python 3.12 as declared in package manifests. Preserve existing
`.env`; [.env.example](.env.example) owns configuration names/defaults. Use the existing
dependencies and services; do not create competing listeners merely to repeat checks.

For a fresh checkout, install `uv` using its standalone installer (or `pipx install
uv` on an externally managed Python installation; do not override system Python
package protections). From the repository root:

```powershell
npm.cmd install --legacy-peer-deps
uv sync
uv run playwright install chromium
uv run pytest --collect-only -q
npm.cmd run typecheck --workspace @markettwin/web
npm.cmd run test --workspace @markettwin/web
npm.cmd run build --workspace @markettwin/web
```

The npm peer-dependency flag is required by the current dependency tree. The
repository currently disables lockfile generation in `.npmrc`. On Linux, Chromium
may also require system libraries (`uv run playwright install --with-deps chromium`).
Install Chromium before running browser tests; `uv sync` alone does not install it.
Run `uv run pytest -q`, `uv run ruff check .`, and `uv run pyright` for Python checks.
Full-project Pyright has existing debt; touched production files must introduce no
new errors. Enable `OUTBOX_RELAY_ENABLED=true` for local Kafka run dispatch.

```powershell
npm.cmd --workspace @markettwin/web run dev
uv run --env-file .env python services/execution-orchestrator/scripts/run_execution_worker.py
uv run --env-file .env python -m markettwin_evaluation_worker.worker
```

The UI requires the configured Control API, database and authenticated workspace.
Starting runs also requires Kafka/outbox dispatch and execution; reports require
evaluation. Pages do not inject demo data when APIs are unavailable. The
[handoff](docs/SESSION_HANDOFF.md#service-operation-and-configuration) consolidates
setup, configuration, ownership, migration and retry-recovery details.

## Design and acceptance

Evidence desk uses teal, charcoal and warm neutrals across desktop/mobile/dialogs
and recovery. Preserve actual APIs, identity, permissions, target/evidence ownership
and browser controls. The handoff retains the 52 CURRENT Figma references and current
route/screenshot coverage; archived prototype behavior is not authoritative.

The single-frozen-contract six-run benchmark passed all gates. Final validation:
1,245 Python tests passed (23 skipped), 199 frontend tests passed, and typecheck,
build, Ruff and focused production Pyright passed. New runs default to discovery,
with legacy/deep modes retained. Changes are local and uncommitted; measured limits
and earlier failed attempts remain in the benchmark results and current-status docs.
