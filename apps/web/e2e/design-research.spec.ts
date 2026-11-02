import AxeBuilder from "@axe-core/playwright";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

// HITL fixtures use mocked API data and a synthetic lease grant. They exercise
// the blank viewer layout without live connections, credential entry, or frames.
test.use({ trace: "off", screenshot: "off" });

test('Chrome layout: dark workspace and readable results', async ({ page }) => {
  test.setTimeout(120000);
  const stage = process.env.MARKETTWIN_LAYOUT_PHASE ?? 'after';
  const output = path.resolve(process.cwd(), '../../.local/chrome-layout', stage);
  await mkdir(output, { recursive: true });
  await page.addInitScript(() => {
    if (!localStorage.getItem('markettwin-theme')) localStorage.setItem('markettwin-theme', 'dark');
  });
  await installWorkspace(page);
  const measurements = [];
  for (const width of [1440, 1920, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const [name, route] of [
      ['workspace', '/overview'],
      ['results', `/runs/${runId}/report`],
      ['inspection', `/runs/${runId}/report?reportView=inspection`],
    ]) {
      await page.goto(route);
      await expect(page.locator('#main-content')).toBeVisible();
      await expect(page.getByText('Opening workspace', { exact: true })).toHaveCount(0);
      await page.evaluate(() => document.fonts.ready);
      const sizing = await page.evaluate(() => {
        const main = document.querySelector('#main-content')!;
        return {
          viewport: innerWidth, content: main.getBoundingClientRect().width,
          bodyFont: getComputedStyle(document.body).fontSize,
          zoom: getComputedStyle(document.body).zoom,
          overflow: document.documentElement.scrollWidth > innerWidth + 1,
          theme: document.documentElement.dataset.theme,
        };
      });
      await page.screenshot({ path: path.join(output, `${name}-${width}.png`), fullPage: true });
      measurements.push({ name, width, ...sizing });
      expect(sizing.overflow).toBe(false);
      expect(sizing.theme).toBe('dark');
      if (stage === 'after') {
        expect(Number.parseFloat(sizing.bodyFont)).toBeGreaterThanOrEqual(16);
        if (name === 'results') {
          await expect(page.getByRole('heading', { name: 'Case execution', exact: true })).toBeVisible();
          await expect(page.getByText('2 of 2 cases recorded as executed.', { exact: true })).toBeVisible();
          await expect(page.getByRole('link', { name: 'Open supporting step', exact: true }))
            .toHaveAttribute('href', `/runs/${runId}/journeys/${journeyId}?step=13`);
        }
        const audit = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze();
        expect(audit.violations.filter(item => item.id === 'color-contrast')).toEqual([]);
      }
    }
  }
  const fs = await import('node:fs/promises');
  await fs.writeFile(path.join(output, 'measurements.json'), JSON.stringify(measurements, null, 2));
  if (stage === 'after') {
    await page.getByRole('button', { name: 'Switch to light theme', exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await page.getByRole('button', { name: 'Switch to dark theme', exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  }
});

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
    payload: {
      generator: "synthetic_e2e_fixture", schema_version: 1, mode: "deep_feature_v1",
      coverage: { planned: 2, executed: 2, passed: 1, failed_assertions: 0, blocked: 0, inconclusive: 1, not_run: 0 },
    },
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
    else if (path === `/api/v1/targets/${targetId}`) data = target;
    else if (path === `/api/v1/targets/${targetId}/scope-revisions`) data = [];
    else if (path === `/api/v1/targets/${targetId}/authorization`) data = {
      id: 'synthetic-authorization', target_id: targetId, status: "authorized", expires_at: null,
      authorization_basis: 'Synthetic fixture authorization for layout review.', authorized_at: '2026-10-15T12:00:00Z',
    };
    else if (path === `/api/v1/workspaces/${workspace.id}/agent-prompts`) data = { agents: [], limit: 100 };
    else if (path === `/api/v1/test-runs/${runId}/agent-prompts`) data = { test_run_id: runId, agents: [] };
    else if (path === `/api/v1/test-runs/${runId}/evaluation-agents`) data = [];
    else if (path === `/api/v1/workspaces/${workspace.id}/ingestion/source-review`) data = {
      id: 'source-review', workspace_id: workspace.id, name: 'Synthetic requirements', source_name: 'requirements.txt',
      status: 'draft', roles: ['product_knowledge'], created_at: '2026-10-15T12:00:00Z', approved_at: null,
      application_ids: [appId], processing_status: 'ready', knowledge_count: 1, artifact_count: 0, skill_count: 0, issue_count: 0,
      preview: { source: { name: 'requirements.txt', source_item_count: 1, processed_item_count: 1 },
        application_knowledge: [{ name: 'Profile requirement', content: 'Preferences persist after saving.', evidence_ordinals: [1], grounding_confidence: 'high', warnings: [] }],
        artifacts: [], skills: [], extraction_issues: [], evidence: [{ ordinal: 1, evidence_type: 'text', content_text: 'Preferences persist after saving.', content_json: null, source_locator: { line_start: 1 }, extractor_name: 'text', extractor_version: '1' }] },
    };
    else if (path.endsWith('/source-review/source-access')) data = { url: 'https://artifact.example.invalid/source.txt' };
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


const phase = process.env.DESIGN_PHASE || 'after';
const out = process.env.DESIGN_EVIDENCE_DIR || path.resolve(process.cwd(), 'test-results/design-review', phase);
const widths = [1440, 1024, 768, 390];
const screens = [
  ['overview', '/overview'], ['applications', '/applications'], ['tests', '/runs'],
  ['composer', '/applications/' + appId + '/runs/new'],
  ['report', '/runs/' + runId + '/report'],
  ['journey', '/runs/' + runId + '/journeys/' + journeyId + '?step=13'],
  ['knowledge', '/knowledge/review'], ['ingestion', '/ingestion'],
  ['settings', '/settings/profile'], ['execution', '/runs/' + runId + '/activity'],
  ['application', `/applications/${appId}`], ['new-application', '/applications/new'],
  ['edit-application', `/applications/${appId}/edit`], ['application-tests', `/applications/${appId}/runs`],
  ['targets', `/applications/${appId}/targets`], ['new-target', `/applications/${appId}/targets/new`],
  ['target', `/targets/${targetId}`], ['edit-target', `/targets/${targetId}/edit`],
  ['authorization', `/targets/${targetId}/authorization`], ['network', `/targets/${targetId}/network`],
  ['source-review', '/knowledge/review/source-review'], ['agents', '/agents'],
  ['workspace-settings', '/settings/workspace'], ['members', '/settings/members'], ['security', '/settings/security'],
  ['run-summary', `/runs/${runId}/overview`], ['run-agents', `/runs/${runId}/agents`],
  ['perspectives', `/runs/${runId}/perspectives`], ['missions', `/runs/${runId}/missions`],
  ['evaluation', `/runs/${runId}/evaluation`], ['journeys', `/runs/${runId}/journeys`],
  ['findings', `/runs/${runId}/findings`], ['evidence', `/runs/${runId}/evidence`],
  ['human-action', `/runs/${runId}/human-action`], ['forbidden', '/403'], ['error', '/error'], ['not-found', '/missing-location'],
];
test('design evidence: populated routes at four widths', async ({page}) => {
  test.setTimeout(600000);
  await installWorkspace(page);
  await mkdir(out, {recursive:true});
  const records = [];
  for (const width of widths) {
    await page.setViewportSize({width, height:1000});
    for (const [name, url] of screens) {
      await page.goto(url);
      await expect(page.locator('#main-content')).toBeVisible();
      await expect(page.getByText('Opening workspace', {exact:true})).toHaveCount(0);
      await page.evaluate(() => document.fonts.ready);
      const audit = await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
      const overflowElements = overflow ? await page.locator('body *').evaluateAll(nodes => nodes.filter(node => node.getBoundingClientRect().right > innerWidth + 1 && getComputedStyle(node).position !== 'fixed').map(node => ({ tag: node.tagName, class: node.className })).slice(0, 15)) : [];
      const errors = await page.locator('main [role="alert"]').allTextContents();
      const file = name + '-' + width + '.png';
      await page.screenshot({path:path.join(out,file),fullPage:true,animations:'disabled'});
      records.push({name,url,width,file,overflow,overflowElements,errors,violations:audit.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))});
    }
  }
  const fs = await import('node:fs/promises');
  await fs.writeFile(path.join(out,'manifest.json'),JSON.stringify(records,null,2));
  if (phase === 'after') {
    expect(records.filter(r=>r.overflow), 'Responsive overflow').toEqual([]);
    expect(records.filter(r=>r.violations.length), 'Accessibility violations').toEqual([]);
  }
});
test('design evidence: public pages, empty workspace and drawer', async ({page}) => {
  test.setTimeout(120000);
  await mkdir(out, {recursive:true});
  await installWorkspace(page,{emptyApplications:true});
  for (const width of [1440,390]) {
    await page.setViewportSize({width,height:1000});
    await page.goto('/overview');
    await expect(page.getByRole('heading',{name:'Add your first application'})).toBeVisible();
    await page.screenshot({path:path.join(out,'empty-'+width+'.png'),fullPage:true,animations:'disabled'});
    if(width===390){
      await page.getByRole('button',{name:'Open navigation'}).click();
      await expect(page.getByRole('dialog',{name:'Workspace navigation'})).toBeVisible();
      await page.screenshot({path:path.join(out,'drawer-390.png'),fullPage:true,animations:'disabled'});
      await page.keyboard.press('Escape');
      await expect(page.getByRole('button',{name:'Open navigation'})).toBeFocused();
    }
  }
  await page.unroute('**/api/v1/**');
  await page.route('**/api/v1/**', route=>route.fulfill({status:401,json:{detail:'Not authenticated'}}));
  for(const width of [1440,1024,768,390]){
    await page.setViewportSize({width,height:1000});
    for(const [name,url] of [['home','/'],['how','/how-it-works'],['signin','/login'],['callback','/auth/callback']]){
      await page.goto(url); await expect(page.locator('h1').first()).toBeVisible();
      await page.evaluate(()=>document.fonts.ready);
      await page.screenshot({path:path.join(out,name+'-'+width+'.png'),fullPage:true,animations:'disabled'});
      if (name === 'callback') {
        await page.getByRole('link', { name: 'Return to sign in' }).click();
        await expect(page).toHaveURL(/\/login$/);
      }
      if(phase==='after'){
        expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width+1);
        const audit = await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();
        expect(audit.violations).toEqual([]);
      }
    }
  }
});

test('redesign: draft creation, optional fields and evidence navigation', async ({page}) => {
  test.setTimeout(90000);
  const fixture = await installWorkspace(page);
  await page.goto('/overview');
  await page.getByRole('link',{name:'Review report',exact:true}).click();
  await expect(page).toHaveURL(/\/report$/);
  await page.getByRole('button',{name:/Cancel profile preference edit/}).click();
  await expect(page.locator('.feature-case-detail').getByText('Unavailable',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:/Save profile preference/}).click();
  await page.getByRole('link',{name:'Open supporting step',exact:true}).click();
  await expect(page).toHaveURL(/step=13/);
  await page.goto('/applications/'+appId+'/runs/new');
  await page.getByRole('button',{name:'Create test',exact:true}).click();
  await expect(page.locator('#test-brief')).toBeFocused();
  await expect(page.locator('#test-brief')).toHaveAttribute('aria-invalid','true');
  await page.getByRole('button',{name:'Checkout confidence',exact:true}).click();
  const goal=await page.locator('#test-brief').inputValue();
  await page.locator('.composer-disclosure').first().locator('summary').click();
  await page.locator('.security-disclosure summary').click();
  await expect(page.locator('#test-brief')).toHaveValue(goal);
  await page.getByLabel('Test name',{exact:false}).fill('Checkout evidence review');
  await page.getByRole('button',{name:'Create test',exact:true}).click();
  await expect(page).toHaveURL(/\/overview$/);
  expect(fixture.createRunPayload).toBeDefined();
  expect(JSON.stringify(fixture.createRunPayload)).toContain('Checkout evidence review');
  expect(JSON.stringify(fixture.createRunPayload)).toContain(goal);
});

test('redesign: long case list, keyboard demo and explicit execution recovery',async({page})=>{
  test.setTimeout(90000);
  await installWorkspace(page,{stressCaseCount:60});
  await page.setViewportSize({width:390,height:1000});
  await page.goto('/runs/'+runId+'/report');
  await expect(page.locator('.feature-case-choice')).toHaveCount(60);
  await page.locator('.feature-case-choice').last().click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(391);
  await page.screenshot({path:path.join(out,'long-cases-390.png'),fullPage:true,animations:'disabled'});
  await page.goto('/runs/'+runId+'/activity');
  await expect(page.getByRole('alert').filter({hasText:'Live execution status is unavailable'})).toBeVisible();
  await page.getByRole('button',{name:'Retry status'}).click();
  await expect(page.getByRole('alert').filter({hasText:'Live execution status is unavailable'})).toBeVisible();
  await page.unroute('**/api/v1/**');
  await page.route('**/api/v1/**',route=>route.fulfill({status:401,json:{detail:'Not authenticated'}}));
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.goto('/');
  const step=page.getByRole('button',{name:/Verify saved state/});
  await step.focus();await page.keyboard.press('Enter');
  await expect(step).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('.mt-demo-comparison')).toContainText('Email updates enabled');
});

test('redesign: recorded activity stays linked to its evidence',async({page})=>{
  await installWorkspace(page);
  await page.route('**/live-browser?*',route=>route.fulfill({json:{run_id:runId,run_status:'completed',server_observed_at:'2026-10-15T12:00:04Z',browser:null,pause:null,activity:{next_cursor:null,items:[{id:'step-13',run_id:runId,journey_id:journeyId,execution_id:null,step_id:13,source:'deterministic_case',kind:'assertion',status:'completed',occurred_at:'2026-10-15T12:00:04Z',title:'Verify saved state'}]}}}));
  await page.route('**/human-actions',route=>route.fulfill({json:[]}));
  await page.route('**/action-approvals',route=>route.fulfill({json:[]}));
  await page.setViewportSize({width:1440,height:1000});
  await page.goto('/runs/'+runId+'/activity');
  await page.getByRole('button',{name:/Verify saved state/}).click();
  const inspector=page.getByRole('region',{name:'Selected activity'});
  await expect(inspector).toContainText('does not by itself establish a product defect');
  await page.screenshot({path:path.join(out,'recorded-execution-1440.png'),fullPage:true,animations:'disabled'});
  await inspector.getByRole('link',{name:/Inspect step 13/}).click();
  await expect(page).toHaveURL(/step=13/);
});
