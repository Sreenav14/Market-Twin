import type { TargetAuthorization } from "./api";

export function isAuthorizationActive(
  authorization: Pick<TargetAuthorization, "status" | "expires_at"> | null,
  now = Date.now(),
): boolean {
  return Boolean(
    authorization?.status === "authorized" &&
    (!authorization.expires_at || Date.parse(authorization.expires_at) > now),
  );
}
