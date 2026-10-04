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

  return readResponse<T>(response);
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
  startRun: (runId: string) =>
    request<TestRun>(
      `/api/v1/test-runs/${runId}/start`,
      {
        method: "POST",
      },
    ),
  createRun: (applicationId: string, targetId: string, testBrief: string, knowledgeIds: string[] = []) =>
    request<TestRun>(`/api/v1/applications/${applicationId}/test-runs`, {
      method: "POST",
      body: JSON.stringify({ target_id: targetId, study_brief: testBrief, knowledge_entry_ids: knowledgeIds }),
    }),
};
