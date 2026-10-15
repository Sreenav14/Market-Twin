import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

// HITL fixtures use mocked API data and a synthetic lease grant. They exercise
// the blank viewer layout without live connections, credential entry, or frames.
test.use({ trace: "off", screenshot: "off" });

const runId = "11111111-1111-4111-8111-111111111111";
const appId = "22222222-2222-4222-8222-222222222222";
const targetId = "33333333-3333-4333-8333-333333333333";
const journeyId = "55555555-5555-4555-8555-555555555555";
const approvalId = "66666666-6666-4666-8666-666666666666";
const artifactId = "77777777-7777-4777-8777-777777777777";

const syntheticUser = {
  id: "88888888-8888-4888-8888-888888888888",
  email: "reviewer@example.invalid",
  normalized_email: "reviewer@example.invalid",
  display_name: "Review fixture",
};
const workspace = {
  id: "99999999-9999-4999-8999-999999999999",
  name: "Synthetic review workspace",
  status: "active",
  role: "owner",
};
const app = {
  id: appId,
  workspace_id: workspace.id,
  created_by_user_id: syntheticUser.id,
  name: "Synthetic storefront",
  description: "Mocked E2E fixture",
  status: "active",
};
const target = {
  id: targetId,
  application_id: appId,
  name: "Synthetic test target",
  environment: "test",
  base_url: "https://target.example.invalid",
  requires_auth: false,
  status: "active",
  allowed_origins: [],
};
const run = {
  id: runId,
  test_number: 42,
  workspace_id: workspace.id,
  application_id: appId,
  target_id: targetId,
  created_by_user_id: syntheticUser.id,
  status: "completed",
  target_snapshot: {
    name: target.name,
    environment: target.environment,
    requires_auth: false,
  },
  configuration_snapshot: {
    test_name: "Synthetic profile review",
    study_brief: "Can a test user update a profile using the documented form?",
    testing_depth: "low",
    execution_mode: "deep_feature_v1",
  },
};
const results = {
  test_run_id: runId,
  report: {
    id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    version: 1,
    status: "completed",
    executive_summary: "Synthetic evidence fixture for UI layout review.",
    payload: { generator: "synthetic_e2e_fixture", schema_version: 1 },
    generated_at: "2026-10-15T12:00:00Z",
  },
  findings: [],
};
const journeys = [
  {
    id: journeyId,
    run_id: runId,
    ordinal: 1,
    persona_name: "Synthetic profile user",
    mission_title: "Update profile preferences",
    step_count: 3,
    artifact_count: 1,
    evidence_available: true,
    summary: "Synthetic journey fixture.",
    success_criteria: ["The preference is saved."],
    execution_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    attempt_number: 1,
    execution_status: "completed",
    outcome: "passed",
    started_at: "2026-10-15T12:00:00Z",
    completed_at: "2026-10-15T12:00:04Z",
    error_message: null,
    result: { summary: "Preference saved in synthetic fixture." },
  },
];
const journeyDetail = {
  journey: journeys[0],
  steps: [
    { id: 11, step_number: 1, action_type: "navigate", action_summary: "Open profile", observation_summary: "Profile opened", status: "completed", started_at: null, completed_at: null },
    { id: 12, step_number: 2, action_type: "fill", action_summary: "Choose email updates", observation_summary: "Control selected", status: "completed", started_at: null, completed_at: null },
    { id: 13, step_number: 3, action_type: "assert", action_summary: "Verify saved state", observation_summary: "Synthetic preference shown", status: "completed", started_at: null, completed_at: null },
  ],
  artifacts: [{
    id: artifactId,
    step_id: 13,
    artifact_type: "screenshot",
    content_type: "image/png",
    size_bytes: 128,
    created_at: "2026-10-15T12:00:04Z",
    kind: "browser_screenshot",
  }],
  findings: [],
  next_after_step: null,
  artifacts_truncated: false,
};
const featureCases = {
  available: true,
  evaluation_pending: false,
  coverage: {
    planned: 2,
    passed: 1,
    failed_assertions: 0,
    blocked: 0,
    inconclusive: 1,
    not_run: 0,
  },
  cases: [
    {
      case_id: "preference-save",
      title: "Save profile preference",
      kind: "positive",
      verdict: "passed",
      recorded_verdict: "passed",
      journey_id: journeyId,
      assertions: [{
        assertion_id: "preference-visible",
        expected_value: "Email updates enabled",
        observed_value: "Email updates enabled",
        status: "passed",
        step_id: 13,
        artifact_ids: [artifactId],
        origin: "approved_requirement",
      }],
    },
    {
      case_id: "preference-cancel",
      title: "Cancel profile preference edit",
      kind: "negative",
      verdict: "inconclusive",
      recorded_verdict: "inconclusive",
      journey_id: journeyId,
      assertions: [{
        assertion_id: "preference-unchanged",
        expected_value: true,
        observed_value: null,
        status: "inconclusive",
        step_id: 12,
        artifact_ids: [],
        origin: "fixture_truth",
      }],
    },
  ],
};
const humanAction = {
  id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
  test_run_id: runId,
  execution_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  browser_session_id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
  request_type: "login",
  status: "pending",
  created_at: "2026-10-15T12:01:00Z",
  expires_at: "2026-10-15T12:06:00Z",
  control_generation: 0,
  lease_id: null,
  lease_expires_at: null,
};
const pendingApproval = {
  id: approvalId,
  action_summary: "Save the synthetic profile preference",
  environment: "test",
  status: "pending",
  expires_at: "2026-10-15T12:10:00Z",
  step_id: 12,
  journey_id: journeyId,
};

async function installWorkspace(page: Page, options: {
  role?: string;
  emptyApplications?: boolean;
  runStatus?: string;
  stressCaseCount?: number;
} = {}) {
  let approvalStatus = "pending";
  const artifactAccessRequests: string[] = [];
  let createRunPayload: Record<string, unknown> | undefined;
  await page.route("https://artifact.example.invalid/**", (route) => route.fulfill({
    status: 200,
    contentType: "image/png",
    body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jf2sAAAAASUVORK5CYII=", "base64"),
  }));
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const roleWorkspace = { ...workspace, role: options.role ?? workspace.role };
    let data: unknown;
    let status = 200;

    if (path === "/api/v1/me") data = syntheticUser;
    else if (path === "/api/v1/workspaces") data = [roleWorkspace];
    else if (path === `/api/v1/workspaces/${workspace.id}/applications`) data = options.emptyApplications ? [] : [app];
    else if (path === `/api/v1/applications/${appId}`) data = app;
    else if (path === `/api/v1/applications/${appId}/targets`) data = [target];
    else if (path === `/api/v1/targets/${targetId}/authorization`) data = { status: "authorized", expires_at: null };
    else if (path === `/api/v1/workspaces/${workspace.id}/ingestion`) data = [];
    else if (path === `/api/v1/applications/${appId}/test-runs`) {
      if (request.method() === "POST") {
        createRunPayload = request.postDataJSON();
        data = { ...run, status: "draft" };
      } else data = [run];
    } else if (path === `/api/v1/test-runs/${runId}`) data = { ...run, status: options.runStatus ?? run.status };
    else if (path === `/api/v1/test-runs/${runId}/results`) data = results;
    else if (path === `/api/v1/test-runs/${runId}/flow`) data = {
      nodes: [
        { id: "plan", kind: "meta", label: "Feature plan", status: "completed" },
        { id: "case-one", kind: "journey", label: "Save profile preference", status: "completed" },
        { id: "collector", kind: "collector", label: "Case collector", status: "completed" },
        { id: "evaluation", kind: "evaluation", label: "Evaluation", status: "completed" },
        { id: "report", kind: "report", label: "Report", status: "completed" },
      ],
      edges: [
        { source: "plan", target: "case-one" },
        { source: "case-one", target: "collector" },
        { source: "collector", target: "evaluation" },
        { source: "evaluation", target: "report" },
      ],
      execution_policy: "once_per_journey",
      revision: "synthetic-ui-fixture",
    };
    else if (path === `/api/v1/test-runs/${runId}/journeys`) data = journeys;
    else if (path === `/api/v1/test-runs/${runId}/collection`) data = {
      collection: { journey_count: 1 }, collected_at: "2026-10-15T12:00:05Z",
    };
    else if (path === `/api/v1/test-runs/${runId}/test-cases`) data = options.stressCaseCount
      ? {
        ...featureCases,
        coverage: { ...featureCases.coverage, planned: options.stressCaseCount },
        cases: Array.from({ length: options.stressCaseCount }, (_, index) => ({
          ...featureCases.cases[0],
          case_id: `stress-case-${index + 1}`,
          title: index === options.stressCaseCount! - 1
            ? "Synthetic case with a deliberately long title that must wrap cleanly within the available detail panel width"
            : `Synthetic feature case ${String(index + 1).padStart(3, "0")}`,
        })),
      }
      : featureCases;
    else if (path === `/api/v1/test-runs/${runId}/hitl-summary`) data = {
      executor_mode: "deterministic_case_steps",
      reused_auth_cases: 4,
      human_requests: { completed: 1 },
      action_approvals: { consumed: 2 },
      role_coverage: [{ role: "shopper", planned: 4, authenticated: 1, executed: 3, passed: 2, blocked: 0, inconclusive: 1, not_run: 1 }],
      inventory: [{ feature_key: "profile-preferences", asserted_cases: 2, not_explored: 0 }],
    };
    else if (path === `/api/v1/test-runs/${runId}/journeys/${journeyId}`) data = journeyDetail;
    else if (path === `/api/v1/test-runs/${runId}/human-actions`) data = options.role === "viewer" || options.role === "member" ? [] : [humanAction];
    else if (path === `/api/v1/test-runs/${runId}/action-approvals`) data = options.role === "viewer" || options.role === "member" ? [] : [{ ...pendingApproval, status: approvalStatus }];
    else if (path === `/api/v1/human-actions/${humanAction.id}/claim`) data = {
      request_id: humanAction.id,
      browser_session_id: humanAction.browser_session_id,
      lease_id: "ffffffff-ffff-4fff-8fff-ffffffffffff",
      lease_token: "synthetic-lease-secret-never-rendered",
      generation: 1,
      expires_at: "2026-10-15T12:06:00Z",
      viewer_available: true,
      viewer_url: "wss://viewer.example.invalid/api/v1/hitl-viewer",
      viewer_ticket: "synthetic-single-use-ticket-never-rendered",
    };
    else if (path === `/api/v1/action-approvals/${approvalId}/decision`) {
      approvalStatus = request.postDataJSON().approved ? "approved" : "rejected";
      data = { id: approvalId, status: approvalStatus };
    } else if (path === `/api/v1/test-runs/${runId}/artifacts/${artifactId}/access`) {
      artifactAccessRequests.push(path);
      data = {
        artifact_id: artifactId,
        artifact_type: "screenshot",
        content_type: "image/png",
        url: "https://artifact.example.invalid/synthetic-temporary-access",
        expires_in_seconds: 30,
      };
    } else if (path === "/api/v1/health/kafka") data = { status: "connected", outbox_relay_enabled: true };
    else {
      status = 404;
      data = { detail: "This synthetic UI fixture has no matching API route." };
    }

    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
  });
  return {
    get artifactAccessRequests() { return artifactAccessRequests; },
    get createRunPayload() { return createRunPayload; },
  };
}

async function checkViewportAndA11y(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(() => window.innerWidth) + 1);
  const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  expect(audit.violations).toEqual([]);
}

const viewportMatrix = [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "mobile", width: 390, height: 844 },
  { name: "small-mobile", width: 320, height: 740 },
];

test("populated feature case inspector and exact More routing reflow across the viewport matrix", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "This test drives its own four viewport matrix.");
  test.setTimeout(90_000);
  await installWorkspace(page);
  const screenshotDirectory = path.resolve(process.cwd(), "../../.local/ui-redesign/screenshots");
  await mkdir(screenshotDirectory, { recursive: true });

  for (const viewport of viewportMatrix) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto(`/runs/${runId}/journeys`);
    await expect(page.getByRole("heading", { name: "Feature cases", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Save profile preference" })).toBeVisible();
    await page.getByRole("button", { name: /Cancel profile preference edit/ }).click();
    await expect(page.getByRole("heading", { name: "Cancel profile preference edit" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open supporting step" })).toHaveAttribute("href", `/runs/${runId}/journeys/${journeyId}?step=12`);
    await checkViewportAndA11y(page);
    await page.screenshot({ path: path.join(screenshotDirectory, `cases-${viewport.width}.png`) });

    const more = page.locator(".run-more-nav summary");
    await expect(more).toBeVisible();
    await more.click();
    await page.getByRole("link", { name: "Activity", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/runs/${runId}/activity$`));
  }
});

test("authenticated artifact metadata loads through the access endpoint at desktop and mobile widths", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "This test drives its own viewport matrix.");
  const fixture = await installWorkspace(page);
  for (const viewport of viewportMatrix) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto(`/runs/${runId}/evidence`);
    await expect(page.getByText(`Artifact ${artifactId}`)).toBeVisible();
    await page.getByRole("button", { name: "View evidence" }).click();
    await expect(page.getByRole("link", { name: "Recorded screenshot evidence" })).toBeVisible();
    expect(fixture.artifactAccessRequests).toContain(`/api/v1/test-runs/${runId}/artifacts/${artifactId}/access`);
    await checkViewportAndA11y(page);
  }
});

test("100-case workbench stress stays usable at 320px and 1440px with keyboard selection and provenance", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "This test drives its own wide and minimum-width viewports.");
  test.setTimeout(90_000);
  await installWorkspace(page, { stressCaseCount: 100 });
  const longTitle = "Synthetic case with a deliberately long title that must wrap cleanly within the available detail panel width";

  for (const viewport of [
    { width: 1440, height: 1000 },
    { width: 320, height: 740 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto(`/runs/${runId}/journeys`);
    await expect(page.getByRole("heading", { name: "Feature cases", exact: true })).toBeVisible();
    if (viewport.width === 1440) {
      const coverage = page.locator(".authenticated-coverage");
      const summary = coverage.locator("summary");
      await expect(summary).toContainText("1 verified handoffs");
      await expect(summary).toContainText("4 reused cases");
      await expect(summary).toContainText("2 consumed approvals");
      await summary.focus();
      await summary.press("Enter");
      await expect.poll(() => coverage.evaluate((element) => (element as HTMLDetailsElement).open)).toBe(true);
      await expect(coverage.getByText(/Role shopper: 1 authenticated/)).toBeVisible();
      await expect(coverage.getByText(/Authentication does not establish full application coverage/)).toBeVisible();
      await summary.press("Enter");
      await expect.poll(() => coverage.evaluate((element) => (element as HTMLDetailsElement).open)).toBe(false);
    }
    const firstCase = page.getByRole("button", { name: /Synthetic feature case 001/ });
    await firstCase.focus();
    await firstCase.press("Enter");
    await expect(page.getByRole("heading", { name: "Synthetic feature case 001" })).toBeVisible();
    await expect(page.locator("dl div").filter({ has: page.locator("dt", { hasText: "Source" }) }).locator("dd")).toHaveText("approved requirement");
    const finalCase = page.getByRole("button", { name: new RegExp(longTitle) });
    await finalCase.focus();
    await finalCase.press("Enter");
    await expect(page.getByRole("heading", { name: longTitle })).toBeVisible();
    if (viewport.width === 320) {
      const list = page.locator(".feature-case-list");
      const listMetrics = await list.evaluate((element) => ({ clientHeight: element.clientHeight, scrollHeight: element.scrollHeight }));
      expect(listMetrics.clientHeight).toBeLessThanOrEqual(360);
      expect(listMetrics.scrollHeight).toBeGreaterThan(listMetrics.clientHeight);
    }
    await checkViewportAndA11y(page);
  }
});

test("pending human request and action approval are explicit without opening the browser viewer", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "This test drives its own viewport matrix.");
  test.setTimeout(90_000);
  await installWorkspace(page, { runStatus: "awaiting_human" });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`/runs/${runId}/overview`);
  await expect(page.getByRole("heading", { name: "A human action is holding this test" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Human Assistance for this test" })).toHaveAttribute("href", `/runs/${runId}/human-action`);
  for (const viewport of viewportMatrix) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto(`/runs/${runId}/human-action`);
    await expect(page.getByRole("heading", { name: "Awaiting human: login" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Take browser control/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: pendingApproval.action_summary })).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve once" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Reject" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open Human Assistance for this test" })).toHaveCount(0);
    await checkViewportAndA11y(page);
    expect(page.url()).not.toContain("ticket");
  }
});

test("non-owner role sees the protected request is paused and receives no HITL controls", async ({ page }) => {
  await installWorkspace(page, { role: "member", runStatus: "awaiting_human" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/runs/${runId}/human-action`);
  await expect(page.getByRole("status")).toContainText("Human browser control and action approvals require an owner or administrator role.");
  await expect(page.getByRole("button", { name: /Take browser control|Cancel request|Release control|Approve once|Reject/ })).toHaveCount(0);
  await checkViewportAndA11y(page);
});

test("claimed synthetic lease renders a usable blank viewer without connecting to the protected browser", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "This test drives its own desktop and minimum-width viewports.");
  await installWorkspace(page, { runStatus: "awaiting_human" });
  let protectedViewerConnections = 0;
  page.on("websocket", (socket) => {
    if (socket.url() === "wss://viewer.example.invalid/api/v1/hitl-viewer") protectedViewerConnections += 1;
  });
  const directory = path.resolve(process.cwd(), "../../.local/ui-redesign/screenshots");
  await mkdir(directory, { recursive: true });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`/runs/${runId}/human-action`);
  await page.getByRole("button", { name: /Take browser control/ }).click();
  const viewer = page.locator(".human-browser-viewer");
  await expect(viewer).toBeVisible();
  await expect(viewer.getByRole("button", { name: "Connect to protected browser" })).toBeVisible();
  const desktopWidth = await viewer.evaluate((element) => element.getBoundingClientRect().width);
  expect(desktopWidth).toBeGreaterThanOrEqual(600);
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    window.scrollTo(0, 0);
  });
  await viewer.screenshot({ path: path.join(directory, "hitl-viewer-blank.png") });
  await page.screenshot({ path: path.join(directory, "hitl-human-action-page-blank.png"), fullPage: true });
  expect(protectedViewerConnections).toBe(0);

  await page.setViewportSize({ width: 320, height: 740 });
  const mobileWidth = await viewer.evaluate((element) => element.getBoundingClientRect().width);
  expect(mobileWidth).toBeGreaterThanOrEqual(240);
  expect(mobileWidth).toBeLessThanOrEqual(320);
  await checkViewportAndA11y(page);
  expect(protectedViewerConnections).toBe(0);
});

test("new test zones reflow and default legacy creation payload stays unchanged", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "This test drives its own viewport matrix.");
  test.setTimeout(90_000);
  const fixture = await installWorkspace(page);
  const screenshotDirectory = path.resolve(process.cwd(), "../../.local/ui-redesign/screenshots");
  await mkdir(screenshotDirectory, { recursive: true });
  for (const viewport of viewportMatrix) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.goto(`/applications/${appId}/runs/new`);
    await expect(page.getByRole("heading", { name: "What to test" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "How to execute" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Security and authorization" })).toBeVisible();
    await expect(page.getByLabel("Testing mode")).toHaveValue("legacy_persona");
    await checkViewportAndA11y(page);
    if (viewport.width === 1440 || viewport.width === 320) {
      await page.screenshot({ path: path.join(screenshotDirectory, `new-run-${viewport.width}.png`) });
    }
  }

  await page.getByLabel("Your testing goal").fill("Can a synthetic user save a profile preference?");
  await page.getByRole("button", { name: "Create test" }).click();
  await expect(page).toHaveURL(new RegExp(`/runs/${runId}/overview$`));
  expect(fixture.createRunPayload).toEqual({
    target_id: targetId,
    study_brief: "Can a synthetic user save a profile preference?",
    knowledge_entry_ids: [],
    testing_depth: "medium",
  });
});

test("capture a synthetic empty overview for visual review", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium", "Capture one safe empty-state image only.");
  await installWorkspace(page, { emptyApplications: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/overview");
  await expect(page.getByRole("heading", { name: "Add your first application" })).toBeVisible();
  await checkViewportAndA11y(page);
  const directory = path.resolve(process.cwd(), "../../.local/ui-redesign/screenshots");
  await mkdir(directory, { recursive: true });
  await page.screenshot({ path: path.join(directory, "workbench-empty-overview.png"), fullPage: true });
});
