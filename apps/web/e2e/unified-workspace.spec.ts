import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// These records exist only in intercepted browser-test responses.
const application = { id: "app", workspace_id: "workspace", created_by_user_id: "user", name: "Catalog fixture", description: "Browser layout fixture", status: "active" };
const target = { id: "target", application_id: "app", name: "Catalog staging", environment: "staging", base_url: "https://catalog.example.test", requires_auth: false, status: "active", allowed_origins: [{ scheme: "https", hostname: "catalog.example.test", port: null, include_subdomains: false }] };
const run = { id: "test", test_number: 1, workspace_id: "workspace", application_id: "app", target_id: "target", created_by_user_id: "user", status: "completed", created_at: "2026-11-02T12:00:00Z", target_snapshot: target, configuration_snapshot: { test_name: "Catalog search", study_brief: "Check catalog search", execution_mode: "discovery_contract_v1", discovery_stage: "completed", discovery_map: { features: [{ name: "Search" }], journeys: [{ journey_key: "search", completed: true }] } } };
const report = { test_run_id: "test", findings: [], report: { id: "report", version: 1, status: "completed", generated_at: null, executive_summary: "Search could not be checked again.", payload: { mode: "discovery_contract_v1", coverage: { tested_features: 1, discovered_features: 1 }, what_works: [], confirmed: [], unverified: [{ check: "Search completion", reason: "replay_unavailable" }], market_verdict: { verdict: "insufficient_evidence", journeys_executed: 1, journeys_approved: 1, confirmed_defects: 0, persona_means: {} } } } };

async function fixture(page: Page) {
  const unexpected: string[] = [];
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const responses: Record<string, unknown> = {
      "/api/v1/me": { id: "user", email: "reviewer@example.test", normalized_email: "reviewer@example.test", display_name: "Layout reviewer" },
      "/api/v1/workspaces": [{ id: "workspace", name: "Layout fixture workspace", role: "owner", status: "active" }],
      "/api/v1/workspaces/workspace/applications": [application],
      "/api/v1/workspaces/workspace/ingestion": [],
      "/api/v1/applications/app": application,
      "/api/v1/applications/app/targets": [target],
      "/api/v1/applications/app/test-runs": [run],
      "/api/v1/targets/target/authorization": { id: "authorization", target_id: "target", status: "authorized", expires_at: null },
      "/api/v1/test-runs/test": run,
      "/api/v1/test-runs/test/results": report,
      "/api/v1/test-runs/test/flow": { nodes: [], edges: [], revision: "fixture", execution_policy: "once_per_journey" },
      "/api/v1/test-runs/test/journeys": [],
      "/api/v1/test-runs/test/human-actions": [],
      "/api/v1/test-runs/test/action-approvals": [],
      "/api/v1/test-runs/test/live-browser": { run_id: "test", run_status: "completed", server_observed_at: "2026-11-02T12:00:00Z", browser: null, activity: { items: [], next_cursor: null }, pause: null },
      "/api/v1/health/kafka": { status: "connected", outbox_relay_enabled: true },
    };
    if (route.request().method() !== "GET" || !(path in responses)) {
      unexpected.push(`${route.request().method()} ${path}`);
      await route.fulfill({ status: 404, json: { detail: "No mutation or unmatched API is allowed in this layout fixture." } });
    } else await route.fulfill({ json: responses[path] });
  });
  return unexpected;
}

async function layout(page: Page) {
  await expect(page.locator(".concept-workspace")).toBeVisible();
  await expect(page.locator(".error-panel")).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
  const style = await page.locator(".concept-workspace").evaluate(element => {
    const css = getComputedStyle(element);
    return { font: css.fontFamily, paper: css.getPropertyValue("--paper").trim(), ink: css.color, overflow: document.documentElement.scrollWidth > innerWidth + 1 };
  });
  expect(style.font).toContain("Inter");
  expect(style.paper.toLowerCase()).toBe("#faf7f1");
  expect(style.ink).toBe("rgb(17, 17, 17)");
  expect(style.overflow).toBe(false);
}

const pages = [
  ["/dashboard", "Dashboard"], ["/applications", "Your apps"],
  ["/applications/app", "Catalog fixture"], ["/applications/app/runs/new", "Here's my app"],
  ["/settings/profile", "Settings"],
] as const;

test("authenticated management pages keep concept styling and fit supported widths", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const unexpected = await fixture(page);
  for (const width of [360, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const [path, heading] of pages) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1, name: heading, exact: true })).toBeVisible();
      await layout(page);
      if (path.endsWith("/new")) await expect(page.getByLabel("App URL", { exact: true })).toHaveValue(target.base_url);
      if ((width === 360 || width === 1440) && (path.endsWith("/new") || path === "/applications"))
        await page.screenshot({ path: testInfo.outputPath(`${path.endsWith("/new") ? "create" : "apps"}-${width}.png`), fullPage: true });
    }
  }
  expect(unexpected).toEqual([]);
});

test("management forms and keyboard navigation remain accessible", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  const unexpected = await fixture(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  for (const [path, heading] of pages) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: heading, exact: true })).toBeVisible();
    const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(audit.violations).toEqual([]);
  }
  await page.goto("/applications");
  await expect(page.getByRole("heading", { level: 1, name: "Your apps", exact: true })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
  await page.setViewportSize({ width: 360, height: 900 });
  const menu = page.getByRole("button", { name: "Open navigation" });
  await menu.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toBeFocused();
  await page.screenshot({ path: testInfo.outputPath("settings-navigation-mobile.png"), fullPage: true });
  expect(unexpected).toEqual([]);
});

test("discovery test overview, results, and watch views fit mobile and desktop", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  const unexpected = await fixture(page);
  for (const width of [360, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const view of ["overview", "results", "watch"]) {
      await page.goto(`/runs/test/${view}`);
      await expect(page.getByRole("heading", { level: 1, name: /Catalog search/ })).toBeVisible();
      if (view === "results") await expect(page.getByRole("heading", { name: "What works", exact: true }).last()).toBeVisible();
      if (view === "watch") await expect(page.getByRole("heading", { name: "Watch live", exact: true })).toBeVisible();
      await layout(page);
      const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      expect(audit.violations).toEqual([]);
      await page.screenshot({ path: testInfo.outputPath(`${view}-${width}.png`), fullPage: true });
    }
  }
  expect(unexpected).toEqual([]);
});
