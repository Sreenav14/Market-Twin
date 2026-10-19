import { describe, expect, it } from "vitest";
import {
  asRecord,
  canDeleteTest,
  countValue,
  findingClassification,
  isConfirmedFinding,
  reportMetrics,
  reportVerdict,
  severityRank,
} from "./results";
import type { Finding, RunResults } from "./api";

function verdictReport(total: unknown, statusCounts: unknown, findings: Finding[] = []): RunResults {
  return {
    test_run_id: "run", findings,
    report: {
      id: "report", version: 1, status: "completed", executive_summary: null,
      generated_at: null, payload: { journeys: { total, status_counts: statusCounts } },
    },
  };
}

const productFinding: Finding = {
  id: "finding", severity: "high", category: "visual_criterion",
  finding_kind: "observed_product_issue", verification_status: "verified_visual",
  title: "A recorded issue", summary: "Evidence supports this issue", recommendation: null,
  status: "open", journey_ids: ["journey"], evidence: { step_ids: [1], artifact_ids: ["image"] },
};

describe("evidence-aware report verdict", () => {
  it.each([
    [undefined, undefined], [0, {}], [2, {}], [2, { completed: 3 }],
    [2, { completed: 2, failed: 1 }], [1.5, { completed: 1.5 }],
  ])("does not conclude coverage from absent, empty or inconsistent data: %s %s", (total, counts) => {
    const verdict = reportVerdict(verdictReport(total, counts));
    expect(verdict.label).toBe("Insufficient evidence");
    expect(verdict.tone).toBe("caution");
    expect(verdict.completionRate).toBeNull();
  });

  it("keeps unfinished journeys distinct from confirmed product issues", () => {
    const verdict = reportVerdict(verdictReport(3, { completed: 1, failed: 2 }));
    expect(verdict.tone).toBe("caution");
    expect(verdict.description).toContain("1 of 3 journeys completed");
    expect(verdict.completionRate).toBe(33);
    expect(verdict.title).toContain("No verified issues");
  });

  it("requires review for unverified observations even after complete execution", () => {
    const observation = { ...productFinding, verification_status: "unverified" };
    const verdict = reportVerdict(verdictReport(2, { completed: 2 }, [observation]));
    expect(verdict.label).toBe("Needs review");
    expect(verdict.description).toContain("1 unverified observation");
    expect(verdict.tone).toBe("caution");
  });

  it("keeps recorded execution issues visible even when all journeys completed", () => {
    const diagnostic = { ...productFinding, finding_kind: "test_execution_issue", verification_status: "unverified" };
    const verdict = reportVerdict(verdictReport(2, { completed: 2 }, [diagnostic]));
    expect(verdict.label).toBe("Review test coverage");
    expect(verdict.description).toContain("Execution issues were recorded");
  });

  it("limits a completed finding-free result to the recorded scope", () => {
    const verdict = reportVerdict(verdictReport(2, { completed: 2 }));
    expect(verdict.label).toBe("Recorded scope completed");
    expect(verdict.description).toContain("not a product quality guarantee");
    expect(verdict.title).toBe("No verified product issues recorded");
  });

  it.each([
    ["verified_visual", "Recorded visual checks"],
    ["verified_deterministic", "Recorded deterministic assertions"],
  ])("describes the actual %s verification path", (verification_status, description) => {
    const finding = { ...productFinding, verification_status };
    const verdict = reportVerdict(verdictReport(2, { completed: 2 }, [finding]));
    expect(verdict.tone).toBe("failed");
    expect(verdict.title).toBe("1 verified product issue");
    expect(verdict.description).toContain(description);
    expect(verdict.description).not.toContain("Independent assertion and visual");
  });

  it("retains verified findings when overall coverage is unavailable", () => {
    const verdict = reportVerdict(verdictReport(undefined, undefined, [productFinding]));
    expect(verdict.tone).toBe("failed");
    expect(verdict.description).toContain("coverage remains incomplete or unavailable");
  });
});

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
