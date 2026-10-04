import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("ingest, review, and select approved knowledge before test creation", async ({ page }, testInfo) => {
  test.setTimeout(60000);
  const entry = {
    id: "knowledge-one", workspace_id: "workspace", name: "Product requirements", source_name: "requirements.txt",
    status: "draft", roles: ["product_knowledge"], created_at: "2026-10-03T10:00:00Z", approved_at: null,
    application_ids: [] as string[], processing_status: "ready",
    knowledge_count: 1, artifact_count: 0, skill_count: 0, issue_count: 0,
    preview: {
      source: { name: "requirements.txt", source_item_count: 1, processed_item_count: 1 },
      application_knowledge: [{ name: "Account requirements", content: "Customers can create an account with an email address.", evidence_ordinals: [1], grounding_confidence: "high", warnings: [] }],
      artifacts: [], skills: [], extraction_issues: [],
      evidence: [{ ordinal: 1, evidence_type: "text", content_text: "Account creation requires an email address.", content_json: null, source_locator: { line_start: 1, line_end: 4 }, extractor_name: "text", extractor_version: "1" }],
    },
  };
  let ingested = false;
  let processed = false;
  let selected: string[] = [];
  const app = { id: "app", workspace_id: "workspace", name: "Demo application", status: "active" };
  const run = { id: "run", workspace_id: "workspace", application_id: "app", target_id: "target", status: "draft", target_snapshot: { name: "Staging", environment: "staging" }, configuration_snapshot: { study_brief: "Evaluate account creation" } };
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let data: unknown;
    if (path === "/api/v1/me") data = { id: "user", email: "reviewer@example.com", display_name: "Morgan Lee" };
    else if (path === "/api/v1/workspaces") data = [{ id: "workspace", name: "Demo workspace", status: "active", role: "owner" }];
    else if (path === "/api/v1/workspaces/workspace/applications") data = [app];
    else if (path === "/api/v1/workspaces/workspace/ingestion") {
      if (request.method() === "POST") {
        expect(request.headers()["content-type"]).toContain("multipart/form-data; boundary=");
        expect(request.postDataBuffer()?.toString()).toContain("requirements.txt");
        expect(request.postDataBuffer()?.toString()).toContain("Account creation requires an email address.");
        ingested = true;
        await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ ...entry, processing_status: "queued" }) });
        return;
      } else data = ingested ? [entry, { ...entry, id: "unreviewed", name: "Unreviewed source", status: "draft" }] : [];
    }
    else if (path.endsWith("/source-access")) data = { url: "https://example.invalid/source" };
    else if (path.endsWith("/approve")) { entry.status = "approved"; data = entry; }
    else if (path === "/api/v1/workspaces/workspace/ingestion/knowledge-one/applications") {
      entry.application_ids = request.postDataJSON().application_ids;
      data = entry;
    }
    else if (path === "/api/v1/workspaces/workspace/ingestion/knowledge-one") data = { ...entry, processing_status: processed ? "ready" : "processing" };
    else if (path === "/api/v1/applications/app") data = app;
    else if (path === "/api/v1/applications/app/targets") data = [{ id: "target", application_id: "app", name: "Staging", environment: "staging", status: "active", base_url: "https://example.invalid" }];
    else if (path === "/api/v1/targets/target/authorization") data = { status: "authorized", expires_at: null };
    else if (path === "/api/v1/applications/app/test-runs") {
      if (request.method() === "POST") { selected = request.postDataJSON().knowledge_entry_ids; data = run; }
      else data = [];
    }
    else if (path === "/api/v1/test-runs/run") data = run;
    else { await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "No results yet." }) }); return; }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(data) });
  });
  async function inspect(name: string) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(audit.violations).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`${name}.png`), fullPage: true });
  }
  await page.goto("/ingestion");
  await expect(page.getByRole("heading", { name: "Ingestion", exact: true })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary navigation" }).getByRole("link", { name: "Ingestion", exact: true })).toBeVisible();
  await inspect("ingestion");
  await page.getByLabel("Source file", { exact: true }).setInputFiles({ name: "requirements.txt", mimeType: "text/plain", buffer: Buffer.from("Account creation requires an email address.") });
  await page.getByLabel("Source purpose").selectOption("product_knowledge");
  await page.getByLabel("Knowledge set name").fill("Product requirements");
  await page.getByRole("button", { name: "Ingest knowledge", exact: true }).click();
  await expect(page).toHaveURL(/knowledge\/review\/knowledge-one$/);
  await expect(page.getByRole("progressbar", { name: "Ingestion progress" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve knowledge" })).toHaveCount(0);
  await inspect("processing");
  processed = true;
  await page.getByRole("link", { name: "Back to review knowledge" }).click();
  await page.getByRole("link", { name: "Review Product requirements", exact: true }).click();
  await expect(page.getByText("Account requirements", { exact: true })).toBeVisible();
  await expect(page.getByText("Lines 1–4 · text", { exact: true })).toBeVisible();
  expect((await page.getByText("Lines 1–4 · text", { exact: true }).boundingBox())!.width).toBeGreaterThan(100);
  await expect(page.getByRole("button", { name: "Approve knowledge" })).toBeDisabled();
  await inspect("review");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Approve knowledge" }).click();
  await expect(page.getByText("Available for tests", { exact: true })).toBeVisible();
  await page.getByRole("checkbox", { name: "Demo application", exact: true }).check();
  await page.getByRole("button", { name: "Save applications", exact: true }).click();
  await expect(page.getByRole("link", { name: "Create test for Demo application", exact: true })).toBeVisible();
  await inspect("applications");
  await page.goto("/knowledge/review");
  await expect(page.locator(".row-primary strong").filter({ hasText: "Unreviewed source" })).toBeVisible();
  await inspect("review-list");
  await page.goto("/ingestion");
  await expect(page.locator(".row-primary strong").filter({ hasText: "Product requirements" })).toBeVisible();
  await inspect("sources-list");
  await page.goto("/applications/app/runs/new");
  await expect(page.getByRole("checkbox", { name: /Product requirements/ })).not.toBeChecked();
  await expect(page.getByText("Unreviewed source", { exact: true })).toHaveCount(0);
  await page.getByRole("checkbox", { name: /Product requirements/ }).check();
  await page.getByLabel("Your testing goal").fill("Evaluate account creation against requirements");
  await inspect("test-selection");
  await page.getByRole("button", { name: /Create test/ }).click();
  await expect(page).toHaveURL(/runs\/run\/overview$/);
  expect(selected).toEqual(["knowledge-one"]);
});
