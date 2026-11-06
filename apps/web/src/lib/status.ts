import type { FindingSeverity, JourneyOutcome, TestRunStatus } from "./api";

// The tone union is the codebase's real one: the four concept status
// tones from concept-tokens.css (--works / --broken / --couldnot /
// --notchecked, the StatusPill vocabulary) plus the lifecycle tone
// "info" used for in-progress run states.
export type StatusTone = "works" | "broken" | "couldnot" | "notchecked" | "info";

export interface StatusEntry {
  word: string;
  tone: StatusTone;
}

export type HarnessItemStatus =
  | "worked"
  | "broken"
  | "could_not_check"
  | "not_checked"
  | "observed_once"
  | "blocked"
  | "needs_human_login";

export type ExecutionStatus =
  | "running"
  | "completed"
  | "timed_out"
  | "timeout"
  | "policy_blocked"
  | "cancelled"
  | "failed";

// The infra entry set: the exact labels KafkaStatusBadge renders today
// (checking / unknown / connected / connected · relay off / unavailable),
// keyed so the component can adopt the map without changing its words.
export type InfraStatus =
  | "checking"
  | "unknown"
  | "connected"
  | "connected_relay_off"
  | "unavailable";

export type StatusSource =
  | "run"
  | "harnessItem"
  | "journeyOutcome"
  | "execution"
  | "severity"
  | "infra";

export const RUN_STATUS: Record<TestRunStatus, StatusEntry> = {
  draft: { word: "Draft", tone: "notchecked" },
  planning: { word: "Planning", tone: "info" },
  queued: { word: "Queued", tone: "info" },
  running: { word: "Running", tone: "info" },
  awaiting_human: { word: "Needs you", tone: "couldnot" },
  completed: { word: "Completed", tone: "works" },
  failed: { word: "Failed", tone: "broken" },
  cancelled: { word: "Cancelled", tone: "notchecked" },
};

export const HARNESS_ITEM_STATUS: Record<HarnessItemStatus, StatusEntry> = {
  worked: { word: "Worked", tone: "works" },
  broken: { word: "Broken", tone: "broken" },
  could_not_check: { word: "Could not check", tone: "couldnot" },
  not_checked: { word: "Not checked", tone: "notchecked" },
  observed_once: { word: "Seen once", tone: "couldnot" },
  blocked: { word: "Blocked", tone: "couldnot" },
  needs_human_login: { word: "Needs your login", tone: "couldnot" },
};

export const JOURNEY_OUTCOME_STATUS: Record<JourneyOutcome, StatusEntry> = {
  passed: { word: "Worked", tone: "works" },
  failed: { word: "Broken", tone: "broken" },
  partial: { word: "Partly done", tone: "couldnot" },
  inconclusive: { word: "Could not check", tone: "couldnot" },
};

export const EXECUTION_STATUS: Record<ExecutionStatus, StatusEntry> = {
  running: { word: "Running", tone: "info" },
  completed: { word: "Done", tone: "works" },
  timed_out: { word: "Timed out", tone: "couldnot" },
  timeout: { word: "Timed out", tone: "couldnot" },
  policy_blocked: { word: "Blocked by policy", tone: "couldnot" },
  cancelled: { word: "Cancelled", tone: "notchecked" },
  failed: { word: "Failed", tone: "broken" },
};

export const SEVERITY_STATUS: Record<FindingSeverity, StatusEntry> = {
  critical: { word: "Critical", tone: "broken" },
  high: { word: "High", tone: "broken" },
  medium: { word: "Medium", tone: "couldnot" },
  low: { word: "Low", tone: "info" },
  info: { word: "Info", tone: "info" },
};

export const INFRA_STATUS: Record<InfraStatus, StatusEntry> = {
  checking: { word: "Kafka checking", tone: "notchecked" },
  unknown: { word: "Kafka status unknown", tone: "couldnot" },
  connected: { word: "Kafka connected", tone: "works" },
  connected_relay_off: { word: "Kafka connected · relay off", tone: "couldnot" },
  unavailable: { word: "Kafka unavailable", tone: "couldnot" },
};

const STATUS_MAPS: Record<StatusSource, Record<string, StatusEntry>> = {
  run: RUN_STATUS,
  harnessItem: HARNESS_ITEM_STATUS,
  journeyOutcome: JOURNEY_OUTCOME_STATUS,
  execution: EXECUTION_STATUS,
  severity: SEVERITY_STATUS,
  infra: INFRA_STATUS,
};

export function statusEntry(source: StatusSource, value: string): StatusEntry {
  const entry = STATUS_MAPS[source][value];
  if (entry) return entry;
  if (import.meta.env.DEV) {
    throw new Error(`Unmapped ${source} status: ${value}`);
  }
  console.warn(`Unmapped ${source} status: ${value}`);
  return { word: value, tone: "notchecked" };
}
