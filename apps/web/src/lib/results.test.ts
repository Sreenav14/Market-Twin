import { describe, expect, it } from "vitest";
import { asRecord, countValue, reportMetrics, severityRank } from "./results";
import type { RunResults } from "./api";

describe("report data boundaries", () => {
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
    const results: RunResults = { test_run_id: "run", findings: [], report: { id: "report", version: 1, status: "completed", executive_summary: null, generated_at: null, payload: {} } };
    expect(reportMetrics(results)).toEqual({ journeyTotal: null, outcomes: [], statuses: [], criticalCount: 0, artifactCount: 0, deterministic: false });
  });
  it("puts unrecognized severity after the known severity levels", () => {
    expect(severityRank("critical")).toBeLessThan(severityRank("low"));
    expect(severityRank("future-value")).toBeGreaterThan(severityRank("info"));
  });
});
