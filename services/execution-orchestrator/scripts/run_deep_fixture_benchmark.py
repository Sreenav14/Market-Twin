"""Execute static fixture oracles in Chromium; never score model narratives.

This direct_fixture mode establishes fixture truth, not autonomous tester quality.
No database, model provider, or external website is used. Each case gets a fresh
browser context and exact observation/screenshot artifacts in the output directory.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import Page, Route, async_playwright

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "tests/benchmarks/markettwin_deep/manifest.json"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def score(
    results: list[dict[str, Any]], cases: list[dict[str, Any]], variant: str,
) -> dict[str, Any]:
    """Denominators include missing results; failed tools cannot prove a defect."""
    by_id = {result["case_id"]: result for result in results}
    case_ids = {case["id"] for case in cases}
    if (len(case_ids) != len(cases) or len(by_id) != len(results)
            or set(by_id) - case_ids):
        raise ValueError("Duplicate or foreign case results cannot be scored.")
    completed = [result for result in results if result["execution_status"] == "completed"]
    asserted = [result for result in completed if result["verdict"] != "unverified"]
    return {
        "planned_executable_cases": len(cases),
        "completed_browser_cases": len(completed),
        "scenario_execution_rate": {"numerator": len(completed), "denominator": len(cases)},
        "oracle_coverage": {"numerator": len(asserted), "denominator": len(completed)},
        "ground_truth_agreement": {
            "numerator": sum(
                by_id.get(case["id"], {}).get("verdict") == case["expected_verdict"][variant]
                and by_id.get(case["id"], {}).get("execution_status") == "completed"
                for case in cases
            ),
            "denominator": len(cases),
        },
        "missing_results": [case["id"] for case in cases if case["id"] not in by_id],
        "autonomous_metrics": {
            "verified_finding_precision": None,
            "seeded_defect_recall": None,
            "evidence_provenance_correctness": None,
            "model_cost": None,
            "reason": "Direct fixture oracle execution; no autonomous case-bound run was scored.",
        },
    }


async def execute_case(page: Page, case: dict[str, Any]) -> list[dict[str, Any]]:
    for action in case["actions"]:
        locator = page.locator(action["selector"])
        if action["kind"] == "fill":
            await locator.fill(action["value"])
        elif action["kind"] == "click":
            await locator.click()
        elif action["kind"] == "select":
            await locator.select_option(action["value"])
        elif action["kind"] == "wait":
            await locator.wait_for(state="visible")
        else:
            raise ValueError("Unsupported fixture action.")
    observations: list[dict[str, Any]] = []
    for assertion in case["assertions"]:
        locator = page.locator(assertion["selector"])
        kind = assertion["kind"]
        if kind == "text":
            actual: str | bool = (await locator.inner_text()).strip()
        elif kind == "visible":
            actual = await locator.is_visible()
        elif kind == "enabled":
            actual = await locator.is_enabled()
        else:
            raise ValueError("Unsupported fixture assertion.")
        observations.append({
            **assertion, "actual": actual, "matches": actual == assertion["expected"],
        })
    if not observations:
        raise ValueError("Fixture cases must contain at least one independent assertion.")
    return observations


async def run(variant: str, output: Path) -> dict[str, Any]:
    manifest_bytes = MANIFEST.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest["schema_version"] != 1 or not 1 <= len(manifest["cases"]) <= 32:
        raise ValueError("Unsupported or unbounded benchmark manifest.")
    fixture = (ROOT / manifest["fixture_path"]).resolve()
    if not fixture.is_relative_to(ROOT / "services/execution-orchestrator/tests/fixtures"):
        raise ValueError("Benchmark fixture must stay in the repository fixture directory.")
    fixture_sha256 = hashlib.sha256(fixture.read_bytes()).hexdigest()
    await asyncio.to_thread(output.mkdir, parents=True, exist_ok=True)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(QuietHandler, directory=str(fixture.parent)),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{server.server_port}"

    async def local_only(route: Route) -> None:
        parsed = urlsplit(route.request.url)
        if parsed.scheme == "http" and parsed.netloc == urlsplit(origin).netloc:
            await route.continue_()
        else:
            await route.abort("blockedbyclient")

    results: list[dict[str, Any]] = []
    started = time.monotonic()
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                for index, case in enumerate(manifest["cases"]):
                    context = await browser.new_context(
                        viewport={"width": 390, "height": 844}, service_workers="block",
                    )
                    await context.route("**/*", local_only)
                    page = await context.new_page()
                    page.set_default_timeout(3000)
                    result: dict[str, Any] = {
                        "case_id": case["id"], "execution_status": "failed",
                        "verdict": "unverified", "assertions": [],
                    }
                    try:
                        async with asyncio.timeout(15):
                            await page.goto(f"{origin}/{fixture.name}?variant={variant}")
                            observations = await execute_case(page, case)
                            screenshot = f"case-{index + 1:02d}.png"
                            await page.screenshot(path=str(output / screenshot), full_page=True)
                            result.update(
                                execution_status="completed", assertions=observations,
                                verdict=("satisfied" if all(o["matches"] for o in observations)
                                         else "not_satisfied"),
                                screenshot=screenshot,
                            )
                    except Exception as error:
                        result["error_type"] = type(error).__name__
                    finally:
                        await context.close()
                    results.append(result)
            finally:
                await browser.close()
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
    report: dict[str, Any] = {
        "schema_version": 1, "mode": "direct_fixture", "variant": variant,
        "fixture_version": manifest["fixture_version"],
        "fixture_sha256": fixture_sha256,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "metrics": score(results, manifest["cases"], variant), "cases": results,
        "diagnostic_probes": [{"id": p["id"], "status": "not_executed"}
                              for p in manifest.get("diagnostic_probes", [])],
        "limitations": ["Direct fixture execution is not a persisted autonomous MarketTwin run.",
                        "Diagnostic probes and autonomous precision/recall remain unmeasured."],
    }
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    rows = ["# Direct fixture benchmark", "", f"Variant: {variant}",
            "", "No autonomous tester precision or recall is claimed.", "",
            "| Case | Execution | Oracle verdict |", "|---|---|---|"]
    rows.extend(f"| {r['case_id']} | {r['execution_status']} | {r['verdict']} |" for r in results)
    metrics = report["metrics"]
    rows.extend(["", f"Completed browser cases: {metrics['completed_browser_cases']}/"
                 f"{metrics['planned_executable_cases']}.",
                 f"Ground-truth agreement: {metrics['ground_truth_agreement']['numerator']}/"
                 f"{metrics['ground_truth_agreement']['denominator']}."])
    (output / "results.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-development", action="store_true", required=True)
    parser.add_argument("--variant", choices=("good", "bad"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(run(args.variant, args.output_dir))
    print(json.dumps({"mode": result["mode"], "variant": result["variant"],
                      "metrics": result["metrics"]}))
    if result["metrics"]["ground_truth_agreement"]["numerator"] != len(result["cases"]):
        raise SystemExit(1)
