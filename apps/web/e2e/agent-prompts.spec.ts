import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("inspect saved agent YAML and create an edited rerun draft", async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  if (testInfo.project.name === "chromium") await page.setViewportSize({ width: 1100, height: 900 });
  const source = { id: "source", workspace_id: "workspace", application_id: "app", target_id: "target", status: "completed", target_snapshot: { name: "Staging", base_url: "https://example.invalid" }, configuration_snapshot: { study_brief: "Evaluate information discovery", testing_depth: "medium" } };
  const draft = { ...source, id: "fork", status: "draft" };
  const runtimeName = "markettwin_careful_first_timer__validate_empty_contact_address";
  const yaml = `snapshot_id: persona-snapshot\nagent_role: persona\nagent_name: ${runtimeName}\nmodel: openai/example\nmodel_configuration: {}\ntools: [browser_click]\npersona: {name: First user}\nmission: {name: Find information}\ninstruction: |\n  Act as the assigned user.\nruntime_prompt: |\n  Visit the authorized application.\n`;
  let submitted: { snapshot_id: string; prompt_yaml: string } | undefined;
  let savedYaml: string | null = null;
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data: unknown;
    if (path === "/api/v1/me") data = { id: "user", email: "reviewer@example.com", display_name: "Morgan Lee" };
    else if (path === "/api/v1/workspaces") data = [{ id: "workspace", name: "Demo workspace", status: "active", role: "owner" }];
    else if (path === "/api/v1/workspaces/workspace/applications") data = [{ id: "app", workspace_id: "workspace", name: "Demo application", status: "active" }];
    else if (path === "/api/v1/applications/app/test-runs") data = [source];
    else if (path === "/api/v1/workspaces/workspace/agent-prompts") {
      const query = new URL(route.request().url()).searchParams;

      data = { limit: 100, agents: query.get("created_after")?.startsWith("2030") ? [] : [{ snapshot: { id: "persona-snapshot", test_run_id: "source", agent_role: "persona", runtime_agent_name: runtimeName, model_name: "openai/example", created_at: "2026-10-04T10:00:00Z", persona_snapshot: { name: "First user" }, mission_snapshot: { name: "Find information" } }, test_brief: "Evaluate information discovery", duration_seconds: 12.3 }] };
    }
    else if (path.endsWith("/agent-prompts")) data = { test_run_id: "source", agents: [{ snapshot: { id: "persona-snapshot", agent_role: "persona", runtime_agent_name: runtimeName, model_name: "openai/example", created_at: "2026-10-04T10:00:00Z", persona_snapshot: { name: "First user" }, mission_snapshot: { name: "Find information" } }, available_tools: ["browser_click", "browser_get_state"], yaml, saved_yaml: savedYaml, saved_at: savedYaml ? "2026-10-04T12:00:00Z" : null }] };
    else if (path.endsWith("/draft")) {
      const input = route.request().postDataJSON().prompt_yaml;
      if (input === "instruction: [") {
        await route.fulfill({ status: 422, json: { detail: "Enter valid YAML with unique keys and no aliases." } });
        return;
      }
      savedYaml = input;
      data = { prompt_yaml: savedYaml, updated_at: "2026-10-04T12:00:00Z" };
    }
    else if (path.endsWith("/agent-reruns")) {
      submitted = route.request().postDataJSON();
      if (submitted!.prompt_yaml === "instruction: [") {
        await route.fulfill({ status: 422, json: { detail: "Enter valid YAML with unique keys and no aliases." } });
        return;
      }
      data = draft;
    }
    else if (path === "/api/v1/test-runs/source") data = source;
    else if (path === "/api/v1/test-runs/fork") data = draft;
    else if (path.endsWith("/journeys")) data = [];
    else if (path.endsWith("/flow")) data = { nodes: ["meta", "collector", "evaluation", "report"].map((id) => ({ id, kind: id, label: id, status: "completed" })), edges: [{ source: "meta", target: "collector" }, { source: "collector", target: "evaluation" }, { source: "evaluation", target: "report" }], revision: "fixture", execution_policy: "once_per_journey" };
    else if (path === "/api/v1/health/kafka") data = { status: "connected", outbox_relay_enabled: true };
    else { await route.fulfill({ status: 404, json: { detail: "No results yet." } }); return; }
    await route.fulfill({ json: data });
  });
  await page.goto("/agents");
  await page.getByRole("button", { name: "Demo application View test agent flows" }).click();
  await page.getByRole("link", { name: /source.*Test/ }).click();
  await expect(page).toHaveURL(/runs\/source\/agents$/);
  await page.getByText("Advanced agent configuration and recorded diagnostics", { exact: true }).click();
  const editor = page.getByLabel("Prompt YAML");
  if (testInfo.project.name === "chromium") {
    await page.setViewportSize({ width: 1600, height: 1000 });
    const choice = page.locator(".agent-prompt-choice").first();
    await expect(choice).toBeVisible();
    const nameFits = await choice.evaluate((element) => {
      const text = element.querySelector("strong")!;
      return text.getBoundingClientRect().right <= element.getBoundingClientRect().right && text.scrollWidth <= text.clientWidth + 1;
    });
    expect(nameFits).toBe(true);
    await page.screenshot({ path: testInfo.outputPath("agent-flow-long-name.png"), fullPage: true });
    await page.setViewportSize({ width: 1100, height: 900 });
  }
  await expect(editor).toHaveValue(yaml);
  await editor.fill("instruction: [");
  await expect(page.getByRole("button", { name: "Create rerun draft" })).toBeDisabled();
  await page.getByRole("button", { name: "Save prompt" }).click();
  await expect(page.getByRole("alert")).toContainText("Enter valid YAML");
  await expect(page).toHaveURL(/runs\/source\/agents$/);
  await page.getByRole("button", { name: "Reset edits" }).click();
  await expect(editor).toHaveValue(yaml);
  const edited = yaml.replace("Act as the assigned user.", "Observe navigation carefully and record genuine confusion.") + `rerun_configuration:
  name: Agent_2
  agent_type: SequentialAgent
  temperature: 0.05
  tools: [browser_click]
  sub_agents:
    - name: Agent_3
      agent_type: LlmAgent
      temperature: 0.05
      tools: [browser_get_state]
      sub_agents: []
      instruction: Inspect navigation and retain browser evidence references.
`;
  await editor.fill(edited);
  await page.getByLabel("Agents created from", { exact: true }).fill("2030-01-01");
  await expect(page.getByText("The selected agent is outside these dates. Its editor stays open.")).toBeVisible();
  await expect(editor).toHaveValue(edited);
  if (testInfo.project.name === "chromium") expect((await editor.boundingBox())?.width).toBeGreaterThan(340);
  await page.getByLabel("Agents created from", { exact: true }).fill("");
  await expect(page.getByText("Rerun agent settings", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Sequential Agent", exact: true })).toBeVisible();
  const stages = page.locator(".agent-flow-stage > h3");
  await expect(stages).toHaveText(["Meta Agent", "Sequential Agent", "Collector", "Evaluation and Report"]);
  await expect(page.locator(".agent-flow-stage").nth(1).getByRole("button")).toHaveCount(1);
  const scroller = page.getByLabel("Test execution stages");
  expect(await scroller.evaluate((element) => getComputedStyle(element).overflowY)).toBe("auto");
  await expect(page.getByRole("button", { name: "Create rerun draft" })).toBeDisabled();
  await page.getByRole("button", { name: "Save prompt" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Prompt saved" })).toBeVisible();
  await page.goto("/agents");
  await page.getByRole("button", { name: "Demo application View test agent flows" }).click();
  await page.getByRole("link", { name: /source.*Test/ }).click();
  await page.getByText("Advanced agent configuration and recorded diagnostics", { exact: true }).click();
  await expect(editor).toHaveValue(edited);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(audit.violations).toEqual([]);
  await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur(); window.scrollTo(0, 0); });
  await page.screenshot({ path: testInfo.outputPath("agent-prompt-width.png"), fullPage: true });
  await page.getByRole("button", { name: "Create rerun draft" }).click();
  await expect(page).toHaveURL(/runs\/fork\/overview$/);
  expect(submitted).toEqual({ snapshot_id: "persona-snapshot", prompt_yaml: edited });
  await expect(page.getByRole("button", { name: "Start test", exact: true })).toBeVisible();
});
