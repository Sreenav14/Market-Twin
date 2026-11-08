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
  | "pending"
  | "running"
  | "worked"
  | "broken"
  | "could_not_check"
  | "not_checked"
  | "blocked"
  | "needs_human_login"
  | "owner_disabled";

export type ExecutionStatus =
  | "running"
  | "completed"
  | "timed_out"
  | "policy_blocked"
  | "cancelled"
  | "skipped"
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
  | "journeyExecution"
  | "execution"
  | "severity"
  | "infra"
  | "contractStage"
  | "finding"
  | "assertion"
  | "criterion"
  | "evaluation"
  | "lifecycle"
  | "mode"
  | "flow";

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
  pending: { word: "Pending", tone: "notchecked" },
  running: { word: "Running", tone: "info" },
  worked: { word: "Worked", tone: "works" },
  broken: { word: "Broken", tone: "broken" },
  could_not_check: { word: "Could not check", tone: "couldnot" },
  not_checked: { word: "Not checked", tone: "notchecked" },
  blocked: { word: "Blocked", tone: "couldnot" },
  needs_human_login: { word: "Needs your login", tone: "couldnot" },
  owner_disabled: { word: "Turned off by you", tone: "notchecked" },
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
  policy_blocked: { word: "Blocked by policy", tone: "couldnot" },
  cancelled: { word: "Cancelled", tone: "notchecked" },
  skipped: { word: "Skipped", tone: "notchecked" },
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

// Journey execution as rendered beside a journey (RunJourneysPage and its
// siblings): the execution words plus the two states a journey record can
// sit in before any execution exists.
export const JOURNEY_EXECUTION_STATUS: Record<string, StatusEntry> = {
  ...EXECUTION_STATUS,
  pending: { word: "Pending", tone: "notchecked" },
  "not started": { word: "Not started", tone: "notchecked" },
  not_started: { word: "Not started", tone: "notchecked" },
};

// Run-flow node statuses (RunFlowPanel): journey execution values plus the
// pipeline-only states the flow builder emits (test_run_results.py
// build_run_flow) — a node waiting on the human, on the report, or with
// nothing recorded.
export const FLOW_STATUS: Record<string, StatusEntry> = {
  ...JOURNEY_EXECUTION_STATUS,
  awaiting_human: { word: "Needs you", tone: "couldnot" },
  not_recorded: { word: "Not recorded", tone: "notchecked" },
  awaiting_report: { word: "Awaiting report", tone: "info" },
};

// The contract run's discovery stages (RunLayout header). These words were
// invented inline in the layout; they live here now so every status word in
// the product comes from this one file (examination X-1).
export const CONTRACT_STAGE_STATUS: Record<string, StatusEntry> = {
  discovering: { word: "Exploring", tone: "info" },
  awaiting_approval: { word: "Awaiting test approval", tone: "couldnot" },
  executing: { word: "Testing", tone: "info" },
  evaluating: { word: "Writing report", tone: "info" },
};

// Finding verification / classification words (FindingListItem,
// FindingDetailPage, RunFindingsPage, testerWork summaries).
export const FINDING_STATUS: Record<string, StatusEntry> = {
  unverified: { word: "Needs checking", tone: "couldnot" },
  "needs verification": { word: "Needs checking", tone: "couldnot" },
  verified_deterministic: { word: "Checked", tone: "works" },
  verified_visual: { word: "Checked", tone: "works" },
  "verified assertion issue": { word: "Checked issue", tone: "broken" },
  "visually verified issue": { word: "Visual observation", tone: "couldnot" },
  did_not_reproduce: { word: "Did not happen again", tone: "notchecked" },
  replay_unavailable: { word: "Could not check again", tone: "couldnot" },
  human_action_required: { word: "Needs you", tone: "couldnot" },
};

// Assertion outcomes on criterion rows (JourneyDetailPage).
export const ASSERTION_STATUS: Record<string, StatusEntry> = {
  satisfied: { word: "Check passed", tone: "works" },
  not_satisfied: { word: "Check did not pass", tone: "broken" },
  "not reported": { word: "Not reported", tone: "notchecked" },
};

// Visual-evidence criterion results (RunEvaluationPage derives
// passed/failed/unverified from the recorded criterion status).
export const CRITERION_STATUS: Record<string, StatusEntry> = {
  passed: { word: "Check passed", tone: "works" },
  failed: { word: "Check did not pass", tone: "broken" },
  unverified: { word: "Needs checking", tone: "couldnot" },
};

// Evaluation pipeline states.
export const EVALUATION_STATUS: Record<string, StatusEntry> = {
  evaluation_pending: { word: "Waiting for results", tone: "info" },
  evaluating: { word: "Checking results", tone: "info" },
};

// Lifecycle words for the records that are not runs, journeys, executions
// or findings: applications, targets, workspaces, knowledge sets, flow
// nodes. One map, so a word can never drift between those surfaces.
export const LIFECYCLE_STATUS: Record<string, StatusEntry> = {
  active: { word: "Active", tone: "works" },
  approved: { word: "Approved", tone: "works" },
  authorized: { word: "Authorized", tone: "works" },
  "not authorized": { word: "Not authorized", tone: "broken" },
  revoked: { word: "Revoked", tone: "broken" },
  expired: { word: "Expired", tone: "broken" },
  draft: { word: "Draft", tone: "notchecked" },
  frozen: { word: "Frozen", tone: "notchecked" },
  open: { word: "Open", tone: "couldnot" },
  pending: { word: "Pending", tone: "notchecked" },
  paused: { word: "Paused", tone: "couldnot" },
  ready: { word: "Ready", tone: "works" },
  processing: { word: "Processing", tone: "info" },
  researching: { word: "Researching", tone: "info" },
  generating: { word: "Generating", tone: "info" },
  review: { word: "Needs review", tone: "couldnot" },
  queued: { word: "Queued", tone: "info" },
  running: { word: "Running", tone: "info" },
  waiting: { word: "Waiting", tone: "info" },
  requested: { word: "Requested", tone: "info" },
  started: { word: "Started", tone: "info" },
  completed: { word: "Completed", tone: "works" },
  failed: { word: "Failed", tone: "broken" },
  healthy: { word: "Healthy", tone: "works" },
  unavailable: { word: "Not available", tone: "couldnot" },
  connected: { word: "Connected", tone: "works" },
};

// The execution-mode labels shown in run headers and pickers. One entry
// per mode the API can name; harness_v1 registered here when the mode
// shipped, so its header word comes from the same table as the others.
export const MODE_STATUS: Record<string, StatusEntry> = {
  discovery_contract_v1: { word: "Explore, approve and test", tone: "info" },
  deep_feature_v1: { word: "Feature checks", tone: "info" },
  legacy_persona: { word: "Exploratory testing", tone: "info" },
  harness_v1: { word: "Lead agent testing", tone: "info" },
};

const STATUS_MAPS: Record<StatusSource, Record<string, StatusEntry>> = {
  run: RUN_STATUS,
  harnessItem: HARNESS_ITEM_STATUS,
  journeyOutcome: {
    ...JOURNEY_OUTCOME_STATUS,
    "not recorded": { word: "Not recorded", tone: "notchecked" },
  },
  journeyExecution: JOURNEY_EXECUTION_STATUS,
  execution: EXECUTION_STATUS,
  severity: SEVERITY_STATUS,
  infra: INFRA_STATUS,
  contractStage: CONTRACT_STAGE_STATUS,
  finding: FINDING_STATUS,
  assertion: ASSERTION_STATUS,
  criterion: CRITERION_STATUS,
  evaluation: EVALUATION_STATUS,
  lifecycle: LIFECYCLE_STATUS,
  mode: MODE_STATUS,
  flow: FLOW_STATUS,
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
