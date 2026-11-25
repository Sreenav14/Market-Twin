export type TestRunStatus =
  | "draft"
  | "planning"
  | "queued"
  | "running"
  | "awaiting_human"
  | "completed"
  | "failed"
  | "cancelled";

export type JourneyOutcome = "passed" | "failed" | "partial" | "inconclusive";
export type TestingDepth = "low" | "medium" | "high";
export type FindingSeverity = "critical" | "high" | "medium" | "low" | "info";

export interface CurrentUser {
  id: string;
  email: string;
  normalized_email: string;
  display_name: string | null;
}

export interface Workspace {
  id: string;
  name: string;
  status: string;
  role: string;
}

/** The app's latest completed run that produced a report (W2). The
 * verdict is the report's stored market verdict, verbatim; null when
 * that report carries no market verdict. The whole summary is null
 * when the app has no completed run with a finished report. */
export interface LatestRunSummary {
  latest_run_id: string;
  latest_run_status: string;
  verdict: string | null;
  finished_at: string | null;
}

export interface Application {
  id: string;
  workspace_id: string;
  created_by_user_id: string;
  name: string;
  description: string | null;
  status: string;
  latest_run_summary: LatestRunSummary | null;
}

export interface HumanAction {
  id: string;
  test_run_id: string;
  execution_id: string;
  browser_session_id: string;
  request_type: string;
  journey_id?: string | null;
  journey_title?: string | null;
  requesting_agent?: string | null;
  requested_by_step_id?: number | null;
  browser_state?: string | null;
  instructions?: string;
  status: "pending" | "leased" | "completed" | "cancelled" | "expired" | "skipped";
  created_at: string;
  expires_at: string | null;
  control_generation: number;
  lease_id: string | null;
  lease_expires_at: string | null;
}

export interface HumanLeaseGrant {
  request_id: string;
  browser_session_id: string;
  lease_id: string;
  lease_token: string;
  generation: number;
  expires_at: string;
  viewer_available: boolean;
  viewer_url?: string;
  viewer_ticket?: string;
}

export interface LiveBrowser {
  browser_session_id: string;
  execution_id: string;
  journey_id: string;
  generation: number;
  control_state: string;
  viewer_state: "available" | "suppressed";
  journey_title: string;
  requesting_agent: string;
  board_item?: { index: number; total: number; label: string } | null;
}
export interface LiveGrant {
  ticket: string;
  viewer_url: string;
  browser: LiveBrowser;
}

export interface RunActivityItem {
  id: string;
  run_id: string;
  journey_id: string | null;
  execution_id: string | null;
  step_id: number | null;
  source: "browser_agent" | "deterministic_case" | "planner" | "human_assistance" | "approval" | "evaluation" | "report" | "system";
  kind: string;
  status: string;
  occurred_at: string;
  title: string;
}

export interface LiveExecution {
  run_id: string;
  run_status: TestRunStatus;
  server_observed_at: string;
  browser: LiveBrowser | null;
  activity: { items: RunActivityItem[]; next_cursor: string | null };
  pause?: ExecutionPause | null;
}

export interface ExecutionPause {
  id: string;
  status: string;
  execution_id: string;
  journey_id: string;
  browser_session_id: string;
  generation: number;
  human_request_id: string | null;
  created_at: string;
  expires_at: string;
  acknowledged_at: string | null;
  completed_at: string | null;
}

export interface ActionApproval {
  step_id?: number;
  journey_id?: string;
  id: string;
  action_summary: string;
  environment: string;
  status: "pending" | "approved";
  expires_at: string;
}

export type GroundingConfidence = "low" | "medium" | "high";

export interface ApplicationKnowledgeDraft {
  name: string;
  content: string;
  evidence_ordinals: number[];
  grounding_confidence: GroundingConfidence;
  warnings: string[];
}

export interface ProcedureArtifactDraft extends ApplicationKnowledgeDraft {
  kind: "procedure" | "artifact";
  steps: string[];
}

export interface SkillDefinition {
  intent: string;
  preconditions: string[];
  inputs: string[];
  constraints: string[];
  expected_outcomes: string[];
  failure_signals: string[];
}

export interface GeneratedSkillDraft {
  name: string;
  definition: SkillDefinition;
  evidence_ordinals: number[];
  grounding_confidence: GroundingConfidence;
  warnings: string[];
}

export interface KnowledgePreviewEvidence {
  ordinal: number;
  evidence_type: string;
  content_text: string | null;
  content_json: Record<string, unknown> | null;
  source_locator: Record<string, unknown>;
  extractor_name: string;
  extractor_version: string;
}

export interface KnowledgePreviewIssue {
  code: string;
  message: string;
  source_locator: Record<string, unknown>;
  requires_fallback: boolean;
}

export interface KnowledgePreviewResponse {
  source: {
    name: string;
    original_url?: string | null;
    source_item_count: number;
    processed_item_count: number;
  };
  application_knowledge: ApplicationKnowledgeDraft[];
  artifacts: ProcedureArtifactDraft[];
  skills: GeneratedSkillDraft[];
  evidence: KnowledgePreviewEvidence[];
  extraction_issues: KnowledgePreviewIssue[];
}

export interface KnowledgeFileIndex {
  id: string;
  slug: string;
  title: string;
  description: string;
  token_count: number;
  sha256: string;
  version: number;
  status: "generated" | "approved" | "superseded";
}

export interface KnowledgeFileContent {
  slug: string;
  title: string;
  description: string;
  markdown: string;
  evidence: KnowledgePreviewEvidence[];
}

export interface IngestionSummary {
  id: string;
  workspace_id: string;
  name: string;
  source_name: string;
  status: "draft" | "approved";
  roles: string[];
  created_at: string;
  approved_at: string | null;
  knowledge_count: number;
  artifact_count: number;
  skill_count: number;
  issue_count: number;
  file_count?: number;
  processing_status?: "queued" | "processing" | "ready" | "failed";
  processing_error?: string | null;
  original_source_url?: string | null;
  processing_stage?: "queued" | "researching" | "generating" | "review" | "approved" | "failed";
  application_ids?: string[];
}

export interface IngestionEntry extends IngestionSummary {
  preview: KnowledgePreviewResponse;
  files?: KnowledgeFileIndex[];
}

export interface AllowedOrigin {
  scheme: string;
  hostname: string;
  port: number | null;
  include_subdomains: boolean;
}

export interface Target {
  id: string;
  application_id: string;
  name: string;
  environment: string;
  base_url: string;
  requires_auth: boolean;
  status: string;
  allowed_origins: AllowedOrigin[];
  scope_parent_id?: string | null;
}

export interface TargetAuthorization {
  id: string;
  target_id: string;
  created_by_user_id: string;
  authorized_by_user_id: string | null;
  status: string;
  authorization_basis: string;
  created_at: string;
  authorized_at: string | null;
  revoked_at: string | null;
  expires_at: string | null;
}

export interface TestRun {
  created_at?: string;
  test_number?: number | null;
  id: string;
  workspace_id: string;
  application_id: string;
  target_id: string;
  created_by_user_id: string;
  status: TestRunStatus;
  status_reason?: string | null;
  target_snapshot: Record<string, unknown>;
  configuration_snapshot: Record<string, unknown>;
  human_action_approvals_enabled?: boolean;
  run_kind?: string;
  harness_run_mode?: "read_only" | "standard";
}
export interface PersonaDefinitionSummary {
  persona_id: string;
  persona_type: string;
  name: string;
  enabled: boolean;
  yaml: string;
}

export interface BoardItem {
  item_id: string;
  state_id: string;
  case_id: string;
  role: string;
  name: string;
  status: string;
  blocker: string | null;
  attempts: number;
  page_url: string;
}
export interface RunBoard {
  run_id: string;
  run_status: string;
  run_kind: string;
  total: number;
  counts: Record<string, number>;
  items: BoardItem[];
}
export interface ArtifactAccess {
  artifact_id: string;
  artifact_type: string;
  content_type: string;
  url: string;
  expires_in_seconds: number;
}
export interface RunPreflight {
  ready: boolean;
  checks: { name: string; ready: boolean; reason: string | null; advisory?: boolean }[];
}
export interface Finding {
  id: string;
  severity: FindingSeverity;
  category: string;
  finding_kind?: string;
  verification_status?: string;
  title: string;
  summary: string;
  recommendation: string | null;
  status: string;
  journey_ids: string[];
  evidence: { step_ids: number[]; artifact_ids: string[] };
}

export interface RunResults {
  test_run_id: string;
  report: {
    id: string;
    version: number;
    status: string;
    executive_summary: string | null;
    payload: Record<string, unknown>;
    generated_at: string | null;
  };
  findings: Finding[];
}

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const FETCH_CEILING_MS = 30_000;

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const timeout = AbortSignal.timeout(FETCH_CEILING_MS);
  const signal = init?.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
  const response = await fetch(path, {
    ...init,
    signal,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-MarketTwin-Request": "1",
      ...init?.headers,
    },
  });

  return readResponse<T>(response);
}

export interface JourneyExecution {
  id: string;
  ordinal: number;
  persona_name: string;
  persona_perspective: string;
  mission_title: string;
  mission_objective: string;
  step_count: number;
  artifact_count: number;
  evidence_available: boolean;
  summary: string | null;
  success_criteria: string[];
  execution_id: string | null;
  runtime_name?: string | null;
  attempt_number: number | null;
  execution_status: string | null;
  outcome: string | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  result: Record<string, unknown> | null;
}

export interface JourneyDetail {
  journey: JourneyExecution;
  steps: { id: number; step_number: number; action_type: string; action_summary: string;
    observation_summary: string | null; status: string; started_at: string | null;
    completed_at: string | null }[];
  artifacts: { id: string; step_id: number | null; artifact_type: string;
    content_type: string; size_bytes: number | null; created_at: string; kind: string | null }[];
  findings: Finding[];
  next_after_step: number | null;
  artifacts_truncated: boolean;
}

async function requestForm<T>(path: string, form: FormData, signal?: AbortSignal): Promise<T> {
  const timeout = AbortSignal.timeout(FETCH_CEILING_MS);
  const response = await fetch(path, {
    method: "POST",
    credentials: "include",
    body: form,
    headers: { "X-MarketTwin-Request": "1" },
    signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
  });
  return readResponse<T>(response);
}

async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`;

    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
      else if (body.detail && typeof body.detail === "object" && "reason" in body.detail && typeof body.detail.reason === "string") message = body.detail.reason;
      else if (Array.isArray(body.detail)) {
        const issues = body.detail.flatMap((issue: unknown) => {
          if (!issue || typeof issue !== "object" || !("msg" in issue) || typeof issue.msg !== "string") return [];
          const location = "loc" in issue && Array.isArray(issue.loc)
            ? issue.loc.filter((part: unknown) => typeof part === "string" && part !== "body").join(" / ")
            : "";
          return [`${location ? `${location}: ` : ""}${issue.msg}`];
        });
        message = issues.length ? issues.slice(0, 4).join("; ") : "Check the form fields and try again.";
      }
    } catch {
      // Preserve the safe fallback when the response is not JSON.
    }

    throw new ApiError(message, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
export const RUN_PAGE_SIZE = 100;

function fetchRunPage(applicationId: string, offset = 0): Promise<TestRun[]> {
  return request<TestRun[]>(
    `/api/v1/applications/${applicationId}/test-runs?limit=${RUN_PAGE_SIZE}&offset=${offset}`,
  );
}

export const api = {
  listPersonas: (applicationId: string, signal?: AbortSignal) =>
    request<PersonaDefinitionSummary[]>(`/api/v1/applications/${applicationId}/personas`, { signal }),
  updatePersona: (applicationId: string, personaId: string, yaml: string) =>
    request<PersonaDefinitionSummary>(`/api/v1/applications/${applicationId}/personas/${personaId}`, {
      method: "PUT", headers: { "Content-Type": "application/json", "X-MarketTwin-Request": "1" },
      body: JSON.stringify({ yaml }),
    }),
  extendPark: (runId: string) =>
    request<{ parked_at: string; deadline_at: string }>(`/api/v1/test-runs/${runId}/park/extend`, {
      method: "POST", headers: { "X-MarketTwin-Request": "1" },
    }),
  stopRun: (runId: string) =>
    request<{ test_run_id: string; run_status: string; stop_requested_at: string }>(`/api/v1/test-runs/${runId}/stop`, {
      method: "POST", headers: { "X-MarketTwin-Request": "1" },
    }),
  getRunBoard: (runId: string, signal?: AbortSignal) =>
    request<RunBoard>(`/api/v1/test-runs/${runId}/board`, { signal, cache: "no-store" }),
  disableBoardItem: (runId: string, itemId: string) =>
    request<RunBoard>(`/api/v1/test-runs/${runId}/board/items/${itemId}/disable`, {
      method: "POST", headers: { "X-MarketTwin-Request": "1" },
    }),
  requestExecutionPause: (runId: string, browser: LiveBrowser) =>
    request<ExecutionPause>(`/api/v1/test-runs/${runId}/live-browser/pause`, {
      method: "POST", headers: { "X-MarketTwin-Request": "1" },
      body: JSON.stringify({ browser_session_id: browser.browser_session_id, generation: browser.generation }),
    }),
  resumeExecutionPause: (runId: string, pauseId: string) =>
    request<ExecutionPause>(`/api/v1/test-runs/${runId}/live-browser/pause/${pauseId}/resume`, {
      method: "POST", headers: { "X-MarketTwin-Request": "1" },
    }),
  getLiveGrant: (runId: string, browserSessionId?: string, signal?: AbortSignal) => {
    const query = browserSessionId ? `?browser_session_id=${browserSessionId}` : "";
    return request<LiveGrant>(`/api/v1/test-runs/${runId}/live-grant${query}`, {
      method: "POST", headers: { "X-MarketTwin-Request": "1" }, signal,
    });
  },
  getLiveExecution: (runId: string, cursor?: string, signal?: AbortSignal) => {
    const query = new URLSearchParams({ limit: "50" });
    if (cursor) query.set("cursor", cursor);
    return request<LiveExecution>(`/api/v1/test-runs/${runId}/live-browser?${query}`, { signal, cache: "no-store" });
  },
  ingestKnowledgeLink: (workspaceId: string, url: string, name: string, roles: string[]) =>
    request<IngestionEntry>(`/api/v1/workspaces/${workspaceId}/ingestion/link`, {
      method: "POST", body: JSON.stringify({ url, name, roles }),
    }),
  ingestKnowledge: (
    workspaceId: string,
    file: File,
    name: string,
    roles: string[],
    signal?: AbortSignal,
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("name", name);
    roles.forEach((role) => form.append("roles", role));
    return requestForm<IngestionEntry>(
      `/api/v1/workspaces/${workspaceId}/ingestion`,
      form,
      signal,
    );
  },
  listIngestion: (workspaceId: string, applicationId?: string) =>
    request<IngestionSummary[]>(`/api/v1/workspaces/${workspaceId}/ingestion${applicationId ? `?application_id=${encodeURIComponent(applicationId)}` : ""}`),
  getIngestion: (workspaceId: string, entryId: string) =>
    request<IngestionEntry>(`/api/v1/workspaces/${workspaceId}/ingestion/${entryId}`),
  getKnowledgeFile: (workspaceId: string, entryId: string, slug: string) =>
    request<KnowledgeFileContent>(`/api/v1/workspaces/${workspaceId}/ingestion/${entryId}/files/${encodeURIComponent(slug)}`),
  approveIngestion: (workspaceId: string, entryId: string) =>
    request<IngestionEntry>(`/api/v1/workspaces/${workspaceId}/ingestion/${entryId}/approve`, { method: "POST" }),
  deleteIngestion: (workspaceId: string, entryId: string) =>
    request<void>(`/api/v1/workspaces/${workspaceId}/ingestion/${entryId}`, { method: "DELETE" }),
  retryIngestion: (workspaceId: string, entryId: string) =>
    request<IngestionEntry>(`/api/v1/workspaces/${workspaceId}/ingestion/${entryId}/retry`, { method: "POST" }),
  renameIngestion: (workspaceId: string, entryId: string, name: string) =>
    request<IngestionEntry>(`/api/v1/workspaces/${workspaceId}/ingestion/${entryId}`, { method: "PATCH", body: JSON.stringify({ name }) }),
  attachIngestion: (workspaceId: string, entryId: string, applicationIds: string[]) =>
    request<IngestionEntry>(`/api/v1/workspaces/${workspaceId}/ingestion/${entryId}/applications`, { method: "PUT", body: JSON.stringify({ application_ids: applicationIds }) }),
  getKnowledgeSourceAccess: (workspaceId: string, entryId: string) =>
    request<{ url: string }>(`/api/v1/workspaces/${workspaceId}/ingestion/${entryId}/source-access`),
  kafkaHealth: (signal?: AbortSignal) =>
    request<{ status: "connected" | "unavailable"; outbox_relay_enabled: boolean }>(
      "/api/v1/health/kafka",
      { signal },
    ),
  getArtifactAccess: (
    runId: string,
    artifactId: string,
    signal?: AbortSignal,
  ) =>
    request<ArtifactAccess>(
      `/api/v1/test-runs/${runId}/artifacts/${artifactId}/access`,
      { signal },
    ),
  deleteRun: (id: string) =>
    request<void>(`/api/v1/test-runs/${id}`, { method: "DELETE" }),
  deleteTarget: (id: string) =>
    request<void>(`/api/v1/targets/${id}`, { method: "DELETE" }),
  deleteApplication: (id: string) =>
    request<void>(`/api/v1/applications/${id}`, { method: "DELETE" }),
  me: () => request<CurrentUser>("/api/v1/me"),
  login: (email: string) =>
    request<CurrentUser>("/api/v1/auth/local/login", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  listWorkspaces: () => request<Workspace[]>("/api/v1/workspaces"),
  listApplications: (workspaceId: string) =>
    request<Application[]>(`/api/v1/workspaces/${workspaceId}/applications`),
  getApplication: (applicationId: string) =>
    request<Application>(`/api/v1/applications/${applicationId}`),
  createApplication: (workspaceId: string, name: string, description: string) =>
    request<Application>(`/api/v1/workspaces/${workspaceId}/applications`, {
      method: "POST",
      body: JSON.stringify({ name, description: description || null }),
    }),
  listTargets: (applicationId: string) =>
    request<Target[]>(`/api/v1/applications/${applicationId}/targets`),
  getTarget: (targetId: string) =>
    request<Target>(`/api/v1/targets/${targetId}`),
  listScopeRevisions: (targetId: string) =>
    request<Target[]>(`/api/v1/targets/${targetId}/scope-revisions`),
  requestScopeRevision: (targetId: string, payload: { name: string; origins: string[]; request_basis: string }) =>
    request<Target>(`/api/v1/targets/${targetId}/scope-revisions`, {
      method: "POST", body: JSON.stringify(payload),
    }),
  createTarget: (
    applicationId: string,
    payload: {
      name: string;
      environment: string;
      base_url: string;
      requires_auth: boolean;
    },
  ) =>
    request<Target>(`/api/v1/applications/${applicationId}/targets`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getAuthorization: (targetId: string) =>
    request<TargetAuthorization>(`/api/v1/targets/${targetId}/authorization`),
  authorizeTarget: (targetId: string, authorizationBasis: string) =>
    request<TargetAuthorization>(`/api/v1/targets/${targetId}/authorization`, {
      method: "POST",
      body: JSON.stringify({
        confirm_authorized: true,
        authorization_basis: authorizationBasis,
      }),
    }),
  revokeAuthorization: (targetId: string) =>
    request<TargetAuthorization>(
      `/api/v1/targets/${targetId}/authorization/revoke`,
      { method: "POST" },
    ),
  listRunsPage: fetchRunPage,
  listRuns: async (applicationId: string): Promise<TestRun[]> => {
    // Aggregate callers need complete counts, while the tests page loads on demand.
    const runs = new Map<string, TestRun>();
    for (let offset = 0; ; offset += RUN_PAGE_SIZE) {
      const page = await fetchRunPage(applicationId, offset);
      for (const run of page) runs.set(run.id, run);
      if (page.length < RUN_PAGE_SIZE) return [...runs.values()];
    }
  },
  getRun: (runId: string, signal?: AbortSignal) =>
    request<TestRun>(`/api/v1/test-runs/${runId}`, { signal }),
  getRunPreflight: (runId: string) => request<RunPreflight>(`/api/v1/test-runs/${runId}/preflight`),
  getRunResults: (runId: string, signal?: AbortSignal) =>
    request<RunResults>(`/api/v1/test-runs/${runId}/results`, { signal }),
  getRunJourneys: (runId: string, signal?: AbortSignal) =>
    request<JourneyExecution[]>(`/api/v1/test-runs/${runId}/journeys`, { signal }),
  startRun: (runId: string) =>
    request<TestRun>(
      `/api/v1/test-runs/${runId}/start`,
      {
        method: "POST",
      },
    ),
  listHumanActions: (runId: string, signal?: AbortSignal) =>
    request<HumanAction[]>(`/api/v1/test-runs/${runId}/human-actions`, { signal }),
  claimHumanAction: (requestId: string) =>
    request<HumanLeaseGrant>(`/api/v1/human-actions/${requestId}/claim`, {
      method: "POST", headers: { "X-MarketTwin-Request": "1" },
      body: JSON.stringify({ lease_seconds: 30 }),
    }),
  renewHumanAction: (requestId: string, lease: HumanLeaseGrant) =>
    request<{ expires_at: string }>(`/api/v1/human-actions/${requestId}/renew`, {
      method: "POST", headers: { "X-MarketTwin-Request": "1" },
      body: JSON.stringify({ lease_id: lease.lease_id, lease_token: lease.lease_token, generation: lease.generation }),
    }),
  reconnectHumanAction: (requestId: string, lease: HumanLeaseGrant) =>
    request<{ expires_at: string; viewer_url: string; viewer_ticket: string }>(`/api/v1/human-actions/${requestId}/viewer`, {
      method: "POST", headers: { "X-MarketTwin-Request": "1" },
      body: JSON.stringify({ lease_id: lease.lease_id, lease_token: lease.lease_token, generation: lease.generation }),
    }),
  skipHumanAction: (requestId: string) =>
    request<{ id: string; status: "skipped" }>(`/api/v1/human-actions/${requestId}/skip`, {
      method: "POST", headers: { "X-MarketTwin-Request": "1" },
    }),
  releaseHumanAction: (requestId: string, lease: HumanLeaseGrant) =>
    request<{ generation: number }>(`/api/v1/human-actions/${requestId}/release`, {
      method: "POST", headers: { "X-MarketTwin-Request": "1" },
      body: JSON.stringify({ lease_id: lease.lease_id, lease_token: lease.lease_token, generation: lease.generation }),
    }),
  listActionApprovals: (runId: string, signal?: AbortSignal) =>
    request<ActionApproval[]>(`/api/v1/test-runs/${runId}/action-approvals`, { signal }),
  decideActionApproval: (approvalId: string, approved: boolean) =>
    request<{ id: string; status: string }>(`/api/v1/action-approvals/${approvalId}/decision`, {
      method: "POST", headers: { "X-MarketTwin-Request": "1" },
      body: JSON.stringify({ approved }),
    }),
  researchAppLink: (workspaceId: string, applicationId: string, targetId: string, researchUrl: string) =>
    request<{ map_id: string; status: string }>(
      `/api/v1/workspaces/${workspaceId}/applications/${applicationId}/targets/${targetId}/map-builds`,
      { method: "POST", body: JSON.stringify({ research_url: researchUrl }) },
    ),
  learnTask: (applicationId: string, targetId: string, name: string, pageUrl: string, expectedText: string) =>
    request<TestRun>(`/api/v1/applications/${applicationId}/test-runs`, {
      method: "POST",
      body: JSON.stringify({
        target_id: targetId, name, study_brief: "Learn a browser task by verifying its visible outcome.",
        run_kind: "explore_test", harness_run_mode: "read_only",
        learn_task: { page_url: pageUrl, expected_text: expectedText },
      }),
    }),
  createRun: (applicationId: string, targetId: string, testBrief: string, testingDepth: TestingDepth = "medium", name = "", runKind = "explore_test", authVerification?: { origin: string; marker_selector: string; expected_marker: string; role: string; account_reference: string; auth_only_origins?: string[] }, humanActionApprovals = false, syntheticFixtureApproval = false, sensitiveActionRules: unknown[] = [], authMode?: "required" | "optional", runtimeHumanAssistance = true, allowOffsiteNavigation = false, harnessRunMode?: "read_only" | "standard", approvedTestData: { key: string; value: string }[] = [], creationRequestId?: string) =>
    request<TestRun>(`/api/v1/applications/${applicationId}/test-runs`, {
      method: "POST",
        body: JSON.stringify({ creation_request_id: creationRequestId, target_id: targetId, study_brief: testBrief, run_kind: runKind, runtime_human_assistance: runtimeHumanAssistance, allow_offsite_navigation: allowOffsiteNavigation, testing_depth: testingDepth, ...(name.trim() ? { name: name.trim() } : {}), ...(authVerification ? { auth_verification: authVerification, ...(authMode ? { auth_mode: authMode } : {}) } : {}), ...(humanActionApprovals ? { human_action_approvals: true, sensitive_action_rules: sensitiveActionRules } : {}), ...(syntheticFixtureApproval ? { synthetic_fixture_approval: true } : {}), ...(harnessRunMode === "standard" ? { harness_run_mode: "standard", ...(approvedTestData.length ? { approved_test_data: approvedTestData } : {}) } : {}) }),
    }),
};

// --- Phase 3: skill library (doc 22 section 12.2) ---------------------------

// The six lifecycle states a skill version can sit in (the shared
// table in markettwin_shared/app_map_common.py); the words for them
// live in lib/status.ts under the "skill" source.
export type SkillLifecycleStatus =
  | "draft"
  | "replay_verified"
  | "active"
  | "suspect"
  | "quarantined"
  | "retired";

export interface AppMapSkillLibraryLine {
  skill_id: string;
  name: string;
  skill_kind: string;
  lifecycle_status: SkillLifecycleStatus | null;
  version_id: string | null;
  version_number: number | null;
  last_replay_result: string | null;
  last_replay_at: string | null;
  replay_count: number;
  heal_count: number;
  retired_reason: string | null;
  diagnosis_model_calls: number;
  status_reason: string | null;
  // The latest version's task-source kind: "document" marks a task
  // candidate (doc 29 section 3.4). The skills endpoint does not send
  // this yet, so it is undefined in practice and no line is classified
  // as a candidate until the endpoint exposes it.
  task_source_kind?: string | null;
}

export async function fetchAppMapSkills(
  base: string,
): Promise<{ items: AppMapSkillLibraryLine[] }> {
  return request<{ items: AppMapSkillLibraryLine[] }>(`${base}/app-map/skills`);
}

export interface AppMapSkillUsageVersion {
  version_id: string;
  version_number: number;
  lifecycle_status: SkillLifecycleStatus | null;
  replay_count: number;
  heal_count: number;
  last_replay_result: string | null;
  last_replay_at: string | null;
  retired_reason: string | null;
}

export interface AppMapSkillUsage {
  skill_id: string;
  total_model_calls: number;
  total_model_tokens: number;
  diagnosis_model_calls: number;
  events_by_kind: Record<string, number>;
  latest_version: AppMapSkillUsageVersion | null;
}

export async function fetchAppMapSkillUsage(
  base: string,
  skillId: string,
): Promise<AppMapSkillUsage> {
  return request<AppMapSkillUsage>(`${base}/app-map/skills/${skillId}/usage`);
}
