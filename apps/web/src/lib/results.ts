import type { Finding, RunResults } from "./api";

export const severityOrder = ["critical", "high", "medium", "low", "info"] as const;
export const terminalStatuses = new Set(["completed", "failed", "cancelled", "timed_out", "policy_blocked"]);
export function severityRank(value: string) {
  const rank = severityOrder.indexOf(value as typeof severityOrder[number]);
  return rank < 0 ? severityOrder.length : rank;
}
export function sortFindings(findings: Finding[], sort = "severity") {
  return [...findings].sort((a, b) => sort === "journeys"
    ? b.journey_ids.length - a.journey_ids.length || severityRank(a.severity) - severityRank(b.severity)
    : severityRank(a.severity) - severityRank(b.severity) || a.title.localeCompare(b.title));
}
export function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
export function countValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}
export function reportMetrics(results: RunResults) {
  const journeys = asRecord(results.report.payload.journeys);
  return {
    journeyTotal: countValue(journeys.total),
    outcomes: Object.entries(asRecord(journeys.outcome_counts)).filter((entry): entry is [string, number] => countValue(entry[1]) !== null),
    statuses: Object.entries(asRecord(journeys.status_counts)).filter((entry): entry is [string, number] => countValue(entry[1]) !== null),
    criticalCount: results.findings.filter(f => f.severity === "critical" || f.severity === "high").length,
    artifactCount: new Set(results.findings.flatMap(f => f.evidence.artifact_ids)).size,
    deterministic: results.report.payload.generator === "deterministic_evaluation_v1",
  };
}
export function formatDate(value: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
