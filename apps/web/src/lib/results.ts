import type {
  Finding,
  FindingSeverity,
  TestRun,
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

export function pendingDiscoveryCount(snapshot: Record<string, unknown>): number {
  const { pending } = asRecord(snapshot.discovery_frontier);
  return Array.isArray(pending) ? pending.filter((url) => typeof url === "string").length : 0;
}

export function partialExplorationLabel(run: Pick<TestRun, "status" | "configuration_snapshot">): string | null {
  const pending = terminalTestStatuses.has(run.status) ? pendingDiscoveryCount(run.configuration_snapshot) : 0;
  if (pending === 0) return null;
  return `Partial exploration ? ${pending} URL ${pending === 1 ? "candidate" : "candidates"} still queued`;
}

export function countValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null;
}

export function formatDate(value: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
