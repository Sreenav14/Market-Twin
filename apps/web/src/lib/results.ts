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
      results.report.payload.generator === "deterministic_evaluation_v1" ||
      results.report.payload.mode === "deep_feature_v1",
  };
}

export function reportVerdict(results: RunResults, feature = results.report.payload.mode === "deep_feature_v1") {
  const metrics = reportMetrics(results);
  const statusCounts = new Map(metrics.statuses);
  const cases = asRecord(results.report.payload.coverage);
  const unit = feature ? "cases" : "journeys";
  const total = feature ? countValue(cases.planned) : metrics.journeyTotal;
  const completed = feature ? countValue(cases.executed)
    : metrics.statuses.length ? statusCounts.get("completed") ?? 0 : null;
  const caseCountsValid = ["planned", "executed", "passed", "failed_assertions", "blocked", "inconclusive", "not_run"]
    .every(key => typeof cases[key] === "number" && Number.isInteger(cases[key]) && (cases[key] as number) >= 0)
    && Number(cases.executed) <= Number(cases.planned)
    && Number(cases.passed) <= Number(cases.executed)
    && ["passed", "blocked", "inconclusive", "not_run"].reduce((sum, key) => sum + Number(cases[key]), 0) <= Number(cases.planned);
  const coverageKnown = total !== null && Number.isInteger(total) && total > 0
    && completed !== null && (feature ? caseCountsValid
      : metrics.statuses.every(([, count]) => Number.isInteger(count))
        && metrics.statuses.reduce((sum, [, count]) => sum + count, 0) <= total);
  const coverageComplete = coverageKnown && completed === total
    && (!feature || ["blocked", "inconclusive", "not_run"].every(key => cases[key] === 0));
  const completionRate = coverageKnown ? Math.round((completed / total) * 100) : null;
  const verified = results.findings.filter(isConfirmedFinding);
  const diagnostics = results.findings.filter(
    (finding) => findingClassification(finding) === "Test execution issue",
  );
  const observations = results.findings.filter(
    (finding) => !isConfirmedFinding(finding) && !diagnostics.includes(finding),
  );
  const coverage = { total, completed, completionRate, unit };

  if (verified.length) {
    const visual = verified.some((finding) => finding.verification_status === "verified_visual");
    const assertion = verified.some((finding) => finding.verification_status === "verified_deterministic");
    const method = visual && assertion ? "Recorded visual checks and deterministic assertions"
      : visual ? "Recorded visual checks" : "Recorded deterministic assertions";
    return {
      ...coverage, tone: "failed" as const, label: "Issues found",
      title: `${verified.length} verified product ${verified.length === 1 ? "issue" : "issues"}`,
      description: `${method} support these findings. ${coverageComplete
        ? "Conclusions apply to the recorded scope."
        : "Execution coverage remains incomplete or unavailable."}`,
    };
  }
  if (!coverageKnown) {
    return {
      ...coverage, tone: "caution" as const, label: "Insufficient evidence",
      title: "Coverage is not established",
      description: "No verified product issues were recorded. Missing or inconsistent completion data, or an empty test scope, prevents a conclusion about the tested product.",
    };
  }
  if (!coverageComplete || diagnostics.length || (feature && (cases.passed !== total || Number(cases.failed_assertions) > 0))) {
    return {
      ...coverage, tone: "caution" as const, label: "Review test coverage",
      title: "No verified issues · Test coverage needs review",
      description: `${completed} of ${total} ${feature ? "cases recorded as executed" : "journeys completed"}. ${diagnostics.length
        ? "Execution issues were recorded; inspect them before drawing conclusions."
        : feature ? "Review case verdicts and their assertions; blocked, inconclusive or unverified work is not a pass."
        : "Unfinished work limits the conclusions available from this test."}`,
    };
  }
  if (observations.length) {
    return {
      ...coverage, tone: "caution" as const, label: "Needs review",
      title: "No verified issues · Observations need review",
      description: `All ${total} ${unit} ${feature ? "were executed" : "completed"}, with ${observations.length} unverified ${observations.length === 1 ? "observation" : "observations"} to inspect. Completion alone does not establish that the product works correctly.`,
    };
  }
  return {
    ...coverage, tone: "clean" as const, label: "Recorded scope completed",
    title: "No verified product issues recorded",
    description: `All ${total} ${unit} ${feature ? "were evaluated" : "completed"} without recorded product findings or execution issues. This result applies only to the recorded scope and is not a product quality guarantee.`,
  };
}

export function formatDate(value: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
