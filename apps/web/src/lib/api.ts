export type TestRunStatus =
  | "draft"
  | "planning"
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type JourneyOutcome = "passed" | "failed" | "partial" | "inconclusive";
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
  id: string;
  workspace_id: string;
  application_id: string;
  target_id: string;
  created_by_user_id: string;
  status: TestRunStatus;
  target_snapshot: Record<string, unknown>;
  configuration_snapshot: Record<string, unknown>;
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


export interface ModelUsageSummary {
  attempts: number;
  completed: number;
  failed: number;
  rate_limited: number;
  unknown_usage_attempts: number;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  tool_input_tokens: number;
  provider_total_tokens: number;
  latency_ms: number;
}

export interface AgentSummary {
  id: string;
  role: "meta" | "persona" | "visual_verifier" | string;
  name: string;
  runtime: string;
  model_provider: string | null;
  model_name: string | null;
  journey_id: string | null;
  execution_id: string | null;
  persona_name: string | null;
  mission_name: string | null;
  created_at: string;
  usage: ModelUsageSummary;
}

export interface ModelInvocation {
  id: string;
  journey_id: string | null;
  execution_id: string | null;
  status: string;
  usage_status: string;
  invocation_sequence: number | null;
  attempt_number: number;
  model_provider: string | null;
  model_name: string | null;
  model_version: string | null;
  input_tokens: number | null;
  cached_input_tokens: number | null;
  output_tokens: number | null;
  reasoning_tokens: number | null;
  tool_input_tokens: number | null;
  provider_total_tokens: number | null;
  latency_ms: number | null;
  started_at: string;
  completed_at: string | null;
  error_code: string | null;
}

export interface AgentDetail extends AgentSummary {
  agent_version: string;
  snapshot_schema_version: number;
  template_id: string | null;
  template_version: string | null;
  model_configuration: Record<string, unknown>;
  base_instruction: string | null;
  effective_instruction: string | null;
  runtime_prompt: string | null;
  persona: Record<string, unknown> | null;
  mission: Record<string, unknown> | null;
  success_criteria: string[];
  tools: string[];
  policy_references: Record<string, unknown>;
  metadata: Record<string, unknown>;
  snapshot_sha256: string;
  yaml: string;
  invocations: ModelInvocation[];
}

export interface TestRunUsage {
  test_run_id: string;
  usage: ModelUsageSummary;
  by_role: Record<string, ModelUsageSummary>;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

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
  listRunAgents: (runId: string, signal?: AbortSignal) =>
    request<AgentSummary[]>("/api/v1/test-runs/" + runId + "/agents", { signal }),
  getRunAgent: (runId: string, snapshotId: string, signal?: AbortSignal) =>
    request<AgentDetail>(
      "/api/v1/test-runs/" + runId + "/agents/" + snapshotId,
      { signal },
    ),
  getRunUsage: (runId: string, signal?: AbortSignal) =>
    request<TestRunUsage>("/api/v1/test-runs/" + runId + "/usage", { signal }),
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
  createRun: (applicationId: string, targetId: string, testBrief: string) =>
    request<TestRun>(`/api/v1/applications/${applicationId}/test-runs`, {
      method: "POST",
      body: JSON.stringify({ target_id: targetId, study_brief: testBrief }),
    }),
};
