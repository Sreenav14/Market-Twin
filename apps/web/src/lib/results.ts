import type {
  Finding,
  FindingSeverity,
  RunResults,
  TestRunStatus,
} from "./api";

export const severityOrder: readonly FindingSeverity[] = [
  "critical",
  "high",
  "medium",
  "low",
  "info",
];
export const terminalTestStatuses = new Set<TestRunStatus>([
  "completed",
  "failed",
  "cancelled",
]);
export const deletableTestStatuses = new Set<TestRunStatus>([
  "draft",
  "completed",
  "failed",
  "cancelled",
]);

export function canDeleteTest(status: TestRunStatus) {
  return deletableTestStatuses.has(status);
}

export function severityRank(value: string) {
  const rank = severityOrder.indexOf(value as FindingSeverity);
  return rank < 0 ? severityOrder.length : rank;
}

export function sortFindings(findings: Finding[], sort = "severity") {
  return [...findings].sort((a, b) =>
    sort === "journeys"
      ? b.journey_ids.length - a.journey_ids.length ||
        severityRank(a.severity) - severityRank(b.severity)
      : severityRank(a.severity) - severityRank(b.severity) ||
        a.title.localeCompare(b.title),
  );
}

export function findingClassification(finding: Finding) {
  if (finding.finding_kind === "observed_product_issue" &&
    finding.verification_status === "verified_deterministic" &&
    finding.evidence.step_ids.length > 0 && finding.evidence.artifact_ids.length > 0)
    return "Verified assertion issue";
  if (
    finding.finding_kind === "observed_product_issue" &&
    finding.verification_status === "verified_visual" &&
    finding.evidence.artifact_ids.length > 0
  ) return "Visually verified issue";
  if (
    finding.finding_kind === "test_execution_issue" ||
    ["policy", "execution_reliability"].includes(finding.category)
  ) return "Test execution issue";
  return "Needs Verification";
}

export function isConfirmedFinding(finding: Finding) {
  return ["Visually verified issue", "Verified assertion issue"].includes(findingClassification(finding));
}

export function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function countValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null;
}

export function reportMetrics(results: RunResults) {
  const journeys = asRecord(results.report.payload.journeys);
  return {
    journeyTotal: countValue(journeys.total),
    outcomes: Object.entries(asRecord(journeys.outcome_counts)).filter(
      (entry): entry is [string, number] => countValue(entry[1]) !== null,
    ),
    statuses: Object.entries(asRecord(journeys.status_counts)).filter(
      (entry): entry is [string, number] => countValue(entry[1]) !== null,
    ),
    criticalCount: results.findings.filter(
      (f) => isConfirmedFinding(f) && (f.severity === "critical" || f.severity === "high"),
    ).length,
    artifactCount: new Set(
      results.findings.flatMap((f) => f.evidence.artifact_ids),
    ).size,
    deterministic:
      results.report.payload.generator === "deterministic_evaluation_v1",
  };
}

export function formatDate(value: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
