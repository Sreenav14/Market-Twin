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

export interface Application {
  id: string;
  workspace_id: string;
  created_by_user_id: string;
  name: string;
  description: string | null;
  status: string;
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
    source_item_count: number;
    processed_item_count: number;
  };
  application_knowledge: ApplicationKnowledgeDraft[];
  artifacts: ProcedureArtifactDraft[];
  skills: GeneratedSkillDraft[];
  evidence: KnowledgePreviewEvidence[];
  extraction_issues: KnowledgePreviewIssue[];
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
  processing_status?: "queued" | "processing" | "ready" | "failed";
  processing_error?: string | null;
  application_ids?: string[];
}

export interface IngestionEntry extends IngestionSummary {
  preview: KnowledgePreviewResponse;
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
  test_number?: number | null;
  id: string;
  workspace_id: string;
  application_id: string;
  target_id: string;
  created_by_user_id: string;
  status: TestRunStatus;
  target_snapshot: Record<string, unknown>;
  configuration_snapshot: Record<string, unknown>;
  human_action_approvals_enabled?: boolean;
}
export interface ArtifactAccess {
  artifact_id: string;
  artifact_type: string;
  content_type: string;
  url: string;
  expires_in_seconds: number;
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

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
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
  const response = await fetch(path, {
    method: "POST",
    credentials: "include",
    body: form,
    signal,
  });
  return readResponse<T>(response);
}

async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`;

    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail))
        message = "Check the form fields and try again.";
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
export const api = {
  requestExecutionPause: (runId: string, browser: LiveBrowser) =>
    request<ExecutionPause>(`/api/v1/test-runs/${runId}/live-browser/pause`, {
      method: "POST", headers: { "X-MarketTwin-Request": "1" },
      body: JSON.stringify({ browser_session_id: browser.browser_session_id, generation: browser.generation }),
    }),
  resumeExecutionPause: (runId: string, pauseId: string) =>
    request<ExecutionPause>(`/api/v1/test-runs/${runId}/live-browser/pause/${pauseId}/resume`, {
      method: "POST", headers: { "X-MarketTwin-Request": "1" },
    }),
  getLiveExecution: (runId: string, cursor?: string, signal?: AbortSignal) => {
    const query = new URLSearchParams({ limit: "50" });
    if (cursor) query.set("cursor", cursor);
    return request<LiveExecution>(`/api/v1/test-runs/${runId}/live-browser?${query}`, { signal, cache: "no-store" });
  },
  getLiveBrowserFrame: async (runId: string, browser: LiveBrowser, signal: AbortSignal): Promise<Blob> => {
    const query = new URLSearchParams({ browser_session_id: browser.browser_session_id, generation: String(browser.generation) });
    const response = await fetch(`/api/v1/test-runs/${runId}/live-browser/frame?${query}`, {
      credentials: "include", cache: "no-store", signal,
    });
    if (!response.ok) throw new ApiError("The selected live browser is unavailable.", response.status);
    if (response.headers.get("content-type")?.split(";")[0].trim() !== "image/jpeg") {
      throw new ApiError("The live browser returned an invalid frame.", 502);
    }
    const frame = await response.blob();
    if (!frame.size || frame.size > 2 * 1024 * 1024) throw new ApiError("The live browser frame exceeded its limits.", 502);
    return frame;
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
  getWorkspace: (workspaceId: string) =>
    request<Workspace>(`/api/v1/workspaces/${workspaceId}`),
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
  listRuns: (applicationId: string) =>
    request<TestRun[]>(`/api/v1/applications/${applicationId}/test-runs`),
  getRun: (runId: string, signal?: AbortSignal) =>
    request<TestRun>(`/api/v1/test-runs/${runId}`, { signal }),
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
  cancelHumanAction: (requestId: string) =>
    request<{ id: string; status: string }>(`/api/v1/human-actions/${requestId}/cancel`, {
      method: "POST", headers: { "X-MarketTwin-Request": "1" },
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
  createRun: (applicationId: string, targetId: string, testBrief: string, knowledgeIds: string[] = [], testingDepth: TestingDepth = "medium", name = "", executionMode = "legacy_persona", authVerification?: { origin: string; marker_selector: string; expected_marker: string; role: string; account_reference: string; auth_only_origins?: string[] }, humanActionApprovals = false, syntheticFixtureApproval = false, sensitiveActionRules: unknown[] = [], authMode?: "required" | "optional", runtimeHumanAssistance = true) =>
    request<TestRun>(`/api/v1/applications/${applicationId}/test-runs`, {
      method: "POST",
        body: JSON.stringify({ target_id: targetId, study_brief: testBrief, runtime_human_assistance: runtimeHumanAssistance, knowledge_entry_ids: knowledgeIds, testing_depth: testingDepth, ...(name.trim() ? { name: name.trim() } : {}), ...(executionMode === "deep_feature_v1" ? { execution_mode: executionMode } : {}), ...(authVerification ? { auth_verification: authVerification, ...(authMode ? { auth_mode: authMode } : {}) } : {}), ...(humanActionApprovals ? { human_action_approvals: true, sensitive_action_rules: sensitiveActionRules } : {}), ...(syntheticFixtureApproval ? { synthetic_fixture_approval: true } : {}) }),
    }),
};
