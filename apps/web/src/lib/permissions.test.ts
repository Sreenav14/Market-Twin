import { describe, expect, it } from "vitest";
import { canAuthorizeTarget, canManageLifecycle, canWriteWorkspace } from "./permissions";

describe("workspace permissions", () => {
  it("allows owner admin and member to write", () => { expect(canWriteWorkspace("owner")).toBe(true); expect(canWriteWorkspace("admin")).toBe(true); expect(canWriteWorkspace("member")).toBe(true); expect(canWriteWorkspace("viewer")).toBe(false); });
  it("limits target authorization to owner and admin", () => { expect(canAuthorizeTarget("owner")).toBe(true); expect(canAuthorizeTarget("admin")).toBe(true); expect(canAuthorizeTarget("member")).toBe(false); });
  it("limits lifecycle administration", () => { expect(canManageLifecycle("owner")).toBe(true); expect(canManageLifecycle("admin")).toBe(true); expect(canManageLifecycle("member")).toBe(false); });
});
