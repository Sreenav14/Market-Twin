import type { TestRun } from "./api";

const statusLabels: Record<string, string> = {
  inconclusive: "Could not check", policy_blocked: "Could not check",
  unverified: "Needs checking", timed_out: "Time limit reached",
  awaiting_human: "Needs your help", human_action_required: "Needs your help",
  evaluation_pending: "Waiting for results", evaluating: "Checking results",
  verified_deterministic: "Checked", verified_visual: "Checked",
  did_not_reproduce: "Did not happen again", replay_unavailable: "Could not check again",
  satisfied: "Check passed", not_satisfied: "Check did not pass",
  unavailable: "Not available", legacy_persona: "Exploratory testing",
  deep_feature_v1: "Feature checks", discovery_contract_v1: "Explore, approve and test",
  "needs verification": "Needs checking",
  "verified assertion issue": "Checked issue",
  "visually verified issue": "Visual observation",
};

export function statusLabel(value: string): string {
  return statusLabels[value.toLowerCase()] ?? value.replaceAll("_", " ");
}

export function textValue(value: unknown, fallback = "—"): string {
  if (typeof value === "string" && value.trim().length > 0) return value;
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  return fallback;
}

/**
 * Return the user-facing Test name stored in the legacy `study_brief` snapshot field.
 *
 * `/runs` and `study_brief` remain compatibility identifiers in V1, but the product
 * language shown to users is consistently "Test".
 */
export function testBrief(configuration: Record<string, unknown>): string {
  return textValue(configuration.study_brief, "Untitled test");
}

export function testReference(run: TestRun): string {
  return typeof run.test_number === "number" && run.test_number > 0
    ? `MT-${String(run.test_number).padStart(6, "0")}`
    : run.id.slice(0, 8);
}

export function testTitle(run: TestRun): string {
  return `${testReference(run)} · ${textValue(run.configuration_snapshot.test_name, "Test")}`;
}
