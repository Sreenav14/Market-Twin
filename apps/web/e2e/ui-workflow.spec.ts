import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const runId = "11111111-1111-4111-8111-111111111111";
const appId = "22222222-2222-4222-8222-222222222222";
const targetId = "33333333-3333-4333-8333-333333333333";
const findingId = "44444444-4444-4444-8444-444444444444";
const app = {
  id: appId,
  workspace_id: "workspace",
  created_by_user_id: "user",
  name: "Northstar Commerce",
  description: "Customer storefront and checkout",
  status: "active",
};
const run = {
  id: runId,
  test_number: 42,
  workspace_id: "workspace",
  application_id: appId,
  target_id: targetId,
  created_by_user_id: "user",
  status: "completed",
  target_snapshot: {
    name: "Storefront",
    environment: "staging",
    requires_auth: false,
  },
  configuration_snapshot: {
    test_name: "Checkout confidence",
    study_brief: "Can first-time shoppers complete checkout with confidence?",
  },
};
const finding = {
  id: findingId,
  severity: "high",
  category: "journey_failure",
  title: "The checkout journey could not be completed",
  summary:
    "A simulated shopper reached checkout but could not complete the purchase.",
  recommendation:
    "Review the checkout step and its supporting evidence before repeating the test.",
  status: "open",
  journey_ids: ["journey-one"],
  evidence: { step_ids: [12], artifact_ids: ["artifact-one"] },
};
const results = {
  test_run_id: runId,
  report: {
    id: "report",
    version: 1,
    status: "completed",
    executive_summary:
      "Three journeys were evaluated. One high-priority finding needs review before the next release.",
    payload: {
      generator: "deterministic_evaluation_v1",
      schema_version: 1,
      journeys: { total: 3, outcome_counts: { passed: 2, failed: 1 } },
    },
    generated_at: "2026-09-10T10:00:00Z",
  },
  findings: [
    finding,
    {
      ...finding,
      id: "finding-two",
      severity: "low",
      title: "A console error was recorded",
      category: "console_error",
    },
  ],
};

async function mockApi(
  page: Page,
  options: {
    resultsStatus?: number;
    targetError?: boolean;
    role?: string;
    empty?: boolean;
    runStatus?: string;
    listRunStatus?: string;
    emptyWorkspace?: boolean;
    emptyRuns?: boolean;
    brief?: string;
  } = {},
) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown;
    let status = 200;
    if (path === "/api/v1/health/kafka")
      data = { status: "connected", outbox_relay_enabled: true };
    else if (path === "/api/v1/me")
      data = {
        id: "user",
        email: "researcher@example.com",
        normalized_email: "researcher@example.com",
        display_name: "Morgan Lee",
      };
    else if (path === "/api/v1/workspaces")
      data = [
        {
          id: "workspace",
          name: "Northstar team",
          role: options.role || "owner",
          status: "active",
        },
      ];
    else if (path === "/api/v1/workspaces/workspace/applications")
      data = options.emptyWorkspace ? [] : [app];
    else if (path === "/api/v1/workspaces/workspace/ingestion") data = [];
    else if (path === `/api/v1/applications/${appId}`) data = app;
    else if (path === `/api/v1/applications/${appId}/targets`) {
      if (options.targetError) {
        status = 500;
        data = { detail: "Targets are temporarily unavailable." };
      } else
        data = [
          {
            id: targetId,
            application_id: appId,
            name: "Storefront",
            environment: "staging",
            base_url: "https://shop.example.com",
            requires_auth: false,
            status: "active",
            allowed_origins: [],
          },
        ];
    } else if (path === `/api/v1/targets/${targetId}/authorization`)
      data = {
        id: "authorization",
        target_id: targetId,
        status: "authorized",
        expires_at: null,
      };
    else if (path === `/api/v1/applications/${appId}/test-runs`)
      data =
        route.request().method() === "POST"
          ? { ...run, status: "draft" }
          : options.emptyRuns
            ? []
            : [{ ...run, status: options.listRunStatus || "completed",
                configuration_snapshot: { ...run.configuration_snapshot, study_brief: options.brief || run.configuration_snapshot.study_brief } }];
    else if (path === `/api/v1/test-runs/${runId}`)
      data = { ...run, status: options.runStatus || "completed",
        configuration_snapshot: { ...run.configuration_snapshot, study_brief: options.brief || run.configuration_snapshot.study_brief } };
    else if (path === `/api/v1/test-runs/${runId}/flow`) data = { nodes: [], edges: [], revision: "fixture", execution_policy: "once_per_journey" };
    else if (path === `/api/v1/test-runs/${runId}/results`) {
      status = options.resultsStatus || 200;
      data =
        status === 200
          ? { ...results, findings: options.empty ? [] : results.findings }
          : {
              detail:
                status === 409
                  ? "Evaluation results are not available yet."
                  : "You do not have access to these results.",
            };
    } else {
      status = 404;
      data = { detail: "Not available in this fixture." };
    }
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(data),
    });
  });
}
async function checkLayoutAndAccessibility(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
  expect(overflow).toBe(false);
  const audit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(audit.violations).toEqual([]);
}

test("repeated persona claims stay under Needs Verification and out of confirmed totals", async ({ page }, testInfo) => {
  await mockApi(page);
  const observations = [
    { ...finding, id: "repeated-claim", category: "cross_persona_pattern", severity: "info",
      finding_kind: "not_verified", verification_status: "unverified",
      title: "Repeated agent-reported unmet criterion: Confirmation visible",
      summary: "Two personas reported the same unmet criterion. Agreement between synthetic personas is not independent verification.",
      journey_ids: ["journey-one", "journey-two"] },
    { ...finding, id: "missing-evidence", title: "Agent reported failure without evidence",
      finding_kind: "not_verified", verification_status: "unverified",
      evidence: { step_ids: [], artifact_ids: [] } },
    { ...finding, id: "visual-issue", category: "visual_criterion", severity: "medium",
      finding_kind: "observed_product_issue", verification_status: "verified_visual",
      title: "Visual criterion not satisfied: Heading readable",
      summary: "Visual verification found the heading clipped in the cited screenshot." },
  ];
  await page.route(`**/api/v1/test-runs/${runId}/results`, (route) => route.fulfill({
    contentType: "application/json", body: JSON.stringify({ ...results,
      report: { ...results.report, executive_summary: "One visually verified issue and two observations needing verification." },
      findings: observations,
    }),
  }));
  await page.route(`**/api/v1/test-runs/${runId}/flow`, (route) => route.fulfill({
    contentType: "application/json", body: JSON.stringify({
      nodes: [
        { id: "meta", kind: "meta", label: "Meta Agent", status: "completed" },
        { id: "journey:one", kind: "journey", label: "First-time buyer · Checkout", status: "completed" },
        { id: "journey:two", kind: "journey", label: "Returning buyer · Checkout", status: "completed" },
        { id: "journey:three", kind: "journey", label: "Guest shopper · Checkout", status: "completed" },
        { id: "collector", kind: "collector", label: "Collector", status: "completed" },
        { id: "evaluation", kind: "evaluation", label: "Evaluation", status: "completed" },
        { id: "report", kind: "report", label: "Report", status: "completed" },
      ], edges: [
        { source: "meta", target: "journey:one" },
        { source: "journey:one", target: "journey:two" },
        { source: "journey:two", target: "journey:three" },
        { source: "journey:three", target: "collector" },
        { source: "collector", target: "evaluation" },
        { source: "evaluation", target: "report" },
      ], execution_policy: "once_per_journey", revision: "verification-test-fixture",
    }),
  }));
  await page.goto(`/runs/${runId}/findings`);
  await expect(page.getByText("1 confirmed · 3 total records")).toBeVisible();
  const unverified = page.getByRole("region", { name: "Needs Verification" });
  await expect(unverified.getByRole("button", { name: new RegExp(observations[0].title) })).toBeVisible();
  await expect(unverified.getByRole("button", { name: new RegExp(observations[1].title) })).toBeVisible();
  await expect(unverified.getByRole("button", { name: new RegExp(observations[2].title) })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Confirmed issues" }).getByRole("button", { name: new RegExp(observations[2].title) })).toBeVisible();
  await checkLayoutAndAccessibility(page);
  await page.screenshot({ path: `../../artifacts/v1/needs-verification-${testInfo.project.name}.png`, fullPage: true });
  await unverified.getByRole("button", { name: new RegExp(observations[1].title) }).click();
  await page.getByRole("link", { name: "Open finding details" }).click();
  await expect(page.getByText(/No evidence references were attached/)).toBeVisible();
  await page.getByRole("navigation", { name: "Test sections" }).getByRole("link", { name: "Report" }).click();
  await expect(page.getByText("1 confirmed issues. Severity totals below include confirmed issues only.")).toBeVisible();
  await expect(page.locator(".severity-summary").getByText("0", { exact: true })).toHaveCount(4);
});

test("completed test: triage, detail and report", async ({
  page,
}, testInfo) => {
  await mockApi(page);
  await page.goto(`/runs/${runId}/overview`);
  await expect(
    page.getByRole("heading", { name: "2 findings to review" }),
  ).toBeVisible();
  await expect(page.getByText("Planning is not connected yet.")).toHaveCount(0);
  await checkLayoutAndAccessibility(page);
  await page.screenshot({
    path: testInfo.outputPath("overview.png"),
    fullPage: true,
  });
  await page
    .getByRole("navigation", { name: "Test sections" })
    .getByRole("link", { name: /Findings/ })
    .click();
  await page.getByLabel("Severity", { exact: true }).selectOption("high");
  await expect(page).toHaveURL(/severity=high/);
  const selectedFinding = page.getByRole("button", { name: new RegExp(finding.title) });
  await expect(selectedFinding).toBeVisible();
  await expect(
    page.getByRole("button", { name: /A console error was recorded/ }),
  ).toHaveCount(0);
  await checkLayoutAndAccessibility(page);
  await page.screenshot({
    path: testInfo.outputPath("findings.png"),
    fullPage: true,
  });
  await selectedFinding.click();
  await page.getByRole("link", { name: "Open finding details" }).click();
  await expect(
    page.getByRole("heading", { name: "Recommendation", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("artifact-one", { exact: true })).toBeVisible();
  await checkLayoutAndAccessibility(page);
  await page
    .getByRole("navigation", { name: "Test sections" })
    .getByRole("link", { name: "Report" })
    .click();
  await expect(
    page.getByRole("heading", { name: "What this test found" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Journey outcomes" }),
  ).toBeVisible();
  await checkLayoutAndAccessibility(page);
  await page.screenshot({
    path: testInfo.outputPath("report.png"),
    fullPage: true,
  });
});

test("409 is an evaluation waiting state", async ({ page }) => {
  await mockApi(page, { resultsStatus: 409 });
  await page.goto(`/runs/${runId}/findings`);
  await expect(
    page.getByRole("heading", { name: "Preparing evaluation" }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("pending evaluation automatically displays the persisted report when ready", async ({ page }) => {
  test.setTimeout(60_000);
  await mockApi(page);
  let ready = false;
  let requests = 0;
  await page.route(`**/api/v1/test-runs/${runId}/results`, (route) => {
    requests += 1;
    return route.fulfill({
      status: ready ? 200 : 409,
      json: ready ? results : {
        detail: "Test run execution completed, but evaluation results are not available yet.",
      },
    });
  });
  await page.goto(`/runs/${runId}/report`);
  await expect(page.getByRole("heading", { name: "Preparing evaluation" })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  ready = true;
  await expect(page.getByRole("heading", { name: "What this test found" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(results.report.executive_summary, { exact: true })).toBeVisible();
  expect(requests).toBeGreaterThan(1);
  await checkLayoutAndAccessibility(page);
});

test("forbidden results show a recoverable error", async ({ page }) => {
  await mockApi(page, { resultsStatus: 403 });
  await page.goto(`/runs/${runId}/report`);
  await expect(page.getByRole("alert")).toContainText("You do not have access");
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
});

test("a waiting evaluation can recover or surface a later permission error", async ({
  page,
}) => {
  await mockApi(page, { resultsStatus: 409 });
  await page.goto(`/runs/${runId}/findings`);
  await expect(
    page.getByRole("heading", { name: "Preparing evaluation" }),
  ).toBeVisible();
  await page.route(`**/api/v1/test-runs/${runId}/results`, (route) =>
    route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "Access changed. Contact your administrator.",
      }),
    }),
  );
  await page.getByRole("button", { name: "Check again" }).click();
  await expect(page.getByRole("alert")).toContainText("Access changed.");
});

test("empty evaluation is honest about scope", async ({ page }) => {
  await mockApi(page, { empty: true });
  await page.goto(`/runs/${runId}/findings`);
  await expect(
    page.getByRole("heading", { name: "No findings in this evaluation" }),
  ).toBeVisible();
});

test("test creation sends a real request with the chosen brief", async ({
  page,
}, testInfo) => {
  await mockApi(page);
  await page.goto(`/applications/${appId}/runs/new`);
  await expect(page.getByLabel("Your testing goal")).toBeVisible();
  await page.getByLabel("Test name", { exact: false }).fill("Pricing clarity");
  await expect(page.getByLabel("Testing depth")).toHaveValue("medium");
  await page.getByLabel("Testing depth").selectOption("low");
  await expect(page.locator("#testing-depth-help")).toContainText("1 mission (3 journeys)");
  await page
    .getByRole("button", { name: "Pricing clarity", exact: true })
    .click();
  await expect(page.getByLabel("Your testing goal")).toHaveValue(
    /first-time customer/,
  );
  await checkLayoutAndAccessibility(page);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({
    path: testInfo.outputPath("new-test.png"),
    fullPage: true,
  });
  const request = page.waitForRequest(
    (req) => req.method() === "POST" && req.url().includes("/test-runs"),
  );
  await page.getByRole("button", { name: "Create test", exact: true }).click();
  expect((await request).postDataJSON()).toEqual({
    target_id: targetId,
    knowledge_entry_ids: [],
    testing_depth: "low",
    name: "Pricing clarity",
    study_brief:
      "Can a first-time customer understand our pricing and confidently choose the right plan?",
  });
  await expect(page).toHaveURL(new RegExp(`/runs/${runId}/overview`));
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("MT-000042 · Checkout confidence");
});

test("target fetch failure cannot trap the test form in loading", async ({
  page,
}) => {
  await mockApi(page, { targetError: true });
  await page.goto(`/applications/${appId}/runs/new`);
  await expect(page.getByRole("alert")).toContainText(
    "Targets are temporarily unavailable.",
  );
});

test("read-only users cannot create tests", async ({ page }) => {
  await mockApi(page, { role: "viewer" });
  await page.goto(`/applications/${appId}/runs/new`);
  await expect(
    page.getByRole("heading", { name: "Read-only workspace" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Create test", exact: true }),
  ).toHaveCount(0);
});

test("workspace navigation supports keyboard and mobile", async ({
  page,
}, testInfo) => {
  await mockApi(page);
  await page.goto("/overview");
  await expect(
    page.getByRole("heading", { name: "Workspace overview" }),
  ).toBeVisible();
  await checkLayoutAndAccessibility(page);
  await page.screenshot({
    path: testInfo.outputPath("workspace.png"),
    fullPage: true,
  });
  await page.keyboard.press("Control+k");
  await expect(
    page.getByRole("dialog", { name: "Quick navigation" }),
  ).toBeVisible();
  await checkLayoutAndAccessibility(page);
  await page.getByLabel("Search pages").fill("tests");
  await page
    .getByRole("navigation", { name: "Navigation results" })
    .getByRole("link", { name: /^Tests / })
    .click();
  await expect(page).toHaveURL(/\/runs$/);
  await expect(
    page.getByRole("heading", { name: "Tests", exact: true }),
  ).toBeVisible();
});

for (const item of [
  {
    kind: "test",
    id: runId,
    page: "/runs",
    endpoint: `/api/v1/test-runs/${runId}`,
    list: `/api/v1/applications/${appId}/test-runs`,
  },
  {
    kind: "target",
    id: targetId,
    page: `/applications/${appId}/targets`,
    endpoint: `/api/v1/targets/${targetId}`,
    list: `/api/v1/applications/${appId}/targets`,
  },
  {
    kind: "application",
    id: appId,
    page: "/applications",
    endpoint: `/api/v1/applications/${appId}`,
    list: "/api/v1/workspaces/workspace/applications",
  },
]) {
  test(`delete ${item.kind} requires confirmation and removes the row after success`, async ({
    page,
  }) => {
    await mockApi(page, item.kind === "test" ? { listRunStatus: "draft" } : {});
    let deleted = false;
    await page.route("**/api/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === item.endpoint && route.request().method() === "DELETE") {
        deleted = true;
        await route.fulfill({ status: 204 });
        return;
      }
      if (deleted && path === item.list) {
        await route.fulfill({ json: [] });
        return;
      }
      await route.fallback();
    });
    await page.goto(item.page);
    const trigger = page.getByRole("button", {
      name: new RegExp(`^Delete ${item.kind}:`),
    });
    await trigger.click();
    await expect(
      page.getByRole("button", { name: "Cancel", exact: true }),
    ).toBeFocused();
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    expect(deleted).toBe(false);
    await trigger.click();
    await checkLayoutAndAccessibility(page);
    await page
      .getByRole("button", { name: `Delete ${item.kind}`, exact: true })
      .click();
    await expect(trigger).toHaveCount(0);
    expect(deleted).toBe(true);
    await page.reload();
    await expect(trigger).toHaveCount(0);
  });
}
test("delete conflict preserves the target and shows the server message", async ({
  page,
}) => {
  await mockApi(page);
  await page.route(`**/api/v1/targets/${targetId}`, (route) =>
    route.fulfill({
      status: 409,
      json: { detail: "Delete this target's tests first." },
    }),
  );
  await page.goto(`/applications/${appId}/targets`);
  await page.getByRole("button", { name: "Delete target: Storefront" }).click();
  await page
    .getByRole("button", { name: "Delete target", exact: true })
    .click();
  await expect(page.getByRole("alert")).toContainText(
    "Delete this target's tests first.",
  );
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByRole("link", { name: /Storefront/ })).toBeVisible();
});
test("viewers have no delete actions and started tests cannot be deleted", async ({
  page,
}) => {
  await mockApi(page, { role: "viewer" });
  await page.goto("/runs");
  await expect(
    page.getByRole("heading", { name: "Tests", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /^Delete/ })).toHaveCount(0);
  await mockApi(page, { runStatus: "running" });
  await page.goto(`/runs/${runId}/overview`);
  await expect(
    page.getByRole("button", { name: /^Delete test:/ }),
  ).toBeDisabled();
});

test("queued tests do not claim planning is complete", async ({ page }) => {
  await mockApi(page, { runStatus: "queued" });
  await page.goto(`/runs/${runId}/overview`);
  const planning = page.locator(".lifecycle-rail li").filter({ hasText: "Planning" });
  await expect(planning).toHaveClass("stage-current");
  await expect(planning).toContainText("Current stage");
  await expect(page.locator(".lifecycle-rail li").filter({ hasText: "Execution" }))
    .toContainText("Up next");
});

test("active workspace tests refresh to completed without navigation", async ({ page }) => {
  await mockApi(page, { listRunStatus: "running" });
  let requests = 0;
  await page.route(`**/api/v1/applications/${appId}/test-runs`, (route) => {
    requests += 1;
    return route.fulfill({ json: [{ ...run, status: requests === 1 ? "running" : "completed" }] });
  });
  await page.goto("/overview");
  await expect(page.locator(".study-row .status-badge")).toHaveText("running");
  await expect(page.locator(".metric-signal")).toHaveCount(1);
  await expect(page.locator(".study-row .status-badge"))
    .toHaveText("completed", { timeout: 10_000 });
  await expect(page.locator(".metric-signal")).toHaveCount(0);
});

test("starting a draft updates status and continues polling", async ({ page }) => {
  await mockApi(page);
  let started = false;
  let polls = 0;
  await page.route(`**/api/v1/test-runs/${runId}/start`, (route) => {
    started = true;
    return route.fulfill({ json: { ...run, status: "queued" } });
  });
  await page.route(`**/api/v1/test-runs/${runId}`, (route) => {
    if (started) polls += 1;
    return route.fulfill({ json: { ...run, status: !started ? "draft" : polls === 1 ? "queued" : "completed" } });
  });
  await page.goto(`/runs/${runId}/overview`);
  await expect(page.getByText("Kafka connected", { exact: true })).toBeVisible();
  const startSize = await page.getByRole("button", { name: "Start test", exact: true }).boundingBox();
  const deleteSize = await page.getByRole("button", { name: /^Delete test:/ }).boundingBox();
  expect(startSize?.height).toBe(deleteSize?.height);
  await page.getByRole("button", { name: "Start test", exact: true }).click();
  await expect(page.getByText("Kafka connected", { exact: true })).toHaveCount(0);
  await expect(page.locator(".page-action .status-badge")).toHaveText("queued");
  await expect(page.locator(".page-action .status-badge"))
    .toHaveText("completed", { timeout: 10_000 });
  await expect(page.getByRole("heading", { name: "2 findings to review" })).toBeVisible();
});

test("expired target authorization is visible and does not offer an authorized test", async ({ page }) => {
  await mockApi(page);
  await page.route(`**/api/v1/targets/${targetId}`, (route) => route.fulfill({ json: {
    id: targetId, application_id: appId, name: "Storefront", environment: "staging",
    base_url: "https://shop.example.com", requires_auth: false, status: "active", allowed_origins: [],
  } }));
  await page.route(`**/api/v1/targets/${targetId}/authorization`, (route) => route.fulfill({ json: {
    id: "authorization", target_id: targetId, status: "authorized", expires_at: "2020-01-01T00:00:00Z",
  } }));
  await page.goto(`/targets/${targetId}`);
  await expect(page.getByText("expired", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "New test", exact: true })).toHaveCount(0);
  await checkLayoutAndAccessibility(page);
});

test("empty workspace and tests offer clear next actions", async ({ page }) => {
  await mockApi(page, { emptyWorkspace: true });
  await page.goto("/overview");
  await expect(page.getByRole("heading", { name: "Add your first application" })).toBeVisible();
  await checkLayoutAndAccessibility(page);
  await mockApi(page, { emptyRuns: true });
  await page.goto("/runs");
  await expect(page.getByRole("heading", { name: "No tests yet" })).toBeVisible();
  await checkLayoutAndAccessibility(page);
});

test("reduced motion disables decorative transitions", async ({ page }) => {
  await mockApi(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/overview");
  const trigger = page.getByRole("button", { name: "Open quick navigation" });
  await expect(trigger).toBeVisible();
  expect(await trigger.evaluate((element) => getComputedStyle(element).transitionDuration)).toBe("0s");
  await trigger.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(await page.locator(".dialog-overlay").evaluate((element) => getComputedStyle(element).animationName))
    .toBe("none");
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
});

for (const path of ["/overview", "/runs", `/applications/${appId}/runs/new`, `/runs/${runId}/overview`]) {
  test(`320px reflow with long content: ${path}`, async ({ page }) => {
    await mockApi(page, { brief: "Review the complete checkout journey for a first-time customer. ".repeat(8) });
    await page.setViewportSize({ width: 320, height: 780 });
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByText("Kafka connected", { exact: true })).toHaveCount(0);
    await checkLayoutAndAccessibility(page);
  });
}

test("320px draft controls stay usable and Start matches other button heights", async ({ page }, testInfo) => {
  await mockApi(page, { runStatus: "draft" });
  await page.setViewportSize({ width: 320, height: 780 });
  await page.goto(`/runs/${runId}/overview`);
  await expect(page.getByText("Kafka connected", { exact: true })).toBeVisible();
  const start = await page.getByRole("button", { name: "Start test", exact: true }).boundingBox();
  const remove = await page.getByRole("button", { name: /^Delete test:/ }).boundingBox();
  expect(start?.height).toBe(remove?.height);
  expect(start?.width).toBeLessThan(180);
  await checkLayoutAndAccessibility(page);
  await page.screenshot({ path: testInfo.outputPath("start-test-narrow.png"), fullPage: true });
});

for (const path of ["/overview", "/runs"]) {
  test(`background refresh failure preserves data and retry recovers: ${path}`, async ({ page }) => {
    await mockApi(page);
    let requests = 0;
    let failing = true;
    await page.route(`**/api/v1/applications/${appId}/test-runs`, (route) => {
      requests += 1;
      return requests > 1 && failing
        ? route.fulfill({ status: 503, json: { detail: "Temporary outage" } })
        : route.fulfill({ json: [{ ...run, status: failing ? "running" : "completed" }] });
    });
    await page.goto(path);
    await expect(page.locator(".study-row .status-badge")).toHaveText("running");
    await expect(page.getByRole("alert")).toContainText("Showing the last loaded data", { timeout: 15_000 });
    await expect(page.locator(".study-row .status-badge")).toHaveText("running");
    failing = false;
    await page.getByRole("button", { name: "Try again", exact: true }).click();
    await expect(page.locator(".study-row .status-badge")).toHaveText("completed");
    await expect(page.getByRole("alert")).toHaveCount(0);
  });
}
