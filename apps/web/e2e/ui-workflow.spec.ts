import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const runId = "11111111-1111-4111-8111-111111111111";
const appId = "22222222-2222-4222-8222-222222222222";
const targetId = "33333333-3333-4333-8333-333333333333";
const findingId = "44444444-4444-4444-8444-444444444444";
const app = { id: appId, workspace_id: "workspace", created_by_user_id: "user", name: "Northstar Commerce", description: "Customer storefront and checkout", status: "active" };
const run = { id: runId, workspace_id: "workspace", application_id: appId, target_id: targetId, created_by_user_id: "user", status: "completed", target_snapshot: { name: "Storefront", environment: "staging", requires_auth: false }, configuration_snapshot: { study_brief: "Can first-time shoppers complete checkout with confidence?" } };
const finding = { id: findingId, severity: "high", category: "journey_failure", title: "The checkout journey could not be completed", summary: "A simulated shopper reached checkout but could not complete the purchase.", recommendation: "Review the checkout step and its supporting evidence before repeating the test.", status: "open", journey_ids: ["journey-one"], evidence: { step_ids: [12], artifact_ids: ["artifact-one"] } };
const results = { test_run_id: runId, report: { id: "report", version: 1, status: "completed", executive_summary: "Three journeys were evaluated. One high-priority finding needs review before the next release.", payload: { generator: "deterministic_evaluation_v1", schema_version: 1, journeys: { total: 3, outcome_counts: { passed: 2, failed: 1 } } }, generated_at: "2026-09-10T10:00:00Z" }, findings: [finding, { ...finding, id: "finding-two", severity: "low", title: "A console error was recorded", category: "console_error" }] };

async function mockApi(page: Page, options: { resultsStatus?: number; targetError?: boolean; role?: string; empty?: boolean; runStatus?: string } = {}) {
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown;
    let status = 200;
    if (path === "/api/v1/me") data = { id: "user", email: "researcher@example.com", normalized_email: "researcher@example.com", display_name: "Morgan Lee" };
    else if (path === "/api/v1/workspaces") data = [{ id: "workspace", name: "Northstar team", role: options.role || "owner", status: "active" }];
    else if (path === "/api/v1/workspaces/workspace/applications") data = [app];
    else if (path === `/api/v1/applications/${appId}`) data = app;
    else if (path === `/api/v1/applications/${appId}/targets`) {
      if (options.targetError) { status = 500; data = { detail: "Targets are temporarily unavailable." }; }
      else data = [{ id: targetId, application_id: appId, name: "Storefront", environment: "staging", base_url: "https://shop.example.com", requires_auth: false, status: "active", allowed_origins: [] }];
    }
    else if (path === `/api/v1/targets/${targetId}/authorization`) data = { id: "authorization", target_id: targetId, status: "authorized", expires_at: null };
    else if (path === `/api/v1/applications/${appId}/test-runs`) data = route.request().method() === "POST" ? { ...run, status: "created" } : [run];
    else if (path === `/api/v1/test-runs/${runId}`) data = { ...run, status: options.runStatus || "completed" };
    else if (path === `/api/v1/test-runs/${runId}/results`) {
      status = options.resultsStatus || 200;
      data = status === 200 ? { ...results, findings: options.empty ? [] : results.findings } : { detail: status === 409 ? "Evaluation results are not available yet." : "You do not have access to these results." };
    } else { status = 404; data = { detail: "Not available in this fixture." }; }
    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
  });
}
async function checkLayoutAndAccessibility(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  expect(overflow).toBe(false);
  const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(audit.violations).toEqual([]);
}

test("completed test: triage, detail and report", async ({ page }, testInfo) => {
  await mockApi(page);
  await page.goto(`/runs/${runId}/overview`);
  await expect(page.getByRole("heading", { name: "2 findings to review" })).toBeVisible();
  await expect(page.getByText("Planning is not connected yet.")).toHaveCount(0);
  await checkLayoutAndAccessibility(page);
  await mkdir("../../docs/ui-review", { recursive: true });
  await page.screenshot({ path: `../../docs/ui-review/overview-${testInfo.project.name}.png`, fullPage: true });
  await page.getByRole("navigation", { name: "Test sections" }).getByRole("link", { name: /Findings/ }).click();
  await page.getByLabel("Severity", { exact: true }).selectOption("high");
  await expect(page).toHaveURL(/severity=high/);
  await expect(page.getByRole("heading", { name: finding.title })).toBeVisible();
  await expect(page.getByRole("heading", { name: "A console error was recorded" })).toHaveCount(0);
  await checkLayoutAndAccessibility(page);
  await page.screenshot({ path: `../../docs/ui-review/findings-${testInfo.project.name}.png`, fullPage: true });
  await page.getByRole("heading", { name: finding.title }).click();
  await expect(page.getByRole("heading", { name: "Recommendation", exact: true })).toBeVisible();
  await expect(page.getByText("artifact-one", { exact: true })).toBeVisible();
  await checkLayoutAndAccessibility(page);
  await page.getByRole("navigation", { name: "Test sections" }).getByRole("link", { name: "Report" }).click();
  await expect(page.getByRole("heading", { name: "What this test found" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Journey outcomes" })).toBeVisible();
  await checkLayoutAndAccessibility(page);
  await page.screenshot({ path: `../../docs/ui-review/report-${testInfo.project.name}.png`, fullPage: true });
});

test("409 is an evaluation waiting state", async ({ page }) => {
  await mockApi(page, { resultsStatus: 409 });
  await page.goto(`/runs/${runId}/findings`);
  await expect(page.getByRole("heading", { name: "Evaluation is not available yet" })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("forbidden results show a recoverable error", async ({ page }) => {
  await mockApi(page, { resultsStatus: 403 });
  await page.goto(`/runs/${runId}/report`);
  await expect(page.getByRole("alert")).toContainText("You do not have access");
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
});

test("a waiting evaluation can recover or surface a later permission error", async ({ page }) => {
  await mockApi(page, { resultsStatus: 409 });
  await page.goto(`/runs/${runId}/findings`);
  await expect(page.getByRole("heading", { name: "Evaluation is not available yet" })).toBeVisible();
  await page.route(`**/api/v1/test-runs/${runId}/results`, route => route.fulfill({
    status: 403, contentType: "application/json", body: JSON.stringify({ detail: "Access changed. Contact your administrator." }),
  }));
  await page.getByRole("button", { name: "Check again" }).click();
  await expect(page.getByRole("alert")).toContainText("Access changed.");
});

test("empty evaluation is honest about scope", async ({ page }) => {
  await mockApi(page, { empty: true });
  await page.goto(`/runs/${runId}/findings`);
  await expect(page.getByRole("heading", { name: "No findings in this evaluation" })).toBeVisible();
});

test("test creation sends a real request with the chosen brief", async ({ page }, testInfo) => {
  await mockApi(page);
  await page.goto(`/applications/${appId}/runs/new`);
  await expect(page.getByLabel("Your testing goal")).toBeVisible();
  await page.getByRole("button", { name: "Pricing clarity", exact: true }).click();
  await expect(page.getByLabel("Your testing goal")).toHaveValue(/first-time customer/);
  await checkLayoutAndAccessibility(page);
  await mkdir("../../docs/ui-review", { recursive: true });
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({ path: `../../docs/ui-review/new-study-${testInfo.project.name}.png`, fullPage: true });
  const request = page.waitForRequest(req => req.method() === "POST" && req.url().includes("/test-runs"));
  await page.getByRole("button", { name: "Create test", exact: true }).click();
  expect((await request).postDataJSON()).toEqual({ target_id: targetId, study_brief: "Can a first-time customer understand our pricing and confidently choose the right plan?" });
  await expect(page).toHaveURL(new RegExp(`/runs/${runId}/overview`));
});

test("target fetch failure cannot trap the test form in loading", async ({ page }) => {
  await mockApi(page, { targetError: true });
  await page.goto(`/applications/${appId}/runs/new`);
  await expect(page.getByRole("alert")).toContainText("Targets are temporarily unavailable.");
});

test("read-only users cannot create tests", async ({ page }) => {
  await mockApi(page, { role: "viewer" });
  await page.goto(`/applications/${appId}/runs/new`);
  await expect(page.getByRole("heading", { name: "Read-only workspace" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Create test", exact: true })).toHaveCount(0);
});

test("workspace navigation supports keyboard and mobile", async ({ page }, testInfo) => {
  await mockApi(page);
  await page.goto("/overview");
  await expect(page.getByRole("heading", { name: "Workspace overview" })).toBeVisible();
  await checkLayoutAndAccessibility(page);
  await mkdir("../../docs/ui-review", { recursive: true });
  await page.screenshot({ path: `../../docs/ui-review/workspace-${testInfo.project.name}.png`, fullPage: true });
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("dialog", { name: "Quick navigation" })).toBeVisible();
  await checkLayoutAndAccessibility(page);
  await page.getByLabel("Search pages").fill("tests");
  await page.getByRole("navigation", { name: "Navigation results" }).getByRole("link").click();
  await expect(page).toHaveURL(/\/runs$/);
  await expect(page.getByRole("heading", { name: "Tests", exact: true })).toBeVisible();
});

for (const item of [
  { kind: "test", id: runId, page: "/runs", endpoint: `/api/v1/test-runs/${runId}`, list: `/api/v1/applications/${appId}/test-runs` },
  { kind: "target", id: targetId, page: `/applications/${appId}/targets`, endpoint: `/api/v1/targets/${targetId}`, list: `/api/v1/applications/${appId}/targets` },
  { kind: "application", id: appId, page: "/applications", endpoint: `/api/v1/applications/${appId}`, list: "/api/v1/workspaces/workspace/applications" },
]) {
  test(`delete ${item.kind} requires confirmation and removes the row after success`, async ({ page }) => {
    await mockApi(page);
    let deleted = false;
    await page.route("**/api/v1/**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (path === item.endpoint && route.request().method() === "DELETE") {
        deleted = true; await route.fulfill({ status: 204 }); return;
      }
      if (deleted && path === item.list) {
        await route.fulfill({ json: [] }); return;
      }
      await route.fallback();
    });
    await page.goto(item.page);
    const trigger = page.getByRole("button", { name: new RegExp(`^Delete ${item.kind}:`) });
    await trigger.click();
    await expect(page.getByRole("button", { name: "Cancel", exact: true })).toBeFocused();
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    expect(deleted).toBe(false);
    await trigger.click();
    await checkLayoutAndAccessibility(page);
    await page.getByRole("button", { name: `Delete ${item.kind}`, exact: true }).click();
    await expect(trigger).toHaveCount(0);
    expect(deleted).toBe(true);
    await page.reload();
    await expect(trigger).toHaveCount(0);
  });
}
test("delete conflict preserves the target and shows the server message", async ({ page }) => {
  await mockApi(page);
  await page.route(`**/api/v1/targets/${targetId}`, route => route.fulfill({ status: 409, json: { detail: "Delete this target's tests first." } }));
  await page.goto(`/applications/${appId}/targets`);
  await page.getByRole("button", { name: "Delete target: Storefront" }).click();
  await page.getByRole("button", { name: "Delete target", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Delete this target's tests first.");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByRole("link", { name: /Storefront/ })).toBeVisible();
});
test("viewers have no delete actions and running tests cannot be deleted", async ({ page }) => {
  await mockApi(page, { role: "viewer" });
  await page.goto("/runs");
  await expect(page.getByRole("heading", { name: "Tests", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Delete/ })).toHaveCount(0);
  await mockApi(page, { runStatus: "running" });
  await page.goto(`/runs/${runId}/overview`);
  await expect(page.getByRole("button", { name: /^Delete test:/ })).toBeDisabled();
});
