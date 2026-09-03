export type WorkspaceRole = "owner" | "admin" | "member" | "viewer" | string;

const WRITE_ROLES = new Set(["owner", "admin", "member"]);
const AUTHORIZATION_ROLES = new Set(["owner", "admin"]);

export function canWriteWorkspace(role: WorkspaceRole | undefined): boolean {
  return role !== undefined && WRITE_ROLES.has(role);
}

export function canAuthorizeTarget(role: WorkspaceRole | undefined): boolean {
  return role !== undefined && AUTHORIZATION_ROLES.has(role);
}

export function canManageLifecycle(role: WorkspaceRole | undefined): boolean {
  return role === "owner" || role === "admin";
}

export function roleLabel(role: WorkspaceRole | undefined): string {
  if (!role) return "Loading access";
  return `${role.charAt(0).toUpperCase()}${role.slice(1)} access`;
}
