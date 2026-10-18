import { expect, it } from "vitest";
import type { RunResults } from "./api";
import { emptyFindingsSummary } from "./emptyFindingsSummary";

function report(payload: Record<string, unknown>): RunResults {
  return { test_run_id: "run", findings: [], report: { id: "report", version: 1, status: "completed", generated_at: null, executive_summary: null, payload } };
}

it("separates failed inferred assertions from verified findings without changing outcomes", () => {
  const input = report({ mode: "deep_feature_v1", coverage: { planned: 2, passed: 1, failed_assertions: 2, blocked: 0, inconclusive: 0, not_run: 0 }, cases: [{ assertions: [{ origin: "inferred", status: "not_satisfied" }, { origin: "inferred", status: "not_satisfied" }] }] });
  const summary = emptyFindingsSummary(input);
  expect(summary.title).toBe("No verified findings");
  expect(summary.copy).toContain("Assertions failed");
  expect(summary.copy).toContain("independent confirmation");
  expect(summary.counts).toContainEqual(["Failed assertions", 2]);
  expect(summary.counts).toContainEqual(["Planner-inferred assertions", 2]);
  expect(input.findings).toEqual([]);
  expect((input.report.payload.coverage as Record<string, number>).passed).toBe(1);
});

it("reports blocked, inconclusive and skipped coverage without calling them passes", () => {
  const summary = emptyFindingsSummary(report({ mode: "deep_feature_v1", coverage: { passed: 1, failed_assertions: 0, inconclusive: 1, blocked: 2, not_run: 3, human_assistance_skipped: 1 } }));
  expect(summary.copy).toContain("These gaps are not passing checks");
  expect(summary.counts).toContainEqual(["Human assistance skipped", 1]);
  expect(summary.counts).toContainEqual(["Failed assertions", 0]);
});

it("does not invent missing coverage or treat malformed counts as zero", () => {
  expect(emptyFindingsSummary(report({})).counts).toEqual([]);
  const summary = emptyFindingsSummary(report({ mode: "deep_feature_v1", coverage: { planned: "2", passed: -1, failed_assertions: 0.5 }, cases: [null, { assertions: "invalid" }] }));
  expect(summary.counts).toEqual([]);
  expect(summary.copy).not.toContain("every check passed.");
});

it("preserves persona outcome distinctions in the empty findings explanation", () => {
  const summary = emptyFindingsSummary(report({ journeys: { total: 3, outcome_counts: { passed: 1, failed: 1, inconclusive: 1 } } }));
  expect(summary.featureCases).toBe(false);
  expect(summary.counts).toContainEqual(["Failed outcomes", 1]);
  expect(summary.counts).toContainEqual(["Inconclusive outcomes", 1]);
});
