import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("the simple agent map updates from the saved plan and keeps large plans compact", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  let count = 0;
  let revision = 1;
  let starts = 0;
  const run = { id: "flow-run", workspace_id: "workspace", application_id: "app", target_id: "target", created_by_user_id: "user", status: "running", target_snapshot: { name: "Staging", environment: "test" }, configuration_snapshot: { study_brief: "Review application navigation" } };
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown;
    if (path === "/api/v1/me") data = { id: "user", email: "reviewer@example.com", display_name: "Morgan Lee" };
    else if (path === "/api/v1/workspaces") data = [{ id: "workspace", name: "Demo workspace", status: "active", role: "owner" }];
    else if (path === "/api/v1/test-runs/flow-run") data = run;
    else if (path === "/api/v1/test-runs/flow-run/journeys") data = Array.from({ length: count }, (_, index) => ({ id: `journey-${index}`, ordinal: index + 1, persona_name: `Customer ${index + 1}`, mission_title: "Discover relevant account guidance", success_criteria: ["Account guidance is discoverable"], execution_id: index < 2 ? `execution-${index}` : null, attempt_number: index < 2 ? 1 : null, execution_status: index === 0 ? "completed" : index === 1 ? "running" : null, outcome: index === 0 ? "passed" : null, started_at: null, completed_at: null, error_message: null, result: index === 0 ? { summary: "Relevant account guidance was found." } : null }));
    else if (path === "/api/v1/test-runs/flow-run/collection") data = { collection: null, collected_at: null };
    else if (path === "/api/v1/test-runs/flow-run/flow") {
      const nodes = [
        { id: "meta", kind: "meta", label: "Meta Agent", status: count ? "completed" : "running" },
        ...Array.from({ length: count }, (_, index) => ({ id: `journey:${index}`, kind: "journey", label: `Customer ${index + 1} · Discover relevant account guidance`, status: index === 0 ? "completed" : index === 1 ? "running" : "not_started" })),
        { id: "collector", kind: "collector", label: "Supervisor collection", status: "not_started" },
        { id: "evaluation", kind: "evaluation", label: "Evaluation", status: "not_started" },
        { id: "report", kind: "report", label: "Report", status: "not_started" },
      ];
      data = { nodes, edges: nodes.slice(1).map((node, index) => ({ source: nodes[index].id, target: node.id })), execution_policy: "once_per_journey", revision: String(revision) };
    }
    else if (path.endsWith("/start")) { starts += 1; await route.fulfill({ status: 400, json: { detail: "Map inspection cannot start execution." } }); return; }
    else { await route.fulfill({ status: 404, json: { detail: "No fixture for this request." } }); return; }
    await route.fulfill({ json: data });
  });
  await page.goto("/runs/flow-run/journeys");
  const flow = page.getByRole("complementary", { name: "Agent flow", exact: true });
  await expect(flow.getByText("0 journeys", { exact: true })).toBeVisible();
  const disclosure = flow.locator("details").first();
  if (testInfo.project.name === "mobile-chromium") {
    await expect(disclosure).not.toHaveAttribute("open", "");
    await flow.locator("summary").first().click();
  } else await expect(disclosure).toHaveAttribute("open", "");
  await expect(flow.getByText("Meta Agent", { exact: true })).toBeVisible();
  await expect(flow.getByText("Each planned journey runs once. The supervisor collects outputs before evaluation.", { exact: true })).toBeVisible();
  count = 2;
  revision += 1;
  await expect(flow.getByText("2 journeys", { exact: true })).toBeVisible({ timeout: 12_000 });
  await flow.locator(".run-flow-journeys > summary").click();
  const first = flow.locator("li").filter({ has: page.locator(".run-flow-node-label", { hasText: "Customer 1 · Discover relevant account guidance" }) }).last();
  await expect(first.getByText("completed", { exact: true })).toBeVisible();
  const second = flow.locator("li").filter({ has: page.locator(".run-flow-node-label", { hasText: "Customer 2 · Discover relevant account guidance" }) }).last();
  await expect(second.getByText("running", { exact: true })).toBeVisible();
  await expect(second.getByText("Browser tools · Playwright", { exact: true })).toBeVisible();
  await expect(flow.locator(".run-flow-nodes").first().locator(":scope > li")).toHaveCount(5);
  await expect(flow.locator(".connected")).toHaveCount(5);
  await flow.locator(".run-flow-journeys > summary").click();
  count = 4;
  revision += 1;
  await expect(flow.getByText("4 journeys", { exact: true })).toBeVisible({ timeout: 12_000 });
  await expect(flow.getByText("Customer 4 · Discover relevant account guidance", { exact: true })).not.toBeVisible();
  await flow.locator(".run-flow-journeys > summary").click();
  await expect(flow.getByText("Customer 4 · Discover relevant account guidance", { exact: true })).toBeVisible();
  await expect(flow.getByText("Supervisor collection", { exact: true })).toBeVisible();
  await expect(flow.getByText("Evaluation", { exact: true })).toBeVisible();
  await expect(flow.getByText("Report", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Customer 4 · Discover relevant account guidance", exact: true })).toBeVisible();
  await flow.locator(".run-flow-journeys > summary").click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(audit.violations).toEqual([]);
  await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); window.scrollTo(0, 0); });
  await page.screenshot({ path: testInfo.outputPath("agent-flow.png"), fullPage: true });
  expect(starts).toBe(0);
});
