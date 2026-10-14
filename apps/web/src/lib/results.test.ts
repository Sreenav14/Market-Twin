import { describe, expect, it } from "vitest";
import {
  asRecord,
  canDeleteTest,
  countValue,
  findingClassification,
  isConfirmedFinding,
  reportMetrics,
  severityRank,
} from "./results";
import type { Finding, RunResults } from "./api";

describe("report data boundaries", () => {
  it("keeps repeated and legacy claims out of confirmed issue counts", () => {
    const finding: Finding = {
      id: "claim", severity: "high", category: "cross_persona_pattern",
      finding_kind: "not_verified", verification_status: "unverified",
      title: "Repeated claim", summary: "Two personas reported failure", recommendation: null,
      status: "open", journey_ids: ["one", "two"], evidence: { step_ids: [7], artifact_ids: ["image"] },
    };
    expect(findingClassification(finding)).toBe("Needs Verification");
    expect(isConfirmedFinding(finding)).toBe(false);
    const results: RunResults = {
      test_run_id: "run", findings: [finding], report: {
        id: "report", version: 1, status: "completed", executive_summary: null,
        generated_at: null, payload: {},
      },
    };
    expect(reportMetrics(results).criticalCount).toBe(0);
    expect(isConfirmedFinding({ ...finding, finding_kind: undefined, verification_status: undefined })).toBe(false);
    const verified = { ...finding, category: "visual_criterion", finding_kind: "observed_product_issue", verification_status: "verified_visual" };
    expect(isConfirmedFinding(verified)).toBe(true);
    expect(isConfirmedFinding({ ...verified, evidence: { step_ids: [], artifact_ids: [] } })).toBe(false);
  });
  it("keeps absent or invalid metrics distinct from zero", () => {
    expect(countValue(undefined)).toBeNull();
    expect(countValue("3")).toBeNull();
    expect(countValue(Number.NaN)).toBeNull();
    expect(countValue(-1)).toBeNull();
    expect(countValue(0)).toBe(0);
    expect(asRecord(null)).toEqual({});
    expect(asRecord([])).toEqual({});
  });
  it("accepts sparse report payloads without inventing coverage", () => {
    const results: RunResults = {
      test_run_id: "run",
      findings: [],
      report: {
        id: "report",
        version: 1,
        status: "completed",
        executive_summary: null,
        generated_at: null,
        payload: {},
      },
    };
    expect(reportMetrics(results)).toEqual({
      journeyTotal: null,
      outcomes: [],
      statuses: [],
      criticalCount: 0,
      artifactCount: 0,
      deterministic: false,
    });
  });
  it("allows draft and terminal tests to be deleted, while protecting active tests", () => {
    expect(canDeleteTest("draft")).toBe(true);
    expect(canDeleteTest("failed")).toBe(true);
    expect(canDeleteTest("cancelled")).toBe(true);
    expect(canDeleteTest("completed")).toBe(true);
    expect(canDeleteTest("queued")).toBe(false);
    expect(canDeleteTest("planning")).toBe(false);
    expect(canDeleteTest("running")).toBe(false);
  });
  it("puts unrecognized severity after the known severity levels", () => {
    expect(severityRank("critical")).toBeLessThan(severityRank("low"));
    expect(severityRank("future-value")).toBeGreaterThan(severityRank("info"));
  });
});
