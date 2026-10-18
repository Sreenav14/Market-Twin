import type { JourneyDetail, JourneyExecution } from "./api";

export function journeyIdentity(journey: JourneyExecution, featureCaseMode = false) {
  const discovery = ["human_auth_bootstrap_v1", "browser_discovery_v1"].includes(journey.runtime_name ?? "")
    || journey.ordinal === 10000;
  const featureCase = !discovery && (featureCaseMode || journey.result?.mode === "deep_feature_v1");
  const caseId = typeof journey.result?.case_id === "string" ? journey.result.case_id : null;
  return { featureCase, caseId: discovery ? null : caseId,
    executor: discovery ? "Browser discovery" : featureCase ? "Deterministic browser executor" : journey.persona_name,
    ...(discovery ? { discovery: true } : {}),
  };
}

export function assertionObservation(summary: string | null) {
  if (!summary) return null;
  try {
    const value: unknown = JSON.parse(summary);
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const record = value as Record<string, unknown>;
    if (typeof record.assertion_id !== "string" || typeof record.oracle !== "string"
      || typeof record.status !== "string" || !("expected_value" in record)
      || !("observed_value" in record)) return null;
    const display = (item: unknown) => item === null ? "Not observed"
      : ["string", "boolean", "number"].includes(typeof item) ? String(item) : "Unavailable";
    return {
      id: record.assertion_id, oracle: record.oracle.replaceAll("_", " "), status: record.status,
      expected: display(record.expected_value), observed: display(record.observed_value),
      reason: typeof record.reason === "string" ? record.reason.replaceAll("_", " ") : null,
    };
  } catch { return null; }
}

export function initialJourneyStep(steps: JourneyDetail["steps"]) {
  return steps.find((step) => ["failed", "policy_blocked", "timed_out", "cancelled"].includes(step.status)
    || ["not_satisfied", "unverified"].includes(assertionObservation(step.observation_summary)?.status ?? ""))
    ?? steps[0];
}

export function journeyBlocker(journey: JourneyExecution, step?: JourneyDetail["steps"][number]) {
  if (journey.execution_status === "skipped")
    return "Not tested—human assistance skipped. Other independent work can continue.";
  let diagnostic = journey.result?.diagnostic;
  if (!diagnostic && step?.status === "policy_blocked" && step.observation_summary) {
    try { diagnostic = JSON.parse(step.observation_summary); } catch { /* Keep raw text out of diagnostics. */ }
  }
  const reason = diagnostic && typeof diagnostic === "object" && !Array.isArray(diagnostic)
    && "reason_code" in diagnostic && typeof diagnostic.reason_code === "string"
    ? diagnostic.reason_code : null;
  const detail = reason ?? step?.observation_summary ?? journey.error_message ?? "";
  if (reason === "origin_not_authorized") {
    const origin = diagnostic && typeof diagnostic === "object" && "requested_origin" in diagnostic
      && typeof diagnostic.requested_origin === "string" ? diagnostic.requested_origin : "the destination";
    return `Navigation to ${origin} is outside this run's approved scope. An authorized operator must approve a new exact-origin scope revision and start a new run. Logging in does not authorize this destination.`;
  }
  if (detail.includes("human_assistance_unverified")) return "Human assistance ended without a verified continuation. The executor did not resume the pending action. Review Human Assistance history.";
  if (detail.includes("absent_scope")) return "The required page region was not found. The scoped browser action could not run.";
  if (detail.includes("ambiguous_scope")) return "More than one page region matched. The executor stopped rather than choose an uncertain region.";
  if (detail.includes("absent_target")) return "The requested control was not found. The browser action could not run.";
  if (detail.includes("ambiguous_target")) return "More than one control matched. The executor stopped rather than choose an uncertain control.";
  if (step?.status === "policy_blocked" || journey.execution_status === "policy_blocked")
    return "Execution was blocked by a policy or human decision. Review the recorded reason and Human Assistance history.";
  if (step?.status === "timed_out" || journey.execution_status === "timed_out")
    return "Execution reached its time limit. Review the last recorded step and evidence.";
  if (step?.status === "failed" || journey.execution_status === "failed")
    return "The browser executor could not complete this journey. The recorded failure is an execution issue; it does not establish a product defect.";
  return null;
}
