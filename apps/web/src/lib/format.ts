import type { TestRun } from "./api";
import {
  ASSERTION_STATUS,
  EVALUATION_STATUS,
  EXECUTION_STATUS,
  FINDING_STATUS,
  JOURNEY_OUTCOME_STATUS,
  MODE_STATUS,
  RUN_STATUS,
} from "./status";

function words(map: Record<string, { word: string }>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(map).map(([key, entry]) => [key, entry.word]),
  );
}

// Prose labels for classifications, modes and pipeline states. Every word
// is derived from lib/status.ts — the one status vocabulary (examination
// X-1) — so a label printed in a sentence can never drift from the word
// the same state wears as a pill. The only entry owned here is a prose
// phrasing that is not a status ("Not available").
const statusLabels: Record<string, string> = {
  ...words(FINDING_STATUS),
  ...words(ASSERTION_STATUS),
  ...words(EVALUATION_STATUS),
  ...words(MODE_STATUS),
  inconclusive: JOURNEY_OUTCOME_STATUS.inconclusive.word,
  policy_blocked: EXECUTION_STATUS.policy_blocked.word,
  timed_out: EXECUTION_STATUS.timed_out.word,
  awaiting_human: RUN_STATUS.awaiting_human.word,
  unavailable: "Not available",
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
  const brief = textValue(configuration.study_brief, "");
  if (brief) return brief;
  return textValue(configuration.test_name, "Untitled test");
}

export function testReference(run: TestRun): string {
  return typeof run.test_number === "number" && run.test_number > 0
    ? `MT-${String(run.test_number).padStart(6, "0")}`
    : run.id.slice(0, 8);
}

export function testTitle(run: TestRun): string {
  return `${testReference(run)} · ${textValue(run.configuration_snapshot.test_name, "Test")}`;
}
