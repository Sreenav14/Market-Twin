import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type TestInfo } from "@playwright/test";

const runId = "recorded-run";
const artifactId = "cafe1234-5678-4567-8123-abcdef123456";
const previewUrl = "https://evidence.example.invalid/recorded-preview.svg";
const run = {
  id: runId, workspace_id: "workspace", application_id: "app", target_id: "target",
  created_by_user_id: "user", status: "completed",
  target_snapshot: { name: "Staging", environment: "test", base_url: "https://example.invalid" },
  configuration_snapshot: { study_brief: "Verify checkout and account navigation", testing_depth: "medium" },
};
const journeys = [
  {
    id: "checkout", ordinal: 1, persona_name: "First-time shopper", mission_title: "Place an order",
    success_criteria: ["An order confirmation is visible"], execution_id: "execution-one", attempt_number: 1,
    execution_status: "completed", outcome: "failed", started_at: "2026-10-04T10:00:00Z", completed_at: "2026-10-04T10:00:12Z", error_message: null,
    result: { summary: "The browser journey finished, but checkout showed an error.", actions: ["Submitted checkout once"], observations: ["Payment validation prevented confirmation"], friction_points: ["The error did not identify the invalid field"], blockers: [] },
  },
  {
    id: "account", ordinal: 2, persona_name: "Returning customer", mission_title: "Open account settings",
    success_criteria: ["Account settings opens"], execution_id: "execution-two", attempt_number: 1,
    execution_status: "failed", outcome: null, started_at: "2026-10-04T10:00:14Z", completed_at: "2026-10-04T10:00:15Z", error_message: "Browser session closed before the action completed.", result: null,
  },
  {
    id: "help", ordinal: 3, persona_name: "Support seeker", mission_title: "Find returns guidance",
    success_criteria: ["Returns policy is discoverable"], execution_id: null, attempt_number: null,
    execution_status: null, outcome: null, started_at: null, completed_at: null, error_message: null, result: null,
  },
];
const records = [
  {
    criterion: "Payment error is visible", status: "satisfied", reported_status: "satisfied",
    rationale: "The recorded screenshot shows a payment error beside checkout.",
    observed_details: ["Payment could not be processed is visible"], evidence: { step_ids: [7], artifact_ids: [artifactId] },
  },
  {
    criterion: "Order confirmation is visible", status: "unsatisfied", reported_status: "satisfied",
    rationale: "The screenshot contains an error and no order confirmation.",
    observed_details: ["No order number is visible"], evidence: { step_ids: [7, 8], artifact_ids: [artifactId] },
  },
  {
    criterion: "Account settings opens", status: "unverified", reported_status: "not observed",
    rationale: "No screenshot was recorded after the browser session closed.",
    observed_details: [], evidence: { step_ids: [], artifact_ids: [] },
  },
];

type MockState = { pending: boolean; payload: Record<string, unknown>; denied: boolean; accessRequests: number; starts: number };

async function mockRun(page: Page, overrides: Partial<MockState> = {}) {
  const state: MockState = { pending: false, payload: { evaluation_records: records }, denied: false, accessRequests: 0, starts: 0, ...overrides };
  await page.route(previewUrl, (route) => route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="560" height="200"><rect width="560" height="200" fill="#f5f7fa"/><text x="24" y="45" fill="#172431" font-family="sans-serif" font-size="24">Checkout</text><text x="24" y="110" fill="#b42335" font-family="sans-serif" font-size="18">Payment could not be processed</text></svg>' }));
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown;
    if (path === "/api/v1/me") data = { id: "user", email: "reviewer@example.com", display_name: "Morgan Lee" };
    else if (path === "/api/v1/workspaces") data = [{ id: "workspace", name: "Demo workspace", status: "active", role: "owner" }];
    else if (path === `/api/v1/test-runs/${runId}`) data = run;
    else if (path === `/api/v1/test-runs/${runId}/journeys`) data = journeys;
    else if (path === `/api/v1/test-runs/${runId}/journeys/checkout`) data = {
      journey: { ...journeys[0], persona_perspective: "First-time customer", mission_objective: "Complete checkout", step_count: 2, artifact_count: 1, evidence_available: true, summary: journeys[0].result?.summary },
      steps: [
        { id: 7, step_number: 1, action_type: "click", action_summary: "Click a semantic page element.", observation_summary: "Page: https://example.invalid", status: "completed", started_at: null, completed_at: null },
        { id: 8, step_number: 2, action_type: "click", action_summary: "Click a semantic page element.", observation_summary: "Action did not complete.", status: "failed", started_at: null, completed_at: null },
      ], artifacts: [{ id: artifactId, step_id: 7, artifact_type: "screenshot", kind: "viewport", content_type: "image/svg+xml", size_bytes: 200, created_at: "2026-10-04T10:00:12Z" }], findings: [], next_after_step: null, artifacts_truncated: false,
    };
    else if (path === `/api/v1/test-runs/${runId}/collection`) data = { collection: { journey_count: 3 }, collected_at: "2026-10-04T10:00:20Z" };
    else if (path === `/api/v1/test-runs/${runId}/evaluation-agents`) data = [];
    else if (path === `/api/v1/test-runs/${runId}/flow`) data = {
      nodes: [{ id: "meta", kind: "meta", label: "Meta Agent", status: "completed" }, ...journeys.map((journey) => ({ id: `journey:${journey.id}`, kind: "journey", label: `${journey.persona_name} · ${journey.mission_title}`, status: journey.execution_status || "not_started" })), { id: "collector", kind: "collector", label: "Supervisor collection", status: "completed" }, { id: "evaluation", kind: "evaluation", label: "Evaluation", status: state.pending ? "awaiting_report" : "completed" }, { id: "report", kind: "report", label: "Report", status: state.pending ? "not_started" : "completed" }],
      edges: [{ source: "meta", target: "journey:checkout" }, { source: "journey:checkout", target: "journey:account" }, { source: "journey:account", target: "journey:help" }, { source: "journey:help", target: "collector" }, { source: "collector", target: "evaluation" }, { source: "evaluation", target: "report" }],
      execution_policy: "once_per_journey", revision: state.pending ? "pending" : "saved",
    };
    else if (path === `/api/v1/test-runs/${runId}/results`) {
      if (state.pending) { await route.fulfill({ status: 409, json: { detail: "Evaluation is not saved yet." } }); return; }
      data = { test_run_id: runId, report: { id: "report", version: 1, status: "completed", executive_summary: "Checkout needs correction; account access could not be verified.", payload: state.payload, generated_at: "2026-10-04T10:01:00Z" }, findings: [] };
    }
    else if (path === `/api/v1/test-runs/${runId}/artifacts/${artifactId}/access`) {
      state.accessRequests += 1;
      if (state.denied) { await route.fulfill({ status: 403, json: { detail: "You do not have access to this evidence." } }); return; }
      data = { artifact_id: artifactId, artifact_type: "screenshot", content_type: "image/svg+xml", url: previewUrl, expires_in_seconds: 60 };
    }
    else if (path.endsWith("/start")) { state.starts += 1; await route.fulfill({ status: 400, json: { detail: "These checks must not start execution." } }); return; }
    else { await route.fulfill({ status: 404, json: { detail: "No fixture for this request." } }); return; }
    await route.fulfill({ json: data });
  });
  return state;
}

async function checkLayout(page: Page, testInfo: TestInfo, screenshot?: string) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(audit.violations).toEqual([]);
  if (screenshot) {
    await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); window.scrollTo(0, 0); });
    await page.screenshot({ path: testInfo.outputPath(`${screenshot}.png`), fullPage: true });
  }
}

test("journey step selection never substitutes another step's screenshot", async ({ page }, testInfo) => {
  const state = await mockRun(page);
  await page.goto(`/runs/${runId}/journeys/checkout`);
  await expect(page.getByRole("heading", { name: "Place an order", exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Step 1/ }).click();
  await expect(page.getByRole("img", { name: "Recorded screenshot evidence" })).toBeVisible();
  const initialAccessRequests = state.accessRequests;
  await page.getByRole("button", { name: /Step 2/ }).click();
  await expect(page.getByText("Evidence unavailable for this step.", { exact: true })).toBeVisible();
  await expect(page.getByRole("img", { name: "Recorded screenshot evidence" })).toHaveCount(0);
  await expect(page.locator('.journey-step[data-status="failed"]')).toHaveAttribute("aria-pressed", "true");
  expect(state.accessRequests).toBe(initialAccessRequests);
  await checkLayout(page, testInfo, "journey-detail");
  expect(state.starts).toBe(0);
});

test("journey outputs remain available while evaluation is pending", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  const state = await mockRun(page, { pending: true });
  await page.goto(`/runs/${runId}/journeys`);
  await expect(page.getByRole("heading", { name: "Journey results" })).toBeVisible();
  await expect(page.getByText(/Supervisor collected 3 journey outputs/)).toBeVisible();
  const completed = page.getByRole("article").filter({ has: page.getByRole("heading", { name: "First-time shopper · Place an order" }) });
  await expect(completed.getByText("completed", { exact: true })).toBeVisible();
  await expect(completed.getByText("failed", { exact: true })).toBeVisible();
  await expect(completed.getByText("The browser journey finished, but checkout showed an error.")).toBeVisible();
  await completed.locator("summary").click();
  await expect(completed.getByText("Submitted checkout once", { exact: true })).toBeVisible();
  await expect(completed.getByText("Payment validation prevented confirmation", { exact: true })).toBeVisible();
  const failed = page.getByRole("article").filter({ has: page.getByRole("heading", { name: "Returning customer · Open account settings" }) });
  await expect(failed.getByText("failed", { exact: true })).toBeVisible();
  await expect(failed.getByText("not recorded", { exact: true })).toBeVisible();
  await expect(failed.getByText("Browser session closed before the action completed.")).toBeVisible();
  const notStarted = page.getByRole("article").filter({ has: page.getByRole("heading", { name: "Support seeker · Find returns guidance" }) });
  await expect(notStarted.getByText("not started", { exact: true })).toBeVisible();
  await expect(notStarted.getByText("not recorded", { exact: true })).toBeVisible();
  await checkLayout(page, testInfo, "journey-results");
  await page.getByRole("link", { name: "View evaluation", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Preparing evaluation" })).toBeVisible();
  await expect(page.getByText(/Browser execution is complete\. Evaluation is still pending/)).toBeVisible();
  await checkLayout(page, testInfo);
  await page.getByRole("button", { name: "Check again", exact: true }).click();
  state.pending = false;
  await page.getByRole("button", { name: "Refresh test", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Evaluation records" })).toBeVisible();
  const flowPanel = page.getByRole("complementary", { name: "Agent flow", exact: true });
  if (await flowPanel.locator("details").first().getAttribute("open") === null) await flowPanel.locator("summary").first().click();
  const reportNode = flowPanel.locator("li").filter({ has: page.getByText("Report", { exact: true }) });
  await expect(reportNode.getByText("completed", { exact: true })).toBeVisible();
  expect(state.starts).toBe(0);
});

test("evaluation explains each visual check and opens its exact recorded evidence", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  const state = await mockRun(page);
  await page.goto(`/runs/${runId}/evaluation`);
  for (const [index, status] of ["passed", "failed", "unverified"].entries()) {
    const record = page.getByRole("article").filter({ has: page.getByRole("heading", { name: records[index].criterion, exact: true }) });
    await expect(record.getByText(status, { exact: true })).toBeVisible();
    await expect(record.getByText(records[index].rationale, { exact: true })).toBeVisible();
  }
  const unsatisfied = page.getByRole("article").filter({ has: page.getByRole("heading", { name: "Order confirmation is visible", exact: true }) });
  await expect(unsatisfied.getByText("Persona reported: satisfied", { exact: true })).toBeVisible();
  await expect(unsatisfied.getByText("Evidence steps: 7, 8", { exact: true })).toBeVisible();
  await expect(unsatisfied.getByText("No order number is visible", { exact: true })).toBeVisible();
  const evidence = unsatisfied.getByRole("link", { name: "Evidence cafe1234", exact: true });
  await expect(evidence).toHaveAttribute("href", `/runs/${runId}/evidence/${artifactId}`);
  await checkLayout(page, testInfo, "evaluation-records");
  await evidence.click();
  await expect(page.getByRole("heading", { name: "Recorded evidence" })).toBeVisible();
  await expect(page.getByText(`Artifact ${artifactId}.`, { exact: false })).toBeVisible();
  expect(state.accessRequests).toBe(0);
  await page.getByRole("button", { name: "View evidence", exact: true }).click();
  const image = page.getByRole("img", { name: "Recorded screenshot evidence" });
  await expect(image).toBeVisible();
  await expect.poll(() => image.evaluate((node: HTMLImageElement) => node.naturalWidth)).toBeGreaterThan(0);
  await expect(image).toHaveAttribute("src", previewUrl);
  expect(state.accessRequests).toBe(1);
  await checkLayout(page, testInfo, "recorded-evidence");
  await page.getByRole("link", { name: "Back to evaluation", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Evaluation records" })).toBeVisible();
  expect(state.starts).toBe(0);
});

for (const [name, payload, copy] of [
  ["historical report", {}, "Detailed checks were not recorded for this report version. Its saved findings and report remain available."],
  ["evaluation without visual checks", { evaluation_records: [] }, "No visual criteria were selected for verification in this evaluation. This does not indicate that every criterion passed."],
] as const) {
  test(`${name} does not imply that all visual checks passed`, async ({ page }, testInfo) => {
    test.setTimeout(60_000);
    const state = await mockRun(page, { payload });
    await page.goto(`/runs/${runId}/evaluation`);
    await expect(page.getByRole("heading", { name: "Evaluation records" })).toBeVisible();
    await expect(page.getByText(copy, { exact: true })).toBeVisible();
    await expect(page.getByRole("article")).toHaveCount(0);
    await checkLayout(page, testInfo);
    await page.getByRole("navigation", { name: "Test sections" }).getByRole("link", { name: "Report", exact: true }).click();
    await expect(page.getByRole("heading", { name: "What this test found" })).toBeVisible();
    await expect(page.getByText("Checkout needs correction; account access could not be verified.", { exact: true })).toBeVisible();
    expect(state.starts).toBe(0);
  });
}

test("denied evidence access never displays a preview, including after a successful preview", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  const state = await mockRun(page, { denied: true });
  await page.goto(`/runs/${runId}/evidence/${artifactId}`);
  await page.getByRole("button", { name: "View evidence", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("You do not have access to this evidence.");
  await expect(page.getByRole("img", { name: "Recorded screenshot evidence" })).toHaveCount(0);
  await checkLayout(page, testInfo);
  state.denied = false;
  await page.getByRole("button", { name: "View evidence", exact: true }).click();
  await expect(page.getByRole("img", { name: "Recorded screenshot evidence" })).toBeVisible();
  state.denied = true;
  await page.getByRole("button", { name: "Refresh evidence", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("You do not have access to this evidence.");
  await expect(page.getByRole("img", { name: "Recorded screenshot evidence" })).toHaveCount(0);
  await expect(page.getByRole("link").filter({ has: page.getByRole("img", { name: "Recorded screenshot evidence" }) })).toHaveCount(0);
  expect(state.accessRequests).toBe(3);
  expect(state.starts).toBe(0);
});

test("saved model assessment explains its scope and links each individual conclusion to the recorded journey", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  const state = await mockRun(page, { payload: {
    evaluation_records: records,
    assessment: {
      status: "completed",
      individual_results: [{ journey_id: "account", persona_name: "Returning customer", mission_title: "Open account settings", goal_outcome: "inconclusive", ease_of_use: "inconclusive", summary: "Account navigation could not be evaluated because the browser session closed.", recommendations: [] }],
      overall: { goal_outcome: "partially_met", ease_of_use: "difficult", summary: "Checkout produced useful error evidence, but account navigation remains unverified.", supporting_journey_ids: ["checkout", "account"], recommendations: ["Explain the invalid checkout field beside its input."], limitations: ["Only assigned flows were assessed; untested application areas have no verdict."] },
      runtime: { model_name: "configured/model", duration_seconds: 2.5 },
    },
  } });
  await page.goto(`/runs/${runId}/evaluation`);
  const assessment = page.getByRole("region", { name: "Overall assessment", exact: true });
  await expect(assessment.getByText("partial", { exact: true })).toBeVisible();
  await expect(assessment.getByText("Ease of use: difficult", { exact: true })).toBeVisible();
  await expect(assessment.getByText("Checkout produced useful error evidence, but account navigation remains unverified.", { exact: true })).toBeVisible();
  await expect(assessment.getByText("Only assigned flows were assessed; untested application areas have no verdict.", { exact: true })).toBeVisible();
  await expect(assessment.getByText("Explain the invalid checkout field beside its input.", { exact: true })).toBeVisible();
  await expect(assessment.getByText(/configured\/model · 2\.5 seconds/)).toBeVisible();
  const disclosure = assessment.locator("details");
  await expect(disclosure).not.toHaveAttribute("open", "");
  await assessment.locator("summary").click();
  const individual = assessment.getByRole("article");
  await expect(individual.getByRole("heading", { name: "Returning customer · Open account settings", exact: true })).toBeVisible();
  await expect(individual.getByText("inconclusive", { exact: true })).toBeVisible();
  await expect(individual.getByText("Account navigation could not be evaluated because the browser session closed.", { exact: true })).toBeVisible();
  const source = individual.getByRole("link", { name: "Inspect recorded journey", exact: true });
  await expect(source).toHaveAttribute("href", `/runs/${runId}/journeys#journey-account`);
  await checkLayout(page, testInfo, "model-assessment");
  await source.click();
  await expect(page).toHaveURL(new RegExp(`/runs/${runId}/journeys#journey-account$`));
  await expect(page.locator("#journey-account").getByRole("heading", { name: "Returning customer · Open account settings", exact: true })).toBeVisible();
  await expect(page.locator("#journey-account").getByText("Browser session closed before the action completed.", { exact: true })).toBeVisible();
  await page.getByRole("navigation", { name: "Test sections" }).getByRole("link", { name: "Report", exact: true }).click();
  await expect(assessment.getByText("partial", { exact: true })).toBeVisible();
  await expect(assessment.getByText("Only assigned flows were assessed; untested application areas have no verdict.", { exact: true })).toBeVisible();
  await expect(assessment.getByRole("link", { name: "Supporting journey account", exact: true })).toHaveAttribute("href", `/runs/${runId}/journeys#journey-account`);
  await checkLayout(page, testInfo);
  expect(state.starts).toBe(0);
});
