import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("approval and contract results preserve accessible checks and honest coverage", async ({ page }, testInfo) => {
  let report = false;
  const contract = { contract_id: "contract", test_run_id: "run", version: 1, status: "draft", journeys: [{ journey_key: "search", title: "Search catalog", feature_key: "catalog", excluded: false, steps: [{ action: "click", target: { role: "button", name: "Search" } }], safe_test_data_keys: [], assertions: [{ assertion_id: "results", oracle: "title", target_role: null, target_name: null, expected_value: "Results", plain_language: "After searching, the title is Results.", source_step_ordinal: 1, origin: null, excluded: false }] }] };
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown;
    if (path === "/api/v1/me") data = { id: "user", email: "reviewer@example.test", display_name: "Reviewer" };
    else if (path === "/api/v1/workspaces") data = [{ id: "workspace", name: "Review workspace", role: "owner", status: "active" }];
    else if (path === "/api/v1/test-runs/run") data = { id: "run", workspace_id: "workspace", application_id: "app", target_id: "target", created_by_user_id: "user", status: report ? "completed" : "awaiting_human", target_snapshot: { name: "Catalog app", base_url: "https://example.test", allowed_origins: [{ scheme: "https", hostname: "example.test" }] }, configuration_snapshot: { execution_mode: "discovery_contract_v1", discovery_stage: report ? "completed" : "awaiting_approval", discovery_map: { features: [{}], journeys: [{ journey_key: "search", completed: true }] } } };
    else if (path.endsWith("/contract")) data = contract;
    else if (path.endsWith("/preflight")) data = { ready: true, checks: [] };
    else if (path.endsWith("/journeys")) data = [];
    else if (path.endsWith("/results") && report) data = { test_run_id: "run", findings: [], report: { id: "report", version: 1, status: "completed", generated_at: null, executive_summary: "No confirmed problems", payload: { mode: "discovery_contract_v1", coverage: { tested_features: 1, discovered_features: 2 }, what_works: [], confirmed: [], unverified: [{ check: "Search completion", reason: "replay_unavailable" }], market_verdict: { verdict: "insufficient_evidence", journeys_executed: 1, journeys_approved: 2, confirmed_defects: 0, persona_means: {} } } } };
    else { await route.fulfill({ status: 404, json: { detail: "Not available in this fixture." } }); return; }
    await route.fulfill({ json: data });
  });
  for (const state of ["contract", "report"]) {
    report = state === "report";
    await page.goto(`/runs/run/${state}`);
    await expect(page.getByRole("heading", { name: report ? "What works" : "Approve the tests", exact: true }).last()).toBeVisible();
    const selector = report ? ".contract-report" : ".contract-review";
    const axe = await new AxeBuilder({ page }).include(selector).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(axe.violations).toEqual([]);
    const overflow = await page.evaluate(() => Array.from(document.querySelectorAll("body *")).filter(element => element.getBoundingClientRect().right > window.innerWidth + 1).map(element => `${element.tagName}.${element.className}`).slice(0, 20));
    expect(overflow).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`${state}.png`), fullPage: true });
  }
});
