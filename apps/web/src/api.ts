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
  status: string;
  target_snapshot: Record<string, unknown>;
  configuration_snapshot: Record<string, unknown>;
}

export class ApiError extends Error {
  status: number;

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
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the fallback message when the response is not JSON.
    }

    throw new ApiError(message, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const api = {
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
  getTarget: (targetId: string) => request<Target>(`/api/v1/targets/${targetId}`),
  createTarget: (
    applicationId: string,
    payload: { name: string; environment: string; base_url: string; requires_auth: boolean },
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
    request<TargetAuthorization>(`/api/v1/targets/${targetId}/authorization/revoke`, {
      method: "POST",
    }),

  listRuns: (applicationId: string) =>
    request<TestRun[]>(`/api/v1/applications/${applicationId}/test-runs`),
  getRun: (runId: string) => request<TestRun>(`/api/v1/test-runs/${runId}`),
  createRun: (applicationId: string, targetId: string, studyBrief: string) =>
    request<TestRun>(`/api/v1/applications/${applicationId}/test-runs`, {
      method: "POST",
      body: JSON.stringify({ target_id: targetId, study_brief: studyBrief }),
    }),
};
