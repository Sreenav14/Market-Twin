import type { RunResults } from "./api";
import { asRecord, countValue } from "./results";

export function emptyFindingsSummary(results: RunResults) {
  const payload = results.report.payload;
  const featureCases = payload.mode === "deep_feature_v1";
  const coverage = asRecord(payload.coverage);
  const counts: [string, number][] = [];
  const addCount = (label: string, value: unknown) => {
    const count = countValue(value);
    if (count !== null && Number.isInteger(count)) counts.push([label, count]);
  };
  if (featureCases) {
    for (const [key, label] of [["planned", "Cases planned"], ["passed", "Cases passed"], ["failed_assertions", "Failed assertions"], ["inconclusive", "Inconclusive cases"], ["blocked", "Blocked cases"], ["not_run", "Cases not run"], ["human_assistance_skipped", "Human assistance skipped"]]) {
      addCount(label, coverage[key]);
    }
    const assertions = Array.isArray(payload.cases) ? payload.cases.flatMap((entry: unknown) => {
      const recorded = asRecord(entry).assertions;
      return Array.isArray(recorded) ? recorded.map((assertion: unknown) => asRecord(assertion)) : [];
    }) : [];
    if (assertions.length) {
      addCount("Recorded assertions", assertions.length);
      addCount("Planner-inferred assertions", assertions.filter((assertion) => assertion.origin === "inferred").length);
    }
  } else {
    const journeys = asRecord(payload.journeys);
    addCount("Journeys evaluated", journeys.total);
    for (const [outcome, value] of Object.entries(asRecord(journeys.outcome_counts))) {
      const labels: Record<string, string> = { passed: "Passed outcomes", failed: "Failed outcomes", partial: "Partial outcomes", inconclusive: "Inconclusive outcomes", none: "Outcomes not recorded" };
      if (labels[outcome]) addCount(labels[outcome], value);
    }
  }
  const failed = countValue(coverage.failed_assertions);
  const incomplete = [coverage.inconclusive, coverage.blocked, coverage.not_run].some((value) => (countValue(value) ?? 0) > 0);
  return {
    title: "No verified findings",
    copy: featureCases && failed !== null && failed > 0
      ? "Assertions failed, but the recorded checks did not establish a verified product defect. Planner-inferred expectations require independent confirmation against approved requirements and evidence. Review the cases to see what failed and why."
      : featureCases && incomplete
        ? "Some cases were inconclusive, blocked or not run. These gaps are not passing checks. Review their recorded outcomes and evidence; no verified product finding was produced."
        : "No verified product finding was produced by the available checks. This does not mean every check passed or that the product is defect-free. Review the recorded outcomes, scope and evidence.",
    counts,
    featureCases,
  };
}
