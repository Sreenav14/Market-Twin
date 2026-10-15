import { describe, expect, it } from "vitest";
import type { TargetAuthorization } from "./api";
import { isAuthorizationActive } from "./targetAuthorization";

const authorization: Pick<TargetAuthorization, "status" | "expires_at"> = {
  status: "authorized",
  expires_at: "2026-10-02T00:00:00Z",
};

describe("target authorization expiry", () => {
  it("treats an expired authorization as inactive", () => {
    expect(isAuthorizationActive(authorization, Date.parse("2026-10-03T00:00:00Z"))).toBe(false);
  });

  it("treats an unexpired authorization as active", () => {
    expect(isAuthorizationActive(authorization, Date.parse("2026-10-01T12:00:00Z"))).toBe(true);
  });

  it("supports authorized grants without an expiry", () => {
    expect(isAuthorizationActive({ ...authorization, expires_at: null }, Date.now())).toBe(true);
  });
});
