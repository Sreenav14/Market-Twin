import { describe, expect, it } from "vitest";
import type { TestRun } from "./api";
import { testBrief, testReference, testTitle } from "./format";

describe("test identity", () => {
  const run: TestRun = { id: "12345678-uuid", test_number: 42, workspace_id: "workspace", application_id: "app", target_id: "target", created_by_user_id: "user", status: "draft", target_snapshot: {}, configuration_snapshot: {
    test_name: "Pricing clarity", study_brief: "A long task describing the customer's goal",
  } };
  it("uses a short name and stable numeric reference while preserving the goal", () => {
    expect(testReference(run)).toBe("MT-000042");
    expect(testTitle(run)).toBe("MT-000042 · Pricing clarity");
    expect(testBrief(run.configuration_snapshot)).toContain("long task");
  });
  it("supports older test responses without showing their full goal as the heading", () => {
    expect(testTitle({ ...run, test_number: undefined, configuration_snapshot: { study_brief: "Long goal" } })).toBe("12345678 · Test");
  });
});
