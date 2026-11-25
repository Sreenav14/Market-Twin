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



async function reportWorkspace(page: Page) {
  await installWorkspace(page);
  const tasks=Array.from({length:6},(_,index)=>({...journeys[0],id:index?`55555555-5555-4555-8555-55555555556${index}`:journeyId,
    persona_name:index<3?'First-time user':'Returning user',persona_perspective:'Synthetic test perspective',
    mission_title:['Save profile preference','Cancel profile edit','Submit protected form','Open preferences','Validate missing input','Review profile'][index],mission_objective:'Complete the documented task.',
    ordinal:index+1,execution_id:index===3?null:journeys[0].execution_id,
    execution_status:index===2?'policy_blocked':index===3?'skipped':'completed',outcome:index===1?'failed':index===4?null:'passed',
    step_count:index===3?0:3,artifact_count:index===3?0:1,evidence_available:index!==3,runtime_name:'persona_executor_v1'}));
  const findings=[
    {id:'a0000000-0000-4000-8000-000000000001',title:'Preference was not retained',summary:'The recorded saved-state assertion did not match.',severity:'high',category:'functional',finding_kind:'observed_product_issue',verification_status:'verified_deterministic',status:'open',recommendation:'Inspect the saved-state handler.',journey_ids:[journeyId],evidence:{step_ids:[13],artifact_ids:[artifactId]}},
    {id:'a0000000-0000-4000-8000-000000000002',title:'Label needs a visual review',summary:'The observation has not been visually confirmed.',severity:'medium',category:'visual_criterion',finding_kind:'unverified',verification_status:'unverified',status:'open',recommendation:null,journey_ids:[tasks[1].id],evidence:{step_ids:[],artifact_ids:[]}},
    {id:'a0000000-0000-4000-8000-000000000003',title:'Navigation was blocked by scope',summary:'The executor stopped outside the approved scope.',severity:'info',category:'policy',finding_kind:'test_execution_issue',verification_status:'not_applicable',status:'open',recommendation:'Review the approved target scope.',journey_ids:[tasks[2].id],evidence:{step_ids:[],artifact_ids:[]}},
    {id:'a0000000-0000-4000-8000-000000000004',title:'Saved state differs across tasks',summary:'Two task records cite a saved-state issue.',severity:'medium',category:'functional',finding_kind:'observed_product_issue',verification_status:'verified_visual',status:'open',recommendation:'Review both task records.',journey_ids:[journeyId,tasks[1].id],evidence:{step_ids:[13],artifact_ids:[artifactId]}},
  ];
  await page.route(`**/test-runs/${runId}`,route=>route.fulfill({json:{...run,configuration_snapshot:{...run.configuration_snapshot,execution_mode:'legacy_persona'}}}));
  await page.route(`**/test-runs/${runId}/results`,route=>route.fulfill({json:{...results,findings,report:{...results.report,payload:{schema_version:1,generator:'deterministic_evaluation_v1',journeys:{total:6,status_counts:{completed:4,policy_blocked:1,skipped:1},outcome_counts:{passed:3,failed:1,none:2}},findings:{total:4,confirmed_issue_count:2,unverified_observation_count:1,execution_diagnostic_count:1,category_counts:{functional:2,visual_criterion:1,policy:1}},assessment:{status:'completed',individual_results:tasks.map(task=>({journey_id:task.id,goal_outcome:task.execution_status==='completed'?'partially_met':'inconclusive',ease_of_use:'inconclusive',summary:'Synthetic qualitative assessment of saved evidence.',recommendations:['Review the supporting record.']}))}}}}}));
  await page.route(`**/test-runs/${runId}/journeys`,route=>route.fulfill({json:tasks}));
  await page.route(`**/journeys/${journeyId}?*`,route=>{
    const after=Number(new URL(route.request().url()).searchParams.get('after_step')??0);
    return route.fulfill({json:{...journeyDetail,steps:after?journeyDetail.steps.slice(2):journeyDetail.steps.slice(0,2),next_after_step:after?null:2}});
  });
}
const evidence=process.env.REPORT_EVIDENCE_DIR||(process.env.DESIGN_EVIDENCE_DIR?path.join(process.env.DESIGN_EVIDENCE_DIR,'report'):path.resolve(process.cwd(),'test-results/report-intelligence'));

test("Summary stays readable across four widths and keeps the legacy report URL usable", async ({ page }) => {
  test.setTimeout(120_000);
  await reportWorkspace(page);
  await mkdir(evidence, { recursive: true });
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(`/runs/${runId}/report`);
    await expect(page.getByRole("region", { name: "Takeaway" })).toBeVisible();
    const tabs = page.getByRole("navigation", { name: "Test sections" });
    await expect(tabs.getByRole("link")).toHaveText(["Summary", "Watch", "Activity", "Evidence"]);
    await expect(tabs.getByRole("link", { name: "Summary" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { name: "Journey outcomes" })).toBeVisible();
    await expect(page.getByText("Worked · 3 of 6")).toBeVisible();
    await expect(page.getByText("Model assessment")).toHaveCount(0);
    await page.evaluate(() => document.fonts.ready);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
    const violations = (await new AxeBuilder({ page }).include(".report-frame").withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations;
    expect(violations.map(({ id, nodes }) => ({ id, nodes: nodes.map(node => node.target) }))).toEqual([]);
    await page.screenshot({ path: path.join(evidence, `summary-${width}.png`), fullPage: true, animations: "disabled" });
  }
});

test("Summary enables keyboard review of a finding with its own evidence link", async ({ page }) => {
  await reportWorkspace(page);
  await page.goto(`/runs/${runId}`);
  const findings = page.locator("#report-findings");
  await expect(findings.getByText("Preference was not retained")).toHaveCount(0);
  await findings.getByRole("button", { name: "Functionality · 2" }).click();
  const verified = findings.getByText("Verified · 2", { exact: true });
  await verified.focus();
  await verified.press("Enter");
  await expect(findings.getByText("Preference was not retained")).toBeVisible();
  await expect(findings.getByText("Label needs a visual review")).toHaveCount(0);
  await findings.getByText("Preference was not retained").click();
  await expect(findings.getByRole("link", { name: "View evidence" })).toHaveAttribute("href", `/runs/${runId}/journeys/${journeyId}?step=13`);
});

test("historical feature-case anchor opens its saved case list", async ({ page }) => {
  await installWorkspace(page);
  await page.goto(`/runs/${runId}/results#report-feature-cases`);
  const cases = page.locator("#report-feature-cases");
  await expect(cases).toHaveAttribute("open", "");
  await expect(cases.getByRole("button", { name: /Save profile preference/ })).toBeVisible();
});
